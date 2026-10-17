"""MetaWorld+ standard mode, graded by the live episode (owner 2026-10-17, board 0150/0151): the sim service
(images/metaworld/standard/server_mw.py) and the standard grader (scripts/metaworldplus/shared/grade_standard.py) on a
stand-in tool module (no MuJoCo, no Meta-World, no GPU), and the generator's start-state hashes.

    python3 scripts/metaworldplus/tests/test_live_grading.py          # needs numpy

Covers: a live success is a 1 and a live failure a 0, with nothing replayed (the stand-in's replay() leaves a mark);
final.json says graded_by "live", replays 0, video_source "render" and has no replay_success / deterministic; a video
that fails, or a service that dies while rendering it, leaves the verdict as it was; a give-up after crashes that were
not all inside the agent's calls is infrastructure, one after crashes inside its calls is the agent's 0; a scene that
does not start at the frozen instance (instance hash or starting-state hash) is refused before the agent is served
(instance_mismatch, infrastructure); a missing, unreadable or unfinalized final.json is infrastructure; a simulator
error raised by the agent's actions is a 0. Meta-World's success check has no hold or settle window, so there is no
settle case. The generator's RCB_INSTANCE_SHA / RCB_START_SHA equal mw_tool's instance hash and the state hash of the
restored scene (SHA-256 of the instance's integration state), checked on the frozen instances with numpy.
"""
from __future__ import annotations

import hashlib
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

ROOT = Path(__file__).resolve().parents[3]
SERVER = ROOT / "images/metaworld/standard/server_mw.py"
GRADER = ROOT / "scripts/metaworldplus/shared/grade_standard.py"
RCB1 = ROOT / "scripts/metaworldplus/shared/rcb1.py"
sys.dont_write_bytecode = True

# A stand-in for mw_tool: a 4-channel point "hand"; success when its x has passed 0.3 (STUB_SUCCESS=0: never).
STUB = '''
import hashlib, os, time
import numpy as np
CONTROL_DT = 0.0125; N = 4; ACTION_NAMES = ["dx", "dy", "dz", "grip"]
ACTION_TYPE = {"name": "ee_delta", "dtype": "float64"}
CAMERA_VIEWS = {"front": {"lookat": (0.0, 0.6, 0.0), "distance": 1.5, "azimuth": 270.0, "elevation": -30.0}}
PROPRIO_LAYOUT = ["x", "y", "z", "grip"]
D = os.environ["RCB_DATA"]
def mark(name):
    with open(os.path.join(D, name), "a") as f: f.write("x")
class _Cam:
    forward = (0.0, 1.0, 0.0); up = (0.0, 0.0, 1.0)
    def __init__(self, x): self.pos = (x, 0.0, 1.0)
class _Scene: camera = [_Cam(-0.034), _Cam(0.034)]
class _Model:
    ncam = 0; vis = type("V", (), {"global_": type("G", (), {"fovy": 45.0})()})()
class _Renderer:
    scene = _Scene()
    def __init__(self, model, h, w): self.h, self.w, self.depth = h, w, False
    def enable_depth_rendering(self): self.depth = True
    def update_scene(self, data, camera=None): pass
    def render(self): return np.zeros((self.h, self.w) if self.depth else (self.h, self.w, 3), np.float32 if self.depth else np.uint8)
class _MJ:
    Renderer = _Renderer
    class MjvCamera:
        def __init__(self): self.lookat = np.zeros(3); self.distance = self.azimuth = self.elevation = 0.0
class Session:
    mj = _MJ()
    def __init__(self, instance, enable_render=False):
        self.inst = {"text": "stub", "env_id": "stub-v3"}; self.instance_sha = "a" * 64
        self.model = _Model(); self.data = None; self.target_pos = [0.0, 0.6, 0.1]
        self.lower = -np.ones(4); self.upper = np.ones(4)
        self.reset()
    def reset(self): self.q = np.zeros(4); self.targets = np.zeros(4); self.n = 0
    def step(self, a):
        a = np.clip(np.asarray(a, float), -1, 1); self.targets = a; self.q = self.q + 0.01 * a; self.n += 1
        if a[3] == 0.5: raise RuntimeError("simulation unstable")   # a simulator error after the state moved
    def hold_targets(self): return np.array([0.0, 0.0, 0.0, self.targets[3]])
    def proprio(self): return self.q.astype(np.float32)
    def state_sha(self): return hashlib.sha256(self.q.tobytes()).hexdigest()
    def check(self):
        ok = os.environ.get("STUB_SUCCESS", "1") == "1" and self.q[0] > 0.3
        return {"success": bool(ok), "reward": 10.0 if ok else 1.0, "control_steps": self.n}
    def replay(self, actions):
        mark("replayed")
        self.reset()
        for a in actions: self.step(a)
        return {"success": self.check()["success"], "state_sha": self.state_sha(), "final_reward": 0.0}
    def render_video(self, actions, path, every=2, fps=25, camera="front"):
        mark("rendered")
        if os.environ.get("STUB_VIDEO") == "fail": raise RuntimeError("the renderer failed")
        if os.environ.get("STUB_VIDEO") == "hang": time.sleep(3600)
        self.reset()
        for a in actions: self.step(a)
        open(path, "wb").write(b"mp4"); open(str(path)[:-4] + ".last.png", "wb").write(b"png")
'''
START_SHA = hashlib.sha256(bytes(4 * 8)).hexdigest()   # the stand-in's state hash at its start (four float64 zeros)


