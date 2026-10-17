#!/usr/bin/env python3
"""Fresh-process check of a reference: rows within the joint-speed limits (+1e-9 vs the previous row, from the keyframe
ctrl), then an open-loop replay through rcb_ikea (the grader's path) and final_check().
  check_ref.py REF.npz"""
import sys, time, json, hashlib
import numpy as np
import rcb_ikea as R

path = sys.argv[1]
s = R.Session('ikea365')
c = R.load_trajectory(path, s.nu, s.timestep)
prev = np.vstack([s.data.ctrl.copy()[None], c[:-1]])
d = np.abs(c - prev); lim = s.step_limit
over = (d > lim + R.SPEED_TOL) & np.isfinite(lim)
ratio = np.where(np.isfinite(lim), d / np.where(np.isfinite(lim), lim, 1), 0).max()
t0 = time.time()
fc = s.replay(c)
wall = time.time() - t0
rep = fc['end']['report']
print(json.dumps(dict(ref=path, sha256=hashlib.sha256(open(path, 'rb').read()).hexdigest(), rows=len(c),
                      sim_s=round(len(c) * s.control_dt, 3), rows_over=int(over.any(1).sum()), max_step_ratio=float(ratio),
                      slewed_ticks=s.slewed_ticks, success=fc['success'], failures=rep.get('failures'),
                      accepted=rep.get('operations_accepted'), support=rep.get('strict_support', {}).get('verified'),
                      end_terminal=fc['end']['terminal'], settled_success=fc['settled']['success'],
                      state_sha=fc['state_sha'], settled_sha=fc['settled_sha'], wall_s=round(wall, 1))), flush=True)
