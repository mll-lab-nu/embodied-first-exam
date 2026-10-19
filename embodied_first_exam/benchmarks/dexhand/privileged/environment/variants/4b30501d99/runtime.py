"""Actuator-only USB plug insertion episode (genuine hand on the Tianji Marvin right arm) with a strict,
state-derived verdict (FAMILY_PLUGIN.md section 4)."""

from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path

os.environ.setdefault("MUJOCO_GL", "egl")

import mujoco
import numpy as np

from checker import Checker
from scene import USB, arm_rig, build, hands

CONFIG_PATH = Path(__file__).with_name("task.json")
TASK = "usb_plug_insert"


class Session:
    """One frozen USB plug insertion episode. ``hand`` is ``sharpa`` (default) or ``wuji``; when omitted, the
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
        self.tcp_body = "wrist_stage"  # the right flange's hand mount (same body name for both hands)
        self.layout = arm_rig.layout(self.model)
        self.checker = Checker(self.model, self.config, USB)
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
        self.last = self.checker.features(self.data)
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
        return bool(self.success or self.failure)

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
        ck = self.checker
        for substep in range(self.substeps):
            mujoco.mj_step(self.model, self.data)
            if any(
                self.data.warning[w].number
                for w in (mujoco.mjtWarning.mjWARN_BADQPOS, mujoco.mjtWarning.mjWARN_BADQVEL,
                          mujoco.mjtWarning.mjWARN_BADQACC)
            ) or not np.isfinite(self.data.qpos).all():
                ck.failure, ck.failure_detail = "unstable_physics", {"control": self.steps, "substep": substep}
                break
            violation = ck.substep_violation(self.data)
            if violation:
                # Fail fast: the episode ends at the physics substep that broke an invariant.
                ck.failure = violation[0]
                ck.failure_detail = {**violation[1], "control": self.steps, "substep": substep}
                break
        self.steps += 1
        mujoco.mj_forward(self.model, self.data)
        if not ck.failure:
            self.last = ck.update(self.data, self.steps)
        else:
            self.last = ck.features(self.data)
        if self.steps >= self.max_control_steps and not self.done:
            ck.failure, ck.failure_detail = "episode_budget", {"control": self.steps}
        return self.features()

    def features(self):
        f = dict(self.last)
        for key in ("tip_depth_m", "tip_lateral_m", "tip_vertical_m", "plug_pos", "hub_pos"):
            f[key] = np.asarray(f[key]).round(6).tolist()
        f.update(success=self.success, failure=self.failure, failure_detail=self.failure_detail, steps=self.steps)
        return f

    def status(self):
        f = self.features()
        seated = f["seated_port"]
        reason = "success" if self.success else (self.failure or "")
        if not reason and seated is not None and seated != self.config["target_port"]:
            reason = "wrong_port"
        return {
            **f,
            "done": self.done,
            "stage": f["stage"],
            "total_stages": 3,
            "reason": reason,
            "failed": bool(self.failure),
            "hand": self.hand,
        }

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

    # ------------------------------------------------------------------ snapshots (authoring and search)
    def snapshot(self):
        state = np.empty(mujoco.mj_stateSize(self.model, mujoco.mjtState.mjSTATE_INTEGRATION))
        mujoco.mj_getState(self.model, self.data, state, mujoco.mjtState.mjSTATE_INTEGRATION)
        ck = self.checker
        return {
            "state": state,
            "steps": self.steps,
            "actions": len(self.actions),
            "last": dict(self.last),
            "checker": {k: getattr(ck, k) for k in ("stage", "hold", "no_hand", "success", "failure",
                                                    "failure_detail", "lift_step", "seat_step")},
        }

    def restore(self, snap):
        mujoco.mj_setState(self.model, self.data, snap["state"], mujoco.mjtState.mjSTATE_INTEGRATION)
        mujoco.mj_forward(self.model, self.data)
        self.steps = snap["steps"]
        del self.actions[snap["actions"]:]
        self.last = dict(snap["last"])
        for k, v in snap["checker"].items():
            setattr(self.checker, k, v)

    def state_sha(self):
        state = np.empty(mujoco.mj_stateSize(self.model, mujoco.mjtState.mjSTATE_INTEGRATION))
        mujoco.mj_getState(self.model, self.data, state, mujoco.mjtState.mjSTATE_INTEGRATION)
        digest = hashlib.sha256(state.astype("<f8").tobytes())
        ck = self.checker
        digest.update(json.dumps([ck.stage, ck.hold, ck.no_hand, ck.success, ck.failure, self.steps]).encode())
        # Physics and predicate parameters only (never instruction prose, titles or camera placement).
        prose = {"title", "description", "instruction", "modeling", "category", "difficulty", "mechanism", "robot",
                 "cameras", "schema_version", "release_status"}
        digest.update(json.dumps({k: v for k, v in self.config.items() if k not in prose}, sort_keys=True).encode())
        digest.update(self.hand.encode())
        return digest.hexdigest()

    # ------------------------------------------------------------------ rendering (evidence only)
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
