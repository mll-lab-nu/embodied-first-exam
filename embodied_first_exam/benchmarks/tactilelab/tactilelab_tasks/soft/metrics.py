"""Pure-numpy geometry and success metrics of the cloth / cable tasks (no simulator imports).

Frames: env-local metres.  Poses handed to these functions are ``[x y z qx qy qz qw]`` (xyzw, the soft-world
convention of :mod:`tactilelab_tasks.softbody_geom.spec`); the pad poses the tasks keep are in that order.
"""

from __future__ import annotations

from typing import Dict, Optional, Sequence, Tuple

import numpy as np

from ..softbody_geom import spec

__all__ = [
    "box_surface_distance",
    "contact_counts",
    "pad_penetration",
    "box_overlap",
    "cloth_samples",
    "in_frame_box",
    "edge_arclength",
    "project_on_polyline",
    "displacement_rms",
    "cable_length",
    "cable_slack",
    "cable_sag",
    "stretch_ratio",
    "slot_centerline",
    "rail_boxes",
    "polyline_distance",
    "routed_prefix_length",
    "fold_partners",
    "fold_errors",
]


# ----------------------------------------------------------------------------- boxes
def box_surface_distance(points: np.ndarray, pose: np.ndarray, half: Sequence[float]) -> np.ndarray:
    """Distance ``(N,)`` of ``points`` from the surface of the oriented box ``(pose xyzw, half extents)``; negative inside
    (by the smaller penetration, max-norm)."""
    pose = np.asarray(pose, dtype=np.float64)
    local = spec.pose_apply(spec.pose_inverse(pose), np.asarray(points, dtype=np.float64))
    q = np.abs(local) - np.asarray(half, dtype=np.float64)[None]
    outside = np.linalg.norm(np.maximum(q, 0.0), axis=1)
    inside = np.minimum(q.max(axis=1), 0.0)
    return outside + inside


def contact_counts(
    points: np.ndarray, radius: float, pads: np.ndarray, halves: Sequence[Sequence[float]], tol: float = 0.001
) -> np.ndarray:
    """Number of surface samples touching each pad box (distance to the box surface at most ``radius + tol``)."""
    out = np.zeros(len(pads), dtype=np.int64)
    for k in range(len(pads)):
        d = box_surface_distance(points, pads[k], halves[k])
        out[k] = int(np.sum(d <= radius + tol))
    return out


def pad_penetration(
    points: np.ndarray, pads: np.ndarray, halves: Sequence[Sequence[float]], margin: float = 0.004, depth: float = 0.04
) -> np.ndarray:
    """``(C, 2)`` per pad box: points inside the box and points behind it (past its back face, on the finger side, within the
    pad footprint widened by ``margin``, no further than ``depth`` behind).  The collider frame's +z is the contact face, so
    "behind" is local ``z < -half_z``.  A soft body pushed through a pad shows up as a growing "behind" count."""
    pts = np.asarray(points, dtype=np.float64)
    out = np.zeros((len(pads), 2), dtype=np.int64)
    for k in range(len(pads)):
        local = spec.pose_apply(spec.pose_inverse(np.asarray(pads[k], dtype=np.float64)), pts)
        hx, hy, hz = (float(v) for v in halves[k])
        foot = (np.abs(local[:, 0]) < hx + margin) & (np.abs(local[:, 1]) < hy + margin)
        out[k, 0] = int(np.sum(foot & (np.abs(local[:, 2]) < hz)))
        out[k, 1] = int(np.sum(foot & (local[:, 2] < -hz) & (local[:, 2] > -hz - depth)))
    return out


