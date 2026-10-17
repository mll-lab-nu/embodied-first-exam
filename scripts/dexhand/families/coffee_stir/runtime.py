"""Actuator-only coffee stirring dynamics with a strict, state-derived verdict (see checker.py)."""

from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path

os.environ.setdefault("MUJOCO_GL", "egl")

import mujoco
import numpy as np

from checker import STAGES, Checker
from scene import arm_rig, build, hands

CONFIG_PATH = Path(__file__).with_name("task.json")
TASK = "coffee_stir"
PROSE_KEYS = {"title", "category", "description", "difficulty", "mechanism", "instruction", "robot", "modeling"}


class Session:
    """One frozen coffee stirring episode. ``hand`` is ``sharpa`` (default) or ``wuji``; when omitted, the
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
        self.initial_targets = np.clip(
            np.asarray(self.config["initial_targets"][self.hand], dtype=float), *self.model.actuator_ctrlrange.T
        )
        if self.initial_targets.shape != (self.action_dim,):
            raise ValueError(f"initial_targets[{self.hand}] must have {self.action_dim} values")
        self.initial_qpos = np.asarray(self.config["initial_qpos"][self.hand], dtype=float)
        if self.initial_qpos.shape != (self.model.nq,):
            raise ValueError(f"initial_qpos[{self.hand}] must have {self.model.nq} values")
        self.control_dt = self.config["control_dt"]
        self.substeps = round(self.control_dt / self.config["physics_dt"])
        self.max_control_steps = int(self.config["max_steps"])
        self.qadr = self.model.jnt_qposadr[self.model.actuator_trnid[:, 0]]
        self.joint_names = [self.model.joint(int(j)).name for j in self.model.actuator_trnid[:, 0]]
        self.actuator_names = [self.model.actuator(i).name for i in range(self.model.nu)]
        self.tcp_body = "wrist_stage"  # the right hand's flange mount on the Marvin arm
        self.checker = Checker(self.model, self.config)
        self.renderer = None
        self.reset()

    # ------------------------------------------------------------------ episode
    def reset(self):
        """Exact frozen reset: the settled start state (spoon lying on the worktop, arms at their start pose)."""
        mujoco.mj_resetData(self.model, self.data)
        self.data.qpos[:] = self.initial_qpos
        self.data.ctrl[:] = self.initial_targets
        mujoco.mj_forward(self.model, self.data)
        self.steps = 0
        self.checker.reset(self.data)
        self.last = self.checker.update(self.data)
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
        return bool(self.checker.success or self.checker.failure)

    def hold_action(self):
        return self.data.ctrl.copy()

    def cameras(self):
        return ["overview", "closeup", "top"]

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
        ck = self.checker
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
                ck.failure = "unstable_physics"
                ck.failure_detail = {"control": self.steps, "substep": substep}
                break
            violation = ck.violation(self.data)
            if violation:
                # Fail fast: the episode ends at the physics substep that broke an invariant.
                ck.failure, detail = violation
                ck.failure_detail = {**detail, "control": self.steps, "substep": substep}
                break
        self.steps += 1
        mujoco.mj_forward(self.model, self.data)
        self.last = ck.update(self.data)
        if self.steps >= self.max_control_steps and not self.done:
            ck.failure = "episode_budget"
            ck.failure_detail = {"control": self.steps}
        return self.features()

    def replay(self, actions):
        """Reset, execute rows until the episode ends (success or failure) or the rows run out."""
        self.reset()
        for action in np.asarray(actions, dtype=np.float64):
            self.step(action)
            if self.done:
                break
        return self.status()

    # ------------------------------------------------------------- snapshots
    def snapshot(self):
        # INTEGRATION includes ctrl and the solver warm start, so a restored episode continues bit for bit.
        state = np.empty(mujoco.mj_stateSize(self.model, mujoco.mjtState.mjSTATE_INTEGRATION))
        mujoco.mj_getState(self.model, self.data, state, mujoco.mjtState.mjSTATE_INTEGRATION)
        return {"physics": state, "ctrl": self.data.ctrl.copy(), "warning": [int(self.data.warning[w].number)
                for w in range(len(self.data.warning))], "steps": self.steps, "checker": self.checker.snapshot(),
                "last": dict(self.last)}

    def restore(self, snap):
        mujoco.mj_setState(self.model, self.data, snap["physics"], mujoco.mjtState.mjSTATE_INTEGRATION)
        for w, n in enumerate(snap["warning"]):
            self.data.warning[w].number = n
        mujoco.mj_forward(self.model, self.data)  # derived quantities (poses, contacts) for the checker
        mujoco.mj_setState(self.model, self.data, snap["physics"], mujoco.mjtState.mjSTATE_INTEGRATION)
        self.steps = snap["steps"]
        self.checker.restore(snap["checker"])
        self.last = dict(snap["last"])

    def save_trajectory(self, actions, path):
        """Write the privileged deliverable: ``actions`` plus this session's ``hand`` and ``task``."""
        hands.write_trajectory(path, actions, hand=self.hand, task=self.task)

    def state_sha(self):
        state = np.empty(mujoco.mj_stateSize(self.model, mujoco.mjtState.mjSTATE_INTEGRATION))
        mujoco.mj_getState(self.model, self.data, state, mujoco.mjtState.mjSTATE_INTEGRATION)
        digest = hashlib.sha256(state.astype("<f8").tobytes())
        digest.update(self.checker.get_state().astype("<f8").tobytes())
        digest.update(str(self.checker.failure).encode())
        # Physics/predicate parameters only: editing the prose (title, instruction, notes) never changes evidence hashes.
        params = {k: v for k, v in self.config.items() if k not in PROSE_KEYS}
        digest.update(json.dumps(params, sort_keys=True).encode())
        digest.update(self.hand.encode())
        return digest.hexdigest()

    # --------------------------------------------------------------- render
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
