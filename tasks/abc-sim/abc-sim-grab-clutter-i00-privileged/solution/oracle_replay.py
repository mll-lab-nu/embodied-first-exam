"""Oracle (privileged): replay the reference rows in the tooling, check them, and save them as the deliverable."""

import json
import os

import numpy as np
from rcb_abc import Session

rows = np.load(os.path.join(os.path.dirname(os.path.abspath(__file__)), "oracle.npy"))
s = Session(instance="/app/instance.npz")
r = s.replay(rows)
s.save_trajectory(rows, "/app/output/trajectory.npz", meta={"source": "reference trajectory (solution/oracle.npy)"})
print(json.dumps(r))
if not r["success"]:
    raise SystemExit("the reference trajectory does not succeed from the frozen instance")