def box_overlap(pose_a: np.ndarray, half_a: Sequence[float], pose_b: np.ndarray, half_b: Sequence[float]) -> float:
    """Separating-axis test of two oriented boxes: ``> 0`` is the overlap depth along the least-overlapping axis, ``<= 0`` a
    lower bound of the clearance."""
    Ra = spec.quat_to_mat(np.asarray(pose_a, dtype=np.float64)[3:7])
    Rb = spec.quat_to_mat(np.asarray(pose_b, dtype=np.float64)[3:7])
    ha, hb = np.asarray(half_a, dtype=np.float64), np.asarray(half_b, dtype=np.float64)
    t = np.asarray(pose_b, dtype=np.float64)[:3] - np.asarray(pose_a, dtype=np.float64)[:3]
    axes = [Ra[:, i] for i in range(3)] + [Rb[:, i] for i in range(3)]
    axes += [np.cross(Ra[:, i], Rb[:, j]) for i in range(3) for j in range(3)]
    depth = np.inf
    for L in axes:
        n = float(np.linalg.norm(L))
        if n < 1e-9:
            continue
        L = L / n
        ra = float(np.sum(ha * np.abs(Ra.T @ L)))
        rb = float(np.sum(hb * np.abs(Rb.T @ L)))
        depth = min(depth, ra + rb - abs(float(t @ L)))
    return float(depth)


def cloth_samples(q: np.ndarray, tris: np.ndarray) -> np.ndarray:
    """Surface samples of a cloth: its particles plus the centroids of its triangles."""
    q = np.asarray(q, dtype=np.float64)
    t = np.asarray(tris, dtype=np.int64)
    return np.concatenate([q, q[t].mean(axis=1)], axis=0)


def in_frame_box(
    point: np.ndarray, frame_pose: np.ndarray, half: Sequence[float], center: Sequence[float] = (0.0, 0.0, 0.0)
) -> bool:
    """Is ``point`` inside the box of half extents ``half`` centred at ``center`` of the frame ``frame_pose`` (xyzw)?"""
    local = spec.pose_apply(
        spec.pose_inverse(np.asarray(frame_pose, dtype=np.float64)), np.asarray(point, dtype=np.float64)
    )
    return bool(np.all(np.abs(local - np.asarray(center, dtype=np.float64)) <= np.asarray(half, dtype=np.float64)))


# ----------------------------------------------------------------------------- cloth edges
def edge_arclength(points: np.ndarray) -> np.ndarray:
    """Cumulative arc length ``(n,)`` along an ordered polyline."""
    p = np.asarray(points, dtype=np.float64)
    return np.concatenate([[0.0], np.cumsum(np.linalg.norm(np.diff(p, axis=0), axis=1))])


def project_on_polyline(polyline: np.ndarray, rest_s: np.ndarray, query: np.ndarray) -> Tuple[float, float]:
    """Material coordinate of ``query`` on a deformed polyline: the closest point, expressed in the rest arc length
    ``rest_s`` of the nodes (interpolated), so it names the same cloth point whatever the cloth does.  ``(s, distance)``."""
    p = np.asarray(polyline, dtype=np.float64)
    q = np.asarray(query, dtype=np.float64)
    a, b = p[:-1], p[1:]
    ab = b - a
    t = np.clip(np.sum((q - a) * ab, axis=1) / np.maximum(np.sum(ab * ab, axis=1), 1e-18), 0.0, 1.0)
    c = a + t[:, None] * ab
    d = np.linalg.norm(c - q[None], axis=1)
    i = int(np.argmin(d))
    s = float(rest_s[i] + t[i] * (rest_s[i + 1] - rest_s[i]))
    return s, float(d[i])


def displacement_rms(points: np.ndarray, ref: np.ndarray, mask: Optional[np.ndarray] = None) -> float:
    d = np.asarray(points, dtype=np.float64) - np.asarray(ref, dtype=np.float64)
    if mask is not None:
        d = d[mask]
    return float(np.sqrt(np.mean(np.sum(d * d, axis=1)))) if len(d) else 0.0


# ----------------------------------------------------------------------------- cable
def cable_length(nodes: np.ndarray) -> float:
    return spec.polyline_length(nodes)


def cable_slack(nodes: np.ndarray, end_a: Optional[np.ndarray] = None, end_b: Optional[np.ndarray] = None) -> float:
    """Slack ratio ``path_length / chord - 1`` between the two end points (default: the polyline's own ends)."""
    p = np.asarray(nodes, dtype=np.float64)
    a = p[0] if end_a is None else np.asarray(end_a, dtype=np.float64)
    b = p[-1] if end_b is None else np.asarray(end_b, dtype=np.float64)
    chord = float(np.linalg.norm(b - a))
    return spec.polyline_length(p) / max(chord, 1e-9) - 1.0


