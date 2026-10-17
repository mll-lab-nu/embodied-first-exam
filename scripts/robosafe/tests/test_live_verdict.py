#!/usr/bin/env python3
"""The standard and standard-realtime tasks are graded by the live episode (owner, 2026-10-17, board 0151): the real
server.py (both releases' adapters, scripts/robosafe/shared/ and shared-0.5.3/) on the real rcb_service.py, driven
through Service.handle() with a stand-in for RoboSafeBench (numpy; no simulator, no subprocess), then the real
tests/grade.py on what the service wrote:
  - a live success scores 1, a live failure 0; verdict.json is RoboSafeBench's verdict on the live episode;
  - live_verdict can only take a success away (live_rule);
  - no replay runs: no subprocess, no replay.py, one RoboSafeBench episode built before the verdict (the video's
    Session is the only other, after it);
  - a failed video leaves the verdict as it is; a start that is not the frozen instance's is instance_mismatch (infra);
  - a give-up after crashes between calls is infra, after crashes inside the calls a 0 that is not;
  - no final.json is infra; the realtime adapter adds clock_hook to verdict.json and replays nothing either;
  - a live pass judged at the time limit and at the step cap, also after a crash between the end and its judging;
  - the realtime service end to end through on_sigusr1() and poll().
Pillow and imageio are not needed (the video's encoder and PIL are stand-ins when they are missing).

    python3 scripts/robosafe/tests/test_live_verdict.py            # every release and clock, each in its own process
"""
from __future__ import annotations

import hashlib
import json
import os
import pathlib
import subprocess
import sys
import tempfile
import time
import types
import unittest
from unittest import mock

HERE = pathlib.Path(__file__).resolve().parents[1]
RELEASE = os.environ.get("RSB_TEST_RELEASE", "0.5.4")
CLOCK = os.environ.get("RSB_TEST_CLOCK", "paused")
OWN = HERE / "shared-0.5.3" if RELEASE == "0.5.3" else HERE / "shared"
STARTS = []                                          # every RoboSafeBench episode built (the fake verify.start)


class Ep:
    """A stand-in RoboSafeBench episode under the control interface: a point that moves; `done` ends it."""
    interface = "control"
    control_dt, max_control_steps = 0.02, 400
    cameras, proprio_layout = ["front"], ["x", "y"]

    def __init__(self, key):
        self.key, self.clock = dict(key), dict(key).get("clock", "paused")
        self.pos, self.ended, self.calls, self.picture_events = [0.0, 0.0], None, [], []
        self.world = types.SimpleNamespace(tick=0)
        self.render_fails = False
        self.pass_without_exit = False                    # a member that passes judged as it stands (no exit)

    def action_types(self):
        return {"joint_position": {"dim": 2, "layout": ["x", "y"], "lower": [-1, -1], "upper": [1, 1], "units": "m",
                                   "semantics": "where", "interpolable": True, "text": False},
                "done": {"dim": 0, "layout": [], "lower": [], "upper": [], "units": "", "semantics": "the exit",
                         "interpolable": False, "text": True}}

    def camera_spec(self):
        return {"front": {"depth": False}}

    def proprio(self):
        return list(self.pos)

    def act(self, typ, row, text):
        self.calls.append(typ)
        self.world.tick += 1
        if typ == "done":
            self.ended = {"reason": "done", "text": text}
        else:
            if row[0] > 0.95:
                raise RuntimeError("the arm hit the table")      # a sim error the agent's row caused
            self.pos = [float(v) for v in row]
        return {"ok": True, "result": None}

    tick = None                                       # no external-clock hooks: the realtime adapter's fallback

    def execute(self, call, think_ticks=1):
        return self.act(*call)

    def command(self, typ):
        return list(self.pos) if typ == "joint_position" else []

    def hold(self):
        return "joint_position", list(self.pos)

    def render(self, cam):
        import numpy as np
        if self.render_fails or os.environ.get("RSB_TEST_RENDER_FAILS") and len(STARTS) > 1:
            raise RuntimeError("no GL")
        return np.zeros((4, 4, 3), np.uint8)

    def capture_pictures(self, cams):
        self.picture_events.append({"k": "capture", "frame_id": len(self.picture_events), "cameras": cams,
                                    "calls": len(self.calls), "tick": self.world.tick})
        return len(self.picture_events) - 1

    def deliver_only(self):
        pass

    def deliver_picture_frames(self, ids):
        pass

    def state_hash(self):
        return hashlib.sha256(json.dumps([self.key.get("seed", 0), self.pos, self.world.tick]).encode()).hexdigest()

    def record(self):
        return {"calls": list(self.calls), "picture_events": list(self.picture_events)}


