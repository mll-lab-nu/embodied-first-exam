"""Per-task oracle regression through native Harbor, with explicit blocked coverage."""
from collections import Counter
import json
import os
from pathlib import Path
import sys
import time

from .catalog import inventory
from .contracts import BridgeError, read_json
from .packaging import check_package, package
from .verification import assess_trial, assess_smoke_trial

ROOT = Path(__file__).resolve().parents[3]


def save(path, document):
    path = Path(path)
    temporary = path.with_suffix(".tmp")
    temporary.write_text(json.dumps(document, indent=2, ensure_ascii=False) + "\n")
    temporary.replace(path)


def reference_for(row, references):
    """Explicit recipes override defaults; runner presence alone is insufficient."""
    task = Path(row["task"])
    if task.name in references:
        recipe = dict(references[task.name])
        allowed = {"kind", "trajectory", "source_instance", "entrypoint", "source_root", "includes", "kwargs", "data_files", "smoke_steps"}
        if set(recipe) - allowed:
            raise BridgeError("Unknown reference fields: " + str(sorted(set(recipe) - allowed)))
        return recipe
    if (task / "solution/bridge_manifest.json").is_file():
        return dict(kind="packaged")
    if row["mode"] == "standard":
        return dict(kind="privileged_output")
    callback = row.get("session_callback")
    if callback:
        recipe = dict(kind="session", entrypoint=callback, source_root=str(ROOT))
        if row["family"] != "cast_coil":
            recipe["kwargs"] = dict(variation=row["difficulty"])
        from .references import reference_data
        recipe["data_files"], recipe["includes"] = reference_data(ROOT, row["family"], row["difficulty"], row.get("seed", 0))
        return recipe
    if row["bridge"] == "existing_script_packable":
        return dict(kind="existing")
    raise BridgeError("No bound oracle recipe: supply --references or add a Session callback; local runner evidence is not a Harbor solution")


def prepare(output, *, tasks_root=None, families=(), tiers=("easy", "medium", "hard"),
            modes=("privileged", "standard"), references=None, candidate=False, harbor=None, nop=True,
            smoke_steps=None, wall_seconds=None):
    if smoke_steps is not None and (type(smoke_steps) is not int or not 1 <= smoke_steps <= 1000):
        raise BridgeError("smoke_steps must be an integer in [1, 1000]")
    if wall_seconds is not None and (not isinstance(wall_seconds, (int, float)) or wall_seconds <= 0):
        raise BridgeError("wall_seconds must be positive")
    sys.path.insert(0, str(ROOT / "scripts"))
    from topogym_versions import require_task, task_root, release, identity
    output = Path(output).resolve()
    output.mkdir(parents=True, exist_ok=False)
    release_error = None
    if tasks_root is None:
        try:
            tasks_root = task_root(ROOT)
        except ValueError as error:
            # Coverage-only baseline inventory. Every row remains blocked; no fallback execution.
            release_error = str(error)
            tasks_root = ROOT / release(ROOT, "published")["tasks_root"]
    tasks_root = Path(tasks_root).resolve()
    if not tasks_root.is_dir():
        raise BridgeError(f"Tasks root does not exist: {tasks_root}")
    rows = inventory(ROOT, tasks_root, tiers=tiers)["tasks"]
    rows = [row for row in rows if (not families or row["family"] in families) and row["mode"] in modes]
    if not rows:
        raise BridgeError("No tasks matched the selection")
    # A missing twin is missing coverage, never an implicitly passing mode.
    names = {Path(row["task"]).name for row in rows}
    for row in list(rows):
        for mode in modes:
            twin = Path(row["task"]).name.removesuffix("-" + row["mode"]) + "-" + mode
            if twin not in names:
                rows.append(dict(row, task=str(tasks_root / twin), mode=mode))
                names.add(twin)
    references = references or {}
    unknown = set(references) - {Path(row["task"]).name for row in rows}
    if unknown:
        raise BridgeError("Reference names outside the selected tasks: " + str(sorted(unknown)))
    document = dict(schema_version=1, status="planned", output=str(output), tasks_root=str(tasks_root),
                    release=identity(ROOT), candidate=candidate, harbor_qualified=False,
                    scope="native Harbor oracle grades; release activation and media qualification are separate",
                    harbor=str(harbor or ROOT / ".venv-harbor/bin/harbor"), nop=nop,
                    smoke_steps=smoke_steps, wall_seconds=wall_seconds, tasks=[])
    for row in sorted(rows, key=lambda r: (r["mode"] == "standard", r["task"])):
        entry = dict(task=row["task"], family=row["family"], difficulty=row["difficulty"], mode=row["mode"],
                     status="ready", grade=None, grade_one=False, errors=[], runs=[],
                     runners=row["runners"], session_callback=row["session_callback"], bridge=row["bridge"])
        try:
            if release_error:
                raise BridgeError(release_error)
            checked = require_task(row["task"], ROOT, registered=not candidate)
            entry["runtime_binding"] = checked["runtime_binding"]
            entry["reference"] = reference_for(row, references)
            if smoke_steps is not None and row["mode"] == "privileged":
                if entry["reference"]["kind"] != "session":
                    raise BridgeError("Connectivity smoke requires a real Session callback")
                entry["reference"]["smoke_steps"] = smoke_steps
            if entry["reference"]["kind"] == "packaged":
                check_package(row["task"])
        except (BridgeError, OSError, ValueError, KeyError) as error:
            entry.update(status="blocked", errors=[str(error)])
        document["tasks"].append(entry)
    summarize(document)
    save(output / "plan.json", document)
    save(output / "results.json", document)
    return document


