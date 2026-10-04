"""Sequential native Harbor oracle/nop jobs with explicit outputs and resource supervision."""
from __future__ import annotations

import json
import os
from pathlib import Path
import tomllib

from .catalog import TIERS, task_difficulty
from .contracts import BridgeError, read_json
from .packaging import check_package


def require_bound_candidate(task, *, inspect_docker=False):
    import sys
    root = Path(__file__).resolve().parents[3]
    sys.path.insert(0, str(root / "scripts"))
    from topogym_versions import require_task
    from .binding import check_lock_for_task
    recipe = read_json(Path(task) / "solution/bridge_manifest.json")
    lock = recipe.get("runtime_binding")
    if lock is None:
        raise BridgeError("Formal jobs require a runtime binding; unbound packages are development artifacts")
    require_task(task, root, inspect_docker=inspect_docker, registered=True)
    check_lock_for_task(task, lock, inspect_docker=inspect_docker)
    sub = "environment/sim" if recipe["mode"] == "standard" else "environment"
    for relative in (sub + "/runtime_binding.json", "tests/runtime_binding.json"):
        path = Path(task) / relative
        if not path.is_file() or read_json(path) != lock:
            raise BridgeError("Simulator and verifier must both contain the selected runtime binding: " + relative)
    return lock


def plan(tasks, output, harbor, agents=("oracle", "nop"), *, tiers=None):
    output = Path(output).resolve()
    if output.exists():
        raise BridgeError("Batch output already exists; use a new directory to retain previous evidence")
    if not tasks or len(set(map(str, tasks))) != len(tasks):
        raise BridgeError("Choose at least one unique candidate task")
    if not agents or set(agents) - {"oracle", "nop"} or len(set(agents)) != len(agents):
        raise BridgeError("Batch supports unique native oracle/nop agents only")
    if tiers is not None and (not tiers or set(tiers) - set(TIERS)):
        raise BridgeError("Select known difficulty tiers")
    jobs = []
    for task in tasks:
        checked = check_package(task)
        lock = require_bound_candidate(task)
        metadata = tomllib.loads((Path(checked["task"]) / "task.toml").read_text())["metadata"]
        difficulty = task_difficulty(checked["task"], metadata)
        if tiers is not None and difficulty not in tiers:
            raise BridgeError(f"Task difficulty {difficulty!r} is outside selected tiers {list(tiers)}: {task}")
        for agent in agents:
            name = f"{len(jobs) + 1:03d}-{agent}"
            jobs.append(dict(name=name, task=checked["task"], mode=checked["mode"], agent=agent, difficulty=difficulty,
                runtime_binding=lock,
                command=[str(harbor), "run", "-p", checked["task"], "-a", agent,
                         "-n", "1", "-k", "1", "-o", str(output / "jobs"), "--job-name", name]))
    return dict(schema_version=1, output=str(output), jobs=jobs, harbor_qualified=False,
                selected_tiers=list(tiers) if tiers is not None else None,
                note="No model credentials or random-instance sampling; each task is a bound candidate")


def assess_job(path, agent, returncode):
    files = list(Path(path).glob("*/result.json"))
    if returncode != 0 or len(files) != 1:
        return dict(status="infra_failed", returncode=returncode, trial_results=len(files))
    result = read_json(files[0])
    rewards = (result.get("verifier_result") or {}).get("rewards") or {}
    if (result.get("exception_info") or not result.get("finished_at")
            or rewards.get("success") not in (0, 1)
            or any(rewards.get(k, 0) for k in ("grader_error", "infra_error", "gpu_lost", "instance_mismatch"))):
        status = "infra_failed"
    elif rewards["success"] != (1 if agent == "oracle" else 0):
        status = "unexpected_score"
    elif agent == "oracle" and (rewards.get("runtime_binding_ok") != 1 or
            (rewards.get("instance_exact", rewards.get("runtime_binding_ok")) != 1)):
        status = "unbound_result"
    else:
        status = "expected_score"
    return dict(status=status, rewards=rewards, result=str(files[0]))


def execute(plan_document):
    from topogym.utils.process_limits import run_guarded
    # Check every image before starting any job. Never fall back to another tag.
    for job in plan_document["jobs"]:
        lock = require_bound_candidate(job["task"], inspect_docker=True)
        if lock != job["runtime_binding"]:
            raise BridgeError("Runtime binding changed after planning")
    output = Path(plan_document["output"])
    output.mkdir(parents=True, exist_ok=False)
    (output / "plan.json").write_text(json.dumps(plan_document, indent=2) + "\n")
    results = []
    for job in plan_document["jobs"]:
        check_package(job["task"])
        logs = output / "supervision" / job["name"]
        logs.mkdir(parents=True)
        code = run_guarded(job["command"], logs, cwd=Path(job["task"]).parent, env=dict(os.environ))
        require_bound_candidate(job["task"], inspect_docker=True)
        assessed = assess_job(output / "jobs" / job["name"], job["agent"], code)
        results.append(dict(name=job["name"], **assessed))
        (output / "results.json").write_text(json.dumps(dict(results=results, harbor_qualified=False,
            scope="job scores only; media, isolation and both-mode qualification still require review"), indent=2) + "\n")
        if assessed["status"] != "expected_score":
            return 1
    return 0
