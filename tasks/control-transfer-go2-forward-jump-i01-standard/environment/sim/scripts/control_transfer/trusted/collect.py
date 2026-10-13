"""Trusted Harbor collect hook, invoked in sim after the agent stops."""

import json
import os
from pathlib import Path
import signal
import time

root = Path(os.environ.get("RCB_DATA", "/data"))
end = time.monotonic() + 1740
while time.monotonic() < end:
    try:
        final = json.loads((root / "final.json").read_text())
        if final.get("finalized") is True:
            print(json.dumps(final))
            raise SystemExit(0)
    except (OSError, ValueError):
        pass
    try:
        os.kill(int((root / "server.pid").read_text()), signal.SIGUSR1)
    except (OSError, ValueError):
        pass
    time.sleep(2)
raise SystemExit("Evaluator did not finalize before the collection deadline")
