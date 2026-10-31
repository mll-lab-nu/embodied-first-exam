"""Tests for the gateway's trial attribution scan (gateway.parse_inspect, Trials._scan): a bad line never wipes the map.

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


if __name__ == "__main__":
    unittest.main()
