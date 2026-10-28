#!/usr/bin/env python3
"""Verify a frozen Klone suite, record allocation attempts, and audit its denominator."""

from __future__ import annotations

import argparse
from collections import Counter, defaultdict
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import socket
import subprocess
import tempfile


def _read(path: Path) -> dict:
    """Read one JSON object without inspecting environment credentials."""
    value = json.loads(path.read_text())
    if not isinstance(value, dict):
        raise ValueError(f"Expected an object: {path}")
    return value


def _write(path: Path, value: dict) -> None:
    """Atomically publish one audit record, including on shared storage."""
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
    try:
        with os.fdopen(fd, "w") as stream:
            json.dump(value, stream, indent=2, ensure_ascii=False, allow_nan=False)
            stream.write("\n")
        os.replace(temporary, path)
    finally:
        Path(temporary).unlink(missing_ok=True)


def verify(suite: Path, index: int) -> None:
    """Reject source or selection drift before any GPU/model work begins."""
    manifest = _read(suite / "suite.json")
    shard = manifest["shards"][index]
    if shard["index"] != index:
        raise ValueError("Shard index mismatch")
    source = suite / "source"
    snapshot = _read(suite / "snapshot_manifest.json")
    for name, digest in snapshot["files_sha256"].items():
        relative = Path(name)
        if relative.is_absolute() or ".." in relative.parts:
            raise ValueError("Unsafe snapshot path")
        if hashlib.sha256((source / relative).read_bytes()).hexdigest() != digest:
            raise ValueError(f"Frozen source changed: {name}")
    selection = suite / shard["selection"]
    if hashlib.sha256(selection.read_bytes()).hexdigest() != shard["selection_sha256"]:
        raise ValueError("Frozen episode selection changed")
    rows = _read(selection)["episodes"]
    if rows != shard["episodes"]:
        raise ValueError("Shard does not match declared suite denominator")


def record_status(suite: Path, index: int, status: str, exit_code: int | None) -> dict:
    """Keep each Slurm allocation/restart visible even before a trace exists."""
    manifest = _read(suite / "suite.json")
    shard = manifest["shards"][index]
    attempt_id = f"{os.environ['SLURM_JOB_ID']}-restart-{os.environ.get('SLURM_RESTART_COUNT', '0')}"
    path = suite / "allocations" / f"shard-{index:04d}" / f"{attempt_id}.json"
    value = _read(path) if path.exists() else {
        "schema": "humanclaw_suite_allocation_v1", "shard": index,
        "requested_episodes": shard["episodes"], "hostname": socket.gethostname(),
        "started_at_utc": datetime.now(timezone.utc).isoformat(),
        "slurm": {key: os.environ.get(key) for key in (
            "SLURM_JOB_ID", "SLURM_ARRAY_JOB_ID", "SLURM_ARRAY_TASK_ID", "SLURM_RESTART_COUNT",
            "SLURM_JOB_ACCOUNT", "SLURM_JOB_PARTITION", "SLURM_JOB_NODELIST",
        )},
    }
    value.update(status=status, exit_code=exit_code, updated_at_utc=datetime.now(timezone.utc).isoformat())
    _write(path, value)
    return value


def storage_guard(suite: Path) -> dict:
    """Stop pending tasks in this array if recording capacity cannot be verified."""
    from humanclaw_bench.experiments.storage import StorageCapacityError, check_storage

    try:
        return check_storage(suite)
    except StorageCapacityError as exc:
        result = {"schema": "humanclaw_storage_block_v1", "error": str(exc),
                  "at_utc": datetime.now(timezone.utc).isoformat(),
                  "array_job_id": os.environ.get("SLURM_ARRAY_JOB_ID"), "scheduler_actions": []}
        array_id = result["array_job_id"]
        if array_id and array_id.isdecimal():
            # Hold remaining siblings; if Slurm refuses, cancel only pending
            # siblings so an entire array cannot cascade through quota errors.
            for command in (["scontrol", "hold", array_id], ["scancel", "--state=PENDING", array_id]):
                try:
                    action = subprocess.run(command, capture_output=True, text=True, timeout=30)
                    result["scheduler_actions"].append({"command": command, "returncode": action.returncode,
                                                        "stdout": action.stdout, "stderr": action.stderr})
                    if action.returncode == 0:
                        break
                except (OSError, subprocess.SubprocessError) as error:
                    result["scheduler_actions"].append({"command": command, "error": str(error)})
        # The log remains useful even if writing a separate receipt is impossible.
        print(json.dumps(result), flush=True)
        try:
            _write(suite / "storage_block.json", result)
        except OSError:
            pass
        raise


