"""Rotations and rigid transforms. Quaternions are (w, x, y, z), as in MuJoCo; a pose is (position, quaternion)."""
from __future__ import annotations

import math

import numpy as np

Pose = tuple[np.ndarray, np.ndarray]


def unit(v) -> np.ndarray:
    v = np.asarray(v, dtype=np.float64)
    n = float(np.linalg.norm(v))
    if n == 0.0:
        raise ValueError("zero vector has no direction")
    return v / n


def quat_mul(a, b) -> np.ndarray:
    aw, ax, ay, az = a
    bw, bx, by, bz = b
    return np.array([aw * bw - ax * bx - ay * by - az * bz,
                     aw * bx + ax * bw + ay * bz - az * by,
                     aw * by - ax * bz + ay * bw + az * bx,
                     aw * bz + ax * by - ay * bx + az * bw])


def quat_conj(q) -> np.ndarray:
    return np.array([q[0], -q[1], -q[2], -q[3]], dtype=np.float64)


def quat_axis_angle(axis, angle: float) -> np.ndarray:
    a = unit(axis)
    s = math.sin(angle / 2.0)
    return np.array([math.cos(angle / 2.0), a[0] * s, a[1] * s, a[2] * s])


def quat_yaw(yaw: float) -> np.ndarray:
    return np.array([math.cos(yaw / 2.0), 0.0, 0.0, math.sin(yaw / 2.0)])


def quat_to_mat(q) -> np.ndarray:
    w, x, y, z = unit(q)
    return np.array([[1 - 2 * (y * y + z * z), 2 * (x * y - w * z), 2 * (x * z + w * y)],
                     [2 * (x * y + w * z), 1 - 2 * (x * x + z * z), 2 * (y * z - w * x)],
                     [2 * (x * z - w * y), 2 * (y * z + w * x), 1 - 2 * (x * x + y * y)]])


def mat_to_quat(m) -> np.ndarray:
    m = np.asarray(m, dtype=np.float64).reshape(3, 3)
    tr = m[0, 0] + m[1, 1] + m[2, 2]
    if tr > 0.0:
        s = math.sqrt(tr + 1.0) * 2.0
        q = np.array([0.25 * s, (m[2, 1] - m[1, 2]) / s, (m[0, 2] - m[2, 0]) / s, (m[1, 0] - m[0, 1]) / s])
    elif m[0, 0] > m[1, 1] and m[0, 0] > m[2, 2]:
        s = math.sqrt(1.0 + m[0, 0] - m[1, 1] - m[2, 2]) * 2.0
        q = np.array([(m[2, 1] - m[1, 2]) / s, 0.25 * s, (m[0, 1] + m[1, 0]) / s, (m[0, 2] + m[2, 0]) / s])
    elif m[1, 1] > m[2, 2]:
        s = math.sqrt(1.0 + m[1, 1] - m[0, 0] - m[2, 2]) * 2.0
        q = np.array([(m[0, 2] - m[2, 0]) / s, (m[0, 1] + m[1, 0]) / s, 0.25 * s, (m[1, 2] + m[2, 1]) / s])
    else:
        s = math.sqrt(1.0 + m[2, 2] - m[0, 0] - m[1, 1]) * 2.0
        q = np.array([(m[1, 0] - m[0, 1]) / s, (m[0, 2] + m[2, 0]) / s, (m[1, 2] + m[2, 1]) / s, 0.25 * s])
    return unit(q)


def quat_from_axes(x=None, y=None, z=None) -> np.ndarray:
    """Quaternion of the frame with the given axes (any two; the third is their cross product)."""
    if x is None:
        y, z = unit(y), unit(z)
        x = np.cross(y, z)
    elif y is None:
        z, x = unit(z), unit(x)
        y = np.cross(z, x)
    else:
        x, y = unit(x), unit(y)
        z = np.cross(x, y)
    return mat_to_quat(np.column_stack([x, y, z]))


def rotate(q, v) -> np.ndarray:
    return quat_to_mat(q) @ np.asarray(v, dtype=np.float64)


def rotvec(q_from, q_to) -> np.ndarray:
    """The rotation vector (axis * angle, world frame) that takes orientation q_from to q_to by the short way."""
    d = quat_mul(q_to, quat_conj(q_from))
    if d[0] < 0.0:
        d = -d
    s = float(np.linalg.norm(d[1:]))
    if s < 1e-12:
        return 2.0 * d[1:]
    return d[1:] / s * (2.0 * math.atan2(s, d[0]))


