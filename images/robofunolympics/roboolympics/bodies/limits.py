"""Real-robot arm limits for RoboOlympics bodies (numpy only; shared by every sport with a robot arm).

A body's limits are data: `bodies/<body>/body.toml [limits.arm]` holds the manufacturer's numbers with their sources
(Franka Panda / FER and Franka Research 3: Franka "Control Interface Specification and Robot Limits"; KUKA LBR iiwa 14
R820: KUKA's data sheet). This module turns them into the three things a sport's controller needs, so that no arm can
do what the real robot cannot:

  plan_line(q0, q1, lim, T)    a time-optimal straight-line joint move, rest to rest, under the joint velocity,
                               acceleration and jerk limits (a 7-segment jerk-limited "S-curve" on the path
                               parameter, the slowest joint setting the pace); optionally stretched to T seconds
  JerkLimiter                  the robot's 1 kHz setpoint generator: it follows any joint reference (the 10 ms targets
                               of a sport's controller, a player's low-level trajectory) and guarantees that the
                               setpoint it sends to the servo never exceeds the velocity, acceleration and jerk limits
                               (what libfranka's rate limiter and a real motion generator do); a reference that is
                               itself within the limits is followed with a few milliseconds of lag
  TorqueRateLimiter            the servo's output stage: the commanded joint torque changes by at most dtau_max per
                               second and stays within tau_max (libfranka's kMaxTorqueRate and the motor torques)
  check_rows(...)              a low-level trajectory (rows of joint targets at a fixed step) against the velocity and
                               acceleration limits: None or the reason to refuse it
  stats(...)                   per-joint p50 / p95 / p99 / max of |velocity|, |acceleration|, |jerk|, |torque|,
                               |torque rate| against the limits (tools/arm_limits.py measures matches with it)

What it does not change: the physics of balls, contacts and the world; the sports' own base / rail / cart limits (a
sport states those); joint ranges (the MJCF's).

Body-agnostic by design: the wheeled humanoid of the unified body (bodies/wheeled_humanoid, `Rig.apply`) can put its
targets through a JerkLimiter and its servo output through a TorqueRateLimiter in the same way, with its own
body.toml [limits.arm] (accel_rad_s2, jerk_rad_s3, torque_rate_nm_s once a source for them exists).
"""

from __future__ import annotations

import math
import tomllib
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent


# ------------------------------------------------------------------------------------------------ the limits
@dataclass(frozen=True)
class ArmLimits:
    """One arm's joint limits (arrays of the arm's joints, in order) and where they come from."""

    body: str
    model: str
    range_lo: np.ndarray
    range_hi: np.ndarray
    vel: np.ndarray  # rad/s
    acc: np.ndarray | None  # rad/s^2   (None: the manufacturer publishes none)
    jerk: np.ndarray | None  # rad/s^3
    tau: np.ndarray  # N m
    dtau: np.ndarray | None  # N m/s
    sources: dict = field(default_factory=dict)
    cartesian: dict = field(default_factory=dict)

    @property
    def n(self) -> int:
        return len(self.vel)

    def scaled(self, k: float) -> "ArmLimits":
        """velocity, acceleration and jerk limits times k (a sport that declares a deviation; torques unchanged)"""
        f = lambda a, p: None if a is None else a * k**p
        return ArmLimits(
            self.body,
            self.model + f" (x{k:g})",
            self.range_lo,
            self.range_hi,
            self.vel * k,
            f(self.acc, 1),
            f(self.jerk, 1),
            self.tau,
            self.dtau,
            self.sources,
            self.cartesian,
        )

    def with_jerk(self, jerk) -> "ArmLimits":
        """the same limits with these jerk limits (e.g. jerk_caps(): what the torque rate allows at a pose)"""
        return ArmLimits(
            self.body,
            self.model,
            self.range_lo,
            self.range_hi,
            self.vel,
            self.acc,
            np.asarray(jerk, float),
            self.tau,
            self.dtau,
            self.sources,
            self.cartesian,
        )

    def table(self) -> dict:
        """the limits as plain lists (for /spec and the instructions)"""
        r = lambda a, nd=4: None if a is None else [round(float(x), nd) for x in a]
        return dict(
            body=self.body,
            model=self.model,
            range_rad=[r(self.range_lo), r(self.range_hi)],
            velocity_rad_s=r(self.vel),
            acceleration_rad_s2=r(self.acc),
            jerk_rad_s3=r(self.jerk, 1),
            torque_nm=r(self.tau, 2),
            torque_rate_nm_s=r(self.dtau, 1),
        )


