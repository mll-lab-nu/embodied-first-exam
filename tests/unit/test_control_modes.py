"""Control frame conventions and atomic validation, independent of Genesis."""
from types import SimpleNamespace
from dataclasses import replace
import numpy as np
import pytest

from topogym.robot.control import compile_action
from topogym.robot.description import JointGroup, RobotDescription
from topogym.robot.joint_position import JointPositionRobot


@pytest.fixture
def robot():
    g = JointGroup("left", ("a", "b"), ("f1", "f2"), ("f1",), "hand",
                   ((-2., 2.), (-2., 2.)), "gripper_position_m", (0., .04),
                   (0., 0., .01, .01), (1., 1., 1.), (1., 1., 1.), (1., 1., 1.),
                   tcp_position_in_hand_m=(0., 0., .1))
    r = object.__new__(JointPositionRobot)
    r.description = RobotDescription("fixture", (g, replace(g, name="right")))
    r.groups = {x.name: x for x in r.description.groups}
    r.observe = lambda: {name: dict(joint_position_rad=np.array([.2, -.3]),
        tcp_position_world_m=np.array([1., 2., 3.]), tcp_orientation_wxyz=np.array([1., 0., 0., 0.]))
        for name in r.groups}
    r.entity = SimpleNamespace(get_qpos=lambda: np.zeros(4))
    r._indices = {"left": [0, 1], "right": [2, 3]}
    r._q_indices = r._indices
    return r


def test_joint_delta_uses_measured_state_and_gripper_is_absolute(robot):
    command = compile_action(robot, {"left": {"joint_delta_rad": [.1, .2], "gripper_position_m": .02}}, "JOINT_DELTA")
    np.testing.assert_allclose(command["left"]["joint_position_rad"], [.3, -.1])
    assert command["left"]["gripper_position_m"] == .02


def test_delta_world_rotation_and_tcp_are_converted_before_ik(robot, monkeypatch):
    from topogym.solvers.genesis_kinematics import GenesisIKSolver
    captured = []
    monkeypatch.setattr(GenesisIKSolver, "solve_checked", lambda self, **kw: captured.append(kw) or np.zeros(4))
    compile_action(robot, {"left": {"translation_world_m": [.2, 0., 0.],
                                      "rotation_world_rad": [0., np.pi / 2, 0.]}}, "EE_DELTA")
    np.testing.assert_allclose(captured[0]["position_world_m"], [1.1, 2., 3.], atol=1e-12)
    np.testing.assert_allclose(captured[0]["orientation_wxyz"], [2**-.5, 0., 2**-.5, 0.], atol=1e-12)


def test_invalid_second_arm_rejected_before_any_ik(robot, monkeypatch):
    from topogym.solvers.genesis_kinematics import GenesisIKSolver
    monkeypatch.setattr(GenesisIKSolver, "solve_checked", lambda *args, **kw: pytest.fail("IK before complete input validation"))
    with pytest.raises(ValueError):
        compile_action(robot, {"left": {"translation_world_m": [.01, 0., 0.]},
                               "right": {"rotation_world_rad": [0., float("nan"), 0.]}}, "EE_DELTA")


@pytest.mark.parametrize("command", [
    {"joint_delta_rad": [False, 0.]}, {"joint_delta_rad": [9., 0.]},
    {"joint_delta_rad": [1.]}, {"gripper_position_m": .05},
])
def test_bad_delta_or_gripper_rejected(robot, command):
    with pytest.raises(ValueError):
        compile_action(robot, {"left": command}, "JOINT_DELTA")


def test_incomplete_or_non_unit_absolute_pose_rejected(robot):
    with pytest.raises(ValueError):
        compile_action(robot, {"left": {"position_world_m": [1., 2., 3.]}}, "EE_ABS")
    with pytest.raises(ValueError):
        compile_action(robot, {"left": {"position_world_m": [1., 2., 3.], "orientation_wxyz": [2., 0., 0., 0.]}}, "EE_ABS")


def test_world_delta_on_rotated_tcp_and_rotated_tool_frame(robot, monkeypatch):
    """Noncommuting rotations distinguish world delta from local delta."""
    from topogym.solvers.genesis_kinematics import GenesisIKSolver
    half = 2**-.5
    robot.groups = {name: replace(group, tcp_orientation_in_hand_wxyz=(half, 0., 0., half))
                    for name, group in robot.groups.items()}
    robot.description = replace(robot.description, groups=tuple(robot.groups.values()))
    robot.observe = lambda: {name: dict(
        joint_position_rad=np.array([.2, -.3]),
        tcp_position_world_m=np.array([1., 2., 3.]),
        tcp_orientation_wxyz=np.array([half, 0., 0., half]),
    ) for name in robot.groups}
    captured = []
    monkeypatch.setattr(GenesisIKSolver, "solve_checked",
                        lambda self, **kw: captured.append(kw) or np.zeros(4))
    compile_action(robot, {"left": {
        "translation_world_m": [-.01, 0., 0.],
        "rotation_world_rad": [np.pi / 2, 0., 0.],
    }}, "EE_DELTA")
    # After world Rx(90), cancelling the tool's Rz(90) leaves hand Rx(90).
    # Its local +Z offset points along world -Y, so hand Y is TCP Y + 0.1.
    np.testing.assert_allclose(captured[0]["position_world_m"], [.99, 2.1, 3.], atol=1e-12)
    np.testing.assert_allclose(captured[0]["orientation_wxyz"], [half, half, 0., 0.], atol=1e-12)


@pytest.mark.parametrize("mode", ["EE_ABS", "EE_DELTA"])
def test_gripper_only_and_empty_action_do_not_solve_ik(robot, monkeypatch, mode):
    from topogym.solvers.genesis_kinematics import GenesisIKSolver
    monkeypatch.setattr(GenesisIKSolver, "solve_checked",
                        lambda *args, **kwargs: pytest.fail("Gripper-only action invoked IK"))
    assert compile_action(robot, {}, mode) == {}
    command = {"left": {"gripper_position_m": .025}}
    assert compile_action(robot, command, mode) == command


def test_native_ik_limit_roundoff_does_not_relax_action_limits(robot, monkeypatch):
    from topogym.solvers.genesis_kinematics import GenesisIKSolver
    monkeypatch.setattr(GenesisIKSolver, "solve_checked",
                        lambda *args, **kwargs: np.array([2.+3e-10, -2.-4e-10, 0., 0.]))
    pose = {"left": {"position_world_m": [1., 2., 3.], "orientation_wxyz": [1., 0., 0., 0.]}}
    command = compile_action(robot, pose, "EE_ABS")
    assert command["left"]["joint_position_rad"] == [2., -2.]
    with pytest.raises(ValueError, match="outside model limits"):
        compile_action(robot, {"left": {"joint_position_rad": [2.+3e-10, 0.]}}, "JOINT_ABS")
    monkeypatch.setattr(GenesisIKSolver, "solve_checked",
                        lambda *args, **kwargs: np.array([2.+1e-5, 0., 0., 0.]))
    with pytest.raises(ValueError, match="outside model limits"):
        compile_action(robot, pose, "EE_ABS")
