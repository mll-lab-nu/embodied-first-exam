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
                "s=make_circuit_spec(1,'monaco',revision='circuit-lap/2'); assert 'numpy' not in sys.modules and 'mujoco' not in sys.modules; print(json.dumps(s))",
            ],
            text=True,
        )
        spec = json.loads(result)
        self.assertEqual(spec["public"]["track_id"], "monaco-6")
        self.assertEqual(spec["task_variant"], "circuit-lap/2")
        self.assertTrue(all(c["full_lap"] for bank in spec["bank"].values() for c in bank))
        self.assertEqual({c["plant_seed"] for bank in spec["bank"].values() for c in bank}, {11100})
        self.assertTrue(all(c["track_id"] == "monaco-6" for bank in spec["bank"].values() for c in bank))

    def test_sector_specs_match_frozen_pre_lap_revision(self):
        import hashlib
        from scripts.control_transfer.anycar_spec import make_circuit_spec

        # Canonical spec digests from pre-lap commit 1cac5b65fb65, with the #329 review's limitations text.
        frozen = [(0, 'zigzag', '64a0165da4529ba578c227bcd33117d3c39665fd6152082ccdde42123276f0ca'), (1, 'monaco', 'a6622af4c95cc1faaa1730be6fd7e2d2b58032d1a4f112b874f1f38d2371f627'), (0, 'silverstone', 'b7c14eb88f48df6c4217e9da5ed75d2c81586cf85a19c8973aa3035a005a5031')]
        for index, name, expected in frozen:
            spec = make_circuit_spec(index, name)
            raw = json.dumps(spec, sort_keys=True, separators=(",", ":")).encode()
            self.assertEqual(hashlib.sha256(raw).hexdigest(), expected)
            self.assertEqual(spec, make_circuit_spec(index, name, revision="circuit-sector/1"))
            self.assertTrue(all("full_lap" not in c for bank in spec["bank"].values() for c in bank))
        with self.assertRaises(ValueError):
            make_circuit_spec(0, "silverstone", revision="circuit-lap/3")

    def test_stdlib_metadata_matches_every_physics_route(self):
        import math
        from scripts.control_transfer.components.anycarbench.tracks import route_metadata, route_metadata_catalog

        rows = route_metadata_catalog()["routes"]
        self.assertEqual(set(rows), set(track_ids()))
        for name in track_ids():
            length = get_route(name).length
            self.assertEqual(route_metadata(name)["scaled_length_m"], length)
            self.assertEqual(rows[name]["horizon_s"], math.ceil((length / .85 + 2.5) / .02) * .02)
        self.assertEqual(max(rows, key=lambda n: rows[n]["horizon_s"]), "valencia-1")
        result = subprocess.check_output([sys.executable, "-S", "-c",
            "import sys; from scripts.control_transfer.components.anycarbench.tracks import route_metadata_catalog; "
            "r=route_metadata_catalog()['routes']; assert 'numpy' not in sys.modules; "
            "assert 'mujoco' not in sys.modules; print(max(v['horizon_s'] for v in r.values()))"], text=True)
        self.assertEqual(float(result), 3878.76)

    def test_stdlib_budget_covers_all_160_runnable_routes(self):
        import math
        from scripts.control_transfer.components.anycarbench.tracks import route_budget

        for name in track_ids():
            steps = math.ceil((get_route(name).length / .85 + 2.5) / .02)
            budget = route_budget(name)
            self.assertGreaterEqual(budget["horizon_upper_bound_s"], steps * .02)
            self.assertGreaterEqual(budget["control_steps_upper_bound"], steps)
            self.assertGreaterEqual(budget["telemetry_rows_upper_bound"], steps // 5 + 1)
            self.assertGreaterEqual(budget["decoded_frames_upper_bound"], steps // 5 + 1)
            self.assertFalse(budget["wall_time_is_guaranteed_bound"])
        result = subprocess.check_output([sys.executable, "-S", "-c",
            "import json,sys; from scripts.control_transfer.components.anycarbench.tracks import track_ids,route_budget; "
            "r=[route_budget(n) for n in track_ids()]; assert len(r)==160; "
            "assert 'numpy' not in sys.modules and 'mujoco' not in sys.modules; "
            "print(json.dumps(max(r,key=lambda x:x['horizon_upper_bound_s'])))"], text=True)
        largest = json.loads(result)
        self.assertEqual(largest["track_id"], "valencia-1")
        self.assertEqual(largest["horizon_upper_bound_s"], 3880)
        self.assertEqual(largest["render_wall_time_estimate_s"], 7820)

    def test_compact_catalog_is_closed_steerable_and_fixed_duration(self):
        from scripts.control_transfer.components.anycarbench.tracks import compact_catalog, compact_route_budget

        self.assertEqual(set(compact_catalog()["routes"]), set(track_ids()))
        for name in track_ids():
            route = get_route(name, "compact-30s/1")
            np.testing.assert_allclose(route.at(0), route.at(route.length), atol=1e-10)
            self.assertAlmostEqual(route.length, 45.0, places=6)
            self.assertLessEqual(np.max(np.abs(route.at(np.linspace(0,route.length,8192))[:,3])), .81)
            self.assertEqual(compact_route_budget(name)["horizon_upper_bound_s"], 30)
        with self.assertRaises(ValueError):
            get_route("silverstone", "unknown")

    def test_compact_spec_stdlib_and_completed_lap_scoring(self):
        code = ("import json,sys; from scripts.control_transfer.anycar_spec import make_circuit_spec; "
                "s=make_circuit_spec(0,'monaco',revision='circuit-compact-lap/3'); "
                "assert 'numpy' not in sys.modules and 'mujoco' not in sys.modules; print(json.dumps(s))")
        spec = json.loads(subprocess.check_output([sys.executable, "-S", "-c", code], text=True))
        self.assertEqual(spec["public"]["horizon_s"], 30)
        self.assertTrue(all(c["full_lap"] and c["route_revision"]=="compact-30s/1"
                            for bank in spec["bank"].values() for c in bank))
        for name in ("silverstone", "monaco", "suzuka"):
            route = get_route(name, "compact-30s/1")
            command = dict(track_id=name, route_revision="compact-30s/1", start_fraction=.23,
                           speed=route.length/27.5, full_lap=True)
            targets = np.array([reference(t,command) for t in np.arange(1501)*.02])
            states = np.zeros((1501,11)); states[:,:4]=targets[:,:4]
            result = score_trajectory(states,targets,command)
            self.assertTrue(result["success"], result)
            self.assertAlmostEqual(result["lap_time_s"],28.0,delta=.02)
            self.assertFalse(score_trajectory(states[:1351],targets[:1351],command)["success"])
            stationary = np.repeat(states[:1],1501,axis=0)
            self.assertEqual(score_trajectory(stationary,targets,command)["score"],0)

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
