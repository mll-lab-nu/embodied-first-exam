"""A numpy stand-in for rcb_robodojo.Session (test_server.py): actions jump to their targets, cameras render grey images
and, like the real Session.observe(), an observation is cached per (resets, actions); FAKE_INSTANCE=mismatch rebuilds the
layout to another state hash."""
import hashlib, json, os
import numpy as np
ARMS = ("left", "right"); CAMERAS = ("cam_head", "cam_left_wrist", "cam_right_wrist")
ARM_SLICE = {"left": slice(0, 6), "right": slice(7, 13)}; GRIP_INDEX = {"left": 6, "right": 13}
class Session:
    def __init__(self, task, instance=None, strict=False, depth=False):
        self.inst = json.load(open(instance)) if isinstance(instance, str) else (instance or {})
        self.task = task; self.n_steps = 0; self._resets = 0; self._targets = np.zeros(14); self._rec = None; self.step_lim = 15000
        self._obs_key = None; self.renders = 0
        self.instance_sha = "aa" if os.environ.get("FAKE_INSTANCE", "exact") == "exact" else "bb"
        self.instance_exact = self.instance_sha == self.inst.get("state_sha", "aa")
    def observe(self):
        key = (self._resets, self.n_steps)
        if self._obs_key != key: self._obs_key = key; self.renders += 1
        return {}
    def render_frame(self, c="cam_head"):
        self.observe()
        return np.full((24, 32, 3), self.n_steps % 255, np.uint8)
    def render_depth(self, c="cam_head"): self.observe(); return np.ones((24, 32), np.float32)
    def camera_info(self, cams=None):
        return {c: {"intrinsic_cv": np.eye(3).tolist(), "extrinsic_cv": np.eye(4)[:3].tolist(), "cam2world_gl": np.eye(4).tolist(),
                    "image_size": [32, 24], "mount": {"type": "static"}} for c in (cams or CAMERAS)}
    def robot_spec(self): return {"arms": {a: {"joints": {f"{a}_joint{i}": [-3.0, 3.0] for i in range(1, 7)}} for a in ARMS}, "controller": {}}
    def instruction(self): return "do the task"
    def kinematics_check(self): return {"ok": True}
    def kinematics(self, req): return {"ok": True}
    def proprio(self):
        return {"joint_pos": [0.0] * 14, "tcp_pose": [0.0] * 14, "gripper_cmd": [0.0] * 2, "joint_vel": [0.0] * 14,
                "gripper_opening": [0.0] * 2, "joint_effort": [0.0] * 12}
    def hold_action(self): return self._targets.copy()
    def step(self, a):
        a = np.asarray(a, dtype=np.float32).reshape(-1); assert a.size == 14
        if self._rec is not None: self._rec.append(a.copy())
        self._targets = a.astype(np.float64); self.n_steps += 1; return False
    @property
    def done(self): return False
    def success(self): return False
    def end_reason(self): return None
    def state_sha(self): return hashlib.sha1(self._targets.tobytes() + str(self.n_steps).encode()).hexdigest()[:16]
    def record_start(self): self._rec = []
    def record_stop(self): r = np.stack(self._rec) if self._rec else np.zeros((0, 14), np.float32); self._rec = None; return r
    def save_trajectory(self, acts, path, meta=None): np.savez(path, actions=acts, task=self.task, meta=json.dumps(meta or {}))
    def fk(self, q): return {f"{a}_link6": [0.3, 0.0, 0.5, 1, 0, 0, 0] for a in ARMS}
    def ik(self, targets, seed=None): return {"q": np.zeros(12), "error": {a: {"pos_m": 0.0, "rot_rad": 0.0} for a in ARMS}}
