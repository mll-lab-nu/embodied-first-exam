"""Segments exercise the actual Env loop against the deterministic world fixture."""
from dataclasses import replace
from threading import Thread
import json

import pytest

from topogym.simulator import SegmentRunner
from topogym.simulator.rollout_simulation.segment_contract import SegmentError
from topogym.tasks.base import TaskResult


@pytest.fixture
def segment(local_env, tmp_path):
    with SegmentRunner(local_env, tmp_path / "trail") as runner:
        yield runner, runner.interaction()


def test_two_segments_preserve_ticks_and_log_every_tick(segment, local_env):
    runner, actor = segment
    assert actor.timing_spec["control_dt_s"] == .03
    with pytest.raises(TypeError):
        actor.timing_spec["control_dt_s"] = 1.
    actor.begin_segment(request_id="a")
    result = actor.step({"target": 1.})
    first = actor.end_segment()
    assert local_env._world.physics_step == 3
    assert first["physics_steps"] == 3
    assert actor.end_segment() == first
    actor.observe()
    assert local_env._world.physics_step == 3
    actor.begin_segment(request_id="b")
    actor.step({"target": 2.})
    second = actor.end_segment()
    assert first["end_state_ref"] == second["start_state_ref"]
    assert second["physics_steps"] == 3
    rows = [json.loads(s) for s in (runner.root / "private/physics_states.jsonl").read_text().splitlines()]
    assert [r["state"]["physics_step"] for r in rows] == list(range(7))
    assert [r["segment_id"] for r in rows] == [0, 1, 1, 1, 2, 2, 2]
    assert "seed" not in result[4] and "support" not in result[4]
    assert "executed_joint_targets" not in result[4]


def test_terminal_on_third_tick_stops_remaining_actions(local_env, tmp_path):
    local_env._config = replace(local_env.config, control_decimation=10)
    def update(state, dt):
        local_env._task.result = TaskResult(terminated=state["physics_step"] == 3,
                                             reason="private termination detail")
        return local_env._task.result
    local_env._task.update = update
    with SegmentRunner(local_env, tmp_path / "terminal") as runner:
        actor = runner.interaction()
        result = actor.run_segment(request_id="terminal", actions=[{"target": 1.}] * 4)
        assert result["physics_steps"] == 3
        assert result["control_steps"] == 1
        assert result["reason"] == "env_terminal"
        assert result["feedback"]["termination_reason"] == "task_terminal"
        assert local_env._world.physics_step == 3
        assert actor.run_segment(request_id="terminal", actions=[{"target": 1.}] * 4) == result


def test_batch_and_sequence_idempotence(segment, local_env):
    runner, actor = segment
    actor.begin_segment(request_id="stream")
    first = actor.step({"target": 1.}, sequence=0)
    assert actor.step({"target": 1.}, sequence=0) is first
    with pytest.raises(SegmentError, match="conflict"):
        actor.step({"target": 2.}, sequence=0)
    assert local_env._world.physics_step == 3
    actor.end_segment()
    result = actor.run_segment(request_id="batch", actions=[{"target": 2.}])
    assert actor.run_segment(request_id="batch", actions=[{"target": 2.}]) == result
    with pytest.raises(SegmentError, match="conflict"):
        actor.run_segment(request_id="batch", actions=[{"target": 3.}])
    assert local_env._world.physics_step == 6


def test_empty_segment_does_not_advance(segment, local_env):
    _, actor = segment
    result = actor.run_segment(request_id="empty", actions=[])
    assert result["start_state_ref"] == result["end_state_ref"]
    assert result["physics_steps"] == result["control_steps"] == 0
    assert local_env._world.physics_step == 0


def test_invalid_action_preserves_prefix_and_allows_new_segment(segment, local_env):
    _, actor = segment
    actor.begin_segment(request_id="invalid")
    actor.step({"target": 1.})
    with pytest.raises(SegmentError, match="invalid_action"):
        actor.step({"secret_path": 1.})
    result = actor.end_segment()
    assert result["control_steps"] == 1
    assert result["reason"] == "invalid_action"
    assert not local_env._faulted
    assert actor.run_segment(request_id="next", actions=[])["start_state_ref"] == result["end_state_ref"]


def test_fault_keeps_saved_prefix_and_never_observes_faulted_env(segment, local_env, monkeypatch):
    runner, actor = segment
    original = local_env._world.advance
    def fail():
        if local_env._world.physics_step == 2:
            raise OSError("sensitive /internal/path")
        original()
    monkeypatch.setattr(local_env._world, "advance", fail)
    actor.begin_segment(request_id="fault")
    with pytest.raises(SegmentError, match="^env_error$"):
        actor.step({"target": 1.})
    result = actor.end_segment()
    assert result["physics_steps"] == 2
    assert result["status"] == "incomplete"
    assert "/internal/path" not in str(result)
    assert len((runner.root / "private/physics_states.jsonl").read_text().splitlines()) == 3
    with pytest.raises(SegmentError, match="faulted"):
        actor.begin_segment(request_id="later")


