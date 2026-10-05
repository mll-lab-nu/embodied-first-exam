"""pi0.5 ALOHA gripper values <-> TopoGym opening (NumPy only).

openpi (aloha_policy.py) converts between the standard ALOHA normalized gripper values and pi's gripper, the motor
angle between 0.5476 rad (closed in pi's data) and pi/2 (fully open), through the Interbotix linkage. Using the
ALOHA normalized value directly as TopoGym's opening would put pi's "closed" at opening 0.553 (21 mm per finger).
Here TopoGym's opening is the finger travel between pi's closed and fully open positions of that linkage, so closed
and open match: states are encoded so that openpi's input transform yields the same finger travel, and actions are
decoded from the motor angle openpi outputs.
"""
import numpy as np

POSITION_CLOSED, POSITION_OPEN = 0.01844, 0.05800   # ALOHA normalized finger position range, m
JOINT_CLOSED, JOINT_OPEN = -0.6213, 1.4910          # ALOHA normalized gripper joint range, rad
ARM_LENGTH, HORN_RADIUS = 0.036, 0.022              # Interbotix linkage, m


def finger(angle):
    """Linear finger position of the Interbotix linkage at a motor angle (inverse of openpi's linear_to_radian)."""
    return HORN_RADIUS * np.sin(angle) + np.sqrt(ARM_LENGTH ** 2 - (HORN_RADIUS * np.cos(angle)) ** 2)


FINGER_CLOSED, FINGER_OPEN = finger(0.5476), finger(np.pi / 2)


def to_openpi_gripper(opening):
    """TopoGym opening -> the ALOHA normalized finger position openpi expects in the state."""
    position = FINGER_CLOSED + np.asarray(opening) * (FINGER_OPEN - FINGER_CLOSED)
    return (position - POSITION_CLOSED) / (POSITION_OPEN - POSITION_CLOSED)


def from_openpi_gripper(value):
    """openpi's ALOHA gripper action (normalized joint) -> TopoGym opening. Angles past the linkage's widest point
    (pi/2) stay fully open; commands below pi's closed angle give negative openings, which the adapter clips."""
    angle = np.minimum(np.asarray(value) * (JOINT_OPEN - JOINT_CLOSED) + JOINT_CLOSED, np.pi / 2)
    return (finger(angle) - FINGER_CLOSED) / (FINGER_OPEN - FINGER_CLOSED)
