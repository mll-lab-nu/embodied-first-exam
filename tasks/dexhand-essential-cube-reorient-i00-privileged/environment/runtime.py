"""Task-local Sharpa Wave simulator, physical observations and actuator replay."""

from __future__ import annotations

import hashlib
import json
import math
import os
from pathlib import Path

os.environ.setdefault("MUJOCO_GL", "egl")

import mujoco
import numpy as np

import essential
import hands
from checker import Checker
from scene import FREE_TASKS, PALM_BODY, WRIST_JOINTS, build

ACTION_DIM = 28
SUPPORTED_HANDS = ("sharpa", "wuji")
ACTION_DIMS = {"sharpa": 28, "wuji": 26}
# Sharpa-named reset keys of the frozen instance and their Wuji counterparts (HAND_INTERFACE.md section 3).
WUJI_RESET_KEYS = ("initial_fingers", "initial_hand_joints")  # replaced by essential.wuji_reset() for Wuji
MAX_TRAJECTORY_ROWS = 50_000
CONTROL_DT = 0.02
FINGERS = ("thumb", "index", "middle", "ring", "pinky")
# Task coordinates: along the fingers, across the palm, out of the palm.
PALM_AXES = np.array([[0.0, 0.0, 1.0], [0.0, -1.0, 0.0], [1.0, 0.0, 0.0]])


def locked_wrist_targets_match(targets, spec):
    """Check fixed targets allowing the standard client's float32 wire format."""
    return bool(np.all(np.abs(np.asarray(targets, dtype=np.float64) - essential.initial_wrist(spec))
                       <= essential.wrist_wire_tolerance(spec)))


def actuator_targets_in_range(targets, limits, spec):
    """Accept representational rounding at a bound, never extra motor travel."""
    tolerance = (np.abs(limits.astype(np.float32).astype(np.float64) - limits) + 1e-9
                 if essential.is_essential(spec) else np.full_like(limits, 1e-9))
    values = np.asarray(targets, dtype=np.float64)
    return bool(np.all(values >= limits[:, 0] - tolerance[:, 0])
                and np.all(values <= limits[:, 1] + tolerance[:, 1]))


def catalog(path=None):
    p = Path(path) if path else Path(__file__).with_name("catalog.json")
    if not p.exists():
        p = Path(__file__).parent.parent / "catalog.json"
    # a task directory always has its own catalog.json; a source checkout may carry only essential_catalog.json
    tasks = json.loads(p.read_text())["tasks"] if path or p.exists() else []
    extra = p.with_name("essential_catalog.json")
    if path is None and extra.exists():
        tasks += json.loads(extra.read_text())["tasks"]
    return tasks


def _euler(r):
    pitch = math.asin(float(np.clip(-r[2, 0], -1, 1)))
    return math.atan2(r[2, 1], r[2, 2]), pitch, math.atan2(r[1, 0], r[0, 0])


