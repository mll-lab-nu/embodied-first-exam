"""Tests for the realtime service (shared/realtime/rcb_realtime.py) and its client, over real HTTP, against the toy
simulator of test_standard_service.py: no MuJoCo, no GPU, a few seconds.

    python -m unittest discover -s scripts/humanoidbench/tests     # needs numpy and requests
"""
from __future__ import annotations

import importlib.util
import json
import sys
import tempfile
import threading
import time
import unittest
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from test_standard_service import FakeSim  # noqa: E402   (puts shared/standard/ on sys.path)

REALTIME = HERE.parents[0] / "shared" / "realtime"
sys.path.append(str(REALTIME))                     # appended: `import rcb_client` elsewhere stays the standard client
import rcb_realtime  # noqa: E402

_spec = importlib.util.spec_from_file_location("rcb_client_realtime", REALTIME / "rcb_client.py")
rcb_client_realtime = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(rcb_client_realtime)
EpisodeOver, Robot = rcb_client_realtime.EpisodeOver, rcb_client_realtime.Robot


class FastSim(FakeSim):
    """The toy point at 100 Hz, with a goal it never reaches unless a test wants it to."""
    control_dt, max_control_steps = 0.01, 300

    def __init__(self, goal: float = 1e9):
        super().__init__(goal)


class Live(unittest.TestCase):
    """A realtime service on a free port: its simulator loop and its HTTP server each in a thread."""

    goal, reset_budget = 1e9, 2

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.data = self.tmp.name
        self.start_service()

    def start_service(self):
        self.svc = rcb_realtime.RealtimeService(self.make_sim(), data=self.data, reset_budget=self.reset_budget,
                                                slowdown=1.0)
        self.svc.start()
        self.srv = self.svc.http_server(("127.0.0.1", 0))
        self.stop = threading.Event()
        self.threads = [threading.Thread(target=self.srv.serve_forever, daemon=True),
                        threading.Thread(target=self.svc.loop, args=(self.stop,), daemon=True)]
        for t in self.threads:
            t.start()
        self.r = Robot(f"http://127.0.0.1:{self.srv.server_address[1]}", timeout=10)

    def make_sim(self):
        return FastSim(self.goal)

    def stop_service(self):
        self.stop.set()
        self.threads[1].join(5)
        self.srv.shutdown()
        self.srv.server_close()

    def tearDown(self):
        self.stop_service()
        self.tmp.cleanup()

    def finalize(self) -> dict:
        self.svc.on_sigusr1()
        for _ in range(100):
            fin = json.loads(Path(self.data, "final.json").read_text())
            if fin.get("finalized"):
                return fin
            time.sleep(0.05)
        self.fail("never finalized")

    def journal(self) -> np.ndarray:
        return np.fromfile(Path(self.data, "trajectory_live.f64"), dtype=np.float64).reshape(-1, 1)

    def ticks(self) -> np.ndarray:
        return np.fromfile(Path(self.data, "ticks.f64"), dtype=np.float64).reshape(-1, 2)


class TestClock(Live):
    def test_spec_declares_the_realtime_timing(self):
        t = self.r.spec()["timing"]
        self.assertTrue(t["realtime"])
        self.assertEqual(t["slowdown"], 1.0)
        self.assertAlmostEqual(t["wall_s_per_control_step"], 0.01)
        self.assertEqual(self.r.spec()["protocol"], "eai-standard/2.3")

    def test_an_episode_waits_paused_until_its_first_submit(self):
        self.r.get_obs()
        time.sleep(0.15)
        st = self.r.status()
        self.assertEqual(st["control_steps"], 0)
        self.assertFalse(st["running"])

    def test_time_runs_after_the_first_submit_and_the_last_target_is_held(self):
        res = self.r.submit("move", [[0.5]] * 3, interpolate="hold", cameras=[])
        self.assertEqual(res.meta["start_step"], 0)
        self.assertTrue(res.meta["running"])
        self.assertEqual(res.last, {})                       # cameras=[]: no images
        self.assertEqual(res.proprio.shape, (1, 2))
        time.sleep(0.3)
        st = self.r.status()
        self.assertTrue(20 <= st["control_steps"] <= 40, st)  # about 30 steps at 100 Hz
        res = self.r.get_obs(cameras=[])
        self.assertAlmostEqual(res.meta["proprio"]["now"][1], 0.5)   # the command still in force: held
        self.assertGreater(self.svc.held_steps, 10)

    def test_a_watch_returns_what_ran_meanwhile(self):
        self.r.submit("move", [[1.0]], cameras=[])
        res = self.r.get_obs(cameras=["cam"], seconds=0.1, video="frames", video_fps=30)
        self.assertEqual(res.meta["control_steps_watch"], 10)
        self.assertGreaterEqual(len(res.frames["cam"]), 3)

    def test_a_watch_starts_the_clock(self):
        res = self.r.get_obs(cameras=[], seconds=0.05)
        self.assertEqual(res.meta["control_steps_watch"], 5)
        self.assertTrue(self.r.status()["running"])


