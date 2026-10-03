"""Independent tick-evidence audit of a Claws oracle run; never trusts the native success flag alone."""
import hashlib
import json
from pathlib import Path

import fcl
import numpy as np

from topogym.tasks.interlocked_claws.terminal import separation_candidate
from topogym.planning.buzz_wire_3d.kinematics import manager, distance, mesh_object
from topogym.planning.hedgehog_in_cage.kinematics import surface_object
from topogym.planning.rigid_reference.feedback import body_pose, relative_pose, errors
from topogym.planning.rigid_reference.geometry import RigidPathChecker
from topogym.utils.io import to_jsonable
from .object_oracle import frozen_problem
from .evidence import decode_record
from topogym.assets.geometry.interlocked_claws import ARM_LIMITS


def audit_execution(run, output, *, require_native_success=False, robot_geometry=True, pair_margin_m=.00005,
                    piece_force_n=8., departure_window_s=1., tolerate_piece_contact=False, contact_depth_limit_m=.0005):
    """tolerate_piece_contact=True permits bounded sliding contact throughout:
    engine penetration stays below 1 mm and the independent
    FCL triangle contact depth between the piece surfaces stays below contact_depth_limit_m."""
    run, output = Path(run), Path(output)
    trail = run/"trail"
    metadata = json.loads((trail/"private/static_model.json").read_text())
    episode = metadata["episode"]
    task, meshes, poses, table, frozen = frozen_problem(output, variation=episode["canonical_variation_id"], seed=episode["seed"])
    target, other = frozen["target"], frozen["other"]
    assets = json.loads((trail/"asset_manifest.json").read_text())
    if assets != frozen["asset_sha256"]:
        raise ValueError("Recorded assets do not match the independently rebuilt geometry")
    if episode["model_revision"] != task.model_revision or episode["task_id"] != task.task_id:
        raise ValueError("Wrong task/model revision")
    if episode["instance_id"] != task.instance_id or episode["terminal"]["revision"] != task.terminal_revision:
        raise ValueError("Wrong instance or terminal revision")
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
    if (config["grasp_assist"]["model"] != "contact_weld_v1" or episode["robot_id"] != "aloha"
            or episode["initial_state"] is not None):
        raise ValueError("This audit covers ALOHA with contact-triggered assistance and the authored pregrasp birth")
    dt = float(config["physics_dt_s"])
    pair = RigidPathChecker(meshes[target], meshes[other], margin_m=pair_margin_m)
    initial_relative = relative_pose(poses[target], poses[other])
    if not RigidPathChecker(meshes[target], meshes[other]).initial_free(initial_relative):
        raise ValueError("Authored initial geometry intersects")
    piece_objects = {name: surface_object(np.asarray(m.vertices, float), np.asarray(m.faces, np.int32)) for name, m in meshes.items()}
    piece_managers = {name: manager([obj]) for name, obj in piece_objects.items()}
    shapes, self_pairs, fingers_of = [], [], {}
    if robot_geometry:
        descriptor = json.loads((run/"robot_geometry.json").read_text())
        payload = run/"robot_geometry.npz"
        if hashlib.sha256(payload.read_bytes()).hexdigest() != descriptor["sha256"]:
            raise ValueError("Robot geometry checksum mismatch")
        with np.load(payload) as arrays:
            for link in descriptor["links"]:
                for key in link["geoms"]:
                    shapes.append((link["name"], mesh_object(arrays[key+"_vertices"], arrays[key+"_faces"])))
        for side in ("left", "right"):
            fingers_of[side] = {f"{side}/left_finger_link", f"{side}/right_finger_link"}
        nonfinger = {side: manager([obj for name, obj in shapes if name.startswith(side+"/") and "finger" not in name]) for side in fingers_of}
        arm = {side: manager([obj for name, obj in shapes if name.startswith(side+"/")]) for side in fingers_of}
    failures, stable, active, count = [], 0., False, 0
    max_penetration = max_forbidden = max_pair_force = 0.
    min_pair_gap = min_robot_gap = float("inf")
    max_drift = {"left": [0., 0.], "right": [0., 0.]}
    bindings, acquired = {}, {}
    first_goal_tick, last = None, None
    first_moving_tick, last_pair_contact_tick = None, None
    max_triangle_depth = 0.
    surface_intersection_ticks = 0
    minimum_joint_margin = float("inf")
    maximum_robot_self_force = 0.
    evidence_hash = hashlib.sha256()
    # Pregrasp birth: the Task assigns the target piece to the left hand and the remainder to the right.
    # The assisted bindings must confirm the same assignment once they exist.
    ownership = {"left": target, "right": other}
    bindings_confirmed = False
    def fail(reason, tick):
        if len(failures) < 30:
            failures.append(dict(reason=reason, tick=tick))
    with (trail/"private/physics_states.jsonl").open("rb") as stream:
        for line in stream:
            evidence_hash.update(line)
            row = decode_record(json.loads(line), trail/"private", digest=evidence_hash)
            state, world = row["state"], row["world"]
            tick = state["physics_step"]
            if tick != count or state["episode_id"] != episode["episode_id"] or state["branch_id"] != 0:
                raise ValueError("Tick gap, cross-episode state, or rewind in proof chain")
            if abs(state["sim_time_s"]-tick*dt) > 1e-8:
                raise ValueError("Physical time does not match tick count")
            bodies = world["bodies"]
            for side in ("left", "right"):
                q = np.asarray(row["robot"][side]["joint_position_rad"], float)
                limits = np.asarray(ARM_LIMITS)
                if q.shape != (6,) or not np.isfinite(q).all():
                    raise ValueError("Missing or invalid measured arm joints")
                margin = float(np.minimum(q-limits[:, 0], limits[:, 1]-q).min())
                minimum_joint_margin = min(minimum_joint_margin, margin)
                if margin < -1e-4:
                    fail("measured_joint_limit", tick)
            robot_ids = set(bodies["robot"]["link_indices"])
            table_ids = set(bodies["table"]["link_indices"])
            piece_ids = {name: set(bodies[name]["link_indices"]) for name in (target, other)}
            links = world["articulations"]["robot"]["links"]
            index_of = dict(zip(list(links), bodies["robot"]["link_indices"], strict=True))
            if tick == 0:
                for name in (target, other):
                    if max(errors(body_pose(bodies[name]), poses[name])) > 1e-9:
                        raise ValueError("Modified initial piece pose")
                if world["assist_active"]:
                    raise ValueError("Pre-attached grasp at birth")
                q = np.asarray(row["robot"]["left"]["joint_position_rad"]+row["robot"]["right"]["joint_position_rad"])
                planned = np.asarray(episode["initial_robot_qpos"]).reshape(2, 8)[:, :6].ravel() if "initial_robot_qpos" in episode else None
                if planned is not None and np.max(np.abs(q-planned)) > 1e-6:
                    raise ValueError("Proof did not start at the authored pregrasp posture")
            moving = names.get(row["segment_id"]) in {"separate", "park", "transport", "stable_goal"}
            contacts = world["contacts"]
            a, b = np.asarray(contacts["link_a"]).reshape(-1), np.asarray(contacts["link_b"]).reshape(-1)
            forces = np.asarray(contacts["force"], float).reshape(-1, 3)
            depths = np.asarray(contacts["penetration"], float).reshape(-1)
            if not (len(a) == len(b) == len(forces) == len(depths)) or not np.isfinite(np.r_[forces.ravel(), depths]).all():
                raise ValueError("Invalid contact data")
            max_penetration = max(max_penetration, float(depths.max(initial=0.)))
            grasp_hands = world.get("grasp", {}).get("hands", {})
            if not bindings_confirmed and all(grasp_hands.get(s, {}).get("binding") for s in ("left", "right")):
                bound = {s: tuple(grasp_hands[s]["binding"]["target"])[0] for s in ("left", "right")}
                if bound != ownership:
                    raise ValueError("Assisted bindings do not match the pregrasp hand/piece assignment")
                bindings_confirmed = True
            finger_ids = {}
            if ownership:
                finger_ids = {piece: {index_of[f"{s}/left_finger_link"], index_of[f"{s}/right_finger_link"]} for s, piece in ownership.items()}
            base = min(robot_ids)
            for x, y, force in zip(a, b, forces):
                value = float(np.linalg.norm(force)); pr = {int(x), int(y)}
                if int(x) in robot_ids and int(y) in robot_ids:
                    maximum_robot_self_force = max(maximum_robot_self_force, value)
                    if value > .01:
                        fail("native_robot_self_contact", tick)
                if pr & robot_ids and pr & table_ids and not pr & {base}:
                    max_forbidden = max(max_forbidden, value)
                    if value > .01:
                        fail("robot_table_contact", tick)
                for name, ids in piece_ids.items():
                    if pr & ids and pr & robot_ids and not pr & finger_ids.get(name, set()):
                        max_forbidden = max(max_forbidden, value)
                        if value > .01:
                            fail("robot_piece_contact_outside_holding_fingers", tick)
                if all(pr & ids for ids in piece_ids.values()):
                    max_pair_force = max(max_pair_force, value)
                    if moving:
                        if first_moving_tick is None:
                            first_moving_tick = tick
                        last_pair_contact_tick = tick
                        if value > piece_force_n:
                            fail("piece_piece_force", tick)
                        if not tolerate_piece_contact and tick-first_moving_tick > departure_window_s/dt:
                            fail("piece_piece_contact_after_departure_window", tick)
            if moving:
                if first_moving_tick is None:
                    first_moving_tick = tick
                if not world["assist_active"]:
                    fail("assisted_binding_missing_during_motion", tick)
                gap = pair.clearance(relative_pose(body_pose(bodies[target]), body_pose(bodies[other])))
                if gap >= 0.:
                    min_pair_gap = min(min_pair_gap, gap)
                if gap < 0.:
                    surface_intersection_ticks += 1
                    # Surfaces intersect: measure the triangle contact depth independently of the engine SDF.
                    contacts_fcl = fcl.CollisionResult()
                    fcl.collide(*pair.pair.objects, fcl.CollisionRequest(num_max_contacts=4000, enable_contact=True), contacts_fcl)
                    depth = max((float(c.penetration_depth) for c in contacts_fcl.contacts), default=0.)
                    max_triangle_depth = max(max_triangle_depth, depth)
                    if tolerate_piece_contact:
                        if depth > contact_depth_limit_m:
                            fail("piece_triangle_contact_depth", tick)
                    elif tick-first_moving_tick > departure_window_s/dt:
                        fail("piece_surface_intersection", tick)
            for side in ("left", "right"):
                binding = grasp_hands.get(side, {}).get("binding")
                if binding is None:
                    if moving:
                        fail(f"{side}_binding_missing", tick)
                    continue
                if side not in bindings:
                    bindings[side] = binding
                    evidence = binding.get("acquisition_evidence", {})
                    fingers = {index_of[f"{side}/left_finger_link"], index_of[f"{side}/right_finger_link"]}
                    hits = set()
                    for contact in evidence.get("rows", []):
                        if np.linalg.norm(contact["force_n"]) > .01:
                            pr = {contact["link_a"], contact["link_b"]}
                            if pr & piece_ids[tuple(binding["target"])[0]]:
                                hits |= pr & fingers
                    acquired[side] = hits == fingers and evidence.get("physics_step", tick+1) <= tick
                hand_pose = body_pose(links[f"{side}/gripper_link"])
                actual = relative_pose(hand_pose, body_pose(bodies[tuple(binding["target"])[0]]))
                translation, angle = errors(actual, body_pose(binding["relative_pose"]))
                max_drift[side] = np.maximum(max_drift[side], [translation, angle]).tolist()
                if moving and (translation > .003 or angle > .05):
                    fail(f"{side}_grasp_drift", tick)
            if shapes:
                for name, obj in shapes:
                    p, r = body_pose(links[name])
                    obj.setTransform(fcl.Transform(r.as_matrix(), p))
                for name, obj in piece_objects.items():
                    p, r = body_pose(bodies[name])
                    obj.setTransform(fcl.Transform(r.as_matrix(), p))
                    piece_managers[name].update()
                for m in (*nonfinger.values(), *arm.values()):
                    m.update()
                if distance(arm["left"], arm["right"]) < 0.:
                    fail("imported_inter_arm_surface_intersection", tick)
                for side in ("left", "right"):
                    for name in (target, other):
                        checked = nonfinger[side] if ownership and ownership.get(side) == name else arm[side]
                        gap = distance(checked, piece_managers[name])
                        min_robot_gap = min(min_robot_gap, gap)
                        if gap < 0.:
                            fail(f"imported_{side}_surface_intersects_{name}", tick)
            reached, failure, _ = separation_candidate(world, task.placement_vertices,
                                                      minimum_separation_m=task.config["minimum_separation_m"])
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
    if max_penetration > .001:
        fail("contact_penetration_exceeds_1mm", count-1)
    if not all(acquired.get(s) for s in ("left", "right")):
        fail("no_bilateral_contact_acquisition_on_both_hands", count-1)
    if not bindings_confirmed:
        fail("assisted_bindings_never_confirmed", count-1)
    if stable < task.config["stable_duration_s"]-1e-10:
        fail("goal_not_stable_for_required_duration", count-1)
    native = bool(last["task"]["result"]["task_success"])
    if require_native_success and not native:
        fail("native_task_success_missing", count-1)
    return dict(status="passed" if not failures else "rejected", passed=not failures, failures=failures,
        native_task_success=native, accepted_proof=not failures and native and bool(shapes),
        checked_states=count, physics_steps=count-1, physical_evidence_sha256=evidence_hash.hexdigest(),
        instance_id=episode["instance_id"], model_revision=episode["model_revision"], seed=episode["seed"],
        geometry_matched=True, goal_region_identity=task.goal_region_identity, ownership=ownership,
        first_goal_tick=first_goal_tick, raw_goal_stable_time_s=stable, required_stable_time_s=task.config["stable_duration_s"],
        maximum_contact_penetration_m=max_penetration, maximum_forbidden_contact_force_n=max_forbidden,
        maximum_piece_pair_force_n=max_pair_force,
        minimum_measured_arm_joint_margin_rad=minimum_joint_margin,
        maximum_native_robot_self_contact_force_n=maximum_robot_self_force,
        minimum_nonintersecting_piece_pair_clearance_m=min_pair_gap if np.isfinite(min_pair_gap) else None,
        piece_surface_intersection_ticks=surface_intersection_ticks,
        piece_pair_force_limit_n=piece_force_n, departure_window_s=departure_window_s,
        piece_contact_tolerated=tolerate_piece_contact, maximum_piece_triangle_contact_depth_m=max_triangle_depth,
        triangle_contact_depth_limit_m=contact_depth_limit_m if tolerate_piece_contact else None,
        first_moving_tick=first_moving_tick, last_piece_pair_contact_tick=last_pair_contact_tick,
        minimum_robot_piece_clearance_m=min_robot_gap if shapes else None,
        maximum_grasp_drift={s: dict(translation_m=v[0], rotation_rad=v[1]) for s, v in max_drift.items()},
        bilateral_acquisition_verified=acquired, robot_surface_audit=bool(shapes),
        physical_dt_s=dt, solver_substeps=config["solver_substeps"], assistance="contact_weld_v1",
        limitations=["Finite seed/default-parameter instance", "Contact-triggered assisted grasp on both hands; not friction-only",
                     "Tick-end evidence; no continuous-time/all-substep qualification", "No RGB/video qualification", "Finger/piece clamp penetration up to 1 mm tolerated (pregrasp squeeze under the assisted grasp)",
                     ("Piece/piece sliding contact tolerated throughout: engine penetration below 1 mm and FCL triangle contact depth below the declared limit; no clearance claim for the executed run" if tolerate_piece_contact else "Piece/piece contact tolerated only inside the departure window after the sagged assisted grasp binds (limit piece_force_n); afterwards any piece/piece contact fails; the geometric witness, not the run, certifies clearance")])
