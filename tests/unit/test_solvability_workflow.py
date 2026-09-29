"""Cache invalidation and qualification gates, using the actual segment loop."""
from copy import deepcopy
from dataclasses import replace
import json

import numpy as np
import pytest

from topogym.planning.base import ActionSequencePolicy
from topogym.planning.solvability import PathCache, QualificationWorkflow, Stage, Step, identity_for
from topogym.simulator import SegmentRunner
from topogym.tasks.base import TaskResult


@pytest.fixture
def managed(local_env, monkeypatch, tmp_path):
    spec = dict(robot_id="fixture", mode="JOINT_ABS", arms=["arm"], groups={"arm": dict(
        arm_joint_names=["joint"], gripper_field="gripper_position_m", gripper_limits=[0., .04])})
    monkeypatch.setattr(type(local_env), "action_spec", property(lambda self: spec))
    original = local_env._robot.observe

    def observe():
        values = original()
        values["arm"].update(tcp_position_world_m=np.array([local_env._world.position, 0., 0.]),
                            tcp_orientation_wxyz=np.array([1., 0., 0., 0.]),
                            finger_position_m=np.array([.01, .01]))
        return values

    monkeypatch.setattr(local_env._robot, "observe", observe)
    local_env._sensors.invalidate()
    with SegmentRunner(local_env, tmp_path / "trail") as runner:
        yield runner


def stage(**changes):
    base = Stage("window", "interaction", {"actions": 2},
                 lambda tick: ActionSequencePolicy([{"target": 1.}, {"target": 1.}]),
                 lambda tick: {"entry": True}, lambda tick: {"invariant": True},
                 lambda tick: {"exit": True}, .1)
    return replace(base, **changes)


def workflow(managed, tmp_path, mode="diagnostic"):
    return QualificationWorkflow(managed, tmp_path / "qualification", identity_for(managed), mode=mode)


def test_cache_reuses_only_identical_state_and_detects_corruption(managed, tmp_path):
    cache = PathCache(tmp_path / "cache", identity_for(managed))
    measured = {"world": {"finger_velocity": 0.}, "robot": {"q": [0.]}}
    calls = []

    def build():
        calls.append(1)
        return {"anchors": [0, 1]}

    plan, cold = cache.plan({"gap": .001}, measured, build)
    assert not cold['cache_hit']
    assert cache.plan({"gap": .001}, measured, build)[1]['cache_hit']
    moved = deepcopy(measured)
    moved['world']['finger_velocity'] = .01
    assert not cache.plan({"gap": .001}, moved, build)[1]['cache_hit']
    assert not cache.plan({"gap": .002}, measured, build)[1]['cache_hit']
    assert len(calls) == 3
    path = cache.root / (cold['key'] + '.json')
    record = json.loads(path.read_text())
    record['plan']['anchors'] = [0, 2]
    path.write_text(json.dumps(record))
    with pytest.raises(ValueError, match='Changed path-cache'):
        cache.plan({"gap": .001}, measured, build)


def test_failed_planning_is_not_cached(managed, tmp_path):
    cache = PathCache(tmp_path / 'cache', identity_for(managed))
    with pytest.raises(RuntimeError):
        cache.plan({}, {'world': {'x': 1}, 'robot': {'q': 1}},
                   lambda: (_ for _ in ()).throw(RuntimeError('no path')))
    assert not list(cache.root.glob('*.json'))


def test_handoff_uses_actual_final_state_and_monitors_every_physics_tick(managed, tmp_path):
    flow = workflow(managed, tmp_path)
    starts = []

    def build(tick):
        starts.append(tick['state']['physics_step'])
        return ActionSequencePolicy([{'target': 1.}])

    first = flow.run(stage(build_policy=build))
    second = flow.run(stage(build_policy=build))
    assert starts == [0, 3]
    assert first['checked_physics_ticks'] == second['checked_physics_ticks'] == 3
    report = flow.finish()
    assert report['status'] == 'local_windows_passed'
    assert not report['accepted_proof'] and not report['native_task_success']


def test_transient_failure_between_control_observations_is_latched_and_rewindable(managed, tmp_path):
    flow = workflow(managed, tmp_path)
    birth = dict(episode_id=flow.episode, state_id=0)
    with pytest.raises(ValueError, match='transient_contact'):
        flow.run(stage(invariant=lambda tick: {'transient_contact': tick['state']['physics_step'] != 1}))
    assert flow.report['stages'][0]['checked_physics_ticks'] == 3
    assert not managed.env._faulted
    flow.rewind(birth)
    assert managed.env.tick_record()['state']['branch_id'] == 1
    assert flow.run(stage())['passed']
    assert flow.finish()['status'] == 'local_windows_passed'
    assert not flow.report['accepted_proof']


def test_invalid_entry_cannot_run_actions(managed, tmp_path):
    flow = workflow(managed, tmp_path)
    with pytest.raises(ValueError, match='booleans'):
        flow.run(stage(entry=lambda tick: {'missing_contact_evidence': None}))
    assert managed.env.tick_record()['state']['physics_step'] == 0


def test_local_budget_failure_is_not_success(managed, tmp_path):
    flow = workflow(managed, tmp_path)
    with pytest.raises(ValueError, match='stage_time_budget'):
        flow.run(stage(max_simulation_s=.02))
    assert flow.finish()['status'] == 'incomplete'


