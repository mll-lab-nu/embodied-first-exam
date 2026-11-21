"""Pose math for the EFE Robot MCP server (numpy only). Quaternions are wxyz unless a name says otherwise."""
from __future__ import annotations
import math
import numpy as np


def q_from(q, order: str = "wxyz") -> np.ndarray:
    """A unit quaternion in wxyz from one in `order` ("wxyz" or "xyzw")."""
    q = np.asarray(q, dtype=np.float64).reshape(4)
    if order == "xyzw":
        q = q[[3, 0, 1, 2]]
    n = float(np.linalg.norm(q))
    if not math.isfinite(n) or n < 1e-9:
        raise ValueError("quaternion has zero length")
    return q / n


def q_to(q, order: str = "wxyz") -> np.ndarray:
    q = np.asarray(q, dtype=np.float64).reshape(4)
    return q[[1, 2, 3, 0]] if order == "xyzw" else q.copy()


def q_mul(a, b) -> np.ndarray:
    w1, x1, y1, z1 = a
    w2, x2, y2, z2 = b
    return np.array([w1 * w2 - x1 * x2 - y1 * y2 - z1 * z2,
                     w1 * x2 + x1 * w2 + y1 * z2 - z1 * y2,
                     w1 * y2 - x1 * z2 + y1 * w2 + z1 * x2,
                     w1 * z2 + x1 * y2 - y1 * x2 + z1 * w2])


def q_conj(q) -> np.ndarray:
    return np.array([q[0], -q[1], -q[2], -q[3]], dtype=np.float64)


def q_to_mat(q) -> np.ndarray:
    w, x, y, z = q
    return np.array([[1 - 2 * (y * y + z * z), 2 * (x * y - z * w), 2 * (x * z + y * w)],
                     [2 * (x * y + z * w), 1 - 2 * (x * x + z * z), 2 * (y * z - x * w)],
                     [2 * (x * z - y * w), 2 * (y * z + x * w), 1 - 2 * (x * x + y * y)]])


def mat_to_q(m) -> np.ndarray:
    m = np.asarray(m, dtype=np.float64)
    t = np.trace(m)
    if t > 0:
        s = math.sqrt(t + 1.0) * 2
        q = [0.25 * s, (m[2, 1] - m[1, 2]) / s, (m[0, 2] - m[2, 0]) / s, (m[1, 0] - m[0, 1]) / s]
    elif m[0, 0] > m[1, 1] and m[0, 0] > m[2, 2]:
        s = math.sqrt(1.0 + m[0, 0] - m[1, 1] - m[2, 2]) * 2
        q = [(m[2, 1] - m[1, 2]) / s, 0.25 * s, (m[0, 1] + m[1, 0]) / s, (m[0, 2] + m[2, 0]) / s]
    elif m[1, 1] > m[2, 2]:
        s = math.sqrt(1.0 + m[1, 1] - m[0, 0] - m[2, 2]) * 2
        q = [(m[0, 2] - m[2, 0]) / s, (m[0, 1] + m[1, 0]) / s, 0.25 * s, (m[1, 2] + m[2, 1]) / s]
    else:
        s = math.sqrt(1.0 + m[2, 2] - m[0, 0] - m[1, 1]) * 2
        q = [(m[1, 0] - m[0, 1]) / s, (m[0, 2] + m[2, 0]) / s, (m[1, 2] + m[2, 1]) / s, 0.25 * s]
    q = np.array(q)
    return q / np.linalg.norm(q)


def yaw_q(yaw: float) -> np.ndarray:
    return np.array([math.cos(yaw / 2), 0.0, 0.0, math.sin(yaw / 2)])


def q_yaw(q) -> float:
    w, x, y, z = q
    return math.atan2(2 * (w * z + x * y), 1 - 2 * (y * y + z * z))


def rpy_to_q(r, p, y) -> np.ndarray:
    cr, sr, cp, sp, cy, sy = (math.cos(r / 2), math.sin(r / 2), math.cos(p / 2), math.sin(p / 2),
                              math.cos(y / 2), math.sin(y / 2))
    return np.array([cr * cp * cy + sr * sp * sy, sr * cp * cy - cr * sp * sy,
                     cr * sp * cy + sr * cp * sy, cr * cp * sy - sr * sp * cy])


def q_to_rpy(q):
    w, x, y, z = q
    r = math.atan2(2 * (w * x + y * z), 1 - 2 * (x * x + y * y))
    p = math.asin(max(-1.0, min(1.0, 2 * (w * y - z * x))))
    yw = math.atan2(2 * (w * z + x * y), 1 - 2 * (y * y + z * z))
    return r, p, yw


def q_angle(a, b) -> float:
    """Rotation angle (rad, 0..pi) between two orientations."""
    d = abs(float(np.dot(a, b)))
    return 2 * math.acos(min(1.0, d))


def q_to_rotvec(q) -> np.ndarray:
    q = np.asarray(q, dtype=np.float64)
    if q[0] < 0:
        q = -q
    s = float(np.linalg.norm(q[1:]))
    if s < 1e-12:
        return np.zeros(3)
    ang = 2 * math.atan2(s, q[0])
    return q[1:] / s * ang


def rotvec_to_q(v) -> np.ndarray:
    v = np.asarray(v, dtype=np.float64)
    ang = float(np.linalg.norm(v))
    if ang < 1e-12:
        return np.array([1.0, 0, 0, 0])
    ax = v / ang
    return np.concatenate([[math.cos(ang / 2)], ax * math.sin(ang / 2)])


def slerp(a, b, t: float) -> np.ndarray:
    a = np.asarray(a, dtype=np.float64); b = np.asarray(b, dtype=np.float64)
    d = float(np.dot(a, b))
    if d < 0:
        b, d = -b, -d
    if d > 0.9995:
        q = a + t * (b - a)
        return q / np.linalg.norm(q)
    th = math.acos(d)
    return (math.sin((1 - t) * th) * a + math.sin(t * th) * b) / math.sin(th)


class Frame:
    """A rigid transform `parent <- child`: position p and wxyz quaternion q of the child frame in the parent frame."""

    def __init__(self, p=(0, 0, 0), q=(1, 0, 0, 0)):
        self.p = np.asarray(p, dtype=np.float64).reshape(3)
        self.q = q_from(q)
        self.R = q_to_mat(self.q)

    def to_parent(self, p, q=None):
        """Pose given in this (child) frame -> the parent frame."""
        pp = self.p + self.R @ np.asarray(p, dtype=np.float64)
        return pp, (None if q is None else q_mul(self.q, q))

    def from_parent(self, p, q=None):
        """Pose given in the parent frame -> this (child) frame."""
        pc = self.R.T @ (np.asarray(p, dtype=np.float64) - self.p)
        return pc, (None if q is None else q_mul(q_conj(self.q), q))

    def vec_from_parent(self, v):
        return self.R.T @ np.asarray(v, dtype=np.float64)

    def vec_to_parent(self, v):
        return self.R @ np.asarray(v, dtype=np.float64)


def canon_q(q) -> np.ndarray:
    """q and -q are one rotation: the representative with w >= 0."""
    q = np.asarray(q, dtype=np.float64)
    return -q if q[0] < 0 else q
