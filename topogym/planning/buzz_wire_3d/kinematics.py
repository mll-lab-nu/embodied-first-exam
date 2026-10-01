"""Read-only Genesis IK and full imported collision-surface candidate checks."""
import numpy as np
import fcl
from scipy.spatial.transform import Rotation, Slerp

from topogym.solvers.genesis_kinematics import GenesisFKSolver, GenesisIKSolver
from topogym.utils.arrays import to_numpy
from .policy import rotation


class CheckedJointPolicy:
    """Owner adapter: read-only IK queries, then ordinary JOINT_ABS actions.

    The task policy still consumes observations and produces Cartesian intent.
    Planned free-hand joint seeds preserve the chosen redundant IK branch.
    This adapter has no step/reset/set-qpos operation.
    """
    def __init__(self, policy, robot):
        self.policy, self.robot = policy, robot
        self.solver = GenesisIKSolver(robot.entity)

    def __getattr__(self, name):
        return getattr(self.policy,name)

    def initialize(self, context):
        adapted = dict(context)
        adapted["action_spec"] = dict(context["action_spec"])
        if adapted["action_spec"]["mode"] != "JOINT_ABS":
            raise ValueError("CheckedJointPolicy requires JOINT_ABS")
        adapted["action_spec"]["mode"] = "EE_ABS"
        self.policy.initialize(adapted)

    def act(self, observation):
        intent = self.policy.act(observation)
        if intent is None or not intent:
            return intent
        arm = intent["arm"]
        result = {"gripper_position_rad":arm["gripper_position_rad"]} if "gripper_position_rad" in arm else {}
        if "joint_position_rad" in arm:
            # These references have already passed owner-side FK/collision
            # sampling. The public JOINT_ABS compiler still enforces limits.
            result["joint_position_rad"] = arm["joint_position_rad"]
            return {"arm":result}
        if "position_world_m" in arm:
            group = self.robot.groups["arm"]
            seed = to_numpy(self.robot.entity.get_qpos()).reshape(-1).copy()
            planned = getattr(self.policy,"desired_arm_seed",None)
            if planned is not None:
                seed[self.robot._q_indices["arm"][:7]] = planned
            r = rotation(arm["orientation_wxyz"])
            arguments = dict(link_name=group.hand_link,
                position_world_m=np.asarray(arm["position_world_m"])-r.apply(group.tcp_position_in_hand_m),
                orientation_wxyz=arm["orientation_wxyz"],joint_dof_indices=self.robot._indices["arm"][:7],
                initial_qpos=seed)
            try:
                q = self.solver.solve_checked(**arguments)
            except ValueError:
                # An extended arm may converge slowly from the measured seed.
                # Retry the same Cartesian target with the route's checked
                # redundant solution; retain the original residual thresholds.
                reference = getattr(self.policy,"reference_arm_seed",None)
                seed = seed.copy()
                if reference is not None:
                    seed[self.robot._q_indices["arm"][:7]] = reference
                arguments.update(initial_qpos=seed,max_solver_iterations=300)
                try:
                    q = self.solver.solve_checked(**arguments)
                except ValueError:
                    nominal = getattr(self.policy,"nominal_tcp_target",None)
                    if nominal is None:
                        raise
                    np_, nr = nominal
                    target_p = np.asarray(arm["position_world_m"])
                    correction = (r*nr.inv()).as_rotvec()
                    for fraction in (.5,.25,0.):
                        rp = np_+fraction*(target_p-np_)
                        rr = Rotation.from_rotvec(fraction*correction)*nr
                        arguments.update(position_world_m=rp-rr.apply(group.tcp_position_in_hand_m),
                                         orientation_wxyz=rr.as_quat()[[3,0,1,2]])
                        try:
                            q = self.solver.solve_checked(**arguments)
                        except ValueError:
                            if fraction == 0.:
                                raise
                            continue
                        # Prevent integral windup when feedback compensation
                        # reaches beyond an otherwise reachable nominal pose.
                        self.policy.bias *= fraction
                        self.policy.angle_bias *= fraction
                        self.policy.tracking["ik_compensation_fraction"] = fraction
                        break
            result["joint_position_rad"] = q[self.robot._q_indices["arm"][:7]].tolist()
        return {"arm":result}


