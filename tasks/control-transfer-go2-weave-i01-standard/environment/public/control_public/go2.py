"""Public data-only Go2 control ABI and nominal kinematics; no private plant access."""

import json

import numpy as np

from .go2_data import (
    CHANNELS as CHANNELS,
    UNITS as UNITS,
    PARAMS as PARAMS,
    LEGS as LEGS,
    JOINT_NAMES as JOINT_NAMES,
    default_policy as default_policy,
    validate as validate,
)

TORQUE_LIMIT = np.tile([23.7, 23.7, 35.55], 4)
VELOCITY_LIMIT = np.tile([30.1, 30.1, 20.07], 4)
DEFAULT_Q = np.tile([0.0, 0.9, -1.8], 4)
LOWER = np.array([-1.0472, -1.5708, -2.7227] * 2 + [-1.0472, -0.5236, -2.7227] * 2)
UPPER = np.array([1.0472, 3.4907, -0.83776] * 2 + [1.0472, 4.5379, -0.83776] * 2)
HIP = np.array([[0.1934, 0.0465, 0], [0.1934, -0.0465, 0], [-0.1934, 0.0465, 0], [-0.1934, -0.0465, 0]])
SIDES = np.array([1, -1, 1, -1])


def rotation(rpy):
    r, p, y = rpy
    cr, sr, cp, sp, cy, sy = np.cos(r), np.sin(r), np.cos(p), np.sin(p), np.cos(y), np.sin(y)
    return np.array(
        [
            [cy * cp, cy * sp * sr - sy * cr, cy * sp * cr + sy * sr],
            [sy * cp, sy * sp * sr + cy * cr, sy * sp * cr - cy * sr],
            [-sp, cp * sr, cp * cr],
        ]
    )


def forward_leg(q, side):
    a, b, c = q
    x = -0.213 * (np.sin(b) + np.sin(b + c))
    z = -0.213 * (np.cos(b) + np.cos(b + c))
    return np.array([x, side * 0.0955 * np.cos(a) - z * np.sin(a), side * 0.0955 * np.sin(a) + z * np.cos(a)])


def inverse_leg(foot, side):
    x, y, z = foot
    zleg = -np.sqrt(max(y * y + z * z - 0.0955**2, 0.005))
    hip = np.arctan2(y, -z) - np.arctan2(side * 0.0955, -zleg)
    calf = -np.arccos(np.clip((x * x + zleg * zleg - 2 * 0.213**2) / (2 * 0.213**2), -0.9999, 0.9999))
    thigh = np.arctan2(-x, -zleg) - calf / 2
    return np.array([hip, thigh, calf])


