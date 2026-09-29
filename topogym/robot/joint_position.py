"""Shared model-driven joint targets and restorable control state; no clock."""

from __future__ import annotations
from copy import deepcopy
from dataclasses import dataclass
from typing import Mapping
import numpy as np
from topogym.utils.arrays import to_numpy
from .description import describe_robot


@dataclass(frozen=True)
class RobotState:
    targets: dict
    robot_id: str = "aloha"


class JointPositionRobot:
    def __init__(self, entity, config):
        self.entity, self.config = entity, config
        self.description = describe_robot(config)
        self.groups = {g.name: g for g in self.description.groups}
        self.sides = tuple(self.groups)
        self._targets, self._indices, self._q_indices, self._hands, self._controlled = (
            {},
            {},
            {},
            {},
            {},
        )
        first = self.description.groups[0]
        self.joint_limits_rad = np.asarray(first.arm_limits_rad)
        self.gripper_limits_m = (
            first.gripper_limits if first.gripper_field.endswith("_m") else None
        )
        for name, group in self.groups.items():
            joints = [
                entity.get_joint(n) for n in group.arm_joints + group.finger_joints
            ]
            if any(
                len(j.dofs_idx_local) != 1 or len(j.qs_idx_local) != 1 for j in joints
            ):
                raise ValueError("Controlled joints must have one scalar coordinate")
            self._indices[name] = [j.dofs_idx_local[0] for j in joints]
            self._q_indices[name] = [j.qs_idx_local[0] for j in joints]
            self._hands[name] = entity.get_link(group.hand_link)
            controlled = [
                entity.get_joint(n).dofs_idx_local[0]
                for n in group.arm_joints + group.actuated_fingers
            ]
            self._controlled[name] = controlled
            if any(
                len(v) != len(controlled) for v in (group.kp, group.kv, group.force)
            ):
                raise ValueError(f"Controller gains do not match {name} actuator count")
            entity.set_dofs_kp(np.asarray(group.kp), controlled)
            entity.set_dofs_kv(np.asarray(group.kv), controlled)
            forces = np.asarray(group.force)
            entity.set_dofs_force_range(-forces, forces, controlled)
            n = len(group.arm_joints)
            self._targets[name] = dict(
                joint_position_rad=list(group.home[:n]),
                **{group.gripper_field: float(group.home[n])},
            )
        self.validate_action(self._targets)

    @property
    def action_spec(self):
        groups = {
            name: dict(
                arm_joint_names=list(g.arm_joints),
                joint_limits_rad=list(g.arm_limits_rad),
                gripper_field=g.gripper_field,
                gripper_limits=list(g.gripper_limits),
                gripper_semantics="native joint coordinate, not full aperture",
            )
            for name, g in self.groups.items()
        }
        return dict(
            robot_id=self.description.robot_id,
            arms=list(self.groups),
            groups=groups,
            omission="Omitted groups/fields retain their targets; empty action holds targets",
        )

    def validate_action(self, action):
        if not isinstance(action, Mapping) or set(action) - self.groups.keys():
            raise ValueError(f"Action groups must be among {tuple(self.groups)}")
        canonical = {}
        for name, command in action.items():
            g = self.groups[name]
            if (
                not isinstance(command, Mapping)
                or not command
                or set(command) - {"joint_position_rad", g.gripper_field}
            ):
                raise ValueError(f"Invalid {name} command fields")
            canonical[name] = {}
            if "joint_position_rad" in command:
                raw = command["joint_position_rad"]
                q = np.asarray(raw)
                bounds = np.asarray(g.arm_limits_rad)
                if (
                    q.shape != (len(g.arm_joints),)
                    or q.dtype.kind not in "fiu"
                    or not np.isfinite(q).all()
                    or any(isinstance(v, (bool, np.bool_)) for v in raw)
                ):
                    raise ValueError(
                        f"Expected {len(g.arm_joints)} finite joint angles"
                    )
                if np.any(q < bounds[:, 0]) or np.any(q > bounds[:, 1]):
                    raise ValueError("Joint target outside model limits")
                canonical[name]["joint_position_rad"] = q.astype(float).tolist()
            if g.gripper_field in command:
                value = command[g.gripper_field]
                if (
                    isinstance(value, (bool, np.bool_))
                    or not isinstance(value, (int, float, np.integer, np.floating))
                    or not np.isfinite(value)
                    or not g.gripper_limits[0] <= value <= g.gripper_limits[1]
                ):
                    raise ValueError(
                        f"Invalid native gripper target: {g.gripper_field}"
                    )
                canonical[name][g.gripper_field] = float(value)
        return canonical

    def apply_action(self, action):
        command = self.validate_action(action)
        targets = deepcopy(self._targets)
        for name, values in command.items():
            targets[name].update(values)
        for name, g in self.groups.items():
            target = targets[name]
            self.entity.control_dofs_position(
                np.r_[
                    target["joint_position_rad"],
                    [target[g.gripper_field]] * len(g.actuated_fingers),
                ],
                self._controlled[name],
            )
        self._targets = targets

    def reset_home(self):
        for name, g in self.groups.items():
            if getattr(self.entity.material, "coup_type", None) == "external_articulation":
                current = to_numpy(self.entity.get_qpos()).reshape(-1)[self._q_indices[name]]
                if not np.allclose(current, g.home, rtol=0, atol=1e-10):
                    raise RuntimeError("IPC robot home must be declared before World.build")
            else:
                self.entity.set_dofs_position(
                    np.asarray(g.home), self._indices[name], zero_velocity=True
                )
            n = len(g.arm_joints)
            self._targets[name] = dict(
                joint_position_rad=list(g.home[:n]),
                **{g.gripper_field: float(g.home[n])},
            )
        self.apply_action({})
        from topogym.solvers.genesis_kinematics import prepare_kinematics
        prepare_kinematics(self.entity, self._hands[self.sides[0]])

    def observe(self):
        from scipy.spatial.transform import Rotation
        positions = to_numpy(self.entity.get_qpos()).reshape(-1)
        velocities = to_numpy(self.entity.get_dofs_velocity()).reshape(-1)
        result = {}
        for name, g in self.groups.items():
            q = positions[self._q_indices[name]]
            n = len(g.arm_joints)
            hand = self._hands[name]
            unit = "m" if g.gripper_field.endswith("_m") else "rad"
            hand_position = to_numpy(hand.get_pos()).reshape(-1, 3)[0]
            hand_quat = to_numpy(hand.get_quat()).reshape(-1, 4)[0]
            rotation = Rotation.from_quat(hand_quat[[1, 2, 3, 0]])
            offset_rotation = Rotation.from_quat(np.asarray(g.tcp_orientation_in_hand_wxyz)[[1, 2, 3, 0]])
            tcp_quat = (rotation * offset_rotation).as_quat()[[3, 0, 1, 2]]
            if tcp_quat[0] < 0:
                tcp_quat = -tcp_quat
            result[name] = dict(
                joint_position_rad=q[:n].copy(),
                joint_velocity_rad_s=velocities[self._indices[name][:n]].copy(),
                **{f"finger_position_{unit}": q[n:].copy()},
                hand_position_world_m=hand_position,
                hand_orientation_wxyz=hand_quat,
                tcp_position_world_m=hand_position + rotation.apply(g.tcp_position_in_hand_m),
                tcp_orientation_wxyz=tcp_quat,
                joint_position_target_rad=np.asarray(
                    self._targets[name]["joint_position_rad"]
                ).copy(),
                **{
                    f"gripper_position_target_{unit}": self._targets[name][
                        g.gripper_field
                    ]
                },
            )
        return result

    def capture_state(self):
        return RobotState(deepcopy(self._targets), self.description.robot_id)

    def restore_state(self, state):
        if (
            not isinstance(state, RobotState)
            or state.robot_id != self.description.robot_id
        ):
            raise ValueError("Robot state belongs to another embodiment")
        if set(state.targets) != set(self.groups) or any(
            set(state.targets[name]) != {"joint_position_rad", group.gripper_field}
            for name, group in self.groups.items()
        ):
            raise ValueError(
                "Robot checkpoint must contain every group and target field"
            )
        self.validate_action(state.targets)
        self._targets = deepcopy(state.targets)
        # World restores exact control buffers; do not reissue commands here.


def make_robot(entity, config):
    return JointPositionRobot(entity, config)
