"""MuJoCo Playground and DexToolBench standard modes, graded by the live episode (owner, 2026-10-17, board 0151): no
grading replay. Stand-in simulators, no MuJoCo, no GPU; needs numpy.

    python3 scripts/mujoco-playground/tests/test_live_grading.py

1. images/mujoco/limited/server_mj.py (DexToolBench; Playground ALOHA / Panda) with the generated tests/grade.py of a
   DexToolBench and an ALOHA standard task: live success -> 1 (DexToolBench: every goal reached, reward = progress),
   live failure -> 0; the stand-in's replay() leaves a marker if anything calls it (nothing may); a video that fails
   leaves the verdict as it is; a start state that is not the recorded one (RCB_START_SHA, or the tooling's own start
   check raising) gives up before serving the agent (instance_mismatch, infra); crashes between calls past the resume
   budget are infra, crashes inside calls the agent's 0; a missing final.json is infra.
2. The quadrupeds' 2.2 collect hook (shared/standard/finalize.sh on the real rcb_limited.py) and grader: the live
   verdict, nothing replayed (a stand-in rcb_quadruped.py leaves a marker if called), the video pass's failure changes
   nothing, a give-up kept, the service not ending in time -> infra; the 2.2 service refuses a scene whose start does
   not hash to the instance's state_sha (instance_mismatch, infra).
3. The standard-realtime twin's grader (shared/realtime/grade.py) on the shared layer's final.json shapes, and its
   adapter (shared/realtime/server.py): no verify(), a start_sha.
"""
from __future__ import annotations

import ast
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
ROOT = HERE.parents[2]
PG = HERE.parent
sys.dont_write_bytecode = True
sys.path.insert(0, str(HERE))
from test_standard_2_1_servers import RCB1, STUB, free_port  # noqa: E402

LAYER = ROOT / "scripts" / "eai_standard"
DTB_TASK = ROOT / "tasks" / "dextoolbench_hammer_claw_hammer_swing_down-standard"
ALOHA_TASK = ROOT / "tasks" / "mujoco_playground_aloha_hand_over-standard"

# The stand-in tool, made a DexToolBench one (module name rcb_dtb: two goals, a goal reached by a step whose first target
# is 1.0) or a Playground one (check(): success when the first joint is past 0.5). replay() must never be called.
EXTRA = '''
GOAL_TIMEOUT_STEPS = 0
_Base = Session
class Session(_Base):
    def __init__(self, instance, enable_render=True):
        if os.environ.get("STUB_RAISE"):
            raise RuntimeError("initial state hash 000 != instance 111")
        super().__init__(instance, enable_render)
        self.goals = [[0.0] * 7, [0.0] * 7]; self.reached = 0
    def step(self, tg):
        super().step(tg)
        self.n_steps = getattr(self, "n_steps", 0) + 1
        if self.n_steps > int(os.environ.get("STUB_ERROR_AFTER") or 10**9): raise RuntimeError("the simulator blew up")
        if float(np.asarray(tg, float)[0]) == 1.0: self.reached = min(2, self.reached + 1)
    def reset(self): super().reset(); self.reached = 0
    def progress(self):
        return {"reached": self.reached, "n_goals": 2, "progress": self.reached / 2, "done": self.reached >= 2, "failed": False,
                "steps_on_goal": 0, "steps_left_on_goal": None, "goal_distance_m": None}
    def check(self): return {"success": bool(self.q[0] > 0.5), "box_to_target_m": 0.01, "right_holds": bool(self.q[0] > 0.5)}
    def replay(self, A):
        open(os.path.join(os.environ["RCB_DATA"], "REPLAY_CALLED"), "w").write("x")
        raise AssertionError("a grading replay ran")
    def render_video(self, A, path, every=2, fps=25):
        if os.environ.get("STUB_VIDEO") == "crash": raise RuntimeError("no GL")
        open(path, "wb").write(b"mp4")
        return {}
'''


