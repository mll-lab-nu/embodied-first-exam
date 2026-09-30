from topogym.tasks.slotted_post_ring.common import SlottedPostRingTask
from terminal_fixtures import placement, region


def fixture():
    task = SlottedPostRingTask()
    state = placement(task,("target_ring",),("post","cord","bead_left","disc_left","disc_right"),
        soft_names=("cord",),attachments=("cord_disc_left","cord_disc_right"))
    return task,state


def test_whole_ring_in_region_and_system_dragging_rejected():
    task,state = fixture()
    assert task.evaluate_goal_region(state,region())[0]
    state["bodies"]["target_ring"]["position_m"][0] = 1.19
    assert not task.evaluate_goal_region(state,region())[0]
    state["bodies"]["target_ring"]["position_m"][0] = 1.
    state["fem"]["cord"]["position_m"][-1,0] = .51
    assert not task.evaluate_goal_region(state,region())[0]


def test_broken_attachment_missing_evidence_and_not_yet_activated():
    task,state = fixture()
    assert task.evaluate_state(state)[2]["evaluation_status"] == "unavailable"
    state["ipc"]["attachment_residual_m"]["cord_disc_left"] = .1
    assert task.evaluate_goal_region(state,region())[1] == "connection_or_volume_invalid"
    assert task.evaluate_state(state)[1] == "connection_or_volume_invalid"
    state["ipc"] = {}
    assert not task.evaluate_goal_region(state,region())[0]
