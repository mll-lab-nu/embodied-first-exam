"""Read-only ALOHA kinematics and collision checks for Rope Threading plans.

A CPU Genesis scene with the shared tabletop and both arms is built once; no
physics tick is ever taken. Rings, stands and bases come from the frozen task
geometry; the rope tube of the current follow-the-leader state is an obstacle
for every link except the fingers of the hand that holds it.
"""
import fcl
import numpy as np
from scipy.spatial.transform import Rotation, Slerp

from topogym.planning.buzz_wire_3d.kinematics import mesh_object, manager, distance
from topogym.solvers.genesis_kinematics import GenesisFKSolver, GenesisIKSolver
from topogym.utils.arrays import to_numpy
from topogym.utils.geometry.rope import make_elastic_tube_mesh

BASE_LINKS = {"base_link", "waist_link", "shoulder_link"}
FINGER_LINKS = {"left_finger_link", "right_finger_link"}


def contact_depth(first, second):
    """Maximum FCL contact depth estimate, or infinity for incomplete data.

    Used only by explicitly relaxed planning checks. Native contact solving
    still governs execution; triangle contact depth is a geometric estimate.
    """
    request = fcl.CollisionRequest(num_max_contacts=10000, enable_contact=True)
    result = fcl.CollisionResult()
    if isinstance(first, fcl.CollisionObject):
        fcl.collide(first, second, request, result)
    else:
        data = fcl.CollisionData(request=request, result=result)
        first.collide(second, data, fcl.defaultCollisionCallback)
        result = data.result
    depths = np.asarray([c.penetration_depth for c in result.contacts], float)
    if not len(depths) or len(depths) >= 10000 or not np.isfinite(depths).all():
        return float("inf")
    return max(0., float(depths.max()))


def _bvh(mesh_or_vf):
    if isinstance(mesh_or_vf, tuple):
        vertices, faces = mesh_or_vf
    else:
        vertices, faces = mesh_or_vf.vertices, mesh_or_vf.faces
    model = fcl.BVHModel()
    model.beginModel(len(vertices), len(faces))
    model.addSubModel(np.asarray(vertices, float), np.asarray(faces, dtype=np.int32))
    model.endModel()
    return fcl.CollisionObject(model)


def frame_from_axes(x, z):
    x = np.asarray(x, float); x = x/np.linalg.norm(x)
    z = np.asarray(z, float); z = z-x*(x@z); z = z/np.linalg.norm(z)
    return Rotation.from_matrix(np.column_stack([x, np.cross(z, x), z]))


def grasp_orientation(tangent, family, roll_rad):
    """TCP rotation for a rope pinched at a station.

    across: rope runs along the gripper z axis (pinched across the pads), the
    approach axis x is rolled about the rope from pointing down.
    along: fingers point against the tip direction (x = -tangent), the
    closing axis y is rolled about the rope from horizontal.
    """
    t = np.asarray(tangent, float); t = t/np.linalg.norm(t)
    down = np.array([0., 0., -1.])
    reference = down-t*(t@down)
    if np.linalg.norm(reference) < 1e-6:
        reference = np.array([1., 0., 0.])-t*(t@[1., 0., 0.])
    reference /= np.linalg.norm(reference)
    turned = Rotation.from_rotvec(roll_rad*t).apply(reference)
    if family == "across":
        return frame_from_axes(turned, t)
    if family in ("along", "along_lead"):
        # along: fingers point against the tip (x = -t); along_lead: fingers
        # point towards the tip (x = +t). y is the rolled reference, z = x cross y.
        x = -t if family == "along" else t
        y = turned-x*(x@turned); y /= np.linalg.norm(y)
        return Rotation.from_matrix(np.column_stack([x, y, np.cross(x, y)]))
    raise ValueError("Unknown grasp family")


