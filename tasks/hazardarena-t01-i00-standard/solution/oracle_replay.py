"""Oracle (standard): the privileged oracle's reference outcome, submitted through the client: its recorded control
steps, one row per control step, or a decline. No privileged information at run time; it was recorded offline."""

import json
from pathlib import Path

import numpy as np
from rcb_client import Robot

ref = dict(np.load(Path(__file__).with_name("oracle.npz"), allow_pickle=False))
r = Robot()
spec = r.spec()
dt = spec["control_dt"]
rows = max(1, int(spec["max_chunk_s"] / dt) - 1)
actions = np.asarray(ref["actions"], dtype=np.float64)
cam = next(iter(spec["cameras"]))
for i in range(0, len(actions), rows):
    res = r.submit("joint_position", actions[i : i + rows], dt=dt, interpolate="hold", cameras=[cam], video="none")
    print(f"chunk {i // rows}: steps={res.meta['control_steps']} done={res.meta['done']} reason={res.meta['reason']}")
    if res.meta["done"]:
        break
if int(ref["decline"]):
    res = r.submit("decline", [], cameras=[cam], video="none", note=str(ref["note"]))
    print(f"decline: done={res.meta['done']} reason={res.meta['reason']}")
print("status:", json.dumps(r.status()))
