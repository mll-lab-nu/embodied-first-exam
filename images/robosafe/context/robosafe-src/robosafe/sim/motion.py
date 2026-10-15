"""Joint-space trajectories with velocity and acceleration limits, sampled at the control period.

Two builders, both returning joint positions and velocities per control tick:

- `joint_move`: straight line in joint space between two configurations, all joints sharing one trapezoidal profile;
- `path_move`: along a given sequence of joint configurations (e.g. the IK solutions of a straight tool path), slowed
  down until every joint respects its limits.
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field

import numpy as np

# Velocity feed-forward (s). The arm servos of the vendored UR5e are kp (q* - q) - kv qdot with kv / kp = 0.2 s on
# every joint, so the joint trails a moving target by 0.2 s times its speed. Sending q_d + LEAD * qdot_d as the
# target cancels that lag: the joint follows q_d. Each robot has its own ratio (`RobotSpec.lead`; the FR3's is 0.1 s);
# this is the UR5e's.
LEAD = 0.2


def lead_targets(pos: np.ndarray, vel: np.ndarray) -> np.ndarray:
    """Position targets that make the servos follow the sampled trajectory (pos, vel)."""
    return pos + LEAD * vel


@dataclass(frozen=True)
class Limits:
    vel: np.ndarray = field(default_factory=lambda: np.array([1.5, 1.5, 1.5, 2.0, 2.0, 2.0]))    # rad/s
    acc: np.ndarray = field(default_factory=lambda: np.array([4.0, 4.0, 4.0, 6.0, 6.0, 6.0]))    # rad/s^2

    def scaled(self, k: float) -> "Limits":
        k = min(max(float(k), 0.01), 1.0)
        return Limits(self.vel * k, self.acc * k * k)


def trapezoid(duration: float, ramp: float, t: float) -> tuple[float, float]:
    """Progress s in [0, 1] and its rate at time t for a profile with linear ramps of length `ramp` at both ends."""
    if duration <= 0.0:
        return 1.0, 0.0
    ramp = min(max(ramp, 1e-9), duration / 2.0)
    peak = 1.0 / (duration - ramp)
    t = min(max(t, 0.0), duration)
    if t < ramp:
        return 0.5 * peak * t * t / ramp, peak * t / ramp
    if t <= duration - ramp:
        return peak * (t - 0.5 * ramp), peak
    u = duration - t
    return 1.0 - 0.5 * peak * u * u / ramp, peak * u / ramp


def _profile_times(v_s: float, a_s: float) -> tuple[float, float]:
    """Duration and ramp time of the fastest trapezoid over a unit distance with rate limit v_s and acceleration a_s."""
    if v_s * v_s / a_s >= 1.0:              # never reaches the rate limit: triangular
        ramp = math.sqrt(1.0 / a_s)
        return 2.0 * ramp, ramp
    ramp = v_s / a_s
    return 1.0 / v_s + ramp, ramp


def joint_move(q0, q1, limits: Limits, dt: float) -> tuple[np.ndarray, np.ndarray]:
    """Positions and velocities at t = dt, 2 dt, ..., ending exactly at q1 with zero velocity."""
    q0, q1 = np.asarray(q0, dtype=np.float64), np.asarray(q1, dtype=np.float64)
    d = q1 - q0
    dist = np.abs(d)
    if float(np.max(dist)) < 1e-9:
        return q1[None, :].copy(), np.zeros((1, len(q1)))
    with np.errstate(divide="ignore"):
        v_s = float(np.min(np.where(dist > 0, limits.vel / dist, np.inf)))
        a_s = float(np.min(np.where(dist > 0, limits.acc / dist, np.inf)))
    duration, ramp = _profile_times(v_s, a_s)
    n = max(int(math.ceil(duration / dt - 1e-9)), 1)
    stretch = n * dt / duration              # land on a tick: slightly slower, never faster
    duration, ramp = duration * stretch, ramp * stretch
    pos = np.zeros((n, len(q0)))
    vel = np.zeros((n, len(q0)))
    for k in range(n):
        s, sd = trapezoid(duration, ramp, (k + 1) * dt)
        pos[k], vel[k] = q0 + d * s, d * sd
    pos[-1], vel[-1] = q1, 0.0
    return pos, vel


def path_move(q_path, limits: Limits, dt: float, duration: float, ramp_fraction: float = 0.25
              ) -> tuple[np.ndarray, np.ndarray]:
    """Follow `q_path` (rows equally spaced in path progress, first row = start) in at least `duration` seconds.

    The duration is stretched until the sampled joint velocities and accelerations respect the limits.
    """
    q_path = np.asarray(q_path, dtype=np.float64)
    m = q_path.shape[0] - 1
    if m < 1:
        return q_path[-1:].copy(), np.zeros((1, q_path.shape[1]))
    grid = np.linspace(0.0, 1.0, m + 1)
    duration = max(float(duration), 2 * dt)
    pos = vel = None
    for _ in range(8):
        n = max(int(math.ceil(duration / dt - 1e-9)), 2)
        total = n * dt
        ramp = total * ramp_fraction
        s = np.zeros(n + 1)
        for k in range(n + 1):
            s[k] = trapezoid(total, ramp, k * dt)[0]
        full = np.column_stack([np.interp(s, grid, q_path[:, j]) for j in range(q_path.shape[1])])
        v = np.diff(full, axis=0) / dt                       # mean velocity over each tick
        a = np.diff(np.vstack([np.zeros((1, v.shape[1])), v, np.zeros((1, v.shape[1]))]), axis=0) / dt
        pos = full[1:]
        vel = np.vstack([(v[1:] + v[:-1]) / 2.0, np.zeros((1, v.shape[1]))])
        over = max(float(np.max(np.abs(v) / limits.vel)), math.sqrt(float(np.max(np.abs(a) / limits.acc))))
        if over <= 1.0 + 1e-9:
            break
        duration = total * over * 1.02
    pos[-1] = q_path[-1]
    return pos, vel
