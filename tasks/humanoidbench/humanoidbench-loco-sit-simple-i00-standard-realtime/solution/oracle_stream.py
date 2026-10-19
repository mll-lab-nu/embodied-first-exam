"""Oracle (standard-realtime mode): the reference actions (sit_simple_actions.npy, the privileged oracle's 999 rows of
normalised servo targets) streamed through the client into the running episode's plan, one row per control step
(dt = control_dt, hold): the first chunk starts the clock at step 0, the second is planned from the step where the
first ends, long before that step comes, so every row runs at its own control step. The service ends the episode the
moment the return reaches the pass mark."""
import os
import time

import numpy as np
from rcb_client import Robot

A = np.load(os.path.join(os.path.dirname(os.path.abspath(__file__)), "sit_simple_actions.npy"))
r = Robot()
dt = r.spec()["control_dt"]
rows = int(round(r.spec()["max_chunk_s"] / dt))
for i in range(0, len(A), rows):
    res = r.submit("joint_position", A[i:i + rows], dt=dt, interpolate="hold", at=i, cameras=[], note="oracle")
    print(f"rows {i}..{i + len(A[i:i + rows])} planned from step {res.meta['start_step']}, late {res.meta['late_steps']}",
          flush=True)
    if res.meta["late_steps"]:
        raise SystemExit("a chunk arrived late: the episode would not run the reference rows")
while not r.status()["done"]:
    time.sleep(0.5)
print(r.status())
