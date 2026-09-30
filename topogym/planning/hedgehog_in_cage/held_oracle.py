"""Owner-side route search using a measured grasp and measured finger state."""
import numpy as np
import trimesh
from pathlib import Path
from scipy.spatial.transform import Rotation

from topogym.planning.rigid_reference.feedback import body_pose, relative_pose
from topogym.planning.rigid_reference.geometry import (
    RigidPathChecker, combine_meshes, interpolate, matrix, pose_dict,
)
from topogym.planning.rigid_reference.rrt import connect_search
from topogym.planning.rigid_reference.search import check_path
from .kinematics import HedgehogIK
from .object_oracle import frozen_problem, shorten
from topogym.utils.io import write_json_atomic


class HeldPathChecker(RigidPathChecker):
    """Certify ball and attached tool separately with their true motion radii.

    Both follow the same rigid pose. Taking the smaller of their certified
    bounds covers the full union without using a distant wrist's radius to
    bound the ball's motion next to a narrow bar.
    """
    def __init__(self, fixed, ball, tool, *, margin_m):
        super().__init__(fixed, combine_meshes([ball, tool]), margin_m=margin_m)
        self.parts = [RigidPathChecker(fixed, mesh, margin_m=margin_m) for mesh in (ball, tool)]

    def edge(self, start, end):
        results = []
        for index, checker in enumerate(self.parts):
            result = checker.edge(start, end)
            self.queries += result["queries"]
            results.append(result)
            if not result["passed"]:
                return dict(result, held_component="ball" if index == 0 else "tool")
        return dict(passed=True,
            clearance_lower_bound_m=min(row["clearance_lower_bound_m"] for row in results),
            leaves=sum(row["leaves"] for row in results), queries=sum(row["queries"] for row in results),
            distance_error_m=self.error, components=results,
            coverage="bounded motion of every ball and rigid tool surface; other arm links checked by IK")


