"""Drift family admission, observation projection and standalone package checks."""

import copy
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import tomllib
import unittest

from scripts.control_transfer.gen_tasks import render
from scripts.control_transfer.check_contract import check
from scripts.control_transfer.specs import spec
from scripts.control_transfer.trusted.adapter import feedback, validate

ROOT = Path(__file__).resolve().parents[3]


class DriftPackaging(unittest.TestCase):
    def test_stdlib_registry_and_frozen_plant(self):
        code = """
import sys
sys.path.insert(0, sys.argv[1])
def deny(event, args):
    if event == 'import' and args[0].split('.')[0] in {'numpy', 'mujoco', 'torch', 'warp'}:
        raise AssertionError(args[0])
sys.addaudithook(deny)
from scripts.control_transfer.specs import spec
for i in range(2):
    s = spec('anycar-drift-v3', i)
    assert s['family'] == 'anycar-drift-v3' and s['task_variant'] == 'drift-park/3'
    assert s['schema'] == 'control-transfer-instance/2'
    assert s['transfer_track'] == 'same-plant'
    assert {c['plant_seed'] for bank in s['bank'].values() for c in bank} == {10100 + i*1000}
    assert len(s['bank']['adaptation']) == 3 and len(s['bank']['held_out']) == 10
    assert s['public']['image_interval_s'] == 0.1
"""
        subprocess.run([sys.executable, "-I", "-S", "-c", code, str(ROOT)], check=True)

    def test_command_allowlist_cannot_carry_private_fields(self):
        row = {
            "feedback": {
                "command": dict(radius=1.5, park_x=-3, park_y=2.05, slot_length=1.2, slot_width=0.65, start_x=-1.0, target_yaw=0.0, revision="drift-park/3"),
                "telemetry": [{"t": 0, "values": [0.0] * 14}],
            },
            "metrics": {"score": 100},
            "dynamics": {"plant_seed": 123},
        }
        with tempfile.TemporaryDirectory() as folder:
            got = feedback("anycar-drift-v3", row, folder)
            self.assertEqual(set(got), {"command", "telemetry", "images"})
            self.assertEqual(got["command"], row["feedback"]["command"])
            mutations = [
                lambda r: r["feedback"]["command"].update(revision="private-seed-123"),
                lambda r: r["feedback"]["command"].update(target_yaw=float("inf")),
                lambda r: r["feedback"]["command"].update(plant_seed=123),
                lambda r: r["feedback"]["command"].update(park_x=float("nan")),
                lambda r: r["feedback"]["command"].update(radius=True),
                lambda r: r["feedback"]["telemetry"][0]["values"].append(123),
                lambda r: r["feedback"].update(metrics={"score": 100}),
            ]
            for mutate in mutations:
                bad = copy.deepcopy(row)
                mutate(bad)
                with self.assertRaises(ValueError):
                    feedback("anycar-drift-v3", bad, folder)
        self.assertEqual(
            json.loads(validate("anycar-drift-v3", spec("anycar-drift-v3", 0)["public"]["default_policy"])),
            spec("anycar-drift-v3", 0)["public"]["default_policy"],
        )

    def test_generated_public_nominal_runs_without_trusted_tree(self):
        with tempfile.TemporaryDirectory() as tmp:
            task = Path(tmp) / "control-transfer-anycar-drift-v3-i00-standard"
            old = os.umask(0o022)
            try:
                render(task, "anycar-drift-v3", 0)
            finally:
                os.umask(old)
            self.assertEqual(check(task), [])
            metadata = tomllib.loads((task / "task.toml").read_text())
            self.assertEqual(metadata["metadata"]["oracle"], "none")
            self.assertEqual(metadata["agent"]["timeout_sec"], 14400)
            self.assertEqual(metadata["verifier"]["environment_mode"], "separate")
            import hashlib

            # no verifier payload copy (tasks are built from content-stamped trees, #266): tests/ ships its files
            for name in ("grade.py", "test.sh", "instance.json"):
                self.assertTrue((task / "tests" / name).is_file())
            public = task / "environment/public"
            geometry = public / "scripts/control_transfer/components/anycarbench"
            for prefix in ("control_public", "scripts/control_transfer/control_public"):
                self.assertTrue((public / prefix / "anycar_drift_feedback.py").is_file())
            self.assertEqual(
                {p.name for p in geometry.iterdir()},
                {"__init__.py", "model.py", "drift_v3.py", "LICENSE.anycar"},
            )
            self.assertFalse(any("trusted" in p.parts or p.name.endswith("spec.py") for p in public.rglob("*")))
            code = """
import sys
sys.path.insert(0, sys.argv[1])
import numpy as np
from control_public.anycar_drift_v3_nominal import train_rollout, DEFAULT
from scripts.control_transfer.control_public.anycar_drift_v3_nominal import train_rollout as alternate
a, b = train_rollout(DEFAULT), alternate(DEFAULT)
assert a.shape == (801, 15) and np.isfinite(a).all() and np.array_equal(a, b)
assert not any('trusted' in n.split('.') for n in sys.modules)
"""
            subprocess.run(
                [sys.executable, "-I", "-B", "-c", code, str(public)],
                cwd=tmp,
                check=True,
                capture_output=True,
                timeout=60,
            )

    def test_all_video_frames_reach_feedback_including_slide_and_stop(self):
        with tempfile.TemporaryDirectory() as tmp:
            video = Path(tmp) / "video.mp4"
            subprocess.run(
                [
                    "ffmpeg",
                    "-v",
                    "error",
                    "-f",
                    "lavfi",
                    "-i",
                    "color=c=orange:size=64x32:rate=10",
                    "-frames:v",
                    "161",
                    "-threads",
                    "1",
                    "-pix_fmt",
                    "yuv420p",
                    str(video),
                ],
                check=True,
            )
            row = {
                "feedback": {
                    "command": dict(
                        radius=1.5,
                        park_x=-3,
                        park_y=2.05,
                        slot_length=1.2,
                        slot_width=0.65,
                        start_x=-1.0, target_yaw=0.0, revision="drift-park/3",
                    ),
                    "telemetry": [],
                }
            }
            images = feedback("anycar-drift-v3", row, tmp)["images"]
            self.assertEqual(len(images), 161)
            self.assertEqual([x["time_s"] for x in images], [i / 10 for i in range(161)])


if __name__ == "__main__":
    unittest.main()
