"""Geometry, binding locality and negative controls for blanket initialization."""
from dataclasses import replace
import unittest
from types import SimpleNamespace

import numpy as np
import trimesh
from hydra import compose, initialize_config_dir
from omegaconf import OmegaConf

from topogym.core.config import CONFIG_ROOT
from topogym.tasks.blanket_flatten.geometry import BlanketLayout, generate, material_coordinates, panel_clearance
from topogym.tasks.blanket_flatten.diagnostics import AcceptanceWindow, binding_audit, footprint_area, flatten_gates, initial_gates
from topogym.tasks.catalog import load_card


class BlanketChecks(unittest.TestCase):
    def test_full_turn_spiral_keeps_separated_isometric_surface(self):
        with initialize_config_dir(version_base='1.3', config_dir=str(CONFIG_ROOT)):
            cfg = compose(config_name='blanket_flatten_fold_spiral')
        layout = BlanketLayout(**OmegaConf.to_container(cfg.task.geometry))
        v, f, uv, panels, report = generate(layout)
        mesh = trimesh.Trimesh(v, f, process=False)
        self.assertEqual(mesh.euler_number, 1)
        self.assertEqual(len(mesh.split(only_watertight=False)), 1)
        self.assertAlmostEqual(mesh.area, .60*.48, places=10)
        self.assertLess(report['maximum_edge_metric_error'], 1e-10)
        self.assertGreater(report['roll_turn_deg'], 360)
        self.assertGreaterEqual(report['minimum_nonadjacent_panel_gap_m'], .024)
        self.assertAlmostEqual(v[:, 2].min(), .020)
        self.assertLess(v[:, 2].max(), .21)

    def test_mixed_folds_and_roll_preserve_material_and_clearance(self):
        layout = BlanketLayout(fold_count=3, fold_angle_deg=118, fold_angle_jitter_deg=12,
            roll_fold_count=5, crease_slant=.045, drop_clearance_m=.025,
            pitch_deg=145, tilt_deg=5, seed=2, max_attempts=256)
        for seed in range(12):
            with self.subTest(seed=seed):
                v, f, uv, panels, report = generate(replace(layout, seed=seed))
                mesh = trimesh.Trimesh(v, f, process=False)
                self.assertEqual(mesh.euler_number, 1)
                self.assertEqual(len(mesh.split(only_watertight=False)), 1)
                self.assertTrue(mesh.is_winding_consistent)
                self.assertAlmostEqual(mesh.area, .60*.48, places=10)
                self.assertLess(report['maximum_edge_metric_error'], 1e-10)
                self.assertGreaterEqual(report['minimum_nonadjacent_panel_gap_m'], .032)
                self.assertAlmostEqual(v[:, 2].min(), .025)
                angles = np.asarray(report['fold_angles_deg'])
                np.testing.assert_array_equal(np.sign(angles[:3]), [1, -1, 1])
                self.assertTrue(np.all(angles[3:] < 0))
                self.assertGreater(report['roll_turn_deg'], 210)
                # Arbitrary remesh points must still recover their original UVs.
                actual, distance = material_coordinates(v[f].mean(axis=1)[::-1], v, uv, panels)
                np.testing.assert_allclose(actual, uv[f].mean(axis=1)[::-1], atol=1e-10)
                self.assertLess(distance.max(), 1e-10)

    def test_birth_is_one_isometric_disk_with_surface_clearance(self):
        for seed in range(12):
            with self.subTest(seed=seed):
                v, f, uv, panels, report = generate(BlanketLayout(seed=seed))
                mesh = trimesh.Trimesh(v, f, process=False)
                self.assertEqual(mesh.euler_number, 1)
                self.assertEqual(len(mesh.split(only_watertight=False)), 1)
                self.assertTrue(mesh.is_winding_consistent)
                self.assertAlmostEqual(mesh.area, .60*.48, places=10)
                self.assertLess(report["maximum_edge_metric_error"], 1e-10)
                self.assertGreaterEqual(report["minimum_nonadjacent_panel_gap_m"], .032)
                self.assertAlmostEqual(v[:, 2].min(), .10)
                np.testing.assert_array_equal(generate(BlanketLayout(seed=seed))[0], v)

    def test_reordered_off_surface_particles_recover_material_coordinates(self):
        v, f, uv, panels, _ = generate()
        # Triangle centroids approximate arbitrary remesh locations; order is deliberately reversed.
        points = v[f].mean(axis=1)[::-1]
        expected = uv[f].mean(axis=1)[::-1]
        actual, distance = material_coordinates(points, v, uv, panels)
        np.testing.assert_allclose(actual, expected, atol=1e-10)
        self.assertLess(distance.max(), 1e-10)

    def test_panel_gap_detects_crossing_interiors(self):
        # No vertices coincide, but the two panel interiors cross.
        v = np.array([[-1,-1,0],[1,-1,0],[1,1,0],[-1,1,0],
                      [-2,-2,4],[2,-2,4],[2,2,4],[-2,2,4],
                      [0,-.5,-1],[0,.5,-1],[0,.5,1],[0,-.5,1]], dtype=float)
        self.assertEqual(panel_clearance(v, np.arange(12).reshape(3,4))[0], 0.)

    def test_invalid_birth_and_impossible_gap_rejected(self):
        for change in (dict(seed=-1), dict(seed=True), dict(fold_count=1), dict(width_m=0),
                       dict(drop_clearance_m=float("nan")), dict(birth_gap_particle_ratio=2),
                       dict(fold_angle_deg=179), dict(birth_gap_particle_ratio=100, max_attempts=2),
                       dict(roll_fold_count=-1), dict(roll_fold_count=1.5), dict(roll_direction=0),
                       dict(roll_angle_jitter_deg=90), dict(panel_width_jitter=1)):
            with self.subTest(change=change), self.assertRaises(ValueError):
                generate(replace(BlanketLayout(), **change))

    def test_flattening_rejects_pressed_fold_raised_corner_and_held_sheet(self):
        with initialize_config_dir(version_base="1.3", config_dir=str(CONFIG_ROOT)):
            cfg = compose(config_name="blanket_flatten_preview")
        success = OmegaConf.to_container(cfg.task.success, resolve=True)
        initial = OmegaConf.to_container(cfg.task.initialization, resolve=True)
        metrics = dict(finite=True, coverage_ratio=1., minimum_height_m=.004, maximum_height_m=.004,
                       p95_height_m=.004, mean_speed_m_s=0., p99_speed_m_s=0., maximum_speed_m_s=0.,
                       outside_table_particles=0, maximum_edge_stretch=1., maximum_visual_edge_stretch=1.)
        self.assertTrue(all(flatten_gates(metrics, success, released=True).values()))
        self.assertFalse(all(initial_gates(metrics, initial).values()))
        for change in (dict(coverage_ratio=.5), dict(maximum_height_m=.10), dict(outside_table_particles=1),
                       dict(minimum_height_m=-.01), dict(maximum_edge_stretch=1.4), dict(maximum_visual_edge_stretch=4)):
            self.assertFalse(all(flatten_gates({**metrics, **change}, success, released=True).values()))
        self.assertFalse(all(flatten_gates(metrics, success, released=False).values()))
        self.assertFalse(all(initial_gates({"finite": False}, initial).values()))
        # Two flattened layers cover only half the material, despite negligible height.
        vertices = np.array([[0,0,0],[.3,0,0],[.3,.48,0],[0,.48,0]], dtype=float)
        double = np.vstack((vertices, vertices+[0,0,.008]))
        faces = np.array([[0,1,2],[0,2,3],[4,5,6],[4,6,7]])
        self.assertAlmostEqual(footprint_area(double, faces)/(.60*.48), .5)
        self.assertEqual(load_card("blanket_flatten")["physics"]["qualification"], "unqualified")

    def test_acceptance_requires_sustained_gates_and_small_displacement(self):
        window = AcceptanceWindow(.4, .008)
        positions = np.zeros((10, 3))
        self.assertFalse(window.update(0., positions, {"settled": True}))
        self.assertFalse(window.update(.4, positions+.01, {"settled": True}))
        self.assertFalse(window.update(.6, positions+.01, {"released": False}))
        self.assertFalse(window.update(.8, positions+.01, {"released": True}))
        self.assertTrue(window.update(1.2, positions+.011, {"released": True}))
        with self.assertRaises(ValueError):
            window.update(1.1, positions, {"released": True})

    def test_actual_support_audit_rejects_far_material_and_foreign_entity(self):
        coords = np.linspace(-.032, .032, 9)
        uv = np.array([(x, y) for x in coords for y in coords])
        vertices = np.column_stack((uv, np.ones(len(uv))))
        panels = np.array([[0, 72, 80, 8]])
        indices = np.array([[40, 39, 41, 31]])
        weights = np.array([[1., 0, 0, 0]])
        field = SimpleNamespace(support_idxs=SimpleNamespace(to_numpy=lambda: indices),
                                support_weights=SimpleNamespace(to_numpy=lambda: weights))
        tensor = SimpleNamespace(detach=lambda: SimpleNamespace(cpu=lambda: vertices))
        cloth = SimpleNamespace(solver=SimpleNamespace(vverts_info=field), vvert_start=0, n_vverts=1,
                                particle_start=0, n_particles=len(vertices), _vverts=vertices[[40]],
                                get_particles_pos=lambda: tensor)
        self.assertTrue(binding_audit(cloth, vertices, uv, panels, .008)[0]["passed"])
        indices[0, 3] = 0
        self.assertFalse(binding_audit(cloth, vertices, uv, panels, .008)[0]["passed"])
        indices[0, 3] = len(vertices)
        with self.assertRaises(ValueError):
            binding_audit(cloth, vertices, uv, panels, .008)


if __name__ == "__main__":
    unittest.main()
