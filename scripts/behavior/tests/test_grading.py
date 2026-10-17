"""Whose failure a 0 is, in BEHAVIOR's two graders and the standard collect hook (board 0067): the real
tests/grade.py of both template twins and the real environment/sim/finalize.sh, on synthetic records; no simulator.

    python3 -m unittest discover -s scripts/behavior/tests          # needs numpy

- standard tests/grade.py (2026-10-17, board 0151: graded by the live episode): success = the live success, settled
  successes included; a missing, unreadable or unfinalized final.json, a give-up between calls and instance_mismatch
  are infra_error = 1 (no verdict on the agent), never a plain 0; replay fields of old records are not read; a reward is
  written in every case;
- environment/sim/finalize.sh (run whole, with a stand-in `python` for the end command and the replay CLI): final.json
  from episode.json, no replay; a video-only render only when the live video is missing, which never changes the
  verdict; the atomic final.json;
- privileged tests/grade.py (with a stand-in tooling module): an unreadable trajectory is bad_trajectory, a replay that
  dies is grader_error, instance_ok 0 is infra_error;
- (2026-10-14) the privileged grader: the graded replays run alike, without the video; the video is a third replay whose
  state never decides `deterministic`; a replay that ends on a simulator breakdown is a failure with sim_breakdown.
"""
from __future__ import annotations

import json
import os
import shutil
import stat
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[3]
STD = ROOT / "tasks" / "behavior-picking-up-trash-i00-standard"
PRIV = ROOT / "tasks" / "behavior-picking-up-trash-i00-privileged"
EPISODE = {"success": True, "steps": 3, "calls": 2, "control_steps": 90, "physics_steps": 360, "elapsed_s": 12.0, "reason": "success",
           "task": "picking_up_trash", "n_actions": 90, "live_sha": "aaaa", "sim_startups": 1, "resumes": 0, "graded_by": "live",
           "replays": 0, "settle_steps": 0, "settled_success": False, "q_score": 1.0}
GOOD = {**EPISODE, "finalized": True, "live_success": True, "video": True, "video_source": "live", "video_pending": False}


# ------------------------------------------------------------------------------------------------ standard grade.py
def grade_standard(final) -> tuple[str | None, dict | None]:
    """Run the standard grader on a final.json (dict, raw text, or None = no file): (reward.txt, reward.json)."""
    with tempfile.TemporaryDirectory(prefix="rcb_behavior_grade_") as tmp:
        out, log = Path(tmp) / "out", Path(tmp) / "log"
        out.mkdir(); log.mkdir()
        if final is not None:
            (out / "final.json").write_text(final if isinstance(final, str) else json.dumps(final))
        env = {**os.environ, "RCB_DATA": str(out), "RCB_VERIFIER_LOG_DIR": str(log)}
        subprocess.run([sys.executable, str(STD / "tests" / "grade.py")], capture_output=True, text=True, timeout=60, env=env)
        txt = (log / "reward.txt").read_text().strip() if (log / "reward.txt").exists() else None
        js = json.loads((log / "reward.json").read_text()) if (log / "reward.json").exists() else None
        return txt, js


