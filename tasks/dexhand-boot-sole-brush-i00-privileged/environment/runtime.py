"""Privileged session of ``boot_sole_brush``: a dexterous hand on the right arm of the Tianji Marvin robot brushes six
clods off the sole of a boot that stands sole-up on a rack peg; the clods must fall into the collection tray.

Only actuator targets act on the simulator (14 arm joint targets + both hands' finger targets, 50 Hz, 10 physics
substeps of 2 ms; the left arm stays parked). The boot, clods and brush are free bodies moved by contact and gravity only. The predicate
(``checker.py``) is evaluated from simulator state after every physics substep (fail-fast) and every control (stages).
"""

from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path

os.environ.setdefault("MUJOCO_GL", "egl")

import mujoco
import numpy as np

from checker import STAGES, BrushChecker
from scene import arm_rig, build, hands, robot_parts

HERE = Path(__file__).resolve().parent
TASK_ID = "boot_sole_brush"
ACTION_DIM = {"sharpa": 58, "wuji": 54}  # 14 Marvin arm targets + left and right hand finger targets
# task.json keys that describe the task in words or place cameras; they never enter the physics or the predicate.
PROSE_KEYS = {"schema_version", "title", "category", "difficulty", "description", "instruction", "mechanism", "modeling",
              "release_status", "cameras"}


def _config(instance=None):
    path = Path(instance) if instance else HERE / "task.json"
    if not path.is_file():
        path = HERE / "instance.json"
    return json.loads(path.read_text())


