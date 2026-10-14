"""The privileged quadruped verifier (shared/grade.py): the agent's session log, and infrastructure vs agent failure.
Standard library only.

    python3 scripts/mujoco-playground/tests/test_grade_privileged.py

The log is self-reported cost, written in the agent's container: whatever bytes it holds, the verdict is written as
without it (a log that was not UTF-8 used to end the verifier before any reward file).

The replays run `rcb_quadruped.py replay` in fresh processes; here a stub of it (next to a copy of grade.py) answers as
the real one does on each path, and a stub numpy reads the trajectory (a JSON file). A replay process that dies, or a
start that does not rebuild, is no verdict on the agent (`infra_error` = 1, board 0105); the agent's own failure is a 0
with `infra_error` = 0.
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
            self.assertEqual((reward["missing_trajectory"], reward["grader_error"], reward["infra_error"],
                              reward["agent_sessions"], reward["agent_resets"]), (1, 0, 0, 2, 1), reward)


STUB_NUMPY = """import json
float64 = float
class _A:
    def __init__(self, rows):
        self.rows = rows; self.ndim = 2; self.shape = (len(rows), len(rows[0]) if rows else 0)
    def __len__(self):
        return len(self.rows)
class _D(dict):
    files = property(lambda self: list(self))
def load(path, allow_pickle=False):
    return _D(json.load(open(path)))
def asarray(x, dtype=None):
    return x if isinstance(x, _A) else _A(x)
def zeros(shape):
    return _A([])
def isfinite(a):
    return True
def all(x):
    return bool(x)
"""
# the replay tool: STUB_MODE = ok (success, same state), fail (the agent's 0), crash (no result: the process died),
# mismatch (the start did not rebuild), bad (the rows were refused: bad_trajectory)
STUB_TOOL = """import json, os, sys
a = sys.argv; mode = os.environ["STUB_MODE"]
if mode == "crash":
    sys.exit(3)
out = {"instance_ok": mode != "mismatch", "success": mode in ("ok", "mismatch"), "state_sha": "s", "video": False}
if mode == "bad":
    out.update(success=False, bad_trajectory=1, error="PrimitiveError()")
json.dump(out, open(a[a.index("--out") + 1], "w"))
"""


class InfraVsAgent(unittest.TestCase):
    def grade(self, mode: str) -> tuple[str, dict]:
        with tempfile.TemporaryDirectory() as d:
            d = Path(d); log = d / "log"
            (d / "grade.py").write_text(GRADE.read_text().replace('"/logs/agent/rcb/rcb_session_log.jsonl"', repr(str(d / "x")))
                                        .replace('"/app/output/rcb_session_log.jsonl"', repr(str(d / "x"))))
            (d / "numpy.py").write_text(STUB_NUMPY)
            (d / "rcb_quadruped.py").write_text(STUB_TOOL)
            (d / "instance.json").write_text(json.dumps({"horizon": 1000}))
            (d / "trajectory.npz").write_text(json.dumps({"actions": [[0.0] * 12] * 5}))
            r = subprocess.run([sys.executable, "-B", str(d / "grade.py"), "--instance", str(d / "instance.json"),
                                "--traj", str(d / "trajectory.npz")], capture_output=True, text=True, cwd=d,
                               env={**os.environ, "RCB_VERIFIER_LOG_DIR": str(log), "STUB_MODE": mode,
                                    "PYTHONPATH": str(d)})
            self.assertEqual(r.returncode, 0, r.stderr[-400:])
            return (log / "reward.txt").read_text().strip(), json.loads((log / "reward.json").read_text())

    def test_success(self):
        txt, rw = self.grade("ok")
        self.assertEqual((txt, rw["success"], rw["deterministic"], rw["infra_error"], rw["grader_error"]), ("1", 1, 1, 0, 0), rw)

    def test_the_agents_failure_is_its_0(self):
        for mode in ("fail", "bad"):
            txt, rw = self.grade(mode)
            self.assertEqual((txt, rw["success"], rw["infra_error"], rw["grader_error"]), ("0", 0, 0, 0), (mode, rw))

    def test_a_replay_process_without_a_result_is_no_verdict(self):
        txt, rw = self.grade("crash")
        self.assertEqual((txt, rw["success"], rw["infra_error"], rw["grader_error"], rw["replay_failed"]), ("0", 0, 1, 1, 1), rw)

    def test_a_start_that_does_not_rebuild_is_no_verdict(self):
        txt, rw = self.grade("mismatch")
        self.assertEqual((txt, rw["success"], rw["infra_error"], rw["grader_error"], rw["instance_mismatch"]), ("0", 0, 1, 1, 1), rw)


if __name__ == "__main__":
    unittest.main()
