"""Historical coverage, curve feasibility, ordered scoring and public packaging checks."""

import json
import subprocess
import sys
import unittest
import numpy as np
from scripts.control_transfer.components.anycarbench.tracks import catalog, track_ids, get_route, resolve_track
from scripts.control_transfer.control_public.anycar import reference, HORIZON
from scripts.control_transfer.trusted.anycar import score_trajectory


class CircuitTests(unittest.TestCase):
    def test_all_historical_venues_have_runnable_layout(self):
        data = catalog()
        self.assertEqual(data["revision"], "7cf634e8e0dadd6d3bfdbbe880e34f8cae5698fa")
        self.assertEqual(len(data["circuits"]), 160)
        venues = {x["circuit_id"] for x in data["circuits"].values()}
        self.assertEqual(len(venues), 78)
        self.assertEqual(len(track_ids()), 160)  # 159 source layouts + synthetic zigzag
        for name in venues:
            self.assertIn(resolve_track(name), track_ids())
        with self.assertRaisesRegex(ValueError, "Disjoint"):
            resolve_track("buenos-aires-1")
        with self.assertRaises(ValueError):
            resolve_track("../private")

    def test_all_interpolants_close_and_respect_steering(self):
        for name in track_ids():
            with self.subTest(name=name):
                route = get_route(name)
                points = route.at(np.linspace(0, route.length, 4096))
                self.assertTrue(np.isfinite(points).all())
                np.testing.assert_allclose(route.at(0), route.at(route.length), atol=1e-10)
                self.assertLess(np.max(np.abs(points[:, 3])), 1.2)
                if route.scale is not None:
                    self.assertLess(route.scale, 1.0)
                self.assertGreaterEqual(route.length, 79.99)

    def test_circuit_generation_without_site_packages(self):
        result = subprocess.check_output(
            [
                sys.executable,
                "-S",
                "-c",
                "import json,sys; from scripts.control_transfer.anycar_spec import make_circuit_spec; "
                "s=make_circuit_spec(1,'monaco'); assert 'numpy' not in sys.modules and 'mujoco' not in sys.modules; print(json.dumps(s))",
            ],
            text=True,
        )
        spec = json.loads(result)
        self.assertEqual(spec["public"]["track_id"], "monaco-6")
        self.assertEqual(spec["task_variant"], "circuit-lap/2")
        self.assertTrue(all(c["full_lap"] for bank in spec["bank"].values() for c in bank))
        self.assertEqual({c["plant_seed"] for bank in spec["bank"].values() for c in bank}, {11100})
        self.assertTrue(all(c["track_id"] == "monaco-6" for bank in spec["bank"].values() for c in bank))

    def test_full_lap_requires_finish_and_measures_crossing(self):
        from scripts.control_transfer.control_public.anycar import DT

        route = get_route("silverstone")
        command = dict(track_id="silverstone", start_fraction=0.23, speed=0.85, full_lap=True)
        expected = route.length / 0.85 + 0.5
        targets = np.array([reference(t, command) for t in np.arange(0, expected + 0.1, DT)])
        states = np.zeros((len(targets), 11))
        states[:, :4] = targets[:, :4]
        result = score_trajectory(states, targets, command)
        self.assertTrue(result["success"], result)
        self.assertTrue(result["full_lap_completed"])
        self.assertAlmostEqual(result["lap_time_s"], expected, delta=DT)
        # Almost a lap is insufficient, even if tracking was perfect until stopping.
        incomplete = score_trajectory(states[:-20], targets[:-20], command)
        self.assertFalse(incomplete["success"])
        self.assertFalse(incomplete["full_lap_completed"])
        self.assertIsNone(incomplete["lap_time_s"])
        standing = np.repeat(states[:1], len(states), axis=0)
        self.assertFalse(score_trajectory(standing, targets, command)["success"])
        self.assertFalse(score_trajectory(states[::-1], targets, command)["success"])

    def test_ordered_gates_reject_standing_reverse_and_shortcuts(self):
        for name in ["zigzag", "monaco", "suzuka"]:
            command = dict(track_id=name, start_fraction=0.0, speed=0.85)
            targets = np.array([reference(t, command) for t in np.linspace(0, HORIZON, 1201)])
            states = np.zeros((1201, 11))
            states[:, :4] = targets[:, :4]
            result = score_trajectory(states, targets, command)
            self.assertTrue(result["success"], (name, result))
            self.assertGreater(result["score"], 99)
            stationary = np.tile(states[0], (1201, 1))
            stationary[:, 3] = 0
            self.assertEqual(score_trajectory(stationary, targets, command)["score"], 0)
            self.assertFalse(score_trajectory(states[::-1], targets, command)["success"])
            shortcuts = states.copy()
            shortcuts[:, :2] = np.linspace(states[0, :2], states[-1, :2], 1201)
            if np.max(np.linalg.norm(shortcuts[:, :2] - states[:, :2], axis=1)) > 0.7:
                self.assertFalse(score_trajectory(shortcuts, targets, command)["success"])


if __name__ == "__main__":
    unittest.main()
