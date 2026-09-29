"""Limited-mode oracle: submit the unlimited oracle's recorded targets (one row per control step) through the client.
No privileged information at run time; the rows were recorded offline (solution/ of the unlimited task)."""
import json, os, sys
import numpy as np
from rcb_client import Robot
r = Robot(); spec = r.spec(); dt = spec["control_dt"]; rows = max(1, int(spec["max_chunk_s"] / dt) - 1)
A = np.load(os.path.join(os.path.dirname(os.path.abspath(__file__)), "oracle_targets.npy")).astype(np.float64)
cam = next(iter(spec["cameras"]))
for i in range(0, len(A), rows):
    res = r.submit("joint_position", A[i:i + rows], dt=dt, interpolate="hold", cameras=[cam], video="none", note=f"oracle chunk {i // rows}")
    print(f"chunk {i // rows}: rows={res.meta['executed_rows']} steps={res.meta['control_steps']} done={res.meta['done']} task={json.dumps(res.meta['task'])[:120]}", flush=True)
    if res.meta["done"]: break
print("status:", r.status())
