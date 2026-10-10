"""Oracle (privileged): replay the reference rows in the tooling, check them, and save them as the deliverable."""

import json
import os
import sys

import numpy as np

sys.path.insert(0, "/opt/tools")
from rcb_autobio import Session  # noqa: E402

rows = np.load(os.path.join(os.path.dirname(os.path.abspath(__file__)), "oracle.npz"))["actions"].astype(np.float64)
s = Session(instance="/app/instance.json")
r = s.replay(rows)
s.save_trajectory(rows, "/app/output/trajectory.npz", meta={"source": "reference trajectory (solution/oracle.npz)"})
print(json.dumps(r))
if not r["success"]:
    raise SystemExit("the reference trajectory does not succeed from the frozen instance")
