"""Numeric, observation-driven drift controller with anticipatory countersteering.

Only public route commands and the declared noisy measurement vector are used.
No deployment dynamics, contact flags, monitor state or private seeds are inputs.
"""

import json
import math

SCHEMA = "anycar-drift-controller/3"
BOUNDS = {
    "route_speed": (0.2, 3.0),
    "entry_speed": (0.0, 5.0),
    "accelerate_index": (70.0, 110.0),
    "drift_lead_m": (0.2, 1.8),
    "trigger_preview_s": (0.0, 0.3),
    "turn_speed": (0.0, 5.0),
    "turn_steer": (0.2, 0.36),
    "yaw_preview_s": (0.0, 0.5),
    "brake_remaining_rad": (0.0, math.pi),
    "brake_speed": (0.0, 3.0),
    "counter_offset_rad": (-0.3, 0.5),
    "heading_gain": (0.1, 4.0),
    "yaw_rate_gain": (0.0, 1.0),
    "brake": (0.0, 1.0),
}
DEFAULT = {
    "schema": "anycar-drift-controller/3",
    "route_speed": 1.2,
    "entry_speed": 4.87477733242999,
    "accelerate_index": 98.0,
    "drift_lead_m": 1.49573696028281,
    "trigger_preview_s": 0.0,
    "turn_speed": 3.7608570656700038,
    "turn_steer": 0.3331896227491897,
    "yaw_preview_s": 0.05530469264397912,
    "brake_remaining_rad": 1.781540780795078,
    "brake_speed": 0.2223729129498621,
    "counter_offset_rad": 0.0,
    "heading_gain": 0.73,
    "yaw_rate_gain": 0.46,
    "brake": 1.0,
}


def validate(policy):
    if (
        not isinstance(policy, dict)
        or set(policy) != {"schema", *BOUNDS}
        or policy["schema"] != SCHEMA
    ):
        raise ValueError("Invalid feedback drift controller schema")
    for key, (lo, hi) in BOUNDS.items():
        value = policy[key]
        if (
            type(value) not in (int, float)
            or not math.isfinite(value)
            or not lo <= value <= hi
        ):
            raise ValueError("Invalid feedback drift coefficient")
    return json.dumps(
        policy, sort_keys=True, allow_nan=False, separators=(",", ":")
    ).encode()


class Controller:
    def __init__(self, policy, course):
        from scripts.control_transfer.components.anycarbench.drift_v3 import route

        validate(policy)
        self.p = policy
        self.course = course
        self.path = route(course)
        self.index = 0
        self.phase = "route"
        self.timer = 0.0
        self.heading = math.pi
        self.previous_yaw = None

    def step(self, observation):
        import numpy as np

        from .anycar_drift_v3 import DT, wrap

        p = self.p
        x, y, yaw, forward, lateral, yaw_rate = observation[:6]

        def clip(value):
            return max(-0.36, min(0.36, value))

        if self.phase == "route":
            last = min(len(self.path), self.index + 25)
            self.index += int(
                np.argmin(np.sum((self.path[self.index : last] - [x, y]) ** 2, axis=1))
            )
            goal = self.path[min(self.index + 8, len(self.path) - 1)]
            angle = wrap(math.atan2(goal[1] - y, goal[0] - x) - yaw)
            steer = math.atan2(
                2 * 0.2965 * math.sin(angle),
                max(0.2, float(np.linalg.norm(goal - [x, y]))),
            )
            # Accelerate while still on the final portion of the U-bend.
            speed = (
                p["entry_speed"]
                if self.index > p["accelerate_index"]
                else p["route_speed"]
            )
            if self.index > len(self.path) - 12:
                self.phase = "entry"
            return [speed, clip(steer), 0.0]
        if self.phase == "entry":
            world_vx = forward * math.cos(yaw) - lateral * math.sin(yaw)
            predicted_x = x + p["trigger_preview_s"] * world_vx
            if predicted_x <= self.course["park_x"] + p["drift_lead_m"]:
                self.phase = "turn"
                self.heading = math.pi + wrap(yaw - math.pi)
                self.previous_yaw = yaw
            else:
                return [
                    p["entry_speed"],
                    clip(1.5 * wrap(math.pi - yaw) + 0.4 * (y - self.course["radius"])),
                    0.0,
                ]
        self.heading += wrap(yaw - self.previous_yaw)
        self.previous_yaw = yaw
        self.timer += DT
        target = 2 * math.pi + self.course["target_yaw"]
        if self.phase == "turn":
            predicted_heading = self.heading + p["yaw_preview_s"] * max(0.0, yaw_rate)
            if (
                predicted_heading >= target - p["counter_offset_rad"]
                or self.timer >= 3.0
            ):
                self.phase = "counter"
                self.timer = 0.0
            else:
                # Reduce the drive command at drift initiation, before the bay.
                slowing = self.heading >= target - p["brake_remaining_rad"]
                speed = p["brake_speed"] if slowing else p["turn_speed"]
                return [speed, p["turn_steer"], p["brake"]]
        # Brake the drive wheels; countersteer according to measured heading/rate.
        steer = (
            p["heading_gain"] * (target - self.heading) - p["yaw_rate_gain"] * yaw_rate
        )
        return [0.0, clip(steer), p["brake"]]