def _identity(episode: dict) -> tuple[str, str, str]:
    """Use the frozen benchmark identity rather than run directory names."""
    return tuple(str(episode.get(field, "")) for field in ("scene_id", "episode_id", "object_category"))


def suite_outcomes(manifest: dict, runs: list[dict], allocations: list[dict], matches) -> dict:
    """Count each requested episode once; retain every attempt separately for costs."""
    requested = {}
    for shard in manifest["shards"]:
        for episode in shard["episodes"]:
            key = _identity(episode)
            if key in requested:
                raise ValueError("Duplicate requested episode")
            requested[key] = (episode, shard["index"])
    if len(requested) != manifest["requested_episodes"]:
        raise ValueError("Suite denominator differs from episode list")
    by_episode = defaultdict(list)
    for run in runs:
        episode = dict(run.get("metadata", {}).get("episode", {}))
        episode["scene_id"] = episode.get("scene_label", episode.get("scene_id"))
        by_episode[_identity(episode)].append(run)
    by_shard = defaultdict(list)
    for allocation in allocations:
        by_shard[allocation["shard"]].append(allocation)
    rows = []
    for key, (episode, shard) in requested.items():
        attempts = by_episode[key]
        completed = [run for run in attempts if (
            run["status"] == "completed" and run["trace_diagnostics"]["ok"]
            and not run["trace_diagnostics"]["warnings"] and matches(run, episode)
        )]
        # A resumed batch should skip completed episodes. Multiple completions
        # are ambiguous and must not silently improve the benchmark score.
        selected = completed[0] if len(completed) == 1 else None
        success = selected["outcome"].get("task_success") if selected else None
        success = success if isinstance(success, bool) else None
        if len(completed) > 1:
            state = "duplicate_completed"
        elif selected:
            state = "scored" if success is not None else "completed_unscored"
        elif attempts:
            state = "no_valid_completed_trace"
        else:
            states = {entry["status"] for entry in by_shard[shard]}
            if states & {"failed", "interrupted"}:
                state = "infrastructure_failure_without_trace"
            else:
                state = "allocation_without_trace" if states else "not_started"
        rows.append({"episode": episode, "shard": shard, "state": state, "task_success": success,
                     "selected_run_id": selected["run_id"] if selected else None,
                     "attempt_run_ids": [run["run_id"] for run in attempts]})
    scored = sum(isinstance(row["task_success"], bool) for row in rows)
    successes = sum(row["task_success"] is True for row in rows)
    return {
        "requested_episodes": len(rows), "scored_episodes": scored,
        "unscored_episodes": len(rows) - scored, "task_successes": successes,
        "task_success_rate_all_requested": successes / len(rows) if rows else None,
        "task_success_rate_scored": successes / scored if scored else None,
        "scoring_coverage": scored / len(rows) if rows else None,
        "episode_state_counts": dict(Counter(row["state"] for row in rows)),
        "extra_unrequested_run_ids": [run["run_id"] for key, values in by_episode.items() if key not in requested for run in values],
        "episodes": rows,
    }


def report(suite: Path) -> dict:
    """Build a CPU-only suite report with a fixed requested-episode denominator."""
    from humanclaw_bench.batch import _trace_configuration, _trace_matches
    from humanclaw_bench.config import load_config
    from humanclaw_bench.environment import load_project_environment
    from humanclaw_bench.evaluation.metrics import aggregate_metric_files
    from humanclaw_bench.experiments.report import summarize_runs

    load_project_environment()
    manifest = _read(suite / "suite.json")
    if manifest.get("recovery_parent"):
        return recovery_report(suite, manifest)
    settings = manifest["settings"]
    source = suite / "source"
    config = {**settings, "compute_metrics": True, "scene_dataset_config": manifest["scene_dataset_config"]}
    expected = _trace_configuration(config, load_config(source / "configs/paper_fullval_v1.json"),
                                    source / settings["model_config"])
    collection = summarize_runs(suite / "results", write=True)
    allocations = [_read(path) for path in sorted((suite / "allocations").glob("*/*.json"))]
    outcomes = suite_outcomes(manifest, collection["runs"], allocations,
                              lambda run, episode: _trace_matches(run, episode, expected))
    metrics = aggregate_metric_files(suite / "results", write_summary=True)
    result = {
        "schema": "humanclaw_suite_summary_v1", "suite_id": manifest["suite_id"],
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "outcomes": outcomes, "all_attempts": collection["aggregate"],
        "paper_metrics": metrics,
        "paper_metrics_scope": "Latest metrics.json files only; use outcomes for the fixed suite denominator, "
                               "and all_attempts for tokens/cost/latency including interrupted attempts.",
        "allocation_status_counts": dict(Counter(row["status"] for row in allocations)),
        "source": "Frozen source/configuration; explicit no API budget cap; no model calls in this report.",
    }
    _write(suite / "suite_summary.json", result)
    return result


