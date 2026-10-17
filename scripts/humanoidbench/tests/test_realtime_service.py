"""Tests for the realtime service (shared/realtime/rcb_realtime.py) and its client, over real HTTP, against the toy
simulator of test_standard_service.py: no MuJoCo, no GPU, a few seconds.

    python -m unittest discover -s scripts/humanoidbench/tests     # needs numpy and requests
"""
from __future__ import annotations

import importlib.util
import json
import signal
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
import rcb_service  # noqa: E402

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
        self.assertEqual((fin["graded_by"], fin["replays"], fin["realtime"]), ("live", 0, 1))
        self.assertNotIn("deterministic", fin)
        self.assertEqual(self.svc.sim.replays, 0)            # the verdict is the live episode's: nothing replayed

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
        self.assertEqual((fin["success"], fin["live_success"], fin["graded_by"], fin["replays"]), (True, True, "live", 0))
        self.assertEqual(fin["protocol"], "eai-standard/2.3")
        self.assertNotIn("infra_error", fin)
        self.assertEqual(self.svc.sim.replays, 0)

    def test_live_verdict_can_take_the_success_away(self):
        """A settle window on the live simulator, run after the clock stopped (live_verdict); the verdict stays live."""
        sim = self.svc.sim
        sim.live_verdict = lambda rows, success: {"success": False, "settled": 0}
        self.r.submit("move", [[1.0]] * 10, interpolate="hold", cameras=[])
        time.sleep(0.15)
        fin = self.finalize()
        self.assertEqual((fin["live_success"], fin["live_rule"], fin["success"], fin["settled"]), (True, False, False, 0))
        self.assertNotIn("infra_error", fin)

    def test_a_watch_ends_with_the_episode(self):
        self.r.submit("move", [[1.0]] * 10, interpolate="hold", cameras=[])
        res = self.r.get_obs(cameras=[], seconds=1.0)
        self.assertTrue(res.done)
        self.assertLess(res.meta["control_steps_watch"], 10)


class TestSimulatorError(Live):
    """A simulator error raised by a control step after the agent's first command is the agent's 0 (owner, 2026-10-17;
    STANDARD_MODE Part 3; before, every error that ended the graded episode was infrastructure)."""

    def make_sim(self):
        def boom(sim):
            if sim.t == 5:
                raise RuntimeError("simulator blew up")
        sim = FastSim(self.goal)
        sim.on_step = boom
        return sim

    def test_an_error_after_the_first_command_is_the_agents(self):
        self.r.submit("move", [[1.0]] * 10, interpolate="hold", cameras=[])
        time.sleep(0.15)
        st = self.r.status()
        self.assertTrue(st["done"])
        self.assertEqual(st["reason"], "error")
        fin = self.finalize()
        self.assertNotIn("infra_error", fin)
        self.assertFalse(fin["success"])
        self.assertIn("first_command", [json.loads(x)["ev"] for x in Path(self.data, "episode.jsonl").read_text().splitlines()])

    def test_an_error_before_any_command_is_infrastructure(self):
        """The clock started by a watch (get_obs(seconds)): only held steps ran, none the agent planned."""
        try:
            self.r.get_obs(cameras=[], seconds=0.2)          # held steps; the fifth raises
        except Exception:  # noqa: BLE001 -- the watch may end with the episode or answer 500
            pass
        time.sleep(0.1)
        fin = self.finalize()
        self.assertEqual((fin["reason"], fin.get("infra_error")), ("error", 1))


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



