"""Host-only command FK, native IK and collision checks for ALOHA over the knot rope.

Command FK copies authored chain data once and never touches live solver fields.
Native IK uses the shared scratch/RNG-preserving adapter. Neither query advances physics. The table and both arms
participate in collision queries; the deformable rope is not a collision body
here (fingers are meant to touch it, physics decides the rest).

Grasps are vertical pinches: approach straight down, jaws closing across the
rope (perpendicular to the local rope tangent), the pads' contact point on the
rope centre line. This is the pin/pull grasp of HULK (Grannen et al., CoRL 2020)
on a table-top rope.
"""
import fcl
import numpy as np
from scipy.spatial.transform import Rotation

from topogym.planning.buzz_wire_3d.kinematics import mesh_object, manager, distance
from topogym.solvers.genesis_kinematics import GenesisIKSolver
from topogym.utils.arrays import to_numpy
from .chain_fk import StaticChainFK

# Pad contact point relative to the TCP along the approach axis (ALOHA, as in Horseshoe).
CONTACT_IN_TCP_M = np.array([.01381, 0., -.00055])


def vertical_pinch(point_m, tangent_xy, flip=1, *, yaw_deg=0., tilt_deg=0.):
    """TCP position and rotation whose pad contact sits on point_m, jaws across the rope."""
    down = np.array([0., 0., -1.])
    t = np.asarray(tangent_xy, float)[:2]
    jaw = flip*np.array([-t[1], t[0], 0.])/np.linalg.norm(t)
    turn = Rotation.from_matrix(np.column_stack([down, jaw, np.cross(down, jaw)]))
    turn = Rotation.from_euler('z', yaw_deg, degrees=True)*turn*Rotation.from_euler('y', tilt_deg, degrees=True)
    return np.asarray(point_m, float)-turn.apply(CONTACT_IN_TCP_M), turn


