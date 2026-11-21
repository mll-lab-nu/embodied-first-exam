"""Oracle (standard mode): streams the privileged oracle's joint targets (`oracle_qpos.npy`, one row per 10 ms control
step) as one-second `joint_position` chunks (`hold`, dt = 0.01 s) through the same client an agent has. The client sends
the rows as float64 and the service executes them as sent, so the episode runs exactly the recorded rows. Uses no
privileged information at run time (only the pre-recorded targets).

It spends the task's reset budget first (spec()["budget"]["reset"]): each scouting episode runs the first second of the
rows and is reset away, so every oracle run also checks that a reset restores the frozen start (the service refuses a
reset that does not: instance_mismatch); the last episode, the graded one, runs all the rows from the start.

One-second chunks make a few dozen calls, each checkpointed by the service with its state hash (crash recovery). The
script follows spec()["on_service_error"]: after a connection error or a 5xx it waits until the service answers again
(it resumed the SAME episode), reads how many control steps it executed and continues from the next row."""
import os, sys, time
import numpy as np
import requests
sys.path.insert(0, "/opt/tools")
from rcb_client import Robot, EpisodeOver
HERE = os.path.dirname(os.path.abspath(__file__))
Q = np.load(os.path.join(HERE, "oracle_qpos.npy")).astype(np.float64)           # (N, D), one row per control step
r = Robot(timeout=3600)
spec = r.spec(); dt = float(spec["control_dt"]); CH = max(1, int(round(1.0 / dt)))
CAM = dict(cameras=[sorted(spec["cameras"])[0]], video="none")                  # one camera's last frame: the cheapest call
resets = int(spec["budget"]["reset"])
print("spec:", spec["protocol"], "rows:", len(Q), "resets:", resets, flush=True)


def wait_status() -> dict:
    """The service's status once it answers again after a crash; a service that gave up on the trial answers 409."""
    t = time.time()
    while time.time() - t < 3600:
        try:
            return r.status()
        except requests.exceptions.HTTPError as e:
            if e.response is not None and e.response.status_code == 409:
                raise SystemExit(f"the service gave up on this trial: {e}")
            time.sleep(3)
        except requests.exceptions.RequestException:
            time.sleep(3)
    raise RuntimeError("the service did not come back")


def reset() -> None:
    """POST /reset; a reset lost with a crash never happened (the service resumes the old episode), so retry it."""
    ep = int(r.status()["episode"])
    for _ in range(6):
        try:
            res = r.reset(cameras=CAM["cameras"])
            print("reset ->", {k: res.meta.get(k) for k in ("episode", "resets_left", "control_steps", "control_steps_total")}, flush=True)
            return
        except (requests.exceptions.RequestException, RuntimeError) as e:
            print(f"reset failed ({type(e).__name__}: {str(e)[:120]}); waiting for the service", flush=True)
            if int(wait_status()["episode"]) > ep:
                return
    raise RuntimeError("reset kept failing")


def run(rows: np.ndarray) -> dict:
    """Stream rows from the episode's current step; returns the last status."""
    i, crashes = int(r.status()["control_steps"]), 0
    while i < len(rows):
        try:
            res = r.submit("joint_position", rows[i:i + CH], dt=dt, interpolate="hold", note=f"oracle rows {i}..", **CAM)
        except EpisodeOver as e:
            print("episode over:", e, flush=True); break
        except (requests.exceptions.RequestException, RuntimeError) as e:   # the service crashed: it resumes the same episode
            crashes += 1
            print(f"service error ({type(e).__name__}: {str(e)[:120]}); waiting for it to resume", flush=True)
            if crashes > 6:
                raise
            st = wait_status()
            if st.get("done"):
                break
            i = int(st["control_steps"]); continue
        i = int(res.meta["control_steps"])
        if res.meta["done"]:
            print("done:", res.meta["reason"], "at control step", i, flush=True); break
    return r.status()


for k in range(resets):                     # scouting episodes, reset away (never graded)
    st = run(Q[:CH])
    print(f"episode {st.get('episode')}: {st['control_steps']} control steps, done={st['done']}; reset", flush=True)
    reset()
st = run(Q)                                  # the graded episode: every row from the frozen start
print("status:", st, flush=True)
