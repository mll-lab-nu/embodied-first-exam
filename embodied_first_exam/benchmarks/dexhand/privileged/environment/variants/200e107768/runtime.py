"""Actuator-only stool brace insertion dynamics with a strict state-derived verdict (see checker.py)."""

from __future__ import annotations

import copy
import hashlib
import json
import os
from pathlib import Path

os.environ.setdefault("MUJOCO_GL", "egl")

import mujoco
import numpy as np

from checker import STAGES, Checker
from scene import build, hands

TASK = "stool_brace_insert"
CONFIG_PATH = Path(__file__).with_name("task.json")
# Descriptive texts never enter the evidence hashes (editing prose must not change state_sha).
TEXT_KEYS = {"title", "description", "instruction", "modeling", "category", "difficulty", "mechanism", "robot"}
_UNSTABLE = (mujoco.mjtWarning.mjWARN_BADQPOS, mujoco.mjtWarning.mjWARN_BADQVEL, mujoco.mjtWarning.mjWARN_BADQACC)


class Session:
    """One frozen stool episode. ``hand`` is ``sharpa`` (default) or ``wuji``; when omitted, ``DEXHAND_HAND`` selects
    it. Graders pass the hand recorded with the trajectory."""

    def __init__(self, task=TASK, instance=None, asset_dir=None, config=None, hand=None):
        if task != TASK:
            raise ValueError("Unknown task: " + str(task))
        self.config = json.loads(Path(instance or CONFIG_PATH).read_text()) if config is None else config
        self.spec = self.config
        self.task = task
        self.hand = hands.selected(hand)
        self.hand_info = hands.info(self.hand)
        self.robot = self.hand_info["robot"] + "-floating"
        self.model, self.xml = build(self.config, asset_dir, self.hand)
        self.data = mujoco.MjData(self.model)
        self.action_dim = self.model.nu
        self.initial_targets = np.asarray(self.config["initial_targets"][self.hand], dtype=float)
        if self.initial_targets.shape != (self.action_dim,):
            raise ValueError(f"initial_targets[{self.hand}] must have {self.action_dim} values")
        self.control_dt = float(self.config["control_dt"])
        self.substeps = round(self.control_dt / self.config["physics_dt"])
        self.max_control_steps = int(self.config["max_steps"])
        self.qadr = self.model.jnt_qposadr[self.model.actuator_trnid[:, 0]]
        self.joint_names = [self.model.joint(int(j)).name for j in self.model.actuator_trnid[:, 0]]
        self.actuator_names = [self.model.actuator(i).name for i in range(self.model.nu)]
        self.tcp_body = "wrist_stage"
        self.checker = Checker(self.model, self.config)
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
        self.actions = []
        self.checker.reset(self.data)
        self.last = self.checker.evaluate(self.model, self.data)
        self.initial_sha = self.state_sha()
        return self.status()

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
        return bool(self.checker.success or self.checker.failure)

    def hold_action(self):
        return self.data.ctrl.copy()

    def cameras(self):
        return ["overview", "closeup", "side"]

    def features(self):
        return {
            **self.last,
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
            "stage": self.checker.stage,
            "total_stages": len(STAGES),
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
            return self.features()
        self.data.ctrl[:] = np.clip(values, lo, hi)
        self.actions.append(self.data.ctrl.copy())
        checker = self.checker
        for substep in range(self.substeps):
            mujoco.mj_step(self.model, self.data)
            if any(self.data.warning[w].number for w in _UNSTABLE):
                checker.failure = "unstable_physics"
                checker.failure_detail = {"control": self.steps, "substep": substep}
                break
            violation = checker.invariant_violation(self.data)
            if violation:
                # Fail fast: the episode ends at the physics substep that broke an invariant.
                checker.failure, part = violation
                checker.failure_detail = {"part": part, "control": self.steps, "substep": substep}
                break
        self.steps += 1
        mujoco.mj_forward(self.model, self.data)
        self.last = checker.evaluate(self.model, self.data)
        if self.steps >= self.max_control_steps and not self.done:
            checker.failure = "episode_budget"
            checker.failure_detail = {"control": self.steps}
        return self.features()

    def replay(self, actions):
        """Reset, execute rows until the episode ends (success or failure) or the rows run out."""
        self.reset()
        for action in np.asarray(actions, dtype=np.float64):
            self.step(action)
            if self.done:
                break
        return self.status()

    def save_trajectory(self, actions, path):
        """Write the privileged deliverable: ``actions`` plus this session's ``hand`` and ``task``."""
        hands.write_trajectory(path, actions, hand=self.hand, task=self.task)

    # ------------------------------------------------------------------ snapshots (authoring / search)
    def snapshot(self):
        state = np.empty(mujoco.mj_stateSize(self.model, mujoco.mjtState.mjSTATE_INTEGRATION))
        mujoco.mj_getState(self.model, self.data, state, mujoco.mjtState.mjSTATE_INTEGRATION)
        return {
            "state": state,
            "steps": self.steps,
            "n_actions": len(self.actions),
            "checker": self.checker.get_state(),
            "last": copy.deepcopy(self.last),
        }

    def restore(self, snap):
        mujoco.mj_setState(self.model, self.data, snap["state"], mujoco.mjtState.mjSTATE_INTEGRATION)
        mujoco.mj_forward(self.model, self.data)
        self.steps = snap["steps"]
        del self.actions[snap["n_actions"]:]
        self.checker.set_state(snap["checker"])
        self.last = copy.deepcopy(snap["last"])

    def state_sha(self):
        state = np.empty(mujoco.mj_stateSize(self.model, mujoco.mjtState.mjSTATE_INTEGRATION))
        mujoco.mj_getState(self.model, self.data, state, mujoco.mjtState.mjSTATE_INTEGRATION)
        digest = hashlib.sha256(state.astype("<f8").tobytes())
        physics = {k: v for k, v in self.config.items() if k not in TEXT_KEYS}
        digest.update(json.dumps(physics, sort_keys=True).encode())
        digest.update(json.dumps(self.checker.get_state(), sort_keys=True).encode())
        digest.update(self.hand.encode())
        return digest.hexdigest()

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
