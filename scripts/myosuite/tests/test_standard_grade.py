"""Tests for the standard-mode verifier (shared/standard/grade.py) on synthetic final.json files: standard library only.

    python3 -m unittest discover -s scripts/myosuite/tests

What is graded is the sim sidecar's final.json. An infrastructure failure -- no final.json, one that cannot be read, one
the collect hook never finalized, a replay process that died -- is infra_error = 1, never the agent's 0 (PROTOCOL §2.6).
"""
import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

GRADE = Path(__file__).resolve().parents[1] / "shared" / "standard" / "grade.py"
GOOD = {"finalized": True, "success": True, "replay_success": True, "deterministic": True, "live_matches_replay": True,
        "reason": "success", "video": True, "control_steps": 72, "n_actions": 72}


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
            for key in ("success", "deterministic", "infra_error", "grader_error"):              # in every branch
                self.assertIn(key, reward)
            return (log / "reward.txt").read_text().strip(), reward

    def test_a_finalized_success_passes(self):
        txt, r = self.grade(GOOD)
        self.assertEqual((txt, r["success"], r["infra_error"], r["finalized"], r["video_rendered"]), ("1", 1, 0, 1, 1))

    def test_success_needs_live_replay_and_determinism(self):
        for key in ("success", "replay_success", "deterministic"):
            txt, r = self.grade({**GOOD, key: False})
            self.assertEqual((txt, r["success"], r["infra_error"]), ("0", 0, 0), key)
        txt, r = self.grade({**GOOD, "instance_mismatch": 1, "infra_error": 1})
        self.assertEqual((txt, r["success"], r["infra_error"], r["grader_error"]), ("0", 0, 1, 1))

    def test_a_missing_final_json_is_infrastructure(self):
        txt, r = self.grade(None)
        self.assertEqual((txt, r["success"], r["missing_log"], r["infra_error"], r["grader_error"]), ("0", 0, 1, 1, 0))

    def test_an_unreadable_final_json_is_infrastructure(self):
        for text in ('{"finalized": true, "succ', "[1, 2]", "null", ""):
            txt, r = self.grade(text)
            self.assertEqual((txt, r["success"], r["infra_error"], r["grader_error"]), ("0", 0, 1, 1), text)

    def test_a_never_finalized_final_json_is_infrastructure(self):
        """The service's live summary only: the collect hook ran out of time, or died, before its replays' verdict."""
        txt, r = self.grade({"finalized": False, "success": True, "reason": "success", "control_steps": 72})
        self.assertEqual((txt, r["success"], r["live_success"], r["finalized"], r["infra_error"]), ("0", 0, 1, 0, 1))

    def test_an_infrastructure_flag_never_passes(self):
        txt, r = self.grade({**GOOD, "infra_error": 1})
        self.assertEqual((txt, r["success"], r["infra_error"]), ("0", 0, 1))
        txt, r = self.grade({**GOOD, "replay_success": False, "deterministic": False, "replay_failed": 1, "infra_error": 1})
        self.assertEqual((r["success"], r["infra_error"], r["grader_error"]), (0, 1, 1))

    def test_the_agents_failures_stay_the_agents(self):
        txt, r = self.grade({"finalized": True, "success": False, "replay_success": False, "deterministic": True,
                             "reason": "timeout"})
        self.assertEqual((txt, r["success"], r["infra_error"], r["timeout"], r["deterministic"]), ("0", 0, 0, 1, 1))
        txt, r = self.grade({"finalized": True, "success": False, "replay_success": False, "deterministic": True,
                             "reason": "error"})
        self.assertEqual((r["success"], r["infra_error"], r["sim_error"]), (0, 0, 1))


if __name__ == "__main__":
    unittest.main()
