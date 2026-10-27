"""A kinematic stand-in of the robot for sidecar-only runs of the soft tasks (no Isaac Sim).

:class:`KinematicHandScene` implements the scene interface a :class:`tactilelab_tasks.soft.base.SoftTask` needs (``step``,
``robot_obs``, ``render_cameras``, ``get_state`` / ``set_state``, ``link_pose``) with the right hand teleported to every
streamed end-effector target and the fingers following their commanded joint targets.  The gel pad frames are placed
with the kinematics of the X-Trainer GelSight Mini gripper (the finger prismatic joints under ``J1_6`` and the sensor
weld on each finger), so the pinch-frame helpers and the collider boxes see the same geometry as on the real
articulation.  The left arm is static; its forearm link ``J2_3`` can be given a pose for the sleeve task.

Only meant for tests and offline plan checks: nothing here collides, the hand is a perfect tracker.
"""

from __future__ import annotations

from typing import Any, Dict, Optional

import numpy as np

from ..backends.robot import gripper_targets
from ..core import math as m
from ..core.types import GRIPPER_WIDTH_OFFSET, PARKED_LEFT_ARM, Action

__all__ = ["KinematicHandScene", "finger_joint_pose", "gel_pose_in_finger"]

# finger prismatic joints under J1_6 (URDF): origin xyz / rpy and the sliding axis in the joint frame
_FINGER_JOINTS = {
    "J1_7": {"xyz": (-0.0625, -0.024005, 0.11568), "rpy": (1.5708, 0.0, 1.5708), "axis": (0.0, 0.0, -1.0)},
    "J1_8": {"xyz": (0.0625, -0.024005, 0.11568), "rpy": (-1.5708, 0.0, 1.5708), "axis": (0.0, 0.0, 1.0)},
}
# the GelSight Mini gel body in each finger frame: gel +z = contact face normal = finger +z (inner face), case yaw +90 deg
_GEL_IN_FINGER = {
    "gsmini_left": {"pos": (0.0234807, 0.0613874, 0.0172584), "quat": (0.70710678, 0.0, 0.0, 0.70710678)},
    "gsmini_right": {"pos": (0.0234807, -0.0626126, 0.0172584), "quat": (0.70710678, 0.0, 0.0, 0.70710678)},
}


def _quat_from_rpy(rpy) -> np.ndarray:
    """URDF ``rpy`` (fixed-axis roll, pitch, yaw) as a wxyz quaternion."""
    return m.quat_from_euler_xyz_deg(np.degrees(np.asarray(rpy, dtype=np.float64)))


def finger_joint_pose(finger: str, q: float) -> np.ndarray:
    """Pose7 (wxyz) of finger link ``J1_7`` / ``J1_8`` in the ``J1_6`` frame at joint value ``q``."""
    j = _FINGER_JOINTS[finger]
    origin = m.pose_from_pos_quat(j["xyz"], _quat_from_rpy(j["rpy"]))
    slide = m.pose_from_pos_quat(np.asarray(j["axis"], dtype=np.float64) * float(q), (1.0, 0.0, 0.0, 0.0))
    return m.pose_compose(origin, slide)


def gel_pose_in_finger(gel: str) -> np.ndarray:
    g = _GEL_IN_FINGER[gel]
    return m.pose_from_pos_quat(g["pos"], g["quat"])


