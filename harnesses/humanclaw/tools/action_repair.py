#!/usr/bin/env python3
"""Prepare and run a selective action-parser repair campaign without editing old runs.

The input is the audited, last-attempt-per-episode table, not a success filter.
All outputs go under an explicitly selected, user-owned experiments directory.
"""
from __future__ import annotations

import argparse
import ast
from collections import Counter, defaultdict
from copy import deepcopy
import csv
from concurrent.futures import ThreadPoolExecutor
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import time
import uuid
from urllib.parse import unquote

CAMPAIGN = "action-repair-azure-20261021"
EXPECTED = {"codex_r1": (922, 920), "codex_r2": (547, 543), "codex_r3": (468, 468)}
OLD_ROOT = Path("/gscratch/scrubbed/linjli/humanclaw/experiments")
OWN_ROOT = Path("/gscratch/scrubbed/hengyil6/humanclaw-analysis/experiments")
OWN_DATA_ROOT = Path("/gscratch/stf/hengyil6/data/humanclaw-hssd-val41")
AZURE = "https://ai-thopo-9134.services.ai.azure.com/openai/v1"
FIX_FILES = ("agent/skills.py", "harnesses/environment.py", "motion/runner.py",
             "motion/conditioning.py", "experiments/integration.py")
WORKER_SOURCE = Path(__file__).read_bytes()


def read(path):
    return json.loads(Path(path).read_text())


def digest(path):
    h = hashlib.sha256()
    with Path(path).open("rb") as f:
        for block in iter(lambda: f.read(1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()


def write(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name + ".tmp-" + uuid.uuid4().hex)
    temporary.write_text(json.dumps(value, indent=2, ensure_ascii=False, allow_nan=False) + "\n")
    os.replace(temporary, path)


def build_plan(mismatches, diagnostics, own_root=OWN_ROOT):
    with Path(mismatches).open() as f:
        rows = list(csv.DictReader(f))
    grouped = defaultdict(list)
    for row in rows:
        if row["label"] not in EXPECTED:
            raise ValueError("Unexpected cohort in explicit-mismatch audit")
        grouped[row["label"], row["shard"]].append(row)
    with Path(diagnostics).open() as f:
        selected = {}
        for row in csv.DictReader(f):
            key = row["label"], row["shard"]
            if key in grouped:
                if key in selected:
                    raise ValueError(f"Ambiguous selected attempt: {key}")
                selected[key] = row
    counts = {c: (sum(len(v) for k, v in grouped.items() if k[0] == c),
                  sum(k[0] == c for k in grouped)) for c in EXPECTED}
    if counts != EXPECTED or set(grouped) != set(selected):
        raise ValueError(f"Audit selection/count mismatch: {counts}")
    entries = []
    for index, (key, errors) in enumerate(sorted(grouped.items())):
        row = selected[key]
        original = Path(row["run"])
        relative = original.relative_to(OLD_ROOT)
        if relative.parts[1:3] != ("results", key[1]):
            raise ValueError("Run/shard mismatch")
        for error in errors:
            if not Path(error["transcript_path"]).is_relative_to(original):
                raise ValueError("Mismatch evidence belongs to another attempt")
        entries.append({
            "index": index, "cohort": key[0], "shard": key[1],
            "suite": relative.parts[0], "original_run": str(original),
            "local_copy_run": str(Path(own_root) / relative),
            "destination": str(Path(own_root) / relative.parts[0] / CAMPAIGN / "results" / key[1]),
            "scene": row["scene"], "episode": row["episode"], "target": row["target"],
            "mismatches": [{k: e[k] for k in ("step_1based", "tool", "raw_action", "applied_action",
                                               "explicit_intent", "applied", "native_line")} for e in errors],
        })
    return {"schema": "humanclaw_action_repair_plan_v1", "campaign": CAMPAIGN,
            "destination_root": str(own_root), "expected_counts": counts,
            "inputs": {"mismatches_sha256": digest(mismatches), "diagnostics_sha256": digest(diagnostics)},
            "provider_change": {"from": "Copilot/Magpie", "to": "Azure OpenAI", "model": "gpt-6-astra"},
            "writes_to_original_runs": False, "entries": entries}


def audit(plan_path):
    """Pin server manifests and locate the source variants before any paid work."""
    plan = read(plan_path)
    own = Path(plan["destination_root"]).resolve()
    groups = {}
    def inspect(entry):
        # Use the exact audited source attempt. Restored copies on scrubbed can
        # be cold/partial; output placement is independent of this read-only input.
        source = Path(entry["original_run"])
        content = (source / "run.json").read_bytes()
        manifest = json.loads(content)
        return entry, source, manifest, hashlib.sha256(content).hexdigest()

    with ThreadPoolExecutor(max_workers=8) as pool:
      for entry, source, manifest, manifest_sha in pool.map(inspect, plan["entries"]):
        destination = Path(entry["destination"]).resolve()
        if not destination.is_relative_to(own) or destination.is_relative_to(OLD_ROOT.resolve()):
            raise ValueError("Repair destination must remain inside the user's output root")
        md = manifest["metadata"]
        if md["harness"] != "codex" or str(md["episode_id"]) != entry["episode"]:
            raise ValueError("Selected manifest identity does not match the audit")
        fingerprint = md["source"]["files_sha256"]
        entry.update(source_run=str(source), old_run_id=manifest["run_id"],
                     old_run_sha256=manifest_sha, source_variant=fingerprint,
                     reasoning_effort=md["harness_config"]["reasoning_effort"],
                     max_images_per_request=md["harness_config"].get("max_images_per_request"))
        if fingerprint not in groups:
            groups[fingerprint] = {"source": str(OLD_ROOT / entry["suite"] / "source"),
                                   "sample_run": str(source), "files": md["source"]["files"],
                                   "commit": md["source"].get("commit"), "entries": 0}
        groups[fingerprint]["entries"] += 1
        if entry["index"] % 200 == 0:
            print(json.dumps({"audited": entry["index"] + 1}), flush=True)
    plan["source_variants"] = groups
    write(Path(plan_path).with_name("audited_plan.json"), plan)
    return {"episodes": len(plan["entries"]), "variants": [
        {k: v for k, v in group.items() if k != "files"} | {"fingerprint": key}
        for key, group in groups.items()]}


def replace_function(text, replacement, name, owner=None):
    """Replace one complete function, retaining every unrelated source byte."""
    def locate(code):
        nodes = ast.parse(code).body
        if owner:
            nodes = next(n for n in nodes if isinstance(n, ast.ClassDef) and n.name == owner).body
        return next(n for n in nodes if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef)) and n.name == name)
    before, after = locate(text), locate(replacement)
    lines, new = text.splitlines(keepends=True), replacement.splitlines(keepends=True)
    return "".join(lines[:before.lineno - 1] + new[after.lineno - 1:after.end_lineno] + lines[before.end_lineno:])


