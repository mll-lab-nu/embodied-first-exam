"""Independent tick-evidence audit; never trusts the native success flag alone."""
import hashlib
import json
import re
from pathlib import Path

import fcl
import numpy as np
from scipy.spatial.transform import Rotation

from topogym.evaluation.task_metrics import placement_candidate
from topogym.planning.buzz_wire_3d.kinematics import manager, distance, mesh_object
from topogym.planning.rigid_reference.feedback import body_pose, relative_pose, errors
from topogym.planning.rigid_reference.geometry import RigidPathChecker, matrix
from topogym.utils.io import to_jsonable
from .kinematics import surface_object
from .object_oracle import frozen_problem


def phase_role(name):
    """Known controller phases; unknown names cannot evade transport checks."""
    if name == "initial-observation":
        return "initial"
    match = re.fullmatch(r"(?:regrasp_[0-9]+_)?(partial_close|home_to_pregrasp|transfer_to_pregrasp|approach|close|test_lift|"
                         r"release_for_regrasp|retreat_after_release|pickup_departure|extract|stable_goal|intermediate_hold)", name)
    if match is None:
        raise ValueError("Unknown Hedgehog audit phase: "+str(name))
    if match[1] == "retreat_after_release":
        return "released_transfer"
    return "clear_transport" if match[1] in {"pickup_departure", "extract", "stable_goal", "intermediate_hold"} else "acquisition_or_support"


def binding_acquisition_valid(binding, world, tick):
    """Check each newly acquired binding, including acquisitions after release."""
    evidence = binding["acquisition_evidence"]
    bodies = world["bodies"]
    ball_ids = set(bodies["hedgehog_ball"]["link_indices"])
    link_map = dict(zip(world["articulations"]["robot"]["links"], bodies["robot"]["link_indices"], strict=True))
    fingers = {link_map["left_finger"], link_map["right_finger"]}
    if (binding["hand"] != "arm" or binding["target"] != ["hedgehog_ball", "hedgehog"]
            or binding["links"][0] != link_map["hand"] or binding["links"][1] not in ball_ids
            or evidence["source"] != "genesis_rigid_final_substep"
            or not 0 < evidence["physics_step"] <= tick):
        return False
    hits = set()
    for contact in evidence["rows"]:
        force = np.asarray(contact["force_n"], float)
        if force.shape != (3,) or not np.isfinite(force).all():
            return False
        if np.linalg.norm(force) > .01:
            pair = {contact["link_a"], contact["link_b"]}
            if pair & ball_ids:
                hits |= pair & fingers
    return hits == fingers


def binding_matches_native_contacts(binding, world, tick):
    """At first observation, corroborate acquisition with that tick's contacts."""
    evidence = binding["acquisition_evidence"]
    if evidence["physics_step"] != tick:
        return False
    contacts = world["contacts"]
    a = np.asarray(contacts["link_a"]).reshape(-1)
    b = np.asarray(contacts["link_b"]).reshape(-1)
    forces = np.asarray(contacts["force"], float).reshape(-1, 3)
    depths = np.asarray(contacts["penetration"], float).reshape(-1)
    if not (len(a) == len(b) == len(forces) == len(depths)):
        return False
    for row in evidence["rows"]:
        if not any(x == row["link_a"] and y == row["link_b"]
                   and np.array_equal(force, np.asarray(row["force_n"], float))
                   and depth == row["penetration_m"]
                   for x, y, force, depth in zip(a, b, forces, depths)):
            return False
    return bool(evidence["rows"])


