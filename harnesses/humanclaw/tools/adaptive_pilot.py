#!/usr/bin/env python3
"""Freeze, submit and audit the approved 24-task diagnostic cohort on Klone."""
from __future__ import annotations
import argparse
import csv
import hashlib
import json
import os
from pathlib import Path
import shutil
import sqlite3
import subprocess
import sys
import tarfile
import time


def save(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + f".{os.getpid()}.tmp")
    temporary.write_text(json.dumps(value, indent=2, ensure_ascii=False) + "\n")
    temporary.replace(path)


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def prepare(root, repository):
    if root.exists():
        raise ValueError("Cohort directory already exists; never replace a frozen cohort")
    branch = subprocess.check_output(["git", "branch", "--show-current"], cwd=repository, text=True).strip()
    if branch != "harness-improving":
        raise ValueError("Prepare from the requested harness-improving branch")
    if subprocess.check_output(["git", "diff", "HEAD"], cwd=repository):
        raise ValueError("Commit task sources before freezing")
    revision = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=repository, text=True).strip()
    root.mkdir(parents=True)
    source = root / "source"; source.mkdir()
    archive = root / "source.tar"
    with archive.open("wb") as out:
        subprocess.run(["git", "archive", "HEAD", "src", "harnesses/pi-adaptive", "configs", "tools",
            "pyproject.toml", "README.md", "docs/ADAPTIVE_PILOT.md"], cwd=repository, stdout=out, check=True)
    with tarfile.open(archive) as tar:
        tar.extractall(source, filter="data")
    archive.unlink()
    files = {str(p.relative_to(source)): sha(p) for p in source.rglob("*") if p.is_file()}
    # Only host-side benchmark data/credentials; candidate sandboxes do not mount these.
    assets = Path("/gscratch/stf/hengyil6/HumanCLAW")
    for name in (".env", "data", "weights", "resources"):
        dest = source / name
        if dest.is_dir():
            shutil.rmtree(dest)
        if dest.exists():
            dest.unlink()
        dest.symlink_to(assets / name)
    modules = source / "harnesses/pi-adaptive/node_modules"
    modules.symlink_to(repository / "harnesses/pi-adaptive/node_modules")
    plan = json.loads((source / "configs/experiments/adaptive_pilot24.json").read_text())
    config = json.loads((source / "configs/harnesses/pi_adaptive.json").read_text())
    config["node_command"] = "/tmp/hc-adaptive-hengyil6-deps/node-v22.19.0-linux-x64/bin/node"
    save(root / "harness.json", config)
    save(root / "plan.json", plan)
    for row in plan["episodes"]:
        save(root / "episodes" / (row["shard"] + ".json"), {"episodes": [{k: row[k] for k in ("scene_id", "episode_id", "object_category")}], "n_episodes": 1})
    files = {name: value for name, value in files.items() if not name.startswith("weights/")}
    freeze = {"schema": "adaptive-cohort-freeze-v1", "revision": revision, "branch": branch,
        "source_files": files, "plan_sha256": sha(root / "plan.json"), "harness_sha256": sha(root / "harness.json"),
        "created_at": time.time(), "python": sys.executable, "max_gpu_concurrency": 2}
    dependency_archive = Path("/gscratch/stf/hengyil6/humanclaw-adaptive-deps-20261026.tar.gz")
    freeze["dependency_archive"] = str(dependency_archive)
    freeze["dependency_archive_sha256"] = sha(dependency_archive)
    freeze["resource_manifest_sha256"] = sha(assets / "resources/assets.json")
    save(root / "freeze.json", freeze)
    (root / "logs").mkdir()
    print(json.dumps({"cohort": str(root), "revision": revision, "tasks": len(plan["episodes"])}))


def verify(root):
    freeze = json.loads((root / "freeze.json").read_text())
    if sha(root / "plan.json") != freeze["plan_sha256"] or sha(root / "harness.json") != freeze["harness_sha256"]:
        raise ValueError("Frozen cohort configuration changed")
    if sha(root / "source/resources/assets.json") != freeze["resource_manifest_sha256"]:
        raise ValueError("Shared benchmark resource manifest changed")
    for name, expected in freeze["source_files"].items():
        if sha(root / "source" / name) != expected:
            raise ValueError(f"Frozen source changed: {name}")
    return json.loads((root / "plan.json").read_text())


