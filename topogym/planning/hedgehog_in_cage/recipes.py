"""Manager oracle: home, contact acquisition, measured route, fixed goal.

Only observation policies issue native joint targets. Geometry and IK queries
are read-only. This routine does not modify object poses or passive joints.
"""
import hashlib
import json
from pathlib import Path

import numpy as np
from scipy.spatial.transform import Rotation

from topogym.utils.arrays import to_numpy
from topogym.utils.io import write_json_atomic, to_jsonable
from .guards import ContactGuardedSequence, GraspGuardedSequence
from .kinematics import HedgehogIK
from .held_oracle import plan_held_path


def _pickup_settings(pickup):
    approach_margin = float((pickup or {}).get("minimum_approach_clearance_m", .0003))
    pregrasp_distance = float((pickup or {}).get("pregrasp_distance_m", .045))
    intermediate = (pickup or {}).get("intermediate_goal")
    release_for_regrasp = bool((pickup or {}).get("release_for_regrasp", False))
    if release_for_regrasp and intermediate is None:
        raise ValueError("A regrasp release diagnostic requires an explicit intermediate goal")
    if not np.isfinite(approach_margin) or approach_margin < .0001:
        raise ValueError("Pickup approach clearance must be finite and at least 0.1 mm")
    if not np.isfinite(pregrasp_distance) or not .005 <= pregrasp_distance <= .15:
        raise ValueError("Pregrasp distance must be between 5 and 150 mm")
    return approach_margin, pregrasp_distance, intermediate, release_for_regrasp


def _transport_settings(pickup, variation):
    margin = float((pickup or {}).get("held_path_clearance_m", .0001 if variation == "easy" else .001))
    speed = float((pickup or {}).get("maximum_transport_joint_speed_rad_s", .05 if variation == "easy" else .15))
    if not np.isfinite(margin) or not .0001 <= margin <= .005:
        raise ValueError("Held path clearance must be between 0.1 and 5 mm")
    if not np.isfinite(speed) or not .01 <= speed <= .25:
        raise ValueError("Transport joint speed must be between 0.01 and 0.25 rad/s")
    return margin, speed


def _departure_settings(pickup):
    """Optional checked motion after a short, explicitly recorded support lift."""
    profile = pickup or {}
    hints = profile.get("pickup_departure_hints")
    if hints is None:
        if "support_separation_m" in profile:
            raise ValueError("A custom support separation requires departure hints")
        return None, .012
    if not isinstance(hints, list) or not 1 <= len(hints) <= 64:
        raise ValueError("Pickup departure requires 1 to 64 cage-frame poses")
    for pose in hints:
        if not isinstance(pose, dict):
            raise ValueError("Pickup departure poses must be mappings")
        p = np.asarray(pose.get("position_m"), float)
        q = np.asarray(pose.get("quaternion_wxyz"), float)
        if (p.shape != (3,) or q.shape != (4,) or not np.isfinite(p).all()
                or not np.isfinite(q).all() or not np.isclose(np.linalg.norm(q), 1.)):
            raise ValueError("Pickup departure requires finite positions and unit quaternions")
    separation = float(profile.get("support_separation_m", .0005))
    if not np.isfinite(separation) or not .0001 <= separation <= .001:
        raise ValueError("Support separation must be between 0.1 and 1 mm")
    return hints, separation


