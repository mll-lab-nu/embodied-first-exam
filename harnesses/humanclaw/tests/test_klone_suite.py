"""Offline checks for frozen suite identity and a denominator spanning Slurm shards."""

import hashlib
import importlib.util
import json
from pathlib import Path

import pytest

SPEC = importlib.util.spec_from_file_location("klone_suite", Path(__file__).parents[1] / "tools/klone_suite.py")
suite = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(suite)


def episode(index):
    return {"scene_id": "scene", "episode_id": str(index), "object_category": "bed"}


def manifest(count):
    return {"requested_episodes": count,
            "shards": [{"index": i, "episodes": [episode(i)]} for i in range(count)]}


def run(index, run_id, *, status="completed", success=True, warnings=None, matching=True):
    return {"run_id": run_id, "status": status, "metadata": {"episode": episode(index)},
            "outcome": {"task_success": success},
            "trace_diagnostics": {"ok": True, "warnings": warnings or []}, "matching": matching}


def test_suite_keeps_failed_unstarted_and_retried_episodes_in_denominator():
    runs = [run(0, "interrupted-attempt", status="interrupted", success=None),
            run(0, "complete-attempt", success=False), run(1, "success"),
            run(3, "partial", warnings=["missing run.end"])]
    allocations = [{"shard": 2, "status": "failed"}]
    result = suite.suite_outcomes(manifest(5), runs, allocations, lambda r, e: r["matching"])
    assert result["requested_episodes"] == 5
    assert result["scored_episodes"] == 2
    assert result["unscored_episodes"] == 3
    assert result["task_successes"] == 1
    assert result["task_success_rate_all_requested"] == 0.2
    assert result["task_success_rate_scored"] == 0.5
    assert result["episodes"][0]["attempt_run_ids"] == ["interrupted-attempt", "complete-attempt"]
    assert result["episode_state_counts"] == {
        "scored": 2, "infrastructure_failure_without_trace": 1,
        "no_valid_completed_trace": 1, "not_started": 1,
    }


def test_suite_refuses_ambiguous_completions_mismatched_configs_and_unrequested_runs():
    runs = [run(0, "first", success=False), run(0, "second", success=True),
            run(1, "changed-config", matching=False), run(999, "outside")]
    result = suite.suite_outcomes(manifest(2), runs, [], lambda r, e: r["matching"])
    assert result["scored_episodes"] == 0
    assert result["task_success_rate_scored"] is None
    assert result["episode_state_counts"] == {"duplicate_completed": 1, "no_valid_completed_trace": 1}
    assert result["extra_unrequested_run_ids"] == ["outside"]


def test_suite_distinguishes_an_allocation_without_trace_from_never_started():
    result = suite.suite_outcomes(manifest(1), [], [{"shard": 0, "status": "running"}], lambda r, e: True)
    assert result["episode_state_counts"] == {"allocation_without_trace": 1}


def test_suite_rejects_duplicate_episode_plan():
    value = manifest(2)
    value["shards"][1]["episodes"] = [episode(0)]
    with pytest.raises(ValueError, match="Duplicate requested"):
        suite.suite_outcomes(value, [], [], lambda r, e: True)


def test_verification_detects_changes_to_frozen_source_and_episode_selection(tmp_path):
    source = tmp_path / "source"
    source.mkdir()
    (source / "code.py").write_text("original\n")
    selection = tmp_path / "episodes.json"
    selection.write_text(json.dumps({"episodes": [episode(0)]}))
    value = manifest(1)
    value["shards"][0].update(selection="episodes.json", selection_sha256=hashlib.sha256(selection.read_bytes()).hexdigest())
    suite._write(tmp_path / "suite.json", value)
    suite._write(tmp_path / "snapshot_manifest.json", {"files_sha256": {"code.py": hashlib.sha256((source / "code.py").read_bytes()).hexdigest()}})
    suite.verify(tmp_path, 0)
    selection.write_text(json.dumps({"episodes": [episode(1)]}))
    with pytest.raises(ValueError, match="selection changed"):
        suite.verify(tmp_path, 0)
    selection.write_text(json.dumps({"episodes": [episode(0)]}))
    (source / "code.py").write_text("modified\n")
    with pytest.raises(ValueError, match="source changed"):
        suite.verify(tmp_path, 0)


def test_allocation_records_keep_restarts_and_initialization_failure(tmp_path, monkeypatch):
    suite._write(tmp_path / "suite.json", manifest(1))
    monkeypatch.setenv("SLURM_JOB_ID", "123")
    monkeypatch.setenv("SLURM_RESTART_COUNT", "0")
    suite.record_status(tmp_path, 0, "preflight", None)
    first = suite.record_status(tmp_path, 0, "failed", 1)
    monkeypatch.setenv("SLURM_RESTART_COUNT", "1")
    suite.record_status(tmp_path, 0, "running", None)
    paths = list((tmp_path / "allocations/shard-0000").glob("*.json"))
    assert len(paths) == 2
    assert suite._read(tmp_path / "allocations/shard-0000/123-restart-0.json") == first
    assert first["status"] == "failed"
    assert first["exit_code"] == 1


