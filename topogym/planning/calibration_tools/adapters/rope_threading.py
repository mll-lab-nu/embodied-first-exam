"""Passive relay diagnostics for deformable material stations and robot tracking.

Unlike rigid object tracking, a rope station is identified by its material
coordinate. These measurements never modify the scene or rerun grasp admission.
"""
import numpy as np
import time
from scipy.spatial.transform import Rotation

from ..grasp_observation import explain_grasp


def compare_material_track(world, track, sigma, stations_m):
    """Compare measured FEM stations to a geometric track at the same material coordinates.

    This can read decoded owner evidence offline. It deliberately performs no
    rigid alignment: a drooping or stretched end must remain visible as error.
    ``sigma`` is a caller-supplied geometric hypothesis, not measured progress.
    """
    rope = world["fem"]["rope"]
    material = np.asarray(rope["material_s_m"], float).reshape(-1)
    vertices = np.asarray(rope["position_m"], float).reshape(-1, 3)
    stations = np.asarray(stations_m, float).reshape(-1)
    if (not len(material) or len(material) != len(vertices) or not len(stations)
            or not np.isfinite(material).all() or not np.isfinite(vertices).all()
            or not np.isfinite(stations).all() or not np.isfinite(sigma)
            or np.any(stations < material.min()-1e-7) or np.any(stations > material.max()+1e-7)):
        raise ValueError("Finite FEM material coordinates and in-range stations are required")
    measured, counts = [], []
    for station in stations:
        indices = np.flatnonzero(np.abs(material-station) <= .003)
        if not len(indices):
            indices = np.argsort(np.abs(material-station))[:24]
        measured.append(vertices[indices].mean(axis=0))
        counts.append(len(indices))
    measured = np.asarray(measured)
    predicted = np.asarray(track.rope(stations, float(sigma)), float)
    errors = np.linalg.norm(measured-predicted, axis=1)
    return dict(sigma_hypothesis_m=float(sigma), max_error_m=float(errors.max()),
                rms_error_m=float(np.sqrt(np.mean(errors**2))),
                stations=[dict(material_s_m=float(s), measured_m=m.tolist(), predicted_m=p.tolist(),
                               error_m=float(e), sampled_vertices=n)
                          for s, m, p, e, n in zip(stations, measured, predicted, errors, counts)],
                scope="passive material-coordinate comparison; geometric progress is a hypothesis, not a task certificate")


def recheck_relay(samples, metadata, *, problem, kin, track, assignment, check_options=None):
    """Recheck cached joint samples against a rebuilt task, never relabel a pass.

    The mount/home, assignment and material-station path must match. Every
    robot sample is checked against the new fixtures and modelled rope; the
    caller separately recertifies the target object's full relay schedule.
    """
    from topogym.utils.io import to_jsonable
    started = time.monotonic()
    if not metadata.get("complete_relay", True):
        raise ValueError("Partial relay probes cannot be reused as complete relay plans")
    if (metadata["assignment"] != assignment or
            to_jsonable(metadata["identity"]["robot_scene"]) != to_jsonable(problem.identity["robot_scene"]) or
            not np.allclose(metadata["home_qpos"], kin.home, atol=1e-9, rtol=0)):
        raise ValueError("Cached relay mount, home or assignment differs")
    check_options = check_options or {}
    if set(check_options)-{"fixture_margin_m", "rope_margin_m", "inter_arm_m", "max_penetration_m"}:
        raise ValueError("Recheck options may only change collision margins")
    options = dict(metadata["options"], **check_options)
    active, checked, failures = set(), [], []
    for index, row in enumerate(samples):
        kind = str(row["phase"]).split(":")[0]
        side = str(row["side"])
        if np.isfinite(row["station"]).all():
            predicted = track.rope([row["station"][3]], row["sigma"])[0]
            if not np.allclose(predicted, row["station"][:3], atol=1e-7, rtol=0):
                raise ValueError(f"Cached material-station path differs at sample {index}")
            if "station_tangent" in row:
                tangent = track.tangent(np.array([row["station"][3]+row["sigma"]]))[0]
                if not np.allclose(tangent, row["station_tangent"], atol=1e-7, rtol=0):
                    raise ValueError(f"Cached material tangent differs at sample {index}")
        if kind == "pinch":
            active.add(side)
        elif kind == "retreat":
            active.discard(side)
        touching = active | ({side} if kind in {"approach", "retreat"} else set())
        kin.set_rope(track.rope(problem.stations_m, row["sigma"]))
        result = kin.check(row["qpos"], holding=touching, margin_m=options["fixture_margin_m"],
                           rope_margin_m=options["rope_margin_m"], inter_arm_m=options["inter_arm_m"],
                           max_penetration_m=options.get("max_penetration_m", 0.))
        checked.append(dict(index=index, phase=str(row["phase"]), **result))
        if not result["passed"]:
            failures.append(checked[-1])
            break
    verified_count = len(checked)-len(failures)
    result = dict(passed=not failures, phases=[], options=options, checks=checked, failures=failures,
                  sample_count=verified_count, wall_time_s=time.monotonic()-started,
                  scope="cached joint samples rechecked against current robot, fixtures and modelled rope; no physics")
    converted = [dict(q=row["qpos"], phase=str(row["phase"]), sigma=float(row["sigma"]))
                 for row in samples[:verified_count]]
    return result, converted


