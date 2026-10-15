"""RopeThreading geometry and the old success predicate (pure numpy).

Sources (RoboTangle, read-only worktree yamlab_port/ref/topogym_2dafa5f):
  - topogym/tasks/rope_threading/common.py   usable_rope_aperture_radius, RopeThreadingTask.evaluate_state
  - topogym/utils/geometry/passage.py         aperture_crossings (copied line for line below)
  - topogym/tasks/release_profile.py          release profile contact_relaxed_v16 (the STL package's scenes)
Scene data: src_data/<tier>/{layout.json, rope_start_centerline.csv, start_state.md} = copies of
tmp/2026-10-11_robotangle_v1_stl/rope_threading/<tier>/.

Frames: old table frame (mm, origin = tabletop centre, +Z up) -> YAMLab world (m):
    world_xy = Rz(yaw) @ old_xy / 1000 + t_xy,   world_z = TABLE_SUPPORT_Z + old_z / 1000.
"""
from __future__ import annotations

import json
import os
from pathlib import Path

import numpy as np

SRC = Path(__file__).resolve().parent / "src_data"
# Physical support height of YAMLab's table collider (resting bodies sit at 0.7500; nominal top 0.7517,
# measured by knot_untying). Old z is height above the tabletop, so the stands' bases rest on it.
TABLE_SUPPORT_Z = 0.7500
TUBE_RADIUS = 0.006        # ring tube radius (STL: outer 162 mm, aperture 138 mm -> R 75, tube 6 mm)
ROPE_RADIUS = 0.004
STAND_RADIUS = 0.005       # stand = capsule r 5 mm (old generator: trimesh capsule of the MJCF stand geom)

# Re-layout (chosen from the YAM reach study, see STATUS.md): yaw +90 deg, old +X -> world +Y,
# old +Y -> world -X (the rings come toward the arms, the rope's U bulges away from them).
RELAYOUT = {
    "easy": dict(yaw_deg=90.0, t_xy=(0.58, 0.0)),
    # medium (deviation D9, approved 2026-10-12): the old scene fits the table in no rotation, so the ring assembly and
    # the rope start are placed rigidly each. Values from tools/medium_layout_search.py --reverse (+ --refine): the
    # oracle feeds the start tip (R3 first); every stroke, both ready poses and the start tip's drag path are
    # reachable (checked as Runner.goto plans them: home -> ready -> first pinch); the rope start (the easy pose shifted
    # 5 cm to -y) keeps all stand bases inside its U, >= 63 mm clear. (t x 0.58 was tried: the right arm's drags then
    # leave too little overhang for the ledge grasp.)
    # 2026-10-13: fixed by the user (attempts B yaw 0 and C yaw 345 are in STATUS.md); R3 is fed, received, pulled and
    # kept, the R3 -> R2 transfer is open (STATUS.md "Medium attempt A").
    # 2026-10-14 (deviations D11 + D12, approved by the user): ring group yaw 15 at t (0.612, -0.351), rope start
    # mirrored (rope_mirror_deg) at rope_t (0.54, -0.0703); the oracle threads this layout (STATUS.md "Medium, D12").
    "medium": dict(yaw_deg=15.0, t_xy=(0.612, -0.351), rope_yaw_deg=90.0, rope_t_xy=(0.54, -0.0703), rope_mirror_deg=90.0),
}

# Exploration only: RT_RELAYOUT (JSON) updates RELAYOUT["medium"] (e.g. {"ring_adjust": {"R2": [0, 0, -20]}}); RT_ASSET_DIR
# (read by rope_threading_manager_cfg) points the env at the matching assets built with the same variable.
if os.environ.get("RT_RELAYOUT"):
    RELAYOUT["medium"].update(json.loads(os.environ["RT_RELAYOUT"]))

# Terminal thresholds. RELEASE = the release profile contact_relaxed_v16 of the released robotangle-r2 instances the
# STL package comes from (release_profile.py: max speed 1 cm/s, allowance 1 mm, round_ring profile): the task's
# success predicate. STRICT = the old class defaults (common.py: 1 mm/s, margin 0.1 mm, no allowance, cylindrical):
# logged as a diagnostic.
STRICT = dict(maximum_speed_m_s=0.001, aperture_margin_m=0.0001, allowance_m=0.0, profile="cylindrical")
RELEASE = dict(maximum_speed_m_s=0.01, aperture_margin_m=0.0001, allowance_m=0.001, profile="round_ring")
STABLE_DURATION_S = 0.5


# ------------------------------------------------------------------------------------------ scene
def load_layout(tier: str) -> dict:
    return json.loads((SRC / tier / "layout.json").read_text())


