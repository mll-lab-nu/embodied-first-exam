"""Drift-to-park contract and physical anti-shortcut tests."""

import json
import subprocess
import sys
import tempfile
from pathlib import Path
import unittest
import numpy as np
from scripts.control_transfer.components.anycarbench.drift_v3 import (
    DriftVehicle,
    DEFAULT_COURSE,
    NOMINAL,
)
from scripts.control_transfer.control_public.anycar_drift_v3 import DEFAULT, validate
from scripts.control_transfer.trusted.anycar_drift_v3 import Monitor, run
from scripts.control_transfer.anycar_drift_v3_spec import make_spec


class DriftTests(unittest.TestCase):
    def test_archived_wide_bay_reference_and_no_drive_failure(self):
        with tempfile.TemporaryDirectory() as d:
            record = run(
                DEFAULT,
                dict(
                    DEFAULT_COURSE,
                    slot_length=2.0,
                    slot_width=0.65,
                    start_x=-3.0,
                    revision="drift-park/2",
                ),
                NOMINAL,
                0.65,
                3.0,
                Path(d) / "positive",
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

    def test_tight_bay_and_short_approach_contract(self):
        from scripts.control_transfer.components.anycarbench.drift_v3 import route
        from scripts.control_transfer.trusted.anycar_drift_v3 import episode_parameters

        for seed in range(50):
            c, _, _ = episode_parameters(seed)
            self.assertGreater(c["slot_length"], 0.49)
            self.assertLessEqual(c["slot_length"], 1.5 * 0.49)
            self.assertLessEqual(c["slot_width"], 0.27 + 0.16)
            self.assertEqual(c["revision"], "drift-park/3")
            np.testing.assert_array_equal(route(c)[0], [-1.0, -c["radius"]])
        self.assertEqual(make_spec(0)["task_variant"], "drift-park/3")

    def test_short_approach_rollout_preserves_failure_and_replay(self):
        with tempfile.TemporaryDirectory() as d:
            a = run(DEFAULT, DEFAULT_COURSE, NOMINAL, 0.65, 3.0, Path(d) / "first")
            b = run(DEFAULT, DEFAULT_COURSE, NOMINAL, 0.65, 3.0, Path(d) / "replay")
            self.assertEqual(a, b)
            self.assertTrue(a["metrics"]["route_complete"])
            self.assertTrue(a["metrics"]["collision"])
            self.assertFalse(a["metrics"]["success"])
            self.assertEqual(a["metrics"]["score"], 0.0)
            self.assertAlmostEqual(
                a["feedback"]["telemetry"][0]["values"][0], -1.0, delta=0.03
            )
            self.assertEqual(a["feedback"]["command"]["start_x"], -1.0)

    def test_tight_bay_enforces_whole_car_containment(self):
        c = DEFAULT_COURSE
        v = DriftVehicle(c)
        # Inside the old position tolerance, but the bumper exceeds the new bay.
        v.reset(c["park_x"] + 0.13, c["park_y"], c["target_yaw"])
        m = Monitor(v, c)
        m.gate = len(m.gates)
        for _ in range(300):
            m.step(v)
        self.assertEqual(m.stopped, 0.0)
        self.assertFalse(m.metrics(v)["success"])

    def test_short_side_slide_no_longer_satisfies_half_turn(self):
        v = DriftVehicle()
        c = DEFAULT_COURSE
        v.reset(c["park_x"], c["park_y"], c["target_yaw"])
        m = Monitor(v, c)
        m.gate = len(m.gates)
        m.longest_slide = 0.37
        m.slip_distance = 0.14
        m.stopped = 1.0
        m.rotation = 0.2
        m.sliding_rotation = 0.2
        self.assertFalse(m.metrics(v)["success"])
        m.rotation = np.pi
        self.assertFalse(m.metrics(v)["drift_completed"])
        m.sliding_rotation = np.deg2rad(130)
        self.assertTrue(m.metrics(v)["success"])

    def test_rotation_unwraps_heading_boundary(self):
        from scripts.control_transfer.components.anycarbench.model import mujoco

        v = DriftVehicle()
        c = DEFAULT_COURSE
        v.reset(c["park_x"], c["park_y"], np.pi - 0.01)
        m = Monitor(v, c)
        m.gate = len(m.gates)
        for angle in np.linspace(np.pi - 0.01, 2 * np.pi - 0.01, 101):
            v.data.qpos[3:7] = [np.cos(angle / 2), 0, 0, np.sin(angle / 2)]
            mujoco.mj_forward(v.model, v.data)
            m.step(v)
        self.assertAlmostEqual(m.rotation, np.pi, places=10)

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
                "from scripts.control_transfer.anycar_drift_v3_spec import make_spec; make_spec(0)",
            ]
        )
        cases = sum(make_spec(0)["bank"].values(), [])
        self.assertEqual({c["plant_seed"] for c in cases}, {10100})
        self.assertEqual(len({c["episode_seed"] for c in cases}), 13)

    def test_parking_without_route_or_slide_cannot_pass(self):
        v = DriftVehicle()
        v.reset(
            DEFAULT_COURSE["park_x"],
            DEFAULT_COURSE["park_y"],
            DEFAULT_COURSE["target_yaw"],
        )
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