def test_owner_reset_finalizes_and_expires_old_runner(segment, local_env):
    runner, actor = segment
    actor.begin_segment(request_id="reset")
    actor.step({"target": 1.})
    local_env.reset(seed=8)
    report = json.loads((runner.root / "report.json").read_text())
    assert report["segments"][-1]["result"]["reason"] == "cancelled"
    with pytest.raises(SegmentError, match="expired"):
        actor.observe()


def test_rewind_preserves_audit_and_new_branch(segment, local_env):
    runner, actor = segment
    access = runner.interaction(privileged=True)
    initial = actor.initial["state_ref"]
    actor.begin_segment(request_id="before")
    with pytest.raises(SegmentError, match="End the active"):
        access.rewind_to(initial)
    actor.step({"target": 1.})
    first = actor.end_segment()
    access.rewind_to(initial)
    after = actor.run_segment(request_id="after", actions=[{"target": 2.}])
    assert after["branch_id"] != first["branch_id"]
    assert after["end_state_ref"]["state_id"] > first["end_state_ref"]["state_id"]
    assert access.get_log(1, "history_events")[0]["kind"] == "rewind"


def test_outside_step_and_reentrant_callback_cannot_advance(segment, local_env):
    _, actor = segment
    actor.begin_segment(request_id="guard")
    with pytest.raises(SegmentError, match="active segment"):
        local_env.step({"target": 1.})
    errors = []
    def callback(record):
        for operation in (lambda: local_env.step({"target": 99.}), local_env.close):
            try:
                operation()
            except RuntimeError as error:
                errors.append(str(error))
        with pytest.raises(TypeError):
            record["world"]["position"] = 99.
    remove = local_env.add_state_sink(callback)
    actor.step({"target": 1.})
    remove()
    assert len(errors) == 6
    assert local_env._world.physics_step == 3


def test_nonfinite_batch_fails_before_begin(segment, local_env):
    runner, actor = segment
    with pytest.raises(ValueError):
        actor.run_segment(request_id="bad", actions=[{"target": 1.}, {"target": float("nan")}])
    assert local_env._world.physics_step == 0
    assert set(runner._records) == {0}


def test_environment_limit_is_not_segment_limit(segment, local_env):
    _, actor = segment
    result = actor.run_segment(request_id="long", actions=[{"target": 1.}] * 10)
    assert result["reason"] == "env_time_limit"
    assert result["control_steps"] == 4
    assert local_env._world.physics_step == 12


def test_static_bad_late_action_has_no_side_effects(segment, local_env):
    runner, actor = segment
    with pytest.raises(ValueError):
        actor.run_segment(request_id="bad_fields", actions=[{"target": 1.}, {"unknown": 2.}])
    assert set(runner._records) == {0}
    assert local_env._world.physics_step == 0


def test_state_sink_failure_is_not_a_complete_segment(segment, local_env, monkeypatch):
    runner, actor = segment
    original = runner._evidence.tick
    def fail(record, *, segment_id):
        if record["state"]["physics_step"] == 2:
            from topogym.simulator.rollout_simulation.evidence import EvidenceError
            raise EvidenceError("disk full")
        original(record, segment_id=segment_id)
    monkeypatch.setattr(runner._evidence, "tick", fail)
    actor.begin_segment(request_id="disk")
    with pytest.raises(SegmentError, match="evidence_error"):
        actor.step({"target": 1.})
    result = actor.end_segment()
    assert not result["evidence_complete"]
    assert len(local_env.state_history) == 3
    assert len((runner.root / "private/physics_states.jsonl").read_text().splitlines()) == 2


def test_repeated_terminal_sequence_is_read_only(segment, local_env):
    _, actor = segment
    actor.begin_segment(request_id="last")
    for i in range(4):
        result = actor.step({"target": 1.}, sequence=i)
    assert result[3]
    assert actor.step({"target": 1.}, sequence=3) is result
    assert local_env._world.physics_step == 12


def test_concurrent_begin_rejected_while_step_is_running(segment, local_env, monkeypatch):
    from threading import Event
    runner, actor = segment
    entered, release = Event(), Event()
    original = local_env._world.advance
    def delayed():
        entered.set()
        assert release.wait(5)
        original()
    monkeypatch.setattr(local_env._world, "advance", delayed)
    actor.begin_segment(request_id="thread")
    errors = []
    def run():
        try:
            actor.step({"target": 1.})
        except Exception as error:
            errors.append(error)
    worker = Thread(target=run)
    worker.start()
    try:
        assert entered.wait(5)
        with pytest.raises(SegmentError, match="busy"):
            runner.interaction().begin_segment(request_id="other")
    finally:
        release.set()
        worker.join(5)
    assert not errors and not worker.is_alive()


def test_zero_step_segment_after_rewind_uses_restored_state(segment):
    runner, actor = segment
    initial = actor.initial["state_ref"]
    actor.run_segment(request_id="before", actions=[{"target": 1.}])
    runner.interaction(privileged=True).rewind_to(initial)
    result = actor.run_segment(request_id="empty_after", actions=[])
    assert result["start_state_ref"] == result["end_state_ref"] == initial
    assert result["physics_steps"] == 0


