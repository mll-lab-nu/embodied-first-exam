"""Whose failure a 0 is, in BEHAVIOR's two graders and the standard collect hook (board 0067): the real
tests/grade.py of both template twins and the real environment/sim/finalize.sh, on synthetic records; no simulator.

    python3 -m unittest discover -s scripts/behavior/tests          # needs numpy

- standard tests/grade.py: a missing, unreadable or unfinalized final.json and a replay that did not run to its result
  are infra_error = 1 (no verdict on the agent), never a plain 0; a reward is written in every case;
- environment/sim/finalize.sh (run whole, with a stand-in `python` for the end command and the replay CLI): replay exit
  codes, a replay that dies / hangs / prints nothing, the atomic final.json;
- privileged tests/grade.py (with a stand-in tooling module): an unreadable trajectory is bad_trajectory, a replay that
  dies is grader_error, instance_ok 0 is infra_error.
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
           "task": "picking_up_trash", "n_actions": 90, "live_sha": "aaaa", "sim_startups": 1, "resumes": 0}
GOOD = {**EPISODE, "finalized": True, "replay_success": True, "deterministic": True, "live_matches_replay": True, "video": True, "q_score": 1.0}


# ------------------------------------------------------------------------------------------------ standard grade.py
def grade_standard(final) -> tuple[str | None, dict | None]:
    """Run the standard grader on a final.json (dict, raw text, or None = no file): (reward.txt, reward.json)."""
    with tempfile.TemporaryDirectory(prefix="rcb_behavior_grade_") as tmp:
        out, log = Path(tmp) / "out", Path(tmp) / "log"
        out.mkdir(); log.mkdir()
        if final is not None:
            (out / "final.json").write_text(final if isinstance(final, str) else json.dumps(final))
        src = (STD / "tests" / "grade.py").read_text()
        assert '"/logs/verifier"' in src and '("/out", "/data")' in src
        src = src.replace('"/logs/verifier"', repr(str(log))).replace('("/out", "/data")', repr((str(out),)))
        (Path(tmp) / "grade.py").write_text(src)
        subprocess.run([sys.executable, str(Path(tmp) / "grade.py")], capture_output=True, text=True, timeout=60)
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
        self.assertIn("deterministic", js); self.assertIn("infra_error", js); self.assertIn("grader_error", js)
        return js

    def test_pass(self):
        self.check(GOOD, "1", success=1, infra_error=0, grader_error=0, finalized=1, missing_log=0, replay_error=0)

    def test_agent_failures_stay_the_agents(self):
        self.check({**GOOD, "success": False, "replay_success": False, "reason": "timeout"}, "0", success=0, infra_error=0, grader_error=0)
        self.check({**GOOD, "deterministic": False}, "0", success=0, infra_error=0)
        self.check({**GOOD, "replay_success": False}, "0", success=0, infra_error=0)
        self.check({**GOOD, "success": False, "replay_success": False, "reason": "failure: the robot fell over"}, "0", infra_error=0, task_failure=1)
        # every crash happened inside a call: the layer's give-up without the infra flag
        self.check({"success": False, "done": True, "reason": "sim_crashed_on_call", "finalized": True, "gave_up": True}, "0",
                   infra_error=0, gave_up=1, finalized=1)

    def test_missing_final_json_is_infrastructure(self):
        self.check(None, "0", success=0, missing_log=1, infra_error=1, grader_error=0, deterministic=0)

    def test_unreadable_final_json_still_writes_a_reward(self):
        for raw in ('{"success": true, "finali', "", "[1, 2]", "null", "\x00\x00"):
            self.check(raw, "0", success=0, infra_error=1, grader_error=1, missing_log=0)

    def test_unfinalized_is_infrastructure_even_when_live_succeeded(self):
        # the service's own copy: the collect hook was killed or never completed, so no replay fields
        self.check({**EPISODE, "finalized": False, "done": True}, "0", success=0, live_success=1, finalized=0, infra_error=1)
        self.check({**GOOD, "finalized": False}, "0", success=0, infra_error=1)
        self.check({k: v for k, v in GOOD.items() if k != "finalized"}, "0", success=0, infra_error=1)

    def test_replay_that_did_not_run_is_infrastructure(self):
        self.check({**GOOD, "replay_success": False, "deterministic": False, "replay_error": "replay 1: no result (exit 139)", "infra_error": 1},
                   "0", success=0, infra_error=1, grader_error=1, replay_error=1)
        self.check({**GOOD, "gpu_lost": True, "replay_success": False}, "0", infra_error=1, grader_error=1, gpu_lost=1)

    def test_layer_infra_verdicts(self):
        self.check({"success": False, "done": True, "reason": "sim_crashed", "finalized": True, "gave_up": True, "infra_error": 1}, "0",
                   infra_error=1, gave_up=1)
        self.check({**GOOD, "infra_error": 1}, "0", success=0, infra_error=1)      # an infra flag never passes


# ------------------------------------------------------------------------------------------------ finalize.sh
FAKE_PYTHON = r"""#!/bin/sh
# stand-in for `python` in finalize.sh: the end command, the replay CLI ($RCB_TOOL), and the real interpreter for heredocs
case "$1" in
  /srv/rcb_limited.py) exit "${FAKE_END_RC:-0}" ;;
  "$RCB_TOOL")
    n=$(( $(cat "$RCB_DATA/.n" 2>/dev/null || echo 0) + 1 )); echo "$n" > "$RCB_DATA/.n"
    eval "mode=\${FAKE_REPLAY_$n:-ok}"
    case "$mode" in
      ok)      echo '[rcb] noise on stdout'; echo '{"replays": [{"success": true, "state_sha": "aaaa", "q_score": 1.0}], "instance_matches": true}' ;;
      fail)    echo '{"replays": [{"success": false, "state_sha": "aaaa", "q_score": 0.3}], "instance_matches": true}' ;;
      drift)   echo '{"replays": [{"success": false, "state_sha": "cccc", "q_score": 0.0}], "instance_matches": false}' ;;
      other)   echo '{"replays": [{"success": true, "state_sha": "bbbb", "q_score": 1.0}], "instance_matches": true}' ;;
      die)     echo 'Segmentation fault' >&2; exit 139 ;;
      silent)  exit 0 ;;
      error)   echo '{"error": "trajectory task x != y"}'; exit 2 ;;
      hang)    exec sleep 600 ;;
    esac ;;
  *) exec "$REAL_PYTHON" "$@" ;;