class StandardGrader(unittest.TestCase):
    def check(self, final, reward: str, **want):
        txt, js = grade_standard(final)
        self.assertEqual(txt, reward, js)
        self.assertIsNotNone(js)
        for k, v in want.items():
            self.assertEqual(js.get(k), v, (k, js))
        self.assertTrue(all(isinstance(v, (int, float)) and not isinstance(v, bool) for v in js.values()), js)   # numeric only
        self.assertIn("infra_error", js); self.assertIn("grader_error", js)
        self.assertEqual((js["graded_by_live"], js["replays"]), (1, 0), js)
        self.assertNotIn("replay_success", js); self.assertNotIn("deterministic", js)
        return js

    def test_live_success_passes(self):
        self.check(GOOD, "1", success=1, live_success=1, infra_error=0, grader_error=0, finalized=1, missing_log=0, video_live=1)

    def test_a_settled_success_is_the_live_episodes(self):
        self.check({**GOOD, "settled_success": True, "settle_steps": 37}, "1", success=1, settled_success=1, settle_steps=37)

    def test_agent_failures_stay_the_agents(self):
        self.check({**GOOD, "success": False, "live_success": False, "reason": "timeout", "settle_steps": 150}, "0", success=0, infra_error=0, grader_error=0)
        self.check({**GOOD, "success": False, "live_success": False, "reason": "failure: the robot fell over"}, "0", infra_error=0, task_failure=1)
        self.check({**GOOD, "success": False, "live_success": False, "reason": "error"}, "0", infra_error=0, sim_error=1)
        g = self.check({**GOOD, "success": False, "live_success": False, "reason": "failure: simulator breakdown (robot state not finite)",
                        "sim_breakdown": True}, "0", infra_error=0, sim_breakdown=1, task_failure=1)
        # every crash happened inside a call: the layer's give-up without the infra flag
        self.check({"success": False, "done": True, "reason": "sim_crashed_on_call", "finalized": True, "gave_up": True}, "0",
                   infra_error=0, gave_up=1, finalized=1, sim_crashed_on_call=1)

    def test_replay_fields_of_old_records_decide_nothing(self):
        self.check({**GOOD, "success": False, "live_success": False, "replay_success": True, "deterministic": True}, "0", success=0)
        self.check({**GOOD, "replay_success": False, "deterministic": False}, "1", success=1)

    def test_a_missing_video_keeps_the_verdict(self):
        self.check({**GOOD, "video": False, "video_source": None, "video_pending": True}, "1", success=1, video_rendered=0, video_pending=1)

    def test_missing_final_json_is_infrastructure(self):
        self.check(None, "0", success=0, missing_log=1, infra_error=1, grader_error=0)

    def test_unreadable_final_json_still_writes_a_reward(self):
        for raw in ('{"success": true, "finali', "", "[1, 2]", "null", "\x00\x00"):
            self.check(raw, "0", success=0, infra_error=1, grader_error=1, missing_log=0)

    def test_unfinalized_is_infrastructure_even_when_live_succeeded(self):
        # the service's own copy: the collect hook was killed or never completed
        self.check({**EPISODE, "finalized": False, "done": True}, "0", success=0, live_success=1, finalized=0, infra_error=1)
        self.check({k: v for k, v in GOOD.items() if k != "finalized"}, "0", success=0, infra_error=1)

    def test_a_post_exception_state_is_never_a_success(self):
        self.check({**GOOD, "success": True, "live_success": True, "reason": "error"}, "0", success=0, infra_error=0, sim_error=1)

    def test_live_graded_trials_are_no_regrade_candidates(self):
        sys.path.insert(0, str(ROOT / "scripts" / "behavior"))
        import regrade
        self.assertFalse(regrade.candidate("standard", {"graded_by_live": 1, "finalized": 1, "success": 0, "live_success": 0}))
        self.assertTrue(regrade.candidate("standard", {"finalized": 1, "success": 0, "deterministic": 0}))   # an old record

    def test_layer_infra_verdicts(self):
        self.check({"success": False, "done": True, "reason": "sim_crashed", "finalized": True, "gave_up": True, "infra_error": 1}, "0",
                   infra_error=1, gave_up=1)
        self.check({"success": False, "done": True, "reason": "resume_failed: journal shorter than the log", "finalized": True,
                    "gave_up": True, "infra_error": 1}, "0", infra_error=1)
        self.check({"success": False, "done": True, "reason": "instance_mismatch: the frozen start state did not rebuild here",
                    "finalized": True, "gave_up": True, "infra_error": 1}, "0", infra_error=1, instance_ok=0)
        self.check({**GOOD, "infra_error": 1}, "0", success=0, infra_error=1)      # an infra flag never passes
        self.check({**GOOD, "gave_up": True}, "0", success=0)                       # a give-up never passes