def load(body: str, root: Path | str | None = None) -> ArmLimits:
    """The arm limits of bodies/<body>/body.toml (root: the directory holding bodies/<body>; default: this one)."""
    d = tomllib.loads((Path(root or HERE) / body / "body.toml").read_text())
    L = d["limits"]["arm"]
    arr = lambda k: None if L.get(k) is None else np.asarray(L[k], float)
    return ArmLimits(
        body=body,
        model=d["body"]["title"],
        range_lo=arr("range_lo_rad"),
        range_hi=arr("range_hi_rad"),
        vel=arr("speed_rad_s"),
        acc=arr("accel_rad_s2"),
        jerk=arr("jerk_rad_s3"),
        tau=arr("torque_nm"),
        dtau=arr("torque_rate_nm_s"),
        sources=dict(d.get("sources", {})),
        cartesian=dict(d.get("limits", {}).get("cartesian", {})),
    )


# ------------------------------------------------------------------------------------------------ S-curve
def _scurve_params(D, V, A, J):
    """rest-to-rest S-curve over distance D >= 0 under V, A, J: (Tj, Ta, Tv, vp, ap): jerk time, acceleration-phase
    time, cruise time, peak velocity, peak acceleration. Time-optimal (the 7-segment profile)."""
    if D <= 0.0:
        return 0.0, 0.0, 0.0, 0.0, 0.0
    vp = V
    Ta = 2.0 * math.sqrt(V / J) if V * J < A * A else V / A + A / J
    if D < vp * Ta:  # the peak velocity is not reached
        vp = (D * D * J / 4.0) ** (1.0 / 3.0)
        if vp <= A * A / J:
            Ta = 2.0 * math.sqrt(vp / J)
        else:
            vp = 0.5 * A * (-A / J + math.sqrt(A * A / (J * J) + 4.0 * D / A))
            Ta = vp / A + A / J
    Tj = min(Ta / 2.0, A / J)
    ap = J * Tj
    Tv = max(0.0, D / vp - Ta) if vp > 0 else 0.0
    return Tj, Ta, Tv, vp, ap


def _acc_phase(t, Tj, Ta, vp, ap, J):
    """(p, v, a) at time t in the acceleration phase [0, Ta]"""
    if t <= Tj:
        return J * t**3 / 6.0, 0.5 * J * t * t, J * t
    if t <= Ta - Tj:
        u = t - Tj
        return J * Tj**3 / 6.0 + 0.5 * J * Tj * Tj * u + 0.5 * ap * u * u, 0.5 * J * Tj * Tj + ap * u, ap
    tau = max(0.0, Ta - t)
    return vp * Ta / 2.0 - (vp * tau - J * tau**3 / 6.0), vp - 0.5 * J * tau * tau, J * tau


