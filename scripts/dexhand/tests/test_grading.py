"""DexHand's two graders on stub replays: the verdict rules of the privileged `tests/grade.py` and of the standard
`tests/grade.py`, without a simulator (standard library only; ci_checks/check-unit-tests.sh, first tier).

Privileged: the shared grader runs the task's `replay.py` twice and gives reward 1 only when both fresh replays
succeed with the same final state hash; an invalid archive is a clean 0 (`bad_trajectory`), a crashed replay an
infrastructure error. Standard: the grader reads only the sidecar's `final.json` and fails closed.

    python3 scripts/dexhand/tests/test_grading.py
"""
from __future__ import annotations

import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest

SHARED = Path(__file__).resolve().parents[1] / "shared"

# A replay.py stand-in: writes the verdict the test put in STUB_VERDICT_<n>, n = 1 or 2 from the grader's output name
# (replay1.json / replay2.json: the two replays run at the same time), and notes that it ran
STUB_REPLAY = r'''
import os, sys
from pathlib import Path
args = sys.argv[1:]
out = Path(args[args.index("--out") + 1])
with open(os.environ["STUB_COUNTER"], "a") as f:
    f.write(out.name + "\n")
n = 1 if out.name == "replay1.json" else 2
spec = os.environ.get(f"STUB_VERDICT_{n}", "{}")
if spec == "EXIT":
    sys.exit(3)
out.write_text(spec)
'''