esac
"""


def finalize(episode: dict | None = EPISODE, **env) -> dict:
    """Run the real finalize.sh in a scratch /out with the stand-in python; returns final.json (plus "_stdout")."""
    with tempfile.TemporaryDirectory(prefix="rcb_behavior_fin_") as tmp:
        tmp = Path(tmp); out = tmp / "out"; bindir = tmp / "bin"
        out.mkdir(); bindir.mkdir()
        fake = bindir / "python"
        fake.write_text(FAKE_PYTHON); fake.chmod(fake.stat().st_mode | stat.S_IEXEC)
        if episode is not None:
            (out / "episode.json").write_text(json.dumps(episode))
        (out / "final.json").write_text(json.dumps({**(episode or {}), "finalized": False}))     # the service's own copy
        np.savez(out / "trajectory.npz", actions=np.zeros((3, 25), np.float32), task="picking_up_trash")
        e = {**os.environ, "PATH": f"{bindir}:{os.environ['PATH']}", "REAL_PYTHON": sys.executable, "RCB_DATA": str(out),
             "RCB_TOOL": "/srv/rcb_behavior.py", "RCB_TASK": "picking_up_trash", "RCB_INSTANCE": "/srv/instance.json",
             "PYTHONPATH": str(STD / "environment" / "sim"), **{k: str(v) for k, v in env.items()}}
        p = subprocess.run(["sh", str(STD / "environment" / "sim" / "finalize.sh")], env=e, capture_output=True, text=True, timeout=300)
        assert p.returncode == 0, p.stderr
        assert not list(out.glob("final.json*tmp")), "a temporary final.json was left behind"
        return {**json.loads((out / "final.json").read_text()), "_stdout": p.stdout}


def gpu_openable() -> bool:
    """finalize.sh's own GPU probe: on a host whose /dev/nvidia* cannot be opened every run is the gpu_lost case."""
    for dev in ("/dev/nvidiactl", "/dev/nvidia0"):
        if os.path.exists(dev):
            try:
                open(dev, "rb").close()
            except OSError:
                return False
    return True


