"""The RoboCasa-series verifiers (shared/grade_standard.py, shared/grade_privileged.py; RoboCasa365 and RoboCasa-GR1
carry byte copies) on forged records, and the standard-mode sim service (images/robocasa/standard/server_casa.py, byte
copies in images/robocasa365/ and images/robocasa-gr1/) with its collect hook (shared/finalize.sh) on a stand-in tool
module: no simulator. The verdict is the live episode's (board 0151): no replay may run.

    python3 scripts/robocasa/tests/test_graders.py      # the service tests need numpy (skipped without it)
"""
import importlib.util
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

HERE = Path(__file__).resolve().parents[1]
ROOT = HERE.parents[1]
SHARED = HERE / "shared"
SERVER = ROOT / "images/robocasa/standard/server_casa.py"
HAVE_NUMPY = importlib.util.find_spec("numpy") is not None


def load(name: str, **paths):
    spec = importlib.util.spec_from_file_location(f"casa_{name}", SHARED / f"{name}.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    for k, v in paths.items():
        setattr(mod, k, v)
    return mod


def grade_dir(data: Path, log: Path) -> dict:
    load("grade_standard", DATA=str(data), LOG=str(log)).main()
    r = json.loads((log / "reward.json").read_text())
    assert (log / "reward.txt").read_text().strip() == str(r["success"])
    assert "replay_success" not in r and "deterministic" not in r, r
    assert (r["graded_by_live"], r["replays"]) == (1, 0), r
    return r


LIVE_OK = {"graded_by": "live", "replays": 0, "success": True, "live_success": True, "initial_success": False,
           "finalized": True, "done": True, "reason": "timeout", "video": True, "video_pending": False,
           "video_source": "render", "live_state_sha": "ab", "state_sha": "ab"}


class Standard(unittest.TestCase):
    def grade(self, final) -> dict:
        with tempfile.TemporaryDirectory() as d:
            data, log = Path(d, "data"), Path(d, "log")
            data.mkdir()
            if final is not None:
                (data / "final.json").write_text(final if isinstance(final, str) else json.dumps(final))
            return grade_dir(data, log)

    def test_live_success_passes(self):
        r = self.grade(LIVE_OK)
        self.assertEqual((r["success"], r["live_success"], r["infra_error"], r["grader_error"]), (1, 1, 0, 0))

    def test_live_failure_fails_and_is_no_infra(self):
        r = self.grade({**LIVE_OK, "success": False, "live_success": False})
        self.assertEqual((r["success"], r["live_success"], r["infra_error"]), (0, 0, 0))

    def test_solved_at_the_start_or_ended_on_a_simulator_error_fails(self):
        """The service's verdict ("success") carries the rule beyond the live check: not solved at the start, no
        simulator error; the grader never passes what the service failed."""
        r = self.grade({**LIVE_OK, "success": False, "initial_success": True})
        self.assertEqual((r["success"], r["live_success"], r["initial_success"], r["infra_error"]), (0, 1, 1, 0))
        r = self.grade({**LIVE_OK, "success": False, "reason": "error"})
        self.assertEqual((r["success"], r["sim_error"], r["infra_error"]), (0, 1, 0))

    def test_a_replay_record_never_passes(self):
        """A record without the live verdict (graded_by), or a replay's fields with the live check false, is 0."""
        old = {"success": True, "deterministic": True, "live_success": True, "replay_success": True, "finalized": True}
        self.assertEqual(self.grade(old)["success"], 0)
        r = self.grade({**LIVE_OK, "live_success": False, "replay_success": True, "deterministic": True})
        self.assertEqual((r["success"], r["infra_error"]), (0, 0))

    def test_give_up_after_crashes_between_calls_is_infra(self):
        for reason in ("sim_crashed", "resume_failed: journal shorter than the log", "instance_mismatch: x"):
            r = self.grade({"success": False, "done": True, "reason": reason, "finalized": True, "infra_error": 1})
            self.assertEqual((r["success"], r["infra_error"]), (0, 1), reason)

    def test_crashes_inside_the_agents_calls_are_the_agents(self):
        r = self.grade({"success": False, "done": True, "reason": "sim_crashed_on_call", "finalized": True})
        self.assertEqual((r["success"], r["infra_error"], r["sim_crashed_on_call"]), (0, 0, 1))

    def test_a_missing_video_changes_no_verdict(self):
        r = self.grade({**LIVE_OK, "video": False})
        self.assertEqual((r["success"], r["video_rendered"], r["infra_error"]), (1, 0, 0))

    def test_no_verdict_is_infra(self):
        r = self.grade(None)
        self.assertEqual((r["success"], r["infra_error"], r["missing_log"]), (0, 1, 1))
        r = self.grade('{"finalized": tr')
        self.assertEqual((r["success"], r["infra_error"], r["grader_error"]), (0, 1, 1))
        r = self.grade({"done": True, "reason": "timeout", "finalized": False})          # the hook ran out of time
        self.assertEqual((r["success"], r["infra_error"]), (0, 1))
        r = self.grade({**LIVE_OK, "success": None, "finalize_error": "OSError()"})
        self.assertEqual((r["success"], r["infra_error"], r["grader_error"]), (0, 1, 1))

    def test_evidence_fields_of_the_wrong_type_cost_no_verdict(self):
        """Before: int("many") raised and the trial had no reward file."""
        r = self.grade({**LIVE_OK, "control_steps": "many", "calls": [3], "elapsed_s": {"s": 1}, "final_reward": "1.0x"})
        self.assertEqual((r["success"], r["infra_error"], r["control_steps"], r["calls"], r["elapsed_s"]), (1, 0, 0, 0, 0.0))
        r = self.grade({**LIVE_OK, "success": False, "live_success": False, "control_steps": 7, "elapsed_s": 2.5})
        self.assertEqual((r["success"], r["infra_error"], r["control_steps"], r["elapsed_s"]), (0, 0, 7, 2.5))


# A stand-in for casa_tool: a 12-channel robot whose success is q[0] >= 0.5; it logs every Session it builds and every
# replay or render pass to $RCB_DATA, so the tests see that nothing replays the episode to grade it.
STUB = '''
import hashlib, json, os
import numpy as np
D = os.environ["RCB_DATA"]
def _note(name):
    with open(os.path.join(D, name), "a") as f: f.write("x")
def scene_option(): return None
class _Cam: id = 0
class _Model:
    cam_fovy = [45.0]
    def camera(self, name): return _Cam()
class _Data: cam_xmat = [np.eye(3).reshape(-1)]; cam_xpos = [np.zeros(3)]
class _Renderer:
    def __init__(self, model, h, w): self.h, self.w = h, w
    def enable_depth_rendering(self): pass
    def update_scene(self, data, camera=None, scene_option=None): pass
    def render(self): return np.zeros((self.h, self.w, 3), np.uint8)
class _MJ: Renderer = _Renderer
class Session:
    control_dt = 0.05; action_dim = 12; action_names = [f"c{i}" for i in range(12)]; proprio_layout = ["q0"]
    camera_views = {"cam": {"camera": "cam"}}
    action_spec = {"channels": [{"unit": "m", "kind": "delta", "index": i} for i in range(12)], "parts": {}, "frame": "base"}
    def __init__(self, instance, enable_render=True):
        _note("sessions")
        self.inst = {"text": "stub", "env_name": "Stub"}; self.model = _Model(); self.data = _Data(); self.mj = _MJ()
        self.instance_sha = os.environ.get("STUB_INSTANCE_SHA", "inst")
        self.lower = -np.ones(12); self.upper = np.ones(12); self.reset()
    def reset(self):
        self.q = np.zeros(12) + float(os.environ.get("STUB_START", "0")); self.targets = np.zeros(12)
        self.success = bool(self.q[0] >= 0.5); self.initial_success = self.success; self.reward = 0.0
    def step(self, a):
        a = np.asarray(a, float)
        if a[1] == 0.75: os._exit(3)                                  # a crash inside the agent's call
        if a[1] == 0.5: raise RuntimeError("unstable simulation")      # a simulator error raised by the agent's action
        self.q = self.q + a; self.targets = a.copy(); self.success = bool(self.q[0] >= 0.5); self.reward = float(self.q[0])
    def hold_targets(self): return np.zeros(12)
    def proprio(self): return self.q[:1]
    def check(self): return {"success": self.success, "reward": self.reward, "control_steps": 0}
    def state_sha(self): return hashlib.sha256(self.q.tobytes()).hexdigest()
    def replay(self, A): _note("replays"); raise AssertionError("no replay may grade the episode")
    def render_video(self, A, path, every=2, fps=10):
        _note("renders")
        if os.environ.get("STUB_VIDEO_FAIL"): raise RuntimeError("no OSMesa")
        self.reset()
        for row in A: self.step(row)
        open(path, "wb").write(b"mp4"); open(path[:-4] + ".last.png", "wb").write(b"png")
'''


def free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


@unittest.skipUnless(HAVE_NUMPY, "needs numpy (the service imports it)")
class Service(unittest.TestCase):
    """server_casa.py on the stand-in, then finalize.sh and grade_standard.py on what it wrote."""

    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="rcb-casa-live-"))
        self.srv, self.data = self.tmp / "srv", self.tmp / "data"
        self.srv.mkdir()
        self.data.mkdir()
        shutil.copy(SERVER, self.srv / "server_casa.py")
        shutil.copy(SHARED / "rcb1.py", self.srv / "rcb1.py")
        (self.srv / "stub_casa.py").write_text(STUB)
        self.port, self.proc, self.env = free_port(), None, {}

    def tearDown(self):
        if self.proc and self.proc.poll() is None:
            self.proc.kill()
            self.proc.wait()
        shutil.rmtree(self.tmp, ignore_errors=True)

    def start(self, **env) -> None:
        self.env.update(env)
        e = {**os.environ, "RCB_DATA": str(self.data), "RCB_PORT": str(self.port), "RCB_TOOL": "stub_casa",
             "RCB_INSTANCE": str(self.srv / "instance.npz"), "PYTHONPATH": str(self.srv), "PYTHONDONTWRITEBYTECODE": "1",
             **self.env}
        log = open(self.tmp / "log", "a")
        self.proc = subprocess.Popen([sys.executable, str(self.srv / "server_casa.py")], env=e, cwd=self.srv,
                                     stdout=log, stderr=log)

    def up(self, timeout: float = 30) -> None:
        t0 = time.time()
        while time.time() - t0 < timeout:
            self.assertIsNone(self.proc.poll(), (self.tmp / "log").read_text()[-2000:])
            try:
                urllib.request.urlopen(f"http://127.0.0.1:{self.port}/status", timeout=5).read()
                return
            except OSError:
                time.sleep(0.05)
        self.fail("the service did not come up")

    def submit(self, rows) -> int:
        body = json.dumps({"actions": rows, "video": "none", "cameras": ["cam"]}).encode()
        try:
            urllib.request.urlopen(urllib.request.Request(f"http://127.0.0.1:{self.port}/submit", data=body), timeout=30)
            return 200
        except urllib.error.HTTPError as e:
            return e.code
        except OSError:
            return -1

    def row(self, q0=0.0, flag=0.0):
        r = [0.0] * 12
        r[0], r[1] = q0, flag
        return r

    def final(self) -> dict:
        try:
            return json.loads((self.data / "final.json").read_text())
        except (OSError, ValueError):
            return {}

    def collect(self) -> dict:
        """The collect hook as Harbor runs it (finalize.sh in the sidecar), then the verifier."""
        out = subprocess.run(["sh", str(SHARED / "finalize.sh")], env={**os.environ, "RCB_DATA": str(self.data),
                             "RCB_COLLECT_WAIT_S": "60", "RCB_COLLECT_START_S": "20", "RCB_COLLECT_POLL_S": "0.2"},
                             capture_output=True, text=True, timeout=120)
        self.assertEqual(out.returncode, 0, out.stdout + out.stderr)
        self.assertFalse((self.data / "video.pending").exists(), out.stdout)
        return grade_dir(self.data, self.tmp / "log_verifier")

    def notes(self, name: str) -> int:
        try:
            return (self.data / name).stat().st_size
        except OSError:
            return 0

    def test_live_success_is_the_verdict_and_nothing_is_replayed(self):
        self.start()
        self.up()
        self.assertEqual(self.submit([self.row(0.3), self.row(0.3)]), 200)
        r = self.collect()
        fin = self.final()
        self.assertEqual((fin["graded_by"], fin["replays"], fin["success"], fin["live_success"]), ("live", 0, True, True))
        self.assertEqual((fin["video"], fin["video_pending"], fin["video_source"]), (True, False, "render"))
        self.assertEqual(fin["live_state_sha"], fin["state_sha"])
        self.assertEqual((r["success"], r["live_success"], r["infra_error"], r["video_rendered"]), (1, 1, 0, 1))
        self.assertEqual((self.notes("sessions"), self.notes("replays"), self.notes("renders")), (1, 0, 1))
        self.assertTrue((self.data / "replay.mp4").exists() and (self.data / "trajectory.npz").exists())

    def test_live_failure_is_0(self):
        self.start()
        self.up()
        self.assertEqual(self.submit([self.row(0.3)]), 200)
        r = self.collect()
        self.assertEqual((self.final()["success"], r["success"], r["infra_error"]), (False, 0, 0))
        self.assertEqual(self.notes("replays"), 0)

    def test_a_success_lost_before_the_end_is_0(self):
        self.start()
        self.up()
        self.assertEqual(self.submit([self.row(0.6), self.row(-0.3)]), 200)
        self.assertEqual(self.collect()["success"], 0)

    def test_a_failed_video_leaves_the_verdict(self):
        self.start(STUB_VIDEO_FAIL="1")
        self.up()
        self.assertEqual(self.submit([self.row(0.6)]), 200)
        r = self.collect()
        fin = self.final()
        self.assertEqual((fin["success"], fin["video"], fin["video_pending"]), (True, False, False))
        self.assertEqual((r["success"], r["infra_error"], r["video_rendered"]), (1, 0, 0))

    def test_a_simulator_error_from_the_agents_action_is_0_not_infra(self):
        self.start()
        self.up()
        self.assertEqual(self.submit([self.row(0.6)]), 200)
        self.assertEqual(self.submit([self.row(0.0, 0.5)]), 500)            # the episode ends on the error
        r = self.collect()
        fin = self.final()
        self.assertEqual((fin["reason"], fin["live_success"], fin["success"]), ("error", True, False))
        self.assertEqual((r["success"], r["sim_error"], r["infra_error"]), (0, 1, 0))

    def test_a_crash_inside_the_agents_call_is_0_not_infra(self):
        self.start(RCB_MAX_RESUMES="0")
        self.up()
        self.assertEqual(self.submit([self.row(0.6)]), 200)
        self.assertEqual(self.submit([self.row(0.0, 0.75)]), -1)            # the service died serving the call
        self.proc.wait(10)
        self.start()                                                       # compose's restart
        t0 = time.time()
        while time.time() - t0 < 30 and not self.final().get("finalized"):
            time.sleep(0.1)
        r = self.collect()
        self.assertEqual(self.final()["reason"], "sim_crashed_on_call")
        self.assertEqual((r["success"], r["infra_error"], r["sim_crashed_on_call"]), (0, 0, 1))
        self.assertEqual(self.notes("replays"), 0)

    def test_a_crash_between_calls_past_the_resumes_is_infra(self):
        self.start(RCB_MAX_RESUMES="0")
        self.up()
        self.assertEqual(self.submit([self.row(0.6)]), 200)
        self.proc.kill()                                                   # not inside a call
        self.proc.wait(10)
        self.start()
        t0 = time.time()
        while time.time() - t0 < 30 and not self.final().get("finalized"):
            time.sleep(0.1)
        r = self.collect()
        self.assertEqual(self.final()["reason"], "sim_crashed")
        self.assertEqual((r["success"], r["infra_error"]), (0, 1))

    def test_a_crash_resumes_the_same_episode_and_the_live_verdict_stands(self):
        self.start(RCB_MAX_RESUMES="2")
        self.up()
        self.assertEqual(self.submit([self.row(0.3)]), 200)
        self.proc.kill()
        self.proc.wait(10)
        self.start()
        self.up()
        self.assertEqual(self.submit([self.row(0.3)]), 200)                # q0 = 0.6 only if the first chunk was kept
        r = self.collect()
        self.assertEqual((r["success"], r["infra_error"]), (1, 0))
        self.assertEqual(self.notes("replays"), 0)

    def test_the_start_is_checked_against_the_frozen_instance(self):
        """RCB_START_SHA / RCB_INSTANCE_SHA from the generator; a scene solved at the start: instance_mismatch, infra,
        and the agent is never served (the port is not bound)."""
        import hashlib
        good = hashlib.sha256(bytes(8 * 12)).hexdigest()                  # the stand-in's start: q = 0
        cases = [({"RCB_START_SHA": good, "RCB_INSTANCE_SHA": "inst"}, False),
                 ({"RCB_START_SHA": "0" * 64}, True),
                 ({"RCB_INSTANCE_SHA": "other"}, True),
                 ({"STUB_START": "0.7"}, True)]
        for env, bad in cases:
            with self.subTest(env=env):
                self.tearDown()
                self.setUp()
                self.start(**env)
                if not bad:
                    self.up()
                    self.assertEqual(self.submit([self.row(0.6)]), 200)
                    self.assertEqual(self.collect()["success"], 1)
                    continue
                t0 = time.time()
                while time.time() - t0 < 30 and not self.final().get("finalized"):
                    time.sleep(0.1)
                fin = self.final()
                self.assertTrue(fin["reason"].startswith("instance_mismatch"), fin)
                self.assertEqual(self.submit([self.row(0.6)]), -1)         # never served
                r = self.collect()
                self.assertEqual((r["success"], r["infra_error"]), (0, 1))


class Privileged(unittest.TestCase):
    def test_a_verifier_that_cannot_import_its_tool_is_a_grader_error(self):
        """Before: the import failed inside the trajectory check and was booked as the agent's invalid trajectory."""
        self.assertNotIn("casa_tool", sys.modules)
        with tempfile.TemporaryDirectory() as d:
            traj, log = Path(d, "trajectory.npz"), Path(d, "log")
            traj.write_bytes(b"anything")
            load("grade_privileged", TRAJ=traj, LOG=log).main()
            r = json.loads((log / "reward.json").read_text())
            self.assertEqual((r["success"], r["grader_error"], r["invalid_trajectory"]), (0, 1, 0), r)
            self.assertIn("casa_tool", (log / "grader_error.txt").read_text())


if __name__ == "__main__":
    unittest.main()
