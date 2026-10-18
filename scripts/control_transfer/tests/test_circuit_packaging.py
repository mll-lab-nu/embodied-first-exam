"""Circuit generation and trust-boundary checks requiring only the standard library."""

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
from scripts.control_transfer.gen_tasks import render
from scripts.control_transfer.check_contract import check


class CircuitPackaging(unittest.TestCase):
    def test_all_layout_specs_are_stdlib_and_distinct(self):
        code = """
import sys
sys.path.insert(0, sys.argv[1])
def deny(event, args):
    if event == 'import' and args[0].split('.')[0] in {'numpy', 'mujoco', 'torch', 'warp'}:
        raise AssertionError(args[0])
sys.addaudithook(deny)
from scripts.control_transfer.specs import spec
from scripts.control_transfer.components.anycarbench.tracks import track_ids
ids = track_ids()
assert len(ids) == 160
names = set()
for track in ids:
    for index in range(2):
        name = 'anycar-circuit-v1-' + track
        s = spec(name, index)
        assert s['name'] == name and s['public']['track_id'] == track
        assert s['task_variant'] == s['public']['task_variant'] == 'circuit-sector/1'
        assert {c['plant_seed'] for bank in s['bank'].values() for c in bank} == {10100 + index*1000}
        assert all(c['track_id'] == track for bank in s['bank'].values() for c in bank)
        names.add((name, index))
assert len(names) == 320
"""
        subprocess.run([sys.executable, "-I", "-S", "-c", code, str(ROOT)], check=True, capture_output=True)

    def test_generated_geometry_allowlist_and_private_bank(self):
        with tempfile.TemporaryDirectory() as tmp:
            task = Path(tmp) / "control-transfer-anycar-circuit-v1-zigzag-i00-standard"
            previous = os.umask(0o022)
            try:
                render(task, "anycar-circuit-v1-zigzag", 0)
                self.assertEqual(check(task), [])
            finally:
                os.umask(previous)
            public = task / "environment/public"
            geometry = public / "scripts/control_transfer/components/anycarbench"
            self.assertEqual(
                {p.name for p in geometry.iterdir()},
                {
                    "__init__.py",
                    "model.py",
                    "tracks.py",
                    "circuits.json",
                    "route_lengths.json",
                    "compact_routes.json",
                    "LICENSE.anycar",
                    "LICENSE.f1db",
                    "NOTICE",
                },
            )
            self.assertFalse(any("trusted" in p.parts or p.name.endswith("spec.py") for p in public.rglob("*")))
            public_spec = json.loads((public / "task-spec.json").read_text())
            self.assertEqual(public_spec["track_id"], "zigzag")
            self.assertNotIn("plant_seed", json.dumps(public_spec))
            self.assertNotIn("episode_seed", json.dumps(public_spec))
            private_spec = json.loads((task / "tests/instance.json").read_text())
            self.assertEqual(len(private_spec["bank"]["held_out"]), 10)
            metadata = tomllib.loads((task / "task.toml").read_text())["metadata"]
            self.assertEqual(metadata["oracle"], "none")
            self.assertIn("--track zigzag", (task / "instruction.md").read_text())
            # A misplaced operator bank must fail the existing exact package boundary.
            (public / "anycar_spec.py").write_text("plant_seed = 10100\n")
            self.assertTrue(any("anycar_spec.py" in e for e in check(task)))


if __name__ == "__main__":
    unittest.main()
