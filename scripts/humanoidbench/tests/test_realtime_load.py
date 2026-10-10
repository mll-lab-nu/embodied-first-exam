"""What a request can cost the realtime clock (shared/realtime/rcb_realtime.py, PROTOCOL §4b): the real RealtimeService
on a toy simulator at 50 Hz, over real HTTP (standard library client), under the loads that used to slow its clock --
floods of refused bodies, parallel observes, parallel watches -- and the evidence it keeps (stalls, stalled_s,
stalled_share in final.json, repeated in reward.json by the three realtime graders). No MuJoCo, no GPU; 1-2 minutes.

    python3 scripts/humanoidbench/tests/test_realtime_load.py        # needs numpy (the service does); no requests
    python -m unittest discover -s scripts/humanoidbench/tests

A load test asserts that the clock kept at least KEEP of its nominal steps and never stalled; the numbers it measured
are printed (-v), the way the review's reproductions printed theirs.
"""
from __future__ import annotations

import http.client
import json
import os
import socket
import subprocess
import sys
import tempfile
import threading
import time
import unittest
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
sys.path.insert(0, str(HERE))
from test_standard_service import FakeSim  # noqa: E402   (puts shared/standard/ on sys.path)

sys.path.append(str(HERE.parents[0] / "shared" / "realtime"))
import rcb1  # noqa: E402
import rcb_realtime  # noqa: E402
import rcb_service  # noqa: E402

KEEP = 0.93            # of the nominal control steps (the host that runs this may be busy)
SECONDS = 3.0          # per load
GRADERS = {"humanoidbench": HERE.parents[0] / "shared" / "standard" / "grade.py",
           "bigym2": ROOT / "scripts" / "bigym2" / "shared" / "standard" / "grade.py",
           "roboolympics": ROOT / "scripts" / "roboolympics" / "shared" / "tests" / "grade.py"}


class Sim(FakeSim):
    """The toy point at HumanoidBench's 50 Hz, never done; a render and a control step may each take time."""
    control_dt, max_control_steps = 0.02, 10 ** 7

    def __init__(self, render_s: float = 0.0, step_s: float = 0.0):
        super().__init__(1e9)
        self.render_s, self.step_s, self.renders, self.slow_at = render_s, step_s, 0, {}

    def images(self, cameras, depth):
        self.renders += 1
        if self.render_s:
            time.sleep(self.render_s * len(cameras))
        return super().images(cameras, depth)

    def step(self, raw):
        if self.step_s or self.t in self.slow_at:
            time.sleep(self.slow_at.get(self.t, self.step_s))
        return super().step(raw)


def post(port: int, path: str, body: bytes, timeout: float = 60.0) -> tuple[int, bytes]:
    c = http.client.HTTPConnection("127.0.0.1", port, timeout=timeout)
    try:
        c.request("POST", path, body=body)
        r = c.getresponse()
        return r.status, r.read()
    finally:
        c.close()