class Family:
    def judge(self, inst, ep):
        ok = (bool(ep.ended) or ep.pass_without_exit) and ep.pos[0] > 0.5
        return {"pass": ok, "outcome": "safe_done" if ok else "gave_up", "judgment_class": "completed" if ok else "incapable",
                "marks": {"looked": None}, "ended": ep.ended or {}, "events": []}


def start(key):
    ep = Ep(key)
    STARTS.append(ep)
    return Family(), None, ep


def install():
    for name in ("robosafebench", "robosafe"):     # the package's name from 0.5.4, and before
        pkg, verify = types.ModuleType(name), types.ModuleType(name + ".verify")
        verify.start = start
        pkg.verify = verify
        sys.modules[name], sys.modules[name + ".verify"] = pkg, verify
    try:
        from PIL import Image  # noqa: F401
    except ImportError:                                   # render_video saves the last frame with PIL: a stand-in
        pil = types.ModuleType("PIL")
        pil.Image = types.SimpleNamespace(fromarray=lambda a: types.SimpleNamespace(
            save=lambda path: open(path, "wb").close()))
        sys.modules["PIL"], sys.modules["PIL.Image"] = pil, pil.Image
    dirs = ([OWN / "realtime", HERE / "shared/realtime"] if CLOCK == "realtime" else []) + [OWN / "standard",
                                                                                            HERE / "shared/standard"]
    sys.path[:0] = [str(d) for d in dirs]


def no_subprocess(*a, **k):
    raise AssertionError(f"a subprocess was started in the finalize: {a[:1]}")


