from types import SimpleNamespace
from copy import deepcopy
import numpy as np
import pytest
from scipy.spatial.transform import Rotation
from topogym.tasks.fiber_bundling.common import FiberBundlingTask
from terminal_fixtures import body


def contact_summary(step=0, events=()):
    return dict(schema_version=1, physics_step=step, substeps_complete=True,
        geometry_roles_complete=True, robot_geometry_complete=True,
        expected_substeps=0 if step == 0 else 4, sampled_substeps=0 if step == 0 else 4,
        sampling_scope="initial_pose" if step == 0 else "substeps", events=list(events))


def fixture(task_class=FiberBundlingTask):
    task = task_class()
    task.table_height_m = .75
    count = task.config["geometry"].get("fiber_count", 2)
    task.layout = SimpleNamespace(fiber_count=count,fiber_segments=2,fiber_length_m=.04,
        trunk_segments=2,trunk_length_m=.2,fiber_radius_m=.001,trunk_radius_m=.004,
        minimum_aperture_radius=.05,ring_tube_radius_m=.005)
    links = {f"fiber_{i:02d}_{j:02d}":body((-.1+j*.02,(i-count/2)*.002,.8)) for i in range(count) for j in range(2)}
    links["trunk_01"] = body((-.2,0,.8))
    q = Rotation.from_euler("y",90,degrees=True).as_quat()[[3,0,1,2]]
    state = dict(physics_step=0,articulations={"fiber_bundle":dict(links=links)},
        bodies={"bundling_ring":body((0,0,.8),q)},contact_events=contact_summary())
    return task,state


def move(state,x):
    for link in state["articulations"]["fiber_bundle"]["links"].values():
        link["position_m"][0] += x
    state["physics_step"] += 1
    state["contact_events"] = contact_summary(state["physics_step"])


def test_all_material_stations_pass_and_rewind_restores_progress():
    task,state = fixture()
    task.initialize(state)
    saved = task.get_state()
    saved_world = deepcopy(state)
    move(state,.2)
    task.update(state,.01)
    assert task.evaluate_state(state)[0]
    assert all(np.all(s["stages"] == 2) for s in task.task_state["strands"])
    task.set_state(saved)
    assert not task.evaluate_state(saved_world)[0]  # World and Task rewind to the same tick.
    assert all(np.all(s["stages"] == 0) for s in task.task_state["strands"])


def test_exit_retry_and_outside_bypass():
    task,state = fixture()
    task.initialize(state)
    move(state,.2); task.update(state,.01)
    move(state,-.2); task.update(state,.01)
    assert not task.evaluate_state(state)[0]
    move(state,.2); task.update(state,.01)
    assert task.evaluate_state(state)[0]
    task,state = fixture()
    for link in state["articulations"]["fiber_bundle"]["links"].values():
        link["position_m"][1] += .2
    task.initialize(state)
    move(state,.2); task.update(state,.01)
    assert not task.evaluate_state(state)[0]


def test_missing_strand_and_forged_history_rejected():
    task,state = fixture()
    task.initialize(state)
    saved = task.get_state()
    saved["task_state"]["strands"].pop()
    with pytest.raises(ValueError,match="strand count"):
        task.set_state(saved)
    assert len(task.task_state["strands"]) == 2
    del state["articulations"]["fiber_bundle"]["links"]["fiber_01_01"]
    with pytest.raises(KeyError):
        task.evaluate_state(state)


def test_large_bend_prevents_success_without_damage_failure():
    task,state = fixture()
    task.initialize(state)
    move(state,.2)
    link = state["articulations"]["fiber_bundle"]["links"]["fiber_00_01"]
    link["quaternion_wxyz"] = Rotation.from_euler("y",100,degrees=True).as_quat()[[3,0,1,2]]
    reached,failure,metrics,_ = task.evaluate_transition(state,deepcopy(task.task_state))
    assert not reached and failure is None and metrics["maximum_bend_deg"] > 60


