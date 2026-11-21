"""Standard-mode oracle: stream the privileged reference trajectory's rows (oracle_trajectory.npz, the privileged twin's
solution: `actions` (T, 8), 7 joint targets + the gripper command, one row per 20 Hz control step) through the eai-standard client in one-second `joint_position` chunks
with `hold` interpolation (each row held for exactly one control step: the same commands the privileged replay feeds). After
a service crash it waits for the resumed episode and continues from the control step the service reports."""
import os, sys, time
import numpy as np
sys.path.insert(0, "/opt/tools")
from rcb_client import Robot, EpisodeOver  # noqa: E402

Q = np.load(os.path.join(os.path.dirname(os.path.abspath(__file__)), "oracle_trajectory.npz"))["actions"].astype(np.float32)
r = Robot(); spec = r.spec(); hz = int(spec["control_hz"])
i = int(r.status().get("control_steps") or 0)
while i < len(Q):
    try:
        res = r.submit("joint_position", Q[i:i + hz], dt=1.0 / hz, interpolate="hold", video="none")
        i += int(res.meta.get("control_steps_chunk") or 0)
        if res.meta.get("done"):
            break
    except EpisodeOver:
        break
    except Exception as exc:  # noqa: BLE001 — a service crash: wait for the resumed episode, continue where it stands
        print(f"[oracle] {exc!r}; waiting for the service", flush=True)
        r.wait_ready(); i = int(r.status().get("control_steps") or 0); time.sleep(1)
print(r.status(), flush=True)
