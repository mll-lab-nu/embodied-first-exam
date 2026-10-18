"""Oracle (standard mode): stream the validated actuator rows through the agent's client.

One row per control (`hold`, dt = 1 / spec()["control_hz"]), in chunks of at most 250 rows and 10 s. The rows are sent
as float64 through the client's own request path (the service accepts any float dtype), so the service executes the
validated targets bit for bit. After a service crash the script waits until the service has resumed the SAME episode,
reads how many controls it executed and continues from the next row. The hand is the service's (DEXHAND_HAND on the
sim service); a hand or width mismatch stops the oracle.
"""

import os
import sys
import time

import numpy as np
import requests

sys.path.insert(0, "/opt/tools")
import rcb1  # noqa: E402
from rcb_client import EpisodeOver, Robot  # noqa: E402

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(1, HERE)
from solution_parts import load  # noqa: E402  (trajectory.npz, or trajectory.json + parts checked by sha256)

ROWS, HAND = load(HERE)
robot = Robot(timeout=3600)
spec = robot.spec()
HZ = float(spec.get("control_hz", 50))
DT = 1.0 / HZ
CHUNK = max(1, min(250, int(float(spec.get("max_chunk_s", 10)) * HZ + 1e-9)))
dim = int(spec["action_types"]["joint_position"]["dim"])
print("spec:", spec["protocol"], "robot:", spec.get("robot"), "hand:", spec.get("hand"), "dim:", dim, flush=True)
if dim != ROWS.shape[1] or spec.get("hand", "sharpa") != HAND:
    raise SystemExit(f"oracle rows are {HAND} width {ROWS.shape[1]}; the service runs {spec.get('hand')} width {dim}")
start = time.time()
index, done, crashes = 0, False, 0
while index < len(ROWS) and not done:
    chunk = ROWS[index:index + CHUNK]
    try:
        # video "none" at 1 frame per simulated second: the service still samples frames for the call's record,
        # so the lowest rate keeps a long oracle fast; it never changes the executed controls.
        meta = {"type": "joint_position", "interpolate": "hold", "video": "none", "dt": DT, "video_fps": 1,
                "note": f"oracle rows {index}..{index + len(chunk) - 1}",
                "cameras": (spec.get("default_cameras") or list(spec["cameras"]))[:1], "depth": "none"}
        part = rcb1.array_part("actions", np.ascontiguousarray(chunk, dtype=np.float64))
        result = robot._post("/submit", meta, [part], timeout=1800)
    except EpisodeOver as error:
        print("episode over:", error)
        break
    except requests.exceptions.RequestException as error:
        crashes += 1
        print(f"service unreachable ({type(error).__name__}); waiting for the same episode", flush=True)
        state = robot.wait_ready(3600)
        if state.get("done"):
            break
        index = int(state["control_steps"])
        continue
    steps = int(result.meta["control_steps"])
    print(f"rows {index}..{index + len(chunk) - 1}: control_steps={steps} done={result.meta['done']} "
          f"reason={result.meta['reason']}", flush=True)
    done = bool(result.meta["done"])
    index = steps
print("status:", robot.status(), "crashes:", crashes, "wall %.0fs" % (time.time() - start))
