#!/usr/bin/env python3
"""Shared manager CLI for the Hedgehog/Claws plan, using SegmentRunner."""
import argparse
from dataclasses import asdict
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


def oracle_for(env):
    """Freeze manager oracle inputs; the policy never receives an Env handle."""
    from topogym.simulator.rollout_simulation.segment_contract import fingerprint
    from topogym.utils.io import to_jsonable
    task, robot = env._task, env._robot
    world = env._world.read_state()
    target, = task.placement_targets
    if task.task_id == "interlocked_claws":
        other, = task.placement_remainder
        ownership = {target: "left", other: "right"}
    else:
        ownership = {target: "arm"}
    grasps = {}
    for name, arm in ownership.items():
        group = robot.groups[arm]
        grasps[name] = dict(arm=arm, finger_link_indices=[int(robot.entity.get_link(n).idx) for n in group.grasp.finger_links])
    initial = dict(robot=robot.observe(), bodies={n: world["bodies"][n] for n in (*task.placement_targets, *task.placement_remainder)})
    identity = dict(instance_id=task.instance_id, model_revision=task.model_revision,
        terminal_revision=task.terminal_revision, goal_region_identity=task.goal_region_identity,
        asset_sha256=env._asset_build.sha256, initial_state_sha256=fingerprint(initial))
    return to_jsonable(dict(task_id=task.task_id, model_revision=task.model_revision, identity=identity,
        grasps=grasps, targets=task.placement_targets, remainder=task.placement_remainder,
        vertices=task.placement_vertices, goal_region=asdict(task.goal_region),
        stable_duration_s=task.config["stable_duration_s"], initial=initial))


def worker(args):
    from topogym.utils.io import write_json_atomic, to_jsonable
    output = args.output
    report = dict(status="running", task_id=args.task, variant=args.variant, seed=args.seed,
        part=args.part, started=time.time(), observation_mode="unlimited authorized world truth",
        assist="none", start="pregrasp" if args.task == "interlocked_claws" else "default_home",
        geometry_path_verified=False, robot_execution_verified=False, mechanism_completed=None,
        task_success=False, process_quality_passed=None, mechanism_evidence={}, media_qualified=False,
        contact_coverage="tick-end contacts; solver-substep completeness is not claimed")
    write_json_atomic(output/"run_report.json", report)
    try:
        if args.part == "geometry":
            from topogym.planning.rigid_reference.search import search_geometry
            evidence = search_geometry(args.task, args.variant, args.seed, output, samples=args.samples, rrt_iterations=args.rrt_iterations)
            write_json_atomic(output/"geometry_report.json", evidence)
            report.update(status=evidence["status"], mechanism_evidence=evidence["mechanism_evidence"])
            return 0 if evidence.get("mechanism_geometry_path_verified") else 2
        if args.part == "solve" and args.route is None:
            raise ValueError("No qualified robot route is bundled for this new geometry. Run --part geometry first; supply --route only after P1/T2 review.")
        if args.task == "hedgehog_in_cage" and args.part == "hold":
            raise ValueError("Hedgehog starts at home and needs an actual pickup route before a hold diagnostic")
        import numpy as np
        import torch
        from topogym.simulator import Env, SimulatorConfig, SegmentRunner
        from topogym.planning.rigid_reference.feedback import FrictionReferencePolicy, Limits
        from topogym.simulator.rollout_simulation.segment_contract import fingerprint
        torch.set_num_threads(1)
        config = SimulatorConfig(task_id=args.task, variation_id=args.variant,
            task_parameters={} if args.initial_finger_position is None else {"initial_finger_position_m": args.initial_finger_position},
            compute_backend=args.compute_backend, enable_rgb=not args.no_rgb,
            control_mode="EE_ABS", enable_privileged=True, physics_dt_s=args.physics_dt,
            control_decimation=args.control_decimation, solver_substeps=args.solver_substeps,
            max_physics_steps=int(np.ceil(args.episode_seconds/args.physics_dt)), work_dir=output/"scene")
        report["config"] = to_jsonable(config)
        if args.compute_backend == "cuda" and not torch.cuda.is_available():
            raise RuntimeError("CUDA/Nyx unavailable; use explicit --compute-backend cpu --no-rgb for physics diagnostics")
        with Env(config) as env:
            env.reset(seed=args.seed)
            oracle = oracle_for(env)
            write_json_atomic(output/"oracle.json", oracle)
            route = json.loads(args.route.read_text()) if args.route else None
            if args.part == "hold":
                # Easy/hard share only this diagnostic, never the medium route.
                class HoldDiagnostic(FrictionReferencePolicy):
                    task_id, robot_id, model_revision = args.task, "aloha", env._task.model_revision
                cls = HoldDiagnostic
            elif args.task == "interlocked_claws":
                from topogym.planning.interlocked_claws import InterlockedClawsMediumPolicy
                cls = InterlockedClawsMediumPolicy
            else:
                from topogym.planning.hedgehog_in_cage import HedgehogInCageMediumPolicy
                cls = HedgehogInCageMediumPolicy
            if args.part == "solve":
                # Fail closed until full robot collision evidence is linked.
                # A caller-controlled boolean cannot grant qualification.
                raise ValueError("Full robot route qualification is pending; solve execution is not yet enabled. Object geometry witnesses alone are insufficient.")
            policy = cls(oracle=oracle, route=route, part=args.part)
            parameters = dict(oracle=oracle, route=route, limits=asdict(Limits()), part=args.part)
            manifest = json.loads((output/"run_source_manifest.json").read_text())
            report.update(oracle_identity=oracle["identity"], submission_hash=fingerprint(dict(source=manifest, parameters=parameters)))
            write_json_atomic(output/"run_report.json", report)
            with SegmentRunner(env, output, prepared_output=True) as runner:
                result = runner.run_policy(request_id="friction-reference", policy=policy,
                    submission_hash=report["submission_hash"], mode="unlimited", state_fields=("world",))
                report.update(segment=to_jsonable(result), task_result=to_jsonable(env._task.result),
                    task_success=bool(env._task.result.task_success), last_phase=policy.phase,
                    policy_completed=policy.completed, failure=policy.failure,
                    maximum_grasp_drift=policy.max_drift, simulation_time_s=env._world.sim_time_s,
                    status="hold_passed" if policy.completed and result["reason"] == "policy_done" else "policy_failed")
                write_json_atomic(output/"phase_events.json", policy.events)
                write_json_atomic(output/"feedback_samples.json", policy.samples)
            # Round-trip belongs to T7, with a fresh policy instance afterwards.
            if args.check_rewind:
                before = oracle["initial"]
                access = env.interaction(privileged=True)
                access.rewind_to(runner.initial["state_ref"])
                after = oracle_for(env)["initial"]
                # Compare numeric state rather than renewed state IDs.
                report["segment0_rewind_equal"] = fingerprint(before) == fingerprint(after)
                report["restored_task_stable_time_s"] = env._task.stable_time_s
        return 0 if report["status"] == "hold_passed" else 2
    except Exception:
        report.update(status="failed", error=traceback.format_exc())
        return 1
    finally:
        report["wall_time_s"] = time.time()-report["started"]
        write_json_atomic(output/"run_report.json", report)