class SportSim:
    """A simulator with several action types, as RoboOlympics' adapter (rcb_olympics.Olympics) has them: one
    interpolable target (`mallet`, 2 values: held until replaced) and commands that are not targets (`stroke` 10 values,
    `toss` 4, `stop` 1: one row is one command, issued at its control step). As there: clip() turns a one-value command
    into [1], command() is the current target for `mallet` and zeros otherwise, hold() is a row of its own type that
    issues nothing, and to_sim() reads a row by its type's layout -- so a row planned under the wrong type raises, and
    the episode would end "error" (infra_error)."""
    control_dt, max_control_steps = 0.01, 10_000
    cameras, depth_cameras = ("cam",), ()
    proprio_layout = ["step", "mallet_x", "mallet_y"]
    raw_dim = 3
    DIMS = {"mallet": 2, "stroke": 10, "toss": 4, "stop": 1}
    replay_free = True     # its verify() raises: nothing may call it

    def __init__(self):
        self.reset()

    def spec(self) -> dict:
        return {"simulator": "sport", "robot": "arm", "task_text": "play", "episode": "ends at the wall clock",
                "action_types": {k: {"dim": d} for k, d in self.DIMS.items()}, "cameras": {"cam": {"hw": [2, 2]}}}

    def interpolable(self, typ: str) -> bool:
        return typ == "mallet"

    def images(self, cameras, depth):
        return {c: np.zeros((2, 2, 3), np.uint8) for c in cameras}, {}

    def proprio(self) -> np.ndarray:
        return np.array([self.t, *self.target], np.float32)

    def clip(self, typ, rows):
        if self.DIMS[typ] == 1:
            return np.ones((len(rows), 1)), []
        return np.array(rows, dtype=np.float64), []

    def command(self, typ) -> np.ndarray:
        return np.array(self.target) if typ == "mallet" else np.zeros(self.DIMS[typ])

    def hold(self):
        return "hold", np.zeros(1)

    def to_sim(self, typ, row) -> np.ndarray:
        row = np.asarray(row, dtype=np.float64)
        if typ == "hold" or (typ != "mallet" and not np.any(row)):
            return np.array([-1.0, 0.0, 0.0])                # no command at this step
        if typ == "mallet":
            xy = (float(row[0]), float(row[1]))              # a row of another type's layout: IndexError
            if xy == tuple(self.target):
                return np.array([-1.0, 0.0, 0.0])            # the target in force: nothing new
            self.issued.append((self.t, "mallet", xy))
            return np.array([0.0, *xy])
        float(row[self.DIMS[typ] - 1])                       # the type's last column (IndexError if the row is short)
        if len(row) != self.DIMS[typ]:
            raise ValueError(f"a {typ} row with {len(row)} values")
        self.issued.append((self.t, typ, tuple(row.tolist())))
        return np.array([float(list(self.DIMS).index(typ)), 0.0, 0.0])

    def step(self, raw):
        if int(raw[0]) == 0:
            self.target = [float(raw[1]), float(raw[2])]
        self.t += 1
        return False, False, {}

    def reset(self) -> None:
        self.t, self.target, self.issued = 0, [0.0, 0.0], []

    def state_sha(self) -> str:
        return f"{self.t}:{self.target}"

    def verify(self, rows) -> dict:
        raise AssertionError("a grading replay ran: the standard modes are graded by the live episode (board 0151)")

    def save_trajectory(self, rows, path, meta) -> None:
        np.savez(path, rows=rows)

    def render_video(self, rows, path) -> None:
        Path(path).write_bytes(b"mp4")


class ByHand(unittest.TestCase):
    """A realtime service whose clock the test drives: requests through dispatch(), control steps through tick()."""

    reset_budget = 0

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.data = self.tmp.name
        self.sim = self.make_sim()
        self.svc = self.service(self.sim)

    def tearDown(self):
        self.tmp.cleanup()

    def make_sim(self):
        return SportSim()

    def service(self, sim):
        svc = rcb_realtime.RealtimeService(sim, data=self.data, reset_budget=self.reset_budget, slowdown=1000.0)
        svc.start()
        return svc

    def post(self, path: str, **meta):
        job = rcb_realtime._Job("POST", path, json.dumps(meta).encode())
        self.svc.dispatch(job)
        return job

    def submit(self, typ: str, rows, **meta) -> tuple[int, dict]:
        job = self.post("/submit", type=typ, actions=rows, cameras=[], **meta)
        if job.reply[0] == "raw":
            return job.reply[1], json.loads(job.reply[3])
        return 200, job.reply[1]

    def run_steps(self, n: int) -> None:
        for _ in range(n):
            self.svc.tick()

    def finalize(self) -> dict:
        self.svc.on_sigusr1()
        self.svc.poll()
        return json.loads(Path(self.data, "final.json").read_text())


STROKE, STROKE2 = [0.5] + [1.0] * 9, [0.7] + [2.0] * 9
TOSS = [0.0, -1.0, 1.0, 0.2]