class KnotIK:
    def __init__(self, world, robot, table_height_m):
        self.robot = robot
        self.seed = to_numpy(robot.entity.get_qpos()).reshape(-1).copy()
        self.ik = GenesisIKSolver(robot.entity)
        self.fk = StaticChainFK(robot.entity)
        self.table_height = float(table_height_m)
        pose = self.fk.solve(self.seed)
        ps = np.asarray(pose['position_world_m']).reshape(-1, 3)
        rs = Rotation.from_quat(np.asarray(pose['orientation_wxyz']).reshape(-1, 4)[:, [1, 2, 3, 0]])
        self.shapes, by_geom = [], {}
        for link in robot.entity.links:
            side = link.name.split('/')[0]
            for geom in link.geoms:
                vertices = rs[link.idx_local].inv().apply(to_numpy(geom.get_verts()).reshape(-1, 3)-ps[link.idx_local])
                obj = mesh_object(vertices, geom.init_faces)
                self.shapes.append((side, link.name, link.idx_local, vertices, obj))
                by_geom[int(geom.idx)] = (side, link.name, obj)
        # Genesis' authored adjacency and neutral-pose exclusions decide which
        # same-arm pairs may never intersect.
        valid_pairs = world.scene.sim.rigid_solver.collider._valid_collision_pairs
        self.self_pairs = [(by_geom[int(a)], by_geom[int(b)]) for a, b in valid_pairs
                           if int(a) in by_geom and int(b) in by_geom and by_geom[int(a)][0] == by_geom[int(b)][0]]
        self.by_arm = {side: manager([x[4] for x in self.shapes if x[0] == side]) for side in robot.groups}
        # A collision sphere's display mesh is inscribed. Use native primitive
        # outer covers for the command/table guard, including the fingertip balls.
        from .collision_audit import rigid_cover_vertices
        entries = [(link, geom) for link in robot.entity.links
                   if 'gripper' in link.name or 'finger' in link.name for geom in link.geoms]
        if not entries:
            raise ValueError('Missing gripper collision geometry')
        solver = world.scene.sim.rigid_solver
        ids = [int(geom.idx) for link, geom in entries]
        positions = to_numpy(solver.get_geoms_pos(ids, relative=False)).reshape(-1, 3)
        turns = Rotation.from_quat(to_numpy(solver.get_geoms_quat(ids, relative=False)).reshape(-1, 4)[:, [1, 2, 3, 0]])
        self.gripper_covers = []
        for (link, geom), position, turn in zip(entries, positions, turns, strict=True):
            cover, _ = rigid_cover_vertices(geom.type.name, geom.data, geom.init_verts)
            local = rs[link.idx_local].inv().apply(turn.apply(cover)+position-ps[link.idx_local])
            self.gripper_covers.append((link.name.split('/')[0], link.idx_local, local))

    def gripper_table_clearance(self, q, sides=None):
        """Conservative command-pose gap; this is not a measured-physics certificate."""
        sides = set(self.robot.groups if sides is None else sides)
        pose = self.fk.solve(q)
        positions = np.asarray(pose['position_world_m']).reshape(-1, 3)
        turns = Rotation.from_quat(np.asarray(pose['orientation_wxyz']).reshape(-1, 4)[:, [1, 2, 3, 0]])
        gaps = {side: float('inf') for side in sides}
        for side, index, vertices in self.gripper_covers:
            if side in sides:
                gaps[side] = min(gaps[side], float((turns[index].apply(vertices)+positions[index])[:, 2].min()-self.table_height))
        if not gaps or not np.isfinite(list(gaps.values())).all():
            raise ValueError('Incomplete gripper command geometry')
        return gaps

    def solve(self, side, tcp, seed=None):
        p, r = tcp
        group = self.robot.groups[side]
        hand_r = r*Rotation.from_quat(np.roll(group.tcp_orientation_in_hand_wxyz, -1)).inv()
        start = (self.seed if seed is None else seed).copy()
        indices = self.robot._q_indices[side][:6]
        seeds = [start]
        home = start.copy()
        home[indices] = self.seed[indices]
        seeds.append(home)
        limits = np.asarray(group.arm_limits_rad)
        for sign in (1., -1.):
            alternative = start.copy()
            alternative[indices] = np.clip(start[indices]+sign*np.array([.2, -.3, .3, .4, -.2, .4]),
                                           limits[:, 0], limits[:, 1])
            seeds.append(alternative)
        errors = []
        for initial in seeds:
            try:
                return self.ik.solve_checked(link_name=group.hand_link,
                    position_world_m=p-hand_r.apply(group.tcp_position_in_hand_m),
                    orientation_wxyz=hand_r.as_quat()[[3, 0, 1, 2]], initial_qpos=initial,
                    joint_dof_indices=self.robot._indices[side][:6], max_solver_iterations=300,
                    position_tolerance_m=.0005, orientation_tolerance_rad=.01)
            except ValueError as error:
                errors.append(str(error))
        raise ValueError(f'IK exhausted {len(seeds)} seeds: {errors[-1]}')

    def check(self, q):
        pose = self.fk.solve(q)
        ps = np.asarray(pose['position_world_m']).reshape(-1, 3)
        rs = Rotation.from_quat(np.asarray(pose['orientation_wxyz']).reshape(-1, 4)[:, [1, 2, 3, 0]])
        minimum = float('inf')
        for side, name, index, vertices, obj in self.shapes:
            obj.setTransform(fcl.Transform(rs[index].as_matrix(), ps[index]))
            if name.rsplit('/', 1)[-1] not in {'base_link', 'waist_link', 'shoulder_link'}:
                minimum = min(minimum, float((rs[index].apply(vertices)+ps[index])[:, 2].min()-self.table_height))
        for m in self.by_arm.values():
            m.update()
        issues = []
        if any(fcl.collide(a[2], b[2], fcl.CollisionRequest(), fcl.CollisionResult()) for a, b in self.self_pairs):
            issues.append('same_arm_collision')
        if minimum < .0005:
            issues.append('table')
        gap = distance(self.by_arm['left'], self.by_arm['right'])
        if gap < .001:
            issues.append('inter_arm')
        for side, group in self.robot.groups.items():
            joints = q[self.robot._q_indices[side][:6]]
            limits = np.asarray(group.arm_limits_rad)
            if np.any(joints < limits[:, 0]) or np.any(joints > limits[:, 1]):
                issues.append(side+'/joint_limits')
        return dict(passed=not issues, issues=issues, table_clearance_m=minimum, inter_arm_gap_m=float(gap))