def patch_source(root, fix_root):
    """Backport execution fixes without copying model-visible prompt changes."""
    root, fix_root = Path(root), Path(fix_root)
    package = root / "src/humanclaw_bench"
    before = {name: (package / name).read_text() for name in FIX_FILES}
    fixed = {name: (fix_root / name).read_text() for name in FIX_FILES}
    result = dict(before)
    for symbol in ("SkillCall", "skill_to_text"):
        def ast_symbol(code):
            return ast.dump(next(n for n in ast.parse(code).body if getattr(n, "name", None) == symbol))
        if ast_symbol(before["agent/skills.py"]) != ast_symbol(fixed["agent/skills.py"]):
            raise ValueError(f"Unrelated skill schema changed: {symbol}")
    result["agent/skills.py"] = fixed["agent/skills.py"]
    name = "harnesses/environment.py"
    result[name] = replace_function(before[name], fixed[name], "call", "EnvironmentBridge")
    marker = "from humanclaw_bench.agent.skills import normalize_action"
    if result[name].count(marker) != 1:
        raise ValueError("Unexpected native bridge import")
    result[name] = result[name].replace(marker, marker.replace("import ", "import ACTION_PARSER_VERSION, "))
    result["motion/runner.py"] = replace_function(before["motion/runner.py"], fixed["motion/runner.py"],
                                                  "generate", "MotionSkillRunner")
    name = "motion/conditioning.py"
    result[name] = replace_function(before[name], fixed[name], "condition_args")
    result[name] = result[name].replace("import pickle\n", "import pickle\nimport math\n", 1)
    name = "experiments/integration.py"
    marker = '        **native,\n'
    if before[name].count(marker) != 1:
        raise ValueError("Unexpected run metadata construction")
    result[name] = before[name].replace(marker, marker +
        '        "action_parser_version": "humanclaw-action-parser-v2",\n'
        '        "action_repair": evaluator.config.get("action_repair"),\n')
    for name, text in result.items():
        ast.parse(text)
        (package / name).write_text(text)
    return {name: {"before": hashlib.sha256(before[name].encode()).hexdigest(),
                   "after": digest(package / name)} for name in FIX_FILES}


