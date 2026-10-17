"""Tests for the standard-mode verifier (shared/standard/grade.py) on synthetic final.json files: standard library only.

    python3 -m unittest discover -s scripts/myosuite/tests

What is graded is the sim sidecar's final.json: since 2026-10-17 (owner, board 0151) the live episode's verdict
("graded_by": "live", nothing replayed). An infrastructure failure -- no final.json, one that cannot be read, one the
collect hook never finalized, a give-up after crashes that were not all inside the agent's calls, a scene that did not
start at the frozen instance -- is infra_error = 1, never the agent's 0 (PROTOCOL §2.6); the agent's own failures (a
crash inside its calls, a simulator error from its actions, a timeout) stay its 0. The service, hook and grader run
together in test_standard_server.py.
Last, the privileged verifier (shared/grade.py) and the one file of the agent's it reads as text, the session log.
"""
import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

GRADE = Path(__file__).resolve().parents[1] / "shared" / "standard" / "grade.py"
PRIVILEGED = GRADE.parents[1] / "grade.py"
GOOD = {"finalized": True, "graded_by": "live", "replays": 0, "success": True, "live_success": True, "reason": "success",
        "video": True, "video_pending": False, "video_source": "render", "control_steps": 72, "n_actions": 72,
        "live_sha": "abc", "state_sha": "abc"}


class Grade(unittest.TestCase):
    def grade(self, final) -> tuple[str, dict]:
        with tempfile.TemporaryDirectory() as d:
            data, log = Path(d, "data"), Path(d, "log")
            data.mkdir()
            if final is not None:
                (data / "final.json").write_text(final if isinstance(final, str) else json.dumps(final))
            env = {**os.environ, "RCB_DATA": str(data), "RCB_VERIFIER_LOG_DIR": str(log)}
            subprocess.run([sys.executable, str(GRADE)], env=env, check=True, capture_output=True)
            reward = json.loads((log / "reward.json").read_text())
            self.assertTrue(all(isinstance(v, (int, float)) for v in reward.values()), reward)   # numbers only
            for key in ("success", "live_success", "graded_by_live", "replays", "infra_error", "grader_error",
                        "sim_error", "finalized", "missing_log"):                                # in every branch
                self.assertIn(key, reward)
            self.assertEqual((reward["graded_by_live"], reward["replays"]), (1, 0))
            for key in ("replay_success", "deterministic", "live_matches_replay"):              # no replay any more
                self.assertNotIn(key, reward)
            return (log / "reward.txt").read_text().strip(), reward

    def test_a_live_success_passes(self):
        txt, r = self.grade(GOOD)
        self.assertEqual((txt, r["success"], r["live_success"], r["infra_error"], r["finalized"], r["video_rendered"]),
                         ("1", 1, 1, 0, 1, 1))

    def test_a_live_failure_is_the_agents_0(self):
        for reason in ("timeout", "failure: object dropped", "error"):
            txt, r = self.grade({**GOOD, "success": False, "live_success": False, "reason": reason})
            self.assertEqual((txt, r["success"], r["infra_error"], r["grader_error"]), ("0", 0, 0, 0), reason)
        self.assertEqual(self.grade({**GOOD, "success": False, "live_success": False, "reason": "error"})[1]["sim_error"], 1)

    def test_a_window_that_did_not_hold_is_a_failure(self):
        """The hold / track window is part of the task's rule live: an episode whose window broke never ended in
        success (the service's success is False), and a success the service's live rule took away is no pass."""
        txt, r = self.grade({**GOOD, "success": False, "live_success": False, "reason": "failure: on track at 40 of 57 steps"})
        self.assertEqual((txt, r["success"], r["infra_error"], r["task_failure"]), ("0", 0, 0, 1))
        txt, r = self.grade({**GOOD, "success": False, "live_success": True, "live_rule": False})
        self.assertEqual((txt, r["success"], r["live_success"], r["infra_error"]), ("0", 0, 1, 0))

    def test_a_video_that_failed_changes_nothing(self):
        txt, r = self.grade({**GOOD, "video": False, "video_pending": False})
        self.assertEqual((txt, r["success"], r["infra_error"], r["video_rendered"]), ("1", 1, 0, 0))

    def test_a_missing_final_json_is_infrastructure(self):
        txt, r = self.grade(None)
        self.assertEqual((txt, r["success"], r["missing_log"], r["infra_error"], r["grader_error"]), ("0", 0, 1, 1, 0))

    def test_an_unreadable_final_json_is_infrastructure(self):
        for text in ('{"finalized": true, "succ', "[1, 2]", "null", ""):
            txt, r = self.grade(text)
            self.assertEqual((txt, r["success"], r["infra_error"], r["grader_error"]), ("0", 0, 1, 1), text)

    def test_a_final_json_without_a_verdict_is_infrastructure(self):
        """The service's live summary only (the collect hook ran out of time, or died, before it wrote the verdict), or a
        finalized file that holds neither the live verdict nor a give-up."""
        txt, r = self.grade({"finalized": False, "success": True, "reason": "success", "control_steps": 72})
        self.assertEqual((txt, r["success"], r["live_success"], r["finalized"], r["infra_error"]), ("0", 0, 1, 0, 1))
        txt, r = self.grade({"finalized": True, "success": True, "reason": "success"})
        self.assertEqual((txt, r["success"], r["no_verdict"], r["infra_error"]), ("0", 0, 1, 1))
        txt, r = self.grade({**GOOD, "infra_error": 1, "error": "collect hook: the sim service did not end and dump"})
        self.assertEqual((txt, r["success"], r["infra_error"]), ("0", 0, 1))

    def test_crashes_between_calls_are_infrastructure_and_in_calls_the_agents(self):
        gave_up = {"finalized": True, "gave_up": True, "done": True, "success": False}
        for reason in ("sim_crashed", "resume_failed: replayed state differs from the logged one"):
            txt, r = self.grade({**gave_up, "reason": reason, "infra_error": 1})
            self.assertEqual((txt, r["success"], r["infra_error"], r["gave_up"]), ("0", 0, 1, 1), reason)
        txt, r = self.grade({**gave_up, "reason": "sim_crashed_on_call"})
        self.assertEqual((txt, r["success"], r["infra_error"], r["sim_crashed_on_call"], r["no_verdict"]), ("0", 0, 0, 1, 0))

    def test_a_scene_that_was_not_the_frozen_instance_is_infrastructure(self):
        txt, r = self.grade({"finalized": True, "gave_up": True, "success": False, "infra_error": 1, "instance_mismatch": 1,
                             "reason": "instance_mismatch: the scene started at 1, the frozen instance records 2"})
        self.assertEqual((txt, r["success"], r["infra_error"], r["grader_error"], r["instance_mismatch"]), ("0", 0, 1, 1, 1))
        txt, r = self.grade({**GOOD, "instance_mismatch": 1})        # never a pass, whatever else the file says
        self.assertEqual((txt, r["success"], r["infra_error"]), ("0", 0, 1))


