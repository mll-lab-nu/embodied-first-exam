"""Sample actual robot and held-link geometry before accepting approximate IK.

Read-only kinematics; no pose setters, stepping, or synthetic Task success.
This is a bounded sampled sweep, not a continuous dynamics certificate.
"""
from dataclasses import dataclass, field
import numpy as np
from scipy.spatial.transform import Rotation

from topogym.solvers.genesis_kinematics import GenesisFKSolver
from topogym.utils.arrays import to_numpy


def joint_samples(start, goal, step_rad=.005):
    start, goal = np.asarray(start, float), np.asarray(goal, float)
    if start.ndim != 1 or start.shape != goal.shape or not np.isfinite([start, goal]).all():
        raise ValueError('Invalid candidate joint path')
    if not np.isfinite(step_rad) or step_rad <= 0:
        raise ValueError('Invalid candidate sampling interval')
    count = max(1, int(np.ceil(np.max(np.abs(goal - start), initial=0.) / step_rad)))
    if count > 1600:
        raise ValueError('Candidate joint path exceeds the bounded sweep budget')
    return (start + u * (goal - start) for u in np.linspace(0., 1., count + 1))


@dataclass
class Shape:
    entity: str
    link: object
    geom_id: int
    vertices: np.ndarray
    obj: object
    offset_p: np.ndarray = field(default_factory=lambda: np.zeros(3))
    offset_r: object = field(default_factory=Rotation.identity)


