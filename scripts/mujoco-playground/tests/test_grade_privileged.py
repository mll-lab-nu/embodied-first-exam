"""The privileged quadruped verifier (shared/grade.py) and the agent's session log: standard library only.

    python3 scripts/mujoco-playground/tests/test_grade_privileged.py

The log is self-reported cost, written in the agent's container: whatever bytes it holds, the verdict is written as
without it (a log that was not UTF-8 used to end the verifier before any reward file).
"""
import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

GRADE = Path(__file__).resolve().parents[1] / "shared" / "grade.py"
BAD = (b'{"ev": "session_start"}\n{"ev": "reset", "note": "\xff\xfe"}\n\x00\n{"ev": "session_start"}\n'
       + b"x" * 2**20 + b"\n")   # not UTF-8, a NUL, a 1 MB line (where the count stops)


class SessionLog(unittest.TestCase):
    def test_a_log_that_is_not_utf8_costs_no_verdict(self):
        with tempfile.TemporaryDirectory() as d:
            log, slog = Path(d, "log"), Path(d, "rcb_session_log.jsonl")
            slog.write_bytes(BAD)
            src = GRADE.read_text()
            self.assertIn('"/app/output/rcb_session_log.jsonl"', src)
            Path(d, "grade.py").write_text(src.replace('"/logs/agent/rcb/rcb_session_log.jsonl"', repr(str(slog)))
                                              .replace('"/app/output/rcb_session_log.jsonl"', repr(str(slog))))
            Path(d, "numpy.py").write_text("")   # no trajectory: numpy is imported and never used
            r = subprocess.run([sys.executable, "-B", str(Path(d, "grade.py")), "--instance", "x",
                                "--traj", str(Path(d, "none.npz"))], capture_output=True, text=True,
                               env={**os.environ, "RCB_VERIFIER_LOG_DIR": str(log)})
            self.assertEqual(r.returncode, 0, r.stderr[-400:])
            reward = json.loads((log / "reward.json").read_text())
            self.assertEqual((log / "reward.txt").read_text().strip(), "0")
            self.assertEqual((reward["missing_trajectory"], reward["grader_error"], reward["agent_sessions"],
                              reward["agent_resets"]), (1, 0, 2, 1), reward)


if __name__ == "__main__":
    unittest.main()
