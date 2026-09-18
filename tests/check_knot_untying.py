"""Reject a false knot, self-intersection, and unusable initial rope geometry."""
from dataclasses import replace
import json
from pathlib import Path
import tempfile
import unittest

from hydra import compose, initialize_config_dir
import numpy as np
from omegaconf import OmegaConf
import trimesh

from topogym.tasks.catalog import load_card
from topogym.tasks.knot_untying.geometry import (
    KnotLayout, generate_assets, inspect_geometry, minimum_nonlocal_distance,
)


class KnotGeometryChecks(unittest.TestCase):
    def test_open_trefoil_and_its_mirror(self):
        for hand, sign in (("right", 1), ("left", -1)):
            layout = KnotLayout(handedness=hand)
            p = layout.centerline()
            report = inspect_geometry(p, layout)
            self.assertEqual(report["crossing_count"], 3)
            self.assertEqual(report["projected_writhe"], sign*3)
            self.assertEqual(report["gauss_unsigned"], [1, 2, 3, 1, 2, 3])
            self.assertTrue(report["trefoil_diagram_verified"])
            self.assertGreater(np.linalg.norm(p[0]-p[-1]), .30)
            self.assertGreater(report["minimum_nonlocal_surface_gap_m"], .003)
            self.assertGreater(report["minimum_bend_radius_m"], 6*layout.rope_radius_m)
            self.assertLessEqual(np.linalg.norm(np.diff(p, axis=0), axis=1).max(), layout.segment_length_m*1.001)

    def test_flat_intersection_and_wrong_crossing_rejected(self):
        layout = KnotLayout()
        p = layout.centerline()
        p[:, 2] = .02
        with self.assertRaises(ValueError):
            inspect_geometry(p, layout)
        p = layout.centerline()
        # Switch one crossing: the three projected crossings alone are not proof.
        p[80:97, 2] = .035
        with self.assertRaises(ValueError):
            inspect_geometry(p, layout)

    def test_intersection_between_samples_detected(self):
        p = np.array([[-1., 0, 0], [1, 0, 0], [0, -1, 0], [0, 1, 0]])
        distance, pair = minimum_nonlocal_distance(p, .01)
        self.assertLess(distance, 1e-12)
        self.assertEqual(pair, [0, 2])

    def test_invalid_layouts_rejected(self):
        for kwargs in ({"rope_radius_m": 0}, {"planar_scale_m": float("nan")},
                       {"radial_segments": 8.5}, {"cut_angle_rad": 1.0},
                       {"handedness": "both"}, {"tail_length_m": .02}):
            with self.subTest(kwargs=kwargs), self.assertRaises(ValueError):
                KnotLayout(**kwargs)
        thick = replace(KnotLayout(), rope_radius_m=.008)
        with self.assertRaises(ValueError):
            inspect_geometry(thick.centerline(), thick)

    def test_mesh_is_one_watertight_component_and_reproducible(self):
        with tempfile.TemporaryDirectory() as temporary:
            folder = Path(temporary)
            generate_assets(folder)
            mesh = trimesh.load(folder/"rope.obj", process=True, force="mesh")
            self.assertTrue(mesh.is_watertight)
            self.assertTrue(mesh.is_winding_consistent)
            self.assertGreater(mesh.volume, 0)
            self.assertEqual(len(mesh.split()), 1)
            hashes = json.loads((folder/"sha256.json").read_text())
            generate_assets(folder)
            self.assertEqual(hashes, json.loads((folder/"sha256.json").read_text()))

    def test_config_card_and_geometry_agree(self):
        root = Path(__file__).resolve().parents[1]
        with initialize_config_dir(version_base="1.3", config_dir=str(root/"configs")):
            cfg = compose(config_name="knot_untying_preview")
            layout = KnotLayout(**OmegaConf.to_container(cfg.task.geometry, resolve=True))
            self.assertEqual(layout, KnotLayout())
            card = load_card("knot_untying")["baseline"]
            self.assertEqual(card["rope_diameter_m"], 2*layout.rope_radius_m)
            self.assertEqual(card["free_tail_lengths_m"], [layout.tail_length_m]*2)
            self.assertEqual(card["rest_shape"], cfg.task.rope.fem.rest_shape)


if __name__ == "__main__":
    unittest.main()
