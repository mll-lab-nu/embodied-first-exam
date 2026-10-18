"""No simulator required: native lifecycle, transport boundary and trusted verifier."""

import copy
import hashlib
import json
from pathlib import Path
import sys
import tempfile
import threading
import time
import unittest
from unittest.mock import Mock
from urllib.error import HTTPError
from urllib.request import Request, urlopen

sys.path.insert(0, str(Path(__file__).resolve().parents[3]))
from scripts.quadrotor_landing.native.service import Runtime, BoundedServer, handler, parse, select_submission
from scripts.quadrotor_landing.native.verify import verdict, digest


class Verifier(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.data = self.root / "data"
        (self.data / "session").mkdir(parents=True)
        self.instance = self.root / "instance.json"
        self.instance.write_text(
            json.dumps({"task_version": "test/1", "score_version": "test/1", "bank": {"held_out": [{}, {}]}})
        )
        self.report = {
            "task_version": "test/1",
            "score_version": "test/1",
            "score": 90.0,
            "successes": 2,
            "episodes": [
                {"case": 0, "success": True, "score": 100.0, "replay_verified": True},
                {"case": 1, "success": True, "score": 80.0, "replay_verified": True},
            ],
        }
        self.final = {
            "schema": "landing-final/1",
            "protocol": "eai-policy/1.0",
            "finalized": True,
            "infra_error": False,
            "no_submission": False,
            "instance_sha256": hashlib.sha256(self.instance.read_bytes()).hexdigest(),
        }
        self.write()

    def write(self):
        self.final["grade_sha256"] = digest(self.report)
        self.final["success"] = self.report["successes"] == len(self.report["episodes"])   # the sidecar's verdict
        (self.data / "session/grade.json").write_text(json.dumps(self.report))
        (self.data / "final.json").write_text(json.dumps(self.final))

    def result(self):
        return verdict(self.data, self.instance)

    def test_continuous_score_and_binary_contract(self):
        out = self.result()
        self.assertEqual((out["success"], out["final_reward"], out["progress"]), (1, 90.0, 0.9))
        self.assertTrue(all(type(v) in (int, float) for v in out.values()))
        self.report["episodes"][1].update(success=False, score=0)
        self.report.update(score=50.0, successes=1)
        self.write()
        out = self.result()
        self.assertEqual((out["success"], out["final_reward"], out["infra_error"]), (0, 50.0, 0))

    def test_agent_files_cannot_supply_verdict(self):
        (self.data / "final.json").unlink()
        output = self.root / "app/output"
        output.mkdir(parents=True)
        (output / "reward.json").write_text('{"success":1,"final_reward":100}')
        (output / "final.json").write_text(json.dumps(self.final))
        self.assertEqual(self.result()["infra_error"], 1)
        self.assertEqual(self.result()["success"], 0)

    def test_missing_or_corrupt_evidence_is_infrastructure_failure(self):
        for field, value in [("finalized", False), ("infra_error", True), ("instance_sha256", "bad")]:
            old = self.final[field]
            self.final[field] = value
            self.write()
            self.assertEqual(self.result()["infra_error"], 1)
            self.final[field] = old
        self.write()
        (self.data / "session/grade.json").write_text("{}")
        self.assertEqual(self.result()["infra_error"], 1)

    def test_invalid_replay_and_nonfinite_or_out_of_range_score(self):
        original = copy.deepcopy(self.report)
        for update in [{"replay_verified": False}, {"score": 101}, {"score": -1}, {"success": 1}, {"case": 7}]:
            self.report = copy.deepcopy(original)
            self.report["episodes"][0].update(update)
            self.write()
            self.assertEqual(self.result()["infra_error"], 1)
        (self.data / "session/grade.json").write_text('{"score":NaN}')
        self.assertEqual(self.result()["infra_error"], 1)

    def test_nop_is_zero_not_infrastructure_failure(self):
        self.final.update(no_submission=True, grade_sha256=None)
        (self.data / "final.json").write_text(json.dumps(self.final))
        out = self.result()
        self.assertEqual((out["success"], out["infra_error"], out["final_reward"]), (0, 0, 0))


class Lifecycle(unittest.TestCase):
    def state(self):
        return {
            "rounds": [
                {"id": "round-1", "status": "completed", "completed_at": 10},
                {"id": "round-2", "status": "completed", "completed_at": 30},
                {"id": "round-3", "status": "running"},
            ],
            "sealed": False,
        }

    def test_automatic_selection_excludes_late_and_inflight(self):
        s = self.state()
        self.assertEqual(select_submission(s, 20)["id"], "round-1")
        self.assertEqual(select_submission(s, 30)["id"], "round-2")
        self.assertIsNone(select_submission(s, 9))

    def test_explicit_seal_is_not_replaced_by_a_later_round(self):
        s = self.state()
        s.update(sealed=True, selected="round-1")
        self.assertEqual(select_submission(s, 50)["id"], "round-1")
        s["selected"] = "round-2"
        self.assertIsNone(select_submission(s, 20))

    def runtime(self, folder):
        runtime = object.__new__(Runtime)
        runtime.root = Path(folder)
        runtime.cutoff_path = runtime.root / "cutoff.json"
        runtime.instance_sha = "instance"
        runtime.residual = Path("/unused")
        runtime.lock = threading.Lock()
        runtime.stop = threading.Event()
        runtime.cutoff = 20
        runtime.wall_clock_s = 10
        runtime.session = Mock()
        runtime.session.root = runtime.root / "session"
        runtime.session.state = {**self.state(), "deadline": 20, "infrastructure_error": False, "native_started_at": 10}
        runtime.evaluate = Mock(return_value={"score": 80, "successes": 1, "episodes": [{"case": 0}]})
        return runtime

    def test_trusted_finalize_selects_once_and_closes_api(self):
        with tempfile.TemporaryDirectory() as folder:
            runtime = self.runtime(folder)
            runtime.request_finalize()
            runtime.finalize()
            self.assertEqual(runtime.session.state["selected"], "round-1")
            self.assertEqual(runtime.call("deploy", {})["error"], "Session closed")
            runtime.finalize()
            runtime.evaluate.assert_called_once()
            self.assertFalse(json.loads((runtime.root / "final.json").read_text())["infra_error"])

    def test_finalize_nop_and_failed_deployment_are_distinct(self):
        for infra in (False, True):
            with tempfile.TemporaryDirectory() as folder:
                runtime = self.runtime(folder)
                runtime.session.state.update(rounds=[], infrastructure_error=infra)
                runtime.finalize()
                final = json.loads((runtime.root / "final.json").read_text())
                self.assertEqual(final["infra_error"], infra)
                self.assertEqual(final["no_submission"], not infra)
                runtime.evaluate.assert_not_called()

    def test_clock_starts_once_and_busy_requests_do_not_race(self):
        with tempfile.TemporaryDirectory() as folder:
            runtime = self.runtime(folder)
            runtime.session.state["native_started_at"] = None
            runtime.session.call.return_value = {"ok": True}
            runtime.call("describe", {})
            deadline = runtime.session.state["deadline"]
            self.assertAlmostEqual(deadline, time.time() + 10, delta=1)
            runtime.call("describe", {})
            self.assertEqual(runtime.session.state["deadline"], deadline)
            with runtime.lock:
                self.assertEqual(runtime.call("deploy", {})["error"], "Evaluator busy")


class Transport(unittest.TestCase):
    def test_strict_json(self):
        for raw in ('{"a":1,"a":2}', '{"a":NaN}', '{"a":Infinity}'):
            with self.assertRaises(ValueError):
                parse(raw)

    def test_private_routes_paths_and_oversized_bodies_are_rejected(self):
        runtime = Mock()
        runtime.call.return_value = {"rounds_remaining": 3}
        server = BoundedServer(("127.0.0.1", 0), handler(runtime))
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            base = f"http://127.0.0.1:{server.server_port}"
            for path in ("/data/final.json", "/grade", "/reset", "/../../instance.json"):
                with self.assertRaises(HTTPError):
                    urlopen(Request(base + path, data=b"{}"), timeout=5)
            with self.assertRaises(HTTPError):
                urlopen(Request(base + "/deploy", data=b"x" * 8193), timeout=5)
            runtime.call.assert_not_called()
            spec = json.load(urlopen(base + "/spec", timeout=5))
            self.assertEqual(spec["protocol"], "eai-policy/1.0")
            json.load(urlopen(Request(base + "/describe", data=b"{}"), timeout=5))
            runtime.call.assert_called_once_with("describe", {})
        finally:
            server.shutdown()
            server.server_close()
            thread.join()


if __name__ == "__main__":
    unittest.main(verbosity=2)
