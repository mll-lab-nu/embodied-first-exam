"""Generator contract checks runnable with Python -S and no simulation packages."""

import json
import unittest

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

    def test_callers_cannot_mutate_shared_defaults(self):
        spec = make_spec(0)
        spec["public"]["default_policy"]["residual"][0][0] = 9
        spec["public"]["bounds"]["kp"] = (0, 0)
        again = make_spec(0)
        self.assertEqual(again["public"]["default_policy"]["residual"][0][0], 0)
        self.assertEqual(again["public"]["bounds"]["kp"], (0.5, 20.0))


if __name__ == "__main__":
    unittest.main()
