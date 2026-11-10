"""Tests for the gateway's trial attribution scan (gateway.parse_inspect, Trials): a bad line never wipes the map; a
scan looks at the containers of this runner's own running trials only, and no more often than it needs to.

    python3 scripts/usage_gateway/tests/test_scan.py     # stdlib only; docker is stubbed
"""
from __future__ import annotations

import pathlib
import subprocess
import sys
import tempfile
import types
import unittest
from unittest import mock

HERE = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(HERE))
import gateway  # noqa: E402


class ParseInspect(unittest.TestCase):
    def test_blank_and_partial_lines_are_skipped(self):
        out = "a__1__env 172.18.0.2\n\n   \nb__2__env\nother 172.17.0.5\nc__3__env 172.19.0.2 172.20.0.3\n"
        self.assertEqual(gateway.parse_inspect(out),
                         {"172.18.0.2": "a__1", "172.19.0.2": "c__3", "172.20.0.3": "c__3"})


class Scan(unittest.TestCase):
    def test_blank_line_keeps_every_other_trial(self):
        with tempfile.TemporaryDirectory() as td:
            jobs = pathlib.Path(td)
            for name in ("t1__aaa", "t2__bbb"):
                (jobs / "job" / name).mkdir(parents=True)
            inspect = "t1__aaa__env 172.18.0.2\n\nt2__bbb__env 172.19.0.2\n"

            def run(cmd, **_):
                return types.SimpleNamespace(stdout="id1\nid2\nid3\n" if cmd[1] == "ps" else inspect)

            trials = gateway.Trials(jobs)
            with mock.patch.object(subprocess, "run", run):
                self.assertEqual(trials.lookup("172.18.0.2"), jobs / "job" / "t1__aaa")
                self.assertEqual(trials.lookup("172.19.0.2"), jobs / "job" / "t2__bbb")


class Engine:
    """A stub docker / podman CLI: containers (id, compose project, IPs); records every call."""

    def __init__(self, containers):
        self.containers, self.calls = containers, []

    def __call__(self, cmd, **_):
        self.calls.append(cmd)
        if cmd[1] == "ps":
            want = [a.split("=", 2) for a in cmd if a.startswith("label=")]
            ids = [c for c, (proj, _ips) in self.containers.items()
                   if all(len(w) == 2 or proj == w[2] for w in want)]
            return types.SimpleNamespace(stdout="".join(f"{i}\n" for i in ids))
        if cmd[1] == "inspect":
            out = "".join(f"{self.containers[i][0]} {' '.join(self.containers[i][1])}\n" for i in cmd[4:])
            return types.SimpleNamespace(stdout=out)
        raise AssertionError(cmd)

    def inspected(self):
        return [i for c in self.calls if c[1] == "inspect" for i in c[4:]]


