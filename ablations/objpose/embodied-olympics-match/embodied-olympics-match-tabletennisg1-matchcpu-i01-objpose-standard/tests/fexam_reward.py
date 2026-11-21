#!/usr/bin/env python3
"""Embodied First Exam's reward fields on top of the Embodied Olympics Judge's reward.json (tests/grade.py): infra_error =
the trial is not a valid result (the Judge's technical_failure / void / grader_error); graded_by_live 1, replays 0 (the
live match is the verdict: final.json graded_by "live"); realtime, slowdown, opponent_level, steps from the sim's
final.json. Numbers only."""
import json
from pathlib import Path

LOG, DATA = Path("/logs/verifier"), Path("/data")
r = json.loads((LOG / "reward.json").read_text()) if (LOG / "reward.json").exists() else {"success": 0, "grader_error": 1}
try:
    f = json.loads((DATA / "final.json").read_text())
except (OSError, ValueError):
    f = {}
if not isinstance(f, dict):
    f = {}
live = f.get("graded_by") == "live" and f.get("verdict_replay") is False
r["infra_error"] = int(bool(r.get("technical_failure", 1)) or bool(r.get("void")) or bool(r.get("grader_error"))
                       or not live)
if r["infra_error"]:
    r["success"] = 0
r["graded_by_live"] = int(live)
r["replays"] = 0
r["realtime"] = 0
r["slowdown"] = float(f.get("slowdown") or 0)
r["opponent_level"] = int((f.get("cfg") or {}).get("level") or 0) if str((f.get("cfg") or {}).get("level") or "0").isdigit() else 0
r["steps"] = int(f.get("steps") or 0)
r["replay_video"] = int((DATA / "replay.mp4").exists())
(LOG / "reward.json").write_text(json.dumps({k: v for k, v in r.items()
                                             if isinstance(v, (int, float)) and k != "deterministic"}))
(LOG / "reward.txt").write_text(str(int(r.get("success", 0))) + "\n")
