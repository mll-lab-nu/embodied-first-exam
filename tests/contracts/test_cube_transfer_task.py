"""The cube Task evaluates physical history independently of policy labels."""
import numpy as np
from fixtures.cube_transfer import CubeTransferTask
import pytest


def state(task, tick, position, opened=True, withdrawal=.12):
    return dict(physics_step=tick, bodies={"cube": dict(position_m=np.asarray(position),
        quaternion_wxyz=np.array([1., 0, 0, 0]), linear_velocity_m_s=np.zeros(3), angular_velocity_rad_s=np.zeros(3))},
        articulations={"robot": dict(links={"hand": dict(
            position_m=np.asarray(position)+[0, 0, withdrawal+.1029],
            quaternion_wxyz=np.array([0., 1., 0., 0.]))},
            joints={name: {"position": [0. if opened else .6]} for name in ("finger_joint1", "finger_joint2")})})


def test_pushing_to_target_cannot_pass_and_history_restores(tmp_path):
    task = CubeTransferTask(seed=0)
    task.declare(tmp_path, .9)
    task.initialize(state(task, 0, task.start))
    for tick in range(1, 8):
        result = task.update(state(task, tick, task.target), .1)
    assert not result.task_success
    for tick in range(8, 11):
        task.update(state(task, tick, task.start+[0, 0, .1], opened=False, withdrawal=.005), .1)
    saved = task.get_state()
    task.update(state(task, 11, task.target+[0, 0, .1], opened=False, withdrawal=.005), .1)
    assert task.lifted and task.transported
    for tick in range(12, 19):
        result = task.update(state(task, tick, task.target, opened=False), .1)
    assert not result.task_success  # Still holding the object.
    for tick in range(19, 26):
        result = task.update(state(task, tick, task.target), .1)
    assert result.task_success
    task.set_state(saved)
    assert task.lifted and not task.transported and not task.result.task_success


@pytest.mark.parametrize("scenario", ["blocked", "brief_lift", "unheld_flight", "dropped"])
def test_failed_manipulation_is_not_success(tmp_path, scenario):
    task = CubeTransferTask(seed=0)
    task.declare(tmp_path, .9)
    task.initialize(state(task, 0, task.start))
    if scenario == "blocked":
        for tick in range(1, 11):
            task.update(state(task, tick, task.start, opened=False, withdrawal=.005), .1)
        assert not task.lifted
    elif scenario == "brief_lift":
        task.update(state(task, 1, task.start+[0, 0, .1], opened=False, withdrawal=.005), .025)
        task.update(state(task, 2, task.target, opened=True), .025)
        assert not task.held_once
    elif scenario == "unheld_flight":
        for tick in range(1, 11):
            task.update(state(task, tick, task.target+[0, 0, .1], opened=True), .1)
        assert not task.lifted and not task.transported
    else:
        for tick in range(1, 4):
            task.update(state(task, tick, task.start+[0, 0, .1], opened=False, withdrawal=.005), .1)
        task.update(state(task, 4, task.target+[0, 0, .1], opened=False, withdrawal=.005), .1)
        result = task.update(state(task, 5, task.target-[0, 0, .2]), .1)
        assert result.terminated and result.reason == "cube_fell"
    assert not task.result.task_success
