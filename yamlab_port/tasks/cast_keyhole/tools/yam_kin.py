"""Numpy forward/inverse kinematics of one YAM arm, read from the unchanged YAMLab USD
(yamlab/robot/yam/arm/yam.usd, joint local frames dumped with pxr on 2026-10-12).

PhysX joint convention: T_body1 = T_body0 * L0 * R_axis(q) * L1^-1, axis = joint-frame X.
Frames: arm base = the arm prim (world pose = ROBOT arm position, identity rotation).
"""
from __future__ import annotations

import numpy as np
from scipy.spatial.transform import Rotation

# (p0, q0_wxyz, p1, q1_wxyz, lower_deg, upper_deg) for joint1..6; the arm root is at the arm prim origin.
_J = [
    ((0, 0, 0.0631), (0.5, 0.5, -0.5, 0.5), (0, 0, 0), (0.70710678, 0, -0.70710678, 0), -150.0, 175.0),
    ((0.000025, -0.020, 0.0409), (0.70710678, 0.70710678, 0, 0), (0, 0, 0), (0.70710678, 0, -0.70710678, 0), 0.0, 210.0),
    ((0.264, 0, 0), (0, 0.70710678, 0, -0.70710678), (0, 0, 0), (0.70710678, 0, -0.70710678, 0), 0.0, 210.0),
    ((-0.245, -0.060, 0.0), (0.70710678, 0, -0.70710678, 0), (0, 0, 0), (0.70710678, 0, -0.70710678, 0), -90.0, 90.0),
    ((-0.074, -0.0395, 0.000025), (0.70710678, 0, 0, 0.70710678), (0, 0, 0), (0.70710678, 0, -0.70710678, 0), -90.0, 90.0),
    ((0.0, 0.0353, 0.0395), (0.5, -0.5, -0.5, 0.5), (0, 0, 0), (0.70710678, 0, -0.70710678, 0), -120.0, 120.0),
]
LOWER = np.radians([j[4] for j in _J])
UPPER = np.radians([j[5] for j in _J])

# Fingers (prismatic along joint-frame X), in link_6.
_F = {
    "left_finger": ((-0.04506, 0.024, 0.05456), (0, 0, 0, -1.0), (0, 0, 0), (0.70710707, 0, -0.70710707, 0)),
    "right_finger": ((0.04506, -0.024, 0.05456), (0.70710695, -0.70710695, 0, 0), (0, 0, 0), (0.70710695, 0, -0.70710695, 0)),
}
# finger pad keypoints in the finger link frame (configs/robot/yam.yaml): tip, base1, base2
PADS = {"left_finger": np.array([[-0.088, 0.025, -0.045], [-0.02, 0.058, -0.048], [-0.02, -0.008, -0.048]]),
        "right_finger": np.array([[-0.025, -0.088, -0.045], [-0.058, -0.02, -0.048], [0.008, -0.02, -0.048]])}


def _T(p, q_wxyz):
    T = np.eye(4)
    w, x, y, z = q_wxyz
    T[:3, :3] = Rotation.from_quat([x, y, z, w]).as_matrix()
    T[:3, 3] = p
    return T


def _Rx(q):
    c, s = np.cos(q), np.sin(q)
    return np.array([[1, 0, 0, 0], [0, c, -s, 0], [0, s, c, 0], [0, 0, 0, 1.]])


def _Tx(d):
    T = np.eye(4); T[0, 3] = d
    return T


_L0 = [_T(j[0], j[1]) for j in _J]
_L1i = [np.linalg.inv(_T(j[2], j[3])) for j in _J]
_F0 = {k: _T(v[0], v[1]) for k, v in _F.items()}
_F1i = {k: np.linalg.inv(_T(v[2], v[3])) for k, v in _F.items()}


def fk_all(q):
    """List of 4x4 link transforms [link_1..link_6] in the arm base frame."""
    T = np.eye(4)
    out = []
    for i in range(6):
        T = T @ _L0[i] @ _Rx(q[i]) @ _L1i[i]
        out.append(T)
    return out


def finger_T(T6, name, d):
    return T6 @ _F0[name] @ _Tx(d) @ _F1i[name]


