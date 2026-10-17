"""Actuator-only vacuum dust-bin reseat dynamics with an ordered, fail-fast predicate."""

from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path

os.environ.setdefault("MUJOCO_GL", "egl")

import mujoco
import numpy as np

from checker import Checker
import scene as scene_module
from scene import build, hands

CONFIG_PATH = Path(__file__).with_name("task.json")
TASK = "vacuum_bin_reseat"
TEXT_KEYS = {"schema_version", "title", "category", "difficulty", "description", "instruction", "mechanism",
             "release_status", "robot", "modeling"}


class Session:
    """One frozen vacuum episode. ``hand`` is ``sharpa`` (default) or ``wuji``; when omitted, the
    ``DEXHAND_HAND`` environment variable selects it. Graders pass the hand recorded with the trajectory."""

    def __init__(self, task=TASK, instance=None, asset_dir=None, config=None, hand=None):
        if task != TASK:
            raise ValueError("Unknown task: " + str(task))
        self.config = json.loads(Path(instance or CONFIG_PATH).read_text()) if config is None else config
        self.spec = self.config
        self.task = task
        self.hand = hands.selected(hand)
        self.hand_info = hands.info(self.hand)
        if self.config.get("rig", "floating") == "marvin":
            self.robot = scene_module.arm_rig_id()
        elif "left_wrist_stage" in self.config:
            self.robot = self.hand_info["robot"] + "-floating-bimanual"
        else:
            self.robot = self.hand_info["robot"] + "-floating"
        self.model, self.xml = build(self.config, asset_dir, self.hand)
        self.data = mujoco.MjData(self.model)
        self.action_dim = self.model.nu
        self.initial_targets = np.asarray(self.config["initial_targets"][self.hand], dtype=float)
        if self.initial_targets.shape != (self.action_dim,):
            raise ValueError(f"initial_targets[{self.hand}] must have {self.action_dim} values")
        self.control_dt = self.config["control_dt"]
        self.substeps = round(self.control_dt / self.config["physics_dt"])
        self.max_control_steps = self.config["max_steps"]
        self.qadr = self.model.jnt_qposadr[self.model.actuator_trnid[:, 0]]
        self.joint_names = [self.model.joint(int(j)).name for j in self.model.actuator_trnid[:, 0]]
        self.actuator_names = [self.model.actuator(i).name for i in range(self.model.nu)]
        if self.config.get("rig", "floating") == "marvin":
            self.tcp_body = "wrist_stage"  # the right hand's flange mount
        else:
            self.tcp_body = self.model.body(int(self.model.jnt_bodyid[self.model.actuator_trnid[5, 0]])).name
        self.object_qadr = int(self.model.jnt_qposadr[self.model.joint("vacuum_free").id])
        self.object_qpos = np.asarray(self.config["initial_object_qpos"], dtype=float)
        self.checker = Checker(self.model, self.config)
        self.renderer = None
        self.reset()

    # ------------------------------------------------------------------ episode
    def reset(self):
        mujoco.mj_resetData(self.model, self.data)
        self.data.qpos[self.qadr] = self.initial_targets
        self.data.qpos[self.object_qadr:self.object_qadr + self.object_qpos.size] = self.object_qpos
        self.data.ctrl[:] = self.initial_targets
        mujoco.mj_forward(self.model, self.data)
        self.checker.reset_state(self.data)
        self.steps = 0
        self.actions = []
        self.initial_sha = self.state_sha()

    def hold_action(self):
        return self.data.ctrl.copy()

    @property
    def success(self):
        return self.checker.success

    @property
    def failure(self):
        return self.checker.failure

    @property
    def failure_detail(self):
        return self.checker.failure_detail

    @property
    def done(self):
        return bool(self.success or self.failure)

    def cameras(self):
        return ["overview", "closeup"]

    def features(self):
        f = self.checker.features(self.data)
        f["steps"] = self.steps
        return f

    def status(self):
        f = self.features()
        return {
            **f,
            "done": self.done,
            "stage": self.checker.stage if not self.success else 3,
            "total_stages": 3,
            "reason": "success" if self.success else (self.failure or ""),
            "failed": bool(self.failure),
            "hand": self.hand,
        }

    def step(self, action):
        values = np.asarray(action, dtype=np.float64)
        if values.shape != (self.action_dim,) or not np.isfinite(values).all():
            raise ValueError(f"Expected {self.action_dim} finite actuator targets")
        lo, hi = self.model.actuator_ctrlrange.T
        if np.any(values < lo - 1e-6) or np.any(values > hi + 1e-6):
            raise ValueError("Actuator targets exceed native joint bounds")
        if self.done:
            # The episode ended at the first success or failure; later rows are not executed.
            return self.status()
        self.data.ctrl[:] = np.clip(values, lo, hi)
        self.actions.append(self.data.ctrl.copy())
        for substep in range(self.substeps):
            mujoco.mj_step(self.model, self.data)
            reason = self.checker.substep(self.data)
            if reason:
                self.checker.failure_detail = {**(self.checker.failure_detail or {}), "control": self.steps,
                                               "substep": substep}
                break
        self.steps += 1
        mujoco.mj_forward(self.model, self.data)
        self.checker.control(self.data, self.steps)
        if self.steps >= self.max_control_steps and not self.done:
            self.checker.fail("episode_budget", {"control": self.steps})
        return self.status()

    def replay(self, actions):
        """Reset, execute rows until the episode ends (success or failure) or the rows run out."""
        self.reset()
        for action in np.asarray(actions, dtype=np.float64):
            self.step(action)
            if self.done:
                break
        return self.status()

    # ------------------------------------------------------------------ search helpers (privileged tooling)
    def snapshot(self):
        size = mujoco.mj_stateSize(self.model, mujoco.mjtState.mjSTATE_INTEGRATION)
        state = np.empty(size)
        mujoco.mj_getState(self.model, self.data, state, mujoco.mjtState.mjSTATE_INTEGRATION)
        return {"state": state, "checker": self.checker.snapshot(), "steps": self.steps,
                "actions": len(self.actions)}

    def restore(self, snap):
        mujoco.mj_setState(self.model, self.data, snap["state"], mujoco.mjtState.mjSTATE_INTEGRATION)
        mujoco.mj_forward(self.model, self.data)
        self.checker.restore(snap["checker"])
        self.steps = snap["steps"]
        del self.actions[snap["actions"]:]

    def save_trajectory(self, actions, path):
        """Write the privileged deliverable: ``actions`` plus this session's ``hand`` and ``task``."""
        hands.write_trajectory(path, actions, hand=self.hand, task=self.task)

    def state_sha(self):
        state = np.empty(mujoco.mj_stateSize(self.model, mujoco.mjtState.mjSTATE_INTEGRATION))
        mujoco.mj_getState(self.model, self.data, state, mujoco.mjtState.mjSTATE_INTEGRATION)
        digest = hashlib.sha256(state.astype("<f8").tobytes())
        digest.update(json.dumps(self.checker.predicate_state()).encode())
        # Physics and predicate parameters only (never instruction prose), so text edits keep the evidence hashes.
        params = {k: v for k, v in self.config.items() if k not in TEXT_KEYS}
        digest.update(json.dumps(params, sort_keys=True).encode())
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
