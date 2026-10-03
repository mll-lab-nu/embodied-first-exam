"""Build new self-contained Harbor candidates without editing their source tasks."""
from __future__ import annotations

import ast
import importlib.util
import json
from pathlib import Path
import re
import shlex
import shutil
import tempfile
import tomllib

from .contracts import (BridgeError, differences, digest, file_hashes, instance_binding,
                        load_trajectory, member, read_json, require_same_instance)

RUNTIME_FILES = ("__init__.py", "contracts.py", "actions.py", "runtime.py")
PRIVATE_PREFIX = "topogym.planning"
FORBIDDEN_PARTS = {"calibration_tools", "legacy", "deferred"}


def task_inputs(task):
    task = Path(task).resolve()
    config = tomllib.loads(member(task, "task.toml").read_text())
    mode = config.get("metadata", {}).get("mode", config.get("metadata", {}).get("tier"))
    if mode not in {"privileged", "standard"}:
        mode = "standard" if (task / "environment/sim/instance.json").is_file() else "privileged"
    sub = "environment/sim" if mode == "standard" else "environment"
    instance = member(task, sub + "/instance.json")
    tooling = member(task, sub + "/rcb_topogym.py")
    return task, mode, instance, tooling


def _module_path(root, module):
    name = module.replace(".", "/")
    for suffix in (".py", "/__init__.py"):
        if (root / (name + suffix)).is_file():
            return name + suffix
    return None


def collect_helpers(root, module, includes=()):
    """Static transitive planning imports plus explicit data/dynamic dependencies.

    Only planning helpers may be supplied by solution/. Installed task, physics,
    robot and public tooling modules remain authoritative.
    """
    root = Path(root).resolve()
    if not module.startswith(PRIVATE_PREFIX + "."):
        raise BridgeError("Session callbacks must be private topogym.planning modules")
    pending = [module]
    files = {}

    def add_file(name):
        if not name.startswith("topogym/planning/") or FORBIDDEN_PARTS & set(Path(name).parts):
            raise BridgeError(f"Nonportable or development-only private helper: {name}")
        files[name] = member(root, name)

    def add_module(name, required=False):
        if name.split(".")[0] in {"scripts", "legacy"} or FORBIDDEN_PARTS & set(name.split(".")):
            raise BridgeError(f"Development-only dependency must be separated before packaging: {name}")
        if name == PRIVATE_PREFIX or name.startswith(PRIVATE_PREFIX + "."):
            path = _module_path(root, name)
            if path is None:
                if required:
                    raise BridgeError(f"Private module is missing: {name}")
                return
            if path not in files:
                pending.append(name)

    for name in includes:
        add_file(name)
        if name.endswith(".py"):
            pending.append(name.removesuffix(".py").replace("/", ".").removesuffix(".__init__"))
    visited = set()
    while pending:
        current = pending.pop()
        if current in visited:
            continue
        visited.add(current)
        path = _module_path(root, current)
        if path is None:
            raise BridgeError(f"Private module is missing: {current}")
        add_file(path)
        # Package initializers may themselves have imports; inspect them too.
        pieces = current.split(".")
        for n in range(2, len(pieces)):
            add_module(".".join(pieces[:n]), required=True)
        package = current if path.endswith("/__init__.py") else current.rpartition(".")[0]
        tree = ast.parse(files[path].read_text(), filename=path)
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    add_module(alias.name, required=True)
            elif isinstance(node, ast.ImportFrom):
                name = node.module or ""
                if node.level:
                    name = importlib.util.resolve_name("." * node.level + name, package)
                add_module(name, required=True)
                for alias in node.names:
                    if alias.name != "*":
                        add_module(name + "." + alias.name)
    return files