# ------------------------------------------------------------------------------------------------ finalize.sh
FAKE_PYTHON = r"""#!/bin/sh
# stand-in for `python` in finalize.sh: the end command, the replay CLI ($RCB_TOOL), and the real interpreter for heredocs
case "$1" in
  /srv/rcb_limited.py) exit "${FAKE_END_RC:-0}" ;;
  "$RCB_TOOL")
    echo "$*" >> "$RCB_DATA/.args"
    case "${FAKE_RENDER:-ok}" in
      ok)      cp "$FAKE_MP4" "$RCB_DATA/replay.mp4"; echo '{"replays": [{"success": false, "state_sha": "zzzz"}], "instance_matches": false}' ;;
      die)     echo 'Segmentation fault' >&2; exit 139 ;;
      hang)    exec sleep 600 ;;
    esac ;;
  *) exec "$REAL_PYTHON" "$@" ;;
esac
"""


def tiny_mp4(path: Path) -> bool:
    if not shutil.which("ffmpeg"):
        return False
    r = subprocess.run(["ffmpeg", "-loglevel", "error", "-y", "-f", "lavfi", "-i", "color=c=gray:s=64x64:d=1", "-r", "10",
                        "-pix_fmt", "yuv420p", str(path)], capture_output=True, timeout=120)
    return r.returncode == 0 and path.exists()


def finalize(episode: dict | None = EPISODE, live_video: str = "good", newest_pid: int | None = None, **env) -> dict:
    """Run the real finalize.sh in a scratch /out with the stand-in python; returns final.json (plus "_stdout", "_args").
    live_video: "good" (a playable live.mp4), "bad" (a file that does not play) or "none"."""
    with tempfile.TemporaryDirectory(prefix="rcb_behavior_fin_") as tmp:
        tmp = Path(tmp); out = tmp / "out"; bindir = tmp / "bin"
        out.mkdir(); bindir.mkdir()
        fake = bindir / "python"
        fake.write_text(FAKE_PYTHON); fake.chmod(fake.stat().st_mode | stat.S_IEXEC)
        mp4 = tmp / "v.mp4"; have = tiny_mp4(mp4)
        if episode is not None:
            (out / "episode.json").write_text(json.dumps(episode))
        if newest_pid is not None:                              # startups.jsonl: the newest service start's pid
            (out / "startups.jsonl").write_text(json.dumps({"ts": 1, "pid": 1}) + "\n" + json.dumps({"ts": 2, "pid": newest_pid}) + "\n")
        (out / "final.json").write_text(json.dumps({**(episode or {}), "finalized": False}))     # the service's own copy
        np.savez(out / "trajectory.npz", actions=np.zeros((3, 25), np.float32), task="picking_up_trash")
        if live_video == "good" and have:
            shutil.copy(mp4, out / "live.mp4")
        elif live_video == "bad":
            (out / "live.mp4").write_bytes(b"not a video")
        e = {**os.environ, "PATH": f"{bindir}:{os.environ['PATH']}", "REAL_PYTHON": sys.executable, "RCB_DATA": str(out),
             "RCB_TOOL": "/srv/rcb_behavior.py", "RCB_TASK": "picking_up_trash", "RCB_INSTANCE": "/srv/instance.json",
             "FAKE_MP4": str(mp4), "PYTHONPATH": str(STD / "environment" / "sim"), **{k: str(v) for k, v in env.items()}}
        p = subprocess.run(["sh", str(STD / "environment" / "sim" / "finalize.sh")], env=e, capture_output=True, text=True, timeout=300)
        assert p.returncode == 0, p.stderr
        assert not list(out.glob("final.json*tmp")), "a temporary final.json was left behind"
        args = (out / ".args").read_text().splitlines() if (out / ".args").exists() else []
        assert all("--video" in a for a in args) and len(args) <= 1, args     # never a grading replay; one video-only render at most
        fin = json.loads((out / "final.json").read_text())
        assert "replay_success" not in fin and "deterministic" not in fin, fin
        return {**fin, "_stdout": p.stdout, "_args": args, "_have_ffmpeg": have}


