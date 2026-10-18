"""A stand-in for the BEHAVIOR tooling (rcb_behavior.py) with no simulator: just enough of Session for the standard
sim service (tasks/behavior-*-standard/environment/sim/server.py) to start and serve, so test_standard_service.py can
drive the real service code, the real shared layer and real HTTP requests. One "control step" adds the action to a
25-number state. Knobs (environment): STUB_GOAL_AT (the success rule's window closes at that control step: the episode
ends there as a success), STUB_FALL_AT (the episode ends there as a fall), STUB_BREAKDOWN_AT (the episode ends there as a
simulator breakdown), STUB_LOG (every executed step is appended there, one line per step), STUB_INSTANCE_MISMATCH=1
(the frozen start does not rebuild: instance_matches False)."""
from __future__ import annotations

import hashlib
import json
import os

import numpy as np

MAX_STEPS = int(os.environ.get("STUB_MAX_STEPS", "200000"))
FALL_TILT_TOLERANCE, FALL_HEIGHT_M, FALL_HOLD_STEPS, FALL_REASON = 0.75, 0.03, 300, "failure: the robot fell over"
REST_STEPS, REST_SPEED_M_S, SETTLE_STEPS = 30, 0.05, 150
BREAKDOWN_REASON = "failure: simulator breakdown"
MP4_FRAGMENTED = "frag_keyframe+empty_moov+default_base_moof"
GL2CV = np.diag([1.0, -1.0, -1.0, 1.0])
CAMS = ("robot_r1:zed_link:Camera:0", "robot_r1:left_realsense_link:Camera:0", "robot_r1:right_realsense_link:Camera:0")


class PrimitiveError(RuntimeError):
    pass


class _T:
    """The little of a torch tensor the service uses."""
    def __init__(self, a): self.a = np.asarray(a, dtype=np.float64)
    def cpu(self): return self.a
    def tolist(self): return self.a.tolist()


class _Idx(list):
    def tolist(self): return list(self)


class _Robot:
    joints = [f"base_footprint_{k}_joint" for k in ("x", "y", "z", "rx", "ry", "rz")] + [f"torso_joint{i}" for i in range(1, 5)] \
        + [f"{a}_arm_joint{i}" for i in range(1, 8) for a in ("left", "right")] + [f"{a}_gripper_finger_joint{i}" for a in ("left", "right") for i in (1, 2)]
    trunk_control_idx = _Idx(range(6, 10))
    arm_control_idx = {"left": _Idx(range(10, 24, 2)), "right": _Idx(range(11, 24, 2))}
    gripper_control_idx = {"left": _Idx((24, 25)), "right": _Idx((26, 27))}
    joint_lower_limits = [-3.0] * 24 + [0.0] * 4
    joint_upper_limits = [3.0] * 24 + [0.05] * 4
    controller_action_idx = {"base": [0, 1, 2], "trunk": [3, 4, 5, 6], "arm_left": list(range(7, 14)), "gripper_left": [14, 15],
                             "arm_right": list(range(16, 23)), "gripper_right": [23, 24]}


class _Task:
    success = False


class _Env:
    episode_steps = 0
    task = _Task()


