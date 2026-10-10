"""A stand-in for the MolmoSpaces tooling (no MuJoCo): what environment/sim/server.py needs of Episode, on numpy."""
import hashlib, types
import numpy as np
def load_instance(path):
    return {"family": "pick", "instance": "i00", "t0": {"action_dim": 8}, "facts": {"goal": "pick it", "horizon_s": 2.0},
            "episode": {"robot": {"robot_name": "franka"}}}
class Episode:
    def __init__(self, inst):
        self.inst = inst; self.dt = 0.066; self.horizon = 30; self.action_dim = 8; self._n = 0; self.q = np.zeros(8)
        self.env = types.SimpleNamespace(current_model=types.SimpleNamespace(opt=types.SimpleNamespace(timestep=0.002)))
        self.agent_cameras = ["wrist", "exo"]; self.joint_names = [f"j{i}" for i in range(7)]; self.grippers = ["gripper"]
        self.layout = self.joint_names + ["gripper"]
    def camera_info(self, c):
        return {"mount": {"type": "static"}, "image_size": [16, 16], "intrinsic_cv": [[16, 0, 8], [0, 16, 8], [0, 0, 1]],
                "extrinsic_cv": np.eye(4)[:3].tolist(), "cam2world_gl": np.eye(4).tolist()}
    def command_limits(self): return np.array([[-3.0, 3.0]] * 7 + [[0.0, 255.0]])
    def robot_spec(self): return {"name": "stub"}
    def kinematics_spec(self):
        return {"endpoint": "/kinematics", "joint_names": self.joint_names, "frame": "world", "quaternion_order": "wxyz", "links": ["gripper"],
                "tcp_frames": ["gripper"], "ee_frames": ["gripper"], "ik_targets": ["gripper"]}
    def kinematics(self, req): return {"ok": True}
    @property
    def steps(self): return self._n
    @property
    def done(self): return self._n >= self.horizon
    def proprio(self):
        return {"joint_pos": self.q[:7], "joint_vel": np.zeros(7), "joint_effort": np.zeros(7), "gripper_opening": np.array([0.08]),
                "tcp_pose": np.array([0, 0, 0, 1, 0, 0, 0.0])}
    def render(self, c): return np.full((16, 16, 3), self._n % 255, np.uint8)
    def render_depth(self, c): return np.ones((16, 16), np.float32)
    def hold_row(self): return self.q.copy()
    def step(self, row):
        if self.done: return False
        self.q = np.asarray(row, float).copy(); self._n += 1; return True
    def success(self): return False
    def state_sha(self): return hashlib.sha1(self.q.tobytes() + bytes([self._n % 255])).hexdigest()[:16]
