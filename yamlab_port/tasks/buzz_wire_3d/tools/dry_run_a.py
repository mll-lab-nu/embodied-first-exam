"""Offline kinematic dry run of option A (stages_a.StagesA)."""
import json, sys, time
import numpy as np
from scipy.spatial.transform import Rotation
from bw_geom import Scene, Layout, TABLE_Z
from grasps import T_from
from plan_r import Planner, PlanError
from stages_r import OfflineExecutor
import stages_a

hs = float(sys.argv[1]) if len(sys.argv) > 1 else stages_a.H_START
tier = sys.argv[2] if len(sys.argv) > 2 else "very_easy"
import os
tx, ty = (float(v) for v in os.environ.get("BUZZ_LAYOUT_T", "0.5144,0.270").split(","))
s = Scene(tier, layout=Layout(0.0, (tx, ty, TABLE_Z)))
P = Planner(s)
ex = OfflineExecutor(P, s)
h_old = np.degrees(np.arctan2(*s.start_R.apply([1, 0, 0])[[1, 0]]))
Rz = Rotation.from_euler("z", hs - h_old, degrees=True)
post = np.r_[s.rail[0, :2], 0]
ex.W = T_from((Rz * s.start_R).as_matrix(), Rz.apply(s.start_p - post) + post)
notes = {}
t0 = time.time()
try:
    stages_a.StagesA(P, ex, notes).run()
    status = "PLAN_OK"
except PlanError as e:
    status = f"PLAN_FAIL {e}"
print(status, tier, "layout", (tx, ty), "start yaw", hs, "%.0f s" % (time.time() - t0), json.dumps(notes))
