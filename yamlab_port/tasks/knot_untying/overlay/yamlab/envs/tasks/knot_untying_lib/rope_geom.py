"""Pure-numpy rope geometry for the YAMLab knot_untying port.

- Old start centreline (table frame, mm) -> YAM world (m) re-layout.
- Capsule-chain discretisation (equal chords).
- Top-view crossing analysis with over/under order.
- The old success predicate: planar_clearance + on_table + quiet + intact.

planar_clearance / segment_distance_2d are copied from
ref/topogym_2dafa5f/topogym/utils/geometry/passage.py (RoboTangle, read-only worktree)
and kept line-for-line equivalent.
"""
from __future__ import annotations

import json
from pathlib import Path

import numpy as np

# copies of tmp/2026-10-11_robotangle_v1_stl/knot_untying/<tier>/{rope_start_centerline.csv,layout.json,start_state.md}
STL_ROOT = Path(__file__).resolve().parent / "src_data"
TABLE_Z = 0.7517          # YAMLab table top (configs/robot/yam.yaml table.position z)
ROPE_RADIUS = 0.004       # 8 mm rope
ROPE_RHO = 650.0          # kg/m3

# Old predicate thresholds (tasks/knot_untying/common.py, terminal_v5)
MAX_SPEED = 0.001         # m/s
TABLE_CLEARANCE = 0.003   # z.max <= table + 2r + 3 mm
PENETRATION_TOL = 0.001   # z.min >= table - 1 mm
STABLE_DURATION_S = 0.5

# Re-layout per tier: old table frame (mm, +X toward ALOHA right arm, +Y away from the
# ALOHA bases) -> YAM world (m). Rotation yaw -90 deg: old +Y (loop side) -> YAM +X (away
# from the YAM bases), old +X -> YAM -Y. The old bounding-box centre goes to `center_xy`.
RELAYOUT = {
    "very_easy": dict(yaw_deg=-90.0, center_xy=(0.56, 0.0)),
    "easier": dict(yaw_deg=-90.0, center_xy=(0.56, 0.0)),
    "easy": dict(yaw_deg=-90.0, center_xy=(0.56, 0.0)),
    "medium": dict(yaw_deg=-90.0, center_xy=(0.56, 0.0)),
}


def load_old_centerline(tier: str) -> np.ndarray:
    p = np.loadtxt(STL_ROOT / tier / "rope_start_centerline.csv", delimiter=",", skiprows=2)
    return p / 1000.0


def relayout_transform(tier: str, old_mm: np.ndarray | None = None):
    """Return (R2, t2) such that world_xy = R2 @ old_xy_m + t2; world_z = TABLE_Z + old_z_m."""
    cfg = RELAYOUT[tier]
    old = load_old_centerline(tier) if old_mm is None else old_mm
    c_old = 0.5 * (old[:, :2].min(0) + old[:, :2].max(0))
    a = np.deg2rad(cfg["yaw_deg"])
    R2 = np.array([[np.cos(a), -np.sin(a)], [np.sin(a), np.cos(a)]])
    t2 = np.asarray(cfg["center_xy"]) - R2 @ c_old
    return R2, t2


def to_world(tier: str, old_m: np.ndarray) -> np.ndarray:
    R2, t2 = relayout_transform(tier)
    out = np.empty_like(old_m)
    out[:, :2] = old_m[:, :2] @ R2.T + t2
    out[:, 2] = TABLE_Z + old_m[:, 2]
    return out


def chord_walk(curve: np.ndarray, d: float, n: int) -> np.ndarray:
    """n+1 points on the polyline `curve`, consecutive points exactly `d` apart (chord)."""
    pts = [curve[0]]
    seg = 0
    cur = curve[0]
    for _ in range(n):
        # find the first polyline point beyond distance d from cur, then intersect the sphere
        while True:
            if seg + 1 >= len(curve):
                # extrapolate along last direction
                v = curve[-1] - curve[-2]
                v /= np.linalg.norm(v)
                nxt = cur + d * v
                break
            a, b = (cur if np.linalg.norm(curve[seg] - cur) < 1e-12 else curve[seg]), curve[seg + 1]
            if np.linalg.norm(b - cur) >= d:
                # solve |a + t (b - a) - cur| = d for t in [0,1], largest root
                ab = b - a
                ac = a - cur
                A = ab @ ab
                B = 2 * ab @ ac
                C = ac @ ac - d * d
                disc = max(B * B - 4 * A * C, 0.0)
                t = (-B + np.sqrt(disc)) / (2 * A)
                nxt = a + np.clip(t, 0, 1) * ab
                break
            seg += 1
        pts.append(nxt)
        cur = nxt
        # make sure the next search starts at the segment holding `cur`
    return np.asarray(pts)


