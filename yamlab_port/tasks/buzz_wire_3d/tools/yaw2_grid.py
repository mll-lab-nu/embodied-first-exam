import numpy as np
from scipy.spatial.transform import Rotation
from bw_geom import *
from grasps import *
from plan_r import Planner, frame_h_n
s = Scene(layout=Layout(-90.0, (0.96, 0.055679, TABLE_Z)))
P = Planner(s)
Rg = ring()
p1 = s.rail[-1, :2]
rng = np.random.default_rng(4)
for hdeg in (-30, -60, -75, -90, -105, -120):
    h = np.array([np.cos(np.radians(hdeg)), np.sin(np.radians(hdeg)), 0])
    for beta in (-30, -15, 0, 15, 30):
        row = []
        for hz in (0.055, 0.062, 0.07, 0.08):
            n = Rotation.from_rotvec(np.radians(beta) * h).apply([0, 0, -1.0])
            W = T_from(frame_h_n(h, n), np.r_[p1, s.deck_top + hz])
            T = W @ Rg
            sols = P.ik["left"].solve_multi(T[:3, 3], T[:3, :3], None, n_random=160, rng=rng)
            if not sols:
                row.append("   --  "); continue
            c = max((P.clear("left", q, -0.0023) for q in sols), key=lambda c: min(c["wire"], c["deck"]))
            row.append(f"{c['wire']*1000:4.0f}/{c['deck']*1000:3.0f}")
        print(f"h {hdeg:4d} b {beta:3d} hz55,62,70,80: " + " ".join(row), flush=True)
