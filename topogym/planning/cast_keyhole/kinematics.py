"""Owner-side coupled IK planning through read-only native Genesis FK queries.

The relative puzzle path is fixed; its common world orientation is free. This
avoids treating the old robot-specific world poses as geometric constraints.
The resulting poses are still only candidates until actual policy execution.
"""
import numpy as np
from scipy.optimize import least_squares
from scipy.spatial.transform import Rotation, Slerp

from topogym.solvers.genesis_kinematics import GenesisFKSolver
from topogym.utils.arrays import to_numpy
from .policy import PARTS, ASSEMBLY_ROTATIONS, rotation


def audit_coupled_plan(robot, entities, body_origins, plan, table_height, *, check_piece_separation=False,
                       assembly_transforms=None, check_own_piece=False):
    """Sample native collision geometry, including both cameras and fingers."""
    import trimesh
    from .policy import canonical_offsets
    from topogym.planning.rigid_reference.geometry import matrix
    fk = GenesisFKSolver(robot.entity)
    seed = to_numpy(robot.entity.get_qpos()).reshape(-1).copy()
    origins = canonical_offsets(body_origins)
    assembly_rotations = ASSEMBLY_ROTATIONS
    if assembly_transforms is not None:
        assembly_rotations = {s: Rotation.from_matrix(assembly_transforms[n][:3, :3])
                              for s, n in (("left", "gold"), ("right", "silver"))}
        origins = {s: assembly_rotations[s].inv().apply(
            np.asarray(body_origins[PARTS[s]])-assembly_transforms[n][:3, 3])
            for s, n in (("left", "gold"), ("right", "silver"))}
    managers = {name: trimesh.collision.CollisionManager() for name in [*PARTS, *PARTS.values()]}
    geometry = []
    for side in PARTS:
        for link in robot.entity.links:
            if not link.name.startswith(side+"/"):
                continue
            for index, geom in enumerate(link.geoms):
                mesh = geom.mesh.trimesh.copy()
                mesh.apply_transform(matrix(geom.init_pos, rotation(geom.init_quat)))
                name = f"{link.name}/{index}"
                managers[side].add_object(name, mesh)
                check_table = link.name.rsplit("/", 1)[-1] not in {"base_link", "waist_link", "shoulder_link"}
                geometry.append((side, name, link.idx_local, mesh.vertices.copy(), check_table))
        name = PARTS[side]
        if len(entities[name].links) != 1:
            raise ValueError("Route audit requires the frozen single-link pieces")
        for index, geom in enumerate(entities[name].links[0].geoms):
            mesh = geom.mesh.trimesh.copy()
            mesh.apply_transform(matrix(geom.init_pos, rotation(geom.init_quat)))
            managers[name].add_object(str(index), mesh)
    issues, minimum = [], float("inf")
    for index, frame in enumerate(plan["frames"]):
        q = seed.copy()
        for side in PARTS:
            q[robot._q_indices[side][:6]] = frame["joint_position_rad"][side]
            if "finger_position_m" in frame:
                q[robot._q_indices[side][6:]] = frame["finger_position_m"][side]
        pose = fk.solve(q)
        pp = np.asarray(pose["position_world_m"]).reshape(-1, 3)
        rr = np.asarray(pose["orientation_wxyz"]).reshape(-1, 4)
        gap = float("inf")
        for side, name, link, vertices, check_table in geometry:
            r = rotation(rr[link])
            managers[side].set_transform(name, matrix(pp[link], r))
            if check_table:
                gap = min(gap, float((r.apply(vertices)+pp[link])[:, 2].min()-table_height))
        minimum = min(minimum, gap)
        for side, name in PARTS.items():
            body = frame["bodies"][side]
            r = rotation(body["quaternion_wxyz"])
            transform = matrix(np.asarray(body["position_m"])+r.apply(origins[side]),
                               r*assembly_rotations[side].inv())
            for object_name in managers[name]._objs:
                managers[name].set_transform(object_name, transform)
        hits = {}
        pairs_to_check = [("left", "right"), ("left", PARTS["right"]), ("right", PARTS["left"])]
        if check_own_piece:
            pairs_to_check.extend((s, PARTS[s]) for s in PARTS)
        for a, b in pairs_to_check:
            collided, pairs = managers[a].in_collision_other(managers[b], return_names=True)
            if collided:
                hits[a+"__"+b] = sorted(pairs)
        if check_piece_separation:
            collided, pairs = managers[PARTS["left"]].in_collision_other(managers[PARTS["right"]], return_names=True)
            if collided:
                hits["gold__silver"] = sorted(pairs)
        if hits or gap < .002:
            issues.append(dict(frame=index, stage=frame["stage"], table_clearance_m=gap, collisions=hits))
    return dict(passed=not issues, scope="sampled native collision meshes; no physical or continuous-path success claim",
                frames=len(plan["frames"]), minimum_table_clearance_m=minimum, issues=issues)


