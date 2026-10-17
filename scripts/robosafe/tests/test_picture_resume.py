#!/usr/bin/env python3
"""server.py after a crash-resume: the recorded picture events the replayed journal did not reach are dropped and
DATA/picture_events.jsonl is rewritten as the events the resumed episode holds, so the next picture does not fail
("not reached") on every restart; Service._resume calls it (numpy; no simulator: the session is a stand-in).

    python3 scripts/robosafe/tests/test_picture_resume.py
"""
import json
import os
import pathlib
import sys
import tempfile
import types
import unittest

STANDARD = pathlib.Path(__file__).resolve().parents[1] / "shared/standard"
sys.path.insert(0, str(STANDARD))
sys.modules.setdefault("rcb_rsb", types.ModuleType("rcb_rsb"))   # server.py imports it; nothing here uses it
import server  # noqa: E402


class PictureResume(unittest.TestCase):
    def robot(self, d, history, reached):
        r = object.__new__(server.RoboSafe)
        r.data, r._picture_path = d, os.path.join(d, "picture_events.jsonl")
        with open(r._picture_path, "w") as f:
            f.writelines(json.dumps(e) + "\n" for e in history)
        r._pictures_written = len(history)
        r.s = types.SimpleNamespace(_picture_replay=history[len(reached):], ep=types.SimpleNamespace(picture_events=list(reached)))
        return r

    def test_unreached_events_are_dropped_and_the_file_rewritten(self):
        h = [{"k": "capture", "frame_id": 0, "calls": 1, "tick": 5}, {"k": "delivery", "frame_ids": [0], "calls": 1, "tick": 9}]
        with tempfile.TemporaryDirectory() as d:
            r = self.robot(d, h, h[:1])
            self.assertEqual(r.trim_picture_replay(), 1)
            self.assertEqual(r.s._picture_replay, [])
            lines = [json.loads(x) for x in pathlib.Path(r._picture_path).read_text().splitlines()]
            self.assertEqual(lines, h[:1])
            self.assertEqual(r._pictures_written, 1)
            r.s.ep.picture_events.append({"k": "capture", "frame_id": 1, "calls": 2, "tick": 7})
            r._persist_picture_events()               # appends after the rewritten prefix, nothing skipped
            self.assertEqual(len(pathlib.Path(r._picture_path).read_text().splitlines()), 2)

    def test_nothing_unreached_leaves_the_file(self):
        h = [{"k": "capture", "frame_id": 0, "calls": 1, "tick": 5}]
        with tempfile.TemporaryDirectory() as d:
            r = self.robot(d, h, h)
            before = pathlib.Path(r._picture_path).read_text()
            self.assertEqual(r.trim_picture_replay(), 0)
            self.assertEqual(pathlib.Path(r._picture_path).read_text(), before)

    def test_service_resume_calls_it(self):
        self.assertIs(server.rcb_service.Service._resume, server._resume)
        logged, calls = [], []
        svc = types.SimpleNamespace(sim=types.SimpleNamespace(trim_picture_replay=lambda: 2),
                                    log=lambda ev, **kw: logged.append((ev, kw)))
        orig = server._service_resume
        server._service_resume = lambda self, ev: calls.append(ev)
        try:
            server._resume(svc, ["e"])
        finally:
            server._service_resume = orig
        self.assertEqual(calls, [["e"]])
        self.assertEqual(logged, [("picture_events_dropped", {"n": 2})])


if __name__ == "__main__":
    unittest.main()
