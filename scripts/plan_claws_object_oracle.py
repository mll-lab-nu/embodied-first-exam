#!/usr/bin/env python3
"""Freeze and verify a Claws object-only separation witness; no robot success claim."""
import argparse
import json
import os
from pathlib import Path
import sys
import time

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--seed", type=int, default=0)
    parser.add_argument("--variation", choices=("easy", "medium", "hard"), default="easy")
    parser.add_argument("--clearance-mm", type=float, help="Defaults: easy 1, medium/hard 4 mm")
    parser.add_argument("--audit", type=Path, help="Rebuild and verify an existing object_witness.json")
    parser.add_argument("--worker", action="store_true", help=argparse.SUPPRESS)
    args = parser.parse_args()
    if args.clearance_mm is None:
        args.clearance_mm = 1. if args.variation == "easy" else 4.
    if not 0 < args.clearance_mm < 10:
        parser.error("Use a clearance between 0 and 10 mm")
    args.output = args.output.resolve()
    if args.worker:
        from topogym.planning.interlocked_claws.object_oracle import plan_object_path, audit_object_path
        from topogym.utils.io import write_json_atomic
        start = time.monotonic()
        if args.audit:
            report = audit_object_path(json.loads(args.audit.read_text()), args.output)
        else:
            report = plan_object_path(args.output, variation=args.variation, seed=args.seed,
                                      clearance_m=args.clearance_mm/1000)
        report["wall_time_s"] = time.monotonic()-start
        write_json_atomic(args.output/("object_audit.json" if args.audit else "object_witness.json"), report)
        print(report["status"], flush=True)
        return 0 if report["status"] == "object_witness_verified" else 2

    args.output.mkdir(parents=True, exist_ok=False)
    from scripts.test_policy_cube_transfer import snapshot
    from topogym.utils.process_limits import run_guarded
    source = snapshot(args.output)
    command = [sys.executable, str(source/"scripts/plan_claws_object_oracle.py"),
               "--worker", "--output", str(args.output), "--seed", str(args.seed),
               "--clearance-mm", str(args.clearance_mm), "--variation", args.variation]
    if args.audit:
        target = args.output/"submitted_witness.json"
        target.write_bytes(args.audit.read_bytes())
        command += ["--audit", str(target)]
    (args.output/"invocation.json").write_text(json.dumps(dict(command=command), indent=2)+"\n")
    environment = dict(os.environ, PYTHONPATH=str(source), OMP_NUM_THREADS="1",
                       MKL_NUM_THREADS="1", OPENBLAS_NUM_THREADS="1", QD_NUM_THREADS="1")
    result = run_guarded(command, args.output, cwd=source, env=environment)
    print(f"exit={result}; {args.output}", flush=True)
    return result


if __name__ == "__main__":
    raise SystemExit(main())
