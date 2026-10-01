#!/usr/bin/env python3
"""Freeze and run a Buzz Wire policy without RGB/video; retain all tick evidence."""
import argparse
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


def worker(args):
    import torch
    from topogym.simulator import Env, SimulatorConfig, SegmentRunner
    from topogym.config.registry import task_definition
    from topogym.planning.buzz_wire_3d import BuzzWirePolicy
    from topogym.utils.grasp import GraspAssistConfig, GraspTarget
    from topogym.utils.io import write_json_atomic, to_jsonable
    from topogym.simulator.rollout_simulation.segment_contract import fingerprint
    torch.set_num_threads(1)
    output = args.output
    compiled = json.loads(args.compiled_actions.read_text()) if args.compiled_actions else None
    source_differences = []
    layout = task_definition("buzz_wire_3d", args.variant)().build_layout()
    grip_point = (layout.loop_radius_m+layout.stem_length_m+layout.grip_length_m*.55, 0., 0.)
    config = SimulatorConfig(task_id="buzz_wire_3d", variation_id=args.variant, robot_id="panda_robotiq",
        control_mode=args.control_mode, enable_privileged=True, enable_rgb=False, compute_backend=args.compute_backend,
        physics_dt_s=args.physics_dt, control_decimation=args.control_decimation, solver_substeps=args.solver_substeps,
        max_physics_steps=round(args.episode_seconds/args.physics_dt), work_dir=output/"scene",
        grasp_assist=GraspAssistConfig(model="contact_weld_v1",
            targets=(GraspTarget("wand", "wand", grip_point, .025),)))
    if compiled is not None:
        if compiled["seed"] != args.seed or compiled["config"]["variation_id"] != args.variant:
            raise ValueError("Compiled policy seed/variant differs from requested run")
        for name, expected in compiled["provenance"]["original_manifest"].items():
            if name.startswith("topogym/") and not name.startswith("topogym/planning/"):
                actual = hashlib.sha256((ROOT/name).read_bytes()).hexdigest()
                if actual != expected:
                    source_differences.append(dict(path=name,development_sha256=expected,execution_sha256=actual))
        values = dict(compiled["config"])
        values.update(work_dir=str(output/"scene"), max_physics_steps=len(compiled["actions"])+400)
        if args.feedback_finish:
            values["max_physics_steps"] = max(values["max_physics_steps"],round(args.episode_seconds/values["physics_dt_s"]))
        config = SimulatorConfig(**values)
    report = dict(status="running", started=time.time(), config=to_jsonable(config), variant=args.variant,
        seed=args.seed, task_success=False, from_default_home=True, mode="unlimited", part=args.part,
        policy_parameters=dict(grasp_height_m=args.grasp_height, grasp_tilt_deg=args.grasp_tilt),
        qualification="single frozen instance; contact_weld_v1 assist; no RGB/video; explicit timing; no half-dt qualification")
    if compiled is not None:
        report["policy_kind"] = "compiled_joint_actions_from_checked_ik_development"
        report["compiled_actions_sha256"] = hashlib.sha256(args.compiled_actions.read_bytes()).hexdigest()
        report["development_source_differences"] = source_differences
        if args.feedback_finish:
            report.update(policy_kind="compiled_prefix_then_observation_feedback",compiled_prefix_steps=5052)
    write_json_atomic(output/"run_report.json", report)
    try:
        with Env(config) as env:
            env.reset(seed=args.seed)
            def make_policy(**values):
                inner = BuzzWirePolicy(**values)
                if args.control_mode == "JOINT_ABS":
                    from topogym.planning.buzz_wire_3d.kinematics import CheckedJointPolicy
                    return CheckedJointPolicy(inner,env._robot)
                return inner
            report.update(instance_id=env._task.instance_id, initial_robot=to_jsonable(env._robot.observe()),
                initial_task=to_jsonable(env._task.result), asset_sha256=to_jsonable(env._asset_build.sha256))
            policy = make_policy(route=env._task.route, origin=env._task.origin, part="pickup",
                                   grasp_height=args.grasp_height, grasp_tilt=args.grasp_tilt)
            if compiled is not None:
                from topogym.planning.buzz_wire_3d.compiled import CompiledJointPolicy
                policy = CompiledJointPolicy(compiled,action_limit=5052 if args.feedback_finish else None)
            with SegmentRunner(env, output, prepared_output=True) as runner:
                last_phase = [None]
                def tick(row):
                    state, world = row["state"], row["world"]
                    if state["physics_step"] % 40 == 0 or policy.phase != last_phase[0]:
                        record = dict(state=state, phase=policy.phase, task=env._task.result,
                                      wand=world["bodies"]["wand"], robot=row["robot"],
                                      grasp=world["grasp"], tracking=policy.tracking)
                        record["robot_contact_sample"] = [event for event in world["contact_events"]["events"]
                            if "robot" in (event["role_a"], event["role_b"])][:12]
                        write_json_atomic(output/"progress.json", record)
                    if policy.phase != last_phase[0]:
                        print(policy.phase, state["sim_time_s"], flush=True)
                        last_phase[0] = policy.phase
                env.add_state_sink(tick)
                tick(env.tick_record())
                source = json.loads((output/"run_source_manifest.json").read_text())
                result = runner.run_policy(request_id="buzz-"+args.variant, policy=policy,
                    submission_hash=fingerprint(dict(source=source, args=vars(args))),
                    mode="unlimited", state_fields=("world",))
                report["segments"] = [to_jsonable(result)]
                report.update(last_phase=policy.phase, task_result=to_jsonable(env._task.result),
                    physics_steps=env._world.physics_step, simulation_time_s=env._world.sim_time_s)
                write_json_atomic(output/"run_report.json", report)
                if args.feedback_finish and result["reason"] == "policy_done":
                    from topogym.planning.buzz_wire_3d.recipes import easy_finish_stages
                    for stage,parameters in enumerate(easy_finish_stages(env,output),1):
                        policy = make_policy(route=env._task.route,origin=env._task.origin,**parameters)
                        result = runner.run_policy(request_id=f"buzz-finish-stage-{stage}",policy=policy,
                            submission_hash=fingerprint(dict(source=source,parameters=parameters)),
                            mode="unlimited",state_fields=("world",))
                        report["segments"].append(to_jsonable(result))
                        report.update(last_phase=policy.phase,task_result=to_jsonable(env._task.result),
                                      physics_steps=env._world.physics_step,simulation_time_s=env._world.sim_time_s)
                        write_json_atomic(output/"run_report.json",report)
                        if env._task.result.task_success:
                            break
                        if result["reason"] != "policy_done":
                            raise RuntimeError(f"Feedback finish stage {stage} stopped: {result['reason']}")
                if compiled is None and args.part in {"all", "regrasp", "traverse"} and result["reason"] == "policy_done":
                    policy = make_policy(route=env._task.route, origin=env._task.origin,
                        part="regrasp" if args.variant == "easy" else "park")
                    result = runner.run_policy(request_id="buzz-"+args.variant+"-regrasp", policy=policy,
                        submission_hash=fingerprint(dict(source=source, part="regrasp")),
                        mode="unlimited", state_fields=("world",))
                    report["segments"].append(to_jsonable(result))
                    report.update(last_phase=policy.phase, task_result=to_jsonable(env._task.result),
                        physics_steps=env._world.physics_step, simulation_time_s=env._world.sim_time_s)
                    write_json_atomic(output/"run_report.json", report)
                    if result["reason"] == "policy_done" and args.variant != "easy":
                        import numpy as np
                        from scipy.spatial.transform import Rotation
                        from topogym.planning.buzz_wire_3d.kinematics import BuzzIK
                        from topogym.planning.buzz_wire_3d.policy import rotation
                        print("planning_open_hand_transfer", flush=True)
                        kin = BuzzIK(env)
                        body = env._world.read_state()["bodies"]["wand"]
                        p,r = np.asarray(body["position_m"]),rotation(body["quaternion_wxyz"])
                        l = env._task.layout
                        gr = r*Rotation.from_euler("y",255,degrees=True)*Rotation.from_euler("z",180,degrees=True)
                        gp = p+r.apply([l.loop_radius_m+l.stem_length_m+l.grip_length_m*.4,0,0])+[0,0,.012]
                        transfer = kin.plan_free_tcp((gp-gr.apply([0,0,.04]),gr))
                        write_json_atomic(output/"open_hand_transfer.json", transfer)
                        policy = make_policy(route=env._task.route,origin=env._task.origin,part="acquire",plan=transfer)
                        result = runner.run_policy(request_id="buzz-"+args.variant+"-acquire",policy=policy,
                            submission_hash=fingerprint(transfer),mode="unlimited",state_fields=("world",))
                        report["segments"].append(to_jsonable(result))
                        report.update(last_phase=policy.phase, task_result=to_jsonable(env._task.result),
                            physics_steps=env._world.physics_step, simulation_time_s=env._world.sim_time_s)
                        write_json_atomic(output/"run_report.json",report)
                if compiled is None and args.part in {"all", "traverse"} and result["reason"] == "policy_done":
                    import numpy as np
                    from topogym.planning.buzz_wire_3d.kinematics import BuzzIK
                    from topogym.planning.buzz_wire_3d.policy import rotation
                    policy.phase = "planning_route"
                    print(policy.phase, flush=True)
                    kin = BuzzIK(env)
                    body = env._world.read_state()["bodies"]["wand"]
                    p, r = np.asarray(body["position_m"]), rotation(body["quaternion_wxyz"])
                    tcp = env._robot.observe()["arm"]
                    offset_p = r.inv().apply(np.asarray(tcp["tcp_position_world_m"])-p)
                    offset_r = r.inv()*rotation(tcp["tcp_orientation_wxyz"])
                    attempts = report["planning_attempts"] = []
                    for spacing, width in ((.008, 4), (.004, 12), (.002, 24)):
                        attempt = dict(spacing_m=spacing, beam_width=width)
                        attempts.append(attempt)
                        try:
                            plan = kin.plan_route(env._task.route, env._task.origin, offset_p, offset_r,
                                spacing=spacing, beam_width=width,
                                progress=lambda row: write_json_atomic(output/"planning_progress.json", row))
                            write_json_atomic(output/f"coarse_ik_plan_{len(attempts)}.json", plan)
                            plan = kin.refine(plan, offset_p, offset_r)
                            attempt["passed"] = True
                            break
                        except ValueError as error:
                            attempt.update(passed=False, error=str(error))
                            write_json_atomic(output/"run_report.json", report)
                    else:
                        raise RuntimeError(f"Route candidate search exhausted: {attempts}")
                    write_json_atomic(output/"ik_plan.json", plan)
                    policy = make_policy(route=env._task.route, origin=env._task.origin, part="solve", plan=plan)
                    result = runner.run_policy(request_id="buzz-"+args.variant+"-solve", policy=policy,
                        submission_hash=fingerprint(plan), mode="unlimited", state_fields=("world",))
                    report["segments"].append(to_jsonable(result))
                    report.update(last_phase=policy.phase, task_result=to_jsonable(env._task.result),
                        physics_steps=env._world.physics_step, simulation_time_s=env._world.sim_time_s)
                    write_json_atomic(output/"run_report.json",report)
                    if result["reason"] == "policy_done" and args.part == "all":
                        from scipy.spatial.transform import Rotation
                        l = env._task.layout
                        print("planning_finish_regrasp",flush=True)
                        kin = BuzzIK(env)
                        body = env._world.read_state()["bodies"]["wand"]
                        p,r = np.asarray(body["position_m"]),rotation(body["quaternion_wxyz"])
                        grasp_y = 75. if r.apply([0,0,1])[2]<0 else 105.
                        gr = r*Rotation.from_euler("y",grasp_y,degrees=True)*Rotation.from_euler("z",180,degrees=True)
                        gp = p+r.apply([l.loop_radius_m+l.stem_length_m+l.grip_length_m*.4,0,0])+[0,0,.012]
                        transfer = kin.plan_free_tcp((gp-gr.apply([0,0,.04]),gr))
                        write_json_atomic(output/"finish_open_hand_transfer.json",transfer)
                        policy = make_policy(route=env._task.route,origin=env._task.origin,
                            part="acquire",plan=transfer,grasp_y=grasp_y)
                        result = runner.run_policy(request_id="buzz-"+args.variant+"-finish-acquire",policy=policy,
                            submission_hash=fingerprint(transfer),mode="unlimited",state_fields=("world",))
                        report["segments"].append(to_jsonable(result))
                        if result["reason"] == "policy_done":
                            policy = make_policy(route=env._task.route,origin=env._task.origin,part="finish")
                            result = runner.run_policy(request_id="buzz-"+args.variant+"-finish",policy=policy,
                                submission_hash=fingerprint(dict(source=source,part="finish")),
                                mode="unlimited",state_fields=("world",))
                            report["segments"].append(to_jsonable(result))
                report.update(last_phase=policy.phase,
                    task_result=to_jsonable(env._task.result), phase_endpoints=policy.samples,
                    physics_steps=env._world.physics_step, simulation_time_s=env._world.sim_time_s,
                    task_success=bool(env._task.result.task_success), statistics=runner._evidence.statistics())
                if not (report["task_success"] if args.part == "all" else result["reason"] == "policy_done"):
                    raise RuntimeError(f"Run did not pass: {result['reason']} in {policy.phase}")
                report["status"] = "passed"
    except BaseException:
        report.update(status="failed", error=traceback.format_exc())
        raise
    finally:
        report["wall_time_s"] = time.time()-report["started"]
        write_json_atomic(output/"run_report.json", report)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--variant", choices=("easy", "medium", "hard"), default="easy")
    parser.add_argument("--seed", type=int, default=0)
    parser.add_argument("--part", choices=("all", "pickup", "regrasp", "traverse"), default="all")
    parser.add_argument("--compute-backend", choices=("cpu", "cuda"), default="cpu")
    parser.add_argument("--control-mode",choices=("JOINT_ABS","EE_ABS"),default="JOINT_ABS")
    parser.add_argument("--physics-dt", type=float, default=.025)
    parser.add_argument("--control-decimation", type=int, default=1)
    parser.add_argument("--solver-substeps", type=int, default=40)
    parser.add_argument("--episode-seconds", type=float, default=360.)
    parser.add_argument("--grasp-height", type=float, default=.012)
    parser.add_argument("--grasp-tilt", type=float, default=75.)
    parser.add_argument("--compiled-actions", type=Path,
                        help="Execute compiled ordinary actions afresh from home, without state restoration")
    parser.add_argument("--feedback-finish",action="store_true",
                        help="Easy seed-0 recipe: replay the held prefix, then remeasure and finish through observation policies")
    parser.add_argument("--worker", action="store_true", help=argparse.SUPPRESS)
    args = parser.parse_args()
    args.output = args.output.resolve()
    if args.feedback_finish and (not args.compiled_actions or args.variant != "easy" or args.seed != 0):
        parser.error("--feedback-finish currently requires easy seed 0 and --compiled-actions")
    if args.worker:
        return worker(args)
    args.output.mkdir(parents=True, exist_ok=False)
    extra_args = list(sys.argv[1:])
    if args.compiled_actions:
        frozen_actions = args.output/"policy_actions.json"
        frozen_actions.write_bytes(args.compiled_actions.read_bytes())
        index = extra_args.index("--compiled-actions")
        extra_args[index+1] = str(frozen_actions)
    from scripts.test_policy_cube_transfer import snapshot
    source = snapshot(args.output)
    (args.output/"source_manifest.json").rename(args.output/"run_source_manifest.json")
    command = [sys.executable, str(source/"scripts/oracle_runners/run_buzz_wire_policy.py"), *extra_args, "--worker"]
    (args.output/"invocation.json").write_text(json.dumps(dict(command=command), indent=2))
    with (args.output/"runtime.log").open("x") as log:
        process = subprocess.Popen(command, cwd=ROOT, stdout=log, stderr=subprocess.STDOUT,
            env=dict(os.environ, PYTHONPATH=str(source), OMP_NUM_THREADS="1", MKL_NUM_THREADS="1",
                     OPENBLAS_NUM_THREADS="1", TOPOGYM_VISUAL_ASSET_ROOT=str(ROOT/".external/nyx-assets")))
        while process.poll() is None:
            try:
                process.wait(timeout=30)
            except subprocess.TimeoutExpired:
                progress_path = args.output/"progress.json"
                progress = json.loads(progress_path.read_text()) if progress_path.exists() else {}
                print(args.variant,progress.get("phase","building"),
                      progress.get("state",{}).get("sim_time_s"),flush=True)
    print(f"exit={process.returncode}; {args.output}")
    raise SystemExit(process.returncode)


if __name__ == "__main__":
    main()