def pybin(tmp: Path) -> Path:
    """A PATH entry whose `python` is this interpreter (the hooks call `python`)."""
    b = tmp / "bin"
    b.mkdir(exist_ok=True)
    if not (b / "python").exists():   # a wrapper, not a symlink: a venv's python finds its packages by its own path
        (b / "python").write_text(f'#!/bin/sh\nexec "{sys.executable}" "$@"\n')
        (b / "python").chmod(0o755)
    return b


def run_grade(script: Path, data: Path) -> tuple[str, dict]:
    logs = data.parent / "verifier"
    shutil.rmtree(logs, ignore_errors=True); logs.mkdir()
    subprocess.run([sys.executable, "-B", str(script)], check=True, capture_output=True,
                   env={**os.environ, "RCB_DATA": str(data), "RCB_VERIFIER_LOG_DIR": str(logs)})
    return f"{float((logs / 'reward.txt').read_text()):g}", json.loads((logs / "reward.json").read_text())   # "1", "0", "0.5"


class ServerMj(unittest.TestCase):
    TOOL = "rcb_dtb"

    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="rcb-live-mj-"))
        self.srv, self.data = self.tmp / "srv", self.tmp / "data"
        self.srv.mkdir(); self.data.mkdir()
        shutil.copy(ROOT / "images/mujoco/limited/server_mj.py", self.srv / "server_mj.py"); shutil.copy(RCB1, self.srv / "rcb1.py")
        (self.srv / f"{self.TOOL}.py").write_text(STUB + EXTRA)
        (self.srv / "instance.json").write_text("{}")
        self.port = free_port(); self.proc = None; self.env = {}

    def tearDown(self):
        self.stop()
        shutil.rmtree(self.tmp, ignore_errors=True)

    def stop(self):
        if self.proc:
            self.proc.kill(); self.proc.wait(); self.log.close(); self.proc = None

    def start(self, **env):
        self.env.update(env)
        e = {**os.environ, "RCB_DATA": str(self.data), "RCB_PORT": str(self.port), "RCB_TOOL": self.TOOL,
             "RCB_INSTANCE": str(self.srv / "instance.json"), "PYTHONDONTWRITEBYTECODE": "1", **self.env}
        self.log = open(self.tmp / "log", "a")
        self.proc = subprocess.Popen([sys.executable, str(self.srv / "server_mj.py")], env=e, cwd=self.srv, stdout=self.log, stderr=self.log)

    def up(self) -> bool:
        for _ in range(300):
            if self.proc.poll() is not None:
                return False
            try:
                urllib.request.urlopen(f"http://127.0.0.1:{self.port}/status", timeout=5).read(); return True
            except OSError:
                time.sleep(0.05)
        return False

    def submit(self, rows):
        req = urllib.request.Request(f"http://127.0.0.1:{self.port}/submit",
                                     data=json.dumps({"type": "joint_position", "dt": 0.02, "actions": rows, "video": "none"}).encode())
        try:
            return urllib.request.urlopen(req, timeout=60).status
        except urllib.error.HTTPError as e:
            return e.code

    def final(self) -> dict:
        try:
            return json.loads((self.data / "final.json").read_text())
        except (OSError, ValueError):
            return {}

    def end(self) -> dict:
        os.kill(self.proc.pid, signal.SIGUSR1)
        for _ in range(600):
            if self.final().get("video_done"):
                break
            time.sleep(0.05)
        return self.final()

    def grade(self, task: Path = DTB_TASK):
        return run_grade(task / "tests" / "grade.py", self.data)

    def assert_no_replay(self):
        self.assertFalse((self.data / "REPLAY_CALLED").exists(), "a grading replay ran")

    def test_live_success_is_graded_without_a_replay(self):
        self.start(); self.assertTrue(self.up())
        self.assertEqual(self.submit([[0.2, 0.2], [1.0, 0.0], [1.0, 0.0]]), 200)   # two goals: the episode ends
        fin = self.end()
        self.assert_no_replay()
        self.assertEqual((fin["graded_by"], fin["replays"], fin["finalized"], fin["reason"]), ("live", 0, True, "all goals reached"))
        self.assertTrue(fin["success"] and fin["live_success"]); self.assertEqual(fin["goals_reached"], 2)
        self.assertTrue(fin["video"]); self.assertFalse(fin["video_pending"]); self.assertEqual(fin["video_source"], "render")
        self.assertNotIn("deterministic", fin)
        txt, rw = self.grade()
        self.assertEqual((txt, rw["success"], rw["graded_by_live"], rw["replays"], rw["infra_error"], rw["progress"]),
                         ("1", 1, 1, 0, 0, 1.0))
        self.assertNotIn("deterministic", rw)

    def test_live_failure_is_0_with_its_progress(self):
        self.start(); self.assertTrue(self.up())
        self.assertEqual(self.submit([[1.0, 0.0], [0.3, 0.0]]), 200)                # one goal of two, then the time is up
        fin = self.end()
        self.assert_no_replay()
        self.assertEqual((fin["success"], fin["reason"], fin["goals_reached"]), (False, "timeout", 1))
        txt, rw = self.grade()
        self.assertEqual((txt, rw["success"], rw["infra_error"], rw["progress"]), ("0", 0, 0, 0.5))

    def test_a_failed_video_leaves_the_verdict(self):
        self.start(STUB_VIDEO="crash"); self.assertTrue(self.up())
        self.submit([[1.0, 0.0], [1.0, 0.0]])
        fin = self.end()
        self.assertTrue(fin["success"]); self.assertFalse(fin["video"]); self.assertFalse(fin["video_pending"])
        txt, rw = self.grade()
        self.assertEqual((txt, rw["infra_error"], rw["video_rendered"]), ("1", 0, 0))

    def test_another_start_state_is_refused_before_the_agent_is_served(self):
        self.start(RCB_START_SHA="not-the-start")   # (no port probe: another test on the host may hold a recycled port)
        for _ in range(200):
            if self.final().get("gave_up"):
                break
            time.sleep(0.05)
        fin = self.final()
        self.assertEqual((fin["reason"], fin["instance_mismatch"], fin["infra_error"], fin["finalized"], fin["video_done"]),
                         ("instance_mismatch", 1, 1, True, True))
        self.assertFalse(any(json.loads(x).get("ev") == "start" for x in (self.data / "episode.jsonl").read_text().splitlines()))
        txt, rw = self.grade()
        self.assertEqual((txt, rw["infra_error"], rw["instance_mismatch"]), ("0", 1, 1))
        # the agent's client gets the refusal at once (409 with the reason), not a silent port
        body = None
        for _ in range(100):
            try:
                urllib.request.urlopen(f"http://127.0.0.1:{self.port}/status", timeout=5)
            except urllib.error.HTTPError as e:
                body = json.loads(e.read()); break
            except OSError:
                time.sleep(0.1)
        self.assertEqual((body or {}).get("reason"), "instance_mismatch")
        self.assertTrue(body["gave_up"]); self.assertEqual(body["infra_error"], 1)

    def test_the_right_start_state_is_served(self):
        sha = __import__("hashlib").sha1(b"\0" * 32).hexdigest()[:16]    # the stand-in's start: q = targets = 0 (2 + 2 doubles)
        self.start(RCB_START_SHA=sha); self.assertTrue(self.up())
        self.assertEqual(json.loads((self.data / "episode.jsonl").read_text().splitlines()[0])["ev"], "start")

    def test_the_toolings_own_start_check_is_an_infra_give_up(self):
        self.start(STUB_RAISE="1")
        for _ in range(200):
            if self.final().get("gave_up"):
                break
            time.sleep(0.05)
        fin = self.final()
        self.assertEqual((fin["instance_mismatch"], fin["infra_error"]), (1, 1))
        self.assertFalse((self.data / "episode.jsonl").exists() and "\"start\"" in (self.data / "episode.jsonl").read_text())
        self.assertEqual(self.grade()[1]["infra_error"], 1)

    def crash_and_restart(self, in_call: bool) -> dict:
        self.start(RCB_MAX_RESUMES="0"); self.assertTrue(self.up())
        self.assertEqual(self.submit([[0.4, 0.0]]), 200)
        self.stop()                                                   # the service dies (between calls) ...
        if in_call:                                                   # ... or while serving a call
            with open(self.data / "episode.jsonl", "a") as f:
                f.write(json.dumps({"ts": time.time(), "ev": "call_begin", "path": "/submit", "call": 2}) + "\n")
        self.start()                                                  # compose restarts it: no resume left, a give-up
        for _ in range(200):
            if self.final().get("gave_up"):
                break
            time.sleep(0.05)
        return self.final()

    def test_crashes_between_calls_are_infra(self):
        fin = self.crash_and_restart(in_call=False)
        self.assertEqual((fin["reason"], fin.get("infra_error")), ("sim_crashed", 1))
        txt, rw = self.grade()
        self.assertEqual((txt, rw["infra_error"], rw["gave_up"]), ("0", 1, 1))

    def test_crashes_inside_calls_are_the_agents_0(self):
        fin = self.crash_and_restart(in_call=True)
        self.assertEqual(fin["reason"], "sim_crashed_on_call"); self.assertNotIn("infra_error", fin)
        txt, rw = self.grade()
        self.assertEqual((txt, rw["infra_error"], rw["sim_crashed_on_call"], rw["no_verdict"]), ("0", 0, 1, 0))

    def test_a_missing_or_unfinalized_final_json_is_infra(self):
        txt, rw = self.grade()
        self.assertEqual((txt, rw["infra_error"], rw["missing_log"]), ("0", 1, 1))
        (self.data / "final.json").write_text(json.dumps({"success": True, "finalized": False, "done": True}))
        self.assertEqual(self.grade()[1]["infra_error"], 1)
        # an old service's record (a replay's verdict, no graded_by) is no live verdict
        (self.data / "final.json").write_text(json.dumps({"success": True, "finalized": True, "deterministic": True}))
        self.assertEqual(self.grade()[1]["infra_error"], 1)