def track_orientation(previous, tangent):
    """Minimal reorientation keeping the closing axis y perpendicular to the rope.

    The rope may run anywhere in the pad plane (x-z), so only y is constrained.
    """
    t = np.asarray(tangent, float); t = t/np.linalg.norm(t)
    x0, y0 = previous.apply([1., 0., 0.]), previous.apply([0., 1., 0.])
    y = y0-t*(t@y0)
    if np.linalg.norm(y) < 1e-6:
        y = np.cross(t, x0)
    y /= np.linalg.norm(y)
    x = x0-y*(y@x0)
    if np.linalg.norm(x) < 1e-6:
        x = np.cross(y, t)
    x /= np.linalg.norm(x)
    return Rotation.from_matrix(np.column_stack([x, y, np.cross(x, y)]))


def track_material_orientation(previous, tangent, family):
    """Parallel-transport the material axis captured by a finite grasp band.

    Constraining only the closing axis lets the reference rope turn inside the
    pad plane while the real assisted material patch keeps its local direction.
    """
    local = {"across": [0., 0., 1.], "along": [-1., 0., 0.], "along_lead": [1., 0., 0.]}[family]
    before = previous.apply(local)
    after = np.asarray(tangent, float)/np.linalg.norm(tangent)
    axis = np.cross(before, after)
    sine, cosine = np.linalg.norm(axis), np.clip(before@after, -1., 1.)
    if sine < 1e-10:
        turn = Rotation.identity() if cosine > 0 else Rotation.from_rotvec(np.pi*previous.apply([0., 1., 0.]))
    else:
        turn = Rotation.from_rotvec(axis/sine*np.arctan2(sine, cosine))
    return turn*previous


