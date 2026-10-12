"""Offline kinematic dry run of Plan R (stages_r.StagesR with the OfflineExecutor)."""
import json
import sys
import time
import numpy as np
from bw_geom import Scene, Layout, TABLE_Z
from plan_r import Planner, PlanError
from stages_r import StagesR, OfflineExecutor

TX = float(sys.argv[1]) if len(sys.argv) > 1 else 0.96
s = Scene(layout=Layout(-90.0, (TX, 0.055679, TABLE_Z)))
P = Planner(s)
ex = OfflineExecutor(P, s)
notes = {}
t0 = time.time()
try:
    StagesR(P, ex, notes).run()
    status = "PLAN_OK"
except PlanError as e:
    status = f"PLAN_FAIL {e}"
print(status, "%.0f s" % (time.time() - t0), json.dumps(notes))
np.savez(f"../../results/dry_run_r_{TX:.3f}.npz", phase=np.array([t[0] for t in ex.traj]),
         side=np.array([t[1] for t in ex.traj]), q=np.array([t[2] for t in ex.traj]) if ex.traj else np.zeros((0, 6)))