def chain_from_tier(tier: str, n_links: int):
    """Joint points (n+1,3) in world, link length d."""
    old = load_old_centerline(tier)
    L = np.linalg.norm(np.diff(old, axis=0), axis=1).sum()
    d = L / n_links
    world = to_world(tier, old)
    pts = chord_walk(world, d, n_links)
    return pts, d, L


def link_frames(pts: np.ndarray):
    """Centres (n,3) and quaternions wxyz (n,4) with local +X along p_i -> p_{i+1}, minimal twist."""
    n = len(pts) - 1
    centres = 0.5 * (pts[:-1] + pts[1:])
    quats = np.zeros((n, 4))
    prev_R = None
    for i in range(n):
        x = pts[i + 1] - pts[i]
        x /= np.linalg.norm(x)
        if prev_R is None:
            up = np.array([0.0, 0.0, 1.0])
            y = np.cross(up, x)
            if np.linalg.norm(y) < 1e-6:
                y = np.array([0.0, 1.0, 0.0])
            y /= np.linalg.norm(y)
            z = np.cross(x, y)
            R = np.column_stack((x, y, z))
        else:
            # parallel transport of previous frame onto new tangent (no twist)
            x0 = prev_R[:, 0]
            R_rel = _rot_between(x0, x)
            R = R_rel @ prev_R
        prev_R = R
        quats[i] = mat_to_quat(R)
    return centres, quats


def _rot_between(a, b):
    a = a / np.linalg.norm(a)
    b = b / np.linalg.norm(b)
    v = np.cross(a, b)
    c = float(a @ b)
    if np.linalg.norm(v) < 1e-12:
        return np.eye(3)
    vx = np.array([[0, -v[2], v[1]], [v[2], 0, -v[0]], [-v[1], v[0], 0]])
    return np.eye(3) + vx + vx @ vx * (1.0 / (1.0 + c))


def mat_to_quat(R):
    tr = np.trace(R)
    if tr > 0:
        s = np.sqrt(tr + 1.0) * 2
        w = 0.25 * s
        x = (R[2, 1] - R[1, 2]) / s
        y = (R[0, 2] - R[2, 0]) / s
        z = (R[1, 0] - R[0, 1]) / s
    elif R[0, 0] > R[1, 1] and R[0, 0] > R[2, 2]:
        s = np.sqrt(1.0 + R[0, 0] - R[1, 1] - R[2, 2]) * 2
        w = (R[2, 1] - R[1, 2]) / s
        x = 0.25 * s
        y = (R[0, 1] + R[1, 0]) / s
        z = (R[0, 2] + R[2, 0]) / s
    elif R[1, 1] > R[2, 2]:
        s = np.sqrt(1.0 + R[1, 1] - R[0, 0] - R[2, 2]) * 2
        w = (R[0, 2] - R[2, 0]) / s
        x = (R[0, 1] + R[1, 0]) / s
        y = 0.25 * s
        z = (R[1, 2] + R[2, 1]) / s
    else:
        s = np.sqrt(1.0 + R[2, 2] - R[0, 0] - R[1, 1]) * 2
        w = (R[1, 0] - R[0, 1]) / s
        x = (R[0, 2] + R[2, 0]) / s
        y = (R[1, 2] + R[2, 1]) / s
        z = 0.25 * s
    q = np.array([w, x, y, z])
    return q / np.linalg.norm(q)


def quat_to_mat(q):
    q = np.asarray(q, float)
    w, x, y, z = q[..., 0], q[..., 1], q[..., 2], q[..., 3]
    R = np.empty(q.shape[:-1] + (3, 3))
    R[..., 0, 0] = 1 - 2 * (y * y + z * z)
    R[..., 0, 1] = 2 * (x * y - w * z)
    R[..., 0, 2] = 2 * (x * z + w * y)
    R[..., 1, 0] = 2 * (x * y + w * z)
    R[..., 1, 1] = 1 - 2 * (x * x + z * z)
    R[..., 1, 2] = 2 * (y * z - w * x)
    R[..., 2, 0] = 2 * (x * z - w * y)
    R[..., 2, 1] = 2 * (y * z + w * x)
    R[..., 2, 2] = 1 - 2 * (x * x + y * y)
    return R