class TestPlan(Live):
    def test_a_chunk_at_a_future_step_keeps_what_is_planned_before_it(self):
        self.r.submit("move", [[1.0]] * 30, interpolate="hold", cameras=[])
        res = self.r.submit("move", [[-1.0]] * 5, interpolate="hold", at=20, cameras=[])
        self.assertEqual(res.meta["start_step"], 20)
        self.assertEqual(res.meta["plan_end_step"], 25)
        time.sleep(0.4)
        fin = self.finalize()
        j = self.journal()[:, 0]
        np.testing.assert_array_equal(j[:20], 1.0)
        np.testing.assert_array_equal(j[20:25], -1.0)
        np.testing.assert_array_equal(j[25:], -1.0)        # then held
        self.assertTrue(fin["deterministic"])
        self.assertEqual(fin["realtime"], 1)

    def test_a_late_chunk_drops_the_rows_whose_steps_are_gone(self):
        self.r.submit("move", [[0.0]], cameras=[])
        time.sleep(0.1)
        res = self.r.submit("move", np.linspace(0.01, 1.0, 100)[:, None], interpolate="hold", at=0, cameras=[])
        late = res.meta["late_steps"]
        self.assertGreater(late, 5)
        self.assertEqual(res.meta["start_step"], res.meta["control_steps"])
        time.sleep(0.05)
        self.finalize()
        j = self.journal()[:, 0]
        self.assertAlmostEqual(j[res.meta["control_steps"]], np.linspace(0.01, 1.0, 100)[late])

    def test_linear_starts_from_the_target_in_force_before_at(self):
        self.r.submit("move", [[0.0]] * 10, interpolate="hold", cameras=[])
        self.r.submit("move", [[1.0]], dt=0.04, interpolate="linear", at=8, cameras=[])
        time.sleep(0.2)
        self.finalize()
        np.testing.assert_allclose(self.journal()[8:12, 0], [0.25, 0.5, 0.75, 1.0])

    def test_at_too_far_ahead_or_malformed_is_400(self):
        for at in (10_000, -1, 1.5, "x"):
            with self.assertRaises(ValueError):
                self.r._post("/submit", {"type": "move", "actions": [[0.1]], "at": at}, [], timeout=10)
        self.assertEqual(self.r.status()["calls"], 0)

    def test_the_tick_log_lines_up_with_the_journal(self):
        self.r.submit("move", [[0.2]] * 5, cameras=[])
        time.sleep(0.2)
        self.finalize()
        ticks, journal = self.ticks(), self.journal()
        self.assertEqual(len(ticks), len(journal))
        np.testing.assert_array_equal(ticks[:5, 1], 1.0)    # call 1's chunk
        self.assertTrue(np.all(ticks[5:, 1] == -1.0))       # then held
        self.assertTrue(np.all(np.diff(ticks[:, 0]) >= 0))
        self.assertTrue(Path(self.data, "calls.jsonl").read_text().strip())
        self.assertEqual(np.fromfile(Path(self.data, "submitted.f64")).reshape(-1, 2).tolist(), [[1.0, 0.2]] * 5)


