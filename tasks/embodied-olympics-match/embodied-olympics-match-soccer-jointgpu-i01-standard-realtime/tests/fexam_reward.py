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
# policy_fingerprint.py on the replayed match (does the released Booster walking policy fit the seat's rows?), only
# when the seat won the live match (no replay otherwise; fingerprint.json is then absent).
try:
    fp = json.loads((DATA / "fingerprint.json").read_text())
except (OSError, ValueError):
    fp = None
if not isinstance(fp, dict):   # only the sim's audit writes it; anything else is no audit
    fp = None
acted = int(r.get("applied") or 0) > 0
# the audit's replay must reproduce the live match (replay_agrees, #328 review): otherwise its samples are not the match's
# (None: the audit found no final.json to compare with, while the verifier read one: not expected; the audit stands)
audited = fp is not None and fp.get("replay_agrees") is not False
r["policy_audit"] = int(audited)
r["policy_audit_replay_agrees"] = int(bool(fp and fp.get("replay_agrees")))
r["walking_policy_violation"] = int(bool(audited and fp.get("flag")))


def no_win():                  # a voided win is not counted as a win anywhere (won, A_won, ...)
    for k in [k for k in r if k == "won" or k.endswith("_won")]:
        r[k] = 0


if acted and r.get("success") and not audited:
    r["success"], r["infra_error"], r["policy_audit_missing"] = 0, 1, 1   # a win that could not be audited is void
    no_win()
elif r["walking_policy_violation"]:
    r["success"] = 0
    no_win()
(LOG / "reward.json").write_text(json.dumps({k: v for k, v in r.items() if isinstance(v, (int, float))}))
(LOG / "reward.txt").write_text(str(int(r.get("success", 0))) + "\n")
