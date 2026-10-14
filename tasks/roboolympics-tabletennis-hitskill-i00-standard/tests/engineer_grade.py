#!/usr/bin/env python3
"""reward.json of an Engineer task (tools/export_fexam.py): skilleval's report -> success = a valid evaluation whose
API-test success rate is at least the line. Numbers only."""
import json
import sys
from pathlib import Path

LOG = Path("/logs/verifier")
line, n_expected = float(sys.argv[1]), int(sys.argv[2])
try:
    rep = json.loads((LOG / "report.json").read_text())
except (OSError, ValueError):
    rep = None
out = {"success": 0, "infra_error": 0, "grader_error": 0, "line": line}
if rep is None:
    out["grader_error"] = 1
else:
    api = rep.get("api_test") or {}
    n = int(api.get("n") or api.get("cases") or len(rep.get("api_rows") or []))
    rate = float(api.get("success_rate") or 0.0)
    det = bool((rep.get("determinism") or {}).get("deterministic", True))
    # skilleval: valid = false with a reason = the deliverable's own problem (missing, does not load, no function):
    # a valid 0 for the player, not a grader error
    deliverable_ok = bool(rep.get("valid", True))
    out.update(api_success_rate=rate, api_cases=n, api_successes=int(round(rate * n)), deterministic=int(det),
               deliverable_ok=int(deliverable_ok),
               eval_wall_s=float(rep.get("seconds") or rep.get("wall_s") or 0.0))
    for k, v in api.items():
        if isinstance(v, (int, float)) and not isinstance(v, bool) and k not in out:
            out["api_" + k] = v
    out["grader_error"] = int(deliverable_ok and n != n_expected)
    out["success"] = int(deliverable_ok and n == n_expected and rate >= line and det)
(LOG / "reward.json").write_text(json.dumps(out))
(LOG / "reward.txt").write_text(str(out["success"]) + "\n")
