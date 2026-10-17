"""Batter-whisk Session: one dexterous hand on a six-axis wrist stage, actuator targets only."""

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
TASK = "batter_whisk"
# task.json entries that define the physics and the predicate (hashed by state_sha; texts and cameras are not).
PHYSICS_KEYS = ("rig", "marvin", "floor_z", "physics_dt", "control_dt", "max_steps", "table_z", "counter", "bowl_pos",
                "bowl_sectors",
                "bowl_wall_proxy_m", "whisk_pos", "wire_proxy_radius_m", "wire_points_per_strand", "head_point_z",
                "stage", "workspace", "predicate", "reset_state")
# Checker attributes that make up the verdict state (saved by snapshot(), restored by restore()).
VERDICT_STATE = ("bowl_xy0", "bowl_z0", "stage", "pickup_steps", "turns", "prev_angle", "free_steps", "placed", "unsupported_steps",
                 "drain_steps", "hold", "success", "failure", "failure_detail", "max_bowl_tilt", "max_bowl_slide", "f")


class Session:
    """One frozen batter-whisk episode. ``hand`` is ``sharpa`` (default) or ``wuji``; when omitted, the
    ``DEXHAND_HAND`` environment variable selects it. Graders pass the hand recorded with the trajectory."""

    def __init__(self, task=TASK, instance=None, asset_dir=None, config=None, hand=None):
        if task != TASK:
            raise ValueError("Unknown task: " + str(task))
        self.config = json.loads(Path(instance or CONFIG_PATH).read_text()) if config is None else config
        self.spec = self.config
        self.task = task
        self.hand = hands.selected(hand)
        self.hand_info = hands.info(self.hand)
        self.marvin = self.config.get("rig") == "marvin"
        self.robot = "marvin-bimanual-sharpa-wave" if self.marvin else self.hand_info["robot"] + "-floating"
        self.model, self.xml = build(self.config, asset_dir, self.hand)
        self.data = mujoco.MjData(self.model)
        self.action_dim = self.model.nu
        reset = self.config["reset_state"][self.hand]
        self.reset_qpos = np.asarray(reset["qpos"], dtype=np.float64)
        self.initial_targets = np.asarray(reset["ctrl"], dtype=np.float64)
        if self.reset_qpos.shape != (self.model.nq,) or self.initial_targets.shape != (self.action_dim,):
            raise ValueError(f"reset_state[{self.hand}] does not match the model")
        self.control_dt = float(self.config["control_dt"])
        self.substeps = round(self.control_dt / self.config["physics_dt"])
        self.joint_names = [self.model.joint(int(j)).name for j in self.model.actuator_trnid[:, 0]]
        self.actuator_names = [self.model.actuator(i).name for i in range(self.model.nu)]
        self.tcp_body = "right_hand_mount" if self.marvin else "wrist_stage"
        self.max_control_steps = int(self.config["max_steps"])
        self.checker = Checker(self.model, self.config)
        self.renderer = None
        self.reset()

    # ------------------------------------------------------------------ episode
    def reset(self):
        mujoco.mj_resetData(self.model, self.data)
        self.data.qpos[:] = self.reset_qpos
        self.data.ctrl[:] = self.initial_targets
        mujoco.mj_forward(self.model, self.data)
        self.steps = 0
        self.actions = []
        self.checker.reset(self.data)
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
        return bool(self.checker.success or self.checker.failure)

    def features(self):
        return {**self.checker.summary(), "steps": self.steps}

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
        unstable = False
        for _ in range(self.substeps):
            mujoco.mj_step(self.model, self.data)
            if any(
                self.data.warning[w].number
                for w in (mujoco.mjtWarning.mjWARN_BADQPOS, mujoco.mjtWarning.mjWARN_BADQVEL,
                          mujoco.mjtWarning.mjWARN_BADQACC)
            ):
                unstable = True
                break
        self.steps += 1
        mujoco.mj_forward(self.model, self.data)
        self.checker.update(self.data, self.steps, unstable=unstable)
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

    # ------------------------------------------------------------------ snapshots (authoring / planning)
    def snapshot(self):
        size = mujoco.mj_stateSize(self.model, mujoco.mjtState.mjSTATE_INTEGRATION)
        state = np.empty(size)
        mujoco.mj_getState(self.model, self.data, state, mujoco.mjtState.mjSTATE_INTEGRATION)
        ck = self.checker
        verdict = {k: (v.copy() if isinstance(v, np.ndarray) else v) for k, v in vars(ck).items() if k in VERDICT_STATE}
        return {"state": state, "steps": self.steps, "n_actions": len(self.actions), "verdict": verdict}

    def restore(self, snap):
        mujoco.mj_setState(self.model, self.data, snap["state"], mujoco.mjtState.mjSTATE_INTEGRATION)
        mujoco.mj_forward(self.model, self.data)
        self.steps = snap["steps"]
        del self.actions[snap["n_actions"]:]
        for k, v in snap["verdict"].items():
            setattr(self.checker, k, v.copy() if isinstance(v, np.ndarray) else v)

    def state_sha(self):
        state = np.empty(mujoco.mj_stateSize(self.model, mujoco.mjtState.mjSTATE_INTEGRATION))
        mujoco.mj_getState(self.model, self.data, state, mujoco.mjtState.mjSTATE_INTEGRATION)
        digest = hashlib.sha256(state.astype("<f8").tobytes())
        ck = self.checker
        verdict = [ck.stage, ck.pickup_steps, ck.turns, ck.drain_steps, ck.hold, ck.free_steps, ck.placed, ck.unsupported_steps,
                   bool(ck.success), ck.failure or "", self.steps]
        digest.update(json.dumps(verdict).encode())
        physics = {k: self.config[k] for k in PHYSICS_KEYS if k in self.config}
        digest.update(json.dumps(physics, sort_keys=True).encode())
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
