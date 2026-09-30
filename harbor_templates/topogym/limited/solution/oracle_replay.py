"""Oracle (limited mode v2): replays the unlimited oracle's joint targets, sampled every K control steps, as
`joint_position` chunks with dt = K/30 s — i.e. the oracle's own timing, streamed through the same interface an agent
has. K = 1 with `hold` replays the recorded rows exactly. Uses no privileged information at run time."""
import json, os, sys, time
import numpy as np
sys.path.insert(0, "/opt/tools")
from rcb_client import Robot, EpisodeOver
HERE = os.path.dirname(os.path.abspath(__file__))
Q = np.load(os.path.join(HERE, "oracle_qpos.npy")).astype(np.float32)           # (N, 16), one row per K control steps
M = json.load(open(os.path.join(HERE, "oracle_meta.json"))) if os.path.exists(os.path.join(HERE, "oracle_meta.json")) else {}
K = int(M.get("K", 1)); interp = M.get("interpolate", "hold")
r = Robot(); spec = r.spec(); hz = float(spec.get("control_hz", 30)); dt = K / hz
print("spec:", spec["protocol"], "rows:", len(Q), "dt:", dt, flush=True)
rows_per_chunk = max(1, int(spec.get("max_chunk_s", 10) / dt + 1e-9))
t0 = time.time(); done = False
for i in range(0, len(Q), rows_per_chunk):
    chunk = Q[i:i + rows_per_chunk]
    try:
        res = r.submit("joint_position", chunk, dt=dt, interpolate=interp, cameras=[next(iter(spec["cameras"]))], video="none", note=f"oracle chunk {i // rows_per_chunk}")
    except EpisodeOver as e:
        print("episode over:", e); break
    print(f"chunk {i // rows_per_chunk}: rows={res.meta['executed_rows']} steps={res.meta['control_steps_chunk']} clipped={res.meta['n_clipped']} done={res.meta['done']}", flush=True)
    if res.meta["done"]: done = True; print("done:", res.meta["reason"]); break
if not done:
    obs = r.get_obs(seconds=1.0, cameras=[next(iter(spec["cameras"]))], video="none"); print("settle:", obs.meta["done"], obs.meta["reason"])
print("status:", r.status(), "wall %.0fs" % (time.time() - t0))
