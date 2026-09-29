from types import SimpleNamespace
import numpy as np
import pytest
from topogym.tasks.rope_threading.common import RopeThreadingTask
from terminal_fixtures import body, soft, ipc


def fixture(points=((-1,0,.8),(3,0,.8))):
    task = RopeThreadingTask()
    rings = [dict(name=f"R{i+1}",center_m=[i,0,.8],normal=[-1 if i==0 else 1,0,0],radius_m=.15,tube_radius_m=.01) for i in range(3)]
    task.layout = SimpleNamespace(rope_radius_m=.002, rings=lambda:rings,
                                  required_crossings=lambda:[("R1",-1),("R2",1),("R3",1)])
    rope = soft(points)
    task.centerline_map = (np.arange(len(points)),rope["material_s_m"].copy())
    state = dict(fem={"rope":rope},bodies={r["name"]:body() for r in rings},ipc=ipc(),physics_step=1)
    return task,state


def test_signed_material_sequence_and_incomplete_success_gate():
    task,state = fixture()
    reached,failure,metrics = task.evaluate_state(state)
    assert reached and not failure
    assert metrics["crossing_sequence"] == [("R1",-1),("R2",1),("R3",1)]
    for tick in range(1,10):
        state["physics_step"] = tick
        assert not task.update(state,.1).terminated


@pytest.mark.parametrize("points", [((3,0,.8),(-1,0,.8)), ((-1,0,.8),(1.5,0,.8)), ((-1,0,.8),(3,0,.8),(-1,0,.8)), ((-1,1,.8),(3,1,.8))])
def test_wrong_direction_missing_extra_and_outside(points):
    task,state = fixture(points)
    assert not task.evaluate_state(state)[0]


def test_all_vertices_must_settle_and_ipc_evidence_required():
    task,state = fixture()
    state["fem"]["rope"]["velocity_m_s"][0,0] = .01
    assert not task.evaluate_state(state)[0]
    state["ipc"] = {}
    assert task.evaluate_state(state)[2]["evaluation_status"] == "unavailable"


def test_ring_poses_are_measured_not_assumed():
    task,state = fixture()
    state["bodies"]["R2"]["position_m"][1] = 1.
    assert not task.evaluate_state(state)[0]


def test_selected_ring_layout_supplies_its_own_order():
    task,state = fixture()
    rings = task.layout.rings()[:2]
    task.layout.rings = lambda:rings
    task.layout.required_crossings = lambda:[("R1",-1),("R2",1)]
    reached,_,metrics = task.evaluate_state(state)
    assert reached and metrics["crossing_sequence"] == [("R1",-1),("R2",1)]
