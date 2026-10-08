"""Oracle (privileged): replay the reference rows in the tooling, check them, and save them as the deliverable."""

import json
import os
import sys

import numpy as np

sys.path.insert(0, "/opt/tools")
import rcb_labutopia as M  # noqa: E402

rows = np.load(os.path.join(os.path.dirname(os.path.abspath(__file__)), "oracle.npz"))["actions"].astype(np.float64)
s = M.Session(instance="/app/instance.json", cameras=False)
r = s.replay(rows)
s.save_trajectory(rows, "/app/output/trajectory.npz", meta={"source": "reference trajectory (solution/oracle.npz)"})
print(json.dumps(r))
if not r["success"]:
    print("the reference trajectory does not succeed from the frozen instance", file=sys.stderr)
s.close()
M.finish(0 if r["success"] else 1)
