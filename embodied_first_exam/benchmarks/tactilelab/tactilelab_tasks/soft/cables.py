"""Geometry, nominal scenes, metrics and success predicates of the three cable tasks (pure numpy).

The cable is a chain of ``newton.Rod`` segments simulated in the sidecar (``softbody.world``); the Isaac side only sees
its centreline ``cable_nodes`` ``(S + 1, 3)`` and the segment poses.  Everything here works on those arrays and on the
``(C, 7)`` collider poses of the gripper, so the same code runs in the task modules, in the sidecar-only tests and in the
policies.  Frames: env-local metres, quaternions **xyzw** (the soft-body convention of :mod:`tactilelab_tasks.softbody_geom.spec`).

Contents
    metrics        box / polyline helpers, cable slack / sag / stretch, slot centreline and rails, routed prefix length
    pinch pads     the two gel pad boxes of a top-down pinch, the finger clearance boxes, pad vs fixture overlap
    hand           cuRobo collision spheres of the hand links: how far the hand reaches past the pinch centre
    needle         ``cable_needle_thread``: wall with a hole, two cable clips, the straight cable, crossing metrics
    slack          ``cable_slack_reduce``: clamp, notched ridge, the bump-shaped cable, slack / slip / stretch metrics
    route          ``cable_route_channel``: slot rails, cable clips, far post, initial cable, adaptive picks, routed length
"""

from __future__ import annotations

import os
from typing import Any, Dict, List, Optional, Sequence, Tuple

import numpy as np

from ..softbody_geom import spec
from ..softbody_geom.soft_scenes import TABLE_Z, gsmini_colliders, task_world

# =====================================================================================================================
# metrics
# =====================================================================================================================


def box_surface_distance(points: np.ndarray, pose: np.ndarray, half: Sequence[float]) -> np.ndarray:
    """Distance ``(N,)`` of ``points`` from the surface of an oriented box (``pose`` xyzw, half extents ``half``); negative
    inside (the smaller penetration, max-norm)."""
    inv = spec.pose_inverse(np.asarray(pose, dtype=np.float64))
    local = spec.pose_apply(inv, np.asarray(points, dtype=np.float64))
    q = np.abs(local) - np.asarray(half, dtype=np.float64)[None]
    outside = np.linalg.norm(np.maximum(q, 0.0), axis=1)
    inside = np.minimum(q.max(axis=1), 0.0)
    return outside + inside


def contact_counts(
    points: np.ndarray, radius: float, pads: np.ndarray, halves: Sequence[Sequence[float]], tol: float = 0.001
) -> np.ndarray:
    """Number of sample points touching each pad box (distance to the box surface at most ``radius + tol``)."""
    out = np.zeros(len(pads), dtype=np.int64)
    for k in range(len(pads)):
        out[k] = int(np.sum(box_surface_distance(points, pads[k], halves[k]) <= radius + tol))
    return out


def pad_penetration(
    points: np.ndarray, pads: np.ndarray, halves: Sequence[Sequence[float]], margin: float = 0.004, depth: float = 0.04
) -> np.ndarray:
    """``(C, 2)`` per pad box: points inside the box and points behind it (past its back face, within the footprint widened
    by ``margin``, at most ``depth`` behind).  The collider frame's +z is the contact face.  A soft body pushed through a pad
    shows up as a growing "behind" count."""
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
    """Separating-axis test of two oriented boxes (poses xyzw): > 0 is the overlap depth along the least-overlapping axis,
    <= 0 a lower bound of the clearance."""
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


def edge_arclength(points: np.ndarray) -> np.ndarray:
    """Cumulative arc length ``(n,)`` along an ordered polyline."""
    p = np.asarray(points, dtype=np.float64)
    return np.concatenate([[0.0], np.cumsum(np.linalg.norm(np.diff(p, axis=0), axis=1))])


def project_on_polyline(polyline: np.ndarray, rest_s: np.ndarray, query: np.ndarray) -> Tuple[float, float]:
    """Material coordinate of ``query`` on a deformed polyline: the closest point, expressed in the rest arc length
    ``rest_s`` of the nodes (interpolated).  Returns ``(s, distance)``."""
    p = np.asarray(polyline, dtype=np.float64)
    q = np.asarray(query, dtype=np.float64)
    a, b = p[:-1], p[1:]
    ab = b - a
    t = np.clip(np.sum((q - a) * ab, axis=1) / np.maximum(np.sum(ab * ab, axis=1), 1e-18), 0.0, 1.0)
    c = a + t[:, None] * ab
    d = np.linalg.norm(c - q[None], axis=1)
    i = int(np.argmin(d))
    return float(rest_s[i] + t[i] * (rest_s[i + 1] - rest_s[i])), float(d[i])


def cable_length(nodes: np.ndarray) -> float:
    return spec.polyline_length(nodes)


def cable_slack(nodes: np.ndarray, end_a: Optional[np.ndarray] = None, end_b: Optional[np.ndarray] = None) -> float:
    """Slack ratio ``path_length / chord - 1`` between two end points (default: the polyline's own ends)."""
    p = np.asarray(nodes, dtype=np.float64)
    a = p[0] if end_a is None else np.asarray(end_a, dtype=np.float64)
    b = p[-1] if end_b is None else np.asarray(end_b, dtype=np.float64)
    return spec.polyline_length(p) / max(float(np.linalg.norm(b - a)), 1e-9) - 1.0


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


def cable_point_at(nodes: np.ndarray, s: float, look: float = 0.015) -> Tuple[np.ndarray, np.ndarray]:
    """Cable point at arc length ``s`` from node 0 and the horizontal unit tangent there (towards the free end)."""
    nodes = np.asarray(nodes, dtype=np.float64)
    sa = edge_arclength(nodes)
    p = np.array([np.interp(s, sa, nodes[:, k]) for k in range(3)])
    q = np.array([np.interp(min(s + look, sa[-1]), sa, nodes[:, k]) for k in range(3)])
    t = q - p
    t[2] = 0.0
    return p, t / max(np.linalg.norm(t), 1e-9)


def point_before_end(nodes: np.ndarray, back: float, look: float = 0.02) -> Tuple[np.ndarray, np.ndarray]:
    """A point ``back`` metres of cable before the free end (the last node) and the horizontal cable direction there,
    pointing towards the free end."""
    nodes = np.asarray(nodes, dtype=np.float64)
    s = edge_arclength(nodes)
    t = max(s[-1] - back, 0.0)
    p = np.array([np.interp(t, s, nodes[:, k]) for k in range(3)])
    q = np.array([np.interp(min(t + look, s[-1]), s, nodes[:, k]) for k in range(3)])
    d = q - p
    d[2] = 0.0
    return p, d / max(np.linalg.norm(d), 1e-9)


def point_before_tip(nodes: np.ndarray, back: float) -> np.ndarray:
    """Point of the cable ``back`` metres before its tip (the last node), measured along the current polyline."""
    nodes = np.asarray(nodes, dtype=np.float64)[::-1]
    seg = np.linalg.norm(np.diff(nodes, axis=0), axis=1)
    acc = np.concatenate([[0.0], np.cumsum(seg)])
    s = min(float(back), float(acc[-1]))
    i = int(np.clip(np.searchsorted(acc, s) - 1, 0, len(seg) - 1))
    f = (s - acc[i]) / max(seg[i], 1e-9)
    return nodes[i] + f * (nodes[i + 1] - nodes[i])


def cable_samples(nodes: np.ndarray) -> np.ndarray:
    """Surface sample points of a cable for the contact counts: the nodes and the segment midpoints."""
    n = np.asarray(nodes, dtype=np.float64)
    return np.concatenate([n, 0.5 * (n[1:] + n[:-1])], axis=0)


def bump_arc(a: np.ndarray, b: np.ndarray, length: float, n_seg: int, side: float = 1.0) -> np.ndarray:
    """A cable of arc length ``length`` from ``a`` to ``b`` bulging sideways as a smooth bump with zero end slope
    (``A (1 - cos 2 pi t) / 2``), so it joins a straight head and a straight tail without a kink.  ``(n_seg + 1, 3)``,
    equally spaced in arc length."""
    a, b = np.asarray(a, dtype=np.float64), np.asarray(b, dtype=np.float64)
    cv = b - a
    chord = float(np.linalg.norm(cv[:2]))
    u = cv[:2] / chord
    nrm = np.array([-u[1], u[0]])
    t = np.linspace(0.0, 1.0, 800)

    def pts_for(amp: float) -> np.ndarray:
        off = float(side) * amp * 0.5 * (1.0 - np.cos(2.0 * np.pi * t))
        return np.column_stack([a[None, :2] + t[:, None] * cv[None, :2] + off[:, None] * nrm[None], a[2] + t * cv[2]])

    lo, hi = 0.0, 1.5 * chord
    for _ in range(50):
        mid = 0.5 * (lo + hi)
        lo, hi = (mid, hi) if spec.polyline_length(pts_for(mid)) < length else (lo, mid)
    return spec.resample_polyline(pts_for(0.5 * (lo + hi)), n_seg)


# -- slot -------------------------------------------------------------------------------------------------------------