def prepare(plan_path, fix_root):
    """Reconstruct recorded code hashes and isolate the small backport per version."""
    plan_path, fix_root = Path(plan_path), Path(fix_root)
    plan = read(plan_path)
    control = plan_path.parent
    for key, group in plan["source_variants"].items():
        target = control / "sources" / key[:16]
        receipt = target / "repair_source.json"
        if receipt.is_file():
            group["prepared_source"] = str(target)
            continue
        target.mkdir(parents=True, exist_ok=False)
        origin = Path(group["source"])
        # Prefer bytes whose hash matches the actual recorded run. The source
        # symlink can have moved since a campaign began; use Git only if needed.
        for name, expected in group["files"].items():
            rel = Path(name)
            if rel.is_absolute() or ".." in rel.parts or rel.parts[0] not in {"src", "configs"}:
                raise ValueError("Unsafe recorded source path")
            source = origin / rel
            content = source.read_bytes() if source.is_file() else b""
            if hashlib.sha256(content).hexdigest() != expected:
                content = subprocess.check_output(["git", "show", f"{group['commit']}:{name}"],
                                                  cwd=origin, stderr=subprocess.PIPE)
            if hashlib.sha256(content).hexdigest() != expected:
                raise ValueError(f"Cannot recover recorded source: {key[:16]} {name}")
            destination = target / rel
            destination.parent.mkdir(parents=True, exist_ok=True)
            destination.write_bytes(content)
        shutil.copy2(origin / "pyproject.toml", target / "pyproject.toml")
        physics = "src/humanclaw_bench/envs/half_physics/humanclaw.physics_config.json"
        shutil.copy2(origin / physics, target / physics)
        for asset in ("resources", "weights", "data"):
            (target / asset).symlink_to((origin / asset).resolve(), target_is_directory=True)
        patch = patch_source(target, fix_root)
        # The native runner, proxy, prompts and declarations remain exactly the
        # recorded version. Only the five allowlisted execution/metadata files differ.
        after = {n: digest(target / n) for n in group["files"]}
        changed = {n for n in after if after[n] != group["files"][n]}
        if changed != {"src/humanclaw_bench/" + n for n in FIX_FILES}:
            raise ValueError(f"Unexpected repair scope: {changed}")
        write(receipt, {"base_commit": group["commit"], "original_source_digest": key,
                        "fix_commit": "be8c4e4f8f9d19050ae99ec1ff8399334b5e1be1",
                        "files": after, "patch": patch, "preserved_native_decision_flow": True})
        group["prepared_source"] = str(target)
        print(json.dumps({"prepared_source": str(target), "episodes": group["entries"]}), flush=True)
    plan["prepared_at_unix"] = time.time()
    write(control / "prepared_plan.json", plan)
    return {"prepared_variants": len(plan["source_variants"]), "episodes": len(plan["entries"])}


def azure_settings(metadata, wrapper):
    """Preserve experiment settings; change only the authorized provider and launcher path."""
    model = deepcopy(metadata["model_config"])
    for key in ("base_url_env", "model_env", "api_key", "azure_endpoint", "api_version"):
        model.pop(key, None)
    model.update(backend="openai_compatible", model="gpt-6-astra", base_url=AZURE + "/",
                 api_key_env="AZURE_OPENAI_API_KEY", require_api_key=True)
    native = deepcopy(metadata["harness_config"])
    native.pop("responses_base_url_env", None)
    native.update(responses_base_url=AZURE, api_key_env="AZURE_OPENAI_API_KEY",
                  auth="azure", allow_http=False, codex_command=[str(wrapper), "app-server"])
    return model, native


