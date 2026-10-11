"""The DexJoCo sim service (the real shared/standard/server.py on the real shared layer rcb_limited.py) with a stand-in
simulator, over HTTP; needs numpy, no MuJoCo.

    python3 scripts/dexjoco/tests/test_standard_server.py

- A camera that rides on a body of the scene which is not the robot's own (decided from the model: a body behind an
  object's joint, a mocap body, a camera aimed at one) gives images and depth and never a pose: no mount, no extrinsics
  in /spec, in meta["cameras"] or per frame, no /kinematics link. bimanual_photograph's `cam_pos_z` sits on the camera
  the hands pick up; its calibration was that object's live pose (review R3B-M1).
- One call returns at most max_frames_per_call images; a larger request is a 400 that executes nothing (R3B-M2).
- The committed facts (instances/<family>/facts.json `scene_cameras`, which the texts are written from) agree with the
  frozen instances' models.
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
DEXJOCO, LAYER = HERE.parent, HERE.parents[1] / "eai_standard"
sys.path.insert(0, str(LAYER))
import rcb1  # noqa: E402

sys.path.insert(0, str(HERE))
import stub_mujoco  # noqa: E402

SCENE = ["cam_pos_z", "drawer_cam", "target_cam", "aim_cam"]      # stub_mujoco's cameras that are not the robot's own
OWN = ["front", "handcam_rgb_right", "handcam_rgb_left"]


class Service(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.mkdtemp()
        srv, data = Path(cls.tmp, "srv"), Path(cls.tmp, "data")
        srv.mkdir()
        data.mkdir()
        shutil.copy(DEXJOCO / "shared" / "standard" / "server.py", srv)
        for f in ("rcb_limited.py", "rcb1.py"):
            shutil.copy(LAYER / f, srv)
        shutil.copy(HERE / "stub_mujoco.py", srv / "mujoco.py")
        shutil.copy(HERE / "stub_rcb_dexjoco.py", srv / "rcb_dexjoco.py")
        (srv / "task_text.txt").write_text("stub\n")
        with socket.socket() as s:
            s.bind(("127.0.0.1", 0))
            port = s.getsockname()[1]
        cls.url = f"http://127.0.0.1:{port}"
        cls.log = open(Path(cls.tmp, "server.log"), "w")
        cls.proc = subprocess.Popen(
            [sys.executable, "-B", str(srv / "server.py")], cwd=cls.tmp, stdout=cls.log, stderr=subprocess.STDOUT,
            env={**os.environ, "RCB_DATA": str(data), "RCB_PORT": str(port), "RCB_TASK": "bimanual_photograph",
                 "RCB_INSTANCE": str(srv / "none.npz"), "PYTHONDONTWRITEBYTECODE": "1"})
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
        return self.call("/status")[1]["control_steps"]

    def hold_rows(self, n: int) -> list:
        _, meta, _ = self.call("/observe", {"cameras": ["front"], "video": "none"})
        now, groups = np.array(meta["proprio"]["now"]), self.call("/spec")[1]["proprio_groups"]
        tcp = now[groups["tcp_target"][0]:][:14]
        hand = now[groups["hand_target"][0]:][:32]
        row = np.concatenate([tcp[:7], hand[:16], tcp[7:], hand[16:]])
        return [row.tolist()] * n

    # ------------------------------------------------------------------ R3B-M1: no pose of a camera on the scene
    def test_spec_gives_a_scene_camera_no_mount_and_no_pose(self):
        spec = self.call("/spec")[1]
        self.assertEqual(sorted(spec["cameras"]), sorted(OWN + SCENE))
        for c in SCENE:
            cam = spec["cameras"][c]
            self.assertEqual((cam["mount"]["type"], cam["mount"]["parent_link"]), ("link", None), c)
            self.assertFalse({"link_T_cam_cv", "extrinsic_cv", "cam2world_gl"} & set(cam["mount"]), c)
            self.assertNotIn("static", cam["mounted"], c)
            self.assertTrue(cam["rgb"] and cam["depth"] and cam["intrinsic_cv"], c)
        text = json.dumps(spec)
        for body in ("link_19", "drawer", "target"):                # the bodies they ride on are named nowhere
            self.assertNotIn(f'"{body}"', text)
        self.assertEqual(spec["cameras"]["front"]["mount"]["type"], "static")
        self.assertIn("extrinsic_cv", spec["cameras"]["front"]["mount"])
        hand = spec["cameras"]["handcam_rgb_left"]["mount"]
        self.assertEqual((hand["type"], hand["parent_link"]), ("link", "attachment_left"))
        self.assertIn("attachment_left", spec["kinematics"]["links"])

    def test_responses_give_a_scene_camera_images_and_depth_only(self):
        rows = self.hold_rows(5)
        code, meta, parts = self.call("/submit", {"type": "ee_pose", "actions": rows, "cameras": OWN + SCENE,
                                                  "video": "frames", "video_fps": 50, "depth": "frames"})
        self.assertEqual(code, 200, meta)
        n = parts["proprio"]["data"].shape[0]
        self.assertEqual(n, 7)                                       # the first frame, 5 control steps, the last
        obj = stub_mujoco.OBJECT_START
        for c in SCENE:
            info = meta["cameras"][c]
            self.assertIsNone(info["extrinsic_cv"], c)
            self.assertIsNone(info["cam2world_gl"], c)
            self.assertTrue(np.all(np.isnan(parts[f"extrinsic_cv/{c}"]["data"])), c)
            self.assertEqual(parts[f"frames/{c}"]["data"].shape[0], n, c)       # the images still come
            self.assertIn(f"last/{c}", parts)
            self.assertIn(f"depth_frames/{c}", parts)
        for c in OWN:
            self.assertTrue(np.all(np.isfinite(parts[f"extrinsic_cv/{c}"]["data"])), c)
            self.assertEqual(np.array(meta["cameras"][c]["cam2world_gl"]).shape, (4, 4), c)
        # nothing numeric in the response is the object's position (it started at OBJECT_START and moved in x)
        flat = np.concatenate([np.asarray(p["data"], np.float64).ravel() for k, p in parts.items()
                               if k.startswith("extrinsic_cv/") or k == "proprio"])
        for v in (obj[1], obj[2], obj[1] + 0.0, obj[2] + 0.06):
            self.assertFalse(np.any(np.isclose(flat, v, atol=1e-9)), v)
        self.assertNotIn(str(obj[1]), json.dumps(meta))

    def test_kinematics_has_no_link_of_the_scene(self):
        spec = self.call("/spec")[1]
        q = [0.0] * len(spec["kinematics"]["joint_names"])
        code, out, _ = self.call("/kinematics", {"op": "fk", "q": q})
        self.assertEqual(code, 200)
        self.assertFalse({"link_19", "drawer", "target"} & set(out["poses"]))
        code, out, _ = self.call("/kinematics", {"op": "fk", "q": q, "links": ["link_19"]})
        self.assertEqual(code, 400)

    # ------------------------------------------------------------------ R3B-M2: the images of one call are bounded
    def test_a_call_over_the_frame_budget_is_400_and_runs_nothing(self):
        spec = self.call("/spec")[1]
        limit = spec["max_frames_per_call"]
        self.assertEqual(limit, 1000)
        before = self.steps()
        too_many = [
            ("/observe", {"seconds": 30, "video_fps": 50, "cameras": ["front"]}),                    # 1502 frames
            ("/observe", {"seconds": 30, "video_fps": 50, "cameras": ["front"], "video": "none"}),   # recorded all the same
            ("/observe", {"seconds": 30, "cameras": OWN + ["cam_pos_z"]}),                           # 4 x 302
            ("/observe", {"seconds": 10, "video_fps": 50, "cameras": ["front"], "depth": "frames"}),  # 502 x 2
            ("/observe", {"seconds": 10, "video_fps": 50, "cameras": ["front"], "include_depth": True}),
            ("/submit", {"type": "ee_pose", "actions": self.hold_rows(500), "video_fps": 50, "cameras": OWN[:2]}),
            ("/submit", {"type": "ee_pose", "actions": self.hold_rows(20), "dt": 0.5, "video_fps": 50, "cameras": OWN[:2]}),
        ]
        for path, body in too_many:
            code, out, _ = self.call(path, body)
            self.assertEqual(code, 400, (path, {k: v for k, v in body.items() if k != "actions"}, out))
            self.assertIn("max_frames_per_call", out["error"])
        st = self.call("/status")[1]
        self.assertEqual((st["control_steps"], st["done"]), (before, False))

    def test_the_largest_default_requests_fit(self):
        """The default camera at the default video_fps for the longest watch and the longest chunk, and what the limit
        just allows: accepted, with exactly the frames the budget counted."""
        before = self.steps()
        code, meta, parts = self.call("/observe", {"seconds": 30, "video": "none"})
        self.assertEqual((code, parts["proprio"]["data"].shape[0]), (200, 302))
        code, meta, parts = self.call("/submit", {"type": "ee_pose", "actions": self.hold_rows(500), "video": "none"})
        self.assertEqual((code, parts["proprio"]["data"].shape[0]), (200, 102))
        code, meta, parts = self.call("/observe", {"seconds": 19.96, "video_fps": 50, "video": "none"})   # 2 + 998
        self.assertEqual((code, parts["proprio"]["data"].shape[0]), (200, 1000))
        self.assertEqual(self.steps(), before + 1500 + 500 + 998)

    def test_a_repeated_camera_is_one_camera(self):
        code, meta, parts = self.call("/observe", {"seconds": 1, "cameras": ["front"] * 1000, "video": "frames"})
        self.assertEqual(code, 200, meta)
        self.assertEqual(parts["frames/front"]["data"].shape[0], 12)             # 2 + 50 control steps / 5
        self.assertEqual(list(meta["cameras"]), ["front"])


class Facts(unittest.TestCase):
    def test_scene_cameras_of_the_facts_match_the_frozen_models(self):
        """The service's rule on each frozen instance's model arrays: a camera whose body (or a parent) is a mocap body
        or sits behind a joint that is not one of the robot's (the first 23 joints per arm) has no pose. The texts are
        written from facts.json `scene_cameras`; only bimanual_photograph has one (`cam_pos_z`)."""
        seen = {}
        for d in sorted((DEXJOCO / "instances").iterdir()):
            facts = json.loads((d / "facts.json").read_text())
            z = np.load(d / "instance.npz", allow_pickle=False)
            own = set(range(46 if d.name.startswith("bimanual_") else 23))
            self.assertTrue(own <= {int(j) for j in z["model__actuator_trnid"][:, 0]}, d.name)    # the robot's: all actuated
            parent, adr, num, mocap = (z[f"model__body_{k}"] for k in ("parentid", "jntadr", "jntnum", "mocapid"))

            def own_body(b: int) -> bool:
                while b > 0:
                    if mocap[b] >= 0 or any(j not in own for j in range(int(adr[b]), int(adr[b]) + int(num[b]))):
                        return False
                    b = int(parent[b])
                return True

            self.assertEqual(len(facts["cameras"]), len(z["model__cam_bodyid"]), d.name)
            scene = [c for i, c in enumerate(facts["cameras"])
                     if not all(own_body(int(b)) for b in [z["model__cam_bodyid"][i]]
                                + ([z["model__cam_targetbodyid"][i]] if int(z["model__cam_mode"][i]) in (3, 4) else []) if b >= 0)]
            self.assertEqual(facts["scene_cameras"], scene, d.name)
            seen[d.name] = scene
        self.assertEqual({k: v for k, v in seen.items() if v}, {"bimanual_photograph": ["cam_pos_z"]})
        self.assertEqual(len(seen), 11)


if __name__ == "__main__":
    unittest.main()