class Privileged(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.tests = self.tmp / "tests"
        self.tests.mkdir()
        shutil.copyfile(SHARED / "grade.py", self.tests / "grade.py")
        (self.tests / "replay.py").write_text(STUB_REPLAY)
        (self.tests / "grading.json").write_text(json.dumps({"replay_timeout_s": 60, "video_timeout_s": 60}))
        (self.tests / "instance.json").write_text(json.dumps({"id": "essential_cube_layer"}))
        self.logs = self.tmp / "logs"
        self.traj = self.tmp / "output" / "trajectory.npz"
        self.traj.parent.mkdir()

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def grade(self, **verdicts):
        env = {**os.environ, "RCB_VERIFIER_LOG_DIR": str(self.logs), "RCB_TRAJECTORY": str(self.traj),
               "STUB_COUNTER": str(self.tmp / "counter")}
        env.pop("RCB_TASK", None)
        for key, value in verdicts.items():
            env[f"STUB_VERDICT{key}"] = value if isinstance(value, str) else json.dumps(value)
        subprocess.run([sys.executable, str(self.tests / "grade.py")], env=env, check=True, timeout=120)
        return (json.loads((self.logs / "reward.json").read_text()), (self.logs / "reward.txt").read_text().strip())

    def ok(self, sha="a" * 64, **extra):
        return {"success": True, "state_sha": sha, "steps": 450, "stage": 3, "hand": "sharpa", "n_actions": 450,
                "reason": "success", "bad_trajectory": 0, **extra}

    def test_missing_trajectory_is_zero_not_infra(self):
        result, reward = self.grade(_1=self.ok(), _2=self.ok())
        self.assertEqual((reward, result["missing_trajectory"], result["infra_error"]), ("0", 1, 0))

    def test_symlinked_trajectory_counts_as_missing(self):
        target = self.tmp / "elsewhere.npz"
        target.write_bytes(b"x")
        self.traj.symlink_to(target)
        result, reward = self.grade(_1=self.ok(), _2=self.ok())
        self.assertEqual((reward, result["missing_trajectory"]), ("0", 1))

    def test_two_identical_successes_score_one(self):
        self.traj.write_bytes(b"stub")
        result, reward = self.grade(_1=self.ok(), _2=self.ok())
        self.assertEqual((reward, result["success"], result["deterministic"], result["infra_error"]), ("1", 1, 1, 0))
        self.assertEqual((result["n_actions"], result["sim_steps"], result["stages_completed"]), (450, 450, 3))

    def test_differing_final_hashes_score_zero(self):
        self.traj.write_bytes(b"stub")
        result, reward = self.grade(_1=self.ok("a" * 64), _2=self.ok("b" * 64))
        self.assertEqual((reward, result["deterministic"]), ("0", 0))

    def test_one_failed_replay_scores_zero(self):
        self.traj.write_bytes(b"stub")
        result, reward = self.grade(_1=self.ok(), _2=self.ok(success=False, reason="object_dropped"))
        self.assertEqual((reward, result["success"], result["infra_error"]), ("0", 0, 0))

    def test_success_must_be_a_real_boolean(self):
        self.traj.write_bytes(b"stub")
        result, reward = self.grade(_1=self.ok(success="true"), _2=self.ok(success=1))
        self.assertEqual(reward, "0")

    def test_bad_trajectory_is_a_clean_zero(self):
        self.traj.write_bytes(b"stub")
        bad = {"success": False, "bad_trajectory": 1, "error": "width 27 does not match hand sharpa (28)",
               "hand": "sharpa", "state_sha": "", "steps": 0, "stage": 0, "n_actions": 0, "reason": ""}
        result, reward = self.grade(_1=bad, _2=bad)
        self.assertEqual((reward, result["bad_trajectory"], result["infra_error"], result["deterministic"]),
                         ("0", 1, 0, 0))

    def test_bad_flag_overrides_claimed_success(self):
        self.traj.write_bytes(b"stub")
        result, reward = self.grade(_1=self.ok(bad_trajectory=1), _2=self.ok(bad_trajectory=1))
        self.assertEqual((reward, result["bad_trajectory"]), ("0", 1))

    def test_crashed_replay_is_an_infrastructure_error(self):
        self.traj.write_bytes(b"stub")
        result, reward = self.grade(_1="EXIT", _2="EXIT")
        self.assertEqual((reward, result["infra_error"]), ("0", 1))

    def test_unreadable_verdict_is_an_infrastructure_error(self):
        self.traj.write_bytes(b"stub")
        result, reward = self.grade(_1="[1, 2]", _2="not json")
        self.assertEqual((reward, result["infra_error"]), ("0", 1))

    def test_oversized_archive_is_rejected_unread(self):
        with open(self.traj, "wb") as f:
            f.truncate(64_000_001)
        result, reward = self.grade(_1=self.ok(), _2=self.ok())
        self.assertEqual((reward, result["bad_trajectory"], result["infra_error"]), ("0", 1, 0))
        self.assertFalse((self.tmp / "counter").exists())   # never replayed

    def test_wuji_is_reported_numerically(self):
        self.traj.write_bytes(b"stub")
        result, _ = self.grade(_1=self.ok(hand="wuji"), _2=self.ok(hand="wuji"))
        self.assertEqual(result["hand_wuji"], 1)
        self.assertTrue(all(isinstance(v, (int, float)) for v in result.values()))   # Harbor rejects strings
        self.assertEqual(json.loads((self.logs / "details.json").read_text())["hand"], "wuji")


class Standard(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        shutil.copyfile(SHARED / "standard/grade.py", self.tmp / "grade.py")
        self.data = self.tmp / "data"
        self.data.mkdir()
        self.logs = self.tmp / "logs"

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def grade(self, final=None):
        if final is not None:
            (self.data / "final.json").write_text(final if isinstance(final, str) else json.dumps(final))
        env = {**os.environ, "RCB_DATA": str(self.data), "RCB_VERIFIER_LOG_DIR": str(self.logs)}
        subprocess.run([sys.executable, str(self.tmp / "grade.py")], env=env, check=True, timeout=60)
        return json.loads((self.logs / "reward.json").read_text()), (self.logs / "reward.txt").read_text().strip()

    def good(self, **extra):
        return {"finalized": True, "success": True, "replay_success": True, "deterministic": True,
                "live_matches_replay": True, "infra_error": 0, "n_actions": 450, "control_steps": 450, "calls": 3,
                "hand": "sharpa", **extra}

    def test_every_trusted_check_must_hold(self):
        result, reward = self.grade(self.good())
        self.assertEqual((reward, result["success"], result["infra_error"]), ("1", 1, 0))
        for key in ("success", "replay_success", "deterministic", "live_matches_replay"):
            with self.subTest(missing=key):
                result, reward = self.grade(self.good(**{key: False}))
                self.assertEqual(reward, "0")

    def test_no_verdict_fails_closed(self):
        for final in ({**self.good(), "finalized": False}, {**self.good(), "deterministic": None},
                      {**self.good(), "infra_error": 1}):
            with self.subTest(final=final):
                result, reward = self.grade(final)
                self.assertEqual((reward, result["infra_error"]), ("0", 1))

    def test_missing_or_malformed_final_json_fails_closed(self):
        result, reward = self.grade()
        self.assertEqual((reward, result["infra_error"], result["missing_log"]), ("0", 1, 1))
        for payload in ("[]", "null", "not JSON"):
            with self.subTest(payload=payload):
                result, reward = self.grade(payload)
                self.assertEqual((reward, result["infra_error"]), ("0", 1))

    def test_hand_is_reported_numerically(self):
        result, _ = self.grade(self.good(hand="wuji"))
        self.assertEqual(result["hand_wuji"], 1)
        self.assertTrue(all(isinstance(v, (int, float)) for v in result.values()))


if __name__ == "__main__":
    unittest.main()