def slot_centerline(
    start_xy: Sequence[float],
    heading_deg: float,
    straight: float,
    turn_deg: float = 0.0,
    turn_radius: float = 0.07,
    straight2: float = 0.0,
    step: float = 0.005,
) -> np.ndarray:
    """Centreline ``(N, 2)`` of a slot: ``straight`` m from ``start_xy`` along ``heading_deg``, then (``turn_deg`` != 0) a
    circular arc (positive = left) of ``turn_radius``, then ``straight2`` m.  Points ``step`` apart."""
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
    """Static boxes (``pos``, ``half``, ``quat`` xyzw) forming the two rails of a slot: a rail piece every ``segment_len``
    of centreline, yawed to the local heading, overlapped a little so curves have no gaps."""
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
        q = spec.quat_from_yaw(float(np.arctan2(u[1], u[0])))
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
    """Distance ``(N,)`` of each point to a polyline and the signed side (+ left of the travel direction)."""
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
    """Length [m] of the longest prefix (from node 0) of the cable lying in the slot and the per-node in-slot mask: a node is
    in the slot when its lateral distance to the centreline is at most ``slot_width / 2 - radius + lat_tol`` and it rests on
    the slot floor (centre height at most ``z_floor + radius + z_tol``)."""
    p = np.asarray(nodes, dtype=np.float64)
    d, _ = polyline_distance(p[:, :2], centerline_xy)
    ok = (d <= 0.5 * slot_width - radius + lat_tol) & (p[:, 2] <= z_floor + radius + z_tol)
    bad = np.nonzero(~ok)[0]
    k = int(bad[0]) if len(bad) else len(p)
    if k <= 1:
        return 0.0, ok
    return float(np.linalg.norm(np.diff(p[:k], axis=0), axis=1).sum()), ok


# =====================================================================================================================
# pinch pads, finger clearance boxes, fixture overlap
# =====================================================================================================================

#: gel pad collider half extents (``soft_scenes.GSMINI_COLLIDERS``): x = the 21 mm side = the finger length (vertical in a
#: top-down pinch), y = the 16 mm side = the finger width (along the cable), z = half the 4 mm pad thickness (+z = contact face)
PAD_HALVES = ((0.0105, 0.008, 0.002), (0.0105, 0.008, 0.002))
#: pad 0 of a top-down pinch with the cable heading +x: the gel face looks +y, the finger length points down (xyzw)
Q_PAD0 = np.array([-0.5, 0.5, 0.5, 0.5])
# the finger body around the gel pad (clearance model): it reaches FINGER_TIP_BELOW below the pad centre along the finger
# length, FINGER_ABOVE above it, lies FINGER_FACE_RECESS .. + FINGER_THICKNESS behind the gel face, FINGER_HALF_WIDTH wide
FINGER_TIP_BELOW = 0.019
FINGER_ABOVE = 0.030
FINGER_FACE_RECESS = 0.004
FINGER_THICKNESS = 0.028
FINGER_HALF_WIDTH = 0.018


def pinch_pads(mid: Sequence[float], theta: float, face_gap: float, pad_half_z: float = 0.002) -> np.ndarray:
    """``(2, 7)`` xyzw poses of the two gel pad boxes of a top-down pinch centred at ``mid`` with the cable heading ``theta``
    (rad about z) and the gel faces ``face_gap`` apart (box centres ``2 pad_half_z`` further apart)."""
    c, sn = np.cos(theta), np.sin(theta)
    Rz = np.array([[c, -sn, 0.0], [sn, c, 0.0], [0.0, 0.0, 1.0]])
    R0 = Rz @ spec.quat_to_mat(Q_PAD0)
    R1 = R0 @ np.diag([1.0, -1.0, -1.0])
    n = R0[:, 2]
    d = 0.5 * (float(face_gap) + 2.0 * float(pad_half_z))
    m = np.asarray(mid, dtype=np.float64)
    return np.array(
        [np.concatenate([m - d * n, spec.mat_to_quat(R0)]), np.concatenate([m + d * n, spec.mat_to_quat(R1)])]
    )


def pads_from_frame(mid: Sequence[float], R_mid: np.ndarray, face_gap: float, pad_half_z: float = 0.002) -> np.ndarray:
    """``(2, 7)`` xyzw pad poses of a pinch frame ``(mid, R_mid)`` whose +z is the closing axis (pad 0 towards pad 1) and
    whose x / y are those of pad 0; pad 1 is pad 0 turned by pi about x."""
    R0 = np.asarray(R_mid, dtype=np.float64)
    R1 = R0 @ np.diag([1.0, -1.0, -1.0])
    n = R0[:, 2]
    d = 0.5 * (float(face_gap) + 2.0 * float(pad_half_z))
    m = np.asarray(mid, dtype=np.float64)
    return np.array(
        [np.concatenate([m - d * n, spec.mat_to_quat(R0)]), np.concatenate([m + d * n, spec.mat_to_quat(R1)])]
    )


def gel_link_poses_from_pads(pads: np.ndarray, pad_offset_z: float = 0.002) -> Dict[str, np.ndarray]:
    """The gel link poses (``gsmini_left`` = pad 0, ``gsmini_right`` = pad 1) behind the two pad boxes: the pad box sits
    ``pad_offset_z`` along the link's +z.  Used to mirror the whole gripper (pads, cases, fingers) from two pad poses."""
    out = {}
    for name, k in (("gsmini_left", 0), ("gsmini_right", 1)):
        p = np.asarray(pads[k], dtype=np.float64)
        out[name] = np.concatenate(
            [p[:3] - spec.quat_rotate(p[3:7], np.array([0.0, 0.0, float(pad_offset_z)])), p[3:7]]
        )
    return out


def finger_boxes(pads: np.ndarray, pad_half_z: float = 0.002) -> List[Tuple[np.ndarray, np.ndarray]]:
    """Clearance boxes ``(pose7 xyzw, half)`` of the two finger bodies from the two gel pad poses."""
    out = []
    for k in range(min(2, len(pads))):
        pose = np.asarray(pads[k], dtype=np.float64)
        R = spec.quat_to_mat(pose[3:7])
        s_down = -1.0 if float(R[2, 0]) > 0.0 else 1.0
        c_local = np.array(
            [
                s_down * 0.5 * (FINGER_TIP_BELOW - FINGER_ABOVE),
                0.0,
                float(pad_half_z) - FINGER_FACE_RECESS - 0.5 * FINGER_THICKNESS,
            ]
        )
        half = np.array([0.5 * (FINGER_TIP_BELOW + FINGER_ABOVE), FINGER_HALF_WIDTH, 0.5 * FINGER_THICKNESS])
        out.append((np.concatenate([pose[:3] + R @ c_local, pose[3:7]]), half))
    return out


def fixture_overlap(
    pads: np.ndarray, pad_halves: Sequence[Sequence[float]], boxes: Sequence[Tuple[str, np.ndarray, np.ndarray]]
) -> Dict[str, Any]:
    """Deepest overlap (m, > 0 = intersecting) of the two gel pad boxes and of the finger clearance boxes with the fixture
    ``boxes`` ``(name, pose7 xyzw, half)``: ``{"pad", "finger", "pad_name", "finger_name"}``."""
    out: Dict[str, Any] = {"pad": float("-inf"), "finger": float("-inf"), "pad_name": "", "finger_name": ""}
    fingers = finger_boxes(pads, float(pad_halves[0][2]) if len(pad_halves) else 0.002)
    mid = np.asarray(pads[:2], dtype=np.float64)[:, :3].mean(axis=0)
    r_hand = 0.08
    boxes = [
        b
        for b in boxes
        if float(np.linalg.norm(np.asarray(b[1][:3], dtype=np.float64) - mid))
        <= r_hand + float(np.linalg.norm(np.asarray(b[2], dtype=np.float64)))
    ]
    for name, fpose, fhalf in boxes:
        for k in range(min(2, len(pads))):
            d = box_overlap(np.asarray(pads[k], dtype=np.float64), pad_halves[k], fpose, fhalf)
            if d > out["pad"]:
                out["pad"], out["pad_name"] = float(d), name
        for fpose_k, fhalf_k in fingers:
            d = box_overlap(fpose_k, fhalf_k, fpose, fhalf)
            if d > out["finger"]:
                out["finger"], out["finger_name"] = float(d), name
    return out


def statics_as_boxes(statics: Sequence[Dict[str, Any]]) -> List[Tuple[str, np.ndarray, np.ndarray]]:
    """``(name, pose7 xyzw, half)`` of every static box of a world config (for the clearance checks)."""
    return [
        (
            str(s.get("name", f"static{i}")),
            np.concatenate(
                [
                    np.asarray(s["pos"], dtype=np.float64),
                    np.asarray(s.get("quat", [0.0, 0.0, 0.0, 1.0]), dtype=np.float64),
                ]
            ),
            np.asarray(s["half"], dtype=np.float64),
        )
        for i, s in enumerate(statics)
    ]


# =====================================================================================================================
# hand clearance (cuRobo collision spheres)
# =====================================================================================================================

HAND_LINKS = ("J1_6", "J1_7", "J1_8")
#: bounding box (min, max) of the wrist camera housing in the ``J1_6`` frame: its surface joins the ``J1_6`` spheres as
#: zero-radius points so the hand's front extent covers the housing too
WRIST_HOUSING_BOX = ((-0.021, -0.0934, 0.0096), (0.0211, -0.0339, 0.0683))


def default_hand_spheres_yml() -> str:
    """The shipped cuRobo description of the robot (``assets/robots/xtrainer_gsmini/curobo/xtrainer_gsmini.yml``)."""
    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    return os.path.join(root, "assets", "robots", "xtrainer_gsmini", "curobo", "xtrainer_gsmini.yml")


