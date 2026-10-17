"""Actuator-only desk-fan front-guard installation with a strict state-derived verdict."""

from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path

os.environ.setdefault("MUJOCO_GL", "egl")

import mujoco
import numpy as np

from checker import STAGES, Checker
from geometry import OPEN
from scene import build, hands

CONFIG_PATH = Path(__file__).with_name("task.json")
TASK = "fan_guard_install"
# Bound tolerance: float32 rounding of a target at its bound (relative 6e-8) must not reject a row.
TOL = 1e-6
# task.json keys that define the physics and the predicate (hashed into state_sha).
PHYSICS_KEYS = ("id", "physics_dt", "control_dt", "max_steps", "wrist_stage", "initial_targets", "checker")


class Session:
    """One frozen fan-guard episode. ``hand`` is ``sharpa`` (default) or ``wuji``; when omitted, the ``DEXHAND_HAND``
    environment variable selects it. Graders pass the hand recorded with the trajectory."""

    def __init__(self, task=TASK, instance=None, asset_dir=None, config=None, hand=None):
        if task != TASK:
            raise ValueError("Unknown task: " + str(task))
        self.config = json.loads(Path(instance or CONFIG_PATH).read_text()) if config is None else config
        self.spec = self.config
        self.task = task
        self.hand = hands.selected(hand)
        self.hand_info = hands.info(self.hand)
        self.model, self.xml = build(self.config, asset_dir, self.hand)
        self.data = mujoco.MjData(self.model)
        self.action_dim = self.model.nu
        self.initial_targets = np.asarray(self.config["initial_targets"][self.hand], dtype=float)
        if self.initial_targets.shape != (self.action_dim,):
            raise ValueError(f"initial_targets[{self.hand}] must have {self.action_dim} values")
        self.control_dt = self.config["control_dt"]
        self.substeps = round(self.control_dt / self.config["physics_dt"])
        self.max_control_steps = int(self.config["max_steps"])
        self.robot = self.hand_info["robot"] + "-floating"
        self.tcp_body = self.model.body(int(self.model.jnt_bodyid[self.model.actuator_trnid[5, 0]])).name
        self.qadr = self.model.jnt_qposadr[self.model.actuator_trnid[:, 0]]
        self.joint_names = [self.model.joint(int(j)).name for j in self.model.actuator_trnid[:, 0]]
        self.actuator_names = [self.model.actuator(i).name for i in range(self.model.nu)]
        self.clip_qadr = np.array([self.model.jnt_qposadr[self.model.joint(f"clip_hinge_{i}").id] for i in range(4)])
        self.checker = Checker(self.model, self.config)
        self.renderer = None
        self.reset()

    # ------------------------------------------------------------------ episode
    def reset(self):
        mujoco.mj_resetData(self.model, self.data)
        self.data.qpos[self.qadr] = self.initial_targets
        self.data.qpos[self.clip_qadr] = OPEN  # all four perimeter clips start open (source start state)
        self.data.ctrl[:] = self.initial_targets
        mujoco.mj_forward(self.model, self.data)
        self.steps = 0
        self.checker.reset(self.data)
        self.last = self.checker.evaluate(self.data, 0)
        self.checker.hold = 0
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
        return [cam["name"] for cam in self.config["cameras"]]

    def features(self):
        return {
            **self.last,
            "stage": self.checker.stage,
            "stage_name": STAGES[self.checker.stage - 1] if self.checker.stage else "",
            "success": self.success,
            "failure": self.failure,
            "failure_detail": self.failure_detail,
            "steps": self.steps,
        }

    def status(self):
        return {
            **self.features(),
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
        if np.any(values < lo - TOL) or np.any(values > hi + TOL):
            raise ValueError("Actuator targets exceed native joint bounds")
        if self.done:
            # The episode ended at the first success or failure; later rows are not executed.
            return self.features()
        self.data.ctrl[:] = np.clip(values, lo, hi)
        checker = self.checker
        for substep in range(self.substeps):
            mujoco.mj_step(self.model, self.data)
            if not np.isfinite(self.data.qpos).all() or any(
                self.data.warning[w].number
                for w in (mujoco.mjtWarning.mjWARN_BADQPOS, mujoco.mjtWarning.mjWARN_BADQVEL,
                          mujoco.mjtWarning.mjWARN_BADQACC)
            ):
                checker.failure = "unstable_physics"
                checker.failure_detail = {"control": self.steps, "substep": substep}
                break
            violation = checker.invariant_violation(self.data)
            if violation:
                # Fail fast: the episode ends at the physics substep that broke an invariant.
                checker.failure, detail = violation
                checker.failure_detail = {**detail, "control": self.steps, "substep": substep}
                break
        self.steps += 1
        mujoco.mj_forward(self.model, self.data)
        self.last = checker.evaluate(self.data, self.steps)
        if self.failure:
            checker.success = False
            checker.hold = 0
        if self.steps >= self.max_control_steps and not self.success and not self.failure:
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

    # ------------------------------------------------------------------ tooling
    def snapshot(self):
        """Full simulator + predicate state (authoring/search tooling; never part of a graded replay)."""
        size = mujoco.mj_stateSize(self.model, mujoco.mjtState.mjSTATE_INTEGRATION)
        state = np.empty(size)
        mujoco.mj_getState(self.model, self.data, state, mujoco.mjtState.mjSTATE_INTEGRATION)
        return {"state": state, "ctrl": self.data.ctrl.copy(), "steps": self.steps, "last": dict(self.last),
                "checker": self.checker.snapshot()}

    def restore(self, snap):
        mujoco.mj_setState(self.model, self.data, snap["state"], mujoco.mjtState.mjSTATE_INTEGRATION)
        self.data.ctrl[:] = snap["ctrl"]
        mujoco.mj_forward(self.model, self.data)
        self.steps = snap["steps"]
        self.last = dict(snap["last"])
        self.checker.restore(snap["checker"])

    def state_sha(self):
        state = np.empty(mujoco.mj_stateSize(self.model, mujoco.mjtState.mjSTATE_INTEGRATION))
        mujoco.mj_getState(self.model, self.data, state, mujoco.mjtState.mjSTATE_INTEGRATION)
        digest = hashlib.sha256(state.astype("<f8").tobytes())
        digest.update(np.asarray(self.checker.scalars(), dtype="<f8").tobytes())
        digest.update(str(self.checker.failure).encode())
        # Physics and predicate parameters only (never instruction prose, titles or presentation cameras).
        digest.update(json.dumps({k: self.config[k] for k in PHYSICS_KEYS}, sort_keys=True).encode())
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
