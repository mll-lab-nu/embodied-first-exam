#!/usr/bin/env python3
"""Freeze three lock object witnesses and optionally lift them to Genesis IK.

Does not run dynamics or change the Task's success gate. All results keep
object, sampled IK, collision, grasp and formal physical qualification separate.
"""
import argparse
from dataclasses import asdict
import hashlib
import json
import os
from pathlib import Path
import sys
import traceback

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


def worker(args):
    from topogym.config.registry import task_definition
    from topogym.config.scene import load_scene_config
    from topogym.simulator import SimulatorConfig
    from topogym.planning.lock_picking.object_route import construct_route, audit_route
    from topogym.utils.io import write_json_atomic, to_jsonable
    variants = ("easy", "medium", "hard") if args.variation == "all" else (args.variation,)
    summary = dict(scope="Coaxial object proof and sampled robot IK; no new physical success",
                   seed=args.seed, variants={}, accepted_physical_proofs=0)
    failed = False
    for variant in variants:
        output = args.output/variant
        output.mkdir(exist_ok=False)
        config = SimulatorConfig(task_id="lock_picking", variation_id=variant,
            robot_id="panda_robotiq", compute_backend="cpu", precision="64",
            enable_rgb=False, enable_privileged=True, work_dir=output/"scene")
        report = dict(variation=variant, seed=args.seed, status="running",
                      native_task_success=False, dynamics_verified=False)
        try:
            scene = load_scene_config(config)
            table = scene.env.world.table
            task = task_definition("lock_picking", variant)(seed=args.seed)
            task.declare(output/"object_assets", float(table.pos[2]+table.size[2]/2))
            g, stops = task.layout, task.config["rotor_stops"]
            states = construct_route(g, stops)
            certificate = audit_route(g, stops, states)
            report.update(status="object_verified", instance_id=task.instance_id,
                model_revision=task.model_revision, terminal_revision=task.terminal_revision,
                task_parameters=to_jsonable(task.config), geometry=asdict(g),
                simulator_config=to_jsonable(config), object_certificate=certificate,
                states=states, asset_sha256={str(p.relative_to(output/"object_assets")):
                    hashlib.sha256(p.read_bytes()).hexdigest()
                    for p in sorted((output/"object_assets").rglob("*")) if p.is_file()})
            write_json_atomic(output/"object_witness.json", report)
            print(variant, "object passed", certificate["retreats"], flush=True)
            if args.ik:
                import torch
                from topogym.simulator import Env
                from topogym.planning.lock_picking.kinematics import lift_route
                torch.set_num_threads(1)
                with Env(config) as env:
                    env.reset(seed=args.seed)
                    if task.instance_id != env._task.instance_id or asdict(env._task.layout) != asdict(g):
                        raise ValueError("IK environment does not match the object witness")
                    ik_report, samples = lift_route(env, states, grasp_roll_deg=args.grasp_roll_deg)
                    ik_report["asset_sha256"] = to_jsonable(env._asset_build.sha256)
                    write_json_atomic(output/"ik_report.json", ik_report)
                    write_json_atomic(output/"ik_samples.json", samples)
                    report["status"] = "object_and_ik_verified" if ik_report["passed"] else "ik_failed"
                    report["ik_report"] = "ik_report.json"
                    failed |= not ik_report["passed"]
                    print(variant, report["status"], ik_report.get("error", ""), flush=True)
            write_json_atomic(output/"report.json", report)
        except Exception:
            failed = True
            report.update(status="failed", error=traceback.format_exc())
            write_json_atomic(output/"report.json", report)
            print(report["error"], flush=True)
        summary["variants"][variant] = dict(status=report["status"], report=f"{variant}/report.json")
        write_json_atomic(args.output/"summary.json", summary)
    return 2 if failed else 0


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--variation", choices=("all", "easy", "medium", "hard"), default="all")
    parser.add_argument("--seed", type=int, default=0)
    parser.add_argument("--ik", action="store_true")
    parser.add_argument("--grasp-roll-deg", type=float, default=-45.)
    parser.add_argument("--worker", action="store_true", help=argparse.SUPPRESS)
    args = parser.parse_args()
    args.output = args.output.resolve()
    if args.worker:
        return worker(args)
    args.output.mkdir(parents=True, exist_ok=False)
    from scripts.test_policy_cube_transfer import snapshot
    from topogym.utils.process_limits import run_guarded
    source = snapshot(args.output)
    command = [sys.executable, str(source/"scripts/plan_lock_picking_oracle.py"), "--worker",
               "--output", str(args.output), "--variation", args.variation,
               "--seed", str(args.seed), "--grasp-roll-deg", str(args.grasp_roll_deg)]
    if args.ik:
        command.append("--ik")
    (args.output/"invocation.json").write_text(json.dumps(dict(command=command), indent=2)+"\n")
    environment = dict(os.environ, PYTHONPATH=str(source), OMP_NUM_THREADS="1",
        MKL_NUM_THREADS="1", OPENBLAS_NUM_THREADS="1", QD_NUM_THREADS="1")
    result = run_guarded(command, args.output, cwd=source, env=environment)
    print(f"exit={result}; {args.output}", flush=True)
    return result


if __name__ == "__main__":
    raise SystemExit(main())
