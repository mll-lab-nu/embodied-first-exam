"""Capsule-chain helpers (pure numpy/scipy).

Copied 2026-10-12 from yamlab_port/tasks/knot_untying/overlay/yamlab/envs/tasks/knot_untying_lib/rope_geom.py
(knot_untying agent; joint-coordinate convention measured there: err 1.8e-7 m). Functions unchanged.
"""
from __future__ import annotations

import numpy as np

def chord_walk(curve: np.ndarray, d: float, n: int) -> np.ndarray:
    """n+1 points on the polyline `curve`, consecutive points exactly `d` apart (chord)."""
    pts = [curve[0]]
    seg = 0
    cur = curve[0]
    for _ in range(n):
        # find the first polyline point beyond distance d from cur, then intersect the sphere
        while True:
            if seg + 1 >= len(curve):
                # extrapolate along last direction
                v = curve[-1] - curve[-2]
                v /= np.linalg.norm(v)
                nxt = cur + d * v
                break
            a, b = (cur if np.linalg.norm(curve[seg] - cur) < 1e-12 else curve[seg]), curve[seg + 1]
            if np.linalg.norm(b - cur) >= d:
                # solve |a + t (b - a) - cur| = d for t in [0,1], largest root
                ab = b - a
                ac = a - cur
                A = ab @ ab
                B = 2 * ab @ ac
                C = ac @ ac - d * d
                disc = max(B * B - 4 * A * C, 0.0)
                t = (-B + np.sqrt(disc)) / (2 * A)
                nxt = a + np.clip(t, 0, 1) * ab
                break
            seg += 1
        pts.append(nxt)
        cur = nxt
        # make sure the next search starts at the segment holding `cur`
    return np.asarray(pts)


def link_frames(pts: np.ndarray):
    """Centres (n,3) and quaternions wxyz (n,4) with local +X along p_i -> p_{i+1}, minimal twist."""
    n = len(pts) - 1
    centres = 0.5 * (pts[:-1] + pts[1:])
    quats = np.zeros((n, 4))
    prev_R = None
    for i in range(n):
        x = pts[i + 1] - pts[i]
        x /= np.linalg.norm(x)
        if prev_R is None:
            up = np.array([0.0, 0.0, 1.0])
            y = np.cross(up, x)
            if np.linalg.norm(y) < 1e-6:
                y = np.array([0.0, 1.0, 0.0])
            y /= np.linalg.norm(y)
            z = np.cross(x, y)
            R = np.column_stack((x, y, z))
        else:
            # parallel transport of previous frame onto new tangent (no twist)
            x0 = prev_R[:, 0]
            R_rel = _rot_between(x0, x)
            R = R_rel @ prev_R
        prev_R = R
        quats[i] = mat_to_quat(R)
    return centres, quats


def _rot_between(a, b):
    a = a / np.linalg.norm(a)
    b = b / np.linalg.norm(b)
    v = np.cross(a, b)
    c = float(a @ b)
    if np.linalg.norm(v) < 1e-12:
        return np.eye(3)
    vx = np.array([[0, -v[2], v[1]], [v[2], 0, -v[0]], [-v[1], v[0], 0]])
    return np.eye(3) + vx + vx @ vx * (1.0 / (1.0 + c))


def mat_to_quat(R):
    tr = np.trace(R)
    if tr > 0:
        s = np.sqrt(tr + 1.0) * 2
        w = 0.25 * s
        x = (R[2, 1] - R[1, 2]) / s
        y = (R[0, 2] - R[2, 0]) / s
        z = (R[1, 0] - R[0, 1]) / s
    elif R[0, 0] > R[1, 1] and R[0, 0] > R[2, 2]:
        s = np.sqrt(1.0 + R[0, 0] - R[1, 1] - R[2, 2]) * 2
        w = (R[2, 1] - R[1, 2]) / s
        x = 0.25 * s
        y = (R[0, 1] + R[1, 0]) / s
        z = (R[0, 2] + R[2, 0]) / s
    elif R[1, 1] > R[2, 2]:
        s = np.sqrt(1.0 + R[1, 1] - R[0, 0] - R[2, 2]) * 2
        w = (R[0, 2] - R[2, 0]) / s
        x = (R[0, 1] + R[1, 0]) / s
        y = 0.25 * s
        z = (R[1, 2] + R[2, 1]) / s
    else:
        s = np.sqrt(1.0 + R[2, 2] - R[0, 0] - R[1, 1]) * 2
        w = (R[1, 0] - R[0, 1]) / s
        x = (R[0, 2] + R[2, 0]) / s
        y = (R[1, 2] + R[2, 1]) / s
        z = 0.25 * s
    q = np.array([w, x, y, z])
    return q / np.linalg.norm(q)


def quat_to_mat(q):
    q = np.asarray(q, float)
    w, x, y, z = q[..., 0], q[..., 1], q[..., 2], q[..., 3]
    R = np.empty(q.shape[:-1] + (3, 3))
    R[..., 0, 0] = 1 - 2 * (y * y + z * z)
    R[..., 0, 1] = 2 * (x * y - w * z)
    R[..., 0, 2] = 2 * (x * z + w * y)
    R[..., 1, 0] = 2 * (x * y + w * z)
    R[..., 1, 1] = 1 - 2 * (x * x + z * z)
    R[..., 1, 2] = 2 * (y * z - w * x)
    R[..., 2, 0] = 2 * (x * z - w * y)
    R[..., 2, 1] = 2 * (y * z + w * x)
    R[..., 2, 2] = 1 - 2 * (x * x + y * y)
    return R


def chain_points_from_links(pos, quat, d):
    """From link centres/quats (n,3)/(n,4): joint points estimated from both sides.

    Returns (joints (n+1,3) [averaged], gaps (n-1,) distance between the two estimates of
    each interior joint)."""
    R = quat_to_mat(quat)
    ax = R[:, :, 0]
    tail = pos - 0.5 * d * ax
    head = pos + 0.5 * d * ax
    gaps = np.linalg.norm(head[:-1] - tail[1:], axis=1)
    joints = np.vstack((tail[:1], 0.5 * (head[:-1] + tail[1:]), head[-1:]))
    return joints, gaps


def joint_positions_from_links(quats, joint_names):
    """PhysX spherical-joint coordinates (measured convention, probe_joints.py: err 1.8e-7 m):
    joint 'j_iii:k' = k-th (x,y,z) component of the rotation vector of conj(q_i) * q_{i+1}."""
    from scipy.spatial.transform import Rotation as Rot
    q = np.asarray(quats)[:, [1, 2, 3, 0]]
    out = np.zeros(len(joint_names))
    for k, name in enumerate(joint_names):
        base, ax = name.split(":")
        i = int(base[2:])
        out[k] = (Rot.from_quat(q[i]).inv() * Rot.from_quat(q[i + 1])).as_rotvec()[int(ax)]
    return out


def material_points(pos, quat, d):
    """Link end points and centres (the points whose speed the quiet check bounds)."""
    return np.vstack((chain_points_from_links(pos, quat, d)[0], pos))
