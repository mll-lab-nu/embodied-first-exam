from topogym.tasks.interlocked_claws.common import InterlockedClawsTask
from terminal_fixtures import placement, region


def test_claw_target_does_not_swap_and_holding_is_allowed():
    task = InterlockedClawsTask()
    state = placement(task,("claw_a",),("claw_b",))
    state["contacts"] = {"robot_holding":True}
    assert task.evaluate_goal_region(state,region())[0]
    state["bodies"]["claw_a"]["position_m"][0] = 0
    state["bodies"]["claw_b"]["position_m"][0] = 1
    assert not task.evaluate_goal_region(state,region())[0]
    assert task.goal_region_observation(region())["target_entities"] == ["claw_a"]
