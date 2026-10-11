"""The MyoSuite sim service (the real shared/standard/server.py on the real shared layer rcb_limited.py) with a stand-in
simulator, over HTTP; needs numpy, no MuJoCo, no MyoSuite.

    python3 scripts/myosuite/tests/test_standard_server.py

One call returns at most max_frames_per_call images (cameras x frames, per-frame depth counted again): a larger request
is a 400 that executes nothing; before 2026-10-10 a call had no bound, and one request within the documented ranges
could exhaust the sidecar's memory (review R3B-M2). The largest default requests fit, a camera named more than once is
one camera (POST /reset too), and a camera on a body of the scene still has no pose.
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


if __name__ == "__main__":
    unittest.main()
