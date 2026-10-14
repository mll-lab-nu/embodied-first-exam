"""Oracle (standard mode): replays the privileged oracle's joint targets, sampled every K control steps, as
`joint_position` chunks with dt = K/control_hz s, using the frozen service's reported control frequency (normally 40 Hz).
They are streamed through the same interface an agent
has. K = 1 with `hold` replays the recorded rows exactly. Uses no privileged information at run time.
Source: scripts/robowits/shared/oracle_replay.py; the rows come from scripts/robowits/oracles/<family>/oracle_qpos.npy."""
import json, os, sys, time
import numpy as np
import requests
sys.path.insert(0, "/opt/tools")
from rcb_client import Robot, EpisodeOver
HERE = os.path.dirname(os.path.abspath(__file__))
Q = np.load(os.path.join(HERE, "oracle_qpos.npy")).astype(np.float32)           # (N, action_dim), one row per K control steps
M = json.load(open(os.path.join(HERE, "oracle_meta.json"))) if os.path.exists(os.path.join(HERE, "oracle_meta.json")) else {}
K = int(M.get("K", 1)); interp = M.get("interpolate", "hold")
r = Robot(); spec = r.spec(); hz = float(spec.get("control_hz", 30)); dt = K / hz
print("spec:", spec["protocol"], "rows:", len(Q), "dt:", dt, flush=True)
rows_per_chunk = max(1, int(spec.get("max_chunk_s", 10) / dt + 1e-9))
t0 = time.time(); done = False; i = 0; n = 0; crashes = 0
while i < len(Q):
    chunk = Q[i:i + rows_per_chunk]
    try:
        res = r.submit("joint_position", chunk, dt=dt, interpolate=interp, cameras=[next(iter(spec["cameras"]))], video="none", note=f"oracle chunk {n} (row {i})")
    except EpisodeOver as e:
        print("episode over:", e); break
    except requests.exceptions.RequestException as e:
        # The service crashed (spec["on_service_error"]): it restarts and resumes the SAME episode in the state after the
        # last call it completed; the call in flight is lost as a whole. Wait for it, then continue after the rows it holds
        # (every row is K control steps from the episode start).
        crashes += 1
        if crashes > 3:
            raise
        print(f"service error ({type(e).__name__}); waiting for the resume", flush=True)
        st = r.wait_ready(timeout=3600)
        i = int(st["control_steps"]) // K
        print(f"resumed: calls={st['calls']} control_steps={st['control_steps']} resumes={st.get('resumes')} -> row {i}", flush=True)
        if st.get("done"):
            done = True; break
        continue
    rows = int(res.meta["executed_rows"]); n += 1
    print(f"chunk {n}: rows={rows} steps={res.meta['control_steps_chunk']} clipped={res.meta['n_clipped']} done={res.meta['done']} stopped={res.stopped}", flush=True)
    if res.meta["done"]: done = True; print("done:", res.meta["reason"]); break
    if rows == 0:
        break
    i += rows
if not done:
    obs = r.get_obs(seconds=1.0, cameras=[next(iter(spec["cameras"]))], video="none"); print("settle:", obs.meta["done"], obs.meta["reason"])
print("status:", r.status(), "wall %.0fs" % (time.time() - t0))
