"""Noisy-state switching, finite artifact boundary, and predictive drift tests."""

import json
import math
import tempfile
import unittest
from pathlib import Path

import numpy as np

from scripts.control_transfer.components.anycarbench.drift_v3 import DEFAULT_COURSE
from scripts.control_transfer.control_public.anycar_drift_v3 import (
    DEFAULT as OLD,
)
from scripts.control_transfer.control_public.anycar_drift_v3 import (
    Controller,
    LegacyController,
    validate,
)
from scripts.control_transfer.control_public.anycar_drift_feedback import (
    DEFAULT,
)
from scripts.control_transfer.control_public.anycar_drift_feedback import (
    Controller as FeedbackController,
)


class FeedbackDriftTests(unittest.TestCase):
    def test_tight_bay_reference_and_no_handbrake_ablation(self):
        from scripts.control_transfer.components.anycarbench.model import NOMINAL
        from scripts.control_transfer.trusted.anycar_drift_v3 import run

        with tempfile.TemporaryDirectory() as d:
            passed = run(
                DEFAULT, DEFAULT_COURSE, NOMINAL, 0.65, 3.0, Path(d) / "positive"
            )
            self.assertTrue(passed["metrics"]["success"], passed["metrics"])
            self.assertFalse(passed["metrics"]["collision"])
            self.assertGreater(passed["metrics"]["stopped_for_s"], 0.5)
            failed = run(
                dict(DEFAULT, brake=0.0),
                DEFAULT_COURSE,
                NOMINAL,
                0.65,
                3.0,
                Path(d) / "no_handbrake",
            )
            self.assertFalse(failed["metrics"]["success"])
            self.assertEqual(failed["metrics"]["score"], 0.0)

    def test_versioned_numeric_boundary(self):
        self.assertEqual(json.loads(validate(DEFAULT)), DEFAULT)
        self.assertIsInstance(Controller(OLD, DEFAULT_COURSE), LegacyController)
        self.assertIsInstance(Controller(DEFAULT, DEFAULT_COURSE), FeedbackController)
        for bad in [
            dict(DEFAULT, yaw_rate_gain=float("nan")),
            dict(DEFAULT, brake_speed=True),
            dict(DEFAULT, code="execute"),
            dict(DEFAULT, brake_remaining_rad=7),
            dict(DEFAULT, entry_speed=6),
        ]:
            with self.assertRaises(ValueError):
                validate(bad)

    def test_acceleration_precedes_legacy_trigger(self):
        new = Controller(DEFAULT, DEFAULT_COURSE)
        old = Controller(OLD, DEFAULT_COURSE)
        point = new.path[100]
        for c in [new, old]:
            c.index = 100
        o = np.r_[point, 2.4, 1.2, 0.0, 0.0, np.zeros(5)]
        self.assertEqual(new.step(o)[0], DEFAULT["entry_speed"])
        self.assertEqual(old.step(o)[0], OLD["route_speed"])

    def test_velocity_predicts_drift_start_relative_to_bay(self):
        c = Controller(dict(DEFAULT, trigger_preview_s=0.1), DEFAULT_COURSE)
        c.phase = "entry"
        boundary = DEFAULT_COURSE["park_x"] + DEFAULT["drift_lead_m"]
        o = np.r_[
            boundary + 0.15,
            DEFAULT_COURSE["radius"],
            math.pi,
            2.0,
            0.0,
            0.0,
            np.zeros(5),
        ]
        c.step(o)
        self.assertEqual(c.phase, "turn")
        c = Controller(dict(DEFAULT, trigger_preview_s=0.1), DEFAULT_COURSE)
        c.phase = "entry"
        o[3] = 0.0
        c.step(o)
        self.assertEqual(c.phase, "entry")

    def test_drive_reduction_precedes_countersteer(self):
        c = Controller(
            dict(DEFAULT, brake_remaining_rad=1.5, yaw_preview_s=0.0), DEFAULT_COURSE
        )
        c.phase = "turn"
        c.heading = 5.0
        c.previous_yaw = 5.0 - 2 * math.pi
        o = np.r_[-1.7, 1.6, c.previous_yaw, 1.0, -0.5, 2.0, np.zeros(5)]
        action = c.step(o)
        self.assertEqual(c.phase, "turn")
        self.assertEqual(action[0], DEFAULT["brake_speed"])
        self.assertEqual(action[1], DEFAULT["turn_steer"])

    def test_yaw_rate_predicts_countersteer_and_latches(self):
        p = dict(DEFAULT, yaw_preview_s=0.2, counter_offset_rad=0.0)
        for rate, expected in [(0.0, "turn"), (2.0, "counter")]:
            c = Controller(p, DEFAULT_COURSE)
            c.phase = "turn"
            c.heading = 2 * math.pi - 0.3
            c.previous_yaw = -0.3
            o = np.r_[-1.7, 1.4, -0.3, 1.0, -0.4, rate, np.zeros(5)]
            action = c.step(o)
            self.assertEqual(c.phase, expected)
            if expected == "counter":
                self.assertEqual(action[0], 0.0)
                self.assertLess(action[1], 0.0)
                o[2] = -0.4
                c.step(o)
                self.assertEqual(c.phase, "counter")


if __name__ == "__main__":
    unittest.main()
