"""Video-derived four-ring initial topology, aperture and integration checks."""
from dataclasses import replace
import hashlib
import json
from pathlib import Path
import tempfile
import unittest

from hydra import compose, initialize_config_dir
import numpy as np
from omegaconf import OmegaConf

from topogym.tasks.catalog import TASK_IDS, load_card
from topogym.tasks.orbits.geometry import OrbitsLayout, generate_assets, geometry_report, make_meshes, winding_numbers
from topogym.tasks.orbits.scene import OrbitsScene


class OrbitsChecks(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.layout = OrbitsLayout()
        cls.parts, cls.cord = make_meshes(cls.layout)

    def test_initial_apertures_connections_and_cord_clearance(self):
        report = geometry_report(self.layout, self.parts, self.cord)
        self.assertTrue(report["passed"], report)
        self.assertFalse(report["physics_qualified"])
        self.assertEqual(len(report["intentional_fixed_joints"]), 10)
        np.testing.assert_allclose(np.abs(report["winding_about_posts"]), [0, 0, 0, 0, 1], atol=1e-6)

    def test_filled_ring_aperture_is_rejected(self):
        parts = dict(self.parts, ring_4=self.parts["ring_4"].convex_hull)
        report = geometry_report(self.layout, parts, self.cord)
        self.assertFalse(report["passed"])
        self.assertFalse(report["checks"]["four_real_ring_apertures"])

    def test_untrapped_or_wrong_post_bight_is_rejected(self):
        for dx, expected in ((.12, [0, 0, 0, 0, 0]), (-self.layout.post_spacing_m, [0, 0, 0, 1, 1])):
            with self.subTest(dx=dx):
                cord = self.cord.copy(); cord[:, 0] += dx
                winding = np.abs(winding_numbers(cord, self.layout.post_x))
                np.testing.assert_allclose(winding, expected, atol=1e-6)
                self.assertFalse(np.allclose(winding, [0, 0, 0, 0, 1]))

    def test_wrong_counts_intersections_and_nonfinite_dimensions_rejected(self):
        for change in (dict(ring_count=9), dict(ring_count=True), dict(post_spacing_m=.066),
                       dict(ring_step_m=.01), dict(ball_radius_m=.08), dict(base_length_m=.2),
                       dict(cord_radius_m=float("nan")), dict(bight_radius_m=.004)):
            with self.subTest(change=change), self.assertRaises(ValueError):
                replace(self.layout, **change).validate()

    def test_reloadable_assets_and_hashes(self):
        import trimesh
        with tempfile.TemporaryDirectory() as directory:
            folder = Path(directory)
            layout, report = generate_assets(folder, self.layout)
            self.assertEqual(layout, OrbitsLayout(**json.loads((folder/"layout.json").read_text())))
            np.testing.assert_array_equal(np.load(folder/"cord_centerline.npy"), self.cord)
            self.assertEqual(report, json.loads((folder/"geometry_report.json").read_text()))
            for i in range(4):
                self.assertEqual(trimesh.load(folder/f"ring_{i+1}.obj", force="mesh").euler_number, 0)
            for name, digest in json.loads((folder/"sha256.json").read_text()).items():
                self.assertEqual(hashlib.sha256((folder/name).read_bytes()).hexdigest(), digest)

    def test_uniform_scale_preserves_cord_eyes_and_fixed_connections(self):
        small = self.layout.scaled(.35)
        parts, cord = make_meshes(small)
        np.testing.assert_allclose(cord, self.cord*.35, atol=1e-12)
        np.testing.assert_allclose(small.eyes, self.layout.eyes*.35, atol=1e-12)
        for name, mesh in parts.items():
            np.testing.assert_allclose(mesh.bounds, self.parts[name].bounds*.35, atol=1e-10)
            self.assertEqual(mesh.euler_number, self.parts[name].euler_number)
            self.assertAlmostEqual(mesh.volume, self.parts[name].volume*.35**3, places=10)
        report = geometry_report(small, parts, cord)
        self.assertTrue(report["passed"], report)
        self.assertEqual(small, OrbitsLayout(**json.loads(json.dumps(report["dimensions"]))))

    def test_catalog_config_and_step_guard(self):
        self.assertEqual(TASK_IDS[12], "orbits")
        card = load_card("orbits")
        self.assertEqual(card["baseline"]["ring_count"], 4)
        with initialize_config_dir(version_base="1.3", config_dir=str(Path(__file__).resolve().parents[1]/"configs")):
            cfg = compose(config_name="orbits_preview")
            OmegaConf.to_container(cfg, resolve=True, throw_on_missing=True)
            self.assertEqual(cfg.robot_control.robot.name, "aloha")
            self.assertEqual(OrbitsLayout(**OmegaConf.to_container(cfg.task.geometry)), self.layout)
        with self.assertRaisesRegex(RuntimeError, "Static reconstruction"):
            OrbitsScene(None, self.layout, {}, {}).step()


if __name__ == "__main__":
    unittest.main()
