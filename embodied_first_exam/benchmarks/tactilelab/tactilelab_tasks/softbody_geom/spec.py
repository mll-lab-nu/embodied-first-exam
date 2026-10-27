"""Pure-numpy description of the soft bodies and their colliders (imported by both the Isaac and the Newton interpreters).

Frames: everything is in the env-local frame, metres, quaternions ``xyzw`` (Newton order; the Isaac side of the package
uses ``wxyz`` and converts with the helpers below).
"""

from __future__ import annotations

import copy
import dataclasses
from typing import Any, Dict, Optional, Sequence, Tuple

import numpy as np

# -- quaternion / pose helpers (xyzw) ---------------------------------------------------------------------------------


def quat_wxyz_to_xyzw(q: np.ndarray) -> np.ndarray:
    q = np.asarray(q, dtype=np.float64)
    return np.concatenate([q[..., 1:], q[..., :1]], axis=-1)


def quat_xyzw_to_wxyz(q: np.ndarray) -> np.ndarray:
    q = np.asarray(q, dtype=np.float64)
    return np.concatenate([q[..., 3:], q[..., :3]], axis=-1)


def pose7_wxyz_to_xyzw(p: np.ndarray) -> np.ndarray:
    """``[x y z qw qx qy qz]`` (package convention) -> ``[x y z qx qy qz qw]`` (sidecar wire), broadcasting."""
    p = np.asarray(p, dtype=np.float64)
    return np.concatenate([p[..., :3], quat_wxyz_to_xyzw(p[..., 3:7])], axis=-1)


def pose7_xyzw_to_wxyz(p: np.ndarray) -> np.ndarray:
    p = np.asarray(p, dtype=np.float64)
    return np.concatenate([p[..., :3], quat_xyzw_to_wxyz(p[..., 3:7])], axis=-1)


def quat_mul(a: np.ndarray, b: np.ndarray) -> np.ndarray:
    """Hamilton product, xyzw, broadcasting."""
    ax, ay, az, aw = np.moveaxis(np.asarray(a, dtype=np.float64), -1, 0)
    bx, by, bz, bw = np.moveaxis(np.asarray(b, dtype=np.float64), -1, 0)
    return np.stack(
        [
            aw * bx + ax * bw + ay * bz - az * by,
            aw * by - ax * bz + ay * bw + az * bx,
            aw * bz + ax * by - ay * bx + az * bw,
            aw * bw - ax * bx - ay * by - az * bz,
        ],
        axis=-1,
    )


def quat_rotate(q: np.ndarray, v: np.ndarray) -> np.ndarray:
    """Rotate ``v`` (``(..., 3)``) by unit quaternion ``q`` (xyzw, broadcasting)."""
    q = np.asarray(q, dtype=np.float64)
    v = np.asarray(v, dtype=np.float64)
    u = q[..., :3]
    w = q[..., 3:4]
    t = 2.0 * np.cross(u, v)
    return v + w * t + np.cross(u, t)


def quat_to_mat(q: np.ndarray) -> np.ndarray:
    """3x3 rotation matrix of a unit quaternion (xyzw)."""
    x, y, z, w = (float(v) for v in np.asarray(q, dtype=np.float64) / np.linalg.norm(q))
    return np.array(
        [
            [1 - 2 * (y * y + z * z), 2 * (x * y - z * w), 2 * (x * z + y * w)],
            [2 * (x * y + z * w), 1 - 2 * (x * x + z * z), 2 * (y * z - x * w)],
            [2 * (x * z - y * w), 2 * (y * z + x * w), 1 - 2 * (x * x + y * y)],
        ]
    )


