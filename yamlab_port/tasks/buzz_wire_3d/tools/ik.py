"""Damped-least-squares IK for one YAM arm on the numpy model (tools/yam_kin.py)."""
import numpy as np
from scipy.spatial.transform import Rotation
from yam_kin import YamArm

ARM_BASES = {"left": (0.2525, 0.305, 0.76), "right": (0.2525, -0.305, 0.76)}


def pose_error(T, p, R):
    dp = p - T[:3, 3]
    dR = Rotation.from_matrix(R @ T[:3, :3].T).as_rotvec()
    return np.r_[dp, dR]


class IK:
    def __init__(self, side):
        self.side = side
        self.arm = YamArm(base_pos=ARM_BASES[side])
        self.lo = self.arm.lo + 1e-3
        self.hi = self.arm.hi - 1e-3

    def tcp(self, q, off):
        """off: 4x4 TCP frame in link6."""
        return self.arm.link6(q) @ off

    def solve(self, p, R, off, q0, iters=300, tol=1e-6, lam=0.02, w_rot=1.0, step=0.5):
        q = np.clip(np.array(q0, float), self.lo, self.hi)
        W = np.diag([1, 1, 1, w_rot, w_rot, w_rot])
        for it in range(iters):
            T = self.tcp(q, off)
            e = pose_error(T, p, R)
            if np.linalg.norm(e[:3]) < tol and np.linalg.norm(e[3:]) < 10 * tol:
                return q, True, e
            J = self.arm.jacobian_space(q, T[:3, 3])
            Jw = W @ J
            dq = Jw.T @ np.linalg.solve(Jw @ Jw.T + lam ** 2 * np.eye(6), W @ e)
            n = np.linalg.norm(dq)
            if n > step:
                dq *= step / n
            q = np.clip(q + dq, self.lo, self.hi)
        T = self.tcp(q, off)
        e = pose_error(T, p, R)
        return q, bool(np.linalg.norm(e[:3]) < 1e-4 and np.linalg.norm(e[3:]) < 1e-3), e

    def solve_multi(self, p, R, off, seeds=None, n_random=40, rng=None, prefer=None, **kw):
        rng = rng or np.random.default_rng(0)
        cands = list(seeds or [])
        cands += [rng.uniform(self.lo, self.hi) for _ in range(n_random)]
        sols = []
        for q0 in cands:
            q, ok, e = self.solve(p, R, off, q0, **kw)
            if ok:
                sols.append(q)
        if not sols:
            return None, []
        if prefer is not None:
            sols.sort(key=lambda q: np.linalg.norm(q - prefer))
        return sols[0], sols


def frame(R=np.eye(3), p=(0, 0, 0)):
    T = np.eye(4)
    T[:3, :3] = R
    T[:3, 3] = p
    return T


# ----------------------------------------------------------------------------- batched IK (fast)
def _batch_rot(axis, th):
    """Rodrigues for one unit axis and a batch of angles -> (B,3,3)."""
    K = np.array([[0, -axis[2], axis[1]], [axis[2], 0, -axis[0]], [-axis[1], axis[0], 0]])
    s, c = np.sin(th)[:, None, None], np.cos(th)[:, None, None]
    return np.eye(3)[None] + s * K[None] + (1 - c) * (K @ K)[None]


class BatchIK:
    """Damped-least-squares IK over a batch of seeds (numpy, vectorised). Target: link_6 @ off."""

    def __init__(self, side):
        self.side = side
        self.arm = YamArm(base_pos=ARM_BASES[side])
        self.lo = self.arm.lo + 1e-3
        self.hi = self.arm.hi - 1e-3
        B = self.arm.base
        self.w = []
        self.p = []
        for j in self.arm.joints[:6]:
            a = np.array(j["axis"]) / np.linalg.norm(j["axis"])
            self.w.append(B[:3, :3] @ a)
            self.p.append(B[:3, :3] @ np.array(j["point"]) + B[:3, 3])
        self.M = B @ self.arm.T0["link_6"]

    def fk(self, Q, off=None):
        """Q (B,6) -> link6@off (B,4,4), plus per-joint world axes/points (B,6,3) for the Jacobian."""
        n = len(Q)
        G = np.tile(np.eye(4), (n, 1, 1))
        W = np.zeros((n, 6, 3))
        P = np.zeros((n, 6, 3))
        for i in range(6):
            W[:, i] = G[:, :3, :3] @ self.w[i]
            P[:, i] = (G[:, :3, :3] @ self.p[i]) + G[:, :3, 3]
            R = _batch_rot(self.w[i], Q[:, i])
            T = np.tile(np.eye(4), (n, 1, 1))
            T[:, :3, :3] = R
            T[:, :3, 3] = self.p[i] - R @ self.p[i]
            G = G @ T
        T = G @ self.M
        if off is not None:
            T = T @ off
        return T, W, P

    def solve(self, p, R, off, Q0, iters=150, lam=0.02, step=0.5, tol_p=1e-4, tol_r=1e-3):
        Q = np.clip(np.array(Q0, float), self.lo, self.hi)
        Rt = np.asarray(R)
        for it in range(iters):
            T, W, P = self.fk(Q, off)
            ep = p[None] - T[:, :3, 3]
            Rerr = Rt[None] @ np.transpose(T[:, :3, :3], (0, 2, 1))
            er = Rotation.from_matrix(Rerr).as_rotvec()
            e = np.concatenate([ep, er], axis=1)
            J = np.zeros((len(Q), 6, 6))
            J[:, :3, :] = np.transpose(np.cross(W, T[:, None, :3, 3] - P), (0, 2, 1))
            J[:, 3:, :] = np.transpose(W, (0, 2, 1))
            A = J @ np.transpose(J, (0, 2, 1)) + lam ** 2 * np.eye(6)[None]
            dq = np.einsum("bji,bj->bi", J, np.linalg.solve(A, e[..., None])[..., 0])
            nrm = np.linalg.norm(dq, axis=1, keepdims=True)
            dq = np.where(nrm > step, dq * step / np.maximum(nrm, 1e-12), dq)
            Q = np.clip(Q + dq, self.lo, self.hi)
        T, _, _ = self.fk(Q, off)
        ep = np.linalg.norm(p[None] - T[:, :3, 3], axis=1)
        er = np.linalg.norm(Rotation.from_matrix(Rt[None] @ np.transpose(T[:, :3, :3], (0, 2, 1))).as_rotvec(), axis=1)
        ok = (ep < tol_p) & (er < tol_r)
        return Q, ok, ep, er

    def solve_multi(self, p, R, off=None, n_random=64, rng=None, seeds=None):
        rng = rng or np.random.default_rng(0)
        Q0 = rng.uniform(self.lo, self.hi, size=(n_random, 6))
        if seeds is not None and len(seeds):
            Q0 = np.r_[np.atleast_2d(seeds), Q0]
        Q, ok, ep, er = self.solve(np.asarray(p, float), R, off if off is not None else np.eye(4), Q0)
        sols = Q[ok]
        # de-duplicate
        uniq = []
        for q in sols:
            if not any(np.abs(q - u).max() < 1e-2 for u in uniq):
                uniq.append(q)
        return uniq
