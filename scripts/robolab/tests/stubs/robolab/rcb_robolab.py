import numpy as np
from fake_common import Base, MAX_STEPS  # noqa: F401
SETTLE_STEPS = 30                                            # the real tooling's end-of-episode hold
class _T:                                                    # the two torch calls the server makes on the joint limits
    def __init__(self, a): self.a = np.asarray(a)
    def __getitem__(self, k): return _T(self.a[k])
    def detach(self): return self
    def cpu(self): return self
    def numpy(self): return self.a
class _Robot:
    class data:
        soft_joint_pos_limits = _T(np.stack([np.full((9, 2), [-3.0, 3.0])]))
class _Env:
    def get_env_results(self): return [{"success": False}]
class Session(Base):
    DIM = 8
    def __init__(self, task, instance=None, strict=False, depth=False):
        self._init(); self.robot = _Robot(); self.arm_ids = list(range(7)); self.env = _Env(); self._ee = np.array([0.4, 0.0, 0.5])
        self._obs = {"cams": ("egocentric_mirrored_camera", "over_shoulder_left_camera", "wrist_cam")}
    def ee_pose(self): return self._ee.copy(), np.array([1.0, 0, 0, 0])
    def ik_step(self, wp, q): self._ee = np.asarray(wp, dtype=np.float64); return self._targets[0:7].copy()
    def kinematics_spec(self):
        return {"endpoint": "/kinematics", "joint_names": [f"panda_joint{i}" for i in range(1, 8)], "frame": "base", "quaternion_order": "wxyz",
                "links": ["tcp"], "tcp_frames": ["tcp"], "ee_frames": ["tcp"], "ik_targets": ["tcp"]}
    def proprio(self):
        return {"joint_pos": [0.0] * 8, "tcp_pose": [0.0] * 7, "gripper_cmd": 0.0, "joint_vel": [0.0] * 8, "gripper_opening": 0.0, "joint_effort": [0.0] * 7}