class TestEnd(Live):
    goal = 0.5

    def test_success_stops_the_clock_and_submit_is_409(self):
        self.r.submit("move", [[1.0]] * 10, interpolate="hold", cameras=[])
        time.sleep(0.15)
        st = self.r.status()
        self.assertTrue(st["done"])
        self.assertEqual(st["reason"], "success")
        self.assertFalse(st["running"])
        self.assertEqual(st["control_steps"], 5)
        with self.assertRaises(EpisodeOver):
            self.r.submit("move", [[1.0]], cameras=[])
        fin = self.finalize()
        self.assertTrue(fin["success"])
        self.assertEqual(fin["protocol"], "eai-standard/2.3")
        self.assertNotIn("infra_error", fin)

    def test_a_watch_ends_with_the_episode(self):
        self.r.submit("move", [[1.0]] * 10, interpolate="hold", cameras=[])
        res = self.r.get_obs(cameras=[], seconds=1.0)
        self.assertTrue(res.done)
        self.assertLess(res.meta["control_steps_watch"], 10)


class TestSimulatorError(Live):
    """PROTOCOL §4b: a simulator error that ends the graded episode is infrastructure, not the agent's failure."""

    def make_sim(self):
        def boom(sim):
            if sim.t == 5:
                raise RuntimeError("simulator blew up")
        sim = FastSim(self.goal)
        sim.on_step = boom
        return sim

    def test_a_simulator_error_is_an_infra_error(self):
        self.r.submit("move", [[1.0]] * 10, interpolate="hold", cameras=[])
        time.sleep(0.15)
        st = self.r.status()
        self.assertTrue(st["done"])
        self.assertEqual(st["reason"], "error")
        fin = self.finalize()
        self.assertEqual(fin["infra_error"], 1)
        self.assertFalse(fin["success"])


class TestResetAndResume(Live):
    def test_a_reset_starts_a_paused_episode(self):
        self.r.submit("move", [[0.3]], cameras=[])
        time.sleep(0.1)
        res = self.r.reset(cameras=["cam"])
        self.assertEqual(res.meta["control_steps"], 0)
        self.assertFalse(res.meta["running"])
        self.assertEqual(res.meta["episode"], 2)
        time.sleep(0.1)
        self.assertEqual(self.r.status()["control_steps"], 0)

    def test_a_restart_resumes_the_same_episode_paused(self):
        self.r.submit("move", [[0.1]] * 400, interpolate="hold", cameras=[])
        time.sleep(1.3)                                      # past the first checkpoint (one per second of robot time)
        self.stop_service()
        n_ticks = len(self.ticks())
        self.start_service()
        st = self.r.status()
        self.assertFalse(st["running"])
        self.assertGreaterEqual(st["control_steps"], 100)
        self.assertEqual(st["control_steps"] % 100, 0)       # back at the last checkpoint
        self.assertEqual(len(self.ticks()), self.svc.journal_rows)
        self.assertLessEqual(len(self.ticks()), n_ticks)



class SlowSim(FastSim):
    """The toy point, its every step slower than its control_dt: the service is behind its clock the whole time."""

    def step(self, row):
        time.sleep(0.015)                                    # 15 ms of work per 10 ms control step
        return super().step(row)


class BehindTheClock(Live):
    """A simulator slower than real time must not starve requests (before the fix they waited for the next stall,
    MAX_LAG_S of debt = 0.5 s or more)."""

    def make_sim(self):
        return SlowSim(self.goal)

    def test_requests_are_served_while_behind(self):
        self.r.submit("move", [[0.0]], cameras=[])           # starts the clock
        waits = []
        for _ in range(10):
            t = time.monotonic()
            self.r.status()
            waits.append(time.monotonic() - t)
        self.assertTrue(self.svc.running)
        self.assertGreater(self.svc.lag, 0.0)               # it is behind
        self.assertLess(max(waits), 0.2, waits)              # and still answers within about a step
        self.assertLess(self.svc.max_queue_wait, 0.2)
        self.assertIn("max_queue_wait_s", self.svc._timing_record())


if __name__ == "__main__":
    unittest.main()