def rot2(yaw_deg):
    a = np.radians(yaw_deg)
    return np.array([[np.cos(a), -np.sin(a)], [np.sin(a), np.cos(a)]])


def to_world(tier: str, p_mm) -> np.ndarray:
    p = np.atleast_2d(np.asarray(p_mm, float)) / 1000.0
    cfg = RELAYOUT[tier]
    out = np.empty_like(p)
    out[:, :2] = p[:, :2] @ rot2(cfg["yaw_deg"]).T + np.asarray(cfg["t_xy"])
    out[:, 2] = TABLE_SUPPORT_Z + p[:, 2]
    return out


def dir_to_world(tier: str, v) -> np.ndarray:
    v = np.asarray(v, float)
    out = v.copy()
    out[:2] = rot2(RELAYOUT[tier]["yaw_deg"]) @ v[:2]
    return out / np.linalg.norm(out)


def ring_basis(n):
    n = np.asarray(n, float) / np.linalg.norm(n)
    h = np.array([0.0, 0.0, 1.0]) if abs(n[2]) < 0.9 else np.array([1.0, 0.0, 0.0])
    u = np.cross(h, n); u /= np.linalg.norm(u)
    v = np.cross(n, u)
    return u, v


def scene(tier: str) -> dict:
    """Rings (world centre, normal, R, tube), stands, bases and the required order, in YAM world (m)."""
    lay = load_layout(tier)
    rope = [x for x in lay["non_printable"] if x["name"] == "rope"][0]
    parts = {p["name"]: p for p in lay["parts"]}
    rings = []
    for r in rope["route"]["rings"]:
        name = r["name"]
        c = to_world(tier, parts[name]["pose"]["table"]["position_mm"])[0]
        n = dir_to_world(tier, r["normal"])
        R = r["aperture_diameter_mm"] / 2000.0 + TUBE_RADIUS
        stand = parts[name + "_stand"]["pose"]["table"]["position_mm"]
        base = parts[name + "_base"]["pose"]["table"]["position_mm"]
        ring = dict(name=name, center=c, normal=n, radius=R, tube=TUBE_RADIUS,
                    stand_center=to_world(tier, stand)[0], base_center=to_world(tier, base)[0])
        adj = RELAYOUT[tier].get("ring_adjust", {}).get(name)
        if adj:     # (dx, dy, rot_deg): ring, stand and base move together, rotated about the ring's vertical axis
            dx, dy, rot = adj; Rm = rot2(rot)
            for k in ("stand_center", "base_center"):
                ring[k] = ring[k].copy(); ring[k][:2] = c[:2] + Rm @ (ring[k][:2] - c[:2]) + (dx, dy)
            ring["normal"] = ring["normal"].copy(); ring["normal"][:2] = Rm @ ring["normal"][:2]
            ring["center"] = c.copy(); ring["center"][:2] += (dx, dy)
            ring["base_yaw_deg"] = RELAYOUT[tier]["yaw_deg"] + rot
        rings.append(ring)
    order = [(e[:-1], 1 if e[-1] == "+" else -1) for e in rope["route"]["order"]]
    return dict(rings=rings, order=order, rope_length=rope["length_mm"] / 1000.0,
                rope_radius=rope["diameter_mm"] / 2000.0, material=rope["sim_material"])


# Stand / base sizes (STL extents): every stand is a vertical capsule r 5 mm whose lower end sits at
# z = 4.897 mm (inside the 8 mm base), so its total length = 2 (z_centre - 4.897 mm): R1 332, R2 311, R3 281 mm
# (= R*_stand.stl z extents). Bases: 50 (old x) x 80 (old y) x 8 mm boxes, axis-aligned in the old frame.
STAND_BOTTOM_OLD_Z = 0.004897
BASE_SIZE_OLD = (0.050, 0.080, 0.008)


def stand_length(stand_center_world_z: float) -> float:
    return 2.0 * (stand_center_world_z - TABLE_SUPPORT_Z - STAND_BOTTOM_OLD_Z)


def start_centerline_world(tier: str) -> np.ndarray:
    """Rope start in world. A tier may give the rope start its own rigid placement (`rope_yaw_deg`, `rope_t_xy`:
    world_xy = Rz(rope_yaw) old_xy + rope_t), when the old scene does not fit the YAM tabletop (medium); the rope
    shape is unchanged. `rope_mirror_deg` (deviation D11) first reflects the old xy across the line through the origin
    at that angle (the U's symmetry axis): same shape, point order and predicate, mirrored left <-> right."""
    p = np.loadtxt(SRC / tier / "rope_start_centerline.csv", delimiter=",", skiprows=2)
    cfg = RELAYOUT[tier]
    if "rope_yaw_deg" not in cfg:
        return to_world(tier, p)
    q = p / 1000.0
    out = np.empty_like(q)
    xy = q[:, :2]
    if "rope_mirror_deg" in cfg:
        a2 = np.radians(2.0 * cfg["rope_mirror_deg"])
        xy = xy @ np.array([[np.cos(a2), np.sin(a2)], [np.sin(a2), -np.cos(a2)]]).T
    out[:, :2] = xy @ rot2(cfg["rope_yaw_deg"]).T + np.asarray(cfg["rope_t_xy"])
    out[:, 2] = TABLE_SUPPORT_Z + q[:, 2]
    return out


