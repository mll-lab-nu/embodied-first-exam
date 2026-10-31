"""Quaternion and rigid-transform helpers (numpy, float64).

One convention everywhere: quaternions are ``wxyz`` unit quaternions, rotations are
right-handed, poses are ``[x y z qw qx qy qz]`` (:data:`tactilelab_tasks.core.types.Pose7`).
Euler angles are extrinsic XYZ in degrees (``R = Rz(c) @ Ry(b) @ Rx(a)``), the
convention of the scene configuration files.
"""

from __future__ import annotations

import numpy as np

_EPS = 1e-12


# ----------------------------------------------------------------------------- quaternions
def quat_normalize(q: np.ndarray) -> np.ndarray:
    """Return ``q / |q|`` (works on ``(..., 4)``)."""
    q = np.asarray(q, dtype=np.float64)
    n = np.linalg.norm(q, axis=-1, keepdims=True)
    return q / np.maximum(n, _EPS)


def quat_conjugate(q: np.ndarray) -> np.ndarray:
    """``(w, -x, -y, -z)``."""
    q = np.asarray(q, dtype=np.float64)
    return q * np.array([1.0, -1.0, -1.0, -1.0])


def quat_inverse(q: np.ndarray) -> np.ndarray:
    """Inverse of a unit quaternion (= conjugate after normalisation)."""
    return quat_conjugate(quat_normalize(q))


def quat_mul(a: np.ndarray, b: np.ndarray) -> np.ndarray:
    """Hamilton product ``a * b`` (apply ``b`` first, then ``a``). Broadcasts over ``(..., 4)``."""
    a = np.asarray(a, dtype=np.float64)
    b = np.asarray(b, dtype=np.float64)
    aw, ax, ay, az = a[..., 0], a[..., 1], a[..., 2], a[..., 3]
    bw, bx, by, bz = b[..., 0], b[..., 1], b[..., 2], b[..., 3]
    return np.stack(
        [
            aw * bw - ax * bx - ay * by - az * bz,
            aw * bx + ax * bw + ay * bz - az * by,
            aw * by - ax * bz + ay * bw + az * bx,
            aw * bz + ax * by - ay * bx + az * bw,
        ],
        axis=-1,
    )


def quat_rotate(q: np.ndarray, v: np.ndarray) -> np.ndarray:
    """Rotate vector(s) ``v`` ``(..., 3)`` by quaternion(s) ``q`` ``(..., 4)``."""
    q = quat_normalize(q)
    v = np.asarray(v, dtype=np.float64)
    w = q[..., :1]
    u = q[..., 1:]
    t = 2.0 * np.cross(u, v)
    return v + w * t + np.cross(u, t)


def quat_rotate_inverse(q: np.ndarray, v: np.ndarray) -> np.ndarray:
    """Rotate ``v`` by the inverse of ``q``."""
    return quat_rotate(quat_conjugate(q), v)


def quat_to_matrix(q: np.ndarray) -> np.ndarray:
    """Rotation matrix ``(..., 3, 3)`` of a unit quaternion."""
    q = quat_normalize(q)
    w, x, y, z = q[..., 0], q[..., 1], q[..., 2], q[..., 3]
    m = np.empty(q.shape[:-1] + (3, 3), dtype=np.float64)
    m[..., 0, 0] = 1 - 2 * (y * y + z * z)
    m[..., 0, 1] = 2 * (x * y - z * w)
    m[..., 0, 2] = 2 * (x * z + y * w)
    m[..., 1, 0] = 2 * (x * y + z * w)
    m[..., 1, 1] = 1 - 2 * (x * x + z * z)
    m[..., 1, 2] = 2 * (y * z - x * w)
    m[..., 2, 0] = 2 * (x * z - y * w)
    m[..., 2, 1] = 2 * (y * z + x * w)
    m[..., 2, 2] = 1 - 2 * (x * x + y * y)
    return m