def main(task_id=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--task", choices=("hedgehog_in_cage", "interlocked_claws"), default=task_id, required=task_id is None)
    parser.add_argument("--variant", choices=("easy", "medium", "hard"), default="medium")
    parser.add_argument("--part", choices=("geometry", "hold", "solve"), default="geometry")
    parser.add_argument("--seed", type=int, default=0)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--route", type=Path)
    parser.add_argument("--samples", type=int, default=128)
    parser.add_argument("--rrt-iterations", type=int, default=1000)
    parser.add_argument("--episode-seconds", type=float, default=120.)
    parser.add_argument("--physics-dt", type=float, default=.0025)
    parser.add_argument("--control-decimation", type=int, default=10)
    parser.add_argument("--solver-substeps", type=int, default=4)
    parser.add_argument("--compute-backend", choices=("cuda", "cpu"), default="cuda")
    parser.add_argument("--no-rgb", action="store_true")
    parser.add_argument("--check-rewind", action="store_true")
    parser.add_argument("--initial-finger-position", type=float,
                        help="Task-owned Claws pregrasp diagnostic; native metres, recorded as a distinct configuration")
    parser.add_argument("--worker", action="store_true", help=argparse.SUPPRESS)
    args = parser.parse_args()
    if args.samples < 1:
        parser.error("--samples must be positive")
    if args.rrt_iterations < 0:
        parser.error("--rrt-iterations must be nonnegative")
    if args.initial_finger_position is not None and (args.task != "interlocked_claws" or args.part != "hold"):
        parser.error("--initial-finger-position is a Claws hold diagnostic only")
    args.output = args.output.resolve()
    if args.worker:
        raise SystemExit(worker(args))
    args.output.mkdir(parents=True, exist_ok=False)
    from scripts.test_policy_cube_transfer import snapshot
    source = snapshot(args.output)
    (args.output/"source_manifest.json").rename(args.output/"run_source_manifest.json")
    if args.route:
        route = args.route.read_bytes()
        args.route = args.output/"submitted_route.json"
        args.route.write_bytes(route)
    command = [sys.executable, str(source/"scripts/oracle_runners/run_rigid_reference_policy.py"), "--worker",
        "--task", args.task, "--variant", args.variant, "--part", args.part, "--seed", str(args.seed),
        "--output", str(args.output), "--samples", str(args.samples), "--episode-seconds", str(args.episode_seconds),
        "--rrt-iterations", str(args.rrt_iterations),
        "--physics-dt", str(args.physics_dt), "--control-decimation", str(args.control_decimation),
        "--solver-substeps", str(args.solver_substeps), "--compute-backend", args.compute_backend]
    for name in ("no_rgb", "check_rewind"):
        if getattr(args, name):
            command.append("--"+name.replace("_", "-"))
    if args.route:
        command.extend(["--route", str(args.route)])
    if args.initial_finger_position is not None:
        command.extend(["--initial-finger-position", str(args.initial_finger_position)])
    from topogym.utils.io import write_json_atomic
    write_json_atomic(args.output/"invocation.json", dict(command=command, snapshot=str(source)))
    environment = dict(os.environ, PYTHONPATH=str(source), OMP_NUM_THREADS="1", MKL_NUM_THREADS="1",
        OPENBLAS_NUM_THREADS="1", QD_NUM_THREADS="1", TOPOGYM_VISUAL_ASSET_ROOT=str(ROOT/".external/nyx-assets"))
    with (args.output/"runtime.log").open("x") as log:
        result = subprocess.run(command, cwd=source, env=environment, stdout=log, stderr=subprocess.STDOUT)
    print(f"exit={result.returncode}; {args.output}", flush=True)
    raise SystemExit(result.returncode)


if __name__ == "__main__":
    main()
