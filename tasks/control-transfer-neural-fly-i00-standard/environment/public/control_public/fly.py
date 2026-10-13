"""Public figure-eight reference and numeric geometric controller, SI/world frame."""

import copy
import math
import numpy as np

MASS = 2.53
DT = 0.02
DURATION = 6 * 2 * np.pi
DEFAULT = {
    "kp": 6.0,
    "kd": 4.0,
    "ki": 0.4,
    "attitude_gain": 80.0,
    "rate_gain": 16.0,
    "residual": [[0.0] * 7 for _ in range(3)],
}
BOUNDS = {
    "kp": (0.5, 20.0),
    "kd": (0.5, 12.0),
    "ki": (0.0, 5.0),
    "attitude_gain": (20.0, 180.0),
    "rate_gain": (5.0, 40.0),
}


def validate(p):
    if not isinstance(p, dict) or set(p) != set(DEFAULT):
        raise ValueError("Policy fields")
    for k, (a, b) in BOUNDS.items():
        if type(p[k]) not in (int, float) or not math.isfinite(p[k]) or not a <= p[k] <= b:
            raise ValueError("Policy bounds")
    r = np.asarray(p["residual"])
    if r.shape != (3, 7) or r.dtype.kind not in "fi" or not np.isfinite(r).all() or np.max(np.abs(r)) > 20:
        raise ValueError("Residual bounds")
    return copy.deepcopy(p)


def target(t, phase=0.0, yaw=0.0, center=(0.0, 0.0, 1.8)):
    a = t + phase
    c, s = np.cos(yaw), np.sin(yaw)
    R = np.array([[c, -s, 0], [s, c, 0], [0, 0, 1]])
    p = np.array([1.25 * np.sin(a), 0, 0.75 * np.sin(2 * a)])
    v = np.array([1.25 * np.cos(a), 0, 1.5 * np.cos(2 * a)])
    acc = np.array([-1.25 * np.sin(a), 0, -3 * np.sin(2 * a)])
    return R @ p + center, R @ v, R @ acc


class Controller:
    def __init__(self, p):
        self.p = validate(p)
        self.integral = np.zeros(3)

    def action(self, obs):
        p = self.p
        position = np.array(obs["position"])
        velocity = np.array(obs["velocity"])
        goal = np.array(obs["target_position"])
        speed = np.array(obs["target_velocity"])
        acc = np.array(obs["target_acceleration"])
        self.integral = np.clip(self.integral + DT * (goal - position), -2, 2)
        features = np.r_[1, velocity, np.array(obs["quaternion"])[1:]]
        f = (
            MASS
            * (
                acc
                + p["kp"] * (goal - position)
                + p["kd"] * (speed - velocity)
                + p["ki"] * self.integral
                + [0, 0, 9.81]
            )
            - np.array(p["residual"]) @ features
        )
        return f