class RopeThreadingKinematics:
    def __init__(self, problem, *, seed=0):
        import genesis as gs
        from omegaconf import OmegaConf
        from topogym.config.scene import load_scene_config
        from topogym.simulator.config import SimulatorConfig
        from topogym.world.tabletop import StandardTabletopSceneBuilder
        from topogym.robot.joint_position import JointPositionRobot
        config = SimulatorConfig(task_id="rope_threading", variation_id=problem.identity["variation_id"],
                                 task_parameters=problem.identity.get("task_parameters", {}),
                                 enable_rgb=False, compute_backend="cpu")
        scene_config = load_scene_config(config)
        if not getattr(gs, "_initialized", False):
            gs.init(backend=gs.cpu, precision="64", seed=int(seed), logging_level="warning")
        env_cfg = OmegaConf.create(OmegaConf.to_container(scene_config.env, resolve=True))
        env_cfg.cameras = {}
        builder = StandardTabletopSceneBuilder(env_cfg, scene_config.robot_control,
                                               rigid_options=gs.options.RigidOptions())
        base = builder.create(show_viewer=False, include_robot=True,
                              robot_material=gs.materials.Rigid(gravity_compensation=1.0))
        base.scene.build()
        self.scene = base.scene
        self.entity = base.entity_registry.entities["robot"]
        self.robot = JointPositionRobot(self.entity, scene_config.robot_control)
        self.robot.reset_home()
        self.problem = problem
        self.table_height = float(problem.table_height_m)
        self.fk, self.ik = GenesisFKSolver(self.entity), GenesisIKSolver(self.entity)
        self.home = to_numpy(self.entity.get_qpos()).reshape(-1).copy()
        self.limits = {side: np.asarray(g.arm_limits_rad) for side, g in self.robot.groups.items()}
        pose = self.fk.solve(self.home)
        ps = np.asarray(pose["position_world_m"]).reshape(-1, 3)
        rs = Rotation.from_quat(np.asarray(pose["orientation_wxyz"]).reshape(-1, 4)[:, [1, 2, 3, 0]])
        self.link_names = [link.name for link in self.entity.links]
        self.shapes = []   # (side, short link name, link index, local vertices, fcl object)
        by_geom = {}
        pads = {side: [] for side in self.robot.groups}
        for link in self.entity.links:
            side, _, short = link.name.partition("/")
            for geom in link.geoms:
                world = to_numpy(geom.get_verts()).reshape(-1, 3)
                local = rs[link.idx_local].inv().apply(world-ps[link.idx_local])
                obj = mesh_object(local, geom.init_faces)
                self.shapes.append((side, short, link.idx_local, local, obj))
                by_geom[int(geom.idx)] = (side, short, obj)
                if short in FINGER_LINKS and len(world) <= 200:
                    pads[side].append(world.mean(axis=0))   # contact spheres on the pads
        valid = self.scene.sim.rigid_solver.collider._valid_collision_pairs
        self.self_pairs = [(by_geom[int(a)], by_geom[int(b)]) for a, b in valid
                           if int(a) in by_geom and int(b) in by_geom and by_geom[int(a)][0] == by_geom[int(b)][0]]
        self.by_arm = {side: manager([x[4] for x in self.shapes if x[0] == side]) for side in self.robot.groups}
        self.fingers = {side: manager([x[4] for x in self.shapes if x[0] == side and x[1] in FINGER_LINKS])
                        for side in self.robot.groups}
        self.finger_fixture_only = problem.identity.get("task_parameters", {}).get("rope_robot_contact", "full") == "fingers"
        self.finger_rope_only = self.finger_fixture_only
        self.nonfinger = {side: manager([x[4] for x in self.shapes if x[0] == side and x[1] not in FINGER_LINKS])
                          for side in self.robot.groups}
        self.nonhand = {side: manager([x[4] for x in self.shapes if x[0] == side
                                       and x[1] not in FINGER_LINKS | {"gripper_base"}]) for side in self.robot.groups}
        self.fixtures = manager([_bvh(problem.fixtures)])
        from .geometry import _fixture_meshes
        meshes, names = _fixture_meshes(problem.layout, problem.table_height_m)
        self.named_fixtures = [(name, manager([_bvh(mesh)])) for name, mesh in zip(names, meshes)]
        self.risers = manager([_bvh(mesh) for mesh in problem.risers])
        self.above_base = manager([x[4] for x in self.shapes if x[1] != "base_link"])
        # Pad centre relative to the TCP site, expressed in the TCP frame (per side).
        self.pad_offset = {}
        for side, group in self.robot.groups.items():
            hand = self.link_names.index(group.hand_link)
            tcp = ps[hand]+rs[hand].apply(group.tcp_position_in_hand_m)
            centre = np.mean(pads[side], axis=0) if pads[side] else tcp
            self.pad_offset[side] = rs[hand].inv().apply(centre-tcp)
        self.rope = None
        self.jacobian_check = {side: self.verify_jacobian(side) for side in self.robot.groups}

    # ----- rope obstacle -------------------------------------------------
    def set_rope(self, points):
        vertices, faces = make_elastic_tube_mesh(np.asarray(points), radius=self.problem.rope_radius_m, radial_segments=12)
        self.rope = manager([_bvh((vertices, faces))])

    # ----- IK ------------------------------------------------------------
    def tcp_pose(self, q, side):
        group = self.robot.groups[side]
        pose = self.fk.solve(q)
        hand = self.link_names.index(group.hand_link)
        p = np.asarray(pose["position_world_m"]).reshape(-1, 3)[hand]
        r = Rotation.from_quat(np.asarray(pose["orientation_wxyz"]).reshape(-1, 4)[hand][[1, 2, 3, 0]])
        return p+r.apply(group.tcp_position_in_hand_m), r*Rotation.from_quat(np.roll(group.tcp_orientation_in_hand_wxyz, -1))

    def hand_target(self, side, tcp):
        p, r = tcp
        group = self.robot.groups[side]
        hand_r = r*Rotation.from_quat(np.roll(group.tcp_orientation_in_hand_wxyz, -1)).inv()
        return p-hand_r.apply(group.tcp_position_in_hand_m), hand_r

    def jacobian(self, q, side):
        """World-frame [linear; angular] Jacobian of the hand link at q (6 x 16)."""
        self.entity.set_qpos(np.asarray(q, float))
        link = self.entity.get_link(self.robot.groups[side].hand_link)
        return to_numpy(self.entity.get_jacobian(link)).reshape(6, -1)

    def verify_jacobian(self, side, delta=1e-5):
        q = self.home.copy()
        idx = self.robot._q_indices[side][:6]
        dofs = self.robot._indices[side][:6]
        J = self.jacobian(q, side)[:, dofs]
        hand = self.link_names.index(self.robot.groups[side].hand_link)
        errors = []
        for k in range(6):
            plus, minus = q.copy(), q.copy()
            plus[idx[k]] += delta; minus[idx[k]] -= delta
            a, b = self.fk.solve(plus), self.fk.solve(minus)
            dp = (np.asarray(a["position_world_m"]).reshape(-1, 3)[hand]-np.asarray(b["position_world_m"]).reshape(-1, 3)[hand])/(2*delta)
            ra = Rotation.from_quat(np.asarray(a["orientation_wxyz"]).reshape(-1, 4)[hand][[1, 2, 3, 0]])
            rb = Rotation.from_quat(np.asarray(b["orientation_wxyz"]).reshape(-1, 4)[hand][[1, 2, 3, 0]])
            dr = (ra*rb.inv()).as_rotvec()/(2*delta)
            errors.append(float(np.abs(np.r_[dp, dr]-J[:, k]).max()))
        self.entity.set_qpos(self.home)
        if max(errors) > 1e-3:
            raise RuntimeError(f"Genesis Jacobian convention mismatch: {errors}")
        return errors

    def solve(self, side, tcp, seed, *, limit_margin=.02, iterations=120, damping=.02, max_step=.15,
              position_tolerance_m=1e-4, orientation_tolerance_rad=1e-3):
        """Damped least-squares IK from the seed; minimal joint motion per step.

        Branch continuity is enforced by construction: no random restarts.
        Unreachable poses (from this branch) raise ValueError.
        """
        target_p, target_r = self.hand_target(side, tcp)
        idx = self.robot._q_indices[side][:6]
        dofs = self.robot._indices[side][:6]
        lo, hi = self.limits[side][:, 0]+limit_margin, self.limits[side][:, 1]-limit_margin
        hand = self.link_names.index(self.robot.groups[side].hand_link)
        q = np.asarray(seed, float).copy()
        q[idx] = np.clip(q[idx], lo, hi)
        for _ in range(iterations):
            pose = self.fk.solve(q)
            p = np.asarray(pose["position_world_m"]).reshape(-1, 3)[hand]
            r = Rotation.from_quat(np.asarray(pose["orientation_wxyz"]).reshape(-1, 4)[hand][[1, 2, 3, 0]])
            error = np.r_[target_p-p, (target_r*r.inv()).as_rotvec()]
            if np.linalg.norm(error[:3]) < position_tolerance_m and np.linalg.norm(error[3:]) < orientation_tolerance_rad:
                self.entity.set_qpos(self.home)
                return q
            J = self.jacobian(q, side)[:, dofs]
            step = J.T@np.linalg.solve(J@J.T+damping**2*np.eye(6), error)
            scale = max(1., np.abs(step).max()/max_step)
            q[idx] = np.clip(q[idx]+step/scale, lo, hi)
        self.entity.set_qpos(self.home)
        raise ValueError(f"IK failed: residual position {np.linalg.norm(error[:3]):.4g} m, orientation {np.linalg.norm(error[3:]):.4g} rad")

    # ----- checks --------------------------------------------------------
    def check(self, q, *, holding=None, margin_m=.005, rope_margin_m=.003, inter_arm_m=.01,
              max_penetration_m=0.):
        """Geometric checks at one joint configuration. holding: side(s) pinching the rope."""
        holding = set() if holding is None else ({holding} if isinstance(holding, str) else set(holding))
        pose = self.fk.solve(q)
        ps = np.asarray(pose["position_world_m"]).reshape(-1, 3)
        rs = Rotation.from_quat(np.asarray(pose["orientation_wxyz"]).reshape(-1, 4)[:, [1, 2, 3, 0]])
        table = float("inf")
        for side, short, index, local, obj in self.shapes:
            obj.setTransform(fcl.Transform(rs[index].as_matrix(), ps[index]))
            if short not in BASE_LINKS:
                table = min(table, float((rs[index].apply(local)+ps[index])[:, 2].min()-self.table_height))
        for m in (*self.by_arm.values(), *self.nonfinger.values(), *self.nonhand.values(), *self.fingers.values()):
            m.update()
        self.above_base.update()
        issues, detail = [], {}
        def below(gap, margin, first, second, label):
            if gap >= margin:
                return False
            if gap < 0 and max_penetration_m > 0:
                depth = contact_depth(first, second)
                if depth <= max_penetration_m:
                    detail.setdefault("allowed_contacts", []).append(dict(pair=label, estimated_depth_m=depth))
                    return False
                detail.setdefault("rejected_contacts", []).append(dict(pair=label, estimated_depth_m=depth))
            return True
        self_hits = []
        for a, b in self.self_pairs:
            if fcl.collide(a[2], b[2], fcl.CollisionRequest(), fcl.CollisionResult()):
                if below(-1., 0., a[2], b[2], f"{a[0]}/{a[1]}:{b[1]}"):
                    self_hits.append([a[1], b[1], a[0]])
        if self_hits:
            issues.append("same_arm_collision"); detail["self_collisions"] = self_hits
        detail["table_clearance_m"] = table
        if table < (-max_penetration_m if max_penetration_m > 0 else .0005):
            issues.append("table")
        arms = distance(self.by_arm["left"], self.by_arm["right"])
        detail["inter_arm_m"] = arms
        if below(arms, inter_arm_m, self.by_arm["left"], self.by_arm["right"], "inter_arm"):
            issues.append("inter_arm")
        # Fixed base links intentionally rest on these task-authored risers.
        riser_gap = distance(self.above_base, self.risers)
        detail["riser_clearance_m"] = riser_gap
        if below(riser_gap, .0005, self.above_base, self.risers, "base_riser"):
            issues.append("base_riser")
        for side in self.by_arm:
            fixture_arm = self.fingers[side] if self.finger_fixture_only else self.by_arm[side]
            detail["fixture_contact_links"] = "fingers" if self.finger_fixture_only else "all"
            gap = distance(fixture_arm, self.fixtures)
            detail[side+"_fixture_m"] = gap
            if below(gap, margin_m, fixture_arm, self.fixtures, side+"/fixtures"):
                issues.append(side+"/fixtures")
                detail[side+"_near_fixtures"] = {name: measured for name, fixture in self.named_fixtures
                    if (measured := distance(fixture_arm, fixture)) < margin_m}
            if self.rope is not None and not (self.finger_rope_only and side in holding):
                checked = (self.fingers[side] if self.finger_rope_only else
                           self.nonhand[side] if side in holding else self.by_arm[side])
                gap = distance(checked, self.rope)
                detail[side+"_rope_m"] = gap
                if below(gap, rope_margin_m, checked, self.rope, side+"/rope"):
                    issues.append(side+"/rope")
                if side in holding and not self.finger_rope_only:
                    base = manager([x[4] for x in self.shapes if x[0] == side and x[1] == "gripper_base"])
                    base_gap = distance(base, self.rope)
                    detail[side+"_gripper_base_rope_m"] = base_gap
                    if below(base_gap, 0., base, self.rope, side+"/gripper_base_rope"):
                        issues.append(side+"/gripper_base_rope")
        for side, limits in self.limits.items():
            joints = q[self.robot._q_indices[side][:6]]
            if np.any(joints < limits[:, 0]) or np.any(joints > limits[:, 1]):
                issues.append(side+"/joint_limits")
        return dict(passed=not issues, issues=issues, **detail)


def interpolate_pose(a, b, u):
    p = a[0]+u*(b[0]-a[0])
    r = Slerp([0., 1.], Rotation.concatenate([a[1], b[1]]))(u)
    return p, r
