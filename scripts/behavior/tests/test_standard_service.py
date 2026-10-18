"""The BEHAVIOR standard sim service on a stub simulator (stub_rcb_behavior.py): the real service code
(tasks/behavior-picking-up-trash-i00-standard/environment/sim/server.py), the real shared layer (scripts/eai_standard/)
and real HTTP requests; no Isaac, no GPU.

    python3 -m unittest discover -s scripts/behavior/tests          # needs numpy

What it pins down (board 0067): a malformed request is a 400 and executes nothing (PROTOCOL §4.6) instead of ending
the one episode as a simulator error; dt is never rounded; /spec states the runaway guard; a resume whose replayed
episode ends before the logged one neither crashes every restart nor books the divergence as the agent's failure.
"""
from __future__ import annotations

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

import numpy as np

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
SIM = ROOT / "tasks" / "behavior-picking-up-trash-i00-standard" / "environment" / "sim"
LAUNCHER = """import runpy, sys
import rcb_limited as L
_serve, PORT = L.serve, int(sys.argv[1])
L.serve = lambda svc, port=PORT: _serve(svc, port)        # the service binds :8000; the test needs a free port
runpy.run_path("server.py", run_name="__main__")
"""


def free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


class Service:
    def __init__(self, work: Path | None = None, **env):
        self.work = work or Path(tempfile.mkdtemp(prefix="rcb_behavior_svc_"))
        for f in ("server.py", "rcb_limited.py", "rcb1.py"):
            shutil.copy(SIM / f, self.work / f)
        shutil.copy(HERE / "stub_rcb_behavior.py", self.work / "rcb_behavior.py")
        (self.work / "launcher.py").write_text(LAUNCHER)
        self.out = self.work / "out"
        self.port = free_port()
        self.env = {**os.environ, "RCB_DATA": str(self.out), "RCB_INSTANCE": str(self.work / "instance.json"),
                    "PYTHONDONTWRITEBYTECODE": "1", **{k: str(v) for k, v in env.items()}}
        self.log = open(self.work / "server.log", "ab")
        self.p = subprocess.Popen([sys.executable, "launcher.py", str(self.port)], cwd=self.work, env=self.env,
                                  stdout=self.log, stderr=subprocess.STDOUT)

    def url(self, path: str) -> str:
        return f"http://127.0.0.1:{self.port}{path}"

    def wait(self, timeout: float = 60.0) -> dict:
        t0 = time.time()
        while time.time() - t0 < timeout:
            if self.p.poll() is not None:
                raise RuntimeError(f"service exited {self.p.returncode}: {(self.work / 'server.log').read_text()[-2000:]}")
            try:
                return json.load(urllib.request.urlopen(self.url("/spec"), timeout=5))
            except (urllib.error.URLError, ConnectionError, OSError):
                time.sleep(0.2)
        raise RuntimeError("service did not come up")

    def get(self, path: str) -> dict:
        return json.load(urllib.request.urlopen(self.url(path), timeout=30))

    def post(self, path: str, body: dict | str) -> tuple[int, dict]:
        """(status, JSON error body or {}): raw JSON, so nulls and wrong types reach the service as they are."""
        data = body.encode() if isinstance(body, str) else json.dumps(body).encode()
        req = urllib.request.Request(self.url(path), data=data, headers={"Content-Type": "application/json"})
        try:
            with urllib.request.urlopen(req, timeout=120) as r:
                r.read()
                return r.status, {}
        except urllib.error.HTTPError as e:
            try:
                return e.code, json.loads(e.read() or b"{}")
            except ValueError:
                return e.code, {}

    def kill(self) -> None:
        if self.p.poll() is None:
            self.p.send_signal(signal.SIGKILL)
        self.p.wait()
        self.log.close()

    def final(self) -> dict:
        return json.loads((self.out / "final.json").read_text())


ROW = [0.0] * 25
POSE = [0.3, 0.2, 1.0, 0, 0, 0, 1.0, 1.0, 0.3, -0.2, 1.0, 0, 0, 0, 1.0, 1.0]


def submit(**kw) -> dict:
    return {"type": "joint_position", "actions": [ROW, ROW], "dt": 0.1, "video": "frames", **kw}


