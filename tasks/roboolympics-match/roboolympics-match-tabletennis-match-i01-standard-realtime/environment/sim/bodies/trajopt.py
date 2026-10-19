"""Fixed-time, jerk-limited joint trajectories through soft waypoints (numpy only; shared by the arm sports).

A striking arm (table tennis, tennis, badminton) must be at a given joint position with a given joint velocity at a
given time (the contact), starting from whatever state it is in now, without exceeding the real robot's velocity,
acceleration and jerk limits (bodies/limits.py). The velocity-limited cubic swings the sports used ask for 3-12x the
Panda's acceleration; a JerkLimiter servo then follows them late. This module plans motions the servo can follow:

  plan(q0, v0, a0, n, dt, lim, waypoints, ...)   one joint trajectory per joint, n steps of dt, piecewise-constant
        jerk, from the current state (q0, v0, a0); every waypoint is soft (position, velocity and / or acceleration
        wanted at step k, each with its own tolerance); the limits are hard boxes (velocity, acceleration, jerk at
        `margin` of the limits, the joint range): the motion is the smoothest (least squared jerk) that meets the
        waypoints within the limits, and when the waypoints cannot all be met it is the best reachable compromise
        (the residuals say by how much). A convex QP per joint (the joints are independent; synchronisation comes
        from the shared waypoint times), solved by ADMM with a cached factorisation: no solver dependency.
  ramp_time(v, lim, margin)                      the shortest time to bring a joint from rest to velocity v (or v
        to rest) under the acceleration and jerk limits: how long a stroke from a wind-up pose at rest must last
  stroke(q0, v0, a0, n, dt, lim, q1, v1, ...)    the striking motion built on plan(): an anticipation move from the
        current state to a wind-up pose (free, chosen by the optimiser) where the arm is at rest, then the stroke
        that starts as late as possible (the slowest joint's ramp time before the contact) and reaches (q1, v1) at
        step n, optionally through a pre-contact pose, then a follow-through that brings the arm to rest; with too
        little time for the full scheme it plans directly to the contact (best reachable state)

Units: rad, rad/s, rad/s^2, rad/s^3, seconds. Joint arrays are (joints,), trajectories (steps, joints); step k of a
trajectory is the state at time k * dt after now (k = 1..N; row k - 1 of the returned arrays).
"""

from __future__ import annotations

import math
from dataclasses import dataclass

import numpy as np

try:  # inside a task: bodies/ is a package next to the sport; in a checkout the same
    from . import limits as AL
except ImportError:  # pragma: no cover - loaded as a plain module
    import limits as AL  # type: ignore

_CACHE: dict = {}


@dataclass
class Waypoint:
    """What the motion should do at step k (1-based): position q, velocity v, acceleration a (None: free), each with a
    tolerance (the error at which its cost equals one unit of squared normalised jerk over the whole motion)."""

    k: int
    q: np.ndarray | None = None
    v: np.ndarray | None = None
    a: np.ndarray | None = None
    tol_q: float = 2e-4
    tol_v: float = 2e-3
    tol_a: float = 2e-2


def _maps(N: int, dt: float):
    """Linear maps from the jerk sequence x (N) to acceleration, velocity, position at steps 1..N (zero initial
    state), piecewise-constant jerk: a+ = a + x dt, v+ = v + a dt + x dt^2/2, q+ = q + v dt + a dt^2/2 + x dt^3/6."""
    key = ("maps", N, dt)
    if key not in _CACHE:
        Ma = np.zeros((N, N)); Mv = np.zeros((N, N)); Mq = np.zeros((N, N))
        for i in range(N):  # unit jerk in step i
            a = v = q = 0.0
            for k in range(N):
                x = 1.0 if k == i else 0.0
                q = q + v * dt + a * dt * dt / 2 + x * dt**3 / 6
                v = v + a * dt + x * dt * dt / 2
                a = a + x * dt
                Ma[k, i], Mv[k, i], Mq[k, i] = a, v, q
        _CACHE[key] = (Ma, Mv, Mq)
    return _CACHE[key]


