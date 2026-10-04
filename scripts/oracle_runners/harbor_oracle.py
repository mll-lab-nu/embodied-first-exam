#!/usr/bin/env python3
"""Inspect, package and run task-independent private Harbor oracle candidates."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))


def main(argv=None):
    from topogym.planning.harbor_bridge.contracts import BridgeError, differences, instance_binding, read_json
    from topogym.planning.harbor_bridge.packaging import package, check_package
    from topogym.planning.harbor_bridge.catalog import TIERS
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    inventory = sub.add_parser("inventory", help="Read-only task/runner inventory; no simulator imports")
    inventory.add_argument("--tasks-root", type=Path, default=None)
    inventory.add_argument("--tiers", nargs="+", choices=TIERS, help="Only inspect exact difficulty tiers")
    bind = sub.add_parser("bind", help="Pin actual local image/source, task tooling and immutable instance inputs")
    bind.add_argument("--task", type=Path, action="append")
    bind.add_argument("--release", choices=("active", "published"), default="active")
    bind.add_argument("--output", type=Path, required=True)
    probe = sub.add_parser("preflight", help="Fresh-process exact restore, separate from oracle success")
    probe.add_argument("--task", type=Path, required=True)
    probe.add_argument("--runtime-lock", type=Path, required=True)
    probe.add_argument("--output", type=Path, required=True)
    probe.add_argument("--gpu", default="0")
    probe.add_argument("--execute", action="store_true")
    compare = sub.add_parser("compare", help="Compare full frozen identities including external state assets")
    compare.add_argument("--reference-instance", type=Path, required=True)
    compare.add_argument("--target-instance", type=Path, required=True)
    build = sub.add_parser("package", help="Create output/<task-name>; original task is never changed")
    build.add_argument("--task", type=Path, required=True)
    build.add_argument("--output", type=Path, required=True)
    build.add_argument("--kind", choices=("existing", "session", "public_trajectory", "native_trajectory"), required=True)
    build.add_argument("--trajectory", type=Path)
    build.add_argument("--source-instance", type=Path)
    build.add_argument("--entrypoint", help="Private planning module:function accepting (session, output, **kwargs)")
    build.add_argument("--source-root", type=Path)
    build.add_argument("--include", action="append", default=[], help="Relative private planning dependency/data file")
    build.add_argument("--kwargs", type=Path, help="JSON object of callback arguments")
    build.add_argument("--runtime-lock", type=Path, required=True, help="Manager-generated runtime binding")
    check = sub.add_parser("check", help="Verify a candidate's complete bound inputs; no physics")
    check.add_argument("--task", type=Path, required=True)
    run = sub.add_parser("run", help="Plan native Harbor jobs; --execute runs them with memory supervision")
    run.add_argument("--task", type=Path, action="append", required=True)
    run.add_argument("--output", type=Path, required=True)
    run.add_argument("--harbor", default=str(ROOT / ".venv-harbor/bin/harbor"))
    run.add_argument("--agents", nargs="+", choices=("oracle", "nop"), default=["oracle", "nop"])
    run.add_argument("--execute", action="store_true")
    run.add_argument("--tiers", nargs="+", choices=TIERS, help="Reject any task outside this difficulty scope")
    args = parser.parse_args(argv)
    try:
        # Explicit paths must satisfy the same active-release contract as defaults.
        if args.command in {"bind", "preflight", "package", "check", "run"}:
            sys.path.insert(0, str(ROOT / "scripts"))
            from topogym_versions import require_task
            paths = getattr(args, "task", None) or []
            for path in paths if isinstance(paths, list) else [paths]:
                require_task(path, ROOT)
            if args.command == "bind" and args.release != "active":
                raise BridgeError("New oracle experiments use the active release")
        if args.command == "inventory":
            from topogym.planning.harbor_bridge.catalog import inventory as inspect
            sys.path.insert(0, str(ROOT / "scripts"))
            from topogym_versions import task_root
            result = inspect(ROOT, args.tasks_root or task_root(ROOT), tiers=args.tiers)
        elif args.command == "bind":
            from topogym.planning.harbor_bridge.binding import bind_tasks, selected_tasks
            result = bind_tasks(args.task or selected_tasks(selection=args.release), args.output)
        elif args.command == "preflight":
            from topogym.planning.harbor_bridge.binding import preflight
            result = preflight(args.task, args.runtime_lock, args.output, gpu=args.gpu, execute=args.execute)
        elif args.command == "compare":
            diff = differences(instance_binding(args.reference_instance), instance_binding(args.target_instance))
            print(json.dumps(dict(compatible=not diff, differences=diff), indent=2))
            return int(bool(diff))
        elif args.command == "package":
            result = package(args.task, args.output, kind=args.kind, trajectory=args.trajectory,
                source_instance=args.source_instance, entrypoint=args.entrypoint, source_root=args.source_root,
                includes=args.include, kwargs=read_json(args.kwargs) if args.kwargs else None,
                runtime_lock=read_json(args.runtime_lock))
        elif args.command == "check":
            result = check_package(args.task)
        else:
            from topogym.planning.harbor_bridge.batch import plan, execute
            result = plan(args.task, args.output, args.harbor, args.agents, tiers=args.tiers)
            if args.execute:
                return execute(result)
        print(json.dumps(result, indent=2, ensure_ascii=False))
        return 0
    except (BridgeError, OSError, ValueError, KeyError) as error:
        print(json.dumps(dict(status="blocked", error=f"{type(error).__name__}: {error}"), ensure_ascii=False), file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
