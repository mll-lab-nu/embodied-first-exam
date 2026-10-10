"""Tests of the RoboTwin standard-mode service (environment/sim/server.py) and both graders against a stand-in
simulator (stub_sim.py): no SAPIEN, no GPU. The service and graders under test are the template tasks' shipped files.

    python3 -m unittest discover -s scripts/robotwin/tests          # needs numpy

Covers: malformed requests are 400s that leave the episode alive (a zero-row chunk, dt / video_fps / cameras of the
wrong type or not finite); the calibration in every response is the current one (the wrist camera moves); the agent's
clock starts at its first request; the verdict is written before the videos, survives a restart, and is graded without
`finalized`; a failed verification replay and an instance that does not rebuild are infra_error, not the agent's 0.
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

ROOT = Path(__file__).resolve().parents[3]
STD = ROOT / "tasks" / "robotwin_2_0_stack_blocks_two-standard"
PRIV = ROOT / "tasks" / "robotwin_2_0_stack_blocks_two-privileged"
HERE = Path(__file__).resolve().parent
sys.dont_write_bytecode = True
sys.path.insert(0, str(STD / "environment"))
import rcb1  # noqa: E402

LIVE_STUB = '''
class LiveRecorder:
    def __init__(self, *a, **k): pass
    def open(self): pass
    def tick(self): pass
    def set_label(self, *a): pass
    def end_call(self): pass
    def close(self): return {}
    def render_from_trajectory(self, acts): return {"live_video": False}
'''


def free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


class Service:
    """The shipped server.py + rcb1.py in a scratch directory next to the stand-in simulator, as a child process."""

    def __init__(self, tmp: Path, **env):
        self.srv, self.data = tmp / "srv", tmp / "data"
        if not self.srv.exists():
            self.srv.mkdir(); self.data.mkdir()
            for f in ("server.py", "rcb1.py", "instance.json"):
                shutil.copy(STD / "environment/sim" / f, self.srv / f)
            shutil.copy(HERE / "stub_sim.py", self.srv / "rcb_traj.py")
            (self.srv / "rcb_live.py").write_text(LIVE_STUB)
        self.env = {k: str(v) for k, v in env.items()}
        self.port = free_port(); self.proc = None

    def start(self, wait: bool = True):
        env = {**os.environ, "RCB_DATA": str(self.data), "RCB_PORT": str(self.port), "PYTHONDONTWRITEBYTECODE": "1", **self.env}
        self.proc = subprocess.Popen([sys.executable, str(self.srv / "server.py")], env=env, cwd=self.srv,
                                     stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        t0 = time.time()
        while wait and time.time() - t0 < 30:
            if (self.data / "server.pid").exists() and (self.data / "server.pid").read_text() == str(self.proc.pid):
                return self
            if self.proc.poll() is not None:
                raise RuntimeError(f"service exited with {self.proc.returncode}")
            time.sleep(0.05)
        if wait:
            raise RuntimeError("service did not come up")
        return self

    def stop(self):
        if self.proc and self.proc.poll() is None:
            self.proc.kill(); self.proc.wait()

    def get(self, path: str) -> dict:
        return json.loads(urllib.request.urlopen(f"http://127.0.0.1:{self.port}{path}", timeout=30).read())

    def post(self, path: str, meta: dict, actions=None, raw: bytes | None = None):
        """-> (status, meta or error dict, parts)."""
        parts = [] if actions is None else [rcb1.array_part("actions", np.asarray(actions, dtype=np.float32))]
        body = raw if raw is not None else rcb1.encode(meta, parts)
        req = urllib.request.Request(f"http://127.0.0.1:{self.port}{path}", data=body, headers={"Content-Type": "application/x-rcb1"})
        try:
            r = urllib.request.urlopen(req, timeout=60)
        except urllib.error.HTTPError as e:
            return e.code, json.loads(e.read() or b"{}"), {}
        m, p = rcb1.decode(r.read())
        return 200, m, p

    def final(self) -> dict:
        try:
            return json.loads((self.data / "final.json").read_text())
        except (OSError, ValueError):
            return {}

    def wait_final(self, key: str = "finalized", timeout: float = 30) -> dict:
        t0 = time.time()
        while time.time() - t0 < timeout:
            d = self.final()
            if d.get(key) not in (None, False):
                return d
            time.sleep(0.05)
        raise AssertionError(f"final.json never had {key}: {self.final()}")

    def grade(self) -> dict:
        log = self.data.parent / "verifier"
        shutil.rmtree(log, ignore_errors=True)
        subprocess.run([sys.executable, str(STD / "tests/grade.py")], check=True, capture_output=True,
                       env={**os.environ, "RCB_DATA": str(self.data), "RCB_VERIFIER_LOG_DIR": str(log)})
        out = json.loads((log / "reward.json").read_text())
        assert (log / "reward.txt").read_text().strip() == str(out["success"])
        assert all(isinstance(v, (int, float)) and not isinstance(v, bool) for v in out.values()), out
        for k in ("success", "deterministic", "infra_error", "sim_error", "grader_error"):
            assert k in out, (k, out)
        return out


def row(j1: float = 0.0, grip: float = 0.0) -> list:
    r = [0.0] * 14
    r[0], r[6] = j1, grip
    return r


class ServiceCase(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="rcb-robotwin-test-")); self.svc = None

    def tearDown(self):
        if self.svc:
            self.svc.stop()
        shutil.rmtree(self.tmp, ignore_errors=True)

    def service(self, **env) -> Service:
        self.svc = Service(self.tmp, **env).start()
        return self.svc


class Requests(ServiceCase):
    def test_malformed_requests_are_400_and_the_episode_goes_on(self):
        s = self.service()
        good = {"type": "joint_position", "dt": 0.02, "video": "none"}
        bad = [
            ({**good}, np.zeros((0, 14))),                              # a zero-row chunk (a slice past the end)
            ({**good, "dt": None}, [row()]), ({**good, "dt": "fast"}, [row()]), ({**good, "dt": [0.02]}, [row()]),
            ({**good, "dt": float("inf")}, [row()]), ({**good, "dt": float("nan")}, [row()]),
            ({**good, "video_fps": float("inf")}, [row()]), ({**good, "video_fps": None}, [row()]),
            ({**good, "cameras": 3}, [row()]), ({**good, "cameras": {"a": 1}}, [row()]),
            ({**good, "type": ["joint_position"]}, [row()]), ({**good, "type": None}, [row()]),
            ({**good, "interpolate": 5}, [row()]), ({**good, "video": 7}, [row()]),
            ({**good}, np.zeros((2, 5))), ({**good}, [[float("nan")] * 14]),
            ({"type": "ee_pose"}, np.zeros((0, 16))),
        ]
        for meta, acts in bad:
            code, err, _ = s.post("/submit", meta, acts)
            self.assertEqual(code, 400, (meta, err))
        for meta in ({"seconds": None}, {"seconds": float("inf")}, {"seconds": float("nan")}, {"seconds": -1},
                     {"video_fps": float("inf")}, {"cameras": 3}):
            code, err, _ = s.post("/observe", meta)
            self.assertEqual(code, 400, (meta, err))
        code, err, _ = s.post("/submit", {}, raw=rcb1.MAGIC + b"\x02\x00\x00\x00[]")      # an RCB1 frame whose header is not an object
        self.assertEqual(code, 400, err)
        for body in ('{"type": "joint_position", "actions": {"a": 1}}',                       # JSON bodies: actions of the wrong type,
                     '{"type": "joint_position", "actions": [[' + "9" * 400 + "]]}",              # a 400-digit integer (OverflowError),
                     '{"type": "joint_position", "actions": [[1, 2], [3]]}', '{"type": "joint_position", "actions": "x"}',
                     '{"type": "joint_position", "actions": null}', "[1, 2]", "{not json"):
            code, err, _ = s.post("/submit", {}, raw=body.encode())
            self.assertEqual(code, 400, (body[:60], err))
        st = s.get("/status")
        self.assertEqual((st["done"], st["reason"], st["physics_steps"]), (False, None, 0))   # no physics ran, nothing ended
        # the same episode still takes a valid chunk; odd but harmless fields are accepted as before
        code, m, _ = s.post("/submit", {**good, "note": 5, "cameras": "head_camera"}, [row(0.1)])
        self.assertEqual((code, m["executed_rows"], m["done"]), (200, 1, False))
        code, m, parts = s.post("/observe", {"cameras": ["head_camera", 7, "no_such_camera"], "video": None})
        self.assertEqual(code, 200); self.assertIn("last/head_camera", parts)

    def test_calibration_is_recomputed_for_every_response(self):
        s = self.service()
        _, m0, _ = s.post("/observe", {})
        self.assertEqual(m0["cameras"]["left_camera"]["cam2world_gl"][0][3], 0.0)
        _, m1, _ = s.post("/submit", {"type": "joint_position", "dt": 0.02, "video": "none"}, [row(0.3)])
        self.assertAlmostEqual(m1["cameras"]["left_camera"]["cam2world_gl"][0][3], 0.3, places=6)     # the wrist camera moved with the arm
        self.assertEqual(m1["cameras"]["head_camera"], m0["cameras"]["head_camera"])                    # a static camera did not
        _, m2, _ = s.post("/observe", {"seconds": 0.1})
        self.assertEqual(m2["cameras"], m1["cameras"])
        # per frame: a wrist camera's pose at every returned frame; static cameras carry none
        _, m3, parts = s.post("/submit", {"type": "joint_position", "dt": 0.1, "video": "frames", "video_fps": 25,
                                          "cameras": ["left_camera", "head_camera"]}, [row(0.4)])
        poses = parts["cam2world_gl/left_camera"]["data"]
        self.assertEqual(poses.shape, (parts["frames/left_camera"]["data"].shape[0], 4, 4))
        self.assertAlmostEqual(float(poses[0, 0, 3]), 0.3, places=6); self.assertAlmostEqual(float(poses[-1, 0, 3]), 0.4, places=6)
        self.assertTrue(np.all(np.diff(poses[:, 0, 3]) >= 0))
        self.assertEqual(poses[-1].tolist(), m3["cameras"]["left_camera"]["cam2world_gl"])
        self.assertNotIn("cam2world_gl/head_camera", parts)
        spec = s.get("/spec")
        self.assertIn("state the response ends in", spec["camera_calibration"])
        self.assertEqual(spec["cameras"]["left_camera"]["mounted"], "left wrist")

    def test_the_clock_starts_at_the_first_request(self):
        s = self.service()
        time.sleep(1.5)                                   # the agent's set-up: the service is up, nobody has called it
        spec = s.get("/spec")
        self.assertIn("first request", spec["budget"]["wall_clock_note"])
        _, m, _ = s.post("/observe", {})
        self.assertLess(m["time_s"], 1.0)
        self.assertGreater(m["time_left_s"], spec["budget"]["wall_clock_s"] - 1.0)
        first = [json.loads(l) for l in (s.data / "episode.jsonl").read_text().splitlines() if '"first_request"' in l]
        self.assertEqual(len(first), 1)
        s.post("/submit", {"type": "joint_position", "dt": 0.02, "video": "none"}, [row(0.1)])
        s.stop(); time.sleep(1.0)                         # a crash: the resumed service keeps the clock's origin
        s.start()
        _, m2, _ = s.post("/observe", {})
        self.assertGreater(m2["time_s"], 1.0)
        self.assertEqual(m2["step"], 1)

    def test_the_service_uses_robotwins_own_gripper_rule(self):
        s = self.service()
        made = [json.loads(l) for l in (s.data / "stub_session.jsonl").read_text().splitlines()]
        self.assertEqual(made, [{"task": "stack_blocks_two", "gripper_state": "command", "enable_render": True}])


class Verdicts(ServiceCase):
    def succeed(self, s: Service):
        code, m, _ = s.post("/submit", {"type": "joint_position", "dt": 0.1, "video": "none"}, [row(0.6, 1.0)])
        self.assertEqual((code, m["done"], m["reason"]), (200, True, "success"))

    def test_success_is_graded_1(self):
        s = self.service()
        self.succeed(s)
        d = s.wait_final()
        self.assertEqual((d["success"], d["replay_success"], d["deterministic"], d["video"]), (True, True, True, True))
        out = s.grade()
        self.assertEqual((out["success"], out["deterministic"], out["infra_error"], out["finalized"]), (1, 1, 0, 1))
        code, err, _ = s.post("/submit", {"type": "joint_position"}, [row()])
        self.assertEqual(code, 409)

    def test_nothing_done_is_the_agents_0(self):
        s = self.service()
        os.kill(s.proc.pid, signal.SIGUSR1)               # the collect hook: time is up
        d = s.wait_final()
        self.assertEqual((d["reason"], d["replay_success"], d["deterministic"]), ("timeout", False, True))
        out = s.grade()
        self.assertEqual((out["success"], out["infra_error"], out["grader_error"]), (0, 0, 0))

    def test_a_verdict_on_disk_is_graded_before_the_videos_and_survives_a_restart(self):
        s = self.service(RCB_STUB_VIDEO_S=60)
        self.succeed(s)
        d = s.wait_final("replay_success")                # the verdict is written; the video is still rendering
        self.assertEqual((d["finalized"], d["deterministic"]), (False, True))
        out = s.grade()
        self.assertEqual((out["success"], out["finalized"], out["infra_error"]), (1, 0, 0))
        s.stop()                                          # the service dies while rendering; compose restarts it
        s.start()
        d = s.final()
        self.assertEqual((d["success"], d["replay_success"], d["deterministic"], d["finalized"]), (True, True, True, True))
        self.assertEqual(s.grade()["success"], 1)
        os.kill(s.proc.pid, signal.SIGUSR1); time.sleep(0.3)      # the collect hook's signal changes nothing
        self.assertEqual(s.final(), d)

    def test_a_failed_verification_replay_is_infra_error(self):
        s = self.service(RCB_STUB_REPLAY_FAIL=1)
        self.succeed(s)
        d = s.wait_final()
        self.assertEqual((d["success"], d["replay_success"], d["finalize_error"], d["infra_error"]), (True, None, 1, 1))
        out = s.grade()
        self.assertEqual((out["success"], out["infra_error"], out["grader_error"], out["live_success"]), (0, 1, 1, 1))

    def test_an_unfinished_finalize_is_infra_error(self):
        s = self.service()
        s.post("/submit", {"type": "joint_position", "dt": 0.02, "video": "none"}, [row(0.1)])
        d = s.final()                                     # the collect hook gave up before any verdict: final.json as the episode left it
        self.assertEqual((d["done"], d["finalized"], d["replay_success"]), (False, False, None))
        out = s.grade()
        self.assertEqual((out["success"], out["infra_error"], out["missing_log"]), (0, 1, 0))

    def test_an_instance_that_does_not_rebuild_is_reported(self):
        s = Service(self.tmp, RCB_STUB_HASH_MISMATCH=1); self.svc = s
        s.start(wait=False)
        self.assertNotEqual(s.proc.wait(timeout=30), 0)   # first start: crash, compose retries
        self.assertEqual(s.final(), {})
        s.start()                                         # second start: say so and idle (the hook finds final.json at once)
        d = s.final()
        self.assertTrue(d["reason"].startswith("instance_mismatch"), d)
        self.assertEqual((d["finalized"], d["infra_error"], d["success"]), (True, 1, False))
        out = s.grade()
        self.assertEqual((out["success"], out["infra_error"], out["instance_mismatch"]), (0, 1, 1))


class StandardGrader(unittest.TestCase):
    """tests/grade.py of the standard twin on hand-written final.json files."""

    def grade(self, final):
        with tempfile.TemporaryDirectory() as td:
            s = Service.__new__(Service); s.data = Path(td) / "data"; s.data.mkdir()
            if final is not None:
                (s.data / "final.json").write_text(final if isinstance(final, str) else json.dumps(final))
            return s.grade()

    def test_cases(self):
        ok = {"success": True, "replay_success": True, "deterministic": True, "finalized": True, "reason": "success", "done": True}
        g = self.grade
        self.assertEqual(g(ok)["success"], 1)
        out = g(None); self.assertEqual((out["success"], out["missing_log"], out["infra_error"]), (0, 1, 1))
        for corrupt in ('{"success": true, "repl', "", "[1, 2]", "null"):
            out = g(corrupt); self.assertEqual((out["success"], out["infra_error"], out["grader_error"]), (0, 1, 1), corrupt)
        self.assertEqual(g({**ok, "finalized": False})["success"], 1)                         # the verdict stands without the videos
        self.assertEqual(g({**ok, "deterministic": False})["success"], 0)
        self.assertEqual(g({**ok, "deterministic": False})["infra_error"], 0)
        self.assertEqual(g({**ok, "success": False, "reason": "timeout"})["infra_error"], 0)
        out = g({**ok, "success": False, "reason": "error"}); self.assertEqual((out["success"], out["sim_error"], out["infra_error"]), (0, 1, 0))
        for no_verdict in ({"success": True, "done": True, "reason": "success", "finalized": False},
                           {"success": False, "done": False, "reason": None, "finalized": False},
                           {"success": True, "done": True, "reason": "success", "finalized": True, "replay_success": None, "deterministic": None}):
            out = g(no_verdict); self.assertEqual((out["success"], out["infra_error"]), (0, 1), no_verdict)
        for reason in ("sim_crashed", "resume_failed: journal shorter than the log", "resume_failed: replayed state differs from the logged one"):
            out = g({"success": False, "done": True, "reason": reason, "finalized": True, "infra_error": 1})
            self.assertEqual((out["success"], out["infra_error"]), (0, 1), reason)
            out = g({"success": False, "done": True, "reason": reason, "finalized": True})          # the reason alone is enough
            self.assertEqual(out["infra_error"], 1, reason)
        out = g({"success": False, "done": True, "reason": "sim_crashed_on_call", "finalized": True})
        self.assertEqual((out["success"], out["infra_error"], out["sim_crashed_on_call"]), (0, 0, 1))  # the agent's own call killed the sim
        self.assertEqual(g({**ok, "infra_error": 1})["success"], 0)


class PrivilegedGrader(unittest.TestCase):
    """tests/grade.py of the privileged twin: the deliverable checks, the instance probe and the video deadline, with the
    stand-in simulator as rcb_traj (its Session grades fl_joint1 > 0.5 with the left gripper value open)."""

    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="rcb-robotwin-test-"))
        self.tests = self.tmp / "tests"; self.tests.mkdir()
        shutil.copy(PRIV / "tests/grade.py", self.tests / "grade.py")
        shutil.copy(PRIV / "tests/instance.json", self.tests / "instance.json")
        shutil.copy(HERE / "stub_sim.py", self.tests / "rcb_traj.py")

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def grade(self, traj: Path | None, **env) -> dict:
        log = self.tmp / "verifier"; shutil.rmtree(log, ignore_errors=True)
        r = subprocess.run([sys.executable, str(self.tests / "grade.py"), "--family", "stack_blocks_two", "--instance",
                            str(self.tests / "instance.json"), "--traj", str(traj or self.tmp / "none.npz")],
                           capture_output=True, text=True, timeout=120,
                           env={**os.environ, "RCB_VERIFIER_LOG_DIR": str(log), "PYTHONDONTWRITEBYTECODE": "1", **{k: str(v) for k, v in env.items()}})
        self.assertEqual(r.returncode, 0, r.stderr)
        out = json.loads((log / "reward.json").read_text())
        self.assertEqual((log / "reward.txt").read_text().strip(), str(out["success"]))
        self.assertTrue(all(isinstance(v, (int, float)) and not isinstance(v, bool) for v in out.values()), out)
        for k in ("success", "deterministic", "grader_error"):
            self.assertIn(k, out)
        return out

    def npz(self, **arrays) -> Path:
        p = self.tmp / "trajectory.npz"
        np.savez(p, **arrays)
        return p

    def good(self, n=3, j1=0.6, grip=1.0) -> np.ndarray:
        a = np.zeros((n, 34)); a[:, 0] = j1; a[:, 32] = grip
        return a

    def test_malformed_deliverables_are_the_agents(self):
        cases = {
            "text": (self.tmp / "trajectory.npz", lambda p: p.write_text("not an npz")),
            "empty": (self.tmp / "trajectory.npz", lambda p: p.write_bytes(b"")),
        }
        for name, (p, make) in cases.items():
            make(p); out = self.grade(p)
            self.assertEqual((out["success"], out.get("bad_trajectory"), out["grader_error"]), (0, 1, 0), name)
        for name, arrays in {
            "no task": dict(actions=self.good()), "no actions": dict(task="stack_blocks_two"),
            "pickled": dict(actions=np.array([{"a": 1}], dtype=object), task="stack_blocks_two"),
            "strings": dict(actions=np.array([["a"] * 34]), task="stack_blocks_two"),
            "width 14": dict(actions=np.zeros((5, 14)), task="stack_blocks_two"),
            "1-D": dict(actions=np.zeros(34), task="stack_blocks_two"),
            "NaN": dict(actions=np.full((2, 34), np.nan), task="stack_blocks_two"),
            "too long": dict(actions=np.zeros((200_001, 34), dtype=np.float32), task="stack_blocks_two"),
        }.items():
            out = self.grade(self.npz(**arrays))
            self.assertEqual((out["success"], out.get("bad_trajectory"), out["grader_error"], out["deterministic"]), (0, 1, 0, 0), name)
        out = self.grade(self.npz(actions=self.good(), task="stack_bowls_two"))
        self.assertEqual((out["success"], out.get("wrong_family"), out["grader_error"]), (0, 1, 0))

    def test_verdicts(self):
        out = self.grade(self.npz(actions=self.good(), task="stack_blocks_two"))
        self.assertEqual((out["success"], out["deterministic"], out["n_actions"], out["video_rendered"]), (1, 1, 3, 1))
        out = self.grade(self.npz(actions=self.good(j1=0.1), task="stack_blocks_two"))
        self.assertEqual((out["success"], out["deterministic"], out["grader_error"]), (0, 1, 0))
        out = self.grade(self.npz(actions=np.zeros((0, 34)), task="stack_blocks_two"))
        self.assertEqual((out["success"], out["n_actions"]), (0, 0))

    def test_missing_trajectory_probes_the_instance(self):
        out = self.grade(None)
        self.assertEqual((out["success"], out["missing_trajectory"], out["infra_error"], out["grader_error"]), (0, 1, 0, 0))
        self.assertNotIn("instance_mismatch", out)
        out = self.grade(None, RCB_STUB_HASH_MISMATCH=1)                       # this host does not rebuild the instance
        self.assertEqual((out["success"], out["missing_trajectory"], out["instance_mismatch"], out["infra_error"]), (0, 1, 1, 1))
        (self.tests / "rcb_traj.py").write_text("raise ImportError('no simulator here')\n")
        out = self.grade(None)                                                 # the verifier cannot build a scene at all
        self.assertEqual((out["missing_trajectory"], out["instance_probe_error"], out["infra_error"]), (1, 1, 1))

    def test_instance_mismatch_with_a_trajectory(self):
        out = self.grade(self.npz(actions=self.good(), task="stack_blocks_two"), RCB_STUB_HASH_MISMATCH=1)
        self.assertEqual((out["success"], out["instance_mismatch"], out["infra_error"], out["grader_error"]), (0, 1, 1, 1))

    def test_the_videos_stop_at_the_deadline_and_keep_the_verdict(self):
        t0 = time.time()
        out = self.grade(self.npz(actions=self.good(), task="stack_blocks_two"), RCB_STUB_VIDEO_S=60, RCB_VERIFIER_VIDEO_DEADLINE_S=3)
        self.assertLess(time.time() - t0, 30)
        self.assertEqual((out["success"], out["deterministic"], out["video_rendered"]), (1, 1, 0))


if __name__ == "__main__":
    unittest.main()