def relay_diagnostics(record, policy):
    world = record["world"]
    grasp = explain_grasp(world.get("grasp"))
    # Full patch indices/offsets already live in owner physics evidence. Keep
    # this diagnostic log small enough to inspect during a running episode.
    for hand in grasp["hands"].values():
        binding = hand["binding"]
        if binding is not None:
            hand["binding"] = dict(target=binding.get("target"), vertex_count=len(binding.get("indices", ())),
                                   acquisition_evidence=binding.get("acquisition_evidence"))
    arms = {}
    for side, (q, p, _, opening) in policy.targets.items():
        actual = record["robot"][side]
        arms[side] = dict(
            joint_error_rad=float(np.max(np.abs(np.asarray(actual["joint_position_rad"])-q))),
            tcp_reference_error_m=float(np.linalg.norm(np.asarray(actual["tcp_position_world_m"])-p)),
            finger_position_m=actual["finger_position_m"], commanded_opening_m=opening)
    station = None
    index = policy.active_index if policy.active_index is not None else 0
    sample = policy.samples[index]
    if np.isfinite(sample["station"]).all():
        material = float(sample["station"][3])
        measured = policy._station_position(world, material)
        reference = np.asarray(sample["station"][:3])
        station = dict(sample_index=index, material_s_m=material, measured_m=measured.tolist(), planned_m=reference.tolist(),
                       error_m=float(np.linalg.norm(measured-reference)))
        limits = np.asarray(world["fem"]["rope"]["material_s_m"])
        tangent = (policy._station_position(world, min(material+.01, limits.max()))
                   -policy._station_position(world, max(material-.01, limits.min())))
        if np.linalg.norm(tangent) > 1e-5:
            tangent /= np.linalg.norm(tangent)
            side = str(sample["side"])
            orientation = np.asarray(record["robot"][side]["tcp_orientation_wxyz"])
            frame = Rotation.from_quat(orientation[[1, 2, 3, 0]])
            station.update(material_tangent_world=tangent.tolist(),
                           material_tangent_tcp=frame.inv().apply(tangent).tolist())
    return dict(arms=arms, station=station, grasp=grasp,
                ipc_native_valid=world.get("ipc", {}).get("native_valid"),
                scope="passive measurements; joint interpolation TCP reference is not an FK certificate")


