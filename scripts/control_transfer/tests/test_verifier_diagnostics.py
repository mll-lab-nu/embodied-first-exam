"""Private verifier diagnostics regressions; runs with Python -S, no simulator."""

import errno
import hashlib
import json
from pathlib import Path
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[3]))

from scripts.control_transfer.trusted.verify import digest, verdict


class VerifierDiagnosticsTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.instance = self.root / "instance.json"
        self.spec = {
            "bank": {"held_out": [{"episode_seed": 1}, {"episode_seed": 2}]},
            "evaluation_requirements": {"physics": "mujoco-cpu", "gpu_devices": []},
        }
        self.final = {
            "schema": "control-transfer-final/1",
            "instance_sha256": digest(self.spec),
            "finalized": True,
            "infra_error": False,
            "no_submission": False,
            "graded_by": "live",
            "success": True,
            "episodes": [
                {"case": i, "success": True, "replay_verified": True, "score": 70.0 + i, "state_sha256": "a" * 64}
                for i in range(2)
            ],
        }
        self.final["evidence_sha256"] = digest(self.final["episodes"])
        self.write(self.instance, self.spec)
        self.write(self.root / "final.json", self.final)
        (self.root / "held-out").mkdir()
        for i in range(2):
            for replay in ("a", "b"):
                self.write(
                    self.runtime(i, replay),
                    {**self.spec["evaluation_requirements"], "software_renderer_verified": replay == "a"},
                )

    @staticmethod
    def write(path, value):
        path.write_text(json.dumps(value, indent=2) + "\n")

    def runtime(self, i=1, replay="b"):
        return self.root / "held-out" / f"case-{i}-{replay}.runtime.json"

    def check(self, stage=None):
        diagnostics = {"stale": True}
        result = verdict(self.root, self.instance, diagnostics)
        self.assertEqual(result, verdict(self.root, self.instance))
        self.assertNotIn("stale", diagnostics)
        self.assertNotIn("fail_stage", result)
        self.assertEqual(diagnostics["fail_stage"], stage)
        self.assertEqual(diagnostics["status"], "rejected" if stage else "accepted")
        if stage:
            self.assertEqual(result["infra_error"], 1)
            self.assertEqual(result["episodes"], 0)
        return result, diagnostics

    def test_valid_and_exact_raw_input_hashes(self):
        result, d = self.check()
        self.assertEqual(
            result,
            {
                "success": 1,
                "infra_error": 0,
                "live_success": 1,
                "graded_by_live": 1,
                "replays": 0,
                "final_reward": 70.5,
                "progress": 0.705,
                "success_rate": 1.0,
                "episodes": 2,
            },
        )
        self.assertEqual(len(d["inputs"]), 6)
        for entry in d["inputs"]:
            raw = Path(entry["path"]).read_bytes()
            self.assertEqual(entry["size_bytes"], len(raw))
            self.assertEqual(entry["sha256"], hashlib.sha256(raw).hexdigest())
        self.assertEqual(d["expected_instance_sha256"], self.final["instance_sha256"])

    def test_missing_runtime_records_exact_exception_and_path(self):
        path = self.runtime()
        path.unlink()
        _, d = self.check("read_runtime")
        self.assertEqual((d["exception_class"], d["errno"]), ("FileNotFoundError", errno.ENOENT))
        self.assertEqual(d["path"], str(path))
        self.assertEqual((d["case"], d["replay"]), (1, "b"))
        self.assertNotIn("sha256", d["inputs"][-1])

    def test_wrong_instance_reports_both_digests(self):
        self.spec["index"] = 999
        self.write(self.instance, self.spec)
        _, d = self.check("instance_digest")
        self.assertEqual(d["expected_instance_sha256"], digest(self.spec))
        self.assertEqual(d["actual_instance_sha256"], self.final["instance_sha256"])
        self.assertNotEqual(d["expected_instance_sha256"], d["actual_instance_sha256"])

    def test_invalid_evidence_digest(self):
        self.final["episodes"][0]["score"] = 99.0
        self.write(self.root / "final.json", self.final)
        _, d = self.check("evidence_digest")
        self.assertNotEqual(d["expected_evidence_sha256"], d["actual_evidence_sha256"])

    def test_truncated_runtime_records_decode_error_and_raw_hash(self):
        self.runtime().write_bytes(b'{"physics":')
        _, d = self.check("read_runtime")
        self.assertEqual(d["exception_class"], "JSONDecodeError")
        self.assertIsNone(d["errno"])
        self.assertEqual(d["inputs"][-1]["sha256"], hashlib.sha256(b'{"physics":').hexdigest())

    def test_runtime_requirement_remains_enforced(self):
        # both graded runs are unrendered (the video is rendered after the verdict): no renderer check in the verdict
        self.write(self.runtime(), {"physics": "other", "gpu_devices": []})
        self.check("runtime_requirements")

    def test_no_submission_stays_non_infrastructure_zero(self):
        self.final.update(no_submission=True, episodes=[], evidence_sha256=digest([]))
        self.write(self.root / "final.json", self.final)
        result, d = self.check()
        self.assertEqual((result["infra_error"], result["success"], result["final_reward"]), (0, 0, 0.0))
        self.assertEqual(len(d["inputs"]), 2)


if __name__ == "__main__":
    unittest.main()
