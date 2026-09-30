"""Standard ee vectors <-> X-VLA RoboTwin2 ee6d vectors (NumPy and SciPy only).

X-VLA RoboTwin2, per arm, left first: [xyz, v6, g] (X-VLA models/action_hub.py EE6DActionSpace).
  xyz  origin of URDF link6 in the RoboTwin world (m); the RoboTwin TCP lies tcp_offset_m further along link6 x.
  v6   X-VLA rot6d, the first two matrix columns flattened row-major, of the rotation obtained by reading
       RoboTwin's scalar-first quaternion as scalar-last. Training and the official client both do this
       (X-VLA issue #93), so the misread is reproduced here.
  g    1 - RoboTwin gripper, 1 = closed; the official client closes when g > 0.7.
Each arm keeps its TCP pose relative to its own base frame (TopoGym -> RoboTwin), with the frames given in the
model config. Tool axes match (x approach, z up at the neutral pose) for the ViperX gripper link and RoboTwin link6.
"""
import numpy as np
from scipy.spatial.transform import Rotation

CLOSE_THRESHOLD = 0.7


def base_transform(topogym_base, robotwin_base):
    """(A, a) with p_robotwin = A p_topogym + a, from base frames given as [x, y, z, yaw_deg] (z up)."""
    A = Rotation.from_euler("z", robotwin_base[3] - topogym_base[3], degrees=True).as_matrix()
    return A, np.asarray(robotwin_base[:3]) - A @ np.asarray(topogym_base[:3])


def orthonormal(c1, c2):
    b1 = c1 / np.linalg.norm(c1)
    b2 = c2 - (b1 @ c2) * b1
    b2 = b2 / np.linalg.norm(b2)
    return np.stack([b1, b2, np.cross(b1, b2)], axis=1)


def arm_to_xvla(arm, A, a, tcp_offset):
    rotation = A @ orthonormal(arm[3:6], arm[6:9])
    x, y, z, w = Rotation.from_matrix(rotation).as_quat()
    misread = Rotation.from_quat([w, x, y, z]).as_matrix()
    return np.r_[A @ arm[:3] + a - tcp_offset * rotation[:, 0], misread[:, :2].reshape(6), 1.0 - arm[9]]


def arm_from_xvla(arm, A, a, tcp_offset):
    w, x, y, z = Rotation.from_matrix(orthonormal(arm[3:9:2], arm[4:9:2])).as_quat()
    rotation = Rotation.from_quat([x, y, z, w]).as_matrix()
    topogym = A.T @ rotation
    tcp = A.T @ (arm[:3] + tcp_offset * rotation[:, 0] - a)
    return np.r_[tcp, topogym[:, 0], topogym[:, 1], float(arm[9] <= CLOSE_THRESHOLD)]


def to_xvla(ee, transforms, tcp_offset):
    """Measured standard ee state (20,) -> X-VLA proprio (20,)."""
    return np.concatenate([arm_to_xvla(arm, *t, tcp_offset)
                           for arm, t in zip(np.split(ee, 2), transforms)]).astype(np.float32)


def from_xvla(actions, transforms, tcp_offset):
    """X-VLA actions (H, 20) -> standard ee_abs rows (H, 20)."""
    return np.array([np.concatenate([arm_from_xvla(arm, *t, tcp_offset)
                                     for arm, t in zip(np.split(row, 2), transforms)]) for row in actions], np.float32)