class ServerMjPlayground(ServerMj):
    """The same service on a Playground tool (ALOHA / Panda): the final state's check() is the verdict."""
    TOOL = "rcb_aloha"

    def test_live_success_is_graded_without_a_replay(self):
        self.start(); self.assertTrue(self.up())
        self.assertEqual(self.submit([[1.0, 1.0]] * 30), 200)
        fin = self.end()
        self.assert_no_replay()
        self.assertEqual((fin["graded_by"], fin["replays"], fin["success"], fin["live_success"], fin["right_holds"]),
                         ("live", 0, True, True, True))
        txt, rw = self.grade(ALOHA_TASK)
        self.assertEqual((txt, rw["success"], rw["infra_error"], rw["right_holds"]), ("1", 1, 0, 1))

    def test_live_failure_is_0_with_its_progress(self):
        self.start(); self.assertTrue(self.up())
        self.submit([[0.2, 0.0]] * 5)
        fin = self.end()
        self.assert_no_replay()
        self.assertFalse(fin["success"])
        txt, rw = self.grade(ALOHA_TASK)
        self.assertEqual((txt, rw["success"], rw["infra_error"]), ("0", 0, 0))

    def test_a_failed_video_leaves_the_verdict(self):
        self.start(STUB_VIDEO="crash"); self.assertTrue(self.up())
        self.submit([[1.0, 1.0]] * 30)
        fin = self.end()
        self.assertTrue(fin["success"]); self.assertFalse(fin["video"])
        self.assertEqual(self.grade(ALOHA_TASK)[0], "1")

    def test_a_simulator_error_is_never_a_success(self):
        """A sim error ends the episode; the state after it passes check() here, and is still not a success."""
        self.start(STUB_ERROR_AFTER="30"); self.assertTrue(self.up())
        self.assertEqual(self.submit([[1.0, 1.0]] * 30), 200)
        self.assertEqual(self.submit([[1.0, 1.0]] * 5), 500)
        fin = self.end()
        self.assert_no_replay()
        self.assertEqual((fin["reason"], fin["success"], fin["live_success"]), ("error", False, False))
        txt, rw = self.grade(ALOHA_TASK)
        self.assertEqual((txt, rw["success"], rw["sim_error"], rw["infra_error"]), ("0", 0, 1, 0))

    def grade(self, task: Path = ALOHA_TASK):
        return run_grade(task / "tests" / "grade.py", self.data)


