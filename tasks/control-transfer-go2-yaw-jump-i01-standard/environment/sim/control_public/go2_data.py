"""Stdlib-only public Go2 policy data and bounded JSON validation."""

import json
import math

LEGS = ("FL", "FR", "RL", "RR")
JOINT_NAMES = tuple(f"{leg}_{joint}_joint" for leg in LEGS for joint in ("hip", "thigh", "calf"))
PARAMS = {
    "height": (0.20, 0.36),
    "stance_width": (0.09, 0.18),
    "period": (0.25, 1.2),
    "swing_height": (0.015, 0.13),
    "stride_gain": (0.0, 2.0),
    "lateral_gain": (0.3, 1.5),
    "push_pd_scale": (0.0, 1.0),
    "yaw_gain": (0.0, 2.0),
    "attitude_gain": (0.0, 2.5),
    "rate_gain": (0.0, 0.3),
    "support": (0.0, 2.0),
    "crouch_height": (0.16, 0.28),
    "push_duration": (0.08, 0.35),
    "extend_height": (0.30, 0.42),
    "push_gain": (0.0, 5.0),
    "jump_forward": (0.0, 2.5),
    "jump_yaw": (0.0, 4.0),
    "flight_time": (0.10, 0.7),
    "landing_height": (0.22, 0.35),
}
CHANNELS = (
    list(JOINT_NAMES)
    + [f"dq_{j}" for j in JOINT_NAMES]
    + ["imu_roll", "imu_pitch", "imu_yaw"]
    + ["gyro_x", "gyro_y", "gyro_z"]
    + ["command_vx", "command_vy", "command_yaw_rate", "command_roll", "command_pitch", "command_jump", "command_yaw"]
)
UNITS = ["rad"] * 12 + ["rad/s"] * 12 + ["rad"] * 3 + ["rad/s"] * 3 + ["m/s", "m/s", "rad/s", "rad", "rad", "m", "rad"]


def default_policy():
    """Neutral starting artifact; trained/reference artifacts are operator-owned."""
    return {
        "schema": "go2-controller/1",
        "enabled": True,
        "parameters": dict(
            height=0.30,
            stance_width=0.12,
            period=0.5,
            swing_height=0.06,
            stride_gain=1.0,
            lateral_gain=1.0,
            push_pd_scale=0.25,
            yaw_gain=1.0,
            attitude_gain=0.5,
            rate_gain=0.04,
            support=1.0,
            crouch_height=0.20,
            push_duration=0.16,
            extend_height=0.40,
            push_gain=2.8,
            jump_forward=1.0,
            jump_yaw=1.0,
            flight_time=0.35,
            landing_height=0.28,
        ),
        "kp": [45.0] * 12,
        "kd": [1.4] * 12,
        "joint_bias": [0.0] * 12,
        "trajectory": [[0.0] * 12 for _ in range(17)],
        "feedback": [[0.0] * 6 for _ in range(12)],
    }


def _array(x, shape, lo, hi):
    if not isinstance(x, list) or len(x) != shape[0]:
        raise ValueError("Invalid numeric shape")
    if len(shape) > 1:
        return [_array(v, shape[1:], lo, hi) for v in x]
    if any(type(v) not in (float, int) or not math.isfinite(v) or not lo <= v <= hi for v in x):
        raise ValueError("Invalid numeric value")
    return [float(v) for v in x]


def validate(policy):
    if not isinstance(policy, dict) or set(policy) != {
        "schema",
        "enabled",
        "parameters",
        "kp",
        "kd",
        "joint_bias",
        "trajectory",
        "feedback",
    }:
        raise ValueError("Invalid policy fields")
    if policy["schema"] != "go2-controller/1" or type(policy["enabled"]) is not bool:
        raise ValueError("Invalid schema")
    params = policy["parameters"]
    if not isinstance(params, dict) or set(params) != set(PARAMS):
        raise ValueError("Invalid parameter fields")
    params = {k: _array([params[k]], (1,), *bound)[0] for k, bound in PARAMS.items()}
    clean = dict(schema="go2-controller/1", enabled=policy["enabled"], parameters=params)
    for key, shape, lo, hi in (
        ("kp", (12,), 0, 100),
        ("kd", (12,), 0, 8),
        ("joint_bias", (12,), -0.3, 0.3),
        ("trajectory", (17, 12), -1.5, 1.5),
        ("feedback", (12, 6), -3, 3),
    ):
        clean[key] = _array(policy[key], shape, lo, hi)
    return json.dumps(clean, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()
