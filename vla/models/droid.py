"""Joint convention of DROID-trained checkpoints on the TopoGym Panda.

DROID mounts the Robotiq 2F-85 on the Panda flange with no yaw: its reset pose has q7 = 0, and the official DROID
simulation models (MolmoAct2's fr3_robotiq.urdf, RoboLab's DROID USD) attach the gripper to the flange directly.
TopoGym attaches the Robotiq to the Franka hand frame instead, -45 deg about the flange axis
(topogym/assets/robot.py build_robotiq_panda). It also sets the Robotiq's own rotation to identity, so the knuckles
lie along the y axis of that mount frame, as they lie along the flange y axis in DROID; the two grippers then
differ by exactly that 45 deg, and the same gripper pose reads q7_droid = q7_topogym - pi/4.
"""
import numpy as np

WRIST_OFFSET_RAD = np.pi / 4


def to_droid_joints(joints):
    """TopoGym arm joints (7,) -> the DROID convention."""
    droid = np.array(joints[:7], dtype=np.float32)
    droid[6] -= WRIST_OFFSET_RAD
    return droid


def from_droid_joints(joints):
    """DROID joint targets (..., 7) -> TopoGym arm joints."""
    topogym = np.array(joints, dtype=np.float32)
    topogym[..., 6] += WRIST_OFFSET_RAD
    return topogym
