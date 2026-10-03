"""Read-only native IK/FK and sampled imported-collision-mesh audits."""
import numpy as np
import trimesh
from scipy.spatial.transform import Rotation

from topogym.utils.arrays import to_numpy
from topogym.solvers.genesis_kinematics import GenesisIKSolver, GenesisFKSolver
from topogym.planning.rigid_reference.geometry import matrix
from .geometry import pose
from .contracts import positive_int


def joint_margin(robot, q):
    margins = []
    for side, group in robot.groups.items():
        joints = q[robot._q_indices[side][:len(group.arm_joints)]]
        limits = np.asarray(group.arm_limits_rad)
        margins.extend((np.min(joints-limits[:, 0]), np.min(limits[:, 1]-joints)))
        fingers = q[robot._q_indices[side][len(group.arm_joints):]]
        if len(fingers) and (np.min(fingers) < group.gripper_limits[0]-1e-8 or
                             np.max(fingers) > group.gripper_limits[1]+1e-8):
            return -1.
    return float(min(margins))


def solve(env, targets, seeds=None):
    robot = env._robot
    if not isinstance(targets, dict) or not targets or not set(targets) <= set(robot.groups):
        raise ValueError("targets maps robot group names to world TCP poses")
    seeds = [to_numpy(robot.entity.get_qpos()).reshape(-1)] if seeds is None else seeds
    if not seeds or len(seeds) > 1000:
        raise ValueError("Provide between 1 and 1000 full-robot qpos seeds")
    ik, fk = GenesisIKSolver(robot.entity), GenesisFKSolver(robot.entity)
    results = []
    for index, seed in enumerate(seeds):
        q = np.asarray(seed, dtype=float).copy()
        if q.shape != (robot.entity.n_qs,) or not np.isfinite(q).all():
            raise ValueError("Each seed needs finite full-robot qpos")
        try:
            for side, value in targets.items():
                p, r = pose(value)
                group = robot.groups[side]
                tcp_rotation = Rotation.from_quat(np.asarray(group.tcp_orientation_in_hand_wxyz)[[1, 2, 3, 0]])
                hand_rotation = r * tcp_rotation.inv()
                q = ik.solve_checked(link_name=group.hand_link,
                    position_world_m=p-hand_rotation.apply(group.tcp_position_in_hand_m),
                    orientation_wxyz=hand_rotation.as_quat()[[3, 0, 1, 2]], initial_qpos=q,
                    joint_dof_indices=robot._indices[side][:len(group.arm_joints)])
            margin = joint_margin(robot, q)
            result = dict(seed_index=index, accepted=margin >= 0, qpos=q.tolist(),
                          minimum_joint_margin_rad=margin, residual_tolerance_m=1e-4,
                          orientation_tolerance_rad=1e-3)
        except ValueError as error:
            result = dict(seed_index=index, accepted=False, error=str(error))
        results.append(result)
    return dict(candidates=results, scope="native IK residual and joint limits; no collision or physical proof", physics_steps=0)