# ------------------------------------------------------------------------------------------ predicate
def aperture_crossings(points, center, normal, radius, *, tolerance=1e-9):
    """Copied from topogym/utils/geometry/passage.py (line-for-line equivalent).

    Open polyline hits, with no artificial closure or signed cancellation.
    Tangencies/coplanar runs touching the aperture are reported as ambiguous.
    Radius is the usable aperture after tube/rope/clearance margins.
    """
    p = np.asarray(points, float)
    c = np.asarray(center, float)
    n = np.asarray(normal, float)
    if len(p) < 2 or c.shape != (3,) or n.shape != (3,) or not np.isfinite(np.r_[c, n, radius, tolerance]).all():
        raise ValueError("Invalid aperture")
    if radius <= 0 or tolerance <= 0 or np.linalg.norm(n) <= 1e-12:
        raise ValueError("Invalid aperture dimensions")
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


def usable_rope_aperture_radius(ring_radius, tube_radius, rope_radius, margin, allowance=0.0, *,
                                axial_offset_m=0.0, profile="cylindrical"):
    """Copied from topogym/tasks/rope_threading/common.py (same arithmetic)."""
    if not 0 <= allowance <= 0.5 * rope_radius:
        raise ValueError("aperture_contact_allowance_m must be between zero and half the rope radius")
    if abs(axial_offset_m) > tube_radius:
        raise ValueError("Aperture slice must lie within the ring tube thickness")
    expanded_tube = tube_radius + rope_radius - allowance
    if profile == "round_ring":
        expanded_tube = np.sqrt(expanded_tube ** 2 - axial_offset_m ** 2)
    return ring_radius - expanded_tube - margin


def threading_check(points, rings, order, rope_radius=ROPE_RADIUS, params=STRICT):
    """Geometric part of RopeThreadingTask.evaluate_state on the centreline `points` (material order).

    Returns (threaded, diag): threaded = crossing sequence == order and thickness clear and not ambiguous."""
    hits, ambiguous, thickness_ok = [], False, True
    per_ring = {}
    for ring in rings:
        c, n = np.asarray(ring["center"]), np.asarray(ring["normal"])
        radius = usable_rope_aperture_radius(ring["radius"], ring["tube"], rope_radius, params["aperture_margin_m"],
                                             params["allowance_m"])
        crossings, uncertain = aperture_crossings(points, c, n, radius)
        nominal, _ = aperture_crossings(points, c, n, ring["radius"] - ring["tube"])
        ok_r = len(nominal) == len(crossings)
        ambiguous |= uncertain
        for offset in (-ring["tube"], ring["tube"]):
            sr = usable_rope_aperture_radius(ring["radius"], ring["tube"], rope_radius, params["aperture_margin_m"],
                                             params["allowance_m"], axial_offset_m=offset, profile=params["profile"])
            boundary, unsure = aperture_crossings(points, c + offset * n, n, sr)
            ambiguous |= unsure
            ok_r &= [h["sign"] for h in boundary] == [h["sign"] for h in crossings]
        thickness_ok &= ok_r
        per_ring[ring["name"]] = dict(n_hits=len(crossings), n_nominal=len(nominal), thickness_clear=bool(ok_r),
                                      radial_m=[float(np.linalg.norm(np.asarray(h["point_m"]) - c)) for h in crossings])
        hits.extend(dict(h, ring=ring["name"]) for h in crossings)
    hits.sort(key=lambda h: h["material_coordinate"])
    sequence = [(h["ring"], h["sign"]) for h in hits]
    threaded = bool(sequence == list(order) and thickness_ok and not ambiguous)
    return threaded, dict(crossing_sequence=[f"{r}{'+' if s > 0 else '-'}" for r, s in sequence],
                          crossing_material_coordinates=[h["material_coordinate"] for h in hits],
                          ambiguous=bool(ambiguous), thickness_clear=bool(thickness_ok), per_ring=per_ring)


def ring_route_points(points, rings):
    """Diagnostic: per ring, signed axial distance of every point (for progress plots)."""
    return {r["name"]: (np.asarray(points) - r["center"]) @ r["normal"] for r in rings}
