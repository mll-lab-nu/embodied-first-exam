"""Standard-realtime reference solution: the privileged twin's reference solution (the rows its controller stepped, by
action type) planned into the attempt at the control steps where they ran there: each run of one type is one chunk,
`submit(..., at=<its first step>)`, sent ahead of time (at most max_ahead_steps ahead of the clock). The first chunk,
at step 0, starts the clock; the rows then run at the same control steps as in the privileged replay."""
import time

import numpy as np

from rcb_client import EpisodeOver, Robot

d = np.load("/solution/rows.npz", allow_pickle=False)
names, dims, typ, rows = [str(x) for x in d["names"]], d["dims"], d["type"], d["rows"]
r = Robot()
spec = r.spec()
dt, ahead = float(spec["control_dt"]), int(spec["timing"]["max_ahead_steps"])
chunks, i, n = [], 0, len(typ)
while i < n:
    j = i
    while j < n and typ[j] == typ[i] and j - i < 200:          # one chunk: a run of one type, at most 2 s
        j += 1
    chunks.append((i, j))
    i = j
try:
    for i, j in chunks:
        while i and r.status()["control_steps"] < i - ahead // 2:   # well inside max_ahead_steps
            time.sleep(0.02)
        r.submit(names[typ[i]], rows[i:j, :dims[typ[i]]], dt=dt, interpolate="hold", at=i, cameras=[])
    while not r.status()["done"]:
        time.sleep(0.1)
except EpisodeOver:
    pass
res = r.get_obs(cameras=[])
print(r.status(), {k: res.meta.get(k) for k in ("outcome", "stages_reached", "stages_total")})