class RobotGeometry:
    def __init__(self, env):
        self.env = env
        self.robot = env._robot
        self.fk = GenesisFKSolver(self.robot.entity)
        self.robot_manager = trimesh.collision.CollisionManager()
        self.moving_manager = trimesh.collision.CollisionManager()
        self.obstacles = trimesh.collision.CollisionManager()
        self.links = {}
        self.exclusions = set()
        self.mount_exclusions = set()
        native_links = {link.idx: link for link in self.robot.entity.links}
        def rigid_root(index):
            link = native_links[index]
            while link.parent_idx in native_links and not any(joint.n_dofs for joint in link.joints):
                link = native_links[link.parent_idx]
            return link
        world = env._world.read_state()
        for entity_name, entity in env._world.entities.items():
            if entity_name not in world["articulations"]:
                continue
            for link in entity.links:
                local = []
                measured = world["articulations"][entity_name]["links"][link.name]
                p, r = pose({key: measured[key] for key in ("position_m", "quaternion_wxyz")})
                for geom in link.geoms:
                    if not geom.contype and not geom.conaffinity:
                        continue
                    vertices = r.inv().apply(to_numpy(geom.get_verts()).reshape(-1, 3)-p)
                    local.append(trimesh.Trimesh(vertices, geom.init_faces, process=False))
                if not local:
                    continue
                mesh = trimesh.util.concatenate(local)
                label = entity_name + "/" + link.name
                if entity_name == "robot":
                    self.robot_manager.add_object(label, mesh)
                    if not link.is_fixed:
                        self.moving_manager.add_object(label, mesh)
                    root = rigid_root(link.idx)
                    self.links[label] = dict(index=link.idx_local, global_index=link.idx,
                                              parent=rigid_root(root.parent_idx).idx if root.parent_idx in native_links else -1,
                                              rigid_root=root.idx,
                                              fixed=bool(link.is_fixed), vertices=mesh.vertices)
                else:
                    self.obstacles.add_object(label, mesh, transform=matrix(p, r))
        for a, left in self.links.items():
            for b, right in self.links.items():
                if a != b and (left["rigid_root"] == right["rigid_root"] or
                    left["parent"] == right["rigid_root"] or right["parent"] == left["rigid_root"]):
                    self.exclusions.add(tuple(sorted((a, b))))
            if left["fixed"]:
                for b in self.obstacles._objs:
                    if b.startswith("table/"):
                        self.mount_exclusions.add(tuple(sorted((a, b))))

    def check(self, path, *, allowed_contacts=(), include_tcp=False, cancelled=lambda: False):
        positive_int(len(path), "path samples", 10000)
        if type(include_tcp) is not bool:
            raise ValueError("include_tcp must be a boolean")
        allowed = {tuple(sorted(pair)) for pair in allowed_contacts}
        if any(len(pair) != 2 or any(not isinstance(v, str) for v in pair) for pair in allowed_contacts):
            raise ValueError("allowed_contacts needs explicit pairs of entity/link labels")
        issues, evaluated, tcp_path = [], 0, []
        margin = minimum_gap = None
        for index, values in enumerate(path):
            if cancelled():
                break
            q = np.asarray(values, dtype=float)
            result = self.fk.solve(q)
            positions = np.asarray(result["position_world_m"]).reshape(-1, 3)
            rotations = np.asarray(result["orientation_wxyz"]).reshape(-1, 4)
            if include_tcp:
                frame = {}
                for side, group in self.robot.groups.items():
                    link = self.robot.entity.get_link(group.hand_link).idx_local
                    turn = Rotation.from_quat(rotations[link][[1, 2, 3, 0]])
                    tcp_turn = turn*Rotation.from_quat(np.asarray(group.tcp_orientation_in_hand_wxyz)[[1, 2, 3, 0]])
                    frame[side] = dict(position_m=(positions[link]+turn.apply(group.tcp_position_in_hand_m)).tolist(),
                                       quaternion_wxyz=tcp_turn.as_quat()[[3, 0, 1, 2]].tolist())
                tcp_path.append(frame)
            current = joint_margin(self.robot, q)
            margin = current if margin is None else min(margin, current)
            for name, link in self.links.items():
                i = link["index"]
                self.robot_manager.set_transform(name, matrix(positions[i], Rotation.from_quat(rotations[i][[1, 2, 3, 0]])))
                if not link["fixed"]:
                    self.moving_manager.set_transform(name, matrix(positions[i], Rotation.from_quat(rotations[i][[1, 2, 3, 0]])))
            _, pairs = self.robot_manager.in_collision_internal(return_names=True)
            hits = {tuple(sorted(p)) for p in pairs} - self.exclusions - allowed
            _, pairs = self.robot_manager.in_collision_other(self.obstacles, return_names=True)
            hits |= {tuple(sorted(p)) for p in pairs} - allowed - self.mount_exclusions
            if self.moving_manager._objs and self.obstacles._objs:
                gap = max(0., float(self.moving_manager.min_distance_other(self.obstacles)))
                if np.isfinite(gap):
                    minimum_gap = gap if minimum_gap is None else min(minimum_gap, gap)
            if hits or current < 0:
                issues.append(dict(sample=index, collisions=sorted(hits), joint_margin_rad=current))
            evaluated += 1
        return dict(passed=not issues and evaluated == len(path), evaluated_samples=evaluated,
                    total_samples=len(path), minimum_joint_margin_rad=margin, issues=issues,
                    minimum_environment_clearance_m=minimum_gap,
                    clearance_includes_allowed_contacts=True,
                    excluded_adjacent_or_fixed_links=sorted(self.exclusions),
                    excluded_fixed_table_mounts=sorted(self.mount_exclusions), allowed_contacts=sorted(allowed),
                    scope="sampled imported collision meshes, including fingers and modeled obstacles; no continuous proof",
                    visual_only_camera_housing_covered=False, physics_steps=0,
                    **(dict(tcp_path=tcp_path, tcp_path_source="native FK at the submitted qpos samples")
                       if include_tcp else {}))
