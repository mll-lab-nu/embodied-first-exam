"""picture_hang: a dual-arm robot with two dexterous hands hangs a 2 kg framed print on two wall hooks (actuator-only
physics).

One ``step(row)`` applies the row's position targets for ``substeps`` physics steps of ``physics_dt`` (50 Hz control).
Only the robot's position servos (two 7-joint Marvin arms and the two hands' fingers) act; the frame and its passive D-rings move only
through contact, gravity and their passive hinges. The verdict (``checker.Checker``) is evaluated from simulator
state after every control: ordered stages, fail-fast failures, terminal released hold.
"""

from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path

os.environ.setdefault("MUJOCO_GL", "egl")

import mujoco  # noqa: E402
import numpy as np  # noqa: E402

from checker import Checker  # noqa: E402
from scene import build, hands  # noqa: E402

TASK_ID = "picture_hang"
CONFIG_PATH = Path(__file__).with_name("task.json")
STATE = mujoco.mjtState.mjSTATE_INTEGRATION
# task.json fields that define the physics and the verdict (hashed into state_sha); texts and cameras are not.
PHYSICS_KEYS = ("physics_dt", "control_dt", "max_steps", "robot_base", "start", "initial_targets", "predicate")
ROBOTS = {"sharpa": "marvin-bimanual-sharpa-wave", "wuji": "marvin-bimanual-wuji-hand-2.2"}