def free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


class Case(unittest.TestCase):
    ENV: dict = {}

    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="rcb-mw-live-test-"))
        self.srv, self.data, self.logs = self.tmp / "srv", self.tmp / "data", self.tmp / "verifier"
        for d in (self.srv, self.data, self.logs):
            d.mkdir()
        shutil.copy(SERVER, self.srv / "server.py"); shutil.copy(RCB1, self.srv / "rcb1.py")
        (self.srv / "stub_tool.py").write_text(STUB); (self.srv / "instance.npz").write_text("stub")
        self.port = free_port(); self.proc = None; self.env = dict(self.ENV)

    def tearDown(self):
        self.stop()
        shutil.rmtree(self.tmp, ignore_errors=True)

    # ---- the service
    def start(self, **env) -> None:
        self.env.update(env)
        e = {**os.environ, "RCB_DATA": str(self.data), "RCB_PORT": str(self.port), "RCB_TOOL": "stub_tool",
             "RCB_INSTANCE": str(self.srv / "instance.npz"), "PYTHONDONTWRITEBYTECODE": "1", "PYTHONPATH": str(self.srv),
             **self.env}
        self.log = open(self.tmp / "log", "a")
        self.proc = subprocess.Popen([sys.executable, str(self.srv / "server.py")], env=e, cwd=self.srv,
                                     stdout=self.log, stderr=self.log)

    def stop(self) -> None:
        if self.proc:
            self.proc.kill(); self.proc.wait(); self.log.close(); self.proc = None

    def wait_up(self, timeout: float = 30) -> dict:
        t0 = time.time()
        while time.time() - t0 < timeout:
            self.assertIsNone(self.proc.poll(), f"the service exited: {(self.tmp / 'log').read_text()[-2000:]}")
            try:
                return json.loads(urllib.request.urlopen(f"http://127.0.0.1:{self.port}/status", timeout=5).read())
            except OSError:
                time.sleep(0.05)
        self.fail("the service did not come up")

    def submit(self, rows: list) -> int:
        body = json.dumps({"dt": 0.0125, "actions": rows, "video": "none"}).encode()
        try:
            urllib.request.urlopen(urllib.request.Request(f"http://127.0.0.1:{self.port}/submit", data=body), timeout=60).read()
            return 200
        except urllib.error.HTTPError as e:
            return e.code

    def final(self) -> dict:
        try:
            return json.loads((self.data / "final.json").read_text())
        except (OSError, ValueError):
            return {}

    def wait_final(self, key: str = "video_done", timeout: float = 30) -> dict:
        t0 = time.time()
        while time.time() - t0 < timeout:
            if self.final().get(key):
                return self.final()
            time.sleep(0.05)
        self.fail(f"final.json never had {key}: {self.final()} {(self.tmp / 'log').read_text()[-2000:]}")

    def end_episode(self) -> dict:
        """What the collect hook does once the agent's container is stopped: SIGUSR1, then wait for video_done."""
        os.kill(self.proc.pid, signal.SIGUSR1)
        return self.wait_final()

    def episode(self, rows: int = 40) -> dict:
        self.start(); self.wait_up()
        self.assertEqual(self.submit([[1.0, 0.0, 0.0, -1.0]] * rows), 200)
        return self.end_episode()

    # ---- the grader
    def grade(self) -> dict:
        e = {**os.environ, "RCB_DATA": str(self.data), "RCB_VERIFIER_LOG_DIR": str(self.logs), "PYTHONDONTWRITEBYTECODE": "1"}
        subprocess.run([sys.executable, str(GRADER)], env=e, check=True, capture_output=True, timeout=60)
        out = json.loads((self.logs / "reward.json").read_text())
        self.assertEqual((self.logs / "reward.txt").read_text().strip(), str(out["success"]))
        self.assertTrue(all(isinstance(v, (int, float)) for v in out.values()), out)   # numbers only
        self.assertNotIn("replay_success", out); self.assertNotIn("deterministic", out)
        self.assertEqual((out["graded_by_live"], out["replays"]), (1, 0))
        return out

    def assert_live_verdict(self, fin: dict) -> None:
        self.assertEqual((fin["graded_by"], fin["replays"], fin["video_source"], fin["finalized"]), ("live", 0, "render", True))
        self.assertNotIn("replay_success", fin); self.assertNotIn("deterministic", fin)
        self.assertEqual(fin["state_sha"], fin["live_state_sha"])
        self.assertFalse((self.data / "replayed").exists(), "a grading replay ran")

    def events(self) -> list:
        return [json.loads(x) for x in (self.data / "episode.jsonl").read_text().splitlines() if x.strip()]