@pytest.mark.parametrize("variation", ["base", "fiber_bundling_easy", "fiber_bundling_medium", "fiber_bundling_hard"])
def test_enabled_success_and_rewind_across_termination(variation):
    from topogym.config.registry import task_definition, require_task_support
    from topogym.simulator.interaction import public_info
    cls = task_definition("fiber_bundling", variation)
    require_task_support("fiber_bundling", "solve", variation)
    task, state = fixture(cls)
    task.initialize(state)
    birth, world_birth = task.get_state(), deepcopy(state)
    for tick in range(1, 7):
        move(state, .2 if tick == 1 else 0)
        result = task.update(state, .1)
        assert result.task_success == (tick == 6)
    assert result.terminated and result.reward == 1 and result.evaluation_status == "available"
    info = public_info(dict(goal_evaluation_complete=task.goal_complete,
        task_success=result.task_success, task_terminated=result.terminated,
        evaluation_status=result.evaluation_status, termination_reason=result.reason))
    assert info["task_outcome"] == "success" and info["task_success"] is True
    assert result.metrics["goal_evaluation_complete"] is True
    assert not result.metrics["thresholds_calibrated"]
    won = task.get_state()
    task.set_state(birth)
    assert not task.result.terminated and not task.evaluate_state(world_birth)[0]
    task.set_state(won)
    move(state, -.2)
    assert task.update(state, .1).task_success  # A saved terminal stays terminal.


@pytest.mark.parametrize("case", ["one_strand", "tips_only", "reverse", "bypass", "bend"])
def test_incomplete_or_wrong_passage_never_terminates_successfully(case):
    task, state = fixture()
    if case == "reverse":
        move(state, .2)
        state["physics_step"], state["contact_events"] = 0, contact_summary()
    if case == "bypass":
        for link in state["articulations"]["fiber_bundle"]["links"].values():
            link["position_m"][1] += .2
    task.initialize(state)
    move(state, -.2 if case == "reverse" else .07 if case == "tips_only" else .2)
    links = state["articulations"]["fiber_bundle"]["links"]
    if case == "one_strand":
        for name, link in links.items():
            if name.startswith("fiber_01_"):
                link["position_m"][0] -= .2
    if case == "bend":
        links["fiber_00_01"]["quaternion_wxyz"] = Rotation.from_euler("y",100,degrees=True).as_quat()[[3,0,1,2]]
    for tick in range(8):
        if tick:
            move(state, 0)
        result = task.update(state, .1)
        assert not result.terminated and not result.task_success


def shift_strands(state, y):
    for name, link in state["articulations"]["fiber_bundle"]["links"].items():
        if name.startswith("fiber_"):
            link["position_m"][1] = y


def settle(task, state, ticks=7):
    for _ in range(ticks):
        move(state, 0)
        result = task.update(state, .1)
        if result.terminated:
            break
    return result


def test_strand_guided_in_by_the_ring_front_counts():
    # The tip crosses the old entry plane (6 mm before the ring plane) 52 mm off
    # axis, beyond the old 48.9 mm limit but inside the tube centreline (55 mm),
    # then reaches the ring plane in the hole: a real passage, formerly rejected.
    task, state = fixture()
    shift_strands(state, .052)
    task.initialize(state)
    move(state, .057)  # tip at 3 mm before the ring plane
    task.update(state, .1)
    shift_strands(state, .03)
    move(state, 0)
    task.update(state, .1)
    move(state, .2)
    task.update(state, .1)
    assert settle(task, state).task_success


