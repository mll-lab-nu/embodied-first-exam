"""Dough scene geometry (pure numpy, importable on both sides of the Newton bridge).

Everything is env-local, metres, z up.  A *blob* is a set of MPM particles filling a shape on a jittered grid of
``ppc`` particles per axis and voxel; the particles of one blob all stand for the same volume.
"""

from __future__ import annotations

from typing import Dict, Tuple

import numpy as np


def _grid_in_box(lo: np.ndarray, hi: np.ndarray, voxel: float, ppc: int, rng, jitter: float):
    """Jittered regular grid of particles in the box [lo, hi]; spacing voxel / ppc."""
    h = voxel / ppc
    n = np.maximum(1, np.round((hi - lo) / h)).astype(int)
    h3 = (hi - lo) / n
    axes = [lo[k] + (np.arange(n[k]) + 0.5) * h3[k] for k in range(3)]
    pts = np.stack(np.meshgrid(*axes, indexing="ij"), axis=-1).reshape(-1, 3)
    if jitter > 0:
        pts = pts + (rng.random(pts.shape) - 0.5) * jitter * h3
    return pts, float(np.prod(h3))


def blob_points(
    shape: Dict,
    voxel: float,
    ppc: int = 2,
    seed: int = 0,
    jitter: float = 0.5,
) -> Tuple[np.ndarray, float]:
    """Particles filling ``shape``; returns ``(points (n, 3), particle_volume [m^3])``.

    ``shape`` is one of
      * ``{"type": "cylinder", "center": [x, y, z0], "radius": r, "height": h}``  (z0 = bottom)
      * ``{"type": "box", "center": [x, y, z0], "size": [sx, sy, h]}``            (z0 = bottom)
      * ``{"type": "heights", "lo": [x0, y0], "dx": dx, "heights": H (nx, ny), "z0": z}``  a height field
      * ``{"type": "ellipsoid", "center": [x, y, z0], "radii": [a, b, c]}``       (z0 = bottom, centre z0 + c)
    """
    rng = np.random.default_rng(seed)
    t = shape["type"]
    if t == "cylinder":
        c = np.asarray(shape["center"], float)
        r, h = float(shape["radius"]), float(shape["height"])
        lo = np.array([c[0] - r, c[1] - r, c[2]])
        hi = np.array([c[0] + r, c[1] + r, c[2] + h])
        pts, pv = _grid_in_box(lo, hi, voxel, ppc, rng, jitter)
        keep = (pts[:, 0] - c[0]) ** 2 + (pts[:, 1] - c[1]) ** 2 <= r * r
        return pts[keep], pv
    if t == "box":
        c = np.asarray(shape["center"], float)
        s = np.asarray(shape["size"], float)
        lo = np.array([c[0] - 0.5 * s[0], c[1] - 0.5 * s[1], c[2]])
        hi = np.array([c[0] + 0.5 * s[0], c[1] + 0.5 * s[1], c[2] + s[2]])
        return _grid_in_box(lo, hi, voxel, ppc, rng, jitter)
    if t == "ellipsoid":
        c = np.asarray(shape["center"], float)
        a, b, cc = (float(v) for v in shape["radii"])
        lo = np.array([c[0] - a, c[1] - b, c[2]])
        hi = np.array([c[0] + a, c[1] + b, c[2] + 2 * cc])
        pts, pv = _grid_in_box(lo, hi, voxel, ppc, rng, jitter)
        q = (pts - np.array([c[0], c[1], c[2] + cc])) / np.array([a, b, cc])
        return pts[(q * q).sum(1) <= 1.0], pv
    if t == "heights":
        H = np.asarray(shape["heights"], float)
        x0, y0 = (float(v) for v in shape["lo"])
        dx = float(shape["dx"])
        z0 = float(shape.get("z0", 0.0))
        nx, ny = H.shape
        lo = np.array([x0, y0, z0])
        hi = np.array([x0 + nx * dx, y0 + ny * dx, z0 + float(H.max())])
        pts, pv = _grid_in_box(lo, hi, voxel, ppc, rng, jitter)
        ix = np.clip(((pts[:, 0] - x0) / dx).astype(int), 0, nx - 1)
        iy = np.clip(((pts[:, 1] - y0) / dx).astype(int), 0, ny - 1)
        return pts[pts[:, 2] - z0 <= H[ix, iy]], pv
    raise ValueError(f"unknown blob shape {t!r}")


def union_points(blobs, voxel: float, ppc: int = 2, seed: int = 0, jitter: float = 0.5):
    """Concatenate several blobs (list of shape dicts); all must use the same voxel / ppc (same particle volume)."""
    pts, pv = [], None
    for i, b in enumerate(blobs):
        p, v = blob_points(b, voxel, ppc, seed + i, jitter)
        pts.append(p)
        pv = v if pv is None else pv
    return np.concatenate(pts, 0), float(pv)


def quat_yaw(yaw: float) -> np.ndarray:
    """xyzw quaternion of a rotation ``yaw`` about +z."""
    return np.array([0.0, 0.0, np.sin(0.5 * yaw), np.cos(0.5 * yaw)])


def slerp_xyzw(q0: np.ndarray, q1: np.ndarray, a: float) -> np.ndarray:
    q0 = np.asarray(q0, float)
    q1 = np.asarray(q1, float)
    d = float(np.dot(q0, q1))
    if d < 0:
        q1, d = -q1, -d
    if d > 0.9995:
        q = q0 + a * (q1 - q0)
        return q / np.linalg.norm(q)
    th = np.arccos(np.clip(d, -1, 1))
    return (np.sin((1 - a) * th) * q0 + np.sin(a * th) * q1) / np.sin(th)


def interp_pose(p0: np.ndarray, p1: np.ndarray, a: float) -> np.ndarray:
    """Pose (x y z qx qy qz qw) between two poses: linear position, slerp rotation."""
    out = np.empty(7)
    out[:3] = (1 - a) * p0[:3] + a * p1[:3]
    out[3:] = slerp_xyzw(p0[3:], p1[3:], a)
    return out


def quat_rot_xyzw(q) -> np.ndarray:
    """Rotation matrix of an xyzw quaternion."""
    x, y, z, w = np.asarray(q, float) / np.linalg.norm(q)
    return np.array(
        [
            [1 - 2 * (y * y + z * z), 2 * (x * y - w * z), 2 * (x * z + w * y)],
            [2 * (x * y + w * z), 1 - 2 * (x * x + z * z), 2 * (y * z - w * x)],
            [2 * (x * z - w * y), 2 * (y * z + w * x), 1 - 2 * (x * x + y * y)],
        ]
    )
