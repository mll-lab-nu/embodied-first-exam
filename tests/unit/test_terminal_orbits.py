from topogym.tasks.orbits.common import OrbitsTask
from terminal_fixtures import placement, region


def fixture():
    task = OrbitsTask()
    state = placement(task,("cord","handle"),("base","ring_1"),soft_names=("cord",),
                      attachments=("cord_handle_start","cord_handle_end"))
    return task,state


def test_entire_cord_and_handle_not_just_handle_position():
    task,state = fixture()
    assert task.evaluate_goal_region(state,region())[0]
    state["fem"]["cord"]["position_m"][-1,0] = .2
    assert not task.evaluate_goal_region(state,region())[0]
    task,state = fixture()
    state["bodies"]["handle"]["position_m"][0] = 1.19
    assert not task.evaluate_goal_region(state,region())[0]
    assert "cord" in task.goal_region_observation(region())["instruction"]


def test_motion_height_and_attachment_integrity():
    task,state = fixture()
    state["fem"]["cord"]["velocity_m_s"][-1,0] = .1
    assert not task.evaluate_goal_region(state,region())[0]
    task,state = fixture()
    state["bodies"]["handle"]["position_m"][2] += 1
    assert not task.evaluate_goal_region(state,region())[0]
    task,state = fixture()
    state["ipc"]["attachment_residual_m"]["cord_handle_end"] = .1
    assert task.evaluate_goal_region(state,region())[1]
