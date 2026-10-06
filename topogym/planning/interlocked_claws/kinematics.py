"""Read-only ALOHA IK/FK and imported collision geometry for the Claws pregrasp state.

Both hands already hold their piece at episode birth. Grasp transforms are
measured from the live state, never assumed. Every query is native Genesis
FK/IK plus FCL distances; nothing here sets a pose or advances physics.
"""
import fcl
import numpy as np
from scipy.optimize import least_squares
from scipy.spatial.transform import Rotation

from topogym.planning.buzz_wire_3d.kinematics import mesh_object, manager, distance
from topogym.planning.hedgehog_in_cage.kinematics import surface_object
from topogym.planning.rigid_reference.feedback import body_pose, relative_pose
from topogym.planning.rigid_reference.geometry import interpolate, pose_dict
from topogym.solvers.genesis_kinematics import GenesisFKSolver
from topogym.planning.oracle_ik import OracleIKSolver as GenesisIKSolver
from topogym.utils.arrays import to_numpy

BASE_LINKS = {"base_link", "waist_link", "shoulder_link"}


def densify(poses, *, step_m=.004, step_rad=np.deg2rad(2.), radius_m=.15, with_fraction=False):
    """Insert intermediate poses so that no sample moves more than the step bounds.

    with_fraction=True also returns each sample's fractional index along the input poses."""
    out, fractions = [poses[0]], [0.]
    for k, (a, b) in enumerate(zip(poses, poses[1:])):
        motion = np.linalg.norm(b[0]-a[0])+radius_m*(b[1]*a[1].inv()).magnitude()
        count = max(1, int(np.ceil(max(np.linalg.norm(b[0]-a[0])/step_m, (b[1]*a[1].inv()).magnitude()/step_rad, motion/(2*step_m)))))
        for u in np.linspace(0., 1., count+1)[1:]:
            out.append(interpolate(a, b, u)); fractions.append(k+u)
    return (out, fractions) if with_fraction else out


