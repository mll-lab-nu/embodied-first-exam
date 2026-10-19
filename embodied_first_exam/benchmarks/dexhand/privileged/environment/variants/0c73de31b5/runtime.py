"""Actuator-only jam-jar lid opening: one genuine hand on the Tianji Marvin right arm, passive contact thread."""

from __future__ import annotations

import copy
import hashlib
import json
import os
from pathlib import Path

os.environ.setdefault("MUJOCO_GL", "egl")

import mujoco
import numpy as np

from checker import HOLD_STEPS, STAGES, Checker
from scene import arm_rig, build, hands

CONFIG_PATH = Path(__file__).with_name("task.json")
TASK = "jar_lid_open"
HASHED_CONFIG = ("id", "physics_dt", "control_dt", "max_steps", "table_z", "table_half", "jar_xy", "workspace",
                 "rig", "marvin", "initial_targets", "release_angle_rad", "stop_angle_rad")
UNSTABLE = (mujoco.mjtWarning.mjWARN_BADQPOS, mujoco.mjtWarning.mjWARN_BADQVEL, mujoco.mjtWarning.mjWARN_BADQACC)


class Session:
    """One frozen jar-opening episode. ``hand`` is ``sharpa`` (default) or ``wuji``; when omitted, the
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
        self.control_dt = float(self.config["control_dt"])
        self.substeps = round(self.control_dt / self.config["physics_dt"])
        self.max_control_steps = int(self.config["max_steps"])
        self.qadr = self.model.jnt_qposadr[self.model.actuator_trnid[:, 0]]
        self.joint_names = [self.model.joint(int(j)).name for j in self.model.actuator_trnid[:, 0]]
        self.actuator_names = [self.model.actuator(i).name for i in range(self.model.nu)]
        self.tcp_body = "wrist_stage"
        self.layout = arm_rig.layout(self.model)
        self.checker = Checker(self.model, self.config)
        self.renderer = None
        self.reset()

    # ------------------------------------------------------------------------------------------ episode
    def reset(self):
        mujoco.mj_resetData(self.model, self.data)
        self.data.qpos[self.qadr] = self.initial_targets
        self.data.ctrl[:] = self.initial_targets
        mujoco.mj_forward(self.model, self.data)
        self.steps = 0
        self.checker.reset_state(self.data)
        self.initial_sha = self.state_sha()

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

    def validate(self, action):
        values = np.asarray(action, dtype=np.float64)
        if values.shape != (self.action_dim,) or not np.isfinite(values).all():
            raise ValueError(f"Expected {self.action_dim} finite actuator targets")
        lo, hi = self.model.actuator_ctrlrange.T
        if np.any(values < lo - 1e-6) or np.any(values > hi + 1e-6):
            raise ValueError("Actuator targets exceed native joint bounds")
        return np.clip(values, lo, hi)

    def step(self, action):
        values = self.validate(action)
        if self.done:
            # The episode ended at the first success or failure; later rows are not executed.
            return self.features()
        self.data.ctrl[:] = values
        for substep in range(self.substeps):
            mujoco.mj_step(self.model, self.data)
            if any(self.data.warning[w].number for w in UNSTABLE):
                self.checker.failure = "unstable_physics"
                self.checker.failure_detail = {"control": self.steps, "substep": substep}
                break
            if self.checker.substep(self.data, self.steps, substep):
                break
        self.steps += 1
        if not self.done:
            self.checker.control_end(self.data)
        if self.steps >= self.max_control_steps and not self.done:
            self.checker.failure = "episode_budget"
            self.checker.failure_detail = {"control": self.steps}
        return self.features()

    def features(self):
        f = self.checker.features(self.data)
        f["steps"] = self.steps
        f["positions"] = {name: self.data.xpos[self.model.body(name).id].tolist() for name in ("jar", "lid")}
        return f

    def status(self):
        f = self.features()
        return {
            **f,
            "done": self.done,
            "stage": self.checker.stage,
            "total_stages": len(STAGES),
            "stages": list(STAGES),
            "hold_required": HOLD_STEPS,
            "reason": "success" if self.success else (self.failure or ""),
            "failed": bool(self.failure),
            "hand": self.hand,
        }

    def cameras(self):
        return ["overview", "closeup", "side", "wide"]

    # ------------------------------------------------------------------------------------------ tooling
    def snapshot(self):
        """Full physics + checker state (for search/rollouts); ``restore`` returns to it exactly."""
        spec = mujoco.mjtState.mjSTATE_INTEGRATION
        state = np.empty(mujoco.mj_stateSize(self.model, spec))
        mujoco.mj_getState(self.model, self.data, state, spec)
        return {"physics": state, "steps": self.steps, "checker": copy.deepcopy(self.checker.state())}

    def restore(self, snap):
        mujoco.mj_setState(self.model, self.data, snap["physics"], mujoco.mjtState.mjSTATE_INTEGRATION)
        mujoco.mj_forward(self.model, self.data)
        self.steps = snap["steps"]
        self.checker.load(copy.deepcopy(snap["checker"]))

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

    def state_sha(self):
        spec = mujoco.mjtState.mjSTATE_INTEGRATION
        state = np.empty(mujoco.mj_stateSize(self.model, spec))
        mujoco.mj_getState(self.model, self.data, state, spec)
        digest = hashlib.sha256(state.astype("<f8").tobytes())
        digest.update(self.checker.digest_values().tobytes())
        digest.update(str(self.checker.failure).encode())
        # Physics and predicate parameters only (never the task prose), so text edits keep the evidence hashes.
        digest.update(json.dumps({k: v for k, v in self.config.items() if k in HASHED_CONFIG}, sort_keys=True).encode())
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