def load_hand_spheres(
    yml_path: Optional[str] = None,
    links: Sequence[str] = HAND_LINKS,
    housing: Optional[Sequence[Sequence[float]]] = WRIST_HOUSING_BOX,
    grid: int = 5,
) -> Dict[str, np.ndarray]:
    """Collision spheres ``{link: (S, 4) [cx cy cz r]}`` (link frames) of the hand links from a cuRobo yml, plus the
    surface points of the wrist housing box on the first link."""
    import yaml

    with open(yml_path or default_hand_spheres_yml()) as f:
        cfg = yaml.safe_load(f)
    table = cfg["robot_cfg"]["kinematics"]["collision_spheres"]
    out: Dict[str, np.ndarray] = {}
    for link in links:
        rows = table.get(link) or []
        out[link] = np.array([[*s["center"], s["radius"]] for s in rows], dtype=np.float64).reshape(-1, 4)
    if housing is not None:
        lo, hi = np.asarray(housing[0], dtype=np.float64), np.asarray(housing[1], dtype=np.float64)
        g = np.linspace(0.0, 1.0, max(2, int(grid)))
        pts = np.array([lo + (hi - lo) * np.array([a, b, c]) for a in g for b in g for c in g])
        pts = pts[np.any(np.isclose(pts, lo) | np.isclose(pts, hi), axis=1)]
        link = links[0]
        out[link] = np.concatenate([out.get(link, np.zeros((0, 4))), np.hstack([pts, np.zeros((len(pts), 1))])])
    return out


def spheres_world(spheres: Dict[str, np.ndarray], link_poses: Dict[str, np.ndarray]) -> np.ndarray:
    """``(N, 4)`` spheres in the frame of ``link_poses`` (xyzw per link)."""
    rows = []
    for link, S in spheres.items():
        if link not in link_poses or not len(S):
            continue
        p = np.asarray(link_poses[link], dtype=np.float64)
        R = spec.quat_to_mat(p[3:7])
        rows.append(np.concatenate([S[:, :3] @ R.T + p[:3], S[:, 3:4]], axis=1))
    return np.concatenate(rows) if rows else np.zeros((0, 4))


def front_extent(
    spheres: Dict[str, np.ndarray],
    link_poses: Dict[str, np.ndarray],
    origin: Sequence[float],
    direction: Sequence[float],
    z_max: float = np.inf,
) -> float:
    """How far the hand reaches past ``origin`` along the unit ``direction`` (only spheres whose bottom is below ``z_max``)."""
    W = spheres_world(spheres, link_poses)
    u = np.asarray(direction, dtype=np.float64)
    u = u / np.linalg.norm(u)
    keep = W[:, 2] - W[:, 3] < z_max
    if not keep.any():
        return float("-inf")
    W = W[keep]
    return float(((W[:, :3] - np.asarray(origin, dtype=np.float64)) @ u + W[:, 3]).max())


def link_poses_at(
    link_poses: Dict[str, np.ndarray], mid0: np.ndarray, R0: np.ndarray, mid1: Sequence[float], R1: np.ndarray
) -> Dict[str, np.ndarray]:
    """``link_poses`` (xyzw) moved rigidly with the pinch frame from ``(mid0, R0)`` to ``(mid1, R1)``."""
    D = np.asarray(R1, dtype=np.float64) @ np.asarray(R0, dtype=np.float64).T
    out = {}
    for link, p in link_poses.items():
        p = np.asarray(p, dtype=np.float64)
        out[link] = np.concatenate(
            [
                np.asarray(mid1, dtype=np.float64) + D @ (p[:3] - np.asarray(mid0, dtype=np.float64)),
                spec.mat_to_quat(D @ spec.quat_to_mat(p[3:7])),
            ]
        )
    return out


def housing_faces_fixture(
    spheres: Dict[str, np.ndarray],
    link_poses: Dict[str, np.ndarray],
    mid: np.ndarray,
    boxes: Sequence[Dict[str, Any]],
    link: str = HAND_LINKS[0],
) -> bool:
    """True when the bulk of the wrist (the centroid of ``link``'s spheres) lies on the side of the nearest fixture box
    (``{"center", "half"}``), seen from the pinch centre: the wrist should then be turned by pi."""
    if not boxes:
        return False
    W = spheres_world({link: spheres[link]}, {link: link_poses[link]})
    h = W[:, :3].mean(axis=0) - np.asarray(mid, dtype=np.float64)
    best, d = np.inf, None
    for b in boxes:
        lo, hi = np.asarray(b["center"]) - np.asarray(b["half"]), np.asarray(b["center"]) + np.asarray(b["half"])
        q = np.clip(mid, lo, hi)
        if np.linalg.norm(q - mid) < best:
            best, d = float(np.linalg.norm(q - mid)), q - mid
    h[2] = d[2] = 0.0
    return bool(float(h @ d) > 0.0)


# =====================================================================================================================
# the cable world
# =====================================================================================================================


def world_block(
    table_z: float, statics: Sequence[Dict[str, Any]], cable: Dict[str, Any], table_mu: Optional[float] = None
) -> Dict[str, Any]:
    """The task-specific part of a cable world config: ``table``, ``statics`` and the ``cable`` block (the solver settings
    and the collider list are appended by :func:`cable_world` or by :meth:`tactilelab_tasks.soft.base.SoftTask.world_cfg`)."""
    table: Dict[str, Any] = {"z": float(table_z), "half": [1.0, 1.0], "center": [0.0, 0.0]}
    if table_mu is not None:
        table["mu"] = float(table_mu)
    return {"table": table, "statics": [dict(s) for s in statics], "cable": dict(cable)}


def cable_world(
    table_z: float,
    statics: Sequence[Dict[str, Any]],
    cable: Dict[str, Any],
    table_mu: Optional[float] = None,
    colliders: Optional[Sequence[spec.ColliderSpec]] = None,
    substeps: int = 10,
    iterations: int = 5,
) -> Dict[str, Any]:
    """The complete sidecar world config of a cable task: :func:`world_block` + the six gripper colliders (default:
    ``soft_scenes.gsmini_colliders``), 60 Hz, ``substeps`` x ``iterations``."""
    world = world_block(table_z, statics, cable, table_mu)
    return task_world(
        world,
        list(colliders) if colliders is not None else gsmini_colliders(),
        substeps=substeps,
        iterations=iterations,
        table_z=table_z,
    )


def closed_face_gap(radius: float, pinch_overlap: float) -> float:
    """Gel face gap of the calibrated close: the cable diameter minus two pinch overlaps."""
    return max(2.0 * float(radius) - 2.0 * float(pinch_overlap), 0.0)


# =====================================================================================================================
# cable_needle_thread
# =====================================================================================================================

NEEDLE: Dict[str, Any] = {
    "n_seg": 21,
    "length": 0.21,
    "radius": 0.0035,
    "tip_len": 0.1025,  # cable ahead of the grasp point (the pads hold the cable here)
    "home_mid": [-0.154, -0.117, 1.338],  # pad midpoint of the home pose (used when no robot state exists yet)
    "wall_dx": 0.15,  # wall plane ahead of the pad midpoint along x
    "wall_thickness": 0.012,
    "wall_half": [0.20, 0.20],  # half width (y) and height above the hole centre (z)
    "hole": [0.031, 0.031],  # w (y) x h (z)
    "hole_dy": 0.0,  # hole centre relative to the pad midpoint
    "hole_dz": -0.0325,
    "wall_mu": 0.4,
    "pass_len": 0.035,
    "stretch_max": 1.05,
    "success_hold": 20,
    # the stand: two open-top U clips on posts at these fractions of the cable length from the tail; the cable rests
    # ``drop`` below the pad midpoint
    "stand": {
        "clips": [0.25, 0.75],
        "slot": 0.014,
        "wall": 0.006,
        "depth": 0.012,
        "lip": 0.004,
        "drop": 0.13,
        "mu": 0.5,
    },
    "cable": {
        "radius": 0.0035,
        "density": 922.5,
        "stretch_stiffness": 2.0e4,
        "stretch_damping": 0.1,
        "bend_stiffness": 0.22,
        "bend_damping": 1.0e-3,
        "mu": 0.65,
        "color": [0.15, 0.55, 0.85],
    },
    "pinch_overlap": 0.00075,
    "settle_ticks": 30,
}


