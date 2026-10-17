"""Tests for the standard-mode service core (shared/standard/rcb_service.py), its verifier (grade.py) and client
(rcb_client.py), against a tiny simulator: no MuJoCo, no GPU.

    python -m unittest discover -s scripts/<benchmark>/tests     # needs numpy and requests

FakeSim is a point on a line: each control step moves it by 0.1 x the command, and it succeeds once it reaches `goal`.
It implements the adapter contract rcb_service.Service expects (see Sim in rcb_service.py). Its verify() raises: the
verdict is the live episode's (board 0151), and nothing may replay the episode to grade it.
"""
from __future__ import annotations

import hashlib
import inspect
import json
import os
import subprocess
import sys
import tempfile
import threading
import time
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

# A variant that still grades by a replay (RCB_SERVICE_DIR: LIBERO-MAX's own, until it moves to the live rule) gets
# FakeSim's replay; the live layer must never call it.
REPLAYING = "verify(" in inspect.getsource(Service._finalize)


class Crash(BaseException):
    """What a dying process looks like to the code under test: nothing catches it."""


class FakeSim:
    simulator, robot, control_dt, max_control_steps = "fake", "point", 0.1, 50
    cameras, depth_cameras = ("cam", "side"), ("cam",)
    proprio_layout = ["x", "cmd"]
    raw_dim = 1
    replay_free = True     # it has a verify() (that raises: the proof that nothing calls it), knowingly

    def __init__(self, goal: float = 1.0, on_step=None, save_raises: BaseException | None = None,
                 video_raises: bool = False):
        self.goal, self.on_step, self.save_raises, self.video_raises = goal, on_step, save_raises, video_raises
        self.replays = 0                                # verify() calls: none, ever (the verdict is the live one)
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
        self.replays += 1
        if not REPLAYING:
            raise AssertionError("a grading replay ran: the standard modes are graded by the live episode (board 0151)")
        s = FakeSim(self.goal)
        success = False
        for a in actions:
            done, success, _ = s.step(a)
            if done or success:
                break
        return {"success": bool(success), "state_sha": s.state_sha()}

    def save_trajectory(self, actions: np.ndarray, path: str, meta: dict) -> None:
        if self.save_raises is not None:
            raise self.save_raises
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
        self.assertEqual((f["n_actions"], f["graded_by"], f["replays"], f["live_success"], f["success"]),
                         (3, "live", 0, False, False))
        self.assertNotIn("replay_success", f)
        self.assertNotIn("deterministic", f)
        self.assertEqual(svc.sim.replays, 0)
        self.assertTrue(os.path.exists(os.path.join(self.data, "trajectory.npz")))
        self.assertTrue(f["video"])
        code, body, _ = self.submit(svc, [[0.1]])
        self.assertEqual(code, 409)

    def test_a_live_success_is_the_verdict_and_nothing_is_replayed(self):
        svc = self.service()
        self.submit(svc, [[1.0]] * 12)
        svc.on_sigusr1()
        svc.poll()
        f = final(self.data)
        self.assertEqual((f["live_success"], f["success"], f["graded_by"], f["replays"], f["finalized"]),
                         (True, True, "live", 0, True))
        self.assertEqual((f["n_actions"], f["state_sha"], f["video_source"], f["video"]),
                         (10, svc.sim.state_sha(), "render", True))
        self.assertFalse({"replay_success", "deterministic", "live_rule", "infra_error"} & set(f))
        self.assertEqual(svc.sim.replays, 0)
        self.assertEqual([e for e in events(self.data) if e["ev"] == "verdict"][0]["graded_by"], "live")

    def test_a_live_failure_is_a_zero(self):
        svc = self.service(FakeSim(goal=99))
        self.submit(svc, [[1.0]] * 60)                       # the episode's 50 control steps run out
        svc.on_sigusr1()
        svc.poll()
        f = final(self.data)
        self.assertEqual((f["reason"], f["live_success"], f["success"], f["finalized"], f["n_actions"]),
                         ("failed", False, False, True, 50))
        self.assertNotIn("infra_error", f)
        self.assertEqual(svc.sim.replays, 0)

    def test_live_verdict_can_take_a_success_away(self):
        """The adapter's live_verdict(): e.g. a settle window run on the live simulator after the episode ended."""
        seen = []
        sim = FakeSim()

        def settle(rows, success):
            seen.append((len(rows), success, sim.x))
            for _ in range(5):                               # the hold, on the live simulator
                sim.step(np.array([-1.0]))
            return {"success": sim.x >= sim.goal - 1e-9, "settled_x": sim.x}
        sim.live_verdict = settle
        svc = self.service(sim)
        self.submit(svc, [[1.0]] * 10)
        svc.on_sigusr1()
        svc.poll()
        f = final(self.data)
        self.assertEqual(seen, [(10, True, 1.0)])
        self.assertEqual((f["live_success"], f["live_rule"], f["success"], f["settled_x"], f["finalized"]),
                         (True, False, False, 0.5, True))
        self.assertNotIn("infra_error", f)                   # a failed settle is the agent's: a 0, not infrastructure

    def test_live_verdict_never_gives_a_success(self):
        sim = FakeSim(goal=99)
        sim.live_verdict = lambda rows, success: {"success": True}
        svc = self.service(sim)
        self.submit(svc, [[1.0]] * 3)
        svc.on_sigusr1()
        svc.poll()
        f = final(self.data)
        self.assertEqual((f["live_success"], f["live_rule"], f["success"]), (False, True, False))

    def test_live_verdict_that_holds_keeps_the_success_and_cannot_rewrite_the_service_fields(self):
        sim = FakeSim()
        sim.live_verdict = lambda rows, success: {"success": True, "held_s": 1.0, "reason": "x", "finalized": False,
                                                  "graded_by": "replay", "live_success": False}
        svc = self.service(sim)
        self.submit(svc, [[1.0]] * 10)
        svc.on_sigusr1()
        svc.poll()
        f = final(self.data)
        self.assertEqual((f["success"], f["live_rule"], f["held_s"], f["reason"], f["finalized"], f["graded_by"],
                          f["live_success"]), (True, True, 1.0, "success", True, "live", True))

    def test_live_verdict_numpy_values_are_written_as_json(self):
        sim = FakeSim()
        sim.live_verdict = lambda rows, success: {"success": np.bool_(True), "held_s": np.float32(1.5),
                                                  "xs": np.arange(2), "ev": "x", "ts": 1}
        svc = self.service(sim)
        self.submit(svc, [[1.0]] * 10)
        svc.on_sigusr1()
        svc.poll()
        f = final(self.data)
        self.assertEqual((f["success"], f["live_rule"], f["held_s"], f["xs"]), (True, True, 1.5, [0, 1]))
        self.assertNotIn("ev", f)
        self.assertIn("verdict", [e["ev"] for e in events(self.data)])

    def test_live_verdict_that_is_not_json_or_not_true_takes_the_success_away(self):
        for extra in ({"success": True, "obj": object()}, {"success": "false"}, {"success": 1}):
            with tempfile.TemporaryDirectory() as d:
                self.data = d
                sim = FakeSim()
                sim.live_verdict = lambda rows, success, extra=extra: dict(extra)
                svc = self.service(sim)
                self.submit(svc, [[1.0]] * 10)
                svc.on_sigusr1()
                svc.poll()
                f = final(self.data)
                self.assertEqual((f["success"], f["live_rule"], f["finalized"]), (False, False, True), extra)
                self.assertNotIn("finalize_error", f)

    def test_a_simulator_that_cannot_hash_at_the_end_keeps_the_verdict(self):
        sim = FakeSim(goal=99)
        svc = self.service(sim)
        self.submit(svc, [[0.5]] * 3)

        def broken():
            raise RuntimeError("the episode's error broke the simulator")
        sim.state_sha = broken
        svc.on_sigusr1()
        svc.poll()
        f = final(self.data)
        self.assertEqual((f["finalized"], f["graded_by"], f["state_sha"], f["reason"]), (True, "live", None, "timeout"))
        self.assertNotIn("finalize_error", f)

    def test_live_verdict_that_raises_takes_the_success_away(self):
        sim = FakeSim()

        def boom(rows, success):
            raise RuntimeError("the settle went unstable")
        sim.live_verdict = boom
        svc = self.service(sim)
        self.submit(svc, [[1.0]] * 10)
        svc.on_sigusr1()
        svc.poll()
        f = final(self.data)
        self.assertEqual((f["success"], f["live_rule"], f["finalized"], f["video"]), (False, False, True, True))
        self.assertIn("unstable", f["live_verdict_error"])
        self.assertNotIn("finalize_error", f)

    def test_the_verdict_is_on_disk_even_when_the_video_fails(self):
        svc = self.service(FakeSim(video_raises=True))
        self.submit(svc, [[1.0]] * 10)
        svc.on_sigusr1()
        svc.poll()
        f = final(self.data)
        self.assertEqual((f["finalized"], f["graded_by"], f["video"]), (True, "live", False))
        self.assertEqual((f["success"], f["video_pending"]), (True, False))
        self.assertNotIn("infra_error", f)                   # a lost video is never infrastructure
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
        self.assertEqual((seen["finalized"], seen["success"], seen["live_success"], seen["graded_by"]),
                         (True, True, True, "live"))
        self.assertEqual((seen["video"], seen["video_pending"]), (False, True))
        f = final(self.data)
        self.assertEqual((f["finalized"], f["success"], f["video"], f["video_pending"]), (True, True, True, False))
        self.assertEqual({k: f[k] for k in seen if k not in ("video", "video_pending")},
                         {k: seen[k] for k in seen if k not in ("video", "video_pending")})   # nothing else moved

    def test_a_failed_finalize_waits_for_no_video(self):
        svc = self.service(FakeSim(save_raises=RuntimeError("disk full")))
        self.submit(svc, [[1.0]] * 3)
        svc.on_sigusr1()
        svc.poll()
        f = final(self.data)
        self.assertEqual((f["finalized"], f["video_pending"]), (True, False))
        self.assertFalse(os.path.exists(os.path.join(self.data, "replay.mp4")))

    def test_a_failing_finalize_is_recorded_not_raised(self):
        svc = self.service(FakeSim(save_raises=RuntimeError("disk full")))
        self.submit(svc, [[1.0]] * 3)
        svc.on_sigusr1()
        svc.poll()
        f = final(self.data)
        self.assertEqual((f["finalized"], f["success"]), (True, False))
        self.assertIn("disk full", f["finalize_error"])

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

    def test_a_fatal_signal_between_calls_stays_infrastructure_in_2_1(self):
        """2.1 keeps its in-call rule: crash.log's record of a segfault between calls is logged, not the agent's."""
        if not hasattr(rcb_service, "enable_crash_log"):
            self.skipTest("a variant without the crash log")
        import signal
        svc = self.service(FakeSim(goal=99))
        self.submit(svc, [[0.5]])
        code = ("import os, sys; sys.path.insert(0, sys.argv[1]); import rcb_service; "
                "rcb_service.enable_crash_log(sys.argv[2]); os.kill(os.getpid(), int(sys.argv[3]))")
        for i in range(3):
            r = subprocess.run([sys.executable, "-c", code, str(STANDARD), self.data, str(int(signal.SIGSEGV))],
                               capture_output=True, timeout=60)
            self.assertEqual(r.returncode, -signal.SIGSEGV)
            if i < 2:
                self.service(FakeSim(goal=99))
        with self.assertRaises(GiveUp):
            self.service(FakeSim(goal=99))
        self.assertEqual([e["fatal_signal"] for e in events(self.data) if e["ev"] == "resuming"], [True, True])
        f = final(self.data)
        self.assertEqual((f["reason"], f["infra_error"]), ("sim_crashed", 1))
        self.assertIn(b"Fatal Python error", Path(self.data, "crash.log").read_bytes())

    def die_in_a_call(self, path: str) -> None:
        """A process that died natively serving a call (no finally ran: call_begin without call_end)."""
        with open(os.path.join(self.data, "episode.jsonl"), "a") as f:
            f.write(json.dumps({"ts": time.time(), "ev": "call_begin", "path": path, "call": 99}) + "\n")

    def test_crashes_after_a_success_keep_it(self):
        """Review round 3: three /observe calls dying after the episode succeeded gave the agent a 0 (sim_crashed_on_call).
        The outcome was decided: the restart past the limit finalizes it as it ended."""
        svc = self.service(FakeSim(goal=0.3))
        self.submit(svc, [[1.0]] * 3)
        for i in range(3):
            self.die_in_a_call("/observe")
            if i < 2:
                self.service(FakeSim(goal=0.3))
        with self.assertRaises(GiveUp) as ctx:
            self.service(FakeSim(goal=0.3))
        self.assertTrue(str(ctx.exception).startswith("restarted after finalize"))
        f = final(self.data)
        self.assertEqual((f["finalized"], f["success"], f["live_success"], f["graded_by"], f["reason"]),
                         (True, True, True, "live", "success"))
        self.assertNotIn("infra_error", f)
        self.assertEqual([e["crashed_in_call"] for e in events(self.data) if e["ev"] == "resuming"], [False] * 3)

    def test_crashes_after_a_final_failure_keep_the_zero_not_infrastructure(self):
        svc = self.service(FakeSim(goal=99))
        self.submit(svc, [[1.0]] * 60)                       # the steps run out: failed, no reset to come
        for i in range(3):
            self.die_in_a_call("/observe")
            if i < 2:
                self.service(FakeSim(goal=99))
        with self.assertRaises(GiveUp):
            self.service(FakeSim(goal=99))
        f = final(self.data)
        self.assertEqual((f["finalized"], f["success"], f["reason"], f["graded_by"]), (True, False, "failed", "live"))
        self.assertNotIn("infra_error", f)

    def test_crashes_after_a_failure_with_resets_left_are_not_the_agents(self):
        """The episode ended but a reset could follow: the outcome is not decided, and a crash in a call after the
        episode's end does not count as the agent's (only deaths before it do)."""
        svc = self.service(FakeSim(goal=99), reset_budget=2)
        self.submit(svc, [[1.0]] * 60)
        for i in range(3):
            self.die_in_a_call("/observe")
            if i < 2:
                self.service(FakeSim(goal=99), reset_budget=2)
        with self.assertRaises(GiveUp):
            self.service(FakeSim(goal=99), reset_budget=2)
        f = final(self.data)
        self.assertEqual((f["reason"], f["infra_error"]), ("sim_crashed", 1))

    def test_crashes_inside_a_reset_are_infrastructure(self):
        """A native death in /reset is the scene's rebuild failing, as a Python error there is (review round 3)."""
        svc = self.service(FakeSim(goal=99), reset_budget=5)
        self.submit(svc, [[0.5]])
        for i in range(3):
            self.die_in_a_call("/reset")
            if i < 2:
                self.service(FakeSim(goal=99), reset_budget=5)
        with self.assertRaises(GiveUp):
            self.service(FakeSim(goal=99), reset_budget=5)
        f = final(self.data)
        self.assertEqual((f["reason"], f["infra_error"]), ("sim_crashed", 1))

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
        svc = self.service(FakeSim(save_raises=RuntimeError("disk full")))
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
        self.assertEqual((f["finalized"], f["success"], f["live_success"], f["graded_by"], f["replays"], f["video"]),
                         (True, True, True, "live", 0, False))
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
        self.assertEqual((f["finalized"], f["success"], f["graded_by"], f["video"]), (True, True, "live", False))

    def test_a_verdict_of_a_replaying_service_is_kept_too(self):
        """A final.json of the service before board 0151 (deterministic, no graded_by): a restart keeps it."""
        svc = self.service()
        self.submit(svc, [[1.0]] * 10)
        Path(self.data, "final.json").write_text(json.dumps({"success": True, "live_success": True,
                                                             "replay_success": True, "deterministic": True}))
        with self.assertRaises(GiveUp):
            self.service()
        self.assertTrue(final(self.data)["deterministic"])

    def test_a_timeout_survives_a_crash_during_finalize(self):
        svc = self.service(FakeSim(goal=99, save_raises=Crash()))
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
        self.assertEqual((f["finalized"], f["graded_by"], f["n_actions"], f["reason"], f["success"]),
                         (True, "live", 2, "timeout", False))

    def test_a_crash_in_live_verdict_is_the_episodes_zero_after_the_restart(self):
        """The process dies in the settle window (a native crash would repeat on every resume): the restarted service
        resumes the episode from the journal (the crash-recovery replay, not a grading one) and records the hook as
        failed, a 0, never infrastructure."""
        def crash(rows, success):
            raise Crash()
        sim = FakeSim()
        sim.live_verdict = crash
        svc = self.service(sim)
        self.submit(svc, [[1.0]] * 10)
        svc.on_sigusr1()
        with self.assertRaises(Crash):
            svc.poll()
        self.assertFalse(final(self.data)["finalized"])
        sim2 = FakeSim()
        called = []
        sim2.live_verdict = lambda rows, success: called.append(1) or {"success": True}
        svc2 = self.service(sim2)
        svc2.on_sigusr1()
        svc2.poll()
        f = final(self.data)
        self.assertEqual((f["finalized"], f["success"], f["live_rule"], f["graded_by"], f["live_success"]),
                         (True, False, False, "live", True))
        self.assertTrue(f["live_verdict_error"].startswith("crashed"))   # not run again: it would die again
        self.assertNotIn("infra_error", f)
        self.assertEqual((called, sim2.replays), ([], 0))

    def test_the_clock_survives_a_restart(self):
        svc = self.service()
        call(svc, "GET", "/spec")
        t0 = svc.t0
        svc2 = self.service()
        self.assertEqual(svc2.t0, t0)


