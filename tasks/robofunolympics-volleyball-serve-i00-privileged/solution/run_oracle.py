"""Run the family's reference controller (oracle.py: solve(s), closed loop on the privileged state through the task's
own tooling) and write /app/output/trajectory.npz from the rows it stepped."""
import json
import sys

sys.path.insert(0, "/solution")
from rcb_rfo import Session  # noqa: E402

import oracle  # noqa: E402

s = Session("/app/instance.json")
oracle.solve(s)
st = s.status()
print(json.dumps({k: st[k] for k in ("success", "failed", "stages", "metrics", "steps")}))
s.save_trajectory()
