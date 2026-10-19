"""Actuator-only bicycle-pump dynamics and the strict stroke/pressure/release predicate."""

from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path

os.environ.setdefault("MUJOCO_GL", "egl")

import mujoco
import numpy as np

from checker import STAGE_NAMES, PumpChecker
from scene import arm_rig, build, hands

TASK = "bicycle_pump_stroke"
CONFIG_PATH = Path(__file__).with_name("task.json")
# task.json keys that define the physics, the reset and the predicate (never instruction prose, titles or cameras).
HASHED_CONFIG_KEYS = ("physics_dt", "control_dt", "max_steps", "table_z", "rig", "marvin", "pump", "connect",
                      "strokes", "release", "fail_fast", "initial_targets")


class Session:
    """One frozen bicycle-pump episode. ``hand`` is ``sharpa`` (default) or ``wuji``; when omitted, the
    ``DEXHAND_HAND`` environment variable selects it. Graders pass the hand recorded with the trajectory."""

    def __init__(self, task=TASK, instance=None, asset_dir=None, config=None, hand=None):
        if task != TASK:
            raise ValueError("Unknown task: " + str(task))
        self.config = json.loads(Path(instance or CONFIG_PATH).read_text()) if config is None else config
        self.spec = self.config
        self.task = task
        self.hand = hands.selected(hand)
        self.hand_info = hands.info(self.hand)
        self.robot = arm_rig.ROBOT_ID
        self.model, self.xml = build(self.config, asset_dir, self.hand)
        self.data = mujoco.MjData(self.model)
        self.action_dim = self.model.nu
        self.initial_targets = np.asarray(self.config["initial_targets"][self.hand], dtype=float)
        if self.initial_targets.shape != (self.action_dim,):
            raise ValueError(f"initial_targets[{self.hand}] must have {self.action_dim} values")
        self.control_dt = self.config["control_dt"]
        self.substeps = round(self.control_dt / self.config["physics_dt"])
        self.max_control_steps = int(self.config["max_steps"])
        self.tcp_body = "wrist_stage"
        self.layout = arm_rig.layout(self.model)
        self.qadr = self.model.jnt_qposadr[self.model.actuator_trnid[:, 0]]
        self.joint_names = [self.model.joint(int(j)).name for j in self.model.actuator_trnid[:, 0]]
        self.actuator_names = [self.model.actuator(i).name for i in range(self.model.nu)]
        self.checker = PumpChecker(self.model, self.config)
        self.owner = self.checker.owner
        self.renderer = None
        self.reset()

    # ------------------------------------------------------------------ episode
    def reset(self):
        mujoco.mj_resetData(self.model, self.data)
        self.data.qpos[self.qadr] = self.initial_targets
        self.data.ctrl[:] = self.initial_targets
        mujoco.mj_forward(self.model, self.data)
        self.steps = 0
        self.checker.reset(self.data)
        self.actions = []
        self._features = self.checker.features(self.model, self.data)
        self.initial_sha = self.state_sha()

    @property
    def success(self):
        return bool(self.checker.success)

    @property
    def failure(self):
        return self.checker.failure

    @property
    def failure_detail(self):
        return self.checker.failure_detail

    @property
    def done(self):
        return bool(self.success or self.failure)

    def hold_action(self):
        return self.data.ctrl.copy()

    def cameras(self):
        return list(self.config["cameras"])

    def features(self):
        return dict(self._features, steps=self.steps)

    def status(self):
        f = self.features()
        return {
            **f,
            "done": self.done,
            "stage": f["stage"],
            "total_stages": len(STAGE_NAMES),
            "stage_names": list(STAGE_NAMES),
            "reason": "success" if self.success else (self.failure or ""),
            "failed": bool(self.failure),
            "hand": self.hand,
        }

    def validate(self, action):
        """Return the row as float64 or raise ValueError (width, finiteness, native actuator ranges)."""
        values = np.asarray(action, dtype=np.float64)
        if values.shape != (self.action_dim,) or not np.isfinite(values).all():
            raise ValueError(f"Expected {self.action_dim} finite actuator targets")
        lo, hi = self.model.actuator_ctrlrange.T
        if np.any(values < lo - 1e-6) or np.any(values > hi + 1e-6):
            raise ValueError("Actuator targets exceed native joint bounds")
        return values

    def step(self, action):
        values = self.validate(action)
        lo, hi = self.model.actuator_ctrlrange.T
        if self.done:
            # The episode ended at the first success or failure; later rows are not executed.
            return self.features()
        self.data.ctrl[:] = np.clip(values, lo, hi)
        self.actions.append(self.data.ctrl.copy())
        for substep in range(self.substeps):
            mujoco.mj_step(self.model, self.data)
            # Fail fast: the episode ends at the physics substep that broke an invariant.
            self.checker.substep(self.data, self.steps, substep)
            if self.checker.failure:
                break
        self.steps += 1
        mujoco.mj_forward(self.model, self.data)
        self._features = self.checker.control(self.model, self.data)
        if self.steps >= self.max_control_steps and not self.success and not self.failure:
            self.checker.failure = "episode_budget"
            self.checker.failure_detail = {"control": self.steps}
            self._features = self.checker.features(self.model, self.data)
        return self.features()

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

    # ------------------------------------------------------------------ authoring helpers
    def snapshot(self):
        """Full simulator + checker state (authoring/search only; graders always replay from reset)."""
        size = mujoco.mj_stateSize(self.model, mujoco.mjtState.mjSTATE_INTEGRATION)
        state = np.empty(size)
        mujoco.mj_getState(self.model, self.data, state, mujoco.mjtState.mjSTATE_INTEGRATION)
        c = self.checker
        return {
            "state": state,
            "ctrl": self.data.ctrl.copy(),
            "steps": self.steps,
            "features": dict(self._features),
            "actions": len(self.actions),
            "checker": {k: (v.copy() if isinstance(v, np.ndarray) else (list(v) if isinstance(v, list) else v))
                        for k, v in vars(c).items()
                        if k in ("base0", "connected", "connect_control", "disconnected", "disconnect_control",
                                 "strokes", "armed", "max_depth",
                                 "stroke_log", "hold", "stage", "failure", "failure_detail", "success")},
        }

    def restore(self, snap):
        mujoco.mj_setState(self.model, self.data, snap["state"], mujoco.mjtState.mjSTATE_INTEGRATION)
        self.data.ctrl[:] = snap["ctrl"]
        mujoco.mj_forward(self.model, self.data)
        self.steps = snap["steps"]
        self._features = dict(snap["features"])
        del self.actions[snap["actions"]:]
        for k, v in snap["checker"].items():
            setattr(self.checker, k, v.copy() if isinstance(v, np.ndarray) else (list(v) if isinstance(v, list) else v))

    def state_sha(self):
        state = np.empty(mujoco.mj_stateSize(self.model, mujoco.mjtState.mjSTATE_INTEGRATION))
        mujoco.mj_getState(self.model, self.data, state, mujoco.mjtState.mjSTATE_INTEGRATION)
        digest = hashlib.sha256(state.astype("<f8").tobytes())
        c = self.checker
        predicate = {"connected": c.connected, "disconnected": c.disconnected, "strokes": c.strokes, "armed": c.armed,
                     "hold": c.hold, "stage": c.stage,
                     "failure": c.failure, "success": c.success, "steps": self.steps}
        digest.update(json.dumps(predicate, sort_keys=True).encode())
        # Only the physics/predicate parameters of the frozen instance: editing texts never changes evidence hashes.
        digest.update(json.dumps({k: self.config[k] for k in HASHED_CONFIG_KEYS}, sort_keys=True).encode())
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
