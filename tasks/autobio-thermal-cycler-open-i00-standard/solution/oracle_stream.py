"""Oracle (standard mode): streams the reference rows (solution/oracle.npz, one row of position targets per control
step, float32-exact) as `joint_position` chunks through the client, the same interface an agent has, and ends the
episode with `done` if the task has not ended it. Uses no privileged information at run time; the service's recorded
trajectory is then exactly the privileged reference. If the service crashes it resumes the same episode
(spec["on_service_error"]): the oracle waits until it answers again and goes on from the control step it reports."""

import os
import sys
import time

import numpy as np
import requests

sys.path.insert(0, "/opt/tools")
from rcb_client import EpisodeOver, Robot  # noqa: E402

A = np.load(os.path.join(os.path.dirname(os.path.abspath(__file__)), "oracle.npz"))["actions"].astype(np.float64)
r = Robot()
spec = r.spec()
dt = 1.0 / float(spec["control_hz"])
per_chunk = max(1, int(spec.get("max_chunk_s", 10) / dt + 1e-9))
print("spec:", spec["protocol"], "rows:", len(A), flush=True)
t0, i, over = time.time(), 0, False
while i < len(A):
    chunk = A[i : i + per_chunk]
    try:
        res = r.submit("joint_position", chunk, dt=dt, interpolate="hold", video="none", note=f"oracle rows {i}+")
    except EpisodeOver as e:
        print("episode over:", e)
        over = True
        break
    except requests.exceptions.RequestException as e:  # the service crashed: it restarts and resumes the same episode
        print("service unreachable:", repr(e)[:200], "- waiting for it to resume", flush=True)
        st = r.wait_ready()
        n = int(st["control_steps"])
        if not i <= n <= i + len(chunk):
            raise SystemExit(f"resumed at control step {n}: outside the chunk in flight (rows {i}..{i + len(chunk)})")
        i = n
        continue
    n = int(res.meta["control_steps"])
    print(f"rows {i}..{n}: done={res.meta['done']} reason={res.meta['reason']}", flush=True)
    if res.meta["done"] or n <= i:
        over = bool(res.meta["done"])
        break
    i = n
if not over:  # a task judged on its final state: the rows are in, end the episode there
    try:
        res = r.submit("done", [], note="oracle: all rows executed")
        print("done:", res.meta["done"], res.meta["reason"], flush=True)
    except EpisodeOver as e:
        print("episode over:", e)
print("status:", r.status(), "wall %.0fs" % (time.time() - t0))
