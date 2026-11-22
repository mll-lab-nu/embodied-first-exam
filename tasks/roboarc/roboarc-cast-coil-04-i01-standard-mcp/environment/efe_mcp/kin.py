"""Kinematics in the adapter (owner decision D142): forward and inverse kinematics of one serial chain, for a part whose
robot takes joint commands only and whose service offers no inverse kinematics of its own, where the task's image ships
the robot's model. The manifest carries the chain as that model compiles it (`parts.<part>.kin`): each joint's axis and a
point on it with every joint of the chain at zero, and the tool frame there (product of exponentials, in the model's
root frame); the chain's measured joint values come from proprio. numpy only.

    kin = {"joints": [{"name", "type": "revolute" | "prismatic", "axis": [3], "point": [3], "solve": bool,
                       "limits": [lo, hi] | null}, ...],
           "tcp": {"position": [3], "quaternion_wxyz": [4]}, ...}

Joints without `solve` (a mobile base's, a torso lift's) take their measured values; inverse kinematics moves the
`solve` joints only: damped least squares on the tool point's geometric Jacobian from the seed, then from other starts
within the limits, the solution nearest the seed kept."""
from __future__ import annotations
import math
import numpy as np

import geom


def _skew(w):
    return np.array([[0.0, -w[2], w[1]], [w[2], 0.0, -w[0]], [-w[1], w[0], 0.0]])


def _exp(w, v, th):
    """exp([S] th) of the screw S = (w, v): a unit w (revolute) or w = 0 and a unit v (prismatic)."""
    T = np.eye(4)
    if not w.any():
        T[:3, 3] = v * th
        return T
    W = _skew(w)
    s, c = math.sin(th), math.cos(th)
    T[:3, :3] = np.eye(3) + s * W + (1 - c) * (W @ W)
    T[:3, 3] = (np.eye(3) * th + (1 - c) * W + (th - s) * (W @ W)) @ v
    return T


def _adj(T):
    R, p = T[:3, :3], T[:3, 3]
    A = np.zeros((6, 6))
    A[:3, :3] = R
    A[3:, 3:] = R
    A[3:, :3] = _skew(p) @ R
    return A


def _rotvec(R):
    """The rotation vector of R (axis times angle, |angle| <= pi)."""
    c = max(-1.0, min(1.0, (np.trace(R) - 1) / 2))
    th = math.acos(c)
    if th < 1e-9:
        return np.array([R[2, 1] - R[1, 2], R[0, 2] - R[2, 0], R[1, 0] - R[0, 1]]) / 2
    if th > math.pi - 1e-6:                        # near a half turn: the axis from R + I
        M = (R + np.eye(3)) / 2
        k = int(np.argmax(np.diag(M)))
        a = M[:, k] / math.sqrt(max(M[k, k], 1e-12))
        return a / np.linalg.norm(a) * th
    return np.array([R[2, 1] - R[1, 2], R[0, 2] - R[2, 0], R[1, 0] - R[0, 1]]) * (th / (2 * math.sin(th)))


