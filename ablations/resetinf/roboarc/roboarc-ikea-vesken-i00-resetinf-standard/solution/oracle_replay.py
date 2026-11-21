"""Oracle (standard mode, IKEA MuJoCo): submits the standard reference's control steps (solution/oracle_actions.npz,
`ctrl` (N, nu) float64: the privileged twin's reference trajectory, time-dilated to the joint-speed rule by
scripts/ikea_mujoco/standard/std_reference.py) through the client, one control step per row (dt = 1 / control_hz,
`hold`), in chunks of max_chunk_s, so that the service executes exactly these rows (no row needs the speed limiter:
n_clipped stays 0). The rows are sent as float64 (the client's own transport, Robot._post; Robot.submit sends float32):
MuJoCo on the CPU then reproduces them bit for bit. Uses no privileged information at run time (only the pre-recorded
rows). Source: scripts/ikea_mujoco/standard/oracle_replay.py (adapted from the RoboTangle standard oracle)."""
import os, sys, time
import numpy as np
import requests
sys.path.insert(0, "/opt/tools")
import rcb1
from rcb_client import Robot, EpisodeOver
HERE = os.path.dirname(os.path.abspath(__file__))
Q = np.ascontiguousarray(np.load(os.path.join(HERE, "oracle_actions.npz"))["ctrl"], dtype=np.float64)
r = Robot(); spec = r.spec(); hz = float(spec["control_hz"]); dt = 1.0 / hz
print("spec:", spec["protocol"], "rows:", len(Q), "dt:", dt, flush=True)
rows_per_chunk = max(1, int(spec.get("max_chunk_s", 10) / dt + 1e-9))
cam = spec["default_cameras"][0]


def submit64(chunk, note):
    meta = {"type": "joint_position", "interpolate": "hold", "video": "none", "note": note, "dt": dt, "cameras": [cam], "depth": "none"}
    return r._post("/submit", meta, [rcb1.array_part("actions", chunk)], timeout=1800)


t0 = time.time(); i = 0; n = 0; crashes = 0
while i < len(Q):
    chunk = Q[i:i + rows_per_chunk]
    try:
        res = submit64(chunk, f"oracle chunk {n} (row {i})")
    except EpisodeOver as e:
        print("episode over:", e); break
    except requests.exceptions.RequestException as e:
        # the service crashed: it restarts and resumes the SAME episode after the last call it completed
        crashes += 1
        if crashes > 3:
            raise
        print(f"service error ({type(e).__name__}); waiting for the resume", flush=True)
        st = r.wait_ready(timeout=7200)
        i = int(st["control_steps"])
        print(f"resumed: calls={st['calls']} control_steps={st['control_steps']} -> row {i}", flush=True)
        if st.get("done"):
            break
        continue
    rows = int(res.meta["executed_rows"]); n += 1
    print(f"chunk {n}: rows={rows} steps={res.meta['control_steps_chunk']} clipped={res.meta['n_clipped']} done={res.meta['done']} "
          f"time_left={res.meta['time_left_s']}", flush=True)
    if res.meta["done"]:
        print("done:", res.meta["reason"]); break
    if rows == 0:
        break
    i += rows
print("status:", r.status(), "wall %.0fs" % (time.time() - t0))