def slerp(q0, q1, s: float) -> np.ndarray:
    rv = rotvec(q0, q1)
    ang = float(np.linalg.norm(rv))
    if ang < 1e-12:
        return unit(q0)
    return unit(quat_mul(quat_axis_angle(rv / ang, ang * s), q0))


def compose(a: Pose, b: Pose) -> Pose:
    """a * b: the pose b, given in frame a, expressed in a's parent frame."""
    return (np.asarray(a[0], dtype=np.float64) + rotate(a[1], b[0]), unit(quat_mul(a[1], b[1])))


def inverse(a: Pose) -> Pose:
    qi = quat_conj(unit(a[1]))
    return (-rotate(qi, a[0]), qi)


def as_pose(p) -> Pose:
    """Accept (pos, quat) or {"pos": ..., "quat": ...} (quat optional: identity) or {"pos", "yaw_deg"}."""
    if isinstance(p, dict):
        pos = np.asarray(p["pos"], dtype=np.float64)
        if "quat" in p:
            quat = unit(p["quat"])
        else:
            quat = quat_yaw(math.radians(float(p.get("yaw_deg", 0.0))))
        return (pos, quat)
    pos, quat = p
    return (np.asarray(pos, dtype=np.float64), unit(quat))


def tilt_deg(q) -> float:
    """Angle between the frame's z axis and the world's z axis."""
    return math.degrees(math.acos(max(-1.0, min(1.0, float(quat_to_mat(q)[2, 2])))))


# ---- the hand's orientation as three angles (the pose interface) ------------------------------------------------------
# With all three angles zero the hand points straight down and its fingers close along the bench y axis; the
# orientation is Rz(yaw) Ry(pitch) Rx(roll) applied to that. Angles in degrees.
_HAND_DOWN = np.array([0.0, 0.0, 1.0, 0.0])        # half a turn about y: tool z = -bench z, tool y = bench y


def quat_from_ypr(yaw_deg: float, pitch_deg: float = 0.0, roll_deg: float = 0.0) -> np.ndarray:
    q = quat_mul(quat_axis_angle([0.0, 0.0, 1.0], math.radians(yaw_deg)),
                 quat_mul(quat_axis_angle([0.0, 1.0, 0.0], math.radians(pitch_deg)),
                          quat_axis_angle([1.0, 0.0, 0.0], math.radians(roll_deg))))
    return unit(quat_mul(q, _HAND_DOWN))


def ypr_from_quat(q) -> tuple[float, float, float]:
    """The inverse of `quat_from_ypr` (pitch within 90 degrees either way)."""
    m = quat_to_mat(quat_mul(unit(q), quat_conj(_HAND_DOWN)))
    pitch = math.asin(max(-1.0, min(1.0, -float(m[2, 0]))))
    if abs(float(m[2, 0])) < 1.0 - 1e-9:
        yaw, roll = math.atan2(float(m[1, 0]), float(m[0, 0])), math.atan2(float(m[2, 1]), float(m[2, 2]))
    else:                                           # pointing along the bench x axis: yaw and roll are one angle
        yaw, roll = math.atan2(-float(m[0, 1]), float(m[1, 1])), 0.0
    return math.degrees(yaw), math.degrees(pitch), math.degrees(roll)


def detail_camera_frame(eye, source_rotation, point):
    """One MuJoCo free-camera frame shared by detail RGB and evidence rays.

    Preserve the source optical centre. Only a truly vertical direction needs
    the source camera's up to select its otherwise undefined azimuth.
    Return distance, azimuth/elevation in degrees, and camera-to-world rotation;
    a coincident target returns None, meaning the original camera projection.
    """
    to = np.asarray(point, dtype=np.float64) - np.asarray(eye, dtype=np.float64)
    distance = float(np.linalg.norm(to))
    if distance < 1e-6:
        return None
    forward = to / distance
    azimuth = math.atan2(float(forward[1]), float(forward[0]))
    if float(np.linalg.norm(np.cross(forward, [0., 0., 1.]))) < 1e-8:
        up = np.asarray(source_rotation, dtype=np.float64)[:, 1]
        sign = 1. if forward[2] < 0. else -1.
        azimuth = math.atan2(sign * float(up[1]), sign * float(up[0]))
    elevation = math.asin(max(-1., min(1., float(forward[2]))))
    # These are the actual MuJoCo free-camera axes, including at the poles.
    f = np.array([math.cos(elevation) * math.cos(azimuth),
                  math.cos(elevation) * math.sin(azimuth), math.sin(elevation)])
    right = np.array([math.sin(azimuth), -math.cos(azimuth), 0.])
    rotation = np.column_stack((right, np.cross(right, f), -f))
    return distance, math.degrees(azimuth), math.degrees(elevation), rotation
