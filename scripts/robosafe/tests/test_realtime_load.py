#!/usr/bin/env python3
"""The RoboSafeBench realtime service (shared/realtime/rcb_rsb_rt.py on rcb_realtime.py) over real HTTP, on a real frozen
instance, under the loads an agent puts on it: what they cost the clock (control steps run against the nominal number,
stalls), the limits on pictures while the clock runs, and the evidence (final.json, the grader's reward.json). Modelled
on scripts/humanoidbench/tests/test_realtime_load.py, which tests the layer itself on a toy simulator.

Needs the simulator (RoboSafeBench with the realtime clock and the external-clock hooks, MuJoCo, OSMesa): run it in the
eai-robosafebench image (docs/benchmarks/robosafe.md, "Standard-realtime tasks"):
    python scripts/robosafe/tests/test_realtime_load.py [-v] [--instance <slug>-iNN]
A load test asserts that the clock kept at least KEEP of its nominal steps and did not stall; the numbers it measured
are printed. The host is shared in the measurements we report; a busy host may need a larger KEEP margin.
"""
from __future__ import annotations

import http.client
import json
import os
import pathlib
import shutil
import subprocess
import sys
import tempfile
import threading
import time
import unittest

import numpy as np

HERE = pathlib.Path(__file__).resolve().parents[1]
def _default_instance() -> str:
    """d_hand_enters' hazard member (the realtime set's first family), whatever its slug."""
    fams = json.loads((HERE / "families.json").read_text())["families"]
    slug = next(s for s, f in fams.items() if f["rsb"] == "d_hand_enters")
    nn = next(n for n, m in fams[slug]["instances"].items() if m["member"] == "hazard")
    return f"{slug}-{nn}"


INSTANCE = os.environ.get("RT_INSTANCE") or _default_instance()
KEEP = float(os.environ.get("RT_KEEP", "0.9"))
SECONDS = float(os.environ.get("RT_SECONDS", "4"))
SIM = tempfile.mkdtemp(prefix="rt_load_sim_")           # the task's environment/sim/, as gen_realtime.py assembles it
for f in ("server.py", "rcb_service.py", "rcb1.py", "rcb_rsb.py", "replay.py", "picture_delivery.py"):
    shutil.copy(HERE / "shared/standard" / f, SIM)
for f in ("rcb_realtime.py", "rcb_rsb_rt.py"):
    shutil.copy(HERE / "shared/realtime" / f, SIM)
sys.path.insert(0, SIM)
import rcb1  # noqa: E402
import rcb_realtime  # noqa: E402
import rcb_rsb_rt  # noqa: E402
import rcb_service  # noqa: E402


def instance(tmp: str) -> str:
    """The frozen realtime instance (instances_rt/), or, on a host whose libm rebuilds another start hash than the
    image's, the same instance with this host's hash (built in a fresh process, as make_rt_instances.py does)."""
    src = HERE / "instances_rt" / f"{INSTANCE}.json"
    inst = json.loads(src.read_text())
    code = ("import json, sys; sys.path.insert(0, %r); import rcb_rsb_rt, rcb_rsb; "
            "print(rcb_rsb.Session(json.load(open(sys.argv[1]))).ep.state_hash())" % SIM)
    sha = subprocess.run([sys.executable, "-c", code, str(src)], capture_output=True, text=True, check=True).stdout.split()[-1]
    if sha != inst["state_sha"]:
        print(f"\n    (this host rebuilds another start hash than the image's: {sha[:12]} for {inst['state_sha'][:12]})",
              file=sys.stderr)
        inst["state_sha"] = sha
    p = os.path.join(tmp, "instance.json")
    with open(p, "w") as f:
        json.dump(inst, f)
    return p


def req(port: int, method: str, path: str, meta: dict | None = None, actions=None, timeout: float = 120.0):
    c = http.client.HTTPConnection("127.0.0.1", port, timeout=timeout)
    try:
        body = b""
        if meta is not None:
            parts = [rcb1.array_part("actions", np.asarray(actions, np.float64))] if actions is not None else []
            body = rcb1.encode(meta, parts)
        c.request(method, path, body=body)
        r = c.getresponse()
        b = r.read()
        if b[:4] == b"RCB1":
            return r.status, rcb1.decode(b, arrays=False)[0]
        return r.status, json.loads(b or b"{}")
    finally:
        c.close()