def preflight_simplified_pickup(robot, entities, body_origins, geometry, policy, table_height):
    """Read-only IK/FK for home orientation, approach and open-finger descent.

    No candidate joints are installed. Actual acquisition and later extraction
    remain separate physical tests. Own-piece collisions are included here.
    """
    from topogym.solvers.genesis_kinematics import GenesisIKSolver
    from topogym.assets.geometry.cast_keyhole import plate_assembly_transforms
    ik = GenesisIKSolver(robot.entity)
    q = to_numpy(robot.entity.get_qpos()).reshape(-1).copy()
    for side in PARTS:
        q[robot._q_indices[side][6:]] = .027
    initial, bodies = policy.tcp(), policy.bodies()
    targets = policy.pickup_waypoints()
    frames, failure, minimum_margin = [], None, float("inf")
    try:
        for stage, _, target in targets:
            turns = {s: Slerp([0, 1], Rotation.from_quat([initial[s][1].as_quat(), r.as_quat()]))
                     for s, (_, r) in target.items()}
            for u in np.linspace(0., 1., 41):
                for side, (p, _) in target.items():
                    group = robot.groups[side]
                    tcp_p = initial[side][0]+u*(p-initial[side][0])
                    hand_r = turns[side](u)*rotation(group.tcp_orientation_in_hand_wxyz).inv()
                    q = ik.solve_checked(link_name=group.hand_link,
                        position_world_m=tcp_p-hand_r.apply(group.tcp_position_in_hand_m),
                        orientation_wxyz=hand_r.as_quat()[[3, 0, 1, 2]], initial_qpos=q,
                        joint_dof_indices=robot._indices[side][:6])
                    joints = q[robot._q_indices[side][:6]]
                    limits = np.asarray(group.arm_limits_rad)
                    margin = float(min(np.min(joints-limits[:, 0]), np.min(limits[:, 1]-joints)))
                    minimum_margin = min(minimum_margin, margin)
                    if margin < .01:
                        raise ValueError("Pickup candidate has less than 0.01 rad joint margin")
                frames.append(dict(stage=stage, fraction=float(u),
                    bodies={s: dict(position_m=p.tolist(), quaternion_wxyz=r.as_quat()[[3, 0, 1, 2]].tolist())
                            for s, (p, r) in bodies.items()},
                    joint_position_rad={s: q[robot._q_indices[s][:6]].tolist() for s in PARTS},
                    finger_position_m={s: q[robot._q_indices[s][6:]].tolist() for s in PARTS}))
            initial = target
    except ValueError as error:
        failure = dict(stage=stage, side=side, fraction=float(u), error=str(error))
    audit = audit_coupled_plan(robot, entities, body_origins, dict(frames=frames), table_height,
        assembly_transforms=plate_assembly_transforms(geometry), check_own_piece=True) if frames else None
    return dict(passed=failure is None and audit is not None and audit["passed"],
        scope="sampled native IK and full meshes through open-finger approach; no physical grasp or solve claim",
        physics_steps=0, failure=failure, collision_audit=audit,
        minimum_joint_margin_rad=minimum_margin if np.isfinite(minimum_margin) else None, frames=frames)