class ClawsIK:
    def __init__(self, env, meshes, ownership):
        """meshes: frozen local trimesh per piece; ownership: {piece_name: side}."""
        self.robot = robot = env._robot
        self.ik, self.fk = GenesisIKSolver(robot.entity), GenesisFKSolver(robot.entity)
        self.seed = to_numpy(robot.entity.get_qpos()).reshape(-1).copy()
        self.table_height = float(env._task.table_height_m)
        self.ownership = dict(ownership)
        self.holding = {side: name for name, side in ownership.items()}
        self.arm_q = {side: list(robot._q_indices[side][:6]) for side in robot.groups}
        self.arm_dofs = {side: list(robot._indices[side][:6]) for side in robot.groups}
        self.limits = {side: np.asarray(robot.groups[side].arm_limits_rad, float) for side in robot.groups}
        ps, rs = self.link_frames(self.seed)
        self.shapes, by_geom = [], {}
        for link in robot.entity.links:
            side = link.name.split("/")[0]
            for geom in link.geoms:
                local = rs[link.idx_local].inv().apply(to_numpy(geom.get_verts()).reshape(-1, 3)-ps[link.idx_local])
                obj = mesh_object(local, geom.init_faces)
                self.shapes.append((side, link.name, link.idx_local, local, obj))
                by_geom[int(geom.idx)] = (side, link.name, obj)
        valid = env._world.scene.sim.rigid_solver.collider._valid_collision_pairs
        self.self_pairs = [(by_geom[int(a)], by_geom[int(b)]) for a, b in valid
                           if int(a) in by_geom and int(b) in by_geom and by_geom[int(a)][0] == by_geom[int(b)][0]]
        self.by_arm = {side: manager([x[4] for x in self.shapes if x[0] == side]) for side in robot.groups}
        self.nonfinger = {side: manager([x[4] for x in self.shapes if x[0] == side and "finger" not in x[1]])
                          for side in robot.groups}
        self.pieces = {}
        for name, mesh in meshes.items():
            obj = surface_object(np.asarray(mesh.vertices, float), np.asarray(mesh.faces, np.int32))
            self.pieces[name] = (np.asarray(mesh.vertices, float), obj, manager([obj]))
        world = env._world.read_state()
        self.initial_pieces = {name: body_pose(world["bodies"][name]) for name in meshes}
        self.offsets = {}
        for name, side in ownership.items():
            self.offsets[side] = relative_pose(self.initial_pieces[name], self.tcp(self.seed, side))
        self.queries = 0

    def link_frames(self, q):
        pose = self.fk.solve(q)
        ps = np.asarray(pose["position_world_m"]).reshape(-1, 3)
        rs = Rotation.from_quat(np.asarray(pose["orientation_wxyz"]).reshape(-1, 4)[:, [1, 2, 3, 0]])
        return ps, rs

    def tcp(self, q, side, frames=None):
        ps, rs = self.link_frames(q) if frames is None else frames
        group = self.robot.groups[side]
        index = self.robot.entity.get_link(group.hand_link).idx_local
        hr = rs[index]
        return ps[index]+hr.apply(group.tcp_position_in_hand_m), hr*Rotation.from_quat(np.roll(group.tcp_orientation_in_hand_wxyz, -1))

    def piece_from_tcp(self, side, tcp):
        dp, dr = self.offsets[side]
        r = tcp[1]*dr.inv()
        return tcp[0]-r.apply(dp), r

    def tcp_from_piece(self, side, piece):
        dp, dr = self.offsets[side]
        return piece[0]+piece[1].apply(dp), piece[1]*dr

    def pieces_at(self, q, frames=None):
        frames = self.link_frames(q) if frames is None else frames
        return {name: self.piece_from_tcp(side, self.tcp(q, side, frames)) for name, side in self.ownership.items()}

    def solve_arm(self, side, tcp, seed):
        p, r = tcp
        group = self.robot.groups[side]
        hand_r = r*Rotation.from_quat(np.roll(group.tcp_orientation_in_hand_wxyz, -1)).inv()
        self.queries += 1
        return self.ik.solve_checked(link_name=group.hand_link,
            position_world_m=p-hand_r.apply(group.tcp_position_in_hand_m),
            orientation_wxyz=hand_r.as_quat()[[3, 0, 1, 2]], initial_qpos=seed,
            joint_dof_indices=self.arm_dofs[side], max_solver_iterations=300)

    def solve_pieces(self, targets, seed):
        """Explicit world piece poses for each hand; sequential checked IK, previous branch as seed."""
        q = np.asarray(seed, float).copy()
        for name, pose in targets.items():
            side = self.ownership[name]
            q = self.solve_arm(side, self.tcp_from_piece(side, pose), q)
        return q

    def check(self, q, piece_poses, *, robot_margin_m=.0005, table_margin_m=.0005, pair_margin_m=.0005):
        """Sampled full-mesh checks at one configuration; not a continuous certificate."""
        ps, rs = self.link_frames(q)
        table = float("inf")
        for side, name, index, vertices, obj in self.shapes:
            obj.setTransform(fcl.Transform(rs[index].as_matrix(), ps[index]))
            if name.rsplit("/", 1)[-1] not in BASE_LINKS:
                table = min(table, float((rs[index].apply(vertices)+ps[index])[:, 2].min()-self.table_height))
        for m in (*self.by_arm.values(), *self.nonfinger.values()):
            m.update()
        piece_table = float("inf")
        for name, (p, r) in piece_poses.items():
            vertices, obj, m = self.pieces[name]
            obj.setTransform(fcl.Transform(r.as_matrix(), p))
            m.update()
            piece_table = min(piece_table, float((r.apply(vertices)+p)[:, 2].min()-self.table_height))
        issues, gaps = [], {}
        names = list(piece_poses)
        if len(names) == 2:
            gaps["piece_pair_m"] = distance(self.pieces[names[0]][2], self.pieces[names[1]][2])
            if pair_margin_m is not None and gaps["piece_pair_m"] < pair_margin_m:
                issues.append("piece_pair")
        self_hits = [[a[1], b[1]] for a, b in self.self_pairs
                     if fcl.collide(a[2], b[2], fcl.CollisionRequest(), fcl.CollisionResult())]
        if self_hits:
            issues.append("same_arm_collision")
        if table < table_margin_m:
            issues.append("robot_table")
        if piece_table < table_margin_m:
            issues.append("piece_table")
        gaps["inter_arm_m"] = distance(self.by_arm["left"], self.by_arm["right"])
        if gaps["inter_arm_m"] < robot_margin_m:
            issues.append("inter_arm")
        for side, arm in self.by_arm.items():
            for name, (_, _, puzzle) in self.pieces.items():
                checked = self.nonfinger[side] if self.holding.get(side) == name else arm
                gap = gaps[f"{side}/{name}_m"] = distance(checked, puzzle)
                if gap < robot_margin_m:
                    issues.append(f"{side}/{name}")
        for side, indices in self.arm_q.items():
            joints, limits = q[indices], self.limits[side]
            margin = float(min(np.min(joints-limits[:, 0]), np.min(limits[:, 1]-joints)))
            gaps[f"{side}/joint_margin_rad"] = margin
            if margin < .03:
                issues.append(side+"/joint_limits")
        return dict(passed=not issues, issues=issues, robot_table_clearance_m=table,
                    piece_table_clearance_m=piece_table, self_collisions=self_hits, gaps=gaps)


