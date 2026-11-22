#!/usr/bin/env python3
"""The ablation's counts (tests/test.sh, after fexam_reward.py): numbers from the sim's final.json added to reward.json
when present. first_success: a success with no reset and no load."""
import json
from pathlib import Path

LOG, DATA = Path("/logs/verifier"), Path("/data")
try:
    r = json.loads((LOG / "reward.json").read_text())
    f = json.loads((DATA / "final.json").read_text())
except (OSError, ValueError):
    raise SystemExit(0)
for k in ("resets", "saves", "loads", "episodes", "state_queries", "resets_at_success", "loads_at_success"):
    if isinstance(f.get(k), (int, float)) and not isinstance(f.get(k), bool):
        r[k] = f[k]
if "finished" in f:
    r["finished"] = int(bool(f["finished"]))
if "resets" in f:
    r["first_success"] = int(bool(r.get("success")) and (f.get("resets") or 0) + (f.get("loads") or 0) == 0)
(LOG / "reward.json").write_text(json.dumps({k: v for k, v in r.items() if isinstance(v, (int, float))}))