def plan_goal_transfer(robot, entities, body_origins, route_plan, grasp_offsets, policy, table_height):
    """Preflight the same goal transfer used by the passive EE policy."""
    from topogym.solvers.genesis_kinematics import GenesisIKSolver
    from .policy import placement_targets
    ik = GenesisIKSolver(robot.entity)
    last = route_plan["frames"][-1]
    q = to_numpy(robot.entity.get_qpos()).reshape(-1).copy()
    bodies = {s: (np.asarray(b["position_m"]), rotation(b["quaternion_wxyz"])) for s, b in last["bodies"].items()}
    for side in PARTS:
        q[robot._q_indices[side][:6]] = last["joint_position_rad"][side]
    frames, failure, minimum_margin = [], None, float("inf")
    try:
        for stage, duration, target in placement_targets(bodies, grasp_offsets, policy.vertices,
                policy.region, variation=policy.reference["variation_id"]):
            turns = {s: Slerp([0, 1], Rotation.from_quat([bodies[s][1].as_quat(), target[s][1].as_quat()])) for s in PARTS}
            for fraction in np.linspace(0., 1., 61)[1:]:
                poses = {s: (bodies[s][0]+fraction*(target[s][0]-bodies[s][0]), turns[s](fraction)) for s in PARTS}
                for side, (p, r) in poses.items():
                    group = robot.groups[side]
                    offset_p, offset_r = grasp_offsets[side]
                    tcp_p, tcp_r = p+r.apply(offset_p), r*offset_r
                    hand_r = tcp_r*rotation(group.tcp_orientation_in_hand_wxyz).inv()
                    q = ik.solve_checked(link_name=group.hand_link,
                        position_world_m=tcp_p-hand_r.apply(group.tcp_position_in_hand_m),
                        orientation_wxyz=hand_r.as_quat()[[3, 0, 1, 2]], initial_qpos=q,
                        joint_dof_indices=robot._indices[side][:6])
                    limits = np.asarray(group.arm_limits_rad)
                    joints = q[robot._q_indices[side][:6]]
                    margin = float(min(np.min(joints-limits[:, 0]), np.min(limits[:, 1]-joints)))
                    minimum_margin = min(minimum_margin, margin)
                    if margin < .03:
                        raise ValueError("Goal transfer has less than 0.03 rad joint margin")
                frames.append(dict(stage=stage, duration_s=duration/60.,
                    bodies={s: dict(position_m=p.tolist(), quaternion_wxyz=r.as_quat()[[3, 0, 1, 2]].tolist())
                            for s, (p, r) in poses.items()},
                    joint_position_rad={s: q[robot._q_indices[s][:6]].tolist() for s in PARTS}))
            bodies = target
    except ValueError as error:
        failure = dict(stage=stage, fraction=float(fraction), error=str(error))
    audit = audit_coupled_plan(robot, entities, body_origins, dict(frames=frames), table_height,
                              check_piece_separation=True) if frames else None
    return dict(scope="sampled native goal-transfer candidate; actual EE execution still required", physics_steps=0,
                passed=failure is None and audit is not None and audit["passed"],
                failure=failure, minimum_joint_margin_rad=minimum_margin if np.isfinite(minimum_margin) else None,
                collision_audit=audit, frames=frames)


def simplify_relative_samples(samples, tolerance_m=.00004, radius_m=.15):
    """Remove observed jitter, bounding every omitted sample's pose error.

    This is a sampled approximation bound, not a free-space certificate for
    the contact path. Physical execution and Task guards remain necessary.
    """
    if tolerance_m <= 0 or radius_m <= 0:
        raise ValueError("Positive path approximation bounds are required")
    if len(samples) < 3:
        return list(samples)
    keep, pending = {0, len(samples)-1}, [(0, len(samples)-1)]
    while pending:
        lo, hi = pending.pop()
        a, b = samples[lo], samples[hi]
        angular = (b[1]*a[1].inv()).as_rotvec()
        chord = np.r_[b[0]-a[0], radius_m*angular]
        denominator = float(chord@chord)
        worst, split = 0., None
        for i in range(lo+1, hi):
            p, r = samples[i]
            delta = np.r_[p-a[0], radius_m*(r*a[1].inv()).as_rotvec()]
            u = float(np.clip(delta@chord/denominator, 0., 1.)) if denominator > 1e-20 else 0.
            predicted_r = Rotation.from_rotvec(u*angular)*a[1]
            error = float(np.linalg.norm(p-(a[0]+u*(b[0]-a[0])))
                          + radius_m*(r*predicted_r.inv()).magnitude())
            if error > worst:
                worst, split = error, i
        if worst > tolerance_m:
            keep.add(split)
            pending.extend(((lo, split), (split, hi)))
    return [samples[i] for i in sorted(keep)]


