"""Franka Panda forward kinematics to the flange (panda_link8) in the robot base frame (panda_link0).

DROID's cartesian_position is this flange pose as [x, y, z, extrinsic xyz Euler] with no TCP offset; GR00T's
eef_9d is computed from it (the GR00T research check reproduced DROID's stored poses to 3e-8 m).
"""
import numpy as np
from scipy.spatial.transform import Rotation

# Modified (Craig) Denavit-Hartenberg parameters (a, d, alpha) of joints 1-7, then the 0.107 m flange.
DH = ((0, 0.333, 0), (0, 0, -np.pi / 2), (0, 0.316, np.pi / 2), (0.0825, 0, np.pi / 2),
      (-0.0825, 0.384, -np.pi / 2), (0, 0, np.pi / 2), (0.088, 0, np.pi / 2))
FLANGE_M = 0.107


def link_transform(a, d, alpha, theta):
    ca, sa, ct, st = np.cos(alpha), np.sin(alpha), np.cos(theta), np.sin(theta)
    return np.array([[ct, -st, 0, a], [st * ca, ct * ca, -sa, -d * sa], [st * sa, ct * sa, ca, d * ca], [0, 0, 0, 1]])


def flange_pose(q):
    pose = np.eye(4)
    for (a, d, alpha), theta in zip(DH, q):
        pose = pose @ link_transform(a, d, alpha, theta)
    return pose @ link_transform(0, FLANGE_M, 0, 0)


def droid_cartesian(q):
    pose = flange_pose(q)
    return np.r_[pose[:3, 3], Rotation.from_matrix(pose[:3, :3]).as_euler("xyz")]