class Requests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.s = Service()
        cls.spec = cls.s.wait()

    @classmethod
    def tearDownClass(cls):
        cls.s.kill()
        shutil.rmtree(cls.s.work, ignore_errors=True)

    def steps(self) -> int:
        return int(self.s.get("/status")["control_steps"])

    def refused(self, path: str, body) -> None:
        """A 400, nothing executed, the episode goes on."""
        before = self.steps()
        code, err = self.s.post(path, body)
        self.assertEqual(code, 400, (body, err))
        st = self.s.get("/status")
        self.assertEqual(int(st["control_steps"]), before, body)
        self.assertFalse(st["done"], (body, st))

    def test_spec_states_the_runaway_guard(self):
        self.assertEqual(self.spec["max_control_steps"], 200000)
        self.assertIsNone(self.spec["budget"]["steps"])
        self.assertIn("step_guard", self.spec["episode"])
        self.assertIn("200000 control steps", self.spec["episode"])

    def test_good_requests_run(self):
        before = self.steps()
        self.assertEqual(self.s.post("/submit", submit())[0], 200)                       # 2 rows x 0.1 s at 30 Hz
        self.assertEqual(self.steps(), before + 6)
        self.assertEqual(self.s.post("/submit", submit(dt=None, video_fps=None, note=None, cameras=None))[0], 200)   # null = not given
        self.assertEqual(self.steps(), before + 8)                                       # default dt 1/30 s
        self.assertEqual(self.s.post("/observe", {"seconds": 0.1, "video": "frames"})[0], 200)
        self.assertEqual(self.steps(), before + 11)
        self.assertEqual(self.s.post("/observe", {"seconds": None})[0], 200)             # the current frames, no physics
        self.assertEqual(self.steps(), before + 11)
        self.assertEqual(self.s.post("/submit", {"type": "ee_pose", "actions": [POSE], "video": "frames"})[0], 200)
        self.assertGreater(self.steps(), before + 11)

    def test_dt_must_be_a_finite_multiple_of_the_control_period(self):
        for dt in (0.25, 0.05, 1 / 12, 0.45, 0.0, -0.1, 0.6, "0.1", [0.1], {"s": 0.1}, True):
            self.refused("/submit", submit(dt=dt))
        for raw in ("NaN", "Infinity", "1e400", "1" + "0" * 400):                        # json.loads accepts all four
            self.refused("/submit", '{"type": "joint_position", "actions": [[%s]], "video": "frames", "dt": %s}'
                         % (", ".join(["0.0"] * 25), raw))

    def test_video_fps_note_cameras(self):
        for fps in (0, -5, 31, "5", [5], True):
            self.refused("/submit", submit(video_fps=fps))
            self.refused("/observe", {"seconds": 0.1, "video_fps": fps})
        for note in (5, ["a"], {"a": 1}, True):
            self.refused("/submit", submit(note=note))            # used to raise AFTER the chunk ran
        for cams in (5, "head", [1, 2], {"a": 1}):
            self.refused("/submit", submit(cameras=cams))
            self.refused("/observe", {"seconds": 0.1, "cameras": cams})
        for bad in ({"interpolate": "cubic"}, {"interpolate": None}, {"video": "gif"}, {"video": 3}, {"type": None}, {"type": "joint_delta"},
                    {"depth": "all"}, {"actions": [[0.0] * 24]}, {"actions": [0.0] * 25}, {"actions": []}, {"actions": None}):
            self.refused("/submit", submit(**bad))

    def test_observe_seconds(self):
        for sec in (-1, 31, "1", [1], True):
            self.refused("/observe", {"seconds": sec})
        for raw in ("NaN", "Infinity", "1e400"):
            self.refused("/observe", '{"seconds": %s}' % raw)

    def test_ee_pose_rows_are_checked_first(self):
        zero_q = POSE[:3] + [0, 0, 0, 0] + POSE[7:]
        far = [1e300] + POSE[1:]
        for row in (zero_q, far, POSE[:8] + [0.3, -0.2, 2e3] + POSE[11:]):
            self.refused("/submit", {"type": "ee_pose", "actions": [row], "video": "frames"})
        self.refused("/submit", {"type": "ee_pose", "actions": [POSE] * 51, "video": "frames"})


class NonFiniteIK(unittest.TestCase):
    def test_a_non_finite_ik_solution_moves_nothing(self):
        s = Service(STUB_IK="nan")
        try:
            s.wait()
            code, _ = s.post("/submit", {"type": "ee_pose", "actions": [POSE], "video": "frames"})
            self.assertEqual(code, 200)
            st = s.get("/status")
            self.assertFalse(st["done"], st)                      # the stub raises on a non-finite action: it never got one
            ev = [json.loads(l) for l in (s.out / "episode.jsonl").read_text().splitlines()]
            self.assertFalse([e for e in ev if e.get("ev") == "error"])
        finally:
            s.kill(); shutil.rmtree(s.work, ignore_errors=True)


