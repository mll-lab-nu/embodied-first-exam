"""Trusted Harbor collect hook, invoked in sim after the agent stops (and after `kill -9 -1` in the agent's container).

Signals the service (SIGUSR1: cutoff, then finalization) until final.json is written, then waits, within the same
budget, for the video pass that follows the verdict (video.json); a missing video never fails the hook (PROTOCOL §4).
"""

import json
import os
from pathlib import Path
import signal
import time

root = Path(os.environ.get("RCB_DATA", "/data"))
end = time.monotonic() + 840
final = None
while time.monotonic() < end:
    try:
        value = json.loads((root / "final.json").read_text())
        if value.get("finalized") is True:
            final = value
            break
    except (OSError, ValueError):
        pass
    try:
        os.kill(int((root / "server.pid").read_text()), signal.SIGUSR1)
    except (OSError, ValueError):
        pass
    time.sleep(2)
if final is None:
    raise SystemExit("Evaluator did not finalize before the collection deadline")
print(json.dumps(final))
while time.monotonic() < end and not (root / "video.json").exists():
    time.sleep(2)
try:
    print(json.dumps(json.loads((root / "video.json").read_text())))
except (OSError, ValueError):
    print(json.dumps({"video": None, "note": "the video pass did not finish within the collect budget"}))