def _candidate_metadata(text):
    match = re.search(r"(?ms)^\[metadata\]\s*\n(.*?)(?=^\[|\Z)", text)
    if match is None:
        raise BridgeError("Task has no metadata section")
    body = match.group(1)
    body = re.sub(r"(?m)^oracle(?:_evidence)?\s*=.*\n?", "", body)
    body += ('oracle = "none"\n'
             'oracle_evidence = "Private bridge candidate; full Harbor oracle/nop qualification pending. '
             'See solution/bridge_manifest.json."\n\n')
    return text[:match.start(1)] + body + text[match.end(1):]


def _original_script(solution):
    """Recognize the existing generator's run-oracle command, never execute shell to discover it."""
    solve = member(solution, "solve.sh").read_text()
    for line in solve.splitlines():
        words = shlex.split(line, comments=True)
        if "run-oracle" in words and "--code" in words:
            path = words[words.index("--code") + 1]
            if not path.startswith("/solution/"):
                raise BridgeError("Existing solve.sh uses a nonportable oracle path")
            name = path.removeprefix("/solution/")
            member(solution, name)
            return name
    raise BridgeError("No generated run-oracle script found; use a session callback or a bound trajectory")


def package(task, output, *, kind, trajectory=None, source_instance=None,
            entrypoint=None, source_root=None, includes=(), kwargs=None):
    """Write output/<original-task-name>, atomically; never promote oracle metadata."""
    task, mode, instance, tooling = task_inputs(task)
    binding = instance_binding(instance)
    output = Path(output).resolve()
    destination = output / task.name
    if destination.exists() or output == task or output.is_relative_to(task):
        raise BridgeError("Output must be a new candidate outside the source task")
    if kind not in {"existing", "session", "public_trajectory", "native_trajectory"}:
        raise BridgeError("Unsupported package kind")
    if mode == "standard" and kind != "public_trajectory":
        raise BridgeError("Standard mode accepts only a bound public trajectory")
    # Validate the complete source tree before creating anything; no external symlinks.
    original_hashes = file_hashes(task)
    copied, execution = {}, dict(kind=kind)
    if kind.endswith("trajectory"):
        if trajectory is None or source_instance is None:
            raise BridgeError("Trajectories require an explicit source instance")
        require_same_instance(binding, instance_binding(source_instance))
        load_trajectory(trajectory, binding, native=kind == "native_trajectory")
        copied["reference.npz"] = Path(trajectory).resolve()
        execution["artifact"] = "reference.npz"
    elif kind == "existing":
        solution = task / "solution"
        execution = dict(kind="script", script=_original_script(solution))
        for name in file_hashes(solution):
            if name in {"solve.sh", "bridge_manifest.json"} or name.startswith("_harbor_oracle_bridge/"):
                continue
            if FORBIDDEN_PARTS & set(Path(name).parts):
                raise BridgeError(f"Development-only file in existing solution: {name}")
            if name.startswith("topogym/") and not name.startswith("topogym/planning/"):
                raise BridgeError("A private solution may not replace installed simulator modules")
            copied[name] = member(solution, name)
    else:
        if (not isinstance(entrypoint, str)
                or re.fullmatch(r"[A-Za-z_]\w*(?:\.[A-Za-z_]\w*)*:[A-Za-z_]\w*", entrypoint) is None):
            raise BridgeError("Expected module:function session entrypoint")
        if source_root is None or not isinstance(kwargs or {}, dict):
            raise BridgeError("Session callback requires source root and a JSON object of kwargs")
        copied = collect_helpers(source_root, entrypoint.split(":")[0], includes)
        execution.update(entrypoint=entrypoint, kwargs=kwargs or {})
    source_hashes = {name: digest(path) for name, path in copied.items()}
    # Only the runtime (not the catalog or packager) goes into solution/.
    runtime_root = Path(__file__).parent
    for name in RUNTIME_FILES:
        copied["_harbor_oracle_bridge/" + name] = runtime_root / name
    output.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix=".oracle-candidate-", dir=output) as temporary:
        staging = Path(temporary) / task.name
        shutil.copytree(task, staging, ignore=shutil.ignore_patterns("solution", "__pycache__"))
        solution = staging / "solution"
        solution.mkdir()
        for name, source in copied.items():
            target = solution / name
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(source, target)
            if name in source_hashes and digest(target) != source_hashes[name]:
                raise BridgeError(f"Reference changed during packaging: {name}")
        (solution / "bridge_main.py").write_text(
            'from pathlib import Path\nfrom _harbor_oracle_bridge.runtime import main\n'
            'raise SystemExit(main(Path(__file__).resolve().parent))\n')
        (solution / "solve.sh").write_text(
            '#!/bin/bash\nset -euo pipefail\nmkdir -p /app/output\n'
            'exec python /solution/bridge_main.py\n')
        (solution / "solve.sh").chmod(0o755)
        toml = staging / "task.toml"
        toml.write_text(_candidate_metadata(toml.read_text()))
        readme = staging / "README.md"
        original_readme = readme.read_text() if readme.is_file() else ""
        # Do not inherit a source package's oracle qualification statement.
        note = ("This copy is a private Harbor oracle bridge candidate. Its reference is not yet Harbor-qualified.\n"
                "Public environment, frozen instance and verifier inputs are unchanged.\n"
                "See `solution/bridge_manifest.json` for the bound inputs and reference hashes.\n")
        if "## Reference solution" in original_readme:
            original_readme = re.sub(r"(?ms)^## Reference solution\s*\n.*?(?=^## |\Z)",
                                     "## Reference solution\n\n" + note + "\n", original_readme)
        readme.write_text("> Private bridge candidate — qualification pending.\n\n" + original_readme)
        public_hashes = {k: v for k, v in file_hashes(staging).items()
                         if k.startswith(("environment/", "tests/"))}
        expected_public = {k: v for k, v in original_hashes.items()
                           if k.startswith(("environment/", "tests/"))}
        require_same_instance(expected_public, public_hashes)
        manifest = dict(schema_version=1, status="private_candidate", harbor_qualified=False,
                        mode=mode, binding=binding, tooling_sha256=digest(tooling), execution=execution,
                        source_task=str(task), source_reference_sha256=source_hashes,
                        public_files=public_hashes, files=file_hashes(solution),
                        qualification_required=["privileged_oracle", "privileged_nop", "standard_oracle", "standard_nop"],
                        limitations=["Packaging does not prove physical replay or task success",
                                     "Dynamic imports/data files must be included explicitly",
                                     "Standard HTTP does not expose full frozen-instance identity"])
        (solution / "bridge_manifest.json").write_text(json.dumps(manifest, indent=2, allow_nan=False) + "\n")
        # A changing source checkout must not silently become a mixed candidate.
        require_same_instance(original_hashes, file_hashes(task))
        if destination.exists():
            raise BridgeError("Candidate appeared during packaging; refusing overwrite")
        staging.rename(destination)
    return dict(task=str(destination), mode=mode, kind=execution["kind"], harbor_qualified=False,
                private_files=len(manifest["files"]), public_files_unchanged=True,
                instance_sha256=binding["instance_sha256"])


def check_package(task):
    from .runtime import verify_files
    task, mode, instance, tooling = task_inputs(task)
    solution = task / "solution"
    recipe = read_json(solution / "bridge_manifest.json")
    verify_files(solution, recipe)
    require_same_instance(recipe["binding"], instance_binding(instance))
    if mode != recipe["mode"] or digest(tooling) != recipe["tooling_sha256"]:
        raise BridgeError("Task mode or tooling changed after packaging")
    public = {k: v for k, v in file_hashes(task).items() if k.startswith(("environment/", "tests/"))}
    require_same_instance(recipe["public_files"], public)
    meta = tomllib.loads((task / "task.toml").read_text())["metadata"]
    if meta.get("oracle") != "none":
        raise BridgeError("Candidate metadata must not claim oracle qualification")
    return dict(status="passed", scope="package identity and integrity only", harbor_qualified=False,
                task=str(task), execution=recipe["execution"]["kind"], mode=mode)