@unittest.skipUnless(shutil.which("sh") and gpu_openable(), "needs sh and, where a GPU device exists, access to it")
class Finalize(unittest.TestCase):
    def graded(self, fin: dict) -> dict:
        return grade_standard({k: v for k, v in fin.items() if k != "_stdout"})[1]

    def test_two_good_replays(self):
        fin = finalize()
        self.assertTrue(fin["finalized"] and fin["replay_success"] and fin["deterministic"] and fin["live_matches_replay"])
        self.assertNotIn("replay_error", fin); self.assertNotIn("infra_error", fin)
        self.assertIn("replay 1 exit 0", fin["_stdout"]); self.assertIn("replay 2 exit 0", fin["_stdout"])
        self.assertEqual(self.graded(fin)["success"], 1)

    def test_agent_outcomes_are_not_infrastructure(self):
        fin = finalize(FAKE_REPLAY_1="fail", FAKE_REPLAY_2="fail")              # the replays ran and the goal did not hold
        self.assertFalse(fin["replay_success"]); self.assertTrue(fin["deterministic"]); self.assertNotIn("infra_error", fin)
        self.assertEqual(self.graded(fin)["infra_error"], 0)
        fin = finalize(FAKE_REPLAY_2="other")                                   # not deterministic
        self.assertFalse(fin["deterministic"]); self.assertNotIn("infra_error", fin)
        self.assertEqual((self.graded(fin)["success"], self.graded(fin)["infra_error"]), (0, 0))

    def test_a_replay_that_dies_is_infrastructure(self):
        for n, mode, text in ((1, "die", "exit 139"), (2, "die", "exit 139"), (1, "silent", "exit 0"), (2, "error", "trajectory task")):
            fin = finalize(**{f"FAKE_REPLAY_{n}": mode})
            self.assertEqual(fin.get("infra_error"), 1, (n, mode, fin)); self.assertTrue(fin["finalized"])
            self.assertIn(f"replay {n}", fin["replay_error"]); self.assertIn(text, fin["replay_error"])
            self.assertTrue(fin["error"].startswith("infrastructure"))
            g = self.graded(fin)
            self.assertEqual((g["success"], g["infra_error"], g["grader_error"], g["replay_error"]), (0, 1, 1, 1), g)

    def test_a_scene_that_does_not_rebuild_is_infrastructure(self):
        fin = finalize(FAKE_REPLAY_1="drift")
        self.assertEqual((fin.get("infra_error"), fin.get("instance_ok")), (1, 0)); self.assertNotIn("replay_error", fin)
        g = self.graded(fin)
        self.assertEqual((g["success"], g["infra_error"], g["instance_ok"]), (0, 1, 0), g)
        self.assertEqual(self.graded(finalize())["instance_ok"], 1)

    def test_a_replay_out_of_time_is_stopped_and_recorded(self):
        fin = finalize(FAKE_REPLAY_2="hang", RCB_COLLECT_BUDGET_S=0, RCB_REPLAY_MIN_S=2)
        self.assertEqual(fin.get("infra_error"), 1); self.assertIn("replay 2", fin["replay_error"])
        self.assertIn("out of time", fin["replay_error"]); self.assertTrue(fin["finalized"])
        self.assertIn("replay 2 exit 124", fin["_stdout"])

    def test_no_episode_record(self):
        fin = finalize(episode=None)
        self.assertEqual(fin.get("infra_error"), 1); self.assertIn("no episode.json", fin["error"])
        self.assertEqual(self.graded(fin)["infra_error"], 1)

    def test_service_never_ended_the_episode(self):
        fin = finalize(FAKE_END_RC=1)
        self.assertEqual(fin.get("infra_error"), 1); self.assertTrue(fin["finalized"]); self.assertFalse(fin["success"])
        self.assertNotIn("replay 1 exit", fin["_stdout"])


# ------------------------------------------------------------------------------------------------ privileged grade.py
FAKE_TOOL = r'''"""stand-in for the tooling in the verifier: MAX_STEPS and the `replay` CLI"""
import json, os, sys
MAX_STEPS = 200_000
if __name__ == "__main__":
    mode = os.environ.get("FAKE_REPLAY", "ok")
    if mode == "die":
        sys.exit(139)
    sha = "aaaa"
    if mode == "nondet":
        n = os.environ["FAKE_COUNT"]; k = int(open(n).read() or 0) if os.path.exists(n) else 0; open(n, "w").write(str(k + 1)); sha = f"sha{k}"
    print(json.dumps({"replays": [{"success": mode != "fail", "state_sha": sha, "q_score": 1.0, "sim_steps": 3, "fallen": False}],
                      "instance_matches": mode != "drift", "instance_exact": mode != "drift"}))
'''


def grade_privileged(write_traj, **env) -> tuple[str | None, dict | None]:
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
                        "--traj", str(traj), "--no-video"], env=e, capture_output=True, text=True, timeout=120)
        txt = (log / "reward.txt").read_text().strip() if (log / "reward.txt").exists() else None
        js = json.loads((log / "reward.json").read_text()) if (log / "reward.json").exists() else None
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