def verify_evidence(entry):
    """Match every audited rewrite to the original normalization span before rerunning."""
    expected = {(int(m["step_1based"]) - 1, m["raw_action"], m["applied_action"]) for m in entry["mismatches"]}
    pending, found = {}, {}
    with (Path(entry["source_run"]) / "events.jsonl").open() as events:
        for line in events:
            # Most errors occur in the first action. Avoid parsing unrelated
            # model payloads and stop as soon as all selected evidence is found.
            if '"action.normalize"' not in line:
                continue
            e = json.loads(line)
            if e.get("name") != "action.normalize":
                continue
            if e["event"] == "span.start":
                pending[e["span_id"]] = (e["step"], e["data"]["input"]["action_name"], e["event_id"])
            elif e["event"] == "span.end" and e["data"].get("status") == "completed":
                step, raw, start_id = pending[e["span_id"]]
                key = step, raw, e["data"]["output"]["action_name"]
                if key in expected:
                    found[key] = {"span_id": e["span_id"], "start_event_id": start_id, "end_event_id": e["event_id"]}
                if set(found) == expected:
                    return list(found.values())
    raise ValueError("Audited action rewriting was not found in the selected original trace")


def relocate_episode(metadata, saved_replay, dataset_root=OWN_DATA_ROOT):
    """Rebind only scene paths, requiring the original recorded asset hashes."""
    episode = deepcopy(metadata["episode"])
    assets = saved_replay["assets"]
    old_root = Path(assets["scene_dataset_config"]["path"]).parent
    relocations = []
    for field, asset_name in (("scene_dataset_config", "scene_dataset_config"),
                              ("scene_id", "scene_instance")):
        identity = assets[asset_name]
        old = Path(identity["path"])
        if str(old) != episode[field] or not identity.get("sha256"):
            raise ValueError("Frozen scene identity does not match its replay manifest")
        relative = old.relative_to(old_root)
        if ".." in relative.parts:
            raise ValueError("Unsafe scene asset path")
        destination = (Path(dataset_root) / relative).resolve()
        if not destination.is_relative_to(Path(dataset_root).resolve()):
            raise ValueError("Scene asset escapes the owned dataset")
        if digest(destination) != identity["sha256"]:
            raise ValueError(f"Owned scene asset differs from the original: {asset_name}")
        episode[field] = str(destination)
        relocations.append({"field": field, "asset": asset_name, "original": str(old),
                            "replacement": str(destination), "sha256": identity["sha256"]})
    return episode, relocations


def replace_validated_if_enabled(plan_path, index):
    """Apply the user's optional post-validation replacement policy idempotently."""
    plan_path = Path(plan_path)
    control = plan_path.parent
    policy = control / "replacement_policy.json"
    if policy.exists() and read(policy).get("replace_owned_results"):
        subprocess.run([sys.executable, str(control / "action_repair_replace.py"),
                        str(plan_path), "--index", str(index), "--apply"], check=True)


def parse_shared_fileset_capacity(output, fileset):
    """Include shared reservations, not only this user's remaining quota."""
    header, matches = None, []
    for line in output.splitlines():
        fields = [unquote(value) for value in line.split(":")]
        if len(fields) < 4 or fields[:2] != ["mmlsquota", "fileset"]:
            continue
        if fields[2] == "HEADER":
            header = fields
        elif header:
            row = dict(zip(header, fields))
            if row.get("quotaType") == "FILESET" and row.get("name") == fileset:
                matches.append(row)
    if len(matches) != 1:
        raise OSError(f"Cannot verify shared fileset quota for {fileset}")
    row = matches[0]
    def remaining(usage, reserved, soft, hard, factor):
        values = [int(row[key]) for key in (usage, reserved, soft, hard)]
        if any(value < 0 for value in values):
            raise ValueError("Negative quota counter")
        limits = [value for value in values[2:] if value > 0]
        return max(0, min(limits) - values[0] - values[1]) * factor if limits else None
    return {"fileset": fileset,
            "free_bytes": remaining("blockUsage", "blockInDoubt", "blockQuota", "blockLimit", 1024),
            "free_files": remaining("filesUsage", "filesInDoubt", "filesQuota", "filesLimit", 1),
            "in_doubt_bytes": int(row["blockInDoubt"]) * 1024}