def replan_held_branch(planner, qpos, side, targets):
    """Re-solve a complete upcoming hold's TCP path on the acquired branch.

    The other arm is checked at each cached parked pose; its retreat remains
    a separate measured calibration. These future checks cover rigid geometry,
    since the future FEM shape is not known. No live scene is changed.
    """
    kin, q = planner.kin, np.asarray(qpos, float).copy()
    moving = kin.robot._q_indices[side][:6]
    other = kin.robot._q_indices["right" if side == "left" else "left"]
    previous_rope = kin.rope
    kin.rope = None
    rows, checks = [], []
    try:
        for target in targets:
            if not str(target["phase"]).startswith("hold:") or target["side"] != side:
                raise ValueError("Branch continuation requires the complete moving-hand hold")
            q[other] = np.asarray(target["qpos"])[other]
            tcp = np.asarray(target["tcp_"+side])
            pose = (tcp[:3], Rotation.from_quat(tcp[3:7][[1, 2, 3, 0]]))
            next_q = kin.solve(side, pose, q, iterations=300)
            if np.max(np.abs(next_q[moving]-q[moving])) > planner.o["max_joint_change_rad"]:
                raise ValueError("Replanned hold changes joint branch")
            segment = []
            q, checked = planner.joint_transit(side, q, next_q, holding={side},
                opening=planner.o["pinch_opening_m"], phase=str(target["phase"]),
                sigma=float(target["sigma"]), record=segment)
            checks += checked
            rows.append(dict(index=int(target["index"]), qpos=q.tolist()))
        return rows, checks
    finally:
        kin.rope = previous_rope


