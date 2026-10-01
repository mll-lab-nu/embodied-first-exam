#!/usr/bin/env python3
"""Rebuild the current lock scene and audit recorded full robot IK/geometry."""
import argparse
import json
import os
from pathlib import Path
import sys
import traceback

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


def worker(args):
    import torch
    from topogym.simulator import Env, SimulatorConfig
    from topogym.utils.io import write_json_atomic
    from topogym.planning.lock_picking.robot_audit import audit_robot_process
    from topogym.planning.lock_picking.robot_geometry import LockRobotGeometry
    torch.set_num_threads(1)
    original = json.loads((args.run/"run_report.json").read_text())
    values = original["config"]
    values.update(work_dir=str(args.output/"scene"), enable_rgb=False, compute_backend="cpu")
    try:
        with Env(SimulatorConfig(**values)) as env:
            env.reset(seed=0)
            if args.geometry_probe:
                checker = LockRobotGeometry(env)
                result = dict(scope=checker.scope, gaps=checker.check(env._world.read_state()),
                              passed=True, physical_proof=False)
                write_json_atomic(args.output/"geometry_probe.json", result)
            else:
                result = audit_robot_process(env, args.run, args.output)
        return 0 if result["passed"] else 2
    except Exception:
        write_json_atomic(args.output/"failure.json", dict(error=traceback.format_exc()))
        raise


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--geometry-probe", action="store_true", help="Only verify scene query preparation")
    parser.add_argument("--allow-failed", action="store_true", help="Diagnose a sealed failed run; it cannot pass this audit")
    parser.add_argument("--worker", action="store_true", help=argparse.SUPPRESS)
    args = parser.parse_args()
    args.run, args.output = args.run.resolve(), args.output.resolve()
    if args.worker:
        return worker(args)
    if not args.geometry_probe:
        report = json.loads((args.run/"run_report.json").read_text())
        if report["status"] != "route_completed" and not (args.allow_failed and report["status"] == "failed"):
            parser.error("Only audit a sealed, completed robot route")
    args.output.mkdir(parents=True, exist_ok=False)
    from scripts.test_policy_cube_transfer import snapshot
    from topogym.utils.process_limits import run_guarded
    source = snapshot(args.output)
    command = [sys.executable, str(source/"scripts/audit_lock_picking_robot.py"), "--worker",
               "--run", str(args.run), "--output", str(args.output)]
    if args.geometry_probe:
        command.append("--geometry-probe")
    if args.allow_failed:
        command.append("--allow-failed")
    (args.output/"invocation.json").write_text(json.dumps(dict(command=command), indent=2)+"\n")
    result = run_guarded(command, args.output, cwd=source, env=dict(os.environ,
        PYTHONPATH=str(source), OMP_NUM_THREADS="1", MKL_NUM_THREADS="1", OPENBLAS_NUM_THREADS="1", QD_NUM_THREADS="1"))
    print(f"exit={result}; {args.output}", flush=True)
    return result


if __name__ == "__main__":
    raise SystemExit(main())