class NeedleScene:
    """The ``cable_needle_thread`` scene for a pad midpoint ``mid`` at the reset: wall, hole, stand clips and the straight
    cable lying in the clips."""

    def __init__(self, g: Dict[str, Any], table_z: float = TABLE_Z, mid: Optional[Sequence[float]] = None):
        self.g = spec.merge_dicts(NEEDLE, g)
        self.table_z = float(table_z)
        self.mid = np.asarray(mid if mid is not None else self.g["home_mid"], dtype=np.float64)
        self.n_seg = int(self.g["n_seg"])
        self.rest_len = float(self.g["length"])
        self.radius = float(self.g["radius"])
        self.wall = {
            "x": float(self.mid[0] + float(self.g["wall_dx"])),
            "y": float(self.mid[1] + float(self.g["hole_dy"])),
            "z": float(self.mid[2] + float(self.g["hole_dz"])),
            "thickness": float(self.g["wall_thickness"]),
            "hole": [float(v) for v in self.g["hole"]],
        }
        tip = float(self.g["tip_len"])
        tail = self.rest_len - tip
        x = np.linspace(self.mid[0] - tail, self.mid[0] + tip, self.n_seg + 1)
        st = self.g["stand"]
        zc = float(self.mid[2]) - float(st["drop"])
        self.clips = [(float(x[0]) + float(c) * self.rest_len, float(self.mid[1]), zc) for c in st["clips"]]
        self._cable0 = np.stack([x, np.full_like(x, self.mid[1]), np.full_like(x, zc)], axis=1)

    # -- geometry
    @property
    def hole_center(self) -> np.ndarray:
        return np.array([self.wall["x"], self.wall["y"], self.wall["z"]])

    @property
    def wall_near_x(self) -> float:
        return float(self.wall["x"] - 0.5 * self.wall["thickness"])

    @property
    def wall_top_z(self) -> float:
        return float(self.wall["z"] + float(self.g["wall_half"][1]))

    def hole_size(self) -> Tuple[float, float]:
        return float(self.wall["hole"][0]), float(self.wall["hole"][1])

    def wall_boxes(self) -> List[Dict[str, Any]]:
        """Four static slabs around the hole (``name``, ``pos``, ``half``)."""
        w_ = self.wall
        t = 0.5 * w_["thickness"]
        hw, hh = (float(v) for v in self.g["wall_half"])
        w, h = (0.5 * v for v in w_["hole"])
        x, y, z = w_["x"], w_["y"], w_["z"]
        z_lo, z_hi = self.table_z, z + hh
        return [
            {"name": "wall_bottom", "pos": [x, y, 0.5 * (z_lo + z - h)], "half": [t, hw, 0.5 * (z - h - z_lo)]},
            {"name": "wall_top", "pos": [x, y, 0.5 * (z + h + z_hi)], "half": [t, hw, 0.5 * (z_hi - z - h)]},
            {"name": "wall_left", "pos": [x, y - 0.5 * (hw + w), z], "half": [t, 0.5 * (hw - w), h]},
            {"name": "wall_right", "pos": [x, y + 0.5 * (hw + w), z], "half": [t, 0.5 * (hw - w), h]},
        ]

    def stand_boxes(self) -> List[Dict[str, Any]]:
        """Per clip a post from the table up to the cable bottom and two side walls."""
        p = self.g["stand"]
        r = self.radius
        slot, wall, depth, lip = (float(p[k]) for k in ("slot", "wall", "depth", "lip"))
        out = []
        for i, (x, y, zc) in enumerate(self.clips):
            z_bot = zc - r
            out.append(
                {
                    "name": f"clip{i}_post",
                    "pos": [x, y, 0.5 * (self.table_z + z_bot)],
                    "half": [0.5 * depth, 0.5 * slot + wall, 0.5 * (z_bot - self.table_z)],
                }
            )
            z_top = zc + r + lip
            for k, sgn in (("a", -1.0), ("b", 1.0)):
                out.append(
                    {
                        "name": f"clip{i}_wall_{k}",
                        "pos": [x, y + sgn * (0.5 * slot + 0.5 * wall), 0.5 * (z_bot + z_top)],
                        "half": [0.5 * depth, 0.5 * wall, 0.5 * (z_top - z_bot)],
                    }
                )
        return out

    def statics(self) -> List[Dict[str, Any]]:
        return [{**b, "mu": float(self.g["wall_mu"])} for b in self.wall_boxes()] + [
            {**b, "mu": float(self.g["stand"]["mu"])} for b in self.stand_boxes()
        ]

    def fixtures(self) -> List[Dict[str, Any]]:
        """The same boxes for the Isaac stage (``name`` / ``center`` / ``half`` / ``color``)."""
        out = [
            {"name": b["name"], "center": b["pos"], "half": b["half"], "color": [0.62, 0.62, 0.68]}
            for b in self.wall_boxes()
        ]
        out += [
            {"name": b["name"], "center": b["pos"], "half": b["half"], "color": [0.35, 0.35, 0.38]}
            for b in self.stand_boxes()
        ]
        return out

    def initial_cable(self) -> np.ndarray:
        """``(n_seg + 1, 3)``: straight along x, tail first, tip last, lying in the clips."""
        return self._cable0.copy()

    def world_block(self) -> Dict[str, Any]:
        return world_block(self.table_z, self.statics(), self.g["cable"])

    def world(self, colliders: Optional[Sequence[spec.ColliderSpec]] = None) -> Dict[str, Any]:
        return cable_world(self.table_z, self.statics(), self.g["cable"], colliders=colliders)

    def grasp_point(self, nodes: np.ndarray) -> np.ndarray:
        """Where the pads close on the cable: ``tip_len`` before the tip along the current polyline."""
        return point_before_tip(nodes, float(self.g["tip_len"]))

    # -- metrics
    def metrics(self, nodes: np.ndarray) -> Dict[str, Any]:
        """Crossing metrics of the cable against the wall: ``crossings`` of the wall mid-plane, the crossing point and whether
        it is ``inside`` the hole, ``pass`` (tip beyond the far face), ``stretch`` and ``tip``."""
        nodes = np.asarray(nodes, dtype=np.float64)
        w_ = self.wall
        m: Dict[str, Any] = {
            "cross": None,
            "pass": 0.0,
            "crossings": 0,
            "inside": False,
            "stretch": 1.0,
            "tip": nodes[-1].copy(),
            "finite": bool(np.isfinite(nodes).all()),
        }
        if not m["finite"]:
            return m
        m["stretch"] = stretch_ratio(nodes, self.rest_len)
        t = 0.5 * w_["thickness"]
        xs = nodes[:, 0] - w_["x"]
        sgn = np.sign(xs)
        idx = np.nonzero(sgn[:-1] * sgn[1:] < 0)[0]
        m["crossings"] = int(len(idx))
        m["pass"] = float(nodes[-1, 0] - (w_["x"] + t))
        if len(idx):
            i = int(idx[-1])
            f = xs[i] / (xs[i] - xs[i + 1])
            c = nodes[i] + f * (nodes[i + 1] - nodes[i])
            hw, hh = (0.5 * v for v in w_["hole"])
            m["inside"] = bool(
                abs(c[1] - w_["y"]) <= hw - self.radius + 1e-9 and abs(c[2] - w_["z"]) <= hh - self.radius + 1e-9
            )
            m["cross"] = c
        return m

    def judge(self, nodes: np.ndarray, m: Optional[Dict[str, Any]] = None) -> Tuple[bool, Optional[str]]:
        """Instantaneous success test and an optional truncation reason (the cable left the plate)."""
        nodes = np.asarray(nodes, dtype=np.float64)
        m = self.metrics(nodes) if m is None else m
        if not m["finite"]:
            return False, "cable state is not finite"
        if nodes[:, 2].min() < self.table_z - 0.03:
            return False, "the cable fell below the plate"
        ok = bool(
            m["inside"]
            and m["crossings"] == 1
            and m["pass"] >= float(self.g["pass_len"])
            and m["stretch"] <= float(self.g["stretch_max"])
        )
        return ok, None


# =====================================================================================================================
# cable_slack_reduce
# =====================================================================================================================

SLACK: Dict[str, Any] = {
    "n_seg": 26,
    "length": 0.26,
    "radius": 0.0035,
    "fixed_xy": [-0.17, -0.06],
    "chord": 0.208,  # initial end-to-end distance
    "chord_yaw_deg": 0.0,
    "shape": "bump",
    "side": -1.0,  # the bump bulges to this side of the chord (+ left of the chord direction)
    "pinned_segments": [0, 1, 2],
    "clamp_half": [0.016, 0.022, 0.008],
    "clamp_mu": 0.8,
    "slack_target": 0.03,
    "slip_max": 0.012,
    "stretch_max": 1.06,
    "lost_max": 25,
    "success_hold": 20,
    "min_contacts": 1,
    "pinch_gap": 0.0105,
    # the notched ridge under the free end lifts the cable to the pad-centre height (the fingertips reach the plate 19 mm
    # below the pad centre); narrower than the closed pads so the fingers never clamp it
    "ridge_h": 0.01582,
    "ridge_w": 0.003,
    "ridge_lip_h": 0.0013,
    "ridge_lip_w": 0.0006,
    "ridge_mu": 0.5,
    "ridge_x": [0.11, 0.23],  # from the fixed end along x
    "tail_len": 0.07,  # straight tail on the ridge
    # rigid placement of the whole setup (clamp, ridge, cable): turned by ``yaw_deg`` about the fixed end, then shifted
    "dx": 0.002,
    "dy": -0.005,
    "yaw_deg": 0.0,
    "pad_mu": 1.025,
    "fixture_overlap_fail": True,
    "fixture_overlap_tol": 0.0002,
    "cable": {
        "radius": 0.0035,
        "density": 900.0,
        "stretch_stiffness": 2.0e4,
        "stretch_damping": 0.1,
        "bend_stiffness": 0.2,
        "bend_damping": 1.0e-4,
        "mu": 0.8,
        "pinned_segments": [0, 1, 2],
        "color": [0.90, 0.45, 0.10],
    },
    "pinch_overlap": 0.0005,
    "settle_ticks": 45,
}


