"""Production two-process replay invariant for the actual HTTP verifiers.

Only real method/helper AST nodes are loaded: importing the simulator server
would start unrelated service machinery. Fake Popen writes actual temporary raw
replay files; no simulator, engine or subprocess is started by these tests.
"""

import ast
import copy
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import time
from types import SimpleNamespace
import unittest
from unittest.mock import patch

import numpy as np


SOURCE = Path(__file__).resolve().parents[1]
STANDARD = SOURCE / "shared/standard/server.py"
REALTIME = SOURCE / "shared/realtime/rcb_rsb_rt.py"
START_SHA = "f" * 64
FINAL_SHA = "e" * 64


def marker():
    return {'state_sha':START_SHA,'validation_mode':'local-budget-only',
            'validation_policy':{'instruction_id':'local'},'http_fresh_policy':{'instruction_id':'local'},
            'http_fresh_witness_count':1}


def write_json(path, value):
    Path(path).write_text(json.dumps(value, sort_keys=True))


def load_methods():
    """Compile both real bound-method bodies unchanged."""
    standard_tree = ast.parse(STANDARD.read_text(), filename=str(STANDARD))
    # the module's own replay deadline and its waiter, compiled unchanged
    helpers = {"time": time}
    nodes = [n for n in standard_tree.body if (isinstance(n, ast.FunctionDef) and n.name == "wait_replays")
             or (isinstance(n, ast.Assign) and any(getattr(t, "id", None) == "REPLAY_TIMEOUT_S" for t in n.targets))]
    if len(nodes) != 2:
        raise AssertionError("Expected REPLAY_TIMEOUT_S and wait_replays in " + str(STANDARD))
    exec(compile(ast.Module(body=copy.deepcopy(nodes), type_ignores=[]), str(STANDARD), "exec"), helpers)
    common = {
        "json": json,
        "os": os,
        "sys": sys,
        "np": np,
        "tempfile": tempfile,
        "subprocess": subprocess,
        "time": time,
        "REPLAY_TIMEOUT_S": helpers["REPLAY_TIMEOUT_S"],
        "wait_replays": helpers["wait_replays"],
        "rcb_service": SimpleNamespace(write_json_atomic=write_json),
    }
    server = dict(common, HERE=str(STANDARD.parent), __file__=str(STANDARD))
    methods = {}
    for clock, path, tree in (
        ("paused", STANDARD, standard_tree),
        ("realtime", REALTIME, ast.parse(REALTIME.read_text(), filename=str(REALTIME))),
    ):
        nodes = [node for node in ast.walk(tree) if isinstance(node, ast.FunctionDef) and node.name == "verify"]
        if len(nodes) != 1:
            raise AssertionError(f"Expected one actual verify method in {path}")
        namespace = dict(common, HERE=str(path.parent), __file__=str(path))
        namespace.update(
            server=SimpleNamespace(**server),
            hooked=lambda episode: True,
        )
        exec(compile(ast.Module(body=[copy.deepcopy(nodes[0])], type_ignores=[]), str(path), "exec"), namespace)
        methods[clock] = namespace["verify"]
    methods["_timeout"] = helpers["REPLAY_TIMEOUT_S"]
    methods["_wait"] = helpers["wait_replays"]
    return methods


