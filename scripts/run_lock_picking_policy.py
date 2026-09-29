#!/usr/bin/env python3
"""Record a lock oracle through standard passive policy dispatch and Env.step.

The current medium restores the historical two-retreat mechanism. All physics
parameters and measured engine properties are recorded, including failed runs.
"""
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

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


def parameters(setting):
    if setting == "current":
        return {}
    from topogym.tasks.lock_picking.lock_picking_medium import LockPickingMediumTask
    return LockPickingMediumTask.variant_parameters


def pickup_preflight(env, geometry, style, roll):
    """Owner read-only IK queries, with scratch/RNG restored by shared solvers."""
    import numpy as np
    from scipy.spatial.transform import Rotation, Slerp
    from topogym.solvers.genesis_kinematics import GenesisIKSolver
    from topogym.utils.arrays import to_numpy
    from topogym.planning.lock_picking.lock_picking_medium_planning import pickup_waypoints, rotation
    robot = env._robot
    arm = robot.observe()["arm"]
    p, r = np.asarray(arm["tcp_position_world_m"]), rotation(arm["tcp_orientation_wxyz"])
    body = env._world.read_state()["bodies"]["lock_key"]
    kr = rotation(body["quaternion_wxyz"])
    center = np.asarray(body["position_m"])+kr.apply([-geometry["grip_offset"], 0, 0])
    grasp_rotation = (Rotation.from_euler("xyz", [180., 0., roll], degrees=True) if style == "top" else
                      kr*Rotation.from_euler("x", roll, degrees=True)*Rotation.from_euler("y", 90., degrees=True))
    group = robot.groups["arm"]
    solver = GenesisIKSolver(robot.entity)
    seed = to_numpy(robot.entity.get_qpos()).reshape(-1).copy()
    records = []
    for target, orientation, duration, phase in pickup_waypoints(p, r, center, grasp_rotation, style):
        rotations = Slerp([0., 1.], Rotation.from_quat([r.as_quat(), orientation.as_quat()]))
        dt = env.config.physics_dt_s*env.config.control_decimation
        for t in np.linspace(dt/duration, 1., max(2, round(duration/dt))):
            u = t*t*(3-2*t)
            tp, tr = p+u*(target-p), rotations(u)
            try:
                seed = solver.solve_checked(link_name=group.hand_link,
                    position_world_m=tp-tr.apply(group.tcp_position_in_hand_m),
                    orientation_wxyz=tr.as_quat()[[3,0,1,2]],
                    joint_dof_indices=robot._indices["arm"][:len(group.arm_joints)], initial_qpos=seed)
            except ValueError as error:
                return dict(passed=False, phase=phase, progress=float(t), error=str(error), samples=records,
                            qualification="kinematics only; no physics, collision or grasp qualification")
            records.append(dict(phase=phase, progress=float(t), joint_position_rad=seed[robot._q_indices["arm"][:7]].tolist()))
        p, r = target, orientation
    return dict(passed=True, samples=records, qualification="kinematics only; no physics, collision or grasp qualification")


