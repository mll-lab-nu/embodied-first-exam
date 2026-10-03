"""Sequential native Harbor oracle/nop jobs with explicit outputs and resource supervision."""
from __future__ import annotations

import json
import os
from pathlib import Path
import tomllib

from .catalog import TIERS, task_difficulty
from .contracts import BridgeError, read_json
from .packaging import check_package


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
        metadata = tomllib.loads((Path(checked["task"]) / "task.toml").read_text())["metadata"]
        difficulty = task_difficulty(checked["task"], metadata)
        if tiers is not None and difficulty not in tiers:
            raise BridgeError(f"Task difficulty {difficulty!r} is outside selected tiers {list(tiers)}: {task}")
        for agent in agents:
            name = f"{len(jobs) + 1:03d}-{agent}"
            jobs.append(dict(name=name, task=checked["task"], mode=checked["mode"], agent=agent, difficulty=difficulty,
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
    else:
        status = "expected_score"
    return dict(status=status, rewards=rewards, result=str(files[0]))


def execute(plan_document):
    from topogym.utils.process_limits import run_guarded
    output = Path(plan_document["output"])
    output.mkdir(parents=True, exist_ok=False)
    (output / "plan.json").write_text(json.dumps(plan_document, indent=2) + "\n")
    results = []
    for job in plan_document["jobs"]:
        check_package(job["task"])
        logs = output / "supervision" / job["name"]
        logs.mkdir(parents=True)
        code = run_guarded(job["command"], logs, cwd=Path(job["task"]).parent, env=dict(os.environ))
        assessed = assess_job(output / "jobs" / job["name"], job["agent"], code)
        results.append(dict(name=job["name"], **assessed))
        (output / "results.json").write_text(json.dumps(dict(results=results, harbor_qualified=False,
            scope="job scores only; media, isolation and both-mode qualification still require review"), indent=2) + "\n")
        if assessed["status"] != "expected_score":
            return 1
    return 0
