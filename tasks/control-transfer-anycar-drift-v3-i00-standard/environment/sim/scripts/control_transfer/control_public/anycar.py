"""Public data-only controller ABI and nominal time-indexed commands."""

import json
import math

SCHEMA = "anycar-controller/1"
DT = 0.02
HORIZON = 24.0
CHANNELS = [
    "x",
    "y",
    "yaw",
    "forward_speed",
    "lateral_speed",
    "yaw_rate",
    "wheel_fl",
    "wheel_fr",
    "wheel_bl",
    "wheel_br",
    "steering",
    "target_x",
    "target_y",
    "target_yaw",
    "target_speed",
    "target_curvature",
    "requested_speed",
    "requested_steering",
]
UNITS = ["m", "m", "rad", "m/s", "m/s", "rad/s"] + ["rad/s"] * 4 + ["rad", "m", "m", "rad", "m/s", "1/m", "m/s", "rad"]
BOUNDS = {
    "position_gain": (0.1, 4.0),
    "heading_gain": (0.1, 4.0),
    "speed_gain": (0.0, 3.0),
    "integral_gain": (0.0, 1.0),
    "drive_scale": (0.0, 2.0),
    "steering_scale": (0.2, 2.0),
    "steering_bias": (-0.12, 0.12),
    "preview": (0.0, 0.3),
}
DEFAULT = {
    "schema": SCHEMA,
    "position_gain": 1.2,
    "heading_gain": 1.0,
    "speed_gain": 0.25,
    "integral_gain": 0.08,
    "drive_scale": 1.0,
    "steering_scale": 1.0,
    "steering_bias": 0.0,
    "preview": 0.06,
}


def validate(policy):
    if not isinstance(policy, dict) or set(policy) != {"schema", *BOUNDS} or policy["schema"] != SCHEMA:
        raise ValueError("Invalid controller schema")
    for k, (lo, hi) in BOUNDS.items():
        v = policy[k]
        if type(v) not in (int, float) or not lo <= v <= hi or not math.isfinite(v):
            raise ValueError("Invalid controller coefficient")
    return json.dumps(policy, sort_keys=True, allow_nan=False, separators=(",", ":")).encode()


def wrap(a):
    return (a + math.pi) % (2 * math.pi) - math.pi


def reference(t, command):
    """One ellipse lap, prescribed in time, including a 1 s smooth acceleration."""
    import numpy as np

    if "track_id" in command:
        from scripts.control_transfer.components.anycarbench.tracks import get_route

        return get_route(command["track_id"], command.get("route_revision", "circuit-sector/1")).reference(t, command)

    a, b, phase, direction = (command[k] for k in ("a", "b", "phase", "direction"))
    rate = 2 * np.pi / (HORIZON - 0.5)
    effective = 0.5 * t * t if t < 1 else t - 0.5
    theta = phase + direction * rate * effective
    w = direction * rate * min(t, 1.0)
    x, y = a * np.cos(theta), b * np.sin(theta)
    vx, vy = -a * np.sin(theta) * w, b * np.cos(theta) * w
    # Geometric tangent remains defined when the commanded starting speed is zero.
    heading = np.arctan2(direction * b * np.cos(theta), -direction * a * np.sin(theta))
    curvature = direction * a * b / ((a * np.sin(theta)) ** 2 + (b * np.cos(theta)) ** 2) ** 1.5
    return np.array([x, y, heading, np.hypot(vx, vy), curvature])


class Controller:
    def __init__(self, policy):
        validate(policy)
        self.p = policy
        self.integral = 0.0

    def step(self, observation, target):
        import numpy as np

        p = self.p
        x, y, yaw, speed = observation[:4]
        # Predict the measured pose to the previewed command time; preview never advances only the target.
        x += (speed * np.cos(yaw) - observation[4] * np.sin(yaw)) * p["preview"]
        y += (speed * np.sin(yaw) + observation[4] * np.cos(yaw)) * p["preview"]
        yaw += observation[5] * p["preview"]
        tx, ty, tyaw, tv, curvature = target
        dx, dy = tx - x, ty - y
        along = dx * np.cos(tyaw) + dy * np.sin(tyaw)
        cross = -dx * np.sin(tyaw) + dy * np.cos(tyaw)
        # Time-indexed target controls both longitudinal and lateral error. No nearest-waypoint lookup.
        desired_speed = np.clip(tv + p["position_gain"] * along, 0, 2.8)
        self.integral = float(np.clip(self.integral + (desired_speed - speed) * DT, -2, 2))
        drive = p["drive_scale"] * (
            desired_speed + p["speed_gain"] * (desired_speed - speed) + p["integral_gain"] * self.integral
        )
        steer = (
            np.arctan(0.2965 * curvature)
            + p["heading_gain"] * wrap(tyaw - yaw)
            + np.arctan2(p["position_gain"] * cross, max(tv, 0.4))
        )
        return np.array(
            [np.clip(drive, -0.5, 3.0), np.clip(p["steering_scale"] * steer + p["steering_bias"], -0.36, 0.36)]
        )
