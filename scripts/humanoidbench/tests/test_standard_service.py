"""Tests for the standard-mode service core (shared/standard/rcb_service.py), its verifier (grade.py) and client
(rcb_client.py), against a tiny simulator: no MuJoCo, no GPU.

    python -m unittest discover -s scripts/<benchmark>/tests     # needs numpy and requests

FakeSim is a point on a line: each control step moves it by 0.1 x the command, and it succeeds once it reaches `goal`.
It implements the adapter contract rcb_service.Service expects (see Sim in rcb_service.py).
"""
from __future__ import annotations

import hashlib
import json
import os
import subprocess
import sys
import tempfile
import threading
import unittest
from pathlib import Path

import numpy as np

# RCB_SERVICE_DIR: another benchmark's copy of the service (LIBERO-MAX's rcb_service.py is its own variant; the unit
# tests job runs the classes that apply to it against scripts/libero-max/shared/standard)
STANDARD = Path(os.environ.get("RCB_SERVICE_DIR") or Path(__file__).resolve().parents[1] / "shared" / "standard").resolve()
sys.path.insert(0, str(STANDARD))
import rcb1  # noqa: E402
import rcb_service  # noqa: E402
from rcb_service import PROTOCOL, GiveUp, Service  # noqa: E402


class Crash(BaseException):
    """What a dying process looks like to the code under test: nothing catches it."""


class FakeSim:
    simulator, robot, control_dt, max_control_steps = "fake", "point", 0.1, 50
    cameras, depth_cameras = ("cam", "side"), ("cam",)
    proprio_layout = ["x", "cmd"]
    raw_dim = 1

    def __init__(self, goal: float = 1.0, on_step=None, verify_raises: BaseException | None = None,
                 video_raises: bool = False):
        self.goal, self.on_step, self.verify_raises, self.video_raises = goal, on_step, verify_raises, video_raises
        self.reset()

    def spec(self) -> dict:
        return {"simulator": self.simulator, "robot": self.robot, "task_text": "reach x >= goal",
                "episode": "ends on success or after 50 control steps",
                "action_types": {"move": {"dim": 1, "layout": ["dx"], "lower": [-1.0], "upper": [1.0], "units": "-",
                                          "semantics": "moves 0.1 x the command per step"}},
                "cameras": {"cam": {"hw": [4, 6]}, "side": {"hw": [4, 6]}}}

    def interpolable(self, typ: str) -> bool:
        return True

    def images(self, cameras, depth: bool):
        v = int(round(self.x * 100)) % 256
        rgb = {c: np.full((4, 6, 3), v, np.uint8) for c in cameras}
        dep = {c: np.full((4, 6), self.x, np.float32) for c in cameras if depth and c in self.depth_cameras}
        return rgb, dep

    def proprio(self) -> np.ndarray:
        return np.array([self.x, self.cmd], np.float32)

    def clip(self, typ: str, rows: np.ndarray):
        out = np.clip(rows, -1.0, 1.0)
        bad = np.argwhere(out != rows)
        return out, [{"row": int(r), "index": int(i), "reason": "limit [-1, 1]"} for r, i in bad]

    def to_sim(self, typ: str, row: np.ndarray) -> np.ndarray:
        return np.asarray(row, np.float64)

    def command(self, typ: str) -> np.ndarray:
        return np.array([self.cmd])

    def hold(self):
        return "move", np.array([self.cmd])

    def step(self, raw: np.ndarray):
        self.x = round(self.x + 0.1 * float(raw[0]), 10)
        self.cmd, self.t = float(raw[0]), self.t + 1
        if self.on_step:
            self.on_step(self)
        return self.t >= self.max_control_steps, self.x >= self.goal - 1e-9, {}

    def reset(self) -> None:
        self.x, self.cmd, self.t = 0.0, 0.0, 0

    def state_sha(self) -> str:
        return hashlib.sha1(np.array([self.x, self.t], np.float64).tobytes()).hexdigest()[:12]

    def verify(self, actions: np.ndarray) -> dict:
        if self.verify_raises is not None:
            raise self.verify_raises
        s = FakeSim(self.goal)
        success = False
        for a in actions:
            done, success, _ = s.step(a)
            if done or success:
                break
        return {"success": bool(success), "state_sha": s.state_sha()}

    def save_trajectory(self, actions: np.ndarray, path: str, meta: dict) -> None:
        np.savez(path, actions=actions, meta=json.dumps(meta))

    def render_video(self, actions: np.ndarray, path: str) -> None:
        if self.video_raises:
            raise RuntimeError("no GL")
        Path(path).write_bytes(b"mp4")
        Path(path).with_suffix(".last.png").write_bytes(b"png")


def call(svc: Service, method: str, path: str, meta: dict | None = None, actions=None, raw: bytes | None = None):
    """One request through the service's own HTTP surface; returns (status, meta or JSON, RCB1 parts or None)."""
    if raw is not None:
        body = raw
    elif actions is not None:
        body = rcb1.encode(meta or {}, [rcb1.array_part("actions", np.asarray(actions, np.float64))])
    else:
        body = json.dumps(meta or {}).encode() if method == "POST" else b""
    code, ctype, out = svc.handle(method, path, body)
    if ctype == "application/x-rcb1":
        m, p = rcb1.decode(out)
        return code, m, p
    return code, json.loads(out), None


def events(data: str) -> list[dict]:
    return [json.loads(line) for line in Path(data, "episode.jsonl").read_text().splitlines()]