def summarize(document):
    document["counts"] = dict(Counter(row["status"] for row in document["tasks"]))
    document["grade_one_count"] = sum(row["grade_one"] for row in document["tasks"])
    document["all_passed"] = bool(document["tasks"]) and all(row["status"] == "passed" for row in document["tasks"])
    document["connectivity_all_passed"] = bool(document.get("smoke_steps")) and bool(document["tasks"]) and all(
        row["status"] == "smoke_passed" for row in document["tasks"])


def execute(document):
    from topogym.utils.process_limits import run_guarded
    sys.path.insert(0, str(ROOT / "scripts"))
    from topogym_versions import require_task, identity
    output = Path(document["output"])
    document["status"] = "running"
    completed = {}
    halted = False
    deadline = time.monotonic() + document["wall_seconds"] if document.get("wall_seconds") else None
    for index, entry in enumerate(document["tasks"]):
        task = Path(entry["task"])
        if entry["status"] == "blocked":
            continue
        if deadline is not None and time.monotonic() >= deadline:
            entry.update(status="not_run", errors=["Connectivity test wall-clock budget exhausted"])
            continue
        if halted:
            entry.update(status="not_run", errors=["Queue stopped after an infrastructure or evidence failure"])
            continue
        try:
            if identity(ROOT) != document["release"]:
                raise BridgeError("Active source changed after planning; create a new suite")
            checked = require_task(task, ROOT, registered=not document["candidate"], inspect_docker=True)
            if checked["runtime_binding"] != entry["runtime_binding"]:
                raise BridgeError("Task runtime changed after planning")
            recipe = dict(entry["reference"])
            if recipe["kind"] == "privileged_output":
                previous = completed.get(task.name.removesuffix("-standard") + "-privileged")
                accepted_prefix = previous and document.get("smoke_steps") and previous["status"] == "smoke_passed"
                if not previous or not (previous["grade_one"] or accepted_prefix):
                    entry.update(status="blocked_dependency", errors=["No grade-1 privileged trajectory for this exact twin"])
                    continue
                recipe = dict(kind="public_trajectory", trajectory=previous["runs"][0]["trajectory"],
                              source_instance=str(Path(previous["task"]) / "environment/instance.json"))
            if recipe["kind"] != "packaged":
                packaged = package(task, output / "candidates", runtime_lock=entry["runtime_binding"], **recipe)
                task = Path(packaged["task"])
            check_package(task)
            entry["candidate_task"] = str(task)
            entry["status"] = "running"
            summarize(document)
            save(output / "results.json", document)
            for agent in (("oracle", "nop") if document["nop"] else ("oracle",)):
                name = f"{index + 1:03d}-{agent}"
                command = [document["harbor"], "run", "-p", str(task), "-a", agent, "-n", "1", "-k", "1",
                           "--max-retries", "0", "-o", str(output / "jobs"), "--job-name", name]
                log = output / "supervision" / name
                log.mkdir(parents=True)
                save(log / "command.json", command)
                print(f"{task.name} / {agent}: {log / 'runtime.log'}", flush=True)
                require_task(task, ROOT, registered=not document["candidate"], inspect_docker=True)
                check_package(task)
                supervised = command
                if deadline is not None:
                    remaining = max(1, int(deadline - time.monotonic()))
                    supervised = ["timeout", "--signal=INT", "--kill-after=30", str(remaining), *command]
                code = run_guarded(supervised, log, cwd=ROOT, env=dict(os.environ))
                if document.get("smoke_steps") and agent == "oracle":
                    assessment = assess_smoke_trial(output / "jobs" / name, task, entry["mode"], entry["runtime_binding"],
                                                    steps=document["smoke_steps"], returncode=code)
                else:
                    assessment = assess_trial(output / "jobs" / name, task, entry["mode"], entry["runtime_binding"],
                                              agent=agent, returncode=code)
                entry["runs"].append(dict(agent=agent, command=command, **assessment))
                # Detect image/input mutation during the job before accepting its evidence.
                require_task(task, ROOT, registered=not document["candidate"], inspect_docker=True)
                check_package(task)
                if agent == "oracle":
                    entry.update(status=assessment["status"], grade=assessment["grade"], grade_one=assessment["grade_one"])
                elif assessment["status"] != "passed":
                    entry["status"] = "control_failed"
                summarize(document)
                save(output / "results.json", document)
                if assessment["status"] in ("infra_failed", "evidence_failed"):
                    halted = True
                    break
            completed[Path(entry["task"]).name] = entry
        except (BridgeError, OSError, ValueError, KeyError) as error:
            entry.update(status="blocked", grade_one=False, errors=[str(error)])
        finally:
            summarize(document)
            save(output / "results.json", document)
    document["status"] = "complete"
    summarize(document)
    save(output / "results.json", document)
    return 0 if document["all_passed"] or document["connectivity_all_passed"] else 1