class TestMixedActionTypes(ByHand):
    """A plan may hold rows of several action types (RoboOlympics). Before the fix a chunk interpolated from, and filled
    the gap before `at` with, whatever row the plan held there, of whatever type: toss then stroke was a 500 (numpy
    could not broadcast 4 values against 10), stop then mallet filled the gap with a one-value "mallet" row that broke
    the simulator at its step -- either way the match ended "error", infra_error = 1, on the agent's ordinary play."""

    def assert_played_on(self, steps: int) -> dict:
        self.assertFalse(self.svc.done, self.svc.reason)
        self.assertEqual(len(self.svc.episode), steps)
        fin = self.finalize()
        self.assertEqual((fin["reason"], fin["graded_by"], fin["replays"], fin["success"]), ("timeout", "live", 0, False))
        self.assertNotIn("infra_error", fin)
        return fin

    def test_badminton_a_toss_then_a_stroke_ahead(self):
        self.assertEqual(self.submit("toss", [TOSS])[0], 200)
        code, meta = self.submit("stroke", [STROKE], at=30)   # the toss row is still planned: its clock has not ticked
        self.assertEqual((code, meta["start_step"], meta["plan_end_step"]), (200, 30, 31))
        self.run_steps(40)
        self.assertEqual(self.sim.issued, [(0, "toss", tuple(TOSS)), (30, "stroke", tuple(STROKE))])
        self.assert_played_on(40)

    def test_badminton_the_stroke_sent_before_the_toss(self):
        self.assertEqual(self.submit("stroke", [STROKE], at=5)[0], 200)
        self.assertEqual(self.submit("toss", [TOSS], at=20)[0], 200)
        self.run_steps(25)
        self.assertEqual(self.sim.issued, [(5, "stroke", tuple(STROKE)), (20, "toss", tuple(TOSS))])
        self.assert_played_on(25)

    def test_a_command_at_an_earlier_step_replaces_the_later_plan(self):
        self.assertEqual(self.submit("stroke", [STROKE], at=10)[0], 200)
        self.assertEqual(self.submit("toss", [TOSS], at=1)[0], 200)   # from step 1 on the plan is the toss alone
        self.run_steps(15)
        self.assertEqual(self.sim.issued, [(1, "toss", tuple(TOSS))])
        self.assert_played_on(15)

    def test_airhockey_a_stop_then_a_mallet_target_ahead(self):
        self.assertEqual(self.submit("mallet", [[0.3, 0.1]])[0], 200)
        self.run_steps(2)
        self.assertEqual(self.submit("stop", [[1.0]])[0], 200)
        code, meta = self.submit("mallet", [[0.1, -0.5]], at=meta_at(self.svc, 3))
        self.assertEqual(code, 200)
        self.assertEqual([t for t, _, _ in self.svc.plan], ["stop", None, None, "mallet"])   # the gap: held steps
        self.run_steps(6)
        self.assertEqual(self.sim.issued, [(0, "mallet", (0.3, 0.1)), (2, "stop", (1.0,)), (5, "mallet", (0.1, -0.5))])
        self.assertEqual(self.sim.target, [0.1, -0.5])
        self.assert_played_on(8)

    def test_a_mallet_chunk_after_a_stop_interpolates_from_the_current_target(self):
        """Linear, 4 control steps a row, planned behind a `stop`: what the stop will leave in force is not known
        before it runs, so the ramp starts from the simulator's current mallet target (never from the stop's row)."""
        self.submit("mallet", [[0.4, 0.0]])
        self.run_steps(1)
        self.submit("stop", [[1.0]])
        code, meta = self.submit("mallet", [[0.8, 0.4]], dt=0.04, at=meta_at(self.svc, 1))
        self.assertEqual(code, 200)
        rows = [r for t, r, _ in self.svc.plan if t == "mallet"]
        np.testing.assert_allclose(rows, [[0.5, 0.1], [0.6, 0.2], [0.7, 0.3], [0.8, 0.4]])
        self.run_steps(5)
        self.assert_played_on(6)

    def test_a_command_is_not_reissued_through_a_gap(self):
        """stroke, then a stroke 5 steps ahead: the first is issued once (before, the gap repeated it at every step,
        each a fresh command that restarted the swing)."""
        self.submit("stroke", [STROKE])
        code, meta = self.submit("stroke", [STROKE2], at=5)
        self.assertEqual(code, 200)
        self.assertEqual([t for t, _, _ in self.svc.plan], ["stroke", None, None, None, None, "stroke"])
        self.run_steps(8)
        self.assertEqual(self.sim.issued, [(0, "stroke", tuple(STROKE)), (5, "stroke", tuple(STROKE2))])
        self.assertEqual(self.svc.held_steps, 6)             # the gap's four steps and the two after the plan ran out
        self.assert_played_on(8)

    def test_a_command_ahead_is_issued_at_its_step_only(self):
        self.submit("stroke", [STROKE])
        self.submit("stop", [[1.0]], at=3)                   # (before: the gap fired the stop at steps 1 and 2 too)
        self.run_steps(5)
        self.assertEqual(self.sim.issued, [(0, "stroke", tuple(STROKE)), (3, "stop", (1.0,))])
        self.assert_played_on(5)

    def test_a_command_is_its_row_exactly(self):
        """No arithmetic on a command's row, whatever `interpolate` says (linear is the default)."""
        row = [0.1, 0.3, 0.7, 0.9, 1.1, 1.3, 1.7, 1.9, 2.3, 2.9]
        self.submit("stroke", [STROKE])
        self.submit("stroke", [row], at=1)
        self.run_steps(2)
        self.assertEqual(self.sim.issued[1], (1, "stroke", tuple(row)))

    def test_a_target_is_still_held_through_a_gap_and_interpolated_from(self):
        """One action type, a target: as before (HumanoidBench, BiGym 2.0)."""
        self.submit("mallet", [[0.2, 0.0]] * 2, interpolate="hold")
        code, meta = self.submit("mallet", [[1.0, 0.8]], dt=0.04, at=4)
        self.assertEqual([(t, src) for t, _, src in self.svc.plan][:4], [("mallet", 1), ("mallet", 1), ("mallet", -1),
                                                                         ("mallet", -1)])
        np.testing.assert_allclose([r for _, r, _ in self.svc.plan][2:],
                                   [[0.2, 0.0], [0.2, 0.0], [0.4, 0.2], [0.6, 0.4], [0.8, 0.6], [1.0, 0.8]])
        self.run_steps(8)
        self.assertEqual(self.sim.target, [1.0, 0.8])
        self.assert_played_on(8)

    def test_a_layout_the_plan_cannot_take_is_400_and_changes_nothing(self):
        """Planning runs nothing, so whatever goes wrong in it is a 400: here an adapter whose command() does not have
        its type's layout."""
        self.submit("mallet", [[0.2, 0.0]])
        self.sim.command = lambda typ: np.zeros(7)
        self.run_steps(2)                                    # the plan has run out: a chunk now starts from command()
        plan, calls = list(self.svc.plan), self.svc.calls
        code, body = self.submit("mallet", [[1.0, 0.8]], dt=0.04)
        self.assertEqual(code, 400, body)
        self.assertIn("interpolate", body["error"])
        self.assertEqual((list(self.svc.plan), self.svc.calls, self.svc.done), (plan, calls, False))
        refused = [json.loads(line) for line in Path(self.data, "episode.jsonl").read_text().splitlines()
                   if '"plan_refused"' in line]
        self.assertEqual([(e["type"], e["at"]) for e in refused], [("mallet", 2)])   # on the record
        self.assertEqual(self.submit("mallet", [[1.0, 0.8]], dt=0.04, interpolate="hold")[0], 200)
        self.assert_played_on(2)


