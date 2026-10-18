"""Vector wind is a separate experimental task; privileged traces never enter feedback."""

import copy
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import tomllib
import unittest

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT))
from scripts.control_transfer.specs import spec, FAMILIES
from scripts.control_transfer.gen_tasks import render
from scripts.control_transfer.check_contract import check

NAME = "neural-fly-vector-wind-v1"


class WindPackagingTests(unittest.TestCase):
    def test_separate_revision_and_unchanged_trajectory_banks(self):
        self.assertIn(NAME, FAMILIES)
        for index in range(2):
            old, new = spec("neural-fly-general-v1", index), spec(NAME, index)
            self.assertEqual(new["task_revision"], "general-eight-wind/1")
            self.assertEqual(new["public"]["dynamics_revision"], "vector-wind/1")
            self.assertEqual(old["public"]["score"], new["public"]["score"])
            for split in ("adaptation", "held_out"):
                self.assertEqual(
                    new["bank"][split], [dict(c, dynamics_revision="vector-wind/1") for c in old["bank"][split]]
                )

    def test_no_wind_truth_or_operator_renderer_in_public_package(self):
        with tempfile.TemporaryDirectory() as directory:
            task = Path(directory) / f"control-transfer-{NAME}-i00-standard"
            previous = os.umask(0o022)
            try:
                render(task, NAME, 0)
                self.assertEqual(check(task), [])
            finally:
                os.umask(previous)
            metadata = tomllib.loads((task / "task.toml").read_text())["metadata"]
            self.assertEqual(metadata["oracle"], "full")   # its reference run, gen_tasks.EVIDENCE (#329 review)
            self.assertNotIn("18 of 20", metadata["oracle_evidence"])
            for path in (task / "environment/public").rglob("*"):
                if path.is_file():
                    self.assertNotIn("trusted", path.parts)
                    for forbidden in (
                        "wind.npz",
                        "wind_phase",
                        "wind_vector",
                        "velocity_world",
                        "plant_seed",
                        "episode_seed",
                        "neuralfly_wind_demo",
                    ):
                        self.assertNotIn(forbidden, path.read_text(), str(path))
            self.assertFalse(list(task.rglob("neuralfly_wind_demo.py")))
            private = task / "environment/sim/scripts/control_transfer/trusted/fly.py"
            self.assertIn('out / "wind.npz"', private.read_text())
            # The existing exact-contract checker rejects both oracle inflation and a leaked artifact.
            toml = task / "task.toml"
            toml.write_text(toml.read_text().replace('oracle = "full"', 'oracle = "none"'))
            self.assertTrue(check(task))
            toml.write_text(toml.read_text().replace('oracle = "none"', 'oracle = "full"'))
            (task / "environment/public/wind.npz").write_bytes(b"private")
            self.assertTrue(check(task))

    def test_stdlib_registry(self):
        code = """
import sys
sys.path.insert(0,sys.argv[1])
def deny(event,args):
    if event=='import' and args[0].split('.')[0] in {'mujoco','numpy','torch','warp'}: raise AssertionError(args[0])
sys.addaudithook(deny)
from scripts.control_transfer.specs import spec
for index in (0,1): assert spec('neural-fly-vector-wind-v1',index)['dynamics_revision']=='vector-wind/1'
"""
        subprocess.run([sys.executable, "-I", "-B", "-S", "-c", code, str(ROOT)], check=True, capture_output=True)

    def test_feedback_rejects_wind_fields_and_ignores_private_files(self):
        from scripts.control_transfer.trusted.adapter import feedback

        row = dict(
            t=0.0,
            position=[0.0] * 3,
            velocity=[0.0] * 3,
            omega=[0.0] * 3,
            quaternion=[1.0, 0.0, 0.0, 0.0],
            target_position=[0.0] * 3,
            target_velocity=[0.0] * 3,
            target_acceleration=[0.0] * 3,
        )
        record = {"feedback": {"telemetry": [row]}, "dynamics": {"wind_phase": 1.1}, "wind": [1, 2, 3]}
        with tempfile.TemporaryDirectory() as directory:
            (Path(directory) / "wind.npz").write_bytes(b"private")
            delivered = feedback("neural-fly", record, directory)
            self.assertEqual(delivered, {"telemetry": [row], "images": []})
            for nested in (False, True):
                broken = copy.deepcopy(record)
                target = broken["feedback"]["telemetry"][0] if nested else broken["feedback"]
                target["velocity_world"] = [1, 2, 3]
                with self.assertRaises(ValueError):
                    feedback("neural-fly", broken, directory)


if __name__ == "__main__":
    unittest.main()
