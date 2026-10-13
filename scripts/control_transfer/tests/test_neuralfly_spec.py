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
        expected = [
            "809cc5405c6f324c49106bc309a751a2a7eeb11c60ae1d7009a0a1b999e05406",
            "930e6c105347b146fa695b6b8bea79ef92d6093cfc5978c9e168a5e695a9a7be",
        ]
        for i, fingerprint in enumerate(expected):
            value = make_spec(i)
            self.assertEqual(value, make_spec(i, revision="fixed-eight/1"))
            self.assertEqual(
                hashlib.sha256(json.dumps(value, sort_keys=True, allow_nan=False).encode()).hexdigest(), fingerprint
            )
            self.assertEqual(value["name"], "neural-fly")
            self.assertNotIn("task_revision", value)

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
