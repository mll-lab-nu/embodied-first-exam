"""Actuator-only pancake serving dynamics with a strict, state-derived verdict."""

from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path

os.environ.setdefault("MUJOCO_GL", "egl")

import mujoco
import numpy as np

from checker import STAGES, Checker
from scene import build, hands

CONFIG_PATH = Path(__file__).with_name("task.json")
TASK = "pancake_serve"


class Session:
    """One frozen pancake-serving episode. ``hand`` is ``sharpa`` (default) or ``wuji``; when omitted, the
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
        self.initial_qpos = np.asarray(self.config["initial_qpos"][self.hand], dtype=float)
        if self.initial_qpos.shape != (self.model.nq,):
            raise ValueError(f"initial_qpos[{self.hand}] must have {self.model.nq} values")
        self.control_dt = float(self.config["control_dt"])
        self.substeps = round(self.control_dt / self.config["physics_dt"])
        self.max_control_steps = int(self.config["max_steps"])
        self.qadr = self.model.jnt_qposadr[self.model.actuator_trnid[:, 0]]
        self.joint_names = [self.model.joint(int(j)).name for j in self.model.actuator_trnid[:, 0]]
        self.actuator_names = [self.model.actuator(i).name for i in range(self.model.nu)]
        self.marvin = self.config.get("rig") == "marvin"
        self.robot = "marvin-bimanual-sharpa-wave" if self.marvin else self.hand_info["robot"] + "-floating"
        self.tcp_body = "wrist_stage"
        self.checker = Checker(self.model, self.config)
        self.renderer = None
        self.reset()

    # ------------------------------------------------------------------------------------------- episode
    def reset(self):
        """Exact frozen reset: the settled pre-held turner grasp, pancake in the pan, empty plate."""
        mujoco.mj_resetData(self.model, self.data)
        self.data.qpos[:] = self.initial_qpos
        self.data.ctrl[:] = self.initial_targets
        mujoco.mj_forward(self.model, self.data)
        self.steps = 0
        self.actions = []
        self.checker.reset(self.data)
        self.last = self.checker.features(self.model, self.data)
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
        return [c["name"] for c in self.config["cameras"]]

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
            if self.checker.substep(self.data, self.steps, substep):
                break  # fail fast at the physics substep that broke an invariant
        self.steps += 1
        mujoco.mj_forward(self.model, self.data)
        self.last = self.checker.control(self.model, self.data, self.steps)
        if self.steps >= self.max_control_steps and not self.done:
            self.checker.failure = "episode_budget"
            self.checker.failure_detail = {"control": self.steps}
        return self.features()

    def features(self):
        c = self.checker
        return {
            **self.last,
            "stage": int(c.stage),
            "stage_name": STAGES[c.stage - 1] if c.stage else "",
            "on_blade_run": int(c.on_blade_run),
            "hold_controls": int(c.hold),
            "success": bool(c.success),
            "success_step": c.success_step,
            "failure": c.failure,
            "failure_detail": c.failure_detail,
            "steps": int(self.steps),
        }

    def status(self):
        f = self.features()
        return {
            **f,
            "done": self.done,
            "stage": int(self.checker.stage),
            "total_stages": len(STAGES),
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

    # ------------------------------------------------------------------------------------------- tooling
    def snapshot(self):
        """Full simulator + checker state (authoring/search tooling; never used by graders)."""
        size = mujoco.mj_stateSize(self.model, mujoco.mjtState.mjSTATE_INTEGRATION)
        state = np.empty(size)
        mujoco.mj_getState(self.model, self.data, state, mujoco.mjtState.mjSTATE_INTEGRATION)
        c = self.checker
        return {
            "physics": state, "ctrl": self.data.ctrl.copy(), "warmstart": self.data.qacc_warmstart.copy(),
            "steps": self.steps, "n_actions": len(self.actions),
            "checker": (c.stage, c.on_blade_run, c.hold, c.failure, c.failure_detail, c.success, c.success_step),
            "last": dict(self.last),
        }

    def restore(self, snap):
        mujoco.mj_setState(self.model, self.data, snap["physics"], mujoco.mjtState.mjSTATE_INTEGRATION)
        self.data.ctrl[:] = snap["ctrl"]
        self.data.qacc_warmstart[:] = snap["warmstart"]
        mujoco.mj_forward(self.model, self.data)
        self.steps = snap["steps"]
        del self.actions[snap["n_actions"]:]
        c = self.checker
        (c.stage, c.on_blade_run, c.hold, c.failure, c.failure_detail, c.success, c.success_step) = snap["checker"]
        self.last = dict(snap["last"])

    def save_trajectory(self, actions, path):
        """Write the privileged deliverable: ``actions`` plus this session's ``hand`` and ``task``."""
        hands.write_trajectory(path, actions, hand=self.hand, task=self.task)

    def state_sha(self):
        state = np.empty(mujoco.mj_stateSize(self.model, mujoco.mjtState.mjSTATE_INTEGRATION))
        mujoco.mj_getState(self.model, self.data, state, mujoco.mjtState.mjSTATE_INTEGRATION)
        digest = hashlib.sha256(state.astype("<f8").tobytes())
        digest.update(self.checker.predicate_state().astype("<i8").tobytes())
        digest.update(str(self.checker.failure).encode())
        # Physics/verdict parameters and this hand's frozen reset only; editing texts never changes the hash.
        params = {key: self.config[key] for key in Checker.HASHED_KEYS if key in self.config}
        params["initial_qpos"] = self.config["initial_qpos"][self.hand]
        params["initial_targets"] = self.config["initial_targets"][self.hand]
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