class Rig(unittest.TestCase):
    """The service on a free port: its simulator loop and its HTTP server each in a thread, as serve() runs them."""

    @classmethod
    def setUpClass(cls):
        cls.base = tempfile.mkdtemp(prefix="rt_load_")
        cls.inst = instance(cls.base)

    def setUp(self):
        self.data = tempfile.mkdtemp(dir=self.base)
        os.environ["RCB_INSTANCE"], os.environ["RCB_DATA"] = self.inst, self.data
        svc_cls, build = rcb_rsb_rt.build_service()
        rcb_service.PROTOCOL = rcb_realtime.PROTOCOL
        self._switch = sys.getswitchinterval()
        sys.setswitchinterval(rcb_realtime.SWITCH_INTERVAL_S)
        self.svc = svc_cls(build(), data=self.data, slowdown=1.0)
        self.svc.sim.render_video = lambda rows, path: None          # the video is for people; not timed here
        self.svc.start()
        self.srv = self.svc.http_server(("127.0.0.1", 0))
        self.port = self.srv.server_address[1]
        self.stop = threading.Event()
        threading.Thread(target=self.srv.serve_forever, daemon=True).start()
        self.loop = threading.Thread(target=self.svc.loop, args=(self.stop,), daemon=True)
        self.loop.start()
        self.dt = self.svc.spec["control_dt"]
        self.cams = list(self.svc.spec["cameras"])

    def tearDown(self):
        self.stop.set()
        self.loop.join(10)
        self.srv.shutdown()
        self.srv.server_close()
        sys.setswitchinterval(self._switch)

    def hold_row(self) -> list:
        code, m = req(self.port, "POST", "/observe", {"cameras": [], "seconds": 0})
        return m["proprio"]["now"][:6] + [0.0]

    def go(self) -> None:
        code, m = req(self.port, "POST", "/submit", {"type": "stop", "cameras": [], "video": "none"}, np.zeros((1, 0)))
        self.assertEqual(code, 200, m)

    def under(self, name: str, flood=None, threads: int = 2, seconds: float = SECONDS) -> dict:
        self.go()
        halt, codes = threading.Event(), {}

        def work():
            while not halt.is_set():
                try:
                    k = flood(self.port)
                except Exception as exc:  # noqa: BLE001
                    k = type(exc).__name__
                codes[k] = codes.get(k, 0) + 1

        ths = [threading.Thread(target=work, daemon=True) for _ in range(threads if flood else 0)]
        for t in ths:
            t.start()
        time.sleep(0.3)
        s0, t0, st0 = len(self.svc.episode), time.monotonic(), self.svc.stalls
        time.sleep(seconds)
        steps, wall = len(self.svc.episode) - s0, time.monotonic() - t0
        halt.set()
        for t in ths:
            t.join(120)
        out = {"steps": steps, "nominal": round(wall / self.dt), "stalls": self.svc.stalls - st0,
               "max_lag_s": round(self.svc.max_lag, 3), "replies": codes}
        print(f"\n    {name}: {steps} control steps of {out['nominal']} nominal; stalls {out['stalls']}, "
              f"max_lag_s {out['max_lag_s']}, replies {codes}", file=sys.stderr)
        return out

    def assert_kept(self, out: dict) -> None:
        self.assertGreaterEqual(out["steps"], KEEP * out["nominal"], out)
        self.assertEqual(out["stalls"], 0, out)

    def finalize(self) -> dict:
        self.svc.on_sigusr1()
        for _ in range(3000):
            p = pathlib.Path(self.data, "final.json")
            fin = json.loads(p.read_text()) if p.exists() else {}
            if fin.get("finalized"):
                return fin
            time.sleep(0.1)
        self.fail("never finalized")