def mat_to_quat(R: np.ndarray) -> np.ndarray:
    """Unit quaternion (xyzw, w >= 0) of a rotation matrix."""
    R = np.asarray(R, dtype=np.float64)
    t = np.trace(R)
    if t > 0.0:
        s = 0.5 / np.sqrt(t + 1.0)
        q = np.array([(R[2, 1] - R[1, 2]) * s, (R[0, 2] - R[2, 0]) * s, (R[1, 0] - R[0, 1]) * s, 0.25 / s])
    elif R[0, 0] > R[1, 1] and R[0, 0] > R[2, 2]:
        s = 2.0 * np.sqrt(1.0 + R[0, 0] - R[1, 1] - R[2, 2])
        q = np.array([0.25 * s, (R[0, 1] + R[1, 0]) / s, (R[0, 2] + R[2, 0]) / s, (R[2, 1] - R[1, 2]) / s])
    elif R[1, 1] > R[2, 2]:
        s = 2.0 * np.sqrt(1.0 + R[1, 1] - R[0, 0] - R[2, 2])
        q = np.array([(R[0, 1] + R[1, 0]) / s, 0.25 * s, (R[1, 2] + R[2, 1]) / s, (R[0, 2] - R[2, 0]) / s])
    else:
        s = 2.0 * np.sqrt(1.0 + R[2, 2] - R[0, 0] - R[1, 1])
        q = np.array([(R[0, 2] + R[2, 0]) / s, (R[1, 2] + R[2, 1]) / s, 0.25 * s, (R[1, 0] - R[0, 1]) / s])
    q /= np.linalg.norm(q)
    return q if q[3] >= 0 else -q


def frame_from_axes(a: Sequence[float], z: Sequence[float]) -> np.ndarray:
    """Right-handed basis ``[a, z x a, z]`` (columns) from an approach axis ``a`` (orthogonalised against ``z``) and ``z``."""
    z = np.asarray(z, dtype=np.float64)
    z = z / np.linalg.norm(z)
    a = np.asarray(a, dtype=np.float64)
    a = a - (a @ z) * z
    a = a / np.linalg.norm(a)
    return np.stack([a, np.cross(z, a), z], axis=1)


def quat_from_yaw(yaw: float) -> np.ndarray:
    return np.array([0.0, 0.0, np.sin(0.5 * yaw), np.cos(0.5 * yaw)])


def quat_from_euler_deg(rpy_deg: Sequence[float]) -> np.ndarray:
    """xyzw quaternion of intrinsic Z-Y-X (yaw-pitch-roll) angles given as ``[roll, pitch, yaw]`` degrees."""
    r, p, y = (np.radians(float(a)) * 0.5 for a in rpy_deg)
    cr, sr, cp, sp, cy, sy = np.cos(r), np.sin(r), np.cos(p), np.sin(p), np.cos(y), np.sin(y)
    return np.array(
        [
            sr * cp * cy - cr * sp * sy,
            cr * sp * cy + sr * cp * sy,
            cr * cp * sy - sr * sp * cy,
            cr * cp * cy + sr * sp * sy,
        ]
    )


def pose_apply(pose: np.ndarray, local: np.ndarray) -> np.ndarray:
    """World position of ``local`` (``(..., 3)``) seen from the frame ``pose`` = ``(x y z qx qy qz qw)``."""
    pose = np.asarray(pose, dtype=np.float64)
    return pose[..., :3] + quat_rotate(pose[..., 3:7], local)


def pose_compose(a: np.ndarray, b: np.ndarray) -> np.ndarray:
    """``a * b`` (pose ``b`` expressed in frame ``a``)."""
    a = np.asarray(a, dtype=np.float64)
    b = np.asarray(b, dtype=np.float64)
    pos = pose_apply(a, b[..., :3])
    q = quat_mul(a[..., 3:7], b[..., 3:7])
    return np.concatenate([pos, q], axis=-1)


def pose_inverse(p: np.ndarray) -> np.ndarray:
    p = np.asarray(p, dtype=np.float64)
    qi = np.concatenate([-p[..., 3:6], p[..., 6:7]], axis=-1)
    return np.concatenate([quat_rotate(qi, -p[..., :3]), qi], axis=-1)


# -- cloth ------------------------------------------------------------------------------------------------------------


def grid_vertices(cells: Tuple[int, int], size: Tuple[float, float]) -> np.ndarray:
    """``((nx+1)*(ny+1), 3)`` local grid vertices (z=0), row-major in y: index ``iy*(nx+1)+ix``; the grid spans
    ``[0, lx] x [0, ly]`` (origin at the corner)."""
    nx, ny = cells
    lx, ly = size
    xs = np.linspace(0.0, lx, nx + 1)
    ys = np.linspace(0.0, ly, ny + 1)
    X, Y = np.meshgrid(xs, ys)
    return np.stack([X.ravel(), Y.ravel(), np.zeros(X.size)], axis=1)


