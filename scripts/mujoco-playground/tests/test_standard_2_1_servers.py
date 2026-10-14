"""Tests of the three eai-standard/2.1 MuJoCo sim services that are copied into tasks from images/ (server_mj.py:
DexToolBench and MuJoCo Playground; server_mw.py: MetaWorld+; server_casa.py: RoboCasa, RoboCasa365, RoboCasa-GR1)
against a stand-in tool module: no MuJoCo, no GPU. The services under test are the sources in images/.

    python3 scripts/mujoco-playground/tests/test_standard_2_1_servers.py          # needs numpy

Covers, for each service: a negative or non-numeric Content-Length is a 400 and the service stays up (read(-1) would
read without a bound); a camera named many times is rendered once, before the frame budget is counted; a port held by
another process at start is waited for, not a crash; the agent's clock (meta time_s / time_left_s) is not started by
the service's start or by a probe that only connects to the port, starts at the first request, and is not set back by
a resume (RoboTwin's service has these tests in scripts/robotwin/tests/test_standard_service.py); a camera's reported
pose is the viewpoint its image is rendered from, not MuJoCo's left-eye camera; the step limit cuts a chunk and the
response says how many of its rows ran; an episode end logged by a call that was lost with a crash is dropped by the
resume (board 0105: RoboCasa and MetaWorld+ kept it, so the agent lost the episode's rest). server_mj.py's optional reset capability
(PROTOCOL §4.5; DexToolBench standard grants 20): no /reset without a budget; with one, a reset restores the start state,
the budget is enforced (409 after it, after the agent's time), a crash resumes the current episode, and only the last
episode is graded.
"""
from __future__ import annotations

import json
import math
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
class _Cam:
    name = "cam"; id = 0; forward = (1.0, 0.0, 0.0); up = (0.0, 0.0, 1.0); pos = (0.5, 0.2, 1.0)
    def __init__(self, pos=(0.5, 0.2, 1.0)): self.pos = pos
# MuJoCo's two eye cameras (left, right) sit ipd/2 = 3.4 cm to either side of the viewpoint (data.cam_xpos), which is
# what the mono image is rendered from; looking along +x with +z up, the camera's left is +y.
class _Scene: camera = [_Cam((0.5, 0.234, 1.0)), _Cam((0.5, 0.166, 1.0))]
class _Model:
    ncam = 1; cam_mode = [0]; cam_bodyid = [0]; cam_fovy = [45.0]; body_jntnum = [0]; body_mocapid = [-1]; body_parentid = [0]
    cam_sensorsize = [[0.0, 0.0]]; cam_intrinsic = [[0.01, 0.01, 0.0, 0.0]]      # a camera given by its fovy (MuJoCo's defaults)
    if os.environ.get("STUB_SENSOR"):   # a camera given by its sensor: "focal_x focal_y principal_x principal_y sensor_x sensor_y fovy"
        _v = [float(x) for x in os.environ["STUB_SENSOR"].split()]
        cam_intrinsic = [_v[:4]]; cam_sensorsize = [_v[4:6]]; cam_fovy = [_v[6]]
    def camera(self, i): return _Cam()
