"""Buzz-wire geometry in the YAMLab world (pure numpy; no Isaac).

Old geometry (mm, table frame) comes from the RoboTangle v1 STL package
(tmp/2026-10-11_robotangle_v1_stl/buzz_wire_3d/<tier>/) and the old generator
(ref/topogym_2dafa5f/topogym/assets/geometry/buzz_wire_3d.py, layout
straight_span_deck_rest_v1 and siblings): loop R 15.4 mm, tube r 1.26 mm, stem 15.96 mm,
grip box 30.52 x 9.8 x 7 mm, wire r 1.47 mm, end blocks 8 x 8 x 12 mm, deck 520.1 x 368.9 x
142.5 mm (top plate 17.5 mm on four 45 mm feet).

Re-layout: p_world = Rz(LAYOUT_YAW) @ p_old / 1000 + LAYOUT_T. Wand body frame = loop centre,
x along the handle, z = loop normal (the old URDF link frame).
"""
import os
import numpy as np
from scipy.spatial.transform import Rotation

HERE = os.path.dirname(os.path.abspath(__file__))
# old RoboTangle STL package (very_easy + easier copied into ../data/stl; BUZZ_STL_ROOT overrides)
_STL_CANDIDATES = [os.environ.get("BUZZ_STL_ROOT", ""),
                   os.path.join(HERE, "..", "data", "stl"),
                   "/workspace/yamlab_port/runs/buzz_wire_3d/stl"]  # vast mirror of the STL package
STL_ROOT = next(c for c in _STL_CANDIDATES if c and os.path.isdir(c))

TABLE_Z = 0.7517
# --- wand (metres, body frame at loop centre) ---
LOOP_R = 0.0154
TUBE_R = 0.00126
LOOP_SEGMENTS = 64
STEM_LEN = 0.01596
# Wooden grip box. TOOL DEVIATION (approved 2026-10-12): the old grip (30.52 x 9.8 x 7 mm) is too small for the
# YAM finger-tip contact patch (V-shaped fingers, contact only on the last 14 mm of the tips); the port uses a
# taller and longer grip. Loop, stem, wire and all clearances are unchanged.
OLD_GRIP_LEN, OLD_GRIP_HALF_W, OLD_GRIP_HALF_T = 0.03052, 0.0049, 0.0035
GRIP_LEN = 0.045
GRIP_HALF_W = 0.0049      # along body y (unchanged)
GRIP_HALF_T = 0.008       # along body z (16 mm tall)
WIRE_R = 0.00147
APERTURE = LOOP_R - TUBE_R - WIRE_R   # 12.67 mm usable aperture (old task)
GRIP_X0 = LOOP_R + STEM_LEN            # 31.36 mm
GRIP_X1 = GRIP_X0 + GRIP_LEN           # 61.88 mm
GRIP_XC = 0.5 * (GRIP_X0 + GRIP_X1)    # 46.62 mm
STL_ORIGIN_IN_BODY = np.array([0.5 * (GRIP_X1 - (LOOP_R + TUBE_R)), 0.0, 0.0])  # AABB centre: 22.61 mm
RHO_WOOD, RHO_METAL = 650.0, 7800.0
# --- deck (old table frame mm; deck STL frame centred at (55.679, -270, 71.247)) ---
DECK_CENTER_OLD = np.array([55.679, -270.0, 71.247])
DECK_BOXES_LOCAL_MM = [  # (centre, half extents) in the deck STL frame (mm)
    ((0.0, 0.0, 56.75), (260.05, 184.45, 3.0)),        # lower rim plate z 53.75..59.75
    ((0.0, 0.0, 65.5), (249.1, 173.4, 5.75)),          # top plate z 59.75..71.25 (top = 142.5 above table)
] + [((sx * 216.1, sy * 140.4, -8.75), (22.5, 22.5, 62.5)) for sx in (-1, 1) for sy in (-1, 1)]  # feet
STOP_HALF_MM = (4.0, 4.0, 6.0)
DECK_TOP_OLD_MM = 142.5


def load_rail_old_mm(tier):
    return np.loadtxt(os.path.join(STL_ROOT, tier, "buzz_wire_centerline.csv"), delimiter=",", skiprows=2)


def stop_centers_old_mm(tier):
    import json
    d = json.load(open(os.path.join(STL_ROOT, tier, "layout.json")))
    out = []
    for part in d["parts"]:
        if part["name"].startswith("wire_wood_stop"):
            out.append(np.array(part["pose"]["table"]["position_mm"]))
    return out


