#!/usr/bin/env python3
"""Run frozen Cast Keyhole policies through the standard, headless SegmentRunner."""
import argparse
import json
import os
from pathlib import Path
import subprocess
import sys
import time
import traceback

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))


def worker(args, output):
    if args.variation in {"very_easy", "easier"}:
        return simplified_worker(args, output)
    import numpy as np
    import torch
    from topogym.simulator import Env, SimulatorConfig, SegmentRunner
    from topogym.assets.geometry.cast_keyhole import generate_variant_assets
    from topogym.planning.cast_keyhole.policy import (CastKeyholePolicy, ASSEMBLY_ROTATIONS,
        GRASP_POINTS, REGRASP_POINTS, PARTS, FAMILIES, canonical_offsets)
    from topogym.utils.grasp import GraspAssistConfig, GraspTarget
    from topogym.utils.io import write_json_atomic, to_jsonable
    from topogym.simulator.rollout_simulation.segment_contract import fingerprint
    torch.set_num_threads(1)
    family = FAMILIES[args.variation]
    assembly, geometry = generate_variant_assets(output/"planning_assets",
        f"variations/cast_keyhole/{family}/geometry.json")
    origins = {b["name"]: np.asarray(b["origin_m"]) for b in geometry["bodies"]}
    offsets = canonical_offsets(origins)
    vertices = {}
    for s, name in PARTS.items():
        body = next(b for b in assembly.bodies if b.name == name)
        vertices[s] = ASSEMBLY_ROTATIONS[s].inv().apply(body.visual.vertices-origins[name])+offsets[s]
    # One region per rigid link includes the two explicitly planned contact
    # patches. Acquisition still requires actual opposing-finger contacts.
    targets = tuple(GraspTarget(name, name,
                    tuple(ASSEMBLY_ROTATIONS[s].apply((GRASP_POINTS[s]+REGRASP_POINTS[s])/2-offsets[s])),
                    .05 if s == "left" else .04)
                    for s, name in PARTS.items())
    config = SimulatorConfig(task_id="cast_keyhole", variation_id="cast_keyhole_"+args.variation,
        robot_id="aloha", control_mode="EE_ABS", enable_privileged=True, enable_rgb=args.rgb,
        compute_backend=args.backend, physics_dt_s=args.tick, solver_substeps=round(args.tick/.000625),
        control_decimation=round(.025/args.tick), max_physics_steps=round(args.horizon/args.tick), work_dir=output/"scene",
        grasp_assist=GraspAssistConfig(model="contact_weld_v1", targets=targets))
    report = dict(status="running", started=time.time(), config=to_jsonable(config),
        variation=args.variation, seed=args.seed, part=args.part, from_default_home=True,
        timing_scope=("simulator default timing" if args.tick == .0025 else
            "explicit grouped tick; preserves 0.625 ms integration and 40 Hz actions, changes per-tick contact/assist/terminal sampling"),
        assistance="automatic contact_weld_v1; bilateral contact required; not friction-only",
        recording="Nyx RGB" if args.rgb else "no RGB or video; full standard numerical tick/action evidence",
        events=[], segments=[])
    write_json_atomic(output/"run_report.json", report)
    try:
        if args.backend == "cuda" and not torch.cuda.is_available():
            raise RuntimeError("Requested CUDA unavailable")
        with Env(config) as env:
            env.reset(seed=args.seed)
            report.update(instance_id=env._task.instance_id,
                asset_sha256=to_jsonable(env._asset_build.sha256), terminal=env._task.terminal_metadata(),
                initial_robot=to_jsonable(env._robot.observe()), initial_world=to_jsonable(env._world.read_state()))
            from topogym.solvers.genesis_kinematics import GenesisFKSolver
            from topogym.utils.arrays import to_numpy
            from topogym.planning.cast_keyhole.policy import rotation
            park_q = to_numpy(env._robot.entity.get_qpos()).reshape(-1).copy()
            # Stay on the positive wrist-angle branch used during pickup.
            # The home TCP admits a +/-pi alternative after crossing zero.
            park_q[env._robot._q_indices["left"][4]] = .3
            park_fk = GenesisFKSolver(env._robot.entity).solve(park_q)
            group = env._robot.groups["left"]
            link = env._robot.entity.get_link(group.hand_link).idx_local
            pr = rotation(np.asarray(park_fk["orientation_wxyz"]).reshape(-1, 4)[link])
            pp = np.asarray(park_fk["position_world_m"]).reshape(-1, 3)[link]
            park_target = dict(tcp_position_world_m=(pp+pr.apply(group.tcp_position_in_hand_m)).tolist(),
                tcp_orientation_wxyz=(pr*rotation(group.tcp_orientation_in_hand_wxyz)).as_quat()[[3, 0, 1, 2]].tolist())
            report["parking_candidate"] = dict(tcp=park_target,
                joint_position_rad=park_q[env._robot._q_indices["left"][:6]].tolist(), physics_steps=0)
            # Reference world is the robot mounting frame, with the original
            # ALOHA axes. Read its declared base location, not an assumed origin.
            from topogym.config.scene import load_scene_config
            mount = np.asarray(load_scene_config(config).env.robot_mount.pos)
            policy = CastKeyholePolicy(variation=args.variation, body_origins=origins,
                goal_region=report["terminal"]["goal_region"], mount_position=mount,
                canonical_vertices=vertices, part="pickup", speed=args.speed)
            costs = report["timing_costs"] = {}
            def timed(obj, name):
                original = getattr(obj, name)
                key = type(obj).__name__+"."+name
                costs[key] = dict(calls=0, seconds=0.)
                def call(*a, **kw):
                    start = time.perf_counter()
                    try:
                        return original(*a, **kw)
                    finally:
                        costs[key]["calls"] += 1
                        costs[key]["seconds"] += time.perf_counter()-start
                setattr(obj, name, call)
            for name in ("advance", "read_state", "capture_state"):
                timed(env._world, name)
            timed(env._sensors, "sample")
            write_json_atomic(output/"run_report.json", report)
            with SegmentRunner(env, output, prepared_output=True) as runner:
                last_phase = [None]
                record_regrasp = [False]
                regrasp_history = []
                with (output/"private/keyhole_monitor.jsonl").open("x", buffering=1) as stream:
                    def tick(row):
                        world = row["world"]
                        if record_regrasp[0]:
                            regrasp_history.append(to_jsonable(dict(time_s=row["state"]["sim_time_s"],
                                bodies={n: world["bodies"][n] for n in PARTS.values()})))
                        report["events"].extend(to_jsonable(world["grasp"]["events"]))
                        if row["state"]["physics_step"] % config.control_decimation or policy.phase == "created":
                            return
                        record = dict(state=row["state"], phase=policy.phase, diagnostics=policy.diagnostics,
                            bodies={n:world["bodies"][n] for n in PARTS.values()}, grasp=world["grasp"],
                            task_result=env._task.result, assist_active=world["assist_active"])
                        stream.write(json.dumps(to_jsonable(record), allow_nan=False)+"\n")
                        write_json_atomic(output/"progress.json", record)
                        if row["state"]["physics_step"] % 200 == 0 or policy.phase != last_phase[0]:
                            write_json_atomic(output/"timing.json", costs)
                        if policy.phase != last_phase[0]:
                            print(policy.phase, row["state"]["sim_time_s"], flush=True)
                            last_phase[0] = policy.phase
                    env.add_state_sink(tick)
                    result = runner.run_policy(request_id="keyhole-"+args.variation, policy=policy,
                        submission_hash=fingerprint(json.loads((output/"run_source_manifest.json").read_text())),
                        mode="unlimited", state_fields=("world",))
                    report["segments"].append(to_jsonable(result))
                    report.update(last_phase=policy.phase, task_result=to_jsonable(env._task.result),
                        final_world=to_jsonable(env._world.read_state()),
                        final_robot=to_jsonable(env._robot.observe()), physics_steps=env._world.physics_step)
                    write_json_atomic(output/"run_report.json", report)
                    if args.part == "all" and result["reason"] == "policy_done":
                        from topogym.planning.cast_keyhole.kinematics import (CoupledKeyholeIK, plan_regrasp,
                            audit_coupled_plan, plan_goal_transfer)
                        def execute_regrasp_part(part, selected=None, approach=None, transit=None):
                            nonlocal policy
                            policy = CastKeyholePolicy(variation=args.variation, body_origins=origins,
                                goal_region=report["terminal"]["goal_region"], mount_position=mount,
                                canonical_vertices=vertices, part=part, speed=args.speed,
                                regrasp_rotation=selected, regrasp_approach=approach, regrasp_transit=transit,
                                park_target=park_target)
                            value = runner.run_policy(request_id="keyhole-"+args.variation+"-"+part,
                                policy=policy, submission_hash=fingerprint(dict(part=part, rotation=selected, approach=approach, transit=transit,
                                    source=json.loads((output/"run_source_manifest.json").read_text()))),
                                mode="unlimited", state_fields=("world",))
                            report["segments"].append(to_jsonable(value))
                            report.update(last_phase=policy.phase, task_result=to_jsonable(env._task.result),
                                final_world=to_jsonable(env._world.read_state()),
                                final_robot=to_jsonable(env._robot.observe()), physics_steps=env._world.physics_step)
                            write_json_atomic(output/"run_report.json", report)
                            if value["reason"] != "policy_done":
                                raise RuntimeError(f"{part}: {value['reason']}")
                        regrasp_history.append(to_jsonable(dict(time_s=env._world.sim_time_s,
                            bodies={n: env._world.read_state()["bodies"][n] for n in PARTS.values()})))
                        record_regrasp[0] = True
                        for side in ("right", "left"):
                            execute_regrasp_part("release_"+side)
                            inline = side == "left" and args.variation != "medium"
                            if inline:
                                # Keep the free wrist outside the volume swept
                                # by the hanging assembly during this lift.
                                execute_regrasp_part("park_left")
                                execute_regrasp_part("raise_supported")
                            policy.phase = "planning_regrasp_"+side
                            print(policy.phase, flush=True)
                            candidate = plan_regrasp(env._robot, env._world.entities, origins,
                                env._world.read_state()["bodies"], side, env._task.table_height_m,
                                joint_transit=inline)
                            write_json_atomic(output/("regrasp_"+side+"_plan.json"), candidate)
                            if candidate["selected"] is None:
                                raise RuntimeError("No checked regrasp approach for "+side)
                            execute_regrasp_part("grasp_"+side, candidate["selected"]["rotation_xyzw"],
                                                 candidate["selected"]["approach_offsets"], candidate["selected"].get("transit_tcp"))
                        record_regrasp[0] = False
                        write_json_atomic(output/"observed_regrasp_path.json", regrasp_history)
                        policy.phase = "planning_coupled_ik"
                        planner = CoupledKeyholeIK(env._robot, origins, env._world.read_state()["bodies"])
                        def planned(row):
                            write_json_atomic(output/"planning_progress.json", row)
                            if row["frames"] % 20 == 0:
                                print("coupled_ik", row, flush=True)
                        plan = planner.plan(policy, center=mount+[0., .04, .24], stride=1, progress=planned,
                                            entry_history=regrasp_history)
                        write_json_atomic(output/"coupled_ik_plan.json", plan)
                        audit = audit_coupled_plan(env._robot, env._world.entities, origins, plan, env._task.table_height_m)
                        write_json_atomic(output/"coupled_plan_collision_audit.json", audit)
                        if not audit["passed"]:
                            raise RuntimeError("Coupled IK candidate failed the full robot mesh audit")
                        goal_plan = plan_goal_transfer(env._robot, env._world.entities, origins, plan,
                            planner.grasp_offsets, policy, env._task.table_height_m)
                        write_json_atomic(output/"goal_transfer_plan.json", goal_plan)
                        if not goal_plan["passed"]:
                            raise RuntimeError("Goal transfer failed native IK or full mesh preflight")
                        policy = CastKeyholePolicy(variation=args.variation, body_origins=origins,
                            goal_region=report["terminal"]["goal_region"], mount_position=mount,
                            canonical_vertices=vertices, part="solve", speed=args.speed, plan=plan)
                        result = runner.run_policy(request_id="keyhole-"+args.variation+"-solve", policy=policy,
                            submission_hash=fingerprint(plan), mode="unlimited", state_fields=("world",))
                        report["segments"].append(to_jsonable(result))
                    report.update(last_phase=policy.phase,
                        task_result=to_jsonable(env._task.result), final_world=to_jsonable(env._world.read_state()),
                        final_robot=to_jsonable(env._robot.observe()),
                        statistics=runner._evidence.statistics(), physics_steps=env._world.physics_step,
                        diagnostics=to_jsonable(policy.diagnostics))
                    if args.part == "pickup":
                        passed = result["reason"] == "policy_done" and all(
                            h["phase"] == "holding" for h in report["final_world"]["grasp"]["hands"].values())
                        report["status"] = "pickup_passed" if passed else "failed"
                    else:
                        passed = bool(env._task.result.task_success)
                        report["status"] = "passed" if passed else "failed"
                    if not passed:
                        raise RuntimeError(f"Run did not pass: {result['reason']} in {policy.phase}")
    except BaseException:
        report.update(status="failed", error=traceback.format_exc())
        raise
    finally:
        report["wall_time_s"] = time.time()-report["started"]
        write_json_atomic(output/"run_report.json", report)