def plan_measured_keeper(kin, problem, world, qpos, sample, *, options=None, normalize_target=None,
                         follow_targets=None, progress=None):
    """Plan a keeper or relay regrasp from measured FEM stations on a ghost robot.

    The rope is a deformable contact object, so this repair permits arm/rope
    contact; rigid fixture, table, self and inter-arm checks remain enabled.
    Callers must pass an independent kinematics scene, never the live robot.
    The returned path contains ordinary joint targets and performs no simulation
    writes. Native grasp admission and health still decide acquisition.
    """
    from topogym.planning.rope_threading.relay_policy import RopeRelayPolicy
    from topogym.planning.rope_threading.relay_ik import RelayPlanner
    from topogym.planning.rope_threading.relay_kinematics import grasp_orientation
    if (str(sample["phase"]).split(":")[0] not in {"transit", "approach"}
            or not np.isfinite(sample["station"]).all()):
        raise ValueError("Measured grasp repair requires an acquisition phase and finite station")
    side, sigma = str(sample["side"]), float(sample["sigma"])
    material = float(sample["station"][3])
    limits = np.asarray(world["fem"]["rope"]["material_s_m"])
    point = RopeRelayPolicy._station_position(world, material)
    tangent = (RopeRelayPolicy._station_position(world, min(material+.01, limits.max()))
               -RopeRelayPolicy._station_position(world, max(material-.01, limits.min())))
    if not np.isfinite(point).all() or np.linalg.norm(tangent) < 1e-5:
        raise ValueError("Degenerate measured keeper station")
    tangent /= np.linalg.norm(tangent)
    planner = RelayPlanner(problem, None, [], {}, options, kin=kin)
    start = np.asarray(qpos, float).copy()
    previous_rope, previous_mode = kin.rope, kin.finger_rope_only
    kin.set_rope(np.array([RopeRelayPolicy._station_position(world, value) for value in problem.stations_m]))
    kin.finger_rope_only = True
    failures = []
    progress = progress or (lambda record: None)
    families = planner.o.get("measured_grasp_families", ("across", "along", "along_lead"))
    rolls = planner.o.get("measured_rolls_deg", (0, -20, 20, -45, 45, -55, 55, -65, 65, -75, 75,
                                               -90, 90, -110, 110, 180, -135, 135))
    if side == "left" and "measured_rolls_deg" not in planner.o:
        # The measured left-hand regrasp already has a native-tested join at
        # -20 degrees. Prefer it before trying to replace a working hold.
        rolls = (-20, *(angle for angle in rolls if angle != -20))
    try:
        if not families or set(families)-{"across", "along", "along_lead"} or not len(rolls) or not np.isfinite(rolls).all():
            raise ValueError("Measured grasp search requires known families and finite roll angles")
        for family in families:
            for degrees in rolls:
                progress(dict(stage="search", family=family, roll_deg=degrees, failed_branches=len(failures)))
                rotation = grasp_orientation(tangent, family, np.deg2rad(degrees))
                position = point-rotation.apply(kin.pad_offset[side])
                pose = (position, rotation)
                pre = (position-rotation.apply([planner.o["approach_m"], 0., 0.]), rotation)
                for branch in planner.branches(side, pose, start):
                    planner.q = start.copy()
                    rows = []
                    try:
                        final = planner.set_fingers(branch, side, planner.o["pinch_opening_m"])
                        result = planner.check(final, {"left", "right"})
                        if not result["passed"]:
                            raise ValueError(planner.issues(result))
                        q_pre = kin.solve(side, pre, branch, iterations=300)
                        q, checks = planner.transit(side, q_pre, holding={"left", "right"}-{side},
                            phase="transit:measured_keeper", sigma=sigma, record=rows)
                        q, approach = planner.cartesian(side, q, pose,
                            steps=max(2, int(np.ceil(planner.o["approach_m"]/planner.o["approach_step_m"]))),
                            holding={"left", "right"}, opening=planner.o["free_opening_m"],
                            phase="approach:measured_keeper", sigma=sigma, record=rows)
                        checks += approach
                        rows.append(dict(q=planner.set_fingers(q, side, planner.o["pinch_opening_m"]),
                                         phase="pinch:measured_keeper", sigma=sigma))
                        normalization_mode = None
                        normalization_pad_deviation_m = None
                        follow_rows, follow_checks = [], []
                        if normalize_target is not None:
                            # Both ends stay held while the keeper raises and
                            # orients the sagged body back towards the planned
                            # configuration. This is actual robot motion after
                            # native admission, never a rope-state write.
                            tcp = np.asarray(normalize_target["tcp_"+side])
                            goal = (tcp[:3], Rotation.from_quat(tcp[3:7][[1, 2, 3, 0]]))
                            steps = max(20, int(np.ceil(np.linalg.norm(goal[0]-position)/.005)))
                            indices = kin.robot._q_indices[side][:6]
                            target_q = np.asarray(normalize_target["qpos"])
                            saved_q, saved_rows = q.copy(), len(rows)
                            try:
                                q, more = planner.cartesian(side, q, goal, steps=steps,
                                    holding={"left", "right"}, opening=planner.o["pinch_opening_m"],
                                    phase="hold:measured_keeper/shape", sigma=sigma, record=rows)
                                difference = float(np.max(np.abs(q[indices]-target_q[indices])))
                                if difference > .15:
                                    if not follow_targets:
                                        raise ValueError(f"Normalization ended on a different replay branch ({difference:.3f} rad)")
                                    follow_rows, follow_checks = replan_held_branch(planner, q, side, follow_targets)
                                    normalization_mode = "cartesian_replanned_hold"
                                else:
                                    normalization_mode = "cartesian"
                            except ValueError as cartesian_error:
                                # A straight TCP interpolation can leave a valid IK
                                # branch near a wrist singularity. A short joint path
                                # to the actual replay branch is another robot motion,
                                # not a state correction. Bound the pad's departure
                                # from the straight grasp-point segment to 15 mm.
                                rows[:] = rows[:saved_rows]
                                joint_span = float(np.max(np.abs(saved_q[indices]-target_q[indices])))
                                if joint_span > 2.:
                                    raise ValueError(f"{cartesian_error}; normalization joint span {joint_span:.3f} rad exceeds 2 rad")
                                q, more = planner.joint_transit(side, saved_q, target_q,
                                    holding={"left", "right"}, opening=planner.o["pinch_opening_m"],
                                    phase="hold:measured_keeper/shape_joint", sigma=sigma, record=rows)
                                end_pad = goal[0]+goal[1].apply(kin.pad_offset[side])
                                segment = end_pad-point
                                deviations = []
                                for row in rows[saved_rows:]:
                                    pad_p, pad_r = kin.tcp_pose(np.asarray(row["q"]), side)
                                    pad = pad_p+pad_r.apply(kin.pad_offset[side])
                                    u = np.clip((pad-point)@segment/max(segment@segment, 1e-12), 0., 1.)
                                    deviations.append(float(np.linalg.norm(pad-(point+u*segment))))
                                normalization_pad_deviation_m = max(deviations, default=0.)
                                if normalization_pad_deviation_m > .015:
                                    raise ValueError(f"{cartesian_error}; normalization pad deviation {normalization_pad_deviation_m:.4f} m exceeds 0.015 m")
                                difference = float(np.max(np.abs(q[indices]-target_q[indices])))
                                normalization_mode = "joint_bounded"
                            checks += more
                        for row in rows:
                            p, r = kin.tcp_pose(np.asarray(row["q"]), side)
                            row.update(tcp=np.r_[p, r.as_quat()[[3, 0, 1, 2]]].tolist())
                        return dict(passed=True, material_s_m=material, point_m=point.tolist(),
                            tangent=tangent.tolist(), family=family, roll_deg=degrees, rows=rows,
                            normalize_after_acquisition=normalize_target is not None,
                            normalization_mode=normalization_mode,
                            normalization_pad_deviation_m=normalization_pad_deviation_m,
                            follow_rows=follow_rows, follow_checks=follow_checks,
                            replanned_hold_count=len(follow_rows),
                            follow_scope="complete upcoming TCP hold; rigid checks with cached other-arm parked poses; future FEM unknown",
                            replay_branch_error_rad=difference if normalize_target is not None else None,
                            checks=checks, failures=failures,
                            scope="measured keeper or relay regrasp; sampled rigid collision and free-finger/rope checks; arm/rope contacts allowed; native grasp required")
                    except ValueError as error:
                        failures.append(dict(family=family, roll_deg=degrees, error=str(error)))
                        progress(dict(stage="rejected", failed_branches=len(failures), **failures[-1]))
        return dict(passed=False, material_s_m=material, point_m=point.tolist(),
                    tangent=tangent.tolist(), failures=failures)
    finally:
        kin.rope, kin.finger_rope_only = previous_rope, previous_mode


