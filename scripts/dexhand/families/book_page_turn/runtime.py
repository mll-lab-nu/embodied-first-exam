"""Actuator-only board-book page turn with a strict, state-derived verdict."""

from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path

os.environ.setdefault("MUJOCO_GL", "egl")

import mujoco
import numpy as np

from checker import STAGES, PageTurnChecker
from scene import arm_rig, build, hands

CONFIG_PATH = Path(__file__).with_name("task.json")
TASK = "book_page_turn"
# task.json keys that change the physics or the verdict; only these enter state_sha (texts and cameras do not).
HASHED_KEYS = (
    "physics_dt", "control_dt", "max_steps", "settle_substeps", "table_z", "table", "book_xy", "book", "target_leaf",
    "stage_angles_deg", "other_leaf_tolerance_deg", "second_leaf_turn_deg", "book_max_displacement_m",
    "book_max_rotation_deg", "below_table_margin_m", "laid_max_speed_rad_s", "hold_steps", "initial_targets",
    "book_yaw_deg", "floor_z", "desk_legs_x", "marvin",
)


class Session:
    """One frozen page-turn episode. ``hand`` is ``sharpa`` (default) or ``wuji``; when omitted, the
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
        self.control_dt = self.config["control_dt"]
        self.substeps = round(self.control_dt / self.config["physics_dt"])
        self.settle_substeps = int(self.config["settle_substeps"])
        self.max_control_steps = int(self.config["max_steps"])
        self.qadr = self.model.jnt_qposadr[self.model.actuator_trnid[:, 0]]
        self.joint_names = [self.model.joint(int(j)).name for j in self.model.actuator_trnid[:, 0]]
        self.actuator_names = [self.model.actuator(i).name for i in range(self.model.nu)]
        self.robot = arm_rig.ROBOT_ID
        self.tcp_body = "wrist_stage"  # right-hand mount on the Marvin right flange
        self.checker = PageTurnChecker(self.model, self.config)
        self.lo, self.hi = self.model.actuator_ctrlrange.T.copy()
        self.renderer = None
        self.reset()

    # ------------------------------------------------------------------ episode
    def reset(self):
        """Frozen deterministic reset: hand at its declared targets, then a fixed passive settle of the book."""
        mujoco.mj_resetData(self.model, self.data)
        self.data.qpos[self.qadr] = self.initial_targets
        self.data.ctrl[:] = self.initial_targets
        mujoco.mj_forward(self.model, self.data)
        for _ in range(self.settle_substeps):
            mujoco.mj_step(self.model, self.data)
        mujoco.mj_forward(self.model, self.data)
        self.checker.reference(self.data)
        self.steps = 0
        self.actions = []
        self.last = self.checker.features(self.data)
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

    def step(self, action):
        values = np.asarray(action, dtype=np.float64)
        if values.shape != (self.action_dim,) or not np.isfinite(values).all():
            raise ValueError(f"Expected {self.action_dim} finite actuator targets")
        if np.any(values < self.lo - 1e-6) or np.any(values > self.hi + 1e-6):
            raise ValueError("Actuator targets exceed native joint bounds")
        if self.done:
            # The episode ended at the first success or failure; later rows are not executed.
            return self.features()
        self.data.ctrl[:] = np.clip(values, self.lo, self.hi)
        self.actions.append(self.data.ctrl.copy())
        checker = self.checker
        for substep in range(self.substeps):
            mujoco.mj_step(self.model, self.data)
            violation = checker.invariant(self.data)
            if violation:
                # Fail fast: the episode ends at the physics substep that broke an invariant.
                checker.failure, detail = violation
                checker.failure_detail = {"detail": detail, "control": self.steps, "substep": substep}
                break
        self.steps += 1
        mujoco.mj_forward(self.model, self.data)
        self.last = checker.update(self.data)
        if self.steps >= self.max_control_steps and not self.done:
            checker.failure = "episode_budget"
            checker.failure_detail = {"control": self.steps}
        return self.features()

    def features(self):
        f = dict(self.checker.features(self.data))
        f.update(
            stage=self.checker.stage,
            stage_name=(("none",) + STAGES)[self.checker.stage],
            max_target_angle_deg=float(np.degrees(self.checker.max_target_angle)),
            hold_steps=self.checker.hold,
            success=self.checker.success,
            failure=self.checker.failure,
            failure_detail=self.checker.failure_detail,
            steps=self.steps,
        )
        return f

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

    # ------------------------------------------------------------------ snapshots (authoring / search tooling)
    def snapshot(self):
        size = mujoco.mj_stateSize(self.model, mujoco.mjtState.mjSTATE_INTEGRATION)
        state = np.empty(size)
        mujoco.mj_getState(self.model, self.data, state, mujoco.mjtState.mjSTATE_INTEGRATION)
        c = self.checker
        return {
            "state": state,
            "steps": self.steps,
            "n_actions": len(self.actions),
            "checker": (c.stage, c.hold, c.success, c.failure, c.failure_detail, c.max_target_angle),
        }

    def restore(self, snap):
        mujoco.mj_setState(self.model, self.data, snap["state"], mujoco.mjtState.mjSTATE_INTEGRATION)
        mujoco.mj_forward(self.model, self.data)
        self.steps = snap["steps"]
        del self.actions[snap["n_actions"]:]
        c = self.checker
        c.stage, c.hold, c.success, c.failure, c.failure_detail, c.max_target_angle = snap["checker"]
        self.last = c.features(self.data)

    # ------------------------------------------------------------------ deliverables
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
        c = self.checker
        digest.update(json.dumps([c.stage, c.hold, c.success, c.failure, self.steps]).encode())
        digest.update(json.dumps({k: self.config[k] for k in HASHED_KEYS}, sort_keys=True).encode())
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