def test_ring_plane_crossing_outside_or_wrapping_back_never_counts():
    task, state = fixture()
    shift_strands(state, .06)  # beyond the tube centreline: outside the hole
    task.initialize(state)
    move(state, .2)
    task.update(state, .1)
    result = settle(task, state)
    assert not result.task_success and result.metrics["strands_complete"] == [False, False]
    task, state = fixture()
    task.initialize(state)
    move(state, .2)  # through the hole
    task.update(state, .1)
    shift_strands(state, .2)
    move(state, -.2)  # back to the entry side around the outside
    task.update(state, .1)
    move(state, .2)  # forward again outside the ring
    task.update(state, .1)
    result = settle(task, state)
    assert not result.task_success and not any(result.metrics["strands_complete"])


def touch(*, fiber_role="fiber_strand", part="gripper", reverse=False):
    event = dict(role_a="robot", role_b=fiber_role, robot_part_a=part,
                 robot_part_b=None, touching=True, substep=0, force_n=0., penetration_m=0.)
    if reverse:
        event["role_a"], event["role_b"] = event["role_b"], event["role_a"]
        event["robot_part_a"], event["robot_part_b"] = event["robot_part_b"], event["robot_part_a"]
    return event


@pytest.mark.parametrize("reverse", [False, True])
def test_zero_force_transient_gripper_contact_beats_success_and_rewinds(reverse):
    task, state = fixture()
    task.initialize(state)
    for tick in range(1, 6):
        move(state, .2 if tick == 1 else 0)
        task.update(state, .1)
    before, world_before = task.get_state(), deepcopy(state)
    move(state, 0)
    state["contact_events"]["events"] = [touch(reverse=reverse)]
    # Observed violations remain conclusive even when other substeps were missed.
    state["contact_events"].update(substeps_complete=False, sampled_substeps=1)
    result = task.update(state, .1)
    assert result.terminated and not result.task_success and result.evaluation_status == "available"
    assert result.reason == "fiber_gripper_contact" and result.reward == 0
    failed = task.get_state()
    move(state, 0)
    assert task.update(state, .1) == result
    task.set_state(before)
    move(world_before, 0)
    assert task.update(world_before, .1).task_success
    task.set_state(failed)
    assert task.result.reason == "fiber_gripper_contact"


@pytest.mark.parametrize("event", [touch(fiber_role="fiber_sheath"), touch(part="arm")])
def test_sheath_grasp_and_arm_contact_are_not_gripper_strand_violations(event):
    task, state = fixture()
    task.initialize(state)
    for tick in range(1, 7):
        move(state, .2 if tick == 1 else 0)
        state["contact_events"]["events"] = [event]
        result = task.update(state, .1)
    assert result.task_success


@pytest.mark.parametrize("missing", ["summary", "substeps", "geometry", "robot", "classification"])
def test_missing_contact_coverage_stays_unavailable_until_rewind(missing):
    task, state = fixture()
    task.initialize(state)
    birth, world_birth = task.get_state(), deepcopy(state)
    move(state, .2)
    summary = state["contact_events"]
    if missing == "summary":
        state.pop("contact_events")
    elif missing == "substeps":
        summary.update(substeps_complete=False, sampled_substeps=3)
    elif missing == "geometry":
        summary["geometry_roles_complete"] = False
    elif missing == "robot":
        summary["robot_geometry_complete"] = False
    else:
        summary["events"] = [touch(part=None)]
    task.update(state, .1)
    for _ in range(7):
        move(state, 0)
        result = task.update(state, .1)
        assert result.evaluation_status == "unavailable" and not result.terminated
        assert not task.task_state["contact_coverage_complete"] and task.stable_time_s == 0
    task.set_state(birth)
    assert task.task_state["contact_coverage_complete"]
    for tick in range(1, 7):
        move(world_birth, .2 if tick == 1 else 0)
        result = task.update(world_birth, .1)
    assert result.task_success


