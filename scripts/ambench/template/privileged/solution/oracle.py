"""Oracle (privileged): run the reference rows on the frozen instance with the agent's tooling, stopping at the end of
the episode, and save the rows that ran as /app/output/trajectory.npz."""
import json, os
import numpy as np
from rcb_ambench import Session
HERE = os.path.dirname(os.path.abspath(__file__))
s = Session(instance="/app/instance.json", strict=True)
for row in np.load(os.path.join(HERE, "oracle_actions.npy")).astype(np.float64):   # the process's first episode, as the grader's
    if s.step(row):
        break
st = {**s.status(), "executed_rows": s.n_steps}
s.save_trajectory(s.actions(), "/app/output/trajectory.npz", meta={"source": "reference rows"})
print(json.dumps({k: st[k] for k in ("success", "end_reason", "executed_rows", "sim_time_s", "state_sha")}), flush=True)
s.close()
os._exit(0 if st["success"] else 1)