def worker(output, *, setting, part, grasp_roll_deg, grasp_style, physics_dt, solver_substeps, control_decimation, no_rgb, compute_backend):
    import numpy as np
    import torch
    from topogym.simulator import Env, SimulatorConfig, SegmentRunner
    from topogym.planning.lock_picking.lock_picking_medium_planning import LockPickingMediumPolicy
    from topogym.utils.grasp import GraspAssistConfig, GraspTarget
    from topogym.utils.io import write_json_atomic, to_jsonable
    from topogym.utils.arrays import to_numpy
    from topogym.simulator.rollout_simulation.segment_contract import fingerprint
    torch.set_num_threads(1)
    output = Path(output)
    config = SimulatorConfig(task_id="lock_picking", variation_id="lock_picking_medium",
        precision="32", compute_backend=compute_backend,
        robot_id="panda_robotiq", control_mode="EE_ABS", observation_mode="JOINT",
        enable_privileged=True, task_parameters=parameters(setting),
        physics_dt_s=physics_dt, solver_substeps=solver_substeps, control_decimation=control_decimation,
        max_physics_steps=round(240/physics_dt), enable_rgb=not no_rgb,
        work_dir=output/"scene", grasp_assist=GraspAssistConfig("contact_weld_v1",
            (GraspTarget("lock_key", "key", center_m=(-.495, 0., 0.), radius_m=.032),),
            stable_time_s=max(.05, 2*physics_dt)))
    report = dict(status="running", setting=setting, requested_part=part, config=to_jsonable(config),
        policy_parameters=dict(grasp_style=grasp_style, grasp_roll_deg=grasp_roll_deg),
        timing_scope="explicit recorded World tick/substep configuration; simulator defaults unchanged",
        started=time.time(), events=[], segments=[],
        qualification="pending measured execution; Task success qualification remains unchanged",
        from_default_home=True, policy_access="unlimited world state; ordinary EE_ABS actions only",
        provenance=dict(commit="cb60f01b32786cc9c26f754f91b7be4bef3f9ca6",
            semantic_route="2026-09-18_standard_150mm_purple_trace_v1 commands.jsonl",
            changes="Recovered mechanism physics and two-retreat slots; current Panda/Robotiq and lab placement; automatic grasp and regrasp through measured-pose EE actions"))
    write_json_atomic(output/"run_report.json", report)
    active = [None]
    monitor = None
    try:
        if compute_backend == "cuda" and not torch.cuda.is_available():
            raise RuntimeError("CUDA/Nyx unavailable")
        with Env(config) as env:
            env.reset(seed=0)
            geometry = asdict(env._task.layout)
            report.update(geometry=geometry, task_instance_id=env._task.instance_id,
                initial_robot=to_jsonable(env._robot.observe()),
                initial_task=to_jsonable(env._task.result), asset_sha256=to_jsonable(env._asset_build.sha256))
            properties = {}
            for name in ("lock_disc_0", "lock_disc_1", "lock_disc_2", "lock_key"):
                entity = env._world.entities[name]
                properties[name] = dict(mass_kg=float(entity.get_mass()),
                    armature=to_numpy(entity.get_dofs_armature()).tolist(),
                    damping=to_numpy(entity.get_dofs_damping()).tolist())
            report["measured_engine_properties"] = properties
            report["task_physics"] = env._task.config["physics"]
            for name in ("lock_disc_0", "lock_disc_1", "lock_disc_2"):
                measured = properties[name]
                if not (np.allclose(measured["armature"], 0.) and np.allclose(measured["damping"], .03)
                        and np.isclose(measured["mass_kg"], .12)):
                    raise RuntimeError(f"Historical passive physics restoration mismatch: {name}: {measured}")
            if not np.isclose(properties["lock_key"]["mass_kg"], .12):
                raise RuntimeError("Historical key mass restoration mismatch")
            names = {int(link.idx): f"{name}/{link.name}" for name, entity in env._world.entities.items()
                     for link in getattr(entity, "links", ())}
            report["contact_link_names"] = {str(k): v for k, v in names.items()}
            write_json_atomic(output/"run_report.json", report)
            preflight = pickup_preflight(env, geometry, grasp_style, grasp_roll_deg)
            write_json_atomic(output/"kinematic_preflight.json", preflight)
            if not preflight["passed"]:
                raise RuntimeError(f"Read-only pickup preflight failed: {preflight['phase']}: {preflight['error']}")
            with SegmentRunner(env, output, prepared_output=True) as runner:
                monitor = (output/"private/lock_monitor.jsonl").open("x", buffering=1)
                def monitor_tick(row):
                    world = row["world"]
                    grasp = world["grasp"]
                    contacts = world["contacts"]
                    count = len(contacts.get("link_a", []))
                    interesting = []
                    for i in range(count):
                        a, b = int(contacts["link_a"][i]), int(contacts["link_b"][i])
                        if not any(names.get(k, "").startswith(("lock_key/", "robot/")) for k in (a, b)):
                            continue
                        interesting.append(dict(a=names.get(a, str(a)), b=names.get(b, str(b)),
                            penetration_m=float(contacts["penetration"][i]),
                            force_n=float(np.linalg.norm(contacts["force"][i]))))
                    events = to_jsonable(grasp["events"])
                    report["events"].extend(events)
                    progress = dict(state=row["state"], phase=getattr(active[0], "phase", "initial"),
                        key=world["bodies"]["lock_key"], grasp=grasp,
                        task_result=env._task.result, contacts=interesting)
                    monitor.write(json.dumps(to_jsonable(progress), allow_nan=False)+"\n")
                    write_json_atomic(output/"progress.json", progress)
                env.add_state_sink(monitor_tick)
                monitor_tick(env.tick_record())
                source = json.loads((output/"run_source_manifest.json").read_text())
                for name in (("pickup", "solve") if part == "solve" else ("pickup",)):
                    kwargs = dict(geometry=geometry, part=name, grasp_roll_deg=grasp_roll_deg, grasp_style=grasp_style)
                    policy = active[0] = LockPickingMediumPolicy(**kwargs)
                    result = runner.run_policy(request_id=f"lock-{name}", policy=policy,
                        submission_hash=fingerprint(dict(source=source, parameters=kwargs)),
                        mode="unlimited", state_fields=("world", "task"))
                    report["segments"].append(to_jsonable(result))
                    report.update(last_phase=policy.phase, physics_steps=env._world.physics_step,
                                  policy_completed=policy.completed, task_result=to_jsonable(env._task.result))
                    write_json_atomic(output/"run_report.json", report)
                    if result["reason"] != "policy_done":
                        raise RuntimeError(f"Policy stopped in {policy.phase}: {result['reason']}; see private/policies")
                report.update(status="pickup_passed" if part == "pickup" else "route_completed",
                    final_world=to_jsonable(env._world.read_state()))
                if part == "solve":
                    reached, failure, metrics = env._task.evaluate_state(env._world.read_state())
                    report["independent_goal_check"] = dict(reached=reached, failure=failure, metrics=metrics,
                        formal_success=env._task.result.task_success, goal_complete=env._task.goal_complete)
                    # A released shaft normally rests against a bore. Preserve
                    # the Task's strict positive-clearance result independently
                    # of observing insertion, release and a stable resting key.
                    key = env._world.read_state()["bodies"]["lock_key"]
                    from scipy.spatial.transform import Rotation
                    q = np.asarray(key["quaternion_wxyz"])
                    axis = Rotation.from_quat(q[[1, 2, 3, 0]]).apply([1., 0., 0.])
                    tip = np.asarray(key["position_m"])
                    radial_offsets = []
                    if axis[0] > .99:
                        for plate in range(4):
                            for side in (-1., 1.):
                                x = geometry["first_x"]+plate*geometry["pitch"]+side*geometry["disc_thickness"]/2
                                at = tip+axis*((x-tip[0])/axis[0])
                                radial_offsets.append(float(np.linalg.norm(at[1:]-[geometry["center_y"], geometry["axis_z"]])))
                    # Allow only 0.2 mm of measured contact compliance, not a
                    # lateral bypass. The Task's positive-clearance test stays intact.
                    radial_ok = bool(radial_offsets and max(radial_offsets)+geometry["shaft_radius"]/axis[0]
                                     <= geometry["bore_radius"]+.0002)
                    resting_insertion = (bool(metrics.get("leading_tab_inserted")) and
                        bool(metrics.get("shaft_in_goal")) and radial_ok and failure is None and
                        np.linalg.norm(key["linear_velocity_m_s"]) < .01 and
                        np.linalg.norm(key["angular_velocity_rad_s"]) < .1 and
                        not env._world.read_state()["assist_active"])
                    report["independent_goal_check"]["resting_insertion_observed"] = bool(resting_insertion)
                    report["independent_goal_check"].update(radial_offsets_m=radial_offsets,
                        shaft_within_bores_with_contact_tolerance=radial_ok, contact_tolerance_m=.0002)
                    if not resting_insertion:
                        raise RuntimeError("Route finished without a released, stable insertion")
    except BaseException:
        report.update(status="failed", error=traceback.format_exc())
        raise
    finally:
        if monitor is not None:
            monitor.close()
        report["wall_time_s"] = time.time()-report["started"]
        write_json_atomic(output/"run_report.json", report)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--setting", choices=("current", "historical_two_retreats"), default="current")
    parser.add_argument("--part", choices=("pickup", "solve"), default="pickup")
    parser.add_argument("--grasp-roll-deg", type=float, default=0.)
    parser.add_argument("--grasp-style", choices=("top", "side"), default="top")
    parser.add_argument("--physics-dt", type=float, default=.005)
    parser.add_argument("--solver-substeps", type=int, default=8)
    parser.add_argument("--control-decimation", type=int, default=5)
    parser.add_argument("--no-rgb", action="store_true", help="Explicit physics diagnostic; no video qualification")
    parser.add_argument("--compute-backend", choices=("cuda", "cpu"), default="cuda")
    parser.add_argument("--worker", action="store_true", help=argparse.SUPPRESS)
    args = parser.parse_args()
    output = args.output.resolve()
    if args.worker:
        worker(output, setting=args.setting, part=args.part, grasp_roll_deg=args.grasp_roll_deg, grasp_style=args.grasp_style,
               physics_dt=args.physics_dt, solver_substeps=args.solver_substeps,
               control_decimation=args.control_decimation, no_rgb=args.no_rgb, compute_backend=args.compute_backend)
        return
    output.mkdir(parents=True, exist_ok=False)
    from scripts.test_policy_cube_transfer import snapshot
    source = snapshot(output)
    (output/"source_manifest.json").rename(output/"run_source_manifest.json")
    command = [sys.executable, str(source/"scripts/run_lock_picking_policy.py"), "--worker",
        "--output", str(output), "--setting", args.setting, "--part", args.part,
        "--grasp-roll-deg", str(args.grasp_roll_deg), "--grasp-style", args.grasp_style,
        "--physics-dt", str(args.physics_dt), "--solver-substeps", str(args.solver_substeps),
        "--control-decimation", str(args.control_decimation), "--compute-backend", args.compute_backend]
    if args.no_rgb:
        command.append("--no-rgb")
    from importlib.metadata import distribution, version
    engine = Path(distribution("genesis-world").locate_file("genesis"))
    identity = dict(command=command, genesis_version=version("genesis-world"),
        constraint_solver_sha256=hashlib.sha256((engine/"engine/solvers/rigid/constraint/solver.py").read_bytes()).hexdigest())
    (output/"invocation.json").write_text(json.dumps(identity, indent=2))
    env = dict(os.environ, PYTHONPATH=str(source), OMP_NUM_THREADS="1", MKL_NUM_THREADS="1",
        OPENBLAS_NUM_THREADS="1", QD_NUM_THREADS="1", TOPOGYM_VISUAL_ASSET_ROOT=str(ROOT/".external/nyx-assets"))
    with (output/"runtime.log").open("x") as log:
        result = subprocess.run(command, cwd=source, env=env, stdout=log, stderr=subprocess.STDOUT)
    print(f"exit={result.returncode}; {output}", flush=True)
    raise SystemExit(result.returncode)


if __name__ == "__main__":
    main()