def meta_at(svc, ahead: int) -> int:
    """The control step `ahead` steps after the next one."""
    return len(svc.episode) + ahead


class TestRefusedReset(ByHand):
    reset_budget = 1

    def test_a_refused_reset_leaves_a_pending_watch_alone(self):
        self.submit("mallet", [[0.2, 0.0]])
        watch = self.post("/observe", seconds=0.05, cameras=[])
        self.assertFalse(watch.done.is_set())
        refused = self.post("/reset", cameras=["nope"])       # 400: nothing changes
        self.assertEqual(refused.reply[1], 400)
        self.assertFalse(watch.done.is_set())                 # (before: the refused reset answered the watch early)
        self.assertTrue(self.svc.running)
        self.run_steps(5)
        self.assertTrue(watch.done.is_set())
        self.assertEqual(watch.reply[1]["control_steps_watch"], 5)

    def test_a_reset_past_the_budget_leaves_a_pending_watch_alone(self):
        self.submit("mallet", [[0.2, 0.0]])
        self.assertEqual(self.post("/reset", cameras=[]).reply[0], "rcb1")
        self.submit("mallet", [[0.2, 0.0]])
        watch = self.post("/observe", seconds=0.03, cameras=[])
        refused = self.post("/reset", cameras=[])
        self.assertEqual(refused.reply[1], 409)
        self.assertFalse(watch.done.is_set())
        self.run_steps(3)
        self.assertEqual(watch.reply[1]["control_steps_watch"], 3)

    def test_a_granted_reset_answers_the_watch_first(self):
        self.submit("mallet", [[0.2, 0.0]])
        watch = self.post("/observe", seconds=0.05, cameras=[])
        self.run_steps(2)
        self.assertEqual(self.post("/reset", cameras=[]).reply[0], "rcb1")
        self.assertTrue(watch.done.is_set())
        self.assertEqual(watch.reply[1]["control_steps_watch"], 2)


