"""Tests of the three eai-standard/2.1 MuJoCo sim services that are copied into tasks from images/ (server_mj.py:
DexToolBench and MuJoCo Playground; server_mw.py: MetaWorld+; server_casa.py: RoboCasa, RoboCasa365, RoboCasa-GR1)
against a stand-in tool module: no MuJoCo, no GPU. The services under test are the sources in images/.

    python3 scripts/mujoco-playground/tests/test_standard_2_1_servers.py          # needs numpy

Covers, for each service: a negative or non-numeric Content-Length is a 400 and the service stays up (read(-1) would
read without a bound); a camera named many times is rendered once, before the frame budget is counted; a port held by
another process at start is waited for, not a crash. RoboTwin's service has the same tests in
scripts/robotwin/tests/test_standard_service.py.
"""
from __future__ import annotations

import json
import os
import shutil
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
RCB1 = ROOT / "tasks/robotwin_2_0_stack_blocks_two-standard/environment/sim/rcb1.py"   # the codec the generators copy
sys.dont_write_bytecode = True
sys.path.insert(0, str(RCB1.parent))
import rcb1  # noqa: E402

# One stand-in for the three tool modules (rcb_<tool>.py, mw_tool.py, casa_tool.py): a 2-joint point robot, one camera.
STUB = '''
import hashlib, json, os
import numpy as np
CONTROL_DT = 0.02; N = 2; JOINT_NAMES = ACTION_NAMES = ["a", "b"]; CAMERAS = ("cam",); GOAL_TIMEOUT_STEPS = 0; MAX_STEPS = 3000
ACTION_TYPE = {"name": "ee_delta"}; CAMERA_VIEWS = {"cam": {"camera": "cam"}}; PROPRIO_LAYOUT = ["a_pos", "b_pos"]
def scene_option(): return None
class _Cam: name = "cam"; id = 0; forward = (1.0, 0.0, 0.0); up = (0.0, 0.0, 1.0); pos = (0.0, 0.0, 0.0)
class _Scene: camera = [_Cam(), _Cam()]
class _Model:
    ncam = 1; cam_mode = [0]; cam_bodyid = [0]; cam_fovy = [45.0]; body_jntnum = [0]; body_mocapid = [-1]; body_parentid = [0]
    def camera(self, i): return _Cam()
class _Data: cam_xmat = [np.eye(3).ravel()]; cam_xpos = [np.zeros(3)]
class _Renderer:
    scene = _Scene()
    def __init__(self, model, h, w): self.h, self.w, self.depth = h, w, False
    def enable_depth_rendering(self): self.depth = True
    def update_scene(self, data, camera=None, scene_option=None): pass
    def render(self):
        with open(os.path.join(os.environ["RCB_DATA"], "renders"), "a") as f: f.write("x")   # one byte per rendered image
        return np.zeros((self.h, self.w) if self.depth else (self.h, self.w, 3), np.float32 if self.depth else np.uint8)
class _MJ: Renderer = _Renderer
class Session:
    control_dt = CONTROL_DT; action_dim = 12; action_names = [f"c{i}" for i in range(12)]; proprio_layout = PROPRIO_LAYOUT
    camera_views = CAMERA_VIEWS; target_pos = [0.0, 0.0, 0.0]
    action_spec = {"channels": [{"unit": "m", "kind": "delta"}] * 12, "parts": {}, "frame": "base", "note": "", "delta_scale": {}}
    def __init__(self, instance, enable_render=True):
        self.inst = {"text": "stub"}; self.model = _Model(); self.data = _Data(); self.mj = _MJ(); self.n = 0
        n = 12 if os.environ.get("STUB_CASA") else N
        self.q = np.zeros(n); self.targets = np.zeros(n); self.lower = -np.ones(n); self.upper = np.ones(n)
    def step(self, tg): self.targets = np.asarray(tg, float).copy(); self.q = self.q + np.clip(self.targets - self.q, -.05, .05); self.n += 1
    def hold_targets(self): return self.targets.copy()
    def proprio(self): return self.q[:2]
    def state(self): return {"q": self.q, "qd": np.zeros(len(self.q)), "targets": self.targets}
    def state_sha(self): return hashlib.sha1(np.concatenate([self.q, self.targets]).tobytes()).hexdigest()[:16]
    def check(self): return {"success": False}
'''


def free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