def simplified_worker(args, output):
    """New reference candidate through the same Env and SegmentRunner contract."""
    import numpy as np
    import torch
    from topogym.config.registry import task_definition
    from topogym.assets.variation_resources import read_json
    from topogym.tasks.cast_keyhole.common import recommended_grasp_assist
    from topogym.planning.cast_keyhole.simplified_policy import SimplifiedKeyholePolicy
    from topogym.planning.cast_keyhole.policy import PARTS
    from topogym.assets.geometry.cast_keyhole import plate_assembly_transforms
    from scipy.spatial.transform import Rotation
    from topogym.simulator import Env, SimulatorConfig, SegmentRunner
    from topogym.simulator.rollout_simulation.segment_contract import fingerprint
    from topogym.utils.io import to_jsonable, write_json_atomic
    torch.set_num_threads(1)
    task = task_definition("cast_keyhole", args.variation)(seed=args.seed)
    record = read_json(task.geometry_resource)
    assembly, geometry = task.build_assets(output/"planning_assets")
    origins = {b["name"]: np.asarray(b["origin_m"]) for b in geometry["bodies"]}
    transforms = plate_assembly_transforms(record)
    vertices = {s: Rotation.from_matrix(transforms[metal][:3, :3]).inv().apply(
        next(b for b in assembly.bodies if b.name == PARTS[s]).visual.vertices-transforms[metal][:3, 3])
        for s, metal in (("left", "gold"), ("right", "silver"))}
    config = SimulatorConfig(task_id="cast_keyhole", variation_id=task.variation_id,
        robot_id="aloha", control_mode="EE_ABS", enable_privileged=True, enable_rgb=args.rgb,
        compute_backend=args.backend, physics_dt_s=args.tick, solver_substeps=round(args.tick/.000625),
        control_decimation=round(.025/args.tick), max_physics_steps=round(args.horizon/args.tick),
        work_dir=output/"scene", grasp_assist=recommended_grasp_assist(args.variation, args.seed))
    report = dict(status="running", config=to_jsonable(config), reference_status="candidate",
                  variation=task.variation_id, part=args.part, started=time.time())
    write_json_atomic(output/"run_report.json", report)
    try:
        with Env(config) as env:
            env.reset(seed=args.seed)
            report.update(instance_id=env._task.instance_id, asset_sha256=env._asset_build.sha256,
                          terminal=env._task.terminal_metadata())
            policy = SimplifiedKeyholePolicy(geometry=record, variation=task.variation_id,
                body_origins=origins, goal_region=report["terminal"]["goal_region"],
                mount_position=[0., 0., 0.], canonical_vertices=vertices,
                part=args.part, speed=args.speed)
            with SegmentRunner(env, output, prepared_output=True) as runner:
                result = runner.run_policy(request_id="keyhole-"+args.variation,
                    policy=policy, mode="unlimited", state_fields=("world",),
                    submission_hash=fingerprint(dict(geometry=record, config=to_jsonable(config))))
            success = bool(env.is_solved())
            pickup = args.part == "pickup" and result["reason"] == "policy_done"
            report.update(status="passed" if success else "pickup_passed" if pickup else "failed",
                          task_success=success, segment=to_jsonable(result), last_phase=policy.phase,
                          task_result=to_jsonable(env._task.result))
            if not (success or pickup):
                raise RuntimeError("Reference candidate did not complete the requested task")
    except BaseException:
        report.update(status="failed", error=traceback.format_exc())
        raise
    finally:
        report["wall_time_s"] = time.time()-report["started"]
        write_json_atomic(output/"run_report.json", report)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", required=True)
    parser.add_argument("--variation", choices=["very_easy", "easier", "easy", "medium", "hard"], required=True)
    parser.add_argument("--part", choices=["pickup", "all"], default="all")
    parser.add_argument("--backend", choices=["cuda", "cpu"], default="cuda")
    parser.add_argument("--rgb", action="store_true", help="Optional Nyx video; disabled by default")
    parser.add_argument("--seed", type=int, default=0)
    parser.add_argument("--horizon", type=float, default=900.)
    parser.add_argument("--speed", type=float, default=1.)
    parser.add_argument("--tick", type=float, choices=[.0025, .025], default=.0025,
                        help=".025 groups ten integration blocks per saved tick; explicit faster qualification timing")
    parser.add_argument("--worker", action="store_true")
    args = parser.parse_args()
    if args.speed <= 0 or args.horizon <= 0:
        parser.error("speed and horizon must be positive")
    output = Path(args.output).resolve()
    if args.worker:
        return worker(args, output)
    output.mkdir(parents=True, exist_ok=False)
    from scripts.test_policy_cube_transfer import snapshot
    source = snapshot(output)
    (output/"source_manifest.json").rename(output/"run_source_manifest.json")
    command = [sys.executable, str(source/"scripts/oracle_runners/run_cast_keyhole_policy.py"), "--worker",
        "--output", str(output), "--variation", args.variation, "--part", args.part,
        "--backend", args.backend, "--seed", str(args.seed), "--horizon", str(args.horizon), "--speed", str(args.speed),
        "--tick", str(args.tick)]
    if args.rgb:
        command.append("--rgb")
    (output/"invocation.json").write_text(json.dumps(dict(command=command), indent=2)+"\n")
    with (output/"runtime.log").open("x") as log:
        result = subprocess.run(command, cwd=source, stdout=log, stderr=subprocess.STDOUT,
            env=dict(os.environ, PYTHONPATH=str(source), OMP_NUM_THREADS="1", MKL_NUM_THREADS="1",
                OPENBLAS_NUM_THREADS="1", TOPOGYM_VISUAL_ASSET_ROOT=str(ROOT/".external/nyx-assets")))
    print(f"exit={result.returncode}; {output}")
    raise SystemExit(result.returncode)


if __name__ == "__main__":
    main()
