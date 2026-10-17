"""Actuator-only ring-binder page loading with a strict state-derived verdict (DexHand family plugin)."""

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

TASK = "binder_page_load"
CONFIG_PATH = Path(__file__).with_name("task.json")
STAGE_NAMES = ["rings_opened", "pages_placed", "rings_closed", "released_hold"]
PROSE_KEYS = {"title", "description", "instruction", "category", "difficulty", "mechanism", "robot", "modeling",
              "release_status"}


class Session:
    """One frozen binder episode. ``hand`` is ``sharpa`` (default) or ``wuji``; when omitted, the ``DEXHAND_HAND``
    environment variable selects it. Graders pass the hand recorded with the trajectory."""

    total_stages = len(STAGE_NAMES)

    def __init__(self, task=TASK, instance=None, asset_dir=None, config=None, hand=None):
        if task != TASK:
            raise ValueError("Unknown task: " + str(task))
        self.config = json.loads(Path(instance or CONFIG_PATH).read_text()) if config is None else config
        self.spec = self.config
        self.task = task
        self.hand = hands.selected(hand)
        self.hand_info = hands.info(self.hand)
        self.robot = "sharpa-wave-floating" if self.hand == "sharpa" else "wuji-hand-2.2-floating"
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
        self.tcp_body = "wrist_stage"
        self.checker = Checker(self.model, self.config)
        self.renderer = None
        self.reset()

    # ------------------------------------------------------------------ episode
    def reset(self):
        mujoco.mj_resetData(self.model, self.data)
        self.data.qpos[self.qadr] = self.initial_targets
        self.data.ctrl[:] = self.initial_targets
        mujoco.mj_forward(self.model, self.data)
        self.reset_binder = self.data.xpos[self.checker.binder].copy()
        self.steps = 0
        self.stage = 0
        self.hold = 0
        self.hold_ref = None
        self.success = False
        self.failure = None
        self.failure_detail = None
        self.stage_steps = []
        self.initial_sha = self.state_sha()

    @property
    def done(self):
        return bool(self.success or self.failure)

    def hold_action(self):
        return self.data.ctrl.copy()

    def cameras(self):
        return ["overview", "closeup", "rings", "pages"]

    def step(self, action):
        values = np.asarray(action, dtype=np.float64)
        if values.shape != (self.action_dim,) or not np.isfinite(values).all():
            raise ValueError(f"Expected {self.action_dim} finite actuator targets")
        lo, hi = self.model.actuator_ctrlrange.T
        if np.any(values < lo - 1e-6) or np.any(values > hi + 1e-6):
            raise ValueError("Actuator targets exceed native joint bounds")
        if self.done:
            return self.status()
        m, d = self.model, self.data
        d.ctrl[:] = np.clip(values, lo, hi)
        for substep in range(self.substeps):
            mujoco.mj_step(m, d)
            if any(d.warning[w].number for w in (mujoco.mjtWarning.mjWARN_BADQPOS, mujoco.mjtWarning.mjWARN_BADQVEL,
                                                   mujoco.mjtWarning.mjWARN_BADQACC)):
                self.failure = "unstable_physics"
                self.failure_detail = {"control": self.steps, "substep": substep}
                break
            broken = self.checker.failure(d, self.reset_binder)
            if broken:
                # Fail fast: the episode ends at the physics substep that broke an invariant.
                self.failure = broken[0]
                self.failure_detail = {"object": broken[1], "control": self.steps, "substep": substep}
                break
        self.steps += 1
        mujoco.mj_forward(m, d)
        if self.failure:
            return self.status()
        f = self.checker.features(d, self.reset_binder)
        if self.stage == 0 and f["rings_open"]:
            self._advance()
        if self.stage == 1 and self.checker.placed(f):
            self._advance()
        if self.stage == 2 and self.checker.closed_and_linked(f):
            self._advance()
        if self.stage == 3:
            if self.checker.terminal(f) and self.hold and self.checker.still(self.hold_ref, d):
                self.hold += 1
            elif self.checker.terminal(f):
                self.hold, self.hold_ref = 1, self.checker.page_poses(d)
            else:
                self.hold, self.hold_ref = 0, None
            if self.hold >= self.checker.hold_steps:
                self._advance()
                self.success = True
        if not self.done and self.steps >= self.max_control_steps:
            self.failure = "episode_budget"
            self.failure_detail = {"control": self.steps}
        self._last = f
        return self.status(f)

    def _advance(self):
        self.stage += 1
        self.stage_steps.append(self.steps)

    def features(self):
        return self.checker.features(self.data, self.reset_binder)

    def status(self, f=None):
        f = self.features() if f is None else f
        return {
            **f,
            "success": self.success,
            "done": self.done,
            "steps": self.steps,
            "stage": self.stage,
            "stage_name": STAGE_NAMES[self.stage - 1] if self.stage else "",
            "stage_steps": list(self.stage_steps),
            "total_stages": self.total_stages,
            "hold_steps": self.hold,
            "reason": "success" if self.success else (self.failure or ""),
            "failed": bool(self.failure),
            "failure": self.failure,
            "failure_detail": self.failure_detail,
            "hand": self.hand,
        }

    # ------------------------------------------------------------------ tooling
    def snapshot(self):
        state = np.empty(mujoco.mj_stateSize(self.model, mujoco.mjtState.mjSTATE_INTEGRATION))
        mujoco.mj_getState(self.model, self.data, state, mujoco.mjtState.mjSTATE_INTEGRATION)
        return {
            "state": state,
            "ctrl": self.data.ctrl.copy(),
            "episode": (self.steps, self.stage, self.hold, self.success, self.failure, self.failure_detail,
                        list(self.stage_steps), self.hold_ref),
        }

    def restore(self, snap):
        mujoco.mj_setState(self.model, self.data, snap["state"], mujoco.mjtState.mjSTATE_INTEGRATION)
        self.data.ctrl[:] = snap["ctrl"]
        mujoco.mj_forward(self.model, self.data)
        (self.steps, self.stage, self.hold, self.success, self.failure, self.failure_detail,
         stage_steps, self.hold_ref) = snap["episode"]
        self.stage_steps = list(stage_steps)

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
        state = np.empty(mujoco.mj_stateSize(self.model, mujoco.mjtState.mjSTATE_INTEGRATION))
        mujoco.mj_getState(self.model, self.data, state, mujoco.mjtState.mjSTATE_INTEGRATION)
        digest = hashlib.sha256(state.astype("<f8").tobytes())
        digest.update(json.dumps([self.steps, self.stage, self.hold, self.success, self.failure]).encode())
        # Physics and predicate parameters only (never the instruction prose), so text edits keep evidence hashes.
        digest.update(json.dumps({k: v for k, v in self.config.items() if k not in PROSE_KEYS}, sort_keys=True).encode())
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
