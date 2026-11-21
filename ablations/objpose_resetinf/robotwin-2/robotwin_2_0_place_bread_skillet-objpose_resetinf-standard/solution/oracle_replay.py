"""Oracle (standard mode v2): replays the privileged-mode expert's joint targets, sampled every K physics steps, as
`joint_position` chunks with dt = K/250 s and linear interpolation — i.e. the expert's own timing, streamed through the
same interface an agent has. Uses no privileged information at run time (only the pre-recorded targets)."""
import json, os, sys, time
import numpy as np
sys.path.insert(0, "/opt/tools")
from rcb_client import Robot, EpisodeOver
HERE = os.path.dirname(os.path.abspath(__file__))
Q = np.load(os.path.join(HERE, "oracle_qpos.npy")).astype(np.float32)           # (N, 14) or (N, 28: + velocity feed-forward), one row per K physics steps
K = int(json.load(open(os.path.join(HERE, "oracle_meta.json"))).get("K", 25)) if os.path.exists(os.path.join(HERE, "oracle_meta.json")) else 25
dt = K / 250.0
r = Robot(); spec = r.spec(); print("spec:", spec["protocol"], "rows:", len(Q), "dt:", dt, flush=True)
rows_per_chunk = max(1, int(spec.get("max_chunk_s", 10) / dt))
t0 = time.time(); done = False
for i in range(0, len(Q), rows_per_chunk):
    chunk = Q[i:i + rows_per_chunk]
    try:
        res = r.submit("joint_position", chunk, dt=dt, interpolate="linear", cameras=["head_camera"], video="none", note=f"oracle chunk {i // rows_per_chunk}")
    except EpisodeOver as e:
        print("episode over:", e); break
    print(f"chunk {i // rows_per_chunk}: rows={res.meta['executed_rows']} phys={res.meta['physics_steps_chunk']} clipped={res.meta['n_clipped']} done={res.meta['done']}", flush=True)
    if res.meta["done"]: done = True; print("done:", res.meta["reason"]); break
if not done:
    obs = r.get_obs(seconds=1.0, cameras=["head_camera"], video="none"); print("settle:", obs.meta["done"], obs.meta["reason"])
print("status:", r.status(), "wall %.0fs" % (time.time() - t0))
