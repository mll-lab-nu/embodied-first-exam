"""Independent saved-state audit of a complete lock robot episode."""
from collections import deque
import hashlib
import json
from pathlib import Path

import numpy as np

from topogym.utils.io import write_json_atomic
from topogym.utils.grasp import relative_pose, relative_error
from .lock_picking_medium_planning import rotation
from .robot_geometry import LockRobotGeometry


def _rows(path):
    with path.open() as stream:
        for line in stream:
            yield json.loads(line)


def audit_robot_process(env, run, output):
    run, output = Path(run), Path(output)
    report = json.loads((run/"run_report.json").read_text())
    ledger = json.loads((run/"report.json").read_text())
    if ledger["status"] != "complete":
        raise ValueError("Episode evidence is not sealed")
    segments = [row["result"] for row in ledger["segments"]]
    if any(not row["evidence_complete"] or not row["physics_tick_complete"] for row in segments):
        raise ValueError("Incomplete segment evidence")
    if any(a["end_state_ref"] != b["start_state_ref"] for a,b in zip(segments,segments[1:])):
        raise ValueError("Discontinuous segments")
    manifest = json.loads((run/"run_source_manifest.json").read_text())
    for name, digest in manifest.items():
        if hashlib.sha256((run/"source_snapshot"/name).read_bytes()).hexdigest() != digest:
            raise ValueError("Run source hash mismatch: "+name)
    if env._task.instance_id != report["task_instance_id"]:
        raise ValueError("Audit Task differs from recorded instance")
    if dict(env._asset_build.sha256) != report["asset_sha256"]:
        raise ValueError("Audit assets differ from the recorded physical scene")
    group = env._robot.groups["arm"]
    bounds = np.asarray(group.arm_limits_rad)
    geometry = LockRobotGeometry(env)
    errors, contact_violations, geometry_violations = [], [], []
    phases, events = [], []
    minimum_gaps = {k: float("inf") for k in
                    ("robot_fixture_m", "nonfinger_key_m", "finger_nonhandle_m", "nonadjacent_arm_self_m")}
    bindings, grasp_errors = set(), []
    final_window = deque()
    last_state = None
    deep, pending, retreats = False, False, 0
    index, max_force, max_depth, native_reached_ticks = -1, 0., 0., 0
    names = report["contact_link_names"]
    from topogym.solvers.genesis_kinematics import GenesisFKSolver
    fk = GenesisFKSolver(env._robot.entity)
    hand = env._robot.entity.get_link(group.hand_link).idx_local
    max_actual_fk_error, min_joint_margin, max_joint_step = 0., float("inf"), 0.
    previous_q = None
    monitor_rows = _rows(run/"private/lock_monitor.jsonl")
    with (output/"collision_samples.jsonl").open("x") as collisions:
        for index, state in enumerate(_rows(run/"private/physics_states.jsonl")):
            monitor = next(monitor_rows)
            if state["state"] != monitor["state"] or state["state"]["physics_step"] != index:
                raise ValueError("Discontinuous or mismatched saved tick records")
            if state["state"]["branch_id"] != 0:
                raise ValueError("A proof episode must not rewind")
            if last_state is not None and state["state"]["episode_id"] != last_state["state"]["episode_id"]:
                raise ValueError("Mixed episodes")
            world = state["world"]
            q = np.asarray(monitor["robot_qpos"])
            arm_q = q[env._robot._q_indices["arm"][:7]]
            if index == 0 and not np.allclose(arm_q, group.home[:7], atol=1e-6, rtol=0):
                errors.append("Not the default home at birth")
            margin = float(np.minimum(arm_q-bounds[:,0], bounds[:,1]-arm_q).min())
            min_joint_margin = min(min_joint_margin, margin)
            if previous_q is not None:
                max_joint_step = max(max_joint_step, float(abs(arm_q-previous_q).max()))
            previous_q = arm_q
            poses = fk.solve(q)
            fp = np.asarray(poses["position_world_m"]).reshape(-1,3)[hand]
            fr = rotation(np.asarray(poses["orientation_wxyz"]).reshape(-1,4)[hand])
            tcp = fp+fr.apply(group.tcp_position_in_hand_m)
            max_actual_fk_error = max(max_actual_fk_error,
                float(np.linalg.norm(tcp-state["robot"]["arm"]["tcp_position_world_m"])))
            gaps = geometry.check(world)
            for name, gap in gaps.items():
                minimum_gaps[name] = min(minimum_gaps[name], gap)
            if min(gaps.values()) < 0:
                if len(geometry_violations) < 20:
                    geometry_violations.append(dict(tick=index, phase=monitor["phase"], gaps=gaps,
                                                    pairs=geometry.collision_pairs()))
            collisions.write(json.dumps(dict(tick=index, phase=monitor["phase"], gaps=gaps))+"\n")
            phase = monitor["phase"]
            if not phases or phases[-1]["phase"] != phase:
                phases.append(dict(phase=phase, start_tick=index, end_tick=index))
            phases[-1]["end_tick"] = index
            grasp = world["grasp"]
            events.extend(grasp["events"])
            binding = grasp["hands"]["arm"]["binding"]
            if binding is not None:
                tick = binding["acquisition_evidence"]["physics_step"]
                if tick not in bindings:
                    bindings.add(tick)
                    fingers = {int(k) for k,v in names.items() if v in ("robot/left_finger","robot/right_finger")}
                    key_links = set(world["bodies"]["lock_key"]["link_indices"])
                    hits = set()
                    for row in binding["acquisition_evidence"]["rows"]:
                        pair = {row["link_a"], row["link_b"]}
                        if pair & key_links and np.linalg.norm(row["force_n"]) > .01:
                            hits |= pair & fingers
                    if hits != fingers or tick != index or binding["target"] != ["lock_key", "key"]:
                        errors.append(f"Invalid automatic bilateral acquisition at {index}")
                    def array(value):
                        if isinstance(value, dict) and "array_file" in value:
                            with np.load(run/"private"/value["array_file"], allow_pickle=False) as chunk:
                                return chunk[value["key"]]
                        return np.asarray(value)
                    native = {k:array(v) for k,v in world["contacts"].items()}
                    for contact in binding["acquisition_evidence"]["rows"]:
                        found = any(a == contact["link_a"] and b == contact["link_b"]
                            and np.array_equal(f, contact["force_n"]) and d == contact["penetration_m"]
                            for a,b,f,d in zip(native["link_a"],native["link_b"],native["force"],native["penetration"]))
                        if not found:
                            errors.append(f"Acquisition evidence differs from native contacts at {index}")
                parent = world["articulations"]["robot"]["links"]["hand"]
                child = world["articulations"]["lock_key"]["links"]["key"]
                actual = relative_pose(parent["position_m"],parent["quaternion_wxyz"],
                                       child["position_m"],child["quaternion_wxyz"])
                grasp_errors.append(relative_error(binding["relative_pose"],actual))
            for c in monitor["contacts"]:
                robot_a, robot_b = c["a"].startswith("robot/"), c["b"].startswith("robot/")
                forbidden = ((robot_a and not robot_b and not c["b"].startswith("lock_key/"))
                             or (robot_b and not robot_a and not c["a"].startswith("lock_key/")))
                if forbidden and c["force_n"] > .1 and len(contact_violations) < 20:
                    contact_violations.append(dict(tick=index, phase=phase, **c))
                if "lock_key/key" in (c["a"], c["b"]) and any(n.startswith(("lock_disc_","lock_frame_","lock_goal")) for n in (c["a"],c["b"])):
                    max_force, max_depth = max(max_force,c["force_n"]), max(max_depth,c["penetration_m"])
            reached, failure, metrics = env._task.evaluate_state(world)
            native_reached_ticks += int(reached)
            if failure:
                errors.append(f"Task failure at tick {index}: {failure}")
            depth = metrics.get("key_depth", 0.)
            if binding is not None:
                if depth >= 1.9:
                    if pending:
                        retreats += 1
                        pending = False
                    deep = True
                elif deep and depth <= 1.16:
                    pending, deep = True, False
            final_window.append(dict(time=state["state"]["sim_time_s"],
                active=grasp["active"], linear=float(np.linalg.norm(world["bodies"]["lock_key"]["linear_velocity_m_s"])),
                angular=float(np.linalg.norm(world["bodies"]["lock_key"]["angular_velocity_rad_s"]))))
            while final_window and final_window[-1]["time"]-final_window[0]["time"] > .5+1e-8:
                final_window.popleft()
            last_state = state
            if index % 100 == 0:
                write_json_atomic(output/"progress.json", dict(tick=index, phase=phase,
                    geometry_violations=len(geometry_violations), contact_violations=len(contact_violations)))
                print("audit",index,phase,flush=True)
    if next(monitor_rows, None) is not None:
        errors.append("Monitor extends past the saved episode")
    expected = len(env._task.layout.slots[0])-1
    quiet = (final_window[-1]["time"]-final_window[0]["time"] >= .5-1e-8
             and all(not r["active"] and r["linear"]<.01 and r["angular"]<.1 for r in final_window))
    key = last_state["world"]["bodies"]["lock_key"]
    r = rotation(key["quaternion_wxyz"])
    axis, tip, g = r.apply([1.,0.,0.]), np.asarray(key["position_m"]), env._task.layout
    offsets = []
    if axis[0] > .99:
        for plate in range(4):
            for side in (-1.,1.):
                at = tip+axis*((g.disc_x(plate)+side*g.disc_thickness/2-tip[0])/axis[0])
                offsets.append(float(np.linalg.norm(at[1:]-[g.center_y,g.axis_z])))
    radial_ok = bool(offsets and max(offsets)+g.shaft_radius/axis[0] <= g.bore_radius+.0002)
    completion = bool(metrics.get("leading_tab_inserted") and metrics.get("shaft_in_goal")
                      and not metrics.get("clearance_issues") and radial_ok and not failure and quiet)
    completed_controls = [r for r in _rows(run/"private/control_steps.jsonl") if r["kind"]=="completed"]
    queries = list(_rows(run/"private/robot_ik.jsonl"))
    if len(queries) != len(completed_controls) or len(queries) != index:
        errors.append("IK/actions/ticks do not have one-to-one coverage")
    max_compile_difference = 0.
    ik_rows = []
    for query, control in zip(queries, completed_controls):
        if query["state"]["physics_step"]+1 != control["info"]["physics_step"]:
            errors.append("IK query does not precede its executed action")
        if query["ik_requested"]:
            executed = control["info"]["executed_joint_targets"]["arm"]["joint_position_rad"]
            max_compile_difference = max(max_compile_difference,
                float(np.max(abs(np.asarray(executed)-query["arm_joint_position_rad"]))))
            ik_rows.append(query)
    if min_joint_margin < -1e-6 or max_actual_fk_error > 1e-5 or max_compile_difference > 1e-6:
        errors.append("Joint limit or independent FK/compiled target mismatch")
    required = {"close_and_wait_for_automatic_assist", "lift_to_lock_axis", "insert_third_disc",
                "open_for_supported_regrasp", "close_for_automatic_regrasp", "insert_endpoint",
                "release_at_goal", "withdraw_gripper", "verify_stable_insertion"}
    phase_names = {r["phase"] for r in phases}
    if not required <= phase_names:
        errors.append("Missing robot phases: "+str(sorted(required-phase_names)))
    event_names = [r["event"] for r in events]
    if event_names != ["acquired", "released", "acquired", "released"]:
        errors.append("Unexpected grasp event sequence: "+str(event_names))
    if retreats != expected or not quiet or not completion or report["status"] != "route_completed":
        errors.append("Incomplete reindex / released stable insertion")
    result = dict(passed=not errors and not geometry_violations and not contact_violations,
        errors=errors, instance_id=env._task.instance_id, variation=report["variation"],
        ticks=index, saved_states=index+1, physical_time_s=last_state["state"]["sim_time_s"],
        from_default_home=True, no_rewind=True, recorded_ik_queries=len(ik_rows),
        maximum_ik_position_error_m=max(r["position_error_m"] for r in ik_rows),
        maximum_ik_orientation_error_rad=max(r["orientation_error_rad"] for r in ik_rows),
        maximum_query_vs_executed_joint_target_rad=max_compile_difference,
        maximum_measured_qpos_fk_position_error_m=max_actual_fk_error,
        minimum_measured_joint_limit_margin_rad=min_joint_margin, maximum_measured_joint_step_rad=max_joint_step,
        phases=phases, observed_retreats=retreats, expected_retreats=expected,
        grasp_events=[{k:r[k] for k in ("event","physics_step")} for r in events],
        grasp_relative_error_max_translation_m=max(e[0] for e in grasp_errors),
        grasp_relative_error_max_angle_rad=max(e[1] for e in grasp_errors),
        final_half_second=list(final_window), resting_insertion_observed=completion,
        final_goal_metrics=metrics, final_axis_offsets_m=offsets,
        released_contact_compliance_tolerance_m=.0002,
        collision_scope=geometry.scope, minimum_collision_gaps_m=minimum_gaps,
        geometry_violations=geometry_violations, measured_robot_fixture_contact_violations=contact_violations,
        maximum_sampled_key_fixture_force_n=max_force, maximum_sampled_key_fixture_penetration_m=max_depth,
        contact_coverage="last solver substep at every saved World tick; not every substep",
        native_instantaneous_goal_reached_ticks=native_reached_ticks,
        native_task_success=report["task_result"]["task_success"],
        classification="Full assisted robot process with recorded IK; separate from formal benchmark qualification")
    write_json_atomic(output/"robot_process_audit.json", result)
    return result