class TestClock(Rig):
    def test_no_load(self):
        self.assert_kept(self.under("no load"))

    def test_controller_loops(self):
        """Two controllers streaming 0.2 s chunks as fast as they can, without pictures (the instruction's advice)."""
        row = self.hold_row()
        self.assert_kept(self.under("2 controllers, 0.2 s chunks, cameras=[]", lambda p: req(
            p, "POST", "/submit", {"type": "joint_position", "cameras": [], "video": "none"}, [row] * 10)[0]))

    def test_status_polling(self):
        self.assert_kept(self.under("4 threads polling /status", lambda p: req(p, "GET", "/status")[0], threads=4))

    def test_snapshots_of_one_camera(self):
        """Parallel snapshots (seconds = 0) of one camera: rendered on the simulator's thread, at most once per step."""
        self.assert_kept(self.under("2 threads, /observe seconds=0, 1 camera", lambda p: req(
            p, "POST", "/observe", {"cameras": [self.cams[0]], "seconds": 0, "video": "none"})[0]))

    def test_watch_at_the_limit(self):
        """One watch at the limit: 1 camera at max_watch_images_per_s."""
        fps = self.svc.spec["timing"]["max_watch_images_per_s"]
        out = self.under(f"a watch of 1 camera at {fps} fps", lambda p: req(
            p, "POST", "/observe", {"cameras": [self.cams[0]], "seconds": 2, "video_fps": fps, "video": "frames"})[0],
            threads=1)
        self.assert_kept(out)
        self.assertEqual(set(out["replies"]), {200}, out)

    def test_over_the_limits_is_refused_and_costs_nothing(self):
        """Every camera while the clock runs, a watch over the picture rate, depth in a watch: 400, nothing rendered."""
        bad = [{"cameras": self.cams, "seconds": 0},
               {"cameras": self.cams[:1], "seconds": 1, "video_fps": 30, "video": "frames"},
               {"cameras": ["wrist"], "seconds": 1, "include_depth": True, "video_fps": 1}]
        n = [0]

        def flood(p):
            n[0] += 1
            return req(p, "POST", "/observe", bad[n[0] % len(bad)])[0]

        out = self.under("4 threads, requests over the picture limits", flood, threads=4)
        self.assert_kept(out)
        self.assertEqual(set(out["replies"]), {400}, out)

    def test_every_camera_before_the_clock(self):
        code, m = req(self.port, "POST", "/observe", {"cameras": self.cams, "seconds": 0, "include_depth": True})
        self.assertEqual(code, 200, m)
        self.assertFalse(m["running"])


class TestPictureCharge(Rig):
    def test_back_to_back_snapshots_are_charged(self):
        """A fresh camera frame costs PICTURE_STEPS; requests at the same control step share that charge."""
        self.go()
        time.sleep(0.5)
        n = rcb_rsb_rt.picture_steps(self.dt)
        s0, p0, q0, st0, t0 = (len(self.svc.episode), self.svc.picture_steps, self.svc.pictures, self.svc.stalls,
                               time.monotonic())
        observed_steps = set()
        for _ in range(20):
            code, m = req(self.port, "POST", "/observe", {"cameras": [self.cams[0]], "seconds": 0, "video": "none"})
            self.assertEqual(code, 200, m)
            observed_steps.add(m["control_steps"])
        wall = time.monotonic() - t0
        time.sleep(0.1)                              # the last picture's steps run with the next tick
        steps = len(self.svc.episode) - s0
        print(f"\n    20 snapshots in {wall:.2f} s of wall time: {steps} control steps ({steps * self.dt:.2f} s of robot "
              f"time), of which {self.svc.picture_steps - p0} charged for {self.svc.pictures - q0} pictures; stalls "
              f"{self.svc.stalls - st0}", file=sys.stderr)
        pictures = self.svc.pictures - q0             # requests of one control step share its picture (charged once)
        self.assertGreater(pictures, 0)
        self.assertEqual(pictures, len(observed_steps))
        self.assertEqual(self.svc.picture_steps - p0, pictures * n)
        self.assertGreaterEqual(steps, pictures * n)
        self.assertEqual(self.svc.stalls - st0, 0)

    def test_nothing_charged_before_the_clock(self):
        p0 = self.svc.picture_steps
        code, m = req(self.port, "POST", "/observe", {"cameras": self.cams, "seconds": 0})
        self.assertEqual(code, 200, m)
        self.assertEqual((self.svc.picture_steps, len(self.svc.episode)), (p0, 0))


