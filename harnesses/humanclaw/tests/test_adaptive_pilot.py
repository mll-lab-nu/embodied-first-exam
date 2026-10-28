import importlib.util
import json
import tarfile
from pathlib import Path

import numpy as np
import pytest

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("adaptive_pilot", ROOT / "tools/adaptive_pilot.py")
pilot = importlib.util.module_from_spec(spec)
spec.loader.exec_module(pilot)


def test_frozen_diagnostic_panel():
    plan = json.loads((ROOT / "configs/experiments/adaptive_pilot24.json").read_text())
    rows = plan["episodes"]
    assert len(rows) == len({r["scene_id"] for r in rows}) == 24
    assert sum(r["historical"]["success"] == "False" for r in rows) == 16
    assert sum(r["task_type"] == "navigation" for r in rows) == 12
    assert [r["shard"] for r in rows[:2]] == plan["gate_shards"]


def test_submission_preserves_two_task_gate_and_concurrency(tmp_path, monkeypatch):
    plan = json.loads((ROOT / "configs/experiments/adaptive_pilot24.json").read_text())
    pilot.save(tmp_path / "plan.json", plan)
    monkeypatch.setattr(pilot, "verify", lambda root: plan)
    commands = []
    def submit(cmd, **kwargs):
        commands.append(cmd)
        return f"{1000+len(commands)}\n"
    monkeypatch.setattr(pilot.subprocess, "check_output", submit)
    pilot.submit(tmp_path)
    assert "--array=0-1%2" in commands[0]
    assert "--array=2-23%2" in commands[1] and "--dependency=afterok:1001" in commands[1]
    with pytest.raises(ValueError, match="already submitted"):
        pilot.submit(tmp_path)


def test_reports_include_cost_of_failed_attempts(tmp_path):
    plan = json.loads((ROOT / "configs/experiments/adaptive_pilot24.json").read_text())
    pilot.save(tmp_path / "plan.json", plan)
    pilot.save(tmp_path / "state/shard-0362.json", {"status": "completed", "attempts": [
        {"model_usage": {"leaf_model_calls": 3}},
        {"model_usage": {"leaf_model_calls": 10}, "outcome": {"task_success": False, "steps": 100}}]})
    pilot.report(tmp_path)
    row = json.loads((tmp_path / "report.json").read_text())["rows"][0]
    assert row["model_calls_all_attempts"] == 13 and row["new_success"] is False and row["status"] == "completed"


def test_initial_pose_gate_checks_actual_arrays(tmp_path):
    old, new = tmp_path / "old", tmp_path / "new"
    for path in (old, new): (path / "replay").mkdir(parents=True)
    arrays = {k: np.zeros(n) for k,n in [("initial_human_transl",3),("initial_human_global_orient",3),("initial_human_body_pose",69)]}
    for path in (old, new): np.savez(path / "replay/trajectory_before.npz", **arrays)
    row = {"historical": {"run": str(old)}}
    assert pilot.initial_pose(row, new)["status"] == "pass"
    arrays["initial_human_transl"][0] = .01
    np.savez(new / "replay/trajectory_before.npz", **arrays)
    assert pilot.initial_pose(row, new)["status"] == "fail"


def test_archive_verifies_and_preserves_attempt_evidence(tmp_path):
    attempt = tmp_path / "attempt-1"
    (attempt / "episode/trace").mkdir(parents=True)
    (attempt / "episode/trace/evidence.txt").write_text("complete evidence")
    (attempt / "audit.json").write_text('{}')
    result = pilot.archive_attempt(attempt)
    assert result["verified"] and (attempt / "audit.json").exists()
    assert not (attempt / "episode").exists()
    with tarfile.open(result["path"]) as tar:
        assert tar.extractfile('attempt-1/episode/trace/evidence.txt').read() == b'complete evidence'


def test_retry_classifies_terminal_stream_error_not_previous_throttle():
    def model(error=None, incomplete=None):
        return {'event':'span.end','name':'model.responses','data':{'status':'failed' if error or incomplete else 'completed',
            'output':{'error':error,'incomplete_details':incomplete},'attributes':{}}}
    throttle = model(error={'code':'rate_limit_exceeded'})
    filtered = model(incomplete={'reason':'content_filter'})
    assert pilot.terminal_provider_failure([throttle])['retryable']
    assert pilot.terminal_provider_failure([throttle,filtered]) == {
        'category':'content_filter','retryable':False,'http_status':None,'code':'content_filter','message':None}
    assert pilot.terminal_provider_failure([throttle,model()]) is None
    timeout = {'event':'span.end','name':'harness.session','data':{'error':{'type':'TimeoutError','message':'Episode deadline'}}}
    assert pilot.terminal_provider_failure([throttle,timeout]) is None


def test_stopped_cohort_cannot_be_resubmitted_or_start_another_task(tmp_path):
    pilot.save(tmp_path/'STOPPED.json', {'reason':'User stopped this cohort'})
    with pytest.raises(ValueError,match='Cohort stopped'): pilot.submit(tmp_path)
    with pytest.raises(ValueError,match='Cohort stopped'): pilot.run_task(tmp_path,0)


@pytest.mark.parametrize('broken_review', [False, True])
def test_framework_gate_rejects_review_infrastructure_errors(tmp_path, monkeypatch, broken_review):
    import sqlite3
    import humanclaw_bench.experiments.report as reports
    attempt=tmp_path/'attempt-1';run=attempt/'episode/rollout_00/experiment_runs/run-test'
    (run/'native/adaptive').mkdir(parents=True)
    (run/'run.json').write_text('{}');(run/'events.jsonl').write_text('')
    (attempt/'episode/rollout_00/metrics.json').write_text('{}')
    with sqlite3.connect(run/'native/adaptive/journal.sqlite') as db:
        db.executescript('CREATE TABLE events(seq INTEGER,kind TEXT,payload TEXT); CREATE TABLE requests(state TEXT);')
        rows=[(1,'discovery.catalog','{}'),(2,'execution.started','{}')]
        review={'status':'inconclusive','reason':'Evidence insufficient'}
        if broken_review:review['infrastructure_error']={'category':'review_transport','retryable':False}
        rows.append((3,'validation.report',json.dumps({'review':review})))
        db.executemany('INSERT INTO events VALUES (?,?,?)',rows)
    monkeypatch.setattr(reports,'summarize_run',lambda *a,**kw:{'status':'completed','outcome':{'task_success':False},'model_usage':{},'latency':{}})
    monkeypatch.setattr(reports,'validate_trace',lambda *a:{'ok':True})
    monkeypatch.setattr(pilot,'initial_pose',lambda *a:{'status':'pass'})
    audit=pilot.audit(tmp_path,{},attempt)
    assert audit['structural_pass'] is not broken_review
    assert audit['checks']['adaptation_infrastructure_healthy'] is not broken_review
    assert not audit['retryable_infrastructure']
