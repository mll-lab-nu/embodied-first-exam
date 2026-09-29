from types import SimpleNamespace
import numpy as np
from topogym.tasks.knot_untying.common import KnotUntyingTask
from terminal_fixtures import soft, ipc


def fixture():
    task = KnotUntyingTask()
    task.layout = SimpleNamespace(rope_radius_m=.002)
    task.table_height_m = .75
    rope = soft([[0,0,.752],[.02,0,.752],[.04,0,.752],[.06,0,.752]])
    task.centerline_map = (np.arange(4),rope["material_s_m"].copy())
    return task,dict(fem={"rope":rope},ipc=ipc())


def test_tabletop_clear_rope_and_lifted_false_positive():
    task,state = fixture()
    assert task.evaluate_state(state)[0]
    state["fem"]["rope"]["position_m"][:,2] += .1
    assert not task.evaluate_state(state)[0]


def test_crossing_collinear_overlap_motion_and_broken_volume():
    task,state = fixture()
    p = state["fem"]["rope"]["position_m"]
    p[:,:2] = [[0,0],[.05,.05],[0,.05],[.05,0]]
    assert not task.evaluate_state(state)[0]
    p[:,:2] = [[0,0],[.05,0],[.01,0],[.04,0]]
    assert not task.evaluate_state(state)[0]
    task,state = fixture()
    state["fem"]["rope"]["velocity_m_s"][-1,0] = .1
    assert not task.evaluate_state(state)[0]
    state["ipc"]["volume_ratio"]["rope"]["minimum"] = -.01
    assert task.evaluate_state(state)[1] == "rope_volume_invalid"