def _free(N: int, dt: float, q0, v0, a0):
    """position, velocity, acceleration at steps 1..N with zero jerk from (q0, v0, a0): (N, joints) each"""
    t = (np.arange(1, N + 1) * dt)[:, None]
    return q0 + v0 * t + a0 * t * t / 2, v0 + a0 * t, np.broadcast_to(a0, (N, len(q0))).copy()


def plan(q0, v0, a0, n, dt, lim: AL.ArmLimits, waypoints, lo=None, hi=None, margin=0.95, iters=400, rho=0.4):
    """The least-squared-jerk trajectory of n steps from (q0, v0, a0) through the soft waypoints, within the hard
    limits (margin x velocity, acceleration, jerk; the range lo..hi, default the limits' range). Returns dict(q, v, a,
    j: (n, joints) arrays; res: per waypoint the worst |error| of q, v, a; viol: the worst box violation / limit)."""
    q0, v0, a0 = (np.asarray(x, float).copy() for x in (q0, v0, a0))
    nj, N = len(q0), int(n)
    V = lim.vel * margin
    A = (lim.acc if lim.acc is not None else np.full(nj, 1e3)) * margin
    J = (lim.jerk if lim.jerk is not None else np.full(nj, 1e5)) * margin
    lo = np.asarray(lim.range_lo if lo is None else lo, float)
    hi = np.asarray(lim.range_hi if hi is None else hi, float)
    v0 = np.clip(v0, -V, V); a0 = np.clip(a0, -A, A)
    Ma, Mv, Mq = _maps(N, dt)
    fq, fv, fa = _free(N, dt, q0, v0, a0)
    I = np.eye(N)
    mid, half = (lo + hi) / 2, np.maximum((hi - lo) / 2, 1e-9)
    xs = []
    for j in range(nj):  # per joint: variable y = x / J (normalised jerk)
        s = J[j]
        C = np.vstack([I, Ma * (s / A[j]), Mv * (s / V[j]), Mq * (s / half[j])])
        off = np.r_[np.zeros(N), fa[:, j] / A[j], fv[:, j] / V[j], (fq[:, j] - mid[j]) / half[j]]
        P = np.eye(N) * (1.0 / N)
        ql = np.zeros(N)
        for w in waypoints:
            k = int(w.k) - 1
            if not 0 <= k < N:
                continue
            for want, M, f, tol in ((w.q, Mq, fq, w.tol_q), (w.v, Mv, fv, w.tol_v), (w.a, Ma, fa, w.tol_a)):
                if want is None:
                    continue
                r = M[k] * s / tol
                tgt = (np.asarray(want, float)[j] - f[k, j]) / tol
                P = P + np.outer(r, r)
                ql = ql - tgt * r
        sigma = 1e-6
        CtC = C.T @ C
        r_ = rho
        Kinv = np.linalg.inv(P + sigma * np.eye(N) + r_ * CtC)
        y = np.zeros(N); z = np.clip(C @ y + off, -1, 1) - off; lam = np.zeros(len(z))
        # ADMM (OSQP's scheme) on min 1/2 y'Py + ql'y  s.t.  -1 <= Cy + off <= 1, z = Cy; over-relaxation alpha,
        # rho adapted every 25 iterations from the primal / dual residual balance
        alpha = 1.6
        for it in range(iters):
            y = Kinv @ (sigma * y - ql + C.T @ (r_ * z - lam))
            Cy = C @ y
            Cr = alpha * Cy + (1 - alpha) * z
            z_prev = z
            z = np.clip(Cr + lam / r_ + off, -1, 1) - off
            lam = lam + r_ * (Cr - z)
            if it % 25 == 24:
                rp = np.max(np.abs(Cy - z)) / max(np.max(np.abs(Cy)), np.max(np.abs(z)), 1e-9)
                rd = np.max(np.abs(r_ * C.T @ (z - z_prev))) / max(np.max(np.abs(P @ y)), np.max(np.abs(C.T @ lam)),
                                                                     np.max(np.abs(ql)), 1e-9)
                if rp < 1e-5 and rd < 1e-5:
                    break
                f = math.sqrt(max(rp, 1e-12) / max(rd, 1e-12))
                if f > 5 or f < 0.2:
                    r_ = float(np.clip(r_ * f, 1e-4, 1e6))
                    Kinv = np.linalg.inv(P + sigma * np.eye(N) + r_ * CtC)
        xs.append(y * s)
    X = np.array(xs).T                                        # (N, joints) jerk
    a = fa + Ma @ X; v = fv + Mv @ X; q = fq + Mq @ X
    res = []
    for w in waypoints:
        k = int(w.k) - 1
        if not 0 <= k < N:
            continue
        e = {}
        for name, want, arr in (("q", w.q, q), ("v", w.v, v), ("a", w.a, a)):
            if want is not None:
                e[name] = float(np.max(np.abs(arr[k] - np.asarray(want, float))))
        res.append({"k": w.k, **e})
    viol = max(float(np.max(np.abs(X) / (J / margin))), float(np.max(np.abs(a) / (A / margin))),
               float(np.max(np.abs(v) / (V / margin))))
    return dict(q=q, v=v, a=a, j=X, res=res, viol=viol)