def audit_execution(run, output, *, require_native_success=False, robot_geometry=True,
                    allow_hard_initial_settle=False):
    run, output = Path(run), Path(output)
    trail = run/"trail"
    metadata = json.loads((trail/"private/static_model.json").read_text())
    episode = metadata["episode"]
    task, ball, fixed, frame, initial, frozen = frozen_problem(
        output, seed=episode["seed"], variation=episode["canonical_variation_id"])
    assets = json.loads((trail/"asset_manifest.json").read_text())
    if assets != frozen["asset_sha256"]:
        raise ValueError("Recorded assets do not match the independently rebuilt geometry")
    if episode["model_revision"] != task.model_revision or episode["task_id"] != task.task_id:
        raise ValueError("Wrong task/model revision")
    if episode["terminal"]["goal_region"] != to_jsonable(frozen["goal_region"]):
        raise ValueError("Goal region changed")
    ledger = json.loads((trail/"report.json").read_text())
    if ledger["status"] != "complete":
        raise ValueError("Episode evidence is not sealed")
    segments = [row["result"] for row in ledger["segments"]]
    if any(not r["evidence_complete"] or not r["physics_tick_complete"] for r in segments):
        raise ValueError("Incomplete physical evidence")
    if any(a["end_state_ref"] != b["start_state_ref"] for a, b in zip(segments, segments[1:])):
        raise ValueError("Segment chain is discontinuous")
    names = {r["segment_id"]: r["request_id"] for r in segments}
    roles = {segment: phase_role(name) for segment, name in names.items()}
    config = json.loads((trail/"config.json").read_text())
    if (config["grasp_assist"]["model"] != "contact_weld_v1" or
            episode["robot_id"] != "panda_robotiq" or episode["initial_state"] is not None):
        raise ValueError("This audit covers Panda with contact-triggered assistance and authored initial state")
    dt = float(config["physics_dt_s"])
    checker = RigidPathChecker(fixed, ball)
    from .variant_oracle import initial_free
    authored_initial_free = initial_free(checker, initial)
    if allow_hard_initial_settle and (
            task.variation_id != "hedgehog_in_cage_hard" or task.model_revision != "fixed_v2"
            or episode["seed"] != 0 or to_jsonable(task.config) != to_jsonable(task.defaults)
            or dt != .025 or config["solver_substeps"] != 40 or config["control_decimation"] != 1):
        raise ValueError("Recorded initial settling is limited to default hard fixed_v2 seed 0, 25 ms / 40 substeps")
    if not authored_initial_free and not allow_hard_initial_settle:
        raise ValueError("Authored initial geometry intersects: tick-end contact samples cannot qualify it")
    settling_segment = None
    if allow_hard_initial_settle:
        physical_segments = [r for r in segments if r["physics_steps"]]
        if not physical_segments or physical_segments[0]["request_id"] != "partial_close":
            raise ValueError("The original hard episode must begin with recorded home settling")
        settling_segment = physical_segments[0]["segment_id"]
    fixed_world = fixed.copy()
    fixed_world.apply_transform(matrix(*frame))
    fixed_manager = manager([surface_object(fixed_world.vertices, fixed_world.faces)])
    shapes, self_pairs = [], []
    if robot_geometry:
        descriptor = json.loads((run/"robot_geometry.json").read_text())
        payload = run/"robot_geometry.npz"
        if hashlib.sha256(payload.read_bytes()).hexdigest() != descriptor["sha256"]:
            raise ValueError("Robot geometry checksum mismatch")
        with np.load(payload) as arrays:
            for link in descriptor["links"]:
                if link["local_index"] == 0:
                    continue  # intended fixed mounting contact
                for key in link["geoms"]:
                    shapes.append((link["name"], mesh_object(arrays[key+"_vertices"], arrays[key+"_faces"])))
        robot_manager = manager([obj for _, obj in shapes])
        indices = {link["name"]: link["local_index"] for link in descriptor["links"]}
        for i, (name_a, first) in enumerate(shapes):
            for name_b, second in shapes[i+1:]:
                a, b = indices[name_a], indices[name_b]
                if (a >= 8 and b >= 8) or (a < 8 and b < 8 and abs(a-b) <= 2) or min(a, b) >= 6:
                    continue
                self_pairs.append((first, second))
    failures, stable, active, count = [], 0., False, 0
    max_penetration = max_robot_force = max_transport_force = 0.
    min_ball_gap = min_robot_gap = float("inf")
    min_self_gap = float("inf")
    max_grasp_translation = max_grasp_angle = 0.
    acquired = False
    first_goal_tick = None
    last = None
    binding_key = None
    acquisitions = []
    seen_bindings = set()
    evidence_hash = hashlib.sha256()
    settling = dict(ticks=0, stable_time_s=0., maximum_ball_speed_m_s=0.,
                    maximum_center_radius_m=0., maximum_arm_home_error_rad=0.)
    home = np.array([0., np.pi/8, 0., -5*np.pi/8, 0., 3*np.pi/4, -np.pi/4])
    def fail(reason, tick):
        if len(failures) < 30:
            failures.append(dict(reason=reason, tick=tick))
    with (trail/"private/physics_states.jsonl").open("rb") as stream:
        for line in stream:
            evidence_hash.update(line)
            row = json.loads(line)
            state, world = row["state"], row["world"]
            tick = state["physics_step"]
            if tick != count or state["episode_id"] != episode["episode_id"] or state["branch_id"] != 0:
                raise ValueError("Tick gap, cross-episode state, or rewind in proof chain")
            if abs(state["sim_time_s"]-tick*dt) > 1e-8:
                raise ValueError("Physical time does not match tick count")
            bodies = world["bodies"]
            for name in ("hedgehog_mount", "hedgehog_cage"):
                if max(errors(body_pose(bodies[name]), body_pose(frozen["initial_poses"][name]))) > 1e-9:
                    fail("fixed_fixture_moved", tick)
            robot_ids = set(bodies["robot"]["link_indices"])
            fixed_ids = set().union(*(bodies[n]["link_indices"] for n in ("hedgehog_mount", "hedgehog_cage")))
            table_ids, ball_ids = set(bodies["table"]["link_indices"]), set(bodies["hedgehog_ball"]["link_indices"])
            if tick == 0:
                observed = relative_pose(frame, body_pose(bodies["hedgehog_ball"]))
                if max(errors(observed, initial)) > 1e-10 or world["assist_active"]:
                    raise ValueError("Modified initial ball pose or pre-attached grasp")
                q = np.asarray(row["robot"]["arm"]["joint_position_rad"])
                if np.max(np.abs(q-home)) > 1e-8:
                    raise ValueError("Proof did not start at default home")
            if settling_segment is not None and row["segment_id"] == settling_segment:
                # This explicitly retains the solver's initial penetration
                # resolution. It is a finite simulator execution scope, never
                # a claim that the authored t=0 geometry is collision-free.
                pose = relative_pose(frame, body_pose(bodies["hedgehog_ball"]))
                speed = float(np.linalg.norm(bodies["hedgehog_ball"]["linear_velocity_m_s"]))
                angular = float(np.linalg.norm(bodies["hedgehog_ball"]["angular_velocity_rad_s"]))
                radius = float(np.linalg.norm(pose[0][:2]))
                home_error = float(np.max(np.abs(np.asarray(row["robot"]["arm"]["joint_position_rad"])-home)))
                settling["ticks"] += 1
                settling["stable_time_s"] = settling["stable_time_s"]+dt if speed < .002 and angular < .05 else 0.
                settling["maximum_ball_speed_m_s"] = max(settling["maximum_ball_speed_m_s"], speed)
                settling["maximum_center_radius_m"] = max(settling["maximum_center_radius_m"], radius)
                settling["maximum_arm_home_error_rad"] = max(settling["maximum_arm_home_error_rad"], home_error)
                # A solver launch that exits the cage cannot substitute for
                # extraction. This deliberately narrow settling window is
                # checked at every retained tick of this default instance.
                if radius > .04 or not -.09 <= pose[0][2] <= .02:
                    fail("initial_settling_left_declared_cage_interior", tick)
                if home_error > 1e-6 or world["assist_active"]:
                    fail("initial_settling_used_arm_motion_or_binding", tick)
            transport = roles[row["segment_id"]] == "clear_transport"
            if roles[row["segment_id"]] == "released_transfer" and world["assist_active"]:
                fail("binding_active_during_release_retreat", tick)
            contacts = world["contacts"]
            a, b = np.asarray(contacts["link_a"]).reshape(-1), np.asarray(contacts["link_b"]).reshape(-1)
            forces = np.asarray(contacts["force"], float).reshape(-1, 3)
            depths = np.asarray(contacts["penetration"], float).reshape(-1)
            if not (len(a) == len(b) == len(forces) == len(depths)) or not np.isfinite(np.r_[forces.ravel(), depths]).all():
                raise ValueError("Invalid contact data")
            max_penetration = max(max_penetration, float(depths.max(initial=0.)))
            for x, y, force in zip(a, b, forces):
                value = float(np.linalg.norm(force))
                forbidden = ((x in robot_ids and y in fixed_ids) or (y in robot_ids and x in fixed_ids)
                    or (x in robot_ids-{min(robot_ids)} and y in table_ids)
                    or (y in robot_ids-{min(robot_ids)} and x in table_ids))
                if forbidden:
                    max_robot_force = max(max_robot_force, value)
                    if value > .01:
                        fail("robot_fixture_contact", tick)
                if transport and ((x in ball_ids and y in fixed_ids|table_ids) or
                                  (y in ball_ids and x in fixed_ids|table_ids)):
                    max_transport_force = max(max_transport_force, value)
                    if value > .05:
                        fail("ball_fixture_contact_during_transport", tick)
            if transport:
                if not world["assist_active"]:
                    fail("assisted_binding_missing_during_transport", tick)
                gap = checker.clearance(relative_pose(frame, body_pose(bodies["hedgehog_ball"])))
                min_ball_gap = min(min_ball_gap, gap)
                if gap < .00005:
                    fail("ball_surface_clearance", tick)
            grasp = world.get("grasp", {})
            current_binding = grasp.get("hands", {}).get("arm", {}).get("binding")
            if current_binding is not None:
                current_key = hashlib.sha256(json.dumps(current_binding, sort_keys=True).encode()).hexdigest()
                if current_key != binding_key:
                    valid = binding_acquisition_valid(current_binding, world, tick)
                    native_contacts_verified = binding_matches_native_contacts(current_binding, world, tick)
                    if not native_contacts_verified:
                        valid = False
                        fail("acquisition_not_in_current_native_contacts", tick)
                    if current_key in seen_bindings:
                        valid = False
                        fail("old_binding_reused_after_release", tick)
                    if not valid:
                        fail("invalid_bilateral_acquisition", tick)
                    acquisitions.append(dict(first_observed_tick=tick,
                        acquisition_tick=current_binding["acquisition_evidence"]["physics_step"], verified=valid,
                        native_contacts_verified=native_contacts_verified))
                    acquired = acquired or valid
                    seen_bindings.add(current_key)
                    binding_key = current_key
                hand_pose = body_pose(world["articulations"]["robot"]["links"]["hand"])
                actual = relative_pose(hand_pose, body_pose(bodies["hedgehog_ball"]))
                translation, angle = errors(actual, body_pose(current_binding["relative_pose"]))
                max_grasp_translation, max_grasp_angle = max(max_grasp_translation, translation), max(max_grasp_angle, angle)
                if transport and (translation > .002 or angle > .05):
                    fail("grasp_drift", tick)
            else:
                binding_key = None
            if shapes:
                for name, obj in shapes:
                    p, r = body_pose(world["articulations"]["robot"]["links"][name])
                    obj.setTransform(fcl.Transform(r.as_matrix(), p))
                robot_manager.update()
                gap = distance(robot_manager, fixed_manager)
                min_robot_gap = min(min_robot_gap, gap)
                if gap < 0.:
                    fail("imported_robot_surface_collision", tick)
                self_gap = min(float(fcl.distance(a, b, fcl.DistanceRequest(), fcl.DistanceResult()))
                               for a, b in self_pairs)
                min_self_gap = min(min_self_gap, self_gap)
                if self_gap < 0.:
                    fail("nonadjacent_arm_self_collision", tick)
            reached, failure, _ = placement_candidate(world, task.goal_region, task.placement_vertices,
                task.placement_targets, task.placement_remainder)
            stable = stable+dt if reached and active and not failure else 0.
            active = reached and not failure
            if reached and first_goal_tick is None:
                first_goal_tick = tick
            count += 1
            last = row
    if last is None:
        raise ValueError("Empty physical evidence")
    if count-1 != sum(segment["physics_steps"] for segment in segments):
        raise ValueError("Recorded tick count differs from the sealed segment ledger")
    if last["state"]["state_id"] != segments[-1]["end_state_ref"]["state_id"]:
        raise ValueError("The sealed episode end is missing")
    if max_penetration > .0002:
        fail("contact_penetration_exceeds_0.2mm", count-1)
    if settling_segment is not None and (settling["ticks"]*dt < 3. or settling["stable_time_s"] < 1.-1e-10):
        fail("initial_settling_not_recorded_and_stable", count-1)
    if not acquired:
        fail("no_bilateral_contact_acquisition", count-1)
    if stable < 2.-1e-10:
        fail("goal_not_stable_for_2s", count-1)
    native = bool(last["task"]["result"]["task_success"])
    if require_native_success and not native:
        fail("native_task_success_missing", count-1)
    return dict(status="passed" if not failures else "rejected", passed=not failures, failures=failures,
        native_task_success=native, accepted_proof=not failures and native and bool(shapes),
        checked_states=count, physics_steps=count-1, physical_evidence_sha256=evidence_hash.hexdigest(),
        instance_id=episode["instance_id"], model_revision=episode["model_revision"], seed=episode["seed"],
        geometry_matched=True, goal_region_identity=task.goal_region_identity,
        authored_initial_geometry_free=authored_initial_free,
        initial_geometry_policy="recorded_hard_settle" if allow_hard_initial_settle else "strict",
        initial_settling=settling if allow_hard_initial_settle else None,
        proof_class=("simulator_execution_with_authored_initial_overlap" if not authored_initial_free
                     else "simulator_execution_with_free_authored_initial"),
        first_goal_tick=first_goal_tick, raw_goal_stable_time_s=stable,
        maximum_contact_penetration_m=max_penetration, maximum_robot_fixture_force_n=max_robot_force,
        maximum_transport_fixture_force_n=max_transport_force,
        minimum_transport_ball_clearance_m=min_ball_gap if np.isfinite(min_ball_gap) else None,
        minimum_robot_fixture_clearance_m=min_robot_gap if shapes else None,
        minimum_nonadjacent_arm_self_clearance_m=min_self_gap if shapes else None,
        maximum_grasp_translation_m=max_grasp_translation, maximum_grasp_rotation_rad=max_grasp_angle,
        bilateral_acquisition_verified=acquired and all(a["verified"] for a in acquisitions),
        acquisitions=acquisitions, phase_roles={names[key]: value for key, value in roles.items()},
        robot_surface_audit=bool(shapes),
        physical_dt_s=dt, solver_substeps=config["solver_substeps"], assistance="contact_weld_v1",
        limitations=["Finite seed/default-parameter instance", "Contact-triggered assisted grasp; not friction-only",
                     "Tick-end evidence; no continuous-time/all-substep qualification",
                     "No RGB/video qualification", "Robot mounting link0 contact with table is excluded"]
                    + (["Authored t=0 penetration is retained; tick-end penetration statistics do not measure it",
                        "Initial settling interior bounds are checked at saved ticks, not every solver substep"]
                       if allow_hard_initial_settle else []))