class TestLiveVerdict(Case):
    def test_a_live_success_is_a_1_and_nothing_is_replayed(self):
        fin = self.episode(40)                                       # x = 0.4 > 0.3
        self.assert_live_verdict(fin)
        self.assertEqual((fin["success"], fin["live_success"], fin["video"], fin["video_pending"]), (True, True, True, False))
        self.assertEqual((self.data / "rendered").read_text(), "x")  # one video pass, after the verdict
        self.assertTrue((self.data / "replay.mp4").exists() and (self.data / "trajectory.npz").exists())
        import numpy as np
        self.assertEqual(np.load(self.data / "trajectory.npz")["actions"].shape, (40, 4))
        out = self.grade()
        self.assertEqual((out["success"], out["live_success"], out["infra_error"], out["video_rendered"]), (1, 1, 0, 1))

    def test_a_live_failure_is_a_0(self):
        fin = self.episode(10)                                       # x = 0.1: not there
        self.assert_live_verdict(fin)
        self.assertEqual((fin["success"], fin["live_success"]), (False, False))
        out = self.grade()
        self.assertEqual((out["success"], out["infra_error"], out["grader_error"]), (0, 0, 0))

    def test_the_success_rule_is_the_tools_check_on_the_live_state(self):
        self.env["STUB_SUCCESS"] = "0"
        fin = self.episode(40)
        self.assertEqual((fin["success"], fin["live_success"]), (False, False))
        self.assertEqual(self.grade()["success"], 0)

    def test_a_failed_video_leaves_the_verdict(self):
        self.env["STUB_VIDEO"] = "fail"
        fin = self.episode(40)
        self.assert_live_verdict(fin)
        self.assertEqual((fin["success"], fin["video"], fin["video_done"], fin["video_pending"]), (True, False, True, False))
        self.assertTrue(any(e["ev"] == "video_error" for e in self.events()))
        out = self.grade()
        self.assertEqual((out["success"], out["infra_error"], out["video_rendered"]), (1, 0, 0))

    def test_a_service_that_dies_rendering_the_video_keeps_the_verdict(self):
        self.env["STUB_VIDEO"] = "hang"
        self.start(); self.wait_up()
        self.assertEqual(self.submit([[1.0, 0.0, 0.0, -1.0]] * 40), 200)
        os.kill(self.proc.pid, signal.SIGUSR1)
        fin = self.wait_final("finalized")
        self.assertEqual((fin["success"], fin["video_pending"], fin["video_done"]), (True, True, False))
        self.stop()                                                  # the process dies; compose restarts it
        self.start(); fin = self.wait_final()
        self.assert_live_verdict(fin)
        self.assertEqual((fin["success"], fin["video"], fin["video_pending"]), (True, False, False))
        out = self.grade()
        self.assertEqual((out["success"], out["infra_error"]), (1, 0))

    def test_a_simulator_error_after_a_success_is_a_0(self):
        """Review of #306: the check still reported the step before the error while the state was the failed step's."""
        self.start(); self.wait_up()
        self.assertEqual(self.submit([[1.0, 0.0, 0.0, -1.0]] * 40), 200)   # x = 0.4: a success so far
        self.assertEqual(self.submit([[1.0, 0.0, 0.0, 0.5]]), 500)          # the simulator raises: the episode ends
        fin = self.end_episode()
        self.assert_live_verdict(fin)
        self.assertEqual((fin["reason"], fin["success"], fin["live_success"]), ("error", False, False))
        out = self.grade()
        self.assertEqual((out["success"], out["sim_error"], out["infra_error"]), (0, 1, 0))

    def test_a_failed_finalize_on_disk_is_never_rewritten(self):
        self.start(); self.wait_up()
        self.assertEqual(self.submit([[1.0, 0.0, 0.0, -1.0]] * 5), 200)
        self.stop()
        rec = {"finalized": True, "finalize_error": "OSError()", "done": True, "reason": "timeout"}
        (self.data / "final.json").write_text(json.dumps(rec))
        self.start()
        t0 = time.time()
        while time.time() - t0 < 30 and not any(e["ev"] == "restart_refused" for e in self.events()):
            time.sleep(0.05)
        fin = self.final()
        self.assertEqual((fin["finalize_error"], fin["reason"], fin.get("infra_error")), ("OSError()", "timeout", None))
        out = self.grade()
        self.assertEqual((out["success"], out["infra_error"], out["grader_error"]), (0, 1, 1))

    def test_a_simulator_error_from_the_agents_actions_is_a_0(self):
        (self.data / "final.json").write_text(json.dumps({"finalized": True, "graded_by": "live", "replays": 0,
                                                          "success": False, "live_success": False, "reason": "error"}))
        out = self.grade()
        self.assertEqual((out["success"], out["sim_error"], out["infra_error"]), (0, 1, 0))


