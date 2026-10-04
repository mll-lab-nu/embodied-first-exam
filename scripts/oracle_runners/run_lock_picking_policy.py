#!/usr/bin/env python3
"""Record a lock oracle through standard passive policy dispatch and Env.step.

The historical medium route remains available. Reindex supports the three
original families; simplified supports the two-rotor variants. Both can record
IK/FK for every Cartesian action. All physics
parameters and measured engine properties are recorded, including failed runs.
Solve runs end at native Task success, which may occur while still grasping.
"""
import argparse
from dataclasses import asdict
import hashlib
import json
import os
from pathlib import Path
import sys
import time
import traceback

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))


from topogym.planning.lock_picking.runner import (parameters, run_segments, finish_run, pickup_preflight, worker)



def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--setting", choices=("current", "historical_two_retreats"), default="current")
    parser.add_argument("--part", choices=("pickup", "solve"), default="pickup")
    parser.add_argument("--grasp-roll-deg", type=float, default=0.)
    parser.add_argument("--grasp-style", choices=("top", "side"), default="top")
    parser.add_argument("--physics-dt", type=float, default=.005)
    parser.add_argument("--solver-substeps", type=int, default=8)
    parser.add_argument("--control-decimation", type=int, default=5)
    parser.add_argument("--no-rgb", action="store_true", help="Explicit physics diagnostic; no video qualification")
    parser.add_argument("--compute-backend", choices=("cuda", "cpu"), default="cuda")
    parser.add_argument("--variation", choices=("very_easy", "easier", "easy", "medium", "hard"), default="medium")
    parser.add_argument("--route-mode", choices=("historical", "reindex", "simplified"), default="historical")
    parser.add_argument("--audit-ik", action="store_true", help="Record checked IK/FK for each robot action")
    parser.add_argument("--precision", choices=("32", "64"), default="32")
    parser.add_argument("--endpoint-depth", type=float,
                        help="Final insertion in pitches: 3.08 for simplified, 4.08 for reindex by default")
    parser.add_argument("--worker", action="store_true", help=argparse.SUPPRESS)
    args = parser.parse_args()
    simplified = args.variation in {"very_easy", "easier"}
    if simplified != (args.route_mode == "simplified") or (simplified and args.setting != "current"):
        parser.error("very_easy/easier require --route-mode simplified --setting current")
    if not simplified and args.variation != "medium" and (args.route_mode != "reindex" or args.setting != "current"):
        parser.error("easy/hard require --route-mode reindex --setting current")
    if args.endpoint_depth is None:
        args.endpoint_depth = 3.08 if simplified else 4.08
    if simplified and not 3.07 <= args.endpoint_depth <= 3.10:
        parser.error("Simplified endpoint depth must be in [3.07,3.10]")
    if not simplified and (not 4.06 <= args.endpoint_depth <= 4.12 or (args.route_mode != "reindex" and args.endpoint_depth != 4.08)):
        parser.error("Custom endpoint depth requires reindex mode and a value in [4.06,4.12]")
    output = args.output.resolve()
    if args.worker:
        worker(output, setting=args.setting, part=args.part, grasp_roll_deg=args.grasp_roll_deg, grasp_style=args.grasp_style,
               physics_dt=args.physics_dt, solver_substeps=args.solver_substeps,
               control_decimation=args.control_decimation, no_rgb=args.no_rgb, compute_backend=args.compute_backend,
               variation=args.variation, route_mode=args.route_mode, audit_ik=args.audit_ik, precision=args.precision,
               endpoint_depth=args.endpoint_depth)
        return
    output.mkdir(parents=True, exist_ok=False)
    from scripts.test_policy_cube_transfer import snapshot
    source = snapshot(output)
    (output/"source_manifest.json").rename(output/"run_source_manifest.json")
    command = [sys.executable, str(source/"scripts/oracle_runners/run_lock_picking_policy.py"), "--worker",
        "--output", str(output), "--setting", args.setting, "--part", args.part,
        "--grasp-roll-deg", str(args.grasp_roll_deg), "--grasp-style", args.grasp_style,
        "--physics-dt", str(args.physics_dt), "--solver-substeps", str(args.solver_substeps),
        "--control-decimation", str(args.control_decimation), "--compute-backend", args.compute_backend,
        "--variation", args.variation, "--route-mode", args.route_mode, "--precision", args.precision,
        "--endpoint-depth", str(args.endpoint_depth)]
    if args.audit_ik:
        command.append("--audit-ik")
    if args.no_rgb:
        command.append("--no-rgb")
    from importlib.metadata import distribution, version
    engine = Path(distribution("genesis-world").locate_file("genesis"))
    identity = dict(command=command, genesis_version=version("genesis-world"),
        constraint_solver_sha256=hashlib.sha256((engine/"engine/solvers/rigid/constraint/solver.py").read_bytes()).hexdigest())
    (output/"invocation.json").write_text(json.dumps(identity, indent=2))
    env = dict(os.environ, PYTHONPATH=str(source), OMP_NUM_THREADS="1", MKL_NUM_THREADS="1",
        OPENBLAS_NUM_THREADS="1", QD_NUM_THREADS="1", TOPOGYM_VISUAL_ASSET_ROOT=str(ROOT/".external/nyx-assets"))
    from topogym.utils.process_limits import run_guarded
    result = run_guarded(command, output, cwd=source, env=env)
    print(f"exit={result}; {output}", flush=True)
    raise SystemExit(result)


if __name__ == "__main__":
    main()