def plan_regrasp(robot, entities, body_origins, bodies, side, table_height, *,
                 seed_qpos=None, tcp_observation=None, joint_transit=False):
    """Sample the actual hanging pose; never move an engine body or robot.

    Dense native IK and sampled full collision meshes qualify a candidate
    approach, not a successful physical acquisition.
    """
    import trimesh
    from itertools import product
    from .policy import REGRASP_POINTS, PAD_TO_TCP, canonical_offsets
    from topogym.solvers.genesis_kinematics import GenesisIKSolver
    from topogym.planning.rigid_reference.geometry import matrix
    ik, fk = GenesisIKSolver(robot.entity), GenesisFKSolver(robot.entity)
    initial_q = (to_numpy(robot.entity.get_qpos()).reshape(-1).copy() if seed_qpos is None
                 else np.asarray(seed_qpos, dtype=float).copy())
    if initial_q.shape != (int(robot.entity.n_qs),):
        raise ValueError("One complete robot qpos is required")
    observed = robot.observe() if tcp_observation is None else tcp_observation
    initial = (np.asarray(observed[side]["tcp_position_world_m"]),
               rotation(observed[side]["tcp_orientation_wxyz"]))
    origins = canonical_offsets(body_origins)
    body = bodies[PARTS[side]]
    br = rotation(body["quaternion_wxyz"])*ASSEMBLY_ROTATIONS[side]
    bp = np.asarray(body["position_m"])-br.apply(origins[side])
    base = (Rotation.from_matrix([[0, 0, 1], [1, 0, 0], [0, 1, 0]]) if side == "left"
            else Rotation.from_matrix([[0, 0, -1], [-1, 0, 0], [0, 1, 0]]))
    managers = {s: trimesh.collision.CollisionManager() for s in PARTS}
    geometry = []
    for s in PARTS:
        for link in robot.entity.links:
            if not link.name.startswith(s+"/"):
                continue
            for index, geom in enumerate(link.geoms):
                mesh = geom.mesh.trimesh.copy()
                mesh.apply_transform(matrix(geom.init_pos, rotation(geom.init_quat)))
                name = f"{link.name}/{index}"
                managers[s].add_object(name, mesh)
                check_table = s == side and link.name.rsplit("/", 1)[-1] not in {
                    "base_link", "waist_link", "shoulder_link"}
                geometry.append((s, name, link.idx_local, mesh.vertices.copy(), check_table))
    pieces = trimesh.collision.CollisionManager()
    for name in PARTS.values():
        pose = matrix(bodies[name]["position_m"], rotation(bodies[name]["quaternion_wxyz"]))
        entity = entities[name]
        if len(entity.links) != 1:
            raise ValueError("Regrasp sampling requires the frozen single-link pieces")
        for index, geom in enumerate(entity.links[0].geoms):
            mesh = geom.mesh.trimesh.copy()
            mesh.apply_transform(matrix(geom.init_pos, rotation(geom.init_quat)))
            pieces.add_object(f"{name}/{index}", mesh, transform=pose)
    group = robot.groups[side]
    limits = np.asarray(group.arm_limits_rad)
    candidates, accepted = [], []
    def validate(q, row):
        joints = q[robot._q_indices[side][:6]]
        margin = float(min(np.min(joints-limits[:, 0]), np.min(limits[:, 1]-joints)))
        row["minimum_joint_margin_rad"] = min(row["minimum_joint_margin_rad"], margin)
        if margin < .03:
            per_joint = np.minimum(joints-limits[:, 0], limits[:, 1]-joints)
            worst = int(np.argmin(per_joint))
            raise ValueError(f"Less than 0.03 rad joint margin: joint={worst}, q={joints[worst]:.6f}, margin={margin:.6f}")
        pose = fk.solve(q)
        pp = np.asarray(pose["position_world_m"]).reshape(-1, 3)
        rr = np.asarray(pose["orientation_wxyz"]).reshape(-1, 4)
        for s, name, link, vertices, check_table in geometry:
            rlink = rotation(rr[link])
            managers[s].set_transform(name, matrix(pp[link], rlink))
            if check_table:
                gap = float((rlink.apply(vertices)+pp[link])[:, 2].min()-table_height)
                row["minimum_table_clearance_m"] = min(row["minimum_table_clearance_m"], gap)
                if gap < .002:
                    raise ValueError("Less than 2 mm full-tool table clearance: "+name)
        hit, pairs = managers["left"].in_collision_other(managers["right"], return_names=True)
        if hit:
            raise ValueError("Arm-arm mesh intersection: "+str(sorted(pairs)[:2]))
        hit, pairs = managers[side].in_collision_other(pieces, return_names=True)
        if hit:
            raise ValueError("Open hand / puzzle mesh intersection: "+str(sorted(pairs)[:2]))
        index = robot.entity.get_link(group.hand_link).idx_local
        hr = rotation(rr[index])
        return (pp[index]+hr.apply(group.tcp_position_in_hand_m),
                hr*rotation(group.tcp_orientation_in_hand_wxyz))
    # Closing is always across plate thickness; the tilt here is an in-plane
    # approach angle around that jaw axis, not a change to either piece.
    routes = (
        ((.05, .035), (.04, 0.), (0., 0.)),
        ((.13, .05), (.06, 0.), (0., 0.)),
        ((.20, 0.), (.06, 0.), (0., 0.)),
    )
    if joint_transit:
        routes = (((.06, 0.), (.03, 0.), (0., 0.)),)
    # Five degrees leaves room at the wrist limit in the measured hanging
    # pose while keeping the fingers outside the full withdrawal path.
    options = ((5., 0.),) if joint_transit else product((0., -20., 20., -40., 40., -60., 60.), (0., 180.))
    options = tuple(options)
    for route_index, offsets in enumerate(routes):
        for tilt, roll in options:
            local = base*Rotation.from_euler("x", roll, degrees=True)*Rotation.from_euler("y", tilt, degrees=True)
            tr = br*local
            tp = bp+br.apply(REGRASP_POINTS[side])+tr.apply(PAD_TO_TCP)
            targets = [(tp-tr.apply([backoff, 0., 0.])+[0., 0., lift], tr)
                       for backoff, lift in offsets]
            row = dict(side=side, tilt_deg=tilt, roll_deg=roll, passed=False,
                       route_index=route_index, approach_offsets=offsets,
                       minimum_joint_margin_rad=float("inf"), minimum_table_clearance_m=float("inf"))
            q, start = initial_q.copy(), initial
            try:
                for segment, end in enumerate(targets):
                    row["segment"] = segment
                    if joint_transit and segment == 0:
                        rng = np.random.default_rng(4)
                        transit = None
                        failures = []
                        branch_seeds = [np.array([.2, .1, 1., roll, wrist, spin])
                            for roll in (-2.9, 2.9) for wrist in (1.7, 2.1) for spin in (-2., 2.)]
                        for attempt in range(1+len(branch_seeds)+24):
                            seed = q.copy()
                            if 1 <= attempt <= len(branch_seeds):
                                seed[robot._q_indices[side][:6]] = branch_seeds[attempt-1]
                            elif attempt:
                                seed[robot._q_indices[side][:6]] = rng.uniform(limits[:, 0]+.05, limits[:, 1]-.05)
                            try:
                                hand = end[1]*rotation(group.tcp_orientation_in_hand_wxyz).inv()
                                goal = ik.solve_checked(link_name=group.hand_link,
                                    position_world_m=end[0]-hand.apply(group.tcp_position_in_hand_m),
                                    orientation_wxyz=hand.as_quat()[[3, 0, 1, 2]], initial_qpos=seed,
                                    joint_dof_indices=robot._indices[side][:6])
                                trial = dict(row)
                                path = []
                                for u in np.linspace(0., 1., 81):
                                    p, r = validate(q+u*(goal-q), trial)
                                    path.append(dict(position_m=p.tolist(), quaternion_wxyz=r.as_quat()[[3, 0, 1, 2]].tolist()))
                                row.update(trial)
                                row["transit_ik_seed"] = ("current" if attempt == 0 else
                                    "wrist_branch_template" if attempt <= len(branch_seeds) else "uniform_joint_sample")
                                row["transit_ik_attempts"] = attempt+1
                                transit, q = path, goal
                                break
                            except ValueError as error:
                                failures.append(str(error))
                        if transit is None:
                            raise ValueError("No free joint-space transit: "+str(failures[-3:]))
                        row["transit_tcp"] = transit
                        start = end
                        continue
                    turn = Slerp([0, 1], Rotation.from_quat([start[1].as_quat(), end[1].as_quat()]))
                    for sample, u in enumerate(np.linspace(0., 1., 41)[1:], 1):
                        p, r = (1.-u)*start[0]+u*end[0], turn(u)
                        hand = r*rotation(group.tcp_orientation_in_hand_wxyz).inv()
                        q = ik.solve_checked(link_name=group.hand_link,
                            position_world_m=p-hand.apply(group.tcp_position_in_hand_m),
                            orientation_wxyz=hand.as_quat()[[3, 0, 1, 2]], initial_qpos=q,
                            joint_dof_indices=robot._indices[side][:6])
                        joints = q[robot._q_indices[side][:6]]
                        margin = float(min(np.min(joints-limits[:, 0]), np.min(limits[:, 1]-joints)))
                        row["minimum_joint_margin_rad"] = min(row["minimum_joint_margin_rad"], margin)
                        if margin < .03:
                            raise ValueError("Less than 0.03 rad joint margin")
                        if sample % 4:
                            continue
                        validate(q, row)
                    start = end
                row.update(passed=True, rotation_xyzw=local.as_quat().tolist(),
                           final_joint_position_rad=q[robot._q_indices[side][:6]].tolist())
                accepted.append(row)
            except ValueError as error:
                row["error"] = str(error)
            # Keep reports JSON-finite for candidates rejected on the first IK.
            for key in ("minimum_joint_margin_rad", "minimum_table_clearance_m"):
                if not np.isfinite(row[key]):
                    row[key] = None
            candidates.append(row)
        if accepted:
            break
    result = dict(kind="native_regrasp_ik_candidates", physics_steps=0, side=side,
                  geometry_scope="40 IK samples and 10 full mesh checks per Cartesian segment; 81 full mesh/FK samples for optional joint transit",
                  candidates=candidates, selected=None)
    if accepted:
        result["selected"] = max(accepted, key=lambda row: row["minimum_joint_margin_rad"])
    return result


