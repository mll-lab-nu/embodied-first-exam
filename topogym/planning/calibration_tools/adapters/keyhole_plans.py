"""Keyhole TCP waypoint planning using existing native IK/FK and mesh queries.

This adapter accepts a supplied route; it does not search for a puzzle solution.
All collision results are sampled candidates, not continuous/physical proofs.
"""
from copy import deepcopy

import numpy as np

from ..contracts import UnsupportedCapability, digest, json_value, positive_int
from ..tracking import pose, pose_dict, pose_error, relative, tcp_pose


def densify(points, steps, maximum=10000):
    points = np.asarray(points, dtype=float)
    if points.ndim != 2 or not len(points) or not np.isfinite(points).all():
        raise ValueError("Finite complete joint samples required")
    result, indices = [points[0].tolist()], [0]
    for previous, current in zip(points, points[1:]):
        n = max(1, int(np.ceil(np.max(np.abs(current-previous)/steps))))
        if len(result)+n > maximum:
            raise ValueError("Path exceeds 10000 samples; split into declared phases")
        result.extend((previous+(current-previous)*u/n).tolist() for u in range(1, n+1))
        indices.append(len(result)-1)
    return result, indices


class KeyholeTCPAdapter:
    required_coverage = ("joint_limits", "branch_continuity", "tcp_residual", "robot_mesh_samples",
                         "carried_mesh_samples", "piece_pair_samples", "entry_and_joins")

    def __init__(self, owner):
        if owner.config.task_id != "cast_keyhole":
            raise UnsupportedCapability("keyhole_tcp requires Cast Keyhole; supply a task adapter for other tasks")
        self.owner, self.env, self.robot = owner, owner.env, owner.env._robot
        self.names = [None]*int(self.robot.entity.n_qs)
        self.arm_indices, self.finger_indices = [], []
        for side, group in self.robot.groups.items():
            for index, name in zip(self.robot._q_indices[side], group.arm_joints+group.finger_joints):
                self.names[index] = name
            self.arm_indices.extend(self.robot._q_indices[side][:len(group.arm_joints)])
            self.finger_indices.extend(self.robot._q_indices[side][len(group.arm_joints):])
        if any(n is None for n in self.names):
            raise UnsupportedCapability("Native adapter requires a fixed-base scalar-joint robot")
        self._audit = None

    def _request(self, request):
        allowed = {"tcp_path", "grasps", "object_path", "allowed_contacts", "allowed_body_contacts",
                   "max_joint_step_rad", "max_finger_step_m", "max_branch_jump_rad", "max_repair_waypoints",
                   "tcp_tolerance_m", "tcp_tolerance_rad", "object_tolerance_m", "object_tolerance_rad", "phase"}
        if not isinstance(request, dict) or set(request)-allowed:
            raise ValueError("Unknown keyhole_tcp request field")
        positive_int(len(request["tcp_path"]), "tcp_path", 1000)
        for targets in request["tcp_path"]:
            if not targets or not set(targets) <= self.robot.groups.keys():
                raise ValueError("Each TCP waypoint maps robot sides to complete world poses")
            for target in targets.values():
                pose(target)
        for key, default in (("max_joint_step_rad", .025), ("max_finger_step_m", .001),
                             ("max_branch_jump_rad", .35), ("tcp_tolerance_m", 1e-4),
                             ("tcp_tolerance_rad", 1e-3), ("object_tolerance_m", 1e-4),
                             ("object_tolerance_rad", 1e-3)):
            value = request.get(key, default)
            if isinstance(value, bool) or not np.isfinite(value) or value <= 0:
                raise ValueError(key+" must be positive and finite")
        grasps = request.get("grasps", {})
        if not set(grasps) <= self.robot.groups.keys() or not set(grasps.values()) <= {"keyhole_gold", "keyhole_silver"}:
            raise ValueError("grasps maps sides to Keyhole rigid pieces")
        if len(set(grasps.values())) != len(grasps):
            raise UnsupportedCapability("Two hands bound to one piece require a closed-chain adapter")
        if "object_path" in request:
            if len(request["object_path"]) != len(request["tcp_path"]):
                raise ValueError("object_path and tcp_path must have matching waypoints")
            for row in request["object_path"]:
                if not set(row) <= {"keyhole_gold", "keyhole_silver"}:
                    raise ValueError("Unknown object_path entity")
                for target in row.values():
                    pose(target)
        return request

    def identity(self, request):
        self._request(request)
        metadata = json_value(self.env.episode_metadata)
        # Session IDs/temporary output paths are not geometric dependencies.
        geometry = {k: metadata[k] for k in ("task_id", "instance_id", "model_revision",
                    "variation_resource_sha256", "asset_sha256", "scene_variation")}
        config = json_value(self.owner.config)
        config.pop("work_dir", None)
        return dict(geometry=digest(geometry), joints=digest(dict(robot=self.env.action_spec,
            source=self.owner.evidence.source, names=self.names, grasps=request.get("grasps", {}))),
            execution=digest(dict(config=config, timing=json_value(self.env.timing_spec))))

    def snapshot(self, request):
        from topogym.utils.arrays import to_numpy
        world = self.env._world.read_state()
        robot = self.robot.observe()
        objects = {n: {k: world["bodies"][n][k] for k in ("position_m", "quaternion_wxyz")}
                   for n in ("keyhole_gold", "keyhole_silver")}
        grasp_state = (world.get("grasp") or {}).get("hands", {})
        measured_holding = {side: hand["binding"]["target"][0] for side, hand in grasp_state.items()
            if hand.get("phase") == "holding" and (hand.get("binding") or {}).get("target")}
        if measured_holding != request.get("grasps", {}):
            raise UnsupportedCapability("Declare every measured holding binding in request.grasps")
        grasps = {}
        for side, name in request.get("grasps", {}).items():
            # A transform inferred from proximity is not a confirmed grasp.
            hand = grasp_state.get(side, {})
            if hand.get("phase") != "holding" or (hand.get("binding") or {}).get("target", [None])[0] != name:
                raise UnsupportedCapability("Carried-piece cache requires a measured holding binding: "+side)
            grasps[side] = relative(objects[name], tcp_pose(robot[side]))
        from ..inspection import contact_summary
        contacts = contact_summary(world, self.env._world.entities)
        pairs = sorted({tuple(sorted((str(row["a"]), str(row["b"]))))
                        for row in contacts["contacts"]})
        binding = {side: dict(phase=hand.get("phase"), target=(hand.get("binding") or {}).get("target"))
                   for side, hand in grasp_state.items()}
        return json_value(dict(qpos=to_numpy(self.robot.entity.get_qpos()).reshape(-1), objects=objects,
                               grasps=grasps, contacts=dict(pairs=pairs, grasp=binding)))

    def _steps(self, request):
        steps = np.full(len(self.names), request.get("max_joint_step_rad", .025))
        steps[self.finger_indices] = request.get("max_finger_step_m", .001)
        return steps

    def _make(self, request, seed=None, repair=False):
        from ..kinematics import solve
        self._request(request)
        start = self.snapshot(request)
        q = np.asarray(start["qpos"])
        previous, waypoints = q.copy(), []
        count = len(request["tcp_path"])
        budget = request.get("max_repair_waypoints", 8)
        positive_int(budget, "max_repair_waypoints", 1000)
        if repair and count > budget:
            raise ValueError("Local repair waypoint budget exceeded; full planner required")
        for i, targets in enumerate(request["tcp_path"]):
            if self.owner.cancelled():
                raise InterruptedError("Cancelled between IK queries")
            seeds = [previous.tolist()]
            if seed is not None and i < len(seed.get("waypoint_qpos", [])):
                seeds.insert(0, seed["waypoint_qpos"][i])
            candidates = solve(self.env, targets, seeds)["candidates"]
            candidates = [c for c in candidates if c["accepted"] and
                          np.max(np.abs(np.asarray(c["qpos"])[self.arm_indices]-previous[self.arm_indices]))
                          <= request.get("max_branch_jump_rad", .35)]
            if not candidates:
                raise ValueError(f"No continuous IK candidate at waypoint {i}")
            q = np.asarray(min(candidates, key=lambda c: np.linalg.norm(np.asarray(c["qpos"])-previous))["qpos"])
            # Passive finger coordinates stay measured; IK seeds may originate before grasping.
            q[self.finger_indices] = np.asarray(start["qpos"])[self.finger_indices]
            waypoints.append(q.tolist())
            previous = q
        path, indices = densify([start["qpos"], *waypoints], self._steps(request))
        return dict(identity=self.identity(request), start=start, joint_names=self.names,
                    request=deepcopy(request), qpos=path, waypoint_qpos=waypoints, waypoint_indices=indices[1:],
                    coverage={}, coordinates="native full qpos; world m/unit wxyz; physical body origins",
                    planner="existing calibration native IK with branch check and sampled joint interpolation")

    def plan(self, request, seed=None):
        return self._make(request, seed)

    def repair(self, bundle, request):
        return self._make(request, bundle, repair=True)

    def validate(self, bundle):
        from ..kinematics import RobotGeometry
        from topogym.planning.rigid_reference.geometry import matrix
        from topogym.utils.arrays import to_numpy
        from topogym.solvers.collision.triangle_meshes import TriangleMeshPair
        import trimesh

        request = self._request(bundle["request"])
        if bundle["joint_names"] != self.names:
            return dict(passed=False, coverage=[], reason="joint_order_changed")
        current = self.snapshot(request)
        path = np.asarray(bundle["qpos"], dtype=float)
        if path.ndim != 2 or path.shape[1] != len(self.names) or not np.isfinite(path).all():
            raise ValueError("Invalid full qpos route")
        # Validate actual entry as well as every stored/modified join.
        dense, _ = densify([current["qpos"], *path.tolist()], self._steps(request))
        audit = RobotGeometry(self.env)
        pieces = {}
        for name in ("keyhole_gold", "keyhole_silver"):
            p, r = pose(current["objects"][name])
            meshes = [trimesh.Trimesh(r.inv().apply(to_numpy(g.get_verts()).reshape(-1, 3)-p),
                       g.init_faces, process=False) for link in self.env._world.entities[name].links
                      for g in link.geoms if g.contype or g.conaffinity]
            pieces[name] = trimesh.util.concatenate(meshes)
        pair = TriangleMeshPair(tuple(pieces.values()))
        issues, measured_waypoints = [], {}
        # Match stored waypoint indices to dense indices, avoiding float-key rounding.
        _, dense_indices = densify([current["qpos"], *path.tolist()], self._steps(request))
        waypoint_at = {}
        for i, index in enumerate(bundle["waypoint_indices"]):
            if type(index) is not int or not 0 <= index < len(path):
                raise ValueError("Invalid waypoint index")
            waypoint_at.setdefault(dense_indices[index+1], []).append(i)
        max_jump = request.get("max_branch_jump_rad", .35)
        if any(np.max(np.abs(b-a)[self.arm_indices]) > max_jump for a, b in zip(path, path[1:])):
            issues.append(dict(reason="branch_jump"))
        allowed_body = {tuple(sorted(p)) for p in request.get("allowed_body_contacts", [])}
        for index, q in enumerate(dense):
            if self.owner.cancelled():
                return dict(passed=False, coverage=[], reason="cancelled", evaluated_samples=index)
            fk = audit.fk.solve(np.asarray(q))
            pp = np.asarray(fk["position_world_m"]).reshape(-1, 3)
            rr = np.asarray(fk["orientation_wxyz"]).reshape(-1, 4)
            tcps = {}
            for side, group in self.robot.groups.items():
                link = self.robot.entity.get_link(group.hand_link).idx_local
                hp, hr = pose(dict(position_m=pp[link], quaternion_wxyz=rr[link]))
                _, offset_r = pose(dict(position_m=[0, 0, 0], quaternion_wxyz=group.tcp_orientation_in_hand_wxyz))
                tcps[side] = pose_dict(hp+hr.apply(group.tcp_position_in_hand_m), hr*offset_r)
            bodies = deepcopy(current["objects"])
            for side, name in request.get("grasps", {}).items():
                tp, tr = pose(tcps[side])
                gp, gr = pose(current["grasps"][side])
                bodies[name] = pose_dict(tp+tr.apply(gp), tr*gr)
                # Keyhole pieces have a single body link in the frozen native asset.
                if len(self.env._world.entities[name].links) != 1:
                    raise UnsupportedCapability("Carried mesh query requires a single-link piece")
                for label in audit.obstacles._objs:
                    if label.startswith(name+"/"):
                        audit.obstacles.set_transform(label, matrix(*pose(bodies[name])))
            result = audit.check([q], allowed_contacts=request.get("allowed_contacts", ()))
            if not result["passed"]:
                issues.append(dict(sample=index, reason="robot_collision_or_limits", details=result["issues"]))
            gap = pair.clearance(tuple(matrix(*pose(bodies[n])) for n in pieces))
            if gap < 0 and tuple(sorted(pieces)) not in allowed_body:
                issues.append(dict(sample=index, reason="piece_pair_intersection"))
            # Carried-piece vs table/other obstacles, using imported collision cells.
            for name in request.get("grasps", {}).values():
                manager = trimesh.collision.CollisionManager()
                manager.add_object(name, pieces[name], transform=matrix(*pose(bodies[name])))
                _, collisions = manager.in_collision_other(audit.obstacles, return_names=True)
                hits = [(a, b) for a, b in collisions if b.split("/")[0] not in pieces and
                        tuple(sorted((name, b.split("/")[0]))) not in allowed_body]
                if hits:
                    issues.append(dict(sample=index, reason="carried_piece_obstacle", collisions=hits))
            for i in waypoint_at.get(index, []):
                measured_waypoints[i] = (tcps, bodies)
        indices = bundle["waypoint_indices"]
        if len(indices) != len(request["tcp_path"]):
            raise ValueError("Waypoint correspondence is missing")
        for i, index in enumerate(indices):
            tcps, bodies = measured_waypoints[i]
            for side, target in request["tcp_path"][i].items():
                error = pose_error(tcps[side], target)
                if error["translation_m"] > request.get("tcp_tolerance_m", 1e-4) or error["rotation_rad"] > request.get("tcp_tolerance_rad", 1e-3):
                    issues.append(dict(waypoint=i, reason="tcp_residual", side=side, **error))
            for name, target in request.get("object_path", [{}]*len(indices))[i].items():
                error = pose_error(bodies[name], target)
                if error["translation_m"] > request.get("object_tolerance_m", 1e-4) or error["rotation_rad"] > request.get("object_tolerance_rad", 1e-3):
                    issues.append(dict(waypoint=i, reason="object_route_residual", entity=name, **error))
        return dict(passed=not issues, coverage=list(self.required_coverage), issues=issues,
                    evaluated_samples=len(dense), resolution=dict(joint_rad=request.get("max_joint_step_rad", .025),
                    finger_m=request.get("max_finger_step_m", .001)),
                    continuous_certificate=False, physical_success=False, physics_steps=0,
                    scope="sampled native robot/piece meshes, measured rigid grasps; no FEM or independent geometric route certificate")
