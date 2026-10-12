import time, numpy as np
from bw_geom import *
from grasps import *
from plan_r import Planner, rrt_connect, PlanError, interp_T, n_steps
s = Scene(layout=Layout(-90.0, (0.96, 0.055679, TABLE_Z)))
P = Planner(s)
W0 = T_from(s.start_R.as_matrix(), s.start_p)
Gup = pen("up", 0.033, -0.0275, 4.0)
Tg = W0 @ Gup
qg = P.ik["right"].solve_multi(Tg[:3, 3], Tg[:3, :3], None, n_random=256)[0]
Tpre = Tg @ T_from(np.eye(3), [0, 0, -0.04])
Ts = interp_T(Tg, Tpre, n_steps(Tg, Tpre, lin=0.001))
qs, w = P.track("right", Ts, qg, -0.0089, ignore=("stops",))
qpre = qs[-1]
print("qpre", np.round(qpre, 3), "clear", {k: round(v*1000, 1) for k, v in P.clear("right", qpre, -0.0475).items()})
print("home clear", {k: round(v*1000, 1) for k, v in P.clear("right", np.zeros(6), -0.0475).items()})
for wm in (0.015, 0.008, 0.004):
    t = time.time()
    try:
        path = rrt_connect(P, "right", np.zeros(6), qpre, -0.0089, iters=4000,
                           margin={"wire": wm, "deck": 0.004, "stops": 0.004, "table": 0.01})
        print("wire margin", wm, "OK", len(path), "%.0fs" % (time.time() - t))
        break
    except PlanError as e:
        print("wire margin", wm, e, "%.0fs" % (time.time() - t))
