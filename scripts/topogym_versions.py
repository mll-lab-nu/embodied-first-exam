"""Resolve and verify the single active release before starting a new experiment."""
import argparse
import ast
import hashlib
import importlib.util
import json
from pathlib import Path
import sys
import tomllib

ROOT = Path(__file__).resolve().parents[1]
FIRST_BOUND_RELEASE = 15   # tooling v15 introduced runtime bindings and release receipts (task_release.json)


def bound_release(version):
    """True for a tooling version whose packages carry a runtime binding (v15 and later), False for older labels."""
    try:
        return int(str(version)) >= FIRST_BOUND_RELEASE
    except (TypeError, ValueError):
        return False


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


def file_hash(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def public_source(root):
    """Predict prune.py's exact installed bytes without modifying the checkout."""
    root = Path(root)
    omitted = {"agents", "planning", "data", "deferred", "legacy", "redundants", "rollout_simulation", "__pycache__"}
    files = {}
    for path in sorted((root / "topogym").rglob("*")):
        relative = path.relative_to(root)
        if (not path.is_file() or set(relative.parts) & omitted or path.suffix in (".md", ".pyc")
                or any(part.startswith(".env") or part == ".secrets" for part in relative.parts)):
            continue
        if path.is_symlink():
            raise ValueError(f"Release source must be a real file: {relative}")
        data = path.read_bytes()
        if relative.as_posix() == "topogym/assets/geometry/cast_coil.py":
            lines = data.decode().splitlines(keepends=True)
            for node in ast.parse(data).body:
                if isinstance(node, ast.FunctionDef) and node.name == "synthesize":
                    data = "".join(lines[:node.lineno - 1] + lines[node.end_lineno:]).encode()
                    break
        files[relative.as_posix()] = hashlib.sha256(data).hexdigest()
    return dict(sha256=hashlib.sha256(json.dumps(files, sort_keys=True).encode()).hexdigest(), files=len(files))


def identity(root=ROOT):
    root = Path(root)
    target = release(root)
    # Paths/readiness change when a candidate is activated; its definition does not.
    result = {key: target[key] for key in ("name", "tooling_version", "image_version")}
    result.update(source=public_source(root), tooling_sha256=file_hash(root / "harbor_templates/topogym/common/rcb_topogym.py"))
    result["shared_tooling_sha256"] = digest({mode: shared_files(root, mode) for mode in ("unlimited", "limited")})
    recipes = [p for folder in ("images/topogym", "requirements") for p in (root / folder).rglob("*")
               if p.is_file() and "__pycache__" not in p.parts]
    result["runtime_recipe_sha256"] = digest({p.relative_to(root).as_posix(): file_hash(p) for p in sorted(recipes)})
    result["definition_sha256"] = digest(result)
    return result


def shared_files(root, mode):
    spec = importlib.util.spec_from_file_location("_release_tooling_check", Path(root) / "ci_checks/check-topogym-tooling.py")
    checker = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(checker)
    return checker.current_files(mode)


def release(root, selection="active"):
    root = Path(root)
    data = json.loads((root/'ci_checks/topogym_active_release.json').read_text())
    if data.get('schema_version') != 1 or selection not in ('active', 'published'):
        raise ValueError('Unknown TopoGym release selection')
    target = data[selection]
    if selection == 'active' and (root/'images/topogym/VERSION').read_text().strip() != target['image_version']:
        raise ValueError('images/topogym/VERSION differs from the active release manifest')
    return target


def task_root(root, selection="active"):
    target = release(root, selection)
    if not target.get('tasks_root'):
        raise ValueError(f"{target['name']} has no frozen task tree yet; build the candidate or explicitly select published")
    path = Path(root)/target['tasks_root']
    if not path.is_dir():
        raise ValueError(f'Frozen task tree is absent: {path}')
    return path


def task_lock(task):
    task = Path(task)
    standard = (task / "environment/sim/instance.json").is_file()
    actor = task / ("environment/sim" if standard else "environment")
    lock = json.loads((actor / "runtime_binding.json").read_text())
    if json.loads((task / "tests/runtime_binding.json").read_text()) != lock:
        raise ValueError(f"Simulator/verifier binding differs: {task}")
    return lock


def stamp_task(task, root=ROOT):
    """Called by builders only after both simulator and verifier were bound."""
    task = Path(task)
    expected, lock = identity(root), task_lock(task)
    if lock["runtime"]["source"] != expected["source"] or lock["tooling_sha256"] != expected["tooling_sha256"]:
        raise ValueError(f"Task runtime/tooling differs from the selected v{expected['tooling_version']} source; "
                         "rebuild the image and task")
    document = dict(schema_version=1, release=expected, runtime_binding_sha256=digest(lock))
    (task / "task_release.json").write_text(json.dumps(document, indent=2) + "\n")
    return document


def require_task(task, root=ROOT, *, inspect_docker=False, registered=False):
    """Generic Harbor guard; no dependency on a private oracle solution."""
    task, root = Path(task).resolve(), Path(root).resolve()
    expected = identity(root)
    meta = tomllib.loads((task / "task.toml").read_text()).get("metadata", {})
    if meta.get("tooling_version") != expected["tooling_version"]:
        raise ValueError(f"New experiments require tooling {expected['tooling_version']}: {task.name}")
    mode = "limited" if (task / "environment/sim").is_dir() else "unlimited"
    for relative, expected_hash in shared_files(root, mode).items():
        if file_hash(task / relative) != expected_hash:
            raise ValueError(f"Task contains stale public tooling: {task.name}/{relative}")
    receipt = json.loads((task / "task_release.json").read_text())
    lock = task_lock(task)
    if (receipt.get("schema_version") != 1 or receipt.get("release") != expected
            or receipt.get("runtime_binding_sha256") != digest(lock)
            or lock["runtime"]["source"] != expected["source"]
            or lock["tooling_sha256"] != expected["tooling_sha256"]):
        raise ValueError(f"Task does not belong to the selected frozen release: {task}")
    sys.path.insert(0, str(root))
    from topogym.planning.harbor_bridge.binding import check_lock_for_task
    check_lock_for_task(task, lock, inspect_docker=inspect_docker)
    # Validate the tests copy as well, independently of the actor's input files.
    from topogym.simulator.frozen_binding import check_inputs
    standard = (task / "environment/sim/instance.json").is_file()
    instance_path = task / ("environment/sim/instance.json" if standard else "tests/instance.json")
    if not standard:
        check_inputs(instance_path, task / "tests/rcb_topogym.py", lock)
    instance = json.loads(instance_path.read_text())
    tier = meta.get("difficulty")
    if tier in ("easy", "medium", "hard"):
        from topogym.tasks.release_profile import environment_inputs
        params, overrides, _ = environment_inputs(instance["task"], tier,
            variation=instance["variation_id"], seed=instance["seed"],
            parameters=instance["simulator"].get("task_parameters"))
        if params != (instance["simulator"].get("task_parameters") or {}):
            raise ValueError(f"Task parameters omit or override the selected v{expected['tooling_version']} environment profile")
        def contains(actual, required):
            if isinstance(required, dict):
                return isinstance(actual, dict) and all(k in actual and contains(actual[k], v) for k, v in required.items())
            if isinstance(required, list):
                return isinstance(actual, list) and len(actual) == len(required) and all(contains(a, b) for a, b in zip(actual, required))
            return actual == required
        if not contains(instance["simulator"], overrides):
            raise ValueError(f"Simulator options differ from the selected v{expected['tooling_version']} environment profile")
    if registered:
        target = release(root)
        catalog_path = target.get("runtime_catalog")
        if not catalog_path:
            raise ValueError(f"Active v{expected['tooling_version']} task catalog has not been frozen yet")
        catalog = json.loads((root / catalog_path).read_text())
        matches = [row for row in catalog["tasks"] if Path(row["task"]).name == task.name]
        if len(matches) != 1:
            raise ValueError(f"Task is absent/ambiguous in the active catalog: {task.name}")
        recorded = json.loads(((root / catalog_path).parent / matches[0]["lock"]).read_text())
        if recorded != lock:
            raise ValueError(f"Task instance/runtime differs from the active catalog: {task.name}")
    return dict(task=str(task), release=expected, runtime_binding=lock)


def selected_tasks(root=ROOT):
    folder = task_root(root)
    target = release(root)
    paths = [p.parent for p in sorted(folder.glob("*/task.toml"))
             if tomllib.loads(p.read_text()).get("metadata", {}).get("tooling_version") == target["tooling_version"]]
    if not paths:
        raise ValueError("Active task tree contains no current tasks")
    return paths


def freeze_run(path, tasks, root=ROOT):
    """One immutable package selection per batch, including new-vs-resume checks."""
    import fcntl
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    records = [require_task(task, root, registered=True) for task in tasks]
    document = dict(schema_version=1, release=identity(root), tasks=records)
    with path.with_suffix(".guard").open("a") as guard:
        fcntl.flock(guard, fcntl.LOCK_EX)
        if path.exists():
            if json.loads(path.read_text()) != document:
                raise ValueError("Batch belongs to different tasks/release; use a new batch name")
        else:
            with path.open("x") as stream:
                stream.write(json.dumps(document, indent=2) + "\n")
    return document


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=ROOT)
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("identity")
    sub.add_parser("tasks-root")
    listing = sub.add_parser("list")
    listing.add_argument("tasks", nargs="*")
    listing.add_argument("--inspect-docker", action="store_true")
    check = sub.add_parser("check")
    check.add_argument("tasks", type=Path, nargs="+")
    check.add_argument("--inspect-docker", action="store_true")
    check.add_argument("--registered", action="store_true")
    frozen = sub.add_parser("freeze-run")
    frozen.add_argument("--output", type=Path, required=True)
    frozen.add_argument("tasks", type=Path, nargs="+")
    args = parser.parse_args()
    try:
        if args.command == "identity":
            print(json.dumps(identity(args.root)))
        elif args.command == "tasks-root":
            print(task_root(args.root).resolve())
        elif args.command == "freeze-run":
            freeze_run(args.output, args.tasks, args.root)
        else:
            if args.command == "list":
                available = {path.name: path for path in selected_tasks(args.root)}
                tasks = [available[Path(value).name] for value in args.tasks] if args.tasks else list(available.values())
            else:
                tasks = args.tasks
            for task in tasks:
                require_task(task, args.root, inspect_docker=args.inspect_docker,
                             registered=args.command == "list" or args.registered)
                print(Path(task).resolve())
    except (OSError, ValueError, KeyError) as error:
        parser.exit(2, f"Release selection blocked: {error}\n")


if __name__ == "__main__":
    main()
