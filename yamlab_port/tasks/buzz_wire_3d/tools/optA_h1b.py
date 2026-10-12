"""Option A handover-1 search: all handle yaws x tilts x heights, both arms, A and ring grip. Prints compatible pairs."""
import sys
import numpy as np
from scipy.spatial.transform import Rotation
from bw_geom import *
from grasps import *
from plan_r import Planner, frame_h_n
yaw, tx, ty = float(sys.argv[1]), float(sys.argv[2]), float(sys.argv[3])
hlist = [int(v) for v in sys.argv[4].split(",")]
s = Scene(layout=Layout(yaw, (tx, ty, TABLE_Z)))
P = Planner(s)
rng = np.random.default_rng(0)
p0 = s.rail[0, :2]
A = topdown("A", c=GRIP_XC, tip_gap=-0.0025)
RG = ring()


def ok(side, T, fq):
    sols = P.ik[side].solve_multi(T[:3, 3], T[:3, :3], None, n_random=96, rng=rng)
    if not sols:
        return None
    return max(min(P.clear(side, q, fq, ignore=("stops",)).values()) for q in sols)


for hdeg in hlist:
    h = np.array([np.cos(np.radians(hdeg)), np.sin(np.radians(hdeg)), 0])
    for beta in (-45, -30, -15, 0, 15, 30, 45):
        for hz in (0.03, 0.045, 0.06):
            n = Rotation.from_rotvec(np.radians(beta) * h).apply([0, 0, 1.0])
            W = T_from(frame_h_n(h, n), np.r_[p0, s.deck_top + hz])
            r = {f"A_{sd[0]}": ok(sd, W @ A, -0.0059) for sd in ("left", "right")}
            r.update({f"R_{sd[0]}": ok(sd, W @ RG, -0.0023) for sd in ("left", "right")})
            good = [(a, b) for a, b in (("A_r", "R_l"), ("A_l", "R_r")) if r[a] is not None and r[b] is not None and min(r[a], r[b]) > 0.002]
            print(f"h {hdeg:4d} b {beta:3d} hz {hz*1000:.0f}: " + " ".join(f"{k}={'--' if v is None else round(v*1000)}" for k, v in r.items()) + ("   <== " + str(good) if good else ""), flush=True)