def final(data: str) -> dict:
    return json.loads(Path(data, "final.json").read_text())


class Base(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.data = self.tmp.name

    def tearDown(self):
        self.tmp.cleanup()

    def service(self, sim=None, reset_budget: int = 0, **kw) -> Service:
        rcb_service.count_start(self.data)                   # a process start, as main() counts it
        svc = Service(sim or FakeSim(), data=self.data, reset_budget=reset_budget, wall_clock_s=3600.0, **kw)
        svc.start()
        return svc

    def submit(self, svc, rows, **meta):
        return call(svc, "POST", "/submit", {"type": "move", "dt": 0.1, "video": "none", **meta}, actions=rows)


class Endpoints(Base):
    def test_spec_states_protocol_budget_and_contract(self):
        code, spec, _ = call(self.service(), "GET", "/spec")
        self.assertEqual(code, 200)
        self.assertEqual(spec["protocol"], PROTOCOL)
        self.assertEqual(PROTOCOL, "eai-standard/2.1")
        self.assertEqual(spec["budget"], {"reset": 0, "wall_clock_s": 3600.0})
        self.assertEqual(spec["action_types"]["move"]["dim"], 1)
        self.assertEqual(spec["proprio_layout"], ["x", "cmd"])
        self.assertEqual(spec["control_dt"], 0.1)
        self.assertEqual(spec["max_control_steps"], 50)
        for k in ("max_chunk_s", "max_watch_s", "max_frames_per_call", "on_service_error", "episode", "task_text"):
            self.assertIn(k, spec)
        self.assertEqual(spec["cameras"]["cam"]["depth"], True)
        self.assertEqual(spec["cameras"]["side"]["depth"], False)

    def test_everything_else_is_404(self):
        svc = self.service()
        for method, path in [("GET", "/state"), ("GET", "/success"), ("POST", "/reset"), ("POST", "/step"),
                             ("GET", "/observe")]:
            code, body, _ = call(svc, method, path)
            self.assertEqual(code, 404, path)

    def test_status_counts(self):
        svc = self.service()
        self.submit(svc, [[0.5], [0.5]])
        code, st, _ = call(svc, "GET", "/status")
        self.assertEqual(code, 200)
        self.assertEqual((st["calls"], st["rows"], st["control_steps"], st["done"], st["reason"]), (1, 2, 2, False, None))
        self.assertIn("elapsed_s", st)


class Submit(Base):
    def test_response_is_rcb1_with_last_frames_and_one_proprio_row_per_frame(self):
        code, meta, parts = self.submit(self.service(), [[0.5]] * 4, cameras=["cam"], video="frames", video_fps=10)
        self.assertEqual(code, 200)
        self.assertEqual(meta["executed_rows"], 4)
        self.assertEqual(meta["control_steps"], 4)
        self.assertEqual(parts["last/cam"]["data"].shape, (4, 6, 3))
        n = parts["frames/cam"]["data"].shape[0]
        self.assertEqual(parts["proprio"]["data"].shape, (n, 2))
        self.assertEqual(meta["proprio"]["layout"], ["x", "cmd"])
        self.assertAlmostEqual(meta["proprio"]["now"][0], 0.2, places=6)
        for k in ("calls", "rows", "sim_time_s", "time_s", "time_left_s", "done", "reason", "chunk_id", "ok"):
            self.assertIn(k, meta)

    def test_without_video_only_the_last_frame_is_rendered(self):
        sim = FakeSim(goal=99)
        calls = []
        images = sim.images
        sim.images = lambda cams, depth: calls.append(cams) or images(cams, depth)
        svc = self.service(sim)
        code, meta, parts = self.submit(svc, [[0.1]] * 20, cameras=["cam"], video="none", video_fps=10)
        self.assertEqual(len(calls), 1)
        self.assertEqual(parts["proprio"]["data"].shape, (21, 2))          # one row per tick: the start, then each step
        self.assertNotIn("frames/cam", parts)
        self.assertEqual(parts["last/cam"]["data"].shape, (4, 6, 3))
        calls.clear()
        code, meta, parts = call(svc, "POST", "/observe", {"cameras": ["cam"], "video": "none"})
        self.assertEqual((code, len(calls)), (200, 1))
        self.assertIn("last/cam", parts)

    def test_out_of_limit_values_are_clipped_and_reported(self):
        svc = self.service()
        code, meta, _ = self.submit(svc, [[2.0], [0.5]])
        self.assertEqual(code, 200)
        self.assertEqual(meta["n_clipped"], 1)
        self.assertEqual(meta["clipped"][0]["row"], 0)
        self.assertAlmostEqual(svc.sim.x, 0.15)

    def test_invalid_requests_are_400_and_move_nothing(self):
        svc = self.service()
        bad = [({"type": "fly"}, [[0.1]]), ({}, [[0.1, 0.2]]), ({}, [[float("nan")]]), ({"dt": 0.15}, [[0.1]]),
               ({"dt": 0.0}, [[0.1]]), ({"interpolate": "cubic"}, [[0.1]]), ({"video": "gif"}, [[0.1]]),
               ({"cameras": ["nope"]}, [[0.1]]), ({"video_fps": 0}, [[0.1]]), ({"video_fps": 31}, [[0.1]]),
               ({}, [[0.1]] * 101),                                        # 10.1 s > max_chunk_s
               ({"cameras": ["side"], "include_depth": True}, [[0.1]])]     # no depth on that camera
        for meta, rows in bad:
            code, body, _ = self.submit(svc, rows, **meta)
            self.assertEqual(code, 400, (meta, body))
            self.assertIn("error", body)
        code, body, _ = call(svc, "POST", "/submit", raw=b"RCB1garbage")
        self.assertEqual(code, 400)
        code, body, _ = call(svc, "POST", "/submit", raw=b"{not json")
        self.assertEqual(code, 400)
        self.assertEqual((svc.sim.t, svc.sim.x), (0, 0.0))

    def test_malformed_fields_are_400_and_keep_the_episode(self):
        svc = self.service()
        for meta in ({"type": ["move"]}, {"type": {"move": 1}}, {"dt": [0.1]}, {"dt": float("inf")}, {"dt": 1e308},
                     {"video_fps": float("inf")}, {"video_fps": [10]}):
            code, body, _ = self.submit(svc, [[0.1]], **meta)
            self.assertEqual(code, 400, (meta, body))
        for meta in ({"video_fps": float("inf")}, {"seconds": [1]}):
            code, body, _ = call(svc, "POST", "/observe", meta)
            self.assertEqual(code, 400, (meta, body))
        code, st, _ = call(svc, "GET", "/status")
        self.assertEqual((st["done"], st["reason"], st["control_steps"]), (False, None, 0))

    def test_too_many_frames_is_400(self):
        svc = self.service(max_frames_per_call=50)
        code, body, _ = self.submit(svc, [[0.1]] * 100, video="frames", video_fps=10, cameras=["cam", "side"])
        self.assertEqual(code, 400)
        self.assertEqual(svc.sim.t, 0)

    def test_a_repeated_camera_is_rendered_and_returned_once(self):
        """Before: N copies of one name were rendered into one list N times and returned N times (N * N images) while
        the frame budget counted N -- a request of a few hundred bytes could exhaust the service's memory."""
        sim = FakeSim(goal=99)
        asked = []
        images = sim.images
        sim.images = lambda cams, depth: asked.append(list(cams)) or images(cams, depth)
        svc = self.service(sim, max_frames_per_call=50)
        code, meta, parts = self.submit(svc, [[0.1]] * 4, video="frames", video_fps=10,
                                        cameras=["side"] + ["cam"] * 40 + ["side"])
        self.assertEqual(code, 200)
        self.assertTrue(all(a == ["side", "cam"] for a in asked), asked)       # each once, in the order asked for
        n = parts["proprio"]["data"].shape[0]
        self.assertEqual(parts["frames/cam"]["data"].shape, (n, 4, 6, 3))
        self.assertEqual(parts["frames/side"]["data"].shape, (n, 4, 6, 3))
        self.assertEqual([e for e in events(self.data) if e["ev"] == "submit"][-1]["cameras"], ["side", "cam"])
        code, meta, parts = call(svc, "POST", "/observe", {"cameras": ["cam"] * 2000, "video": "frames"})
        self.assertEqual((code, parts["frames/cam"]["data"].shape), (200, (1, 4, 6, 3)))
        # the budget counts what is really returned: 2 cameras x (100 steps at 10 fps + 2) > 50
        code, body, _ = self.submit(svc, [[0.1]] * 100, video="frames", video_fps=10, cameras=["cam", "cam", "side"])
        self.assertEqual(code, 400)

    def test_oversized_body_is_413(self):
        svc = self.service()
        code, ctype, out = svc.handle("POST", "/submit", b"", content_length=64 * 1024 * 1024 + 1)
        self.assertEqual(code, 413)

    def test_json_body_with_actions_list_works(self):
        svc = self.service()
        code, meta, _ = call(svc, "POST", "/submit", {"type": "move", "dt": 0.1, "video": "none", "actions": [[0.3]]})
        self.assertEqual(code, 200)
        self.assertAlmostEqual(svc.sim.x, 0.03)

    def test_linear_interpolation_ramps_from_the_current_command(self):
        svc = self.service()
        self.submit(svc, [[0.9]], dt=0.3, interpolate="linear")
        rows = np.fromfile(os.path.join(self.data, "trajectory_live.f64"), dtype=np.float64)
        np.testing.assert_allclose(rows, [0.3, 0.6, 0.9])

    def test_hold_repeats_the_row(self):
        svc = self.service()
        self.submit(svc, [[0.9]], dt=0.3, interpolate="hold")
        rows = np.fromfile(os.path.join(self.data, "trajectory_live.f64"), dtype=np.float64)
        np.testing.assert_allclose(rows, [0.9, 0.9, 0.9])

    def test_not_interpolable_types_take_one_control_step_per_row(self):
        sim = FakeSim()
        sim.interpolable = lambda typ: False
        code, body, _ = self.submit(self.service(sim), [[0.5]], dt=0.2)
        self.assertEqual(code, 400)

    def test_success_ends_the_episode_mid_chunk_then_409(self):
        svc = self.service()
        code, meta, _ = self.submit(svc, [[1.0]] * 30)
        self.assertEqual((meta["done"], meta["reason"], meta["executed_rows"]), (True, "success", 10))
        code, body, _ = self.submit(svc, [[0.1]])
        self.assertEqual(code, 409)
        self.assertEqual(body["reason"], "success")

    def test_the_episode_cap_ends_it_as_failed(self):
        svc = self.service(FakeSim(goal=99))
        for _ in range(5):
            self.submit(svc, [[0.1]] * 10)
        code, st, _ = call(svc, "GET", "/status")
        self.assertEqual((st["done"], st["reason"], st["control_steps"]), (True, "failed", 50))

    def test_a_simulator_exception_is_500_and_ends_the_episode(self):
        def boom(sim):
            if sim.t == 2:
                raise RuntimeError("physics exploded")
        svc = self.service(FakeSim(on_step=boom))
        code, body, _ = self.submit(svc, [[0.1]] * 3)
        self.assertEqual(code, 500)
        code, st, _ = call(svc, "GET", "/status")
        self.assertEqual((st["done"], st["reason"]), (True, "error"))

    def test_a_value_error_raised_while_stepping_is_still_a_simulator_error(self):
        def boom(sim):
            if sim.t == 2:
                raise ValueError("the simulator refused a step")
        svc = self.service(FakeSim(on_step=boom))
        code, body, _ = self.submit(svc, [[0.1]] * 3)
        self.assertEqual(code, 500)
        self.assertEqual(call(svc, "GET", "/status")[1]["reason"], "error")

    def test_each_call_leaves_its_actions_and_meta_under_calls(self):
        svc = self.service()
        self.submit(svc, [[0.2], [0.3]])
        d = Path(self.data) / "calls" / "000001"
        np.testing.assert_allclose(np.load(d / "actions.npy"), [[0.2], [0.3]])
        self.assertEqual(json.loads((d / "meta.json").read_text())["executed_rows"], 2)


class Observe(Base):
    def test_seconds_zero_is_free(self):
        svc = self.service()
        code, meta, parts = call(svc, "POST", "/observe", {"cameras": ["cam"], "include_depth": True})
        self.assertEqual(code, 200)
        self.assertEqual(svc.sim.t, 0)
        self.assertEqual(parts["depth/cam"]["data"].dtype, np.float16)
        self.assertIn("last/cam", parts)

    def test_watching_holds_the_last_command_and_runs_physics(self):
        svc = self.service()
        self.submit(svc, [[0.5]])
        code, meta, _ = call(svc, "POST", "/observe", {"seconds": 0.3, "video": "none"})
        self.assertEqual(code, 200)
        self.assertEqual(svc.sim.t, 4)
        self.assertAlmostEqual(svc.sim.x, 0.2)
        self.assertEqual(meta["control_steps_watch"], 3)

    def test_seconds_out_of_range_is_400(self):
        code, body, _ = call(self.service(), "POST", "/observe", {"seconds": 31})
        self.assertEqual(code, 400)


class EndOfTrial(Base):
    def test_sigusr1_stops_a_chunk_and_finalizes_a_timeout(self):
        holder = {}
        svc = self.service(FakeSim(goal=99, on_step=lambda s: s.t == 3 and holder["svc"].on_sigusr1()))
        holder["svc"] = svc
        code, meta, _ = self.submit(svc, [[0.1]] * 20)
        self.assertEqual(meta["control_steps"], 3)
        svc.poll()
        f = final(self.data)
        self.assertTrue(f["finalized"])
        self.assertEqual(f["reason"], "timeout")
        self.assertEqual((f["n_actions"], f["deterministic"], f["replay_success"], f["live_success"]), (3, True, False, False))
        self.assertTrue(os.path.exists(os.path.join(self.data, "trajectory.npz")))
        self.assertTrue(f["video"])
        code, body, _ = self.submit(svc, [[0.1]])
        self.assertEqual(code, 409)

    def test_a_success_is_graded_on_the_fresh_replay(self):
        svc = self.service()
        self.submit(svc, [[1.0]] * 12)
        svc.on_sigusr1()
        svc.poll()
        f = final(self.data)
        self.assertEqual((f["live_success"], f["replay_success"], f["deterministic"], f["success"]), (True, True, True, True))
        self.assertEqual(f["n_actions"], 10)

    def test_the_verdict_is_on_disk_even_when_the_video_fails(self):
        svc = self.service(FakeSim(video_raises=True))
        self.submit(svc, [[1.0]] * 10)
        svc.on_sigusr1()
        svc.poll()
        f = final(self.data)
        self.assertEqual((f["finalized"], f["deterministic"], f["video"]), (True, True, False))
        self.assertEqual((f["success"], f["video_pending"]), (True, False))
        self.assertIn("video_error", [e["ev"] for e in events(self.data)])

    def test_the_verdict_is_finalized_before_the_video_is_rendered(self):
        """What the collect hook and the verifier key on ("finalized": true) is on disk with the verdict, so a video
        that is slow, hangs or is killed with the hook costs the video, never the verdict."""
        seen = {}
        sim = FakeSim()
        render = sim.render_video

        def slow_video(actions, path):
            seen.update(final(self.data))                    # final.json while the video renders
            render(actions, path)
        sim.render_video = slow_video
        svc = self.service(sim)
        self.submit(svc, [[1.0]] * 10)
        svc.on_sigusr1()
        svc.poll()
        self.assertEqual((seen["finalized"], seen["success"], seen["deterministic"], seen["replay_success"]),
                         (True, True, True, True))
        self.assertEqual((seen["video"], seen["video_pending"]), (False, True))
        f = final(self.data)
        self.assertEqual((f["finalized"], f["success"], f["video"], f["video_pending"]), (True, True, True, False))
        self.assertEqual({k: f[k] for k in seen if k not in ("video", "video_pending")},
                         {k: seen[k] for k in seen if k not in ("video", "video_pending")})   # nothing else moved

    def test_a_failed_finalize_waits_for_no_video(self):
        svc = self.service(FakeSim(verify_raises=RuntimeError("replay broke")))
        self.submit(svc, [[1.0]] * 3)
        svc.on_sigusr1()
        svc.poll()
        f = final(self.data)
        self.assertEqual((f["finalized"], f["video_pending"]), (True, False))
        self.assertFalse(os.path.exists(os.path.join(self.data, "replay.mp4")))

    def test_a_failing_finalize_is_recorded_not_raised(self):
        svc = self.service(FakeSim(verify_raises=RuntimeError("replay broke")))
        self.submit(svc, [[1.0]] * 3)
        svc.on_sigusr1()
        svc.poll()
        f = final(self.data)
        self.assertTrue(f["finalized"])
        self.assertIn("replay broke", f["finalize_error"])

    def test_final_json_is_valid_json_after_every_call(self):
        svc = self.service()
        for _ in range(3):
            self.submit(svc, [[0.1]])
            self.assertIn('"finalized": false', Path(self.data, "final.json").read_text())


class CrashRecovery(Base):
    def test_a_restart_resumes_the_same_episode(self):
        svc = self.service(FakeSim(goal=99))
        self.submit(svc, [[0.5]] * 4)
        call(svc, "POST", "/observe", {"seconds": 0.2, "video": "none"})
        sha, x = svc.sim.state_sha(), svc.sim.x
        svc2 = self.service(FakeSim(goal=99))                       # the restarted process: a fresh scene
        self.assertEqual((svc2.sim.state_sha(), svc2.sim.x), (sha, x))
        code, st, _ = call(svc2, "GET", "/status")
        self.assertEqual((st["calls"], st["rows"], st["control_steps"], st["done"]), (2, 4, 6, False))
        self.assertEqual(len([e for e in events(self.data) if e["ev"] == "resumed"]), 1)
        self.assertFalse([e for e in events(self.data) if e["ev"] == "resuming"][0]["crashed_in_call"])
        code, meta, _ = self.submit(svc2, [[0.5]])
        self.assertEqual(meta["control_steps"], 7)

    def test_the_call_in_flight_is_lost_as_a_whole(self):
        svc = self.service(FakeSim(goal=99))
        self.submit(svc, [[0.5]] * 2)
        sha = svc.sim.state_sha()
        with open(os.path.join(self.data, "episode.jsonl"), "a") as f:
            f.write(json.dumps({"ts": 0, "ev": "call_begin", "path": "/submit", "call": 2}) + "\n")
        with open(os.path.join(self.data, "trajectory_live.f64"), "ab") as f:
            f.write(np.array([0.5, 0.5, 0.5], np.float64).tobytes())
        svc2 = self.service(FakeSim(goal=99))
        self.assertEqual(svc2.sim.state_sha(), sha)
        self.assertEqual(os.path.getsize(os.path.join(self.data, "trajectory_live.f64")), 2 * 8)
        self.assertTrue([e for e in events(self.data) if e["ev"] == "resuming"][0]["crashed_in_call"])

    def test_a_journal_that_does_not_reach_the_log_refuses_to_resume(self):
        svc = self.service(FakeSim(goal=99))
        self.submit(svc, [[0.5]] * 3)
        open(os.path.join(self.data, "trajectory_live.f64"), "wb").close()
        with self.assertRaises(GiveUp):
            self.service(FakeSim(goal=99))
        f = final(self.data)
        self.assertEqual((f["finalized"], f["infra_error"]), (True, 1))
        self.assertTrue(f["reason"].startswith("resume_failed"))

    def test_more_than_two_crashes_end_the_episode(self):
        svc = self.service(FakeSim(goal=99))
        self.submit(svc, [[0.5]])
        for _ in range(2):
            self.service(FakeSim(goal=99))
        with self.assertRaises(GiveUp):
            self.service(FakeSim(goal=99))
        f = final(self.data)
        self.assertEqual((f["reason"], f["infra_error"], f["finalized"], f["success"]), ("sim_crashed", 1, True, False))

    def test_crashes_while_resuming_count_too(self):
        def crash(_):
            raise Crash()
        svc = self.service(FakeSim(goal=99))
        self.submit(svc, [[0.5]] * 2)
        for _ in range(2):
            with self.assertRaises(Crash):
                self.service(FakeSim(goal=99, on_step=crash))   # dies replaying the journal
        with self.assertRaises(GiveUp):
            self.service(FakeSim(goal=99))
        f = final(self.data)
        self.assertEqual((f["reason"], f["infra_error"], f["finalized"], f["success"]), ("sim_crashed", 1, True, False))

    def test_a_restart_that_died_building_the_scene_counts_too(self):
        svc = self.service(FakeSim(goal=99))
        self.submit(svc, [[0.5]])
        rcb_service.count_start(self.data)                   # this one never got as far as the episode
        self.service(FakeSim(goal=99))
        with self.assertRaises(GiveUp):
            self.service(FakeSim(goal=99))
        self.assertEqual(final(self.data)["reason"], "sim_crashed")

    def test_crashes_that_all_happen_inside_calls_are_the_agents(self):
        svc = self.service(FakeSim(goal=99))
        self.submit(svc, [[0.5]])
        for i in range(3):
            with open(os.path.join(self.data, "episode.jsonl"), "a") as f:
                f.write(json.dumps({"ts": 0, "ev": "call_begin", "path": "/submit", "call": 2}) + "\n")
            if i < 2:
                self.service(FakeSim(goal=99))
        with self.assertRaises(GiveUp):
            self.service(FakeSim(goal=99))
        f = final(self.data)
        self.assertEqual((f["reason"], f.get("infra_error", 0)), ("sim_crashed_on_call", 0))

    def test_a_restart_after_finalize_keeps_the_verdict(self):
        svc = self.service()
        self.submit(svc, [[1.0]] * 10)
        svc.on_sigusr1()
        svc.poll()
        before = final(self.data)
        with self.assertRaises(GiveUp):
            self.service()
        after = final(self.data)
        self.assertEqual({k: after[k] for k in before}, before)

    def test_a_restart_after_a_failed_finalize_keeps_it(self):
        svc = self.service(FakeSim(verify_raises=RuntimeError("replay broke")))
        self.submit(svc, [[1.0]] * 3)
        svc.on_sigusr1()
        svc.poll()
        before = final(self.data)
        with self.assertRaises(GiveUp):
            self.service()
        self.assertEqual(final(self.data), before)

    def test_a_crash_while_rendering_the_video_keeps_the_verdict(self):
        def crash(*_):
            raise Crash()
        sim = FakeSim()
        sim.render_video = crash
        svc = self.service(sim)
        self.submit(svc, [[1.0]] * 10)
        svc.on_sigusr1()
        with self.assertRaises(Crash):
            svc.poll()
        f = final(self.data)                                 # the process is dead: the verdict is there, finalized
        self.assertEqual((f["finalized"], f["success"], f["video_pending"]), (True, True, True))
        with self.assertRaises(GiveUp):
            self.service()
        f = final(self.data)
        self.assertEqual((f["finalized"], f["success"], f["live_success"], f["replay_success"], f["deterministic"],
                          f["video"]), (True, True, True, True, True, False))
        self.assertFalse(f["video_pending"])                 # the restarted service: no video is coming, do not wait
        self.assertNotIn("infra_error", f)

    def test_a_verdict_of_an_older_service_without_finalized_is_kept(self):
        """A final.json with the verdict but "finalized": false (written before finalized moved ahead of the video)."""
        svc = self.service()
        self.submit(svc, [[1.0]] * 10)
        svc.on_sigusr1()
        svc.poll()
        fin = {k: v for k, v in final(self.data).items() if k != "video_pending"}
        Path(self.data, "final.json").write_text(json.dumps({**fin, "finalized": False, "video": False}))
        with self.assertRaises(GiveUp):
            self.service()
        f = final(self.data)
        self.assertEqual((f["finalized"], f["success"], f["deterministic"], f["video"]), (True, True, True, False))

    def test_a_timeout_survives_a_crash_during_finalize(self):
        svc = self.service(FakeSim(goal=99, verify_raises=Crash()))
        self.submit(svc, [[0.5]] * 2)
        svc.on_sigusr1()
        with self.assertRaises(Crash):
            svc.poll()
        svc2 = self.service(FakeSim(goal=99))
        code, st, _ = call(svc2, "GET", "/status")
        self.assertEqual((st["done"], st["reason"]), (True, "timeout"))
        svc2.on_sigusr1()
        svc2.poll()
        f = final(self.data)
        self.assertEqual((f["finalized"], f["deterministic"], f["n_actions"], f["reason"]), (True, True, 2, "timeout"))

    def test_the_clock_survives_a_restart(self):
        svc = self.service()
        call(svc, "GET", "/spec")
        t0 = svc.t0
        svc2 = self.service()
        self.assertEqual(svc2.t0, t0)


class ResetCapability(Base):
    def test_reset_is_available_only_with_a_budget(self):
        svc = self.service(reset_budget=2)
        code, spec, _ = call(svc, "GET", "/spec")
        self.assertEqual(spec["budget"]["reset"], 2)
        self.submit(svc, [[0.5]] * 3)
        code, meta, parts = call(svc, "POST", "/reset", {"cameras": ["cam"]})
        self.assertEqual(code, 200)
        self.assertEqual((meta["resets_left"], meta["control_steps"], meta["done"], meta["episode"]), (1, 0, False, 2))
        self.assertIn("last/cam", parts)
        self.assertEqual(svc.sim.x, 0.0)

    def test_the_budget_runs_out(self):
        svc = self.service(reset_budget=1)
        self.assertEqual(call(svc, "POST", "/reset")[0], 200)
        code, body, _ = call(svc, "POST", "/reset")
        self.assertEqual(code, 409)

    def test_a_failed_episode_can_be_reset_but_a_success_ends_the_trial(self):
        svc = self.service(FakeSim(goal=2.0), reset_budget=3)
        for _ in range(5):
            self.submit(svc, [[0.1]] * 10)
        code, body, _ = self.submit(svc, [[0.1]])
        self.assertEqual(code, 409)
        self.assertEqual(body["resets_left"], 3)
        self.assertEqual(call(svc, "POST", "/reset")[0], 200)
        code, meta, _ = self.submit(svc, [[1.0]] * 20)
        self.assertEqual((meta["reason"], meta["resets_left"]), ("success", 0))
        code, body, _ = call(svc, "POST", "/reset")
        self.assertEqual(code, 409)

    def test_only_the_last_episode_is_graded(self):
        svc = self.service(reset_budget=2)
        self.submit(svc, [[0.5]] * 4)
        call(svc, "POST", "/reset")
        self.submit(svc, [[1.0]] * 10)
        svc.on_sigusr1()
        svc.poll()
        f = final(self.data)
        self.assertEqual((f["n_actions"], f["success"], f["resets"], f["episodes"]), (10, True, 1, 2))

    def test_a_restart_resumes_the_episode_after_the_last_reset(self):
        svc = self.service(FakeSim(goal=99), reset_budget=2)
        self.submit(svc, [[0.5]] * 4)
        call(svc, "POST", "/reset")
        self.submit(svc, [[0.3]] * 2)
        sha = svc.sim.state_sha()
        svc2 = self.service(FakeSim(goal=99), reset_budget=2)
        self.assertEqual(svc2.sim.state_sha(), sha)
        code, st, _ = call(svc2, "GET", "/status")
        self.assertEqual((st["control_steps"], st["resets_left"], st["episode"]), (2, 1, 2))


class ResetChecks(Base):
    def test_a_refused_reset_changes_nothing(self):
        svc = self.service(reset_budget=1)
        self.submit(svc, [[0.1]] * 2)
        code, body, _ = call(svc, "POST", "/reset", {"cameras": ["nope"]})
        self.assertEqual(code, 400)
        code, st, _ = call(svc, "GET", "/status")
        self.assertEqual((st["control_steps"], st["done"], st["resets_left"]), (2, False, 1))
        self.assertEqual(call(svc, "POST", "/reset", {})[0], 200)
        code, body, _ = call(svc, "POST", "/reset", {})
        self.assertEqual((code, body["error"]), (409, "reset budget exhausted"))

    def test_a_reset_the_simulator_fails_is_a_simulator_error(self):
        """Before (LIBERO-MAX's variant until 2026-10): the trial ended "reset" -- the agent's own choice -- when the
        simulator failed to start the new episode."""
        sim = FakeSim(goal=99)
        svc = self.service(sim, reset_budget=2)
        self.submit(svc, [[0.1]] * 2)

        def boom():
            raise RuntimeError("the scene did not build")
        sim.reset = boom
        code, body, _ = call(svc, "POST", "/reset", {})
        self.assertEqual(code, 500)
        code, st, _ = call(svc, "GET", "/status")
        self.assertEqual((st["done"], st["reason"]), (True, "error"))
        self.assertEqual(final(self.data)["reason"], "error")
        ends = [e for e in events(self.data) if e["ev"] == "end"]
        self.assertTrue(ends[-1].get("reset_failed"), ends)


class Grade(Base):
    def grade(self, fin: dict | None) -> tuple[str, dict]:
        logs = os.path.join(self.data, "logs")
        if fin is not None:
            Path(self.data, "final.json").write_text(json.dumps(fin))
        env = {**os.environ, "RCB_DATA": self.data, "RCB_VERIFIER_LOG_DIR": logs}
        subprocess.run([sys.executable, str(STANDARD / "grade.py")], env=env, check=True, capture_output=True)
        return Path(logs, "reward.txt").read_text().strip(), json.loads(Path(logs, "reward.json").read_text())

    def test_success_needs_live_replay_and_determinism(self):
        base = {"finalized": True, "live_success": True, "replay_success": True, "deterministic": True,
                "n_actions": 10, "calls": 3, "rows": 12, "control_steps": 10, "elapsed_s": 5.0, "video": True,
                "reason": "success", "sim_startups": 1}
        txt, r = self.grade(base)
        self.assertEqual((txt, r["success"], r["infra_error"], r["video_rendered"]), ("1", 1, 0, 1))
        for k in ("live_success", "replay_success", "deterministic"):
            txt, r = self.grade({**base, k: False})
            self.assertEqual((txt, r["success"]), ("0", 0), k)
        self.assertTrue(all(isinstance(v, (int, float)) for v in r.values()))

    def test_a_missing_log_is_infrastructure(self):
        txt, r = self.grade(None)
        self.assertEqual((txt, r["success"], r["missing_log"], r["infra_error"]), ("0", 0, 1, 1))
        self.assertEqual((r["deterministic"], r["sim_error"], r["grader_error"]), (0, 0, 0))

    def test_an_unreadable_log_is_infrastructure(self):
        for text in ('{"finalized": true, "live_succ', "[1, 2]", "null", ""):
            Path(self.data, "final.json").write_text(text)
            txt, r = self.grade(None)
            self.assertEqual((txt, r["success"], r["deterministic"], r["infra_error"], r["grader_error"]),
                             ("0", 0, 0, 1, 1), text)

    def test_a_simulator_error_is_reported(self):
        txt, r = self.grade({"finalized": True, "live_success": False, "replay_success": False, "deterministic": True,
                             "reason": "error"})
        self.assertEqual((r["success"], r["sim_error"], r["deterministic"]), (0, 1, 1))
        txt, r = self.grade({"finalized": True, "live_success": False, "replay_success": False, "deterministic": True,
                             "reason": "failed"})
        self.assertEqual(r["sim_error"], 0)

    def test_a_verdict_whose_video_never_came_stands(self):
        """The collect hook ran out of time while the video rendered: finalized, video_pending still true."""
        txt, r = self.grade({"finalized": True, "live_success": True, "replay_success": True, "deterministic": True,
                             "video": False, "video_pending": True, "reason": "success"})
        self.assertEqual((txt, r["success"], r["infra_error"], r["video_rendered"]), ("1", 1, 0, 0))
        self.assertTrue(all(isinstance(v, (int, float)) for v in r.values()))

    def test_a_crashed_service_or_failed_finalize_is_not_the_agents(self):
        txt, r = self.grade({"finalized": True, "success": False, "reason": "sim_crashed", "infra_error": 1})
        self.assertEqual((r["success"], r["infra_error"]), (0, 1))
        txt, r = self.grade({"finalized": True, "finalize_error": "boom", "live_success": True})
        self.assertEqual((r["success"], r["grader_error"], r["infra_error"]), (0, 1, 1))

    def test_an_unfinalized_log_is_infrastructure(self):
        txt, r = self.grade({"finalized": False, "live_success": True})
        self.assertEqual((r["success"], r["infra_error"], r["grader_error"]), (0, 1, 0))

    def test_reward_counts_every_control_step_and_the_reset_budget(self):
        txt, r = self.grade({"finalized": True, "live_success": False, "replay_success": False, "deterministic": True,
                             "n_actions": 10, "control_steps_total": 34, "resets": 2, "reset_budget": 50})
        self.assertEqual((r["n_actions"], r["sim_steps"], r["resets"], r["reset_budget"]), (10, 34, 2, 50))


class Client(Base):
    def test_client_round_trip_over_http(self):
        import rcb_client
        svc = self.service(reset_budget=1)
        srv = svc.http_server(("127.0.0.1", 0))
        threading.Thread(target=srv.serve_forever, daemon=True).start()
        try:
            r = rcb_client.Robot(f"http://127.0.0.1:{srv.server_address[1]}", timeout=10)
            self.assertEqual(r.spec()["protocol"], PROTOCOL)
            res = r.submit("move", np.full((3, 1), 0.5), dt=0.1, cameras=["cam"], video="frames")
            self.assertEqual(res.meta["executed_rows"], 3)
            self.assertEqual(res.frames["cam"].shape[1:], (4, 6, 3))
            self.assertEqual(res.proprio.shape[1], 2)
            obs = r.get_obs(cameras=["cam"], include_depth=True)
            self.assertEqual(obs.depth["cam"].shape, (1, 4, 6))
            self.assertEqual(r.status()["control_steps"], 3)
            with self.assertRaises(ValueError):
                r.submit("move", [[float("inf")]])
            r.submit("move", np.ones((10, 1)), video="none")
            with self.assertRaises(rcb_client.EpisodeOver):
                r.submit("move", [[0.1]], video="none")
            with self.assertRaises(rcb_client.EpisodeOver):
                r.reset()                                    # a success ends the trial, resets or not
        finally:
            srv.shutdown()
            srv.server_close()


    def test_client_errors_are_value_errors_and_keep_the_episode(self):
        import rcb_client
        svc = self.service()
        srv = svc.http_server(("127.0.0.1", 0))
        threading.Thread(target=srv.serve_forever, daemon=True).start()
        try:
            r = rcb_client.Robot(f"http://127.0.0.1:{srv.server_address[1]}", timeout=10)
            with self.assertRaises(ValueError):
                r.submit("move", [[0.1]], dt=float("inf"))
            with self.assertRaises(ValueError):
                r.submit(["move"], [[0.1]])
            with self.assertRaises(ValueError):                  # over the protocol's 64 MB: refused before sending
                r.submit("move", np.zeros((rcb_service.MAX_BODY // 8 + 1, 1)), video="none")
            self.assertEqual((r.status()["done"], r.status()["calls"]), (False, 0))
        finally:
            srv.shutdown()
            srv.server_close()


class Boot(Base):
    def test_the_pid_file_appears_when_the_service_is_ready(self):
        self.service()
        self.assertEqual(Path(self.data, "server.pid").read_text(), str(os.getpid()))

    def test_a_busy_port_is_waited_for_and_the_trial_can_still_end(self):
        import socket
        holder = socket.socket()
        holder.bind(("0.0.0.0", 0))
        holder.listen()
        port = holder.getsockname()[1]
        svc = self.service()
        self.submit(svc, [[0.1]])
        got = {}
        t = threading.Thread(target=lambda: got.update(srv=svc.bind(port)), daemon=True)
        t.start()
        t.join(1.5)
        self.assertTrue(t.is_alive())
        self.assertIn("port_busy", [e["ev"] for e in events(self.data)])
        svc.on_sigusr1()                                      # the trial ends meanwhile: it is still graded
        for _ in range(50):
            if final(self.data)["finalized"]:
                break
            t.join(0.1)
        self.assertEqual((final(self.data)["finalized"], final(self.data)["reason"]), (True, "timeout"))
        holder.close()
        t.join(5)
        self.assertFalse(t.is_alive())
        got["srv"].server_close()

    def test_a_service_that_gave_up_answers_every_request(self):
        """Before: nothing listened after a give-up, and a client waited out its connection timeout."""
        import socket
        import requests
        import rcb_client
        with socket.socket() as k:
            k.bind(("127.0.0.1", 0))
            port = k.getsockname()[1]
        threading.Thread(target=rcb_service.refuse_forever, args=("sim_crashed", port), daemon=True).start()
        url = f"http://127.0.0.1:{port}"
        for _ in range(100):
            try:
                r = requests.get(url + "/status", timeout=5)
                break
            except requests.exceptions.ConnectionError:
                threading.Event().wait(0.05)
        self.assertEqual((r.status_code, r.json()["reason"], r.json()["gave_up"]), (409, "sim_crashed", True))
        self.assertEqual(requests.post(url + "/submit", data=b"x" * 100000, timeout=5).status_code, 409)
        with self.assertRaises(requests.exceptions.HTTPError) as ctx:      # the client: at once, not after its timeout
            rcb_client.Robot(url, timeout=120)
        self.assertEqual(ctx.exception.response.status_code, 409)

    def test_every_start_is_counted(self):
        rcb_service.count_start(self.data)
        rcb_service.count_start(self.data)
        self.assertEqual(len(Path(self.data, "startups.jsonl").read_text().splitlines()), 2)


if __name__ == "__main__":
    unittest.main()