def chain_points_from_links(pos, quat, d):
    """From link centres/quats (n,3)/(n,4): joint points estimated from both sides.

    Returns (joints (n+1,3) [averaged], gaps (n-1,) distance between the two estimates of
    each interior joint)."""
    R = quat_to_mat(quat)
    ax = R[:, :, 0]
    tail = pos - 0.5 * d * ax
    head = pos + 0.5 * d * ax
    gaps = np.linalg.norm(head[:-1] - tail[1:], axis=1)
    joints = np.vstack((tail[:1], 0.5 * (head[:-1] + tail[1:]), head[-1:]))
    return joints, gaps


def stations_points(pos, quat, d):
    """Material stations = end point, link centres, end point (as the brief asks)."""
    joints, _ = chain_points_from_links(pos, quat, d)
    pts = np.vstack((joints[:1], pos, joints[-1:]))
    n = len(pos)
    s = np.r_[0.0, (np.arange(n) + 0.5) * d, n * d]
    return pts, s


# ---------------------------------------------------------------- old predicate helpers
def segment_distance_2d(a, b, c, d):
    a, b, c, d = (np.asarray(x, float) for x in (a, b, c, d))

    def cross(u, v):
        return u[0] * v[1] - u[1] * v[0]

    u, v = b - a, d - c
    den = cross(u, v)
    if abs(den) > 1e-15:
        t, s = cross(c - a, v) / den, cross(c - a, u) / den
        if 0 <= t <= 1 and 0 <= s <= 1:
            return 0.0

    def point_segment(p, x, y):
        edge = y - x
        t = np.clip(np.dot(p - x, edge) / max(np.dot(edge, edge), 1e-30), 0, 1)
        return np.linalg.norm(p - (x + t * edge))

    return min(point_segment(a, c, d), point_segment(b, c, d), point_segment(c, a, b), point_segment(d, a, b))


def planar_clearance(points, material_s, diameter):
    p = np.asarray(points, float)
    s = np.asarray(material_s, float)
    if len(p) < 2 or s.shape != (len(p),) or not np.isfinite(s).all() or np.any(np.diff(s) <= 0) or not np.isfinite(diameter) or diameter <= 0:
        raise ValueError("Invalid planar rope/material coordinates")
    if np.any(np.linalg.norm(np.diff(p[:, :2], axis=0), axis=1) < 1e-9):
        return False, dict(projected_degenerate=True, minimum_nonlocal_distance_m=None)
    edges = np.diff(p[:, :2], axis=0)
    for a, b in zip(edges[:-1], edges[1:]):
        cross = a[0] * b[1] - a[1] * b[0]
        if abs(cross) <= 1e-12 * np.linalg.norm(a) * np.linalg.norm(b) and np.dot(a, b) < 0:
            return False, dict(projected_degenerate=True, minimum_nonlocal_distance_m=0.0)
    minimum = None
    for i in range(len(p) - 1):
        for j in range(i + 2, len(p) - 1):
            distance = segment_distance_2d(*p[i:i + 2, :2], *p[j:j + 2, :2])
            if distance < 1e-10:
                return False, dict(projected_degenerate=False, minimum_nonlocal_distance_m=0.0)
            if s[j] - s[i + 1] < 2 * diameter:
                continue
            minimum = distance if minimum is None else min(minimum, distance)
    return minimum is None or minimum >= diameter, dict(projected_degenerate=False, minimum_nonlocal_distance_m=minimum)


def crossings(points, s=None):
    """Top-view crossings of the polyline. Returns list of dict(i, j, ti, tj, si, sj, zi, zj, xy, first_over)."""
    p = np.asarray(points, float)
    if s is None:
        s = np.r_[0, np.cumsum(np.linalg.norm(np.diff(p, axis=0), axis=1))]
    out = []
    n = len(p) - 1
    for i in range(n):
        a, b = p[i, :2], p[i + 1, :2]
        u = b - a
        for j in range(i + 2, n):
            c, dd = p[j, :2], p[j + 1, :2]
            v = dd - c
            den = u[0] * v[1] - u[1] * v[0]
            if abs(den) < 1e-15:
                continue
            w = c - a
            ti = (w[0] * v[1] - w[1] * v[0]) / den
            tj = (w[0] * u[1] - w[1] * u[0]) / den
            if 0 <= ti < 1 and 0 <= tj < 1:
                zi = p[i, 2] + ti * (p[i + 1, 2] - p[i, 2])
                zj = p[j, 2] + tj * (p[j + 1, 2] - p[j, 2])
                out.append(dict(i=i, j=j, ti=ti, tj=tj,
                                si=float(s[i] + ti * (s[i + 1] - s[i])), sj=float(s[j] + tj * (s[j + 1] - s[j])),
                                zi=float(zi), zj=float(zj), xy=(a + ti * u).tolist(), first_over=bool(zi > zj)))
    return out


