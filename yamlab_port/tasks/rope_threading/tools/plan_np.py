"""Numpy-only planning helpers shared by the oracle and offline probes (no Isaac / torch)."""
import numpy as np
import yam_kin as K
from reach_map import seeds_for

TABLE = 0.75
TABLE_X = (0.3025, 0.8975)       # workstation.usd table_surface collider (not the nominal yam.yaml extents)
TABLE_Y = 0.65
EX, EY, EZ = np.eye(3)
# gripper + wrist + camera envelope in the TCP frame (x approach, y jaw, z along the pads; camera on +z, behind)
GB = np.array([[x, y, z] for x in np.linspace(-0.13, 0.04, 6) for y in np.linspace(-0.07, 0.07, 5)
               for z in np.linspace(-0.035, 0.10, 5)])


def frame(approach, jaw_hint, pos=None):
    a = np.asarray(approach, float); a = a / np.linalg.norm(a)
    j = np.asarray(jaw_hint, float); j = j - a * (a @ j); j = j / np.linalg.norm(j)
    T = np.eye(4); T[:3, :3] = np.c_[a, j, np.cross(a, j)]
    if pos is not None:
        T[:3, 3] = pos
    return T


def frame_az(approach, z_dir, pos=None):
    a = np.asarray(approach, float); a = a / np.linalg.norm(a)
    z = np.asarray(z_dir, float); z = z - a * (a @ z); z = z / np.linalg.norm(z)
    return frame(a, np.cross(z, a), pos)


def pitched(h, deg):
    pr = np.radians(deg)
    return np.cos(pr) * np.asarray(h, float) + np.array([0, 0, -np.sin(pr)])


def grip_T(approach, z_dir, gp, offset):
    T = frame_az(approach, z_dir)
    T[:3, 3] = gp - T[:3, :3] @ offset
    return T


def finger_low_z(T):
    pts = [T[:3, 3] + T[:3, :3] @ np.array([x, y, z]) for x in (-0.037, 0.037) for y in (-0.07, 0.07) for z in (-0.035, 0.035)]
    return min(p[2] for p in pts)


def gripper_clearance(Ta, Tb):
    pa = Ta[:3, 3] + GB @ Ta[:3, :3].T
    pb = Tb[:3, 3] + GB @ Tb[:3, :3].T
    return float(np.min(np.linalg.norm(pa[:, None] - pb[None], axis=2)))


def solve(side, T, q_seed=None, margin=0.05):
    Tb = K.world_to_base(T, side)
    seeds = ([q_seed] if q_seed is not None else []) + seeds_for(Tb[:3, 3])
    for sd in seeds:
        q, ok, ep, er = K.ik(Tb, sd, iters=200, margin=margin)
        if ok:
            return q
    return None


def polyline_station(P, from_tip):
    """P: centreline points in material order (start -> end tip). Point + unit tangent toward the end tip."""
    P = P[::-1]
    s = np.r_[0, np.cumsum(np.linalg.norm(np.diff(P, axis=0), axis=1))]
    i = int(np.searchsorted(s, from_tip)); i = min(max(i, 1), len(P) - 1)
    f = (from_tip - s[i - 1]) / (s[i] - s[i - 1])
    pt = P[i - 1] + f * (P[i] - P[i - 1])
    t = P[i - 1] - P[i]
    return pt, t / np.linalg.norm(t)


APPROACHES = {"down": -EZ}
for nm, h in (("+x", EX), ("-x", -EX), ("+y", EY), ("-y", -EY)):
    for p in (0, 30, 45, 60, 75):
        APPROACHES[f"{nm}p{p}"] = pitched(h, p)


