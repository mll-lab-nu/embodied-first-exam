"""Guard the separation between the experiment and main's accepted registry."""

import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import tomllib
import unittest

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts"))

import task_conventions as official  # noqa: E402
from scripts.control_transfer import proposal  # noqa: E402
from scripts.control_transfer.check_proposal import check  # noqa: E402
from scripts.control_transfer.gen_tasks import render as render_transfer  # noqa: E402
from scripts.quadrotor_landing.gen_tasks import render as render_landing  # noqa: E402


class ProposalBoundary(unittest.TestCase):
    def setUp(self):
        previous = os.umask(0o022)
        self.addCleanup(os.umask, previous)

    def test_proposal_settings_do_not_change_main_module(self):
        self.assertNotIn("Control Transfer", official.CUTOFF_CAP_EXCEPTIONS)
        self.assertFalse(any(p.startswith(("control-transfer-", "quadrotor-landing-")) for p, _ in official.BENCHMARKS))
        self.assertEqual(official.RESOURCES_FILE, ROOT / "scripts/task_resources.toml")
        self.assertEqual(proposal.cutoff_sec("Control Transfer", "standard"), 14400)
        self.assertNotIn("Control Transfer", official.cutoff_table())

    def test_generators_refuse_accepted_registry_before_writing(self):
        target = ROOT / "tasks/control-transfer-test-proposal-i00-standard"
        self.assertFalse(target.exists())
        with self.assertRaisesRegex(ValueError, "accepted tasks/ registry"):
            render_transfer(target, "anycar", 0)
        with self.assertRaisesRegex(ValueError, "accepted tasks/ registry"):
            render_landing(target, 0)
        with self.assertRaises(ValueError):
            proposal.require_experimental_destination(ROOT / "experimental/../tasks")
        self.assertFalse(target.exists())

    def test_frozen_instances_and_official_manifest_stay_separate(self):
        rows = json.loads((proposal.PROPOSAL_ROOT / "migration.json").read_text())["tasks"]
        manifest = tomllib.loads((ROOT / "tasks/dataset.toml").read_text())
        official_ids = {r["name"] for r in manifest["tasks"]}
        for row in rows:
            task = ROOT / row["new_path"]
            self.assertFalse((ROOT / row["old_path"]).exists())
            self.assertNotIn("robot-coding-bench/" + row["id"], official_ids)
            for relative in ("environment/sim/instance.json", "tests/instance.json"):
                self.assertEqual(hashlib.sha256((task / relative).read_bytes()).hexdigest(), row["instance_sha256"])

    def test_main_checker_still_rejects_experimental_protocol(self):
        task = proposal.TASK_ROOT / "control-transfer-anycar-i00-standard"
        result = subprocess.run(
            [sys.executable, str(ROOT / "ci_checks/check-protocol.py"), str(task)],
            capture_output=True,
            text=True,
            check=False,
        )
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("standard-mode `protocol` not in", result.stdout)

    def test_landing_hidden_payload_and_grader_mutations_are_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            task = Path(directory) / "quadrotor-landing-random-pad-i00-standard"
            render_landing(task, 0)
            self.assertEqual(check(task), [])
            for relative in ("environment/public/scripts/quadrotor_landing/public/model.py", "tests/grade.py"):
                file = task / relative
                original = file.read_bytes()
                file.write_bytes(original + b"\nPRIVATE_SEED = 1\n")
                self.assertTrue(check(task), relative)
                file.write_bytes(original)

    def test_transfer_hidden_payload_and_revision_mutations_are_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            task = Path(directory) / "control-transfer-neural-fly-general-v1-i00-standard"
            render_transfer(task, "neural-fly-general-v1", 0)
            self.assertEqual(check(task), [])
            meta = tomllib.loads((task / "task.toml").read_text())["metadata"]
            self.assertTrue(meta["experimental"])
            self.assertEqual(meta["seeds"]["allowed"], [0])
            hidden = task / "environment/public/private.py"
            hidden.write_text("PRIVATE_SEED = 1\n")
            self.assertTrue(check(task))
            hidden.unlink()
            file = task / "environment/sim/instance.json"
            file.write_text(file.read_text().replace("general-eight/1", "fixed-eight/1"))
            self.assertTrue(check(task))


if __name__ == "__main__":
    unittest.main()
