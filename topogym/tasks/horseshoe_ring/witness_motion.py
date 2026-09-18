"""Declared geometric witness motion, shared by validation and pose replay."""
import numpy as np
from scipy.spatial.transform import Rotation, Slerp


def fold_transforms(state, pivot_m=.024):
    """Two moving contact axes make a folded chain while preserving each link.

    State: [fold angle, target xyz in middle-link frame, target delta xyzw].
    All meshes start in the original assembly frame; identity target delta is
    the template's inclined target ring. Left-side bodies stay in place.
    """
    q = np.asarray(state, dtype=float)
    if q.shape != (8,) or not np.isfinite(q).all() or not np.isclose(np.linalg.norm(q[4:]), 1., atol=1e-5):
        raise ValueError("Witness states need one angle, three coordinates and a unit xyzw quaternion")
    left, right = np.array([-pivot_m, 0., 0.]), np.array([pivot_m, 0., 0.])
    half = Rotation.from_euler("y", q[0]/2).as_matrix()
    whole = half@half
    middle = left-half@left
    transforms = [(np.eye(3), np.zeros(3)), (half, middle),
                  (whole, middle+half@right-whole@right),
                  (half@Rotation.from_quat(q[4:]).as_matrix(), middle+half@q[1:4])]
    return transforms


def interpolate(a, b, t):
    a, b = np.asarray(a), np.asarray(b)
    q = Slerp([0., 1.], Rotation.from_quat([a[4:], b[4:]]))([t]).as_quat()[0]
    return np.r_[(1-t)*a[:4]+t*b[:4], q]


