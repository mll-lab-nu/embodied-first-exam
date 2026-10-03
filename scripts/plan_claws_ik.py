#!/usr/bin/env python3
"""Frozen-source Claws robot route planning from the live pregrasp state; read-only kinematics."""
import argparse
import json
import os
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


def grasp_assist_for(variation, seed):
    """Use the task's current contact-triggered assistance declaration."""
    from topogym.tasks.interlocked_claws.common import recommended_grasp_assist
    return recommended_grasp_assist(variation, seed)



def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--witness", type=Path, required=True, help="Verified object_witness.json")
    parser.add_argument("--seed", type=int, default=0)
    parser.add_argument("--variation", choices=("easy", "medium", "hard"), default="easy")
    parser.add_argument("--step-mm", type=float, default=4.)
    parser.add_argument("--step-deg", type=float, default=2.)
    parser.add_argument("--worker", action="store_true", help=argparse.SUPPRESS)
    args = parser.parse_args()
    args.output = args.output.resolve()
    if args.worker:
        import torch
        from topogym.simulator import Env, SimulatorConfig
        from topogym.planning.interlocked_claws.held_oracle import plan_held_route
        torch.set_num_threads(1)
        witness = json.loads(args.witness.read_text())
        config = SimulatorConfig(task_id="interlocked_claws", variation_id=args.variation, compute_backend="cpu",
            enable_rgb=False, enable_privileged=True, control_mode="JOINT_ABS", physics_dt_s=.025,
            solver_substeps=40, control_decimation=1, max_physics_steps=100,
            grasp_assist=grasp_assist_for(args.variation, args.seed), work_dir=args.output/"scene")
        with Env(config) as env:
            env.reset(seed=args.seed)
            report = plan_held_route(env, witness, args.output, step_m=args.step_mm/1000, step_deg=args.step_deg,
                                     progress=lambda e: print(e, flush=True))
        print(report["status"], flush=True)
        return 0 if report["status"] == "held_ik_route_found" else 2
    args.output.mkdir(parents=True, exist_ok=False)
    from scripts.test_policy_cube_transfer import snapshot
    from topogym.utils.process_limits import run_guarded
    source = snapshot(args.output)
    witness = args.output/"submitted_witness.json"
    witness.write_bytes(args.witness.read_bytes())
    command = [sys.executable, str(source/"scripts/plan_claws_ik.py"), "--worker", "--output", str(args.output),
               "--witness", str(witness), "--seed", str(args.seed), "--variation", args.variation,
               "--step-mm", str(args.step_mm), "--step-deg", str(args.step_deg)]
    (args.output/"invocation.json").write_text(json.dumps(dict(command=command), indent=2)+"\n")
    environment = dict(os.environ, PYTHONPATH=str(source), OMP_NUM_THREADS="1", MKL_NUM_THREADS="1",
                       OPENBLAS_NUM_THREADS="1", QD_NUM_THREADS="1", PYTHONUNBUFFERED="1")
    result = run_guarded(command, args.output, cwd=source, env=environment)
    print(f"exit={result}; {args.output}", flush=True)
    return result


if __name__ == "__main__":
    raise SystemExit(main())