class _Data: cam_xmat = [np.array([0.0, 0, -1, -1, 0, 0, 0, 1, 0])]; cam_xpos = [np.array([0.5, 0.2, 1.0])]   # x right = -y, y up = +z, looks along +x
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
    def reset(self): n = len(self.q); self.q = np.zeros(n); self.targets = np.zeros(n); self.n = 0
    def replay(self, A):
        self.reset()
        for row in A: self.step(row)
        return {"state_sha": self.state_sha(), "success": False, "steps": self.n}
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

    def wait_port(self, timeout: float = 30) -> None:
        """Ready, found the way a healthcheck may: by connecting to the port and sending nothing."""
        t0 = time.time()
        while time.time() - t0 < timeout:
            self.assertIsNone(self.proc.poll(), f"the service exited: {(self.tmp / 'log').read_text()[-2000:]}")
            try:
                socket.create_connection(("127.0.0.1", self.port), timeout=2).close()
                return
            except OSError:
                time.sleep(0.05)
        self.fail("the service did not come up")

    def meta(self) -> dict:
        req = urllib.request.Request(f"http://127.0.0.1:{self.port}/observe", data=json.dumps({"video": "none"}).encode())
        return rcb1.decode(urllib.request.urlopen(req, timeout=60).read())[0]

    def first_requests(self) -> list:
        try:
            ev = [json.loads(x) for x in (self.data / "episode.jsonl").read_text().splitlines() if x.strip()]
        except OSError:
            return []
        return [e for e in ev if e.get("ev") == "first_request"]

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

    def intrinsic(self) -> list:
        req = urllib.request.Request(f"http://127.0.0.1:{self.port}/observe", data=json.dumps({"video": "none"}).encode())
        return rcb1.decode(urllib.request.urlopen(req, timeout=60).read())[0]["cameras"]["cam"]["intrinsic_cv"]

    def test_intrinsics_follow_how_the_camera_is_defined(self):
        """MuJoCo renders a camera given by its sensor with the sensor's own extent in each direction, whatever the
        image's aspect, so fx != fy in a 320 x 240 image of ALOHA's 3.896 x 2.140 mm sensor (checked against CPU renders
        in the eai-mujoco image; the service reported fx = fy from the vertical field of view until 2026-10-13)."""
        if self.SERVER.name != "server_mj.py":
            self.skipTest("the MuJoCo service's rule (the MetaWorld+ and RoboCasa scenes have no sensor-defined camera)")
        self.start(); self.wait_up()
        K = self.intrinsic()                                         # fovy 45 deg: square pixels, the image centre
        f = 120 / math.tan(math.radians(45.0) / 2)
        for got, want in zip(sum(K, []), [f, 0, 160, 0, f, 120, 0, 0, 1]):
            self.assertAlmostEqual(got, want, places=6)
        self.proc.kill(); self.proc.wait(); self.log.close(); shutil.rmtree(self.data); self.data.mkdir()
        self.ENV = {**self.ENV, "STUB_SENSOR": "1.93e-3 1.93e-3 0 0 3896e-6 2140e-6 58.008"}     # ALOHA's overhead and wrist cameras
        self.start(); self.wait_up()
        K = self.intrinsic()
        for got, want in zip(sum(K, []), [158.5216, 0, 160, 0, 216.4486, 120, 0, 0, 1]):
            self.assertAlmostEqual(got, want, places=3)
        self.proc.kill(); self.proc.wait(); self.log.close(); shutil.rmtree(self.data); self.data.mkdir()
        self.ENV = {**self.ENV, "STUB_SENSOR": "2e-3 2.5e-3 0.4e-3 -0.25e-3 4e-3 3e-3 61.928"}    # with a principal-point offset
        self.start(); self.wait_up()
        K = self.intrinsic()                                         # fx = 320 * 2 / 4, fy = 240 * 2.5 / 3, cx = 160 - 320 * 0.4 / 4, cy = 120 + 240 * -0.25 / 3
        for got, want in zip(sum(K, []), [160, 0, 128, 0, 200, 100, 0, 0, 1]):
            self.assertAlmostEqual(got, want, places=6)

    def test_the_calibration_is_the_rendered_viewpoint(self):
        """cam2world_gl is the pose the mono image is rendered from (data.cam_xpos / cam_xmat of a model camera), not
        MuJoCo's left-eye camera scene.camera[0], 3.4 cm to its left: the services reported that one until #135
        (2026-10-10: server_mj.py, server_mw.py) and 2026-10-13 (server_casa.py, board 0093)."""
        self.start(); self.wait_up()
        T = self.meta()["cameras"]["cam"]["cam2world_gl"]
        want = [[0, 0, -1, 0.5], [-1, 0, 0, 0.2], [0, 1, 0, 1.0], [0, 0, 0, 1]]
        for got_row, want_row in zip(T, want):
            for got, w in zip(got_row, want_row):
                self.assertAlmostEqual(got, w, places=9)

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


    def test_the_agents_clock_starts_at_its_first_request_and_survives_a_resume(self):
        self.start(); self.wait_port()
        ready = time.time()
        time.sleep(2.0)                                              # up and idle: the harness is still being installed
        self.wait_port()                                             # a probe that connects again
        self.assertEqual(self.first_requests(), [], "the service's start or a connect without a request started the clock")
        t_req = time.time()
        spec = json.loads(urllib.request.urlopen(f"http://127.0.0.1:{self.port}/spec", timeout=5).read())   # the first request
        self.assertIn("first request", spec["budget"]["clock"])
        m0 = self.meta(); lag = time.time() - t_req
        self.assertLessEqual(m0["time_s"], lag + 0.1, f"time_s counts from the service's start ({time.time() - ready:.1f} s ago)")
        self.assertGreaterEqual(m0["time_left_s"], spec["budget"]["wall_clock_s"] - lag - 0.2)
        first = self.first_requests()
        self.assertEqual(len(first), 1)
        self.assertLessEqual(abs(first[0]["ts"] - t_req), lag + 0.1)
        time.sleep(1.5)
        self.proc.kill(); self.proc.wait(); self.log.close()         # a crash: compose restarts the container
        self.start(); self.wait_port()
        m1 = self.meta(); since = time.time() - t_req
        self.assertGreaterEqual(m1["time_s"], m0["time_s"] + 1.5, "the resume set the agent's clock back")
        self.assertGreaterEqual(m1["time_s"], since - lag - 0.3)
        self.assertLessEqual(m1["time_s"], since + 0.1)
        self.assertLessEqual(m1["time_left_s"], m0["time_left_s"] - 1.5)
        self.assertEqual(len(self.first_requests()), 1, "a resume logged a second first_request")
        self.assertEqual(self.wait_up()["calls"], 2)                 # the same episode: both observes are counted


    def chunk(self, rows: list):
        """A chunk in the service's own action type (server_mj.py: joint_position; the others: the tool's)."""
        if self.SERVER.name == "server_mj.py":
            return self.submit(rows)
        return self.post("/submit", {"dt": 0.02, "actions": rows, "video": "none"})

    def test_the_step_limit_cuts_a_chunk(self):
        self.ENV = {**self.ENV, "RCB_MAX_CONTROL_STEPS": "5"}
        self.start(); self.wait_up()
        w = 12 if self.ENV.get("STUB_CASA") else 2
        code, m = self.chunk([[0.1] * w] * 3)
        self.assertEqual((code, m["done"]), (200, False))
        code, m = self.chunk([[0.2] * w] * 4)                        # the limit falls on the chunk's second row
        self.assertEqual((code, m["done"], m["reason"]), (200, True, "step limit"))
        if self.SERVER.name != "server_mj.py":                       # server_mj.py reports the chunk's rows (unchanged)
            self.assertEqual(m["executed_rows"], 2)
        self.assertEqual(self.wait_up()["control_steps"], 5)
        self.assertEqual(self.chunk([[0.2] * w])[0], 409)

    def test_an_end_lost_with_its_call_is_dropped_on_resume(self):
        """A crash inside the call that hit the step limit, after its end was logged and before its checkpoint: the call
        is lost whole (the state goes back to the last checkpoint), so its end must go too, or the resumed episode is over
        at a state that never reached the limit (board 0105, RoboCasa / MetaWorld+)."""
        self.start(); self.wait_up()
        w = 12 if self.ENV.get("STUB_CASA") else 2
        self.assertEqual(self.chunk([[0.1] * w] * 3)[0], 200)
        n = self.wait_up()["control_steps"]
        self.proc.kill(); self.proc.wait(); self.log.close()
        with open(self.data / "episode.jsonl", "a") as f:             # what that crash leaves: call_begin, then the call's end
            for e in ({"ev": "call_begin", "path": "/submit", "call": 2},
                      {"ev": "end", "reason": "step limit", "control_steps": n + 4, "journal_rows": n + 4, "ep_start": 0, "resets": 0}):
                f.write(json.dumps({"ts": time.time(), **e}) + "\n")
        self.start(); st = self.wait_up()
        self.assertEqual((st["done"], st["control_steps"]), (False, n))
        self.assertEqual(self.chunk([[0.2] * w] * 2)[0], 200)        # the episode goes on

    # ---- server_mj.py's reset capability
    def post(self, path: str, meta: dict):
        req = urllib.request.Request(f"http://127.0.0.1:{self.port}{path}", data=json.dumps(meta).encode())
        try:
            m, parts = rcb1.decode(urllib.request.urlopen(req, timeout=60).read())
            return 200, m
        except urllib.error.HTTPError as e:
            return e.code, json.loads(e.read() or b"{}")

    def events(self) -> list:
        return [json.loads(x) for x in (self.data / "episode.jsonl").read_text().splitlines() if x.strip()]

    def submit(self, rows: list):
        return self.post("/submit", {"type": "joint_position", "dt": 0.02, "actions": rows, "video": "none"})

    def reset_case(self, budget: str | None) -> None:
        if self.SERVER.name != "server_mj.py":
            self.skipTest("the reset capability of the MuJoCo service (DexToolBench)")
        if budget is not None:
            self.ENV = {**self.ENV, "RCB_RESET_BUDGET": budget}
        self.start(); self.wait_up()

    def test_no_reset_without_a_budget(self):
        self.reset_case(None)
        spec = json.loads(urllib.request.urlopen(f"http://127.0.0.1:{self.port}/spec", timeout=5).read())
        self.assertEqual(spec["budget"]["reset"], 0); self.assertNotIn("reset", spec)
        self.assertEqual(self.post("/reset", {})[0], 404)
        code, m = self.submit([[0.5, 0.5]] * 3)
        self.assertEqual(code, 200); self.assertNotIn("episode", m); self.assertNotIn("resets_left", m)
        self.assertEqual(self.wait_up()["control_steps"], 3)

    def test_resets_restore_the_start_and_the_budget_is_enforced(self):
        self.reset_case("2")
        spec = json.loads(urllib.request.urlopen(f"http://127.0.0.1:{self.port}/spec", timeout=5).read())
        self.assertEqual(spec["budget"]["reset"], 2); self.assertIn("only the last episode", spec["reset"])
        start_sha = self.events()[0]["state_sha"]
        code, m = self.submit([[0.5, -0.5]] * 4)
        self.assertEqual((code, m["episode"], m["resets_left"], m["control_steps"]), (200, 1, 2, 4))
        self.assertEqual(self.post("/reset", {"cameras": ["cam"], "video": "frames", "include_depth": "x" == "y"})[0], 200)
        st = self.wait_up()
        self.assertEqual((st["episode"], st["resets_left"], st["control_steps"], st["control_steps_total"]), (2, 1, 0, 4))
        resets = [e for e in self.events() if e["ev"] == "reset"]
        self.assertEqual(len(resets), 1); self.assertEqual(resets[0]["state_sha"], start_sha)   # the start state again
        self.assertEqual([e["reason"] for e in self.events() if e["ev"] == "end"], ["reset"])  # the abandoned episode
        self.assertEqual(self.post("/reset", {"video": "gif"})[0], 400)          # a bad request changes nothing
        self.assertEqual(self.wait_up()["resets_left"], 1)
        self.assertEqual(self.submit([[0.2, 0.2]] * 3)[0], 200)
        code, m = self.post("/reset", {})
        self.assertEqual((code, m["episode"], m["resets_left"], m["control_steps_total"]), (200, 3, 0, 7))
        code, m = self.post("/reset", {})
        self.assertEqual(code, 409); self.assertEqual(m["error"], "reset budget exhausted")
        self.assertEqual(self.submit([[0.1, -0.1]] * 2)[0], 200)
        # a crash: compose restarts the container, the same (third) episode resumes from the journal
        self.proc.kill(); self.proc.wait(); self.log.close()
        self.start(); st = self.wait_up()
        self.assertEqual((st["episode"], st["resets_left"], st["control_steps"], st["control_steps_total"], st["done"]), (3, 0, 2, 9, False))
        self.assertEqual([e["ev"] for e in self.events()].count("resumed"), 1)
        self.assertEqual(self.submit([[0.1, -0.1]] * 1)[0], 200)
        # the agent's time is up: the collect hook's SIGUSR1 ends the episode; only the last one is graded
        os.kill(self.proc.pid, signal.SIGUSR1)
        t0 = time.time()
        while time.time() - t0 < 30 and not json.loads((self.data / "final.json").read_text()).get("video_done"):
            time.sleep(0.1)
        fin = json.loads((self.data / "final.json").read_text())
        self.assertEqual((fin["reset_budget"], fin["resets"], fin["episodes"], fin["control_steps"], fin["control_steps_total"]), (2, 2, 3, 3, 10))
        self.assertTrue(fin["deterministic"], fin)                   # the last episode's rows, replayed from the start
        import numpy as np
        self.assertEqual(np.load(self.data / "trajectory.npz")["actions"].shape, (3, 2))

    def test_no_reset_once_the_time_is_up(self):
        self.reset_case("5")
        self.assertEqual(self.submit([[0.5, 0.5]] * 2)[0], 200)
        os.kill(self.proc.pid, signal.SIGUSR1)
        t0 = time.time()
        while time.time() - t0 < 30 and not (self.data / "final.json").exists() or not json.loads((self.data / "final.json").read_text()).get("finalized"):
            time.sleep(0.1)
        code, m = self.post("/reset", {})
        self.assertEqual(code, 409); self.assertIn("time is up", m["error"])
        self.assertEqual(json.loads((self.data / "final.json").read_text())["resets"], 0)


class TestServerMj(ServerCase, unittest.TestCase):
    SERVER = ROOT / "images/mujoco/limited/server_mj.py"


class TestServerMw(ServerCase, unittest.TestCase):
    SERVER = ROOT / "images/metaworld/standard/server_mw.py"


class TestServerCasa(ServerCase, unittest.TestCase):
    SERVER = ROOT / "images/robocasa/standard/server_casa.py"
    ENV = {"STUB_CASA": "1"}


if __name__ == "__main__":
    unittest.main()
