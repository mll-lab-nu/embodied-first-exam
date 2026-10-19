"""Actuator-only drying-rack dynamics with an observable, fail-fast unfold-and-stand predicate."""

from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path

os.environ.setdefault("MUJOCO_GL", "egl")

import mujoco
import numpy as np

from checker import STAGE_NAMES, RackChecker
from scene import build, hands

CONFIG_PATH = Path(__file__).with_name("task.json")
TASK = "drying_rack_unfold"
# Only physics and predicate parameters enter state_sha (instruction prose can change without changing evidence).
PHYSICS_KEYS = ("physics_dt", "control_dt", "max_steps", "table_z", "counter", "rack_pos", "wrist_stage",
                "initial_targets", "predicate")


class Session:
    """One frozen drying-rack episode. ``hand`` is ``sharpa`` (default) or ``wuji``; when omitted, the
    ``DEXHAND_HAND`` environment variable selects it. Graders pass the hand recorded with the trajectory."""

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
        self.control_dt = float(self.config["control_dt"])
        self.substeps = round(self.control_dt / self.config["physics_dt"])
        self.max_control_steps = int(self.config["max_steps"])
        self.qadr = self.model.jnt_qposadr[self.model.actuator_trnid[:, 0]]
        self.joint_names = [self.model.joint(int(j)).name for j in self.model.actuator_trnid[:, 0]]
        self.actuator_names = [self.model.actuator(i).name for i in range(self.model.nu)]
        self.robot = "sharpa-wave-floating" if self.hand == "sharpa" else "wuji-hand-2.2-floating"
        self.tcp_body = "right_hand_C_MC"  # hand mount body (wrapper of the same name for Wuji)
        self.checker = RackChecker(self.model, self.config)
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
        self.actions = []
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

    def cameras(self):
        return [c["name"] for c in self.config["cameras"]]

    def _fail(self, reason, detail):
        self.checker.failure = reason
        self.checker.failure_detail = detail

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
        for substep in range(self.substeps):
            mujoco.mj_step(self.model, self.data)
            if any(
                self.data.warning[w].number
                for w in (
                    mujoco.mjtWarning.mjWARN_BADQPOS,
                    mujoco.mjtWarning.mjWARN_BADQVEL,
                    mujoco.mjtWarning.mjWARN_BADQACC,
                )
            ):
                self._fail("unstable_physics", {"control": self.steps, "substep": substep})
                break
            violation = self.checker.invariant(self.data)
            if violation:
                # Fail fast: the episode ends at the physics substep that broke an invariant.
                self._fail(violation[0], {"what": violation[1], "control": self.steps, "substep": substep})
                break
        self.steps += 1
        mujoco.mj_forward(self.model, self.data)
        f = self.checker.features(self.data)
        if not self.checker.failure:
            self.checker.update(f)
        if self.steps >= self.max_control_steps and not self.done:
            self._fail("episode_budget", {"control": self.steps})
        return self.features(f)

    def features(self, f=None):
        f = dict(self.checker.features(self.data) if f is None else f)
        f.update(
            {
                "stage": int(self.checker.stage),
                "stage_name": (("folded",) + STAGE_NAMES)[int(self.checker.stage)],
                "released_hold_steps": int(self.checker.hold),
                "success": bool(self.checker.success),
                "failure": self.checker.failure,
                "failure_detail": self.checker.failure_detail,
                "steps": self.steps,
            }
        )
        return f

    def status(self):
        f = self.features()
        return {
            **f,
            "done": self.done,
            "total_stages": len(STAGE_NAMES),
            "reason": "success" if self.success else (self.failure or ""),
            "failed": bool(self.failure),
            "hand": self.hand,
        }

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

    # ------------------------------------------------------------------ authoring helpers
    def snapshot(self):
        state = np.empty(mujoco.mj_stateSize(self.model, mujoco.mjtState.mjSTATE_INTEGRATION))
        mujoco.mj_getState(self.model, self.data, state, mujoco.mjtState.mjSTATE_INTEGRATION)
        c = self.checker
        return (state, self.steps, len(self.actions),
                (c.stage, c.hold, c.airborne, c.success, c.failure, c.failure_detail, c.max_stage_seen))

    def restore(self, snap):
        state, steps, n_actions, chk = snap
        mujoco.mj_setState(self.model, self.data, state, mujoco.mjtState.mjSTATE_INTEGRATION)
        mujoco.mj_forward(self.model, self.data)
        self.steps = steps
        del self.actions[n_actions:]
        c = self.checker
        c.stage, c.hold, c.airborne, c.success, c.failure, c.failure_detail, c.max_stage_seen = chk

    def state_sha(self):
        state = np.empty(mujoco.mj_stateSize(self.model, mujoco.mjtState.mjSTATE_INTEGRATION))
        mujoco.mj_getState(self.model, self.data, state, mujoco.mjtState.mjSTATE_INTEGRATION)
        digest = hashlib.sha256(state.astype("<f8").tobytes())
        c = self.checker
        digest.update(json.dumps([c.stage, c.hold, c.airborne, c.success, c.failure, self.steps]).encode())
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
