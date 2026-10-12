import numpy as np
from bw_geom import *
from grasps import *
from plan_r import Planner
s = Scene(layout=Layout(-90.0, (0.96, 0.055679, TABLE_Z)))
P = Planner(s)
W0 = T_from(s.start_R.as_matrix(), s.start_p)
Gup = pen("up", 0.033, -0.0275, 4.0)
sols = P.ik["right"].solve_multi((W0 @ Gup)[:3, 3], (W0 @ Gup)[:3, :3], None, n_random=512, rng=np.random.default_rng(5))
print("branches", len(sols), [np.round(q, 2).tolist() for q in sols])
q = sols[0]
for dz in (0, 0.01, 0.02, 0.03, 0.05):
    W = W0.copy(); W[2, 3] += dz
    T = W @ Gup
    Q, ok, ep, er = P.ik["right"].solve(T[:3, 3], T[:3, :3], np.eye(4), q[None], iters=80)
    q = Q[0]
    pts = P.AP["right"].world(q, -0.0056)
    out = []
    for l, X in pts.items():
        d = seg_point_dist(X, s.rail[:-1], s.rail[1:])
        i = np.unravel_index(np.argmin(d), d.shape)
        out.append((round(d.min() * 1000 - 1.47, 1), l, np.round(X[i[0]], 3).tolist(), int(i[1])))
    out.sort()
    print(dz, ok[0], out[:3])