class EpisodeEnd(unittest.TestCase):
    """(2026-10-17, board 0151) The end of the agent's phase: an episode still running gets the success rule's settle
    window on the live simulator (the service steps it on its request thread once the signal stopped the HTTP loop), and
    is judged there; a start that is not the frozen one; and a breakdown."""

    def end(self, s: Service) -> dict:
        s.p.send_signal(signal.SIGUSR1)                      # the collect hook's end (rcb_limited.py end)
        s.p.wait(timeout=60)
        return json.loads((s.out / "episode.json").read_text())

    @staticmethod
    def steps_log(s: Service) -> int:
        p = Path(s.env["STUB_LOG"])
        return len(p.read_text().splitlines()) if p.exists() else 0

    def test_a_goal_that_settles_after_the_agent_is_a_live_success(self):
        s = Service(STUB_GOAL_AT=40, STUB_LOG=str(Path(tempfile.mkdtemp()) / "steps.log"))   # the agent's rows end at 15 steps
        try:
            s.wait()
            self.assertEqual(s.post("/submit", submit(actions=[ROW] * 5))[0], 200)
            ep = self.end(s)
            self.assertTrue(ep["success"]); self.assertTrue(ep["settled_success"]); self.assertEqual(ep["reason"], "success")
            self.assertEqual(ep["settle_steps"], 25); self.assertEqual(self.steps_log(s), 40)   # held still on the live simulator
            self.assertEqual((ep["graded_by"], ep["replays"]), ("live", 0)); self.assertEqual(ep["pid"], s.p.pid)
            ev = [json.loads(l) for l in (s.out / "episode.jsonl").read_text().splitlines()]
            self.assertTrue([e for e in ev if e.get("ev") == "call_begin" and e.get("path") == "/settle"])   # the window is a call
            self.assertTrue([e for e in ev if e.get("ev") == "call_end" and e.get("path") == "/settle"])
            self.assertEqual(len(np.load(s.out / "trajectory.npz")["actions"]), 15)     # the agent's rows only
            self.assertEqual(ep["n_actions"], 15)
        finally:
            s.kill(); shutil.rmtree(s.work, ignore_errors=True)

    def test_a_window_that_never_closes_is_a_failure(self):
        s = Service(STUB_LOG=str(Path(tempfile.mkdtemp()) / "steps.log"))
        try:
            s.wait()
            self.assertEqual(s.post("/submit", submit(actions=[ROW] * 5))[0], 200)
            ep = self.end(s)
            self.assertFalse(ep["success"]); self.assertFalse(ep["settled_success"]); self.assertEqual(ep["reason"], "timeout")
            self.assertEqual(ep["settle_steps"], 150); self.assertEqual(self.steps_log(s), 165)
        finally:
            s.kill(); shutil.rmtree(s.work, ignore_errors=True)

    def test_a_fall_in_the_window_ends_it_as_a_fall(self):
        s = Service(STUB_FALL_AT=20)
        try:
            s.wait()
            self.assertEqual(s.post("/submit", submit(actions=[ROW] * 5))[0], 200)
            ep = self.end(s)
            self.assertFalse(ep["success"]); self.assertEqual(ep["reason"], "failure: the robot fell over"); self.assertEqual(ep["settle_steps"], 5)
        finally:
            s.kill(); shutil.rmtree(s.work, ignore_errors=True)

    def test_no_window_without_actions_or_after_the_end(self):
        s = Service(STUB_LOG=str(Path(tempfile.mkdtemp()) / "steps.log"))
        try:
            s.wait()
            ep = self.end(s)                                   # the agent never moved: nothing to settle
            self.assertFalse(ep["success"]); self.assertEqual(ep["settle_steps"], 0); self.assertEqual(self.steps_log(s), 0)
        finally:
            s.kill(); shutil.rmtree(s.work, ignore_errors=True)
        s = Service(STUB_GOAL_AT=4, STUB_LOG=str(Path(tempfile.mkdtemp()) / "steps.log"))
        try:
            s.wait()
            self.assertEqual(s.post("/submit", submit(actions=[ROW] * 5))[0], 200)
            ep = self.end(s)                                   # the episode ended in the call (success): no window
            self.assertTrue(ep["success"]); self.assertFalse(ep["settled_success"]); self.assertEqual(ep["settle_steps"], 0)
            self.assertEqual(self.steps_log(s), 4)
        finally:
            s.kill(); shutil.rmtree(s.work, ignore_errors=True)

    def test_a_start_that_is_not_the_frozen_one_gives_up_before_serving(self):
        s = Service(STUB_INSTANCE_MISMATCH=1)
        try:
            t0 = time.time(); fin = {}
            while time.time() - t0 < 60 and not fin.get("gave_up"):
                self.assertIsNone(s.p.poll(), "the service must give up and idle, not crash")
                time.sleep(0.2)
                try:
                    fin = s.final()
                except (OSError, ValueError):
                    pass
            self.assertTrue(fin["gave_up"]); self.assertEqual(fin["infra_error"], 1); self.assertTrue(fin["reason"].startswith("instance_mismatch"))
            ev = [json.loads(l) for l in (s.out / "episode.jsonl").read_text().splitlines()]
            self.assertFalse([e for e in ev if e.get("ev") == "start"])                    # the episode never started
        finally:
            s.kill(); shutil.rmtree(s.work, ignore_errors=True)

    def test_a_breakdown_ends_the_episode(self):
        s = Service(STUB_BREAKDOWN_AT=4)
        try:
            s.wait()
            self.assertEqual(s.post("/submit", submit(actions=[ROW] * 5))[0], 200)
            st = s.get("/status")
            self.assertTrue(st["done"]); self.assertTrue(st["reason"].startswith("failure: simulator breakdown"), st)
            fin = s.final()
            self.assertTrue(fin["reason"].startswith("failure: simulator breakdown")); self.assertEqual(fin["n_actions"], 4)
        finally:
            s.kill(); shutil.rmtree(s.work, ignore_errors=True)


