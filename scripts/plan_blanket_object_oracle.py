#!/usr/bin/env python3
"""Freeze and run the Blanket virtual-hand route witness; no robot success claim."""
import argparse
import json
import os
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--seed", type=int, default=0)
    parser.add_argument("--variation", choices=("very_easy", "easier", "easy", "medium", "hard"), default="easy")
    parser.add_argument("--settle-s", type=float, default=4.)
    parser.add_argument("--pause-s", type=float, default=8., help="Rest between stages (the robot's regrasp time)")
    parser.add_argument("--worker", action="store_true", help=argparse.SUPPRESS)
    args = parser.parse_args()
    args.output = args.output.resolve()
    if args.worker:
        from topogym.planning.blanket_flatten.object_oracle import run_witness
        witness = run_witness(args.output, variation=args.variation, seed=args.seed, settle_s=args.settle_s,
                              pause_s=args.pause_s)
        print(witness["status"], flush=True)
        return 0 if witness["status"] == "object_witness_verified" else 2

    args.output.mkdir(parents=True, exist_ok=False)
    from scripts.test_policy_cube_transfer import snapshot
    from topogym.utils.process_limits import run_guarded
    source = snapshot(args.output)
    command = [sys.executable, str(source/"scripts/plan_blanket_object_oracle.py"), "--worker",
               "--output", str(args.output), "--seed", str(args.seed), "--variation", args.variation,
               "--settle-s", str(args.settle_s), "--pause-s", str(args.pause_s)]
    (args.output/"invocation.json").write_text(json.dumps(dict(command=command), indent=2)+"\n")
    environment = dict(os.environ, PYTHONPATH=str(source), OMP_NUM_THREADS="1", MKL_NUM_THREADS="1",
                       OPENBLAS_NUM_THREADS="1", QD_NUM_THREADS="1", PYTHONUNBUFFERED="1")
    result = run_guarded(command, args.output, cwd=source, env=environment)
    print(f"exit={result}; {args.output}", flush=True)
    return result


if __name__ == "__main__":
    raise SystemExit(main())
