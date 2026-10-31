"""Oracle of the standard twin: the privileged task's reference trajectory (solution/oracle_rows.npz, the rows the scripted
demonstration recorded on the same frozen instance), submitted through the client in chunks of one control step per row.
The privileged rows hold NaN where the service takes a sentinel (spec action_types.ee_pose): a held arm becomes an all-zero
quaternion, no gap override a negative gap, an unchanged drive setting 0. Rows go as float64 (rcb_client.Robot.submit
sends float32), so the service executes the recorded rows exactly. Stops when the episode ends. After a service crash
(a connection error) it waits until the service has resumed the episode (spec on_service_error) and goes on from the row
the resumed episode has reached (status `step`)."""
import sys
import numpy as np
import requests
import rcb1
from rcb_client import Robot, EpisodeOver

A = np.load("/solution/oracle_rows.npz")["actions"].astype(np.float64)
R = A.copy()
for arm in (0, 1):
    held = ~np.all(np.isfinite(R[:, 7 * arm:7 * arm + 7]), axis=1)
    R[held, 7 * arm:7 * arm + 7] = 0.0
R[:, 16:18] = np.where(np.isfinite(R[:, 16:18]), R[:, 16:18], -1.0)
R[:, 18:22] = np.where(np.isfinite(R[:, 18:22]), R[:, 18:22], 0.0)
r = Robot()
spec = r.spec()
dt = 1.0 / float(spec["control_hz"])
n = max(1, int(float(spec["max_chunk_s"]) / dt) - 1)
print(f"[oracle] {len(R)} rows, chunks of {n}", flush=True)
i = 0
try:
    while i < len(R):
        chunk = np.ascontiguousarray(R[i:i + n])
        meta = {"type": "ee_pose", "dt": dt, "interpolate": "hold", "video": "none", "cameras": [spec["default_cameras"][0]]}
        try:
            res = r._post("/submit", meta, [rcb1.array_part("actions", chunk)], timeout=1800)
        except requests.exceptions.ConnectionError as e:     # the service crashed: it resumes after its last completed call
            st = r.wait_ready()
            print(f"[oracle] service error ({type(e).__name__}); resumed at row {st.get('step')}", flush=True)
            if st.get("done"):
                break
            i = int(st.get("step") or 0)
            continue
        i += int(res.meta.get("executed_rows") or 0)
        print(f"[oracle] {i}/{len(R)} rows, control_steps {res.meta.get('control_steps')}, done {res.meta.get('done')} "
              f"({res.meta.get('reason')})", flush=True)
        if res.meta.get("done"):
            break
        if not res.meta.get("executed_rows"):
            print("[oracle] nothing executed", res.meta.get("stopped")); break
except EpisodeOver as e:
    print("[oracle] episode over:", e)
sys.exit(0)
