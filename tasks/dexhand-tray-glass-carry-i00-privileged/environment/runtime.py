"""Session for tray_glass_carry: two hands on two six-axis wrist stages, actuator targets only."""

from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path

os.environ.setdefault("MUJOCO_GL", "egl")

import mujoco
import numpy as np

from checker import Checker
from scene import build, hands

TASK = "tray_glass_carry"
CONFIG_PATH = Path(__file__).with_name("task.json")
TEXT_KEYS = ("schema_version", "id", "title", "category", "description", "difficulty", "mechanism", "instruction",
             "robot", "modeling", "initial_targets", "cameras")


class Session:
    """One frozen episode. ``hand`` is ``sharpa`` (default) or ``wuji``; when omitted, ``DEXHAND_HAND`` selects it.

    A row holds the motor targets of, in order: the left wrist stage (x, y, z in m; rx, ry, rz in rad), the right
    wrist stage (same), the left hand's finger actuators and the right hand's finger actuators
    (``actuator_names``). One row = one 50 Hz control = 10 physics steps of 2 ms.
    """

    def __init__(self, task=TASK, hand=None, instance=None, config=None):
        if task != TASK:
            raise ValueError("Unknown task: " + str(task))
        self.config = json.loads(Path(instance or CONFIG_PATH).read_text()) if config is None else config
        self.spec = self.config
        # state_sha covers the physics/predicate parameters only, never instruction prose or presentation settings.
        self.physics_config = {k: v for k, v in self.config.items() if k not in TEXT_KEYS}
        self.task = task
        self.hand = hands.selected(hand)
        self.hand_info = hands.info(self.hand)
        self.model, self.xml = build(self.config, self.hand)
        self.data = mujoco.MjData(self.model)
        self.action_dim = int(self.model.nu)
        self.actuator_names = [self.model.actuator(i).name for i in range(self.model.nu)]
        self.joint_names = [self.model.joint(int(j)).name for j in self.model.actuator_trnid[:, 0]]
        self.qadr = self.model.jnt_qposadr[self.model.actuator_trnid[:, 0]]
        lo, hi = self.model.actuator_ctrlrange.T
        # Neutral reset: every target 0 clipped into its range (stages at their base pose, open hands).
        self.initial_targets = np.clip(np.zeros(self.action_dim), lo, hi)
        self.control_dt = float(self.config["control_dt"])
        self.substeps = int(round(self.control_dt / self.config["physics_dt"]))
        self.max_control_steps = int(self.config["max_steps"])
        self.robot = self.hand_info["robot"] + "-floating-bimanual"
        self.tcp_bodies = ["l_hand_palm", "r_hand_palm"]
        self.checker = Checker(self.model, self.config)
        self.renderer = None
        self.reset()

    # ------------------------------------------------------------------ episode
    def reset(self):
        mujoco.mj_resetData(self.model, self.data)
        self.data.qpos[self.qadr] = self.initial_targets
        self.data.ctrl[:] = self.initial_targets
        mujoco.mj_forward(self.model, self.data)
        self.checker.reset()
        self.steps = 0
        self.last = self.checker.features(self.data)
        self.initial_sha = self.state_sha()

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

    def validate(self, action):
        values = np.asarray(action, dtype=np.float64)
        if values.shape != (self.action_dim,) or not np.isfinite(values).all():
            raise ValueError(f"Expected {self.action_dim} finite actuator targets")
        lo, hi = self.model.actuator_ctrlrange.T
        if np.any(values < lo - 1e-6) or np.any(values > hi + 1e-6):
            raise ValueError("Actuator targets exceed their ranges")
        return np.clip(values, lo, hi)

    def step(self, action):
        values = self.validate(action)
        if self.done:
            return self.status()  # the episode ended at the first success or failure
        self.data.ctrl[:] = values
        ck = self.checker
        for sub in range(self.substeps):
            mujoco.mj_step(self.model, self.data)
            v = ck.violation(self.data)
            if v:
                ck.failure = v[0]
                ck.detail = {"object": v[1], "control": self.steps, "substep": sub}
                break
        self.steps += 1
        if not ck.failure:
            self.last = ck.update(self.data)
            if not ck.success and self.steps >= self.max_control_steps:
                ck.failure = "episode_budget"
                ck.detail = {"control": self.steps}
        else:
            self.last = ck.features(self.data)
        return self.status()

    def status(self):
        ck = self.checker
        return {
            "success": bool(ck.success),
            "done": self.done,
            "failed": bool(ck.failure),
            "reason": "success" if ck.success else (ck.failure or ""),
            "failure_detail": ck.detail,
            "steps": self.steps,
            "stage": ck.stage,
            "total_stages": 3,
            "hold_steps": ck.hold,
            "hand": self.hand,
            "features": self.last,
        }

    def replay(self, actions):
        self.reset()
        for row in np.asarray(actions, dtype=np.float64):
            self.step(row)
            if self.done:
                break
        return self.status()

    def save_trajectory(self, actions, path):
        hands.write_trajectory(path, actions, hand=self.hand, task=self.task)

    # ------------------------------------------------------------------ snapshots / hashing
    def snapshot(self):
        size = mujoco.mj_stateSize(self.model, mujoco.mjtState.mjSTATE_INTEGRATION)
        state = np.empty(size)
        mujoco.mj_getState(self.model, self.data, state, mujoco.mjtState.mjSTATE_INTEGRATION)
        ck = self.checker
        return {"state": state, "steps": self.steps, "checker": (ck.stage, ck.hold, ck.success, ck.failure, ck.detail),
                "last": self.last}

    def restore(self, snap):
        mujoco.mj_setState(self.model, self.data, snap["state"], mujoco.mjtState.mjSTATE_INTEGRATION)
        mujoco.mj_forward(self.model, self.data)
        ck = self.checker
        ck.stage, ck.hold, ck.success, ck.failure, ck.detail = snap["checker"]
        self.steps = snap["steps"]
        self.last = snap["last"]

    def state_sha(self):
        size = mujoco.mj_stateSize(self.model, mujoco.mjtState.mjSTATE_INTEGRATION)
        state = np.empty(size)
        mujoco.mj_getState(self.model, self.data, state, mujoco.mjtState.mjSTATE_INTEGRATION)
        digest = hashlib.sha256(state.astype("<f8").tobytes())
        digest.update(json.dumps(self.physics_config, sort_keys=True).encode())
        digest.update(json.dumps(self.checker.state() + [self.steps]).encode())
        digest.update(self.hand.encode())
        return digest.hexdigest()

    # ------------------------------------------------------------------ rendering (evidence only)
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