def check_shared_fileset_storage():
    """Fail before paid work when the shared pool cannot meet the reserve."""
    fileset = os.environ.get("HUMANCLAW_GPFS_FILESET", "sata1-scrubbed")
    output = subprocess.check_output([
        os.environ.get("HUMANCLAW_MMLSQUOTA", "/usr/lpp/mmfs/bin/mmlsquota"),
        "-j", fileset, "-Y", os.environ.get("HUMANCLAW_GPFS_FILESYSTEM", "gpfs"),
    ], text=True, stderr=subprocess.PIPE, timeout=30)
    capacity = parse_shared_fileset_capacity(output, fileset)
    for kind, default in (("bytes", 20 * 1024**3), ("files", 20000)):
        reserve = int(os.environ.get("HUMANCLAW_MIN_FREE_" + kind.upper(), default))
        if reserve < 0:
            raise ValueError("Storage reserve must not be negative")
        free = capacity["free_" + kind]
        if free is not None and free < reserve:
            raise OSError(f"Insufficient shared fileset capacity: {free} {kind}; reserve {reserve}. {json.dumps(capacity)}")
    return capacity


def infrastructure_retry_authorization(control, entry):
    """One extra attempt only after a recorded, matching provider-limit repair."""
    path = Path(control) / "infrastructure_retry_authorizations.json"
    authorization = read(path).get(str(entry["index"])) if path.exists() else None
    if authorization is None:
        return None
    if (authorization.get("max_attempts") != 4
            or authorization.get("cause") != "provider_rate_limit"
            or authorization.get("old_run_sha256") != entry["old_run_sha256"]
            or authorization.get("remediation_sha256") != digest(Path(control) / "action_repair_rate_limit.py")
            or not authorization.get("investigation")):
        raise ValueError("Invalid additional infrastructure retry authorization")
    return authorization


def worker(plan_path, index):
    """One fresh attempt per allocation. No writes to the selected original run."""
    import fcntl
    plan_path = Path(plan_path).resolve()
    plan = read(plan_path)
    entry = plan["entries"][index]
    if entry["index"] != index:
        raise ValueError("Index mismatch")
    control = plan_path.parent
    source = Path(plan["source_variants"][entry["source_variant"]]["prepared_source"])
    os.environ["HUMANCLAW_BENCH_HOME"] = str(source)
    sys.path.insert(0, str(source / "src"))
    os.environ["PYTHONDONTWRITEBYTECODE"] = "1"
    sys.dont_write_bytecode = True
    # A cold/stalled shared-filesystem .pyc must not serialize every GPU's
    # startup. Read the identical .py sources, without changing dependencies or
    # writing/replacing caches in the shared environment.
    sys.pycache_prefix = "/tmp/hc-repair-pycache-" + str(os.getuid()) + "-" + uuid.uuid4().hex
    receipt = read(source / "repair_source.json")
    for name, sha in receipt["files"].items():
        if digest(source / name) != sha:
            raise ValueError(f"Frozen repaired source changed: {name}")
    destination = Path(entry["destination"]).resolve()
    own = Path(plan["destination_root"]).resolve()
    old = Path(entry["source_run"]).resolve()
    if not destination.is_relative_to(own) or destination.is_relative_to(old) or old.is_relative_to(destination):
        raise ValueError("Unsafe output location")
    destination.mkdir(parents=True, exist_ok=True)
    with (destination / "allocation.lock").open("a") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        if (destination / "validated_result.json").is_file():
            replace_validated_if_enabled(plan_path, index)
            print(json.dumps({"status": "already_validated", "index": index}))
            return
        if digest(old / "run.json") != entry["old_run_sha256"]:
            raise ValueError("Original selected attempt changed since preparation")
        attempts = list(destination.glob("attempt-*"))
        retry_authorization = infrastructure_retry_authorization(control, entry)
        attempt_limit = retry_authorization["max_attempts"] if retry_authorization else 3
        if len(attempts) >= attempt_limit:
            raise RuntimeError(f"{attempt_limit} attempts already exist; explicit investigation required")
        attempt = destination / ("attempt-" + uuid.uuid4().hex[:12])
        attempt.mkdir()
        (attempt / "worker.py").write_bytes(WORKER_SOURCE)
        status = {"index": index, "cohort": entry["cohort"], "shard": entry["shard"],
                  "source_run": str(old), "old_run_id": entry["old_run_id"],
                  "provider_change": plan["provider_change"], "started_at_unix": time.time(),
                  "attempt": str(attempt), "status": "preflight", "pid": os.getpid(),
                  "slurm_job": os.environ.get("SLURM_JOB_ID"),
                  "slurm_array_job": os.environ.get("SLURM_ARRAY_JOB_ID"),
                  "slurm_restart": os.environ.get("SLURM_RESTART_COUNT", "0"),
                  "worker_sha256": hashlib.sha256(WORKER_SOURCE).hexdigest()}
        status["startup_cache_policy"] = "read_python_sources_without_shared_pyc"
        if retry_authorization:
            status["infrastructure_retry_authorization"] = retry_authorization
        write(attempt / "allocation.json", status)
        try:
            run_attempt(plan, entry, source, attempt, status, control)
        except BaseException as exc:
            status.update(status="failed", error_type=type(exc).__name__, finished_at_unix=time.time())
            write(attempt / "allocation.json", status)
            raise
    # This is post-processing after the complete run has been closed and
    # validated. It never changes agent behavior or reruns a benchmark failure.
    replace_validated_if_enabled(plan_path, index)


