#!/usr/bin/env python3
"""Freeze and execute a registered Coil variant through the standard runner."""
import argparse
import json
import os
import signal
from pathlib import Path
import subprocess
import sys
import time
import traceback

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))


def worker(output, no_rgb=False, part="all", physics_dt=None, control_decimation=None, solver_substeps=None,
           variant="easy", seed=0, compute_backend="cuda", episode_seconds=240., policy_kind="feedback"):
    import numpy as np
    import torch
    from topogym.simulator import Env, SimulatorConfig, SegmentRunner
    from topogym.planning.cast_coil.baseline import CastCoilBaselinePolicy, PARTS
    from topogym.planning.cast_coil.policy import CastCoilPolicy, variant_reference
    from topogym.tasks.cast_coil.common import recommended_grasp_assist
    from topogym.utils.io import write_json_atomic, to_jsonable
    from topogym.simulator.rollout_simulation.segment_contract import fingerprint
    torch.set_num_threads(1)
    defaults = SimulatorConfig()
    physics_dt = defaults.physics_dt_s if physics_dt is None else physics_dt
    control_decimation = defaults.control_decimation if control_decimation is None else control_decimation
    solver_substeps = defaults.solver_substeps if solver_substeps is None else solver_substeps
    assembly, route = variant_reference(variant)
    simplified = hasattr(assembly, "record")
    if simplified and policy_kind != "feedback":
        raise ValueError("Cube variants require their dedicated feedback policy")
    config = SimulatorConfig(task_id="cast_coil", variation_id="cast_coil_"+variant, robot_id="aloha",
        control_mode="EE_ABS", enable_privileged=True, enable_rgb=not no_rgb,
        compute_backend=compute_backend,
        physics_dt_s=physics_dt, control_decimation=control_decimation, solver_substeps=solver_substeps,
        max_physics_steps=round(episode_seconds/physics_dt), work_dir=output/"scene",
        grasp_assist=recommended_grasp_assist(variant, seed))
    report = dict(status="running", started=time.time(), config=to_jsonable(config), events=[],
                  from_default_home=True, mode="unlimited", part=part, segments=[],
                  variant=variant, seed=seed, policy=policy_kind, task_success=False,
                  qualification="single frozen instance; contact_weld_v1 assist; no half-dt qualification",
                  route=[dict(name=m.name, duration_s=m.duration_s) for m in route])
    default_timing = (physics_dt, control_decimation, solver_substeps) == (
        defaults.physics_dt_s, defaults.control_decimation, defaults.solver_substeps)
    report["timing_scope"] = ("simulator default timing" if default_timing else "explicit custom timing") + \
        "; execution outcome recorded separately; no half-dt qualification"
    report["horizon_scope"] = f"{episode_seconds:g} simulated seconds; extends the episode budget without changing its clock"
    write_json_atomic(output/"run_report.json", report)
    try:
        if compute_backend == "cuda" and not torch.cuda.is_available():
            raise RuntimeError("CUDA unavailable; use explicit --compute-backend cpu --no-rgb")
        with Env(config) as env:
            env.reset(seed=seed)
            costs = report["timing_costs"] = {}
            def timed(obj, name):
                original = getattr(obj, name)
                key = type(obj).__name__+"."+name
                costs[key] = dict(calls=0, seconds=0.)
                def call(*args, **kwargs):
                    start = time.perf_counter()
                    try:
                        return original(*args, **kwargs)
                    finally:
                        costs[key]["calls"] += 1
                        costs[key]["seconds"] += time.perf_counter()-start
                setattr(obj, name, call)
            for name in ("advance", "read_state", "capture_state"):
                timed(env._world, name)
            timed(env._sensors, "sample")
            report.update(instance_id=env._task.instance_id, initial_robot=to_jsonable(env._robot.observe()),
                          initial_task=to_jsonable(env._task.result), asset_sha256=to_jsonable(env._asset_build.sha256))
            report["contact_link_names"] = {str(link.idx): f"{name}/{link.name}" for name, entity in env._world.entities.items()
                                             for link in getattr(entity, "links", ())}
            write_json_atomic(output/"run_report.json", report)
            if simplified:
                from topogym.planning.cast_coil.simplified_policy import SimplifiedCoilPolicy
                policy = SimplifiedCoilPolicy(body_origins=env._task.body_origins, part=part,
                    variant=variant, seed=seed, task_parameters=env._task.config)
            elif policy_kind == "baseline":
                policy = CastCoilBaselinePolicy(body_origins=env._task.body_origins, part=part, route=route)
            else:
                policy = CastCoilPolicy(body_origins=env._task.body_origins, part=part, variant=variant)
            coil_links = {link.idx for name in PARTS.values() for link in env._world.entities[name].links}
            contact_summary = report["coil_contacts"] = dict(ticks=0, maximum_penetration_m=0., maximum_force_sum_n=0.)
            with SegmentRunner(env, output, prepared_output=True) as runner:
                with (output/"private/coil_monitor.jsonl").open("x", buffering=1) as monitor:
                    last_phase = [None]
                    def tick(row):
                        world = row["world"]
                        record = dict(state=row["state"], phase=policy.phase, grasp=world["grasp"],
                                      task_result=env._task.result, bodies=world["bodies"],
                                      assist_active=world["assist_active"], tracking=getattr(policy, "tracking", {}))
                        contacts = world.get("contacts", {})
                        mask = np.array([int(a) in coil_links and int(b) in coil_links and a != b
                                         for a,b in zip(contacts.get("link_a", ()), contacts.get("link_b", ()))], dtype=bool)
                        if mask.any():
                            contact_summary["ticks"] += 1
                            depth = float(np.max(np.asarray(contacts["penetration"])[mask]))
                            force = float(np.linalg.norm(np.asarray(contacts["force"])[mask], axis=-1).sum())
                            contact_summary["maximum_penetration_m"] = max(contact_summary["maximum_penetration_m"], depth)
                            contact_summary["maximum_force_sum_n"] = max(contact_summary["maximum_force_sum_n"], force)
                            record["coil_contact"] = dict(penetration_m=depth, force_sum_n=force)
                        monitor.write(json.dumps(to_jsonable(record), allow_nan=False)+"\n")
                        report["events"].extend(to_jsonable(world["grasp"]["events"]))
                        if row["state"]["physics_step"] % 100 == 0 or policy.phase != last_phase[0]:
                            write_json_atomic(output/"progress.json", record)
                            write_json_atomic(output/"timing.json", costs)
                        if policy.phase != last_phase[0]:
                            print(policy.phase, row["state"]["sim_time_s"], flush=True)
                            last_phase[0] = policy.phase
                    env.add_state_sink(tick)
                    tick(env.tick_record())
                    source = json.loads((output/"run_source_manifest.json").read_text())
                    result = runner.run_policy(request_id="coil-"+variant, policy=policy,
                        submission_hash=fingerprint(dict(source=source, part=part, variant=variant, seed=seed, policy=policy_kind)), mode="unlimited", state_fields=("world",))
                    world = env._world.read_state()
                    report.update(segments=[to_jsonable(result)], last_phase=policy.phase,
                        task_result=to_jsonable(env._task.result), final_world=to_jsonable(world),
                        statistics=runner._evidence.statistics(), physics_steps=env._world.physics_step,
                        task_success=bool(env._task.result.task_success), simulation_time_s=env._world.sim_time_s,
                        phase_endpoints=getattr(policy, "samples", []))
                    success = (env._task.result.task_success and not world["assist_active"] if part == "all" else result["reason"] == "policy_done")
                    success = success and result.get("evidence_complete", False) and result.get("physics_tick_complete", False)
                    if not success:
                        raise RuntimeError(f"Run did not pass: {result['reason']} in {policy.phase}")
                    report["status"] = "passed"
    except BaseException:
        report.update(status="failed", error=traceback.format_exc())
        raise
    finally:
        report["wall_time_s"] = time.time()-report["started"]
        write_json_atomic(output/"run_report.json", report)


