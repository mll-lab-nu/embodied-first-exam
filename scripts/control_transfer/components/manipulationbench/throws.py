"""Seeded ballistic launches into the YAM working volume; evaluator-owned."""

import numpy as np

DIRECTIONS = ("front", "left", "right")


def sample_throw(seed):
    rng = np.random.default_rng(seed)
    direction = DIRECTIONS[seed % 3]
    angle = {"front": 0.0, "left": 65.0, "right": -65.0}[direction] + rng.uniform(-10, 10)
    a = np.deg2rad(angle)
    distance = rng.uniform(0.28, 0.40)
    flight = rng.uniform(0.40, 0.52)
    intercept = np.array([rng.uniform(0.39, 0.45), rng.uniform(-0.035, 0.035), 0.3926])
    vz = rng.uniform(0.7, 1.2)
    start = intercept + np.array([distance * np.cos(a), distance * np.sin(a), -vz * flight + 0.5 * 9.81 * flight**2])
    velocity = np.r_[(intercept[:2] - start[:2]) / flight, vz]
    release_step = int(rng.integers(80, 151))
    return {
        "version": "ballistic-v1",
        "direction": direction,
        "position": start.tolist(),
        "velocity": velocity.tolist(),
        "intercept": intercept.tolist(),
        "flight_time_s": float(flight),
        "release_step": release_step,
        "release_time_s": release_step * 0.01,
    }


HEIGHT_BANDS = {"low": (0.55, 0.70), "middle": (0.80, 1.00), "high": (1.10, 1.30)}


def sample_varied_throw(seed):
    """Full 3x3 launch matrix; intended crossing height is independently sampled."""
    rng = np.random.default_rng(seed)
    direction = DIRECTIONS[seed % 3]
    height_band = tuple(HEIGHT_BANDS)[seed // 3 % 3]
    angle = {"front": 0.0, "left": 65.0, "right": -65.0}[direction] + rng.uniform(-15, 15)
    a = np.deg2rad(angle)
    distance = rng.uniform(0.28, 0.40)
    flight = rng.uniform(0.40, 0.55)
    intercept = np.array([rng.uniform(0.39, 0.45), rng.uniform(-0.035, 0.035), rng.uniform(0.35, 0.48)])
    start = np.r_[intercept[:2] + distance * np.array([np.cos(a), np.sin(a)]), rng.uniform(*HEIGHT_BANDS[height_band])]
    velocity = (intercept - start) / flight
    velocity[2] += 0.5 * 9.81 * flight
    release_step = int(rng.integers(80, 151))
    return {
        "version": "direction-height-v1",
        "direction": direction,
        "height_band": height_band,
        "position": start.tolist(),
        "velocity": velocity.tolist(),
        "intercept": intercept.tolist(),
        "flight_time_s": float(flight),
        "release_step": release_step,
        "release_time_s": release_step * 0.01,
    }
