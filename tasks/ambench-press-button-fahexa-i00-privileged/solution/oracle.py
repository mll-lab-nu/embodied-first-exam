"""Oracle (privileged): run the reference rows on the frozen instance with the agent's tooling, stopping at the end of
the episode, and save ALL the reference rows (the expert's, then its 2 s hold) as /app/output/trajectory.npz: a replay
runs them until its episode ends, as this run did."""
import json, os
import numpy as np
from rcb_ambench import Session
HERE = os.path.dirname(os.path.abspath(__file__))
s = Session(instance="/app/instance.json", strict=True)
rows = np.load(os.path.join(HERE, "oracle_actions.npy")).astype(np.float64)
for row in rows:                                   # the process's first episode, as the grader's
    if s.step(row):
        break
st = {**s.status(), "executed_rows": s.n_steps}
s.save_trajectory(rows, "/app/output/trajectory.npz", meta={"source": "reference rows"})
print(json.dumps({k: st[k] for k in ("success", "end_reason", "executed_rows", "sim_time_s", "state_sha")}), flush=True)
s.close()
os._exit(0 if st["success"] else 1)