def ramp_time(v, lim: AL.ArmLimits, margin=0.95):
    """Per joint: the shortest time from rest to velocity v (constant-jerk ramps up and down of the acceleration,
    with a constant-acceleration middle when |v| >= A^2/J)."""
    v = np.abs(np.asarray(v, float))
    A = lim.acc * margin
    J = lim.jerk * margin
    tri = 2.0 * np.sqrt(v / J)
    trap = v / A + A / J
    return np.where(v >= A * A / J, trap, tri)


def stroke(q0, v0, a0, n, dt, lim: AL.ArmLimits, q1, v1, n_follow=30, via=None, via_steps=12, lo=None, hi=None,
           margin=0.95, ramp_pad=1.3, iters=400, tol_q=2e-4, tol_v=2e-2, via_tol=2e-3):
    """The striking motion (see the module text): rows for steps 1..n + n_follow. Returns plan()'s dict plus
    n_stroke (the stroke's steps from the wind-up rest; 0 = direct), scale (the share of v1 delivered: the contact
    velocity projected on v1, over |v1|^2), contact_err_q (rad). The contact position has
    priority over its velocity (tolerances tol_q, tol_v); with a wind-up that cannot be reached in time the direct
    plan is used when it meets the contact better."""
    q1 = np.asarray(q1, float); v1 = np.asarray(v1, float)
    n = int(n)
    n_str = int(math.ceil(float(np.max(ramp_time(v1, lim, margin))) * ramp_pad / dt)) + 2
    base = [Waypoint(n, q=q1, v=v1, tol_q=tol_q, tol_v=tol_v)]
    if via is not None and n > via_steps + 2:
        base.append(Waypoint(n - via_steps, q=np.asarray(via, float), tol_q=via_tol))
        n_str = max(n_str, via_steps + 6)
    if n_follow > 0:
        base.append(Waypoint(n + n_follow, v=np.zeros_like(v1), a=np.zeros_like(v1), tol_v=1e-2, tol_a=0.2))

    def run(windup):
        wps = list(base)
        if windup:
            wps.append(Waypoint(n - n_str, v=np.zeros_like(v1), a=np.zeros_like(v1), tol_v=2e-2, tol_a=0.3))
        out = plan(q0, v0, a0, n + n_follow, dt, lim, wps, lo=lo, hi=hi, margin=margin, iters=iters)
        vc = out["v"][n - 1]
        vv = float(v1 @ v1)
        scale = float(vc @ v1 / vv) if vv > 1e-12 else 1.0      # the delivered velocity along v1, as a share
        out.update(n_stroke=n_str if windup else 0, scale=scale,
                   contact_err_q=float(np.max(np.abs(out["q"][n - 1] - q1))))
        return out
    out = run(True) if n - n_str >= 6 else None
    if out is None or out["contact_err_q"] > 1e-3 or out["scale"] < 0.97:
        alt = run(False)
        if out is None or (alt["contact_err_q"], -alt["scale"]) < (out["contact_err_q"], -out["scale"]):
            out = alt
    return out