class Live(unittest.TestCase):
    """Through the paused service (standard); the realtime service's finalize is the same layer code."""

    def setUp(self):
        if CLOCK == "realtime" and self._testMethodName not in (
                "test_realtime_adapter", "test_realtime_service_through_sigusr1", "test_a_sim_error_in_a_call_is_0_not_infra",
                "test_a_wrong_realtime_instance_is_instance_mismatch"):
            self.skipTest("paused clock only")
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.dir = pathlib.Path(self.tmp.name)
        self.data = self.dir / "data"
        self.data.mkdir()
        os.environ["RCB_DATA"] = str(self.data)
        STARTS.clear()

    def instance(self, frozen=True):
        key = {"family": "f", "member": "m", "seed": 0, "interface": "control",
               **({"clock": "realtime"} if CLOCK == "realtime" else {})}
        sha = Ep(key).state_hash() if frozen else "0" * 64
        inst = {"key": key, "state_sha": sha, "slug": "x01-i00", "robot_title": "a test arm", "task_text": "move"}
        p = self.dir / "instance.json"
        p.write_text(json.dumps(inst))
        return str(p)

    def service(self, frozen=True, max_resumes=2):
        import rcb_service
        if CLOCK == "realtime":
            import rcb_rsb_rt
            svc_cls, build = rcb_rsb_rt.build_service()
            os.environ["RCB_INSTANCE"] = self.instance(frozen)
            return rcb_rsb_rt, build(), svc_cls
        import server
        return server, server.RoboSafe(self.instance(frozen)), rcb_service.Service

    def paused(self, frozen=True, max_resumes=2):
        mod, sim, cls = self.service(frozen, max_resumes)
        svc = cls(sim, data=str(self.data), max_resumes=max_resumes)
        return mod, sim, svc

    def submit(self, svc, typ, rows, note=None):
        body = json.dumps({"type": typ, "actions": rows, "cameras": ["front"], "video": "none",
                           **({"note": note} if note else {})}).encode()
        return svc.handle("POST", "/submit", body)[0]

    def finalize(self, svc):
        import rcb_service
        with mock.patch.object(subprocess, "Popen", side_effect=no_subprocess), \
                mock.patch.object(rcb_service, "encode_mp4", lambda frames, fps: b"mp4"):
            svc.on_sigusr1()
            svc.poll()
        return json.loads((self.data / "final.json").read_text())

    def grade(self, final=True):
        log = self.dir / "log"
        log.mkdir(exist_ok=True)
        if not final:
            (self.data / "final.json").unlink(missing_ok=True)
        tests = self.dir / "tests"
        tests.mkdir(exist_ok=True)
        std = OWN / "standard/grade.py"
        if CLOCK == "realtime":
            (tests / "grade.py").write_bytes((HERE / "shared/realtime/grade.py").read_bytes())
            (tests / "grade_rsb.py").write_bytes(std.read_bytes())
        else:
            (tests / "grade.py").write_bytes(std.read_bytes())
        subprocess.run([sys.executable, str(tests / "grade.py")], check=True, capture_output=True,
                       env={**os.environ, "RCB_DATA": str(self.data), "RCB_VERIFIER_LOG_DIR": str(log)})
        return (log / "reward.txt").read_text().strip(), json.loads((log / "reward.json").read_text())

    def episode(self, x):
        _, sim, svc = self.paused()
        svc.start()
        self.assertEqual(self.submit(svc, "joint_position", [[x, 0.0]] * 5), 200)
        if CLOCK != "realtime":
            self.assertEqual(self.submit(svc, "done", [[]], note="finished"), 200)
        return sim, svc

    # ------------------------------------------------------------------------------------------------------- cases
    def test_live_success_scores_1_and_no_replay_runs(self):
        sim, svc = self.episode(0.8)
        self.assertFalse(hasattr(sim, "verify"))
        n_live = len(STARTS)
        fin = self.finalize(svc)
        self.assertEqual(n_live, 1)                    # the live episode only, until the verdict was written
        self.assertLessEqual(len(STARTS), 2)           # and the video's Session after it
        self.assertEqual((fin["graded_by"], fin["replays"], fin["finalized"]), ("live", 0, True))
        self.assertTrue(fin["live_rule"])
        self.assertNotIn("replay_success", fin)
        self.assertNotIn("deterministic", fin)
        ver = json.loads((self.data / "verdict.json").read_text())
        self.assertEqual(ver["graded_by"], "live")
        self.assertEqual(ver["start"]["start_sha"], ver["start"]["frozen_start_sha"])
        self.assertNotIn("replays", ver)
        self.assertTrue((self.data / "record.json").exists())
        if CLOCK == "paused":
            self.assertTrue(fin["success"] and fin["live_success"])
            self.assertEqual(fin["outcome"], "safe_done")
            txt, r = self.grade()
            self.assertEqual((txt, r["success"], r["graded_by_live"], r["replays"], r["infra_error"]), ("1", 1, 1, 0, 0))
            self.assertEqual(r["outcome_safe_done"], 1)
            self.assertNotIn("replay_success", r)
            self.assertNotIn("deterministic", r)
            self.assertTrue(fin["video"])
        else:
            self.assertIn("clock_hook", ver)

    def test_live_failure_scores_0(self):
        _, svc = self.episode(0.2)
        fin = self.finalize(svc)
        self.assertFalse(fin["success"])
        txt, r = self.grade()
        self.assertEqual((txt, r["success"], r["infra_error"]), ("0", 0, 0))

    def test_live_verdict_only_takes_a_success_away(self):
        sim, svc = self.episode(0.8)
        sim.live_verdict = lambda rows, success: {"success": False}     # e.g. a settle window that failed
        fin = self.finalize(svc)
        self.assertFalse(fin["success"])
        self.assertEqual(self.grade()[1]["success"], 0)

    def test_a_judge_that_raises_is_0_not_infra(self):
        sim, svc = self.episode(0.8)
        sim.s.judge = mock.Mock(side_effect=RuntimeError("judge broke"))
        fin = self.finalize(svc)
        self.assertFalse(fin["success"])
        self.assertIn("live_verdict_error", fin)
        txt, r = self.grade()
        self.assertEqual((txt, r["infra_error"]), ("0", 0))

    def rt_service(self):
        import rcb_realtime
        _, sim, cls = self.service()
        svc = cls(sim, data=str(self.data))
        svc.start()
        return rcb_realtime, sim, svc

    def test_a_sim_error_in_a_call_is_0_not_infra(self):
        """Paused: a row of the agent's raised a simulator error inside its call. Realtime (owner 2026-10-17, STANDARD_MODE
        Part 3): a control step after the agent's first command raised it."""
        if CLOCK == "realtime":
            rcb_realtime, sim, svc = self.rt_service()
            job = rcb_realtime._Job("POST", "/submit", json.dumps({"type": "joint_position", "actions": [[0.99, 0.0]] * 3,
                                                                    "cameras": []}).encode())
            svc.dispatch(job)
            for _ in range(500):
                if svc.done:
                    break
                svc.tick()
                time.sleep(0.002)
            self.assertTrue(svc.done)
        else:
            _, sim, svc = self.paused()
            svc.start()
            self.assertEqual(self.submit(svc, "joint_position", [[0.99, 0.0]]), 500)
        fin = self.finalize(svc)
        self.assertNotIn("infra_error", fin)
        self.assertEqual(fin["reason"], "error")
        txt, r = self.grade()
        self.assertEqual((txt, r["success"], r["infra_error"], r["sim_error"]), ("0", 0, 0, 1))

    def test_a_failed_video_leaves_the_verdict(self):
        sim, svc = self.episode(0.8)
        sim.render_video = mock.Mock(side_effect=RuntimeError("no GL"))
        fin = self.finalize(svc)
        self.assertEqual((fin["finalized"], fin["video"], fin["video_pending"]), (True, False, False))
        if CLOCK == "paused":
            self.assertTrue(fin["success"])
            txt, r = self.grade()
            self.assertEqual((txt, r["infra_error"], r["video_rendered"]), ("1", 0, 0))

    def test_another_start_is_instance_mismatch(self):
        import rcb_service
        _, sim, svc = self.paused(frozen=False)
        with self.assertRaises(rcb_service.GiveUp):
            svc.start()
        fin = json.loads((self.data / "final.json").read_text())
        self.assertTrue(fin["reason"].startswith("instance_mismatch"))
        self.assertEqual(fin["infra_error"], 1)
        txt, r = self.grade()
        self.assertEqual((txt, r["infra_error"]), ("0", 1))

    def crashed(self, in_call: bool):
        import rcb_service
        _, sim, svc = self.paused(max_resumes=0)
        rcb_service.count_start(str(self.data))
        svc.start()
        if in_call:
            svc.log("call_begin", path="/submit", call=1)    # the process died serving the agent's call
        rcb_service.count_start(str(self.data))              # compose restarts it
        _, sim2, svc2 = self.paused(max_resumes=0)
        with self.assertRaises(rcb_service.GiveUp):
            svc2.start()
        return self.grade()

    def test_crashes_between_calls_are_infra(self):
        txt, r = self.crashed(False)
        self.assertEqual((txt, r["infra_error"]), ("0", 1))

    def test_crashes_inside_the_calls_are_0_not_infra(self):
        txt, r = self.crashed(True)
        self.assertEqual((txt, r["infra_error"], r["sim_crashed_on_call"]), ("0", 0, 1))

    def test_realtime_adapter(self):
        """rcb_rsb_rt.py: no verify, the live verdict with clock_hook, the frozen start checked; the realtime grader on
        the standard rule."""
        if CLOCK != "realtime":
            self.skipTest("realtime clock only")
        import numpy as np
        _, sim, cls = self.service()
        self.assertFalse(hasattr(sim, "verify"))
        self.assertEqual(sim.start_sha, sim.s.ep.state_hash())
        sim.s.ep.ended = {"reason": "done"}
        sim.s.ep.pos = [0.8, 0.0]
        with mock.patch.object(subprocess, "Popen", side_effect=no_subprocess):
            out = sim.live_verdict(np.zeros((0, sim.raw_dim)), True)
        self.assertEqual(out["success"], True)
        ver = json.loads((self.data / "verdict.json").read_text())
        self.assertEqual((ver["graded_by"], ver["clock_hook"]), ("live", False))
        self.assertEqual(len(STARTS), 1)
        fin = {"finalized": True, "graded_by": "live", "replays": 0, "success": True, "live_success": True,
               "live_rule": True, "reason": "success", "clock_s": 3.0, "stalls": 1}
        (self.data / "final.json").write_text(json.dumps(fin))
        txt, r = self.grade()
        self.assertEqual((txt, r["graded_by_live"], r["realtime"], r["stalls"]), ("1", 1, 1, 1))
        (self.data / "final.json").write_text(json.dumps({**fin, "success": False, "live_rule": False}))
        self.assertEqual(self.grade()[0], "0")

    def test_realtime_service_through_sigusr1(self):
        """The realtime service: start, the agent gone (SIGUSR1), poll(): the live verdict, nothing replayed."""
        if CLOCK != "realtime":
            self.skipTest("realtime clock only")
        _, sim, svc = self.rt_service()
        sim.s.ep.pass_without_exit = True
        sim.s.ep.pos = [0.8, 0.0]
        fin = self.finalize(svc)
        self.assertEqual((fin["graded_by"], fin["replays"], fin["reason"], fin["success"]), ("live", 0, "timeout", True))
        self.assertTrue(fin["realtime"])
        self.assertLessEqual(len(STARTS), 2)
        ver = json.loads((self.data / "verdict.json").read_text())
        self.assertIn("clock_hook", ver)
        txt, r = self.grade()
        self.assertEqual((txt, r["graded_by_live"], r["realtime"], r["infra_error"]), ("1", 1, 1, 0))

    def test_a_wrong_realtime_instance_is_instance_mismatch(self):
        if CLOCK != "realtime":
            self.skipTest("realtime clock only")
        import rcb_service
        import rcb_rsb_rt
        _, build = rcb_rsb_rt.build_service()
        inst = json.loads(pathlib.Path(self.instance()).read_text())
        inst["key"].pop("clock")
        (self.dir / "instance.json").write_text(json.dumps(inst))
        os.environ["RCB_INSTANCE"] = str(self.dir / "instance.json")
        with self.assertRaises(rcb_service.InstanceMismatch):
            build()

    def test_a_pass_judged_at_the_time_limit(self):
        _, sim, svc = self.paused()
        svc.start()
        sim.s.ep.pass_without_exit = True
        self.assertEqual(self.submit(svc, "joint_position", [[0.8, 0.0]] * 5), 200)
        fin = self.finalize(svc)                          # SIGUSR1: the episode ends at the time limit, judged as it is
        self.assertEqual((fin["reason"], fin["success"], fin["live_rule"]), ("timeout", True, True))
        txt, r = self.grade()
        self.assertEqual((txt, r["timed_out"], r["infra_error"]), ("1", 1, 0))

    def test_a_pass_judged_at_the_step_cap(self):
        _, sim, svc = self.paused()
        svc.start()
        sim.s.ep.pass_without_exit = True
        self.assertEqual(self.submit(svc, "joint_position", [[0.8, 0.0]] * 450), 200)
        self.assertTrue(svc.done)
        self.assertEqual(len(svc.episode), Ep.max_control_steps)
        fin = self.finalize(svc)
        self.assertEqual((fin["reason"], fin["success"]), ("failed", True))
        self.assertEqual(self.grade()[0], "1")

    def test_a_crash_between_the_end_and_its_judging_keeps_the_pass(self):
        import rcb_service
        mod, sim, svc = self.paused()
        rcb_service.count_start(str(self.data))
        svc.start()
        sim.s.ep.pass_without_exit = True
        self.assertEqual(self.submit(svc, "joint_position", [[0.8, 0.0]] * 5), 200)
        mod._service_end(svc, "timeout")                  # checkpoint "end" (success false); the process dies here
        rcb_service.count_start(str(self.data))
        _, sim2, svc2 = self.paused()
        STARTS[-1].pass_without_exit = True
        svc2.start()                                      # resumes the ended episode and judges it
        self.assertTrue(svc2.done and svc2.success)
        fin = self.finalize(svc2)
        self.assertEqual((fin["reason"], fin["success"]), ("timeout", True))

    def test_a_judging_that_raised_raises_again(self):
        sim, svc = self.episode(0.8)
        calls = []

        def broken(inst, ep):
            calls.append(1)
            raise RuntimeError("judge broke")
        sim.s.family.judge = broken
        sim.s._verdict = None                             # not judged yet (the exit's judging is undone for the test)
        for _ in range(2):
            with self.assertRaises(RuntimeError):
                sim.s.judge()
        self.assertEqual(len(calls), 1)

    def test_no_final_json_is_infra(self):
        txt, r = self.grade(final=False)
        self.assertEqual((txt, r["infra_error"], r["missing_log"]), ("0", 1, 1))

    def test_a_recorded_replay_graded_final_is_graded_by_its_live_verdict(self):
        old = {"finalized": True, "success": False, "live_success": False, "replay_success": True,
               "deterministic": True, "reason": "timeout", "n_actions": 3}
        (self.data / "final.json").write_text(json.dumps(old))
        self.assertEqual(self.grade()[0], "0")
        (self.data / "final.json").write_text(json.dumps({**old, "live_success": True, "replay_success": False,
                                                          "success": False}))
        txt, r = self.grade()
        self.assertEqual((txt, r["graded_by_live"], r["infra_error"]), ("1", 0, 0))


def main() -> int:
    if os.environ.get("RSB_TEST_RELEASE"):
        install()
        return 0 if unittest.main(argv=sys.argv[:1], exit=False).result.wasSuccessful() else 1
    bad = 0
    for release in ("0.5.4", "0.5.3"):
        for clock in ("paused", "realtime"):
            print(f"== release {release}, {clock} clock", flush=True)
            env = {**os.environ, "RSB_TEST_RELEASE": release, "RSB_TEST_CLOCK": clock}
            bad += subprocess.run([sys.executable, __file__], env=env).returncode != 0
    print("all passed" if not bad else f"{bad} runs failed")
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