def test_storage_guard_holds_only_its_array_and_records_the_failure(tmp_path, monkeypatch):
    from types import SimpleNamespace
    from humanclaw_bench.experiments.storage import StorageCapacityError
    def fail(path):
        raise StorageCapacityError("inode quota exhausted")
    monkeypatch.setattr("humanclaw_bench.experiments.storage.check_storage", fail)
    monkeypatch.setenv("SLURM_ARRAY_JOB_ID", "123")
    commands = []
    def run(command, **kwargs):
        commands.append(command)
        return SimpleNamespace(returncode=0, stdout="held", stderr="")
    monkeypatch.setattr(suite.subprocess, "run", run)
    with pytest.raises(StorageCapacityError):
        suite.storage_guard(tmp_path)
    assert commands == [["scontrol", "hold", "123"]]
    assert suite._read(tmp_path / "storage_block.json")["array_job_id"] == "123"


def test_storage_guard_fallback_cancels_pending_siblings_only(tmp_path, monkeypatch):
    from types import SimpleNamespace
    from humanclaw_bench.experiments.storage import StorageCapacityError
    def fail(path):
        raise StorageCapacityError("cannot read quota")
    monkeypatch.setattr("humanclaw_bench.experiments.storage.check_storage", fail)
    monkeypatch.setenv("SLURM_ARRAY_JOB_ID", "456")
    commands = []
    def run(command, **kwargs):
        commands.append(command)
        return SimpleNamespace(returncode=1 if len(commands) == 1 else 0, stdout="", stderr="")
    monkeypatch.setattr(suite.subprocess, "run", run)
    with pytest.raises(StorageCapacityError):
        suite.storage_guard(tmp_path)
    assert commands == [["scontrol", "hold", "456"], ["scancel", "--state=PENDING", "456"]]


def test_recovery_report_keeps_original_denominator_and_both_source_identities(tmp_path, monkeypatch):
    import os
    import humanclaw_bench.batch
    parent, child = tmp_path / "original", tmp_path / "recovery"
    parent.mkdir()
    child.mkdir()
    settings = {"model_config": "model.json"}
    original = {**manifest(2), "settings": settings, "scene_dataset_config": "scene.json"}
    suite._write(parent / "suite.json", original)
    plan = {"suite_id": "recovery", "requested_episodes": 1, "settings": settings,
            "scene_dataset_config": "scene.json", "shards": [{"index": 0, "episodes": [episode(1)]}],
            "recovery_parent": {"suite": str(parent), "manifest_sha256": hashlib.sha256((parent / "suite.json").read_bytes()).hexdigest()}}
    runs = [run(0, "completed-original", success=False), run(1, "interrupted-original", status="failed", success=None), run(1, "retry-success")]
    for row, root in zip(runs, (parent, parent, child)):
        directory = root / "results" / row["run_id"]
        directory.mkdir(parents=True)
        (directory / "events.jsonl").write_text("")
        row["run_dir"] = str(directory)
    monkeypatch.setenv("HUMANCLAW_BENCH_HOME", "unchanged")
    monkeypatch.setattr("humanclaw_bench.config.load_config", lambda path: None)
    monkeypatch.setattr("humanclaw_bench.batch._trace_configuration", lambda *args: {"source": os.environ["HUMANCLAW_BENCH_HOME"]})
    checked = []
    def matches(row, episode, expected):
        checked.append((row["run_id"], expected["source"]))
        return Path(row["run_dir"]).is_relative_to(Path(expected["source"]).parent / "results")
    monkeypatch.setattr("humanclaw_bench.batch._trace_matches", matches)
    monkeypatch.setattr("humanclaw_bench.experiments.report.summarize_run_directories", lambda paths, **kw: {"runs": runs, "aggregate": {"runs": 3}})
    result = suite.recovery_report(child, plan)
    assert result["outcomes"]["requested_episodes"] == 2
    assert result["outcomes"]["scored_episodes"] == 2
    assert result["outcomes"]["task_success_rate_all_requested"] == 0.5
    assert result["all_attempts"]["runs"] == 3
    assert ("completed-original", str(parent / "source")) in checked
    assert ("retry-success", str(child / "source")) in checked
    assert os.environ["HUMANCLAW_BENCH_HOME"] == "unchanged"
    (parent / "suite.json").write_text("changed")
    with pytest.raises(ValueError, match="parent manifest changed"):
        suite.recovery_report(child, plan)