def recovery_report(suite: Path, manifest: dict) -> dict:
    """Keep the original denominator and all attempts across a storage repair."""
    from humanclaw_bench.batch import _trace_configuration, _trace_matches
    from humanclaw_bench.config import load_config
    from humanclaw_bench.experiments.report import summarize_run_directories

    lineage = manifest["recovery_parent"]
    parent = Path(lineage["suite"])
    if hashlib.sha256((parent / "suite.json").read_bytes()).hexdigest() != lineage["manifest_sha256"]:
        raise ValueError("Recovery parent manifest changed")
    original = _read(parent / "suite.json")
    original_rows = {_identity(row): shard["index"] for shard in original["shards"] for row in shard["episodes"]}
    expected = {}
    directories = set()
    allocations = []
    previous_home = os.environ.get("HUMANCLAW_BENCH_HOME")
    try:
        for root, plan in ((parent, original), (suite, manifest)):
            source = root / "source"
            os.environ["HUMANCLAW_BENCH_HOME"] = str(source)
            settings = plan["settings"]
            configuration = {**settings, "compute_metrics": True, "scene_dataset_config": plan["scene_dataset_config"]}
            expected[root.resolve()] = _trace_configuration(
                configuration, load_config(source / "configs/paper_fullval_v1.json"), source / settings["model_config"])
            directories.update(path.parent for path in (root / "results").rglob("events.jsonl"))
            for path in (root / "allocations").glob("*/*.json"):
                allocation = _read(path)
                for original_shard in {original_rows[_identity(row)] for row in allocation["requested_episodes"]}:
                    allocations.append({**allocation, "shard": original_shard})
    finally:
        if previous_home is None:
            os.environ.pop("HUMANCLAW_BENCH_HOME", None)
        else:
            os.environ["HUMANCLAW_BENCH_HOME"] = previous_home
    collection = summarize_run_directories(directories, write=False)
    def matches(run, episode):
        for root, configuration in expected.items():
            if Path(run["run_dir"]).is_relative_to(root / "results"):
                return _trace_matches(run, episode, configuration)
        return False
    outcomes = suite_outcomes(original, collection["runs"], allocations, matches)
    result = {
        "schema": "humanclaw_suite_summary_v1", "suite_id": manifest["suite_id"],
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "outcomes": outcomes, "all_attempts": collection["aggregate"],
        "scheduled_recovery_episodes": manifest["requested_episodes"], "recovery_parent": lineage,
        "run_index": [{"run_id": run["run_id"], "run_dir": run["run_dir"], "status": run["status"]} for run in collection["runs"]],
        "source": "Each attempt must match its own frozen source and model/profile settings. Original unsuccessful and interrupted attempts remain in cost accounting.",
        "latency_comparison": "Storage implementation changed; retain source identity and compare latency by source and hardware.",
    }
    _write(suite / "suite_summary.json", result)
    return result


def main() -> int:
    """Run local bookkeeping only; actual episodes use the existing batch dispatcher."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("operation", choices=("verify", "status", "report", "storage"))
    parser.add_argument("suite", type=Path)
    parser.add_argument("--shard", type=int, default=0)
    parser.add_argument("--status", default="running")
    parser.add_argument("--exit-code", type=int)
    args = parser.parse_args()
    if args.operation == "storage":
        from humanclaw_bench.experiments.storage import StorageCapacityError
        try:
            print(json.dumps(storage_guard(args.suite)))
        except StorageCapacityError:
            return 75
    elif args.operation == "verify":
        verify(args.suite, args.shard)
    elif args.operation == "status":
        record_status(args.suite, args.shard, args.status, args.exit_code)
    else:
        result = report(args.suite)
        print(json.dumps({"report": str(args.suite / "suite_summary.json"),
                          "requested": result["outcomes"]["requested_episodes"],
                          "scored": result["outcomes"]["scored_episodes"]}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