class Line:
    """A straight-line joint move q(t) = q0 + s(t) (q1 - q0), s an S-curve from 0 to 1 (rest to rest)."""

    def __init__(self, q0, q1, lim: ArmLimits, T: float = 0.0, margin: float = 1.0):
        self.q0, self.q1 = np.asarray(q0, float).copy(), np.asarray(q1, float).copy()
        dq = np.abs(self.q1 - self.q0)
        big = dq > 1e-12
        if not big.any():
            self.t_min = self.T = 0.0
            self.p = (0.0, 0.0, 0.0, 0.0, 0.0)
            self.V = self.A = self.J = 1.0
            self.k = 1.0
            return
        acc = lim.acc if lim.acc is not None else np.full(lim.n, np.inf)
        jerk = lim.jerk if lim.jerk is not None else np.full(lim.n, np.inf)
        self.V = float(np.min(lim.vel[big] / dq[big])) * margin
        self.A = float(np.min(acc[big] / dq[big])) * margin
        self.J = float(np.min(jerk[big] / dq[big])) * margin
        self.A = min(self.A, 1e9)
        self.J = min(self.J, 1e12)
        self.p = _scurve_params(1.0, self.V, self.A, self.J)
        Tj, Ta, Tv, vp, ap = self.p
        self.t_min = 2.0 * Ta + Tv
        self.T = max(float(T), self.t_min)
        self.k = self.t_min / self.T if self.T > 0 else 1.0  # time scaling of a stretched move

    def s(self, t):
        """(s, ds/dt, d2s/dt2) at time t >= 0"""
        if self.t_min <= 0.0:
            return 1.0, 0.0, 0.0
        u = min(max(t * self.k, 0.0), self.t_min)
        Tj, Ta, Tv, vp, ap = self.p
        if u <= Ta:
            p, v, a = _acc_phase(u, Tj, Ta, vp, ap, self.J)
        elif u <= Ta + Tv:
            p, v, a = vp * Ta / 2.0 + vp * (u - Ta), vp, 0.0
        else:
            p, v, a = _acc_phase(self.t_min - u, Tj, Ta, vp, ap, self.J)
            p, a = 1.0 - p, -a
        return p, v * self.k, a * self.k * self.k

    def at(self, t):
        """(q, qd, qdd) at time t"""
        s, sd, sdd = self.s(t)
        d = self.q1 - self.q0
        return self.q0 + s * d, sd * d, sdd * d

    def samples(self, dt):
        """q at t = dt, 2 dt, ..., n dt with n = ceil(T / dt) (the last sample is q1)"""
        n = max(1, int(math.ceil(self.T / dt - 1e-9)))
        return [self.at(i * dt)[0] if i < n else self.q1.copy() for i in range(1, n + 1)]


def plan_line(q0, q1, lim: ArmLimits, T: float = 0.0, margin: float = 1.0) -> Line:
    return Line(q0, q1, lim, T, margin)


def hermite(q0, v0, q1, v1, T, n):
    """a cubic Hermite segment from (q0, v0) to (q1, v1) over T seconds, sampled at T j / n, j = 1..n: (q, qd) arrays
    (n x joints). Turns rows of targets one control step apart into a smooth reference for the JerkLimiter."""
    q0, v0, q1, v1 = (np.asarray(x, float) for x in (q0, v0, q1, v1))
    s = (np.arange(1, n + 1) / n)[:, None]
    h00, h10, h01, h11 = 2 * s**3 - 3 * s**2 + 1, s**3 - 2 * s**2 + s, -2 * s**3 + 3 * s**2, s**3 - s**2
    d00, d10, d01, d11 = 6 * s**2 - 6 * s, 3 * s**2 - 4 * s + 1, -6 * s**2 + 6 * s, 3 * s**2 - 2 * s
    q = h00 * q0 + h10 * T * v0 + h01 * q1 + h11 * T * v1
    qd = (d00 * q0 + d01 * q1) / T + d10 * v0 + d11 * v1
    return q, qd


def jerk_caps(M, lim: ArmLimits, share: float = 0.7):
    """The joint jerks the torque-rate limit allows with the arm's joint-space inertia M (joints x joints, at a pose):
    the inertia part of the torque rate is M qddd, so joint i may use at most share x dtau_max_i / sum_j |M_ij| (every
    joint at its own cap keeps every torque rate within share of its limit; the rest is left to gravity, Coriolis and
    the servo's corrections). Never above the jerk limits. Without a torque-rate limit: the jerk limits."""
    if lim.dtau is None:
        return lim.jerk
    cap = share * lim.dtau / np.maximum(np.sum(np.abs(np.asarray(M, float)), axis=1), 1e-9)
    return cap if lim.jerk is None else np.minimum(lim.jerk, cap)


# ------------------------------------------------------------------------------------------------ setpoint limiter
def _sqrt_ctrl(err, k, d):
    """the sqrt controller: linear (gain k) near zero, sqrt(2 d |err|) beyond (braking at d), elementwise"""
    lin = d / (k * k)
    a = np.abs(err)
    out = np.where(a <= lin, k * err, np.sign(err) * np.sqrt(np.maximum(0.0, 2.0 * d * (a - 0.5 * lin))))
    return out