def run_attempt(plan, entry, source, attempt, status, control):
    """Start the original evaluator with a frozen episode and measured Azure transport."""
    def stage(name):
        status["preflight_stage"] = name
        write(attempt / "allocation.json", status)
        print(json.dumps({"index": entry["index"], "stage": name}), flush=True)

    stage("import_dependencies")
    import socket
    from dotenv import dotenv_values
    from humanclaw_bench.config import load_config
    from humanclaw_bench.experiments.storage import check_storage
    from humanclaw_bench.experiments.replay import _frozen_episode
    from humanclaw_bench.evaluation.evaluator import HCFindNavInteractEvaluator
    import torch
    import habitat_sim  # fail before a model request if simulator dependencies are missing

    cooldown_config = control / "provider_rate_limit.json"
    if cooldown_config.exists():
        from action_repair_rate_limit import install
        cooldown_policy = read(cooldown_config)
        install(cooldown_policy, control)
        shutil.copy2(control / "action_repair_rate_limit.py", attempt / "provider_rate_limit.py")
        write(attempt / "provider_rate_limit.json", cooldown_policy)
        status["provider_rate_limit_policy"] = {
            **cooldown_policy, "implementation_sha256": digest(control / "action_repair_rate_limit.py"),
            "native_retry_count_unchanged": True, "request_payload_unchanged": True}

    stage("storage_and_evidence")
    status["storage"] = check_storage(attempt)
    status["shared_storage"] = check_shared_fileset_storage()
    verified_evidence = verify_evidence(entry)
    if not torch.cuda.is_available():
        raise RuntimeError("GPU allocation has no usable CUDA device")
    status["hardware"] = {"hostname": socket.gethostname(), "gpu": torch.cuda.get_device_name(0),
                          "torch": torch.__version__, "cuda": torch.version.cuda}
    # Credentials stay with the parent evaluator. The native child receives its
    # existing allowlisted environment and never sees this private file.
    secret = dotenv_values("/gscratch/stf/hengyil6/HumanCLAW/.env").get("AZURE_OPENAI_API_KEY")
    if not secret:
        raise RuntimeError("The user's Azure credential is missing")
    os.environ["AZURE_OPENAI_API_KEY"] = secret
    stage("freeze_configuration")
    old = Path(entry["source_run"])
    manifest = read(old / "run.json")
    metadata = manifest["metadata"]
    profile = deepcopy(metadata["profile"])
    saved_replay = read(old / "replay/replay_manifest.json")
    relocated_episode, relocations = relocate_episode(metadata, saved_replay)
    episode = _frozen_episode({**metadata, "episode": relocated_episode})
    for section in ("physics", "rendering"):
        profile[section] = {**profile.get(section, {}), **saved_replay.get(section, {})}
    for key in ("agent_urdf", "agent_shift_npy", "physics_config"):
        identity = saved_replay.get("assets", {}).get(key)
        if isinstance(identity, dict) and identity.get("path"):
            path = Path(identity["path"])
            if identity.get("sha256") and digest(path) != identity["sha256"]:
                raise ValueError(f"Saved asset changed: {key}")
            profile["physics"][key] = str(path)
    model, native = azure_settings(metadata, control / "codex_isolated.py")
    for name, value in (("profile", profile), ("model", model), ("harness", native)):
        write(attempt / f"{name}.json", value)
    lineage = {"campaign": CAMPAIGN, "cohort": entry["cohort"], "old_run_id": entry["old_run_id"],
               "original_run": entry["original_run"], "source_run_sha256": entry["old_run_sha256"],
               "mismatch_evidence": entry["mismatches"], "provider_change": plan["provider_change"],
               "verified_original_event_ids": verified_evidence,
               "original_source_digest": entry["source_variant"],
               "repair_source_receipt_sha256": digest(source / "repair_source.json"),
               "launcher_sha256": digest(control / "codex_isolated.py"),
               "worker_sha256": status["worker_sha256"],
               "startup_cache_policy": status.get("startup_cache_policy", "original_python_cache"),
               "shared_storage_preflight": status["shared_storage"],
               "provider_rate_limit_policy": status.get("provider_rate_limit_policy"),
               "asset_relocations": relocations,
               "changes": ["action parser and condition validation", "provider: Copilot/Magpie to Azure",
                           "runtime isolation paths for hengyil6 output", "repair provenance metadata",
                           "dataset paths rebound to SHA-256-identical owned copies"],
               "reasoning_effort": native["reasoning_effort"],
               "max_images_per_request": native.get("max_images_per_request"),
               "price_status": "unknown; original provider pricing is not reused"}
    config = {"profile": load_config(attempt / "profile.json"), "episode_override": episode,
              "model_config_path": str(attempt / "model.json"), "harness_config": str(attempt / "harness.json"),
              "output_root": str(attempt / "rollout"), "scene_id": episode.scene_id,
              "scene_dataset_config": episode.scene_dataset_config, "episode_id": episode.episode_id,
              "object_category": episode.object_category, "max_steps": episode.max_steps, "n_rollouts": 1,
              "harness": "codex", "seed": metadata["effective_seed"], "trace": True,
              "compute_metrics": metadata["compute_metrics"], "save_video": metadata["save_video"],
              "parent_run_id": entry["old_run_id"], "source_run": str(old), "action_repair": lineage}
    if metadata["config"].get("device") is not None:
        config["device"] = metadata["config"]["device"]
    write(attempt / "lineage.json", lineage)
    status.update(status="running", preflight_passed=True, preflight_stage="simulator_and_native_startup")
    write(attempt / "allocation.json", status)
    evaluator = HCFindNavInteractEvaluator(config)
    evaluator.check_config_valid()
    evaluator.evaluate_main()
    result = validate_attempt(attempt, metadata, relocations)
    write(attempt / "validation.json", result)
    if not result["ok"]:
        raise RuntimeError("Episode integrity validation did not pass")
    status.update(status="completed", finished_at_unix=time.time(), result=result)
    write(attempt / "allocation.json", status)
    write(attempt.parent / "validated_result.json", status)
    print(json.dumps({"index": entry["index"], "status": "completed", "run": result["run"],
                      "task_success": result["task_success"], "model_calls": result["model_calls"]}), flush=True)