def matrix_to_quat(m: np.ndarray) -> np.ndarray:
    """Unit quaternion ``wxyz`` of a rotation matrix ``(3, 3)`` (Shepperd's method, w >= 0)."""
    m = np.asarray(m, dtype=np.float64)
    if m.shape != (3, 3):
        raise ValueError(f"expected a (3, 3) matrix, got {m.shape}")
    tr = np.trace(m)
    if tr > 0.0:
        s = np.sqrt(tr + 1.0) * 2.0
        q = np.array([0.25 * s, (m[2, 1] - m[1, 2]) / s, (m[0, 2] - m[2, 0]) / s, (m[1, 0] - m[0, 1]) / s])
    elif m[0, 0] > m[1, 1] and m[0, 0] > m[2, 2]:
        s = np.sqrt(1.0 + m[0, 0] - m[1, 1] - m[2, 2]) * 2.0
        q = np.array([(m[2, 1] - m[1, 2]) / s, 0.25 * s, (m[0, 1] + m[1, 0]) / s, (m[0, 2] + m[2, 0]) / s])
    elif m[1, 1] > m[2, 2]:
        s = np.sqrt(1.0 + m[1, 1] - m[0, 0] - m[2, 2]) * 2.0
        q = np.array([(m[0, 2] - m[2, 0]) / s, (m[0, 1] + m[1, 0]) / s, 0.25 * s, (m[1, 2] + m[2, 1]) / s])
    else:
        s = np.sqrt(1.0 + m[2, 2] - m[0, 0] - m[1, 1]) * 2.0
        q = np.array([(m[1, 0] - m[0, 1]) / s, (m[0, 2] + m[2, 0]) / s, (m[1, 2] + m[2, 1]) / s, 0.25 * s])
    q = quat_normalize(q)
    return -q if q[0] < 0.0 else q


def quat_from_axis_angle(axis: np.ndarray, angle: float) -> np.ndarray:
    """Quaternion of a rotation of ``angle`` radians about ``axis``."""
    axis = np.asarray(axis, dtype=np.float64)
    n = np.linalg.norm(axis)
    if n < _EPS:
        return np.array([1.0, 0.0, 0.0, 0.0])
    axis = axis / n
    h = 0.5 * angle
    return np.concatenate([[np.cos(h)], np.sin(h) * axis])


def quat_from_euler_xyz_deg(euler_deg) -> np.ndarray:
    """Quaternion of extrinsic XYZ Euler angles in degrees: ``R = Rz(c) Ry(b) Rx(a)``."""
    a, b, c = np.deg2rad(np.asarray(euler_deg, dtype=np.float64).reshape(3))
    qx = quat_from_axis_angle([1.0, 0.0, 0.0], a)
    qy = quat_from_axis_angle([0.0, 1.0, 0.0], b)
    qz = quat_from_axis_angle([0.0, 0.0, 1.0], c)
    return quat_normalize(quat_mul(qz, quat_mul(qy, qx)))


def quat_to_euler_xyz_deg(q: np.ndarray) -> np.ndarray:
    """Extrinsic XYZ Euler angles in degrees (``roll, pitch, yaw``) of a unit quaternion."""
    m = quat_to_matrix(np.asarray(q, dtype=np.float64).reshape(4))
    sy = -m[2, 0]
    sy = float(np.clip(sy, -1.0, 1.0))
    pitch = np.arcsin(sy)
    if abs(sy) < 1.0 - 1e-9:
        roll = np.arctan2(m[2, 1], m[2, 2])
        yaw = np.arctan2(m[1, 0], m[0, 0])
    else:  # gimbal lock: put everything into roll
        roll = np.arctan2(-m[1, 2], m[1, 1])
        yaw = 0.0
    return np.rad2deg(np.array([roll, pitch, yaw]))


def quat_angle(q: np.ndarray) -> float:
    """Rotation angle (radians, in ``[0, pi]``) of a unit quaternion."""
    q = quat_normalize(np.asarray(q, dtype=np.float64).reshape(4))
    return float(2.0 * np.arccos(np.clip(abs(q[0]), 0.0, 1.0)))


def quat_diff_angle(a: np.ndarray, b: np.ndarray) -> float:
    """Geodesic angle (radians) between two orientations."""
    return quat_angle(quat_mul(quat_inverse(a), b))


def quat_sign_align(q: np.ndarray, ref: np.ndarray) -> np.ndarray:
    """Flip ``q`` into the hemisphere of ``ref`` (``q`` and ``-q`` are the same rotation)."""
    q = np.asarray(q, dtype=np.float64)
    ref = np.asarray(ref, dtype=np.float64)
    dot = np.sum(q * ref, axis=-1, keepdims=True)
    return np.where(dot < 0.0, -q, q)


def quat_distance(a: np.ndarray, b: np.ndarray) -> float:
    """``min(|a - b|, |a + b|)``: the chordal distance used by the MoveL done check."""
    a = np.asarray(a, dtype=np.float64)
    b = np.asarray(b, dtype=np.float64)
    return float(min(np.linalg.norm(a - b), np.linalg.norm(a + b)))


def quat_nlerp(a: np.ndarray, b: np.ndarray, t: float) -> np.ndarray:
    """Normalised linear interpolation (short path)."""
    a = np.asarray(a, dtype=np.float64)
    b = quat_sign_align(np.asarray(b, dtype=np.float64), a)
    return quat_normalize((1.0 - t) * a + t * b)