def gpu_openable() -> bool:
    """finalize.sh's own GPU probe (before the video-only render)."""
    for dev in ("/dev/nvidiactl", "/dev/nvidia0"):
        if os.path.exists(dev):
            try:
                open(dev, "rb").close()
            except OSError:
                return False
    return True


@unittest.skipUnless(shutil.which("sh") and shutil.which("ffprobe"), "needs sh and ffprobe")
class Finalize(unittest.TestCase):
    def graded(self, fin: dict) -> dict:
        return grade_standard({k: v for k, v in fin.items() if not k.startswith("_")})[1]

    def test_the_live_episode_is_the_verdict_and_nothing_replays(self):
        fin = finalize()
        if not fin["_have_ffmpeg"]:
            self.skipTest("needs ffmpeg for a playable live video")
        self.assertEqual(fin["_args"], [])                                     # no replay at all
        self.assertTrue(fin["finalized"] and fin["success"] and fin["live_success"] and fin["video"])
        self.assertEqual((fin["graded_by"], fin["replays"], fin["video_source"], fin["video_pending"], fin["state_sha"]), ("live", 0, "live", False, "aaaa"))
        self.assertEqual(self.graded(fin)["success"], 1)
        fin = finalize({**EPISODE, "success": False, "reason": "timeout", "settle_steps": 150})
        self.assertFalse(fin["success"]); self.assertEqual((self.graded(fin)["success"], self.graded(fin)["infra_error"]), (0, 0))
        fin = finalize({**EPISODE, "reason": "success", "settled_success": True, "settle_steps": 12})
        self.assertTrue(fin["settled_success"]); self.assertEqual(self.graded(fin)["success"], 1)

    @unittest.skipUnless(gpu_openable(), "where a GPU device exists, needs access to it")
    def test_a_missing_live_video_gets_one_render_that_decides_nothing(self):
        for lv in ("none", "bad"):
            fin = finalize(live_video=lv)
            self.assertEqual(len(fin["_args"]), 1, fin["_args"])
            self.assertTrue(fin["success"]); self.assertEqual(self.graded(fin)["success"], 1)   # the render's own result is not read
            if fin["_have_ffmpeg"]:
                self.assertEqual((fin["video"], fin["video_source"], fin["video_pending"]), (True, "render", False))
        fin = finalize(live_video="none", FAKE_RENDER="die")                   # the render fails: only the video is lost
        self.assertEqual((fin["video"], fin["video_pending"]), (False, False)); self.assertNotIn("infra_error", fin)
        self.assertEqual(self.graded(fin)["success"], 1)
        fin = finalize({**EPISODE, "success": False, "reason": "timeout"}, live_video="none")
        self.assertFalse(fin["success"]); self.assertEqual(self.graded(fin)["success"], 0)

    @unittest.skipUnless(gpu_openable(), "where a GPU device exists, needs access to it")
    def test_a_render_out_of_time_loses_only_the_video(self):
        fin = finalize(live_video="none", FAKE_RENDER="hang", RCB_COLLECT_BUDGET_S=400)
        self.assertTrue(fin["success"]); self.assertEqual((fin["video"], fin["video_pending"]), (False, False))
        self.assertIn("video render exit 124", fin["_stdout"])

    def test_a_breakdown_is_a_recorded_failure(self):
        # (2026-10-16) the agent's 0 with sim_breakdown until the owner decides whether it is infrastructure
        fin = finalize({**EPISODE, "success": False, "reason": "failure: simulator breakdown (robot state not finite)", "sim_breakdown": True})
        self.assertTrue(fin["sim_breakdown"]); self.assertFalse(fin.get("infra_error"))
        g = self.graded(fin)
        self.assertEqual((g["success"], g["infra_error"], g["sim_breakdown"]), (0, 0, 1), g)

    def test_no_episode_record(self):
        fin = finalize(episode=None)
        self.assertEqual(fin.get("infra_error"), 1); self.assertIn("no episode.json", fin["error"])
        self.assertEqual(self.graded(fin)["infra_error"], 1)

    def test_service_never_ended_the_episode(self):
        fin = finalize(episode=None, FAKE_END_RC=1)
        self.assertEqual(fin.get("infra_error"), 1); self.assertTrue(fin["finalized"]); self.assertFalse(fin["success"])
        self.assertEqual(fin["_args"], [])

    def test_a_dumped_episode_is_the_verdict_when_the_service_is_late_to_exit(self):
        ep = {**EPISODE, "pid": 4242, "startup": 2}
        fin = finalize(ep, FAKE_END_RC=1, live_video="none", newest_pid=4242)   # the newest start dumped, then did not exit
        self.assertTrue(fin["success"]); self.assertTrue(fin["end_timed_out"]); self.assertNotIn("infra_error", fin)
        self.assertEqual(fin["_args"], [])                      # no render while the service may still hold the GPU
        self.assertEqual((self.graded(fin)["success"], self.graded(fin)["infra_error"]), (1, 0))
        for stale in ({**EPISODE, "pid": 1}, EPISODE):          # an earlier start's record, or one without a pid: never taken
            fin = finalize(stale, FAKE_END_RC=1, live_video="none", newest_pid=4242)
            self.assertEqual(fin.get("infra_error"), 1); self.assertFalse(fin["success"])

    def test_a_give_up_on_disk_is_kept(self):
        fin = finalize(episode=None, FAKE_END_RC=2)                            # rc 2: final.json holds the verdict
        self.assertNotIn("graded_by", fin)                                     # untouched by the hook
        self.assertEqual(fin["_args"], [])