def plan_held_path(env, output, *, random_seed=0, iterations=30000, clearance_m=.0005,
                   measured_state=None, wrist_envelope=True, max_turn_deg=110., grip_point_in_ball=None):
    """No state mutation: a sampled robot path plus a continuous rigid envelope.

    The envelope freezes the measured passive fingers and object/tool relation.
    Actual execution must monitor both and reject drift or forbidden contacts.
    """
    variation = env._task.variation_id.removeprefix("hedgehog_in_cage_")
    task, ball, fixed, frame, _, report = frozen_problem(output, seed=env._task.seed, variation=variation)
    if task.instance_id != env._task.instance_id:
        raise ValueError("Planning geometry differs from the live instance")
    kin = HedgehogIK(env, measured_state=measured_state)
    bp, br = kin.ball_pose
    start = relative_pose(frame, (bp, br))
    fk = kin.fk.solve(kin.seed)
    ps = np.asarray(fk["position_world_m"]).reshape(-1, 3)
    rs = Rotation.from_quat(np.asarray(fk["orientation_wxyz"]).reshape(-1, 4)[:, [1, 2, 3, 0]])
    hand = kin.robot.entity.get_link(kin.group.hand_link).idx_local
    hand_in_ball = relative_pose((bp, br), (ps[hand], rs[hand]))
    held = [ball]
    for index, mesh in kin.local_meshes:
        if index < 7:
            continue
        mesh = mesh.copy()
        mesh.apply_transform(matrix(br.inv().apply(ps[index]-bp), br.inv()*rs[index]))
        held.append(mesh)
    if wrist_envelope:
        # link7 is rigid to the tool. link6 varies only by joint7 rotation
        # about the common hand z axis. A circumscribed cylinder bounds every
        # joint7 angle, so its validity does not depend on an IK branch.
        axis_offset = rs[hand].inv().apply(ps[7]-ps[hand])
        if np.linalg.norm(axis_offset[:2]) > 1e-6:
            raise ValueError("Panda joint7 and hand axes are no longer coaxial")
        vertices = np.vstack([rs[hand].inv().apply(ps[index]+rs[index].apply(mesh.vertices)-ps[hand])
                              for index, mesh in kin.local_meshes if index == 6])
        radius = float(np.linalg.norm(vertices[:, :2], axis=1).max())
        lower_z, upper_z = vertices[:, 2].min(), vertices[:, 2].max()
        envelope = trimesh.creation.cylinder(radius=radius/np.cos(np.pi/64),
                                              height=upper_z-lower_z, sections=64)
        envelope.apply_translation([0., 0., (lower_z+upper_z)/2])
        envelope.apply_transform(matrix(*hand_in_ball))
        held.append(envelope)
    compound = combine_meshes(held)
    def make_checker(margin):
        return (HeldPathChecker(fixed, ball, combine_meshes(held[1:]), margin_m=margin)
                if variation == "easy" else RigidPathChecker(fixed, compound, margin_m=margin))
    checker = make_checker(clearance_m)
    region = env._task.goal_region
    goal_world = np.r_[region.center_xy_m, region.table_height_m+region.placement_height_m/2]
    goal = (frame[1].inv().apply(goal_world-frame[0]), start[1])
    report.update(status="held_search", physical_execution_verified=False,
                  grasp=pose_dict(hand_in_ball), passive_qpos=kin.seed[7:].tolist(),
                  start=pose_dict(start), goal=pose_dict(goal),
                  wrist_envelope=wrist_envelope, max_turn_deg=max_turn_deg,
                  offline_measured_state=measured_state is not None)
    departure = None
    if variation != "medium" and checker.clearance(start) <= max(clearance_m, .001 if variation == "easy" else 0.)+checker.error:
        # A just-acquired grasp can be close to a bar. Certify its departure
        # separately instead of silently dropping the transport clearance.
        entry = make_checker(.00005)
        from .variant_oracle import initial_free
        if not initial_free(entry, start):
            report.update(status="held_endpoint_invalid", endpoint="start",
                          clearance_m=checker.clearance(start))
            return report
        rng_entry = np.random.default_rng(random_seed+701)
        options = []
        for _ in range(2000 if variation == "easy" else 1200):
            offset = (rng_entry.uniform([-.012, -.012, .004], [.012, .012, .035])
                      if variation == "easy" else rng_entry.uniform(-.006, .006, 3))
            pose = (start[0]+offset,
                    Rotation.from_rotvec(rng_entry.normal(0., .08 if variation == "easy" else .045, 3))*start[1])
            gap = checker.clearance(pose)
            if gap > clearance_m+.0003:
                motion = np.linalg.norm(pose[0]-start[0])+checker.radius*(pose[1]*start[1].inv()).magnitude()
                priority = -offset[2]+motion*.01 if variation == "easy" else motion
                options.append((priority, pose, gap))
        for _, pose, gap in sorted(options, key=lambda item: item[0]):
            certificate = entry.edge(start, pose)
            if certificate["passed"]:
                departure = start
                report["departure_certificate"] = dict(certificate, start=pose_dict(start),
                    end=pose_dict(pose), end_clearance_m=gap, margin_m=entry.margin)
                start = pose
                break
        if departure is None:
            report.update(status="no_certified_departure", candidates=len(options))
            return report
    for name, pose in (("start", start), ("goal", goal)):
        if variation == "medium":
            free = checker.initial_free(pose)
        else:
            from .variant_oracle import initial_free
            free = initial_free(checker, pose)
        if not free:
            report.update(status="held_endpoint_invalid", endpoint=name,
                          clearance_m=checker.clearance(pose))
            return report
    rng = np.random.default_rng(random_seed)
    lower = np.array([-.05, goal[0][1], -.075])
    upper = np.array([.05, .02, .045])
    hints = []
    if variation != "medium":
        from .variant_oracle import reference_route
        hints, _ = reference_route(variation)
        lower = np.array([-.08, goal[0][1]-.03, -.08])
        upper = np.array([.24, .12, .25 if variation == "hard" else .14])
    if variation == "easy":
        # The imported CLASSIC hints grip the opposite spike. Generate and
        # validate exit configurations for this measured grasp before using
        # them as a sampling bias. These are not accepted path edges.
        exit_hints = []
        from topogym.assets.geometry.hedgehog_in_cage import HedgehogLayout, load_template
        layout = HedgehogLayout(load_template(), scale=float(task.config["scale"]))
        cage = layout.template["cage"]
        gate_angles = np.deg2rad(cage["window_centers_deg"])
        gate_widths = np.asarray(cage["window_widths"])*layout.unit
        inner_radius = (cage["outer_diameter"]/2-cage["wall_thickness"])*layout.unit
        if grip_point_in_ball is None:
            directions = np.array([end/np.linalg.norm(end)
                for _, end in layout.spike_segments()])
            grip_axis = directions[np.argmax(directions@hand_in_ball[0])]
        else:
            grip_axis = np.asarray(grip_point_in_ball, float)
            if grip_axis.shape != (3,) or not np.isfinite(grip_axis).all() or np.linalg.norm(grip_axis) < 1e-6:
                raise ValueError("A finite nonzero grasp point is required")
            grip_axis = grip_axis/np.linalg.norm(grip_axis)
        grasp_basis = Rotation.align_vectors([[1., 0., 0.]], [grip_axis])[0]
        report["sampling_grip_axis_ball"] = grip_axis.tolist()
        lower[0], upper[1] = -.24, .24
        toward_hand = start[1].apply(grip_axis)
        gate_angle = np.arctan2(toward_hand[1], toward_hand[0])
        gate_angle = np.deg2rad(72.*round(np.rad2deg(gate_angle)/72.))
        counts = [0]*len(gate_angles)
        for attempt in range(50000):
            gate_index = attempt % len(gate_angles)
            if all(count >= 16 for count in counts):
                break
            if counts[gate_index] >= 16:
                continue
            angle, width = gate_angles[gate_index], gate_widths[gate_index]
            radial = np.sqrt(inner_radius**2-(width/2)**2)
            tangent = rng.uniform(-.0004, .0004)
            p = np.array([radial*np.cos(angle)-tangent*np.sin(angle),
                          radial*np.sin(angle)+tangent*np.cos(angle), rng.uniform(-.045, .045)])
            if rng.random() < .3:
                orientation = Rotation.random(random_state=rng)
            else:
                hand_angle = gate_angle if rng.random() < .65 else angle
                orientation = (Rotation.from_euler("z", hand_angle+rng.normal(0., .3))
                               *Rotation.from_euler("y", rng.uniform(-1.4, 1.2))
                               *Rotation.from_euler("x", rng.uniform(-np.pi, np.pi))*grasp_basis)
            pose = (p, orientation)
            if checker.clearance(pose) > clearance_m+checker.error:
                exit_hints.append(pose)
                counts[gate_index] += 1
            if attempt % 1000 == 0:
                write_json_atomic(Path(output)/"search_progress.json", dict(
                    stage="all_window_pose_candidates", attempts=attempt, accepted_per_window=counts))
        if exit_hints:
            hints = exit_hints
        report["exit_sampling_hints"] = [pose_dict(p) for p in exit_hints]
        report["grasp_window_angle_deg"] = float(np.rad2deg(gate_angle))
        report["exit_candidates_per_window"] = dict(zip(map(str, cage["window_centers_deg"]), counts))
    def sample(rng):
        if variation == "easy" and rng.random() < .55:
            # The core can use a different window from the acquired spike.
            # Keep both choices in the proposal; the full compound decides.
            core_angle = float(rng.choice(gate_angles))
            radial = rng.uniform(-.012, .085)
            tangent = rng.uniform(-.002, .002)
            position = np.array([radial*np.cos(core_angle)-tangent*np.sin(core_angle),
                                 radial*np.sin(core_angle)+tangent*np.cos(core_angle),
                                 rng.uniform(-.055, .055)])
            orientation = (Rotation.from_euler("z", gate_angle+rng.normal(0., .22))
                           *Rotation.from_euler("y", rng.uniform(-1.2, .8))
                           *Rotation.from_euler("x", rng.uniform(-np.pi, np.pi))*grasp_basis)
            return position, orientation
        if hints and rng.random() < .65:
            position, orientation = hints[int(rng.integers(len(hints)))]
            if variation == "easy":
                local = rng.normal(0., [.015, .0004, .012])
                offset = Rotation.from_euler("z", np.arctan2(position[1], position[0])).apply(local)
                return (np.clip(position+offset, lower, upper),
                        Rotation.from_rotvec(rng.normal(0., .08, 3))*orientation)
            return (np.clip(position+rng.normal(0., .018, 3), lower, upper),
                    Rotation.from_rotvec(rng.normal(0., .25, 3))*orientation)
        axis = rng.normal(size=3)
        turn = Rotation.from_rotvec(axis/np.linalg.norm(axis)*rng.uniform(0., np.deg2rad(max_turn_deg)))
        return rng.uniform(lower, upper), turn*start[1]
    write_json_atomic(Path(output)/"search_setup.json", report)
    path, evidence = None, dict(connected=False, stages=[])
    if variation == "easy" and hints:
        ranked = sorted(hints, key=lambda pose: -checker.clearance(pose))
        # Each portal lies on the actual inner-wall throat. A whole-space
        # goal tree otherwise spends most of its nodes outside this passage.
        def portal_sample(rng):
            if rng.random() < .8:
                portal = ranked[int(rng.integers(len(ranked)))]
                p, r = interpolate(start, portal, rng.uniform(0., 1.))
                local = rng.normal(0., [.012, .001, .015])
                core_angle = np.arctan2(portal[0][1], portal[0][0])
                return (p+Rotation.from_euler("z", core_angle).apply(local),
                        Rotation.from_rotvec(rng.normal(0., .12, 3))*r)
            return sample(rng)
        def local_sample(rng, pose):
            p, r = pose
            axis = np.eye(3)[int(rng.integers(3))]
            if rng.random() < .5:
                return p+axis*rng.normal(0., .003), r
            return p, Rotation.from_rotvec(axis*rng.normal(0., .035))*r
        prefix, first = connect_search(checker, start, ranked[0], portal_sample, rng=rng,
            iterations=max(1, 3*iterations//5), step_m=.004, metric_radius_m=.09,
            goal_candidates=ranked, local_sample=local_sample,
            progress=lambda data: write_json_atomic(Path(output)/"search_progress.json",
                dict(stage="inside_to_any_throat", portals=len(ranked), **data)))
        evidence["stages"].append(dict(phase="inside_to_any_throat", **first))
        if prefix is not None:
            portal = prefix[-1]
            write_json_atomic(Path(output)/"selected_portal_prefix.json", dict(
                poses=[pose_dict(p) for p in prefix], search=first, physical_execution_verified=False))
            suffix, second = connect_search(checker, portal, goal, sample, rng=rng,
                iterations=max(1, 2*iterations//5), step_m=.004, metric_radius_m=.09,
                local_sample=local_sample,
                progress=lambda data: write_json_atomic(Path(output)/"search_progress.json",
                    dict(stage="throat_to_goal", **data)))
            evidence["stages"].append(dict(phase="throat_to_goal", **second))
            if suffix is not None:
                path, evidence["connected"] = prefix+suffix[1:], True
    else:
        path, evidence = connect_search(checker, start, goal, sample, rng=rng,
            iterations=iterations, step_m=.015,
            progress=lambda data: write_json_atomic(Path(output)/"search_progress.json", data))
    report["search"] = evidence
    if path is None:
        report["status"] = "no_held_path_in_finite_search"
        return report
    path = shorten(checker, path)
    certificate = check_path(checker, path)
    if departure is not None:
        path = [departure, *path]
    report.update(poses=[pose_dict(p) for p in path], certificate=certificate)
    q, rows = kin.seed.copy(), []
    limits = np.asarray(kin.group.arm_limits_rad)
    for edge_index, (a, b) in enumerate(zip(path, path[1:])):
        robot_margin = .00005 if departure is not None and edge_index == 0 else clearance_m
        count = max(1, int(np.ceil((np.linalg.norm(b[0]-a[0])
                         + checker.radius*(b[1]*a[1].inv()).magnitude())/.001)))
        for u in np.linspace(0, 1, count+1)[1:]:
            p, r = interpolate(a, b, u)
            wp, wr = frame[0]+frame[1].apply(p), frame[1]*r
            hp, hr = wp+wr.apply(hand_in_ball[0]), wr*hand_in_ball[1]
            tcp = hp+hr.apply(kin.group.tcp_position_in_hand_m)
            try:
                next_q = kin.solve((tcp, hr), q)
            except ValueError as error:
                report.update(status="held_ik_rejected", reason=str(error), rows=rows)
                return report
            gaps = kin.gaps(next_q, (wp, wr))
            margin = float(np.minimum(next_q[:7]-limits[:, 0], limits[:, 1]-next_q[:7]).min())
            step = float(np.max(np.abs(next_q[:7]-q[:7])))
            if min(gaps.values()) < robot_margin or margin < .01 or step > .1:
                report.update(status="held_robot_collision_or_limit", gaps=gaps,
                              joint_margin_rad=margin, joint_step_rad=step, rows=rows)
                return report
            rows.append(dict(qpos=next_q.tolist(), body=pose_dict((wp, wr)), gaps=gaps,
                             joint_margin_rad=margin, joint_step_rad=step))
            q = next_q
    report.update(status="measured_held_ik_path_found", rows=rows,
                  sampled_material_step_m=.001, physical_execution_verified=False)
    return report