class PrivilegedSessionLog(unittest.TestCase):
    """The agent's session log is self-reported cost: whatever bytes it holds, the verdict is written as without it."""

    BAD = (b'{"ev": "session_start"}\n{"ev": "reset", "note": "\xff\xfe"}\n\x00\n{"ev": "session_start"}\n'
           + b"x" * 2**20 + b"\n")   # not UTF-8, a NUL, a 1 MB line (where the count stops)

    def test_a_log_that_is_not_utf8_costs_no_verdict(self):
        with tempfile.TemporaryDirectory() as d:
            log, slog = Path(d, "log"), Path(d, "rcb_session_log.jsonl")
            slog.write_bytes(self.BAD)
            src = PRIVILEGED.read_text()
            self.assertIn('"/app/output/rcb_session_log.jsonl"', src)
            Path(d, "grade.py").write_text(src.replace('"/app/output/rcb_session_log.jsonl"', repr(str(slog))))
            Path(d, "numpy.py").write_text("")   # no trajectory: numpy is imported and never used (standard library only)
            r = subprocess.run([sys.executable, "-B", str(Path(d, "grade.py")), "--family", "x", "--instance", "x",
                                "--traj", str(Path(d, "none.npz"))], capture_output=True, text=True,
                               env={**os.environ, "RCB_VERIFIER_LOG_DIR": str(log)})
            self.assertEqual(r.returncode, 0, r.stderr[-400:])
            reward = json.loads((log / "reward.json").read_text())
            self.assertEqual((log / "reward.txt").read_text().strip(), "0")
            self.assertEqual((reward["missing_trajectory"], reward["grader_error"], reward["agent_sessions"],
                              reward["agent_resets"]), (1, 0, 2, 1), reward)


STUB_NUMPY = '''"""A stand-in for numpy with what grade.py uses: a trajectory / instance file is JSON here."""
import json


class _Shape(tuple):
    pass


class _Array:
    def __init__(self, rows):
        self.rows = rows
        self.ndim = 2 if rows and isinstance(rows[0], list) else 1
        self.shape = (len(rows), len(rows[0]) if self.ndim == 2 and rows else 0)[: self.ndim]

    def __len__(self):
        return len(self.rows)


class _File(dict):
    files = property(lambda self: list(self))


float64 = float


def load(path, allow_pickle=False):
    return _File({k: (_Array(v) if isinstance(v, list) else v) for k, v in json.load(open(path)).items()})


def asarray(a, dtype=None):
    return a


def isfinite(a):
    return [x == x and abs(x) != float("inf") for r in a.rows for x in r]


def all(a):
    return min(a) if a else True


def savez(path, actions, task):
    json.dump({"actions": actions.rows, "task": task}, open(path, "w"))
'''
STUB_TOOL = '''"""`rcb_myosuite.py replay` as the grader calls it; RCB_FAKE_REPLAY says how the replay process ends."""
import json, os, signal, sys, time
a = dict(zip(sys.argv[2::2], sys.argv[3::2]))
mode = os.environ.get("RCB_FAKE_REPLAY", "ok")
if mode == "killed":
    os.kill(os.getpid(), signal.SIGKILL)              # what an out-of-memory kill of the replay looks like
if mode == "crash":
    raise RuntimeError("the replay tool failed")
if mode == "hang":
    time.sleep(60)
if mode == "garbage":
    open(a["--out"], "w").write("[1, 2")
    sys.exit(0)
rows = json.load(open(a["--traj"]))["actions"]
json.dump({"n_actions": len(rows), "success": rows[-1][0] > 0.5, "state_sha": "abc", "steps": len(rows), "reason": None,
           "instance_ok": mode != "mismatch", "deterministic": True, "video": False}, open(a["--out"], "w"))
'''


