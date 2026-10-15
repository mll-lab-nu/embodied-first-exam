"""Actuator-only remote battery swap episode (Session contract of the DexHand family plugin)."""

from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path

os.environ.setdefault("MUJOCO_GL", "egl")

import mujoco
import numpy as np

from checker import STAGES, Checker
import scene as scene_module
from scene import build, hands

CONFIG_PATH = Path(__file__).with_name("task.json")
# Full physics plus the solver warm start, so a restored snapshot continues bit for bit like the original run.
SNAPSHOT_STATE = mujoco.mjtState.mjSTATE_FULLPHYSICS | mujoco.mjtState.mjSTATE_WARMSTART
TASK = "remote_battery_swap"
PROSE_KEYS = frozenset({"title", "description", "instruction", "modeling", "category", "difficulty", "mechanism",
                        "cameras"})


class Session:
    """One frozen remote-battery-swap episode. ``hand`` is ``sharpa`` (default) or ``wuji``; when omitted, the
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
        self.max_control_steps = int(self.config["max_steps"])
        self.tcp_body = "wrist_stage"
        self.qadr = self.model.jnt_qposadr[self.model.actuator_trnid[:, 0]]
        self.dofs = self.model.jnt_dofadr[self.model.actuator_trnid[:, 0]]
        self.joint_names = [self.model.joint(int(j)).name for j in self.model.actuator_trnid[:, 0]]
        self.actuator_names = [self.model.actuator(i).name for i in range(self.model.nu)]
        self.checker = Checker(self.model, self.config)
        self.owner = self.checker.owner
        self.renderer = None
        self.reset()

    # ------------------------------------------------------------------------------------------------ episode
    def reset(self):
        mujoco.mj_resetData(self.model, self.data)
        self.data.qpos[self.qadr] = self.initial_targets
        self.data.ctrl[:] = self.initial_targets
        mujoco.mj_forward(self.model, self.data)
        self.steps = 0
        self.actions = []
        self.checker.reset(self.data)
        self.last = self.checker.control(self.data, 0)
        self.checker.hold = 0
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
        return bool(self.success or self.failure)

    def hold_action(self):
        return self.data.ctrl.copy()

    def cameras(self):
        return list(self.config["cameras"])

    def features(self):
        f = dict(self.last)
        f.update(success=self.success, failure=self.failure, failure_detail=self.failure_detail, steps=self.steps)
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

    def step(self, action):
        values = np.asarray(action, dtype=np.float64)
        if values.shape != (self.action_dim,) or not np.isfinite(values).all():
            raise ValueError(f"Expected {self.action_dim} finite actuator targets")
        lo, hi = self.model.actuator_ctrlrange.T
        if np.any(values < lo - 1e-6) or np.any(values > hi + 1e-6):  # float32 rounding of a bound is accepted
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
                for w in (mujoco.mjtWarning.mjWARN_BADQPOS, mujoco.mjtWarning.mjWARN_BADQVEL,
                          mujoco.mjtWarning.mjWARN_BADQACC)
            ):
                self.checker.failure = "unstable_physics"
                self.checker.failure_detail = {"control": self.steps, "substep": substep}
                break
            violation = self.checker.substep(self.data, self.steps, substep)
            if violation:
                # Fail fast: the episode ends at the physics substep that broke an invariant.
                self.checker.failure, detail = violation
                self.checker.failure_detail = {**detail, "control": self.steps, "substep": substep}
                break
        self.steps += 1
        mujoco.mj_forward(self.model, self.data)
        if not self.checker.failure:
            self.last = self.checker.control(self.data, self.steps)
        if self.steps >= self.max_control_steps and not self.success and not self.failure:
            self.checker.failure = "episode_budget"
            self.checker.failure_detail = {"control": self.steps}
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

    # ------------------------------------------------------------------------------------------------ state
    def predicate_state(self):
        c = self.checker
        return {
            "steps": self.steps,
            "latched": c.latched,
            "latch_step": c.latch_step,
            "hold": c.hold,
            "success": c.success,
            "failure": c.failure,
            "new_cell_lifted": c.new_cell_lifted,
            "new_cell_clear_count": c.new_cell_clear_count,
        }

    def state_sha(self):
        state = np.empty(mujoco.mj_stateSize(self.model, mujoco.mjtState.mjSTATE_INTEGRATION))
        mujoco.mj_getState(self.model, self.data, state, mujoco.mjtState.mjSTATE_INTEGRATION)
        digest = hashlib.sha256(state.astype("<f8").tobytes())
        digest.update(json.dumps(self.predicate_state(), sort_keys=True).encode())
        # physics and predicate parameters only: editing prose (title, description, instruction, notes) or the
        # preview cameras never changes an evidence hash
        digest.update(json.dumps({k: v for k, v in self.config.items() if k not in PROSE_KEYS}, sort_keys=True).encode())
        digest.update(self.hand.encode())
        return digest.hexdigest()

    def snapshot(self):
        """Full simulator + predicate state (authoring/search tooling; graders never use it)."""
        state = np.empty(mujoco.mj_stateSize(self.model, SNAPSHOT_STATE))
        mujoco.mj_getState(self.model, self.data, state, SNAPSHOT_STATE)
        c = self.checker
        return {
            "physics": state,
            "ctrl": self.data.ctrl.copy(),
            "steps": self.steps,
            "n_actions": len(self.actions),
            "checker": {k: (list(v) if isinstance(v, list) else v) for k, v in vars(c).items()
                        if k in ("latched", "latch_step", "hold", "success", "failure", "failure_detail",
                                 "new_cell_lifted", "new_cell_clear_count")},
            "last": self.last,
        }

    def restore(self, snap):
        mujoco.mj_setState(self.model, self.data, snap["physics"], SNAPSHOT_STATE)
        self.data.ctrl[:] = snap["ctrl"]
        mujoco.mj_forward(self.model, self.data)
        self.steps = snap["steps"]
        del self.actions[snap["n_actions"]:]
        for k, v in snap["checker"].items():
            setattr(self.checker, k, list(v) if isinstance(v, list) else v)
        self.last = snap["last"]

    # ------------------------------------------------------------------------------------------------ render
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