class TestCountersSurviveACrash(ByHand):
    def make_sim(self):
        return FastSim()

    def test_the_realtime_counters_resume_from_the_last_checkpoint(self):
        """stalls, held_steps, late_steps, max_lag_s and max_queue_wait_s cover the whole trial (before, a restarted
        service counted from zero, so final.json reported only what followed the last crash)."""
        job = rcb_realtime._Job("POST", "/submit", json.dumps({"type": "move", "actions": [[0.1]] * 3, "at": 0,
                                                               "cameras": []}).encode())
        self.svc.dispatch(job)
        self.run_steps(2)
        late = rcb_realtime._Job("POST", "/submit", json.dumps({"type": "move", "actions": [[0.2]] * 4, "at": 0,
                                                                "cameras": []}).encode())
        self.svc.dispatch(late)                               # 2 of its rows are for steps already gone
        self.svc.stalls, self.svc.max_lag, self.svc.max_queue_wait = 3, 0.75, 0.2
        self.run_steps(98)                                    # step 100: a checkpoint (one per second of robot time)
        self.assertEqual((self.svc.late_steps, self.svc.held_steps), (2, 96))
        self.run_steps(5)                                     # lost with the crash
        svc2 = self.service(FastSim())                        # the restarted process
        self.assertEqual(len(svc2.episode), 100)
        self.assertEqual((svc2.stalls, svc2.late_steps, svc2.held_steps), (3, 2, 96))
        self.assertEqual((svc2.max_lag, svc2.max_queue_wait), (0.75, 0.2))
        self.svc = svc2
        fin = self.finalize()
        self.assertEqual((fin["stalls"], fin["late_steps"], fin["held_steps"], fin["max_lag_s"]), (3, 2, 96, 0.75))


# One process of a trial's realtime sidecar, as rcb_service.main() runs it (crash.log), that dies by a signal: "step"
# inside a control step of the agent's command (sim.step kills it), "build" after building and resuming but before
# any control step, "held" inside a control step with no command of the agent's (the hold row).
CHILD = r"""
import os, sys
tests, realtime, data, sig, where = sys.argv[1], sys.argv[2], sys.argv[3], int(sys.argv[4]), sys.argv[5]
sys.path.insert(0, tests)
sys.path.append(realtime)
from test_standard_service import FakeSim
import json, rcb_realtime, rcb_service
rcb_service.enable_crash_log(data)

class S(FakeSim):
    control_dt, max_control_steps = 0.01, 10 ** 6

sim = S(goal=1e9)
svc = rcb_realtime.RealtimeService(sim, data=data, slowdown=1000.0)
svc.start()
if where == "build":
    os.kill(os.getpid(), sig)
if where == "step":
    job = rcb_realtime._Job("POST", "/submit", json.dumps({"type": "move", "actions": [[0.1]] * 3,
                                                           "cameras": []}).encode())
    svc.dispatch(job)
sim.on_step = lambda s: os.kill(os.getpid(), sig)
svc.tick()
"""


def die_in(data: str, sig: int, where: str) -> None:
    """A sidecar process of this trial (counted, as main() counts it) that dies by `sig` at `where`."""
    import subprocess
    rcb_service.count_start(data)
    r = subprocess.run([sys.executable, "-c", CHILD, str(HERE), str(REALTIME), data, str(int(sig)), where],
                       capture_output=True, timeout=120)
    assert r.returncode == -sig, (r.returncode, r.stderr[-500:])