def run_medium_oracle(env, runner, output, *, pickup=None, search_iterations=30000):
    output = Path(output)
    variation = env._task.variation_id.removeprefix("hedgehog_in_cage_")
    if env._task.task_id != "hedgehog_in_cage" or (variation != "medium" and pickup is None):
        raise ValueError("An explicit checked pickup is required for an additional Hedgehog variant")
    if env._world.physics_step != 0:
        raise ValueError("The complete oracle must begin at the episode's default home state")
    control_dt = env.config.physics_dt_s*env.config.control_decimation
    assisted = env.config.grasp_assist.model == "contact_weld_v1"
    held_margin, transport_speed = _transport_settings(pickup, variation)
    profiles = [pickup, *((pickup or {}).get("regrasps") or [])]
    settings = [_pickup_settings(profile) for profile in profiles]
    departures = [_departure_settings(profile) for profile in profiles]
    if any(intermediate is None or not release for _, _, intermediate, release in settings[:-1]):
        raise ValueError("Each stage before a regrasp must end at an explicit intermediate release")
    approach_margin, pregrasp_distance, intermediate, release_for_regrasp = settings[0]
    phase_prefix = ""
    report = dict(status="running", start="default_home", assistance=env.config.grasp_assist.model,
                  config=to_jsonable(env.config), instance_id=env._task.instance_id,
                  asset_sha256=env._asset_build.sha256, phases=[], task_success=False,
                  accepted_proof=False, contact_coverage="tick-end samples; no all-substep claim")
    report.update(held_path_margin_m=held_margin, maximum_transport_joint_speed_rad_s=transport_speed,
                  minimum_planned_approach_clearance_m=approach_margin,
                  pregrasp_distance_m=pregrasp_distance,
                  scope=("complete Task attempt with regrasp" if len(profiles)>1 else
                         "intermediate release diagnostic" if intermediate is not None else "complete Task attempt"))
    source = Path(__file__).read_bytes()+Path(__file__).with_name("guards.py").read_bytes()
    # Export the imported collision surfaces in authored link frames so an
    # independent reader can audit the recorded link poses without an engine.
    arrays, links = {}, []
    for link in env._robot.entity.links:
        p = to_numpy(link.get_pos()).reshape(3)
        r = Rotation.from_quat(to_numpy(link.get_quat()).reshape(4)[[1, 2, 3, 0]])
        keys = []
        for geom in link.geoms:
            key = f"geom_{len(arrays)//2}"
            arrays[key+"_vertices"] = r.inv().apply(to_numpy(geom.get_verts()).reshape(-1, 3)-p)
            arrays[key+"_faces"] = np.asarray(geom.init_faces)
            keys.append(key)
        links.append(dict(name=link.name, index=int(link.idx), local_index=int(link.idx_local), geoms=keys))
    np.savez_compressed(output/"robot_geometry.npz", **arrays)
    write_json_atomic(output/"robot_geometry.json", dict(links=links,
        sha256=hashlib.sha256((output/"robot_geometry.npz").read_bytes()).hexdigest(),
        frame="Genesis relative=True authored link frames", source="imported robot collision surfaces"))

    def hold(seconds):
        return [{}]*int(np.ceil(seconds/control_dt))

    def run(name, actions, *, transport=False):
        name = phase_prefix+name
        print(f"{name}: {len(actions)} control steps", flush=True)
        write_json_atomic(output/f"{name}_actions.json", actions)
        policy = GraspGuardedSequence(actions) if transport else ContactGuardedSequence(actions)
        result = runner.run_policy(request_id=name, policy=policy,
            submission_hash=hashlib.sha256(source+json.dumps(actions, sort_keys=True).encode()).hexdigest(),
            mode="unlimited", state_fields=("world",))
        state = dict(world=env._world.read_state(), robot=env._robot.observe(), segment=result)
        write_json_atomic(output/f"{name}_state.json", state)
        report["phases"].append(dict(name=name, result=result))
        write_json_atomic(output/"oracle_report.json", report)
        if result["reason"] != "policy_done" and not env._task.result.task_success:
            raise RuntimeError(f"{name}: {result['reason']}")
        return state

    def joint_actions(path, *, grip=.6, speed=.25):
        previous = to_numpy(env._robot.entity.get_qpos()).reshape(-1)[:7]
        actions = []
        for q in path:
            target = np.asarray(q)[:7]
            count = max(1, int(np.ceil(np.max(np.abs(target-previous))/(speed*control_dt))))
            for u in np.linspace(0., 1., count+1)[1:]:
                actions.append({"arm": {"joint_position_rad": (previous+u*(target-previous)).tolist(),
                                        "gripper_position_rad": grip}})
            previous = target
        return actions+hold(.5)

    write_json_atomic(output/"oracle_report.json", report)
    try:
        for stage_index, pickup in enumerate(profiles):
            phase_prefix = "" if stage_index == 0 else f"regrasp_{stage_index}_"
            approach_margin, pregrasp_distance, intermediate, release_for_regrasp = settings[stage_index]
            held_margin, transport_speed = _transport_settings(pickup, variation)
            run("partial_close", [{"arm": {"gripper_position_rad": .6}}]+hold(10. if stage_index == 0 else 1.)[:-1])
            kin = HedgehogIK(env)
            bp, br = kin.ball_pose
            # Grip the -z spike. The 180-degree symmetric hand roll keeps joint7
            # away from its limit; the contact point stays in the same place.
            relr = Rotation.from_euler("z", 300., degrees=True)*Rotation.from_euler("xy", [-15., -15.], degrees=True)
            relp = np.array([0., 0., -.074])-relr.apply([0., 0., .085])
            if pickup is not None:
                from topogym.planning.rigid_reference.feedback import body_pose
                relp, relr = body_pose(pickup["hand_in_ball"])
            handp, handr = bp+br.apply(relp), br*relr
            prehand = handp-handr.apply([0., 0., pregrasp_distance])
            tcp_offset = handr.apply(kin.group.tcp_position_in_hand_m)
            goal_seed = None
            if pickup is not None and "qpos" in pickup:
                # Trace the checked grasp branch backward. A free-transfer planner
                # may otherwise choose another redundant branch at the same TCP.
                q = kin.seed.copy()
                q[:7] = np.asarray(pickup["qpos"])[:7]
                for u in np.linspace(1., 0., 46):
                    q = kin.solve((prehand+u*(handp-prehand)+tcp_offset, handr), q)
                    gaps = kin.gaps(q)
                    if min(gaps.values()) < approach_margin:
                        write_json_atomic(output/f"{phase_prefix}approach_rejection.json", dict(direction="backward", fraction=u,
                            qpos=q.tolist(), gaps=gaps))
                        raise RuntimeError("Checked pickup branch has a blocked approach")
                goal_seed = q
            home_route = kin.plan_free_tcp((prehand+tcp_offset, handr), random_seed=0, iterations=6000,
                                          goal_seed=goal_seed)
            q, approach = np.asarray(home_route[-1]["qpos"]), []
            for u in np.linspace(0., 1., 46)[1:]:
                q = kin.solve((prehand+u*(handp-prehand)+tcp_offset, handr), q)
                if kin.clearance(q) < approach_margin:
                    write_json_atomic(output/f"{phase_prefix}approach_rejection.json", dict(direction="forward", fraction=u,
                        qpos=q.tolist(), gaps=kin.gaps(q)))
                    raise RuntimeError("Measured fingers/robot cannot execute the pickup approach")
                approach.append(q.tolist())
            write_json_atomic(output/f"{phase_prefix}pickup_plan.json", dict(home_route=home_route, approach_qpos=approach,
                hand_in_ball=dict(position_m=relp.tolist(), quaternion_wxyz=relr.as_quat()[[3, 0, 1, 2]].tolist())))
            run("home_to_pregrasp" if stage_index == 0 else "transfer_to_pregrasp", joint_actions([row["qpos"] for row in home_route]))
            run("approach", joint_actions(approach, speed=.15))
            run("close", [{"arm": {"gripper_position_rad": .8}}]+hold(3.)[:-1])
            before = env._world.read_state()
            if assisted and not before["assist_active"]:
                raise RuntimeError("No contact-triggered grasp acquisition")
            kin = HedgehogIK(env)
            p, r = kin.tcp_pose(kin.seed)
            departure_hints, lift_distance = departures[stage_index]
            if departure_hints is not None:
                cagep, cager = body_pose(before["bodies"]["hedgehog_cage"])
                goalp = cagep+cager.apply(departure_hints[-1]["position_m"])
                requested_rise = goalp[2]-before["bodies"]["hedgehog_ball"]["position_m"][2]
                if not .009 <= requested_rise <= .10:
                    raise ValueError("Pickup departure must end 9 to 100 mm above the measured pickup")
            q, lift = kin.seed.copy(), []
            for u in np.linspace(0., 1., 51)[1:]:
                q = kin.solve((p+[0., 0., lift_distance*u], r), q)
                lift.append(q.tolist())
            state = run("test_lift", joint_actions(lift, grip=.8, speed=.1)+hold(1.))
            if departure_hints is not None:
                if assisted and not state["world"]["assist_active"]:
                    raise RuntimeError("Contact grasp was lost during support separation")
                # Rebuild the grasp from the live state after support separation.
                # All subsequent side motion/rotation is certified and audited
                # as clear transport, not hidden inside a contact-lift exception.
                departure = plan_held_path(env, output/f"{phase_prefix}pickup_departure_geometry",
                    clearance_m=held_margin, wrist_envelope=True, max_turn_deg=180.,
                    iterations=search_iterations, grip_point_in_ball=pickup["grip_point_in_ball"],
                    object_path_hints=departure_hints, preserve_waypoints=True,
                    intermediate_goal=departure_hints[-1], departure_clearance_m=.00001)
                write_json_atomic(output/f"{phase_prefix}pickup_departure_plan.json", departure)
                if departure["status"] != "measured_held_ik_path_found":
                    raise RuntimeError("No verified measured-grasp pickup departure")
                state = run("pickup_departure", joint_actions(
                    [row["qpos"] for row in departure["rows"]], grip=.8, speed=transport_speed), transport=True)
            rise = float(state["world"]["bodies"]["hedgehog_ball"]["position_m"][2]
                         -before["bodies"]["hedgehog_ball"]["position_m"][2])
            report.setdefault("stage_pickups", []).append(dict(stage_index=stage_index, test_lift_rise_m=rise,
                initial_support_lift_m=lift_distance, planned_departure=departure_hints is not None))
            if stage_index == 0:
                report["test_lift_rise_m"] = rise
            if rise < .009 or (assisted and not state["world"]["assist_active"]):
                raise RuntimeError("Pickup did not transfer the ball's weight to the gripper")
            for search_seed in range(3):
                print(f"Measured held search {search_seed}", flush=True)
                plan = plan_held_path(env, output/f"{phase_prefix}held_plan_{search_seed}", random_seed=search_seed,
                                      clearance_m=held_margin, wrist_envelope=True,
                                      max_turn_deg=110. if variation == "medium" else 180.,
                                      iterations=search_iterations,
                                      grip_point_in_ball=None if pickup is None else pickup["grip_point_in_ball"],
                                      object_path_hints=None if pickup is None else pickup.get("object_path_hints"),
                                      departure_clearance_m=(pickup or {}).get("departure_clearance_m", .00005),
                                      intermediate_goal=intermediate,
                                      preserve_waypoints=(pickup or {}).get("preserve_waypoints", False),
                                      placement_goal=(pickup or {}).get("placement_goal"))
                write_json_atomic(output/f"{phase_prefix}held_plan_{search_seed}.json", plan)
                if plan["status"] == "measured_held_ik_path_found":
                    report.setdefault("stage_plans", []).append(dict(stage_index=stage_index, selected_search_seed=search_seed,
                        held_path_margin_m=held_margin, maximum_transport_joint_speed_rad_s=transport_speed))
                    if stage_index == 0:
                        report["selected_search_seed"] = search_seed
                    break
            else:
                raise RuntimeError("No verified measured-grasp IK route in the finite search")
            run("extract", joint_actions([row["qpos"] for row in plan["rows"]], grip=.8, speed=transport_speed), transport=True)
            if intermediate is not None:
                run("intermediate_hold", hold(1.), transport=True)
                if release_for_regrasp:
                    run("release_for_regrasp", [{"arm": {"gripper_position_rad": .6}}]+hold(5.)[:-1])
                if stage_index+1 < len(profiles):
                    continue
                reached, failure, metrics = env._task.evaluate_goal_region(env._world.read_state(), env._task.goal_region)
                report.update(status="intermediate_release_observed" if release_for_regrasp else "intermediate_pose_observed",
                              task_success=bool(env._task.result.task_success), candidate_reached=reached,
                              candidate_failure=failure, candidate_metrics=metrics,
                              task_result=to_jsonable(env._task.result), physics_steps=env._world.physics_step,
                              simulation_time_s=env._world.sim_time_s)
                return report
            if not env._task.result.task_success:
                run("stable_goal", hold(2.5), transport=True)
            reached, failure, metrics = env._task.evaluate_goal_region(env._world.read_state(), env._task.goal_region)
            report.update(status="native_success_pending_audit" if env._task.result.task_success else "candidate_completed",
                          task_success=bool(env._task.result.task_success), candidate_reached=reached,
                          candidate_failure=failure, candidate_metrics=metrics,
                          task_result=to_jsonable(env._task.result), physics_steps=env._world.physics_step,
                          simulation_time_s=env._world.sim_time_s)
            return report
    except Exception as error:
        report.update(status="failed", error=f"{type(error).__name__}: {error}")
        raise
    finally:
        write_json_atomic(output/"oracle_report.json", report)
