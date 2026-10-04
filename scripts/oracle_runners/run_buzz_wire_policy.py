#!/usr/bin/env python3
"""Freeze and run a Buzz Wire policy without RGB/video; retain all tick evidence."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import time
import traceback

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))


from topogym.planning.buzz_wire_3d.runner import (worker)



def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--variant", choices=("easy", "medium", "hard"), default="easy")
    parser.add_argument("--seed", type=int, default=0)
    parser.add_argument("--part", choices=("all", "pickup", "regrasp", "traverse"), default="all")
    parser.add_argument("--compute-backend", choices=("cpu", "cuda"), default="cpu")
    parser.add_argument("--control-mode",choices=("JOINT_ABS","EE_ABS"),default="JOINT_ABS")
    parser.add_argument("--physics-dt", type=float, default=.025)
    parser.add_argument("--control-decimation", type=int, default=1)
    parser.add_argument("--solver-substeps", type=int, default=40)
    parser.add_argument("--episode-seconds", type=float, default=360.)
    parser.add_argument("--grasp-height", type=float, default=.012)
    parser.add_argument("--grasp-tilt", type=float, default=75.)
    parser.add_argument("--compiled-actions", type=Path,
                        help="Execute compiled ordinary actions afresh from home, without state restoration")
    parser.add_argument("--v12-performance", action="store_true",
                        help="Use v12 CPU float64/global rigid solve and goal-gated settling; retain action timing")
    parser.add_argument("--feedback-finish",action="store_true",
                        help="Easy seed-0 recipe: replay the held prefix, then remeasure and finish through observation policies")
    parser.add_argument("--worker", action="store_true", help=argparse.SUPPRESS)
    args = parser.parse_args()
    args.output = args.output.resolve()
    if args.feedback_finish and (not args.compiled_actions or args.variant != "easy" or args.seed != 0):
        parser.error("--feedback-finish currently requires easy seed 0 and --compiled-actions")
    if args.worker:
        return worker(args)
    args.output.mkdir(parents=True, exist_ok=False)
    extra_args = list(sys.argv[1:])
    if args.compiled_actions:
        frozen_actions = args.output/"policy_actions.json"
        frozen_actions.write_bytes(args.compiled_actions.read_bytes())
        index = extra_args.index("--compiled-actions")
        extra_args[index+1] = str(frozen_actions)
    from scripts.test_policy_cube_transfer import snapshot
    source = snapshot(args.output)
    if args.v12_performance:
        # The local Env entry does not apply Harbor Session's optimization.
        # Freeze the actual upstream helper alongside the ordinary policy.
        helper = Path("harbor_templates/topogym/common/rcb_topogym.py")
        target = source / helper
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes((ROOT / helper).read_bytes())
        manifest_path = args.output / "source_manifest.json"
        manifest = json.loads(manifest_path.read_text())
        manifest[str(helper)] = hashlib.sha256(target.read_bytes()).hexdigest()
        manifest_path.write_text(json.dumps(manifest, indent=2) + "\n")
    (args.output/"source_manifest.json").rename(args.output/"run_source_manifest.json")
    command = [sys.executable, str(source/"scripts/oracle_runners/run_buzz_wire_policy.py"), *extra_args, "--worker"]
    (args.output/"invocation.json").write_text(json.dumps(dict(command=command), indent=2))
    with (args.output/"runtime.log").open("x") as log:
        process = subprocess.Popen(command, cwd=ROOT, stdout=log, stderr=subprocess.STDOUT,
            env=dict(os.environ, PYTHONPATH=str(source), OMP_NUM_THREADS="1", MKL_NUM_THREADS="1",
                     OPENBLAS_NUM_THREADS="1", TOPOGYM_VISUAL_ASSET_ROOT=str(ROOT/".external/nyx-assets")))
        while process.poll() is None:
            try:
                process.wait(timeout=30)
            except subprocess.TimeoutExpired:
                progress_path = args.output/"progress.json"
                progress = json.loads(progress_path.read_text()) if progress_path.exists() else {}
                print(args.variant,progress.get("phase","building"),
                      progress.get("state",{}).get("sim_time_s"),flush=True)
    print(f"exit={process.returncode}; {args.output}")
    raise SystemExit(process.returncode)


if __name__ == "__main__":
    main()