class CoupledKeyholeIK:
    def __init__(self, robot, body_origins, bodies, *, seed_qpos=None, tcp_observation=None):
        from .policy import canonical_offsets
        self.robot = robot
        self.fk = GenesisFKSolver(robot.entity)
        self.seed = (to_numpy(robot.entity.get_qpos()).reshape(-1).copy() if seed_qpos is None
                     else np.asarray(seed_qpos, dtype=float).copy())
        if self.seed.shape != (int(robot.entity.n_qs),):
            raise ValueError("One complete robot qpos is required")
        self.indices = np.concatenate([robot._q_indices[s][:6] for s in PARTS])
        self.limits = np.concatenate([robot.groups[s].arm_limits_rad for s in PARTS])
        self.link_indices = {s: robot.entity.get_link(robot.groups[s].hand_link).idx_local for s in PARTS}
        self.origins = canonical_offsets(body_origins)
        tcp = robot.observe() if tcp_observation is None else tcp_observation
        self.grasp_offsets = {}
        for side, name in PARTS.items():
            b = bodies[name]
            r = rotation(b["quaternion_wxyz"])*ASSEMBLY_ROTATIONS[side]
            p = np.asarray(b["position_m"])-r.apply(self.origins[side])
            self.grasp_offsets[side] = (r.inv().apply(np.asarray(tcp[side]["tcp_position_world_m"])-p),
                r.inv()*rotation(tcp[side]["tcp_orientation_wxyz"]))
        self.queries = 0
        self.center_radius = np.array([.02, .02, .015])

    def poses(self, q):
        full = self.seed.copy()
        full[self.indices] = q
        result = self.fk.solve(full)
        positions = np.asarray(result["position_world_m"]).reshape(-1, 3)
        quats = np.asarray(result["orientation_wxyz"]).reshape(-1, 4)
        bodies, hands = {}, {}
        for side in PARTS:
            group, index = self.robot.groups[side], self.link_indices[side]
            hr = rotation(quats[index])
            tr = hr*rotation(group.tcp_orientation_in_hand_wxyz)
            tp = positions[index]+hr.apply(group.tcp_position_in_hand_m)
            dp, dr = self.grasp_offsets[side]
            br = tr*dr.inv()
            bodies[side] = (tp-br.apply(dp), br)
            hands[side] = (tp, tr)
        self.queries += 1
        return bodies, hands

    @staticmethod
    def relative(bodies):
        p, r = bodies["left"]
        pp, rr = bodies["right"]
        return r.inv().apply(pp-p), r.inv()*rr

    def solve(self, relative, center, previous):
        target_p, target_r = relative
        def residual(q):
            bodies, hands = self.poses(q)
            p, r = self.relative(bodies)
            midpoint = (hands["left"][0]+hands["right"][0])/2
            delta = midpoint-center
            workspace_error = np.sign(delta)*np.maximum(np.abs(delta)-self.center_radius, 0.)
            return np.r_[20.*(p-target_p), (r*target_r.inv()).as_rotvec(),
                         10.*workspace_error, .00003*(q-previous)]
        lower, upper = self.limits[:, 0]+.05, self.limits[:, 1]-.05
        seed = np.clip(previous, lower+1e-8, upper-1e-8)
        def converged(intermediate_result):
            # The tiny posture regularizer chooses among redundant solutions;
            # do not spend hundreds of FK calls minimizing it after all task
            # constraints are accurate to 1 um / 10 urad and inside the small
            # allowed common-position box. Final validation
            # below remains independent of the optimizer's termination status.
            error = intermediate_result.fun
            if (np.linalg.norm(error[:3])/20. < 1e-6
                    and np.linalg.norm(error[3:6]) < 1e-5
                    and np.linalg.norm(error[6:9])/10. < 1e-6):
                raise StopIteration
        result = least_squares(residual, seed, bounds=(lower, upper), max_nfev=120,
                               ftol=1e-10, xtol=1e-10, gtol=1e-10, callback=converged)
        errors = residual(result.x)
        if (np.linalg.norm(errors[:3])/20. > .00001 or np.linalg.norm(errors[3:6]) > .0001
                or np.linalg.norm(errors[6:9])/10. > .00001):
            raise ValueError(f"Coupled IK rejected: position={np.linalg.norm(errors[:3])/20.:.6g}, "
                             f"rotation={np.linalg.norm(errors[3:6]):.6g}, workspace={np.linalg.norm(errors[6:9])/10.:.6g}")
        bodies, _ = self.poses(result.x)
        return result.x, bodies

    def plan(self, reference_policy, *, center, stride=1, progress=None, lift_m=0., entry_history=None):
        q = self.seed[self.indices].copy()
        bodies, hands = self.poses(q)
        start_p, start_r = self.relative(bodies)
        end_p, end_r = self.relative(reference_policy.reference_pose(0))
        start_center = (hands["left"][0]+hands["right"][0])/2
        turn = Slerp([0, 1], Rotation.from_quat([start_r.as_quat(), end_r.as_quat()]))
        frames = []
        entry_summary = None
        def append(q, poses, stage, seconds, reference_index=None):
            item = dict(stage=stage, duration_s=float(seconds), reference_index=reference_index,
                joint_position_rad={s: q[i*6:(i+1)*6].tolist() for i, s in enumerate(PARTS)},
                bodies={s: dict(position_m=p.tolist(), quaternion_wxyz=r.as_quat()[[3, 0, 1, 2]].tolist())
                        for s, (p, r) in poses.items()})
            frames.append(item)
            if progress:
                progress(dict(frames=len(frames), stage=stage, reference_index=reference_index,
                              fk_queries=self.queries))
        append(q, bodies, "pickup_hold", 0.)
        # Regrasping lets the unheld piece swing through real contact poses.
        # A straight SE(3) shortcut back to the maze entrance cuts through the
        # metal. Use the same episode's observed relative path in reverse as
        # new action targets. No engine state or past robot q is restored.
        if entry_history:
            safe_center = start_center.copy()
            safe_center[2] = max(safe_center[2], float(center[2])+.06)
            initial_relative = self.relative(bodies)
            for u in np.linspace(0., 1., 13)[1:]:
                q, bodies = self.solve(initial_relative, start_center+u*(safe_center-start_center), q)
                append(q, bodies, "lift_after_regrasp", .25)
            start_center = safe_center
            observed_relative = [self.relative(bodies)]
            for sample in reversed(entry_history):
                poses = {}
                for side, name in PARTS.items():
                    b = sample["bodies"][name]
                    r = rotation(b["quaternion_wxyz"])*ASSEMBLY_ROTATIONS[side]
                    poses[side] = (np.asarray(b["position_m"])-r.apply(self.origins[side]), r)
                observed_relative.append(self.relative(poses))
            compact_relative = simplify_relative_samples(observed_relative)
            entry_summary = dict(observed_samples=len(observed_relative), retained_samples=len(compact_relative),
                omitted_sample_displacement_bound_m=.00004, rotation_radius_m=.15,
                continuous_collision_certificate=False)
            last_relative = compact_relative[0]
            for target in compact_relative[1:]:
                displacement = float(np.linalg.norm(target[0]-last_relative[0])
                    + .15*(target[1]*last_relative[1].inv()).magnitude())
                q, bodies = self.solve(target, start_center, q)
                append(q, bodies, "restore_after_regrasp", max(.05, displacement/.1))
                last_relative = target
            start_p, start_r = self.relative(bodies)
            turn = Slerp([0, 1], Rotation.from_quat([start_r.as_quat(), end_r.as_quat()]))
        lifted_center = start_center+np.array([0., 0., lift_m])
        for u in (np.linspace(0., 1., 13)[1:] if lift_m else []):
            q, poses = self.solve((start_p, start_r), start_center+u*(lifted_center-start_center), q)
            append(q, poses, "lift_assembly", .25)
        for u in np.linspace(0., 1., 25)[1:]:
            q, poses = self.solve((start_p+u*(end_p-start_p), turn(u)),
                                 lifted_center+u*(center-lifted_center), q)
            append(q, poses, "align_route_entry", .25)
        source = reference_policy.reference["frames"]
        indices = sorted(set(range(0, len(source), stride)) | {len(source)-1})
        previous_index = 0
        for index in indices:
            q, poses = self.solve(self.relative(reference_policy.reference_pose(index)), center, q)
            append(q, poses, source[index]["stage"], max(.025, (index-previous_index)/reference_policy.reference["fps"]), index)
            previous_index = index
        return dict(kind="coupled_native_genesis_ik_candidate", physics_steps=0,
                    relative_path_preserved=True, joint_branch_is_not_forced_by_ee_actions=True,
                    entry_history_compaction=entry_summary,
                    center_radius_m=self.center_radius.tolist(), reserved_joint_margin_rad=.05,
                    center_world_m=np.asarray(center).tolist(), fk_queries=self.queries, frames=frames)
