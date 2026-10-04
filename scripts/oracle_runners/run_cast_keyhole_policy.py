#!/usr/bin/env python3
"""Run frozen Cast Keyhole policies through the standard, headless SegmentRunner."""
import argparse
import json
import os
from pathlib import Path
import subprocess
import sys
import time
import traceback

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))


from topogym.planning.cast_keyhole.runner import (worker, simplified_worker)



def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", required=True)
    parser.add_argument("--variation", choices=["very_easy", "easier", "easy", "medium", "hard"], required=True)
    parser.add_argument("--part", choices=["pickup", "all"], default="all")
    parser.add_argument("--backend", choices=["cuda", "cpu"], default="cuda")
    parser.add_argument("--rgb", action="store_true", help="Optional Nyx video; disabled by default")
    parser.add_argument("--seed", type=int, default=0)
    parser.add_argument("--horizon", type=float, default=900.)
    parser.add_argument("--speed", type=float, default=1.)
    parser.add_argument("--gripper-close", type=float, default=.002,
                        help="Simplified policy native close target; frozen Harbor v6 width zero maps to 0.00746875 m")
    parser.add_argument("--tick", type=float, choices=[.0025, .025], default=.0025,
                        help=".025 groups ten integration blocks per saved tick; explicit faster qualification timing")
    parser.add_argument("--worker", action="store_true")
    args = parser.parse_args()
    if args.speed <= 0 or args.horizon <= 0:
        parser.error("speed and horizon must be positive")
    if not 0 <= args.gripper_close < .024:
        parser.error("--gripper-close must lie in [0, 0.024)")
    output = Path(args.output).resolve()
    if args.worker:
        return worker(args, output)
    output.mkdir(parents=True, exist_ok=False)
    from scripts.test_policy_cube_transfer import snapshot
    source = snapshot(output)
    (output/"source_manifest.json").rename(output/"run_source_manifest.json")
    command = [sys.executable, str(source/"scripts/oracle_runners/run_cast_keyhole_policy.py"), "--worker",
        "--output", str(output), "--variation", args.variation, "--part", args.part,
        "--backend", args.backend, "--seed", str(args.seed), "--horizon", str(args.horizon), "--speed", str(args.speed),
        "--tick", str(args.tick), "--gripper-close", str(args.gripper_close)]
    if args.rgb:
        command.append("--rgb")
    (output/"invocation.json").write_text(json.dumps(dict(command=command), indent=2)+"\n")
    with (output/"runtime.log").open("x") as log:
        result = subprocess.run(command, cwd=source, stdout=log, stderr=subprocess.STDOUT,
            env=dict(os.environ, PYTHONPATH=str(source), OMP_NUM_THREADS="1", MKL_NUM_THREADS="1",
                OPENBLAS_NUM_THREADS="1", TOPOGYM_VISUAL_ASSET_ROOT=str(ROOT/".external/nyx-assets")))
    print(f"exit={result.returncode}; {output}")
    raise SystemExit(result.returncode)


if __name__ == "__main__":
    main()