class Chain:
    def __init__(self, kin: dict):
        J = kin["joints"]
        self.names = [j["name"] for j in J]
        self.n = len(J)
        self.w = np.zeros((self.n, 3))
        self.v = np.zeros((self.n, 3))
        self.revolute = np.array([j.get("type", "revolute") == "revolute" for j in J])
        for i, j in enumerate(J):
            a = np.asarray(j["axis"], dtype=np.float64)
            a = a / np.linalg.norm(a)
            if self.revolute[i]:
                self.w[i] = a
                self.v[i] = -np.cross(a, np.asarray(j["point"], dtype=np.float64))
            else:
                self.v[i] = a
        self.solve = np.array([bool(j.get("solve")) for j in J])
        self.idx = np.flatnonzero(self.solve)
        lim = [j.get("limits") or [-np.inf, np.inf] for j in J]
        self.lo = np.array([float(x[0]) for x in lim])
        self.hi = np.array([float(x[1]) for x in lim])
        t = kin["tcp"]
        self.M = np.eye(4)
        self.M[:3, :3] = geom.q_to_mat(geom.q_from(t["quaternion_wxyz"]))
        self.M[:3, 3] = np.asarray(t["position"], dtype=np.float64)

    def fk(self, q) -> np.ndarray:
        """The tool frame (4x4) in the chain's root frame for joint values q (every joint of the chain, in order)."""
        T = np.eye(4)
        for i in range(self.n):
            T = T @ _exp(self.w[i], self.v[i], float(q[i]))
        return T @ self.M

    def _jac(self, q):
        """The tool frame, and the geometric Jacobian of its point (rows: angular, then linear velocity) over the
        solved joints."""
        T = np.eye(4)
        Js = np.zeros((6, self.n))
        for i in range(self.n):
            Js[:, i] = _adj(T) @ np.concatenate([self.w[i], self.v[i]])
            T = T @ _exp(self.w[i], self.v[i], float(q[i]))
        T = T @ self.M
        p = T[:3, 3]
        Jw = Js[:3]
        Jv = Js[3:] - _skew(p) @ Jw
        return T, np.vstack([Jw, Jv])[:, self.idx]

    def _err(self, T, Tg, rot):
        ep = Tg[:3, 3] - T[:3, 3]
        er = _rotvec(Tg[:3, :3] @ T[:3, :3].T) if rot else np.zeros(3)
        return ep, er

    def _descend(self, q, Tg, rot, pos_tol, rot_tol, iters, rot_weight=0.2):
        q = q.copy()
        lam = 0.05
        best = None
        for _ in range(iters):
            T, J = self._jac(q)
            ep, er = self._err(T, Tg, rot)
            pe, re = float(np.linalg.norm(ep)), float(np.linalg.norm(er))
            if best is None or pe + rot_weight * re < best[1] + rot_weight * best[2]:
                best = (q.copy(), pe, re)
            if pe <= pos_tol and re <= rot_tol:
                break
            if rot:
                e = np.concatenate([rot_weight * er, ep])
                A = np.vstack([rot_weight * J[:3], J[3:]])
            else:
                e, A = ep, J[3:]
            dq = A.T @ np.linalg.solve(A @ A.T + lam ** 2 * np.eye(len(e)), e)
            m = float(np.max(np.abs(dq))) if len(dq) else 0.0
            if m > 0.4:
                dq *= 0.4 / m
            q[self.idx] = np.clip(q[self.idx] + dq, self.lo[self.idx], self.hi[self.idx])
        return best

    def nearest(self, q, seed):
        """Each solved revolute joint with a range over a full turn: the angle a whole number of turns from q nearest the
        seed, within the limits."""
        q = q.copy()
        for i in self.idx:
            if self.revolute[i] and self.hi[i] - self.lo[i] >= 2 * math.pi:
                k = round((seed[i] - q[i]) / (2 * math.pi))
                for kk in (k, k - 1, k + 1):
                    x = q[i] + kk * 2 * math.pi
                    if self.lo[i] - 1e-9 <= x <= self.hi[i] + 1e-9:
                        q[i] = x
                        break
        return q

    def ik(self, Tg, seed, pos_tol=2e-4, rot_tol=2e-3, rot=True, iters=150, starts=12, rng=0) -> dict:
        """Joint values (every joint of the chain; the unsolved ones as in the seed) that put the tool frame at Tg (in
        the chain's root frame): {"ok", "q", "pos_err_m", "rot_err_rad"}."""
        seed = np.asarray(seed, dtype=np.float64)
        q0 = seed.copy()
        q0[self.idx] = np.clip(q0[self.idx], self.lo[self.idx], self.hi[self.idx])
        cands = []
        best = self._descend(q0, Tg, rot, pos_tol, rot_tol, iters)
        cands.append(best)
        if not (best[1] <= pos_tol and best[2] <= rot_tol):
            g = np.random.default_rng(rng)
            lo = np.where(np.isfinite(self.lo), self.lo, -math.pi)[self.idx]
            hi = np.where(np.isfinite(self.hi), self.hi, math.pi)[self.idx]
            for _ in range(starts):
                qs = seed.copy()
                qs[self.idx] = lo + (hi - lo) * g.random(len(self.idx))
                c = self._descend(qs, Tg, rot, pos_tol, rot_tol, iters)
                cands.append(c)
        ok = [c for c in cands if c[1] <= pos_tol and c[2] <= rot_tol]
        if ok:
            q = min((self.nearest(c[0], seed) for c in ok), key=lambda x: float(np.sum((x - seed)[self.idx] ** 2)))
            T = self.fk(q)
            ep, er = self._err(T, Tg, rot)
            return {"ok": True, "q": q, "pos_err_m": float(np.linalg.norm(ep)), "rot_err_rad": float(np.linalg.norm(er))}
        c = min(cands, key=lambda c: c[1] + 0.2 * c[2])
        return {"ok": False, "q": self.nearest(c[0], seed), "pos_err_m": c[1], "rot_err_rad": c[2]}