class Session:
    VIDEO_CAMERAS = CAMS

    def __init__(self, task, instance=None, cameras="tiny", strict=False):
        self.task, self.spec, self.instance_id, self.action_dim = task, {"text": "stub task"}, 301, 25
        self.robot, self.env = _Robot(), _Env()
        self.episode_done, self.end_reason, self.breakdown = False, None, None
        self.state = np.zeros(25); self._last = np.zeros(25); self._rec = None
        self.goal_at = int(os.environ.get("STUB_GOAL_AT", "0")) or None
        self.fall_at = int(os.environ.get("STUB_FALL_AT", "0")) or None
        self.breakdown_at = int(os.environ.get("STUB_BREAKDOWN_AT", "0")) or None
        self.log = os.environ.get("STUB_LOG")
        self.instance_sha = "s0"; self.instance_exact = os.environ.get("STUB_INSTANCE_MISMATCH") != "1"
        self.instance_matches = self.instance_exact

    # ---- what the service builds its /spec from
    def primitives(self): return {}
    def _curobo(self): return None
    def _cam_sensors(self): return {c: c for c in CAMS}
    def _frames(self, cams, depth=False):
        img = {c: np.full((64, 64, 3), 40 + (self.env.episode_steps % 200), np.uint8) for c in cams}
        return img, ({c: np.ones((64, 64), np.float32) for c in cams} if depth else {})
    def enable_depth(self, cams): pass
    def _cam_fixed(self): return {c: {"clip": [0.05, 100.0]} for c in CAMS}
    def _cam_view(self, sensor): return np.eye(4)
    def camera_info(self, cams):
        return {c: {"intrinsic_cv": [[50.0, 0, 32], [0, 50.0, 32], [0, 0, 1]], "image_size": [64, 64], "extrinsic_cv": np.eye(4)[:3].tolist(),
                    "cam2world_gl": np.eye(4).tolist(), "mount": {"type": "link", "link": "head", "link_T_cam_cv": np.eye(4).tolist()}} for c in cams}
    def robot_spec(self): return {"name": "r1pro (stub)"}
    def kinematics_spec(self):
        names = [j for j in _Robot.joints[6:24]]
        return {"endpoint": "/kinematics", "joint_names": names, "frame": "base_link", "quaternion_order": "xyzw",
                "links": ["left_tcp", "right_tcp", "left_eef", "right_eef"], "tcp_frames": ["left_tcp", "right_tcp"],
                "ee_frames": ["left_eef", "right_eef"], "ik_targets": ["left_tcp", "right_tcp"]}
    def kinematics(self, req): return {"ok": True}

    # ---- the episode
    def robot_state(self):
        pose = [0, 0, 0, 0, 0, 0, 1.0]
        return {"q": np.concatenate([np.zeros(6), self.state[3:25]]), "base_pose": pose, "eef": {"left": pose, "right": pose}, "qd": np.zeros(28),
                "gripper_opening": {"left": 0.1, "right": 0.1}, "tcp": {"left": pose, "right": pose}, "effort": np.zeros(28)}
    def hold_action(self):
        a = self._last.copy(); a[:3] = 0.0
        return _T(a)
    def _gripper_cmd(self, arm, open_): return _T([0.07, 0.07] if open_ else [0.0, 0.0])
    def ik(self, targets):
        if os.environ.get("STUB_IK") == "nan":
            return {"trunk": np.full(4, np.nan), "left": np.zeros(7), "right": np.zeros(7)}
        return {"trunk": np.zeros(4), "left": np.full(7, 0.1), "right": np.full(7, -0.1)}
    def step(self, action):
        a = np.asarray(action, dtype=np.float32).reshape(-1)
        if a.size != 25: raise ValueError("action must have 25 entries")
        if self.episode_done:
            raise PrimitiveError(f"episode is over ({self.end_reason or 'success or timeout'}); call reset() before stepping again")
        if not np.all(np.isfinite(a)): raise RuntimeError("the stub simulator was handed a non-finite action")
        if self._rec is not None: self._rec.append(a.copy())
        self._last = a.astype(np.float64); self.state = self.state + self._last; self.env.episode_steps += 1
        if self.log:
            with open(self.log, "a") as f: f.write(json.dumps({"step": self.env.episode_steps}) + "\n")
        n = self.env.episode_steps
        if self.breakdown_at and n >= self.breakdown_at:
            self.breakdown = "robot state not finite"; self.end_reason = f"{BREAKDOWN_REASON} (robot state not finite)"
            self.episode_done = True; return True, False
        if self.goal_at and n >= self.goal_at:
            self.env.task.success = True; self.episode_done = True; return True, False
        if self.fall_at and n >= self.fall_at:
            self.end_reason = FALL_REASON; self.episode_done = True; return True, False
        if n >= MAX_STEPS:
            self.episode_done = True; return False, True
        return False, False
    @property
    def succeeded(self): return bool(self.env.task.success)
    def status(self):
        return {"success": self.succeeded, "q_score": 1.0 if self.succeeded else 0.0, "goal_first_step": self.goal_at if self.succeeded else None}
    def settle(self, steps=SETTLE_STEPS):
        n = 0
        while n < steps and self.env.episode_steps > 0 and not self.episode_done:
            self.step(self.hold_action().a); n += 1
        return n
    def state_sha(self): return hashlib.sha1(np.round(self.state, 6).tobytes()).hexdigest()[:16]
    def record_start(self): self._rec = []
    def record_stop(self):
        acts = np.stack(self._rec) if self._rec else np.zeros((0, 25), np.float32); self._rec = None
        return acts.astype(np.float32)
    def save_trajectory(self, actions, path, meta=None):
        np.savez(path, actions=np.asarray(actions, dtype=np.float32), task=self.task, meta=json.dumps(meta or {}))
