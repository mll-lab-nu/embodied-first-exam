#!/usr/bin/env python3
"""tests/grade.py of the RoboSafeBench standard-realtime tasks (shared/realtime/grade.py on the standard grader, copied
in as grade_rsb.py) on hand-made /data contents (standard library only): the verdict and success are the standard
grader's; the clock's record is repeated as numbers (a missing one is 0) and decides nothing.

    python3 scripts/robosafe/tests/test_grade_rt.py
"""
import json
import os
import pathlib
import shutil
import subprocess
import sys
import tempfile

SHARED = pathlib.Path(__file__).resolve().parents[1] / "shared"
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
from test_grade import FINAL_OK, VERDICT, check  # noqa: E402

CLOCK = {"clock_s": 61.2, "max_lag_s": 0.21, "stalls": 2, "stalled_s": 1.4, "stalled_share": 0.0229, "held_steps": 310,
         "late_steps": 3, "max_queue_wait_s": 0.05, "requests_refused": 1, "request_busy_s": 2.5, "slowdown": 1.0,
         "realtime": 1, "protocol": "eai-standard/2.3"}


def grade(final, verdict=None) -> tuple[str, dict]:
    with tempfile.TemporaryDirectory() as d:
        data, logs, tests = pathlib.Path(d, "data"), pathlib.Path(d, "logs"), pathlib.Path(d, "tests")
        data.mkdir()
        tests.mkdir()
        shutil.copy(SHARED / "realtime/grade.py", tests / "grade.py")
        shutil.copy(SHARED / "standard/grade.py", tests / "grade_rsb.py")
        if final is not None:
            (data / "final.json").write_text(json.dumps(final))
        if verdict is not None:
            (data / "verdict.json").write_text(json.dumps(verdict))
        (data / "ticks.f64").write_bytes(b"\0" * 16)
        env = {**os.environ, "RCB_DATA": str(data), "RCB_VERIFIER_LOG_DIR": str(logs)}
        subprocess.run([sys.executable, str(tests / "grade.py")], env=env, check=True, capture_output=True)
        return ((logs / "reward.txt").read_text().strip(), json.loads((logs / "reward.json").read_text()),
                (logs / "ticks.f64").exists())


def main() -> int:
    bad = 0
    txt, r, ticks = grade({**FINAL_OK, **CLOCK}, {**VERDICT, "clock_hook": True})
    bad += check("a passing episode scores 1", txt == "1" and r["success"] == 1 and r["graded_by_live"] == 1)
    bad += check("numbers only", all(isinstance(v, (int, float)) and not isinstance(v, bool) for v in r.values()))
    bad += check("the clock's record repeated", all(r[k] == CLOCK[k] for k in CLOCK if k not in ("realtime", "protocol")))
    bad += check("realtime and clock_hook", r["realtime"] == 1 and r["clock_hook"] == 1)
    bad += check("the standard verdict fields", r["outcome_correct_stop"] == 1 and r["judgment_safe_judgment"] == 1)
    bad += check("the tick log copied", ticks)
    txt, r, _ = grade({**FINAL_OK, **CLOCK, "stalls": 40, "stalled_s": 30.0, "stalled_share": 0.5}, VERDICT)
    bad += check("stalls decide nothing", txt == "1" and r["stalls"] == 40 and r["clock_hook"] == 0)
    txt, r, _ = grade({**FINAL_OK, "success": False, "live_success": False}, VERDICT)
    bad += check("a missing clock field is 0, the standard rule still decides", txt == "0" and r["stalls"] == 0
                 and r["clock_s"] == 0)
    txt, r, _ = grade(None)
    bad += check("no final.json: infra_error, the clock's fields 0", txt == "0" and r["infra_error"] == 1 and r["max_lag_s"] == 0)
    print("FAIL" if bad else "ok", f"({bad} failed)")
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
