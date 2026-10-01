"""Read-only native IK/FK and collision checks for ALOHA over the knot rope.

Plans never change a body pose or advance physics. The table and both arms
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
from topogym.solvers.genesis_kinematics import GenesisFKSolver, GenesisIKSolver
from topogym.utils.arrays import to_numpy

# Pad contact point relative to the TCP along the approach axis (ALOHA, as in Horseshoe).
CONTACT_IN_TCP_M = np.array([.01381, 0., -.00055])


def vertical_pinch(point_m, tangent_xy, flip=1):
    """TCP position and rotation whose pad contact sits on point_m, jaws across the rope."""
    down = np.array([0., 0., -1.])
    t = np.asarray(tangent_xy, float)[:2]
    jaw = flip*np.array([-t[1], t[0], 0.])/np.linalg.norm(t)
    turn = Rotation.from_matrix(np.column_stack([down, jaw, np.cross(down, jaw)]))
    return np.asarray(point_m, float)-turn.apply(CONTACT_IN_TCP_M), turn


class KnotIK:
    def __init__(self, world, robot, table_height_m):
        self.robot = robot
        self.seed = to_numpy(robot.entity.get_qpos()).reshape(-1).copy()
        self.ik = GenesisIKSolver(robot.entity)
        self.fk = GenesisFKSolver(robot.entity)
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

    def solve(self, side, tcp, seed=None):
        p, r = tcp
        group = self.robot.groups[side]
        hand_r = r*Rotation.from_quat(np.roll(group.tcp_orientation_in_hand_wxyz, -1)).inv()
        return self.ik.solve_checked(link_name=group.hand_link,
            position_world_m=p-hand_r.apply(group.tcp_position_in_hand_m),
            orientation_wxyz=hand_r.as_quat()[[3, 0, 1, 2]],
            initial_qpos=self.seed if seed is None else seed,
            joint_dof_indices=self.robot._indices[side][:6], max_solver_iterations=300)

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
