#!/usr/bin/env python3
"""Execute a checked Rope Threading relay IK plan through the standard Env (CUDA FEM/IPC).

The policy replays plan_rope_threading_ik.py samples as EE_ABS actions with
measured-station feedback before each pinch; the IPC soft-band assist holds
the rope after real bilateral finger proximity. The report records the native
Task result; success needs the Task's own crossing, thickness and quiet checks.
"""
import argparse
import json
import os
from pathlib import Path
import hashlib
import sys
import time
import traceback

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))


def worker(output, samples_path, variant, seed, *, physics_dt, control_decimation, solver_substeps,
           episode_seconds, speed_m_s, no_rgb=False):
    import torch
    from topogym.simulator import Env, SimulatorConfig, SegmentRunner
    from topogym.planning.rope_threading.relay_policy import RopeRelayPolicy
    from topogym.planning.rope_threading.relay_artifact import load_plan, validate_scene
    from topogym.utils.grasp import GraspAssistConfig, SoftGraspTarget
    from topogym.utils.io import write_json_atomic, to_jsonable
    from topogym.simulator.rollout_simulation.segment_contract import fingerprint
    torch.set_num_threads(1)
    samples, metadata = load_plan(samples_path, variant=variant, seed=seed)
    config = SimulatorConfig(task_id="rope_threading", variation_id="rope_threading_"+variant, robot_id="aloha",
        control_mode="EE_ABS", observation_mode="EE", seed=seed, history_storage="segment",
        enable_privileged=True, enable_rgb=not no_rgb, compute_backend="cuda",
        physics_dt_s=physics_dt, control_decimation=control_decimation, solver_substeps=solver_substeps,
        max_physics_steps=round(episode_seconds/physics_dt), work_dir=output/"scene",
        grasp_assist=GraspAssistConfig(model="ipc_soft_band_v1", targets=(SoftGraspTarget("rope"),)))
    report = dict(status="running", started=time.time(), config=to_jsonable(config), variant=variant, seed=seed,
                  samples=str(samples_path), samples_sha256=hashlib.sha256(samples_path.read_bytes()).hexdigest(),
                  plan=metadata["plan"], plan_identity=metadata["identity"], sample_count=len(samples), speed_m_s=speed_m_s, task_success=False,
                  from_default_home=True, mode="unlimited", events=[], phases=[],
                  qualification="unqualified", completion_contract="task_success",
                  scope="EE_ABS replay with measured-station feedback and contact-gated ipc_soft_band_v1; sampled IK is not a physics certificate")
    write_json_atomic(output/"run_report.json", report)
    try:
        if not torch.cuda.is_available():
            raise RuntimeError("CUDA unavailable; FEM/IPC requires a CUDA host")
        with Env(config) as env:
            env.reset(seed=seed)
            from topogym.config.scene import load_scene_config
            from topogym.utils.arrays import to_numpy
            asset_dir = Path(next(e.asset_path for e in env._scene_spec.entities if e.name == "rope")).parent
            validate_scene(metadata, task=env._task, scene=load_scene_config(config),
                           home_qpos=to_numpy(env._robot.entity.get_qpos()).reshape(-1), asset_dir=asset_dir)
            report.update(instance_id=env._task.instance_id, initial_task=to_jsonable(env._task.result),
                          asset_sha256=to_jsonable(env._asset_build.sha256))
            write_json_atomic(output/"run_report.json", report)
            policy = RopeRelayPolicy(samples, speed_m_s=speed_m_s, control_dt_s=physics_dt*control_decimation)
            with SegmentRunner(env, output, prepared_output=True) as runner:
                with (output/"private/relay_monitor.jsonl").open("x", buffering=1) as monitor:
                    last = [None]
                    def tick(row):
                        world = row["world"]
                        record = dict(state=row["state"], phase=policy.phase, index=policy.index,
                                      grasp={s: dict(binding=(h["binding"] or {}).get("target"), phase=h["phase"])
                                             for s, h in world["grasp"]["hands"].items()},
                                      task_result=to_jsonable(env._task.result), tracking=to_jsonable(policy.tracking))
                        monitor.write(json.dumps(to_jsonable(record), allow_nan=False)+"\n")
                        report["events"].extend(to_jsonable(world["grasp"]["events"]))
                        if policy.phase != last[0]:
                            report["phases"].append(dict(phase=policy.phase, sim_time_s=row["state"]["sim_time_s"],
                                                         crossings=to_jsonable(env._task.result.metrics.get("crossing_sequence"))
                                                         if hasattr(env._task.result, "metrics") else None))
                            write_json_atomic(output/"progress.json", record)
                            print(policy.phase, row["state"]["sim_time_s"], flush=True)
                            last[0] = policy.phase
                        elif row["state"]["physics_step"] % 400 == 0:
                            write_json_atomic(output/"progress.json", record)
                    env.add_state_sink(tick)
                    tick(env.tick_record())
                    source = json.loads((output/"run_source_manifest.json").read_text())
                    result = runner.run_policy(request_id="rope-relay-"+variant, policy=policy,
                        submission_hash=fingerprint(dict(source=source, variant=variant, seed=seed,
                                                         samples_sha256=report["samples_sha256"], config=to_jsonable(config), speed=speed_m_s)),
                        mode="unlimited", state_fields=("world",))
                    world = env._world.read_state()
                    report.update(segments=[to_jsonable(result)], last_phase=policy.phase, tracking=to_jsonable(policy.tracking),
                                  task_result=to_jsonable(env._task.result), physics_steps=env._world.physics_step,
                                  task_success=bool(env._task.result.task_success), simulation_time_s=env._world.sim_time_s,
                                  assist_active=bool(world["assist_active"]))
                    report["status"] = completion_status(env._task.result, result)
                    report["policy_completed"] = policy.done
                    report["robot_execution_verified"] = report["status"] == "task_success"
    except BaseException:
        report.update(status="failed", error=traceback.format_exc())
        raise
    finally:
        report["wall_time_s"] = time.time()-report["started"]
        write_json_atomic(output/"run_report.json", report)
    return 0 if report["status"] == "task_success" else 1


