"""Actuator-only envelope letter insertion dynamics with a strict state-derived verdict."""

from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path

os.environ.setdefault("MUJOCO_GL", "egl")

import mujoco
import numpy as np

from checker import STAGES, Checker
from scene import build, hands

TASK = "envelope_letter_insert"
CONFIG_PATH = Path(__file__).with_name("task.json")
# task.json entries that are prose or presentation only; state_sha hashes every other (physics/predicate) entry, so
# editing texts or camera framing never changes the evidence hashes.
NON_PHYSICS_KEYS = {"schema_version", "title", "description", "instruction", "modeling", "mechanism", "category",
                    "difficulty", "robot", "cameras"}


class Session:
    """One frozen envelope-letter episode. ``hand`` is ``sharpa`` (default) or ``wuji``; when omitted, the
    ``DEXHAND_HAND`` environment variable selects it. Graders pass the hand recorded with the trajectory."""

    def __init__(self, task=TASK, instance=None, asset_dir=None, config=None, hand=None):
        if task != TASK:
            raise ValueError("Unknown task: " + str(task))
        self.config = json.loads(Path(instance or CONFIG_PATH).read_text()) if config is None else config
        self.spec = self.config
        self.task = task
        self.hand = hands.selected(hand)
        self.hand_info = hands.info(self.hand)
        self.robot = self.hand_info["robot"] + "-floating"
        if self.config.get("rig") == "marvin":  # wave 3: the hand on the right arm of the Marvin dual-arm robot
            self.robot = "marvin-bimanual-sharpa-wave" if self.hand == "sharpa" else "marvin-bimanual-wuji-hand-2.2"
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
        self.tcp_body = "right_hand_C_MC"
        self.owner = {}
        for bid in range(1, self.model.nbody):
            parent = bid
            while parent:
                name = self.model.body(parent).name
                if name in ("letter", "envelope"):
                    self.owner[bid] = name
                    break
                if name == "wrist_stage":
                    self.owner[bid] = "hand"
                    break
                parent = int(self.model.body_parentid[parent])
        self.checker = Checker(self.model, self.config, self.owner)
        self.hold_steps = int(self.config["checker"]["hold_steps"])
        self.renderer = None
        self.reset()

    # ------------------------------------------------------------------ episode
    def reset(self):
        mujoco.mj_resetData(self.model, self.data)
        self.data.qpos[self.qadr] = self.initial_targets
        self.data.ctrl[:] = self.initial_targets
        mujoco.mj_forward(self.model, self.data)
        self.steps = 0
        self.stage = 0
        self.stage_steps = {}
        self.hold = 0
        self.success = False
        self.failure = None
        self.failure_detail = None
        self.actions = []
        self.initial_sha = self.state_sha()

    def hold_action(self):
        return self.data.ctrl.copy()

    @property
    def done(self):
        return bool(self.success or self.failure)

    def cameras(self):
        return list(self.config["cameras"])

    def step(self, action):
        values = np.asarray(action, dtype=np.float64)
        if values.shape != (self.action_dim,) or not np.isfinite(values).all():
            raise ValueError(f"Expected {self.action_dim} finite actuator targets")
        lo, hi = self.model.actuator_ctrlrange.T
        if np.any(values < lo - 1e-6) or np.any(values > hi + 1e-6):
            raise ValueError("Actuator targets exceed native joint bounds")
        if self.done:
            # The episode ended at the first success or failure; later rows are not executed.
            return self.features()
        self.data.ctrl[:] = np.clip(values, lo, hi)
        self.actions.append(self.data.ctrl.copy())
        for substep in range(self.substeps):
            mujoco.mj_step(self.model, self.data)
            if any(
                self.data.warning[w].number
                for w in (
                    mujoco.mjtWarning.mjWARN_BADQPOS,
                    mujoco.mjtWarning.mjWARN_BADQVEL,
                    mujoco.mjtWarning.mjWARN_BADQACC,
                )
            ) or not np.isfinite(self.data.qpos).all():
                self.failure = "unstable_physics"
                self.failure_detail = {"control": self.steps, "substep": substep}
                break
            violation = self.checker.violation(self.data)
            if violation:
                # Fail fast: the episode ends at the physics substep that broke an invariant.
                self.failure, obj = violation
                self.failure_detail = {"object": obj, "control": self.steps, "substep": substep}
                break
        self.steps += 1
        mujoco.mj_forward(self.model, self.data)
        if self.failure:
            return self.features()
        geo = self.checker.geometry(self.data)
        if self.stage == 0 and geo["at_mouth"]:
            self.stage = 1
            self.stage_steps[STAGES[0]] = self.steps
        if self.stage == 1 and geo["inserted"]:
            self.stage = 2
            self.stage_steps[STAGES[1]] = self.steps
        released = False
        if self.stage >= 2 and geo["inserted"]:
            contacts = self.checker.contacts(self.data)
            speeds = self.checker.speeds(self.data)
            released = (
                contacts["hand_letter_contacts"] == 0
                and contacts["hand_envelope_contacts"] == 0
                and self.checker.at_rest(speeds)
            )
        self.hold = self.hold + 1 if released else 0
        if self.hold >= self.hold_steps:
            self.success = True
            self.stage = 3
            self.stage_steps[STAGES[2]] = self.steps
        if self.steps >= self.config["max_steps"] and not self.success and not self.failure:
            self.failure = "episode_budget"
            self.failure_detail = {"control": self.steps}
        return self.features()

    def features(self):
        geo = self.checker.geometry(self.data)
        return {
            **geo,
            **self.checker.contacts(self.data),
            **self.checker.speeds(self.data),
            "letter_pos": self.data.xpos[self.checker.letter_id].tolist(),
            "envelope_pos": self.data.xpos[self.checker.envelope_id].tolist(),
            "stage_completed": self.stage,
            "stage_steps": dict(self.stage_steps),
            "released_hold_steps": self.hold,
            "success": self.success,
            "failure": self.failure,
            "failure_detail": self.failure_detail,
            "steps": self.steps,
        }

    def status(self):
        f = self.features()
        return {
            **f,
            "done": self.done,
            "stage": self.stage,
            "total_stages": len(STAGES),
            "reason": "success" if self.success else (self.failure or ""),
            "failed": bool(self.failure),
            "hand": self.hand,
        }

    # ------------------------------------------------------------------ tooling
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

    def snapshot(self):
        """Full simulator + verdict state (authoring/search helper; never used by graders)."""
        state = np.empty(mujoco.mj_stateSize(self.model, mujoco.mjtState.mjSTATE_INTEGRATION))
        mujoco.mj_getState(self.model, self.data, state, mujoco.mjtState.mjSTATE_INTEGRATION)
        return dict(
            state=state,
            steps=self.steps,
            stage=self.stage,
            stage_steps=dict(self.stage_steps),
            hold=self.hold,
            success=self.success,
            failure=self.failure,
            failure_detail=self.failure_detail,
            n_actions=len(self.actions),
        )

    def restore(self, snap):
        mujoco.mj_setState(self.model, self.data, snap["state"], mujoco.mjtState.mjSTATE_INTEGRATION)
        mujoco.mj_forward(self.model, self.data)
        self.steps, self.stage, self.hold = snap["steps"], snap["stage"], snap["hold"]
        self.stage_steps = dict(snap["stage_steps"])
        self.success, self.failure, self.failure_detail = snap["success"], snap["failure"], snap["failure_detail"]
        del self.actions[snap["n_actions"]:]

    def state_sha(self):
        state = np.empty(mujoco.mj_stateSize(self.model, mujoco.mjtState.mjSTATE_INTEGRATION))
        mujoco.mj_getState(self.model, self.data, state, mujoco.mjtState.mjSTATE_INTEGRATION)
        digest = hashlib.sha256(state.astype("<f8").tobytes())
        physics = {k: v for k, v in self.config.items() if k not in NON_PHYSICS_KEYS}
        digest.update(json.dumps(physics, sort_keys=True).encode())
        digest.update(json.dumps([self.steps, self.stage, self.hold, self.success, self.failure]).encode())
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
