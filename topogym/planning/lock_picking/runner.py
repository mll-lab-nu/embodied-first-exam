"""Record a lock oracle through standard passive policy dispatch and Env.step.

The historical medium route remains available. Reindex supports the three
original families; simplified supports the two-rotor variants. Both can record
IK/FK for every Cartesian action. All physics
parameters and measured engine properties are recorded, including failed runs.
Solve runs end at native Task success, which may occur while still grasping.
"""
import argparse
from dataclasses import asdict
import hashlib
import json
import os
from pathlib import Path
import sys
import time
import traceback



from contextlib import nullcontext
from topogym.planning.harbor_bridge.actions import SessionPolicyRunner
ROOT = Path(__file__).resolve().parents[3]

def parameters(setting):
    if setting == "current":
        return {}
    from topogym.tasks.lock_picking.lock_picking_medium import LockPickingMediumTask
    return LockPickingMediumTask.variant_parameters


def run_segments(runner, *, part, policy_factory, report, save_report):
    """Stop on native success; a finished policy alone is not a solved task."""
    from topogym.utils.io import to_jsonable
    env = runner.env
    for name in (("pickup", "solve") if part == "solve" else ("pickup",)):
        policy, submission_hash = policy_factory(name)
        result = runner.run_policy(request_id=f"lock-{name}", policy=policy,
            submission_hash=submission_hash, mode="unlimited", state_fields=("world", "task"))
        task_result = env._task.result
        report["segments"].append(to_jsonable(result))
        report.update(last_phase=policy.phase, physics_steps=env._world.physics_step,
                      policy_completed=policy.completed, task_result=to_jsonable(task_result),
                      task_success=bool(task_result.task_success), stop_reason=result["reason"])
        save_report()
        if not result["evidence_complete"] or not result["physics_tick_complete"]:
            raise RuntimeError("Oracle segment evidence is incomplete; see private/policies")
        if result["reason"] not in {"policy_done", "env_terminal"}:
            raise RuntimeError(f"Policy stopped in {policy.phase}: {result['reason']}; see private/policies")
        if task_result.terminated and task_result.task_success:
            return  # No release action or next segment is allowed after Env termination.
        if result["reason"] == "env_terminal" or task_result.terminated:
            raise RuntimeError(f"Task stopped without success in {policy.phase}: {task_result.reason}")


def finish_run(task, world, *, part, report):
    """Record release as a diagnostic; success comes from the Task state machine."""
    import numpy as np
    from topogym.utils.io import to_jsonable
    native_success = bool(task.result.terminated and task.result.task_success)
    report.update(final_world=to_jsonable(world), task_result=to_jsonable(task.result),
                  task_success=native_success, released_at_end=not bool(world["assist_active"]))
    if part == "pickup":
        report["status"] = "task_success" if native_success else "pickup_passed"
        return
    reached, failure, metrics = task.evaluate_state(world)
    key = world["bodies"]["lock_key"]
    report["independent_goal_check"] = dict(
        scope="Read-only Task predicate; full robot process audit is separate",
        reached=bool(reached), failure=failure, metrics=to_jsonable(metrics),
        formal_success=native_success, goal_complete=bool(task.goal_complete),
        resting_insertion_observed=bool(reached and failure is None and report["released_at_end"]
            and np.linalg.norm(key["linear_velocity_m_s"]) < .01
            and np.linalg.norm(key["angular_velocity_rad_s"]) < .1))
    if not native_success or not reached or failure is not None:
        raise RuntimeError("Solve ended without confirmed Task success")
    report["status"] = "task_success"


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