class ServerCase:
    """The tests; the subclasses name the service (unittest collects only those)."""
    SERVER: Path
    ENV: dict = {}

    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="rcb-2-1-server-test-"))
        self.srv, self.data = self.tmp / "srv", self.tmp / "data"
        self.srv.mkdir(); self.data.mkdir()
        shutil.copy(self.SERVER, self.srv / "server.py"); shutil.copy(RCB1, self.srv / "rcb1.py")
        (self.srv / "stub_tool.py").write_text(STUB); (self.srv / "instance.json").write_text("{}")
        self.port = free_port(); self.proc = None

    def tearDown(self):
        if self.proc:
            self.proc.kill(); self.proc.wait(); self.log.close()
        shutil.rmtree(self.tmp, ignore_errors=True)

    def start(self) -> None:
        env = {**os.environ, "RCB_DATA": str(self.data), "RCB_PORT": str(self.port), "RCB_TOOL": "stub_tool",
               "RCB_INSTANCE": str(self.srv / "instance.json"), "PYTHONDONTWRITEBYTECODE": "1", **self.ENV}
        self.log = open(self.tmp / "log", "w")
        self.proc = subprocess.Popen([sys.executable, str(self.srv / "server.py")], env=env, cwd=self.srv, stdout=self.log, stderr=self.log)

    def wait_up(self, timeout: float = 30) -> dict:
        t0 = time.time()
        while time.time() - t0 < timeout:
            self.assertIsNone(self.proc.poll(), f"the service exited: {(self.tmp / 'log').read_text()[-2000:]}")
            try:
                return json.loads(urllib.request.urlopen(f"http://127.0.0.1:{self.port}/status", timeout=5).read())
            except OSError:
                time.sleep(0.05)
        self.fail("the service did not come up")

    def raw(self, head: bytes) -> bytes:
        """A request's head sent as raw bytes (urllib would not send such a header), the connection left open as a
        client that goes on sending would; -> the response's first line (a service that waits for a body: timeout)."""
        with socket.create_connection(("127.0.0.1", self.port), timeout=10) as s:
            s.sendall(head)
            return s.makefile("rb").readline()

    def observe(self, meta: dict):
        req = urllib.request.Request(f"http://127.0.0.1:{self.port}/observe", data=json.dumps(meta).encode())
        try:
            return 200, rcb1.decode(urllib.request.urlopen(req, timeout=60).read())[1]
        except urllib.error.HTTPError as e:
            return e.code, json.loads(e.read() or b"{}")

    def renders(self) -> int:
        try:
            return (self.data / "renders").stat().st_size
        except OSError:
            return 0

    def test_bad_content_length_is_a_400_and_the_service_stays_up(self):
        self.start(); self.wait_up()
        for value in (b"-1", b"-2147483648", b"abc"):
            line = self.raw(b"POST /observe HTTP/1.1\r\nHost: sim\r\nContent-Length: " + value + b"\r\n\r\n")
            self.assertIn(b" 400 ", line, (value, line))
        self.assertIsNone(self.proc.poll())
        self.assertEqual(self.wait_up()["calls"], 0)                 # refused before a call began: nothing was executed
        self.assertEqual(self.observe({"video": "none"})[0], 200)

    def test_a_repeated_camera_is_rendered_once(self):
        self.start(); self.wait_up()
        code, one = self.observe({"cameras": ["cam"], "video": "frames"})
        self.assertEqual(code, 200)
        per_call = self.renders()                                    # what one camera costs (frames + calibration)
        # 4000 names would be over the frame budget (3000) if repeats counted, and 4000 x 4000 frames if they were built
        code, many = self.observe({"cameras": ["cam"] * 4000, "video": "frames"})
        self.assertEqual(code, 200, many)
        self.assertEqual(self.renders() - per_call, per_call)
        self.assertEqual(sorted(many), sorted(one))
        self.assertEqual(many["frames/cam"]["data"].shape, one["frames/cam"]["data"].shape)
        self.assertEqual(many["frames/cam"]["data"].shape[0], 1)

    def test_json_true_is_not_a_number(self):
        self.start(); self.wait_up()
        code, err = self.observe({"video": "none", "seconds": True})   # float(True) is 1.0: it watched for 1 s
        self.assertEqual(code, 400, err)
        self.assertEqual(self.wait_up()["calls"], 0)

    def test_a_busy_port_is_waited_for(self):
        with socket.socket() as held:                                # e.g. a process of the agent, in the shared network namespace
            held.bind(("0.0.0.0", self.port)); held.listen(1)
            self.start()
            t0 = time.time()
            while time.time() - t0 < 30 and "waiting for it to be free" not in (self.tmp / "log").read_text():
                self.assertIsNone(self.proc.poll(), "the service died on the busy port (that would count as a crash)")
                time.sleep(0.05)
            self.assertIn("waiting for it to be free", (self.tmp / "log").read_text())
            self.assertIsNone(self.proc.poll())
        self.assertEqual(self.wait_up()["calls"], 0)


class TestServerMj(ServerCase, unittest.TestCase):
    SERVER = ROOT / "images/mujoco/limited/server_mj.py"


class TestServerMw(ServerCase, unittest.TestCase):
    SERVER = ROOT / "images/metaworld/standard/server_mw.py"


class TestServerCasa(ServerCase, unittest.TestCase):
    SERVER = ROOT / "images/robocasa/standard/server_casa.py"
    ENV = {"STUB_CASA": "1"}


if __name__ == "__main__":
    unittest.main()
