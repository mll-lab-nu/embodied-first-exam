"""Generator contract checks runnable with Python -S and no simulation packages."""

import hashlib
import json
import unittest
from pathlib import Path
import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[3]))

from scripts.control_transfer.neuralfly_constants import BOUNDS, DEFAULT
from scripts.control_transfer.neuralfly_spec import make_spec


class NeuralFlySpecTests(unittest.TestCase):
    def test_spec_is_json_serializable_and_matches_public_policy(self):
        spec = make_spec(1)
        json.dumps(spec, allow_nan=False)
        self.assertEqual(spec["public"]["default_policy"], DEFAULT)
        self.assertEqual(spec["public"]["bounds"], BOUNDS)
        cases = spec["bank"]["adaptation"] + spec["bank"]["held_out"]
        self.assertEqual({c["plant_seed"] for c in cases}, {11100})

    def test_legacy_spec_exact_frozen_fingerprints(self):
        # #329 review: the public limitations text names no upstream method (the banks are unchanged)
        expected = [
            "3b0a7d0263988b8334ffe78e976f1e25036bb966a807e103bac539a537e9c7f5",
            "06bf5630910aa9baf937449ce9e60e206e431aaabba414666d7c0fd8025f0dc9",
        ]
        for i, fingerprint in enumerate(expected):
            value = make_spec(i)
            self.assertEqual(value, make_spec(i, revision="fixed-eight/1"))
            self.assertEqual(
                hashlib.sha256(json.dumps(value, sort_keys=True, allow_nan=False).encode()).hexdigest(), fingerprint
            )
            self.assertEqual(value["name"], "neural-fly")
            self.assertNotIn("task_revision", value)

    def test_force_asset_pin_is_one_value(self):
        # the generator writes the digest into the frozen instance, the evaluator checks the staged file against its own
        import re
        root = Path(__file__).resolve().parents[1]
        pins = [re.search(r'^%s = "([0-9a-f]{64})"' % name, (root / f).read_text(), re.M).group(1)
                for f, name in (("gen_tasks.py", "FLY_ASSET_SHA256"), ("trusted/fly.py", "ASSET_SHA256"))]
        self.assertEqual(pins[0], pins[1])

    def test_general_bank_requires_explicit_revision(self):
        value = make_spec(0, revision="general-eight/1")
        self.assertEqual(value["name"], "neural-fly-general-v1")
        for cases in value["bank"].values():
            for case in cases:
                self.assertEqual(case["trajectory_revision"], "general-eight/1")
        with self.assertRaises(ValueError):
            make_spec(0, revision="future")

    def test_callers_cannot_mutate_shared_defaults(self):
        spec = make_spec(0)
        spec["public"]["default_policy"]["residual"][0][0] = 9
        spec["public"]["bounds"]["kp"] = (0, 0)
        again = make_spec(0)
        self.assertEqual(again["public"]["default_policy"]["residual"][0][0], 0)
        self.assertEqual(again["public"]["bounds"]["kp"], (0.5, 20.0))


if __name__ == "__main__":
    unittest.main()