def cable_sag(nodes: np.ndarray) -> float:
    """Maximum distance [m] of the cable from the straight chord between its ends."""
    p = np.asarray(nodes, dtype=np.float64)
    a, b = p[0], p[-1]
    ab = b - a
    n2 = float(ab @ ab)
    if n2 < 1e-12:
        return float(np.max(np.linalg.norm(p - a, axis=1)))
    t = np.clip(((p - a) @ ab) / n2, 0.0, 1.0)
    return float(np.max(np.linalg.norm(p - (a + t[:, None] * ab), axis=1)))


def stretch_ratio(nodes: np.ndarray, rest_length: float) -> float:
    """Current arc length over the rest length."""
    return spec.polyline_length(nodes) / max(rest_length, 1e-9)


# ----------------------------------------------------------------------------- channel (shallow slot)
def slot_centerline(
    start_xy: Sequence[float],
    heading_deg: float,
    straight: float,
    turn_deg: float = 0.0,
    turn_radius: float = 0.07,
    straight2: float = 0.0,
    step: float = 0.005,
) -> np.ndarray:
    """Centreline ``(N, 2)`` of a slot: ``straight`` m from ``start_xy`` along ``heading_deg``, then (if ``turn_deg`` is not 0)
    a circular arc of ``turn_deg`` degrees (positive = left) of radius ``turn_radius``, then ``straight2`` m."""
    p = np.asarray(start_xy, dtype=np.float64).copy()
    h = np.radians(heading_deg)
    pts = [p.copy()]

    def go(length):
        nonlocal p
        n = max(int(np.ceil(length / step)), 1)
        for _ in range(n):
            p = p + (length / n) * np.array([np.cos(h), np.sin(h)])
            pts.append(p.copy())

    go(straight)
    if abs(turn_deg) > 1e-9:
        sgn = 1.0 if turn_deg > 0 else -1.0
        arc = np.radians(abs(turn_deg))
        n = max(int(np.ceil(arc * turn_radius / step)), 2)
        for _ in range(n):
            dh = sgn * arc / n
            ds = turn_radius * arc / n
            h_mid = h + 0.5 * dh
            p = p + ds * np.array([np.cos(h_mid), np.sin(h_mid)])
            h += dh
            pts.append(p.copy())
    if straight2 > 0:
        go(straight2)
    return np.asarray(pts)


def rail_boxes(
    centerline: np.ndarray,
    slot_width: float,
    rail_width: float,
    rail_height: float,
    z_floor: float,
    segment_len: float = 0.02,
) -> list:
    """Static boxes ``{pos, half, quat (xyzw)}`` forming the two rails of a slot along ``centerline`` (one rail piece every
    ``segment_len`` of centreline, yawed to the local heading, slightly overlapped so curves have no gaps)."""
    c = np.asarray(centerline, dtype=np.float64)
    seg = np.linalg.norm(np.diff(c, axis=0), axis=1)
    s = np.concatenate([[0.0], np.cumsum(seg)])
    n = max(int(np.ceil(s[-1] / segment_len)), 1)
    edges = np.linspace(0.0, s[-1], n + 1)
    out = []
    off = 0.5 * slot_width + 0.5 * rail_width
    for i in range(n):
        a = np.array([np.interp(edges[i], s, c[:, k]) for k in range(2)])
        b = np.array([np.interp(edges[i + 1], s, c[:, k]) for k in range(2)])
        d = b - a
        L = float(np.linalg.norm(d))
        u = d / max(L, 1e-9)
        nrm = np.array([-u[1], u[0]])
        yaw = float(np.arctan2(u[1], u[0]))
        q = spec.quat_from_yaw(yaw)
        mid = 0.5 * (a + b)
        for side in (-1.0, 1.0):
            p = mid + side * off * nrm
            out.append(
                {
                    "pos": [float(p[0]), float(p[1]), float(z_floor + 0.5 * rail_height)],
                    "half": [0.5 * L + 0.003, 0.5 * rail_width, 0.5 * rail_height],
                    "quat": [float(v) for v in q],
                }
            )
    return out