class SlackScene:
    """The ``cable_slack_reduce`` scene: clamp on the pinned head, notched ridge under the free end, the bump-shaped cable."""

    def __init__(self, g: Dict[str, Any], table_z: float = TABLE_Z):
        self.g = spec.merge_dicts(SLACK, g)
        self.table_z = float(table_z)
        self.n_seg = int(self.g["n_seg"])
        self.rest_len = float(self.g["length"])
        self.radius = float(self.g["radius"])
        self.g["cable"]["pinned_segments"] = [int(i) for i in self.g["pinned_segments"]]

    # -- placement
    def place(self, p: np.ndarray) -> np.ndarray:
        """The rigid move of the setup applied to points ``(..., 3)``: turn ``yaw_deg`` about the fixed end, shift ``dx, dy``."""
        g = self.g
        f = np.asarray(g["fixed_xy"], dtype=np.float64)
        c, s_ = np.cos(np.radians(float(g["yaw_deg"]))), np.sin(np.radians(float(g["yaw_deg"])))
        q = np.array(p, dtype=np.float64, copy=True)
        x, y = q[..., 0] - f[0], q[..., 1] - f[1]
        q[..., 0] = f[0] + c * x - s_ * y + float(g["dx"])
        q[..., 1] = f[1] + s_ * x + c * y + float(g["dy"])
        return q

    def fixture_quat(self) -> List[float]:
        h = 0.5 * np.radians(float(self.g["yaw_deg"]))
        return [0.0, 0.0, float(np.sin(h)), float(np.cos(h))]

    # -- geometry
    @property
    def z_cable(self) -> float:
        return self.table_z + self.radius + 0.0005

    def clamp_pose(self) -> Tuple[np.ndarray, np.ndarray]:
        """Centre / half extents of the clamp bar on the pinned head (placed)."""
        h = np.asarray(self.g["clamp_half"], dtype=np.float64)
        f = np.asarray(self.g["fixed_xy"], dtype=np.float64)
        seg = self.rest_len / self.n_seg
        k = len(self.g["pinned_segments"])
        centre = np.array([f[0] + 0.5 * k * seg, f[1], self.table_z + 2 * self.radius + 0.001 + h[2]])
        return self.place(centre), h

    def ridge_pose(self) -> Optional[Tuple[np.ndarray, np.ndarray]]:
        h = float(self.g["ridge_h"])
        if h <= 0.0:
            return None
        f = np.asarray(self.g["fixed_xy"], dtype=np.float64)
        x0, x1 = (float(v) for v in self.g["ridge_x"])
        centre = np.array([f[0] + 0.5 * (x0 + x1), f[1], self.table_z + 0.5 * h])
        return self.place(centre), np.array([0.5 * (x1 - x0), 0.5 * float(self.g["ridge_w"]), 0.5 * h])

    def _ridge_nominal(self) -> Optional[Tuple[np.ndarray, np.ndarray]]:
        h = float(self.g["ridge_h"])
        if h <= 0.0:
            return None
        f = np.asarray(self.g["fixed_xy"], dtype=np.float64)
        x0, x1 = (float(v) for v in self.g["ridge_x"])
        return np.array([f[0] + 0.5 * (x0 + x1), f[1], self.table_z + 0.5 * h]), np.array(
            [0.5 * (x1 - x0), 0.5 * float(self.g["ridge_w"]), 0.5 * h]
        )

    def lip_poses(self) -> List[Tuple[np.ndarray, np.ndarray]]:
        """The two notch lips on the ridge top, flush with its sides (placed)."""
        rp = self._ridge_nominal()
        lh = float(self.g["ridge_lip_h"])
        if rp is None or lh <= 0.0:
            return []
        lw = float(self.g["ridge_lip_w"])
        hy = float(rp[1][1])
        z = self.table_z + float(self.g["ridge_h"]) + 0.5 * lh
        return [
            (
                self.place(np.array([rp[0][0], rp[0][1] + s * (hy - 0.5 * lw), z])),
                np.array([rp[1][0], 0.5 * lw, 0.5 * lh]),
            )
            for s in (-1.0, 1.0)
        ]

    def ridge_seat(self) -> float:
        """Height of the resting cable's bottom above the plate on the ridge (on the lip edges with a notch)."""
        h, lh = float(self.g["ridge_h"]), float(self.g["ridge_lip_h"])
        if lh <= 0.0:
            return h
        a = 0.5 * float(self.g["ridge_w"]) - float(self.g["ridge_lip_w"])
        if a >= self.radius:
            return h
        return h + lh - (self.radius - float(np.sqrt(self.radius**2 - a * a)))

    def statics(self) -> List[Dict[str, Any]]:
        quat = self.fixture_quat()
        c, h = self.clamp_pose()
        out = [{"name": "clamp", "pos": c.tolist(), "half": h.tolist(), "quat": quat, "mu": float(self.g["clamp_mu"])}]
        rp = self.ridge_pose()
        if rp is not None:
            out.append(
                {
                    "name": "ridge",
                    "pos": rp[0].tolist(),
                    "half": rp[1].tolist(),
                    "quat": quat,
                    "mu": float(self.g["ridge_mu"]),
                }
            )
        for i, (lc, lh_) in enumerate(self.lip_poses()):
            out.append(
                {
                    "name": f"lip{i}",
                    "pos": lc.tolist(),
                    "half": lh_.tolist(),
                    "quat": quat,
                    "mu": float(self.g["ridge_mu"]),
                }
            )
        return out

    def fixtures(self) -> List[Dict[str, Any]]:
        yaw = float(self.g["yaw_deg"])
        c, h = self.clamp_pose()
        out = [{"name": "clamp", "center": c.tolist(), "half": h.tolist(), "color": [0.25, 0.30, 0.45], "yaw_deg": yaw}]
        rp = self.ridge_pose()
        if rp is not None:
            out.append(
                {
                    "name": "ridge",
                    "center": rp[0].tolist(),
                    "half": rp[1].tolist(),
                    "color": [0.45, 0.45, 0.5],
                    "yaw_deg": yaw,
                }
            )
        for i, (lc, lh_) in enumerate(self.lip_poses()):
            out.append(
                {
                    "name": f"lip{i}",
                    "center": lc.tolist(),
                    "half": lh_.tolist(),
                    "color": [0.45, 0.45, 0.5],
                    "yaw_deg": yaw,
                }
            )
        return out

    def fixture_boxes(self) -> List[Tuple[str, np.ndarray, np.ndarray]]:
        """The ridge and the lips as ``(name, pose7 xyzw, half)`` for the pad clearance check (the clamp is never near the pads)."""
        return statics_as_boxes([s for s in self.statics() if s["name"] != "clamp"])

    def initial_cable(self) -> np.ndarray:
        """``(n_seg + 1, 3)``: a straight pinned head along the chord, the bump, and a straight tail climbing onto the ridge."""
        g = self.g
        chord = float(g["chord"])
        yaw = np.radians(float(g["chord_yaw_deg"]))
        f = np.asarray(g["fixed_xy"], dtype=np.float64)
        a = np.array([f[0], f[1], self.z_cable])
        b = a + chord * np.array([np.cos(yaw), np.sin(yaw), 0.0])
        side = float(g["side"])
        k = len(g["pinned_segments"])
        seg = self.rest_len / self.n_seg
        u = (b - a) / np.linalg.norm(b - a)
        head = a[None, :] + np.arange(k)[:, None] * seg * u[None, :]
        n_tail = int(round(float(g["tail_len"]) / seg)) if float(g["ridge_h"]) > 0.0 else 0
        if n_tail > 0:
            c_end = b - n_tail * seg * u
            if str(g["shape"]) == "bump":
                arc = bump_arc(
                    a + k * seg * u, c_end, self.rest_len - (k + n_tail) * seg, self.n_seg - k - n_tail, side=side
                )
            else:
                arc = spec.planar_arc(
                    a + k * seg * u,
                    c_end,
                    self.rest_len - (k + n_tail) * seg,
                    self.n_seg - k - n_tail,
                    side=side,
                    shape=str(g["shape"]),
                )
            tail_pts = c_end[None, :] + np.arange(1, n_tail + 1)[:, None] * seg * u[None, :]
            pts = np.vstack([head, arc, tail_pts])
            x0 = f[0] + float(g["ridge_x"][0])
            ramp = np.clip((pts[:, 0] - x0) / 0.02, 0.0, 1.0)
            pts[:, 2] += self.ridge_seat() * ramp * ramp * (3.0 - 2.0 * ramp)
        else:
            tail = spec.planar_arc(
                a + k * seg * u, b, self.rest_len - k * seg, self.n_seg - k, side=side, shape=str(g["shape"])
            )
            pts = np.vstack([head, tail])
        return self.place(pts)

    def world_block(self) -> Dict[str, Any]:
        return world_block(self.table_z, self.statics(), self.g["cable"])

    def world(self, colliders: Optional[Sequence[spec.ColliderSpec]] = None) -> Dict[str, Any]:
        if colliders is None:
            colliders = gsmini_colliders(float(self.g["pad_mu"]))
        return cable_world(self.table_z, self.statics(), self.g["cable"], colliders=colliders)

    def fixed_end(self, nodes: np.ndarray) -> np.ndarray:
        return np.asarray(nodes, dtype=np.float64)[0]

    def tracker(self) -> "SlackTracker":
        return SlackTracker(self)