class TestCrashes(Case):
    ENV = {"RCB_MAX_RESUMES": "1"}

    def crash(self, in_call: bool) -> None:
        self.stop()
        if in_call:   # what a crash inside a call leaves: its call_begin is the last event
            with open(self.data / "episode.jsonl", "a") as f:
                f.write(json.dumps({"ts": time.time(), "ev": "call_begin", "path": "/submit", "call": 99}) + "\n")
        self.start()

    def test_a_give_up_after_crashes_between_calls_is_infrastructure(self):
        self.start(); self.wait_up()
        self.assertEqual(self.submit([[1.0, 0.0, 0.0, -1.0]] * 40), 200)
        self.crash(False); self.wait_up()                            # resumed once: the same episode
        self.crash(False)                                            # past RCB_MAX_RESUMES
        fin = self.wait_final()
        self.assertEqual((fin["reason"], fin["infra_error"], fin["success"]), ("sim_crashed", 1, False))
        self.assertFalse((self.data / "replayed").exists())
        out = self.grade()
        self.assertEqual((out["success"], out["infra_error"]), (0, 1))

    def test_a_give_up_after_crashes_inside_the_agents_calls_is_its_0(self):
        self.start(); self.wait_up()
        self.assertEqual(self.submit([[1.0, 0.0, 0.0, -1.0]] * 40), 200)
        self.crash(True); self.wait_up()
        self.crash(True)
        fin = self.wait_final()
        self.assertEqual(fin["reason"], "sim_crashed_on_call"); self.assertNotIn("infra_error", fin)
        out = self.grade()
        self.assertEqual((out["success"], out["infra_error"], out["sim_crashed_on_call"]), (0, 0, 1))

    def test_a_crash_resume_keeps_the_episode_and_its_live_verdict(self):
        self.ENV = {}
        self.start(); self.wait_up()
        self.assertEqual(self.submit([[1.0, 0.0, 0.0, -1.0]] * 40), 200)
        self.crash(False)
        self.assertEqual(self.wait_up()["control_steps"], 40)
        fin = self.end_episode()
        self.assert_live_verdict(fin)
        self.assertEqual(fin["success"], True)
        self.assertEqual(self.grade()["success"], 1)