# ------------------------------------------------------------------------------------------------ 2. quadrupeds, 2.2
STUB_QUAD = """import sys, pathlib, os
pathlib.Path(os.environ["RCB_SRV"], "TOOL_CALLED").write_text(" ".join(sys.argv[1:]))
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


class QuadrupedHook(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="rcb-live-quad-"))
        self.srv, self.data = self.tmp / "srv", self.tmp / "data"
        self.srv.mkdir(); self.data.mkdir()
        shutil.copy(PG / "shared/standard/finalize.sh", self.srv)
        for f in ("rcb_limited.py", "rcb1.py"):
            shutil.copy(LAYER / f, self.srv)
        (self.srv / "rcb_quadruped.py").write_text(STUB_QUAD)
        (self.srv / "video.py").write_text(STUB_VIDEO)
        self.path = f"{pybin(self.tmp)}:{os.environ.get('PATH', '')}"

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def episode(self, **kw):
        ep = {"success": False, "steps": 3, "calls": 2, "control_steps": 3, "physics_steps": 30, "elapsed_s": 12.0,
              "reason": "timeout", "done": True, "env": "Go1Getup", "n_actions": 3, "instance_ok": True, "sim_startups": 1,
              "resumes": 0, "resets": 0, "reset_budget": 10, "episodes": 1, "live_sha": "abc"}
        ep.update(kw)
        (self.data / "episode.json").write_text(json.dumps(ep))
        (self.data / "trajectory.npz").write_bytes(b"npz")
        p = subprocess.Popen(["true"]); p.wait()
        (self.data / "server.pid").write_text(str(p.pid))
        (self.data / "startups.jsonl").write_text(json.dumps({"ts": time.time(), "pid": p.pid}) + "\n")

    def hook(self, budget=300, end_timeout=20, **env):
        r = subprocess.run(["sh", str(self.srv / "finalize.sh")], capture_output=True, text=True, timeout=200,
                           env={**os.environ, "PATH": self.path, "RCB_DATA": str(self.data), "RCB_SRV": str(self.srv),
                                "RCB_TOOL": str(self.srv / "rcb_quadruped.py"), "RCB_INSTANCE": "/nonexistent.json",
                                "RCB_COLLECT_BUDGET_S": str(budget), "RCB_COLLECT_END_TIMEOUT_S": str(end_timeout), **env})
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertFalse((self.srv / "TOOL_CALLED").exists(), "the hook ran the tooling (a grading replay)")
        return json.loads((self.data / "final.json").read_text())

    def grade(self):
        return run_grade(PG / "shared/standard/grade.py", self.data)

    def test_live_success_is_1_and_nothing_is_replayed(self):
        self.episode(success=True, reason="success")
        fin = self.hook()
        self.assertEqual((fin["graded_by"], fin["replays"], fin["finalized"], fin["success"], fin["live_success"]),
                         ("live", 0, True, True, True))
        self.assertTrue(fin["video"]); self.assertFalse(fin["video_pending"])
        for k in ("replay_success", "deterministic", "live_matches_replay"):
            self.assertNotIn(k, fin)
        txt, rw = self.grade()
        self.assertEqual((txt, rw["success"], rw["graded_by_live"], rw["replays"], rw["infra_error"]), ("1", 1, 1, 0, 0))
        self.assertNotIn("deterministic", rw)

    def test_live_failure_and_a_fall_are_0(self):
        for reason in ("timeout", "fell", "horizon", "error"):
            with self.subTest(reason=reason):
                self.episode(success=False, reason=reason)
                self.hook()
                txt, rw = self.grade()
                self.assertEqual((txt, rw["infra_error"], rw["sim_error"]), ("0", 0, int(reason == "error")))
                (self.data / "final.json").unlink()

    def test_a_failed_video_changes_nothing(self):
        for mode in ("crash", "hang"):
            with self.subTest(mode=mode):
                self.episode(success=True, reason="success")
                fin = self.hook(budget=120 if mode == "hang" else 300, STUB_VIDEO=mode)   # hang: 45 s, then stopped
                self.assertTrue(fin["success"]); self.assertFalse(fin["video"]); self.assertFalse(fin["video_pending"])
                txt, rw = self.grade()
                self.assertEqual((txt, rw["infra_error"]), ("1", 0))
                (self.data / "final.json").unlink()

    def test_the_service_not_ending_in_time_is_infra(self):
        p = subprocess.Popen(["sleep", "60"])
        try:
            (self.data / "server.pid").write_text(str(p.pid))
            (self.data / "startups.jsonl").write_text(json.dumps({"ts": time.time(), "pid": p.pid}) + "\n")
            (self.data / "final.json").write_text(json.dumps({"success": True, "finalized": False}))
            fin = self.hook(end_timeout=3)
        finally:
            p.kill(); p.wait()
        self.assertEqual((fin["success"], fin["infra_error"]), (False, 1))
        self.assertEqual(self.grade()[1]["infra_error"], 1)

    def test_a_give_up_is_kept(self):
        for reason, infra, want in (("sim_crashed", True, 1), ("resume_failed: replayed state differs", True, 1),
                                    ("sim_crashed_on_call", False, 0), ("instance_mismatch", True, 1)):
            with self.subTest(reason=reason):
                fin = {"success": False, "done": True, "reason": reason, "finalized": True, "gave_up": True,
                       **({"infra_error": 1} if infra else {})}
                (self.data / "final.json").write_text(json.dumps(fin))
                self.assertEqual(self.hook(), fin)
                txt, rw = self.grade()
                self.assertEqual((txt, rw["infra_error"], rw["gave_up"]), ("0", want, 1))

    def test_missing_unreadable_unfinalized_final_json_is_infra(self):
        txt, rw = self.grade()
        self.assertEqual((txt, rw["infra_error"], rw["missing_log"]), ("0", 1, 1))
        (self.data / "final.json").write_text("{nope")
        self.assertEqual(self.grade()[1]["infra_error"], 1)
        (self.data / "final.json").write_text(json.dumps({"success": True, "finalized": True, "replay_success": True,
                                                          "deterministic": True}))   # an old replay record: no live verdict
        self.assertEqual(self.grade()[1]["infra_error"], 1)


STUB_Q_SERVICE = '''"""Stand-in rcb_quadruped for the 2.2 service's start check: a scene that does not start at the instance's hash."""
N = 12
class Session:
    def __init__(self, instance, enable_render=False, check_hash=True):
        self.inst = {"state_sha": "recorded"}; self.instance_ok = False
        if check_hash: raise RuntimeError("initial state hash built != instance recorded")
    def state_sha(self): return "built"
'''


class QuadrupedService(unittest.TestCase):
    def test_a_scene_off_the_frozen_start_gets_no_episode(self):
        tmp = Path(tempfile.mkdtemp(prefix="rcb-live-quadsvc-"))
        srv, data = tmp / "srv", tmp / "data"
        srv.mkdir(); data.mkdir()
        shutil.copy(PG / "shared/standard/server.py", srv)
        for f in ("rcb_limited.py", "rcb1.py"):
            shutil.copy(LAYER / f, srv)
        (srv / "rcb_quadruped.py").write_text(STUB_Q_SERVICE)
        (srv / "mujoco.py").write_text("")
        port = free_port()
        log = open(tmp / "log", "w")
        proc = subprocess.Popen([sys.executable, "-B", str(srv / "server.py")], cwd=tmp, stdout=log, stderr=subprocess.STDOUT,
                                env={**os.environ, "RCB_DATA": str(data), "RCB_PORT": str(port), "RCB_INSTANCE": str(srv / "i.json")})
        try:
            code = None
            for _ in range(200):
                try:
                    urllib.request.urlopen(f"http://127.0.0.1:{port}/status", timeout=5)
                    code = 200
                except urllib.error.HTTPError as e:
                    code = e.code
                except OSError:
                    time.sleep(0.05); continue
                break
            self.assertEqual(code, 409, (tmp / "log").read_text()[-2000:])
            fin = json.loads((data / "final.json").read_text())
            self.assertEqual((fin["instance_mismatch"], fin["infra_error"], fin["gave_up"], fin["finalized"]), (1, 1, True, True))
            txt, rw = run_grade(PG / "shared/standard/grade.py", data)
            self.assertEqual((txt, rw["infra_error"], rw["instance_mismatch"]), ("0", 1, 1))
        finally:
            proc.kill(); proc.wait(); log.close()
            shutil.rmtree(tmp, ignore_errors=True)


# ------------------------------------------------------------------------------------------------ 3. realtime
class Realtime(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="rcb-live-rt-")); self.data = self.tmp / "data"; self.data.mkdir()

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def grade(self, fin: dict | None):
        if fin is not None:
            (self.data / "final.json").write_text(json.dumps(fin))
        return run_grade(PG / "shared/realtime/grade.py", self.data)

    def test_the_layers_records(self):
        live = {"protocol": "eai-standard/2.3", "finalized": True, "graded_by": "live", "replays": 0, "done": True}
        cases = [
            ({**live, "success": True, "live_success": True, "reason": "success"}, "1", 0),
            ({**live, "success": False, "live_success": False, "reason": "failed"}, "0", 0),
            ({**live, "success": False, "live_success": True, "live_rule": False, "reason": "success"}, "0", 0),   # a live rule took it away
            ({"protocol": "eai-standard/2.3", "success": False, "done": True, "reason": "sim_crashed", "finalized": True, "infra_error": 1}, "0", 1),
            ({"protocol": "eai-standard/2.3", "success": False, "done": True, "reason": "sim_crashed_on_call", "finalized": True}, "0", 0),
            ({"protocol": "eai-standard/2.3", "success": False, "done": True, "finalized": True, "infra_error": 1,
              "reason": "instance_mismatch: the scene started at a, the frozen instance records b"}, "0", 1),
            ({"protocol": "eai-standard/2.3", "success": False, "live_success": True, "finalized": False}, "0", 1),
            ({**live, "success": False, "finalize_error": "boom"}, "0", 1),
        ]
        for fin, want, infra in cases:
            with self.subTest(reason=fin.get("reason"), fin=fin):
                txt, rw = self.grade(fin)
                self.assertEqual((txt, rw["infra_error"], rw["graded_by_live"], rw["replays"]), (want, infra, 1, 0))
                self.assertNotIn("deterministic", rw); self.assertNotIn("replay_success", rw)
        (self.data / "final.json").unlink()
        txt, rw = self.grade(None)
        self.assertEqual((txt, rw["infra_error"], rw["missing_log"]), ("0", 1, 1))

    def test_the_adapter_has_no_verify_and_a_start_sha(self):
        tree = ast.parse((PG / "shared/realtime/server.py").read_text())
        cls = next(n for n in tree.body if isinstance(n, ast.ClassDef) and n.name == "Quadruped")
        self.assertNotIn("verify", {f.name for f in cls.body if isinstance(f, ast.FunctionDef)})
        src = ast.unparse(cls)
        self.assertIn("self.start_sha", src); self.assertIn("check_hash=False", src)


if __name__ == "__main__":
    unittest.main(verbosity=1)