class JerkLimiter:
    """The robot's setpoint generator at the physics rate: per joint a third-order state (q, qd, qdd) that follows a
    reference (position r, velocity rd) and never exceeds |qd| <= vel, |qdd| <= acc, |dqdd/dt| <= jerk.

    A cascade of sqrt controllers (position -> velocity -> acceleration -> jerk) with the reference velocity as
    feed-forward; the jerk is clipped, so the acceleration and velocity bounds hold by construction (the velocity
    bound with a margin of one step of jerk). Deterministic (plain float64 numpy)."""

    KP, KV = 60.0, 300.0  # 1/s: position and velocity loop gains (the linear zone of the sqrt laws)
    BRAKE = 0.6  # position loop brakes at BRAKE x the acceleration limit (room for the jerk)

    def __init__(self, lim: ArmLimits, dt: float, q0=None):
        self.lim, self.dt = lim, float(dt)
        n = lim.n
        self.V = lim.vel - (lim.jerk if lim.jerk is not None else 0.0) * self.dt**2
        self.A = lim.acc if lim.acc is not None else np.full(n, 1e6)
        self.J = lim.jerk if lim.jerk is not None else np.full(n, 1e9)
        self.reset(np.zeros(n) if q0 is None else q0)

    def reset(self, q, qd=None, qdd=None):
        n = self.lim.n
        self.q = np.asarray(q, float).copy()
        self.qd = np.zeros(n) if qd is None else np.asarray(qd, float).copy()
        self.qdd = np.zeros(n) if qdd is None else np.asarray(qdd, float).copy()

    def step(self, r, rd=None, jerk_cap=None):
        """advance one step towards the reference r (velocity rd); jerk_cap: tighter jerk limits for this step (e.g.
        jerk_caps() at the current pose: a soft limit, which the velocity bound may override up to the jerk limit).
        Returns (q, qd, qdd) of the new setpoint"""
        dt, V, A, Jh = self.dt, self.V, self.A, self.J
        J = Jh if jerk_cap is None else np.minimum(Jh, jerk_cap)
        r = np.asarray(r, float)
        rd = np.zeros_like(r) if rd is None else np.asarray(rd, float)
        v_cmd = np.clip(rd + _sqrt_ctrl(r - self.q, self.KP, self.BRAKE * A), -V, V)
        a_cmd = np.clip(_sqrt_ctrl(v_cmd - self.qd, self.KV, J), -A, A)
        # never run past the velocity limit: the acceleration must be able to fall to zero (at the jerk limit)
        # before |qd| reaches V; planned with the soft jerk, enforced with the hard one if the soft one changed
        room_up, room_dn = np.maximum(0.0, V - self.qd), np.maximum(0.0, V + self.qd)
        a_cmd = np.clip(a_cmd, -np.sqrt(2.0 * J * room_dn), np.sqrt(2.0 * J * room_up))
        hard = (self.qdd > np.sqrt(2.0 * Jh * room_up)) | (self.qdd < -np.sqrt(2.0 * Jh * room_dn))
        a_cmd = np.where(hard, np.clip(a_cmd, -np.sqrt(2.0 * Jh * room_dn), np.sqrt(2.0 * Jh * room_up)), a_cmd)
        jl = np.where(hard, Jh, J)
        j = np.clip((a_cmd - self.qdd) / dt, -jl, jl)
        self.q = self.q + self.qd * dt + 0.5 * self.qdd * dt * dt + j * dt**3 / 6.0
        self.qd = self.qd + self.qdd * dt + 0.5 * j * dt * dt
        self.qdd = self.qdd + j * dt
        return self.q, self.qd, self.qdd


class TorqueRateLimiter:
    """The servo's output stage: |tau| <= tau_max and |tau - tau_prev| <= dtau_max * dt every step."""

    def __init__(self, lim: ArmLimits, dt: float, tau0=None):
        self.tau_max = lim.tau
        self.step_max = None if lim.dtau is None else lim.dtau * float(dt)
        self.reset(np.zeros(lim.n) if tau0 is None else tau0)

    def reset(self, tau):
        self.tau = np.clip(np.asarray(tau, float), -self.tau_max, self.tau_max)

    def __call__(self, tau_des):
        t = np.asarray(tau_des, float)
        if self.step_max is not None:
            t = np.clip(t, self.tau - self.step_max, self.tau + self.step_max)
        self.tau = np.clip(t, -self.tau_max, self.tau_max)
        return self.tau