def validate_attempt(attempt, original_metadata, relocations=()):
    """Validate both successful and failed benchmark outcomes, never select by success."""
    from humanclaw_bench.experiments.report import summarize_run, validate_trace
    from humanclaw_bench.agent.skills import normalize_action, ACTION_PARSER_VERSION
    runs = list((attempt / "rollout").glob("*/rollout_00/experiment_runs/*/run.json"))
    if len(runs) != 1:
        raise ValueError("Expected exactly one recorded episode")
    run = runs[0].parent
    manifest = read(runs[0])
    summary = summarize_run(run, write=True)
    trace = validate_trace(run)
    errors = []
    if manifest["status"] != "completed" or not isinstance(manifest["outcome"].get("task_success"), bool):
        errors.append("incomplete_or_infrastructure_error")
    md = manifest["metadata"]
    expected_episode = deepcopy(original_metadata["episode"])
    for relocation in relocations:
        field = relocation["field"]
        if field not in {"scene_id", "scene_dataset_config"} or expected_episode[field] != relocation["original"]:
            raise ValueError("Unexpected episode relocation")
        if digest(relocation["replacement"]) != relocation["sha256"]:
            errors.append("relocated_asset_changed")
        expected_episode[field] = relocation["replacement"]
    if md["episode"] != expected_episode or md["effective_seed"] != original_metadata["effective_seed"]:
        errors.append("initial_episode_or_seed_changed")
    if md.get("action_parser_version") != ACTION_PARSER_VERSION:
        errors.append("incorrect_parser")
    if not trace["ok"] or trace["warnings"]:
        errors.append("trace_incomplete")
    usage = summary["model_usage"]
    if not usage["trace_accounting_complete"] or usage["status_counts"].get("completed", 0) < 1:
        errors.append("model_trace_incomplete")
    pending = {}
    checked = 0
    with (run / "events.jsonl").open() as f:
        for line in f:
            event = json.loads(line)
            if event.get("name") != "action.normalize":
                continue
            if event["event"] == "span.start":
                pending[event["span_id"]] = event["data"]["input"]
            elif event["event"] == "span.end" and event["data"].get("status") == "completed":
                expected = normalize_action(pending[event["span_id"]]).to_json()
                if event["data"]["output"] != expected:
                    errors.append("executed_action_does_not_match_explicit_intent")
                checked += 1
    for name in ("replay_manifest.json", "trajectory_before.npz", "trajectory_after.npz"):
        if not (run / "replay" / name).is_file():
            errors.append("missing_" + name)
    return {"ok": not errors, "errors": errors, "run": str(run), "run_sha256": digest(run / "run.json"),
            "task_success": manifest["outcome"].get("task_success"),
            "model_calls": usage["leaf_model_calls"], "actions_checked": checked,
            "trace": trace, "cost": summary["cost"], "latency": summary["latency"]}


