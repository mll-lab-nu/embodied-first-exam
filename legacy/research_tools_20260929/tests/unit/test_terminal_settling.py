"""Synthetic post-release evidence, not demonstrations of physical task success."""
from copy import deepcopy
from types import SimpleNamespace
import numpy as np
import pytest
from scipy.spatial.transform import Rotation

from topogym.evaluation.terminal import SettlingSpec, evaluate_settling
from topogym.tasks.base import TaskDefinition
from terminal_fixtures import body, soft


def geometry(state, targets=("object",)):
    state["release_geometry"] = dict(schema_version=1, physics_step=state["physics_step"],
        complete=True, robot_present=True,
        robot_bounds_m=np.array([[[1., 1., 1.], [1.1, 1.1, 1.1]]]),
        target_bounds_m={name: np.array([[[-.01]*3, [.01]*3]]) for name in targets})
    return state


def state():
    return geometry(dict(physics_step=0, assist_active=False, bodies={"object": body()}, goal=True))


class ReleaseTask(TaskDefinition):
    task_id = "release_fixture"
    defaults = dict(stable_duration_s=.5)

    def final_settling_spec(self):
        return SettlingSpec(rigid_targets=("object",))

    def evaluate_state(self, state):
        return state["goal"], state.get("failure"), {}


def tick(task, s, dt=.1):
    s["physics_step"] += 1
    s["release_geometry"]["physics_step"] = s["physics_step"]
    return task.update(s, dt)


def test_confirmation_starts_after_release_and_clearance_not_close_command():
    task, s = ReleaseTask(), state()
    task.initialize(s)
    s["assist_active"] = True
    for _ in range(8):
        assert not tick(task, s).task_success
    s["assist_active"] = False
    far = s["release_geometry"]["robot_bounds_m"].copy()
    s["release_geometry"]["robot_bounds_m"][:] = [[[-.01]*3, [.01]*3]]
    for _ in range(8):
        assert not tick(task, s).task_success
    s["release_geometry"]["robot_bounds_m"] = far
    assert tick(task, s).metrics["stable_time_s"] == 0.
    for _ in range(4):
        assert not tick(task, s).task_success
    assert tick(task, s).task_success


@pytest.mark.parametrize("interruption", ["assist", "contact", "speed", "rotation", "drift", "goal", "coverage"])
def test_interruption_resets_window_and_rewind_restores_reference(interruption):
    task, s = ReleaseTask(), state()
    task.initialize(s)
    tick(task, s); tick(task, s); tick(task, s)
    checkpoint, before = task.get_state(), deepcopy(s)
    if interruption == "assist":
        s["assist_active"] = True
    elif interruption == "contact":
        s["release_geometry"]["robot_bounds_m"][:] = [[[-.01]*3, [.01]*3]]
    elif interruption == "speed":
        s["bodies"]["object"]["linear_velocity_m_s"][0] = .1
    elif interruption == "rotation":
        s["bodies"]["object"]["quaternion_wxyz"] = Rotation.from_euler("z", .1).as_quat()[[3,0,1,2]]
    elif interruption == "drift":
        s["bodies"]["object"]["position_m"][0] = .002
    elif interruption == "goal":
        s["goal"] = False
    else:
        s["release_geometry"]["complete"] = False
    result = tick(task, s)
    assert not result.task_success and result.metrics["stable_time_s"] == 0
    assert task.get_state()["final_settling"]["reference"] is None
    task.set_state(checkpoint)
    s = before
    assert not tick(task, s).task_success
    assert not tick(task, s).task_success
    assert tick(task, s).task_success


def test_read_and_repeated_tick_do_not_advance_and_failures_take_priority():
    task, s = ReleaseTask(), state()
    task.initialize(s)
    tick(task, s)
    for _ in range(8):
        task.observe(); task.evaluate_state(s); task.update(s, .1)
    assert task.stable_time_s == 0.
    s["failure"] = "broken"
    del s["release_geometry"]["target_bounds_m"]
    result = tick(task, s)
    assert result.terminated and not result.task_success and result.reason == "broken"