# ------------------------------------------------------------------------------------------------ low-level rows
def check_rows(rows, dt, lim: ArmLimits, prev=None, prev_vel=None, tol=1.001):
    """Rows of joint targets (n x joints) one step dt apart, against the velocity and acceleration limits; prev, the
    targets in force before the first row (and prev_vel, their velocity), join the check if given. Returns None or the
    reason. Jerk is not checked at this step: the JerkLimiter smooths it at the physics rate."""
    a = np.asarray(rows, float)
    if prev is not None:
        a = np.vstack([np.asarray(prev, float)[None], a])
    if len(a) < 2:
        return None
    v = np.diff(a, axis=0) / dt
    if np.any(np.abs(v) > lim.vel * tol + 1e-9):
        i, j = np.argwhere(np.abs(v) > lim.vel * tol + 1e-9)[0]
        return f"joint {j + 1}: {abs(v[i, j]):.3f} rad/s between rows exceeds its speed limit {lim.vel[j]:.3f} rad/s"
    if lim.acc is None:
        return None
    if prev_vel is not None and prev is not None:
        v = np.vstack([np.asarray(prev_vel, float)[None], v])
    if len(v) < 2:
        return None
    acc = np.diff(v, axis=0) / dt
    bad = np.abs(acc) > lim.acc * tol + 1e-9
    if np.any(bad):
        i, j = np.argwhere(bad)[0]
        return (
            f"joint {j + 1}: {abs(acc[i, j]):.2f} rad/s^2 between rows exceeds its acceleration limit "
            f"{lim.acc[j]:.2f} rad/s^2"
        )
    return None


# ------------------------------------------------------------------------------------------------ measurement
QUANTITIES = (
    ("vel", "velocity", "rad/s"),
    ("acc", "acceleration", "rad/s^2"),
    ("jerk", "jerk", "rad/s^3"),
    ("tau", "torque", "N m"),
    ("dtau", "torque rate", "N m/s"),
)


def derivatives(q, dt, breaks=None):
    """velocity, acceleration and jerk of a sampled joint path q (steps x joints) by finite differences; `breaks`
    (step indices where the world was reset) cut the differences. Returns dict of arrays (NaN where undefined)."""
    q = np.asarray(q, float)
    v = np.full_like(q, np.nan)
    v[1:] = np.diff(q, axis=0) / dt
    for b in breaks or ():
        v[b] = np.nan
    a = np.full_like(q, np.nan)
    a[1:] = np.diff(v, axis=0) / dt
    j = np.full_like(q, np.nan)
    j[1:] = np.diff(a, axis=0) / dt
    return dict(vel=v, acc=a, jerk=j)


def stats(series: dict, lim: ArmLimits, joints=None) -> dict:
    """series: name -> (steps x joints) array (NaN = undefined) for vel, acc, jerk, tau, dtau (any subset).
    Returns per quantity: per joint p50, p95, p99, p99.9, max of |x|, the limit, p99 / limit, max / limit and the
    share of samples above the limit."""
    names = joints or [f"A{i + 1}" for i in range(lim.n)]
    out = {}
    for key, title, unit in QUANTITIES:
        x = series.get(key)
        if x is None:
            continue
        L = getattr(lim, key)
        rows = []
        for j in range(lim.n):
            col = np.abs(np.asarray(x, float)[:, j])
            col = col[np.isfinite(col)]
            if not len(col):
                rows.append(None)
                continue
            p = np.percentile(col, [50, 95, 99, 99.9])
            r = dict(
                joint=names[j],
                n=int(len(col)),
                p50=float(p[0]),
                p95=float(p[1]),
                p99=float(p[2]),
                p999=float(p[3]),
                max=float(col.max()),
            )
            if L is not None:
                lj = float(L[j])
                r.update(
                    limit=lj,
                    p99_ratio=float(p[2] / lj),
                    max_ratio=float(col.max() / lj),
                    over_share=float(np.mean(col > lj * 1.001)),
                )
            rows.append(r)
        out[key] = dict(title=title, unit=unit, joints=rows)
    return out