def test_birth_contact_and_invalid_contact_checkpoints_are_rejected():
    task, state = fixture()
    state["contact_events"]["events"] = [touch()]
    with pytest.raises(ValueError, match="fiber_gripper_contact"):
        task.initialize(state)
    state["contact_events"] = contact_summary()
    task.initialize(state)
    saved = task.get_state()
    saved["task_state"]["contact_coverage_complete"] = 1
    with pytest.raises(ValueError, match="contact coverage"):
        task.set_state(saved)
    assert task.task_state["contact_coverage_complete"] is True


@pytest.mark.parametrize("key,value", [("physics_step",99), ("schema_version",2), ("sampled_substeps",5)])
def test_stale_or_malformed_contact_summary_does_not_commit(key, value):
    task, state = fixture()
    task.initialize(state)
    move(state, .2)
    state["contact_events"][key] = value
    with pytest.raises(ValueError, match="contact"):
        task.update(state, .1)
    assert task.last_physics_step == 0 and task.stable_time_s == 0


@pytest.mark.parametrize("variation,count", [("fiber_bundling_easy",4), ("fiber_bundling_medium",8), ("fiber_bundling_hard",16)])
def test_real_declared_assets_have_complete_strand_roles_and_consistent_metadata(tmp_path, variation, count):
    import xml.etree.ElementTree as ET
    from topogym.config.registry import task_definition
    task = task_definition("fiber_bundling", variation)(seed=0)
    spec = task.declare(tmp_path, .75)
    assert spec.metadata["goal_evaluation_complete"] is True
    assert task.terminal_metadata()["goal_complete"] is True
    assert task.terminal_revision == "terminal_v4_fiber_ring_plane"
    entity = next(e for e in spec.entities if e.name == "fiber_bundle")
    strands = {name for name,role in entity.contact_roles.items() if role == "fiber_strand"}
    assert strands == {f"fiber_surface_{i:02d}_{j:02d}" for i in range(count) for j in range(task.layout.fiber_segments)}
    root = ET.parse(entity.asset_path).getroot()
    collisions = {geom.get("name") for geom in root.findall(".//worldbody//geom")
                  if int(geom.get("contype","1")) or int(geom.get("conaffinity","1"))}
    assert set(entity.contact_roles) == collisions
    assert all(not name.startswith(("insulation_","copper_")) for name in entity.contact_roles)


@pytest.mark.parametrize("violation", [False,True])
def test_fiber_terminal_propagates_through_env_and_stops_remaining_ticks(local_env, monkeypatch, violation):
    """Real Fiber/Env/Interaction/history code with synthetic world measurements."""
    from dataclasses import replace
    from topogym.tasks.base import TaskSpec, merge_parameters
    template, initial = fixture()

    class Fiber(FiberBundlingTask):
        defaults = merge_parameters(FiberBundlingTask.defaults, {"stable_duration_s":.02})
        def declare(self, asset_dir, table_height_m):
            self.layout, self.table_height_m = template.layout, .75
            return TaskSpec(())

    world_cls = type(local_env._world)
    original = world_cls.read_state
    def read(world):
        state = deepcopy(initial)
        if world.physics_step:
            move(state,.2)
        state.update(original(world))
        state["contact_events"] = contact_summary(world.physics_step,
            [touch()] if violation and world.physics_step == 3 else [])
        return state
    monkeypatch.setattr(world_cls,"read_state",read)
    local_env._task_class = Fiber
    local_env._config = replace(local_env.config,control_decimation=10)
    local_env.reset(seed=0)
    anchor = local_env.state_history[0].ref
    actor = local_env.interaction()
    _,reward,done,truncated,info = actor.step({"target":0.})
    assert done and not truncated and info["physics_steps"] == 3
    assert reward == int(not violation) and info["task_success"] == (not violation)
    assert info["task_outcome"] == ("failure" if violation else "success")
    if violation:
        assert info["failure_code"] == "task_failed"
    _,info = local_env.privileged.rewind_to(anchor)
    assert not info["task_terminated"] and local_env._world.physics_step == 0
    assert local_env._task.task_state["contact_coverage_complete"]