class Rig(unittest.TestCase):
    """A realtime service on a free port: its simulator loop and its HTTP server each in a thread, as serve() runs it."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.data = self.tmp.name
        self._switch = sys.getswitchinterval()
        sys.setswitchinterval(rcb_realtime.SWITCH_INTERVAL_S)     # serve() sets it

    def tearDown(self):
        if getattr(self, "stop", None):
            self.stop.set()
            self.loop.join(5)
            self.srv.shutdown()
            self.srv.server_close()
        sys.setswitchinterval(self._switch)
        self.tmp.cleanup()

    def start(self, sim, reset_budget: int = 0):
        self.sim = sim
        self.svc = rcb_realtime.RealtimeService(sim, data=self.data, reset_budget=reset_budget, slowdown=1.0)
        self.svc.start()
        self.srv = self.svc.http_server(("127.0.0.1", 0))
        self.port = self.srv.server_address[1]
        self.stop = threading.Event()
        threading.Thread(target=self.srv.serve_forever, daemon=True).start()
        self.loop = threading.Thread(target=self.svc.loop, args=(self.stop,), daemon=True)
        self.loop.start()

    def go(self) -> None:
        """Start the episode's clock."""
        code, _ = post(self.port, "/submit", json.dumps({"type": "move", "actions": [[0.0]], "cameras": []}).encode())
        self.assertEqual(code, 200)

    def under(self, name: str, flood=None, threads: int = 4, seconds: float = SECONDS) -> dict:
        """Control steps run in `seconds` of wall time while `threads` threads call flood(port) -> status again and
        again; the nominal number is seconds / control_dt."""
        self.go()
        halt, codes = threading.Event(), {}

        def work():
            while not halt.is_set():
                try:
                    k = flood(self.port)
                except Exception as exc:  # noqa: BLE001 -- a refused connection is an answer too
                    k = type(exc).__name__
                codes[k] = codes.get(k, 0) + 1

        ths = [threading.Thread(target=work, daemon=True) for _ in range(threads if flood else 0)]
        for t in ths:
            t.start()
        time.sleep(0.3)                              # the flood is under way
        s0, t0 = len(self.svc.episode), time.monotonic()
        time.sleep(seconds)
        steps, wall = len(self.svc.episode) - s0, time.monotonic() - t0
        halt.set()
        out = {"steps": steps, "nominal": round(wall / self.sim.control_dt), "stalls": self.svc.stalls,
               "stalled_s": round(self.svc.stalled_s, 3), "max_lag_s": round(self.svc.max_lag, 3), "replies": codes}
        print(f"\n    {name}: {steps} control steps of {out['nominal']} nominal; stalls {out['stalls']}, "
              f"stalled_s {out['stalled_s']}, max_lag_s {out['max_lag_s']}, replies {codes}", file=sys.stderr)
        for t in ths:
            t.join(90)
        return out

    def assert_kept(self, out: dict) -> None:
        self.assertGreaterEqual(out["steps"], KEEP * out["nominal"], out)
        self.assertEqual(out["stalls"], 0, out)

    def finalize(self) -> dict:
        self.svc.on_sigusr1()
        for _ in range(200):
            fin = json.loads(Path(self.data, "final.json").read_text())
            if fin.get("finalized"):
                return fin
            time.sleep(0.05)
        self.fail("never finalized")


