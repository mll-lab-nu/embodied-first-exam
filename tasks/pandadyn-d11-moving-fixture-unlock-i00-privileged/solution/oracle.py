"""Oracle (privileged): run the reference rows on the frozen instance with the agent's tooling, stopping at the end of
the episode, and save the rows that ran as /app/output/trajectory.npz."""
import json, os
import numpy as np
from rcb_pandadyn import Session
HERE = os.path.dirname(os.path.abspath(__file__))
s = Session(instance="/app/instance.json", strict=True)
rows = np.load(os.path.join(HERE, "oracle_actions.npy")).astype(np.float64)
st = s.replay(rows)
s.save_trajectory(s.actions(), "/app/output/trajectory.npz", meta={"source": "reference rows"})
print(json.dumps({k: st[k] for k in ("success", "end_reason", "executed_rows", "sim_time_s", "state_sha")}), flush=True)
s.close()