def worker(output, *, setting, part, grasp_roll_deg, grasp_style, physics_dt, solver_substeps, control_decimation, no_rgb, compute_backend,
           variation="medium", route_mode="historical", audit_ik=False, precision="32", endpoint_depth=4.08, session=None):
    import numpy as np
    import torch
    from topogym.simulator import Env, SimulatorConfig, SegmentRunner
    from topogym.planning.lock_picking.lock_picking_medium_planning import LockPickingMediumPolicy
    from topogym.utils.grasp import GraspAssistConfig, GraspTarget
    from topogym.tasks.lock_picking.common import recommended_grasp_assist
    from topogym.utils.io import write_json_atomic, to_jsonable
    from topogym.utils.arrays import to_numpy
    from topogym.simulator.rollout_simulation.segment_contract import fingerprint
    torch.set_num_threads(1)
    output = Path(output)
    config = SimulatorConfig(task_id="lock_picking", variation_id=f"lock_picking_{variation}",
        precision=precision, compute_backend=compute_backend,
        robot_id="panda_robotiq", control_mode="EE_ABS", observation_mode="JOINT",
        enable_privileged=True, task_parameters=parameters(setting),
        physics_dt_s=physics_dt, solver_substeps=solver_substeps, control_decimation=control_decimation,
        max_physics_steps=round((360 if route_mode == "reindex" else 240)/physics_dt), enable_rgb=not no_rgb,
        work_dir=output/"scene", grasp_assist=(recommended_grasp_assist(variation)
            if route_mode == "simplified" else GraspAssistConfig("contact_weld_v1",
            (GraspTarget("lock_key", "key", center_m=(-.495, 0., 0.), radius_m=.032),),
            stable_time_s=max(.05, 2*physics_dt))))
    if session is not None:
        config = session.env.config
    report = dict(status="running", setting=setting, variation=variation, route_mode=route_mode,
        requested_part=part, config=to_jsonable(config), audit_ik=audit_ik,
        policy_parameters=dict(grasp_style=grasp_style, grasp_roll_deg=grasp_roll_deg,
                               endpoint_depth=endpoint_depth),
        timing_scope="explicit recorded World tick/substep configuration; simulator defaults unchanged",
        started=time.time(), events=[], segments=[],
        completion_contract="task_success" if part == "solve" else "pickup",
        task_success=False,
        qualification="Native Task success is recorded; independent physical process audit remains separate",
        from_default_home=True, policy_access="unlimited world state; ordinary EE_ABS actions only",
        provenance=dict(commit="cb60f01b32786cc9c26f754f91b7be4bef3f9ca6",
            semantic_route=("two_rotor_v1 straight insertion / first-rotor contact turn" if route_mode == "simplified"
                            else "2026-09-18_standard_150mm_purple_trace_v1 commands.jsonl"),
            changes=("Two-rotor route and short-handle grasp; " if route_mode == "simplified" else
                     "Current family slots and stops with repeated passive reindexing; "
                     if route_mode == "reindex" else "Recovered mechanism physics and two-retreat slots; ")
                    + "current Panda/Robotiq and lab placement; automatic grasp and regrasp through measured-pose EE actions"))
    write_json_atomic(output/"run_report.json", report)
    active = [None]
    monitor = None
    ik_stream = None
    try:
        if compute_backend == "cuda" and not torch.cuda.is_available():
            raise RuntimeError("CUDA/Nyx unavailable")
        with (Env(config) if session is None else nullcontext(session.env)) as env:
            if session is None:
                env.reset(seed=0)
            geometry = asdict(env._task.layout)
            report.update(geometry=geometry, task_instance_id=env._task.instance_id,
                initial_robot=to_jsonable(env._robot.observe()),
                initial_task=to_jsonable(env._task.result), asset_sha256=to_jsonable(env._asset_build.sha256))
            properties = {}
            disc_names = [f"lock_disc_{i}" for i in range(env._task.layout.disc_count)]
            for name in [*disc_names, "lock_key"]:
                entity = env._world.entities[name]
                properties[name] = dict(mass_kg=float(entity.get_mass()),
                    armature=to_numpy(entity.get_dofs_armature()).tolist(),
                    damping=to_numpy(entity.get_dofs_damping()).tolist())
            report["measured_engine_properties"] = properties
            report["task_physics"] = env._task.config["physics"]
            for name in disc_names:
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
            with (SegmentRunner(env, output, prepared_output=True) if session is None else
                  nullcontext(SessionPolicyRunner(session, control_mode="EE_ABS"))) as runner:
                monitor = (output/"private/lock_monitor.jsonl").open("x", buffering=1)
                if audit_ik:
                    ik_stream = (output/"private/robot_ik.jsonl").open("x", buffering=1)
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
                        disc_angles_deg=[float(np.degrees(np.asarray(world["articulations"][name]["joints"]["disc_hinge"]["position"]).item()))
                                         for name in disc_names],
                        task_result=env._task.result, contacts=interesting,
                        robot_qpos=to_numpy(env._robot.entity.get_qpos()).reshape(-1).tolist())
                    monitor.write(json.dumps(to_jsonable(progress), allow_nan=False)+"\n")
                    write_json_atomic(output/"progress.json", progress)
                env.add_state_sink(monitor_tick)
                monitor_tick(env.tick_record())
                source = json.loads((output/"run_source_manifest.json").read_text())
                def policy_factory(name):
                    kwargs = dict(geometry=geometry, part=name, grasp_roll_deg=grasp_roll_deg, grasp_style=grasp_style)
                    if route_mode == "simplified":
                        from topogym.planning.lock_picking.simplified_policy import SimplifiedLockPickingPolicy
                        kwargs["rotor_stops"] = env._task.config["rotor_stops"]
                        kwargs["endpoint_depth"] = endpoint_depth
                        policy = SimplifiedLockPickingPolicy(**kwargs)
                    elif route_mode == "reindex":
                        from topogym.planning.lock_picking.reindex_policy import LockPickingReindexPolicy
                        kwargs["rotor_stops"] = env._task.config["rotor_stops"]
                        kwargs["endpoint_depth"] = endpoint_depth
                        policy = LockPickingReindexPolicy(**kwargs)
                    else:
                        policy = LockPickingMediumPolicy(**kwargs)
                    if audit_ik:
                        from topogym.planning.lock_picking.recorded_ik import RecordedIKPolicy
                        policy = RecordedIKPolicy(policy, env._robot, ik_stream)
                    active[0] = policy
                    return policy, fingerprint(dict(source=source, parameters=kwargs))
                run_segments(runner, part=part, policy_factory=policy_factory, report=report,
                             save_report=lambda: write_json_atomic(output/"run_report.json", report))
                finish_run(env._task, env._world.read_state(), part=part, report=report)
    except BaseException:
        report.update(status="failed", error=traceback.format_exc())
        raise
    finally:
        if monitor is not None:
            monitor.close()
        if ik_stream is not None:
            ik_stream.close()
        report["wall_time_s"] = time.time()-report["started"]
        write_json_atomic(output/"run_report.json", report)

