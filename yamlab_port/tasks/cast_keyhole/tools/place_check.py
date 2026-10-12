"""Right-arm IK reach for silver placements: upright on its +x edge at (fc) with long-axis yaw, tipped by theta
toward +n. Prints feasible (min margin over upright-low / tipped) combos.  usage: python place_check.py"""
import itertools, json, sys
import numpy as np
from scipy.spatial.transform import Rotation
import plan2 as pl, yam_kin as yk
from layout import Scene, TABLE_Z
G = pl.silver_edge_grasp(-0.0024, -0.051, -1.0)
g = Scene("very_easy").goal
lo, hi = np.array(g["xy_min"]) + 0.004, np.array(g["xy_max"]) - 0.004
rng = np.random.default_rng(0)
def solve(T):
    best = None
    for _ in range(40):
        q0 = yk.LOWER + rng.random(6) * (yk.UPPER - yk.LOWER)
        q, ok, _, _ = yk.ik(yk.world_to_base(T, "right"), q0, iters=120)
        if ok:
            m = float(np.min(np.minimum(q - yk.LOWER, yk.UPPER - q)))
            best = m if best is None else max(best, m)
            if m > 0.3: break
    return best
xs = np.array([0, 0, -1.0])
for yawd in range(-90, 91, 15):
    yaw = np.radians(yawd); ys = np.array([np.cos(yaw), np.sin(yaw), 0])
    for nsign in (1, -1):
        n = nsign * np.cross([0, 0, 1.0], ys)
        Rf = np.c_[xs, ys, np.cross(xs, ys)]
        hx = abs(ys[0]) * 0.1035 + abs(n[0]) * 0.039; hy = abs(ys[1]) * 0.1035 + abs(n[1]) * 0.039
        if np.any(hi - lo < 2 * np.r_[hx, hy]): continue
        for fx in np.linspace(lo[0] + hx, hi[0] - hx, 3):
            fc = np.r_[fx, lo[1] + hy]
            rc = fc - n[:2] * 0.0435
            T = np.eye(4); T[:3, :3] = Rf; com = Rf @ np.r_[-0.0003, -0.0024, 0]
            T[:3, 3] = np.r_[rc[0] - com[0], rc[1] - com[1], TABLE_Z + 0.041]
            edges = [T @ np.r_[0.039, 0, zz, 1] for zz in (-0.0045, 0.0045)]
            piv = max(edges, key=lambda q: q[:2] @ n[:2])[:3]; piv[2] = TABLE_Z
            axis = np.cross([0, 0, 1.0], n)
            res = []
            for th in (0, 30, 50, 65):
                Tt = pl.rot_about(T, Rotation.from_rotvec(axis * np.radians(th)).as_matrix(), piv)
                res.append(solve(Tt @ G))
            print(json.dumps(dict(yaw=yawd, n=nsign, fc=fc.round(3).tolist(), margins=res)), flush=True)