class TestStartCheck(Case):
    def refused(self) -> dict:
        fin = self.wait_final()
        self.assertTrue(fin["reason"].startswith("instance_mismatch"), fin)
        self.assertEqual((fin["infra_error"], fin["finalized"], fin["success"]), (1, True, False))
        try:
            urllib.request.urlopen(f"http://127.0.0.1:{self.port}/status", timeout=2)
            self.fail("the agent was served")
        except OSError:
            pass
        self.assertFalse(any(e["ev"] == "start" for e in self.events()))
        out = self.grade()
        self.assertEqual((out["success"], out["infra_error"], out["instance_mismatch"]), (0, 1, 1))
        return fin

    def test_the_wrong_instance_is_refused_before_the_agent_is_served(self):
        self.start(RCB_INSTANCE_SHA="b" * 64, RCB_START_SHA=START_SHA)
        self.refused()

    def test_a_scene_not_at_the_frozen_start_is_refused(self):
        self.start(RCB_INSTANCE_SHA="a" * 64, RCB_START_SHA="0" * 64)
        self.refused()

    def test_the_frozen_start_is_served(self):
        self.start(RCB_INSTANCE_SHA="a" * 64, RCB_START_SHA=START_SHA)
        self.wait_up()
        self.assertEqual(self.events()[0]["state_sha"], START_SHA)


class TestGraderNoVerdict(Case):
    def test_a_missing_final_json_is_infrastructure(self):
        out = self.grade()
        self.assertEqual((out["success"], out["infra_error"], out["missing_log"]), (0, 1, 1))

    def test_an_unreadable_final_json_is_infrastructure(self):
        (self.data / "final.json").write_text('{"finalized": tr')
        out = self.grade()
        self.assertEqual((out["success"], out["infra_error"], out["grader_error"]), (0, 1, 1))

    def test_an_unfinalized_final_json_is_infrastructure(self):
        (self.data / "final.json").write_text(json.dumps({"finalized": False, "done": True, "reason": "timeout",
                                                          "success": True, "live_success": True}))
        out = self.grade()
        self.assertEqual((out["success"], out["infra_error"], out["no_verdict"]), (0, 1, 1))

    def test_a_failed_finalize_is_infrastructure(self):
        (self.data / "final.json").write_text(json.dumps({"finalized": True, "finalize_error": "OSError()"}))
        out = self.grade()
        self.assertEqual((out["success"], out["infra_error"], out["grader_error"]), (0, 1, 1))


class TestGeneratorStartShas(unittest.TestCase):
    def test_the_recorded_hashes_are_mw_tools(self):
        try:
            import numpy as np
        except ImportError:
            self.skipTest("numpy")
        sys.path.insert(0, str(ROOT / "scripts/metaworldplus"))
        sys.path.insert(0, str(ROOT / "scripts"))
        try:
            import generate
        except ImportError as exc:   # task_conventions needs Python 3.11 (tomllib)
            self.skipTest(f"the generator does not import here: {exc}")
        frozen = sorted((ROOT / "scripts/metaworldplus/frozen").glob("*/instance.npz"))
        self.assertEqual(len(frozen), 50)
        for p in frozen:
            got = generate.start_shas(p)
            with np.load(p, allow_pickle=False) as z:
                self.assertEqual(got["instance"], str(z["instance_sha"]), p)
                self.assertEqual(got["start"], hashlib.sha256(z["integration"].tobytes()).hexdigest(), p)


if __name__ == "__main__":
    unittest.main()
