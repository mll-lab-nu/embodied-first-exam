"""Oracle (standard mode): streams the privileged oracle's rows (AM-Bench's end-effector targets + gripper command, one per
120 Hz control step) as `ee_pose` chunks of one second (dt = 1/120 s, `hold`: each row exactly as recorded) through the
same client an agent has. Uses no privileged information at run time (only the pre-recorded rows).

One-second chunks make a dozen or more calls, each checkpointed by the service with its state hash (crash recovery). The
script follows spec()["on_service_error"]: after a connection error it waits until the service has resumed the SAME
episode, reads how many control steps it executed and continues from the next row, so a crash of the service costs only
time."""
import os, sys, time
import numpy as np
import requests
sys.path.insert(0, "/opt/tools")
from rcb_client import Robot, EpisodeOver
HERE = os.path.dirname(os.path.abspath(__file__))
Q = np.load(os.path.join(HERE, "oracle_qpos.npy")).astype(np.float64)           # (N, 8), one row per control step
CHUNK_S = 1.0
r = Robot(timeout=3600)   # a trial's first Isaac start compiles its shaders: up to ~10 min on a busy host
spec = r.spec(); hz = float(spec.get("control_hz", 120)); dt = 1.0 / hz
cam = [(spec.get("default_cameras") or list(spec["cameras"]))[0]]
print("spec:", spec["protocol"], "rows:", len(Q), "dt:", dt, flush=True)
rows_per_chunk = max(1, min(int(CHUNK_S / dt + 1e-9), int(spec.get("max_chunk_s", 10) / dt + 1e-9)))
t0 = time.time(); done = False; i = 0; crashes = 0
while i < len(Q) and not done:
    chunk = Q[i:i + rows_per_chunk]
    try:
        res = r.submit("ee_pose", chunk, dt=dt, interpolate="hold", cameras=cam, video="none", note=f"oracle rows {i}..{i + len(chunk) - 1}")
    except EpisodeOver as e:
        print("episode over:", e); break
    except requests.exceptions.RequestException as e:     # the service crashed: it restarts and resumes the same episode
        crashes += 1
        print(f"service unreachable ({type(e).__name__}); waiting for it to resume the episode", flush=True)
        st = r.wait_ready(3600)
        print("resumed:", st, flush=True)
        if st.get("done"):
            done = True; print("done:", st.get("reason")); break
        i = int(st["control_steps"]); continue
    steps = int(res.meta["control_steps"])
    print(f"rows {i}..{i + len(chunk) - 1}: executed={res.meta['executed_rows']} control_steps={steps} clipped={res.meta['n_clipped']} "
          f"stopped={res.meta.get('stopped')} done={res.meta['done']}", flush=True)
    if res.meta["done"]:
        done = True; print("done:", res.meta["reason"]); break
    i = steps
print("status:", r.status(), "service crashes seen:", crashes, "wall %.0fs" % (time.time() - t0))