class PrivilegedReplay(unittest.TestCase):
    """Whose failure a 0 is: a file that is no trajectory for the instance is the agent's, checked before any replay;
    after that, a replay process that gives no result is the grader's (grader_error and infra_error), never the
    agent's bad_trajectory (as it was booked until 2026-10-10)."""
    NU = 39

    def grade(self, traj, mode="ok", timeout_s=None) -> tuple[str, dict]:
        with tempfile.TemporaryDirectory() as d:
            log = Path(d, "log")
            src = PRIVILEGED.read_text()
            if timeout_s is not None:
                self.assertIn("REPLAY_TIMEOUT_S = 1200", src)
                src = src.replace("REPLAY_TIMEOUT_S = 1200", f"REPLAY_TIMEOUT_S = {timeout_s}")
            Path(d, "grade.py").write_text(src)
            Path(d, "numpy.py").write_text(STUB_NUMPY)
            Path(d, "rcb_myosuite.py").write_text(STUB_TOOL)
            Path(d, "instance.npz").write_text(json.dumps({"task": "obj_hold",
                                                           "model__actuator_ctrlrange": [[0, 1]] * self.NU}))
            Path(d, "trajectory.npz").write_text(traj if isinstance(traj, str) else json.dumps(traj))
            r = subprocess.run([sys.executable, "-B", str(Path(d, "grade.py")), "--instance", str(Path(d, "instance.npz")),
                                "--traj", str(Path(d, "trajectory.npz")), "--no-video"], capture_output=True, text=True,
                               env={**os.environ, "RCB_VERIFIER_LOG_DIR": str(log), "RCB_FAKE_REPLAY": mode,
                                    "PYTHONDONTWRITEBYTECODE": "1"})
            self.assertEqual(r.returncode, 0, r.stderr[-600:])
            reward = json.loads((log / "reward.json").read_text())
            self.assertTrue(all(isinstance(v, (int, float)) for v in reward.values()), reward)
            for key in ("success", "deterministic", "grader_error", "infra_error"):              # in every branch
                self.assertIn(key, reward)
            return (log / "reward.txt").read_text().strip(), reward

    def rows(self, n=5, width=None, win=True) -> dict:
        return {"task": "obj_hold", "actions": [[0.0] * (width or self.NU) for _ in range(n - 1)]
                + [[1.0 if win else 0.0] + [0.0] * ((width or self.NU) - 1)]}

    def test_a_replayed_trajectory_is_graded_by_its_replays(self):
        txt, r = self.grade(self.rows())
        self.assertEqual((txt, r["success"], r["deterministic"], r["grader_error"], r["infra_error"]), ("1", 1, 1, 0, 0))
        txt, r = self.grade(self.rows(win=False))
        self.assertEqual((txt, r["success"], r["grader_error"], r["infra_error"]), ("0", 0, 0, 0))

    def test_a_file_that_is_no_trajectory_is_the_agents(self):
        for what, traj in (("width", self.rows(width=self.NU - 1)), ("NaN", {"task": "obj_hold", "actions": [[float("nan")] * self.NU]}),
                           ("no rows", {"task": "obj_hold", "actions": []}), ("not a file numpy reads", "x")):
            txt, r = self.grade(traj, mode="crash")          # no replay is started for it: the tool's fate does not matter
            self.assertEqual((txt, r.get("bad_trajectory"), r["grader_error"], r["infra_error"]), ("0", 1, 0, 0), what)
        txt, r = self.grade({**self.rows(), "task": "key_turn"})
        self.assertEqual((txt, r.get("wrong_family"), r["grader_error"], r["infra_error"]), ("0", 1, 0, 0))

    def test_a_replay_that_gave_no_result_is_the_graders(self):
        for mode in ("killed", "crash", "garbage"):
            txt, r = self.grade(self.rows(), mode=mode)
            self.assertEqual((txt, r["success"], r.get("replay_failed"), r["grader_error"], r["infra_error"],
                              r.get("bad_trajectory", 0)), ("0", 0, 1, 1, 1, 0), mode)
        txt, r = self.grade(self.rows(), mode="hang", timeout_s=1)
        self.assertEqual((txt, r.get("replay_failed"), r["grader_error"], r["infra_error"]), ("0", 1, 1, 1))

    def test_an_instance_the_host_does_not_rebuild_is_the_graders(self):
        txt, r = self.grade(self.rows(), mode="mismatch")
        self.assertEqual((txt, r["success"], r["instance_ok"], r["grader_error"], r["infra_error"]), ("0", 0, 0, 1, 1))


if __name__ == "__main__":
    unittest.main()