class ResumeEndsEarly(unittest.TestCase):
    """OmniGibson rollouts are not bit-exact: on a resume the replayed episode may end before the logged rows are done."""

    def crash_then_resume(self, **env) -> Service:
        s = Service()
        s.wait()
        self.assertEqual(s.post("/submit", submit(actions=[ROW] * 5))[0], 200)       # 15 control steps, checkpointed
        self.assertEqual(int(s.get("/status")["control_steps"]), 15)
        s.kill()                                                                      # the crash
        return Service(work=s.work, **env)                                            # compose restarts the container

    def test_goal_holds_earlier_in_the_replay(self):
        s = self.crash_then_resume(STUB_GOAL_AT=7)
        try:
            s.wait()                                              # before: PrimitiveError on row 8, on every restart
            st = s.get("/status")
            self.assertTrue(st["done"]); self.assertEqual(st["reason"], "success")
            fin = s.final()
            self.assertTrue(fin["success"]); self.assertFalse(fin["finalized"]); self.assertEqual(fin["resumes"], 1)
            self.assertEqual(len(np.load(s.out / "trajectory.npz")["actions"]), 7)    # what ran, for the fresh replays
            self.assertEqual(s.post("/submit", submit())[0], 409)
        finally:
            s.kill(); shutil.rmtree(s.work, ignore_errors=True)

    def test_a_fall_only_the_replay_had_is_not_the_agents(self):
        s = self.crash_then_resume(STUB_FALL_AT=7)
        try:
            t0 = time.time(); fin = {}
            while time.time() - t0 < 60 and not fin.get("gave_up"):
                self.assertIsNone(s.p.poll(), "the service must give up and idle, not crash")
                time.sleep(0.2)
                try:
                    fin = s.final()
                except (OSError, ValueError):
                    pass
            self.assertTrue(fin["gave_up"]); self.assertTrue(fin["finalized"]); self.assertEqual(fin["infra_error"], 1)
            self.assertFalse(fin["success"]); self.assertTrue(fin["reason"].startswith("resume_failed"), fin["reason"])
            self.assertIsNone(s.p.poll())
        finally:
            s.kill(); shutil.rmtree(s.work, ignore_errors=True)

    def test_a_resume_drops_a_lost_calls_episode_record(self):
        s = Service()
        s.wait()
        self.assertEqual(s.post("/submit", submit(actions=[ROW] * 5))[0], 200)
        s.kill()
        (s.out / "episode.json").write_text(json.dumps({"success": True, "reason": "success"}))   # from a call the crash lost
        s = Service(work=s.work)
        try:
            s.wait()
            self.assertFalse(s.get("/status")["done"])
            self.assertFalse((s.out / "episode.json").exists())   # never taken for this episode's record by finalize.sh
        finally:
            s.kill(); shutil.rmtree(s.work, ignore_errors=True)

    def test_a_plain_resume_continues_the_episode(self):
        s = self.crash_then_resume()
        try:
            s.wait()
            st = s.get("/status")
            self.assertFalse(st["done"]); self.assertEqual(int(st["control_steps"]), 15); self.assertEqual(st["resumes"], 1)
            self.assertEqual(s.post("/submit", submit())[0], 200)
            self.assertEqual(int(s.get("/status")["control_steps"]), 21)
        finally:
            s.kill(); shutil.rmtree(s.work, ignore_errors=True)


if __name__ == "__main__":
    unittest.main()