def plan_keeper_retreat(kin, problem, qpos, side, target, *, options=None):
    """Retract the released helper and reconnect to the planned parked pose."""
    from topogym.planning.rope_threading.relay_ik import RelayPlanner
    planner = RelayPlanner(problem, None, [], {}, options, kin=kin)
    start = np.asarray(qpos, float).copy()
    sigma = float(target["sigma"])
    p, r = kin.tcp_pose(start, side)
    saved_rope, kin.rope = kin.rope, None
    failures = []
    try:
        for name, direction in (("tool", -r.apply([1., 0., 0.])), ("up", np.array([0., 0., 1.]))):
            planner.q, rows = start.copy(), []
            try:
                q, checks = planner.cartesian(side, start, (p+.06*direction, r), steps=12,
                    holding={"left", "right"}, opening=planner.o["free_opening_m"],
                    phase="retreat:measured_keeper/"+name, sigma=sigma, record=rows)
                planner.q = q
                goal = q.copy()
                indices = kin.robot._q_indices[side]
                goal[indices] = np.asarray(target["qpos"])[indices]
                _, more = planner.transit(side, goal, holding={"left", "right"},
                    phase="park:measured_keeper", sigma=sigma, record=rows)
                checks += more
                for row in rows:
                    position, rotation = kin.tcp_pose(np.asarray(row["q"]), side)
                    row["tcp"] = np.r_[position, rotation.as_quat()[[3, 0, 1, 2]]].tolist()
                return dict(passed=True, rows=rows, checks=checks, failures=failures,
                    scope="measured helper release and park; sampled rigid collision checks; deformable arm/rope contacts allowed")
            except ValueError as error:
                failures.append(dict(direction=name, error=str(error)))
        return dict(passed=False, failures=failures)
    finally:
        kin.rope = saved_rope