def test_proof_rejects_rewinds_and_unmonitored_handoffs(managed, tmp_path):
    flow = workflow(managed, tmp_path, mode='proof')
    with pytest.raises(ValueError, match='unavailable'):
        flow.rewind(dict(episode_id=flow.episode, state_id=0))
    flow.run(stage(build_policy=lambda tick: ActionSequencePolicy([{'target': 1.}])))
    managed.interaction().run_segment(request_id='outside', actions=[{'target': 1.}])
    with pytest.raises(ValueError, match='Unmonitored'):
        flow.run(stage())
    assert flow.finish()['status'] == 'incomplete'


@pytest.mark.parametrize('mode,rewound,expected', [
    ('diagnostic', False, 'native_success_pending_independent_audit'),
    ('diagnostic', True, 'local_windows_passed'),
    ('proof', False, 'native_success_pending_independent_audit')])
def test_native_success_alone_never_grants_a_proof(managed, tmp_path, monkeypatch, mode, rewound, expected):
    def success(state, dt):
        managed.env._task.result = TaskResult(task_success=True, terminated=True)
        return managed.env._task.result
    monkeypatch.setattr(managed.env._task, 'update', success)
    flow = workflow(managed, tmp_path, mode=mode)
    if rewound:
        flow.run(stage(build_policy=lambda tick: ActionSequencePolicy([{'target': 1.}])))
        flow.rewind(dict(episode_id=flow.episode, state_id=0))
    flow.run(stage())
    assert flow.finish()['status'] == expected
    assert flow.report['continuous_from_birth'] is not rewound
    assert flow.report['native_task_success'] and not flow.report['accepted_proof']


def step(*candidates):
    # Candidate "budget" is the stage time limit; 0.02 s fails after two ticks.
    return Step('window', candidates, lambda parameters: stage(
        definition={'parameters': dict(parameters, planned=True)}, max_simulation_s=parameters['budget'],
        build_policy=lambda tick: ActionSequencePolicy([{'target': 1.}])))


def test_failed_candidate_rewinds_to_step_start_and_next_candidate_continues(managed, tmp_path):
    flow = workflow(managed, tmp_path)
    flow.run_step(step({'budget': .1}))
    record = flow.run_step(step({'budget': .02}, {'budget': .1}))
    assert record['start']['physics_step'] == 3 and record['start']['branch_id'] == 1
    assert [row['parameters'] for row in record['failed_candidates']] == [{'budget': .02}]
    assert flow.report['chain'] == [0, 2]
    assert flow.finish()['status'] == 'local_windows_passed' and not flow.report['continuous_from_birth']
    selection = json.loads((tmp_path / 'qualification' / 'selection.json').read_text())
    assert [row['parameters'] for row in selection] == [{'budget': .1, 'planned': True}] * 2


def test_exhausted_candidates_wait_for_new_parameters(managed, tmp_path):
    flow = workflow(managed, tmp_path)
    offered = []

    def wait(current, start, tried):
        offered.append((start['physics_step'], len(tried)))
        return {'budget': .1} if len(offered) == 1 else None

    assert flow.run_step(step({'budget': .02}), wait=wait)['parameters'] == {'budget': .1, 'planned': True}
    assert offered == [(0, 1)]
    with pytest.raises(ValueError, match='every candidate'):
        flow.run_step(step({'budget': .02}), wait=wait)
    assert flow.report['chain'] == [1]


def test_planning_rejection_before_physics_keeps_continuity(managed, tmp_path, monkeypatch):
    def success(state, dt):
        managed.env._task.result = TaskResult(task_success=True, terminated=True)
        return managed.env._task.result
    monkeypatch.setattr(managed.env._task, 'update', success)
    flow = workflow(managed, tmp_path)

    def build(parameters):
        if parameters['path'] == 'blocked':
            raise ValueError('no collision-free path')
        return stage()

    flow.run_step(Step('window', ({'path': 'blocked'}, {'path': 'open'}), build))
    assert not flow.report['rewinds']
    assert flow.finish()['status'] == 'native_success_pending_independent_audit'


def test_proof_step_does_not_retry(managed, tmp_path):
    flow = workflow(managed, tmp_path, mode='proof')
    with pytest.raises(ValueError, match='stage_time_budget'):
        flow.run_step(step({'budget': .02}, {'budget': .1}), wait=lambda *args: {'budget': .1})
    assert not flow.report['rewinds'] and flow.finish()['status'] == 'incomplete'


def test_wrong_configuration_identity_is_rejected(managed, tmp_path):
    identity = identity_for(managed)
    identity['config_sha256'] = '0' * 64
    with pytest.raises(ValueError, match='identity differs'):
        QualificationWorkflow(managed, tmp_path / 'bad', identity)


def test_operator_abort_fails_the_running_stage_and_is_cleared_after_rewind(managed, tmp_path):
    abort = tmp_path / 'abort'
    flow = QualificationWorkflow(managed, tmp_path / 'qualification', identity_for(managed), abort_file=abort)

    def build(parameters):
        if parameters['abort']:
            abort.touch()
        return stage(build_policy=lambda tick: ActionSequencePolicy([{'target': 1.}]))

    record = flow.run_step(Step('window', ({'abort': True}, {'abort': False}), build))
    assert 'operator_abort' in record['failed_candidates'][0]['error']
    assert record['passed'] and not abort.exists() and len(flow.report['rewinds']) == 1
