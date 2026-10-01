#!/usr/bin/env python3
"""Frozen-source Hedgehog oracle with an explicit grasp-assistance flag."""
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
    parser.add_argument("--variation", choices=("easy", "medium", "hard"), default="medium")
    parser.add_argument("--pickup", type=Path, help="Explicit checked grasp candidate JSON; required outside medium")
    parser.add_argument("--search-iterations", type=int, default=30000)
    parser.add_argument("--assisted", action="store_true", help="Contact-triggered contact_weld_v1; not friction-only")
    parser.add_argument("--diagnostic", action="store_true", help="Allow a measured candidate pending Task qualification")
    parser.add_argument("--physics-dt", type=float, default=.025)
    parser.add_argument("--substeps", type=int, default=40)
    parser.add_argument("--control-decimation", type=int, default=1)
    parser.add_argument("--max-physics-steps", type=int, default=12000)
    parser.add_argument("--worker", action="store_true", help=argparse.SUPPRESS)
    args = parser.parse_args()
    if args.variation != "medium" and args.pickup is None:
        parser.error("An explicit --pickup is required for easy/hard until its default recipe is qualified")
    args.output = args.output.resolve()
    if args.worker:
        import torch
        from topogym.simulator import Env, SimulatorConfig, SegmentRunner
        from topogym.planning.hedgehog_in_cage.recipes import run_medium_oracle
        torch.set_num_threads(1)
        pickup = json.loads(args.pickup.read_text()) if args.pickup else None
        grasp = dict(model="none")
        if args.assisted:
            from dataclasses import asdict
            from topogym.tasks.hedgehog_in_cage.common import recommended_grasp_assist
            # Use the same authored ball-surface region as public trials. A
            # pickup file chooses motions, not the episode's permitted surface.
            grasp = asdict(recommended_grasp_assist(args.variation, args.seed))
            (args.output/"grasp_region.json").write_text(json.dumps(dict(
                construction="Task recommended authored ball-surface region",
                configuration_source="topogym.tasks.hedgehog_in_cage.common.recommended_grasp_assist",
                grasp_assist=grasp,
                acquisition="Fresh closing intent and bilateral native contacts for each binding"), indent=2)+"\n")
        config = SimulatorConfig(task_id="hedgehog_in_cage", variation_id=args.variation, compute_backend="cpu",
            enable_rgb=False, enable_privileged=True, control_mode="JOINT_ABS", physics_dt_s=args.physics_dt,
            solver_substeps=args.substeps, control_decimation=args.control_decimation,
            max_physics_steps=args.max_physics_steps, grasp_assist=grasp, work_dir=args.output/"scene")
        with Env(config) as env:
            env.reset(seed=args.seed)
            with SegmentRunner(env, args.output/"trail") as runner:
                report = run_medium_oracle(env, runner, args.output, pickup=pickup,
                                           search_iterations=args.search_iterations)
        if report["task_success"]:
            return 0
        if (args.diagnostic and report["candidate_reached"] and
                report["task_result"]["metrics"]["stable_time_s"] >= 2.):
            return 0
        return 2

    args.output.mkdir(parents=True, exist_ok=False)
    from scripts.test_policy_cube_transfer import snapshot
    from topogym.utils.process_limits import run_guarded
    source = snapshot(args.output)
    command = [sys.executable, str(source/"scripts/oracle_runners/run_hedgehog_oracle.py"), "--worker",
               "--output", str(args.output), "--seed", str(args.seed),
               "--physics-dt", str(args.physics_dt), "--substeps", str(args.substeps),
               "--control-decimation", str(args.control_decimation),
               "--max-physics-steps", str(args.max_physics_steps), "--variation", args.variation,
               "--search-iterations", str(args.search_iterations)]
    if args.pickup:
        import shutil
        copied = args.output/"submitted_pickup.json"
        shutil.copy2(args.pickup, copied)
        command += ["--pickup", str(copied)]
    if args.assisted:
        command.append("--assisted")
    if args.diagnostic:
        command.append("--diagnostic")
    (args.output/"invocation.json").write_text(json.dumps(dict(command=command), indent=2)+"\n")
    environment = dict(os.environ, PYTHONPATH=str(source), OMP_NUM_THREADS="1", MKL_NUM_THREADS="1",
                       OPENBLAS_NUM_THREADS="1", QD_NUM_THREADS="1", PYTHONUNBUFFERED="1",
                       TOPOGYM_VISUAL_ASSET_ROOT=str(ROOT/".external/nyx-assets"))
    result = run_guarded(command, args.output, cwd=source, env=environment)
    print(f"exit={result}; {args.output}", flush=True)
    return result


if __name__ == "__main__":
    raise SystemExit(main())
