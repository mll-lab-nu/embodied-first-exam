import numpy as np
from scipy.spatial.transform import Rotation
from bw_geom import *
from grasps import *
from plan_r import Planner, frame_h_n
s = Scene(layout=Layout(-90.0, (0.96, 0.055679, TABLE_Z)))
P = Planner(s)
Gup, Rg = pen("up", 0.033, -0.0275, 4.0), ring()
h0 = s.start_R.apply([1, 0, 0]); h0[2] = 0; h0 /= np.linalg.norm(h0)
p0 = s.rail[0, :2]
rng = np.random.default_rng(3)
for dyaw in (0, 20, -20, 40):
    h = Rotation.from_euler("z", dyaw, degrees=True).apply(h0)
    for beta in (-40, -30, -20, -10, 0):
        row = []
        for hz in (0.045, 0.05, 0.055, 0.06):
            n = Rotation.from_rotvec(np.radians(beta) * h).apply([0, 0, 1.0])
            W = T_from(frame_h_n(h, n), np.r_[p0, s.deck_top + hz])
            res = []
            for side, G, fq in (("right", Gup, -0.0056), ("left", Rg, -0.0023)):
                T = W @ G
                sols = P.ik[side].solve_multi(T[:3, 3], T[:3, :3], None, n_random=160, rng=rng)
                if not sols:
                    res.append("--"); continue
                c = max((P.clear(side, q, fq, ignore=("stops",)) for q in sols), key=lambda c: min(c.values()))
                res.append(f"{c['wire']*1000:.0f}/{c['deck']*1000:.0f}")
            row.append(f"{hz*1000:.0f}:" + ",".join(res))
        print(f"dyaw {dyaw:3d} beta {beta:3d}  " + "  ".join(row), flush=True)
