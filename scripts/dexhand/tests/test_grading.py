"""DexHand's two graders on stub replays: the verdict rules of the privileged `tests/grade.py` and of the standard
`tests/grade.py`, without a simulator (standard library only; ci_checks/check-unit-tests.sh, first tier).

Privileged: the shared grader runs the task's `replay.py` twice and gives reward 1 only when both fresh replays
succeed with the same final state hash; an invalid archive is a clean 0 (`bad_trajectory`), a crashed replay an
infrastructure error. Standard (board 0151): the collect hook (`finalize.py`) writes the live episode's verdict and runs
no grading replay, only one video process; the grader reads only the sidecar's `final.json` and fails closed.

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
if "--video" in args:                       # the third replay, after the verdict (board 0136)
    video = os.environ.get("STUB_VIDEO", "ok")
    if video == "EXIT":
        sys.exit(3)
    if video == "ok":
        Path(args[args.index("--video") + 1]).write_bytes(b"mp4")
    out.write_text('{"video": %s}' % ("true" if video == "ok" else "false"))
    sys.exit(0)
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

    def video(self):
        return json.loads((self.logs / "video.json").read_text()), (self.logs / "replay.mp4").is_file()

    def test_video_is_rendered_after_the_verdict(self):
        self.traj.write_bytes(b"stub")
        result, reward = self.grade(_1=self.ok(), _2=self.ok())
        self.assertEqual((reward, self.video()), ("1", ({"video": True}, True)))
        self.assertEqual((self.tmp / "counter").read_text().split()[-1], "video.json")   # the third, last replay

    def test_failed_video_changes_no_verdict(self):
        self.traj.write_bytes(b"stub")
        before, _ = self.grade(_1=self.ok(), _2=self.ok())
        os.environ["STUB_VIDEO"] = "EXIT"
        try:
            result, reward = self.grade(_1=self.ok(), _2=self.ok())
        finally:
            del os.environ["STUB_VIDEO"]
        record, exists = self.video()
        self.assertEqual((reward, result, record["video"], exists), ("1", before, False, False))

    def test_no_video_without_a_replayable_archive(self):
        result, _ = self.grade(_1=self.ok(), _2=self.ok())          # missing trajectory
        self.assertFalse((self.logs / "video.json").exists())
        self.traj.write_bytes(b"stub")
        bad = {"success": False, "bad_trajectory": 1, "state_sha": "", "n_actions": 0}
        self.grade(_1=bad, _2=bad)
        self.assertFalse((self.logs / "video.json").exists())

    def test_wuji_is_reported_numerically(self):
        self.traj.write_bytes(b"stub")
        result, _ = self.grade(_1=self.ok(hand="wuji"), _2=self.ok(hand="wuji"))
        self.assertEqual(result["hand_wuji"], 1)
        self.assertTrue(all(isinstance(v, (int, float)) for v in result.values()))   # Harbor rejects strings
        self.assertEqual(json.loads((self.logs / "details.json").read_text())["hand"], "wuji")


class Standard(unittest.TestCase):
    """The standard grader: the live episode's verdict in the sidecar's final.json (no replay, board 0151)."""

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
        return {"finalized": True, "graded_by": "live", "replays": 0, "success": True, "live_success": True,
                "live_sha": "a" * 64, "n_actions": 450, "control_steps": 450, "calls": 3, "hand": "sharpa",
                "video": True, "video_pending": False, **extra}

    def test_live_success_scores_one(self):
        result, reward = self.grade(self.good())
        self.assertEqual((reward, result["success"], result["live_success"], result["infra_error"],
                          result["graded_by_live"], result["replays"]), ("1", 1, 1, 0, 1, 0))
        for key in ("replay_success", "deterministic", "live_matches_replay"):
            self.assertNotIn(key, result)

    def test_live_failure_scores_zero_not_infra(self):
        for extra in ({"success": False, "reason": "task_failure"}, {"success": False, "reason": "timeout"},
                      {"success": "true"}):
            with self.subTest(extra=extra):
                result, reward = self.grade(self.good(**extra))
                self.assertEqual((reward, result["infra_error"]), ("0", 0))

    def test_a_sim_error_from_the_agents_actions_is_its_zero(self):
        for success in (False, True):   # even a record that says success: a sim error is never one
            result, reward = self.grade(self.good(success=success, reason="error"))
            self.assertEqual((reward, result["sim_error"], result["infra_error"]), ("0", 1, 0))

    def test_give_up_after_crashes_between_calls_is_infra(self):
        for reason in ("sim_crashed", "resume_failed: replayed state differs from the logged one"):
            with self.subTest(reason=reason):
                result, reward = self.grade({"finalized": True, "gave_up": True, "success": False, "reason": reason,
                                             "infra_error": 1, "graded_by": "live", "replays": 0})
                self.assertEqual((reward, result["infra_error"], result["gave_up"]), ("0", 1, 1))

    def test_crashes_inside_the_agents_calls_are_its_zero(self):
        result, reward = self.grade({"finalized": True, "gave_up": True, "success": False,
                                     "reason": "sim_crashed_on_call", "graded_by": "live", "replays": 0})
        self.assertEqual((reward, result["infra_error"], result["no_verdict"]), ("0", 0, 0))

    def test_instance_mismatch_at_the_start_is_infra(self):
        result, reward = self.grade({"finalized": True, "gave_up": True, "success": False, "reason": "instance_mismatch",
                                     "instance_mismatch": 1, "infra_error": 1})
        self.assertEqual((reward, result["infra_error"], result["instance_mismatch"]), ("0", 1, 1))
        result, reward = self.grade(self.good(instance_mismatch=1))   # never a 1 on a scene that did not build
        self.assertEqual((reward, result["infra_error"]), ("0", 1))

    def test_a_failed_video_changes_no_verdict(self):
        with_video, _ = self.grade(self.good())
        without, reward = self.grade(self.good(video=False))
        self.assertEqual((reward, without["video_rendered"], with_video["video_rendered"]), ("1", 0, 1))
        self.assertEqual({k: v for k, v in without.items() if k != "video_rendered"},
                         {k: v for k, v in with_video.items() if k != "video_rendered"})

    def test_no_verdict_fails_closed(self):
        old_schema = {k: v for k, v in self.good().items() if k != "graded_by"}   # a pre-live-grading final.json
        for final in ({**self.good(), "finalized": False}, old_schema, {**self.good(), "infra_error": 1}):
            with self.subTest(final=final):
                result, reward = self.grade(final)
                self.assertEqual((reward, result["infra_error"]), ("0", 1))

    def test_missing_or_malformed_final_json_fails_closed(self):
        result, reward = self.grade()
        self.assertEqual((reward, result["infra_error"], result["missing_log"]), ("0", 1, 1))
        for payload in ("[]", "null", "not JSON"):
            with self.subTest(payload=payload):
                result, reward = self.grade(payload)
                self.assertEqual((reward, result["infra_error"], result["grader_error"]), ("0", 1, 1))

    def test_hand_is_reported_numerically(self):
        result, _ = self.grade(self.good(hand="wuji"))
        self.assertEqual(result["hand_wuji"], 1)
        self.assertTrue(all(isinstance(v, (int, float)) for v in result.values()))
        (self.data / "final.json").unlink()
        result, _ = self.grade()
        self.assertTrue(all(isinstance(v, (int, float)) for v in result.values()))


# A replay.py stand-in for the collect hook: it may only be called to film (--video); a grading replay fails the test.
STUB_VIDEO = r"""
import os, sys
from pathlib import Path
args = sys.argv[1:]
with open(os.environ["STUB_COUNTER"], "a") as f:
    f.write(" ".join(args) + "\n")
