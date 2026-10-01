"""Oracle (standard mode): replays the privileged oracle's joint targets, sampled every K control steps, as
`joint_position` chunks with dt = K/30 s — i.e. the oracle's own timing, streamed through the same interface an agent
has. K = 1 with `hold` replays the recorded rows exactly. Uses no privileged information at run time.
If the service crashes (a connection error), it does what spec()["on_service_error"] tells an agent: it waits until the
service has resumed the same episode, reads how far the episode got (`control_steps`) and continues from that row."""
import json, os, sys, time
import numpy as np
import requests
sys.path.insert(0, "/opt/tools")
from rcb_client import Robot, EpisodeOver
HERE = os.path.dirname(os.path.abspath(__file__))
Q = np.load(os.path.join(HERE, "oracle_qpos.npy")).astype(np.float32)           # (N, 25), one row per K control steps
M = json.load(open(os.path.join(HERE, "oracle_meta.json"))) if os.path.exists(os.path.join(HERE, "oracle_meta.json")) else {}
K = int(M.get("K", 1)); interp = M.get("interpolate", "hold")
r = Robot(); spec = r.spec(); hz = float(spec.get("control_hz", 30)); dt = K / hz
print("spec:", spec["protocol"], "rows:", len(Q), "dt:", dt, flush=True)
rows_per_chunk = max(1, int(spec.get("max_chunk_s", 10) / dt + 1e-9))
cam = [next(iter(spec["cameras"]))]
t0 = time.time(); done = False; i = 0; n = 0
while i < len(Q):
    chunk = Q[i:i + rows_per_chunk]
    try:
        res = r.submit("joint_position", chunk, dt=dt, interpolate=interp, cameras=cam, video="none", note=f"oracle chunk {n}")
    except EpisodeOver as e:
        print("episode over:", e); break
    except requests.exceptions.RequestException as e:   # the service crashed: it resumes the SAME episode
        st = r.wait_ready()
        print(f"service restarted after {type(e).__name__}: resumed at control step {st['control_steps']} (resumes {st.get('resumes')})", flush=True)
        if st["done"]: done = True; print("done:", st["reason"]); break
        i = int(st["control_steps"]) // K; continue   # each row ran K control steps; the lost call ran none
    print(f"chunk {n}: rows={res.meta['executed_rows']} steps={res.meta['control_steps_chunk']} clipped={res.meta['n_clipped']} done={res.meta['done']}", flush=True)
    i += int(res.meta["executed_rows"]); n += 1
    if res.meta["done"]: done = True; print("done:", res.meta["reason"]); break
    if not res.meta["executed_rows"]: print("the service executed no row:", res.meta.get("stopped")); break
if not done:
    obs = r.get_obs(seconds=1.0, cameras=cam, video="none"); print("settle:", obs.meta["done"], obs.meta["reason"])
print("status:", r.status(), "wall %.0fs" % (time.time() - t0))
