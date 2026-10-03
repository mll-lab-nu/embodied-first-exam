#!/usr/bin/env python3
"""Frozen-source Claws oracle: assisted pregrasp, JOINT_ABS separation and quiet hold."""
import argparse
import json
import os
from pathlib import Path
import shutil
import sys

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--witness", type=Path, required=True, help="Verified object_witness.json")
    parser.add_argument("--seed", type=int, default=0)
    parser.add_argument("--variation", choices=("easy", "medium", "hard"), default="easy")
    parser.add_argument("--joint-speed", type=float, help="Defaults: easy .2, medium .1, hard .08 rad/s")
    parser.add_argument("--piece-force-n", type=float, default=8., help="Guard limit on piece/piece contact force during motion")
    parser.add_argument("--integral-gain", type=float, default=.3, help="Joint-tracking integral correction gain; 0 = pure position control as in the historical A0 replay")
    parser.add_argument("--wrist-feedforward", action="store_true", help="Model-based wrist_rotate droop feedforward from the held piece's gravity moment")
    parser.add_argument("--relative-servo", action="store_true", help="Gentle closed-loop relative-pose correction on the arm holding the remaining piece during separation")
    parser.add_argument("--physics-dt", type=float, default=.025)
    parser.add_argument("--substeps", type=int, default=40)
    parser.add_argument("--control-decimation", type=int, default=1)
    parser.add_argument("--max-physics-steps", type=int, default=40000)
    parser.add_argument("--worker", action="store_true", help=argparse.SUPPRESS)
    args = parser.parse_args()
    if args.joint_speed is None:
        args.joint_speed = {"easy": .2, "medium": .1, "hard": .08}[args.variation]
    if args.joint_speed <= 0 or args.piece_force_n <= 0:
        parser.error("Joint speed and force limit must be positive")
    args.output = args.output.resolve()
    if args.worker:
        import torch
        from topogym.simulator import Env, SimulatorConfig, SegmentRunner
        from topogym.planning.interlocked_claws.recipes import run_claws_oracle
        from scripts.plan_claws_ik import grasp_assist_for
        from topogym.planning.interlocked_claws.object_oracle import audit_object_path
        from topogym.utils.io import write_json_atomic
        torch.set_num_threads(1)
        witness = json.loads(args.witness.read_text())
        audit = audit_object_path(witness, args.output/"witness_validation")
        write_json_atomic(args.output/"witness_audit.json", audit)
        if not audit["passed"]:
            raise ValueError("Object witness failed independent geometry validation")
        config = SimulatorConfig(task_id="interlocked_claws", variation_id=args.variation, compute_backend="cpu",
            enable_rgb=False, enable_privileged=True, control_mode="JOINT_ABS", physics_dt_s=args.physics_dt,
            solver_substeps=args.substeps, control_decimation=args.control_decimation,
            max_physics_steps=args.max_physics_steps, grasp_assist=grasp_assist_for(args.variation, args.seed),
            work_dir=args.output/"scene")
        with Env(config) as env:
            env.reset(seed=args.seed)
            def disk_guard(row):
                if row["state"]["physics_step"] % 40 == 0 and shutil.disk_usage(args.output).free < 128*1024**2:
                    raise RuntimeError("Claws stopped before evidence disk space fell below 128 MiB")
            env.add_state_sink(disk_guard)
            with SegmentRunner(env, args.output/"trail") as runner:
                report = run_claws_oracle(env, runner, args.output, witness, joint_speed_rad_s=args.joint_speed, piece_force_n=args.piece_force_n, integral_gain=args.integral_gain, wrist_feedforward=args.wrist_feedforward, relative_servo=args.relative_servo)
        return 0 if report["task_success"] else 2
    args.output.mkdir(parents=True, exist_ok=False)
    from scripts.test_policy_cube_transfer import snapshot
    from topogym.utils.process_limits import run_guarded
    source = snapshot(args.output)
    witness = args.output/"submitted_witness.json"
    shutil.copy2(args.witness, witness)
    command = [sys.executable, str(source/"scripts/oracle_runners/run_claws_oracle.py"), "--worker", "--output", str(args.output),
               "--witness", str(witness), "--seed", str(args.seed), "--variation", args.variation,
               "--joint-speed", str(args.joint_speed), "--piece-force-n", str(args.piece_force_n), "--integral-gain", str(args.integral_gain), "--physics-dt", str(args.physics_dt),
               "--substeps", str(args.substeps), "--control-decimation", str(args.control_decimation),
               "--max-physics-steps", str(args.max_physics_steps)]
    if args.wrist_feedforward:
        command.append("--wrist-feedforward")
    if args.relative_servo:
        command.append("--relative-servo")
    (args.output/"invocation.json").write_text(json.dumps(dict(command=command), indent=2)+"\n")
    environment = dict(os.environ, PYTHONPATH=str(source), OMP_NUM_THREADS="1", MKL_NUM_THREADS="1",
                       OPENBLAS_NUM_THREADS="1", QD_NUM_THREADS="1", PYTHONUNBUFFERED="1")
    result = run_guarded(command, args.output, cwd=source, env=environment)
    print(f"exit={result}; {args.output}", flush=True)
    return result


if __name__ == "__main__":
    raise SystemExit(main())