def start_pose_old(tier):
    """Wand body pose at the start (loop centre, rotation) in the old table frame, metres.
    Same rest-pose formula as the old generator's endpoint_pose(route, 0) for the deck support, evaluated with the
    port's grip dimensions (the old layout.json start pose used the old grip)."""
    return rest_pose_old(tier, 0)


def rest_pose_old(tier, end):
    rail = load_rail_old_mm(tier) / 1000.0
    deck_xy = DECK_CENTER_OLD[:2] / 1000.0
    span = 2 * LOOP_R + STEM_LEN
    half = GRIP_HALF_T
    pitch = np.arctan2(half, span) - np.arcsin(TUBE_R / np.hypot(span, half))
    pt = rail[0 if end == 0 else -1]
    horizontal = np.r_[-(pt[:2] - deck_xy), 0.0]
    horizontal /= np.linalg.norm(horizontal)
    x = horizontal * np.cos(pitch) + np.array([0, 0, np.sin(pitch)])
    z = -horizontal * np.sin(pitch) + np.array([0, 0, np.cos(pitch)])
    R = Rotation.from_matrix(np.column_stack([x, np.cross(z, x), z]))
    p = pt.copy()
    p[2] = DECK_TOP_OLD_MM / 1000.0 + LOOP_R * np.sin(pitch) + TUBE_R + 0.00005
    return p, R


def finish_pose_old(tier):
    """endpoint_pose(route, 1) of the old generator for the deck-rest finish (metres, table frame)."""
    return rest_pose_old(tier, 1)


# YAM workstation colliders (workstation.usd, world frame): arm pedestal block, gate posts, top bar.
from scipy.spatial.transform import Rotation as _Rot
FRAME_BOXES = [(np.array([0.0, 0.0, 0.375]), np.array([0.2975, 0.65, 0.375]), _Rot.identity()),
               (np.array([0.0, 0.575, 1.2]), np.array([0.015, 0.015, 0.45]), _Rot.identity()),
               (np.array([0.0, -0.575, 1.2]), np.array([0.015, 0.015, 0.45]), _Rot.identity()),
               (np.array([0.0, 0.0, 1.665]), np.array([0.015, 0.59, 0.015]), _Rot.identity())]


class Layout:
    """Old table frame (mm) -> YAMLab world (m): p_w = Rz(yaw) p_old/1000 + t."""

    def __init__(self, yaw_deg=-90.0, t=(0.7645, 0.055679, TABLE_Z)):
        self.yaw_deg = float(yaw_deg)
        self.R = Rotation.from_euler("z", yaw_deg, degrees=True)
        self.t = np.asarray(t, float)

    def p(self, p_old_m):
        return self.R.apply(np.asarray(p_old_m, float)) + self.t

    def rot(self, R_old):
        return self.R * R_old

    def as_dict(self):
        return dict(yaw_deg=self.yaw_deg, translation_m=self.t.tolist(),
                    formula="p_world[m] = Rz(yaw) @ p_old_table[mm] / 1000 + translation")


class Scene:
    def __init__(self, tier="very_easy", layout=None):
        self.tier = tier
        self.L = layout or Layout()
        self.rail_old = load_rail_old_mm(tier) / 1000.0
        self.rail = self.L.p(self.rail_old)
        self.arc = np.r_[0.0, np.cumsum(np.linalg.norm(np.diff(self.rail, axis=0), axis=1))]
        p, R = start_pose_old(tier)
        self.start_p, self.start_R = self.L.p(p), self.L.rot(R)
        p, R = finish_pose_old(tier)
        self.finish_p, self.finish_R = self.L.p(p), self.L.rot(R)
        self.deck_center = self.L.p(DECK_CENTER_OLD / 1000.0)
        self.deck_top = TABLE_Z + DECK_TOP_OLD_MM / 1000.0
        self.deck_boxes = []  # (centre_world, half_extents_in_deck_frame, R_world)
        for c, h in DECK_BOXES_LOCAL_MM:
            cw = self.L.p((DECK_CENTER_OLD + np.array(c)) / 1000.0)
            self.deck_boxes.append((cw, np.array(h) / 1000.0, self.L.R))
        self.stops = [(self.L.p(c / 1000.0), np.array(STOP_HALF_MM) / 1000.0, self.L.R)
                      for c in stop_centers_old_mm(tier)]

    def tangents(self):
        d = np.gradient(self.rail, axis=0)
        return d / np.linalg.norm(d, axis=1, keepdims=True)