def main():
    from topogym.simulator import SimulatorConfig
    defaults = SimulatorConfig()
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", required=True)
    parser.add_argument("--no-rgb", action="store_true")
    parser.add_argument("--part", choices=["all", "pickup"], default="all")
    parser.add_argument("--variant", choices=["very_easy", "easier", "easy", "medium", "hard"], default="easy")
    parser.add_argument("--seed", type=int, default=0)
    parser.add_argument("--compute-backend", choices=["cpu", "cuda"], default="cuda")
    parser.add_argument("--episode-seconds", type=float, default=240.)
    parser.add_argument("--policy", choices=["feedback", "baseline"], default="feedback")
    parser.add_argument("--worker", action="store_true")
    parser.add_argument("--physics-dt", type=float, default=defaults.physics_dt_s,
                        help="Env tick in seconds; defaults to SimulatorConfig")
    parser.add_argument("--control-decimation", type=int, default=defaults.control_decimation,
                        help="Env ticks per action; defaults to SimulatorConfig")
    parser.add_argument("--solver-substeps", type=int, default=defaults.solver_substeps,
                        help="Integration substeps per Env tick; defaults to SimulatorConfig")
    args = parser.parse_args()
    if args.compute_backend == "cpu" and not args.no_rgb:
        parser.error("--compute-backend cpu requires --no-rgb")
    output = Path(args.output).resolve()
    if args.worker:
        return worker(output, args.no_rgb, args.part, args.physics_dt, args.control_decimation, args.solver_substeps,
                      args.variant, args.seed, args.compute_backend, args.episode_seconds, args.policy)
    output.mkdir(parents=True, exist_ok=False)
    from scripts.test_policy_cube_transfer import snapshot
    source = snapshot(output)
    (output/"source_manifest.json").rename(output/"run_source_manifest.json")
    command = [sys.executable, str(source/"scripts/oracle_runners/run_cast_coil_policy.py"), "--worker", "--output", str(output), "--part", args.part]
    command += ["--physics-dt", str(args.physics_dt), "--control-decimation", str(args.control_decimation), "--solver-substeps", str(args.solver_substeps)]
    command += ["--variant", args.variant, "--seed", str(args.seed), "--compute-backend", args.compute_backend,
                "--episode-seconds", str(args.episode_seconds), "--policy", args.policy]
    if args.no_rgb:
        command.append("--no-rgb")
    (output/"invocation.json").write_text(json.dumps(dict(command=command), indent=2))
    with (output/"runtime.log").open("x") as log:
        process = subprocess.Popen(command, cwd=source, stdout=log, stderr=subprocess.STDOUT, start_new_session=True,
            env=dict(os.environ, PYTHONPATH=str(source), OMP_NUM_THREADS="1", MKL_NUM_THREADS="1", OPENBLAS_NUM_THREADS="1",
                     TOPOGYM_VISUAL_ASSET_ROOT=str(ROOT/".external/nyx-assets")))
        import psutil
        try:
            with (output/"resources.jsonl").open("x", buffering=1) as monitor:
                while process.poll() is None:
                    row = dict(time=time.time(), cpu_percent=psutil.cpu_percent(),
                               memory_percent=psutil.virtual_memory().percent)
                    monitor.write(json.dumps(row)+"\n")
                    if row["memory_percent"] >= 90:
                        (output/"resource_stop.json").write_text(json.dumps(row, indent=2))
                        raise RuntimeError("System memory reached 90%; stopping this run")
                    time.sleep(1)
        finally:
            if process.poll() is None:
                os.killpg(process.pid, signal.SIGTERM)
                try:
                    process.wait(timeout=10)
                except subprocess.TimeoutExpired:
                    os.killpg(process.pid, signal.SIGKILL)
                    process.wait()
    print(f"exit={process.returncode}; {output}")
    raise SystemExit(process.returncode)


if __name__ == "__main__":
    main()