def grid_triangles(cells: Tuple[int, int]) -> np.ndarray:
    """``(2*nx*ny, 3)`` counter-clockwise (seen from +z) triangle indices of the grid of :func:`grid_vertices`."""
    nx, ny = cells
    tris = []
    for iy in range(ny):
        for ix in range(nx):
            v0 = iy * (nx + 1) + ix
            v1 = v0 + 1
            v2 = v0 + nx + 2
            v3 = v0 + nx + 1
            # alternate the diagonal so the mesh has no preferred shear direction
            if (ix + iy) % 2 == 0:
                tris += [(v0, v1, v2), (v0, v2, v3)]
            else:
                tris += [(v0, v1, v3), (v1, v2, v3)]
    return np.asarray(tris, dtype=np.int32)


def cloth_rest_positions(c: Dict[str, Any]) -> np.ndarray:
    """Env-local rest positions ``(P, 3)`` of a cloth sheet config (``origin``, ``size``, ``cells``, ``yaw``)."""
    cells = tuple(int(v) for v in c["cells"])
    size = tuple(float(v) for v in c["size"])
    v = grid_vertices(cells, size)
    qz = quat_from_yaw(float(c.get("yaw", 0.0)))
    return np.asarray(c["origin"], dtype=np.float64) + quat_rotate(qz, v)


def region_mask(points_xy: np.ndarray, regions: Sequence[Dict[str, Sequence[float]]]) -> np.ndarray:
    """Boolean mask of the points inside any of the axis-aligned xy rectangles ``{"min": [x, y], "max": [x, y]}``."""
    pts = np.asarray(points_xy, dtype=np.float64)[:, :2]
    m = np.zeros(len(pts), dtype=bool)
    for r in regions:
        lo = np.asarray(r["min"], dtype=np.float64)
        hi = np.asarray(r["max"], dtype=np.float64)
        m |= np.all((pts >= lo - 1e-9) & (pts <= hi + 1e-9), axis=1)
    return m


def grid_boundary_edges(cells: Tuple[int, int]) -> Dict[str, np.ndarray]:
    """Particle ids of the four sheet edges (``x0``: ix=0, ``x1``: ix=nx, ``y0``: iy=0, ``y1``: iy=ny)."""
    nx, ny = cells
    idx = np.arange((nx + 1) * (ny + 1)).reshape(ny + 1, nx + 1)
    return {"x0": idx[:, 0], "x1": idx[:, -1], "y0": idx[0, :], "y1": idx[-1, :]}


# -- cable ------------------------------------------------------------------------------------------------------------


def polyline_length(points: np.ndarray) -> float:
    p = np.asarray(points, dtype=np.float64)
    return float(np.linalg.norm(np.diff(p, axis=0), axis=1).sum())


def resample_polyline(points: np.ndarray, n_seg: int) -> np.ndarray:
    """``(n_seg+1, 3)`` points equally spaced in arc length along ``points``."""
    p = np.asarray(points, dtype=np.float64)
    seg = np.linalg.norm(np.diff(p, axis=0), axis=1)
    s = np.concatenate([[0.0], np.cumsum(seg)])
    t = np.linspace(0.0, s[-1], n_seg + 1)
    return np.stack([np.interp(t, s, p[:, k]) for k in range(3)], axis=1)


def sag_polyline(
    a: np.ndarray, b: np.ndarray, length: float, n_seg: int, z_floor: Optional[float] = None
) -> np.ndarray:
    """A cable of arc length ``length`` between end points ``a`` and ``b`` (``length >= |b - a|``) hanging as an arc in the
    vertical plane through them: a parabola of the matching sag.  If ``z_floor`` is set the lowest points are clipped to it
    (a slack cable lying on a table).  ``(n_seg+1, 3)``, equally spaced in arc length."""
    a = np.asarray(a, dtype=np.float64)
    b = np.asarray(b, dtype=np.float64)
    chord = float(np.linalg.norm(b - a))
    if length < chord - 1e-9:
        raise ValueError(f"cable length {length:.4f} is shorter than the chord {chord:.4f}")
    # parabola length ~ chord + 8 sag^2 / (3 chord)  ->  sag
    sag = np.sqrt(max(length - chord, 0.0) * 3.0 * chord / 8.0)
    u = np.linspace(0.0, 1.0, 400)
    pts = a[None] + u[:, None] * (b - a)[None]
    pts[:, 2] -= 4.0 * sag * u * (1.0 - u)
    if z_floor is not None:
        pts[:, 2] = np.maximum(pts[:, 2], z_floor)
    return resample_polyline(pts, n_seg)


