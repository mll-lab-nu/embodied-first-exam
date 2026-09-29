"""Robot-only layout, telemetry and stateless kinematics for the benchmark.

All physical execution remains in Env.step. Queries use a fixed model qpos
template and preserve Genesis query scratch through GenesisFKSolver.
"""
from __future__ import annotations

import numpy as np
from scipy.spatial.transform import Rotation

from topogym.utils.arrays import to_numpy


def matrix(pose):
    pose = np.asarray(pose, dtype=float)
    if pose.shape != (7,) or not np.isfinite(pose).all() or not np.isclose(np.linalg.norm(pose[3:]), 1, atol=1e-6):
        raise ValueError("Expected xyz and unit wxyz")
    result = np.eye(4)
    result[:3, :3] = Rotation.from_quat(pose[[4, 5, 6, 3]]).as_matrix()
    result[:3, 3] = pose[:3]
    return result


def pose(transform):
    q = Rotation.from_matrix(transform[:3, :3]).as_quat()[[3, 0, 1, 2]]
    if q[0] < 0:
        q = -q
    return np.r_[transform[:3, 3], q].tolist()


class RobotModel:
    def __init__(self, robot, timing):
        self.robot, self.entity, self.timing = robot, robot.entity, timing
        self.groups = tuple(robot.description.groups)
        self.template = to_numpy(self.entity.get_qpos()).reshape(-1).copy()
        self.names, self.q_indices, self.dof_indices, self.bounds = [], [], [], []
        self.action_layout, self.action_limits = [], []
        self.ee_layout, self.tcp_frames = [], []
        self.gripper_columns = []
        for group in self.groups:
            for i, name in enumerate(group.arm_joints + group.finger_joints):
                joint = self.entity.get_joint(name)
                self.names.append(name)
                self.q_indices.append(joint.qs_idx_local[0])
                self.dof_indices.append(joint.dofs_idx_local[0])
                self.bounds.append(group.arm_limits_rad[i] if i < len(group.arm_joints) else group.gripper_limits)
            self.action_layout.extend(group.arm_joints)
            self.action_limits.extend(group.arm_limits_rad)
            self.gripper_columns.append(len(self.action_layout))
            self.action_layout.append(f"{group.name}/{group.gripper_field}")
            self.action_limits.append(group.gripper_limits)
            self.ee_layout.extend(f"{group.name}/{s}" for s in ("x", "y", "z", "qw", "qx", "qy", "qz", group.gripper_field))
            self.tcp_frames.append(f"{group.name}_tcp")
        # Include passive linkage coordinates too: FK of a finger link must be
        # determined by q, not by an unreported current scene coordinate.
        for joint in self.entity.joints:
            if joint.name not in self.names and len(joint.qs_idx_local) == 1:
                self.names.append(joint.name)
                self.q_indices.append(joint.qs_idx_local[0])
                self.dof_indices.append(joint.dofs_idx_local[0])
                self.bounds.append((-np.inf,np.inf))
        self.bounds = np.asarray(self.bounds, float)
        self.home = np.clip(self.template[self.q_indices], self.bounds[:, 0], self.bounds[:, 1])
        self.links = [link.name for link in self.entity.links]
        self.layout = list(self.names) + [f"{name}/velocity" for name in self.names]
        self.layout += [f"{g.name}/opening_m" for g in self.groups]
        self.layout += [f"{frame}/{s}" for frame in self.tcp_frames for s in ("x", "y", "z", "qw", "qx", "qy", "qz")]
        arms = [name for g in self.groups for name in g.arm_joints]
        self.layout += [f"{name}/effort_estimate" for name in arms]
        n, count = len(self.names), len(self.groups)
        self.proprio_groups = dict(joint_pos=[0, n, "measured joint coordinates, rad or m as robot_spec"],
            joint_vel=[n, n, "measured joint velocities"],
            gripper_opening=[2*n, count, "measured inner collision-surface gap along opposing finger centres, m"],
            tcp_pose=[2*n+count, 7*count, "measured TCP, world xyz/wxyz"],
            joint_effort=[2*n+8*count, len(arms), "clamped kp*(target-q)-kv*qdot estimate, N m; not contact force"])
        self.finger_geometry = {}
        from topogym.robot.grasp_geometry import read_grasp_geometry
        transforms = self._fk(self.measured_q())
        for g in self.groups:
            geometry = read_grasp_geometry(robot,g.name)
            self.finger_geometry[g.name] = [(name,(np.c_[vertices,np.ones(len(vertices))] @ np.linalg.inv(transforms[name]).T)[:,:3])
                for name,(vertices,_) in zip(g.grasp.finger_links,geometry["surfaces"])]

    @staticmethod
    def _opening(a,b):
        direction=b.mean(axis=0)-a.mean(axis=0)
        norm=np.linalg.norm(direction)
        if norm < 1e-10:
            raise RuntimeError("Degenerate gripper measurement")
        direction/=norm
        return max(0.,float((b @ direction).min()-(a @ direction).max()))

    def opening_limits(self,g):
        values=[]
        for command in (g.grasp.closed_position,g.grasp.open_position):
            q=self.home.copy()
            for name in g.finger_joints:
                q[self.names.index(name)]=command
            if self.robot.description.robot_id == "panda_robotiq":
                # Nominal parallel-pad pose of the original Robotiq four-bar
                # linkage. Updating its drivers alone leaves the passive pad
                # tree at home and would falsely report zero aperture travel.
                for side in ("left","right"):
                    for suffix,sign in (("spring_link_joint",1),("follower_joint",-1),("coupler_joint",-1)):
                        q[self.names.index(f"r85_{side}_{suffix}")]=sign*command
            transforms=self._fk(q)
            surfaces=[(np.c_[v,np.ones(len(v))] @ transforms[name].T)[:,:3] for name,v in self.finger_geometry[g.name]]
            values.append(self._opening(*surfaces))
        return values

    @property
    def action_dim(self):
        return len(self.action_layout)

    def command(self, row):
        row = np.asarray(row, dtype=float)
        if row.shape != (self.action_dim,) or not np.isfinite(row).all():
            raise ValueError("Wrong canonical action layout")
        result, offset = {}, 0
        for g in self.groups:
            n = len(g.arm_joints)
            result[g.name] = dict(joint_position_rad=row[offset:offset+n].tolist(),
                                 **{g.gripper_field: float(row[offset+n])})
            offset += n+1
        return self.robot.validate_action(result)

    def targets(self):
        targets = self.robot.capture_state().targets
        return np.concatenate([np.r_[targets[g.name]["joint_position_rad"], targets[g.name][g.gripper_field]] for g in self.groups])

    def measured_q(self):
        return to_numpy(self.entity.get_qpos()).reshape(-1)[self.q_indices].copy()

    def measure(self):
        measured = self.robot.observe()
        q = self.measured_q()
        velocity = to_numpy(self.entity.get_dofs_velocity()).reshape(-1)[self.dof_indices]
        openings, tcp, efforts = [], [], []
        from topogym.robot.grasp_geometry import read_grasp_geometry
        for g in self.groups:
            values = measured[g.name]
            geometry = read_grasp_geometry(self.robot, g.name)
            a, b = [v for v, _ in geometry["surfaces"]]
            openings.append(self._opening(a,b))
            tcp.extend(np.r_[values["tcp_position_world_m"], values["tcp_orientation_wxyz"]])
            n = len(g.arm_joints)
            effort = (np.asarray(g.kp[:n]) * (values["joint_position_target_rad"] - values["joint_position_rad"])
                      - np.asarray(g.kv[:n]) * values["joint_velocity_rad_s"])
            efforts.extend(np.clip(effort, -np.asarray(g.force[:n]), g.force[:n]))
        result = np.asarray([*q, *velocity, *openings, *tcp, *efforts], dtype=np.float32)
        if not np.isfinite(result).all():
            raise RuntimeError("Non-finite robot telemetry")
        return result

    def _fk(self, q):
        from topogym.solvers.genesis_kinematics import GenesisFKSolver
        q = np.asarray(q, dtype=float)
        if q.shape != (len(self.names),) or not np.isfinite(q).all():
            raise ValueError("Wrong kinematics q layout")
        full = self.template.copy()
        full[self.q_indices] = q
        result = GenesisFKSolver(self.entity).solve(full)
        positions = result["position_world_m"].reshape(-1, 3)
        quaternions = result["orientation_wxyz"].reshape(-1, 4)
        matrices = {link.name: matrix(np.r_[positions[link.idx_local], quaternions[link.idx_local]]) for link in self.entity.links}
        for g, frame in zip(self.groups, self.tcp_frames):
            matrices[frame] = matrices[g.hand_link] @ matrix(np.r_[g.tcp_position_in_hand_m, g.tcp_orientation_in_hand_wxyz])
        return matrices

    def kinematics(self, request):
        if not isinstance(request, dict) or request.get("op") not in {"fk", "ik"}:
            raise ValueError("Expected fk or ik")
        allowed = {"op", "q", "links"} if request["op"] == "fk" else {"op", "targets", "seed", "tol_pos_m", "tol_rot_rad", "max_iters"}
        if set(request) - allowed:
            raise ValueError("Unknown kinematics field; robot base is fixed")
        if request["op"] == "fk":
            links = request.get("links", self.links + self.tcp_frames)
            if not isinstance(links, list) or any(x not in self.links + self.tcp_frames for x in links):
                raise ValueError("Unknown kinematic link")
            transforms = self._fk(request.get("q", []))
            return dict(ok=True, op="fk", frame="world", poses={name: pose(transforms[name]) for name in links})
        targets = request.get("targets")
        if not isinstance(targets, dict) or not targets or set(targets) - set(self.tcp_frames):
            raise ValueError("IK targets must name TCP frames")
        targets = {k: matrix(v) for k, v in targets.items()}
        seed = np.asarray(request.get("seed", self.home), dtype=float)
        if seed.shape != self.home.shape or not np.isfinite(seed).all():
            raise ValueError("Wrong IK seed layout")
        limits = [request.get("tol_pos_m", 1e-4), request.get("tol_rot_rad", 1e-3)]
        if any(isinstance(x, bool) or not isinstance(x, (int, float)) or not np.isfinite(x) or not 0 < x <= 1 for x in limits):
            raise ValueError("Invalid IK tolerance")
        count = request.get("max_iters", 100)
        if type(count) is not int or not 1 <= count <= 1000:
            raise ValueError("Invalid IK iteration limit")
        moving = [self.names.index(name) for g in self.groups for name in g.arm_joints]
        best = np.clip(seed, self.bounds[:, 0], self.bounds[:, 1])
        def residual(values):
            candidate = best.copy()
            candidate[moving] = values
            found = self._fk(candidate)
            return np.concatenate([np.r_[found[k][:3, 3] - target[:3, 3],
                Rotation.from_matrix(target[:3, :3].T @ found[k][:3, :3]).as_rotvec()] for k, target in targets.items()])
        from scipy.optimize import least_squares
        result = least_squares(residual, best[moving], bounds=(self.bounds[moving, 0], self.bounds[moving, 1]),
                               max_nfev=count, diff_step=1e-4, xtol=1e-9, ftol=1e-9, gtol=1e-9)
        best[moving] = result.x
        errors = residual(result.x).reshape(-1, 6)
        errors = {name: dict(pos_m=float(np.linalg.norm(e[:3])), rot_rad=float(np.linalg.norm(e[3:]))) for name, e in zip(targets, errors)}
        return dict(ok=all(e["pos_m"] <= limits[0] and e["rot_rad"] <= limits[1] for e in errors.values()),
                    op="ik", frame="world", q=best.tolist(), error=errors)

    def ee_command(self, row):
        targets = {frame: row[8*i:8*i+7] for i, frame in enumerate(self.tcp_frames)}
        result = self.kinematics(dict(op="ik", targets={k: list(v) for k,v in targets.items()}, seed=self.measured_q().tolist()))
        if not result["ok"]:
            return self.targets(), result
        row_out = []
        for i, g in enumerate(self.groups):
            row_out.extend(result["q"][self.names.index(name)] for name in g.arm_joints)
            row_out.append(float(row[8*i+7]))
        return np.asarray(row_out), result

    def specifications(self):
        joints, gains, grippers, tcp = [], {}, {}, {}
        for g, frame in zip(self.groups, self.tcp_frames):
            for i, name in enumerate(g.arm_joints + g.actuated_fingers):
                finger = i >= len(g.arm_joints)
                prismatic = finger and g.gripper_field.endswith("_m")
                joints.append(dict(name=name, type="prismatic" if prismatic else "revolute", unit="m" if prismatic else "rad",
                    position_limits=list(g.gripper_limits if finger else g.arm_limits_rad[i]), velocity_limit=None,
                    effort_limit=float(g.force[i]), group=g.name))
                gains[name] = dict(stiffness=float(g.kp[i]), damping=float(g.kv[i]))
            grippers[g.name] = dict(joints=list(g.finger_joints), opening_m=self.opening_limits(g),
                opening_note="nominal parallel-pad collision-envelope gap at closed/open coordinates; compliance/constraint drift is reflected in measured proprio, not this nominal range", command=dict(field=g.gripper_field,
                range=list(g.gripper_limits), open=float(g.grasp.open_position), closed=float(g.grasp.closed_position),
                meaning="native actuator coordinate; gripper switches at the row, no interpolation"), tcp_frame=frame)
            tcp[frame] = dict(parent_link=g.hand_link, link_T_frame=matrix(np.r_[g.tcp_position_in_hand_m,g.tcp_orientation_in_hand_wxyz]).tolist(),
                              definition="fixed robot tool reference; same frame as ee_pose and tcp_pose")
        hz = 1 / self.timing["control_dt_s"]
        model = dict(name=self.robot.description.robot_id, base=dict(type="fixed", pose=pose(self._fk(self.home)[self.links[0]])),
                     joints=joints, grippers=grippers, tcp=tcp,
                     controller=dict(type="joint-position PD", control_hz=hz, physics_hz=1/self.timing["physics_dt_s"], gains=gains))
        kin = dict(endpoint="/kinematics", joint_names=self.names, frame="world", quaternion_order="wxyz", links=self.links+self.tcp_frames,
                   tcp_frames=self.tcp_frames, ee_frames=self.tcp_frames, ik_targets=self.tcp_frames,
                   ik=dict(solver="bounded least-squares over Genesis FK", collision_checking="none", max_iters=100,
                           tol_pos_m=1e-4, tol_rot_rad=1e-3))
        units=[u for g in self.groups for u in (["rad"]*len(g.arm_joints)+["m" if g.gripper_field.endswith("_m") else "rad"])]
        types = dict(joint_position=dict(dim=self.action_dim, layout=self.action_layout, units=units, limits=np.asarray(self.action_limits).tolist(),
                     semantics="arm joint targets interpolate; native gripper coordinate switches per row; dt is a control-period multiple"),
                     ee_pose=dict(dim=len(self.ee_layout), layout=self.ee_layout, units=[u for g in self.groups for u in ["m","m","m","1","1","1","1","m" if g.gripper_field.endswith("_m") else "rad"]],
                     semantics="world TCP xyz/wxyz per arm and native gripper target; IK once per row; dt sets hold duration; failed IK holds"),
                     not_yet=["joint_delta","joint_velocity","ee_delta","joint_torque"])
        return model, kin, types