class SlackTracker:
    """Per-episode metrics of ``cable_slack_reduce``: the pinch is detected from the pad gap and the contact counts, the
    gripped material point is remembered (``s_pinch``) and the slack / sag of the cable between the clamp and that point,
    the slip of the pinch and the stretch are updated every tick."""

    def __init__(self, scene: SlackScene):
        self.scene = scene
        g = scene.g
        self.pinched = False
        self.k_grip: Optional[int] = None
        self.s_pinch: Optional[float] = None
        self.lost = 0
        self.slack = float("nan")
        self.sag = float("nan")
        self.slip = 0.0
        self.stretch = 1.0
        self.contacts = np.zeros(2, dtype=np.int64)
        self.fix_overlap = float("-inf")
        self.finite = True
        self._boxes = scene.fixture_boxes()
        self._rest_s = np.linspace(0.0, scene.rest_len, scene.n_seg + 1)
        self._min_contacts = int(g["min_contacts"])
        self._pinch_gap = float(g["pinch_gap"])

    def update(self, nodes: np.ndarray, pads: np.ndarray, settling: bool = False) -> Dict[str, Any]:
        """``nodes`` ``(S + 1, 3)``, ``pads`` ``(C, 7)`` xyzw collider poses (the two gel pads first)."""
        nodes = np.asarray(nodes, dtype=np.float64)
        sc = self.scene
        self.finite = bool(np.isfinite(nodes).all())
        if not self.finite:
            return self.as_dict()
        self.stretch = stretch_ratio(nodes, sc.rest_len)
        if settling:
            return self.as_dict()
        pads = np.asarray(pads, dtype=np.float64)[:2]
        halves = list(PAD_HALVES)
        ov = fixture_overlap(pads, halves, self._boxes)
        self.fix_overlap = max(self.fix_overlap, ov["pad"], ov["finger"]) if self._boxes else self.fix_overlap
        self.contacts = contact_counts(cable_samples(nodes), sc.radius, pads, halves)
        both = bool(np.all(self.contacts >= self._min_contacts))
        gap = float(np.linalg.norm(pads[0, :3] - pads[1, :3]))
        closed = gap <= self._pinch_gap + 0.012
        mid = pads[:, :3].mean(axis=0)
        s_now, _ = project_on_polyline(nodes, self._rest_s, mid)
        if not self.pinched:
            if both and closed:
                self.pinched = True
                self.s_pinch = s_now
                self.k_grip = int(round(s_now / (sc.rest_len / sc.n_seg)))
        else:
            self.lost = 0 if both else self.lost + 1
            self.slip = abs(s_now - float(self.s_pinch))
        k = self.k_grip if self.k_grip is not None else sc.n_seg
        k = max(2, min(k, sc.n_seg))
        self.slack = cable_slack(nodes[: k + 1])
        self.sag = cable_sag(nodes[: k + 1])
        return self.as_dict()

    def judge(self, nodes: np.ndarray) -> Tuple[bool, Optional[str]]:
        """Instantaneous success test and an optional truncation reason."""
        g = self.scene.g
        nodes = np.asarray(nodes, dtype=np.float64)
        if not np.isfinite(self.slack):
            return False, None
        if not self.finite or not np.isfinite(nodes).all():
            return False, "cable state is not finite"
        if bool(g["fixture_overlap_fail"]) and self.fix_overlap > float(g["fixture_overlap_tol"]):
            return False, f"a pad cut {self.fix_overlap * 1e3:.1f} mm into the ridge"
        if self.pinched and self.lost > int(g["lost_max"]):
            return False, "the pinch was lost"
        if nodes[:, 2].min() < self.scene.table_z - 0.03 or np.abs(nodes[:, :2]).max() > 1.0:
            return False, "the cable left the work plate"
        ok = bool(
            self.pinched
            and self.slack <= float(g["slack_target"])
            and self.slip <= float(g["slip_max"])
            and self.stretch <= float(g["stretch_max"])
            and self.lost <= int(g["lost_max"])
        )
        return ok, None

    def as_dict(self) -> Dict[str, Any]:
        return {
            "slack": self.slack,
            "sag": self.sag,
            "slip": self.slip,
            "stretch": self.stretch,
            "pad_contacts": self.contacts.copy(),
            "pinched": self.pinched,
            "lost": self.lost,
            "pad_fixture_overlap": max(self.fix_overlap, -1.0),
        }


# =====================================================================================================================
# cable_route_channel
# =====================================================================================================================

ROUTE: Dict[str, Any] = {
    "n_seg": 40,
    "length": 0.4,
    "radius": 0.0035,
    "pinned_segments": [0, 1],
    "slot_start": [-0.15, -0.05],
    "slot_heading_deg": 0.0,
    "slot_width": 0.034,
    "rail_width": 0.02,
    "rail_height": 0.005,
    "rail_mu": 0.5,
    "straight": 0.23,
    "turn_deg": 0.0,
    "turn_radius": 0.06,
    "straight2": 0.0,
    "start_offset": 0.07,  # the free part of the cable lies this far beside the slot
    "blend": 0.05,
    "start_lead": 0.03,  # the cable first runs straight along the slot this far, then swings away
    "rest_straight": True,  # the rod's rest shape is the slot centreline: a placed cable stays put
    # the support under the free part of the cable: a row of cable clips (post + two walls) ``ridge_h`` tall along the line
    # ``slot_y + ridge_side * start_offset``; the hose spans the gaps and the picks are taken mid-span
    "ridge_h": 0.022,
    "ridge_w": 0.008,
    "ridge_x0": -0.01,
    "ridge_x1": 0.08,
    "ridge_side": 1.0,
    "ridge_lip_h": 0.0,
    "ridge_lip_w": 0.0007,
    "support": "clips",
    "support_mu": 0.5,
    "clip_spacing": 0.055,
    "clip_x0": 0.01,
    "clip_len": 0.008,
    "clip_post_w": 0.012,
    "clip_post_in": 0.0,
    "clip_wall_h": 0.012,
    "clip_wall_t": 0.0015,
    "clip_slack": 0.001,
    "clip_fence": "both",
    # a tall post with a clip at the far end of the row: after the first carry the tail hangs from the slot up to it, so
    # the later picks pinch the hanging hose in mid-air
    "far_clip_x": 0.15,
    "far_clip_seat": 0.05,
    "far_clip_wall_h": 0.012,
    "far_clip_len": 0.01,
    "pick_in": 0.02,
    "pick_step": 0.04,
    "place_x_max": 0.12,  # the hand reaches x <= ~0.12 over the plate
    "pick_z_min": 0.019,
    "fixture_overlap_fail": True,
    "fixture_overlap_tol": 0.0002,
    "route_len": 0.20,
    "open_gap": 0.02,
    "rest_speed": 0.01,
    "success_hold": 25,
    # rigid shift of the whole setup (slot, clips, far clip, initial cable) in the plate frame
    "dx": -0.005,
    "dy": 0.0,
    "table_mu": 0.7,
    "cable": {
        "radius": 0.0035,
        "density": 900.0,
        "stretch_stiffness": 2.0e4,
        "stretch_damping": 0.1,
        "bend_stiffness": 0.0525,
        "bend_damping": 0.01,
        "mu": 0.8,
        "pinned_segments": [0, 1],
        "color": [0.95, 0.75, 0.10],
    },
    "pinch_overlap": 0.00075,
    "settle_ticks": 45,
}