def planar_arc(
    a: np.ndarray, b: np.ndarray, length: float, n_seg: int, side: float = 1.0, shape: str = "arc"
) -> np.ndarray:
    """A cable of arc length ``length`` lying in the horizontal plane through ``a`` between ``a`` and ``b``, bulging sideways
    (``arc``: one parabolic lobe, ``s``: an S curve of two opposite lobes).  ``(n_seg + 1, 3)``, equally spaced in arc length."""
    a = np.asarray(a, dtype=np.float64)
    b = np.asarray(b, dtype=np.float64)
    chord_v = b - a
    chord = float(np.linalg.norm(chord_v[:2]))
    if length < chord - 1e-9:
        raise ValueError(f"cable length {length:.4f} is shorter than the chord {chord:.4f}")
    u = chord_v[:2] / chord
    nrm = np.array([-u[1], u[0]])
    t = np.linspace(0.0, 1.0, 600)
    if shape == "s":
        # amplitude of A sin(2 pi t): the length of the curve is ~ chord + (pi A)^2 / chord (small amplitude)
        amp = np.sqrt(max(length - chord, 0.0) * chord) / np.pi
        off = amp * np.sin(2.0 * np.pi * t)
    else:
        amp = np.sqrt(max(length - chord, 0.0) * 3.0 * chord / 8.0)
        off = 4.0 * amp * t * (1.0 - t)
    off *= float(side)
    xy = a[None, :2] + t[:, None] * chord_v[None, :2] + off[:, None] * nrm[None]
    z = a[2] + t * chord_v[2]
    pts = np.column_stack([xy, z])
    # the small-amplitude formulas are approximate: rescale the lateral offset until the arc length matches
    for _ in range(30):
        cur = polyline_length(pts)
        if abs(cur - length) < 1e-5:
            break
        amp *= 1.0 + 0.7 * (length - cur) / max(cur - chord, 1e-3)
        off = (4.0 * amp * t * (1.0 - t) if shape != "s" else amp * np.sin(2.0 * np.pi * t)) * float(side)
        pts = np.column_stack([a[None, :2] + t[:, None] * chord_v[None, :2] + off[:, None] * nrm[None], z])
    return resample_polyline(pts, n_seg)


def cable_rod_frame(points: np.ndarray) -> Tuple[np.ndarray, np.ndarray]:
    """Segment midpoints ``(S, 3)`` and unit tangents ``(S, 3)`` of the node polyline."""
    p = np.asarray(points, dtype=np.float64)
    d = np.diff(p, axis=0)
    n = np.linalg.norm(d, axis=1, keepdims=True)
    return 0.5 * (p[1:] + p[:-1]), d / np.maximum(n, 1e-12)


def tube_mesh(nodes: np.ndarray, radius: float, sides: int = 8) -> Tuple[np.ndarray, np.ndarray]:
    """A closed-ended tube around the polyline ``nodes`` ``(N, 3)``: vertices ``(N*sides + 2, 3)`` and triangles.  The vertex
    count only depends on ``N`` and ``sides``, so :func:`tube_vertices` can update the same topology every step."""
    n = len(nodes)
    tris = []
    for i in range(n - 1):
        for k in range(sides):
            a = i * sides + k
            b = i * sides + (k + 1) % sides
            c = (i + 1) * sides + k
            d = (i + 1) * sides + (k + 1) % sides
            tris += [(a, c, b), (b, c, d)]
    cap0 = n * sides
    cap1 = n * sides + 1
    for k in range(sides):
        tris.append((cap0, k, (k + 1) % sides))
        tris.append((cap1, (n - 1) * sides + (k + 1) % sides, (n - 1) * sides + k))
    return tube_vertices(nodes, radius, sides), np.asarray(tris, dtype=np.int32)


