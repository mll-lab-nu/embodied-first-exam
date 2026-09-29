"""Sampling uses simulation time, never rendering speed or agent wall time."""
from __future__ import annotations

import math


def positive(value, name):
    value = float(value)
    if not math.isfinite(value) or value <= 0:
        raise ValueError(f"{name} must be finite and positive")
    return value


class SimulationTimeline:
    def __init__(self, fps, start_time):
        self.fps = positive(fps, "fps")
        self.start = float(start_time)
        if not math.isfinite(self.start):
            raise ValueError("Invalid simulation start time")
        self.index = 0
        self.previous = None

    def advance(self, sim_time):
        sim_time = float(sim_time)
        if not math.isfinite(sim_time) or sim_time < self.start or (
                self.previous is not None and sim_time <= self.previous):
            raise ValueError("Simulation time must strictly increase; reset starts a new recording")
        result = []
        # Multiplication from the integer frame index avoids cumulative drift.
        while self.start + self.index / self.fps <= sim_time + 1e-10:
            result.append((self.index, self.index / self.fps))
            self.index += 1
        self.previous = sim_time
        return result