class RouteScene:
    """Slot, clips and the initial cable of ``cable_route_channel`` on a plate at ``table_z``."""

    def __init__(self, g: Dict[str, Any], table_z: float = TABLE_Z):
        self.g = spec.merge_dicts(ROUTE, g)
        g = self.g
        self.table_z = float(table_z)
        dx, dy = float(g["dx"]), float(g["dy"])
        if dx != 0.0 or dy != 0.0:
            g["slot_start"] = [float(g["slot_start"][0]) + dx, float(g["slot_start"][1]) + dy]
            for k in ("ridge_x0", "ridge_x1"):
                g[k] = float(g[k]) + dx
            if float(g["far_clip_x"]) > 0.0:
                g["far_clip_x"] = float(g["far_clip_x"]) + dx
            g["dx"], g["dy"] = 0.0, 0.0
        self.n_seg = int(g["n_seg"])
        self.rest_len = float(g["length"])
        self.radius = float(g["radius"])
        g["cable"]["pinned_segments"] = [int(i) for i in g["pinned_segments"]]
        extra = max(
            self.rest_len
            - (
                float(g["straight"])
                + float(g["straight2"])
                + abs(float(g["turn_deg"])) / 180.0 * np.pi * float(g["turn_radius"])
            ),
            0.0,
        )
        self.centerline = slot_centerline(
            g["slot_start"],
            g["slot_heading_deg"],
            float(g["straight"]),
            float(g["turn_deg"]),
            float(g["turn_radius"]),
            float(g["straight2"]) + extra,
        )
        self._sa = edge_arclength(np.column_stack([self.centerline, np.zeros(len(self.centerline))]))
        self.slot_len = float(self._sa[-1])

    # -- slot
    def slot_rails(self) -> List[Dict[str, Any]]:
        """Rail boxes along the part of the centreline the task uses (``route_len`` plus a margin)."""
        g = self.g
        used = min(float(g["route_len"]) + 0.04, self.slot_len)
        k = int(np.searchsorted(self._sa, used)) + 1
        return rail_boxes(
            self.centerline[:k], float(g["slot_width"]), float(g["rail_width"]), float(g["rail_height"]), self.table_z
        )

    def centerline_point(self, s: float) -> Tuple[np.ndarray, np.ndarray]:
        """Point (xy) and unit tangent (xy) of the slot centreline at arc length ``s`` from the slot start."""
        c, sa = self.centerline, self._sa
        s = float(np.clip(s, 0.0, sa[-1] - 1e-6))
        p = np.array([np.interp(s, sa, c[:, k]) for k in range(2)])
        q = np.array([np.interp(min(s + 0.01, sa[-1]), sa, c[:, k]) for k in range(2)])
        t = q - p
        return p, t / max(np.linalg.norm(t), 1e-9)

    # -- support
    def ridge_y(self) -> float:
        g = self.g
        return float(g["slot_start"][1]) + float(g["ridge_side"]) * float(g["start_offset"])

    def has_support(self) -> bool:
        return float(self.g["ridge_h"]) > 0.0

    def ridge_box(self) -> Optional[Dict[str, Any]]:
        g = self.g
        h = float(g["ridge_h"])
        if h <= 0.0 or str(g["support"]) == "clips":
            return None
        x0, x1 = float(g["ridge_x0"]), float(g["ridge_x1"])
        return {
            "pos": [0.5 * (x0 + x1), self.ridge_y(), self.table_z + 0.5 * h],
            "half": [0.5 * (x1 - x0), 0.5 * float(g["ridge_w"]), 0.5 * h],
            "quat": [0.0, 0.0, 0.0, 1.0],
        }

    def lip_boxes(self) -> List[Dict[str, Any]]:
        g = self.g
        rb = self.ridge_box()
        lh = float(g["ridge_lip_h"])
        if rb is None or lh <= 0.0:
            return []
        lw = float(g["ridge_lip_w"])
        hy = float(rb["half"][1])
        z = self.table_z + float(g["ridge_h"]) + 0.5 * lh
        return [
            {
                "pos": [rb["pos"][0], rb["pos"][1] + s * (hy - 0.5 * lw), z],
                "half": [rb["half"][0], 0.5 * lw, 0.5 * lh],
                "quat": [0.0, 0.0, 0.0, 1.0],
            }
            for s in (-1.0, 1.0)
        ]

    def ridge_seat(self) -> float:
        """Height of the resting hose's bottom above the plate on the support."""
        g = self.g
        h, lh = float(g["ridge_h"]), float(g["ridge_lip_h"])
        if h <= 0.0:
            return 0.0
        if lh <= 0.0 or str(g["support"]) == "clips":
            return h
        a = 0.5 * float(g["ridge_w"]) - float(g["ridge_lip_w"])
        if a >= self.radius:
            return h
        return h + lh - (self.radius - float(np.sqrt(self.radius**2 - a * a)))

    def clip_xs(self) -> List[float]:
        """Centre x of every clip: every ``clip_spacing`` from ``ridge_x0 + clip_x0`` to ``ridge_x1`` (short of the far post)."""
        g = self.g
        if str(g["support"]) != "clips" or float(g["ridge_h"]) <= 0.0:
            return []
        x0, x1, dx = float(g["ridge_x0"]) + float(g["clip_x0"]), float(g["ridge_x1"]), float(g["clip_spacing"])
        xf = float(g["far_clip_x"])
        if xf > 0.0:
            x1 = min(x1, xf - 0.03)
        return [float(x) for x in np.arange(x0, x1 + 1e-9, dx)]

    def clip_boxes(self) -> List[Dict[str, Any]]:
        """Per clip a post (top = the seat) and two walls ``clip_wall_h`` above it, inner width ``2 r + clip_slack``."""
        g = self.g
        out = []
        h, L, pw = float(g["ridge_h"]), float(g["clip_len"]), float(g["clip_post_w"])
        wh, wt = float(g["clip_wall_h"]), float(g["clip_wall_t"])
        inner = 2.0 * self.radius + float(g["clip_slack"])
        y = self.ridge_y()
        pin = float(g["clip_post_in"])
        s_in = -float(np.sign(float(g["ridge_side"])) or 1.0)
        for i, x in enumerate(self.clip_xs()):
            wy = max(pw, inner + 2 * wt)
            out.append(
                {
                    "name": f"clip{i}",
                    "pos": [x, y + s_in * 0.5 * pin, self.table_z + 0.5 * h],
                    "half": [0.5 * L, 0.5 * (wy + pin), 0.5 * h],
                    "quat": [0.0, 0.0, 0.0, 1.0],
                }
            )
            sides = (-1.0, 1.0) if str(g["clip_fence"]) == "both" else (float(np.sign(float(g["ridge_side"])) or 1.0),)
            for j, sgn in enumerate(sides):
                out.append(
                    {
                        "name": f"clip{i}w{j}",
                        "pos": [x, y + sgn * (0.5 * inner + 0.5 * wt), self.table_z + h + 0.5 * wh],
                        "half": [0.5 * L, 0.5 * wt, 0.5 * wh],
                        "quat": [0.0, 0.0, 0.0, 1.0],
                    }
                )
        return out

    def far_clip_boxes(self) -> List[Dict[str, Any]]:
        g = self.g
        xf = float(g["far_clip_x"])
        if xf <= 0.0 or not self.has_support():
            return []
        L, seat, wh, wt = (
            float(g["far_clip_len"]),
            float(g["far_clip_seat"]),
            float(g["far_clip_wall_h"]),
            float(g["clip_wall_t"]),
        )
        inner = 2.0 * self.radius + float(g["clip_slack"])
        y = self.ridge_y()
        out = [
            {
                "name": "farpost",
                "pos": [xf, y, self.table_z + 0.5 * seat],
                "half": [0.5 * L, 0.5 * (inner + 2 * wt), 0.5 * seat],
                "quat": [0.0, 0.0, 0.0, 1.0],
            }
        ]
        for j, sgn in enumerate((-1.0, 1.0)):
            out.append(
                {
                    "name": f"farpostw{j}",
                    "pos": [xf, y + sgn * (0.5 * inner + 0.5 * wt), self.table_z + seat + 0.5 * wh],
                    "half": [0.5 * L, 0.5 * wt, 0.5 * wh],
                    "quat": [0.0, 0.0, 0.0, 1.0],
                }
            )
        return out

    def support_boxes(self) -> List[Dict[str, Any]]:
        if str(self.g["support"]) == "clips":
            return self.clip_boxes() + self.far_clip_boxes()
        out = []
        rb = self.ridge_box()
        if rb is not None:
            out.append({"name": "ridge", **rb})
        for i, b in enumerate(self.lip_boxes()):
            out.append({"name": f"lip{i}", **b})
        return out

    # -- both engines
    def statics(self) -> List[Dict[str, Any]]:
        out = [{"name": f"rail{i}", **b, "mu": float(self.g["rail_mu"])} for i, b in enumerate(self.slot_rails())]
        out += [{**b, "mu": float(self.g["support_mu"])} for b in self.support_boxes()]
        return out

    def fixtures(self) -> List[Dict[str, Any]]:
        out = []
        for i, b in enumerate(self.slot_rails()):
            yaw = float(np.degrees(2.0 * np.arctan2(b["quat"][2], b["quat"][3])))
            out.append(
                {"name": f"rail{i}", "center": b["pos"], "half": b["half"], "color": [0.36, 0.38, 0.45], "yaw_deg": yaw}
            )
        for b in self.support_boxes():
            out.append(
                {"name": b["name"], "center": b["pos"], "half": b["half"], "color": [0.55, 0.40, 0.25], "yaw_deg": 0.0}
            )
        return out

    def fixture_boxes(self) -> List[Tuple[str, np.ndarray, np.ndarray]]:
        return statics_as_boxes(self.statics())

    def world_block(self) -> Dict[str, Any]:
        return world_block(self.table_z, self.statics(), self.g["cable"], table_mu=float(self.g["table_mu"]))

    def world(self, colliders: Optional[Sequence[spec.ColliderSpec]] = None) -> Dict[str, Any]:
        return cable_world(
            self.table_z, self.statics(), self.g["cable"], table_mu=float(self.g["table_mu"]), colliders=colliders
        )

    # -- cable
    def initial_cable(self, side: Optional[float] = None) -> np.ndarray:
        """``(n_seg + 1, 3)`` initial centreline: a straight lead along the slot, a smooth swing to ``start_offset`` beside
        it, lifted onto the support seat over a 3 cm ramp and rising to the far post's seat over the last span."""
        g = self.g
        side = float(g["ridge_side"]) if side is None else float(side)
        s = np.linspace(0.0, self.rest_len, self.n_seg + 1)
        pts = []
        for si in s:
            p, t = self.centerline_point(min(si, self.slot_len - 1e-4))
            nrm = np.array([-t[1], t[0]])
            u = np.clip((si - float(g["start_lead"])) / float(g["blend"]), 0.0, 1.0)
            off = side * float(g["start_offset"]) * (u * u * (3 - 2 * u))
            q = p + off * nrm
            pts.append([q[0], q[1], self.table_z + self.radius + 0.0005])
        pts = np.asarray(pts)
        pts = spec.resample_polyline(pts, self.n_seg) if abs(spec.polyline_length(pts) - self.rest_len) > 1e-3 else pts
        if self.has_support():
            seat = self.ridge_seat()
            for i in range(len(pts)):
                u = float(np.clip((pts[i, 0] - (float(g["ridge_x0"]) - 0.03)) / 0.03, 0.0, 1.0))
                pts[i, 2] += seat * (u * u * (3 - 2 * u)) + (0.0005 if u > 0 else 0.0)
            xf = float(g["far_clip_x"])
            if xf > 0.0 and str(g["support"]) == "clips":
                xs = self.clip_xs()
                xa = (xs[-1] + 0.5 * float(g["clip_len"]) + 0.01) if xs else float(g["ridge_x0"])
                rise = float(g["far_clip_seat"]) - seat
                for i in range(len(pts)):
                    v = float(np.clip((pts[i, 0] - xa) / max(xf - xa, 1e-6), 0.0, 1.0))
                    pts[i, 2] += rise * (v * v * (3 - 2 * v))
        return pts

    def rest_cable_points(self, points: np.ndarray) -> np.ndarray:
        """The rod's rest shape: the slot centreline at the initial height (``rest_straight``), else the initial points."""
        if points is None or not bool(self.g["rest_straight"]):
            return points
        z = float(np.asarray(points)[0, 2])
        pts = []
        for si in np.linspace(0.0, self.rest_len, self.n_seg + 1):
            p, _ = self.centerline_point(min(si, self.slot_len - 1e-4))
            pts.append([p[0], p[1], z])
        return np.asarray(pts, dtype=np.float64)

    def on_support(self, nodes: np.ndarray, tol_y: float = 0.002, tol_z: float = 0.003) -> np.ndarray:
        """Per-node mask: the node rests on the support line (lateral and height tolerance)."""
        nodes = np.asarray(nodes, dtype=np.float64)
        if not self.has_support():
            return np.zeros(len(nodes), dtype=bool)
        g = self.g
        z_c = self.table_z + self.ridge_seat() + self.radius
        x0, x1 = float(g["ridge_x0"]), float(g["ridge_x1"])
        dy = nodes[:, 1] - self.ridge_y()
        s_in = -float(np.sign(float(g["ridge_side"])) or 1.0)
        lat = (np.abs(dy) <= tol_y) | ((dy * s_in >= 0.0) & (dy * s_in <= float(g["clip_post_in"]) + tol_y))
        return lat & (np.abs(nodes[:, 2] - z_c) <= tol_z) & (nodes[:, 0] >= x0 - 0.01) & (nodes[:, 0] <= x1 + 0.01)

    def spans(self) -> List[Tuple[float, float]]:
        """Open x intervals between neighbouring clips (one interval = the whole blade without clips)."""
        g = self.g
        xs = self.clip_xs()
        if not xs:
            return [(float(g["ridge_x0"]), float(g["ridge_x1"]))] if self.has_support() else []
        hl = 0.5 * float(g["clip_len"])
        out = [(xs[i] + hl, xs[i + 1] - hl) for i in range(len(xs) - 1)]
        if float(g["far_clip_x"]) > 0.0:
            out.append((xs[-1] + hl, float(g["far_clip_x"]) - 0.5 * float(g["far_clip_len"])))
        return out

    def next_pick(
        self,
        nodes: np.ndarray,
        s_min: float,
        margin: float = 0.015,
        end_margin: float = 0.015,
        cover: float = 0.0125,
        grip_dz: float = 0.026,
        closed_gap: Optional[float] = None,
        open_gap: float = 0.02,
    ) -> Optional[float]:
        """Arc length of the next pick on the live cable, or None when the cable is used up.

        With a far post and ``s_min > 0`` (a hanging pick): the first point at least ``pick_step`` of cable past the previous
        pick where the hose is high enough for the pads over the pad footprint, within the hand's reach, before the far post,
        and where the pads and finger bodies clear every fixture in the closed and the open configuration.  With clips: the
        first span whose middle is covered by cable resting on the support line and whose arc length is >= ``s_min``; the
        pick is at the span middle (at most ``pick_in`` past the first clip).  Blade: ``margin`` past the first node at arc
        length >= ``s_min`` resting on it."""
        nodes = np.asarray(nodes, dtype=np.float64)
        sa = edge_arclength(nodes)
        on = self.on_support(nodes)
        g = self.g
        s_reach = float(g["place_x_max"]) - float(g["slot_start"][0])
        if float(g["far_clip_x"]) > 0.0 and s_min > 0.0:
            z_min = float(g["pick_z_min"])
            s_post = (
                float(np.interp(float(g["far_clip_x"]) - 0.5 * float(g["far_clip_len"]), nodes[:, 0], sa))
                if np.all(np.diff(nodes[:, 0]) > 0)
                else sa[-1]
            )
            s_max = min(sa[-1] - float(end_margin), s_post - 0.02, s_reach)
            gap = (2.0 * self.radius - 0.0015) if closed_gap is None else float(closed_gap)
            boxes = self.fixture_boxes()
            for s in np.arange(float(s_min) + float(g["pick_step"]), s_max, 0.0025):
                zs = np.interp([s - 0.008, s, s + 0.008], sa, nodes[:, 2]) - self.table_z
                if zs.min() < z_min - 0.002 or zs[1] < z_min:
                    continue
                p = np.array([np.interp(s, sa, nodes[:, k]) for k in range(3)])
                q = np.array([np.interp(min(s + 0.015, sa[-1]), sa, nodes[:, k]) for k in range(3)])
                theta = float(np.arctan2(q[1] - p[1], q[0] - p[0]))
                mid = np.array([p[0], p[1], max(self.table_z + float(grip_dz), p[2])])
                clear = True
                for gp in (gap, float(open_gap)):
                    ov = fixture_overlap(pinch_pads(mid, theta, gp), PAD_HALVES, boxes)
                    clear = clear and ov["pad"] <= -0.002 and ov["finger"] <= -0.002
                if clear:
                    return float(s)
            return None
        if self.clip_xs():
            z_min = float(g["pick_z_min"])
            for xa, xb in self.spans():
                xm = min(0.5 * (xa + xb), xa + float(g["pick_in"]))
                win = (nodes[:, 0] >= xm - cover - 0.01) & (nodes[:, 0] <= xm + cover + 0.01)
                ok = win & (np.abs(nodes[:, 1] - self.ridge_y()) <= 0.004) & (nodes[:, 2] - self.table_z >= z_min)
                if win.sum() < 2 or not ok[win].all():
                    continue
                idx = np.nonzero(win)[0]
                order = np.argsort(nodes[idx, 0])
                s = float(np.interp(xm, nodes[idx[order], 0], sa[idx[order]]))
                if s < s_min:
                    continue
                return s if s <= min(sa[-1] - end_margin, s_reach) else None
            return None
        for i in range(len(nodes)):
            if sa[i] >= s_min and on[i]:
                s = float(sa[i]) + float(margin)
                return s if s <= sa[-1] - float(end_margin) else None
        return None

    def routed(self, nodes: np.ndarray) -> float:
        return routed_prefix_length(
            np.asarray(nodes, dtype=np.float64), self.centerline, float(self.g["slot_width"]), self.radius, self.table_z
        )[0]

    def tracker(self) -> "RouteTracker":
        return RouteTracker(self)


