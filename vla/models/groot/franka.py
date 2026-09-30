"""Franka Panda forward kinematics to the flange (panda_link8) in the robot base frame (panda_link0), and GR00T's
eef_9d of that flange.

DROID's cartesian_position is this flange pose with no TCP offset (reproduced to 3e-8 m on the DROID sample), its
rotation stored as extrinsic xyz Euler angles. The repo's compute_eef_9d reads those angles as intrinsic "XYZ",
which gives another rotation away from q7 = 0; open loop on the DROID sample the true rotation predicts the recorded
joints better (median error 20 % lower over the 8 executed steps, runs/test_results/20260930_vla_groot_eef9d), so
eef_9d here uses the flange rotation itself.
"""
import numpy as np

# Modified (Craig) Denavit-Hartenberg parameters (a, d, alpha) of joints 1-7, then the 0.107 m flange.
DH = ((0, 0.333, 0), (0, 0, -np.pi / 2), (0, 0.316, np.pi / 2), (0.0825, 0, np.pi / 2),
      (-0.0825, 0.384, -np.pi / 2), (0, 0, np.pi / 2), (0.088, 0, np.pi / 2))
FLANGE_M = 0.107
# gr00t/data/state_action/droid_frame.py DROID_EEF_ROTATION_CORRECT, the frame change of GR00T's DROID data.
EEF_ROTATION_CORRECT = np.array([[0, 0, -1], [-1, 0, 0], [0, 1, 0]])


def link_transform(a, d, alpha, theta):
    ca, sa, ct, st = np.cos(alpha), np.sin(alpha), np.cos(theta), np.sin(theta)
    return np.array([[ct, -st, 0, a], [st * ca, ct * ca, -sa, -d * sa], [st * sa, ct * sa, ca, d * ca], [0, 0, 0, 1]])


def flange_pose(q):
    pose = np.eye(4)
    for (a, d, alpha), theta in zip(DH, q):
        pose = pose @ link_transform(a, d, alpha, theta)
    return pose @ link_transform(0, FLANGE_M, 0, 0)


def eef_9d(q):
    """Flange position and the first two rows of (flange rotation @ EEF_ROTATION_CORRECT)."""
    pose = flange_pose(q)
    return np.r_[pose[:3, 3], (pose[:3, :3] @ EEF_ROTATION_CORRECT)[:2, :].reshape(6)]
