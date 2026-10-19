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
def _rows(p):
    try:
        rows = [json.loads(x) for x in p.read_text().splitlines() if x.strip()]
        return [x for x in rows if isinstance(x, dict)]   # Embodied First Exam (board 0146, #300 review)
    except (OSError, ValueError):
        return []
calls = [c for c in _rows(DATA / "inloop_A.jsonl") if c.get("op") == "call"]
loads = [c for c in _rows(DATA / "inloop_A.jsonl") if c.get("op") == "load"]
r["skill_versions_played"] = len({c.get("sha256") for c in calls if isinstance(c.get("sha256"), str) and c.get("sha256")})
r["skill_loads_failed"] = sum(1 for c in loads if not c.get("ok"))
r["skill_calls"] = len(calls)
r["skill_calls_failed"] = sum(1 for c in calls if not c.get("ok"))
r["skill_hit_calls"] = sum(1 for c in calls if c.get("fn") == "hit")
r["skill_hit_calls_failed"] = sum(1 for c in calls if c.get("fn") == "hit" and not c.get("ok"))
(LOG / "reward.json").write_text(json.dumps({k: v for k, v in r.items() if isinstance(v, (int, float))}))
(LOG / "reward.txt").write_text(str(int(r.get("success", 0))) + "\n")