class OwnTrials(unittest.TestCase):
    def setUp(self):
        self.td = tempfile.TemporaryDirectory()
        self.jobs = pathlib.Path(self.td.name)
        for job, trial in (("mine", "t1__aaa"), ("mine", "t2__done"), ("theirs", "t3__ccc")):
            (self.jobs / job / trial).mkdir(parents=True)
        (self.jobs / "mine" / "t2__done" / "result.json").write_text("{}")
        self.own = self.jobs / ".gateway" / "jobs.1"
        self.own.parent.mkdir()
        self.own.write_text("mine\n../etc\nmine\n")
        self.engine = Engine({"c1": ("t1__aaa__env", ["172.18.0.2"]), "c1s": ("t1__aaa__env", ["172.18.0.3", "172.30.0.2"]),
                              "c3": ("t3__ccc__env", ["172.19.0.2"]), "cx": ("other", ["172.20.0.2"])})
        self.clock = [1000.0]
        self.patches = [mock.patch.object(subprocess, "run", self.engine),
                        mock.patch.object(gateway.time, "time", lambda: self.clock[0])]
        for p in self.patches:
            p.start()

    def tearDown(self):
        for p in self.patches:
            p.stop()
        self.td.cleanup()

    def test_only_own_running_trials_are_listed_and_inspected(self):
        trials = gateway.Trials(self.jobs, self.own)
        self.assertEqual(trials.lookup("172.18.0.3"), self.jobs / "mine" / "t1__aaa")
        self.assertIsNone(trials.lookup("172.19.0.2"))           # another runner's trial: not ours, not looked at
        for c in self.engine.calls:
            if c[1] == "ps":                                     # never an unfiltered listing of the engine
                self.assertIn("label=com.docker.compose.project=t1__aaa__env", c)
        self.assertEqual(sorted(set(self.engine.inspected())), ["c1", "c1s"])
        self.assertEqual(trials.lookup("172.30.0.2"), self.jobs / "mine" / "t1__aaa")   # every network of the sidecar

    def test_without_own_jobs_every_running_trial_is_ours(self):
        trials = gateway.Trials(self.jobs)
        self.assertEqual(trials.lookup("172.19.0.2"), self.jobs / "theirs" / "t3__ccc")
        self.assertEqual(sorted(set(self.engine.inspected())), ["c1", "c1s", "c3"])   # the finished trial is not asked for

    def test_cadence(self):
        trials = gateway.Trials(self.jobs, self.own)
        scans = lambda: sum(c[1] == "inspect" for c in self.engine.calls)
        trials.lookup("172.18.0.2")
        for dt in (1, 5, 10, 19):                               # a known address within TTL: no scan
            self.clock[0] = 1000.0 + dt
            self.assertEqual(trials.lookup("172.18.0.2"), self.jobs / "mine" / "t1__aaa")
        self.assertEqual(scans(), 1)
        self.clock[0] = 1000.0 + trials.TTL + 1
        trials.lookup("172.18.0.2")
        self.assertEqual(scans(), 2)
        trials.lookup("172.99.0.9")                             # unknown: not again within MISS_S
        self.assertEqual(scans(), 2)
        self.clock[0] += trials.MISS_S + 0.1
        self.assertIsNone(trials.lookup("172.99.0.9"))
        self.assertEqual(scans(), 3)

    def test_a_new_trial_is_found_at_its_first_request(self):
        trials = gateway.Trials(self.jobs, self.own)
        trials.lookup("172.18.0.2")
        (self.jobs / "mine2" / "t4__ddd").mkdir(parents=True)
        self.own.write_text(self.own.read_text() + "mine2\n")
        self.engine.containers["c4"] = ("t4__ddd__env", ["172.21.0.2"])
        self.clock[0] += 2
        self.assertEqual(trials.lookup("172.21.0.2"), self.jobs / "mine2" / "t4__ddd")

    def test_a_reused_address_of_a_finished_trial_is_looked_up_again(self):
        trials = gateway.Trials(self.jobs, self.own)
        self.assertEqual(trials.lookup("172.18.0.2"), self.jobs / "mine" / "t1__aaa")
        (self.jobs / "mine" / "t1__aaa" / "result.json").write_text("{}")   # t1 ended; its address goes to t5
        del self.engine.containers["c1"], self.engine.containers["c1s"]
        (self.jobs / "mine" / "t5__eee").mkdir()
        self.engine.containers["c5"] = ("t5__eee__env", ["172.18.0.2"])
        self.clock[0] += 2                                     # well within TTL
        self.assertEqual(trials.lookup("172.18.0.2"), self.jobs / "mine" / "t5__eee")

    def test_many_own_trials_one_listing(self):
        for i in range(gateway.Trials.MAX_FILTERED + 1):
            (self.jobs / "mine" / f"m{i}__x").mkdir()
        trials = gateway.Trials(self.jobs, self.own)
        self.assertEqual(trials.lookup("172.18.0.2"), self.jobs / "mine" / "t1__aaa")
        ps = [c for c in self.engine.calls if c[1] == "ps"]
        self.assertEqual(len(ps), 1)
        self.assertIn("label=com.docker.compose.project", ps[0])

    def test_job_list(self):
        self.assertEqual(gateway.read_job_list(self.own), ["mine", "mine"])
        self.assertEqual(gateway.read_job_list(self.jobs / "missing"), [])


if __name__ == "__main__":
    unittest.main()
