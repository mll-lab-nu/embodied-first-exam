"""Reference trajectories of the SSL robot's base (body.py Rig.set_base_target): acceleration-limited bang-bang
profiles, the SSL teams' standard (TIGERs plan "bang-bang trajectories", S1 / Sumatra BangBangTrajectory2D).

The reference only shapes the motion (arrive at a time, arrive moving): the limits themselves are enforced by
bodies/servo.py PlanarBase, which follows this reference every physics step (speed, acceleration and jerk on the
norm in the robot's frame). numpy only.
"""
from __future__ import annotations

import math

import numpy as np


class BangBang1D:
    """The time-optimal 1D profile from (s0, v0) to (s1, v1) with |v| <= V, |a| <= A: up to three segments
    (accelerate, cruise, accelerate), each (duration, acceleration)."""

    def __init__(self, s0, v0, s1, v1, V, A):
        self.s0, self.v0 = float(s0), float(v0)
        V, A = max(float(V), 1e-9), max(float(A), 1e-9)
        v0 = float(np.clip(v0, -V, V))
        v1 = float(np.clip(v1, -V, V))
        self.v0c = v0
        ds = float(s1) - float(s0)
        self.seg = self._plan(ds, v0, v1, V, A)
        self.T = sum(t for t, _ in self.seg)
        self.v1 = v1

    @staticmethod
    def _plan(ds, v0, v1, V, A):
        d_direct = (v0 + v1) / 2.0 * abs(v1 - v0) / A          # the distance of the direct velocity change
        sgn = 1.0 if ds >= d_direct else -1.0                   # first accelerate up (+) or down (-)
        ds_, v0_, v1_ = sgn * ds, sgn * v0, sgn * v1           # mirrored: first phase accelerates up
        r2 = A * ds_ + 0.5 * (v0_ * v0_ + v1_ * v1_)
        r = math.sqrt(max(0.0, r2))
        vp = -r if (-r >= max(v0_, v1_) - 1e-12) else r          # the lower peak when both are valid: shorter
        vp = max(vp, v0_, v1_)
        segs = []
        if vp > V:                                              # cruise at V
            t1 = (V - v0_) / A
            t3 = (V - v1_) / A
            d1 = (V * V - v0_ * v0_) / (2 * A)
            d3 = (V * V - v1_ * v1_) / (2 * A)
            tc = max(0.0, (ds_ - d1 - d3) / V)
            segs = [(t1, A), (tc, 0.0), (t3, -A)]
        else:
            segs = [((vp - v0_) / A, A), (0.0, 0.0), ((vp - v1_) / A, -A)]
        return [(max(0.0, t), sgn * a) for t, a in segs]

    def at(self, t):
        """(position, velocity) at time t >= 0 (after the end: moving on at the final velocity)"""
        s, v = self.s0, self.v0c
        rem = max(0.0, float(t))
        for dur, a in self.seg:
            h = min(rem, dur)
            s += v * h + 0.5 * a * h * h
            v += a * h
            rem -= h
            if rem <= 0.0:
                return s, v
        return s + v * rem, v


class Plan2D:
    """A 2D reference in the world frame: two 1D profiles whose limits split V and A by an angle alpha so that both
    axes arrive together (TIGERs' synchronisation); the norm of the reference's velocity and acceleration stays
    within V and A. With a requested duration (arrive at t), the speed limit is lowered until the profile takes that
    long (or as long as it can)."""

    def __init__(self, p0, v0, p1, v1, V, A, duration=None):
        p0, v0, p1, v1 = (np.asarray(x, float) for x in (p0, v0, p1, v1))
        self.p0, self.p1, self.v1 = p0, p1, v1
        self.fastest = self._sync(p0, v0, p1, v1, V, A)
        self.x, self.y = self.fastest
        T_min = max(self.x.T, self.y.T)
        self.T_min = T_min
        self.slowed = False
        if duration is not None and duration > T_min + 1e-3:
            vmin = float(np.linalg.norm(v1))                     # cannot cruise slower than the final speed
            lo, hi = max(vmin, 0.02 * V), V
            best = None
            for _ in range(30):
                mid = 0.5 * (lo + hi)
                x, y = self._sync(p0, v0, p1, v1, mid, A)
                T = max(x.T, y.T)
                if T > duration:
                    lo, best = mid, (x, y)
                else:
                    hi = mid
            x, y = self._sync(p0, v0, p1, v1, hi, A)
            if max(x.T, y.T) <= duration + 1e-3 or best is None:
                best = (x, y)
            self.x, self.y = best
            self.slowed = True
        self.T = max(self.x.T, self.y.T)

    @staticmethod
    def _sync(p0, v0, p1, v1, V, A):
        def make(al):
            c, s = math.cos(al), math.sin(al)
            return (BangBang1D(p0[0], v0[0], p1[0], v1[0], V * c, A * c),
                    BangBang1D(p0[1], v0[1], p1[1], v1[1], V * s, A * s))
        lo, hi = 1e-3, math.pi / 2 - 1e-3
        x, y = make(math.pi / 4)
        for _ in range(24):                                     # x gets less with a larger alpha: Tx up, Ty down
            mid = 0.5 * (lo + hi)
            x, y = make(mid)
            if x.T > y.T:
                hi = mid
            else:
                lo = mid
        return x, y

    def at(self, t):
        """(position (2,), velocity (2,)) in the world frame at time t after the plan's start"""
        sx, vx = self.x.at(t)
        sy, vy = self.y.at(t)
        if t > self.T:                                          # after arrival: move on at the final velocity
            dt = t - self.T
            return self.p1 + self.v1 * dt, self.v1.copy()
        return np.array([sx, sy]), np.array([vx, vy])
