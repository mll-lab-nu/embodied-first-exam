from topogym.tasks.hedgehog_in_cage.common import HedgehogInCageTask
from terminal_fixtures import placement, region


def test_spike_outside_and_cage_following_block_success():
    task = HedgehogInCageTask()
    state = placement(task,("hedgehog_ball",),("hedgehog_cage",))
    assert task.evaluate_goal_region(state,region())[0]
    task.placement_vertices["hedgehog_ball"][1,0] = .21
    assert not task.evaluate_goal_region(state,region())[0]
    task.placement_vertices["hedgehog_ball"][1,0] = .02
    state["bodies"]["hedgehog_cage"]["position_m"][0] = .49
    assert not task.evaluate_goal_region(state,region())[0]
