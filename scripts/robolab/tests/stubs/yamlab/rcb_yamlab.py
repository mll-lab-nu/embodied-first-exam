import numpy as np
from fake_common import Base, MAX_STEPS  # noqa: F401
ARMS = ("left", "right"); ARM_JOINTS = tuple(f"joint{i}" for i in range(1, 7)); CAMERAS = ("top", "left_wrist", "right_wrist")
FINGER_OPEN, FINGER_CLOSED = -0.0475, 0.0
ARM_SLICE = {"left": slice(0, 6), "right": slice(7, 13)}; GRIP_INDEX = {"left": 6, "right": 13}
def _np(x): return np.asarray(x)
class _Arm:
    class data:
        soft_joint_pos_limits = np.stack([np.full((7, 2), [-3.0, 3.0])])
class Session(Base):
    DIM = 14
    def __init__(self, task, instance=None, strict=False, depth=False):
        self._init(); self.arm = {a: _Arm() for a in ARMS}; self.joint_ids = {a: list(range(7)) for a in ARMS}
        self._ee = {"left": np.array([0.4, 0.3, 0.9]), "right": np.array([0.4, -0.3, 0.9])}
    _frame_mark = None; _n_restores = 0
    def render_frame(self, c, size=None):
        self._frame_mark = ((self._n_restores, self.n_steps), {c}); return np.zeros((24, 32, 3), np.uint8)
    def success(self): return False
    def fallen(self): return None
    def ee_pose(self, a): return self._ee[a].copy(), np.array([1.0, 0, 0, 0])
    def ik_step(self, a, wp, q): self._ee[a] = np.asarray(wp, dtype=np.float64); return self._targets[ARM_SLICE[a]].copy()
    def kinematics_spec(self):
        return {"endpoint": "/kinematics", "joint_names": [f"{a}_{j}" for a in ARMS for j in ARM_JOINTS], "frame": "world", "quaternion_order": "wxyz",
                "links": ["left_tcp", "right_tcp"], "tcp_frames": ["left_tcp", "right_tcp"], "ee_frames": ["left_tcp", "right_tcp"], "ik_targets": ["left_tcp", "right_tcp"]}
    def proprio(self):
        return {"joint_pos": [0.0] * 14, "tcp_pose": [0.0] * 14, "gripper_cmd": [0.0] * 2, "joint_vel": [0.0] * 14, "gripper_opening": [0.0] * 2, "joint_effort": [0.0] * 12}
