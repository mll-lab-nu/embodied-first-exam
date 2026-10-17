"""DexJoCo standard mode, graded by the live episode (owner, 2026-10-17, board 0151): the collect hook
(shared/standard/finalize.sh, on the real shared layer rcb_limited.py) and the verifier (shared/standard/grade.py) on
synthetic sidecar records, and the service's start-state check on the stub simulator. Needs numpy (the service test);
no MuJoCo.

    python3 scripts/dexjoco/tests/test_standard_grading.py

- the hook writes the live episode's verdict (graded_by = "live", replays = 0) and replays nothing: a stub of the
  privileged tooling (rcb_dexjoco.py replay) leaves a marker if anything calls it;
- live success -> 1, live failure -> 0; the video pass runs after the verdict and its failure or timeout changes
  nothing (and is never infra);
- a give-up after crashes between calls (sim_crashed, resume_failed) -> infra; crashes all inside calls -> 0, not infra;
  a simulator error raised by the agent's actions -> 0 with sim_error, not infra;
- final.json missing / unreadable / not finalized, the service not ending in time -> infra;
- a scene that does not rebuild to the frozen instance's hash: the service starts no episode (instance_mismatch, infra).
"""
import json
import os
import shutil
import signal
import socket
import subprocess
import sys
import tempfile
import time
import unittest
import urllib.error
import urllib.request
from pathlib import Path

HERE = Path(__file__).resolve().parent
DEXJOCO, LAYER = HERE.parent, HERE.parents[1] / "eai_standard"
STD = DEXJOCO / "shared" / "standard"

STUB_TOOL = """import sys, pathlib
pathlib.Path(sys.argv[0]).with_name("TOOL_CALLED").write_text(" ".join(sys.argv[1:]))
sys.exit(1)
"""
STUB_VIDEO = """import json, os, sys, time
a = sys.argv
out, js = a[a.index("--out") + 1], a[a.index("--json") + 1]
mode = os.environ.get("STUB_VIDEO", "ok")
if mode == "hang":
    time.sleep(600)
if mode == "crash":
    raise SystemExit(3)
open(out, "wb").write(b"mp4")
json.dump({"video": True, "rows": 3}, open(js, "w"))
"""


def grade(data: Path) -> tuple[str, dict]:
    logs = data.parent / "verifier"
    shutil.rmtree(logs, ignore_errors=True)
    subprocess.run([sys.executable, "-B", str(STD / "grade.py")], check=True, capture_output=True,
                   env={**os.environ, "RCB_DATA": str(data), "RCB_VERIFIER_LOG_DIR": str(logs)})
    return (logs / "reward.txt").read_text().strip(), json.loads((logs / "reward.json").read_text())