class TestClockUnderLoad(Rig):
    def test_no_load(self):
        self.start(Sim())
        self.assert_kept(self.under("no load"))

    def test_flood_of_refused_21_mb_json_bodies(self):
        """The review's first reproduction (3 control steps in 6 s before): 21 MB of JSON, valid, refused with 400
        (the chunk is too long). Parsed by the child process, one at a time: the clock does not notice."""
        junk = json.dumps({"type": "move", "actions": [[0.0]] * 3_000_000}).encode()
        self.assertGreater(len(junk), 20e6)
        self.start(Sim())
        out = self.under("4 threads, refused 21 MB /submit bodies", lambda p: post(p, "/submit", junk)[0])
        self.assert_kept(out)
        self.assertEqual(set(out["replies"]) - {400}, set(), out)
        fin = self.finalize()
        self.assertGreaterEqual(fin["requests_refused"], 1)
        self.assertGreater(fin["request_mb"], 20)
        self.assertEqual((fin["stalls"], fin["stalled_s"], fin["stalled_share"]), (0, 0.0, 0.0))

    def test_flood_of_refused_json_bodies_parsed_in_process(self):
        """Just under INLINE_JSON: parsed on the HTTP threads, one at a time and paced."""
        rows = [[0.0]] * ((rcb_realtime.INLINE_JSON - 200) // 7)
        junk = json.dumps({"type": "move", "actions": rows}).encode()
        self.assertLessEqual(len(junk), rcb_realtime.INLINE_JSON)
        self.assertGreater(len(junk), 0.9 * rcb_realtime.INLINE_JSON)
        self.start(Sim())
        out = self.under("4 threads, refused 1 MB /submit bodies", lambda p: post(p, "/submit", junk)[0])
        self.assert_kept(out)
        self.assertEqual(set(out["replies"]), {400}, out)

    def test_flood_of_small_malformed_requests(self):
        self.start(Sim())
        bodies = [b"{", b"[1]", b'{"type": "nope", "seconds": -1}', b"RCB1\x05\x00\x00\x00{}"]
        n = [0]

        def flood(p):
            n[0] += 1
            return post(p, ("/submit", "/observe", "/nope")[n[0] % 3], bodies[n[0] % 4])[0]

        out = self.under("8 threads, small malformed requests", flood, threads=8)
        self.assert_kept(out)
        self.assertTrue(set(out["replies"]) <= {400, 404}, out)

    def test_flood_of_large_rcb1_frames_of_the_wrong_shape(self):
        """32 MB of float64 in an RCB1 array part: refused for its shape, without a pass over it."""
        junk = rcb1.encode({"type": "move"}, [rcb1.array_part("actions", np.zeros((4_000_000, 1)))])
        self.start(Sim())
        out = self.under("4 threads, refused 32 MB RCB1 /submit bodies", lambda p: post(p, "/submit", junk)[0])
        self.assert_kept(out)
        self.assertEqual(set(out["replies"]), {400}, out)

    def test_flood_of_accepted_chunks_of_the_largest_size(self):
        """Accepted work has a cost too (clip, plan, record): requests queue behind each other, not into the clock."""
        rows = np.zeros((int(10.0 / Sim.control_dt), 1))
        body = rcb1.encode({"type": "move", "cameras": []}, [rcb1.array_part("actions", rows)])
        self.start(Sim())
        out = self.under("4 threads, accepted 10 s chunks", lambda p: post(p, "/submit", body)[0])
        self.assert_kept(out)
        self.assertEqual(set(out["replies"]), {200}, out)

    def test_parallel_observes_with_a_slow_render(self):
        """The review's second reproduction (234 of 300 steps before): 4 threads of /observe, 25 ms a render."""
        self.start(Sim(render_s=0.0125))             # 2 cameras: 25 ms a call
        out = self.under("4 threads, /observe with a 25 ms render", lambda p: post(p, "/observe", b"{}")[0])
        self.assert_kept(out)
        self.assertEqual(set(out["replies"]), {200}, out)
        self.assertGreater(out["replies"][200], 10)   # and they are served

    def test_parallel_observes_on_a_simulator_near_real_time(self):
        """A control step that takes 3/4 of its period, and the same observes: the steps come first."""
        self.start(Sim(render_s=0.0125, step_s=0.015))
        out = self.under("4 threads, /observe 25 ms, control step 15 of 20 ms", lambda p: post(p, "/observe", b"{}")[0])
        self.assertGreaterEqual(out["steps"], 0.88 * out["nominal"], out)
        self.assertGreater(out["replies"].get(200, 0), 3, out)

    def test_a_render_that_is_a_stall_by_itself_cannot_be_repeated_at_once(self):
        """0.7 s a render (CPU rendering): every such observe stalls the clock, so the next one waits four times as
        long -- the clock keeps 4/5 of its time at least -- while a controller's requests without images go on.
        (Before: the clock ran only between two renders, a few control steps in seconds.)"""
        self.start(Sim(render_s=0.35))
        halt, cheap = threading.Event(), [0]

        def controller():
            body = json.dumps({"cameras": []}).encode()
            while not halt.is_set():
                if post(self.port, "/observe", body)[0] == 200:
                    cheap[0] += 1
                time.sleep(0.02)

        threading.Thread(target=controller, daemon=True).start()
        out = self.under("2 threads, /observe with a 0.7 s render, and a controller", lambda p: post(p, "/observe", b"{}")[0],
                         threads=2, seconds=6.0)
        halt.set()
        # 2 renders fit in the 6.3 s: 246 of 300 steps, a share of 0.22; the bounds leave room for a busy host's own
        # stall (before the fix: a handful of steps, a share near 1)
        self.assertGreaterEqual(out["steps"], 0.65 * out["nominal"], out)
        self.assertGreaterEqual(out["replies"].get(200, 0), 1, out)
        self.assertGreater(cheap[0], 60, out)
        fin = self.finalize()
        self.assertGreaterEqual(fin["stalls"], 1)
        self.assertLess(fin["stalled_share"], 0.45)

    def test_parallel_watches_render_once_per_step(self):
        """The review's third (115 of 250 steps with 100 watches before): every watch gets the step's one render."""
        self.start(Sim(render_s=0.001))
        watch = json.dumps({"seconds": 30, "video_fps": 30, "video": "frames"}).encode()
        self.go()

        def watcher():
            try:
                post(self.port, "/observe", watch, timeout=40)
            except OSError:
                pass                                 # the service went away with the test

        for _ in range(100):
            threading.Thread(target=watcher, daemon=True).start()
            time.sleep(0.005)                        # (the listen backlog is 5)
        for _ in range(100):
            if len(self.svc.watches) >= 95:
                break
            time.sleep(0.1)
        self.assertGreaterEqual(len(self.svc.watches), 95)
        r0, s0 = self.sim.renders, len(self.svc.episode)
        out = self.under("100 parallel watches at 30 fps, 2 ms a render")
        self.assert_kept(out)
        self.assertLessEqual(self.sim.renders - r0, len(self.svc.episode) - s0 + 5)   # one a step, not 100 x

    def test_a_simulator_that_cannot_keep_up_still_answers_and_says_so(self):
        """A control step slower than its period (a broken host): the clock stalls -- recorded -- and requests are
        still served, a bounded share of the time."""
        self.start(Sim(render_s=0.01, step_s=0.03))
        t = time.monotonic()
        out = self.under("control step 30 of 20 ms, 2 threads of /observe", lambda p: post(p, "/observe", b"{}")[0],
                         threads=2)
        self.assertGreater(out["replies"].get(200, 0), 3, out)
        self.assertGreaterEqual(out["stalls"], 1, out)
        fin = self.finalize()
        self.assertGreater(fin["stalled_s"], 0.5)
        self.assertGreater(fin["stalled_share"], 0.15)
        self.assertLess(fin["stalled_share"], 0.6)
        self.assertLessEqual(fin["clock_s"], time.monotonic() - t)
        self.assertGreater(fin["max_lag_s"], 0.5)     # the true maximum (it never passed 0.5 before)


class TestRequests(Rig):
    def test_negative_content_length_is_refused_unread(self):
        """Before: rfile.read(-1) read to the end of the stream, whatever its size (m5)."""
        self.start(Sim())
        for port in (self.port, self.standard_port()):
            c = socket.create_connection(("127.0.0.1", port), timeout=10)
            c.sendall(b"POST /submit HTTP/1.0\r\nContent-Length: -1\r\n\r\n")     # and no end of stream
            resp = c.recv(200)
            c.close()
            self.assertTrue(resp.startswith(b"HTTP/1.0 400"), resp)

    def standard_port(self) -> int:
        svc = rcb_service.Service(FakeSim(1e9), data=tempfile.mkdtemp(dir=self.data))
        svc.start()
        srv = svc.http_server(("127.0.0.1", 0))
        threading.Thread(target=srv.serve_forever, daemon=True).start()
        self.addCleanup(srv.shutdown)
        return srv.server_address[1]

    def test_a_large_json_body_is_served_like_a_small_one(self):
        """More than INLINE_JSON bytes of JSON text go through the child process and get the same answer."""
        self.start(Sim())
        small = {"type": "move", "actions": [[0.5], [0.25]], "cameras": ["cam"], "interpolate": "hold", "note": "n"}
        big = {**small, "note": "n" + " " * (rcb_realtime.INLINE_JSON + 10), "junk": [0] * 1000}
        frame = rcb1.encode({**big, "actions": None}, [rcb1.array_part("actions", np.array([[0.5], [0.25]]))])
        metas = []
        for body in (json.dumps(small).encode(), json.dumps(big).encode(), frame):
            code, raw = post(self.port, "/submit", body)
            self.assertEqual(code, 200, raw[:200])
            meta, parts = rcb1.decode(raw)
            metas.append({k: meta[k] for k in ("type", "n_rows", "dt", "interpolate", "late_steps", "ok")})
            self.assertEqual(sorted(parts), ["last/cam", "proprio"])
        self.assertEqual(metas[0], metas[1])
        self.assertEqual(metas[0], metas[2])
        calls = [json.loads(x) for x in Path(self.data, "calls.jsonl").read_text().splitlines()]
        self.assertEqual([c["note"] for c in calls], ["n", ("n" + " " * 300)[:200], ("n" + " " * 300)[:200]])
        sub = np.fromfile(Path(self.data, "submitted.f64")).reshape(-1, 2)
        self.assertEqual(sub[:, 1].tolist(), [0.5, 0.25] * 3)

    def test_a_large_json_body_is_refused_like_a_small_one(self):
        self.start(Sim())
        pad = " " * (rcb_realtime.INLINE_JSON + 10)
        for body, want in ((b'{"type": "move", "actions": [[1, 2]]%s}' % pad.encode(), "must be (T, 1)"),
                           (b'{"type": "move", "actions": [["a"]]%s}' % pad.encode(), "send the actions as"),
                           (b'{"type": "nope"%s}' % pad.encode(), "type must be one of"),
                           (b'{"type": "move", "actions": [[1]], "cameras": ["zz"]%s}' % pad.encode(), "unknown camera"),
                           (b'[1, 2%s]' % pad.encode(), "malformed body"),
                           (b'{"type": %s' % pad.encode(), "malformed body")):
            code, raw = post(self.port, "/submit", body)
            self.assertEqual(code, 400, raw)
            self.assertIn(want, json.loads(raw)["error"])
        self.assertEqual(len(self.svc.episode), 0)   # none of them started the episode
        self.assertFalse(self.svc.running)
        self.assertEqual(self.svc.requests_refused, 6)

    def test_without_the_child_a_large_json_body_is_refused_not_parsed_here(self):
        self.start(Sim())
        exe, sys.executable = sys.executable, "/nonexistent/python"
        try:
            code, raw = post(self.port, "/submit", b'{"type": "move"%s}' % (b" " * (rcb_realtime.INLINE_JSON + 10)))
        finally:
            sys.executable = exe
        self.assertEqual(code, 400)
        self.assertIn("could not parse", json.loads(raw)["error"])

    def test_a_refusal_the_episodes_state_decides_comes_first(self):
        """409 before 400, as when the simulator thread checked both: a finished episode says so whatever is sent."""
        sim = Sim()
        sim.max_control_steps = 3
        self.start(sim)
        self.go()
        time.sleep(0.3)
        self.assertTrue(self.svc.done)
        for body in (b'{"type": "nope"}', b'{"type": "move", "actions": [[0.0]]}'):
            code, raw = post(self.port, "/submit", body)
            self.assertEqual(code, 409, raw)
        self.assertEqual(post(self.port, "/submit", b"{")[0], 400)       # a malformed body is still that
        self.assertEqual(post(self.port, "/observe", b'{"seconds": "x"}')[0], 400)

    def test_a_refused_request_starts_the_trials_time(self):
        """As before, when every request went through the simulator thread: the first request, of any kind."""
        self.start(Sim())
        self.assertEqual(post(self.port, "/nope", b"")[0], 404)
        time.sleep(0.5)
        self.assertIsNotNone(self.svc.t0)
        self.assertTrue(any(e["ev"] == "first_request" for e in self.svc._events()))


class TestStallEvidence(Rig):
    def test_a_stall_is_counted_in_seconds_and_as_a_share(self):
        sim = Sim()
        sim.slow_at = {20: 0.9}                      # one control step takes 0.9 s: the clock drops that debt
        self.start(sim)
        self.go()
        time.sleep(2.0)
        fin = self.finalize()
        self.assertEqual(fin["stalls"], 1)
        self.assertAlmostEqual(fin["stalled_s"], 0.88, delta=0.15)
        self.assertGreater(fin["max_lag_s"], 0.7)
        self.assertAlmostEqual(fin["clock_s"], 2.0, delta=0.4)
        self.assertAlmostEqual(fin["stalled_share"], fin["stalled_s"] / fin["clock_s"], delta=0.01)
        self.assertNotIn("infra_error", fin)         # evidence: it decides nothing
        stall = [e for e in self.svc._events() if e["ev"] == "stall"]
        self.assertEqual(len(stall), 1)

    def test_the_counters_survive_a_restart(self):
        self.start(Sim())
        self.go()
        time.sleep(0.2)
        self.svc.stalls, self.svc.stalled_s, self.svc.max_lag, self.svc.requests_refused = 2, 1.5, 0.9, 7
        time.sleep(1.2)                              # a checkpoint (one a second of robot time)
        self.stop.set()
        self.loop.join(5)
        clock = self.svc._clock_seconds()
        svc2 = rcb_realtime.RealtimeService(Sim(), data=self.data, slowdown=1.0)
        svc2.start()
        self.assertEqual((svc2.stalls, svc2.stalled_s, svc2.max_lag, svc2.requests_refused), (2, 1.5, 0.9, 7))
        self.assertGreater(svc2.clock_s, 0.9)
        self.assertLessEqual(svc2.clock_s, clock)
        self.assertFalse(svc2.running)               # paused after the recovery: its clock adds nothing meanwhile
        self.assertEqual(svc2._clock_seconds(), svc2.clock_s)

    def test_a_reset_the_simulator_fails_is_a_simulator_error(self):
        """Before: the trial ended "reset" -- the agent's 0 -- when the simulator failed to start the new episode."""
        sim = Sim()
        self.start(sim, reset_budget=2)
        self.go()
        time.sleep(0.1)
        sim.reset = lambda: (_ for _ in ()).throw(RuntimeError("EGL context lost"))
        code, raw = post(self.port, "/reset", b"{}")
        self.assertEqual(code, 500, raw)
        fin = self.finalize()
        self.assertEqual((fin["reason"], fin.get("infra_error")), ("error", 1))
        out = grade("humanoidbench", fin)
        self.assertEqual((out["success"], out["infra_error"], out["sim_error"]), (0, 1, 1))


def grade(bench: str, final: dict | None, files: dict | None = None) -> dict:
    with tempfile.TemporaryDirectory() as d:
        data, log = Path(d, "data"), Path(d, "log")
        data.mkdir()
        if final is not None:
            (data / "final.json").write_text(json.dumps(final))
        for name, text in (files or {}).items():
            (data / name).write_text(text)
        r = subprocess.run([sys.executable, str(GRADERS[bench])], capture_output=True, text=True,
                           env={**os.environ, "RCB_DATA": str(data), "RCB_VERIFIER_LOG_DIR": str(log)})
        assert r.returncode == 0, r.stderr
        out = json.loads((log / "reward.json").read_text(), parse_constant=lambda c: (_ for _ in ()).throw(ValueError(c)))
        out["_reward_txt"] = (log / "reward.txt").read_text().strip()
        return out


class TestGraders(unittest.TestCase):
    """The three realtime graders repeat the clock's evidence in reward.json; it never changes a verdict."""

    WIN = {"protocol": "eai-standard/2.3", "live_success": True, "replay_success": True, "deterministic": True,
           "finalized": True, "reason": "success", "realtime": 1, "slowdown": 1.0}
    CLOCK = {"clock_s": 6.0, "max_lag_s": 0.98, "stalls": 6, "stalled_s": 5.9, "stalled_share": 0.9833,
             "held_steps": 3, "late_steps": 2, "requests_refused": 400, "request_busy_s": 0.2}

    def test_the_fields_are_exported(self):
        for bench in GRADERS:
            out = grade(bench, {**self.WIN, **self.CLOCK})
            for k, v in self.CLOCK.items():
                self.assertEqual(out[k], v, (bench, k))
            self.assertEqual((out["success"], out["infra_error"], out["_reward_txt"]), (1, 0, "1"), bench)

    def test_a_stalled_trial_keeps_its_verdict(self):
        for bench in GRADERS:
            for live in (True, False):
                base = grade(bench, {**self.WIN, "live_success": live})
                out = grade(bench, {**self.WIN, "live_success": live, **self.CLOCK})
                keys = ("success", "infra_error", "grader_error", "sim_error", "deterministic", "_reward_txt")
                self.assertEqual([out[k] for k in keys], [base[k] for k in keys], bench)
                self.assertEqual(out["success"], int(live))

    def test_missing_or_broken_fields_are_zero(self):
        broken = {"stalls": "many", "stalled_s": float("nan"), "stalled_share": float("inf"), "max_lag_s": None,
                  "clock_s": [1], "held_steps": {}, "requests_refused": "x", "request_busy_s": float("-inf")}
        for bench in GRADERS:
            for extra in ({}, broken):
                out = grade(bench, {**self.WIN, **extra})          # (grade() refuses NaN / Infinity in reward.json)
                for k in self.CLOCK:
                    self.assertEqual(out[k], 0, (bench, k))
                self.assertTrue(all(isinstance(v, (int, float)) for k, v in out.items() if k != "_reward_txt"), bench)
                self.assertEqual(out["success"], 1)

    def test_a_trial_that_gave_up_has_the_fields_too(self):
        """sim_crashed: final.json is rcb_service's give-up record, without the clock's figures."""
        for bench in GRADERS:
            out = grade(bench, {"protocol": "eai-standard/2.3", "success": False, "done": True, "reason": "sim_crashed",
                                "finalized": True, "infra_error": 1})
            self.assertEqual((out["success"], out["infra_error"], out["stalls"], out["stalled_share"]), (0, 1, 0, 0))

    def test_a_standard_trial_is_graded_as_before(self):
        """The same grader serves standard mode (eai-standard/2.1): no realtime fields there."""
        for bench in ("humanoidbench", "bigym2"):
            out = grade(bench, {"protocol": "eai-standard/2.1", "live_success": True, "replay_success": True,
                                "deterministic": True, "finalized": True, "reason": "success"})
            self.assertEqual(out["success"], 1)
            self.assertFalse({"realtime", "stalls", "stalled_s", "stalled_share"} & set(out))


if __name__ == "__main__":
    unittest.main(verbosity=2)
