"""Standard-realtime reference solution: RoboSafeBench's scripted reference of this instance, compiled into rows of the
action types (scripts/robosafe/make_instances.py; /solution/oracle.json the plan, /solution/oracle.npz the rows, the
standard task's), streamed through the realtime client. Runs of motion rows go as plans chained with `at`: each chunk
(at most max_chunk_s) takes over where the plan ends, sent while at most one chunk is still queued, so the robot never
waits for this program. A row with a text (a question, a report, an exit) goes in a /submit of its own once the plan
has run out (the robot holds meanwhile), as RoboSafeBench's own realtime player does (compile.play)."""
import json
import os
import time

import numpy as np

from rcb_client import EpisodeOver, Robot

plan = json.load(open("/solution/oracle.json"))["plan"]
arrays = dict(np.load("/solution/oracle.npz")) if os.path.exists("/solution/oracle.npz") else {}
r = Robot()
spec = r.spec()
dt = spec["control_dt"]
per = max(1, int(round(spec["max_chunk_s"] / dt)))


def wait(cond, poll: float = 0.05) -> dict:
    while True:
        st = r.status()
        if st.get("done") or cond(st):
            return st
        time.sleep(poll)


st: dict = {}
try:
    for it in plan:
        typ = it["type"]
        dim = int(spec["action_types"][typ]["dim"])
        if "rows" in it:
            a, b = it["rows"]
            for k in range(a, b, per):
                st = wait(lambda s: s["planned_steps"] <= per)
                if st.get("done"):
                    break
                at = st["control_steps"] + st["planned_steps"] if st.get("running") and st["planned_steps"] else None
                res = r.submit(typ, arrays[typ][k:min(k + per, b)], dt=dt, interpolate="hold", at=at, cameras=[],
                               video="none")
                if res.meta.get("late_steps"):
                    print("late rows:", res.meta["late_steps"], flush=True)
        else:
            st = wait(lambda s: s["planned_steps"] == 0)
            if not st.get("done"):
                r.submit(typ, np.asarray(it["row"], dtype=np.float64).reshape(1, dim), dt=dt, interpolate="hold",
                         cameras=[], video="none", note=it.get("text") or "")
                st = wait(lambda s: s["planned_steps"] == 0)
        if st.get("done"):
            break
except EpisodeOver:
    pass
print(r.status(), flush=True)