class StartState(Base):
    """The frozen initial state is checked on the live simulator when an episode begins (no replay checks it later)."""

    def test_a_scene_at_the_recorded_start_is_served(self):
        sim = FakeSim()
        sim.start_sha = sim.state_sha()
        svc = self.service(sim)
        self.assertEqual(self.submit(svc, [[1.0]] * 10)[0], 200)
        svc.on_sigusr1()
        svc.poll()
        self.assertEqual(final(self.data)["success"], True)

    def test_a_scene_off_the_recorded_start_gives_up_as_infrastructure(self):
        sim = FakeSim()
        sim.start_sha = "0123456789ab"
        with self.assertRaises(GiveUp) as ctx:
            self.service(sim)
        self.assertIn("instance_mismatch", str(ctx.exception))
        f = final(self.data)
        self.assertEqual((f["finalized"], f["success"], f["infra_error"]), (True, False, 1))
        self.assertTrue(f["reason"].startswith("instance_mismatch"))
        self.assertNotIn("start", [e["ev"] for e in events(self.data)])   # no episode began: the agent was never served
        self.assertTrue(Path(self.data, "server.pid").exists())

    def test_a_build_that_refuses_the_instance_gives_up_as_infrastructure(self):
        def build():
            raise rcb_service.InstanceMismatch("seed 3 no longer builds this scene")
        os.environ["RCB_DATA"] = self.data
        refused = []
        real = rcb_service.refuse_forever
        rcb_service.refuse_forever = lambda reason, port=8000: (refused.append(reason), sys.exit(0))
        try:
            with self.assertRaises(SystemExit):
                rcb_service.main(build)
        finally:
            rcb_service.refuse_forever = real
            os.environ.pop("RCB_DATA")
        f = final(self.data)
        self.assertEqual((f["finalized"], f["success"], f["infra_error"]), (True, False, 1))
        self.assertTrue(f["reason"].startswith("instance_mismatch: seed 3"), f["reason"])
        self.assertEqual(len(refused), 1)

    def test_a_graded_episode_begun_by_a_reset_off_the_start_is_void(self):
        sim = FakeSim()
        sim.start_sha = sim.state_sha()
        svc = self.service(sim, reset_budget=2)
        self.submit(svc, [[0.5]] * 2)
        reset = sim.reset

        def bad_reset():
            reset()
            sim.x = 0.3                                      # the reset did not bring the scene back
        sim.reset = bad_reset
        code, body, _ = call(svc, "POST", "/reset")
        self.assertEqual((code, body["gave_up"]), (409, True))       # the service gives up at once
        self.assertTrue(body["reason"].startswith("instance_mismatch"))
        f = final(self.data)
        self.assertEqual((f["finalized"], f["success"], f["instance_mismatch"], f["infra_error"], f["video_pending"]),
                         (True, False, True, 1, False))
        self.assertTrue(f["reason"].startswith("instance_mismatch: a reset"))
        self.assertFalse([e for e in events(self.data) if e["ev"] == "reset"][0]["start_ok"])
        self.assertEqual(self.submit(svc, [[1.0]] * 10)[0], 409)    # nothing runs after it
        self.assertEqual(call(svc, "POST", "/reset")[1]["gave_up"], True)
        svc.on_sigusr1()
        svc.poll()
        self.assertEqual(final(self.data), f)                       # no verdict, no video comes after it

    def test_give_up_on_a_finalized_verdict_clears_video_pending(self):
        Path(self.data, "final.json").write_text(json.dumps({"finalized": True, "success": True, "video": False,
                                                             "video_pending": True, "graded_by": "live"}))
        rcb_service.give_up(self.data, "restarted after finalize", infra=False)
        f = final(self.data)
        self.assertEqual((f["success"], f["video_pending"], f.get("infra_error", 0)), (True, False, 0))

    def test_an_adapter_with_a_replay_is_refused(self):
        """A verify() the service never calls would drop its rule silently (board 0151): refused at build."""
        class Replaying(FakeSim):
            replay_free = False
        with self.assertRaises(TypeError):
            Service(Replaying(), data=self.data)

    def test_a_good_reset_keeps_the_episode_graded(self):
        sim = FakeSim()
        sim.start_sha = sim.state_sha()
        svc = self.service(sim, reset_budget=2)
        self.submit(svc, [[0.5]] * 2)
        self.assertEqual(call(svc, "POST", "/reset")[0], 200)
        self.submit(svc, [[1.0]] * 10)
        svc.on_sigusr1()
        svc.poll()
        f = final(self.data)
        self.assertEqual((f["success"], f.get("infra_error", 0)), (True, 0))

    def test_a_bad_reset_is_infrastructure_after_a_restart_too(self):
        sim = FakeSim(goal=99)
        sim.start_sha = sim.state_sha()
        svc = self.service(sim, reset_budget=2)
        self.submit(svc, [[0.5]] * 2)
        reset = sim.reset

        def bad_reset():
            reset()
            sim.x = 0.3
        sim.reset = bad_reset
        call(svc, "POST", "/reset")
        before = final(self.data)
        sim2 = FakeSim(goal=99)                              # a restart keeps the give-up as it is
        sim2.start_sha = sim2.state_sha()
        with self.assertRaises(GiveUp) as ctx:
            self.service(sim2, reset_budget=2)
        self.assertEqual(str(ctx.exception), "restarted after finalize")
        f = final(self.data)
        self.assertEqual(f, before)
        self.assertTrue(f["reason"].startswith("instance_mismatch: a reset"))