def pad_points(T6, d):
    """Pad keypoints of both fingers (base frame) at finger joint d (both fingers mirror)."""
    return {n: (finger_T(T6, n, d) @ np.c_[PADS[n], np.ones(3)].T).T[:, :3] for n in PADS}


def _tcp_in_link6():
    """TCP = midpoint of the two pad centres (independent of the opening by symmetry); axes:
    x_tcp = approach (finger base -> tip), y_tcp = jaw axis (right pad -> left pad), z = x cross y."""
    T6 = np.eye(4)
    c = {}
    tip = {}
    for d in (-0.0475, 0.0):
        P = pad_points(T6, d)
        for n, pts in P.items():
            c[(n, d)] = 0.5 * (pts[0] + 0.5 * (pts[1] + pts[2]))
            tip[(n, d)] = pts[0] - 0.5 * (pts[1] + pts[2])
    mid = 0.5 * (c[("left_finger", 0.0)] + c[("right_finger", 0.0)])
    approach = tip[("left_finger", 0.0)] + tip[("right_finger", 0.0)]
    approach /= np.linalg.norm(approach)
    jaw = c[("left_finger", -0.0475)] - c[("right_finger", -0.0475)]
    jaw -= approach * (jaw @ approach)
    jaw /= np.linalg.norm(jaw)
    T = np.eye(4)
    T[:3, :3] = np.c_[approach, jaw, np.cross(approach, jaw)]
    T[:3, 3] = mid
    return T


T6_TCP = _tcp_in_link6()


def fk_tcp(q):
    return fk_all(q)[-1] @ T6_TCP


def fk_jac(q):
    """TCP pose and 6x6 analytic geometric Jacobian (linear; angular) in the base frame."""
    T = np.eye(4)
    axes, origins = [], []
    for i in range(6):
        Tj = T @ _L0[i]                  # joint frame (axis = its x) before the joint motion
        axes.append(Tj[:3, 0]); origins.append(Tj[:3, 3])
        T = Tj @ _Rx(q[i]) @ _L1i[i]
    Tt = T @ T6_TCP
    J = np.zeros((6, 6))
    for i in range(6):
        J[:3, i] = np.cross(axes[i], Tt[:3, 3] - origins[i])
        J[3:, i] = axes[i]
    return Tt, J


def jacobian(q):
    return fk_jac(q)[1]


def pose_error(T, Tt):
    e = np.zeros(6)
    e[:3] = Tt[:3, 3] - T[:3, 3]
    e[3:] = Rotation.from_matrix(Tt[:3, :3] @ T[:3, :3].T).as_rotvec()
    return e


def ik(Tt, q0, iters=200, tol_p=1e-5, tol_r=1e-4, damping=1e-3, margin=0.02, weights=None):
    """Damped least squares IK of the TCP to Tt (base frame). Returns (q, ok, err_p, err_r)."""
    q = np.clip(np.array(q0, float), LOWER + margin, UPPER - margin)
    W = np.ones(6) if weights is None else np.asarray(weights)
    for _ in range(iters):
        T, J = fk_jac(q)
        e = pose_error(T, Tt)
        if np.linalg.norm(e[:3]) < tol_p and np.linalg.norm(e[3:]) < tol_r:
            break
        J = J * W[:, None]
        ew = e * W
        dq = J.T @ np.linalg.solve(J @ J.T + damping * np.eye(6), ew)
        n = np.linalg.norm(dq)
        if n > 0.2:
            dq *= 0.2 / n
        q = np.clip(q + dq, LOWER + margin, UPPER - margin)
    T = fk_tcp(q)
    e = pose_error(T, Tt)
    return q, bool(np.linalg.norm(e[:3]) < 1e-4 and np.linalg.norm(e[3:]) < 1e-3), float(np.linalg.norm(e[:3])), float(np.linalg.norm(e[3:]))


BASES = {"left": np.array([0.2525, 0.305, 0.76]), "right": np.array([0.2525, -0.305, 0.76])}


def world_to_base(T_world, side):
    T = np.array(T_world, float).copy()
    T[:3, 3] -= BASES[side]
    return T


def base_to_world(T_base, side):
    T = np.array(T_base, float).copy()
    T[:3, 3] += BASES[side]
    return T