def over_under_sequence(cr):
    passes = []
    for c in cr:
        passes.append((c["si"], "O" if c["first_over"] else "U"))
        passes.append((c["sj"], "U" if c["first_over"] else "O"))
    return [x for _, x in sorted(passes)]


def expected_knot(tier: str):
    lay = json.loads((STL_ROOT / tier / "layout.json").read_text())
    rope = [x for x in lay["non_printable"] if x["name"] == "rope"][0]
    return rope["knot"]


def evaluate(pos, quat, lin_vel, ang_vel, d, radius=ROPE_RADIUS, table_z=TABLE_Z, gap_limit=0.001,
             max_speed=MAX_SPEED, table_clearance=TABLE_CLEARANCE, penetration_tol=PENETRATION_TOL,
             prev_points=None, dt=None):
    """Old evaluate_state on chain state (numpy, single env). Returns (ok, diag).

    Speed: if prev_points/dt are given, the point speed is the finite difference of the material
    points (link ends + centres, see material_points) over dt (= one control step). PhysX's reported
    link velocities carry ~1 cm/s TGS noise while positions are still (probes/sw4), and the old IPC
    velocity is itself a per-step displacement / dt. Without history the speed is reported as
    unavailable and quiet is False. The reported-velocity max is kept as a diagnostic."""
    pts, s = stations_points(pos, quat, d)
    clear, geom = planar_clearance_fast(pts, s, 2 * radius)
    joints, gaps = chain_points_from_links(pos, quat, d)
    zs = np.r_[joints[:, 2], pos[:, 2]]
    zmin, zmax = zs.min() - radius, zs.max() + radius
    on_table = bool(zmin >= table_z - penetration_tol and zmax <= table_z + 2 * radius + table_clearance)
    # point speeds: link centres + both ends of every link (v + w x r)
    R = quat_to_mat(quat)
    arm = 0.5 * d * R[:, :, 0]
    v_head = lin_vel + np.cross(ang_vel, arm)
    v_tail = lin_vel - np.cross(ang_vel, arm)
    rep = np.linalg.norm(np.vstack((lin_vel, v_head, v_tail)), axis=1)
    cur_points = np.vstack((joints, pos))
    if prev_points is not None and dt:
        speeds = np.linalg.norm(cur_points - prev_points, axis=1) / dt
    else:
        speeds = np.array([np.inf])
    quiet = bool(speeds.max() <= max_speed)
    intact = bool(np.isfinite(pos).all() and np.isfinite(quat).all() and (len(gaps) == 0 or gaps.max() <= gap_limit))
    cr = crossings_fast(joints)
    ok = bool(clear and on_table and quiet and intact)
    return ok, dict(planar_clear=bool(clear), on_table=on_table, quiet=quiet, intact=intact,
                    minimum_nonlocal_distance_m=geom.get("minimum_nonlocal_distance_m"),
                    projected_degenerate=geom.get("projected_degenerate"),
                    z_min_surface_above_table_m=float(zmin - table_z), z_max_surface_above_table_m=float(zmax - table_z),
                    maximum_speed_m_s=float(speeds.max()), p99_speed_m_s=float(np.quantile(speeds, 0.99)),
                    reported_velocity_max_m_s=float(rep.max()),
                    max_joint_gap_m=float(gaps.max()) if len(gaps) else 0.0,
                    n_crossings=len(cr), over_under=over_under_sequence(cr))


# ---------------------------------------------------------------- vectorised equivalents (per-step use)
def _pair_segment_distance_2d(A, B, C, D):
    """Vectorised segment_distance_2d over broadcast arrays (..., 2)."""
    def cross(u, v):
        return u[..., 0] * v[..., 1] - u[..., 1] * v[..., 0]
    u, v = B - A, D - C
    den = cross(u, v)
    w = C - A
    with np.errstate(divide="ignore", invalid="ignore"):
        t = cross(w, v) / den
        s = cross(w, u) / den
    inter = (np.abs(den) > 1e-15) & (t >= 0) & (t <= 1) & (s >= 0) & (s <= 1)

    def ps(P, X, Y):
        e = Y - X
        tt = np.clip(np.sum((P - X) * e, -1) / np.maximum(np.sum(e * e, -1), 1e-30), 0, 1)
        return np.linalg.norm(P - (X + tt[..., None] * e), axis=-1)
    dist = np.minimum(np.minimum(ps(A, C, D), ps(B, C, D)), np.minimum(ps(C, A, B), ps(D, A, B)))
    return np.where(inter, 0.0, dist)


