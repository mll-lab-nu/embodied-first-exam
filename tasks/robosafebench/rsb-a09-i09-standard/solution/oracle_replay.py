"""Standard-mode reference solution: RoboSafeBench's scripted reference of this instance, compiled into rows of the
action types (scripts/robosafe/make_instances.py): /solution/oracle.json is the plan, /solution/oracle.npz the rows.
A plan item is either a run of motion rows ({"type", "rows": [a, b]}: rows a..b-1 of that type's array, sent in chunks
of at most max_chunk_s, one control step apart, as they are: interpolate="hold") or one row with its text ({"type",
"row", "text"}: a question, a report, an exit), sent in a /submit of its own with the text as its note."""
import json
import os

import numpy as np

from rcb_client import EpisodeOver, Robot

plan = json.load(open("/solution/oracle.json"))["plan"]
arrays = dict(np.load("/solution/oracle.npz")) if os.path.exists("/solution/oracle.npz") else {}
r = Robot()
spec = r.spec()
cam = [sorted(spec["cameras"])[0]]
dt = spec["control_dt"]
per_chunk = max(1, int(round(spec["max_chunk_s"] / dt)))
res = None
try:
    for it in plan:
        typ = it["type"]
        dim = int(spec["action_types"][typ]["dim"])
        if "rows" in it:
            a, b = it["rows"]
            for k in range(a, b, per_chunk):
                rows = arrays[typ][k:min(k + per_chunk, b)]
                res = r.submit(typ, rows, dt=dt, interpolate="hold", video="none", cameras=cam)
                if res.done or res.meta.get("blocked"):
                    break
        else:
            res = r.submit(typ, np.asarray(it["row"], dtype=np.float64).reshape(1, dim), dt=dt, interpolate="hold",
                           video="none", cameras=cam, note=it.get("text") or "")
        if res is not None and res.meta.get("blocked"):
            print("row refused:", res.meta.get("results", [])[-1:])
        if res is not None and res.done:
            break
except EpisodeOver:
    pass
print(r.status(), None if res is None else {k: res.meta.get(k) for k in ("done", "reason", "result")})
