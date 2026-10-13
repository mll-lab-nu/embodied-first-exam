"""Small numeric policy ABI: feedback gains and a learned residual force basis.
No agent Python or serialized executable objects run inside the evaluator.
"""

import copy
import json
import numpy as np
from .model import ALLOCATION, CLEARANCE, GRAVITY, MASS, ROTOR_MAX, rotation

VERSION = "landing-policy/2"
FEATURES = 14
DEFAULT = {
    "schema": VERSION,
    "kp_z": 1.0,
    "kd_z": 2.0,
    "kp_xy": 2.0,
    "kd_xy": 2.4,
    "descent_s": 6.0,
    "approach_s": 4.0,
    "residual_coefficients": [[0.0] * FEATURES for _ in range(3)],
}
BOUNDS = {
    "kp_z": (0.4, 8.0),
    "kd_z": (0.5, 8.0),
    "kp_xy": (0.5, 6.0),
    "kd_xy": (0.5, 6.0),
    "descent_s": (4.0, 9.0),
    "approach_s": (2.0, 5.0),
}


def validate(policy):
    if not isinstance(policy, dict) or set(policy) != set(DEFAULT) or policy["schema"] != VERSION:
        raise ValueError("Invalid policy schema")
    for key, (lo, hi) in BOUNDS.items():
        value = policy[key]
        if type(value) not in (int, float) or not np.isfinite(value) or not lo <= value <= hi:
            raise ValueError("Invalid policy parameter")
    values = policy["residual_coefficients"]
    if not isinstance(values, list) or len(values) != 3:
        raise ValueError("Invalid residual model")
    for row in values:
        if not isinstance(row, list) or len(row) != FEATURES:
            raise ValueError("Invalid residual model")
        if any(type(x) not in (int, float) or not np.isfinite(x) or abs(x) > 20 for x in row):
            raise ValueError("Invalid residual model")
    return copy.deepcopy(policy)


def load(path):
    raw = path.read_bytes()
    if len(raw) > 4096:
        raise ValueError("Policy too large")

    def unique(pairs):
        d = {}
        for k, v in pairs:
            if k in d:
                raise ValueError("Duplicate field")
            d[k] = v
        return d

    return validate(json.loads(raw, object_pairs_hook=unique))


def features(obs):
    h = max(0.0, float(obs["position"][2] - CLEARANCE))
    r = rotation(obs["quaternion"])
    return np.r_[
        1.0,
        np.exp(-h / np.array([0.12, 0.35, 0.8])),
        np.clip(obs["velocity"], -2, 2),
        r[:, 2] - [0, 0, 1],
        np.asarray(obs["rotor_rpm"]) / 8000 - 0.8,
    ]


def smooth(t, duration):
    s = np.clip(t / duration, 0, 1)
    blend = 10 * s**3 - 15 * s**4 + 6 * s**5
    rate = (30 * s**2 - 60 * s**3 + 30 * s**4) / duration if 0 < s < 1 else 0.0
    acc = (60 * s - 180 * s**2 + 120 * s**3) / duration**2 if 0 < s < 1 else 0.0
    return blend, rate, acc


class Controller:
    def __init__(self, policy):
        self.policy = validate(policy)
        self.initial_position = None
        self.disarmed = False

    def act(self, obs, oracle_force=None):
        c = self.policy
        p, v = np.array(obs["position"]), np.array(obs["velocity"])
        r = rotation(obs["quaternion"])
        if self.initial_position is None:
            self.initial_position = p.copy()
        t = obs["t"]
        pad = np.asarray(obs["pad_position"])
        # First translate at the initial height, then descend at the fixed pad.
        blend, rate, acc = smooth(t, c["approach_s"])
        delta_xy = pad[:2] - self.initial_position[:2]
        xyref = self.initial_position[:2] + delta_xy * blend
        axy = delta_xy * acc + c["kp_xy"] * (xyref - p[:2]) + c["kd_xy"] * (delta_xy * rate - v[:2])
        duration = c["descent_s"]
        blend, rate, acc = smooth(t - c["approach_s"], duration)
        # Slight below-plane demand allows physical contact with noisy navigation.
        delta = CLEARANCE - 0.015 - self.initial_position[2]
        zref = self.initial_position[2] + delta * blend
        az = delta * acc + c["kp_z"] * (zref - p[2]) + c["kd_z"] * (delta * rate - v[2])
        desired = MASS * np.r_[axy, GRAVITY + az]
        predicted = np.clip(np.asarray(c["residual_coefficients"]) @ features(obs), -6.0, 6.0)
        desired -= predicted if oracle_force is None else oracle_force
        total = np.clip(desired @ r[:, 2], 0, 4 * ROTOR_MAX)
        zaxis = desired / max(np.linalg.norm(desired), 1e-9)
        yaxis = np.cross(zaxis, [1.0, 0.0, 0.0])
        yaxis /= max(np.linalg.norm(yaxis), 1e-9)
        rd = np.column_stack([np.cross(yaxis, zaxis), yaxis, zaxis])
        skew = 0.5 * (rd.T @ r - r.T @ rd)
        er = np.array([skew[2, 1], skew[0, 2], skew[1, 0]])
        torque = -0.8 * er - 0.18 * np.array(obs["omega"])
        commands = np.clip(np.linalg.solve(ALLOCATION, np.r_[total, torque]), 0, ROTOR_MAX)
        if (
            t > c["approach_s"] + duration * 0.75
            and p[2] - CLEARANCE < 0.001
            and abs(v[2]) < 0.12
            and np.linalg.norm(p[:2] - pad[:2]) < 0.12
        ):
            self.disarmed = True
        return np.zeros(4) if self.disarmed else commands
