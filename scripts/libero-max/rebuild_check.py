"""Rebuild one frozen LIBERO-MAX case on this host and compare it with what freeze.sh recorded (runs in the
eai-libero-max image, one process per case, see rebuild_check.sh).

    python rebuild_check.py <frozen/<case_id> dir>

Prints one JSON line: whether the start state rebuilt bit-exactly (`initial_ok`, the check every Session makes) and
whether the reference trajectory (oracle.npy) replays to the recorded final state, event step and success
(`final_ok`), plus the numeric kernels in use (lmx_tool.numerics()).
"""

import json
import sys
import time
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent / "shared"))
import lmx_tool  # noqa: E402

d = Path(sys.argv[1])
t0 = time.time()
inst = lmx_tool.load_instance(d / "instance.json")
live = json.loads((d / "report.json").read_text())["live"]
s = lmx_tool.Session(inst, check=False)
r = s.replay(np.load(d / "oracle.npy"))
out = {
    "case_id": d.name,
    "initial_ok": s.initial_state_sha == inst["initial_state_sha"],
    "final_ok": r["state_sha"] == live["state_sha"] and r["event_step"] == live["event_step"] and r["success"],
    "success": r["success"],
    "event_step": r["event_step"],
    "initial_state_sha": s.initial_state_sha[:12],
    "numerics": lmx_tool.numerics(),
    "wall_s": round(time.time() - t0, 1),
}
print(json.dumps(out))
