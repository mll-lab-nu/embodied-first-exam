"""The MyoSuite sim service (the real shared/standard/server.py on the real shared layer rcb_limited.py) with a stand-in
simulator, over HTTP; needs numpy, no MuJoCo, no MyoSuite.

    python3 scripts/myosuite/tests/test_standard_server.py

One call returns at most max_frames_per_call images (cameras x frames, per-frame depth counted again): a larger request
is a 400 that executes nothing; before 2026-10-10 a call had no bound, and one request within the documented ranges
could exhaust the sidecar's memory (review R3B-M2). The largest default requests fit, a camera named more than once is
one camera (POST /reset too), and a camera on a body of the scene still has no pose.

Live grading (owner, 2026-10-17, board 0151), the service with the real collect hook (shared/standard/finalize.sh, the
real rcb_limited.py `end`) and grader: the live episode's success is the verdict (graded_by live, replays 0) and no
replay runs; a failure is the agent's 0; a video render that fails changes nothing; a scene that does not start at the
frozen instance's recorded hash is refused at the start (instance_mismatch, infrastructure) before the agent is served.
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

import numpy as np

HERE = Path(__file__).resolve().parent
MYOSUITE, LAYER = HERE.parent, HERE.parents[1] / "eai_standard"
sys.path.insert(0, str(LAYER))
import rcb1  # noqa: E402

NU = 8
ROW = [0.0] * NU


class Service(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.mkdtemp()
        srv, data = Path(cls.tmp, "srv"), Path(cls.tmp, "data")
        srv.mkdir()
        data.mkdir()
        shutil.copy(MYOSUITE / "shared" / "standard" / "server.py", srv)
        for f in ("rcb_limited.py", "rcb1.py"):
            shutil.copy(LAYER / f, srv)
        shutil.copy(HERE / "stub_mujoco.py", srv / "mujoco.py")
        shutil.copy(HERE / "stub_rcb_myosuite.py", srv / "rcb_myosuite.py")
        np.savez(srv / "instance.npz", task="obj_hold", model__actuator_ctrlrange=np.zeros((NU, 2)))
        (srv / "task.json").write_text(json.dumps({"task_text": "stub", "default_cameras": ["hand_top"], "reference": None}))
        with socket.socket() as s:
            s.bind(("127.0.0.1", 0))
            port = s.getsockname()[1]
        cls.url = f"http://127.0.0.1:{port}"
        cls.log = open(Path(cls.tmp, "server.log"), "w")
        cls.proc = subprocess.Popen(
            [sys.executable, "-B", str(srv / "server.py")], cwd=cls.tmp, stdout=cls.log, stderr=subprocess.STDOUT,
            env={**os.environ, "RCB_DATA": str(data), "RCB_PORT": str(port), "RCB_INSTANCE": str(srv / "instance.npz"),
                 "RCB_RESET_BUDGET": "3", "PYTHONDONTWRITEBYTECODE": "1"})
        for _ in range(150):
            try:
                if cls.call("/status")[0] == 200:
                    return
            except OSError:
                time.sleep(0.2)
        cls.tearDownClass()
        raise RuntimeError("the service did not start: " + Path(cls.tmp, "server.log").read_text()[-3000:])

    @classmethod
    def tearDownClass(cls):
        cls.proc.send_signal(signal.SIGKILL)
        cls.proc.wait()
        cls.log.close()
        shutil.rmtree(cls.tmp, ignore_errors=True)

    @classmethod
    def call(cls, path: str, body: dict | None = None):
        """-> (status, meta or JSON, RCB1 parts or None)"""
        req = urllib.request.Request(cls.url + path, data=None if body is None else json.dumps(body).encode(),
                                     method="GET" if body is None else "POST")
        try:
            with urllib.request.urlopen(req, timeout=120) as h:
                code, raw = h.status, h.read()
        except urllib.error.HTTPError as e:
            code, raw = e.code, e.read()
        if raw[:4] == rcb1.MAGIC:
            return (code, *rcb1.decode(raw))
        return code, json.loads(raw), None

    def steps(self) -> int:
        return self.call("/status")[1]["control_steps_total"]

    def test_a_call_over_the_frame_budget_is_400_and_runs_nothing(self):
        spec = self.call("/spec")[1]
        self.assertEqual((spec["max_frames_per_call"], spec["control_hz"]), (1000, 50.0))
        before = self.call("/status")[1]
        too_many = [
            ("/observe", {"seconds": 30, "video_fps": 50, "cameras": ["hand_top"]}),                      # 1502 frames
            ("/observe", {"seconds": 30, "video_fps": 50, "video": "mp4"}),
            ("/observe", {"seconds": 30, "video_fps": 20, "cameras": ["hand_top", "front"]}),             # 2 x 602
            ("/observe", {"seconds": 10, "video_fps": 50, "depth": "frames"}),                            # 502 x 2
            ("/observe", {"seconds": 10, "video_fps": 50, "include_depth": True}),
            ("/submit", {"type": "muscle", "actions": [ROW] * 500, "video_fps": 50, "cameras": ["hand_top", "front"]}),
            ("/submit", {"type": "muscle", "actions": [ROW] * 20, "dt": 0.5, "video_fps": 50, "cameras": ["hand_top", "front"]}),
        ]
        for path, body in too_many:
            code, out, _ = self.call(path, body)
            self.assertEqual(code, 400, (path, {k: v for k, v in body.items() if k != "actions"}, out))
            self.assertIn("max_frames_per_call", out["error"])
        after = self.call("/status")[1]
        self.assertEqual((after["control_steps_total"], after["calls"], after["done"]),
                         (before["control_steps_total"], before["calls"], False))

    def test_the_largest_default_requests_fit(self):
        """The default camera at the default video_fps for the longest watch and the longest chunk, and what the limit
        just allows: accepted, with exactly the frames the budget counted."""
        before = self.steps()
        code, meta, parts = self.call("/observe", {"seconds": 30, "video": "frames"})
        self.assertEqual((code, parts["frames/hand_top"]["data"].shape[0]), (200, 302))
        code, meta, parts = self.call("/submit", {"type": "muscle", "actions": [ROW] * 500, "video": "frames"})
        self.assertEqual((code, parts["frames/hand_top"]["data"].shape[0]), (200, 102))
        code, meta, parts = self.call("/observe", {"seconds": 19.96, "video_fps": 50, "video": "frames"})   # 2 + 998
        self.assertEqual((code, parts["frames/hand_top"]["data"].shape[0]), (200, 1000))
        code, meta, parts = self.call("/observe", {"seconds": 30, "video_fps": 50, "video": "none",       # no video: 2 frames
                                                   "cameras": ["hand_top", "front"], "depth": "frames"})
        self.assertEqual((code, parts["proprio"]["data"].shape[0]), (200, 2))
        self.assertEqual(self.steps(), before + 1500 + 500 + 998 + 1500)

    def test_a_repeated_camera_is_one_camera_in_a_reset_too(self):
        code, meta, parts = self.call("/reset", {"cameras": ["front"] * 300 + ["hand_top"]})
        self.assertEqual(code, 200, meta)
        self.assertEqual((list(meta["cameras"]), parts["frames/front"]["data"].shape[0]), (["front", "hand_top"], 1))
        code, meta, parts = self.call("/observe", {"seconds": 1, "cameras": ["front"] * 1000, "video": "frames"})
        self.assertEqual((code, parts["frames/front"]["data"].shape[0]), (200, 12))                      # 2 + 50 / 5

    def test_a_camera_on_the_scene_has_no_pose(self):
        spec = self.call("/spec")[1]
        self.assertIsNone(spec["cameras"]["ball_cam"]["mount"]["parent_link"])
        self.assertEqual(spec["cameras"]["hand_top"]["mount"]["parent_link"], "mid")
        code, meta, parts = self.call("/observe", {"cameras": ["ball_cam", "hand_top"], "depth": True})
        self.assertIsNone(meta["cameras"]["ball_cam"]["extrinsic_cv"])
        self.assertTrue(np.all(np.isnan(parts["extrinsic_cv/ball_cam"]["data"])))
        self.assertTrue(np.all(np.isfinite(parts["extrinsic_cv/hand_top"]["data"])))
        self.assertIn("last/ball_cam", parts)


FAKE_VIDEO = """import json, os, sys, time
a = dict(zip(sys.argv[1::2], sys.argv[2::2]))
mode = os.environ.get("RCB_FAKE_VIDEO", "ok")
if mode == "crash":
    open(a["--out"], "wb").write(b"half a file")
    raise RuntimeError("the renderer failed")