def mesh_object(vertices, faces):
    # Imported rigid collision pieces are convexified by Genesis. Convex GJK
    # also detects containment, which triangle-surface distance alone misses.
    import trimesh
    hull = trimesh.convex.convex_hull(np.asarray(vertices, float))
    polygons = np.column_stack([np.full(len(hull.faces), 3), hull.faces]).ravel()
    model = fcl.Convex(hull.vertices, len(hull.faces), polygons)
    return fcl.CollisionObject(model)


def manager(objects):
    result = fcl.DynamicAABBTreeCollisionManager()
    result.registerObjects(objects)
    result.setup()
    return result


def distance(first, second):
    data = fcl.DistanceData(request=fcl.DistanceRequest())
    first.distance(second, data, fcl.defaultDistanceCallback)
    return float(data.result.min_distance)


class BuzzIK:
    def __init__(self, env):
        self.robot = env._robot
        self.ik, self.fk = GenesisIKSolver(self.robot.entity), GenesisFKSolver(self.robot.entity)
        self.seed = to_numpy(self.robot.entity.get_qpos()).reshape(-1).copy()
        self.group = self.robot.groups["arm"]
        self.indices = self.robot._indices["arm"][:7]
        self.arm_qindices = self.robot._q_indices["arm"][:7]
        self.robot_shapes = []
        initial = self.fk.solve(self.seed)
        initial_p = np.asarray(initial["position_world_m"]).reshape(-1,3)
        initial_r = Rotation.from_quat(np.asarray(initial["orientation_wxyz"]).reshape(-1,4)[:,[1,2,3,0]])
        for link in self.robot.entity.links:
            # FK returns internal world link frames; get_pos(relative=True)
            # strips importer inertial alignment. Derive geometry in the exact
            # same FK frames used below, avoiding that mixed-frame error.
            p, r = initial_p[link.idx_local], initial_r[link.idx_local]
            for geom in link.geoms:
                local = r.inv().apply(to_numpy(geom.get_verts()).reshape(-1, 3)-p)
                self.robot_shapes.append((link.idx_local, mesh_object(local, geom.init_faces)))
        self.robot_manager = manager([obj for _, obj in self.robot_shapes])
        wire_count = sum(len(link.geoms) for link in env._world.entities["wire"].links)
        fixed = [mesh_object(to_numpy(g.get_verts()).reshape(-1,3), g.init_faces)
                 for name in ("wire", "wire_base") for link in env._world.entities[name].links for g in link.geoms]
        self.fixed_objects, self.fixed = fixed, manager(fixed)
        self.wire_fixed = manager(fixed[:wire_count])
        wand = env._world.entities["wand"]
        p = to_numpy(wand.get_pos()).reshape(3)
        r = rotation(to_numpy(wand.get_quat()).reshape(4))
        self.wand_objects = [mesh_object(r.inv().apply(to_numpy(g.get_verts()).reshape(-1,3)-p), g.init_faces)
                             for link in wand.links for g in link.geoms]
        self.wand_manager = manager(self.wand_objects)

    def solve(self, tcp, seed):
        p, r = tcp
        return self.ik.solve_checked(link_name=self.group.hand_link,
            position_world_m=p-r.apply(self.group.tcp_position_in_hand_m),
            orientation_wxyz=r.as_quat()[[3,0,1,2]], joint_dof_indices=self.indices, initial_qpos=seed)

    def clearance(self, q, body=None, *, allow_wand_support=False):
        poses = self.fk.solve(q)
        ps = np.asarray(poses["position_world_m"]).reshape(-1,3)
        rs = Rotation.from_quat(np.asarray(poses["orientation_wxyz"]).reshape(-1,4)[:,[1,2,3,0]])
        for link, obj in self.robot_shapes:
            obj.setTransform(fcl.Transform(rs[link].as_matrix(), ps[link]))
        self.robot_manager.update()
        robot_gap = distance(self.robot_manager, self.fixed)
        if body is None:
            return robot_gap
        return min(robot_gap,self.wand_clearance(body,wire_only=allow_wand_support))

    def wand_clearance(self, body, *, wire_only=False):
        p, r = body
        for obj in self.wand_objects:
            obj.setTransform(fcl.Transform(r.as_matrix(), p))
        self.wand_manager.update()
        return distance(self.wand_manager, self.wire_fixed if wire_only else self.fixed)

    def plan_held_waypoints(self, waypoints, offset_p, offset_r, *, allow_wand_support=False,
                            minimum_clearance=.001, maximum_material_step=.0005):
        """Check a held-body path against current passive finger geometry.

        Terminal seating can allow wand contact with its wooden support. Robot
        collisions with the support and all wire collisions remain forbidden.
        Every candidate is a read-only IK/FK query; this method moves nothing.
        """
        q = self.seed.copy()
        tp,tr = self.tcp_pose(q)
        ra = tr*offset_r.inv()
        pa = tp-ra.apply(offset_p)
        frames = [dict(qpos=q.tolist(),position_m=pa.tolist(),
                       quaternion_wxyz=ra.as_quat()[[3,0,1,2]].tolist())]
        for pb,rb in waypoints:
            pb = np.asarray(pb)
            count = max(1,int(np.ceil((np.linalg.norm(pb-pa)+.09*(rb*ra.inv()).magnitude())
                                      /maximum_material_step)))
            turn = Slerp([0,1],Rotation.from_quat([ra.as_quat(),rb.as_quat()]))
            for u in np.linspace(0,1,count+1)[1:]:
                p,r = pa+u*(pb-pa),turn(u)
                q = self.solve((p+r.apply(offset_p),r*offset_r),q)
                gap = self.clearance(q,(p,r),allow_wand_support=allow_wand_support)
                if gap < minimum_clearance:
                    raise ValueError(f"Held waypoint collision at frame {len(frames)}: {gap:.6g} m")
                frames.append(dict(qpos=q.tolist(),position_m=p.tolist(),
                    quaternion_wxyz=r.as_quat()[[3,0,1,2]].tolist(),clearance_m=gap))
            pa,ra = pb,rb
        return frames

    def tcp_pose(self, q):
        poses = self.fk.solve(q)
        index = self.robot.entity.get_link(self.group.hand_link).idx_local
        p = np.asarray(poses["position_world_m"]).reshape(-1, 3)[index]
        r = rotation(np.asarray(poses["orientation_wxyz"]).reshape(-1, 4)[index])
        return p+r.apply(self.group.tcp_position_in_hand_m), r

    def plan_free_tcp(self, target, *, seed=None, random_seed=0, iterations=12000, goal_seed=None,
                      minimum_clearance=.001):
        """Bidirectional joint-space search for an empty, opened hand.

        Returned dense FK targets are executed through the ordinary EE compiler.
        No robot state is set by this search; actual motion needs its own audit.
        """
        if not np.isfinite(minimum_clearance) or not .0001 <= minimum_clearance <= .01:
            raise ValueError("Free-hand planning clearance must be between 0.1 and 10 mm")
        start = self.seed.copy() if seed is None else np.asarray(seed).copy()
        indices = self.arm_qindices
        limits = np.asarray(self.group.arm_limits_rad)
        rng = np.random.default_rng(random_seed)
        start_margin = float(np.minimum(start[indices]-limits[:,0], limits[:,1]-start[indices]).min())
        corridor_margin = min(.12, start_margin-1e-6)
        if corridor_margin < .02:
            raise ValueError(f"Open-hand transfer starts too close to a joint limit: {start_margin:.6g} rad")
        def full(arm):
            q = start.copy()
            q[indices] = arm
            return q
        def valid(arm, minimum_margin=corridor_margin):
            margin = np.minimum(arm-limits[:,0],limits[:,1]-arm).min()
            return margin >= minimum_margin and self.clearance(full(arm)) >= minimum_clearance
        def edge(a, b):
            count = max(1, int(np.ceil(np.linalg.norm(b-a)/.035)))
            return all(valid(a+u*(b-a)) for u in np.linspace(0,1,count+1)[1:])
        goals = []
        for attempt in range(1 if goal_seed is not None else 96):
            initial = start.copy()
            if goal_seed is not None:
                initial[indices] = np.asarray(goal_seed)[indices]
            elif attempt == 1:
                initial[indices] = np.asarray(self.group.home[:7])
            elif 1 < attempt < 24:
                initial[indices] = np.clip(np.asarray(self.group.home[:7])+rng.normal(0,.6,7),limits[:,0]+.12,limits[:,1]-.12)
            elif attempt:
                initial[indices] = rng.uniform(limits[:,0]+.12, limits[:,1]-.12)
            try:
                q = self.solve(target, initial)
            except ValueError:
                continue
            q[7:] = start[7:]
            if valid(q[indices],.12) and all(np.linalg.norm(q[indices]-old)>.2 for old in goals):
                goals.append(q[indices].copy())
                if len(goals) == 4:
                    break
        if not goals:
            raise ValueError("No collision-free IK goal for open-hand transfer")
        if not valid(start[indices]):
            raise ValueError("Open-hand transfer starts in collision")
        trees = [([start[indices].copy()], [-1]), (goals, [-1]*len(goals))]
        def extend(tree, target):
            nodes, parents = tree
            index = int(np.argmin(np.linalg.norm(np.asarray(nodes)-target, axis=1)))
            delta = target-nodes[index]
            norm = np.linalg.norm(delta)
            new = nodes[index]+delta*min(1., .22/max(norm,1e-12))
            if not edge(nodes[index], new):
                return None, False
            nodes.append(new); parents.append(index)
            return len(nodes)-1, norm <= .22
        def ancestry(tree, index):
            path = []
            while index >= 0:
                path.append(tree[0][index]); index = tree[1][index]
            return list(reversed(path))
        path = None
        for step in range(iterations):
            side = step % 2
            tree, other = trees[side], trees[1-side]
            target_arm = (other[0][rng.integers(len(other[0]))] if rng.random()<.2 else
                          rng.uniform(limits[:,0]+.12, limits[:,1]-.12))
            a, _ = extend(tree, target_arm)
            if a is None:
                continue
            for _ in range(80):
                b, reached = extend(other, tree[0][a])
                if b is None:
                    break
                if reached:
                    left, right = ancestry(tree, a), ancestry(other, b)
                    path = left+list(reversed(right))[1:]
                    if side:
                        path.reverse()
                    break
            if path is not None:
                break
        if path is None:
            raise ValueError("Open-hand collision search exhausted")
        for _ in range(150):
            if len(path)<3:
                break
            a,b = sorted(rng.choice(len(path),2,replace=False))
            if b>a+1 and edge(path[a],path[b]):
                path = path[:a+1]+path[b:]
        rows, elapsed = [], 0.
        previous = path[0]
        for a,b in zip(path,path[1:]):
            count = max(1,int(np.ceil(np.linalg.norm(b-a)/.015)))
            for u in np.linspace(0,1,count+1)[1:]:
                arm = a+u*(b-a)
                elapsed += max(float(np.max(abs(arm-previous)))/.25, .025)
                q = full(arm); p,r = self.tcp_pose(q)
                rows.append(dict(time_s=elapsed,position_m=p.tolist(),quaternion_wxyz=r.as_quat()[[3,0,1,2]].tolist(),qpos=q.tolist()))
                previous = arm
        return rows

    def plan_route(self, route, origin, offset_p, offset_r, *, spacing=.008, beam_width=4, progress=None,
                   diagnostic_progress=None, preserve_roll_sectors=False, orientation_guides=(),
                   lattice_search=False, lattice_step_deg=15., world_orientation_neighbors=False,
                   reverse_search=False, start_progress=0., end_progress=1., initial_orientation_wxyz=None,
                   curve_positions=False):
        """Search continuous ring roll; every retained pose passes native IK/FK.

        This is a candidate generator. Actual actions and substep contacts still
        require an independent simulator run. Imported mesh checks are sampled.
        """
        if not 0 <= start_progress < end_progress <= 1:
            raise ValueError("Route search requires an increasing subinterval of [0,1]")
        count = int(np.ceil((route.length-2*route.layout.end_reserve_m)*(end_progress-start_progress)/spacing))+1
        if lattice_search and world_orientation_neighbors:
            raise ValueError("A finite Euler lattice and world orientation neighbors are separate searches")
        limits = np.asarray(self.group.arm_limits_rad)
        beam = [dict(cost=0., q=self.seed, angles=np.zeros(3), frames=[])]
        values = np.linspace(start_progress, end_progress, count) if diagnostic_progress is None else [diagnostic_progress]
        if reverse_search:
            values = values[::-1]
        for index, u in enumerate(values):
            previous_beam = beam
            p, quaternion = route.pose(float(u))
            p = p+origin
            base = rotation(quaternion)
            candidates = []
            wand_gaps = {}
            best_by_angle = {}
            rejects = dict(wand=0, ik=0, joint=0, robot=0)
            for parent in sorted(beam,key=lambda row:row["cost"]):
                step = lattice_step_deg if lattice_search else 15.
                angles = ([np.array([angle, tilt, 0.]) for angle in np.arange(-180, 180, 30.)
                           for tilt in (-60., -30., 0., 30., 60.)] if index == 0 else
                          [parent["angles"]+delta for delta in
                           ([0,0,0], [-step,0,0], [step,0,0], [0,-step,0], [0,step,0], [0,0,-step], [0,0,step])])
                if index == 0 and (diagnostic_progress is not None or preserve_roll_sectors or lattice_search or reverse_search):
                    angles = [np.array([a,b,c]) for a in np.arange(-180,180,30.)
                              for b in (-60.,-30.,0.,30.,60.) for c in (-60.,-30.,0.,30.,60.)]
                orientation_candidates = [(angle,False) for angle in angles]
                if index == 0 and initial_orientation_wxyz is not None:
                    orientation_candidates.append(((base.inv()*rotation(initial_orientation_wxyz)).as_euler("zyx",degrees=True),True))
                if index and world_orientation_neighbors:
                    previous_r = rotation(parent["frames"][-1]["quaternion_wxyz"])
                    for delta in ([0,0,0],[-15,0,0],[15,0,0],[0,-15,0],[0,15,0],[0,0,-15],[0,0,15]):
                        candidate_r = previous_r*Rotation.from_rotvec(np.radians(delta))
                        orientation_candidates.append(((base.inv()*candidate_r).as_euler("zyx",degrees=True),True))
                for angle, transported in orientation_candidates:
                    if lattice_search:
                        angle[0] = (angle[0]+180)%360-180
                    if not transported and np.max(abs(angle[1:])) > 75:
                        continue
                    r = base*Rotation.from_euler("zyx", angle, degrees=True)
                    key = tuple(angle)
                    if lattice_search and key in best_by_angle and parent["cost"] >= best_by_angle[key]["cost"]:
                        continue
                    if key not in wand_gaps:
                        wand_gaps[key] = self.wand_clearance((p,r))
                    if wand_gaps[key] < .001:
                        rejects["wand"] += 1
                        continue
                    try:
                        q = self.solve((p+r.apply(offset_p), r*offset_r), parent["q"])
                    except ValueError:
                        rejects["ik"] += 1
                        continue
                    margin = float(np.minimum(q[self.arm_qindices]-limits[:,0], limits[:,1]-q[self.arm_qindices]).min())
                    if margin < .005:
                        rejects["joint"] += 1
                        continue
                    gap = min(wand_gaps[key],self.clearance(q))
                    if gap < .001:
                        rejects["robot"] += 1
                        continue
                    delta = q[self.arm_qindices]-parent["q"][self.arm_qindices]
                    cost = parent["cost"]+np.dot(delta, delta)+.003/(margin+.02)+.00001/(gap+.001)
                    if index:
                        if world_orientation_neighbors:
                            cost += .00003*float(np.degrees((r*previous_r.inv()).magnitude())**2)
                        else:
                            angle_delta = angle-parent["angles"]
                            angle_delta[0] = (angle_delta[0]+180)%360-180
                            cost += .00003*float(np.sum(angle_delta**2))
                    frame = dict(progress=float(u), position_m=p.tolist(), quaternion_wxyz=r.as_quat()[[3,0,1,2]].tolist(),
                                 qpos=q.tolist(), local_zyx_deg=angle.tolist(), clearance_m=gap, joint_margin_rad=margin,
                                 use_joint_seed=True)
                    if diagnostic_progress is not None:
                        frame["scope"] = "isolated_pose_candidate_not_a_route"
                    rank = cost
                    for guide in orientation_guides:
                        weight = max(0.,1-abs(u-guide["progress"])/guide.get("window",.2))**2
                        difference = angle-np.asarray(guide["local_zyx_deg"])
                        difference[0] = (difference[0]+180)%360-180
                        if world_orientation_neighbors:
                            guide_r = base*Rotation.from_euler("zyx",guide["local_zyx_deg"],degrees=True)
                            rank += .003*weight*float(np.degrees((r*guide_r.inv()).magnitude())**2)
                        else:
                            rank += .003*weight*float(np.dot(difference,difference))
                    candidate = dict(cost=float(cost), rank=float(rank), q=q, angles=angle, orientation=r,
                                     frames=parent["frames"]+[frame])
                    candidates.append(candidate)
                    if key not in best_by_angle or cost < best_by_angle[key]["cost"]:
                        best_by_angle[key] = candidate
            candidates.sort(key=lambda row: row["rank"])
            # Reserve candidates across roll sectors. A single cost-sorted
            # beam otherwise collapses to neighboring poses long before a
            # later bend requires a different handle direction.
            beam = []
            if not preserve_roll_sectors:
                for candidate in candidates:
                    if all((np.degrees((candidate["orientation"]*old["orientation"].inv()).magnitude()) > 5
                            if world_orientation_neighbors else np.linalg.norm(candidate["angles"]-old["angles"]) > 5) or
                           np.linalg.norm(candidate["q"]-old["q"]) > .25 for old in beam):
                        beam.append(candidate)
                    if len(beam) == beam_width:
                        break
            sectors = {}
            for candidate in (candidates if preserve_roll_sectors else ()):
                sector = int(np.floor((candidate["angles"][0]+15)/30)) % 12
                bucket = sectors.setdefault(sector, [])
                if all(np.linalg.norm(candidate["angles"][1:]-old["angles"][1:]) >= 25 or
                       np.linalg.norm(candidate["q"]-old["q"]) > .5 for old in bucket):
                    bucket.append(candidate)
            ordered = sorted(sectors.values(),key=lambda rows: rows[0]["rank"])
            for level in range(beam_width):
                for bucket in ordered:
                    if len(bucket)>level:
                        beam.append(bucket[level])
                    if len(beam)==beam_width:
                        break
                if len(beam)==beam_width:
                    break
            if lattice_search:
                beam = sorted(best_by_angle.values(),key=lambda row:row["cost"])
            if progress:
                progress(dict(index=index, count=count, progress=float(u), candidates=len(candidates),
                              rejects=rejects,
                              isolated_candidates=([candidate["frames"][-1] for candidate in candidates]
                                                   if diagnostic_progress is not None else []),
                              last_reachable=([parent["frames"][-1] for parent in previous_beam if parent["frames"]]
                                              if not beam else []),
                              best=None if not beam else beam[0]["frames"][-1]))
            if not beam:
                raise ValueError(f"No collision-free IK candidate at route progress {u:.6f}")
        frames = beam[0]["frames"]
        frames = frames[::-1] if reverse_search else frames
        if progress:
            progress(dict(stage="coarse_complete",progress=float(values[-1]),complete_frames=frames))
        if curve_positions and diagnostic_progress is None:
            curved = [frames[0]]
            seed = np.asarray(frames[0]["qpos"])
            for a,b in zip(frames,frames[1:]):
                ra,rb = rotation(a["quaternion_wxyz"]),rotation(b["quaternion_wxyz"])
                turns = Slerp([0,1],Rotation.from_quat([ra.as_quat(),rb.as_quat()]))
                bound = (b["progress"]-a["progress"])*(route.length-2*route.layout.end_reserve_m)+.18*(rb*ra.inv()).magnitude()
                for fraction in np.linspace(0,1,max(1,int(np.ceil(bound/.001)))+1)[1:]:
                    u = a["progress"]+fraction*(b["progress"]-a["progress"])
                    p,_ = route.pose(u)
                    p,r = p+origin,turns(fraction)
                    reference = (1-fraction)*np.asarray(a["qpos"])+fraction*np.asarray(b["qpos"])
                    seed = self.solve((p+r.apply(offset_p),r*offset_r),reference)
                    curved.append(dict(progress=float(u),position_m=p.tolist(),
                        quaternion_wxyz=r.as_quat()[[3,0,1,2]].tolist(),qpos=seed.tolist(),use_joint_seed=True))
            frames = curved
            if progress:
                progress(dict(stage="curved_complete",progress=float(values[-1]),complete_frames=frames))
        return frames

    def refine(self, frames, offset_p, offset_r, *, maximum_material_step=.002, preserve_joint_seeds=False):
        """Check interpolation interiors with new IK, not just coarse endpoints."""
        result = [frames[0]]
        seed = np.asarray(frames[0]["qpos"])
        for a, b in zip(frames, frames[1:]):
            pa, pb = np.asarray(a["position_m"]), np.asarray(b["position_m"])
            ra, rb = rotation(a["quaternion_wxyz"]), rotation(b["quaternion_wxyz"])
            turn = Slerp([0,1], Rotation.from_quat([ra.as_quat(), rb.as_quat()]))
            bound = np.linalg.norm(pb-pa)+.18*(rb*ra.inv()).magnitude()
            count = max(1, int(np.ceil(bound/maximum_material_step)))
            for u in np.linspace(0, 1, count+1)[1:]:
                p, r = pa+u*(pb-pa), turn(u)
                guided = preserve_joint_seeds or a.get("use_joint_seed",False) or b.get("use_joint_seed",False)
                if guided:
                    seed = (1-u)*np.asarray(a["qpos"])+u*np.asarray(b["qpos"])
                seed = self.solve((p+r.apply(offset_p), r*offset_r), seed)
                gap = self.clearance(seed, (p, r))
                if gap < .0005:
                    raise ValueError(f"Interpolated collision near {a['progress']:.5f}: {gap:.6g} m")
                result.append(dict(progress=a["progress"]+u*(b["progress"]-a["progress"]),
                    position_m=p.tolist(), quaternion_wxyz=r.as_quat()[[3,0,1,2]].tolist(),
                    qpos=seed.tolist(), clearance_m=gap,use_joint_seed=guided))
        return result

    def joint_references(self, frames, offset_p, offset_r, *, maximum_joint_step=.005,
                         joint_speed=.25, translation_speed=.012, rotation_speed=.35,
                         allow_wand_support=False):
        """Sample the joint curve and derive its reachable body poses with FK.

        Cartesian chords between two IK solutions can leave the reachable
        workspace. These references preserve the checked joint curve instead.
        They still require actual physical execution and contact auditing.
        """
        first = np.asarray(frames[0]["qpos"],float).copy()
        first[7:] = self.seed[7:]
        def body(q):
            p,r = self.tcp_pose(q)
            r = r*offset_r.inv()
            return p-r.apply(offset_p),r
        p,r = body(first)
        result = [dict(time_s=0.,qpos=first.tolist(),position_m=p.tolist(),
                       quaternion_wxyz=r.as_quat()[[3,0,1,2]].tolist())]
        elapsed,previous_q,previous_p,previous_r = 0.,first,p,r
        for a,b in zip(frames,frames[1:]):
            qa,qb = np.asarray(a["qpos"]),np.asarray(b["qpos"])
            count = max(1,int(np.ceil(np.linalg.norm(qb[:7]-qa[:7])/maximum_joint_step)))
            for u in np.linspace(0,1,count+1)[1:]:
                q = qa+u*(qb-qa)
                q[7:] = self.seed[7:]
                p,r = body(q)
                gap = self.clearance(q,(p,r),allow_wand_support=allow_wand_support)
                if gap < .0005:
                    raise ValueError(f"Joint reference collision at sample {len(result)}: {gap:.6g} m")
                elapsed += max(float(np.max(abs(q[:7]-previous_q[:7])))/joint_speed,
                               float(np.linalg.norm(p-previous_p))/translation_speed,
                               float((r*previous_r.inv()).magnitude())/rotation_speed,.00625)
                result.append(dict(time_s=elapsed,qpos=q.tolist(),position_m=p.tolist(),
                                   quaternion_wxyz=r.as_quat()[[3,0,1,2]].tolist(),clearance_m=gap))
                previous_q,previous_p,previous_r = q,p,r
        return result