# ------------------------------------------------------------------ crude collision model (capsules)
def seg_seg_dist(P1, Q1, P2, Q2):
    """Pairwise distances between segments P1Q1 (n,3) and P2Q2 (m,3) -> (n,m). Ericson's clamped closest points."""
    P1, Q1, P2, Q2 = (np.asarray(x, float) for x in (P1, Q1, P2, Q2))
    d1 = (Q1 - P1)[:, None, :]; d2 = (Q2 - P2)[None, :, :]
    r = P1[:, None, :] - P2[None, :, :]
    a = np.sum(d1 * d1, -1); e = np.sum(d2 * d2, -1); f = np.sum(d2 * r, -1)
    c = np.sum(d1 * r, -1); b = np.sum(d1 * d2, -1)
    den = a * e - b * b
    s = np.where(den > 1e-12, np.clip((b * f - c * e) / np.maximum(den, 1e-12), 0, 1), 0.0)
    t = (b * s + f) / np.maximum(e, 1e-12)
    t_c = np.clip(t, 0, 1)
    s = np.where(t < 0, np.clip(-c / np.maximum(a, 1e-12), 0, 1), np.where(t > 1, np.clip((b - c) / np.maximum(a, 1e-12), 0, 1), s))
    c1 = P1[:, None, :] + d1 * s[..., None]
    c2 = P2[None, :, :] + d2 * t_c[..., None]
    return np.linalg.norm(c1 - c2, axis=-1)


def fixture_capsules(rings, n_seg=24, stand_radius=0.005):
    A, B, Rr = [], [], []
    for rg in rings:
        n = np.asarray(rg["normal"], float); h = np.array([0, 0, 1.0]) if abs(n[2]) < 0.9 else np.array([1.0, 0, 0])
        u = np.cross(h, n); u /= np.linalg.norm(u); v = np.cross(n, u)
        th = np.arange(n_seg + 1) * 2 * np.pi / n_seg
        pts = np.asarray(rg["center"]) + rg["radius"] * (np.cos(th)[:, None] * u + np.sin(th)[:, None] * v)
        A += list(pts[:-1]); B += list(pts[1:]); Rr += [rg["tube"]] * n_seg
        sc = np.asarray(rg["stand_center"], float)
        top = 2 * sc[2] - TABLE - 0.0049
        A.append(np.array([sc[0], sc[1], TABLE + 0.005])); B.append(np.array([sc[0], sc[1], top])); Rr.append(stand_radius)
    return np.array(A), np.array(B), np.array(Rr)


ARM_R = (0.045, 0.040, 0.040, 0.038)


def arm_capsules(side, q, grip_open=True):
    """Upper arm, forearm, wrist pieces, and the gripper (link_6 -> fingertips, plus the jaw span) in world."""
    Ts = [K.base_to_world(T, side) for T in K.fk_all(np.asarray(q, float))]
    T6 = Ts[5]
    Tt = T6 @ K.T6_TCP
    o = [T[:3, 3] for T in Ts]
    a, j = Tt[:3, 0], Tt[:3, 1]
    tips = Tt[:3, 3] + 0.037 * a
    half = 0.06 if grip_open else 0.02
    A = [o[1], o[2], o[3], o[4], T6[:3, 3], tips - half * j]
    B = [o[2], o[3], o[4], o[5], Tt[:3, 3] - 0.03 * a, tips + half * j]
    R = list(ARM_R) + [0.045, 0.012]
    return np.array(A), np.array(B), np.array(R)


def arm_clearance(side, q, fix, other=None, grip_open=True):
    """Min surface clearance of arm `side` at q to the fixtures, the table and (optionally) the other arm (side, q)."""
    A, B, Rr = arm_capsules(side, q, grip_open)
    fa, fb, fr = fix
    d = seg_seg_dist(A, B, fa, fb) - Rr[:, None] - fr[None, :]
    # the shoulder capsule starts near the base (below the tabletop level is fine there): skip it for the table
    # the jaw capsule (last) is exempt: picking from the table puts the fingertips 2 mm above it (checked separately).
    # The tabletop is finite (x 0.2995..1.0015, y -0.55..0.55): only capsule points above it count.
    f = np.linspace(0, 1, 7)
    pts = A[1:-1, None, :] + f[None, :, None] * (B[1:-1] - A[1:-1])[:, None, :]
    rr = np.repeat(Rr[1:-1, None], len(f), axis=1)
    over = ((pts[..., 0] > TABLE_X[0] - rr) & (pts[..., 0] < TABLE_X[1] + rr) &
            (np.abs(pts[..., 1]) < TABLE_Y + rr))
    low = np.where(over, pts[..., 2] - rr - TABLE, 1.0)
    out = dict(fixtures=float(d.min()), table=float(low.min()))
    if other is not None:
        A2, B2, R2 = arm_capsules(other[0], other[1], other[2] if len(other) > 2 else True)
        out["arms"] = float((seg_seg_dist(A, B, A2, B2) - Rr[:, None] - R2[None, :]).min())
    return out