class CoupledClawsIK:
    """Relative pose constraint with a free common pose kept near a workspace centre."""

    def __init__(self, kin, target, other, *, center=None, center_radius=(.06, .06, .04)):
        self.kin, self.target, self.other = kin, target, other
        self.sides = (kin.ownership[target], kin.ownership[other])
        self.indices = np.concatenate([kin.arm_q[s] for s in self.sides])
        self.limits = np.concatenate([kin.limits[s] for s in self.sides])
        self.center_radius = np.asarray(center_radius, float)
        if center is None:
            tcps = [kin.tcp(kin.seed, s) for s in self.sides]
            center = np.mean([t[0] for t in tcps], axis=0)
        self.center = np.asarray(center, float)
        # Keep the target piece's world orientation near its authored one while the relative path is followed;
        # the object witness fixed the target entirely, so this stays close to the certified realization.
        self.level = kin.initial_pieces[target][1]
        self.level_weight = .5
        self.wrist_weight = 0.   # set by the planner when the wrist load matters
        self.anchor_weight = .02

    def poses(self, q):
        full = self.kin.seed.copy()
        full[self.indices] = q
        frames = self.kin.link_frames(full)
        pieces = self.kin.pieces_at(full, frames)
        hands = {s: self.kin.tcp(full, s, frames) for s in self.sides}
        return full, pieces, hands

    def limit_penalty(self, q, *, comfort_rad=.3, weight=.05):
        """Soft push away from joint limits so a long separation does not end in a stretched posture."""
        margin = np.minimum(q-self.limits[:, 0], self.limits[:, 1]-q)
        return weight*np.maximum(comfort_rad-margin, 0.)

    def _solve(self, residual, seed, converged, *, penalty=True):
        """Comfort-penalized solve, then an exact refinement from that posture without the penalty."""
        lower, upper = self.limits[:, 0]+.05, self.limits[:, 1]-.05
        seed = np.clip(seed, lower+1e-8, upper-1e-8)
        x = seed
        if penalty:
            x = least_squares(lambda q: residual(q, True), seed, bounds=(lower, upper), max_nfev=150,
                              ftol=1e-10, xtol=1e-10, gtol=1e-10, callback=converged).x
        return least_squares(lambda q: residual(q, False), x, bounds=(lower, upper), max_nfev=150,
                             ftol=1e-12, xtol=1e-12, gtol=1e-12, callback=converged).x

    def avoidance(self, full, pairs, *, clearance_m=.015, weight=3.):
        """Soft push-apart for named same-arm link pairs that collided on a previous solve."""
        if not pairs:
            return np.zeros(0)
        ps, rs = self.kin.link_frames(full)
        shapes = {name: (index, obj) for _, name, index, _, obj in self.kin.shapes}
        values = []
        for a, b in pairs:
            for name in (a, b):
                index, obj = shapes[name]
                obj.setTransform(fcl.Transform(rs[index].as_matrix(), ps[index]))
            d = float(fcl.distance(shapes[a][1], shapes[b][1], fcl.DistanceRequest(), fcl.DistanceResult()))
            values.append(weight*max(0., clearance_m-d))
        return np.asarray(values)

    def solve(self, relative, previous, level=None, avoid=(), center=None, seed=None, level_weight=None, center_radius=None):
        tp, tr = relative
        level = self.level if level is None else level
        center = self.center if center is None else np.asarray(center, float)
        level_weight = self.level_weight if level_weight is None else level_weight
        center_radius = self.center_radius if center_radius is None else np.asarray(center_radius, float)
        def residual(q, penalized=False):
            full, pieces, hands = self.poses(q)
            p, r = relative_pose(pieces[self.target], pieces[self.other])
            midpoint = np.mean([hands[s][0] for s in self.sides], axis=0)
            delta = midpoint-center
            workspace = np.sign(delta)*np.maximum(np.abs(delta)-center_radius, 0.)
            tilt = (pieces[self.target][1]*level.inv()).as_rotvec()[:2]   # roll/pitch only; yaw stays free
            anchor = np.zeros(0) if seed is None else self.anchor_weight*(q-np.asarray(seed, float))   # follow the recorded posture branch
            # The low-gain wrist_rotate joint turns about the gripper's pointing axis; keeping that axis near
            # vertical removes the gravity moment of the held piece about it (horizontal components -> 0).
            upright = self.wrist_weight*np.concatenate([hands[s][1].apply([1., 0., 0.])[:2] for s in self.sides])
            base = np.r_[20.*(p-tp), (r*tr.inv()).as_rotvec(), 10.*workspace, .00003*(q-previous), level_weight*tilt]
            # Anchor and avoidance only shape the penalized first stage; the exact refinement starts from that posture.
            return np.r_[base, self.limit_penalty(q), self.avoidance(full, avoid), anchor, upright] if penalized else base
        def converged(intermediate):
            # SciPy passes an OptimizeResult on some versions and the bare vector on others.
            e = intermediate.fun if hasattr(intermediate, "fun") else residual(np.asarray(intermediate, float))
            if np.linalg.norm(e[:3])/20. < 1e-6 and np.linalg.norm(e[3:6]) < 1e-5 and np.linalg.norm(e[6:9])/10. < 1e-6:
                raise StopIteration
        class _R: pass
        result = _R(); result.x = self._solve(residual, previous, converged)
        e = residual(result.x)
        from topogym.planning.oracle_ik import accept_coupled_candidate
        start, goal = self.kin.seed.copy(), self.kin.seed.copy()
        start[self.indices], goal[self.indices] = previous, result.x
        if not accept_coupled_candidate(self.kin.robot, start, goal,
                [np.linalg.norm(e[:3])/20., np.linalg.norm(e[3:6]), np.linalg.norm(e[6:9])/10.],
                [1e-5, 1e-4, 1e-5]):
            raise ValueError(f"Coupled IK residual: position={np.linalg.norm(e[:3])/20.:.3g} m, "
                             f"rotation={np.linalg.norm(e[3:6]):.3g} rad, workspace={np.linalg.norm(e[6:9])/10.:.3g} m")
        return result.x

    def solve_world(self, targets, previous):
        """Explicit world poses for both pieces; the posture regularizer keeps one continuous branch."""
        def residual(q, penalized=False):
            _, pieces, _ = self.poses(q)
            parts = []
            for name, (tp, tr) in targets.items():
                p, r = pieces[name]
                parts += [20.*(p-tp), (r*tr.inv()).as_rotvec()]
            base = np.r_[np.concatenate(parts), .0003*(q-previous)]
            return np.r_[base, self.limit_penalty(q)] if penalized else base
        n = 6*len(targets)
        def converged(intermediate):
            e = intermediate.fun if hasattr(intermediate, "fun") else residual(np.asarray(intermediate, float))
            if all(np.linalg.norm(e[k:k+3])/20. < 1e-6 and np.linalg.norm(e[k+3:k+6]) < 1e-5 for k in range(0, n, 6)):
                raise StopIteration
        class _R: pass
        result = _R(); result.x = self._solve(residual, previous, converged)
        e = residual(result.x)
        position = max(np.linalg.norm(e[k:k+3])/20. for k in range(0, n, 6))
        rotation = max(np.linalg.norm(e[k+3:k+6]) for k in range(0, n, 6))
        from topogym.planning.oracle_ik import accept_coupled_candidate
        start, goal = self.kin.seed.copy(), self.kin.seed.copy()
        start[self.indices], goal[self.indices] = previous, result.x
        if not accept_coupled_candidate(self.kin.robot, start, goal, [position, rotation], [5e-5, 5e-4]):
            raise ValueError(f"World IK residual: position={position:.3g} m, rotation={rotation:.3g} rad")
        return result.x

    def plan(self, relative_path, *, progress=None, pair_check_from=0, level_hints=None, seeds=None, centers=None,
             max_joint_step_rad=.12):
        """Sampled coupled IK along the relative path; every sample is fully checked.

        Samples before pair_check_from belong to a departure from a measured contact state and
        skip the piece-pair clearance test; everything else is still checked. level_hints, when given,
        are per-sample world orientations the target piece is biased toward (roll/pitch), e.g. a recording."""
        q = self.kin.seed[self.indices].copy()
        rows, failure = [], None
        rng = np.random.default_rng(0)
        retries_used = subdivisions = 0
        avoid = ()
        pending = [(i, pose, None if level_hints is None else level_hints[i],
                    None if seeds is None else np.asarray(seeds[i], float)[self.indices],
                    None if centers is None else centers[i]) for i, pose in enumerate(relative_path)]
        last_pose, depth = None, 0
        while pending:
            index, relative, level, seed, center = pending.pop(0)
            previous = q.copy()
            try:
                # Continuity first: solve from the previous posture. The recorded seed only initializes the
                # very first sample and the retries below, so branch changes are not injected by the seeds.
                q = self.solve(relative, q, level=level, avoid=avoid, center=center,
                               seed=seed)   # recorded posture as soft anchor on every sample
            except ValueError as error:
                failure = dict(index=index, reason="ik", error=str(error))
                break
            if rows and np.abs(q-previous).max() > max_joint_step_rad and depth < 6 and last_pose is not None:
                # Branch discontinuity: halve the relative step and re-solve from the previous posture.
                pending.insert(0, (index, relative, level, seed, center))
                pending.insert(0, (index, interpolate(last_pose, relative, .5), level, seed, center))
                q, depth, subdivisions = previous, depth+1, subdivisions+1
                continue
            full, pieces, _ = self.poses(q)
            check = self.kin.check(full, pieces, pair_margin_m=None if index < pair_check_from else .0005)
            if check["passed"] and rows and index >= pair_check_from and last_pose is not None:
                # Execution interpolates joints linearly between rows: intermediate postures of a large step
                # must also pass; otherwise halve the relative step so the rows get dense enough.
                qa, span = np.asarray(rows[-1]["qpos"]), float(np.abs(full-np.asarray(rows[-1]["qpos"])).max())
                bad = None
                if span > .1:
                    for u in np.linspace(0., 1., int(np.ceil(span/.05))+1)[1:-1]:
                        qm = qa+u*(full-qa)
                        # Rows sit on the certified relative path; intermediate joint-interpolated postures only
                        # need to stay clear of intersection (the route margin itself may be 0.5 mm).
                        mid_check = self.kin.check(qm, self.kin.pieces_at(qm), pair_margin_m=.0002)
                        if not mid_check["passed"]:
                            bad = dict(fraction=float(u), issues=mid_check["issues"]); break
                if bad is not None and depth < 6:
                    pending.insert(0, (index, relative, level, seed, center))
                    pending.insert(0, (index, interpolate(last_pose, relative, .5), level, seed, center))
                    q, depth, subdivisions = previous, depth+1, subdivisions+1
                    continue
                if bad is not None:
                    failure = dict(index=index, reason="joint_interpolation_collision", issues=bad["issues"], fraction=bad["fraction"])
                    rows.append(dict(index=index, qpos=full.tolist(), pieces={n: pose_dict(p) for n, p in pieces.items()},
                                     maximum_joint_change_rad=span, **check))
                    break
            depth = 0
            if not check["passed"] and rows:
                # The kinematic solve knows nothing about collisions: first push the offending same-arm
                # links apart with a soft avoidance term, then look for another nearby branch.
                pairs = [tuple(pair) for pair in check.get("self_collisions", [])]
                if pairs:
                    avoid = tuple(set(avoid)|set(pairs))
                def interpolation_clear(qa, qb):
                    span = float(np.abs(qb-qa).max())
                    for u in np.linspace(0., 1., int(np.ceil(span/.05))+1)[1:-1]:
                        qm = qa+u*(qb-qa)
                        if not self.kin.check(qm, self.kin.pieces_at(qm), pair_margin_m=.0002)["passed"]:
                            return False
                    return True
                variants = [dict(), dict(level_weight=0.), dict(center_radius=self.center_radius*3.), dict(level_weight=0., center_radius=self.center_radius*3.)]
                for attempt in range(24):
                    start = previous if attempt == 0 else (seed if (attempt == 1 and seed is not None) else previous+rng.normal(0., .12+.04*attempt, previous.shape))
                    try:
                        candidate = self.solve(relative, start, level=level if attempt % 2 == 0 else self.level, avoid=avoid, center=center,
                                               seed=seed, **variants[attempt % len(variants)])
                    except ValueError:
                        continue
                    # A branch change is acceptable only if the straight joint-space move to it stays clear.
                    if np.abs(candidate-previous).max() > .35 and not interpolation_clear(self.poses(previous)[0], self.poses(candidate)[0]):
                        continue
                    c_full, c_pieces, _ = self.poses(candidate)
                    c_check = self.kin.check(c_full, c_pieces, pair_margin_m=None if index < pair_check_from else .0005)
                    if c_check["passed"]:
                        q, full, pieces, check = candidate, c_full, c_pieces, c_check
                        retries_used += 1
                        break
            rows.append(dict(index=index, qpos=full.tolist(), pieces={n: pose_dict(p) for n, p in pieces.items()},
                             maximum_joint_change_rad=float(np.abs(q-previous).max()), **check))
            last_pose = relative
            if not check["passed"]:
                failure = dict(index=index, reason="collision", issues=check["issues"])
                break
            if progress and index % 50 == 0:
                progress(dict(index=index, samples=len(relative_path), rows=len(rows)))
        interpolation = dict(note="intermediate postures of every joint step above 0.1 rad were checked in the loop")
        return dict(passed=failure is None, rows=rows, failure=failure, branch_retries=retries_used, subdivisions=subdivisions,
                    joint_interpolation=interpolation, avoided_pairs=[list(p) for p in avoid],
                    scope="relative-path-preserving sampled native coupled IK; contact dynamics not established")

