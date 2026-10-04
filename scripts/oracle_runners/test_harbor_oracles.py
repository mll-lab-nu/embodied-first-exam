#!/usr/bin/env python3
"""Test existing oracles through both native Harbor graders, retaining per-task evidence."""
import argparse
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))


def main(argv=None):
    from topogym.planning.harbor_bridge.catalog import RUNNERS, TIERS
    from topogym.planning.harbor_bridge.suite import prepare, execute
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True, help="New evidence directory; never overwritten")
    parser.add_argument("--tasks-root", type=Path, help="Default: active frozen release (never silently executes old tasks)")
    parser.add_argument("--families", nargs="+", choices=tuple(RUNNERS))
    parser.add_argument("--tiers", nargs="+", choices=TIERS, default=["easy", "medium", "hard"])
    parser.add_argument("--modes", nargs="+", choices=("privileged", "standard"), default=["privileged", "standard"])
    parser.add_argument("--references", type=Path, help="JSON mapping exact task directory names to bridge package arguments")
    parser.add_argument("--candidate", action="store_true", help="Test current-version unregistered candidate tasks without activating the release")
    parser.add_argument("--harbor", type=Path, default=ROOT / ".venv-harbor/bin/harbor")
    parser.add_argument("--no-nop", action="store_true", help="Only oracle grading; omit the negative control")
    parser.add_argument("--execute", action="store_true", help="Run native Harbor; otherwise only save coverage/plan")
    parser.add_argument("--smoke-steps", type=int, help="Execute this many real oracle controls, then grade the incomplete prefix; no solvability claim")
    parser.add_argument("--wall-seconds", type=float, help="Total execution budget; stop owned jobs and leave remaining coverage not_run")
    args = parser.parse_args(argv)
    if args.candidate and args.tasks_root is None:
        parser.error("--candidate requires an explicit --tasks-root")
    try:
        refs = json.loads(args.references.read_text()) if args.references else None
        if refs is not None and not isinstance(refs, dict):
            raise ValueError("--references must contain a JSON object")
        document = prepare(args.output, tasks_root=args.tasks_root, families=args.families,
                           tiers=args.tiers, modes=args.modes, references=refs, candidate=args.candidate,
                           harbor=args.harbor, nop=not args.no_nop, smoke_steps=args.smoke_steps, wall_seconds=args.wall_seconds)
        code = execute(document) if args.execute else int(bool(document["counts"].get("blocked")))
        print(json.dumps({k: document[k] for k in ("output", "status", "counts", "grade_one_count", "all_passed")}, ensure_ascii=False))
        return code
    except (OSError, ValueError, KeyError) as error:
        parser.exit(2, f"Oracle suite blocked: {error}\n")


if __name__ == "__main__":
    raise SystemExit(main())