def tube_vertices(nodes: np.ndarray, radius: float, sides: int = 8) -> np.ndarray:
    p = np.asarray(nodes, dtype=np.float64)
    n = len(p)
    t = np.zeros_like(p)
    t[1:-1] = p[2:] - p[:-2]
    t[0] = p[1] - p[0]
    t[-1] = p[-1] - p[-2]
    t /= np.maximum(np.linalg.norm(t, axis=1, keepdims=True), 1e-12)
    # a reference direction that is never parallel to the tangent, then parallel transport the normal along the cable
    ref = np.array([0.0, 0.0, 1.0])
    normals = np.zeros_like(p)
    nrm = np.cross(t[0], ref)
    if np.linalg.norm(nrm) < 1e-6:
        nrm = np.cross(t[0], np.array([1.0, 0.0, 0.0]))
    nrm /= np.linalg.norm(nrm)
    for i in range(n):
        if i > 0:
            nrm = nrm - np.dot(nrm, t[i]) * t[i]
            nn = np.linalg.norm(nrm)
            nrm = nrm / nn if nn > 1e-9 else np.cross(t[i], ref)
        normals[i] = nrm
    binorm = np.cross(t, normals)
    ang = np.linspace(0.0, 2.0 * np.pi, sides, endpoint=False)
    ring = np.cos(ang)[None, :, None] * normals[:, None, :] + np.sin(ang)[None, :, None] * binorm[:, None, :]
    verts = p[:, None, :] + radius * ring
    caps = np.stack([p[0] - radius * 0.5 * t[0], p[-1] + radius * 0.5 * t[-1]])
    return np.concatenate([verts.reshape(-1, 3), caps], axis=0).astype(np.float32)


# -- config -----------------------------------------------------------------------------------------------------------
DEFAULT_WORLD: Dict[str, Any] = {
    "fps": 60,
    "substeps": 10,
    "iterations": 5,
    "gravity": 9.81,
    "table": {"z": 0.0, "center": [0.0, 0.0], "half": [1.0, 1.0], "thickness": 0.1, "mu": 0.6},
    "soft_contact": {"ke": 1.0e3, "kd": 1.0e1, "mu": 0.8, "gap": 0.005},
    "statics": [],
    "colliders": [],
}

DEFAULT_CLOTH: Dict[str, Any] = {
    "origin": [0.0, 0.0, 0.0],
    "size": [0.2, 0.1],
    "cells": [20, 10],
    "yaw": 0.0,
    "density": 0.25,  # kg/m^2 (a light cotton)
    "tri_ke": 5.0e2,
    "tri_ka": 5.0e2,
    "tri_kd": 1.0e-1,
    "edge_ke": 1.0e-2,
    "edge_kd": 1.0e-4,
    "radius": 0.002,
    "pin_regions": [],
    "self_contact": True,
    "bend_yield": 0.35,  # rad: elastic range of a fold hinge (plastic hinge, sidecar/worlds/softbody.py)
    "bend_crease_angle": 10.0,  # rad: hinges folded sharper than this crease (rest angle follows fully); 10 = never
    "bend_plastic_rate": 0.0,  # fraction of the excess angle absorbed per control frame; 0 = elastic only (default OFF)
    "color": [0.85, 0.35, 0.30],
}

DEFAULT_CABLE: Dict[str, Any] = {
    "radius": 0.003,
    "density": 800.0,
    "stretch_stiffness": 1.0e4,
    "stretch_damping": 1.0e-1,
    "bend_stiffness": 1.0e-2,
    "bend_damping": 1.0e-4,
    "mu": 0.8,
    "ke": 1.0e4,
    "kd": 1.0e-1,
    "pinned_segments": [],
    "self_collision": False,
    "color": [0.90, 0.45, 0.10],
}


