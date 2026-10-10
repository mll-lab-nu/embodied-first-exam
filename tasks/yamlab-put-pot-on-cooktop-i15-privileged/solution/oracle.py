"""Oracle (privileged): run the reference actions on the frozen instance with the agent's tooling, stopping at the first
success, and save the rows that ran as /app/output/trajectory.npz."""
import json, os
import numpy as np
from rcb_yamlab import Session
HERE = os.path.dirname(os.path.abspath(__file__))
inst = json.load(open("/app/instance.json"))
s = Session(inst["task"], instance=inst, strict=True)
acts = np.load(os.path.join(HERE, "oracle_actions.npy")).astype(np.float32)
s.record_start()
for row in acts:
    if s.step(row):
        break
traj = s.record_stop()
s.save_trajectory(traj, "/app/output/trajectory.npz", meta={"source": "reference actions (YAMLab teleoperation demonstration)"})
print(json.dumps({"n_actions": int(len(traj)), **s.status()}), flush=True)
s.close()
