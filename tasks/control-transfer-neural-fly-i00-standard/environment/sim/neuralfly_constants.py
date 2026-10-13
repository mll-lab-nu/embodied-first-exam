"""Public policy data only; safe for generators without simulation dependencies."""

DEFAULT = {
    "kp": 6.0,
    "kd": 4.0,
    "ki": 0.4,
    "attitude_gain": 80.0,
    "rate_gain": 16.0,
    "observer_gain": 0.0,
    "residual": [[0.0] * 7 for _ in range(3)],
}
BOUNDS = {
    "kp": (0.5, 20.0),
    "kd": (0.5, 12.0),
    "ki": (0.0, 5.0),
    "attitude_gain": (20.0, 180.0),
    "rate_gain": (5.0, 40.0),
    "observer_gain": (0.0, 15.0),
}
