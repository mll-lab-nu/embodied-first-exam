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
    "232c35a8bbad0175bce9ae4246164f5161dae7cbeec03133115fa7d8402d6f25",
    "c8233434e65df739b33f4cb515613969af208a32cbdd23adc3b150d37986d784",
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
            self.assertEqual(metadata["oracle"], "none")
            self.assertIn("18 of 20", metadata["oracle_evidence"])
            public = task / "environment/public"
            public_spec = json.loads((public / "task-spec.json").read_text())
            self.assertEqual(public_spec["task_revision"], "general-eight/1")
            for key in ("plant_seed", "episode_seed", "bank", "private_asset"):
                self.assertNotIn(key, json.dumps(public_spec))
            self.assertFalse(any("trusted" in p.parts or p.name.endswith("spec.py") for p in public.rglob("*")))
            # General task cannot inherit the legacy native full-oracle declaration.
            toml = task / "task.toml"
            toml.write_text(toml.read_text().replace('oracle = "none"', 'oracle = "full"'))
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
