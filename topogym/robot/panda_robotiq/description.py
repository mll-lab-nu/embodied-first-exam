"""Existing Panda seven-axis arm and original-scale Robotiq 2F-85 tool."""

from topogym.robot.description import JointGroup, RobotDescription, GraspDescription
from .gripper import DRIVER_JOINTS, DRIVER_LIMITS_RAD


def describe(config):
    group = JointGroup(
        "arm",
        tuple(config.robot.arm_joint_names),
        DRIVER_JOINTS,
        DRIVER_JOINTS,
        str(config.robot.ee_link),
        tuple(map(tuple, config.robot.arm_joint_limits)),
        "gripper_position_rad",
        DRIVER_LIMITS_RAD,
        tuple(config.home.arm),
        tuple(config.controller.kp),
        tuple(config.controller.kv),
        tuple(config.controller.force_limit),
        # Fixed tool reference near the closed finger pads, not a moving pad centre.
        tcp_position_in_hand_m=(0., 0., 0.1029),
        grasp=GraspDescription(("left_finger", "right_finger"), 0., .8,
                               contact_root_link="tool_mount"),
    )
    return RobotDescription("panda_robotiq", (group,))
