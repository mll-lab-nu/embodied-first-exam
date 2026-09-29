"""Robot embodiment data shared by the single joint-position controller."""

from dataclasses import dataclass


@dataclass(frozen=True)
class GraspDescription:
    """Explicit native open/closed coordinates and the two opposing links."""
    finger_links: tuple[str, str]
    open_position: float
    closed_position: float
    # Entire tool subtree, including housing/linkage, for forbidden-contact rules.
    contact_root_link: str | None = None


@dataclass(frozen=True)
class JointGroup:
    name: str
    arm_joints: tuple[str, ...]
    finger_joints: tuple[str, ...]
    actuated_fingers: tuple[str, ...]
    hand_link: str
    arm_limits_rad: tuple
    gripper_field: str
    gripper_limits: tuple[float, float]
    home: tuple[float, ...]
    kp: tuple[float, ...]
    kv: tuple[float, ...]
    force: tuple[float, ...]
    tcp_position_in_hand_m: tuple[float, float, float] = (0., 0., 0.)
    tcp_orientation_in_hand_wxyz: tuple[float, float, float, float] = (1., 0., 0., 0.)
    grasp: GraspDescription | None = None


@dataclass(frozen=True)
class RobotDescription:
    robot_id: str
    groups: tuple[JointGroup, ...]


def describe_robot(config):
    name = str(config.robot.name)
    if name == "aloha":
        from .aloha.description import describe
    elif name == "panda_robotiq":
        from .panda_robotiq.description import describe
    else:
        raise ValueError(f"Unsupported robot combination: {name}")
    return describe(config)
