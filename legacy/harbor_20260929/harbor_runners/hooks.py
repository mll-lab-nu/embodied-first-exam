"""Post-job retention/recovery using containers labelled by our generated tasks.

Harbor's native keep_containers stops the trial without deleting its writable
layer. We delete only stopped, labelled containers after every export is verified.
"""
import hashlib
import json
from pathlib import Path
import subprocess


def run_label(run):
    return "io.topogym.run=" + hashlib.sha256(str(Path(run).resolve()).encode()).hexdigest()


def _docker(*args):
    result = subprocess.run(["docker", *args], capture_output=True, text=True, timeout=60)
    if result.returncode:
        raise RuntimeError("Docker archive recovery/cleanup failed; retained containers were not force-removed")
    return result.stdout


def recover(run):
    """Retry a missing/partial native download from its stopped trial container."""
    from harbor.environments.docker.docker import _sanitize_docker_compose_project_name
    run = Path(run)
    containers = _docker("ps", "-aq", "--filter", "label=" + run_label(run)).split()
    for identity in containers:
        info = json.loads(_docker("inspect", identity))[0]
        if info["State"]["Running"]:
            continue
        project = info["Config"]["Labels"]["com.docker.compose.project"]
        for trial in (run / "jobs/job").iterdir():
            if not trial.is_dir() or not (trial / "result.json").exists():
                continue
            if project != _sanitize_docker_compose_project_name(trial.name + "__env"):
                continue
            source = trial / "artifacts/topogym-rollout"
            if (trial / "artifacts/topogym-rollout.archived.json").exists():
                continue
            # Preserve a failed download for diagnosis; never overwrite it in place.
            if source.exists():
                from .collect import verify_archive
                try:
                    verify_archive(source)
                    continue
                except (OSError, ValueError, KeyError):
                    pass
                from uuid import uuid4
                source.rename(source.with_name("topogym-rollout.partial-" + uuid4().hex))
            source.mkdir(parents=True)
            _docker("cp", identity + ":/trial/rollout/.", str(source))


def cleanup(run, index):
    complete = (index.get("collected_trials") == index.get("expected_trials")
                and bool(index.get("trials")) and all(
                    item.get("status") == "complete" for item in index["trials"].values()))
    if not complete:
        return {"status": "retained", "reason": "exports_not_all_verified"}
    label = "label=" + run_label(run)
    containers = _docker("ps", "-aq", "--filter", label).split()
    for identity in containers:
        info = json.loads(_docker("inspect", identity))[0]
        if info["State"]["Running"]:
            return {"status": "retained", "reason": "container_still_running"}
    for identity in containers:
        _docker("rm", "-v", identity)  # no --force and no shared-image removal
    networks = _docker("network", "ls", "-q", "--filter", label).split()
    for identity in networks:
        _docker("network", "rm", identity)
    return {"status": "removed", "containers": len(containers), "networks": len(networks)}