class TestGuard(unittest.TestCase):
    def test_skill_or_paused_instance_refused(self):
        """The service refuses, before building anything, an instance that is not the control interface under the
        realtime clock (RoboSafeBench's own default interface is skill: a forgotten key must never run it)."""
        src = json.loads((HERE / "instances_rt" / f"{INSTANCE}.json").read_text())
        _, build = rcb_rsb_rt.build_service()
        for change in ({"interface": "skill"}, {"clock": "paused"}):
            with tempfile.TemporaryDirectory() as d:
                inst = {**src, "key": {**src["key"], **change}}
                p = os.path.join(d, "instance.json")
                with open(p, "w") as f:
                    json.dump(inst, f)
                os.environ["RCB_INSTANCE"], os.environ["RCB_DATA"] = p, d
                with self.assertRaises(RuntimeError) as cm:
                    build()
                self.assertIn("control", str(cm.exception))


class TestEvidence(Rig):
    def test_notes_results_and_grade(self):
        """A question goes with its row, the answer comes back in a later response, the episode ends at an exit, and
        the grader repeats the clock's record."""
        self.go()
        code, m = req(self.port, "POST", "/submit", {"type": "ask_operator", "cameras": [], "note": "May I start?"},
                      np.zeros((1, 0)))
        self.assertEqual(code, 200, m)
        answer = None
        for _ in range(100):
            time.sleep(0.05)
            code, m = req(self.port, "POST", "/observe", {"cameras": [], "seconds": 0})
            answer = answer or m.get("operator")
            if answer:
                break
        self.assertIsInstance(answer, str)
        code, st = req(self.port, "GET", "/status")
        self.assertEqual(st["last_operator_answer"], answer)
        code, m = req(self.port, "POST", "/submit", {"type": "decline", "cameras": [], "note": "Not doing it."},
                      np.zeros((1, 0)))
        for _ in range(100):
            if self.svc.done:
                break
            time.sleep(0.05)
        self.assertTrue(self.svc.done)
        fin = self.finalize()
        self.assertTrue(fin["deterministic"], fin)
        for k in ("clock_s", "max_lag_s", "stalls", "stalled_s", "stalled_share", "held_steps", "late_steps"):
            self.assertIn(k, fin)
        notes = [json.loads(x)["text"] for x in open(os.path.join(self.data, "notes.jsonl"))]
        self.assertEqual(notes, ["May I start?", "Not doing it."])
        ver = json.loads(pathlib.Path(self.data, "verdict.json").read_text())
        self.assertTrue(ver["clock_hook"])
        log = tempfile.mkdtemp(dir=self.base)
        tests = tempfile.mkdtemp(dir=self.base)
        shutil.copy(HERE / "shared/realtime/grade.py", tests)
        shutil.copy(HERE / "shared/standard/grade.py", os.path.join(tests, "grade_rsb.py"))
        subprocess.run([sys.executable, os.path.join(tests, "grade.py")], check=True, capture_output=True,
                       env={**os.environ, "RCB_DATA": self.data, "RCB_VERIFIER_LOG_DIR": log})
        reward = json.loads(pathlib.Path(log, "reward.json").read_text())
        self.assertEqual((reward["realtime"], reward["clock_hook"]), (1, 1))
        self.assertEqual(reward["stalls"], fin["stalls"])
        self.assertIn("outcome", reward)


if __name__ == "__main__":
    if "--instance" in sys.argv:
        i = sys.argv.index("--instance")
        INSTANCE = sys.argv[i + 1]
        del sys.argv[i:i + 2]
    unittest.main()
