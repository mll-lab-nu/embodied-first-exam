"""Revision identity, readiness and privacy regressions; standard-library only."""

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
from scripts.control_transfer.specs import FAMILIES, spec
from scripts.control_transfer.gen_tasks import render
from scripts.control_transfer.check_contract import check

LEGACY_DIGESTS = [
    "c2fe542954cc2a0217c6941c03f7b49a1219d0244ef83529a14e06742f043a82",
    "2c51aff182730dfa3a671213dfe32a2af9f5aa0f3b7b0feada6248133e601d9e",
]


class NeuralFlyPackaging(unittest.TestCase):
    def test_explicit_revision_preserves_accepted_legacy_specs(self):
        for index in range(2):
            old = spec("neural-fly", index)
            digest = hashlib.sha256(json.dumps(old, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
            self.assertEqual(digest, LEGACY_DIGESTS[index])
            new = spec("neural-fly-general-v1", index)
            self.assertEqual(new["family"], "neural-fly")
            self.assertEqual(new["task_revision"], "general-eight/1")
            self.assertEqual(new["public"]["name"], "neural-fly-general-v1")
            for part in ("adaptation", "held_out"):
                self.assertEqual(len(new["bank"][part]), len(old["bank"][part]))
                for a, b in zip(new["bank"][part], old["bank"][part]):
                    self.assertEqual(a, dict(b, trajectory_revision="general-eight/1"))
        self.assertIn("neural-fly-general-v1", FAMILIES)

    def test_generated_general_readiness_and_boundary(self):
        with tempfile.TemporaryDirectory() as tmp:
            task = Path(tmp) / "control-transfer-neural-fly-general-v1-i00-standard"
            previous = os.umask(0o022)
            try:
                render(task, "neural-fly-general-v1", 0)
                self.assertEqual(check(task), [])
            finally:
                os.umask(previous)
            metadata = tomllib.loads((task / "task.toml").read_text())["metadata"]
            self.assertEqual(metadata["oracle"], "full")   # its reference run, gen_tasks.EVIDENCE (#329 review)
            self.assertIn("10/10 held-out cases", metadata["oracle_evidence"])
            public = task / "environment/public"
            public_spec = json.loads((public / "task-spec.json").read_text())
            self.assertEqual(public_spec["task_revision"], "general-eight/1")
            for key in ("plant_seed", "episode_seed", "bank", "private_asset"):
                self.assertNotIn(key, json.dumps(public_spec))
            self.assertFalse(any("trusted" in p.parts or p.name.endswith("spec.py") for p in public.rglob("*")))
            # the exact-contract checker rejects an oracle level its reference run does not support
            toml = task / "task.toml"
            toml.write_text(toml.read_text().replace('oracle = "full"', 'oracle = "partial"'))
            self.assertTrue(any("task.toml" in error for error in check(task)))

    def test_static_registry_has_no_simulation_imports(self):
        code = """
import sys
sys.path.insert(0, sys.argv[1])
def deny(event, args):
    if event == 'import' and args[0].split('.')[0] in {'numpy','mujoco','torch','warp'}:
        raise AssertionError(args[0])
sys.addaudithook(deny)
from scripts.control_transfer.specs import spec
for name in ('neural-fly','neural-fly-general-v1'):
    for index in range(2):
        assert spec(name,index)['name'] == name
"""
        subprocess.run([sys.executable, "-I", "-B", "-S", "-c", code, str(ROOT)], check=True, capture_output=True)


if __name__ == "__main__":
    unittest.main()