class AgentClock(Base):
    """meta time_s / time_left_s: the agent's clock. Harbor counts the agent's cutoff around the agent's run only, and
    the sidecar is up before that, so the clock starts at the agent's first request, never with the service."""

    def test_it_starts_at_the_first_request_not_with_the_service(self):
        svc = self.service(FakeSim(goal=99))                        # started and ready; nobody has asked anything
        time.sleep(0.7)                                             # ... while the harness is being installed
        self.assertIsNone(svc.t0)
        self.assertFalse([e for e in events(self.data) if e["ev"] == "first_request"])
        t = time.time()
        code, spec, _ = call(svc, "GET", "/spec")                   # the first request, whatever the endpoint
        self.assertIn("first request", spec["clock"])
        code, meta, _ = call(svc, "POST", "/observe", {"seconds": 0, "video": "none"})
        lag = time.time() - t
        self.assertLessEqual(meta["time_s"], lag + 0.05)
        self.assertGreaterEqual(meta["time_left_s"], 3600.0 - lag - 0.2)
        self.assertEqual(len([e for e in events(self.data) if e["ev"] == "first_request"]), 1)

    def test_a_resume_does_not_set_it_back(self):
        svc = self.service(FakeSim(goal=99))
        code, m0, _ = self.submit(svc, [[0.5]] * 2)
        time.sleep(0.7)
        svc2 = self.service(FakeSim(goal=99))                       # the restarted process resumes the episode
        self.assertEqual(svc2.t0, svc.t0)
        code, m1, _ = call(svc2, "POST", "/observe", {"seconds": 0, "video": "none"})
        self.assertGreaterEqual(m1["time_s"], m0["time_s"] + 0.7)
        self.assertLessEqual(m1["time_left_s"], m0["time_left_s"] - 0.7)
        self.assertEqual(len([e for e in events(self.data) if e["ev"] == "first_request"]), 1)


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
        f = final(self.data)
        self.assertEqual(f["reason"], "error")
        ends = [e for e in events(self.data) if e["ev"] == "end"]
        self.assertTrue(ends[-1].get("reset_failed"), ends)
        if hasattr(rcb_service, "RESERVED"):                 # the live layer (board 0151; not LIBERO-MAX's variant yet):
            svc.on_sigusr1()                                 # the agent's reset was legitimate, so infrastructure
            svc.poll()
            self.assertEqual((f.get("infra_error"), final(self.data).get("infra_error")), (1, 1))

    def test_an_error_the_agents_call_raised_is_its_zero(self):
        def boom(s):
            if s.t == 2:
                raise ValueError("the simulator refused a step")
        svc = self.service(FakeSim(goal=99, on_step=boom))
        self.assertEqual(self.submit(svc, [[0.1]] * 5)[0], 500)
        svc.on_sigusr1()
        svc.poll()
        f = final(self.data)
        self.assertEqual((f["reason"], f.get("infra_error", 0), f["finalized"]), ("error", 0, True))


