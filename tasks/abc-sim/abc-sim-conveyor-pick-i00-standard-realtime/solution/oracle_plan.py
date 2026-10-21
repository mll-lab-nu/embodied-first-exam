"""Standard-realtime reference solution: the privileged twin's reference rows (solution/oracle.npy, one row of 14
joint-position targets per control step) planned into the episode at the control steps where they ran in the privileged
replay: chunks of at most 200 rows, `submit(..., at=<its first step>)`, each sent ahead of time (well inside
max_ahead_steps of the clock). The first chunk, at step 0, starts the clock; the rows then run at the same control steps
as in the privileged replay, so the episode is the privileged reference's."""
import os
import time

import numpy as np

from rcb_client import EpisodeOver, Robot

A = np.load(os.path.join(os.path.dirname(os.path.abspath(__file__)), "oracle.npy")).astype(np.float64)
r = Robot()
spec = r.spec()
dt, ahead = float(spec["control_dt"]), int(spec["timing"]["max_ahead_steps"])
chunks = [(i, min(i + 200, len(A))) for i in range(0, len(A), 200)]
try:
    for i, j in chunks:
        while i and r.status()["control_steps"] < i - ahead // 2:   # well inside max_ahead_steps
            time.sleep(0.02)
        res = r.submit("joint_position", A[i:j], dt=dt, interpolate="hold", at=i, cameras=[])
        print(f"planned rows {i}..{j} at step {i}; now step {res.meta['control_steps']}, late {res.meta.get('late_steps')}",
              flush=True)
    while not r.status()["done"]:
        time.sleep(0.1)
except EpisodeOver:
    pass
print(r.status())