class RouteTracker:
    """Per-episode metrics of ``cable_route_channel``: the routed prefix length, the node speed, whether the hand pinched and
    released, and the deepest pad / finger overlap with a fixture."""

    def __init__(self, scene: RouteScene, control_dt: float = 1.0 / 60.0):
        self.scene = scene
        self.control_dt = float(control_dt)
        self.routed = 0.0
        self.released = False
        self.was_pinched = False
        self.speed = 0.0
        self.prev: Optional[np.ndarray] = None
        self.pad_overlap = float("-inf")
        self.pad_overlap_name = ""
        self.finger_overlap = float("-inf")
        self.finger_overlap_name = ""
        self.finite = True
        self._boxes = scene.fixture_boxes()

    def update(self, nodes: np.ndarray, pads: np.ndarray) -> Dict[str, Any]:
        nodes = np.asarray(nodes, dtype=np.float64)
        self.finite = bool(np.isfinite(nodes).all())
        if not self.finite:
            return self.as_dict()
        g = self.scene.g
        self.routed = self.scene.routed(nodes)
        if self.prev is not None:
            self.speed = float(np.abs(nodes - self.prev).max() / self.control_dt)
        self.prev = nodes.copy()
        pads = np.asarray(pads, dtype=np.float64)[:2]
        gap = float(np.linalg.norm(pads[0, :3] - pads[1, :3]))
        if gap < 0.02:
            self.was_pinched = True
        if self.was_pinched and gap >= float(g["open_gap"]):
            self.released = True
        ov = fixture_overlap(pads, list(PAD_HALVES), self._boxes)
        if ov["pad"] > self.pad_overlap:
            self.pad_overlap, self.pad_overlap_name = ov["pad"], ov["pad_name"]
        if ov["finger"] > self.finger_overlap:
            self.finger_overlap, self.finger_overlap_name = ov["finger"], ov["finger_name"]
        return self.as_dict()

    def judge(self, nodes: np.ndarray) -> Tuple[bool, Optional[str]]:
        g = self.scene.g
        nodes = np.asarray(nodes, dtype=np.float64)
        if not self.finite or not np.isfinite(nodes).all():
            return False, "cable state is not finite"
        if nodes[:, 2].min() < self.scene.table_z - 0.03 or np.abs(nodes[:, :2]).max() > 0.9:
            return False, "the cable left the work plate"
        if bool(g["fixture_overlap_fail"]) and self.pad_overlap > float(g["fixture_overlap_tol"]):
            return False, f"a gel pad cut {self.pad_overlap * 1e3:.1f} mm into {self.pad_overlap_name}"
        ok = bool(self.released and self.routed >= float(g["route_len"]) and self.speed <= float(g["rest_speed"]))
        return ok, None

    def as_dict(self) -> Dict[str, Any]:
        return {
            "routed": self.routed,
            "released": self.released,
            "speed": self.speed,
            "pad_fixture_overlap": max(self.pad_overlap, -1.0),
            "finger_fixture_overlap": max(self.finger_overlap, -1.0),
        }


__all__ = [
    "box_surface_distance",
    "contact_counts",
    "pad_penetration",
    "box_overlap",
    "edge_arclength",
    "project_on_polyline",
    "cable_length",
    "cable_slack",
    "cable_sag",
    "stretch_ratio",
    "cable_point_at",
    "point_before_end",
    "point_before_tip",
    "cable_samples",
    "bump_arc",
    "slot_centerline",
    "rail_boxes",
    "polyline_distance",
    "routed_prefix_length",
    "PAD_HALVES",
    "Q_PAD0",
    "pinch_pads",
    "pads_from_frame",
    "gel_link_poses_from_pads",
    "finger_boxes",
    "fixture_overlap",
    "statics_as_boxes",
    "HAND_LINKS",
    "load_hand_spheres",
    "spheres_world",
    "front_extent",
    "link_poses_at",
    "housing_faces_fixture",
    "world_block",
    "cable_world",
    "closed_face_gap",
    "NEEDLE",
    "NeedleScene",
    "SLACK",
    "SlackScene",
    "SlackTracker",
    "ROUTE",
    "RouteScene",
    "RouteTracker",
]
