"""Actuator-only manual coffee grinder episode with a strict state-derived verdict."""

from __future__ import annotations

import copy
import hashlib
import json
import os
from pathlib import Path

os.environ.setdefault("MUJOCO_GL", "egl")

import mujoco
import numpy as np

from checker import Checker
from scene import build, hands

CONFIG_PATH = Path(__file__).with_name("task.json")
TASK = "grinder_crank"
# Targets may exceed a bound by float32 rounding (the public client sends float32); they are clipped to the bound.
BOUND_TOL = 1e-6
PHYSICS_KEYS = ("physics_dt", "control_dt", "max_steps", "counter", "grinder", "robot_base", "initial_targets",
                "checker")


class Session:
    """One frozen grinder episode. ``hand`` is ``sharpa`` (default) or ``wuji``; when omitted, the ``DEXHAND_HAND``
    environment variable selects it. Graders pass the hand recorded with the trajectory. Both hands of the chosen
    model are used: the right hand on ``right_wrist_*``, the (left) counterholding hand on ``left_wrist_*``."""

    def __init__(self, task=TASK, instance=None, asset_dir=None, config=None, hand=None):
        if task != TASK:
            raise ValueError("Unknown task: " + str(task))
        self.config = json.loads(Path(instance or CONFIG_PATH).read_text()) if config is None else config
        self.spec = self.config
        self.task = task
        self.hand = hands.selected(hand)
        self.hand_info = hands.info(self.hand)
        self.robot = {"sharpa": "marvin-bimanual-sharpa-wave", "wuji": "marvin-bimanual-wuji-hand-2.2"}[self.hand]
        self.model, self.xml = build(self.config, asset_dir, self.hand)
        self.data = mujoco.MjData(self.model)
        self.action_dim = self.model.nu
        names = [self.model.actuator(i).name for i in range(self.model.nu)]
        # Start: the arm pose of task.json (named targets); every finger target 0 (open hands), clipped to its range.
        targets = np.zeros(self.action_dim)
        for name, value in self.config["initial_targets"][self.hand].items():
            targets[names.index(name)] = value
        self.initial_targets = np.clip(targets, *self.model.actuator_ctrlrange.T)
        self.control_dt = float(self.config["control_dt"])
        self.substeps = round(self.control_dt / self.config["physics_dt"])
        self.max_control_steps = int(self.config["max_steps"])
        self.qadr = self.model.jnt_qposadr[self.model.actuator_trnid[:, 0]]
        self.joint_names = [self.model.joint(int(j)).name for j in self.model.actuator_trnid[:, 0]]
        self.actuator_names = [self.model.actuator(i).name for i in range(self.model.nu)]
        self.tcp_bodies = ["right_wrist_stage", "left_wrist_stage"]
        self.lo, self.hi = self.model.actuator_ctrlrange.T.copy()
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
        self.checker.reset(self.data)
        self.initial_sha = self.state_sha()
        return self.status()

    def hold_action(self):
        return self.data.ctrl.copy()

    @property
    def done(self):
        return self.checker.done

    @property
    def success(self):
        return self.checker.success

    @property
    def failure(self):
        return self.checker.failure

    @property
    def failure_detail(self):
        return self.checker.failure_detail

    def validate(self, action):
        values = np.asarray(action, dtype=np.float64)
        if values.shape != (self.action_dim,) or not np.isfinite(values).all():
            raise ValueError(f"Expected {self.action_dim} finite actuator targets")
        if np.any(values < self.lo - BOUND_TOL) or np.any(values > self.hi + BOUND_TOL):
            raise ValueError("Actuator targets exceed native joint bounds")
        return np.clip(values, self.lo, self.hi)

    def step(self, action):
        values = self.validate(action)
        if self.done:
            # The episode ended at the first success or failure; later rows are not executed.
            return self.status()
        self.data.ctrl[:] = values
        for substep in range(self.substeps):
            mujoco.mj_step(self.model, self.data)
            if self.checker.substep(self.data, self.steps, substep):
                break
        self.steps += 1
        mujoco.mj_forward(self.model, self.data)
        self.checker.control(self.data, self.steps)
        if self.steps >= self.max_control_steps and not self.done:
            self.checker._fail("episode_budget", {"control": self.steps})
        return self.status()

    def status(self):
        f = self.checker.features(self.data)
        c = self.checker
        return {
            **f,
            "success": bool(c.success),
            "done": bool(c.done),
            "failed": bool(c.failure),
            "failure": c.failure,
            "failure_detail": c.failure_detail,
            "steps": self.steps,
            "stage": int(c.stage),
            "total_stages": 2,
            "reason": "success" if c.success else (c.failure or ""),
            "hand": self.hand,
        }

    def features(self):
        return self.status()

    def replay(self, actions):
        """Reset, execute rows until the episode ends (success or failure) or the rows run out."""
        self.reset()
        for action in np.asarray(actions, dtype=np.float64):
            self.step(action)
            if self.done:
                break
        return self.status()

    # ------------------------------------------------------------------ snapshots / hashes
    def snapshot(self):
        state = np.empty(mujoco.mj_stateSize(self.model, mujoco.mjtState.mjSTATE_INTEGRATION))
        mujoco.mj_getState(self.model, self.data, state, mujoco.mjtState.mjSTATE_INTEGRATION)
        return {"state": state, "steps": self.steps, "checker": copy.deepcopy(self.checker.state())}

    def restore(self, snap):
        mujoco.mj_setState(self.model, self.data, snap["state"], mujoco.mjtState.mjSTATE_INTEGRATION)
        mujoco.mj_forward(self.model, self.data)
        self.steps = snap["steps"]
        self.checker.set_state(copy.deepcopy(snap["checker"]))
        return self.status()

    def state_sha(self):
        state = np.empty(mujoco.mj_stateSize(self.model, mujoco.mjtState.mjSTATE_INTEGRATION))
        mujoco.mj_getState(self.model, self.data, state, mujoco.mjtState.mjSTATE_INTEGRATION)
        digest = hashlib.sha256(state.astype("<f8").tobytes())
        c = self.checker.state()
        digest.update(json.dumps({k: c[k] for k in ("stage", "hold", "success", "failure")}, sort_keys=True).encode())
        digest.update(str(self.steps).encode())
        # Only the physics / predicate parameters of the instance enter the hash (never texts or camera framing).
        digest.update(json.dumps({k: self.config[k] for k in PHYSICS_KEYS}, sort_keys=True).encode())
        digest.update(self.hand.encode())
        return digest.hexdigest()

    def save_trajectory(self, actions, path):
        """Write the privileged deliverable: ``actions`` plus this session's ``hand`` and ``task``."""
        hands.write_trajectory(path, actions, hand=self.hand, task=self.task)

    # ------------------------------------------------------------------ rendering
    def cameras(self):
        return list(self.config["cameras"])

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