class Session:
    """One frozen picture-hanging episode. ``hand`` is ``sharpa`` (default) or ``wuji``; when omitted, the
    ``DEXHAND_HAND`` environment variable selects it. Graders pass the hand recorded with the trajectory."""

    def __init__(self, task=TASK_ID, hand=None, instance=None, asset_dir=None, config=None):
        if task != TASK_ID:
            raise ValueError(f"Unknown task {task!r}; this runtime serves {TASK_ID!r}")
        self.task = TASK_ID
        self.config = json.loads(Path(instance or CONFIG_PATH).read_text()) if config is None else config
        self.spec = self.config
        self.hand = hands.selected(hand)
        self.hand_info = hands.info(self.hand)
        self.robot = ROBOTS[self.hand]
        self.model, self.xml = build(self.config, self.hand, asset_dir)
        self.data = mujoco.MjData(self.model)
        self.action_dim = int(self.model.nu)
        self.control_dt = float(self.config["control_dt"])
        self.substeps = int(round(self.control_dt / self.config["physics_dt"]))
        self.max_control_steps = int(self.config["max_steps"])
        self.actuator_names = [self.model.actuator(i).name for i in range(self.model.nu)]
        self.joint_names = [self.model.joint(int(j)).name for j in self.model.actuator_trnid[:, 0]]
        self.qadr = self.model.jnt_qposadr[self.model.actuator_trnid[:, 0]]
        self.tcp_bodies = ["l_wrist_stage", "r_wrist_stage"]  # flange mount bodies (hand roots)
        self.ctrl_lo, self.ctrl_hi = self.model.actuator_ctrlrange.T.copy()
        init = self.config["initial_targets"][self.hand]
        targets = np.zeros(self.action_dim)
        for name, value in init.items():
            targets[self.actuator_names.index(name)] = value
        self.initial_targets = np.clip(targets, self.ctrl_lo, self.ctrl_hi)
        self.checker = Checker(self.model, self.config)
        self.renderer = None
        self.reset()

    # ------------------------------------------------------------------ episode
    def reset(self):
        mujoco.mj_resetData(self.model, self.data)
        self.data.qpos[self.qadr] = self.initial_targets
        self.data.ctrl[:] = self.initial_targets
        mujoco.mj_forward(self.model, self.data)
        self.steps = 0
        self.checker.reset()
        self.features = self.checker.update(self.data)
        self.initial_sha = self.state_sha()
        return self.status()

    @property
    def done(self):
        return bool(self.checker.success or self.checker.failure)

    @property
    def success(self):
        return bool(self.checker.success)

    @property
    def failure(self):
        return self.checker.failure

    def hold_action(self):
        return self.data.ctrl.copy()

    def cameras(self):
        return list(self.config["cameras"])

    def step(self, action):
        values = np.asarray(action, dtype=np.float64)
        if values.shape != (self.action_dim,) or not np.isfinite(values).all():
            raise ValueError(f"Expected {self.action_dim} finite actuator targets")
        if np.any(values < self.ctrl_lo - 1e-6) or np.any(values > self.ctrl_hi + 1e-6):
            raise ValueError("Actuator targets exceed the actuator control ranges")
        if self.done:
            return self.status()  # the episode ended at the first success or failure
        self.data.ctrl[:] = np.clip(values, self.ctrl_lo, self.ctrl_hi)
        control = self.steps + 1
        for substep in range(self.substeps):
            mujoco.mj_step(self.model, self.data)
            if any(self.data.warning[w].number for w in (mujoco.mjtWarning.mjWARN_BADQPOS,
                                                        mujoco.mjtWarning.mjWARN_BADQVEL,
                                                        mujoco.mjtWarning.mjWARN_BADQACC)):
                self.checker.failure = "unstable_physics"
                self.checker.failure_detail = {"detail": "MuJoCo bad qpos/qvel/qacc", "control": control,
                                               "substep": substep}
                break
            # Fail fast: the episode ends at the physics substep that broke an invariant.
            if self.checker.substep(self.data, control, substep):
                break
        self.steps = control
        self.features = self.checker.update(self.data, control)
        if not self.done and self.steps >= self.max_control_steps:
            self.checker.failure = "episode_budget"
            self.checker.failure_detail = {"control": self.steps}
        return self.status()

    def status(self):
        c = self.checker
        return {
            "success": bool(c.success),
            "done": self.done,
            "failed": bool(c.failure),
            "reason": "success" if c.success else (c.failure or ""),
            "failure_detail": c.failure_detail,
            "steps": self.steps,
            "stage": c.stage,
            "total_stages": 3,
            "hold_steps": c.hold,
            "hand": self.hand,
            "features": self.features,
        }

    def replay(self, actions):
        """Reset, then execute rows until the episode ends (success or failure) or the rows run out."""
        self.reset()
        for row in np.asarray(actions, dtype=np.float64):
            self.step(row)
            if self.done:
                break
        return self.status()

    # ------------------------------------------------------------------ state
    def state_sha(self):
        state = np.empty(mujoco.mj_stateSize(self.model, STATE))
        mujoco.mj_getState(self.model, self.data, state, STATE)
        digest = hashlib.sha256(state.astype("<f8").tobytes())
        digest.update(json.dumps(self.checker.state_tuple()).encode())
        digest.update(str(self.steps).encode())
        # Physics and predicate parameters only (never instruction prose): editing texts keeps evidence hashes.
        digest.update(json.dumps({k: self.config[k] for k in PHYSICS_KEYS}, sort_keys=True).encode())
        digest.update(self.hand.encode())
        return digest.hexdigest()

    def snapshot(self):
        state = np.empty(mujoco.mj_stateSize(self.model, mujoco.mjtState.mjSTATE_INTEGRATION))
        mujoco.mj_getState(self.model, self.data, state, mujoco.mjtState.mjSTATE_INTEGRATION)
        c = self.checker
        return {"state": state, "ctrl": self.data.ctrl.copy(), "steps": self.steps,
                "checker": (c.stage, c.hold, c.unsupported, c.success, c.failure, c.failure_detail),
                "features": self.features}

    def restore(self, snap):
        mujoco.mj_setState(self.model, self.data, snap["state"], mujoco.mjtState.mjSTATE_INTEGRATION)
        self.data.ctrl[:] = snap["ctrl"]
        mujoco.mj_forward(self.model, self.data)
        self.steps = snap["steps"]
        c = self.checker
        c.stage, c.hold, c.unsupported, c.success, c.failure, c.failure_detail = snap["checker"]
        self.features = snap["features"]

    def save_trajectory(self, actions, path):
        """Write the privileged deliverable: ``actions`` plus this session's ``hand`` and ``task``."""
        hands.write_trajectory(path, actions, hand=self.hand, task=self.task)

    # ------------------------------------------------------------------ rendering
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