if mode == "hang":
    open(a["--out"], "wb").write(b"half a file"); time.sleep(600)
open(a["--out"], "wb").write(b"mp4")
json.dump({"video": True, "frames": 2}, open(a["--result"], "w"))
"""


class LiveGrading(unittest.TestCase):
    """The service, then the collect hook, then the verifier, as a trial runs them (no MuJoCo, no replay)."""

    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.srv, self.data, self.bin = Path(self.tmp, "srv"), Path(self.tmp, "data"), Path(self.tmp, "bin")
        for d in (self.srv, self.data, self.bin):
            d.mkdir()
        for f in ("server.py", "finalize.sh", "grade.py"):
            shutil.copy(MYOSUITE / "shared" / "standard" / f, self.srv)
        for f in ("rcb_limited.py", "rcb1.py"):
            shutil.copy(LAYER / f, self.srv)
        shutil.copy(HERE / "stub_mujoco.py", self.srv / "mujoco.py")
        shutil.copy(HERE / "stub_rcb_myosuite.py", self.srv / "rcb_myosuite.py")
        (self.srv / "video.py").write_text(FAKE_VIDEO)
        # the hook calls `python`, as in the image: this interpreter (a wrapper, not a symlink: a venv's python finds
        # its packages by its own path)
        (self.bin / "python").write_text(f'#!/bin/sh\nexec "{sys.executable}" "$@"\n')
        (self.bin / "python").chmod(0o755)
        np.savez(self.srv / "instance.npz", task="obj_hold", model__actuator_ctrlrange=np.zeros((NU, 2)))
        (self.srv / "task.json").write_text(json.dumps({"task_text": "stub", "default_cameras": ["hand_top"], "reference": None}))
        self.proc = None

    def tearDown(self):
        if self.proc and self.proc.poll() is None:
            self.proc.send_signal(signal.SIGKILL)
        if self.proc:
            self.proc.wait()
            self.log.close()
        shutil.rmtree(self.tmp, ignore_errors=True)

    def env(self, **extra) -> dict:
        return {**os.environ, "RCB_DATA": str(self.data), "RCB_INSTANCE": str(self.srv / "instance.npz"),
                "RCB_SRV": str(self.srv), "PATH": f"{self.bin}:{os.environ.get('PATH', '')}",
                "PYTHONDONTWRITEBYTECODE": "1", **extra}

    def start(self, **extra) -> None:
        with socket.socket() as s:
            s.bind(("127.0.0.1", 0))
            port = s.getsockname()[1]
        self.url = f"http://127.0.0.1:{port}"
        self.log = open(Path(self.tmp, "server.log"), "w")
        self.proc = subprocess.Popen([sys.executable, "-B", str(self.srv / "server.py")], cwd=self.tmp, stdout=self.log,
                                     stderr=subprocess.STDOUT, env=self.env(RCB_PORT=str(port), RCB_RESET_BUDGET="3", **extra))
        for _ in range(150):
            try:
                if self.code("/status")[0] in (200, 409):
                    return
            except OSError:
                time.sleep(0.2)
        raise RuntimeError("the service did not start: " + Path(self.tmp, "server.log").read_text()[-3000:])

    def code(self, path: str, body: dict | None = None):
        req = urllib.request.Request(self.url + path, data=None if body is None else json.dumps(body).encode(),
                                     method="GET" if body is None else "POST")
        try:
            with urllib.request.urlopen(req, timeout=60) as h:
                return h.status, h.read()
        except urllib.error.HTTPError as e:
            return e.code, e.read()

    def collect_and_grade(self, **extra) -> tuple[dict, dict]:
        """The collect hook (it ends the service), then the verifier: -> (final.json, reward.json)."""
        r = subprocess.run(["sh", str(self.srv / "finalize.sh")], env=self.env(RCB_COLLECT_END_TIMEOUT_S="60", **extra),
                           capture_output=True, text=True, timeout=300)
        self.assertEqual(r.returncode, 0, r.stdout[-2000:] + r.stderr[-2000:])
        log = Path(self.tmp, "verifier")
        subprocess.run([sys.executable, str(self.srv / "grade.py")], check=True, capture_output=True,
                       env={**os.environ, "RCB_DATA": str(self.data), "RCB_VERIFIER_LOG_DIR": str(log)})
        self.assertFalse(Path(self.data, "REPLAYED").exists(), "a replay ran")
        self.assertFalse(list(self.data.glob("replay[0-9]*")), "a replay ran")
        final = json.loads(Path(self.data, "final.json").read_text())
        reward = json.loads(Path(log, "reward.json").read_text())
        self.assertEqual((log / "reward.txt").read_text().strip(), str(reward["success"]))
        for k in ("replay_success", "deterministic", "live_matches_replay"):
            self.assertNotIn(k, final)
            self.assertNotIn(k, reward)
        return final, reward

    def test_the_live_success_is_the_verdict_and_nothing_is_replayed(self):
        self.start()
        self.assertEqual(self.code("/submit", {"type": "muscle", "actions": [ROW] * 10, "cameras": [], "video": "none"})[0], 200)
        self.assertEqual(self.code("/submit", {"type": "muscle", "actions": [[99.0] + ROW[1:]], "cameras": [],
                                               "video": "none"})[0], 200)
        final, reward = self.collect_and_grade()
        self.assertEqual((final["success"], final["live_success"], final["graded_by"], final["replays"], final["finalized"],
                          final["video"], final["video_pending"], final["video_source"], final["reason"]),
                         (True, True, "live", 0, True, True, False, "render", "success"))
        self.assertEqual(final["state_sha"], final["live_sha"])
        self.assertEqual((reward["success"], reward["live_success"], reward["graded_by_live"], reward["replays"],
                          reward["infra_error"], reward["video_rendered"], reward["n_actions"]), (1, 1, 1, 0, 0, 1, 11))

    def test_a_live_failure_is_the_agents_0(self):
        self.start()
        self.assertEqual(self.code("/submit", {"type": "muscle", "actions": [ROW] * 10, "cameras": [], "video": "none"})[0], 200)
        final, reward = self.collect_and_grade()
        self.assertEqual((final["success"], final["reason"], final["graded_by"]), (False, "timeout", "live"))
        self.assertEqual((reward["success"], reward["infra_error"], reward["timeout"], reward["grader_error"]), (0, 0, 1, 0))

    def test_a_video_that_fails_or_runs_out_of_time_changes_nothing(self):
        for mode, budget in (("crash", "1800"), ("hang", "125")):
            with self.subTest(mode=mode):
                if self.proc:
                    self.tearDown(); self.setUp()
                self.start()
                self.code("/submit", {"type": "muscle", "actions": [[99.0] + ROW[1:]], "cameras": [], "video": "none"})
                final, reward = self.collect_and_grade(RCB_FAKE_VIDEO=mode, RCB_COLLECT_BUDGET_S=budget)
                self.assertEqual((final["success"], final["video"], final["video_pending"]), (True, False, False))
                self.assertFalse(Path(self.data, "replay.mp4").exists())      # a cut-off file is removed
                self.assertEqual((reward["success"], reward["infra_error"], reward["video_rendered"]), (1, 0, 0))

    def test_a_scene_that_is_not_the_frozen_instance_is_refused_at_the_start(self):
        self.start(RCB_STUB_START_MISMATCH="1")
        code, body = self.code("/status")
        self.assertEqual(code, 409, body)                                  # never served
        self.assertTrue(json.loads(body)["infra_error"])
        self.assertFalse(Path(self.data, "journal.f64").exists())
        final, reward = self.collect_and_grade()
        self.assertEqual((final["instance_mismatch"], final["infra_error"], final["gave_up"], final["success"]),
                         (1, 1, True, False))
        self.assertTrue(final["reason"].startswith("instance_mismatch"))
        self.assertEqual((reward["success"], reward["infra_error"], reward["instance_mismatch"]), (0, 1, 1))


    def test_the_render_pass_draws_the_episode_once_and_decides_nothing(self):
        """The real video.py on the stub simulator (a fake imageio): one pass, the frames, then it stops at the episode's
        end; a deadline keeps what it drew."""
        shutil.copy(MYOSUITE / "shared" / "standard" / "video.py", self.srv / "video.py")
        (self.srv / "imageio").mkdir()
        (self.srv / "imageio" / "__init__.py").write_text("")
        (self.srv / "imageio" / "v2.py").write_text(
            "class _W:\n    def __init__(self, p): self.f = open(p, 'w')\n"
            "    def append_data(self, a): self.f.write('frame\\n')\n    def close(self): self.f.close()\n"
            "def get_writer(path, **kw): return _W(path)\n")
        rows = np.zeros((40, NU)); rows[30, 0] = 99.0                   # the episode succeeds at row 31
        np.savez(self.data / "trajectory.npz", actions=rows)
        out, res = self.data / "replay.mp4", self.data / "video.json"
        r = subprocess.run([sys.executable, "-B", str(self.srv / "video.py"), "--instance", str(self.srv / "instance.npz"),
                            "--traj", str(self.data / "trajectory.npz"), "--out", str(out), "--result", str(res)],
                           env=self.env(), capture_output=True, text=True, timeout=120)
        self.assertEqual(r.returncode, 0, r.stderr[-2000:])
        got = json.loads(res.read_text())
        self.assertEqual((got["video"], got["rows"], got["frames"], got["cut_short"]), (True, 40, 32, False), got)
        self.assertEqual(out.read_text().count("frame"), 32)
        self.assertNotIn("success", got)
        self.assertFalse(Path(self.data, "REPLAYED").exists())


if __name__ == "__main__":
    unittest.main()
