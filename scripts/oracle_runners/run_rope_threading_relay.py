#!/usr/bin/env python3
"""Execute a checked Rope Threading relay IK plan through the standard Env (CUDA FEM/IPC).

The policy replays plan_rope_threading_ik.py samples as JOINT_ABS actions with
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

# Rope's Harbor v12 solver profile; the packaged 75-degree settled state does
# not match these 0-degree instances and must not be loaded.
TOOLING_IPC_OPTIONS = dict(newton_tolerance=1e-3, linear_system_tolerance=1e-5,
                           collision_detection_method="linear_bvh")


def worker(output, samples_path, variant, seed, *, physics_dt, control_decimation, solver_substeps,
           episode_seconds, speed_m_s, no_rgb=False, tooling_ipc=False, free_speed_m_s=None, grasp_max_strain=1.3,
           rope_young_modulus=None, feedback_joint_limit=.25, ipc_tolerance_scale=1., material_feedback=False,
           settle_seconds=5., grasp_strength=100., max_feedback_m=.08,
           feedback_position_tolerance_m=1e-4, feedback_orientation_tolerance_rad=1e-3, measured_keeper=False,
           grasp_follow_error_m=.01, grasp_max_penetration_m=.002, allow_covered_grasp=False, normalize_keeper=False, measured_regrasps=False):
    import torch
    from topogym.simulator import Env, SimulatorConfig, SegmentRunner
    from topogym.planning.rope_threading.relay_policy import RopeRelayPolicy, LiveArmIK
    from topogym.planning.rope_threading.relay_artifact import load_plan, validate_scene
    from topogym.planning.calibration_tools.adapters.rope_threading import relay_diagnostics, MeasuredKeeperPlanner
    from topogym.planning.calibration_tools.candidates import build_candidate
    from topogym.utils.grasp import GraspAssistConfig, SoftGraspTarget
    from topogym.utils.io import write_json_atomic, to_jsonable
    from topogym.simulator.rollout_simulation.segment_contract import fingerprint
    torch.set_num_threads(1)
    samples, metadata = load_plan(samples_path, variant=variant, seed=seed)
    candidate = {} if rope_young_modulus is None else dict(materials=dict(rope=dict(E=rope_young_modulus)))
    ipc_options = dict(TOOLING_IPC_OPTIONS) if tooling_ipc else {}
    if tooling_ipc:
        for name in ("newton_tolerance", "linear_system_tolerance"):
            ipc_options[name] *= ipc_tolerance_scale
    config = SimulatorConfig(task_id="rope_threading", variation_id="rope_threading_"+variant, robot_id="aloha",
        task_parameters=metadata["identity"].get("task_parameters", {}),
        control_mode="JOINT_ABS", observation_mode="EE", seed=seed, history_storage="segment",
        enable_privileged=True, enable_rgb=not no_rgb, compute_backend="cuda",
        physics_dt_s=physics_dt, control_decimation=control_decimation, solver_substeps=solver_substeps,
        max_physics_steps=round(episode_seconds/physics_dt), work_dir=output/"scene",
        ipc_options=ipc_options,
        grasp_assist=GraspAssistConfig(model="ipc_soft_band_v1",
            max_translation_error_m=grasp_follow_error_m, max_penetration_m=grasp_max_penetration_m,
            targets=(SoftGraspTarget("rope", max_strain_ratio=grasp_max_strain, strength=grasp_strength,
                                     require_exposed_patch=not allow_covered_grasp),)))
    report = dict(status="running", started=time.time(), config=to_jsonable(config), variant=variant, seed=seed,
                  samples=str(samples_path), samples_sha256=hashlib.sha256(samples_path.read_bytes()).hexdigest(),
                  plan=metadata["plan"], plan_identity=metadata["identity"], sample_count=len(samples), speed_m_s=speed_m_s, task_success=False,
                  plan_complete=metadata.get("complete_relay", True), plan_scope=metadata["scope"],
                  requested_material_candidate=candidate,
                  from_default_home=True, mode="unlimited", events=[], phases=[],
                  qualification="unqualified", completion_contract="task_success",
                  solver_profile=("harbor_v12_rope" if ipc_tolerance_scale == 1 else "scaled_tooling_experiment")
                      if tooling_ipc else "simulator_default",
                  scope="JOINT_ABS replay with planned-branch station feedback and contact-gated ipc_soft_band_v1; sampled IK is not a physics certificate")
    write_json_atomic(output/"run_report.json", report)
    try:
        if not torch.cuda.is_available():
            raise RuntimeError("CUDA unavailable; FEM/IPC requires a CUDA host")
        report["gpu"] = torch.cuda.get_device_name()
        with Env(config) as env:
            with build_candidate(env, candidate) as material_report:
                env.reset(seed=seed)
            report["material_candidate"] = to_jsonable(material_report)
            from topogym.config.scene import load_scene_config
            from topogym.utils.arrays import to_numpy
            asset_dir = Path(next(e.asset_path for e in env._scene_spec.entities if e.name == "rope")).parent
            validate_scene(metadata, task=env._task, scene=load_scene_config(config),
                           home_qpos=to_numpy(env._robot.entity.get_qpos()).reshape(-1), asset_dir=asset_dir)
            report.update(instance_id=env._task.instance_id, initial_task=to_jsonable(env._task.result),
                          asset_sha256=to_jsonable(env._asset_build.sha256))
            write_json_atomic(output/"run_report.json", report)
            policy = RopeRelayPolicy(samples, kinematics=LiveArmIK(env._robot, max_branch_step_rad=feedback_joint_limit,
                                     position_tolerance_m=feedback_position_tolerance_m,
                                     orientation_tolerance_rad=feedback_orientation_tolerance_rad), speed_m_s=speed_m_s,
                                     control_dt_s=physics_dt*control_decimation, free_speed_m_s=free_speed_m_s,
                                     material_feedback=material_feedback, settle_s=settle_seconds, max_feedback_m=max_feedback_m,
                                     keeper_planner=MeasuredKeeperPlanner(output/"calibration", metadata, normalize=normalize_keeper) if measured_keeper else None, measured_regrasps=measured_regrasps)
            report["policy_options"] = dict(joint_speed_rad_s=policy.joint_speed,
                angular_speed_rad_s=policy.angular_speed, max_feedback_m=policy.max_feedback,
                feedback_decay_m=policy.decay, pinch_opening_m=policy.pinch, free_speed_m_s=policy.free_speed,
                settle_s=policy.settle*policy.dt, finish_mode="hold_last_grasp", feedback_joint_limit_rad=feedback_joint_limit,
                material_feedback=material_feedback, material_feedback_limit_rad=.8)
            report["policy_options"].update(feedback_position_tolerance_m=feedback_position_tolerance_m,
                feedback_orientation_tolerance_rad=feedback_orientation_tolerance_rad, feedback_ik_iterations=400,
                measured_keeper=measured_keeper, normalize_keeper=normalize_keeper, measured_regrasps=measured_regrasps)
            write_json_atomic(output/"run_report.json", report)
            # Owner run: steps.jsonl references the world in private/physics_states.jsonl instead of copying it.
            with SegmentRunner(env, output, prepared_output=True, history_privileged="reference") as runner:
                with (output/"private/relay_monitor.jsonl").open("x", buffering=1) as monitor:
                    last = [None]
                    def tick(row):
                        world = row["world"]
                        record = dict(state=row["state"], wall_time_s=time.time()-report["started"],
                                      phase=policy.phase, index=policy.index,
                                      grasp={s: dict(binding=(h["binding"] or {}).get("target"), phase=h["phase"])
                                             for s, h in world["grasp"]["hands"].items()},
                                      task_result=to_jsonable(env._task.result), tracking=to_jsonable(policy.tracking))
                        if row["state"]["physics_step"] % control_decimation == 0:
                            record["calibration"] = relay_diagnostics(row, policy)
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
                                                         samples_sha256=report["samples_sha256"], config=to_jsonable(config),
                                                         material_candidate=report["material_candidate"],
                                                         policy_options=report["policy_options"], speed=speed_m_s)),
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
    parser.add_argument("--settle-seconds", type=float, default=5., help="Retain the final grasp for the native quiet check")
    parser.add_argument("--speed", type=float, default=.04, help="TCP speed in m/s while replaying samples")
    parser.add_argument("--free-speed", type=float, help="Optional separate transit/retreat/park speed in m/s")
    parser.add_argument("--grasp-max-strain", type=float, default=1.3,
                        help="Explicit soft-grasp material edge-ratio gate; native volume checks remain active")
    parser.add_argument("--allow-covered-grasp", action="store_true", help="Allow bilateral side grasps below another rope segment; disable the gravity-up exposure gate")
    parser.add_argument("--grasp-follow-error", type=float, default=.01, help="Soft-grasp follow error gate (m)")
    parser.add_argument("--grasp-max-penetration", type=float, default=.002, help="Soft-grasp obstacle penetration gate (m)")
    parser.add_argument("--grasp-strength", type=float, default=100.,
                        help="Native contact-gated soft-band constraint strength")
    parser.add_argument("--rope-young-modulus", type=float,
                        help="Exploratory FEM E (Pa), applied by calibration_tools at scene build; recorded separately")
    parser.add_argument("--allow-prefix", action="store_true", help="Explicitly execute a partial calibration artifact")
    parser.add_argument("--material-feedback", action="store_true",
                        help="Align the grasp approach with the measured material tangent (limit .8 rad)")
    parser.add_argument("--measured-regrasps", action="store_true", help="Use measured FEM grasp planning and normalization for later relay acquisitions")
    parser.add_argument("--normalize-keeper", action="store_true", help="After native keeper acquisition, raise/rotate the sagged body towards its nominal supported pose")
    parser.add_argument("--measured-keeper", action="store_true", help="Plan stationary helper grasps from measured FEM state on a CPU ghost robot")
    parser.add_argument("--feedback-joint-limit", type=float, default=.25,
                        help="Maximum feedback IK deviation from the planned joints, in radians")
    parser.add_argument("--max-feedback", type=float, default=.08, help="Maximum measured material-station correction (m)")
    parser.add_argument("--feedback-position-tolerance", type=float, default=1e-4, help="Checked FK position residual (m)")
    parser.add_argument("--feedback-orientation-tolerance", type=float, default=1e-3, help="Checked FK orientation residual (rad)")
    parser.add_argument("--ipc-tolerance-scale", type=float, default=1.,
                        help="Experimental scale on both v12 solve tolerances; requires --tooling-ipc")
    parser.add_argument("--physics-dt", type=float, default=defaults.physics_dt_s)
    parser.add_argument("--control-decimation", type=int, default=defaults.control_decimation)
    parser.add_argument("--solver-substeps", type=int, default=defaults.solver_substeps)
    parser.add_argument("--no-rgb", action="store_true", help="Explicitly disable Nyx recording")
    parser.add_argument("--tooling-ipc", action="store_true",
                        help="Use v12 rope IPC (one substep, Newton/PCG 1e-3/1e-5, linear_bvh)")
    parser.add_argument("--worker", action="store_true", help=argparse.SUPPRESS)
    args = parser.parse_args()
    if args.measured_regrasps and not (args.measured_keeper and args.normalize_keeper):
        parser.error("--measured-regrasps requires --measured-keeper and --normalize-keeper")
    if args.normalize_keeper and not args.measured_keeper:
        parser.error("--normalize-keeper requires --measured-keeper")
    if args.tooling_ipc:
        args.solver_substeps = 1
    import math
    if not all(math.isfinite(v) and v > 0 for v in (args.physics_dt, args.speed, args.episode_seconds, args.settle_seconds)) or min(args.control_decimation, args.solver_substeps) < 1:
        parser.error("Timing and speed must be finite and positive")
    if args.free_speed is not None and not (math.isfinite(args.free_speed) and args.free_speed > 0):
        parser.error("--free-speed must be finite and positive")
    if not math.isfinite(args.grasp_max_strain) or args.grasp_max_strain <= 1:
        parser.error("--grasp-max-strain must be finite and exceed one")
    if not (0 < args.grasp_follow_error <= .05 and 0 < args.grasp_max_penetration <= .02):
        parser.error("Grasp follow error must be (0,.05] m and penetration (0,.02] m")
    if not math.isfinite(args.grasp_strength) or args.grasp_strength <= 0:
        parser.error("--grasp-strength must be finite and positive")
    if not (0 < args.max_feedback <= .3 and 0 < args.feedback_position_tolerance <= .005
            and 0 < args.feedback_orientation_tolerance <= .1):
        parser.error("Feedback bounds: position correction (0,.3] m, IK residual (0,.005] m / (0,.1] rad")
    if args.rope_young_modulus is not None and not (math.isfinite(args.rope_young_modulus) and args.rope_young_modulus > 0):
        parser.error("--rope-young-modulus must be finite and positive")
    if not math.isfinite(args.feedback_joint_limit) or not 0 < args.feedback_joint_limit < 1.5:
        parser.error("--feedback-joint-limit must be in (0, 1.5) radians")
    if not math.isfinite(args.ipc_tolerance_scale) or args.ipc_tolerance_scale <= 0 or (args.ipc_tolerance_scale != 1 and not args.tooling_ipc):
        parser.error("--ipc-tolerance-scale must be positive; non-default requires --tooling-ipc")
    output = Path(args.output).resolve()
    samples = Path(args.samples).resolve()
    from topogym.planning.rope_threading.relay_artifact import load_plan
    loaded, metadata = load_plan(samples, variant=args.variant, seed=args.seed)
    if args.material_feedback and any("station_tangent" not in row for row in loaded):
        parser.error("--material-feedback requires regenerated samples with station_tangent")
    if not metadata.get("complete_relay", True) and not args.allow_prefix:
        parser.error("This is a partial relay probe; --allow-prefix is required")
    if args.worker:
        return worker(output, samples, args.variant, args.seed, physics_dt=args.physics_dt,
                      control_decimation=args.control_decimation, solver_substeps=args.solver_substeps,
                      episode_seconds=args.episode_seconds, speed_m_s=args.speed, no_rgb=args.no_rgb,
                      tooling_ipc=args.tooling_ipc, free_speed_m_s=args.free_speed, grasp_max_strain=args.grasp_max_strain,
                      rope_young_modulus=args.rope_young_modulus, feedback_joint_limit=args.feedback_joint_limit,
                      ipc_tolerance_scale=args.ipc_tolerance_scale, material_feedback=args.material_feedback,
                      settle_seconds=args.settle_seconds, grasp_strength=args.grasp_strength,
                      max_feedback_m=args.max_feedback, feedback_position_tolerance_m=args.feedback_position_tolerance,
                      feedback_orientation_tolerance_rad=args.feedback_orientation_tolerance, measured_keeper=args.measured_keeper,
                      grasp_follow_error_m=args.grasp_follow_error, grasp_max_penetration_m=args.grasp_max_penetration, allow_covered_grasp=args.allow_covered_grasp, normalize_keeper=args.normalize_keeper, measured_regrasps=args.measured_regrasps)
    output.mkdir(parents=True, exist_ok=False)
    from scripts.test_policy_cube_transfer import snapshot
    source = snapshot(output)
    (output/"source_manifest.json").rename(output/"run_source_manifest.json")
    frozen = output/"relay_samples.npz"
    frozen.write_bytes(samples.read_bytes())
    command = [sys.executable, str(source/"scripts/oracle_runners/run_rope_threading_relay.py"), "--worker", "--output", str(output),
               "--samples", str(frozen), "--variant", args.variant, "--seed", str(args.seed),
               "--episode-seconds", str(args.episode_seconds), "--speed", str(args.speed),
               "--settle-seconds", str(args.settle_seconds),
               "--physics-dt", str(args.physics_dt), "--control-decimation", str(args.control_decimation),
               "--solver-substeps", str(args.solver_substeps), "--grasp-max-strain", str(args.grasp_max_strain),
               "--grasp-strength", str(args.grasp_strength),
               "--grasp-follow-error", str(args.grasp_follow_error), "--grasp-max-penetration", str(args.grasp_max_penetration),
               "--feedback-joint-limit", str(args.feedback_joint_limit), "--ipc-tolerance-scale", str(args.ipc_tolerance_scale)]
    command += ["--max-feedback", str(args.max_feedback), "--feedback-position-tolerance", str(args.feedback_position_tolerance),
                "--feedback-orientation-tolerance", str(args.feedback_orientation_tolerance)]
    if args.free_speed is not None:
        command += ["--free-speed", str(args.free_speed)]
    if args.rope_young_modulus is not None:
        command += ["--rope-young-modulus", str(args.rope_young_modulus)]
    if args.no_rgb:
        command += ["--no-rgb"]
    if args.allow_prefix:
        command += ["--allow-prefix"]
    if args.allow_covered_grasp:
        command += ["--allow-covered-grasp"]
    if args.measured_regrasps:
        command += ["--measured-regrasps"]
    if args.normalize_keeper:
        command += ["--normalize-keeper"]
    if args.measured_keeper:
        command += ["--measured-keeper"]
    if args.material_feedback:
        command += ["--material-feedback"]
    if args.tooling_ipc:
        command += ["--tooling-ipc"]
    (output/"invocation.json").write_text(json.dumps(dict(command=command), indent=2)+"\n")
    from topogym.utils.process_limits import run_guarded
    result = run_guarded(command, output, cwd=source,
        env=dict(os.environ, PYTHONPATH=str(source), OMP_NUM_THREADS="1", MKL_NUM_THREADS="1", OPENBLAS_NUM_THREADS="1",
                 PYOPENGL_PLATFORM="egl", TOPOGYM_VISUAL_ASSET_ROOT=str(ROOT/".external/nyx-assets")))
    print(f"exit={result}; {output}")
    return result



if __name__ == "__main__":
    raise SystemExit(main())
