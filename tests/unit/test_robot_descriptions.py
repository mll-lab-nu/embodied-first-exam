"""Two embodiments share a controller while retaining native gripper units and limits."""

from copy import deepcopy
from types import SimpleNamespace
import pytest
from topogym.config import SimulatorConfig
from topogym.config.scene import load_scene_config
from topogym.robot.description import describe_robot
from topogym.robot.joint_position import JointPositionRobot, RobotState


@pytest.mark.parametrize(
    "robot_id,names,arm_count,field",
    [
        ("aloha", ("left", "right"), 6, "gripper_position_m"),
        ("panda_robotiq", ("arm",), 7, "gripper_position_rad"),
    ],
)
def test_profiles_and_atomic_controller_validation(robot_id, names, arm_count, field):
    cfg = load_scene_config(SimulatorConfig(robot_id=robot_id)).robot_control
    description = describe_robot(cfg)
    assert description.robot_id == robot_id
    assert tuple(g.name for g in description.groups) == names
    for group in description.groups:
        assert len(group.arm_joints) == arm_count and group.gripper_field == field
        assert len(group.home) == len(group.arm_joints) + len(group.finger_joints)
        assert len(group.kp) == len(group.arm_joints) + len(group.actuated_fingers)
    # A narrow entity double makes any write from a rejected command observable.
    joint_names = [
        name for g in description.groups for name in g.arm_joints + g.finger_joints
    ]

    class Entity:
        def __init__(self):
            self.writes = []

        def get_joint(self, name):
            index = joint_names.index(name)
            return SimpleNamespace(dofs_idx_local=[index], qs_idx_local=[index])

        def get_link(self, name):
            return SimpleNamespace(name=name)

        def set_dofs_kp(self, *args):
            pass

        def set_dofs_kv(self, *args):
            pass

        def set_dofs_force_range(self, *args):
            pass

        def control_dofs_position(self, values, indices):
            self.writes.append((values.copy(), indices))

    entity = Entity()
    robot = JointPositionRobot(entity, cfg)
    saved = robot.capture_state()
    action = deepcopy(saved.targets)
    action[names[0]]["joint_position_rad"][0] += 0.01
    action[names[-1]][field] = -100.0
    with pytest.raises(ValueError):
        robot.apply_action(action)
    assert not entity.writes and robot.capture_state() == saved
    wrong_units = (
        "gripper_position_m" if field.endswith("rad") else "gripper_position_rad"
    )
    with pytest.raises(ValueError):
        robot.validate_action({names[0]: {wrong_units: 0.0}})
    with pytest.raises(ValueError):
        robot.restore_state(RobotState({}, robot_id))
    robot.apply_action({})
    assert len(entity.writes) == len(names)
    robot.restore_state(saved)
    assert len(entity.writes) == len(names), (
        "Restoring Python targets must not reissue controls"
    )