class ProductionTwoFreshTests(unittest.TestCase):
    def setUp(self):
        self.methods = load_methods()
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.case_number = 0

    def fixture(self, instance=None, passed=True):
        self.case_number += 1
        data = Path(self.temp.name) / str(self.case_number)
        data.mkdir()
        instance = copy.deepcopy(marker() if instance is None else instance)
        instance_path = data / "instance.json"
        write_json(instance_path, instance)
        verdict = {"pass": passed, "marks": {"looked": True}, "outcome": "safe" if passed else "nop"}
        record = {
            "calls": [{"tool": "submit", "type": "done", "rows": [[]]}],
            "digests": ["native-call-digest"],
            "final_hash": FINAL_SHA,
            "picture_events": [{"k": "delivery", "frame_ids": ["original-rgb"]}],
            "native_payload": {"preserve": [1, {"nested": True}]},
        }
        actual = {"state_sha": FINAL_SHA, "start_sha": START_SHA, "verdict": verdict, "record": record}
        session = SimpleNamespace(
            notes=SimpleNamespace(texts=["operator report"]),
            ep=SimpleNamespace(picture_events=copy.deepcopy(record["picture_events"])),
            judge=lambda: copy.deepcopy(verdict),
            record=lambda: copy.deepcopy(record),
            state_sha=lambda: FINAL_SHA,
        )
        robot = SimpleNamespace(
            data=str(data), raw_dim=4, instance=instance, instance_path=str(instance_path), s=session
        )
        return robot, copy.deepcopy(actual)

    def execute(self, clock, robot, actual, launches):
        def popen(argv, *, stdout, stderr):
            self.assertEqual(stdout, subprocess.DEVNULL)
            self.assertFalse(stderr.closed)
            self.assertIn(robot.instance_path, argv)
            output = Path(argv[-2])
            self.assertEqual(output.name, f"replay{len(launches) + 1}.json")
            encoded = json.dumps(actual, sort_keys=True).encode()
            process = SimpleNamespace(returncode=None)

            def wait(timeout=None):
                self.assertIsNotNone(timeout)          # one shared deadline, never an unbounded wait
                self.assertGreater(timeout, 0)
                self.assertLessEqual(timeout, self.methods["_timeout"])
                output.write_bytes(encoded)
                process.returncode = 0
                return 0

            process.wait = wait
            process.poll = lambda: process.returncode
            launches.append({"argv": list(argv), "output": output, "raw_bytes": encoded})
            return process

        rows = np.asarray([[0.125, -0.25, 0.5, 1.0]], dtype=np.float64)
        with patch.object(subprocess, "Popen", side_effect=popen):
            result = self.methods[clock](robot, rows)
        return result

    def test_production_always_launches_two_real_witnesses_despite_budget_fields(self):
        for clock in ("paused", "realtime"):
            for passed in (True, False):
                for inst in ({"state_sha": START_SHA},marker()):
                    with self.subTest(clock=clock, passed=passed, instance=inst):
                        robot,actual=self.fixture(instance=inst,passed=passed);launches=[]
                        result=self.execute(clock,robot,actual,launches)
                        self.assertEqual(len(launches),2)
                        self.assertIs(result['success'],passed)
                        saved=json.loads((Path(robot.data)/'verdict.json').read_text())
                        self.assertEqual(saved['replays']['state_sha'],[FINAL_SHA,FINAL_SHA])
                        self.assertEqual(saved['replays']['start_sha'],[START_SHA,START_SHA])
                        self.assertNotIn('second_fresh',saved['replays'])
                        for entry in launches:self.assertEqual(entry['output'].read_bytes(),entry['raw_bytes'])

    def test_disagreeing_second_witness_still_fails_production(self):
        for clock in ("paused", "realtime"):
            robot,actual=self.fixture();launches=[]
            original=actual.copy()
            def sideeffect(argv,*,stdout,stderr):
                output=Path(argv[-2]);number=len(launches)+1
                payload=copy.deepcopy(original)
                if number==2:payload['state_sha']='0'*64
                process=SimpleNamespace(returncode=None)
                def wait(timeout=None):
                    output.write_text(json.dumps(payload));process.returncode=0;return 0
                process.wait=wait;process.poll=lambda:process.returncode;launches.append(output);return process
            with patch.object(subprocess,'Popen',side_effect=sideeffect):
                result=self.methods[clock](robot,np.zeros((1,4)))
            self.assertEqual(len(launches),2);self.assertFalse(result['success'])
            self.assertEqual(result['state_sha'],'replays-differ')
            self.assertFalse(json.loads((Path(robot.data)/'verdict.json').read_text())['replays']['agree'])

    def test_replay_deadline_kills_what_still_runs(self):
        wait_replays = load_methods()["_wait"]
        killed = []

        def proc(name, hang):
            p = SimpleNamespace(returncode=None)

            def wait(timeout=None):
                if hang and timeout is not None and p.returncode is None:
                    raise subprocess.TimeoutExpired(name, timeout)
                if p.returncode is None:
                    p.returncode = 0
                return p.returncode

            def kill():
                killed.append(name)
                p.returncode = -9

            p.wait, p.kill, p.poll = wait, kill, (lambda: p.returncode)
            return p
        with self.assertRaises(subprocess.TimeoutExpired):
            wait_replays([proc("one", False), proc("two", True)], 5)
        self.assertEqual(killed, ["two"])
        wait_replays([proc("a", False), proc("b", False)], 5)
        self.assertEqual(killed, ["two"])

if __name__=='__main__':unittest.main()