if "--video" not in args:
    sys.exit("a grading replay was started")
mode = os.environ.get("STUB_VIDEO", "ok")
if mode == "EXIT":
    sys.exit(3)
if mode == "SLOW":
    import time; time.sleep(30)
Path(args[args.index("--video") + 1]).write_bytes(b"mp4")
Path(args[args.index("--out") + 1]).write_text('{"video": true, "success": false}')   # its replay's success: ignored
"""


class CollectHook(unittest.TestCase):
    """finalize.py: the verdict from the service's record of the live episode, then one video-only process."""

    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.sim = self.tmp / "srv"
        self.sim.mkdir()
        shutil.copyfile(SHARED / "standard/finalize.py", self.sim / "finalize.py")
        (self.sim / "replay.py").write_text(STUB_VIDEO)
        (self.sim / "grading.json").write_text(json.dumps({"video_timeout_s": 60, "collect_timeout_s": 600}))
        self.data = self.tmp / "data"
        self.data.mkdir()
        self.counter = self.tmp / "counter"

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def run_hook(self, end_rc=0, episode=None, video="ok", grading=None):
        if episode is not None:
            (self.data / "episode.json").write_text(json.dumps(episode))
            (self.data / "trajectory.npz").write_bytes(b"stub")
        if grading is not None:
            (self.sim / "grading.json").write_text(json.dumps(grading))
        env = {**os.environ, "RCB_DATA": str(self.data), "RCB_END_RC": str(end_rc), "RCB_TASK": "coffee_stir",
               "STUB_COUNTER": str(self.counter), "STUB_VIDEO": video}
        env.pop("RCB_REPLAY_SCRIPT", None)
        subprocess.run([sys.executable, str(self.sim / "finalize.py")], env=env, check=True, timeout=120)
        return json.loads((self.data / "final.json").read_text())

    def calls(self):
        return self.counter.read_text().splitlines() if self.counter.exists() else []

    def episode(self, **extra):
        return {"success": True, "live_sha": "a" * 64, "hand": "sharpa", "n_actions": 450, "reason": "success",
                "start_sha": "b" * 64, **extra}

    def test_live_success_is_the_verdict_and_only_the_video_replays(self):
        final = self.run_hook(episode=self.episode())
        self.assertEqual((final["success"], final["live_success"], final["graded_by"], final["replays"],
                          final["finalized"], final["video"], final["video_pending"], final["video_source"]),
                         (True, True, "live", 0, True, True, False, "render"))
        for key in ("replay_success", "deterministic", "live_matches_replay"):
            self.assertNotIn(key, final)
        self.assertEqual(len(self.calls()), 1)
        self.assertIn("--video", self.calls()[0])
        self.assertFalse((self.data / "replay1.json").exists())

    def test_live_failure_is_a_zero_whatever_the_video_replay_says(self):
        final = self.run_hook(episode=self.episode(success=False, reason="object_dropped"))
        self.assertEqual((final["success"], final.get("infra_error", 0), final["video"]), (False, 0, True))

    def test_a_failed_or_late_video_changes_nothing_else(self):
        good = self.run_hook(episode=self.episode())
        for mode, grading in (("EXIT", None), ("SLOW", {"video_timeout_s": 2, "collect_timeout_s": 600})):
            with self.subTest(video=mode):
                (self.data / "replay.mp4").unlink(missing_ok=True)
                final = self.run_hook(episode=self.episode(), video=mode, grading=grading)
                self.assertEqual((final["video"], final["video_pending"], (self.data / "replay.mp4").exists()),
                                 (False, False, False))
                self.assertEqual({k: v for k, v in final.items() if k != "video"},
                                 {k: v for k, v in good.items() if k != "video"})
                self.assertFalse(json.loads((self.data / "video.json").read_text())["video"])

    def test_no_dumped_episode_is_infra(self):
        for rc, episode in ((1, self.episode()), (0, {"success": True})):   # timed out; a record without live_sha
            with self.subTest(rc=rc):
                final = self.run_hook(end_rc=rc, episode=episode)
                self.assertEqual((final["success"], final["infra_error"], final["finalized"]), (False, 1, True))
        self.assertEqual(self.calls(), [])

    def test_a_give_up_verdict_is_kept_and_nothing_replays(self):
        for reason, infra in (("sim_crashed", 1), ("sim_crashed_on_call", 0)):
            with self.subTest(reason=reason):
                gave = {"finalized": True, "gave_up": True, "success": False, "reason": reason,
                        **({"infra_error": 1} if infra else {})}
                (self.data / "final.json").write_text(json.dumps(gave))
                final = self.run_hook(end_rc=2)
                if infra:      # an infrastructure give-up is kept byte for byte: nothing marks it as a live verdict
                    self.assertEqual(final, gave)
                else:
                    self.assertEqual((final["reason"], final.get("infra_error", 0), final["graded_by"], final["video"]),
                                     (reason, infra, "live", False))
        self.assertEqual(self.calls(), [])

    def test_hook_and_grader_together(self):
        self.run_hook(episode=self.episode())
        shutil.copyfile(SHARED / "standard/grade.py", self.tmp / "grade.py")
        logs = self.tmp / "logs"
        env = {**os.environ, "RCB_DATA": str(self.data), "RCB_VERIFIER_LOG_DIR": str(logs)}
        subprocess.run([sys.executable, str(self.tmp / "grade.py")], env=env, check=True, timeout=60)
        result = json.loads((logs / "reward.json").read_text())
        self.assertEqual((result["success"], result["infra_error"], result["video_rendered"]), (1, 0, 1))


class GeneratedTasks(unittest.TestCase):
    """Every standard task records its frozen instance's file hashes for the service's start check, and declares no
    grading replay (its collect hook's limits have no replay_timeout_s)."""

    def test_instance_hashes_match_the_files(self):
        import hashlib
        tasks = sorted((SHARED.parents[2] / "tasks").glob("dexhand-*-standard"))
        self.assertTrue(tasks)
        for task in tasks:
            with self.subTest(task=task.name):
                sim = task / "environment/sim"
                grading = json.loads((sim / "grading.json").read_text())
                shas = grading["instance_sha256"]
                self.assertIn("instance.json", shas)
                self.assertNotIn("replay_timeout_s", grading)
                for name, sha in shas.items():
                    self.assertEqual(hashlib.sha256((sim / name).read_bytes()).hexdigest(), sha)


if __name__ == "__main__":
    unittest.main()
