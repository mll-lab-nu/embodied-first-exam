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

RUNTIME_FILES = ("__init__.py", "contracts.py", "actions.py", "evidence.py", "runtime.py", "frozen_binding.py")
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
            entrypoint=None, source_root=None, includes=(), kwargs=None, runtime_lock=None,
            data_files=None, smoke_steps=None, standard_timing="exact"):
    """Write output/<original-task-name>, atomically; never promote oracle metadata."""
    task, mode, instance, tooling = task_inputs(task)
    binding = instance_binding(instance)
    if runtime_lock is not None:
        from .binding import check_lock_for_task
        check_lock_for_task(task, runtime_lock)
        binding_api = any(isinstance(n, ast.Assign) and any(isinstance(t, ast.Name) and t.id == "BINDING_API" for t in n.targets)
                          and isinstance(n.value, ast.Constant) and n.value.value == 1
                          for n in ast.parse(tooling.read_text()).body)
        if mode == "standard" and not binding_api:
            raise BridgeError("Bound standard execution needs candidate tooling with BINDING_API=1; frozen v14 stays unchanged")
    output = Path(output).resolve()
    destination = output / task.name
    if destination.exists() or output == task or output.is_relative_to(task):
        raise BridgeError("Output must be a new candidate outside the source task")
    if kind not in {"existing", "session", "public_trajectory", "native_trajectory"}:
        raise BridgeError("Unsupported package kind")
    if mode == "standard" and kind != "public_trajectory":
        raise BridgeError("Standard mode accepts only a bound public trajectory")
    if standard_timing not in {"exact", "rate_limited"}:
        raise BridgeError("Unknown standard trajectory timing")
    if standard_timing != "exact" and (mode != "standard" or kind != "public_trajectory"):
        raise BridgeError("Rate conversion requires a standard public trajectory")
    # Validate the complete source tree before creating anything; no external symlinks.
    original_hashes = file_hashes(task)
    copied, execution = {}, dict(kind=kind)
    if smoke_steps is not None:
        if type(smoke_steps) is not int or not 1 <= smoke_steps <= 1000 or kind != "session":
            raise BridgeError("Smoke steps require a session callback and an integer in [1, 1000]")
        execution["smoke_steps"] = smoke_steps
    if kind.endswith("trajectory"):
        if trajectory is None or source_instance is None:
            raise BridgeError("Trajectories require an explicit source instance")
        require_same_instance(binding, instance_binding(source_instance))
        load_trajectory(trajectory, binding, native=kind == "native_trajectory")
        copied["source_reference.npz" if standard_timing == "rate_limited" else "reference.npz"] = Path(trajectory).resolve()
        execution["artifact"] = "reference.npz"
        if mode == "standard":
            execution["standard_timing"] = standard_timing
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
    for name, path in (data_files or {}).items():
        relative = Path(name)
        if (not name.startswith("topogym/planning/") or relative.is_absolute() or ".." in relative.parts
                or FORBIDDEN_PARTS & set(relative.parts) or relative.suffix not in {".json", ".npz"}
                or name in copied):
            raise BridgeError(f"Invalid private reference data destination: {name}")
        source = Path(path).resolve(strict=True)
        if not source.is_file():
            raise BridgeError(f"Reference data is not a file: {source}")
        copied[name] = source
    source_hashes = {name: digest(path) for name, path in copied.items()}
    # Only the runtime (not the catalog or packager) goes into solution/.
    runtime_root = Path(__file__).parent
    for name in RUNTIME_FILES:
        copied["_harbor_oracle_bridge/" + name] = (runtime_root.parents[1] / "simulator/frozen_binding.py"
            if name == "frozen_binding.py" else runtime_root / name)
    output.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix=".oracle-candidate-", dir=output) as temporary:
        staging = Path(temporary) / task.name
        shutil.copytree(task, staging, ignore=shutil.ignore_patterns("solution", "__pycache__"))
        binding_additions = {}
        if runtime_lock is not None and binding_api:
            sub = "environment/sim" if mode == "standard" else "environment"
            for relative in (sub + "/runtime_binding.json", "tests/runtime_binding.json"):
                target = staging/relative
                target.write_text(json.dumps(runtime_lock, indent=2)+'\n')
                if original_hashes.get(relative) != digest(target):
                    binding_additions[relative] = digest(target)
            # Generated templates already contain these COPY lines. This also
            # supports candidate task trees made before binding was introduced.
            for relative, command in (("tests/Dockerfile", "COPY runtime_binding.json /tests/runtime_binding.json"),
                                      ("environment/Dockerfile", "COPY runtime_binding.json /app/runtime_binding.json")):
                target = staging/relative
                if target.is_file() and (mode == "privileged" or relative.startswith("tests/")) and command not in target.read_text():
                    target.write_text(target.read_text()+"\n"+command+"\n")
                    binding_additions[relative] = digest(target)
        solution = staging / "solution"
        solution.mkdir()
        for name, source in copied.items():
            target = solution / name
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(source, target)
            if name in source_hashes and digest(target) != source_hashes[name]:
                raise BridgeError(f"Reference changed during packaging: {name}")
        if standard_timing == "rate_limited":
            from .timing import convert_trajectory
            conversion = convert_trajectory(solution / "source_reference.npz", solution / "reference.npz", binding, tooling)
            (solution / "timing_conversion.json").write_text(json.dumps(conversion, indent=2) + "\n")
            execution["timing_conversion"] = conversion
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
                "Frozen instance inputs are unchanged; added runtime bindings are listed in the manifest.\n"
                "See `solution/bridge_manifest.json` for the bound inputs and reference hashes.\n")
        if "## Reference solution" in original_readme:
            original_readme = re.sub(r"(?ms)^## Reference solution\s*\n.*?(?=^## |\Z)",
                                     "## Reference solution\n\n" + note + "\n", original_readme)
        readme.write_text("> Private bridge candidate — qualification pending.\n\n" + original_readme)
        public_hashes = {k: v for k, v in file_hashes(staging).items()
                         if k.startswith(("environment/", "tests/"))}
        expected_public = {k: v for k, v in original_hashes.items()
                           if k.startswith(("environment/", "tests/"))}
        expected_public.update(binding_additions)
        require_same_instance(expected_public, public_hashes)
        manifest = dict(schema_version=1, status="private_candidate", harbor_qualified=False,
                        mode=mode, binding=binding, tooling_sha256=digest(tooling), execution=execution,
                        runtime_binding=runtime_lock,
                        source_task=str(task), source_reference_sha256=source_hashes,
                        public_files=public_hashes, binding_additions=binding_additions, files=file_hashes(solution),
                        qualification_required=["privileged_oracle", "privileged_nop", "standard_oracle", "standard_nop"],
                        limitations=["Packaging does not prove physical replay or task success",
                                     "Dynamic imports/data files must be included explicitly",
                                     "Standard HTTP exposes only an opaque instance binding ID"])
        (solution / "bridge_manifest.json").write_text(json.dumps(manifest, indent=2, allow_nan=False) + "\n")
        # A changing source checkout must not silently become a mixed candidate.
        require_same_instance(original_hashes, file_hashes(task))
        if destination.exists():
            raise BridgeError("Candidate appeared during packaging; refusing overwrite")
        staging.rename(destination)
    return dict(task=str(destination), mode=mode, kind=execution["kind"], harbor_qualified=False,
                private_files=len(manifest["files"]), public_files_unchanged=not binding_additions,
                frozen_instance_unchanged=True,
                instance_sha256=binding["instance_sha256"])


def check_package(task):
    from .runtime import verify_files
    task, mode, instance, tooling = task_inputs(task)
    solution = task / "solution"
    recipe = read_json(solution / "bridge_manifest.json")
    if recipe.get("runtime_binding") is not None:
        from .binding import check_lock_for_task
        check_lock_for_task(task, recipe["runtime_binding"])
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
