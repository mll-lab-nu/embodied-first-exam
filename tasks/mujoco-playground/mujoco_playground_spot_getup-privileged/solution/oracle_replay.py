"""Oracle (privileged): replay the reference rows in the tooling, check them, and save them as the deliverable."""
import json
import os
import sys

import numpy as np

sys.path.insert(0, "/opt/tools")
from rcb_quadruped import Session  # noqa: E402

rows = np.load(os.path.join(os.path.dirname(os.path.abspath(__file__)), "oracle.npy"))
s = Session("/app/instance.json")
r = s.replay(rows)
s.save_trajectory(rows, "/app/output/trajectory.npz", meta={"source": "reference trajectory (solution/oracle.npy)"})
print(json.dumps({k: v for k, v in r.items() if k != "segments"}))