class Controller:
    """Frozen numeric wrapper: commands and noisy proprioception only, never MjData."""

    def __init__(self, policy):
        self.policy = json.loads(validate(policy))
        self.p = self.policy["parameters"]
        self.kp, self.kd = np.array(self.policy["kp"]), np.array(self.policy["kd"])

    def targets(self, t, task, obs, command):
        p = self.p
        self.kp = np.array(self.policy["kp"])
        self.kd = np.array(self.policy["kd"])
        q, rpy, omega = obs[:12], obs[24:27], obs[27:30]
        target_rp = command[3:5]
        rp = target_rp + p["attitude_gain"] * (target_rp - rpy[:2]) - p["rate_gain"] * omega[:2]
        rp = np.clip(rp, -0.6, 0.6)
        height = p["height"]
        feet = HIP.copy()
        feet[:, 1] += SIDES * p["stance_width"]
        feet[:, 2] = -height
        forces = np.tile([0.0, 0.0, -15.0 * 9.81 / 4 * p["support"]], (4, 1))
        if task == "weave" and t >= 1:
            phase = (t - 1) / p["period"] + np.array([0, 0.5, 0.5, 0])
            phase %= 1
            for leg in range(4):
                vx, vy, wz = command[:3]
                wz += -p["yaw_gain"] * rpy[2] - 0.1 * omega[2]
                vy *= p["lateral_gain"]
                velocity = np.array([vx - wz * feet[leg, 1] * p["yaw_gain"], vy + wz * feet[leg, 0] * p["yaw_gain"]])
                swing = phase[leg] >= 0.6
                if swing:
                    s = (phase[leg] - 0.6) / 0.4
                    x = -0.3 + 0.6 * (3 * s * s - 2 * s * s * s)
                    feet[leg, 2] += p["swing_height"] * np.sin(np.pi * s)
                    forces[leg] *= 0.0
                else:
                    x = 0.3 - phase[leg]
                    forces[leg] *= 1.65
                feet[leg, :2] += velocity * p["period"] * x * p["stride_gain"]
        if task in ("forward-jump", "yaw-jump"):
            start, crouch = 1.2, 0.5
            push = p["push_duration"]
            if start <= t < start + crouch:
                s = (t - start) / crouch
                height = height + (p["crouch_height"] - height) * (3 * s * s - 2 * s * s * s)
            elif start + crouch <= t < start + crouch + push:
                s = (t - start - crouch) / push
                self.kp *= p["push_pd_scale"]
                self.kd *= max(p["push_pd_scale"], 0.2)
                height = p["crouch_height"] + (p["extend_height"] - p["crouch_height"]) * s
                if task == "forward-jump":
                    feet[:, 0] -= command[5] * p["jump_forward"] * 0.12 * s
                else:
                    feet[:, :2] = feet[:, :2] @ rotation([0, 0, command[6] * p["jump_yaw"] * 0.16 * s])[:2, :2]
                forces[:, 2] *= p["push_gain"]
                if task == "forward-jump":
                    forces[:, 0] = -command[5] * p["jump_forward"] * 50
                else:
                    moment = command[6] * p["jump_yaw"] * 15
                    forces[:, 0] = moment * feet[:, 1]
                    forces[:, 1] = -moment * feet[:, 0]
            elif start + crouch + push <= t < start + crouch + push + p["flight_time"]:
                height = p["crouch_height"]
                forces[:] = 0
            elif t >= start + crouch + push + p["flight_time"]:
                height = p["landing_height"]
                self.kd *= 1.5
                if task == "yaw-jump":
                    yaw_error = np.arctan2(np.sin(command[6] - rpy[2]), np.cos(command[6] - rpy[2]))
                    correction = np.clip(0.3 * yaw_error - 0.08 * omega[2], -0.35, 0.35)
                    feet[:, :2] = feet[:, :2] @ rotation([0, 0, correction])[:2, :2]
            feet[:, 2] = -height
        feet = feet @ rotation([rp[0], rp[1], 0])
        targets, feedforward = [], []
        for leg in range(4):
            target = inverse_leg(feet[leg] - HIP[leg], SIDES[leg])
            qi = q[3 * leg : 3 * leg + 3]
            eps = 1e-5
            jac = np.column_stack(
                [
                    (
                        forward_leg(qi + np.eye(3)[j] * eps, SIDES[leg])
                        - forward_leg(qi - np.eye(3)[j] * eps, SIDES[leg])
                    )
                    / (2 * eps)
                    for j in range(3)
                ]
            )
            targets.extend(target)
            feedforward.extend(jac.T @ forces[leg])
        trajectory = np.array(self.policy["trajectory"])
        phase = np.clip((t / 6 if task != "weave" else t / p["period"] % 1) * 16, 0, 16)
        k = min(int(phase), 15)
        offset = trajectory[k] * (1 - (phase - k)) + trajectory[k + 1] * (phase - k)
        error = np.concatenate([target_rp - rpy[:2], [0.0], -omega])
        target = (
            np.array(targets) + np.array(self.policy["joint_bias"]) + offset + np.array(self.policy["feedback"]) @ error
        )
        return np.clip(target, LOWER, UPPER), np.array(feedforward)