def campaign_report(plan_path):
    plan = read(plan_path)
    counts = {c: Counter(requested=sum(e["cohort"] == c for e in plan["entries"])) for c in EXPECTED}
    mapping = []
    replacements = 0
    for entry in plan["entries"]:
        destination = Path(entry["destination"])
        receipt = destination / "validated_result.json"
        group = counts[entry["cohort"]]
        if receipt.is_file():
            result = read(receipt)
            group["validated"] += 1
            group["successes"] += int(result["result"]["task_success"])
            replacement_path = destination / "replacement_receipt.json"
            replacement = read(replacement_path) if replacement_path.exists() else {}
            if replacement.get("status") == "replaced_old_deleted":
                replacements += 1
            mapping.append({"cohort": entry["cohort"], "shard": entry["shard"],
                            "old_run": entry["original_run"],
                            "new_run": replacement.get("canonical_run", result["result"]["run"]),
                            "owned_old_data_deleted": bool(replacement.get("status") == "replaced_old_deleted"),
                            "provider_changed": True, "task_success": result["result"]["task_success"]})
        else:
            attempts = sorted(destination.glob("attempt-*/allocation.json"))
            if attempts:
                recent = max((read(p) for p in attempts), key=lambda r: r["started_at_unix"])
                group[recent["status"]] += 1
            else:
                group["not_started"] += 1
    report = {"campaign": CAMPAIGN, "provider_change": plan["provider_change"],
              "counts": counts, "validated_mapping": mapping,
              "old_results_modified": bool(replacements), "owned_results_replaced": replacements,
              "coauthor_originals_modified": False}
    write(Path(plan_path).parent / "campaign_report.json", report)
    return {k: v for k, v in report.items() if k != "validated_mapping"}


def main():
    p = argparse.ArgumentParser(description=__doc__)
    sub = p.add_subparsers(dest="command", required=True)
    create = sub.add_parser("plan")
    create.add_argument("mismatches", type=Path)
    create.add_argument("diagnostics", type=Path)
    create.add_argument("output", type=Path)
    create.add_argument("--destination-root", type=Path, default=OWN_ROOT)
    a = sub.add_parser("audit")
    a.add_argument("plan", type=Path)
    prep = sub.add_parser("prepare")
    prep.add_argument("plan", type=Path)
    prep.add_argument("fix_source", type=Path)
    w = sub.add_parser("worker")
    w.add_argument("plan", type=Path)
    w.add_argument("index", type=int)
    report = sub.add_parser("report")
    report.add_argument("plan", type=Path)
    args = p.parse_args()
    if args.command == "plan":
        plan = build_plan(args.mismatches, args.diagnostics, args.destination_root)
        if args.output.exists():
            raise FileExistsError(args.output)
        write(args.output, plan)
        result = {"counts": plan["expected_counts"], "episodes": len(plan["entries"])}
    elif args.command == "audit":
        result = audit(args.plan)
    elif args.command == "prepare":
        result = prepare(args.plan, args.fix_source)
    elif args.command == "worker":
        result = worker(args.plan, args.index)
    else:
        result = campaign_report(args.plan)
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
