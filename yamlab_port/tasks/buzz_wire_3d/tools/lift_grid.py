"""Feasibility grid for the G_up lift on the start post: (height, tilt) nodes on the pick IK branch."""
import numpy as np
from scipy.spatial.transform import Rotation
from bw_geom import *
from grasps import *
from plan_r import Planner, frame_h_n
s = Scene(layout=Layout(-90.0, (0.96, 0.055679, TABLE_Z)))
P = Planner(s)
W0 = T_from(s.start_R.as_matrix(), s.start_p)
Gup = pen("up", 0.033, -0.0275, 4.0)
h0 = s.start_R.apply([1, 0, 0]); h0[2] = 0; h0 /= np.linalg.norm(h0)
q0 = P.ik["right"].solve_multi((W0 @ Gup)[:3, 3], (W0 @ Gup)[:3, :3], None, n_random=256)[0]
p0 = s.rail[0, :2]
for sign in (1, -1):
    print("tilt sign", sign)
    for beta in range(0, 61, 10):
        row = []
        q = q0.copy()
        for hz in range(4, 62, 4):
            n = Rotation.from_rotvec(sign * np.radians(beta) * h0).apply([0, 0, 1.0])
            W = T_from(frame_h_n(h0, n), np.r_[p0, s.deck_top + hz / 1000])
            T = W @ Gup
            Q, ok, ep, er = P.ik["right"].solve(T[:3, 3], T[:3, :3], np.eye(4), q[None], iters=100)
            if not ok[0]:
                row.append("  ik ")
                continue
            q = Q[0]
            c = P.clear("right", q, -0.0056, ignore=("stops",))
            row.append(f"{min(c['wire']*1000, 99):4.0f}/{min(c['deck']*1000, 99):2.0f}"[:7])
        print(f"b{beta:2d}", " ".join(row), flush=True)