# ------------------------------------------------------------------------------------------------ privileged grade.py
FAKE_TOOL = r'''"""stand-in for the tooling in the verifier: MAX_STEPS and the `replay` CLI"""
import json, os, sys
MAX_STEPS = 200_000
if __name__ == "__main__":
    open(os.environ["FAKE_COUNT"] + ".args", "a").write(" ".join(sys.argv[1:]) + "\n")
    video = "--video" in sys.argv
    if video and os.environ.get("FAKE_VIDEO") == "die":
        sys.exit(139)
    if video and os.environ.get("FAKE_VIDEO") == "other":
        print(json.dumps({"replays": [{"success": True, "state_sha": "vvvv"}], "instance_matches": True})); sys.exit(0)
    mode = os.environ.get("FAKE_REPLAY", "ok")
    if mode == "breakdown":
        print(json.dumps({"replays": [{"success": False, "state_sha": "dddd", "breakdown": True, "end_reason": "failure: simulator breakdown (x)"}],
                          "instance_matches": True, "instance_exact": True})); sys.exit(0)
    if mode == "die":
        sys.exit(139)
    sha = "aaaa"
    if mode == "nondet":
        n = os.environ["FAKE_COUNT"]; k = int(open(n).read() or 0) if os.path.exists(n) else 0; open(n, "w").write(str(k + 1)); sha = f"sha{k}"
    print(json.dumps({"replays": [{"success": mode != "fail", "state_sha": sha, "q_score": 1.0, "sim_steps": 3, "fallen": False}],
                      "instance_matches": mode != "drift", "instance_exact": mode != "drift"}))
'''


