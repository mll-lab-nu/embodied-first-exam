"""A stand-in for the ManiGuard tooling (no Isaac): what environment/sim/server.py needs of Session, on numpy."""
import hashlib, os, types
import numpy as np
MAX_STEPS = 120
WRIST = "wrist"
class _J:
    def __init__(self, lo, hi): self.lower_limit, self.upper_limit = lo, hi
class _Idx:
    def __init__(self, v): self.v = v
    def tolist(self): return list(self.v)
class Session:
    def __init__(self, task, instance=None, resolution=256, strict=False):
        self.task = task; self.prompt = "do the task"; self.steps = 0; self.done = False; self.reason = None
        self.q = np.zeros(9); self.cmd = np.zeros(8); self.cmd[7] = 1.0; self._rec = None; self.instance_sha = "abc"
        self.frames_taken = 0
        inst = os.environ.get("FAKE_INSTANCE", "exact")        # mismatch: the rebuilt scene is not the frozen instance
        self.instance_exact = inst == "exact"; self.instance_matches = inst != "mismatch"
        names = [f"panda_joint{i}" for i in range(1, 8)] + ["panda_finger_joint1", "panda_finger_joint2"]
        self.robot = types.SimpleNamespace(joints={n: _J(-2.8, 2.8) for n in names}, default_arm="0",
                                           arm_control_idx={"0": _Idx(range(7))}, gripper_control_idx={"0": _Idx([7, 8])})
    def camera_names(self): return ["cam_opposite", "cam_left", "cam_right", "cam_left_shoulder", "wrist"]
    def enable_depth(self, cams): pass
    def camera_info(self, cams=None):
        return {c: {"image_size": [16, 16], "moves": c == "wrist", "intrinsic_cv": [[16, 0, 8], [0, 16, 8], [0, 0, 1]],
                    "mount": {"type": "static"}, "depth_range_m": [0.01, 10.0], "extrinsic_cv": np.eye(4)[:3].tolist(), "cam2world_gl": np.eye(4).tolist()}
                for c in (cams or self.camera_names())}
    def robot_spec(self): return {"name": "stub"}
    def kinematics_spec(self):
        return {"endpoint": "/kinematics", "joint_names": [f"panda_joint{i}" for i in range(1, 8)], "frame": "world", "quaternion_order": "xyzw",
                "links": ["tcp"], "tcp_frames": ["tcp"], "ee_frames": ["tcp"], "ik_targets": ["tcp"]}
    def goal_region(self): return {"radius_m": 0.065}
    def robot_state(self):
        return {"q": self.q, "tcp": np.array([0, 0, 0, 0, 0, 0, 1.0]), "gripper_cmd": self.cmd[7], "qd": np.zeros(9), "gripper_opening": 0.08,
                "eef": np.array([0, 0, 0, 0, 0, 0, 1.0]), "effort": np.zeros(9)}
    def _frames(self, cams, depth=False):
        return {c: np.full((16, 16, 3), self.steps % 255, np.uint8) for c in cams}, ({c: np.ones((16, 16), np.float32) for c in cams} if depth else {})
    def render_grid(self, cameras=None, cols=3):
        self.frames_taken += 1
        return np.concatenate([self._frames([c])[0][c] for c in (cameras or self.camera_names())], axis=1)
    def status(self):
        return {"task_success": False, "ltl_violated": False, "upstream_success": False, "success": False, "counted_violation": False,
                "violation_step": None, "first_contact_step": None, "success_step": None, "upstream_success_step": None, "outcome": "idle",
                "engaged": False, "within_upstream_horizon": None, "constraints": {"r": {"violated": False, "step": None}}}
    def state_sha(self): return hashlib.sha1(self.q.tobytes()).hexdigest()[:16]
    def record_start(self): self._rec = []
    def record_stop(self):
        a = np.asarray(self._rec, np.float32).reshape(-1, 8); self._rec = None; return a
    def save_trajectory(self, acts, path, meta=None): np.savez(path, actions=acts, task=self.task)
    def hold_action(self): return self.cmd.copy()
    def joint_positions(self): return self.q.copy()
    def _ik(self, pos, quat, frame, seed, position_only): return {"ok": True, "q": np.full(7, 0.1), "error": 0.0}
    def kinematics(self, req): return {"ok": True}
    def step(self, a):
        if self.done: raise RuntimeError("the episode is over")
        a = np.asarray(a, np.float32)
        if self._rec is not None: self._rec.append(a.copy())
        self.cmd = a.astype(np.float64); self.q[:7] = a[:7]; self.steps += 1
        if self.steps >= MAX_STEPS: self.done = True; self.reason = "runaway_guard"
        return self.done
