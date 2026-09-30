"""Independent tick-evidence audit; never trusts the native success flag alone."""
import hashlib
import json
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


def audit_execution(run, output, *, require_native_success=False, robot_geometry=True):
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
    config = json.loads((trail/"config.json").read_text())
    if (config["grasp_assist"]["model"] != "contact_weld_v1" or
            episode["robot_id"] != "panda_robotiq" or episode["initial_state"] is not None):
        raise ValueError("This audit covers Panda with contact-triggered assistance and authored initial state")
    dt = float(config["physics_dt_s"])
    checker = RigidPathChecker(fixed, ball)
    from .variant_oracle import initial_free
    if not initial_free(checker, initial):
        raise ValueError("Authored initial geometry intersects: tick-end contact samples cannot qualify it")
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
    binding = None
    evidence_hash = hashlib.sha256()
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
                if np.max(np.abs(q-np.array([0., np.pi/8, 0., -5*np.pi/8, 0., 3*np.pi/4, -np.pi/4]))) > 1e-8:
                    raise ValueError("Proof did not start at default home")
            transport = names.get(row["segment_id"]) in {"extract", "stable_goal"}
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
                if binding is None:
                    binding = current_binding
                    evidence = binding["acquisition_evidence"]
                    link_map = dict(zip(world["articulations"]["robot"]["links"], bodies["robot"]["link_indices"], strict=True))
                    fingers = {link_map["left_finger"], link_map["right_finger"]}
                    hits = set()
                    for contact in evidence["rows"]:
                        if np.linalg.norm(contact["force_n"]) > .01:
                            pair = {contact["link_a"], contact["link_b"]}
                            if pair & ball_ids:
                                hits |= pair & fingers
                    acquired = hits == fingers and evidence["physics_step"] <= tick
                hand_pose = body_pose(world["articulations"]["robot"]["links"]["hand"])
                actual = relative_pose(hand_pose, body_pose(bodies["hedgehog_ball"]))
                translation, angle = errors(actual, body_pose(current_binding["relative_pose"]))
                max_grasp_translation, max_grasp_angle = max(max_grasp_translation, translation), max(max_grasp_angle, angle)
                if transport and (translation > .002 or angle > .05):
                    fail("grasp_drift", tick)
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
        first_goal_tick=first_goal_tick, raw_goal_stable_time_s=stable,
        maximum_contact_penetration_m=max_penetration, maximum_robot_fixture_force_n=max_robot_force,
        maximum_transport_fixture_force_n=max_transport_force,
        minimum_transport_ball_clearance_m=min_ball_gap, minimum_robot_fixture_clearance_m=min_robot_gap if shapes else None,
        minimum_nonadjacent_arm_self_clearance_m=min_self_gap if shapes else None,
        maximum_grasp_translation_m=max_grasp_translation, maximum_grasp_rotation_rad=max_grasp_angle,
        bilateral_acquisition_verified=acquired, robot_surface_audit=bool(shapes),
        physical_dt_s=dt, solver_substeps=config["solver_substeps"], assistance="contact_weld_v1",
        limitations=["Finite seed/default-parameter instance", "Contact-triggered assisted grasp; not friction-only",
                     "Tick-end evidence; no continuous-time/all-substep qualification",
                     "No RGB/video qualification", "Robot mounting link0 contact with table is excluded"])
