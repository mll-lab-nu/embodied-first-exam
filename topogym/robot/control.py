"""Control-mode conversion to common joint targets; never advances physics."""
from collections.abc import Mapping
import numpy as np

from topogym.utils.arrays import to_numpy

MODES = ("JOINT_ABS", "JOINT_DELTA", "EE_ABS", "EE_DELTA")


def action_spec(description, mode):
    if mode not in MODES:
        raise ValueError(f"Unknown control mode: {mode}")
    groups = {}
    for g in description.groups:
        if mode == "JOINT_ABS":
            fields = {"joint_position_rad": [len(g.arm_joints)]}
        elif mode == "JOINT_DELTA":
            fields = {"joint_delta_rad": [len(g.arm_joints)]}
        elif mode == "EE_ABS":
            fields = {"position_world_m": [3], "orientation_wxyz": [4]}
        else:
            fields = {"translation_world_m": [3], "rotation_world_rad": [3]}
        groups[g.name] = dict(
            fields=fields | {g.gripper_field: []}, arm_joint_names=list(g.arm_joints),
            joint_limits_rad=list(g.arm_limits_rad), gripper_field=g.gripper_field,
            gripper_limits=list(g.gripper_limits), gripper_semantics="absolute native joint coordinate, not aperture",
            tcp_position_in_hand_m=g.tcp_position_in_hand_m,
            tcp_orientation_in_hand_wxyz=g.tcp_orientation_in_hand_wxyz,
        )
    return dict(robot_id=description.robot_id, mode=mode, arms=list(groups), groups=groups,
                coordinate_frame="world", delta_reference="measured state before action",
                orientation="unit wxyz; delta uses world rotation vector, left multiplication",
                omission="Empty action/omitted groups hold targets; EE_ABS requires a full pose; omitted EE_DELTA components mean zero measured-state delta; omitted gripper holds")


def _vector(value, count, name):
    x = np.asarray(value)
    if (x.shape != (count,) or x.dtype.kind not in "fiu" or not np.isfinite(x).all()
            or any(isinstance(v, (bool, np.bool_)) for v in value)):
        raise ValueError(f"{name} requires {count} finite numbers")
    return x.astype(float)


def compile_action(robot, action, mode):
    if mode == "JOINT_ABS":
        return robot.validate_action(action)
    if mode not in MODES:
        raise ValueError(f"Unknown control mode: {mode}")
    if not isinstance(action, Mapping) or set(action) - robot.groups.keys():
        raise ValueError("Unknown robot action group")
    from scipy.spatial.transform import Rotation
    normalized, cartesian = {}, {}
    observed = robot.observe()
    # Validate all user input before making any engine query that could use scratch buffers.
    for name, command in action.items():
        g = robot.groups[name]
        allowed = action_spec(robot.description, mode)["groups"][name]["fields"]
        if not isinstance(command, Mapping) or not command or set(command) - allowed.keys():
            raise ValueError(f"Invalid {name} fields for {mode}")
        out = normalized[name] = {}
        if g.gripper_field in command:
            out.update(robot.validate_action({name: {g.gripper_field: command[g.gripper_field]}})[name])
        if mode == "JOINT_DELTA":
            if "joint_delta_rad" in command:
                out["joint_position_rad"] = (observed[name]["joint_position_rad"] +
                    _vector(command["joint_delta_rad"], len(g.arm_joints), "joint_delta_rad")).tolist()
            continue
        pose_fields = set(command) - {g.gripper_field}
        if not pose_fields:
            continue
        measured = observed[name]
        position = np.array(measured["tcp_position_world_m"], copy=True)
        orientation = Rotation.from_quat(np.asarray(measured["tcp_orientation_wxyz"])[[1, 2, 3, 0]])
        if mode == "EE_ABS":
            # Absolute poses are complete, avoiding ambiguous partial pose targets.
            if pose_fields != {"position_world_m", "orientation_wxyz"}:
                raise ValueError("EE_ABS requires both position_world_m and orientation_wxyz")
            position = _vector(command["position_world_m"], 3, "position_world_m")
            q = _vector(command["orientation_wxyz"], 4, "orientation_wxyz")
            if not np.isclose(np.linalg.norm(q), 1., atol=1e-6, rtol=0):
                raise ValueError("orientation_wxyz must be a unit quaternion")
            orientation = Rotation.from_quat(q[[1, 2, 3, 0]])
        else:
            if "translation_world_m" in command:
                position += _vector(command["translation_world_m"], 3, "translation_world_m")
            if "rotation_world_rad" in command:
                orientation = Rotation.from_rotvec(_vector(command["rotation_world_rad"], 3, "rotation_world_rad")) * orientation
        offset = Rotation.from_quat(np.asarray(g.tcp_orientation_in_hand_wxyz)[[1, 2, 3, 0]])
        hand_rotation = orientation * offset.inv()
        cartesian[name] = (position - hand_rotation.apply(g.tcp_position_in_hand_m),
                           hand_rotation.as_quat()[[3, 0, 1, 2]])
    if cartesian:
        from topogym.solvers.genesis_kinematics import GenesisIKSolver
        solver = GenesisIKSolver(robot.entity)
        initial = to_numpy(robot.entity.get_qpos()).reshape(-1).copy()
        for name, (position, quaternion) in cartesian.items():
            g = robot.groups[name]
            candidate = solver.solve_checked(
                link_name=g.hand_link, position_world_m=position, orientation_wxyz=quaternion,
                joint_dof_indices=robot._indices[name][:len(g.arm_joints)], initial_qpos=initial,
            )
            q = candidate[robot._q_indices[name][:len(g.arm_joints)]]
            bounds = np.asarray(g.arm_limits_rad)
            bounded = np.clip(q, bounds[:, 0], bounds[:, 1])
            # A native IK query can retain a measured joint at a stop a few
            # floating-point ulps beyond its model limit. Normalize only that
            # numerical residue; ordinary action limits remain strict and
            # appreciably out-of-range IK results still fail validation.
            if np.max(np.abs(bounded-q), initial=0.) <= 1e-8:
                q = bounded
            normalized[name]["joint_position_rad"] = q.tolist()
    return robot.validate_action(normalized)
