"""Drift-to-park contract and physical anti-shortcut tests."""

import json
import subprocess
import sys
import tempfile
from pathlib import Path
import unittest
import numpy as np
from scripts.control_transfer.components.anycarbench.drift import (
    DriftVehicle,
    DEFAULT_COURSE,
    NOMINAL,
)
from scripts.control_transfer.control_public.anycar_drift import DEFAULT, validate
from scripts.control_transfer.trusted.anycar_drift import Monitor, run
from scripts.control_transfer.anycar_drift_spec import make_spec


class DriftTests(unittest.TestCase):
    def test_nominal_reference_and_no_drive_failure(self):
        with tempfile.TemporaryDirectory() as d:
            record = run(
                DEFAULT, DEFAULT_COURSE, NOMINAL, 0.65, 3.0, Path(d) / "positive"
            )
            self.assertTrue(record["metrics"]["success"], record["metrics"])
            self.assertEqual(set(record["feedback"]), {"command", "telemetry"})
            self.assertEqual(len(record["feedback"]["telemetry"]), 161)
            self.assertTrue(
                all(len(r["values"]) == 14 for r in record["feedback"]["telemetry"])
            )
            for key in (
                "metrics",
                "friction",
                "plant_seed",
                "episode_seed",
                "brake_torque",
            ):
                self.assertNotIn(key, json.dumps(record["feedback"]))
            failed = run(
                dict(DEFAULT, route_speed=0.2, entry_speed=0.0),
                DEFAULT_COURSE,
                NOMINAL,
                0.65,
                3.0,
                Path(d) / "slow",
            )
            self.assertFalse(failed["metrics"]["success"])
            self.assertEqual(failed["metrics"]["score"], 0)

    def test_numeric_policy_boundary(self):
        for p in (
            {},
            dict(DEFAULT, brake=float("nan")),
            dict(DEFAULT, brake=True),
            dict(DEFAULT, entry_speed=100),
            dict(DEFAULT, code="exec"),
        ):
            with self.assertRaises(ValueError):
                validate(p)
        self.assertEqual(json.loads(validate(DEFAULT)), DEFAULT)

    def test_stdlib_spec_and_same_plant(self):
        subprocess.check_call(
            [
                sys.executable,
                "-S",
                "-c",
                "from scripts.control_transfer.anycar_drift_spec import make_spec; make_spec(0)",
            ]
        )
        cases = sum(make_spec(0)["bank"].values(), [])
        self.assertEqual({c["plant_seed"] for c in cases}, {10100})
        self.assertEqual(len({c["episode_seed"] for c in cases}), 13)

    def test_parking_without_route_or_slide_cannot_pass(self):
        v = DriftVehicle()
        v.reset(DEFAULT_COURSE["park_x"], DEFAULT_COURSE["park_y"], np.pi)
        m = Monitor(v, DEFAULT_COURSE)
        for _ in range(40):
            v.advance([0, 0, 1], m.step)
        self.assertFalse(m.metrics(v)["success"])
        self.assertFalse(m.metrics(v)["route_complete"])
        m.gate = len(m.gates)
        for _ in range(40):
            v.advance([0, 0, 1], m.step)
        self.assertGreater(m.stopped, 0.5)
        self.assertFalse(m.metrics(v)["drift_completed"])
        self.assertEqual(m.metrics(v)["score"], 0)

    def test_parked_cars_are_solid_collision_geometry(self):
        v = DriftVehicle()
        c = DEFAULT_COURSE
        v.reset(c["park_x"] + c["slot_length"] / 2 + 0.25, c["park_y"], 0)
        for _ in range(5):
            v.advance([0, 0, 0])
        self.assertTrue(v.collision)

    def test_rear_brake_changes_actual_wheel_motion(self):
        wheel_rates = []
        for brake in (0.0, 1.0):
            v = DriftVehicle()
            v.reset(-3, -1.5, 0)
            for _ in range(50):
                v.advance([2, 0, 0])
            for _ in range(25):
                v.advance([2, 0, brake])
            wheel_rates.append(float(np.mean(abs(v.data.qvel[v.rear_dofs]))))
        self.assertLess(wheel_rates[1], wheel_rates[0] * 0.5)


if __name__ == "__main__":
    unittest.main()