def planar_clearance_fast(points, material_s, diameter):
    """Same result as planar_clearance (checked in test_geom.py), vectorised."""
    p = np.asarray(points, float)
    s = np.asarray(material_s, float)
    if len(p) < 2 or s.shape != (len(p),) or not np.isfinite(s).all() or np.any(np.diff(s) <= 0) or not np.isfinite(diameter) or diameter <= 0:
        raise ValueError("Invalid planar rope/material coordinates")
    if np.any(np.linalg.norm(np.diff(p[:, :2], axis=0), axis=1) < 1e-9):
        return False, dict(projected_degenerate=True, minimum_nonlocal_distance_m=None)
    e = np.diff(p[:, :2], axis=0)
    a, b = e[:-1], e[1:]
    cr = a[:, 0] * b[:, 1] - a[:, 1] * b[:, 0]
    if np.any((np.abs(cr) <= 1e-12 * np.linalg.norm(a, axis=1) * np.linalg.norm(b, axis=1)) & (np.sum(a * b, 1) < 0)):
        return False, dict(projected_degenerate=True, minimum_nonlocal_distance_m=0.0)
    m = len(p) - 1
    I, J = np.triu_indices(m, k=2)
    dist = _pair_segment_distance_2d(p[I, :2], p[I + 1, :2], p[J, :2], p[J + 1, :2])
    if np.any(dist < 1e-10):
        return False, dict(projected_degenerate=False, minimum_nonlocal_distance_m=0.0)
    keep = ~(s[J] - s[I + 1] < 2 * diameter)
    minimum = float(dist[keep].min()) if keep.any() else None
    return minimum is None or minimum >= diameter, dict(projected_degenerate=False, minimum_nonlocal_distance_m=minimum)


def crossings_fast(points):
    p = np.asarray(points, float)
    s = np.r_[0, np.cumsum(np.linalg.norm(np.diff(p, axis=0), axis=1))]
    m = len(p) - 1
    I, J = np.triu_indices(m, k=2)
    u = p[I + 1, :2] - p[I, :2]
    v = p[J + 1, :2] - p[J, :2]
    w = p[J, :2] - p[I, :2]
    den = u[:, 0] * v[:, 1] - u[:, 1] * v[:, 0]
    with np.errstate(divide="ignore", invalid="ignore"):
        ti = (w[:, 0] * v[:, 1] - w[:, 1] * v[:, 0]) / den
        tj = (w[:, 0] * u[:, 1] - w[:, 1] * u[:, 0]) / den
    hit = (np.abs(den) >= 1e-15) & (ti >= 0) & (ti < 1) & (tj >= 0) & (tj < 1)
    out = []
    for k in np.flatnonzero(hit):
        i, j = I[k], J[k]
        zi = p[i, 2] + ti[k] * (p[i + 1, 2] - p[i, 2])
        zj = p[j, 2] + tj[k] * (p[j + 1, 2] - p[j, 2])
        out.append(dict(i=int(i), j=int(j), ti=float(ti[k]), tj=float(tj[k]),
                        si=float(s[i] + ti[k] * (s[i + 1] - s[i])), sj=float(s[j] + tj[k] * (s[j + 1] - s[j])),
                        zi=float(zi), zj=float(zj), xy=(p[i, :2] + ti[k] * u[k]).tolist(), first_over=bool(zi > zj)))
    return out


def joint_positions_from_links(quats, joint_names):
    """PhysX spherical-joint coordinates (measured convention, probe_joints.py: err 1.8e-7 m):
    joint 'j_iii:k' = k-th (x,y,z) component of the rotation vector of conj(q_i) * q_{i+1}."""
    from scipy.spatial.transform import Rotation as Rot
    q = np.asarray(quats)[:, [1, 2, 3, 0]]
    out = np.zeros(len(joint_names))
    for k, name in enumerate(joint_names):
        base, ax = name.split(":")
        i = int(base[2:])
        out[k] = (Rot.from_quat(q[i]).inv() * Rot.from_quat(q[i + 1])).as_rotvec()[int(ax)]
    return out


def material_points(pos, quat, d):
    """Link end points and centres (the points whose speed the quiet check bounds)."""
    return np.vstack((chain_points_from_links(pos, quat, d)[0], pos))