class Session:
    """One frozen episode. ``hand`` is ``sharpa`` (default) or ``wuji``; when omitted, ``DEXHAND_HAND`` selects it."""

    def __init__(self, task=TASK_ID, hand=None, instance=None, config=None, asset_dir=None):
        if task != TASK_ID:
            raise ValueError(f"Unknown task: {task!r}")
        self.task = task
        self.config = _config(instance) if config is None else config
        self.spec = self.config
        self.hand = hands.selected(hand)
        if self.hand not in ACTION_DIM:
            raise ValueError(f"{TASK_ID} supports only {sorted(ACTION_DIM)}")
        self.hand_info = hands.info(self.hand)
        self.model, self.xml = build(self.config, self.hand, asset_dir)
        self.data = mujoco.MjData(self.model)
        m = self.model
        if m.nu != ACTION_DIM[self.hand]:
            raise ValueError(f"{self.hand} scene has {m.nu} actuators, expected {ACTION_DIM[self.hand]}")
        self._structure_check()
        self.action_dim = int(m.nu)
        self.actuator_names = [m.actuator(i).name for i in range(m.nu)]
        self.joint_names = [m.joint(int(j)).name for j in m.actuator_trnid[:, 0]]
        self.qadr = m.jnt_qposadr[m.actuator_trnid[:, 0]]
        self.lo, self.hi = m.actuator_ctrlrange[:, 0].copy(), m.actuator_ctrlrange[:, 1].copy()
        self.initial_targets = np.asarray(self.config["initial_targets"][self.hand], dtype=float)
        if self.initial_targets.shape != (self.action_dim,):
            raise ValueError(f"initial_targets[{self.hand}] must have {self.action_dim} values")
        self.control_dt = float(self.config["control_dt"])
        self.substeps = int(round(self.control_dt / self.config["physics_dt"]))
        self.max_control_steps = int(self.config["max_steps"])
        self.robot = arm_rig.ROBOT_ID
        self.tcp_body = "wrist_stage"
        self.layout = arm_rig.layout(m)
        self.checker = BrushChecker(m, self.data, self.config)
        self.renderer = None
        self.reset()

    def _structure_check(self):
        """Robot-only actuation; boot, brush and clods are free bodies; no welds, mocap or gravity tricks."""
        m = self.model
        right, rest = robot_parts(m)
        robot = right | rest
        problems = []
        for i in range(m.nu):
            j = int(m.actuator_trnid[i, 0])
            if m.actuator_trntype[i] != mujoco.mjtTrn.mjTRN_JOINT or int(m.jnt_bodyid[j]) not in robot:
                problems.append("non-robot actuator " + m.actuator(i).name)
        for name in ["boot", "brush", *[f"clod_{i}" for i in range(len(self.config["clods"]))]]:
            b = m.body(name).id
            if m.body_jntnum[b] != 1 or m.jnt_type[int(m.body_jntadr[b])] != mujoco.mjtJoint.mjJNT_FREE:
                problems.append(name + " is not a free body")
        if m.neq or m.nmocap or np.any(m.body_gravcomp) or not np.allclose(m.opt.gravity, [0, 0, -9.81]):
            problems.append("equality, mocap, gravity compensation or changed gravity")
        if problems:
            raise ValueError("scene structure check failed: " + "; ".join(problems))

    # ------------------------------------------------------------------ episode
    def reset(self):
        """Frozen reset: initial targets, then ``settle_steps`` physics steps holding them (objects come to rest)."""
        m, d = self.model, self.data
        mujoco.mj_resetData(m, d)
        d.qpos[self.qadr] = self.initial_targets
        d.ctrl[:] = self.initial_targets
        mujoco.mj_forward(m, d)
        for _ in range(int(self.config["settle_steps"])):
            mujoco.mj_step(m, d)
        d.time = 0.0
        mujoco.mj_forward(m, d)
        self.steps = 0
        self.checker.reset()
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
            return self.status()
        m, d, c = self.model, self.data, self.checker
        d.ctrl[:] = np.clip(values, self.lo, self.hi)
        for sub in range(self.substeps):
            mujoco.mj_step(m, d)
            if c.substep(self.steps, sub):
                break
        self.steps += 1
        if not c.failure:
            c.control(self.steps)
            if not c.success and self.steps >= self.max_control_steps:
                c.failure = "episode_budget"
                c.failure_detail = {"control": self.steps}
        return self.status()

    def status(self):
        c = self.checker
        f = c.last or {}
        return {
            "success": bool(c.success),
            "done": self.done,
            "failed": bool(c.failure),
            "steps": int(self.steps),
            "stage": int(c.stage),
            "stage_name": STAGES[c.stage - 1] if c.stage else "",
            "total_stages": len(STAGES),
            "reason": "success" if c.success else (c.failure or ""),
            "failure_detail": c.failure_detail,
            "hold": int(c.hold),
            "clods_in_tray": f.get("clods_in_tray", 0),
            "clods_brushed": int(c.brushed.sum()),
            "brush_contact_controls": int(c.brush_contact_controls),
            "features": f,
            "hand": self.hand,
        }

    def replay(self, actions):
        self.reset()
        for row in np.asarray(actions, dtype=np.float64):
            self.step(row)
            if self.done:
                break
        return self.status()

    def save_trajectory(self, actions, path):
        hands.write_trajectory(path, actions, hand=self.hand, task=self.task)

    # ------------------------------------------------------------------ state
    def snapshot(self):
        m, d = self.model, self.data
        state = np.empty(mujoco.mj_stateSize(m, mujoco.mjtState.mjSTATE_INTEGRATION))
        mujoco.mj_getState(m, d, state, mujoco.mjtState.mjSTATE_INTEGRATION)
        return {"physics": state, "ctrl": d.ctrl.copy(), "steps": self.steps, "checker": self.checker.snapshot()}

    def restore(self, snap):
        m, d = self.model, self.data
        mujoco.mj_setState(m, d, snap["physics"], mujoco.mjtState.mjSTATE_INTEGRATION)
        d.ctrl[:] = snap["ctrl"]
        mujoco.mj_forward(m, d)
        self.steps = snap["steps"]
        self.checker.restore(snap["checker"])

    def state_sha(self):
        m, d = self.model, self.data
        state = np.empty(mujoco.mj_stateSize(m, mujoco.mjtState.mjSTATE_INTEGRATION))
        mujoco.mj_getState(m, d, state, mujoco.mjtState.mjSTATE_INTEGRATION)
        digest = hashlib.sha256(state.astype("<f8").tobytes())
        digest.update(self.checker.vector().astype("<f8").tobytes())
        # Physics and predicate parameters only (L3): editing prose or camera placement never changes evidence hashes.
        physical = {k: v for k, v in self.config.items() if k not in PROSE_KEYS}
        digest.update(json.dumps(physical, sort_keys=True).encode())
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
