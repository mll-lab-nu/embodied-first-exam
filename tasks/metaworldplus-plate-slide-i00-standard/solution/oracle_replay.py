"""Oracle (standard): the privileged oracle's recorded actions, submitted through the client (one row per control
step). No privileged information at run time; the rows were recorded offline (scripts/metaworldplus/freeze.py)."""

import json
from pathlib import Path

import numpy as np
from rcb_client import Robot

r = Robot()
spec = r.spec()
dt = spec["control_dt"]
rows = max(1, int(spec["max_chunk_s"] / dt) - 1)
actions = np.load(Path(__file__).with_name("oracle.npz"))["actions"].astype(np.float64)
cam = next(iter(spec["cameras"]))
for i in range(0, len(actions), rows):
    res = r.submit("ee_delta", actions[i : i + rows], dt=dt, interpolate="hold", cameras=[cam], video="none")
    print(f"chunk {i // rows}: steps={res.meta['control_steps']} done={res.meta['done']}", json.dumps(res.meta["task"]))
print("status:", r.status())
