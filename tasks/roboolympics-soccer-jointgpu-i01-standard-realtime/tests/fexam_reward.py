#!/usr/bin/env python3
"""The hub's reward fields on top of our grader's reward.json (pilots/soccer_joint/export_fexam_pair.py): infra_error =
the trial is not a valid result (our technical_failure); realtime, slowdown, opponent_level from the sim's final.json;
gpu_tier = this task's resource tier (1 = the GPU tier). Numbers only."""
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
r["gpu_tier"] = 1
r["replay_video"] = int((DATA / "replay.mp4").exists())
# The rule "no walking or balancing policy you did not build" (instruction): the sim's collect hook ran
# policy_fingerprint.py on the replayed match (does the released Booster walking policy fit the seat's rows?).
try:
    fp = json.loads((DATA / "fingerprint.json").read_text())
except (OSError, ValueError):
    fp = None
acted = int(r.get("applied") or 0) > 0
r["policy_audit"] = int(fp is not None)
r["walking_policy_violation"] = int(bool(fp and fp.get("flag")))
if r["walking_policy_violation"]:
    r["success"] = 0
elif acted and fp is None and r.get("success"):
    r["success"], r["infra_error"], r["policy_audit_missing"] = 0, 1, 1   # a win that could not be audited is void
(LOG / "reward.json").write_text(json.dumps({k: v for k, v in r.items() if isinstance(v, (int, float))}))
(LOG / "reward.txt").write_text(str(int(r.get("success", 0))) + "\n")