def grade_privileged(write_traj, video: bool = False, **env) -> tuple[str | None, dict | None]:
    with tempfile.TemporaryDirectory(prefix="rcb_behavior_pgrade_") as tmp:
        tmp = Path(tmp); log = tmp / "log"; log.mkdir()
        shutil.copy(PRIV / "tests" / "grade.py", tmp / "grade.py")
        (tmp / "rcb_behavior.py").write_text(FAKE_TOOL)
        (tmp / "instance.json").write_text(json.dumps({"action_dim": 25}))
        traj = tmp / "trajectory.npz"
        if write_traj is not None:
            write_traj(traj)
        e = {**os.environ, "RCB_VERIFIER_LOG_DIR": str(log), "FAKE_COUNT": str(tmp / "count"), "PYTHONDONTWRITEBYTECODE": "1",
             **{k: str(v) for k, v in env.items()}}
        subprocess.run([sys.executable, str(tmp / "grade.py"), "--family", "picking_up_trash", "--instance", str(tmp / "instance.json"),
                        "--traj", str(traj)] + ([] if video else ["--no-video"]), env=e, capture_output=True, text=True, timeout=120)
        txt = (log / "reward.txt").read_text().strip() if (log / "reward.txt").exists() else None
        js = json.loads((log / "reward.json").read_text()) if (log / "reward.json").exists() else None
        if js is not None:
            a = tmp / "count.args"
            js["_args"] = a.read_text().splitlines() if a.exists() else []
        return txt, js


def npy_bytes(a) -> bytes:
    import io
    f = io.BytesIO(); np.save(f, a)
    return f.getvalue()


def good_traj(p, **extra):
    np.savez(p, actions=np.zeros((3, 25), np.float32), task="picking_up_trash", **extra)


class PrivilegedGrader(unittest.TestCase):
    def check(self, write_traj, reward: str, env: dict | None = None, **want):
        txt, js = grade_privileged(write_traj, **(env or {}))
        self.assertEqual(txt, reward, js)
        for k, v in want.items():
            self.assertEqual(js.get(k), v, (k, js))
        self.assertIn("deterministic", js); self.assertIn("grader_error", js); self.assertIn("infra_error", js)
        return js

    def test_graded_replays_alike_and_the_video_apart(self):
        txt, js = grade_privileged(good_traj, video=True)
        self.assertEqual(txt, "1", js)
        self.assertEqual(len(js["_args"]), 3, js["_args"])
        self.assertTrue(all("--video" not in a for a in js["_args"][:2])); self.assertIn("--video", js["_args"][2])
        self.assertEqual((js["deterministic"], js["video_replay_matches"]), (1, 1))
        txt, js = grade_privileged(good_traj, video=True, FAKE_VIDEO="other")   # the video replay's state never decides
        self.assertEqual(txt, "1", js); self.assertEqual((js["deterministic"], js["video_replay_matches"]), (1, 0))

    def test_the_verdict_never_waits_for_the_video(self):
        # (2026-10-16, PROTOCOL §4) the verdict is on disk before the video replay; a video replay that dies, or no
        # verifier time left for it, leaves the verdict as it was (video_rendered 0, video.json says why)
        txt, js = grade_privileged(good_traj, video=True, FAKE_VIDEO="die")
        self.assertEqual(txt, "1", js); self.assertEqual((js["success"], js["video_rendered"], js["video_replay_matches"]), (1, 0, 0))
        self.assertEqual(len(js["_args"]), 3, js["_args"])
        txt, js = grade_privileged(good_traj, video=True, RCB_VERIFIER_TIMEOUT_S="700")   # 700 s - 600 s margin: no time
        self.assertEqual(txt, "1", js); self.assertEqual(len(js["_args"]), 2, js["_args"]); self.assertEqual(js["video_rendered"], 0)

    def test_a_breakdown_is_a_recorded_failure(self):
        js = self.check(good_traj, "0", env={"FAKE_REPLAY": "breakdown"}, success=0, sim_breakdown=1, infra_error=0, grader_error=0)
        self.assertEqual(js["deterministic"], 1)

    def test_pass_and_plain_failures(self):
        self.check(good_traj, "1", success=1, grader_error=0, infra_error=0, instance_ok=1, deterministic=1)
        self.check(good_traj, "0", {"FAKE_REPLAY": "fail"}, success=0, grader_error=0, infra_error=0, all_success=0)
        self.check(good_traj, "0", {"FAKE_REPLAY": "nondet"}, success=0, grader_error=0, deterministic=0)
        self.check(None, "0", missing_trajectory=1, grader_error=0, infra_error=0, deterministic=0)

    def test_a_file_the_agent_wrote_wrongly_is_bad_trajectory(self):
        cases = {
            "no task entry": lambda p: np.savez(p, actions=np.zeros((3, 25), np.float32)),
            "no actions entry": lambda p: np.savez(p, task="picking_up_trash"),
            "object actions": lambda p: np.savez(p, actions=np.array([{"a": 1}], dtype=object), task="picking_up_trash"),
            "text actions": lambda p: np.savez(p, actions=np.array(["x", "y"]), task="picking_up_trash"),
            "not an npz": lambda p: p.write_bytes(b"this is not a zip file"),
            "a plain npy": lambda p: p.write_bytes(npy_bytes(np.zeros((3, 25), np.float32))),
            "empty file": lambda p: p.write_bytes(b""),
            "wrong width": lambda p: np.savez(p, actions=np.zeros((3, 24), np.float32), task="picking_up_trash"),
            "one row, flat": lambda p: np.savez(p, actions=np.zeros(25, np.float32), task="picking_up_trash"),
            "nan": lambda p: np.savez(p, actions=np.full((3, 25), np.nan, np.float32), task="picking_up_trash"),
        }
        for name, w in cases.items():
            with self.subTest(name):
                self.check(w, "0", success=0, bad_trajectory=1, grader_error=0, infra_error=0)
        self.check(lambda p: np.savez(p, actions=np.zeros((3, 25), np.float32), task="another_task"), "0", wrong_family=1, grader_error=0)

    def test_the_row_cap_is_the_graders_not_the_runaway_guard(self):
        # 2026-10-14 (board 0121): at most 40,000 rows, so that every accepted trajectory gets a verdict within the
        # replay limit (the tooling's runaway guard, 200,000, is the episode's)
        self.check(lambda p: np.savez(p, actions=np.zeros((40_000, 25), np.float32), task="picking_up_trash"), "1", success=1)
        self.check(lambda p: np.savez(p, actions=np.zeros((40_001, 25), np.float32), task="picking_up_trash"), "0",
                   bad_trajectory=1, grader_error=0, infra_error=0, n_actions=40_001)

    def test_an_extra_entry_does_not_matter_to_the_grader(self):
        self.check(lambda p: good_traj(p, notes=np.array([{"k": 1}], dtype=object)), "1", success=1)

    def test_replay_death_and_instance_drift_are_not_the_agents(self):
        self.check(good_traj, "0", {"FAKE_REPLAY": "die"}, success=0, grader_error=1, infra_error=1, replay_failed=1)
        self.check(good_traj, "0", {"FAKE_REPLAY": "drift"}, success=0, instance_ok=0, infra_error=1, grader_error=1)