def completion_status(task_result, segment):
    if not segment.get("evidence_complete") or not segment.get("physics_tick_complete"):
        return "incomplete_evidence"
    if segment.get("reason") not in {"env_terminal", "policy_done"}:
        return "execution_failed"
    if task_result.task_success and task_result.terminated:
        return "task_success"
    return "not_passed"


def main():
    from topogym.simulator import SimulatorConfig
    defaults = SimulatorConfig()
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", required=True)
    parser.add_argument("--samples", required=True, help="relay_samples.npz from plan_rope_threading_ik.py")
    parser.add_argument("--variant", choices=["easy", "medium", "hard"], required=True)
    parser.add_argument("--seed", type=int, default=0)
    parser.add_argument("--episode-seconds", type=float, default=400.)
    parser.add_argument("--speed", type=float, default=.04, help="TCP speed in m/s while replaying samples")
    parser.add_argument("--physics-dt", type=float, default=defaults.physics_dt_s)
    parser.add_argument("--control-decimation", type=int, default=defaults.control_decimation)
    parser.add_argument("--solver-substeps", type=int, default=defaults.solver_substeps)
    parser.add_argument("--no-rgb", action="store_true", help="Explicitly disable Nyx recording")
    parser.add_argument("--worker", action="store_true", help=argparse.SUPPRESS)
    args = parser.parse_args()
    import math
    if not all(math.isfinite(v) and v > 0 for v in (args.physics_dt, args.speed, args.episode_seconds)) or min(args.control_decimation, args.solver_substeps) < 1:
        parser.error("Timing and speed must be finite and positive")
    output = Path(args.output).resolve()
    samples = Path(args.samples).resolve()
    if args.worker:
        return worker(output, samples, args.variant, args.seed, physics_dt=args.physics_dt,
                      control_decimation=args.control_decimation, solver_substeps=args.solver_substeps,
                      episode_seconds=args.episode_seconds, speed_m_s=args.speed, no_rgb=args.no_rgb)
    from topogym.planning.rope_threading.relay_artifact import load_plan
    load_plan(samples, variant=args.variant, seed=args.seed)
    output.mkdir(parents=True, exist_ok=False)
    from scripts.test_policy_cube_transfer import snapshot
    source = snapshot(output)
    (output/"source_manifest.json").rename(output/"run_source_manifest.json")
    frozen = output/"relay_samples.npz"
    frozen.write_bytes(samples.read_bytes())
    command = [sys.executable, str(source/"scripts/oracle_runners/run_rope_threading_relay.py"), "--worker", "--output", str(output),
               "--samples", str(frozen), "--variant", args.variant, "--seed", str(args.seed),
               "--episode-seconds", str(args.episode_seconds), "--speed", str(args.speed),
               "--physics-dt", str(args.physics_dt), "--control-decimation", str(args.control_decimation),
               "--solver-substeps", str(args.solver_substeps)]
    if args.no_rgb:
        command += ["--no-rgb"]
    (output/"invocation.json").write_text(json.dumps(dict(command=command), indent=2)+"\n")
    from topogym.utils.process_limits import run_guarded
    result = run_guarded(command, output, cwd=source,
        env=dict(os.environ, PYTHONPATH=str(source), OMP_NUM_THREADS="1", MKL_NUM_THREADS="1", OPENBLAS_NUM_THREADS="1",
                 PYOPENGL_PLATFORM="egl", TOPOGYM_VISUAL_ASSET_ROOT=str(ROOT/".external/nyx-assets")))
    print(f"exit={result}; {output}")
    return result



if __name__ == "__main__":
    raise SystemExit(main())
