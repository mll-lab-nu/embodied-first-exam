#!/usr/bin/env python3
"""Freeze and verify a Hedgehog object path; no robot success claim."""
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
    parser.add_argument("--variation", choices=("easy", "medium", "hard"), default="medium")
    parser.add_argument("--iterations", type=int, default=20000)
    parser.add_argument("--clearance-mm", type=float, default=1.)
    parser.add_argument("--audit", type=Path, help="Rebuild and verify an existing object_witness.json")
    parser.add_argument("--worker", action="store_true", help=argparse.SUPPRESS)
    args = parser.parse_args()
    if args.iterations < 1 or not 0 < args.clearance_mm < 10:
        parser.error("Use positive iterations and clearance between 0 and 10 mm")
    args.output = args.output.resolve()
    if args.worker:
        from topogym.planning.hedgehog_in_cage.object_oracle import plan_object_path, audit_object_path
        from topogym.utils.io import write_json_atomic
        start = time.monotonic()
        if args.audit:
            witness = json.loads(args.audit.read_text())
            if witness["variation_id"].removeprefix("hedgehog_in_cage_") == "medium":
                report = audit_object_path(witness, args.output)
            else:
                from topogym.planning.hedgehog_in_cage.variant_oracle import audit_variant_object_path
                report = audit_variant_object_path(witness, args.output)
        elif args.variation != "medium":
            from topogym.planning.hedgehog_in_cage.variant_oracle import plan_variant_object_path
            report = plan_variant_object_path(args.output, variation=args.variation, seed=args.seed,
                                              iterations=args.iterations, clearance_m=args.clearance_mm/1000)
        else:
            report = plan_object_path(args.output, seed=args.seed, iterations=args.iterations,
                                      clearance_m=args.clearance_mm/1000)
        report["wall_time_s"] = time.monotonic()-start
        write_json_atomic(args.output/("object_audit.json" if args.audit else "object_witness.json"), report)
        print(report["status"], flush=True)
        return 0 if report["status"] == "object_witness_verified" else 2

    args.output.mkdir(parents=True, exist_ok=False)
    from scripts.test_policy_cube_transfer import snapshot
    from topogym.utils.process_limits import run_guarded
    source = snapshot(args.output)
    command = [sys.executable, str(source/"scripts/plan_hedgehog_object_oracle.py"),
               "--worker", "--output", str(args.output), "--seed", str(args.seed),
               "--iterations", str(args.iterations), "--clearance-mm", str(args.clearance_mm),
               "--variation", args.variation]
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