def initial_pose(row, run):
    import numpy as np
    historical = Path(row["historical"]["run"].replace("/gscratch/scrubbed/linjli/humanclaw/experiments/", "/gscratch/scrubbed/hengyil6/humanclaw-analysis/experiments/"))
    before = run / "replay/trajectory_before.npz"
    previous = historical / "replay/trajectory_before.npz"
    if not previous.is_file():
        previous = Path(row["historical"]["run"]) / "replay/trajectory_before.npz"
    if not before.is_file() or not previous.is_file():
        return {"status": "inconclusive", "reason": "Saved initialization unavailable"}
    with np.load(before, allow_pickle=False) as new, np.load(previous, allow_pickle=False) as old:
        keys = ["initial_human_transl", "initial_human_global_orient", "initial_human_body_pose"]
        checks = {k: k in new and k in old and new[k].shape == old[k].shape and bool(np.allclose(new[k], old[k], rtol=0, atol=1e-5)) for k in keys}
    return {"status": "pass" if all(checks.values()) else "fail", "checks": checks, "historical": str(previous)}


def terminal_provider_failure(events):
    """Classify only the final model request, including errors carried inside HTTP 200 streams."""
    from humanclaw_bench.harnesses.provider_errors import provider_failure
    final, session_error = None, None
    for event in events:
        if event.get("event") == "span.end" and event.get("name") == "model.responses":
            final = event.get("data", {})
        if event.get("event") == "span.end" and event.get("name") == "harness.session":
            session_error = event.get("data", {}).get("error")
        if event.get("event") == "model.request_rejected":
            final = None
    if session_error and (session_error.get("type") != "RuntimeError" or not session_error.get("message", "").startswith("Pi episode failed:")):
        return None
    if not final or final.get("status") != "failed":
        return None
    attributes, output, error = final.get("attributes") or {}, final.get("output") or {}, final.get("error") or {}
    if attributes.get("provider_failure"):
        return attributes["provider_failure"]
    details = error.get("details") if isinstance(error, dict) else None
    incomplete = output.get("incomplete_details")
    if isinstance(error, dict) and error.get("type") == "response.incomplete":
        incomplete = incomplete or details
    return provider_failure(status=attributes.get("http_status"), error=output.get("error") or details,
                            incomplete=incomplete)


