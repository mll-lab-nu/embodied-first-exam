"""LIBERO-MAX standard mode, graded by the live episode (board 0151): the real sim service (rcb_service.py + server.py),
collect hook (finalize.sh) and verifier (grade.py) of scripts/libero-max/shared/standard/, on a stub lmx_tool
(tests/stub/lmx_tool.py: no simulator).

    python3 scripts/libero-max/tests/test_live_grading.py      # needs numpy
"""
from __future__ import annotations

import json
import os
import signal
import subprocess
import sys
import tempfile
import time
import unittest
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
STANDARD = HERE.parent / "shared" / "standard"
sys.path.insert(0, str(HERE / "stub"))      # lmx_tool: the stub (server.py's own directory has no lmx_tool.py)
sys.path.insert(1, str(STANDARD))
import lmx_tool  # noqa: E402
import rcb1  # noqa: E402
import rcb_service  # noqa: E402
import server  # noqa: E402
from rcb_service import GiveUp, Service  # noqa: E402

assert Path(lmx_tool.__file__).parent == HERE / "stub", lmx_tool.__file__


def final(data: str) -> dict:
    return json.loads(Path(data, "final.json").read_text())


def events(data: str) -> list[dict]:
    return [json.loads(line) for line in Path(data, "episode.jsonl").read_text().splitlines()]