def polyline_distance(points_xy: np.ndarray, polyline_xy: np.ndarray) -> Tuple[np.ndarray, np.ndarray]:
    """Distance ``(N,)`` of each point to a polyline and the signed lateral side (+ left of the travel direction)."""
    P = np.asarray(points_xy, dtype=np.float64)
    c = np.asarray(polyline_xy, dtype=np.float64)
    a, b = c[:-1], c[1:]
    ab = b - a
    ab2 = np.maximum(np.sum(ab * ab, axis=1), 1e-18)
    t = np.clip(np.sum((P[:, None, :] - a[None]) * ab[None], axis=2) / ab2[None], 0.0, 1.0)
    proj = a[None] + t[..., None] * ab[None]
    d = np.linalg.norm(P[:, None, :] - proj, axis=2)
    j = np.argmin(d, axis=1)
    dist = d[np.arange(len(P)), j]
    cross = ab[j, 0] * (P[:, 1] - a[j, 1]) - ab[j, 1] * (P[:, 0] - a[j, 0])
    return dist, np.sign(cross)


def routed_prefix_length(
    nodes: np.ndarray,
    centerline_xy: np.ndarray,
    slot_width: float,
    radius: float,
    z_floor: float,
    z_tol: float = 0.002,
    lat_tol: float = 0.001,
) -> Tuple[float, np.ndarray]:
    """Length [m] of the longest prefix (from node 0) of the cable lying in the slot, and the per-node in-slot mask: a node is
    in the slot when its lateral distance to the centreline is at most ``slot_width / 2 - radius + lat_tol`` and it rests on
    the floor (centre height at most ``z_floor + radius + z_tol``)."""
    p = np.asarray(nodes, dtype=np.float64)
    d, _ = polyline_distance(p[:, :2], centerline_xy)
    ok = (d <= 0.5 * slot_width - radius + lat_tol) & (p[:, 2] <= z_floor + radius + z_tol)
    bad = np.nonzero(~ok)[0]
    k = int(bad[0]) if len(bad) else len(p)
    if k <= 1:
        return 0.0, ok
    return float(np.linalg.norm(np.diff(p[:k], axis=0), axis=1).sum()), ok


# ----------------------------------------------------------------------------- fold
def fold_partners(nx: int, ny: int, attach_columns: int = 2, flap: str = "far") -> Dict[str, np.ndarray]:
    """Index sets of the half fold of an ``(nx + 1) x (ny + 1)`` grid cloth (row-major in x).  ``flap="far"``: ``top`` = the
    particles right of the fold line (columns ``nx // 2 + 1 ..``), ``strip`` = the far ``attach_columns`` columns, ``corners`` =
    the two far corners.  ``flap="near"``: the flap is the left half (columns ``0 .. nx // 2 - 1``), ``strip`` = the first
    ``attach_columns`` columns, ``corners`` = the corners at ``ix = 0``.  ``partner`` = the particle each lands on
    (``(ix, iy) -> (nx - ix, iy)``)."""
    idx = np.arange((nx + 1) * (ny + 1)).reshape(ny + 1, nx + 1)
    half = nx // 2
    near = str(flap) == "near"
    ix = np.arange(0, half) if near else np.arange(half + 1, nx + 1)
    top = np.array([idx[iy, i] for iy in range(ny + 1) for i in ix])
    partner = np.array([idx[iy, nx - i] for iy in range(ny + 1) for i in ix])
    return {
        "top": top,
        "partner": partner,
        "strip": idx[:, : int(attach_columns)].reshape(-1)
        if near
        else idx[:, nx - int(attach_columns) + 1 :].reshape(-1),
        "corners": np.array([idx[0, 0], idx[ny, 0]]) if near else np.array([idx[0, nx], idx[ny, nx]]),
    }


def fold_errors(q: np.ndarray, sets: Dict[str, np.ndarray]) -> Dict[str, float]:
    """``edge``: mean xy distance of the carried strip to its partners; ``skew``: max ``|dy|`` of the lifted half to its
    partners; ``over``: mean height of the lifted half above its partners."""
    q = np.asarray(q, dtype=np.float64)
    top, par = q[sets["top"]], q[sets["partner"]]
    edge = np.isin(sets["top"], sets["strip"])
    return {
        "edge": float(np.linalg.norm(top[edge][:, :2] - par[edge][:, :2], axis=1).mean()),
        "skew": float(np.abs(top[:, 1] - par[:, 1]).max()),
        "over": float((top[:, 2] - par[:, 2]).mean()),
    }