class MeasuredKeeperPlanner:
    """CPU ghost-scene repairs with saved inputs; never mutates the CUDA scene."""
    def __init__(self, output, metadata, *, normalize=False):
        from pathlib import Path
        self.output, self.metadata = Path(output), metadata
        self.count = 0
        self.normalize = normalize

    def __call__(self, obs, sample, targets, *, retreat_target=None, normalize_target=None, follow_targets=None):
        import json
        import subprocess
        import sys
        from topogym.utils.io import write_json_atomic
        directory = self.output/f"keeper_{self.count:02d}"
        self.count += 1
        directory.mkdir(parents=True, exist_ok=False)
        q = np.asarray(self.metadata["home_qpos"]).copy()
        for side, offset in (("left", 0), ("right", 8)):
            # Start at the last commanded configuration and preserve the other
            # arm's hold. Measured joints are saved separately for review.
            q[offset:offset+6] = targets[side][0]
            q[offset+6:offset+8] = targets[side][3]
        def pose_record(row, *, station=False):
            if row is None:
                return None
            # Transit/retreat caches use NaN material markers. They are not
            # measurements and cannot enter strict JSON; retreat needs poses.
            keys = ["phase", "side", "sigma", "qpos", "tcp_left", "tcp_right"]
            if station:
                keys.append("station")
            return {key: row[key] for key in keys}
        payload = dict(metadata=self.metadata, qpos=q, sample=pose_record(sample, station=retreat_target is None),
            retreat_target=pose_record(retreat_target), measured_robot=obs["robot"],
            normalize_target=pose_record(normalize_target) if self.normalize else None,
            follow_targets=[dict(pose_record(row), index=int(row["index"])) for row in (follow_targets or [])],
            world=dict(fem=dict(rope=obs["privileged"]["world"]["fem"]["rope"])))
        write_json_atomic(directory/"input.json", payload)
        with (directory/"planner.log").open("w") as log:
            result = subprocess.run([sys.executable, "-m", __name__, str(directory)], stdout=log, stderr=log)
        if result.returncode:
            raise RuntimeError(f"Measured keeper planner failed; see {directory/'planner.log'}")
        report = json.loads((directory/"result.json").read_text())
        report["evidence"] = str(directory)
        return report


def _repair_worker(directory):
    import json
    from pathlib import Path
    from topogym.planning.rope_threading.geometry import frozen_problem
    from topogym.planning.rope_threading.relay_kinematics import RopeThreadingKinematics
    from topogym.utils.io import write_json_atomic
    directory = Path(directory)
    payload = json.loads((directory/"input.json").read_text())
    metadata = payload["metadata"]
    identity = metadata["identity"]
    problem = frozen_problem(directory/"geometry", variation=identity["variation_id"],
        seed=identity["seed"], task_parameters=identity.get("task_parameters"))
    kin = RopeThreadingKinematics(problem)
    if payload["retreat_target"] is None:
        result = plan_measured_keeper(kin, problem, payload["world"], payload["qpos"],
            payload["sample"], options=metadata["options"], normalize_target=payload.get("normalize_target"),
            follow_targets=payload.get("follow_targets"),
            progress=lambda record: write_json_atomic(directory/"progress.json", record))
    else:
        result = plan_keeper_retreat(kin, problem, payload["qpos"], payload["sample"]["side"],
            payload["retreat_target"], options=metadata["options"])
    write_json_atomic(directory/"result.json", result)


if __name__ == "__main__":
    import sys
    _repair_worker(sys.argv[1])