class TestCrashOwner(unittest.TestCase):
    """A simulator crash inside a control step (crash.log's record shows _step on the crashing thread) after the agent's
    first command is the agent's; a kill, a crash outside a control step (building, resuming, resetting, rendering,
    finalizing) and any crash before the first command are infrastructure (owner, 2026-10-17; review round 2)."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.data = self.tmp.name

    def tearDown(self):
        self.tmp.cleanup()

    def outcome(self, *deaths) -> dict:
        for sig, where in deaths:
            die_in(self.data, sig, where)
        rcb_service.count_start(self.data)                   # the restart that finds the deaths
        with self.assertRaises(rcb_service.GiveUp):
            svc = rcb_realtime.RealtimeService(FastSim(), data=self.data, slowdown=1000.0)
            svc.start()
        return json.loads(Path(self.data, "final.json").read_text())

    def test_segfaults_in_the_agents_steps_are_the_agents(self):
        fin = self.outcome(*[(signal.SIGSEGV, "step")] * 3)
        self.assertEqual((fin["reason"], fin.get("infra_error", 0), fin["success"]), ("sim_crashed_on_call", 0, False))
        died = rcb_service.deaths(self.data)
        self.assertEqual([(d["fatal_signal"], d["in_step"]) for d in died], [(True, True)] * 3)
        ev = [json.loads(x) for x in Path(self.data, "episode.jsonl").read_text().splitlines()]
        self.assertEqual([e["fatal_signal"] for e in ev if e["ev"] == "resuming"], [True, True])
        self.assertIn("first_command", [e["ev"] for e in ev])

    def test_aborts_in_the_agents_steps_are_the_agents(self):
        self.assertEqual(self.outcome(*[(signal.SIGABRT, "step")] * 3)["reason"], "sim_crashed_on_call")

    def test_kills_are_infrastructure(self):
        fin = self.outcome(*[(signal.SIGKILL, "step")] * 3)
        self.assertEqual((fin["reason"], fin["infra_error"]), ("sim_crashed", 1))

    def test_segfaults_outside_a_step_are_infrastructure(self):
        """One agent-time segfault, then two in processes that never got past building and resuming (review repro)."""
        fin = self.outcome((signal.SIGSEGV, "step"), (signal.SIGSEGV, "build"), (signal.SIGSEGV, "build"))
        self.assertEqual((fin["reason"], fin["infra_error"]), ("sim_crashed", 1))
        self.assertEqual([d["in_step"] for d in rcb_service.deaths(self.data)], [True, False, False])

    def test_segfaults_before_the_first_command_are_infrastructure(self):
        fin = self.outcome(*[(signal.SIGSEGV, "held")] * 3)
        self.assertEqual((fin["reason"], fin["infra_error"]), ("sim_crashed", 1))
        ev = [json.loads(x) for x in Path(self.data, "episode.jsonl").read_text().splitlines()]
        self.assertNotIn("first_command", [e["ev"] for e in ev])

    def test_a_kill_among_segfaults_is_infrastructure(self):
        fin = self.outcome((signal.SIGSEGV, "step"), (signal.SIGKILL, "step"), (signal.SIGSEGV, "step"))
        self.assertEqual(fin["reason"], "sim_crashed")

    def test_the_record_must_show_a_step_on_the_crashing_thread(self):
        rec = (b"Fatal Python error: Segmentation fault\n\nThread 0x1 (most recent call first):\n"
               b'  File "rcb_service.py", line 1 in _step\n\nCurrent thread 0x2 (most recent call first):\n'
               b'  File "server.py", line 9 in images\n  File "rcb_realtime.py", line 5 in dispatch\n\n')
        self.assertFalse(rcb_service.crashed_in_step(rec))
        self.assertTrue(rcb_service.crashed_in_step(rec.replace(b"in images", b"in _step")))


class TestWatchImageCap(ByHand):
    """Concurrent watches together stay within the frame budget (review round 3: an agent could otherwise exhaust the
    sidecar's memory, and an OOM kill counts as infrastructure)."""

    def make_sim(self):
        return FastSim()

    def test_watches_beyond_the_budget_in_flight_are_429(self):
        self.svc.max_frames = 120                            # 100 control steps at 30 fps: 35 images a camera
        ok = self.post("/observe", seconds=1.0, cameras=["cam"], video_fps=30)   # 35
        self.assertFalse(ok.done.is_set())
        second = self.post("/observe", seconds=1.0, cameras=["cam", "side"], video_fps=30)   # + 70 = 105
        self.assertFalse(second.done.is_set())
        third = self.post("/observe", seconds=1.0, cameras=["cam", "side"], video_fps=30)    # + 70 > 120
        self.assertEqual(third.reply[1], 429)
        self.assertIn("images_in_flight", json.loads(third.reply[3]))
        self.run_steps(100)                                  # the watches complete
        self.assertTrue(ok.done.is_set() and second.done.is_set())
        again = self.post("/observe", seconds=1.0, cameras=["cam", "side"], video_fps=30)
        self.assertFalse(again.done.is_set())                # room again


class TestFirstCommand(ByHand):
    def make_sim(self):
        return FastSim()

    def test_a_gap_before_a_later_at_is_no_command(self):
        """A target held through a gap (call -1) or the hold row runs before the agent's row: not its first command."""
        self.submit("move", [[0.1]] * 3, at=5)
        self.run_steps(5)
        self.assertFalse(self.svc.commanded)
        self.run_steps(1)
        self.assertTrue(self.svc.commanded)

    def test_a_row_the_simulator_refuses_to_clip_is_a_400(self):
        def bad(typ, rows):
            raise ValueError("a row of the wrong layout")
        self.sim.clip = bad
        code, body = self.submit("move", [[0.1]])
        self.assertEqual(code, 400)
        self.assertFalse(self.svc.done)


class TestResetFailure(ByHand):
    reset_budget = 1

    def make_sim(self):
        return FastSim()

    def test_a_reset_that_fails_to_rebuild_is_infrastructure(self):
        """After the first command too: the scene's rebuild failed, not a control step of the agent's commands."""
        self.submit("move", [[0.1]] * 3, at=0)
        self.run_steps(5)

        def boom():
            raise RuntimeError("the scene did not build")
        self.sim.reset = boom
        self.post("/reset", cameras=[])
        fin = self.finalize()
        self.assertEqual((fin["reason"], fin.get("infra_error")), ("error", 1))


class TestLiveGrading(ByHand):
    """Board 0151: the realtime verdict is the live episode's too; the frozen start is checked on the live simulator."""

    def make_sim(self):
        return FastSim()

    def test_a_scene_off_the_frozen_start_gives_up_before_serving(self):
        tmp = tempfile.TemporaryDirectory()
        try:
            sim = FastSim()
            sim.start_sha = "not-this-one"
            svc = rcb_realtime.RealtimeService(sim, data=tmp.name, slowdown=1000.0)
            with self.assertRaises(rcb_service.GiveUp):
                svc.start()
            fin = json.loads(Path(tmp.name, "final.json").read_text())
            self.assertEqual((fin["finalized"], fin["success"], fin["infra_error"]), (True, False, 1))
            self.assertTrue(fin["reason"].startswith("instance_mismatch"))
        finally:
            tmp.cleanup()

    def test_more_crashes_than_resumes_are_infrastructure(self):
        """No call spans a crash in realtime mode (submit answers at once): a give-up after crashes is sim_crashed."""
        self.submit("move", [[0.1]] * 3, at=0)
        self.run_steps(100)                                  # a checkpoint
        rcb_service.count_start(self.data)                   # (setUp's process start)
        for _ in range(2):
            rcb_service.count_start(self.data)
            self.service(FastSim())
        rcb_service.count_start(self.data)
        with self.assertRaises(rcb_service.GiveUp):
            self.service(FastSim())
        fin = json.loads(Path(self.data, "final.json").read_text())
        self.assertEqual((fin["reason"], fin["infra_error"], fin["success"]), ("sim_crashed", 1, False))

    def test_a_timeout_is_graded_live_and_nothing_is_replayed(self):
        self.submit("move", [[0.1]] * 3, at=0)
        self.run_steps(10)
        fin = self.finalize()
        self.assertEqual((fin["reason"], fin["graded_by"], fin["replays"], fin["success"], fin["n_actions"]),
                         ("timeout", "live", 0, False, 10))
        self.assertEqual(self.sim.replays, 0)


class TestVideoNeverDecides(ByHand):
    def test_the_realtime_verdict_is_finalized_before_the_video(self):
        seen = {}
        self.sim.render_video = lambda rows, path: seen.update(json.loads(Path(self.data, "final.json").read_text()))
        self.submit("mallet", [[0.2, 0.0]])
        self.run_steps(3)
        fin = self.finalize()
        self.assertEqual((seen["finalized"], seen["video_pending"], seen["graded_by"], seen["realtime"]),
                         (True, True, "live", 1))
        self.assertEqual((fin["finalized"], fin["video_pending"], fin["video"], fin["protocol"]),
                         (True, False, True, "eai-standard/2.3"))


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