class LoadTraj(unittest.TestCase):
    """The tooling's own loader (the replay CLI): an extra entry that needs pickle is skipped, the two it needs are not."""

    @classmethod
    def setUpClass(cls):
        import importlib.util
        os.environ["RCB_SESSION_LOG"] = ""; os.environ["RCB_SESSION_LOG_KEEP"] = ""
        spec = importlib.util.spec_from_file_location("rcb_behavior_loader_test", PRIV / "environment" / "rcb_behavior.py")
        cls.M = importlib.util.module_from_spec(spec); spec.loader.exec_module(cls.M)

    def test_extra_object_entry_is_skipped(self):
        with tempfile.TemporaryDirectory() as tmp:
            p = Path(tmp) / "t.npz"
            good_traj(p, notes=np.array([{"k": 1}], dtype=object), meta="{}")
            t = self.M._load_traj(str(p))
            self.assertEqual(t["task"], "picking_up_trash"); self.assertEqual(t["actions"].shape, (3, 25))
            self.assertNotIn("notes", t); self.assertEqual(t["meta"], "{}")
            np.savez(p, actions=np.array([{"a": 1}], dtype=object), task="picking_up_trash")
            with self.assertRaises(ValueError):
                self.M._load_traj(str(p))


if __name__ == "__main__":
    unittest.main()
