"""Oracle (standard mode): the reference actions (sit_simple_actions.npy, the privileged oracle's 999 rows of
normalised servo targets) sent through the client in chunks, one row per control step (dt = control_dt, hold), as an
agent would send them; the service ends the episode the moment the return reaches the pass mark."""
import os

import numpy as np
from rcb_client import Robot

A = np.load(os.path.join(os.path.dirname(os.path.abspath(__file__)), "sit_simple_actions.npy"))
r = Robot()
dt = r.spec()["control_dt"]
rows = int(round(r.spec()["max_chunk_s"] / dt))
for i in range(0, len(A), rows):
    res = r.submit("joint_position", A[i:i + rows], dt=dt, interpolate="hold", cameras=["left_eye_camera"],
                   video="none", note="oracle")
    print(f"rows {i}..{i + res.meta['executed_rows']}: done={res.done} reason={res.meta['reason']}", flush=True)
    if res.done:
        break
print(r.status())
