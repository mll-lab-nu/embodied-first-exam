"""Pure strategy checks; success here is not a physics qualification."""
import numpy as np
import pytest
from topogym.planning.examples.cube_pick_place import CubePickPlacePolicy
from fixtures.cube_pick_place import CubePickPlaceTask
from contracts.test_cube_transfer_task import state


def inputs():
    context = dict(mode="unlimited", timing_spec=dict(control_dt_s=.025),
        observation_spec=dict(privileged_fields=["world"]), action_spec=dict(robot_id="panda_robotiq",
            mode="EE_ABS", arms=["arm"], groups=dict(arm=dict(gripper_field="gripper_position_rad", gripper_limits=[0., .8]))))
    obs = dict(state=dict(sim_time_s=0.), robot=dict(arm=dict(tcp_position_world_m=np.array([0., 0., 1.3]),
        tcp_orientation_wxyz=np.array([1., 0., 0., 0.]))),
        privileged=dict(world=dict(bodies=dict(cube=dict(position_m=np.array([-.1, -.1, .92]))))))
    return context, obs


@pytest.mark.parametrize("cube_follows", [False, True])
def test_stateful_actions_require_cube_lift(cube_follows):
    context, obs = inputs()
    policy = CubePickPlacePolicy()
    policy.initialize(context)
    phases = set()
    for _ in range(700):
        try:
            action = policy.act(obs)
        except RuntimeError as error:
            assert not cube_follows and "failed to lift" in str(error)
            break
        if action is None:
            assert cube_follows and "release" in phases and "retreat" in phases
            break
        assert isinstance(action, dict)
        phases.add(policy.phase)
        command = action.get("arm", {})
        if "position_world_m" in command:
            obs["robot"]["arm"]["tcp_position_world_m"] = np.array(command["position_world_m"])
            obs["robot"]["arm"]["tcp_orientation_wxyz"] = np.array(command["orientation_wxyz"])
        if cube_follows and policy.phase == "lift":
            obs["privileged"]["world"]["bodies"]["cube"]["position_m"] = (
                obs["robot"]["arm"]["tcp_position_world_m"] - [0, 0, .005])
        obs["state"]["sim_time_s"] += .025
    else:
        pytest.fail("Policy failed to end")


def test_limited_cannot_silently_run_world_reference():
    context, _ = inputs()
    context["mode"] = "limited"
    with pytest.raises(ValueError, match="authorized world"):
        CubePickPlacePolicy().initialize(context)


def test_in_place_predicate_requires_lift_release_and_settling(tmp_path):
    task = CubePickPlaceTask(seed=0)
    task.declare(tmp_path, .9)
    task.initialize(state(task, 0, task.start))
    for tick in range(1, 8):
        task.update(state(task, tick, task.start), .1)
    assert not task.result.task_success
    for tick in range(8, 13):
        task.update(state(task, tick, task.start+[0, 0, .1], opened=False, withdrawal=.005), .1)
    assert task.lifted and not task.transported
    for tick in range(13, 20):
        task.update(state(task, tick, task.start, opened=False), .1)
    assert not task.result.task_success
    for tick in range(20, 26):
        task.update(state(task, tick, task.start), .1)
    assert task.result.task_success
