"""ALOHA dual-arm joint groups, native finger rails and home positions."""

from topogym.robot.description import JointGroup, RobotDescription, GraspDescription


def describe(config):
    groups = []
    for side in ("left", "right"):
        arm = tuple(f"{side}/{n}" for n in config.robot.arm_joint_names)
        fingers = tuple(f"{side}/{n}" for n in config.robot.finger_joint_names)
        groups.append(
            JointGroup(
                side,
                arm,
                fingers,
                fingers[:1],
                f"{side}/{config.robot.ee_link}",
                tuple(map(tuple, config.robot.arm_joint_limits)),
                "gripper_position_m",
                (float(config.gripper.closed_qpos), float(config.gripper.open_qpos)),
                tuple(config.home[side]),
                tuple(config.controller.kp),
                tuple(config.controller.kv),
                tuple(config.controller.force_limit),
                # Source MJCF left/right gripper site in gripper_link coordinates.
                tcp_position_in_hand_m=(0.13, 0., -0.003),
                grasp=GraspDescription((f"{side}/left_finger_link", f"{side}/right_finger_link"),
                    float(config.gripper.open_qpos), float(config.gripper.closed_qpos),
                    contact_root_link=f"{side}/gripper_link"),
            )
        )
    return RobotDescription("aloha", tuple(groups))