class Grade(Base):
    def grade(self, fin: dict | None) -> tuple[str, dict]:
        logs = os.path.join(self.data, "logs")
        if fin is not None:
            Path(self.data, "final.json").write_text(json.dumps(fin))
        env = {**os.environ, "RCB_DATA": self.data, "RCB_VERIFIER_LOG_DIR": logs}
        subprocess.run([sys.executable, str(STANDARD / "grade.py")], env=env, check=True, capture_output=True)
        return Path(logs, "reward.txt").read_text().strip(), json.loads(Path(logs, "reward.json").read_text())

    WIN = {"finalized": True, "success": True, "live_success": True, "graded_by": "live", "replays": 0,
           "n_actions": 10, "calls": 3, "rows": 12, "control_steps": 10, "elapsed_s": 5.0, "video": True,
           "reason": "success", "sim_startups": 1}

    def test_success_is_the_live_verdict(self):
        txt, r = self.grade(self.WIN)
        self.assertEqual((txt, r["success"], r["live_success"], r["infra_error"], r["video_rendered"]), ("1", 1, 1, 0, 1))
        self.assertEqual((r["graded_by_live"], r["replays"], r["live_rule"]), (1, 0, 1))
        self.assertFalse({"replay_success", "deterministic"} & set(r))
        for k in ("live_success", "success"):
            txt, r = self.grade({**self.WIN, k: False})
            self.assertEqual((txt, r["success"], r["infra_error"]), ("0", 0, 0), k)
        txt, r = self.grade({k: v for k, v in self.WIN.items() if k != "graded_by"})   # no verdict was written
        self.assertEqual((txt, r["success"]), ("0", 0))
        self.assertTrue(all(isinstance(v, (int, float)) for v in r.values()))

    def test_a_failed_settle_is_a_zero_not_infrastructure(self):
        txt, r = self.grade({**self.WIN, "success": False, "live_rule": False})
        self.assertEqual((txt, r["success"], r["live_success"], r["live_rule"], r["infra_error"]), ("0", 0, 1, 0, 0))
        txt, r = self.grade({**self.WIN, "success": False, "live_rule": False, "live_verdict_error": "unstable"})
        self.assertEqual((r["success"], r["live_verdict_error"], r["infra_error"]), (0, 1, 0))

    def test_a_scene_off_the_frozen_start_is_infrastructure(self):
        txt, r = self.grade({"finalized": True, "success": False, "done": True, "infra_error": 1,
                             "reason": "instance_mismatch: the scene started at x, the frozen instance records y"})
        self.assertEqual((r["success"], r["infra_error"], r["instance_mismatch"]), (0, 1, 1))
        txt, r = self.grade({**self.WIN, "success": False, "instance_mismatch": True, "infra_error": 1})
        self.assertEqual((r["success"], r["infra_error"], r["instance_mismatch"]), (0, 1, 1))

    def test_a_crash_inside_the_agents_calls_is_a_zero_not_infrastructure(self):
        txt, r = self.grade({"finalized": True, "success": False, "done": True, "reason": "sim_crashed_on_call"})
        self.assertEqual((txt, r["success"], r["infra_error"], r["sim_crashed_on_call"]), ("0", 0, 0, 1))

    def test_every_branch_writes_the_same_keys(self):
        _, ok = self.grade(self.WIN)
        _, missing = self.grade(None)
        Path(self.data, "final.json").write_text("[1]")
        _, broken = self.grade(None)
        self.assertEqual(set(missing), set(ok))
        self.assertEqual(set(broken), set(ok))

    def test_a_missing_log_is_infrastructure(self):
        txt, r = self.grade(None)
        self.assertEqual((txt, r["success"], r["missing_log"], r["infra_error"]), ("0", 0, 1, 1))
        self.assertEqual((r["live_success"], r["graded_by_live"], r["sim_error"], r["grader_error"]), (0, 1, 0, 0))

    def test_an_unreadable_log_is_infrastructure(self):
        for text in ('{"finalized": true, "live_succ', "[1, 2]", "null", ""):
            Path(self.data, "final.json").write_text(text)
            txt, r = self.grade(None)
            self.assertEqual((txt, r["success"], r["live_success"], r["infra_error"], r["grader_error"]),
                             ("0", 0, 0, 1, 1), text)

    def test_a_simulator_error_is_reported(self):
        txt, r = self.grade({**self.WIN, "success": False, "live_success": False, "reason": "error"})
        self.assertEqual((r["success"], r["sim_error"], r["infra_error"]), (0, 1, 0))   # the agent's call raised it
        txt, r = self.grade({**self.WIN, "success": False, "live_success": False, "reason": "failed"})
        self.assertEqual(r["sim_error"], 0)

    def test_a_verdict_whose_video_never_came_stands(self):
        """The collect hook ran out of time while the video rendered: finalized, video_pending still true."""
        txt, r = self.grade({**self.WIN, "video": False, "video_pending": True})
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
        txt, r = self.grade({**self.WIN, "success": False, "live_success": False, "n_actions": 10,
                             "control_steps_total": 34, "resets": 2, "reset_budget": 50})
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
