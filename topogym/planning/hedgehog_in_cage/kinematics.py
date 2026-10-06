"""Read-only Panda/Robotiq IK against the actual current Hedgehog geometry.

Concave cage surfaces stay concave. Finger states are measured, not inferred
from the two driver targets. Robot checks are sampled FK checks; they do not
claim continuous joint-space collision certification or a stable grasp.
"""
import fcl
import numpy as np
import trimesh
from scipy.spatial.transform import Rotation

from topogym.planning.buzz_wire_3d.kinematics import BuzzIK, distance, manager, mesh_object
from topogym.solvers.genesis_kinematics import GenesisFKSolver
from topogym.planning.oracle_ik import OracleIKSolver as GenesisIKSolver
from topogym.utils.arrays import to_numpy


def surface_object(vertices, faces):
    """Triangle BVH; unlike a convex hull this preserves the cage's openings."""
    model = fcl.BVHModel()
    model.beginModel(len(vertices), len(faces))
    model.addSubModel(np.asarray(vertices, float), np.asarray(faces, np.int32))
    model.endModel()
    return fcl.CollisionObject(model)


class HedgehogIK(BuzzIK):
    def __init__(self, env, *, measured_state=None):
        if env._task.task_id != "hedgehog_in_cage":
            raise ValueError("Hedgehog geometry is required")
        self.robot = env._robot
        self.ik, self.fk = GenesisIKSolver(self.robot.entity), GenesisFKSolver(self.robot.entity)
        self.seed = to_numpy(self.robot.entity.get_qpos()).reshape(-1).copy()
        self.group = self.robot.groups["arm"]
        self.indices = self.robot._indices["arm"][:7]
        self.arm_qindices = self.robot._q_indices["arm"][:7]
        poses = self.fk.solve(self.seed)
        ps = np.asarray(poses["position_world_m"]).reshape(-1, 3)
        rs = Rotation.from_quat(np.asarray(poses["orientation_wxyz"]).reshape(-1, 4)[:, [1, 2, 3, 0]])
        self.robot_shapes, self.local_meshes, self.names = [], [], {}
        for link in self.robot.entity.links:
            index = link.idx_local
            self.names[index] = link.name
            for geom in link.geoms:
                local = rs[index].inv().apply(to_numpy(geom.get_verts()).reshape(-1, 3)-ps[index])
                self.robot_shapes.append((index, mesh_object(local, geom.init_faces)))
                self.local_meshes.append((index, trimesh.Trimesh(local, geom.init_faces, process=False)))
        # Only link0 has the intended mounting contact with the table.
        self.robot_manager = manager([obj for index, obj in self.robot_shapes if index != 0])
        fingers = set(self.group.grasp.finger_links)
        self.nonfinger_manager = manager([obj for index, obj in self.robot_shapes
                                           if self.names[index] not in fingers])
        fixed = []
        for name in ("hedgehog_cage", "hedgehog_mount", "table"):
            entity = env._world.entities[name]
            for link in entity.links:
                for geom in link.geoms:
                    fixed.append(surface_object(to_numpy(geom.get_verts()).reshape(-1, 3), geom.init_faces))
        self.fixed = manager(fixed)
        self.ball = env._world.entities["hedgehog_ball"]
        self.ball_pose = (to_numpy(self.ball.get_pos()).reshape(3),
                          Rotation.from_quat(to_numpy(self.ball.get_quat()).reshape(4)[[1, 2, 3, 0]]))
        bp, br = self.ball_pose
        self.ball_objects = [mesh_object(br.inv().apply(to_numpy(g.get_verts()).reshape(-1, 3)-bp), g.init_faces)
                             for link in self.ball.links for g in link.geoms]
        self.ball_manager = manager(self.ball_objects)
        # Check nonadjacent arm links and the arm against the entire tool.
        # Internal tool linkage and wrist/tool mating surfaces are excluded.
        self.self_pairs = []
        for i, (a, first) in enumerate(self.robot_shapes):
            for b, second in self.robot_shapes[i+1:]:
                if a >= 8 and b >= 8:
                    continue
                if a < 8 and b < 8 and abs(a-b) <= 2:
                    continue
                if min(a, b) >= 6:
                    continue
                self.self_pairs.append((first, second))
        if measured_state is not None:
            # Offline FK/IK query seed only. No entity setter or episode restore.
            joints = measured_state["articulations"]["robot"]["joints"]
            seed = self.seed.copy()
            for joint in self.robot.entity.joints:
                values = np.asarray(joints[joint.name]["position"], float)
                indices = list(joint.qs_idx_local)
                if values.shape != (len(indices),) or not np.isfinite(values).all():
                    raise ValueError("Invalid measured joint positions")
                seed[indices] = values
            body = measured_state["bodies"]["hedgehog_ball"]
            self.seed = seed
            self.ball_pose = (np.asarray(body["position_m"], float),
                              Rotation.from_quat(np.asarray(body["quaternion_wxyz"])[[1, 2, 3, 0]]))

    def gaps(self, q, body=None):
        poses = self.fk.solve(q)
        ps = np.asarray(poses["position_world_m"]).reshape(-1, 3)
        rs = Rotation.from_quat(np.asarray(poses["orientation_wxyz"]).reshape(-1, 4)[:, [1, 2, 3, 0]])
        for index, obj in self.robot_shapes:
            obj.setTransform(fcl.Transform(rs[index].as_matrix(), ps[index]))
        self.robot_manager.update()
        self.nonfinger_manager.update()
        p, r = self.ball_pose if body is None else body
        for obj in self.ball_objects:
            obj.setTransform(fcl.Transform(r.as_matrix(), p))
        self.ball_manager.update()
        self_gap = min((float(fcl.distance(a, b, fcl.DistanceRequest(), fcl.DistanceResult()))
                        for a, b in self.self_pairs), default=float("inf"))
        return dict(robot_environment_m=distance(self.robot_manager, self.fixed),
                    robot_ball_m=distance(self.robot_manager if body is None else self.nonfinger_manager,
                                          self.ball_manager),
                    nonadjacent_arm_self_m=self_gap)

    def clearance(self, q, body=None, **kwargs):
        return min(self.gaps(q, body).values())