def merge_dicts(base: Dict[str, Any], over: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    """Deep merge of ``over`` on top of a deep copy of ``base`` (nested dicts merged, everything else replaced)."""
    out = copy.deepcopy(base)
    for k, v in (over or {}).items():
        if isinstance(v, dict) and isinstance(out.get(k), dict):
            out[k] = merge_dicts(out[k], v)
        else:
            out[k] = copy.deepcopy(v)
    return out


def world_cfg(over: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """World config with defaults filled in; ``cloth`` / ``cable`` blocks are optional and get their defaults when present."""
    over = dict(over or {})
    cloth = over.pop("cloth", None)
    cable = over.pop("cable", None)
    cfg = merge_dicts(DEFAULT_WORLD, over)
    if cloth is not None:
        cfg["cloth"] = merge_dicts(DEFAULT_CLOTH, cloth)
    if cable is not None:
        cfg["cable"] = merge_dicts(DEFAULT_CABLE, cable)
    if "cloth" not in cfg and "cable" not in cfg:
        raise ValueError("a soft world needs a `cloth` or a `cable` block")
    for i, c in enumerate(cfg["colliders"]):
        need = (
            ("name", "radius", "half_height") if c.get("shape", "box") in ("cylinder", "capsule") else ("name", "half")
        )
        for key in need:
            if key not in c:
                raise ValueError(f"collider #{i} lacks `{key}`")
    return cfg


def tube_cloth(t: Dict[str, Any]) -> Tuple[np.ndarray, np.ndarray]:
    """A sleeve (cylindrical cloth tube): ``(P, 3)`` vertices and ``(T, 3)`` triangles.

    ``t``: ``center`` (the middle of the tube), ``axis`` (unit vector), ``radius``, ``length``, ``n_around``, ``n_len``,
    optional ``phase`` (rad, ring columns turned about the axis), ``flare`` = {``rings``, ``radius``, ``end``, ``ramp``} and
    ``tab`` = {``height``, ``rows``, ``columns``, ``end``, ``up``, ``orient`` = axis|ring} (a pull tab on the cuff ring, appended
    after the tube's vertices).  Vertex ``j * n_around + i`` is ring ``j`` (0 at ``center - length / 2 * axis``), angle ``i``;
    the seam is closed (the last column connects to the first).  Triangles are wound outward."""
    n_a, n_l = int(t["n_around"]), int(t["n_len"])
    axis = np.asarray(t["axis"], dtype=np.float64)
    axis = axis / np.linalg.norm(axis)
    ref = np.array([0.0, 0.0, 1.0]) if abs(axis[2]) < 0.9 else np.array([1.0, 0.0, 0.0])
    u = np.cross(axis, ref)
    u /= np.linalg.norm(u)
    v = np.cross(axis, u)
    ang = np.linspace(0.0, 2.0 * np.pi, n_a, endpoint=False) + float(t.get("phase", 0.0))
    s = np.linspace(-0.5, 0.5, n_l + 1) * float(t["length"])
    verts = np.zeros((n_l + 1, n_a, 3))
    ring_r = np.full(n_l + 1, float(t["radius"]))
    fl = t.get(
        "flare"
    )  # a wider collar at the last rings (a stiff cuff the fingers can pinch without touching the forearm)
    if fl:
        k = int(fl.get("rings", 3))
        end = str(fl.get("end", "last"))
        ids = np.arange(n_l + 1 - k, n_l + 1) if end == "last" else np.arange(0, k)
        ring_r[ids] = float(fl["radius"])
        step = (ids[0] - 1) if end == "last" else (ids[-1] + 1)  # one transition ring half way
        if 0 <= step <= n_l:
            ring_r[step] = 0.5 * (float(t["radius"]) + float(fl["radius"]))
        if fl.get(
            "ramp"
        ):  # a funnel: the radius grows linearly over the last `rings` rings (a conical wall the tilted pads can pinch)
            r0, r1 = float(t["radius"]), float(fl["radius"])
            seq = np.arange(k + 1)
            vals = r0 + (r1 - r0) * seq / k
            tgt = np.arange(n_l - k, n_l + 1) if end == "last" else np.arange(k, -1, -1)
            ring_r[tgt] = vals
    for j in range(n_l + 1):
        verts[j] = (
            np.asarray(t["center"], dtype=np.float64)
            + s[j] * axis
            + ring_r[j] * (np.cos(ang)[:, None] * u + np.sin(ang)[:, None] * v)
        )
    tris = []
    for j in range(n_l):
        for i in range(n_a):
            a = j * n_a + i
            b = j * n_a + (i + 1) % n_a
            c = (j + 1) * n_a + i
            d = (j + 1) * n_a + (i + 1) % n_a
            tris += [(a, b, d), (a, d, c)] if (i + j) % 2 == 0 else [(a, b, c), (b, d, c)]
    verts = verts.reshape(-1, 3)
    tris = np.asarray(tris, dtype=np.int32)
    tab = t.get("tab")
    if tab:  # a pull tab: a flat strip of cloth standing up from the cuff ring (shares the ring vertices), pinched by two pads
        verts, tris = _add_pull_tab(
            verts,
            tris,
            n_a,
            n_l,
            tab,
            axis,
            u,
            v,
            str(t.get("flare", {}).get("end", "last")) if t.get("flare") else "last",
        )
    return verts, tris


def _add_pull_tab(verts, tris, n_a, n_l, tab, axis, u, v, end):
    """Append a strip ``columns`` ring vertices wide and ``rows`` rows of ``height / rows`` tall to the cuff ring (the last ring, or the
    first with ``tab['end'] = 'first'``) at the ring vertices closest to ``tab['up']`` (default world +z).  Returns the new
    ``(verts, tris)``; the tab vertices come after the tube's, row by row (row 1 sits on the ring)."""
    up = np.asarray(tab.get("up", (0.0, 0.0, 1.0)), dtype=np.float64)
    up = up / np.linalg.norm(up)
    ring = n_l if str(tab.get("end", "last")) == "last" else 0
    ids = np.arange(n_a) + ring * n_a
    centre = verts[ids].mean(axis=0)
    top = int(np.argmax((verts[ids] - centre) @ up))
    cols = int(tab.get("columns", 3))
    if str(tab.get("orient", "axis")) == "axis":
        # a fin in the plane containing the sleeve axis and ``up`` (its faces look sideways): columns = the top generatrix, starting at the
        # cuff ring and going inboard; the pads close across it.  ("ring": the strip follows the cuff ring instead: its faces look along the axis)
        step = -1 if ring == n_l else 1
        sel = [top + (ring + step * k) * n_a for k in range(cols)]
    else:
        sel = [ids[(top + k - cols // 2) % n_a] for k in range(cols)]
    rows = int(tab.get("rows", 3))
    h = float(tab["height"]) / rows
    new = []
    idx = np.zeros((rows + 1, cols), dtype=np.int64)
    idx[0] = sel
    base = len(verts)
    for r in range(1, rows + 1):
        for c in range(cols):
            new.append(verts[sel[c]] + r * h * up)
            idx[r, c] = base + len(new) - 1
    tr = []
    for r in range(rows):
        for c in range(cols - 1):
            a, b, d, e = idx[r, c], idx[r, c + 1], idx[r + 1, c + 1], idx[r + 1, c]
            tr += [(a, b, d), (a, d, e)] if (r + c) % 2 == 0 else [(a, b, e), (b, d, e)]
    return np.vstack([verts, np.asarray(new)]), np.vstack([tris, np.asarray(tr, dtype=np.int32)])


@dataclasses.dataclass
class ColliderSpec:
    """One kinematic collider mirrored into the soft world: a box (or cylinder / capsule) fixed to a robot link.

    ``link``: body name in the robot articulation; ``offset``: ``(x y z qx qy qz qw)`` of the shape in the link frame;
    ``half``: box half extents [m]; ``mu``: friction of the surface.
    """

    name: str
    link: str
    half: Tuple[float, float, float]
    offset: Tuple[float, ...] = (0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 1.0)
    mu: float = 1.0
    shape: str = "box"  # box | cylinder | capsule (axis = the collider frame's z)
    radius: float = 0.0
    half_height: float = 0.0

    @staticmethod
    def from_cfg(d: Dict[str, Any]) -> "ColliderSpec":
        off = list(d.get("offset", [0, 0, 0]))
        if len(off) == 3:
            off = off + [0.0, 0.0, 0.0, 1.0]
        return ColliderSpec(
            name=str(d["name"]),
            link=str(d["link"]),
            half=tuple(float(x) for x in d.get("half", (0.0, 0.0, 0.0))),
            offset=tuple(float(x) for x in off),
            mu=float(d.get("mu", 1.0)),
            shape=str(d.get("shape", "box")),
            radius=float(d.get("radius", 0.0)),
            half_height=float(d.get("half_height", 0.0)),
        )

    def world_cfg(self) -> Dict[str, Any]:
        """The sidecar's view of the collider (no link name)."""
        out: Dict[str, Any] = {"name": self.name, "half": list(self.half), "mu": self.mu, "shape": self.shape}
        if self.shape != "box":
            out.update(radius=self.radius, half_height=self.half_height)
        return out


def collider_poses(specs: Sequence[ColliderSpec], link_poses_xyzw: Dict[str, np.ndarray]) -> np.ndarray:
    """``(C, 7)`` env-local xyzw collider poses from the env-local xyzw poses of the links (``{link name: pose7}``), each
    composed with the spec's offset.  The Isaac side calls this once per control tick."""
    out = np.zeros((len(specs), 7), dtype=np.float64)
    for k, s in enumerate(specs):
        out[k] = pose_compose(
            np.asarray(link_poses_xyzw[s.link], dtype=np.float64), np.asarray(s.offset, dtype=np.float64)
        )
    return out.astype(np.float32)