class Hook(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.srv, self.data = self.tmp / "srv", self.tmp / "data"
        self.srv.mkdir(); self.data.mkdir()
        shutil.copy(STD / "finalize.sh", self.srv)
        for f in ("rcb_limited.py", "rcb1.py"):
            shutil.copy(LAYER / f, self.srv)
        (self.srv / "rcb_dexjoco.py").write_text(STUB_TOOL)
        (self.srv / "video.py").write_text(STUB_VIDEO)
        self.bin = self.tmp / "bin"                  # the hook runs `python`: this interpreter (it has numpy)
        self.bin.mkdir()
        (self.bin / "python").write_text(f'#!/bin/sh\nexec "{sys.executable}" "$@"\n')   # not a symlink: a venv's
        (self.bin / "python").chmod(0o755)                                                 # python finds it by path

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def episode(self, **kw):
        """The service's dump: episode.json + trajectory.npz, its PID file naming a process that has exited."""
        ep = {"success": False, "steps": 3, "calls": 2, "control_steps": 3, "physics_steps": 30, "elapsed_s": 12.0,
              "reason": "timeout", "done": True, "task": "water_plant", "n_actions": 3, "task_failure": 0,
              "instance_ok": True, "visible_cpus": 8, "blas_threads": 4, "threads_ok": 1, "sim_startups": 1,
              "resumes": 0, "live_sha": "abc"}
        ep.update(kw)
        (self.data / "episode.json").write_text(json.dumps(ep))
        (self.data / "trajectory.npz").write_bytes(b"npz")
        p = subprocess.Popen(["true"]); p.wait()
        (self.data / "server.pid").write_text(str(p.pid))
        (self.data / "startups.jsonl").write_text(json.dumps({"ts": time.time(), "pid": p.pid}) + "\n")

    def hook(self, budget=300, end_timeout=20, **env):
        r = subprocess.run(["sh", str(self.srv / "finalize.sh")], capture_output=True, text=True, timeout=120,
                           env={**os.environ, "PATH": f"{self.bin}{os.pathsep}{os.environ.get('PATH', '')}",
                                "RCB_DATA": str(self.data), "RCB_SRV": str(self.srv),
                                "RCB_TOOL": str(self.srv / "rcb_dexjoco.py"), "RCB_INSTANCE": "/nonexistent.npz",
                                "RCB_TASK": "water_plant", "RCB_COLLECT_BUDGET_S": str(budget),
                                "RCB_COLLECT_END_TIMEOUT_S": str(end_timeout), **env})
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertFalse((self.srv / "TOOL_CALLED").exists(), "the hook ran the tooling (a grading replay)")
        return json.loads((self.data / "final.json").read_text())

    def test_live_success_is_1_and_nothing_is_replayed(self):
        self.episode(success=True, reason="success")
        fin = self.hook()
        self.assertEqual((fin["graded_by"], fin["replays"], fin["finalized"]), ("live", 0, True))
        self.assertTrue(fin["success"] and fin["live_success"])
        self.assertTrue(fin["video"]); self.assertFalse(fin["video_pending"]); self.assertEqual(fin["video_source"], "render")
        for k in ("replay_success", "deterministic", "live_matches_replay"):
            self.assertNotIn(k, fin)
        txt, rw = grade(self.data)
        self.assertEqual(txt, "1")
        self.assertEqual((rw["success"], rw["live_success"], rw["graded_by_live"], rw["replays"], rw["infra_error"]), (1, 1, 1, 0, 0))
        self.assertNotIn("deterministic", rw); self.assertNotIn("replay_success", rw)

    def test_live_failure_is_0(self):
        self.episode(success=False, reason="timeout")
        self.hook()
        txt, rw = grade(self.data)
        self.assertEqual((txt, rw["success"], rw["infra_error"]), ("0", 0, 0))

    def test_task_failure_is_0_not_infra(self):
        self.episode(success=False, reason="failure: illegal stack", task_failure=1)
        self.hook()
        txt, rw = grade(self.data)
        self.assertEqual((txt, rw["task_failure"], rw["infra_error"]), ("0", 1, 0))

    def test_sim_error_from_the_agents_actions_is_0_not_infra(self):
        for success in (False, True):   # even a record that says success: a sim error is never one
            self.episode(success=success, reason="error")
            self.hook()
            txt, rw = grade(self.data)
            self.assertEqual((txt, rw["sim_error"], rw["infra_error"]), ("0", 1, 0))

    def test_a_failed_video_changes_nothing(self):
        for mode in ("crash", "hang"):
            with self.subTest(mode=mode):
                self.episode(success=True, reason="success")
                # "hang": the video gets 75 s (budget 150 - 60 - 15) and is stopped; the verdict is already on disk
                fin = self.hook(budget=150 if mode == "hang" else 300, STUB_VIDEO=mode)
                self.assertTrue(fin["success"]); self.assertFalse(fin["video"]); self.assertFalse(fin["video_pending"])
                self.assertFalse((self.data / "replay.mp4").exists())
                txt, rw = grade(self.data)
                self.assertEqual((txt, rw["infra_error"], rw["video_rendered"]), ("1", 0, 0))
                (self.data / "final.json").unlink()

    def test_no_time_for_the_video_leaves_the_verdict(self):
        self.episode(success=True, reason="success")
        fin = self.hook(budget=100)    # 100 - 60 - 15 < 60 s: no video pass at all
        self.assertTrue(fin["success"]); self.assertFalse(fin["video"]); self.assertFalse(fin["video_pending"])
        self.assertEqual(grade(self.data)[0], "1")

    def test_the_service_not_ending_in_time_is_infra(self):
        p = subprocess.Popen(["sleep", "60"])     # alive, never dumps
        try:
            (self.data / "server.pid").write_text(str(p.pid))
            (self.data / "startups.jsonl").write_text(json.dumps({"ts": time.time(), "pid": p.pid}) + "\n")
            (self.data / "final.json").write_text(json.dumps({"success": True, "finalized": False}))
            fin = self.hook(end_timeout=3)
        finally:
            p.kill(); p.wait()
        self.assertFalse(fin["success"]); self.assertEqual(fin["infra_error"], 1)
        txt, rw = grade(self.data)
        self.assertEqual((txt, rw["infra_error"]), ("0", 1))

    def test_an_episode_on_another_start_state_is_infra(self):
        self.episode(success=True, reason="success", instance_ok=False)
        fin = self.hook()
        self.assertEqual(fin["instance_mismatch"], 1)
        txt, rw = grade(self.data)
        self.assertEqual((txt, rw["infra_error"], rw["instance_mismatch"]), ("0", 1, 1))

    def test_too_few_threads_is_infra(self):
        self.episode(success=True, reason="success", threads_ok=0, blas_threads=2)
        self.hook()
        txt, rw = grade(self.data)
        self.assertEqual((txt, rw["infra_error"], rw["too_few_cpus"]), ("0", 1, 1))

    def test_a_give_up_is_kept(self):
        for reason, infra, want in (("sim_crashed", True, 1), ("resume_failed: replayed state differs", True, 1),
                                    ("sim_crashed_on_call", False, 0), ("instance_mismatch", True, 1)):
            with self.subTest(reason=reason):
                fin = {"success": False, "done": True, "reason": reason, "finalized": True, "gave_up": True, "resumes": 3,
                       **({"infra_error": 1} if infra else {})}
                (self.data / "final.json").write_text(json.dumps(fin))
                self.assertEqual(self.hook(), fin)          # end exits 2: the give-up is the verdict, untouched
                txt, rw = grade(self.data)
                self.assertEqual((txt, rw["infra_error"], rw["gave_up"]), ("0", want, 1))


class Grader(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp()); self.data = self.tmp / "data"; self.data.mkdir()

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_missing_unreadable_unfinalized_final_json_is_infra(self):
        txt, rw = grade(self.data)
        self.assertEqual((txt, rw["infra_error"], rw["missing_log"]), ("0", 1, 1))
        (self.data / "final.json").write_text("{not json")
        txt, rw = grade(self.data)
        self.assertEqual((txt, rw["infra_error"], rw["grader_error"]), ("0", 1, 1))
        (self.data / "final.json").write_text(json.dumps({"success": True, "finalized": False}))
        txt, rw = grade(self.data)
        self.assertEqual((txt, rw["infra_error"], rw["no_verdict"]), ("0", 1, 1))

    def test_an_old_replay_record_without_the_live_verdict_is_no_verdict(self):
        (self.data / "final.json").write_text(json.dumps({"success": True, "finalized": True, "replay_success": True,
                                                          "deterministic": True}))
        txt, rw = grade(self.data)
        self.assertEqual((txt, rw["infra_error"], rw["no_verdict"]), ("0", 1, 1))


class StartState(unittest.TestCase):
    """The service (real server.py on rcb_limited.py, stub simulator) refuses an episode on a scene that did not rebuild
    to the frozen instance's recorded hash: final.json instance_mismatch + an infrastructure give-up, 409 to the agent."""

    def test_instance_mismatch_gives_up_before_serving(self):
        sys.path.insert(0, str(LAYER))
        tmp = Path(tempfile.mkdtemp())
        srv, data = tmp / "srv", tmp / "data"
        srv.mkdir(); data.mkdir()
        shutil.copy(STD / "server.py", srv)
        for f in ("rcb_limited.py", "rcb1.py"):
            shutil.copy(LAYER / f, srv)
        shutil.copy(HERE / "stub_mujoco.py", srv / "mujoco.py")
        shutil.copy(HERE / "stub_rcb_dexjoco.py", srv / "rcb_dexjoco.py")
        (srv / "task_text.txt").write_text("stub\n")
        with socket.socket() as s:
            s.bind(("127.0.0.1", 0))
            port = s.getsockname()[1]
        log = open(tmp / "server.log", "w")
        proc = subprocess.Popen([sys.executable, "-B", str(srv / "server.py")], cwd=tmp, stdout=log, stderr=subprocess.STDOUT,
                                env={**os.environ, "RCB_DATA": str(data), "RCB_PORT": str(port), "RCB_TASK": "bimanual_photograph",
                                     "RCB_INSTANCE": str(srv / "none.npz"), "PYTHONDONTWRITEBYTECODE": "1",
                                     "STUB_INSTANCE_EXACT": "0"})
        try:
            code = None
            for _ in range(150):
                try:
                    with urllib.request.urlopen(f"http://127.0.0.1:{port}/status", timeout=10) as h:
                        code = h.status
                except urllib.error.HTTPError as e:
                    code = e.code
                except OSError:
                    time.sleep(0.2); continue
                break
            self.assertEqual(code, 409, (tmp / "server.log").read_text()[-2000:])
            fin = json.loads((data / "final.json").read_text())
            self.assertEqual((fin["instance_mismatch"], fin["infra_error"], fin["gave_up"], fin["finalized"]), (1, 1, True, True))
            self.assertFalse(fin["success"])
            ev = [json.loads(x) for x in (data / "episode.jsonl").read_text().splitlines() if x.strip()]
            self.assertFalse(any(e.get("ev") == "start" for e in ev), "an episode was started on the wrong scene")
            txt, rw = grade(data)
            self.assertEqual((txt, rw["infra_error"], rw["instance_mismatch"]), ("0", 1, 1))
        finally:
            proc.send_signal(signal.SIGKILL); proc.wait(); log.close()
            shutil.rmtree(tmp, ignore_errors=True)


if __name__ == "__main__":
    unittest.main(verbosity=1)
