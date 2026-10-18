"""Bounded numeric approach/drift/settle controller. Public nominal information only."""

import json
import math

SCHEMA = "anycar-drift-controller/1"
DT = 0.02
HORIZON = 16.0
BOUNDS = dict(
    route_speed=(0.2, 3.0),
    entry_speed=(0.0, 5.0),
    trigger_x=(-2.6, -0.8),
    turn_time=(0.05, 1.0),
    turn_steer=(-0.36, 0.0),
    counter_time=(0.05, 1.0),
    counter_steer=(0.0, 0.36),
    counter_speed=(0.0, 3.0),
    brake=(0.0, 1.0),
    settle_gain=(0.1, 3.0),
)
DEFAULT = {
    "schema": "anycar-drift-controller/1",
    "route_speed": 1.2,
    "entry_speed": 2.632360684649053,
    "trigger_x": -1.66,
    "turn_time": 0.31204911369245086,
    "turn_steer": -0.36,
    "counter_time": 0.65,
    "counter_steer": 0.36,
    "counter_speed": 0.55,
    "brake": 1.0,
    "settle_gain": 1.0,
}
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
    "requested_speed",
    "requested_steering",
    "rear_brake",
]
UNITS = (
    ["m", "m", "rad", "m/s", "m/s", "rad/s"]
    + ["rad/s"] * 4
    + ["rad", "m/s", "rad", "1"]
)


def validate(p):
    if (
        not isinstance(p, dict)
        or set(p) != {"schema", *BOUNDS}
        or p["schema"] != SCHEMA
    ):
        raise ValueError("Invalid drift controller schema")
    for k, (lo, hi) in BOUNDS.items():
        if (
            type(p[k]) not in (int, float)
            or not lo <= p[k] <= hi
            or not math.isfinite(p[k])
        ):
            raise ValueError("Invalid coefficient")
    return json.dumps(
        p, sort_keys=True, allow_nan=False, separators=(",", ":")
    ).encode()


def wrap(a):
    return (a + math.pi) % (2 * math.pi) - math.pi


class Controller:
    def __init__(self, p, course):
        validate(p)
        from scripts.control_transfer.components.anycarbench.drift import route

        self.path = route(course)
        self.index = 0
        self.p = p
        self.course = course
        self.phase = "route"
        self.timer = 0.0

    def step(self, o):
        import numpy as np

        p = self.p
        x, y, yaw, v = o[:4]
        if self.phase == "route":
            last = min(len(self.path), self.index + 25)
            self.index += int(
                np.argmin(np.sum((self.path[self.index : last] - [x, y]) ** 2, axis=1))
            )
            goal = self.path[min(self.index + 8, len(self.path) - 1)]
            a = wrap(math.atan2(goal[1] - y, goal[0] - x) - yaw)
            steer = math.atan2(
                2 * 0.2965 * math.sin(a), max(0.2, float(np.linalg.norm(goal - [x, y])))
            )
            speed = (
                p["entry_speed"]
                if self.index > len(self.path) - 30
                else p["route_speed"]
            )
            if self.index > len(self.path) - 12:
                self.phase = "entry"
            return [speed, max(-0.36, min(0.36, steer)), 0.0]
        if self.phase == "entry":
            if x <= p["trigger_x"]:
                self.phase = "turn"
                self.timer = 0.0
            else:
                return [
                    p["entry_speed"],
                    max(
                        -0.36,
                        min(
                            0.36,
                            1.5 * wrap(math.pi - yaw)
                            + 0.4 * (y - self.course["radius"]),
                        ),
                    ),
                    0.0,
                ]
        self.timer += DT
        if self.phase == "turn":
            if self.timer >= p["turn_time"]:
                self.phase = "counter"
                self.timer = 0.0
            return [p["entry_speed"], p["turn_steer"], p["brake"]]
        if self.phase == "counter":
            if self.timer >= p["counter_time"]:
                self.phase = "stop"
                self.timer = 0.0
            return [p["counter_speed"], p["counter_steer"], p["brake"]]
        # Stop without a pose teleport or a lateral corrective force.
        return [0.0, max(-0.36, min(0.36, p["settle_gain"] * wrap(math.pi - yaw))), 1.0]