class SceneCandidateCheck:
    def __init__(self, env):
        import fcl
        self.env, self.robot = env, env._robot
        self.fk = GenesisFKSolver(self.robot.entity)
        self.shapes = []
        positions, rotations = self.frames(to_numpy(self.robot.entity.get_qpos()).reshape(-1))
        for name, entity in env._world.entities.items():
            if not hasattr(entity, 'links'):
                continue  # Soft material stays under native IPC/grasp checks.
            for link in entity.links:
                p, r = ((positions[link.idx_local], rotations[link.idx_local]) if name == 'robot'
                        else self.link_pose(link))
                for geom in link.geoms:
                    vertices = r.inv().apply(to_numpy(geom.get_verts()).reshape(-1, 3) - p)
                    kind = geom.type.name
                    if kind in ('SPHERE', 'BOX', 'PLANE', 'CYLINDER', 'CAPSULE'):
                        data = np.asarray(geom.data, float).reshape(-1)
                        if kind == 'SPHERE':
                            mesh = fcl.Sphere(data[0])
                        elif kind == 'BOX':
                            mesh = fcl.Box(*data[:3])
                        elif kind == 'PLANE':
                            mesh = fcl.Halfspace(data[:3], 0.)
                        elif kind == 'CYLINDER':
                            mesh = fcl.Cylinder(*data[:2])
                        else:
                            mesh = fcl.Capsule(*data[:2])
                        solver = env._world.scene.sim.rigid_solver
                        gp = to_numpy(solver.get_geoms_pos([geom.idx], relative=False)).reshape(3)
                        gr = Rotation.from_quat(to_numpy(solver.get_geoms_quat([geom.idx], relative=False)).reshape(4)[[1, 2, 3, 0]])
                        self.shapes.append(Shape(name, link, int(geom.idx), vertices,
                            fcl.CollisionObject(mesh, fcl.Transform(gr.as_matrix(), gp)),
                            r.inv().apply(gp - p), r.inv() * gr))
                        continue
                    if kind != 'MESH':
                        raise ValueError(f'Unsupported candidate collision primitive: {kind}')
                    faces = np.asarray(geom.init_faces, dtype=np.int32).reshape(-1, 3)
                    if not len(vertices) or not len(faces):
                        raise ValueError(f'Missing candidate collision mesh: {name}/{link.name}')
                    if geom.is_convex:
                        # Use the imported native geometry's convexity flag.
                        # Solid GJK also rejects full containment, unlike BVH
                        # surface intersection. Keep task apertures nonconvex.
                        import trimesh
                        hull = trimesh.convex.convex_hull(vertices)
                        polygons = np.column_stack([np.full(len(hull.faces), 3), hull.faces]).ravel()
                        mesh = fcl.Convex(hull.vertices, len(hull.faces), polygons)
                        self.shapes.append(Shape(name, link, int(geom.idx), vertices,
                            fcl.CollisionObject(mesh, fcl.Transform(r.as_matrix(), p))))
                        continue
                    # Keep apertures; convexifying a ring would fill its hole.
                    mesh = fcl.BVHModel()
                    mesh.beginModel(len(vertices), len(faces))
                    mesh.addSubModel(vertices, faces)
                    mesh.endModel()
                    self.shapes.append(Shape(name, link, int(geom.idx), vertices,
                        fcl.CollisionObject(mesh, fcl.Transform(r.as_matrix(), p))))
        if not any(s.entity == 'robot' for s in self.shapes):
            raise ValueError('No robot geometry for candidate validation')
        self.native_pairs = {tuple(sorted((int(a), int(b)))) for a, b in
            env._world.scene.sim.rigid_solver.collider._valid_collision_pairs}

    @staticmethod
    def link_pose(link):
        return (to_numpy(link.get_pos()).reshape(3),
                Rotation.from_quat(to_numpy(link.get_quat()).reshape(4)[[1, 2, 3, 0]]))

    def frames(self, q):
        frames = self.fk.solve(np.asarray(q, float))
        return (np.asarray(frames['position_world_m']).reshape(-1, 3),
                Rotation.from_quat(np.asarray(frames['orientation_wxyz']).reshape(-1, 4)[:, [1, 2, 3, 0]]))

    def held_links(self, positions, rotations):
        """Model measured rigid grips; this creates no physical attachment.

        Passive rigid oracles have no grasp-manager binding. They require live
        bilateral force evidence before using a carried-link approximation.
        """
        world = self.env._world.read_state()
        hands = world.get('grasp', {}).get('hands', {})
        targets = {}
        for side, state in hands.items():
            binding = state.get('binding')
            if state.get('phase') != 'holding' or not binding:
                continue
            targets[side] = tuple(binding['target'])
        contacts = world.get('contacts', {})
        if contacts and all(k in contacts for k in ('link_a', 'link_b', 'force', 'penetration')):
            a, b = (np.asarray(contacts[k]).reshape(-1) for k in ('link_a', 'link_b'))
            force = np.asarray(contacts['force']).reshape(-1, 3)
            depth = np.asarray(contacts['penetration']).reshape(-1)
            if len({len(a), len(b), len(force), len(depth)}) != 1 or not np.isfinite(force).all() or not np.isfinite(depth).all():
                raise ValueError('Invalid measured contact evidence for IK candidate')
            touched = {int(finger): {int(y) if int(x) == int(finger) else int(x)
                for x, y, f, d in zip(a, b, force, depth)
                if (int(x) == int(finger) or int(y) == int(finger)) and np.linalg.norm(f) > 1e-8 and 0 <= d <= .002}
                for finger in set(a) | set(b)}
            for side, group in self.robot.groups.items():
                if side in targets or group.grasp is None:
                    continue
                fingers = [self.robot.entity.get_link(n).idx for n in group.grasp.finger_links]
                links = set.intersection(*(touched.get(i, set()) for i in fingers))
                candidates = {(s.entity, s.link.name) for s in self.shapes if s.entity != 'robot'
                    and s.link.idx in links and not s.link.is_fixed}
                if len(candidates) == 1:
                    targets[side] = candidates.pop()
        if len(set(targets.values())) != len(targets):
            raise ValueError('Ambiguous two-hand ownership in IK candidate')
        held = {}
        for side, target in targets.items():
            link = next((s.link for s in self.shapes if (s.entity, s.link.name) == target), None)
            if link is None:
                continue  # FEM/PBD is not approximated as a rigid payload.
            index = self.robot.entity.get_link(self.robot.groups[side].hand_link).idx_local
            p, r = self.link_pose(link)
            held[target] = (side, index, rotations[index].inv().apply(p - positions[index]),
                            rotations[index].inv() * r)
        return held

    @staticmethod
    def penetration(first, second):
        import fcl
        result = fcl.CollisionResult()
        if not fcl.collide(first, second, fcl.CollisionRequest(num_max_contacts=128, enable_contact=True), result):
            return 0.
        # Unknown depth is not treated as a clear path.
        if not result.contacts:
            return float('inf')
        return max(0., max(float(c.penetration_depth) for c in result.contacts)) + 1e-9

    def check(self, start, goal):
        import fcl
        start, goal = np.asarray(start, float), np.asarray(goal, float)
        samples_q = joint_samples(start, goal)
        if start.shape != (int(self.robot.entity.n_qs),):
            return dict(passed=False, reason='joint_shape')
        for side, group in self.robot.groups.items():
            index = self.robot._q_indices[side][:len(group.arm_joints)]
            limits = np.asarray(group.arm_limits_rad)
            if not np.isfinite(goal[index]).all() or np.any(goal[index] < limits[:, 0]) or np.any(goal[index] > limits[:, 1]):
                return dict(passed=False, reason='joint_limits', side=side)
        measured = to_numpy(self.robot.entity.get_qpos()).reshape(-1)
        mp, mr = self.frames(measured)
        held = self.held_links(mp, mr)
        fixed = {(s.entity, s.link.name): self.link_pose(s.link) for s in self.shapes if s.entity != 'robot'}
        moving = {i for i, s in enumerate(self.shapes) if s.entity == 'robot' or (s.entity, s.link.name) in held}
        pairs = []
        for i, a in enumerate(self.shapes):
            for j in range(i + 1, len(self.shapes)):
                b = self.shapes[j]
                if i not in moving and j not in moving:
                    continue
                if a.entity == b.entity and a.link.idx == b.link.idx:
                    continue
                if a.entity == b.entity == 'robot' and tuple(sorted((a.geom_id, b.geom_id))) not in self.native_pairs:
                    continue
                # The binding admits own-finger/payload contact, not forearm contact.
                contact = False
                for hand, body in ((a, b), (b, a)):
                    target = (body.entity, body.link.name)
                    if hand.entity == 'robot' and target in held:
                        side = held[target][0]
                        if hand.link.name in self.robot.groups[side].grasp.finger_links:
                            contact = True
                if not contact:
                    pairs.append((i, j))

        def place(q):
            p, r = self.frames(q)
            transforms = []
            for s in self.shapes:
                target = (s.entity, s.link.name)
                if s.entity == 'robot':
                    sp, sr = p[s.link.idx_local], r[s.link.idx_local]
                elif target in held:
                    _, index, dp, dr = held[target]
                    sp, sr = p[index] + r[index].apply(dp), r[index] * dr
                else:
                    sp, sr = fixed[target]
                sp, sr = sp + sr.apply(s.offset_p), sr * s.offset_r
                s.obj.setTransform(fcl.Transform(sr.as_matrix(), sp))
                transforms.append(np.r_[sp, sr.as_matrix().reshape(-1)])
            return np.asarray(transforms)

        initial_transforms = place(start)
        baseline = [self.penetration(self.shapes[a].obj, self.shapes[b].obj) for a, b in pairs]
        if not np.isfinite(baseline).all():
            return dict(passed=False, reason='unresolved_contact_depth')
        samples = 0
        for q in samples_q:
            transforms = place(q)
            samples += 1
            for (a, b), before in zip(pairs, baseline):
                depth = self.penetration(self.shapes[a].obj, self.shapes[b].obj)
                # Mesh/mesh contact depth is not a reliable signed distance.
                # Permit only unchanged static baseline contacts (e.g. a bolted
                # robot base). Moving baseline contacts require a task-specific
                # planner; a small/zero triangle depth must never admit collision.
                unchanged = np.allclose(transforms[[a, b]], initial_transforms[[a, b]], rtol=0., atol=1e-10)
                if depth > 0 and not (before > 0 and unchanged):
                    sa, sb = self.shapes[a], self.shapes[b]
                    return dict(passed=False, reason='swept_collision', sample=samples,
                        pair=[f'{sa.entity}/{sa.link.name}', f'{sb.entity}/{sb.link.name}'],
                        penetration_m=depth, initial_penetration_m=before)
        return dict(passed=True, samples=samples, held_rigid_links=[list(k) for k in held],
                    max_joint_sample_rad=.005, soft_material_checked=False, continuous_certificate=False)