class KinematicHandScene:
    """See the module docstring.

    Args:
        eef0: initial pose7 (wxyz, env frame) of the right hand frame ``J1_6``.
        link_poses: fixed env-frame poses of other links (e.g. ``{"J2_3": pose7}`` for the sleeve's forearm).
        finger_rate: maximum finger travel per control tick [m] (the drive is rate limited like a real gripper).
    """

    def __init__(
        self, eef0: np.ndarray, link_poses: Optional[Dict[str, np.ndarray]] = None, finger_rate: float = 0.004
    ):
        self.eef0 = np.asarray(eef0, dtype=np.float64).reshape(7).copy()
        self.eef = self.eef0.copy()
        self.left = m.pose_from_pos_quat((-0.3, 0.4, 1.4), (1.0, 0.0, 0.0, 0.0))
        self.fixed = {k: np.asarray(v, dtype=np.float64).reshape(7).copy() for k, v in (link_poses or {}).items()}
        self.finger_rate = float(finger_rate)
        self.q = np.zeros(16)
        self.q[6:12] = PARKED_LEFT_ARM
        self.q[12:16] = [0.010, -0.010, 0.010, -0.010]
        self.q_target = self.q.copy()
        self.tick = 0
        self._gripper_cmd = np.zeros(2, dtype=np.int64)
        self.base_pose = m.pose_from_pos_quat((-0.5, 0.0, 1.1), (1.0, 0.0, 0.0, 0.0))

    # ------------------------------------------------------------------ SceneLike
    def step(self, action: Action) -> None:
        if not isinstance(action, Action):
            action = Action.from_vector(np.asarray(action))
        tgt = action.arm(0)
        if not np.isnan(tgt).any():
            self.eef = np.asarray(tgt, dtype=np.float64).copy()
            self.eef[3:7] = m.quat_normalize(self.eef[3:7])
        self._gripper_cmd = action.gripper.copy()
        for arm, sl in ((0, slice(12, 14)), (1, slice(14, 16))):
            gap = None if action.gripper_gap is None else action.gripper_gap[arm]
            self.q_target[sl] = gripper_targets(int(action.gripper[arm]), gap=gap)
        d = np.clip(self.q_target[12:16] - self.q[12:16], -self.finger_rate, self.finger_rate)
        self.q[12:16] += d
        self.tick += 1

    def robot_obs(self) -> Dict[str, np.ndarray]:
        r, l = self.eef, self.left
        return {
            "joint_pos": self.q.astype(np.float32),
            "joint_vel": np.zeros(16, dtype=np.float32),
            "ee_pos_right": r[:3].astype(np.float32),
            "ee_quat_right": r[3:7].astype(np.float32),
            "ee_pos_left": l[:3].astype(np.float32),
            "ee_quat_left": l[3:7].astype(np.float32),
            "gripper_width_right": np.array([GRIPPER_WIDTH_OFFSET + self.q[12] - self.q[13]], dtype=np.float32),
            "gripper_width_left": np.array([GRIPPER_WIDTH_OFFSET + self.q[14] - self.q[15]], dtype=np.float32),
        }

    def render_cameras(self) -> Dict[str, np.ndarray]:
        return {}

    def ee_pose(self, arm: int) -> np.ndarray:
        return (self.eef if int(arm) == 0 else self.left).copy()

    def link_pose(self, name: str) -> np.ndarray:
        if name == "J1_6":
            return self.eef.copy()
        if name == "J2_6":
            return self.left.copy()
        if name in ("J1_7", "J1_8"):
            return m.pose_compose(self.eef, finger_joint_pose(name, self.q[12 if name == "J1_7" else 13]))
        if name in ("gsmini_left", "gsmini_right"):
            finger = "J1_7" if name == "gsmini_left" else "J1_8"
            return m.pose_compose(self.link_pose(finger), gel_pose_in_finger(name))
        if name in self.fixed:
            return self.fixed[name].copy()
        raise KeyError(f"link {name!r} is not modelled by the kinematic hand")

    def reset_robot(self, q: Optional[np.ndarray] = None) -> None:
        self.eef = self.eef0.copy()
        self.q[12:16] = [0.010, -0.010, 0.010, -0.010]
        self.q_target = self.q.copy()

    def reset_objects(self) -> None:
        return None

    def get_state(self) -> Dict[str, Any]:
        return {"robot_q": self.q.copy(), "eef": self.eef.copy(), "tick": self.tick}

    def set_state(self, state: Dict[str, Any]) -> None:
        self.q = np.asarray(state["robot_q"], dtype=np.float64).copy()
        self.q_target = self.q.copy()
        self.eef = np.asarray(state["eef"], dtype=np.float64).copy()
        self.tick = int(state.get("tick", self.tick))

    def close(self) -> None:
        return None
