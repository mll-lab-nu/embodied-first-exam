#!/usr/bin/env python3
"""Frozen-source Blanket robot oracle: default home -> assisted two-hand route -> native Task success."""
import argparse
import json
import os
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--seed", type=int, default=0)
    parser.add_argument("--variation", choices=("easy", "medium", "hard"), default="easy")
    parser.add_argument("--max-physics-steps", type=int,
                        help="Defaults: easy / medium 28000, hard 40000 (two stages and ~45 s of relaxation)")
    parser.add_argument("--worker", action="store_true", help=argparse.SUPPRESS)
    args = parser.parse_args()
    if args.max_physics_steps is None:
        args.max_physics_steps = {"easy": 28000, "medium": 28000, "hard": 40000}[args.variation]
    args.output = args.output.resolve()
    if args.worker:
        from topogym.simulator import Env, SimulatorConfig, SegmentRunner
        from topogym.planning.blanket_flatten import assist_support
        from topogym.planning.blanket_flatten.routes import PATCH, ROUTES
        from topogym.planning.blanket_flatten.robot_oracle import run_route_oracle
        # Frozen Blanket scenes are bound to CUDA float64, 2.5 ms / 4 substeps and
        # the prepared camera rig; RGB therefore stays enabled (Nyx).
        config = SimulatorConfig(task_id="blanket_flatten", variation_id=args.variation, compute_backend="cuda",
            enable_rgb=True, enable_privileged=True, control_mode="JOINT_ABS",
            max_physics_steps=args.max_physics_steps, work_dir=args.output/"scene",
            grasp_assist=dict(model="pbd_local_patch_v1", stable_time_s=.03,
                              targets=[dict(entity="blanket", **PATCH,
                                            max_strain_ratio=ROUTES[args.variation]["max_strain_ratio"])]))
        assist_support.enable()   # compatibility call; material support is now public runtime
        with Env(config) as env:
            # Tooling v7: the oracle reads no frames, so observations skip the camera pass (physics identical).
            env.defer_rgb = True
            env.reset(seed=args.seed)
            with SegmentRunner(env, args.output/"trail") as runner:
                report = run_route_oracle(env, runner, args.output, variation=args.variation)
        return 0 if report["task_success"] else 2

    args.output.mkdir(parents=True, exist_ok=False)
    from scripts.test_policy_cube_transfer import snapshot
    from topogym.utils.process_limits import run_guarded
    source = snapshot(args.output)
    command = [sys.executable, str(source/"scripts/oracle_runners/run_blanket_oracle.py"), "--worker",
               "--output", str(args.output), "--seed", str(args.seed), "--variation", args.variation,
               "--max-physics-steps", str(args.max_physics_steps)]
    (args.output/"invocation.json").write_text(json.dumps(dict(command=command), indent=2)+"\n")
    environment = dict(os.environ, PYTHONPATH=str(source), OMP_NUM_THREADS="1", MKL_NUM_THREADS="1",
                       OPENBLAS_NUM_THREADS="1", QD_NUM_THREADS="1", PYTHONUNBUFFERED="1")
    result = run_guarded(command, args.output, cwd=source, env=environment)
    print(f"exit={result}; {args.output}", flush=True)
    return result


if __name__ == "__main__":
    raise SystemExit(main())
