"""Verify native Harbor exports, then move recordings into the shared archive."""
import fcntl
import json
import os
from pathlib import Path
import shutil
import tempfile

from .config import name
from .task_generator import file_hash


def atomic_json(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary = tempfile.mkstemp(dir=path.parent, prefix=".index-")
    try:
        with os.fdopen(fd, "w") as stream:
            json.dump(value, stream, indent=2, ensure_ascii=False, allow_nan=False)
            stream.write("\n")
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


def verify_archive(root):
    root = Path(root)
    if any(p.is_symlink() for p in (root, *root.parents)):
        raise ValueError("Archive path cannot contain symlinks")
    manifest = json.loads((root / "archive_manifest.json").read_text())
    actual = set()
    for path in root.rglob("*"):
        if path.is_symlink():
            raise ValueError("Archive contains symlink")
        if path.is_file() and path.name != "archive_manifest.json":
            actual.add(str(path.relative_to(root)))
    if actual != set(manifest["files"]):
        raise ValueError("Archive file set differs from sealed evidence")
    for relative, expected in manifest["files"].items():
        path = Path(relative)
        if path.is_absolute() or ".." in path.parts:
            raise ValueError("Unsafe archive member")
        path = root / path
        if path.stat().st_size != expected["size_bytes"] or file_hash(path) != expected["sha256"]:
            raise ValueError(f"Archive integrity failure: {relative}")
    return json.loads((root / "verification.json").read_text())


def _allocate(parent):
    parent.mkdir(parents=True, exist_ok=True)
    for number in range(1, 1000000):
        destination = parent / f"rollout_{number:04d}"
        try:
            destination.mkdir(mode=0o700)
            return destination
        except FileExistsError:
            continue
    raise RuntimeError("Rollout archive namespace exhausted")


def collect(run, project):
    run, project = Path(run).resolve(), Path(project).resolve()
    config = json.loads((run / "experiment.resolved.json").read_text())
    expected = json.loads((run / "manifest.json").read_text())["expected_trials"]
    index_path = run / "rollout_index.json"
    with (run / ".collect.lock").open("a") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        index = json.loads(index_path.read_text()) if index_path.exists() else {"trials": {}}
        trials = sorted((run / "jobs/job").glob("*/result.json"))
        for result_path in trials:
            trial = result_path.parent
            key = trial.name
            entry = index["trials"].setdefault(key, {})
            source = trial / "artifacts/topogym-rollout"
            try:
                if entry.get("archive"):
                    destination = Path(entry["archive"])
                else:
                    verify_archive(source)
                    instance = json.loads((source / "instance.json").read_text())
                    if instance not in config["instances"]:
                        raise ValueError("Exported instance differs from frozen run")
                    parent = project / "task_rollouts" / name(run.name) / name(instance["simulator"]["task_id"])
                    destination = _allocate(parent)
                    entry.update(archive=str(destination), status="pending")
                    atomic_json(index_path, index)  # recovery journal before moving any data
                if not (destination / "archive_manifest.json").exists():
                    verify_archive(source)
                    if source.stat().st_dev == destination.parent.stat().st_dev:
                        source.replace(destination)
                    else:
                        staging = Path(tempfile.mkdtemp(prefix=".collect-", dir=destination.parent))
                        try:
                            shutil.copytree(source, staging, dirs_exist_ok=True)
                            verify_archive(staging)
                            staging.replace(destination)
                        except BaseException:
                            shutil.rmtree(staging)
                            raise
                        shutil.rmtree(source)  # only after an intact destination exists
                verification = verify_archive(destination)
                native = json.loads(result_path.read_text())
                no_exception = native.get("exception_info") is None
                entry.update(status="complete", verification=verification,
                    harbor_exception=None if no_exception else native["exception_info"].get("exception_type", "HarborError"),
                    pipeline_passed=bool(no_exception and verification["pipeline_passed"]))
                atomic_json(trial / "artifacts/topogym-rollout.archived.json", {"archive": str(destination)})
            except (OSError, ValueError, KeyError) as error:
                entry.update(status="incomplete", pipeline_passed=False, error=type(error).__name__)
            if config["usage"]["mode"] != "off":
                usage_path = trial / "usage/snapshot.json"
                try:
                    ledger_path = trial / "usage/ledger.sqlite"
                    if ledger_path.is_file():
                        from topogym.agents.usage import UsageLedger
                        usage = UsageLedger(ledger_path).snapshot()
                    elif (run / "usage_sources.resolved.json").exists():
                        raise FileNotFoundError("New budgeted trials require the authoritative ledger")
                    else:
                        usage = json.loads(usage_path.read_text())  # legacy artifact compatibility
                    qualified = bool(usage["closed"] and usage["usage_complete"]
                        and usage["budget_qualified"] and not usage["stop"])
                    failure = usage.get("failure_reason") or (None if qualified else "usage_incomplete")
                except (OSError, ValueError, KeyError):
                    usage, qualified, failure = None, False, "usage_unavailable"
                entry.update(usage=usage, budget_qualified=qualified, failure_reason=failure)
                binding_path = trial / "usage/binding.json"
                if binding_path.exists():
                    entry["usage_binding"] = json.loads(binding_path.read_text())
                entry["usage_by_route"] = (usage or {}).get("by_route", {})
                if not qualified:
                    entry["pipeline_passed"] = False
                    # A lost container still has an explicit host failure result.
                    verification = dict(entry.get("verification", {}))
                    verification.update(reward=0, pipeline_passed=False, outcome="failed",
                        failure_reason=failure, budget_qualified=False, token_budget_enforced=True,
                        usage=usage, evidence_complete=verification.get("evidence_complete", False))
                    entry["verification"] = verification
                stop_path = trial / "usage/stop.json"
                if stop_path.exists():
                    entry["stop_timings"] = json.loads(stop_path.read_text())
            atomic_json(index_path, index)
        index.update(expected_trials=expected, collected_trials=len(index["trials"]),
            pipeline_passed=len(index["trials"]) == expected and all(
                e.get("pipeline_passed", False) for e in index["trials"].values()))
        atomic_json(index_path, index)
        return index