class Base(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.data = os.path.join(self.tmp.name, "data")
        os.makedirs(self.data)
        self.log = os.path.join(self.tmp.name, "replays.jsonl")
        os.environ.update(RCB_DATA=self.data, LMX_STUB_LOG=self.log)

    def tearDown(self):
        for k in ("RCB_DATA", "LMX_STUB_LOG"):
            os.environ.pop(k, None)
        self.tmp.cleanup()

    def instance(self, **kw) -> str:
        inst = {"goal": 1.0, "event_at": 0.3, **kw}
        inst.setdefault("initial_state_sha", lmx_tool.sha_of(float(inst.get("start_x", 0.0)), 0))
        path = os.path.join(self.tmp.name, "instance.json")
        Path(path).write_text(json.dumps(inst))
        return path

    def service(self, **kw) -> Service:
        rcb_service.count_start(self.data)                   # a process start, as main() counts it
        sim = server.LiberoMax(self.instance(**kw), max_control_steps=50)
        svc = Service(sim, data=self.data, wall_clock_s=3600.0)
        svc.start()
        return svc

    def submit(self, svc, dx: float, n: int):
        rows = np.zeros((n, 7))
        rows[:, 0] = dx
        body = rcb1.encode({"type": "ee_delta", "dt": 0.05, "video": "none"}, [rcb1.array_part("actions", rows)])
        code, _, out = svc.handle("POST", "/submit", body)
        return code, (rcb1.decode(out)[0] if code == 200 else json.loads(out))

    def end(self, svc) -> dict:
        svc.on_sigusr1()
        svc.poll()
        return final(self.data)

    def replays(self) -> list[dict]:
        try:
            return [json.loads(line) for line in Path(self.log).read_text().splitlines()]
        except OSError:
            return []

    def grade(self, fin: dict | None = None, text: str | None = None) -> tuple[str, dict]:
        logs = os.path.join(self.tmp.name, "logs")
        if fin is not None:
            Path(self.data, "final.json").write_text(json.dumps(fin))
        if text is not None:
            Path(self.data, "final.json").write_text(text)
        env = {**os.environ, "RCB_DATA": self.data, "RCB_VERIFIER_LOG_DIR": logs}
        subprocess.run([sys.executable, str(STANDARD / "grade.py")], env=env, check=True, capture_output=True)
        r = json.loads(Path(logs, "reward.json").read_text())
        self.assertTrue(all(isinstance(v, (int, float)) for v in r.values()), r)
        self.assertNotIn("replay_success", r)
        self.assertNotIn("deterministic", r)
        return Path(logs, "reward.txt").read_text().strip(), r


class LiveVerdict(Base):
    def test_a_live_success_is_graded_1_and_nothing_replays_before_the_verdict(self):
        svc = self.service()
        code, meta = self.submit(svc, 1.0, 20)
        self.assertEqual((code, meta["done"], meta["reason"], meta["control_steps"]), (200, True, "success", 10))
        f = self.end(svc)
        self.assertEqual((f["success"], f["live_success"], f["graded_by"], f["replays"], f["finalized"]),
                         (True, True, "live", 0, True))
        self.assertEqual((f["event_fired"], f["event_step"], f["n_actions"]), (True, 3, 10))
        self.assertEqual(f["state_sha"], lmx_tool.sha_of(1.0, 10))
        self.assertNotIn("replay_success", f)
        self.assertNotIn("deterministic", f)
        self.assertNotIn("live_rule", f)                     # LIBERO's rule is the live one: no extra check
        self.assertEqual((f["video"], f["video_pending"], f["video_source"]), (True, False, "render"))
        # exactly one replay ran, the video pass, and only once the verdict was on disk
        self.assertEqual(self.replays(), [{"replay": True, "video": True, "after_verdict": True}])
        rec = json.loads(Path(self.data, "replay.video.json").read_text())
        self.assertTrue(rec["ends_in_live_state"])
        txt, r = self.grade()
        self.assertEqual((txt, r["success"], r["live_success"], r["graded_by_live"], r["replays"], r["infra_error"]),
                         ("1", 1, 1, 1, 0, 0))
        self.assertEqual((r["event_fired"], r["event_step"], r["video_rendered"]), (1, 3, 1))

    def test_a_live_failure_is_graded_0_not_infra(self):
        svc = self.service()
        self.submit(svc, 0.5, 5)                              # x = 0.25: neither goal nor event
        f = self.end(svc)
        self.assertEqual((f["success"], f["live_success"], f["reason"], f["event_fired"]), (False, False, "timeout", False))
        txt, r = self.grade()
        self.assertEqual((txt, r["success"], r["infra_error"], r["timeout"], r["event_step"]), ("0", 0, 0, 1, 0))

    def test_the_adapter_has_no_grading_replay(self):
        sim = server.LiberoMax(self.instance())
        self.assertFalse(hasattr(sim, "verify"))
        self.assertEqual(set(sim.live_verdict(np.zeros((0, 7)), False)), {"event_fired", "event_step"})


class Video(Base):
    def run_mode(self, mode: str) -> dict:
        svc = self.service(video=mode)
        self.submit(svc, 1.0, 10)
        return self.end(svc)

    def test_a_failed_video_leaves_the_verdict(self):
        f = self.run_mode("fail")
        self.assertEqual((f["success"], f["finalized"], f["video"], f["video_pending"]), (True, True, False, False))
        self.assertFalse(Path(self.data, "replay.mp4").exists())
        self.assertIn("video_error", [e["ev"] for e in events(self.data)])
        self.assertEqual(self.grade()[1]["success"], 1)

    def test_a_video_pass_over_its_time_leaves_the_verdict(self):
        old, server.VIDEO_TIMEOUT_S = server.VIDEO_TIMEOUT_S, 2.0
        try:
            t = time.time()
            f = self.run_mode("hang")
        finally:
            server.VIDEO_TIMEOUT_S = old
        self.assertLess(time.time() - t, 30)
        self.assertEqual((f["success"], f["video"], f["video_pending"]), (True, False, False))

    def test_a_video_pass_that_diverges_is_recorded_and_decides_nothing(self):
        f = self.run_mode("diverge")
        self.assertEqual((f["success"], f["video"]), (True, True))
        self.assertFalse(json.loads(Path(self.data, "replay.video.json").read_text())["ends_in_live_state"])

    def test_the_verdict_is_on_disk_before_the_video_pass(self):
        seen = {}
        svc = self.service()
        render = svc.sim.render_video

        def watch(rows, path):
            seen.update(final(self.data))
            render(rows, path)
        svc.sim.render_video = watch
        self.submit(svc, 1.0, 10)
        f = self.end(svc)
        self.assertEqual((seen["finalized"], seen["success"], seen["video_pending"], seen["video"]), (True, True, True, False))
        self.assertEqual({k: f[k] for k in seen if not k.startswith("video")},
                         {k: seen[k] for k in seen if not k.startswith("video")})


class Infra(Base):
    def test_a_scene_off_the_frozen_start_is_instance_mismatch(self):
        with self.assertRaises(GiveUp):
            self.service(initial_state_sha="f" * 64)
        f = final(self.data)
        self.assertEqual((f["finalized"], f["success"], f["infra_error"]), (True, False, 1))
        self.assertTrue(f["reason"].startswith("instance_mismatch"))
        self.assertEqual(self.replays(), [])
        txt, r = self.grade()
        self.assertEqual((txt, r["infra_error"], r["instance_mismatch"]), ("0", 1, 1))

    def test_crashes_between_calls_are_infrastructure(self):
        svc = self.service(goal=99)
        self.submit(svc, 0.5, 2)
        for _ in range(2):
            self.service(goal=99)                             # restarts that resume the same episode
        with self.assertRaises(GiveUp):
            self.service(goal=99)
        f = final(self.data)
        self.assertEqual((f["reason"], f["infra_error"], f["success"]), ("sim_crashed", 1, False))
        self.assertEqual(self.grade()[1]["infra_error"], 1)

    def test_crashes_all_inside_calls_are_the_agents(self):
        svc = self.service(goal=99)
        self.submit(svc, 0.5, 2)
        for i in range(3):
            with open(os.path.join(self.data, "episode.jsonl"), "a") as fh:
                fh.write(json.dumps({"ts": 0, "ev": "call_begin", "path": "/submit", "call": 2}) + "\n")
            if i < 2:
                self.service(goal=99)
        with self.assertRaises(GiveUp):
            self.service(goal=99)
        f = final(self.data)
        self.assertEqual((f["reason"], f.get("infra_error", 0)), ("sim_crashed_on_call", 0))
        txt, r = self.grade()
        self.assertEqual((txt, r["success"], r["infra_error"], r["sim_crashed_on_call"]), ("0", 0, 0, 1))

    def test_a_restart_after_the_verdict_keeps_it(self):
        svc = self.service()
        self.submit(svc, 1.0, 10)
        before = self.end(svc)
        with self.assertRaises(GiveUp):
            self.service()
        after = final(self.data)
        self.assertEqual({k: after[k] for k in before}, before)


class Grade(Base):
    LIVE = {"finalized": True, "success": True, "live_success": True, "graded_by": "live", "replays": 0,
            "reason": "success", "event_fired": True, "event_step": 7, "video": True, "video_pending": False}

    def test_missing_unreadable_or_unfinalized_is_infrastructure(self):
        txt, r = self.grade()
        self.assertEqual((txt, r["missing_log"], r["infra_error"]), ("0", 1, 1))
        for text in ('{"finalized": true, "live_succ', "[1, 2]", "null", ""):
            txt, r = self.grade(text=text)
            self.assertEqual((txt, r["infra_error"], r["grader_error"]), ("0", 1, 1), text)
        txt, r = self.grade({**self.LIVE, "finalized": False})
        self.assertEqual((txt, r["infra_error"]), ("0", 1))

    def test_success_is_the_live_verdict(self):
        self.assertEqual(self.grade(self.LIVE)[0], "1")
        for k, v in (("live_success", False), ("success", False), ("graded_by", None)):
            self.assertEqual(self.grade({**self.LIVE, k: v})[0], "0", k)

    def test_a_video_never_finished_costs_nothing(self):
        txt, r = self.grade({**self.LIVE, "video": False, "video_pending": True})
        self.assertEqual((txt, r["infra_error"], r["video_rendered"]), ("1", 0, 0))

    def test_agent_outcomes_are_never_infra(self):
        for reason in ("error", "timeout", "failed", "sim_crashed_on_call"):
            txt, r = self.grade({**self.LIVE, "success": False, "live_success": False, "reason": reason})
            self.assertEqual((txt, r["infra_error"]), ("0", 0), reason)
        self.assertEqual(self.grade({**self.LIVE, "success": False, "live_success": False, "reason": "error"})[1]["sim_error"], 1)

    def test_service_side_failures_are_infra(self):
        txt, r = self.grade({"finalized": True, "success": False, "reason": "sim_crashed", "infra_error": 1})
        self.assertEqual((txt, r["infra_error"]), ("0", 1))
        txt, r = self.grade({"finalized": True, "finalize_error": "boom", "live_success": True})
        self.assertEqual((txt, r["infra_error"], r["grader_error"]), ("0", 1, 1))


FAKE = r'''
import json, os, signal, sys, time
data, video_s = sys.argv[1], float(sys.argv[2])
def on_usr1(*_):
    d = {"finalized": True, "success": True, "live_success": True, "graded_by": "live", "replays": 0,
         "video": False, "video_pending": True}
    json.dump(d, open(os.path.join(data, "final.json"), "w"))
    if video_s >= 0:
        time.sleep(video_s)
        json.dump({**d, "video": True, "video_pending": False}, open(os.path.join(data, "final.json"), "w"))
signal.signal(signal.SIGUSR1, on_usr1)
open(os.path.join(data, "server.pid"), "w").write(str(os.getpid()))
while True:
    time.sleep(0.1)
'''


class Hook(Base):
    def hook(self, video_s: float, wait_s: int) -> tuple[float, dict]:
        proc = subprocess.Popen([sys.executable, "-c", FAKE, self.data, str(video_s)])
        try:
            for _ in range(100):
                if Path(self.data, "server.pid").exists():
                    break
                time.sleep(0.05)
            t = time.time()
            env = {**os.environ, "RCB_DATA": self.data, "RCB_COLLECT_WAIT_S": str(wait_s), "RCB_COLLECT_POLL_S": "0.2"}
            subprocess.run(["sh", str(STANDARD / "finalize.sh")], env=env, check=True, capture_output=True, timeout=60)
            return time.time() - t, final(self.data)
        finally:
            proc.send_signal(signal.SIGKILL)
            proc.wait()

    def test_the_hook_waits_for_the_video_after_the_verdict(self):
        dt, f = self.hook(video_s=2, wait_s=30)
        self.assertLess(dt, 15)
        self.assertEqual((f["finalized"], f["video"], f["video_pending"]), (True, True, False))

    def test_the_hook_stops_at_its_bound_and_the_verdict_stands(self):
        dt, f = self.hook(video_s=-1, wait_s=3)               # the video never finishes
        self.assertLess(dt, 15)
        self.assertEqual((f["finalized"], f["video_pending"]), (True, True))
        self.assertEqual(self.grade()[0], "1")

    def test_finalize_is_well_formed(self):
        text = (STANDARD / "finalize.sh").read_text()
        self.assertIn(f'RCB_COLLECT_WAIT_S:-{5400}', text)
        for gone in ("RCB_FAIL_WAIT_S", "RCB_VIDEO_GRACE_S", '"deterministic"'):
            self.assertNotIn(gone, text)


if __name__ == "__main__":
    unittest.main()
