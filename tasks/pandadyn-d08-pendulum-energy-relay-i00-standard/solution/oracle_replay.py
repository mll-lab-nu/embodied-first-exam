"""Oracle (standard mode): streams the privileged oracle's joint targets, sampled every K control steps, as
`joint_position` chunks of about one second (dt = K/100 s; K = 1 with `hold` replays the recorded rows exactly), through
the same client an agent has. Uses no privileged information at run time (only the pre-recorded targets). The rows are
sent as a float64 array part (`Robot._post`, the request `Robot.submit` builds, without its float32 rounding): these tasks
are sensitive enough that the rows rounded to float32 fail on some of them, and the service executes float64 rows as sent.

One-second chunks make a dozen calls, each checkpointed by the service with its state hash (crash recovery). The script
follows spec()["on_service_error"]: after a connection error it waits until the service has resumed the SAME episode,
reads how many control steps it executed and continues from the next row, so a crash of the service costs only time."""
import json, os, sys, time
import numpy as np
import requests
sys.path.insert(0, "/opt/tools")
from rcb_client import Robot, EpisodeOver
import rcb1
HERE = os.path.dirname(os.path.abspath(__file__))
Q = np.load(os.path.join(HERE, "oracle_qpos.npy")).astype(np.float64)           # (N, D), one row per K control steps
M = json.load(open(os.path.join(HERE, "oracle_meta.json"))) if os.path.exists(os.path.join(HERE, "oracle_meta.json")) else {}
K = int(M.get("K", 1)); interp = M.get("interpolate", "hold")
CHUNK_S = 1.0
r = Robot(timeout=3600)
spec = r.spec(); hz = float(spec.get("control_hz", 100)); dt = K / hz
cam = [(spec.get("default_cameras") or list(spec["cameras"]))[0]]
print("spec:", spec["protocol"], "rows:", len(Q), "dt:", dt, flush=True)
rows_per_chunk = max(1, min(int(CHUNK_S / dt + 1e-9), int(spec.get("max_chunk_s", 10) / dt + 1e-9)))
t0 = time.time(); done = False; i = 0; crashes = 0
while i < len(Q) and not done:
    chunk = Q[i:i + rows_per_chunk]
    try:
        meta = {"type": "joint_position", "interpolate": interp, "video": "none", "note": f"oracle rows {i}..{i + len(chunk) - 1}", "dt": float(dt),
                **r._common(cam, None, None, False)}
        res = r._post("/submit", meta, [rcb1.array_part("actions", np.ascontiguousarray(chunk, dtype=np.float64))], timeout=1800)
    except EpisodeOver as e:
        print("episode over:", e); break
    except requests.exceptions.RequestException as e:     # the service crashed: it restarts and resumes the same episode
        crashes += 1
        print(f"service unreachable ({type(e).__name__}); waiting for it to resume the episode", flush=True)
        st = r.wait_ready(3600)
        print("resumed:", st, flush=True)
        if st.get("done"):
            done = True; print("done:", st.get("reason")); break
        n = int(st["control_steps"])
        if n % K:
            raise RuntimeError(f"resumed at control step {n}, not a row boundary (K = {K})")
        i = n // K; continue
    steps = int(res.meta["control_steps"])
    print(f"rows {i}..{i + len(chunk) - 1}: executed={res.meta['executed_rows']} control_steps={steps} clipped={res.meta['n_clipped']} "
          f"stopped={res.meta.get('stopped')} done={res.meta['done']}", flush=True)
    if res.meta["done"]:
        done = True; print("done:", res.meta["reason"]); break
    i = steps // K
print("status:", r.status(), "service crashes seen:", crashes, "wall %.0fs" % (time.time() - t0))