# ---------------------------------------------------------------- wand primitives
def wand_capsules():
    """[(a, b, r, role)] in the body frame (old tool_capsules), role 'metal'."""
    a = np.arange(LOOP_SEGMENTS) * 2 * np.pi / LOOP_SEGMENTS
    pts = np.c_[LOOP_R * np.cos(a), LOOP_R * np.sin(a), np.zeros_like(a)]
    caps = [(p, q, TUBE_R, "loop") for p, q in zip(pts, np.roll(pts, -1, axis=0))]
    caps.append((np.array([LOOP_R, 0, 0]), np.array([GRIP_X0, 0, 0]), TUBE_R, "stem"))
    return caps


def wand_metal_points(n_ring=256):
    """Dense centreline samples of ring + stem (for distance checks) with their tube radius."""
    a = np.linspace(0, 2 * np.pi, n_ring, endpoint=False)
    ring = np.c_[LOOP_R * np.cos(a), LOOP_R * np.sin(a), np.zeros_like(a)]
    stem = np.c_[np.linspace(LOOP_R, GRIP_X0, 12), np.zeros(12), np.zeros(12)]
    return np.r_[ring, stem]


def seg_point_dist(P, A, B):
    """Distances from points P (n,3) to segments A->B (m,3): returns (n,m)."""
    AB = B - A
    AP = P[:, None, :] - A[None, :, :]
    t = np.clip(np.einsum("nmk,mk->nm", AP, AB) / np.maximum(np.einsum("mk,mk->m", AB, AB), 1e-30), 0, 1)
    C = A[None] + t[..., None] * AB[None]
    return np.linalg.norm(P[:, None, :] - C, axis=-1)


def wand_wire_clearance(scene, p, R):
    """Min surface gap (m) between the wand metal (ring + stem capsules) and the wire capsules."""
    P = R.apply(wand_metal_points()) + p
    near = np.linalg.norm(scene.rail - p, axis=1) < 0.08
    idx = np.flatnonzero(near)
    if len(idx) == 0:
        return 1.0
    lo, hi = max(idx.min() - 1, 0), min(idx.max() + 1, len(scene.rail) - 1)
    d = seg_point_dist(P, scene.rail[lo:hi], scene.rail[lo + 1:hi + 1])
    return float(d.min() - TUBE_R - WIRE_R)


def aperture_crossings(points, center, normal, radius, tolerance=1e-9):
    """Copied from ref/topogym_2dafa5f/topogym/utils/geometry/passage.py (old task helper)."""
    p = np.asarray(points, float)
    c = np.asarray(center, float)
    n = np.asarray(normal, float)
    n = n / np.linalg.norm(n)
    d = (p - c) @ n
    away = np.flatnonzero(abs(d) > tolerance)
    hits, ambiguous = [], False
    for i in np.flatnonzero(abs(d) <= tolerance):
        if np.linalg.norm(p[i] - c) <= radius + tolerance:
            if i == 0 or i == len(p) - 1 or d[i - 1] * d[i + 1] >= 0 or abs(d[i - 1]) <= tolerance or abs(d[i + 1]) <= tolerance:
                ambiguous = True
    for i in range(len(p) - 1):
        if abs(d[i]) <= tolerance and abs(d[i + 1]) <= tolerance:
            edge = p[i + 1] - p[i]
            t = np.clip(np.dot(c - p[i], edge) / max(np.dot(edge, edge), 1e-30), 0, 1)
            ambiguous |= bool(np.linalg.norm(p[i] + t * edge - c) <= radius + tolerance)
    for left, right in zip(away[:-1], away[1:]):
        if d[left] * d[right] >= 0 or right - left > 2:
            continue
        t = -d[left] / (d[left + 1] - d[left])
        point = p[left] + t * (p[left + 1] - p[left])
        distance = np.linalg.norm(point - c)
        if abs(distance - radius) <= tolerance:
            ambiguous = True
        if distance < radius - tolerance:
            hits.append(dict(material_coordinate=float(left + t), sign=1 if d[right] > 0 else -1,
                             point_m=point.tolist()))
    return hits, bool(ambiguous)


def box_point_dist(P, center, half, R):
    """Signed-ish distance from points to an oriented box (positive outside, negative inside)."""
    L = R.inv().apply(P - center)
    q = np.abs(L) - half
    out = np.linalg.norm(np.maximum(q, 0), axis=1)
    inside = np.minimum(q.max(axis=1), 0)
    return out + inside
