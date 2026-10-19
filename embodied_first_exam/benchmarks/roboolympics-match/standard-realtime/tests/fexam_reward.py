#!/usr/bin/env python3
"""The hub's reward fields on top of our grader's reward.json (tools/export_fexam.py): infra_error = the trial is not
a valid result (our technical_failure); realtime, slowdown, opponent_level from the sim's final.json. Numbers only."""
import json
from pathlib import Path

LOG, DATA = Path("/logs/verifier"), Path("/data")
r = json.loads((LOG / "reward.json").read_text()) if (LOG / "reward.json").exists() else {"success": 0, "grader_error": 1}
try:
    f = json.loads((DATA / "final.json").read_text())
except (OSError, ValueError):
    f = {}
r["infra_error"] = int(bool(r.get("technical_failure", 1)) or bool(r.get("grader_error")))
r["realtime"] = 1
r["slowdown"] = float(f.get("slowdown") or 0)
r["opponent_level"] = int((f.get("cfg") or {}).get("level") or 0)
r["steps"] = int(f.get("steps") or 0)
r["success"] = int(bool(r.get("valid_trial")) and bool(r.get("A_won")))   # the agent's seat A against built-in seats
(LOG / "reward.json").write_text(json.dumps({k: v for k, v in r.items() if isinstance(v, (int, float))}))
(LOG / "reward.txt").write_text(str(int(r.get("success", 0))) + "\n")
