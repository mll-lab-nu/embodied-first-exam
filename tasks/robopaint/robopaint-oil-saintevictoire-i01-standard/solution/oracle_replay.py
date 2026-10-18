"""Oracle (standard mode): streams the privileged oracle's joint targets (one row per 20 Hz control step, `hold`) as `joint_position`
chunks through the client — the same interface an agent has. Uses no privileged information at run time (only the pre-recorded
targets); the service's recorded trajectory is then exactly the privileged oracle's. If the service crashes it resumes the same
episode (spec["on_service_error"]): the oracle waits until it answers again and goes on from the control step it reports."""
import json, os, sys, time
import numpy as np
import requests
sys.path.insert(0, "/opt/tools")
from rcb_client import Robot, EpisodeOver
HERE = os.path.dirname(os.path.abspath(__file__))
Q = np.load(os.path.join(HERE, "oracle_qpos.npy")).astype(np.float32)           # (N, 7), one row per K control steps
M = json.load(open(os.path.join(HERE, "oracle_meta.json"))) if os.path.exists(os.path.join(HERE, "oracle_meta.json")) else {}
K = int(M.get("K", 1)); interp = M.get("interpolate", "hold")
r = Robot(); spec = r.spec(); hz = float(spec.get("control_hz", 20)); dt = K / hz
print("spec:", spec["protocol"], "rows:", len(Q), "dt:", dt, flush=True)
rows_per_chunk = max(1, int(spec.get("max_chunk_s", 10) / dt + 1e-9))
t0 = time.time(); i = 0
while i < len(Q):
    chunk = Q[i:i + rows_per_chunk]
    try:
        res = r.submit("joint_position", chunk, dt=dt, interpolate=interp, cameras=["canvas_cam"], video="none", note=f"oracle rows {i}+")
    except EpisodeOver as e:
        print("episode over:", e); break
    except requests.exceptions.RequestException as e:       # the service crashed: it restarts and resumes the same episode
        print("service unreachable:", repr(e)[:200], "- waiting for it to resume", flush=True)
        st = r.wait_ready()
        n = int(st["control_steps"])
        print("service back:", st, flush=True)
        if n % K or not i <= n // K <= i + len(chunk):      # the lost call ran either not at all or completely
            raise SystemExit(f"resumed at control step {n}: not a boundary of the chunk in flight (rows {i}..{i + len(chunk)})")
        i = n // K
        continue
    n = int(res.meta["control_steps"])                       # every row is K control steps: the next row to send
    print(f"rows {i}..{n // K}: steps={res.meta['control_steps_chunk']} clipped={res.meta['n_clipped']} stopped={res.stopped}", flush=True)
    if n // K <= i:
        print("no progress; stopping"); break
    i = n // K
obs = r.get_obs(cameras=["canvas_cam"])
try:
    from PIL import Image
    os.makedirs("/app/output", exist_ok=True); Image.fromarray(obs.last["canvas_cam"]).save("/app/output/canvas_cam_final.png")
except Exception as exc:  # noqa: BLE001
    print("could not save the last frame:", exc)
print("status:", r.status(), "wall %.0fs" % (time.time() - t0))