def audit(root, row, attempt):
    from humanclaw_bench.experiments.report import summarize_run, validate_trace
    runs = list(attempt.glob("*/rollout_00/experiment_runs/*/run.json"))
    if len(runs) != 1:
        return {"structural_pass": False, "reason": "Expected one complete trace", "retryable_infrastructure": False}
    run = runs[0].parent
    summary = summarize_run(run, write=True)
    trace = validate_trace(run)
    journal = run / "native/adaptive/journal.sqlite"
    if not journal.is_file():
        return {"structural_pass": False, "reason": "Missing broker journal", "retryable_infrastructure": False, "run": str(run)}
    db = sqlite3.connect(f"file:{journal}?mode=ro", uri=True)
    counts = dict(db.execute("SELECT kind,COUNT(*) FROM events GROUP BY kind"))
    unresolved = db.execute("SELECT COUNT(*) FROM requests WHERE state IN ('running','accepted','indeterminate')").fetchone()[0]
    kinds = {"candidate.created", "validation.report", "candidate.activated", "candidate.quarantined", "release.decision", "completion.checked", "memory.updated", "program.review"}
    adaptations = [{"seq": n, "kind": k, "data": json.loads(p)} for n,k,p in db.execute("SELECT seq,kind,payload FROM events") if k in kinds]
    db.close()
    init = initial_pose(row, run)
    metrics_files = list(attempt.glob("*/rollout_00/metrics.json"))
    review_errors = [e["data"]["review"]["infrastructure_error"] for e in adaptations
        if e["kind"] in {"validation.report", "program.review"} and e["data"].get("review", {}).get("infrastructure_error")]
    checks = {"completed": summary["status"] == "completed", "trace_valid": trace["ok"],
        "settled": unresolved == 0, "discovered": counts.get("discovery.catalog", 0) > 0,
        "environment_executed": counts.get("execution.started", 0) > 0, "metrics_written": len(metrics_files) == 1,
        "historical_initial_pose_matches": init["status"] == "pass", "adaptation_infrastructure_healthy": not review_errors}
    save(attempt / "adaptation-events.json", adaptations)
    failure = terminal_provider_failure(json.loads(line) for line in (run / "events.jsonl").read_text().splitlines())
    # Only the terminal failure can authorize retry; an earlier throttle cannot excuse a content filter.
    retryable = (summary["status"] != "completed" and unresolved == 0 and trace["ok"] and init["status"] == "pass"
        and not review_errors and bool(failure and failure["retryable"]))
    return {"structural_pass": all(checks.values()), "checks": checks, "initial_pose": init,
        "retryable_infrastructure": retryable, "run": str(run), "outcome": summary["outcome"],
        "provider_failure": failure if summary["status"] != "completed" else None, "review_infrastructure_errors": review_errors,
        "model_usage": summary["model_usage"], "latency": summary["latency"], "events": counts,
        "metrics": json.loads(metrics_files[0].read_text()) if metrics_files else None}


def run_task(root, index):
    if (root / "STOPPED.json").exists():
        raise ValueError("Cohort stopped; prepare a new frozen cohort after repair")
    plan = verify(root)
    row = plan["episodes"][index]
    state_path = root / "state" / (row["shard"] + ".json")
    if state_path.exists():
        raise ValueError("Task already started; explicit reconciliation required, no automatic duplicate")
    if index >= 2:
        for gate in plan["gate_shards"]:
            state = json.loads((root / "state" / (gate + ".json")).read_text())
            if state.get("status") != "completed":
                raise ValueError("Two-task framework gate has not passed")
    source = root / "source"
    reports = []
    for number in (1, 2):
        attempt = root / "results" / row["shard"] / f"attempt-{number}"
        attempt.mkdir(parents=True)
        save(state_path, {"status": "running", "shard": row["shard"], "attempt": number, "attempts": reports, "job_id": os.environ.get("SLURM_JOB_ID")})
        cmd = [sys.executable, "-m", "humanclaw_bench", "run", "--episodes", str(root / "episodes" / (row["shard"] + ".json")),
            "--profile", str(source / "configs/paper_fullval_v1.json"), "--model-config", str(source / "configs/models/azure_gpt6_astra.json"),
            "--scene-dataset-config", "/gscratch/stf/hengyil6/data/humanclaw-hssd-val41/hssd-hab.scene_dataset_config.json",
            "--harness", "pi", "--harness-config", str(root / "harness.json"), "--seed", "0", "--gpus", "auto",
            "--workers-per-gpu", "1", "--trace", "--metrics", "--video", "--output", str(attempt)]
        with (attempt / "process.log").open("w") as out:
            code = subprocess.run(cmd, cwd=source, stdout=out, stderr=subprocess.STDOUT).returncode
        result = audit(root, row, attempt)
        result.update(attempt=number, process_exit_code=code)
        reports.append(result)
        save(attempt / "audit.json", result)
        verify(root)
        result["archive"] = archive_attempt(attempt)
        save(attempt / "audit.json", result)
        if result["structural_pass"]:
            save(state_path, {"status": "completed", "shard": row["shard"], "attempts": reports})
            report(root)
            return 0
        if not result.get("retryable_infrastructure"):
            break
    status = "provider_failed" if result.get("provider_failure") else "framework_failed"
    save(state_path, {"status": status, "shard": row["shard"], "attempts": reports})
    report(root)
    return 1


