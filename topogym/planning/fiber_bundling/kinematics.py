"""Read-only IK and FCL clearance for Fiber Bundling, reusing BuzzIK's planners."""
import numpy as np
import fcl
from scipy.spatial.transform import Rotation

from topogym.planning.buzz_wire_3d.kinematics import BuzzIK, distance, manager, mesh_object
from topogym.solvers.genesis_kinematics import GenesisFKSolver
from topogym.planning.oracle_ik import OracleIKSolver as GenesisIKSolver
from topogym.utils.arrays import to_numpy
from .keyframes import GRASP_LINK, link_pose

# The whole gripper must stay this much farther from fine strands than the
# requested clearance to other obstacles (strand contact fails the Task).
STRAND_MARGIN_M = .001
FIXED_PREFIXES = ("bundling_ring", "ring_mount_", "cable_cradle_")


class FiberIK(BuzzIK):
    """BuzzIK's IK, joint-reference and open-hand planners with Fiber obstacles.

    Obstacles for the robot: ring, ring mount, cradle, the fixed terminal,
    the lead and the sheath links resting in the cradle (more than two links
    behind the grasped one), as sampled now. The two links between the cradle
    and the grasp bend with the held link and are not modelled; the Task allows
    gripper-sheath contact. Held: the grasped link and the next (front) sheath link, rigid
    in the grasped-link frame. Strands: fiber capsules as sampled now, rigid in
    the same frame; only the gripper subtree is checked against them. With no
    held body (open hand) every sheath link and strand is an obstacle. The table
    is left out, as in BuzzIK: the robot base stands on it.
    """

    def __init__(self, env, link=GRASP_LINK):
        self.robot = env._robot
        self.ik, self.fk = GenesisIKSolver(self.robot.entity), GenesisFKSolver(self.robot.entity)
        self.seed = to_numpy(self.robot.entity.get_qpos()).reshape(-1).copy()
        self.group = self.robot.groups["arm"]
        self.indices = self.robot._indices["arm"][:7]
        self.arm_qindices = self.robot._q_indices["arm"][:7]
        self.robot_shapes = []
        initial = self.fk.solve(self.seed)
        initial_p = np.asarray(initial["position_world_m"]).reshape(-1, 3)
        initial_r = Rotation.from_quat(np.asarray(initial["orientation_wxyz"]).reshape(-1, 4)[:, [1, 2, 3, 0]])
        for robot_link in self.robot.entity.links:
            p, r = initial_p[robot_link.idx_local], initial_r[robot_link.idx_local]
            for geom in robot_link.geoms:
                local = r.inv().apply(to_numpy(geom.get_verts()).reshape(-1, 3)-p)
                self.robot_shapes.append((robot_link.idx_local, mesh_object(local, geom.init_faces)))
        self.robot_manager = manager([obj for _, obj in self.robot_shapes])
        # Gripper subtree, as classified for the Task's contact failure.
        root = self.robot.entity.get_link(self.group.grasp.contact_root_link)
        subtree = {int(root.idx)}
        while True:
            children = {int(item.idx) for item in self.robot.entity.links if int(item.parent_idx) in subtree}
            if children <= subtree:
                break
            subtree |= children
        local_ids = {item.idx_local for item in self.robot.entity.links if int(item.idx) in subtree}
        self.gripper_manager = manager([obj for index, obj in self.robot_shapes if index in local_ids])

        state = env._world.read_state()
        world_mesh = lambda geom: mesh_object(to_numpy(geom.get_verts()).reshape(-1, 3), geom.init_faces)
        obstacles = [world_mesh(g) for name, entity in env._world.entities.items()
                     if name.startswith(FIXED_PREFIXES) for item in entity.links for g in item.geoms]
        index = int(link.split("_")[1])
        held_names = {link, f"trunk_{index+1:02d}"}
        rear = {f"trunk_{i:02d}" for i in range(index-2)}
        p, r = link_pose(state, link)
        in_link = lambda geom: mesh_object(r.inv().apply(to_numpy(geom.get_verts()).reshape(-1, 3)-p), geom.init_faces)
        self.held_objects, self.strand_objects, loose, cable = [], [], [], []
        for item in env._world.entities["fiber_bundle"].links:
            for geom in item.geoms:
                if item.name in held_names:
                    self.held_objects.append(in_link(geom))
                    loose.append(world_mesh(geom))
                elif item.name.startswith("fiber_"):
                    self.strand_objects.append(in_link(geom))
                    loose.append(world_mesh(geom))
                elif item.name in rear or item.name.startswith("lead_") or item.name == "fixed_terminal":
                    (obstacles if item.name == "fixed_terminal" else cable).append(world_mesh(geom))
                else:
                    loose.append(world_mesh(geom))  # the bending links between cradle and grasp
        self.obstacles = manager(obstacles)
        self.fixed = manager(obstacles+cable)
        self.free = manager(loose)
        self.held_manager = manager(self.held_objects)
        self.strand_manager = manager(self.strand_objects)

    def clearance(self, q, body=None, *, allow_wand_support=False):
        poses = self.fk.solve(q)
        ps = np.asarray(poses["position_world_m"]).reshape(-1, 3)
        rs = Rotation.from_quat(np.asarray(poses["orientation_wxyz"]).reshape(-1, 4)[:, [1, 2, 3, 0]])
        for index, obj in self.robot_shapes:
            obj.setTransform(fcl.Transform(rs[index].as_matrix(), ps[index]))
        self.robot_manager.update()
        self.gripper_manager.update()
        gap = distance(self.robot_manager, self.fixed)
        if body is None:
            return min(gap, distance(self.robot_manager, self.free))
        return min(gap, *self.held_gaps(body))

    def held_gaps(self, body):
        """Held sheath to fixed obstacles; gripper to strands less the strand margin."""
        p, r = body
        for obj in self.held_objects+self.strand_objects:
            obj.setTransform(fcl.Transform(r.as_matrix(), p))
        self.held_manager.update()
        self.strand_manager.update()
        return (distance(self.held_manager, self.obstacles),
                distance(self.gripper_manager, self.strand_manager)-STRAND_MARGIN_M)
