"""CPU PhysX torque servo with Ruckig references at every physics substep.

All native drives are disabled. Gravity remains enabled on EVERY robot link.
Explicit qf contains PD + gravity/coriolis + inverse-dynamics feedforward, then
TOTAL effort and slew are limited. Solver contact forces are not motor torque.
No state velocity clipping, mass changes, or kinematic robot motion is used.
"""

from __future__ import annotations
import numpy as np
from ruckig import Ruckig, InputParameter, OutputParameter, Result, Synchronization
from .panda_limits import (
    LOWER,
    UPPER,
    VELOCITY,
    ACCELERATION,
    JERK,
    TORQUE,
    TORQUE_RATE,
    FINGER_FORCE,
)


class ConstrainedController:
    def __init__(
        self, robot, dt: float, acceleration_fraction=0.55, jerk_fraction=0.05
    ):
        self.robot = robot
        self.dt = dt
        self.pin = robot.create_pinocchio_model()
        self.tcp_index = next(
            i for i, l in enumerate(robot.links) if l.entity.name == "panda_hand_tcp"
        )
        self.otg = Ruckig(9, dt)
        self.input = InputParameter(9)
        self.input.synchronization = Synchronization.Phase
        self.output = OutputParameter(9)
        self.input.max_velocity = np.r_[VELOCITY * 0.65, 0.025, 0.025].tolist()
        self.input.max_acceleration = np.r_[
            ACCELERATION * acceleration_fraction, 0.1, 0.1
        ].tolist()
        self.input.max_jerk = np.r_[JERK * jerk_fraction, 2.0, 2.0].tolist()
        self.effort_limit = np.r_[TORQUE, FINGER_FORCE, FINGER_FORCE]
        self.rate_limit = np.r_[TORQUE_RATE, 150.0, 150.0]
        self.kp = np.array([500, 600, 500, 500, 180, 160, 100, 300, 300])
        self.kd = np.array([45, 48, 35, 32, 12, 10, 7, 12, 12])
        self.disable_native_drives()
        self.reset()

    def disable_native_drives(self):
        for link in self.robot.links:
            link.disable_gravity = False
        for j in self.robot.active_joints:
            j.set_drive_properties(0.0, 0.0, 0.0, mode="force")
            j.set_friction(0.0)
        for j, lo, hi in zip(self.robot.active_joints[:7], LOWER, UPPER):
            j.set_limits([[float(lo), float(hi)]])

    def reset(self):
        self.disable_native_drives()
        q = self.robot.qpos.astype(float)
        self.input.current_position = q.tolist()
        self.input.current_velocity = [0.0] * 9
        self.input.current_acceleration = [0.0] * 9
        self.input.target_position = q.tolist()
        self.input.target_velocity = [0.0] * 9
        self.input.target_acceleration = [0.0] * 9
        self.torque = np.clip(
            self.robot.compute_passive_force(), -self.effort_limit, self.effort_limit
        )
        self.previous_torque = self.torque.copy()
        self.reference = q.copy()
        self.reference_velocity = np.zeros(9)
        self.reference_acceleration = np.zeros(9)
        self.reference_jerk = np.zeros(9)
        self.saturation_count = 0
        self.plan_initial = None
        self.plan_steps = 0
        self.otg.reset()
        self.pin.compute_forward_kinematics(q)
        self.reference_tcp_pose = self.robot.pose * self.pin.get_link_pose(
            self.tcp_index
        )
        self.reference_tcp_velocity = np.zeros(3)
        self.reference_tcp_acceleration = np.zeros(3)
        self.reference_tcp_omega = np.zeros(3)

    def set_action(self, action: np.ndarray):
        action = np.asarray(action, dtype=float).reshape(-1)
        if action.shape != (8,) or not np.isfinite(action).all():
            raise ValueError(
                "Action must be finite [7 joint targets in rad, total aperture in m]."
            )
        if (
            np.any(action[:7] < LOWER - 1e-7)
            or np.any(action[:7] > UPPER + 1e-7)
            or not -1e-8 <= action[7] <= 0.08000001
        ):
            raise ValueError("Joint target or aperture outside the Panda action space.")
        self.input.target_position = np.r_[
            np.clip(action[:7], LOWER, UPPER),
            np.clip(action[7], 0, 0.08) / 2,
            np.clip(action[7], 0, 0.08) / 2,
        ].tolist()

    def step(self):
        before = {
            key: list(getattr(self.input, key))
            for key in (
                "current_position",
                "current_velocity",
                "current_acceleration",
                "target_position",
                "target_velocity",
                "target_acceleration",
            )
        }
        result = self.otg.update(self.input, self.output)
        if self.output.new_calculation:
            self.plan_initial = before
            self.plan_steps = 1
        else:
            self.plan_steps += 1
        if result < Result.Working:
            raise RuntimeError(f"Ruckig failed: {result}")
        old_acc = self.reference_acceleration.copy()
        self.reference = np.array(self.output.new_position)
        self.reference_velocity = np.array(self.output.new_velocity)
        self.reference_acceleration = np.array(self.output.new_acceleration)
        self.reference_jerk = (self.reference_acceleration - old_acc) / self.dt
        self.output.pass_to_input(self.input)
        previous_pose = self.reference_tcp_pose
        previous_v = self.reference_tcp_velocity.copy()
        self.pin.compute_forward_kinematics(self.reference)
        self.reference_tcp_pose = self.robot.pose * self.pin.get_link_pose(
            self.tcp_index
        )
        self.reference_tcp_velocity = (
            self.reference_tcp_pose.p - previous_pose.p
        ) / self.dt
        self.reference_tcp_acceleration = (
            self.reference_tcp_velocity - previous_v
        ) / self.dt
        from scipy.spatial.transform import Rotation

        delta = (
            self.reference_tcp_pose.to_transformation_matrix()[:3, :3]
            @ previous_pose.to_transformation_matrix()[:3, :3].T
        )
        self.reference_tcp_omega = Rotation.from_matrix(delta).as_rotvec() / self.dt
        q, v = self.robot.qpos, self.robot.qvel
        passive = self.robot.compute_passive_force()
        mass = self.pin.compute_generalized_mass_matrix(q)
        raw = (
            passive
            + mass @ self.reference_acceleration
            + self.kp * (self.reference - q)
            + self.kd * (self.reference_velocity - v)
        )
        self.previous_torque = self.torque.copy()
        limited = np.clip(raw, -self.effort_limit, self.effort_limit)
        self.torque = np.clip(
            limited,
            self.torque - self.rate_limit * self.dt,
            self.torque + self.rate_limit * self.dt,
        )
        self.saturation_count += int(np.any(abs(raw - limited) > 1e-5))
        self.robot.set_qf(self.torque.astype(np.float32))

    def state(self) -> dict:
        return {
            key: np.asarray(getattr(self.input, key)).tolist()
            for key in (
                "current_position",
                "current_velocity",
                "current_acceleration",
                "target_position",
                "target_velocity",
                "target_acceleration",
            )
        } | {
            "torque": self.torque.tolist(),
            "saturation_count": self.saturation_count,
            "reference_tcp_velocity": self.reference_tcp_velocity.tolist(),
            "reference_tcp_omega": self.reference_tcp_omega.tolist(),
            "plan_initial": self.plan_initial,
            "plan_steps": self.plan_steps,
        }

    def restore(self, state: dict):
        self.otg.reset()
        for key, value in state.items():
            if key not in (
                "torque",
                "saturation_count",
                "reference_tcp_velocity",
                "reference_tcp_omega",
                "plan_initial",
                "plan_steps",
            ):
                setattr(self.input, key, value)
        self.plan_initial = state["plan_initial"]
        self.plan_steps = state["plan_steps"]
        if self.plan_initial is not None:
            for key, value in self.plan_initial.items():
                setattr(self.input, key, value)
            for _ in range(self.plan_steps):
                self.otg.update(self.input, self.output)
                self.output.pass_to_input(self.input)
        self.torque = np.array(state["torque"])
        self.previous_torque = self.torque.copy()
        self.saturation_count = state["saturation_count"]
        self.reference = np.array(state["current_position"])
        self.reference_velocity = np.array(state["current_velocity"])
        self.reference_acceleration = np.array(state["current_acceleration"])
        self.pin.compute_forward_kinematics(self.reference)
        self.reference_tcp_pose = self.robot.pose * self.pin.get_link_pose(
            self.tcp_index
        )
        self.reference_tcp_velocity = np.array(state["reference_tcp_velocity"])
        self.reference_tcp_omega = np.array(state["reference_tcp_omega"])