def archive_attempt(attempt):
    """Verify compressed trace contents before removing only this attempt's raw directories."""
    archive = attempt.with_suffix(".tar.gz")
    with tarfile.open(archive, "w:gz") as tar:
        tar.add(attempt, arcname=attempt.name)
    with tarfile.open(archive) as tar:
        for member in tar:
            if member.isfile():
                original = attempt.parent / member.name
                with tar.extractfile(member) as stream:
                    actual = hashlib.file_digest(stream, "sha256").hexdigest()
                if actual != sha(original):
                    raise ValueError("Archive verification failed; raw attempt retained")
    result = {"path": str(archive), "sha256": sha(archive), "bytes": archive.stat().st_size,
              "raw_directory": str(attempt), "verified": True}
    for child in attempt.iterdir():
        if child.is_dir() and not child.is_symlink():
            shutil.rmtree(child)
    return result


def report(root):
    plan = json.loads((root / "plan.json").read_text())
    rows = []
    for row in plan["episodes"]:
        path = root / "state" / (row["shard"] + ".json")
        state = json.loads(path.read_text()) if path.exists() else {"status": "pending", "attempts": []}
        attempts = state.get("attempts", [])
        final = attempts[-1] if attempts else {}
        rows.append({"shard": row["shard"], "group": row["group"], "status": state["status"],
            "historical_success": row["historical"]["success"], "new_success": final.get("outcome", {}).get("task_success"),
            "historical_steps": row["historical"]["steps"], "new_steps": final.get("outcome", {}).get("steps"),
            "attempts": len(attempts), "model_calls_all_attempts": sum(a["model_usage"]["leaf_model_calls"] for a in attempts)
                if attempts and all("model_usage" in a for a in attempts) and state["status"] != "running" else None,
            "candidate_creations": final.get("events", {}).get("candidate.created", 0),
            "activations": final.get("events", {}).get("candidate.activated", 0), "run": final.get("run"),
            "archive": final.get("archive", {}).get("path")})
    # Atomic replacement; either concurrent writer produces a complete snapshot.
    save(root / "report.json", {"attribution": plan["attribution"], "rows": rows,
        "untriggered_is_not_validated": True, "updated_at": time.time()})
    tmp = root / f"report.{os.getpid()}.csv.tmp"
    with tmp.open("w") as out:
        writer = csv.DictWriter(out, fieldnames=list(rows[0])); writer.writeheader(); writer.writerows(rows)
    tmp.replace(root / "report.csv")


def submit(root):
    if (root / "STOPPED.json").exists():
        raise ValueError("Cohort stopped; prepare a new frozen cohort after repair")
    verify(root)
    if (root / "jobs.json").exists():
        raise ValueError("Cohort already submitted")
    script = root / "source/tools/adaptive_pilot.sbatch"
    base = ["sbatch", "--parsable", "--export", f"ALL,HC_ADAPTIVE_COHORT={root}", "--output", str(root / "logs/%A_%a.log")]
    first = subprocess.check_output([*base, "--array=0-1%2", str(script)], text=True).strip().split(";")[0]
    save(root / "jobs.json", {"gate_array": first, "remainder_array": None})
    remaining = subprocess.check_output([*base, "--array=2-23%2", "--dependency=afterok:" + first,
        "--kill-on-invalid-dep=yes", str(script)], text=True).strip().split(";")[0]
    save(root / "jobs.json", {"gate_array": first, "remainder_array": remaining, "max_concurrent_gpu_jobs": 2})
    report(root)
    print(json.dumps({"gate_array": first, "remainder_array": remaining}))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("mode", choices=["prepare", "submit", "run-task", "report", "verify"])
    parser.add_argument("root", type=Path)
    parser.add_argument("--repository", type=Path, default=Path(__file__).resolve().parents[1])
    parser.add_argument("--index", type=int)
    args = parser.parse_args(); root = args.root.resolve()
    if args.mode == "prepare": prepare(root, args.repository.resolve())
    elif args.mode == "submit": submit(root)
    elif args.mode == "run-task": raise SystemExit(run_task(root, args.index))
    elif args.mode == "report": report(root)
    else: verify(root)