@pytest.mark.parametrize("field", ["assist_active", "release_geometry"])
def test_missing_evidence_is_unavailable(field):
    s = state(); del s[field]
    reached, metrics, reference = evaluate_settling(s, SettlingSpec(rigid_targets=("object",)))
    assert not reached and reference is None and metrics["evaluation_status"] == "unavailable"


def test_stale_or_nonfinite_evidence_raises_without_committing():
    task, s = ReleaseTask(), state()
    task.initialize(s); tick(task, s)
    before = task.get_state()
    s["physics_step"] += 1
    with pytest.raises(ValueError, match="Stale"):
        task.update(s, .1)
    assert task.last_physics_step == before["last_physics_step"]
    s["release_geometry"]["physics_step"] = s["physics_step"]
    s["release_geometry"]["robot_bounds_m"][0,0,0] = np.nan
    with pytest.raises(ValueError, match="bounds"):
        task.update(s, .1)
    assert task.stable_time_s == before["stable_time_s"]
    bad = deepcopy(before); del bad["final_settling"]
    with pytest.raises(ValueError, match="checkpoint"):
        task.set_state(bad)
    bad = deepcopy(before); bad["final_settling"]["reference"] = None
    with pytest.raises(ValueError, match="reference"):
        task.set_state(bad)


@pytest.mark.parametrize("group", ["fem", "particles"])
def test_soft_material_speed_drift_and_collision_radius(group):
    s = geometry(dict(physics_step=0, assist_active=False,
        **{group: {"cloth": soft([[0,0,0], [.02,0,0]])}}), ())
    spec = SettlingSpec(**{("fem_targets" if group == "fem" else "particle_targets"): ("cloth",)},
                        particle_radius_m=.01)
    ok, _, ref = evaluate_settling(s, spec)
    assert ok
    s[group]["cloth"]["position_m"][1,1] += .002
    assert not evaluate_settling(s, spec, ref)[0]
    s[group]["cloth"]["position_m"][1,1] = 0
    s[group]["cloth"]["velocity_m_s"][1,0] = .1
    assert not evaluate_settling(s, spec)[0]
    s[group]["cloth"]["velocity_m_s"][:] = 0
    s["release_geometry"]["robot_bounds_m"][:] = [[[.03,-.01,-.01], [.04,.01,.01]]]
    assert evaluate_settling(s, spec)[0] is (group == "fem")


def test_geometry_is_conservative_and_rotations_use_world_frame():
    from topogym.world.physics.release_geometry import ReleaseGeometry
    turn = Rotation.from_euler("z", 45, degrees=True)
    geom = SimpleNamespace(type=SimpleNamespace(name="BOX"), data=[.2,.4,.6], idx=7)
    entity = SimpleNamespace(links=[SimpleNamespace(geoms=[geom])])
    class Solver:
        def get_geoms_pos(self, indices, *, relative):
            assert indices == [7] and relative is False
            return np.array([[1.,2.,3.]])
        def get_geoms_quat(self, indices, *, relative):
            assert relative is False
            return turn.as_quat()[[3,0,1,2]][None]
    world = SimpleNamespace(entities={"object":entity}, physics_step=4,
                            scene=SimpleNamespace(sim=SimpleNamespace(rigid_solver=Solver())))
    result = ReleaseGeometry(world, ("object",)).read()
    assert result["complete"] and not result["robot_present"]
    half = np.abs(turn.as_matrix()) @ [.1,.2,.3]
    np.testing.assert_allclose(result["target_bounds_m"]["object"][0], [[1,2,3]-half, [1,2,3]+half])


def test_only_release_tasks_opt_in():
    from topogym.config.registry import task_catalog, task_definition
    expected = {"cast_coil", "buzz_wire_3d", "knot_untying", "blanket_flatten"}
    for entry in task_catalog():
        task = task_definition(entry["task_id"])()
        assert (task.final_settling_spec() is not None) == (task.task_id in expected)
