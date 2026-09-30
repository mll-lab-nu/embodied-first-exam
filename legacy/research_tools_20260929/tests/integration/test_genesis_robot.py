"""Future ALOHA and Panda/Robotiq Genesis checks; these tests were written but not run.

Robot assets must be installed or TOPOGYM_ASSET_ROOT configured. Test each
TOPOGYM_TEST_DEVICE in its own process with Genesis 1.2.1 and precision 64.
These verify simulator control/continuation, not task-solving competence.
"""

from copy import deepcopy
import os

import numpy as np
import pytest


pytestmark = [pytest.mark.genesis, pytest.mark.rigid]


@pytest.fixture(params=["aloha", "panda_robotiq"])
def robot_world(request):
    import torch
    from topogym.config import SimulatorConfig
    from topogym.config.scene import load_scene_config
    from topogym.robot import make_robot
    from topogym.world import GenesisWorld

    device = os.environ.get("TOPOGYM_TEST_DEVICE", "cpu")
    if device == "cuda" and not torch.cuda.is_available():
        pytest.fail("Requested CUDA validation was not performed: CUDA is unavailable")
    config = SimulatorConfig(
        robot_id=request.param,
        compute_backend=device,
        precision="64",
        enable_rgb=False, enable_privileged=True,
        asset_root=os.environ.get("TOPOGYM_ASSET_ROOT"),
    )
    scene_config = load_scene_config(config)
    world = GenesisWorld.from_tabletop(
        scene_config.env,
        scene_config.robot_control,
        compute_backend=device,
        precision="64",
        seed=5,
        cameras=False,
    )
    try:
        world.build()
        robot = make_robot(world.entities["robot"], scene_config.robot_control)
        robot.reset_home()
        yield world, robot
    finally:
        world.close()


def test_commands_validate_atomically_and_do_not_step(robot_world):
    world, robot = robot_world
    before = robot.observe()
    initial_targets = deepcopy(robot.capture_state().targets)
    first, last = robot.sides[0], robot.sides[-1]
    left = np.asarray(initial_targets[first]["joint_position_rad"])
    left[0] += 0.02
    action = {first: {"joint_position_rad": left}}
    normalized = robot.validate_action(action)
    left[0] += 0.2
    assert normalized[first]["joint_position_rad"][0] != left[0]
    robot.apply_action(normalized)
    assert world.physics_step == 0 and world.scene.t == 0
    np.testing.assert_array_equal(
        robot.observe()[first]["joint_position_rad"],
        before[first]["joint_position_rad"],
    )
    targets = deepcopy(robot.capture_state().targets)
    with pytest.raises(ValueError):
        command = {first: {"joint_position_rad": left.tolist()}}
        command.setdefault(last, {})[robot.groups[last].gripper_field] = -1.0
        robot.apply_action(command)
    assert robot.capture_state().targets == targets, (
        "Any invalid group must reject the entire command"
    )


def test_saved_physics_and_robot_targets_continue_together(robot_world):
    world, robot = robot_world
    command = robot.capture_state().targets
    for index, side in enumerate(robot.sides):
        command[side]["joint_position_rad"][0] += 0.03 * (-1 if index else 1)
    robot.apply_action(command)
    for _ in range(6):
        world.advance()
    saved_world, saved_robot = world.capture_state(), robot.capture_state()
    measured = robot.observe()
    trajectory = []
    for _ in range(8):
        world.advance()
        trajectory.append(robot.observe())
    # Change both an arm target and the gripper target after the saved point.
    group = robot.groups[robot.sides[0]]
    robot.apply_action({group.name: {group.gripper_field: group.gripper_limits[1]}})
    world.advance()
    world.restore_state(saved_world)
    robot.restore_state(saved_robot)
    assert world.physics_step == 6
    assert robot.capture_state().targets == saved_robot.targets
    for side in robot.sides:
        np.testing.assert_array_equal(
            robot.observe()[side]["joint_position_rad"],
            measured[side]["joint_position_rad"],
        )
    tolerance = 2e-8 if os.environ.get("TOPOGYM_TEST_DEVICE", "cpu") == "cpu" else 2e-5
    for expected in trajectory:
        world.advance()
        actual = robot.observe()
        for side in robot.sides:
            finger_field = (
                "finger_position_m"
                if robot.groups[side].gripper_field.endswith("_m")
                else "finger_position_rad"
            )
            np.testing.assert_allclose(
                actual[side]["joint_position_rad"],
                expected[side]["joint_position_rad"],
                rtol=0.0,
                atol=tolerance,
            )
            np.testing.assert_allclose(
                actual[side][finger_field],
                expected[side][finger_field],
                rtol=0.0,
                atol=tolerance,
            )


def test_genesis_kinematics_queries_do_not_move_the_robot(robot_world):
    from topogym.solvers import GenesisFKSolver, GenesisIKSolver

    world, robot = robot_world
    qpos = robot.entity.get_qpos().detach().cpu().numpy().copy()
    before = robot.observe()
    poses = GenesisFKSolver(robot.entity).solve(qpos)
    assert np.isfinite(poses["position_world_m"]).all()
    first = robot.sides[0]
    group = robot.groups[first]
    target = before[first]["hand_position_world_m"]
    solution = GenesisIKSolver(robot.entity).solve(
        link_name=group.hand_link,
        position_world_m=target,
        orientation_wxyz=before[first]["hand_orientation_wxyz"],
        joint_dof_indices=robot._indices[first][: len(group.arm_joints)],
    )
    assert np.isfinite(solution).all()
    assert world.physics_step == 0 and world.scene.t == 0
    np.testing.assert_allclose(
        robot.entity.get_qpos().detach().cpu().numpy(), qpos, rtol=0.0, atol=1e-12
    )
