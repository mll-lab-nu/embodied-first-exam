"""Actuator-only hamburger dynamics and an observable released-stack predicate."""

from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path

os.environ.setdefault("MUJOCO_GL", "egl")

import mujoco
import numpy as np

from scene import LAYER_HALF_HEIGHT, build, hands

CONFIG_PATH = Path(__file__).with_name("task.json")


class Session:
    """One frozen hamburger episode. ``hand`` is ``sharpa`` (default) or ``wuji``; when omitted, the
    ``DEXHAND_HAND`` environment variable selects it. Graders pass the hand recorded with the trajectory."""

    def __init__(self, task="assemble_hamburger", instance=None, asset_dir=None, config=None, hand=None):
        if task != "assemble_hamburger":
            raise ValueError("Unknown task: " + str(task))
        self.config = json.loads(Path(instance or CONFIG_PATH).read_text()) if config is None else config
        self.spec = self.config
        self.task = task
        self.hand = hands.selected(hand)
        self.hand_info = hands.info(self.hand)
        self.model, self.xml = build(self.config, asset_dir, self.hand)
        self.data = mujoco.MjData(self.model)
        self.action_dim = self.model.nu
        self.initial_targets = np.asarray(self.config["initial_targets"][self.hand], dtype=float)
        if self.initial_targets.shape != (self.action_dim,):
            raise ValueError(f"initial_targets[{self.hand}] must have {self.action_dim} values")
        self.control_dt = self.config["control_dt"]
        self.substeps = round(self.control_dt / self.config["physics_dt"])
        self.qadr = self.model.jnt_qposadr[self.model.actuator_trnid[:, 0]]
        self.joint_names = [self.model.joint(int(j)).name for j in self.model.actuator_trnid[:, 0]]
        self.actuator_names = [self.model.actuator(i).name for i in range(self.model.nu)]
        self.names = self.config["recipe"]
        self.bodies = {name: self.model.body(name).id for name in self.names}
        self.owner = {}
        for bid in range(1, self.model.nbody):
            parent = bid
            while parent:
                name = self.model.body(parent).name
                if name in self.bodies:
                    self.owner[bid] = name
                    break
                if name == "wrist_stage":
                    self.owner[bid] = "hand"
                    break
                parent = int(self.model.body_parentid[parent])
        self.bend_jids = [i for i in range(self.model.njnt) if "_bend_" in (self.model.joint(i).name or "")]
        self.bend_qadr = self.model.jnt_qposadr[self.bend_jids]
        self.bend_owner = [self.model.joint(i).name.split("_bend_")[0] for i in self.bend_jids]
        # Fail-fast invariants: every ingredient body (wings included) stays above the table top and inside
        # the declared workspace box, and no ingredient geometry ever touches the table or the floor.
        self.ingredient_body_ids = np.asarray(
            sorted(b for b, owner in self.owner.items() if owner in self.names), dtype=int
        )
        self.ingredient_body_names = [self.owner[b] for b in self.ingredient_body_ids]
        geom_owner = [self.owner.get(int(self.model.geom_bodyid[g]), "world") for g in range(self.model.ngeom)]
        self.ingredient_geom = np.asarray([owner in self.names for owner in geom_owner], dtype=bool)
        self.ground_geom = np.zeros(self.model.ngeom, dtype=bool)
        self.ground_geom[[self.model.geom("table").id, self.model.geom("floor").id]] = True
        workspace = self.config["workspace"]
        self.workspace_lo = np.asarray(workspace["min"], dtype=float)
        self.workspace_hi = np.asarray(workspace["max"], dtype=float)
        self.renderer = None
        self.reset()

    def reset(self):
        mujoco.mj_resetData(self.model, self.data)
        self.data.qpos[self.qadr] = self.initial_targets
        self.data.ctrl[:] = self.initial_targets
        mujoco.mj_forward(self.model, self.data)
        self.steps = 0
        self.released_hold = 0
        self.success = False
        self.failure = None
        self.failure_detail = None
        self.peak_bend = 0.0
        self.actions = []
        self.initial_sha = self.state_sha()

    def hold_action(self):
        return self.data.ctrl.copy()

    @property
    def done(self):
        return bool(self.success or self.failure)

    def status(self):
        f = self.features()
        return {
            **f,
            "done": self.done,
            "stage": f["aligned_layers"],
            "total_stages": len(self.names),
            "reason": "success" if self.success else (self.failure or ""),
            "failed": bool(self.failure),
            "hand": self.hand,
        }

    def cameras(self):
        return ["overview", "closeup"]

    def step(self, action):
        values = np.asarray(action, dtype=np.float64)
        if values.shape != (self.action_dim,) or not np.isfinite(values).all():
            raise ValueError(f"Expected {self.action_dim} finite actuator targets")
        lo, hi = self.model.actuator_ctrlrange.T
        if np.any(values < lo - 1e-7) or np.any(values > hi + 1e-7):
            raise ValueError("Actuator targets exceed native joint bounds")
        if self.done:
            # The episode ended at the first success or failure; later rows are not executed.
            return self.features()
        self.data.ctrl[:] = np.clip(values, lo, hi)
        self.actions.append(self.data.ctrl.copy())
        for substep in range(self.substeps):
            mujoco.mj_step(self.model, self.data)
            bend = np.abs(self.data.qpos[self.bend_qadr])
            self.peak_bend = max(self.peak_bend, float(np.max(bend, initial=0)))
            if any(
                self.data.warning[w].number
                for w in (
                    mujoco.mjtWarning.mjWARN_BADQPOS,
                    mujoco.mjtWarning.mjWARN_BADQVEL,
                    mujoco.mjtWarning.mjWARN_BADQACC,
                )
            ):
                self.failure = "unstable_physics"
                self.failure_detail = {"control": self.steps, "substep": substep}
                break
            violation = self.invariant_violation(bend)
            if violation:
                # Fail fast: the episode ends at the physics substep that broke an invariant.
                self.failure, ingredient = violation
                self.failure_detail = {"ingredient": ingredient, "control": self.steps, "substep": substep}
                break
        self.steps += 1
        mujoco.mj_forward(self.model, self.data)
        f = self.features()
        complete = (
            f["aligned_layers"] == 6
            and f["ordered"]
            and f["adjacent_contacts"] == 5
            and f["base_on_plate"]
            and f["hand_contacts"] == 0
            and f["max_tilt_rad"] <= self.config["tilt_tolerance_rad"]
            and f["max_linear_speed_m_s"] <= self.config["linear_speed_tolerance_m_s"]
            and f["max_angular_speed_rad_s"] <= self.config["angular_speed_tolerance_rad_s"]
            and self.peak_bend <= self.config["max_bend_rad"]
            and not self.failure
        )
        self.released_hold = self.released_hold + 1 if complete else 0
        self.success = self.released_hold >= self.config["released_hold_steps"]
        if self.steps >= self.config["max_steps"] and not self.success and not self.failure:
            self.failure = "episode_budget"
            self.failure_detail = {"control": self.steps}
        return self.features()

    def invariant_violation(self, bend=None):
        """Return (reason, ingredient) for the first broken episode invariant, else None.

        Checked after every 2 ms physics substep. Any violation is terminal: an ingredient that left the
        table top, its support or the workspace cannot be recovered by later actions.
        """
        bend = np.abs(self.data.qpos[self.bend_qadr]) if bend is None else bend
        positions = self.data.xpos[self.ingredient_body_ids]
        below = np.flatnonzero(positions[:, 2] < self.config["table_z"])
        if below.size:
            return "ingredient_below_table", self.ingredient_body_names[below[0]]
        outside = np.flatnonzero(np.any((positions < self.workspace_lo) | (positions > self.workspace_hi), axis=1))
        if outside.size:
            return "ingredient_left_workspace", self.ingredient_body_names[outside[0]]
        count = self.data.ncon
        if count:
            pairs = self.data.contact.geom[:count]
            active = self.data.contact.efc_address[:count] >= 0
            first, second = pairs[:, 0], pairs[:, 1]
            hit = active & (
                (self.ingredient_geom[first] & self.ground_geom[second])
                | (self.ingredient_geom[second] & self.ground_geom[first])
            )
            if hit.any():
                index = int(np.flatnonzero(hit)[0])
                geom = int(first[index] if self.ingredient_geom[first[index]] else second[index])
                return "ingredient_dropped", self.owner[int(self.model.geom_bodyid[geom])]
        over = np.flatnonzero(bend > self.config["max_bend_rad"])
        if over.size:
            return "bend_limit_exceeded", self.bend_owner[over[0]]
        return None

    def features(self):
        target = np.asarray(self.config["target_xy"])
        positions = {name: self.data.xpos[bid].copy() for name, bid in self.bodies.items()}
        offsets = {name: float(np.linalg.norm(pos[:2] - target)) for name, pos in positions.items()}
        tilt = {name: float(np.arccos(np.clip(self.data.xmat[bid, 8], -1, 1))) for name, bid in self.bodies.items()}
        contacts = set()
        hand_contacts = 0
        base_on_plate = False
        source_contacts = set()
        fingers = {name: set() for name in self.names}
        for c in self.data.contact[: self.data.ncon]:
            if c.efc_address < 0:
                continue
            g1, g2 = int(c.geom1), int(c.geom2)
            b1, b2 = int(self.model.geom_bodyid[g1]), int(self.model.geom_bodyid[g2])
            a, b = self.owner.get(b1, "world"), self.owner.get(b2, "world")
            if a in self.names and b in self.names and a != b:
                contacts.add(frozenset((a, b)))
            if "hand" in (a, b) and (a in self.names or b in self.names):
                hand_contacts += 1
                ingredient = b if a == "hand" else a
                hand_geom = self.model.geom(g1 if a == "hand" else g2).name or ""
                fingers[ingredient].update(f for f in ("thumb", "index", "middle", "ring", "pinky") if f in hand_geom)
            n1, n2 = self.model.geom(g1).name, self.model.geom(g2).name
            if (a == "bottom_bun" and n2 == "serving_plate") or (b == "bottom_bun" and n1 == "serving_plate"):
                base_on_plate = True
            for ingredient, other in ((a, n2), (b, n1)):
                if ingredient in self.names and other.endswith("_prep_support"):
                    source_contacts.add(ingredient)
        linear, angular = [], []
        velocity = np.empty(6)
        for bid, owner in self.owner.items():
            if owner in self.names:
                mujoco.mj_objectVelocity(self.model, self.data, mujoco.mjtObj.mjOBJ_BODY, bid, velocity, 0)
                angular.append(float(np.linalg.norm(velocity[:3])))
                linear.append(float(np.linalg.norm(velocity[3:])))
        heights = [float(positions[n][2]) for n in self.names]
        adjacent = sum(frozenset((a, b)) in contacts for a, b in zip(self.names, self.names[1:]))
        return {
            "positions": {name: p.tolist() for name, p in positions.items()},
            "aligned_layers": sum(v <= self.config["alignment_tolerance_m"] for v in offsets.values()),
            "max_alignment_error_m": max(offsets.values()),
            "alignment_errors_m": offsets,
            "ordered": all(a < b for a, b in zip(heights, heights[1:])),
            "adjacent_contacts": adjacent,
            "base_on_plate": base_on_plate,
            "source_contacts": sorted(source_contacts),
            "hand_contacts": hand_contacts,
            "finger_contacts": {name: sorted(values) for name, values in fingers.items()},
            "max_tilt_rad": max(tilt.values()),
            "max_linear_speed_m_s": max(linear, default=0),
            "max_angular_speed_rad_s": max(angular, default=0),
            "peak_bend_rad": self.peak_bend,
            "released_hold_steps": self.released_hold,
            "success": self.success,
            "failure": self.failure,
            "failure_detail": self.failure_detail,
            "steps": self.steps,
        }

    def save_trajectory(self, actions, path):
        """Write the privileged deliverable: ``actions`` plus this session's ``hand`` and ``task``."""
        hands.write_trajectory(path, actions, hand=self.hand, task=self.task)

    def replay(self, actions):
        """Reset, execute rows until the episode ends (success or failure) or the rows run out."""
        self.reset()
        for action in np.asarray(actions, dtype=np.float64):
            self.step(action)
            if self.done:
                break
        return self.status()

    def stack_top(self, through):
        name = self.names[through]
        return float(self.data.xpos[self.bodies[name], 2] + LAYER_HALF_HEIGHT[name])

    def state_sha(self):
        state = np.empty(mujoco.mj_stateSize(self.model, mujoco.mjtState.mjSTATE_INTEGRATION))
        mujoco.mj_getState(self.model, self.data, state, mujoco.mjtState.mjSTATE_INTEGRATION)
        digest = hashlib.sha256(state.astype("<f8").tobytes())
        digest.update(json.dumps(self.config, sort_keys=True).encode())
        digest.update(self.hand.encode())
        return digest.hexdigest()

    def render_frame(self, camera="overview", width=640, height=480, shadows=True):
        if self.renderer is not None and (self.renderer.width != width or self.renderer.height != height):
            self.close()
        if self.renderer is None:
            self.renderer = mujoco.Renderer(self.model, height=height, width=width)
        self.renderer.update_scene(self.data, camera=camera)
        self.renderer.scene.flags[mujoco.mjtRndFlag.mjRND_SHADOW] = shadows
        return self.renderer.render().copy()

    def close(self):
        if self.renderer:
            self.renderer.close()
            self.renderer = None