def test_failure_after_integration_distinguishes_actual_clock_from_saved_prefix(segment, local_env, monkeypatch):
    runner, actor = segment
    def fail(*args, **kwargs):
        raise OSError("task failed after physics")
    monkeypatch.setattr(local_env._task, "update", fail)
    actor.begin_segment(request_id="after_integration")
    with pytest.raises(SegmentError, match="env_error"):
        actor.step({"target": 1.})
    result = actor.end_segment()
    assert result["physics_steps"] == 1
    assert result["saved_physics_steps"] == 0
    assert result["uncheckpointed_physics_steps"] == 1
    assert result["start_state_ref"] == result["end_state_ref"]
    assert not result["evidence_complete"]


def test_reset_during_runner_attachment_does_not_bind_old_episode(local_env, tmp_path, monkeypatch):
    original = local_env.interaction
    def reset_before_attachment(*args, **kwargs):
        access = original(*args, **kwargs)
        local_env.reset(seed=9)
        return access
    monkeypatch.setattr(local_env, "interaction", reset_before_attachment)
    with pytest.raises(SegmentError, match="episode_expired"):
        SegmentRunner(local_env, tmp_path / "raced")
    assert local_env._execution_guard is None
    assert not local_env._faulted


def test_manager_mutations_during_finalize_are_rejected_without_fault(segment, local_env, monkeypatch):
    runner, actor = segment
    actor.begin_segment(request_id="finalizing")
    original = runner._save_report
    def attempt_mutations():
        for operation in (local_env.close, lambda: local_env.reset(seed=9)):
            with pytest.raises(SegmentError, match="execution_busy"):
                operation()
        assert not local_env._faulted
        original()
    monkeypatch.setattr(runner, "_save_report", attempt_mutations)
    assert actor.end_segment()["evidence_complete"]
    monkeypatch.setattr(runner, "_save_report", original)
    assert actor.run_segment(request_id="still_usable", actions=[{"target": 1.}])["physics_steps"] == 3


def test_manager_reset_reserves_runner_through_rebuild(segment, local_env, monkeypatch):
    runner, actor = segment
    original = local_env._release_world
    def check_then_release():
        # The old runner has detached but its mutation reservation still spans
        # the rebuild; a stale operation cannot enter after an earlier check.
        assert runner._lock.locked()
        with pytest.raises(SegmentError, match="expired"):
            actor.begin_segment(request_id="during_reset")
        original()
    monkeypatch.setattr(local_env, "_release_world", check_then_release)
    local_env.reset(seed=10)
    monkeypatch.setattr(local_env, "_release_world", original)
    assert not runner._lock.locked()


def test_owner_report_failure_does_not_publish_complete_segment(segment, monkeypatch):
    runner, actor = segment
    actor.begin_segment(request_id="report_failure")
    actor.step({"target": 1.})
    original = runner._save_report
    def fail():
        raise OSError("owner report disk failure")
    monkeypatch.setattr(runner, "_save_report", fail)
    result = actor.end_segment()
    assert not result["evidence_complete"]
    manifest = json.loads((runner.root / "segments/segment_1/result.json").read_text())
    assert manifest["status"] == "incomplete" and not manifest["evidence_complete"]
    with pytest.raises(SegmentError, match="runner_faulted"):
        actor.begin_segment(request_id="blocked")
    monkeypatch.setattr(runner, "_save_report", original)


def test_contact_summary_failure_and_tick_evidence_share_one_state(local_env,tmp_path,monkeypatch):
    """Inject deterministic measured events; use the actual Task/Env/segment chain."""
    local_env._config=replace(local_env.config,control_decimation=10)
    local_env._task.goal_complete=False
    original=local_env._world.read_state
    def read():
        state=original()
        event=dict(role_a='wand_metal',role_b='wire_metal',touching=True,substep=0,force_n=0.)
        state['contact_events']=dict(schema_version=1,physics_step=state['physics_step'],
            substeps_complete=True,geometry_roles_complete=True,
            events=[event] if state['physics_step']==3 else [])
        return state
    monkeypatch.setattr(local_env._world,'read_state',read)
    def evaluate(state):
        events=state['contact_events']['events']
        return False,'wire_touched' if events else None,{'contact_events':events}
    local_env._task.evaluate_state=evaluate
    anchor=local_env.state_history[0].ref
    with SegmentRunner(local_env,tmp_path/'contact_evidence') as runner:
        actor=runner.interaction()
        result=actor.run_segment(request_id='touch',actions=[{'target':1.}]*3)
        assert result['physics_steps']==3 and result['feedback']['task_outcome']=='failure'
        assert result['feedback']['failure_code']=='wire_touched'
        rows=[json.loads(s) for s in (runner.root/'private/physics_states.jsonl').read_text().splitlines()]
        failure=rows[-1]
        assert failure['state']['physics_step']==3
        assert failure['world']['contact_events']['events']==failure['task']['result']['metrics']['contact_events']
        assert failure['task']['result']['terminated']
        assert 'contact_events' not in str(result['feedback'])
        local_env.privileged.rewind_to(anchor)
        assert not local_env._task.result.terminated
        assert local_env._world.read_state()['contact_events']['events']==[]
