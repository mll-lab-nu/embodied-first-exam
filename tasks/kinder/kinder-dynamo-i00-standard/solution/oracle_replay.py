"""Oracle (standard mode): the privileged oracle's 101 moves (oracle_actions.npy: the delta actions it took, turned into
the odometry frame) sent through the client in chunks, as an agent would send them; the episode ends at the goal."""
import os

import numpy as np
from rcb_client import Robot

A = np.load(os.path.join(os.path.dirname(os.path.abspath(__file__)), "oracle_actions.npy"))
r = Robot()
rows = int(round(r.spec()["max_chunk_s"] / r.spec()["control_dt"]))
for i in range(0, len(A), rows):
    res = r.submit("delta", A[i:i + rows], cameras=["robot_base"], video="none", note="oracle")
    print(f"rows {i}..{i + res.meta['executed_rows']}: done={res.done} reason={res.meta['reason']}", flush=True)
    if res.done:
        break
print(r.status())
