from types import SimpleNamespace
from copy import deepcopy
import numpy as np
import pytest
from scipy.spatial.transform import Rotation
import topogym.tasks.buzz_wire_3d.common as module
from terminal_fixtures import body


def fixture(monkeypatch):
    task = module.BuzzWireTask()
    task.table_height_m = .75
    task.origin = np.zeros(3)
    task.rail = np.array([[-.5,0,.8],[.5,0,.8]])
    task.layout = SimpleNamespace(loop_radius_m=.1,loop_tube_radius_m=.01,wire_radius_m=.005)
    task.route = object()
    r = Rotation.from_euler("y",90,degrees=True)
    monkeypatch.setattr(module,"endpoint_pose",lambda route,end:(np.array([.49,0,.8]),r))
    state = dict(physics_step=0,bodies={"wand":body((-.49,0,.8),r.as_quat()[[3,0,1,2]])},assist_active=False)
    events(state)
    return task,state


def events(state,*pairs,complete=True):
    state["contact_events"] = dict(schema_version=1,physics_step=state["physics_step"],substeps_complete=complete,
        geometry_roles_complete=True,events=[dict(role_a=a,role_b=b,touching=True,substep=1,force_n=0.) for a,b in pairs])


def test_zero_force_touch_fails_and_rewind_removes_future_failure(monkeypatch):
    task,state = fixture(monkeypatch)
    task.initialize(state)
    saved = task.get_state()
    state["physics_step"] = 1
    events(state,("wire_metal","wand_metal"))
    result = task.update(state,.0025)
    assert result.terminated and result.reason == "wire_touched" and not result.task_success
    assert result.metrics["contact_events"][0]["substep"] == 1
    task.set_state(saved)
    assert not task.result.terminated


def test_wood_support_and_unresolved_link_contacts_are_not_metal_touch(monkeypatch):
    task,state = fixture(monkeypatch)
    events(state,("wand_handle","wire_metal"),("wand_metal","wood_stop"))
    assert task.evaluate_state(state)[1] is None
    state.pop("contact_events")
    state["contacts"] = dict(link_a=[1],link_b=[2])
    assert task.evaluate_state(state)[2]["evaluation_status"] == "unavailable"


def test_traversal_support_release_and_failure_priority(monkeypatch):
    task,state = fixture(monkeypatch)
    task.initialize(state)
    for tick,x in enumerate([-.49,-.25,0,.25,.49],1):
        state["physics_step"] = tick
        state["bodies"]["wand"]["position_m"][0] = x
        events(state,("wand_handle","finish_support"))
        result = task.update(state,.01)
    assert task.evaluate_state(state)[0]
    assert not result.task_success  # The full settling window is still required.
    previous = deepcopy(task.task_state)
    task.evaluate_state(state)
    assert task.task_state["cursor_m"] == previous["cursor_m"]
    state["assist_active"] = True
    assert not task.evaluate_state(state)[0]
    state["assist_active"] = False
    events(state,("wand_handle","finish_support"),("wand_metal","wire_metal"))
    assert task.evaluate_state(state)[1] == "wire_touched"


def test_finish_without_traversal_or_stale_events_cannot_qualify(monkeypatch):
    task,state = fixture(monkeypatch)
    state["bodies"]["wand"]["position_m"][0] = .49
    events(state,("wand_handle","finish_support"))
    assert not task.evaluate_state(state)[0]
    state["contact_events"]["physics_step"] = 99
    with pytest.raises(ValueError,match="Stale"):
        task.evaluate_state(state)


def test_missing_earlier_contact_coverage_is_restored_and_never_filled_by_last_tick(monkeypatch):
    task,state = fixture(monkeypatch)
    task.initialize(state)
    initial = task.get_state()
    for tick,x in enumerate([-.49,-.25,0,.25,.49],1):
        state["physics_step"] = tick
        state["bodies"]["wand"]["position_m"][0] = x
        events(state,("wand_handle","finish_support"),complete=tick!=2)
        task.update(state,.01)
    reached,_,metrics = task.evaluate_state(state)
    assert not reached and metrics["evaluation_status"] == "unavailable"
    assert not task.task_state["coverage_complete"]
    task.set_state(initial)
    assert task.task_state["coverage_complete"]  # Discarded future does not poison a fresh branch.


def test_unobserved_birth_cannot_be_certified_by_later_contacts(monkeypatch):
    task,state = fixture(monkeypatch)
    state.pop("contact_events")
    task.initialize(state)
    state["physics_step"] = 1
    events(state)
    task.update(state,.01)
    assert not task.task_state["coverage_complete"]


def test_completed_traversal_survives_lowering_off_last_wire_endpoint(monkeypatch):
    task, state = fixture(monkeypatch)
    task.initialize(state)
    for tick, x in enumerate([-.49, -.25, 0., .25, .49], 1):
        state["physics_step"] = tick
        state["bodies"]["wand"]["position_m"][0] = x
        events(state)
        task.update(state, .01)
    assert task.task_state["traversal_complete"]
    finish = np.array([.51, 0., .8])  # No longer intersects the finite wire.
    r = Rotation.from_euler("y", 90, degrees=True)
    monkeypatch.setattr(module, "endpoint_pose", lambda route, end: (finish, r))
    state["bodies"]["wand"]["position_m"] = finish.copy()
    state["bodies"]["wand"]["quaternion_wxyz"] = (r*Rotation.from_euler("x", 180, degrees=True)).as_quat()[[3,0,1,2]]
    state["physics_step"] += 1
    events(state, ("wand_handle", "finish_support"))
    reached, failure, metrics, history = task.evaluate_transition(state, task.task_state)
    assert reached and failure is None and history["traversal_complete"]
    assert not metrics["traversal_tracked"] and metrics["finish_angle_deg"] < 1e-8
    # Identical finish pose without traversal history must never qualify.
    fresh = task.initial_task_state(state)
    assert not task.evaluate_transition(state, fresh)[0]


def test_success_requires_full_settling_and_touch_still_wins(monkeypatch):
    from test_terminal_settling import geometry
    task, state = fixture(monkeypatch)
    geometry(state, ("wand",))
    task.initialize(state)
    for x in [-.49, -.25, 0., .25, .49]:
        state["physics_step"] += 1
        state["bodies"]["wand"]["position_m"][0] = x
        geometry(state, ("wand",))
        events(state, ("wand_handle", "finish_support"))
        task.update(state, .1)
    before = task.get_state()
    for _ in range(9):
        state["physics_step"] += 1
        geometry(state, ("wand",))
        events(state, ("wand_handle", "finish_support"))
        assert not task.update(state, .1).task_success
    state["physics_step"] += 1
    geometry(state, ("wand",))
    events(state, ("wand_handle", "finish_support"))
    assert task.update(state, .1).task_success
    task.set_state(before)
    state["physics_step"] = before["last_physics_step"]+1
    geometry(state, ("wand",))
    events(state, ("wand_handle", "finish_support"), ("wire_metal", "wand_metal"))
    result = task.update(state, .1)
    assert result.terminated and not result.task_success and result.reason == "wire_touched"