def quat_slerp(a: np.ndarray, b: np.ndarray, t: float) -> np.ndarray:
    """Spherical linear interpolation (short path); falls back to nlerp when nearly parallel."""
    a = quat_normalize(np.asarray(a, dtype=np.float64))
    b = quat_sign_align(quat_normalize(np.asarray(b, dtype=np.float64)), a)
    cos_th = float(np.clip(np.dot(a, b), -1.0, 1.0))
    if cos_th > 1.0 - 1e-8:
        return quat_nlerp(a, b, t)
    th = np.arccos(cos_th)
    s = np.sin(th)
    return (np.sin((1.0 - t) * th) / s) * a + (np.sin(t * th) / s) * b


# ----------------------------------------------------------------------------- poses
def pose_compose(a: np.ndarray, b: np.ndarray) -> np.ndarray:
    """``T_a * T_b``: apply ``b`` in ``a``'s frame (``a`` = parent-to-world, ``b`` = child-in-parent)."""
    a = np.asarray(a, dtype=np.float64)
    b = np.asarray(b, dtype=np.float64)
    pos = a[..., :3] + quat_rotate(a[..., 3:7], b[..., :3])
    quat = quat_normalize(quat_mul(a[..., 3:7], b[..., 3:7]))
    return np.concatenate([pos, quat], axis=-1)


def pose_inverse(p: np.ndarray) -> np.ndarray:
    """Inverse rigid transform."""
    p = np.asarray(p, dtype=np.float64)
    qi = quat_inverse(p[..., 3:7])
    return np.concatenate([-quat_rotate(qi, p[..., :3]), qi], axis=-1)


def pose_transform_point(p: np.ndarray, point: np.ndarray) -> np.ndarray:
    """Map point(s) from the pose's frame to the parent frame."""
    p = np.asarray(p, dtype=np.float64)
    return p[..., :3] + quat_rotate(p[..., 3:7], np.asarray(point, dtype=np.float64))


def pose_relative(a: np.ndarray, b: np.ndarray) -> np.ndarray:
    """``b`` expressed in ``a``'s frame: ``inv(a) * b``."""
    return pose_compose(pose_inverse(a), b)


def pose_to_matrix(p: np.ndarray) -> np.ndarray:
    """Homogeneous ``(4, 4)`` matrix."""
    p = np.asarray(p, dtype=np.float64).reshape(7)
    m = np.eye(4)
    m[:3, :3] = quat_to_matrix(p[3:7])
    m[:3, 3] = p[:3]
    return m


def pose_from_matrix(m: np.ndarray) -> np.ndarray:
    """Pose vector of a homogeneous ``(4, 4)`` matrix."""
    m = np.asarray(m, dtype=np.float64)
    return np.concatenate([m[:3, 3], matrix_to_quat(m[:3, :3])])


def pose_from_pos_quat(pos, quat) -> np.ndarray:
    """Concatenate position and ``wxyz`` quaternion into a pose."""
    return np.concatenate(
        [np.asarray(pos, dtype=np.float64).reshape(3), quat_normalize(np.asarray(quat, dtype=np.float64).reshape(4))]
    )


def pose_from_pos_euler_deg(pos, euler_deg) -> np.ndarray:
    """Pose from position and extrinsic XYZ Euler angles (degrees), the scene-config convention."""
    return pose_from_pos_quat(pos, quat_from_euler_xyz_deg(euler_deg))


def pose_interp(a: np.ndarray, b: np.ndarray, t: float, slerp: bool = True) -> np.ndarray:
    """Interpolate position linearly and orientation by slerp (or nlerp)."""
    a = np.asarray(a, dtype=np.float64)
    b = np.asarray(b, dtype=np.float64)
    pos = (1.0 - t) * a[:3] + t * b[:3]
    quat = quat_slerp(a[3:7], b[3:7], t) if slerp else quat_nlerp(a[3:7], b[3:7], t)
    return np.concatenate([pos, quat])


def pose_error(a: np.ndarray, b: np.ndarray) -> tuple[float, float]:
    """``(translation [m], rotation [rad])`` between two poses."""
    a = np.asarray(a, dtype=np.float64)
    b = np.asarray(b, dtype=np.float64)
    return float(np.linalg.norm(a[:3] - b[:3])), quat_diff_angle(a[3:7], b[3:7])


def is_nan_pose(p: np.ndarray) -> bool:
    """True if any of the 7 numbers is NaN (the *hold* marker)."""
    return bool(np.isnan(np.asarray(p, dtype=np.float64)).any())