class Session:
    """Frozen-scene access; only actuator targets cross the grading boundary."""

    action_dim = ACTION_DIM
    control_dt = CONTROL_DT

    def __init__(self, task, instance=None, asset_dir=None, hand=None):
        self.task = task
        self.hand = hands.selected(hand)
        if self.hand not in SUPPORTED_HANDS:
            raise hands.HandError(f"Hand {self.hand!r} is not available in this task")
        if instance:
            self.spec = json.loads(Path(instance).read_text())
            if self.spec["id"] != task:
                raise ValueError("Instance task mismatch")
        else:
            self.spec = next((s for s in catalog() if s["id"] == task), None)
            if self.spec is None:
                raise ValueError(f"Unknown task: {task}")
        self.frozen_spec = self.spec
        if essential.is_essential(self.spec):
            offered, reason = essential.offered_hands(self.spec)
            if self.hand not in offered:
                raise hands.HandError(f"Hand {self.hand!r} is not offered in {task} (only {', '.join(offered)}): {reason}")
        if self.hand != "sharpa":
            if not essential.is_essential(self.spec):
                raise hands.HandError(f"Hand {self.hand!r} is only available in the essential families")
            # The Sharpa joint names of the frozen reset do not exist on Wuji; use the declared Wuji reset
            # (neutral fingers when none is declared). Stages, invariants and object placement are unchanged.
            parameters = dict(self.spec.get("parameters", {}))
            for key in WUJI_RESET_KEYS:
                if key in parameters:
                    parameters[key] = essential.wuji_reset(self.spec)
            parameters.update(essential.wuji_initial_objects(self.spec))  # held objects' Wuji start, if declared
            parameters["require_initial_palm_contact"] = False
            parameters["initial_horizontal_max_deg"] = 90
            self.spec = {**self.spec, "parameters": parameters}
        self.model, self._initial_joints, self.xml = build(self.spec, asset_dir=asset_dir, hand=self.hand)
        self.data = mujoco.MjData(self.model)
        self.action_dim = self.model.nu
        if self.action_dim != ACTION_DIMS[self.hand]:
            raise ValueError("Unexpected hand actuator layout")
        self.robot = hands.HANDS[self.hand]["robot"] + "-floating"
        self._act_jids = self.model.actuator_trnid[:, 0].astype(int)
        self._act_qpos = self.model.jnt_qposadr[self._act_jids]
        self.joint_names = [self.model.joint(int(j)).name for j in self._act_jids]
        self.actuator_names = [self.model.actuator(i).name for i in range(self.model.nu)]
        self._task_jids = [j for j in range(self.model.njnt) if j not in self._act_jids]
        self._task_dofs = []
        self._task_joint_map = {}
        for j in self._task_jids:
            n = self.model.joint(j).name
            kind = self.model.jnt_type[j]
            count = 6 if kind == mujoco.mjtJoint.mjJNT_FREE else (3 if kind == mujoco.mjtJoint.mjJNT_BALL else 1)
            self._task_dofs.extend(range(int(self.model.jnt_dofadr[j]), int(self.model.jnt_dofadr[j]) + count))
            if kind in (mujoco.mjtJoint.mjJNT_HINGE, mujoco.mjtJoint.mjJNT_SLIDE):
                self._task_joint_map[n] = int(self.model.jnt_qposadr[j])
        self._finger_geoms = {}
        for g in range(self.model.ngeom):
            n = self.model.geom(g).name or ""
            if "fingertip_collision" in n:
                for finger in FINGERS:
                    if finger in n:
                        self._finger_geoms[g] = finger
        self._task_geoms = {g for g in range(self.model.ngeom) if (self.model.geom(g).name or "").startswith("task_")}
        self._moving_bodies = {
            "object",
            "ball_a",
            "ball_b",
            "contents",
            "ring",
        }.intersection(self.model.body(b).name for b in range(self.model.nbody))
        self.checker = Checker(self.spec)
        self._renderer = None
        self.reset()

    def reset(self):
        mujoco.mj_resetData(self.model, self.data)
        self.data.qpos[self._act_qpos[:6]] = (
            essential.initial_wrist(self.spec) if essential.is_essential(self.spec)
            else [-0.08, 0, 0.29, 0, 0, 0]
        )
        # Neutral manufacturer's joint coordinates, clipped to the actual joint limits.
        for j, a in zip(self._act_jids[6:], self._act_qpos[6:]):
            self.data.qpos[a] = np.clip(0, *self.model.jnt_range[j])
        for name, value in self._initial_joints.items():
            self.data.qpos[self._task_joint_map[name]] = value
        self.data.ctrl[:] = self.data.qpos[self._act_qpos]
        self.data.qvel[:] = 0
        if essential.is_essential(self.spec):
            essential.module(self.spec).reset(self)
            if self.hand != "sharpa" and any(
                self.data.warning[w].number
                for w in (mujoco.mjtWarning.mjWARN_BADQPOS, mujoco.mjtWarning.mjWARN_BADQVEL, mujoco.mjtWarning.mjWARN_BADQACC)
            ):
                raise ValueError("The declared reset is physically unstable for this hand")
        self.checker.reset()
        self.steps = 0
        self.actions = []
        self._peaks = {}
        self._raw_yaw = 0.0
        self._yaw_accum = 0.0
        mujoco.mj_forward(self.model, self.data)
        self._palm_initial = self.data.body(PALM_BODY).xpos.copy()
        self._palm_rot_initial = self.data.body(PALM_BODY).xmat.reshape(3, 3).copy()
        self._relative_initial = {}
        self._orientation_initial = {}
        frame = self._palm_rot_initial @ PALM_AXES
        for name in self._moving_bodies:
            body = self.data.body(name)
            self._relative_initial[name] = frame.T @ (body.xpos - self._palm_initial)
            self._orientation_initial[name] = frame.T @ body.xmat.reshape(3, 3)
        if "contents" in self._moving_bodies:
            self._contents_initial = self.data.body("contents").xpos.copy()
        if "ring" in self._moving_bodies:
            self._ring_initial = self.data.body("ring").xpos.copy()
        self.initial_sha = self.state_sha()
        return self.state()

    def hold_action(self):
        return self.data.ctrl.copy()

    def _contact_features(self):
        touch = set()
        target_fingers = set()
        ball_fingers = {"ball_a": set(), "ball_b": set()}
        ring_hook_force = 0.0
        deposit_support = 0
        support = 0
        force = 0.0
        wrench = np.zeros(6)
        expected = {
            "index": "task_a",
            "middle": "task_b",
            "ring": "task_c",
            "thumb": "task_d",
        }
        buttons = self.task in {"button_chord", "key_sequence", "uneven_button_chord"}
        for i in range(self.data.ncon):
            c = self.data.contact[i]
            g1, g2 = int(c.geom1), int(c.geom2)
            if g1 not in self._task_geoms and g2 not in self._task_geoms:
                continue
            mujoco.mj_contactForce(self.model, self.data, i, wrench)
            strength = float(np.linalg.norm(wrench[:3]))
            force = max(force, strength)
            names = [self.model.geom(g).name or "" for g in (g1, g2)]
            if self.task == "coin_edge_roll" and set(names) == {"task_object", "coin_deposit"}:
                deposit_support += 1
            if (
                self.task == "hook_ring"
                and any(n.startswith("task_ring_") for n in names)
                and any(n.startswith("task_hook_") for n in names)
            ):
                # This light ring spreads its weight across several wire pieces.
                ring_hook_force += strength
            if strength <= 0.01:
                continue
            for fg, tg in ((g1, g2), (g2, g1)):
                if fg in self._finger_geoms and tg in self._task_geoms:
                    finger = self._finger_geoms[fg]
                    target_name = self.model.geom(tg).name
                    if target_name in {"task_ball_a", "task_ball_b"}:
                        ball_fingers[target_name.removeprefix("task_")].add(finger)
                    if self.task == "hook_ring" and target_name.startswith("task_ring_"):
                        continue
                    if self.task == "lid_contents" and target_name == "task_contents":
                        continue
                    touch.add(finger)
                    if not buttons or self.model.geom(tg).name == expected.get(finger):
                        target_fingers.add(finger)
            for moving, other in ((g1, g2), (g2, g1)):
                if moving not in self._task_geoms:
                    continue
                other_body = int(self.model.geom_bodyid[other])
                if other_body == 0:
                    support += 1
        return {
            "contacts": float(len(touch)),
            "support": float(support),
            "force": force,
            "contacts_a": float(len(ball_fingers["ball_a"])),
            "contacts_b": float(len(ball_fingers["ball_b"])),
            "ring_hook_contact": float(ring_hook_force >= 0.005),
            "deposit_support": float(deposit_support),
            **{"contact_" + finger: float(finger in target_fingers) for finger in FINGERS},
        }

    def features(self):
        """Read trusted numeric physics features without advancing task history."""
        f = {name: float(self.data.qpos[adr]) for name, adr in self._task_joint_map.items()}
        f.update(self._contact_features())
        f["speed"] = float(np.max(np.abs(self.data.qvel[self._task_dofs]), initial=0))
        palm = self.data.body(PALM_BODY)
        rotation = palm.xmat.reshape(3, 3)
        frame = rotation @ PALM_AXES
        f["palm_drift"] = float(np.linalg.norm(palm.xpos - self._palm_initial))
        f["wrist_rotation"] = math.acos(float(np.clip((np.trace(rotation @ self._palm_rot_initial.T) - 1) / 2, -1, 1)))
        if self.task in FREE_TASKS:
            for name in self._moving_bodies:
                body = self.data.body(name)
                xyz = frame.T @ (body.xpos - palm.xpos) - self._relative_initial[name]
                if name in {"ball_a", "ball_b"}:
                    f["a_x" if name == "ball_a" else "b_x"] = float(xyz[0])
                else:
                    f.update(dict(zip(("x", "y", "z"), map(float, xyz))))
                    relative = frame.T @ body.xmat.reshape(3, 3)
                    roll, pitch, yaw = _euler(relative @ self._orientation_initial[name].T)
                    f.update(
                        roll=roll,
                        pitch=pitch,
                        yaw=self._yaw_accum + math.atan2(math.sin(yaw - self._raw_yaw), math.cos(yaw - self._raw_yaw)),
                    )
            if self.task == "two_ball_exchange":
                f["distance"] = float(np.linalg.norm(self.data.body("ball_a").xpos - self.data.body("ball_b").xpos))
            if self.task == "coin_edge_roll":
                f["deposit_distance"] = float(
                    np.linalg.norm(self.data.body("object").xpos[:2] - self.data.geom("coin_deposit").xpos[:2])
                )
        elif self.task == "lid_contents":
            contents = self.data.body("contents")
            xyz = contents.xpos - self._contents_initial
            f.update(dict(zip(("x", "y", "z"), map(float, xyz))))
            z_axis = contents.xmat.reshape(3, 3)[:, 2]
            f["tilt"] = math.acos(float(np.clip(z_axis[2], -1, 1)))
        elif self.task == "hook_ring":
            ring = self.data.body("ring").xpos
            f["ring_lift"] = float(ring[2] - self._ring_initial[2])
            f["ring_shift"] = float(ring[0] - self._ring_initial[0])
            f["ring_distance"] = float(np.linalg.norm(ring - self.data.body("task_hook").xpos))
        elif self.task == "coordinated_dials":
            f["dial_ratio_error"] = abs(f["a"] + f["b"])
        if essential.is_essential(self.spec):
            f.update(essential.module(self.spec).features(self))
        return f

    def _track_yaw(self):
        if self.task not in FREE_TASKS or "object" not in self._moving_bodies:
            return
        frame = self.data.body(PALM_BODY).xmat.reshape(3, 3) @ PALM_AXES
        relative = frame.T @ self.data.body("object").xmat.reshape(3, 3)
        yaw = _euler(relative @ self._orientation_initial["object"].T)[2]
        self._yaw_accum += math.atan2(math.sin(yaw - self._raw_yaw), math.cos(yaw - self._raw_yaw))
        self._raw_yaw = yaw

    def step(self, action):
        a = np.asarray(action, dtype=np.float64)
        if a.shape != (self.action_dim,) or not np.all(np.isfinite(a)):
            raise ValueError(f"An action must contain {self.action_dim} finite actuator targets")
        limits = self.model.actuator_ctrlrange
        if not actuator_targets_in_range(a, limits, self.spec):
            raise ValueError("Actuator target outside its declared control range")
        if essential.is_essential(self.spec):
            if not locked_wrist_targets_match(a[:6], self.spec):
                raise ValueError("This task locks all six wrist targets to the declared starting pose")
            # Client-side float32 rounding and linear interpolation must never
            # cause a real wrist command. Both wire forms execute the same six
            # canonical targets, and recorded rows replay identically.
            a = a.copy()
            a = np.clip(a, limits[:, 0], limits[:, 1])
            a[:6] = essential.initial_wrist(self.spec)
        if self.checker.failed or self.checker.success:
            return self.status()
        self.data.ctrl[:] = a
        peaks = {}
        violated = None
        window_valid = True
        for _ in range(10):
            mujoco.mj_step(self.model, self.data)
            bad_warnings = (
                mujoco.mjtWarning.mjWARN_BADQPOS,
                mujoco.mjtWarning.mjWARN_BADQVEL,
                mujoco.mjtWarning.mjWARN_BADQACC,
                mujoco.mjtWarning.mjWARN_BADCTRL,
            )
            if any(self.data.warning[warning].number for warning in bad_warnings):
                self.checker.failure = "unstable_physics"
                self.checker.terminal_hold = 0
                break
            mujoco.mj_forward(self.model, self.data)
            self._track_yaw()
            f = self.features()
            if not all(math.isfinite(f.get(key, float("nan"))) for key in self.checker.required_features):
                violated = f
                break
            for key in ("force", "speed"):
                peaks[key] = max(peaks.get(key, 0), f[key])
            # Invariants are sampled at 500 Hz, including forbidden overshoot.
            active = (
                self.checker.stages[self.checker.stage_index]
                if self.checker.stage_index < len(self.checker.stages)
                else self.checker.terminal
            )
            if not self.checker._matches(f, active["bounds"]):
                window_valid = False
            safety_bounds = list(self.checker.invariants.items()) + list(active.get("guards", {}).items())
            for key, (lo, hi) in safety_bounds:
                value = f.get(key, float("nan"))
                if not math.isfinite(value) or (lo is not None and value < lo) or (hi is not None and value > hi):
                    violated = f
                    break
            if violated is not None:
                break
        self.steps += 1
        self.actions.append(a.copy())
        if self.checker.failed:
            return self.status()
        f = violated if violated is not None else self.features()
        f.update(peaks)
        self.checker.update(f, window_valid=window_valid)
        self._peaks = peaks
        return self.status()

    def state_sha(self):
        flags = mujoco.mjtState.mjSTATE_INTEGRATION
        state = np.empty(mujoco.mj_stateSize(self.model, flags))
        mujoco.mj_getState(self.model, self.data, state, flags)
        h = hashlib.sha256(state.tobytes())
        h.update(json.dumps(self.checker.snapshot(), sort_keys=True).encode())
        h.update(np.asarray([self._yaw_accum, self._raw_yaw], dtype=np.float64).tobytes())
        if self.hand != "sharpa":
            h.update(self.hand.encode())  # the Sharpa digest is unchanged from the validated evidence
        if essential.is_essential(self.spec):
            extra = {
                "palm_initial": self._palm_initial.tolist(),
                "palm_rotation_initial": self._palm_rot_initial.tolist(),
                "relative_initial": {name: value.tolist() for name, value in self._relative_initial.items()},
                "orientation_initial": {name: value.tolist() for name, value in self._orientation_initial.items()},
            }
            helper = essential.module(self.spec)
            if hasattr(helper, "snapshot"):
                history = helper.snapshot(self)
                if history:
                    extra["mechanism_history"] = history
            h.update(json.dumps(extra, sort_keys=True, allow_nan=False).encode())
        return h.hexdigest()

    def status(self):
        c = self.checker.snapshot()
        return {
            **c,
            "done": bool(c["success"] or c["failed"]),
            "steps": self.steps,
            "stage": c["stage_index"],
            "total_stages": c["stage_count"],
            "reason": c["failure"] or ("success" if c["success"] else ""),
            "state_sha": self.state_sha(),
            "hand": self.hand,
        }

    def state(self):
        return {
            "qpos": self.data.qpos.copy(),
            "qvel": self.data.qvel.copy(),
            "ctrl": self.data.ctrl.copy(),
            "features": self.features(),
            "objects": {
                name: {
                    "pos": self.data.body(name).xpos.copy(),
                    "quat": self.data.body(name).xquat.copy(),
                }
                for name in self._moving_bodies
            },
        }

    def replay(self, actions):
        rows = np.asarray(actions, dtype=np.float64)
        if (
            rows.ndim != 2
            or rows.shape[1] != self.action_dim
            or len(rows) > MAX_TRAJECTORY_ROWS
            or not np.all(np.isfinite(rows))
        ):
            raise ValueError("Invalid trajectory array")
        limits = self.model.actuator_ctrlrange
        if not actuator_targets_in_range(rows, limits, self.spec):
            raise ValueError("Trajectory target outside its declared control range")
        if essential.is_essential(self.spec) and not locked_wrist_targets_match(rows[:, :6], self.spec):
            raise ValueError("Trajectory attempts to move the locked wrist")
        self.reset()
        for row in rows:
            self.step(row)
            if self.status()["done"]:
                break
        return self.status()

    def save_trajectory(self, actions, path):
        rows = np.asarray(actions, dtype=np.float64)
        if (
            rows.ndim != 2
            or rows.shape[1] != self.action_dim
            or len(rows) > MAX_TRAJECTORY_ROWS
            or not np.all(np.isfinite(rows))
        ):
            raise ValueError("Invalid trajectory array")
        hands.write_trajectory(path, rows, hand=self.hand, task=self.task)

    def cameras(self):
        return [self.model.camera(i).name for i in range(self.model.ncam)]

    def render_frame(self, camera="overview"):
        if camera not in self.cameras():
            raise ValueError("Unknown camera")
        if self._renderer is None:
            self._renderer = mujoco.Renderer(self.model, height=480, width=640)
        self._renderer.update_scene(self.data, camera=camera)
        return self._renderer.render().copy()

    def close(self):
        if self._renderer:
            self._renderer.close()
            self._renderer = None
