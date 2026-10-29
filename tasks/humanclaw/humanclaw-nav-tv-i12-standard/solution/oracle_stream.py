"""Oracle (standard mode): submits the reference actions (solution/actions.json, rows [action_id, value]) as
`skill` chunks through the client. If the service crashes it resumes the same episode: the oracle waits until it
answers again and goes on from the control step it reports."""

import json
import os
import sys
import time

import numpy as np
import requests

sys.path.insert(0, "/opt/tools")
from rcb_client import EpisodeOver, Robot  # noqa: E402

A = np.array(json.load(open(os.path.join(os.path.dirname(os.path.abspath(__file__)), "actions.json"))),
             dtype=np.float64).reshape(-1, 2)
r = Robot()
spec = r.spec()
dt = float(spec["control_dt"])
per_chunk = max(1, int(spec.get("max_chunk_s", 10) / dt + 1e-9))
print("spec:", spec["protocol"], "rows:", len(A), flush=True)
t0, i = time.time(), 0
while i < len(A):
    chunk = A[i : i + per_chunk]
    try:
        res = r.submit("skill", chunk, dt=dt, video="none", note=f"oracle rows {i}+")
    except EpisodeOver as e:
        print("episode over:", e)
        break
    except requests.exceptions.RequestException as e:
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
        break
    i = n
print("status:", r.status(), "wall %.0fs" % (time.time() - t0))
