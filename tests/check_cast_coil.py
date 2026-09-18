"""Initial solid, collision export and scene-config contracts for Cast Coil."""
from copy import deepcopy
from pathlib import Path
import tempfile
import unittest
import xml.etree.ElementTree as ET

from hydra import compose, initialize_config_dir
import numpy as np
import trimesh

from topogym.tasks.cast_coil.geometry import CoilAssembly, clearance, generate_assets, geometry_report, load_template, occupied
from topogym.tasks.catalog import load_card

ROOT = Path(__file__).resolve().parents[1]


class CastCoilChecks(unittest.TestCase):
    def test_two_connected_open_coils_and_collision_free_assembly(self):
        assembly = CoilAssembly()
        report = geometry_report(assembly)
        self.assertTrue(report["passed"])
        self.assertEqual(report["layer_order"], ["gold", "silver", "gold", "silver"])
        self.assertAlmostEqual(report["minimum_initial_clearance_m"], .00075)
        self.assertFalse(report["extraction_route_verified"])
        self.assertFalse(report["turning_windows_verified"])
        for piece in report["pieces"]:
            self.assertEqual(piece["components"], 1)
            self.assertEqual(piece["euler_number"], 2)  # Open curve thickening, not a closed torus.

    def test_gap_is_not_a_visual_only_hole_and_bridge_is_solid(self):
        assembly = CoilAssembly(scale=1)
        gold, silver = assembly.bodies
        # Front gap and inner relief are empty; the depth bridge stays solid.
        self.assertFalse(occupied(np.array([[.013, -.009375, -.005]]), gold.boxes)[0])
        self.assertFalse(occupied(np.array([[0., -.009375, -.011]]), gold.boxes)[0])
        self.assertTrue(occupied(np.array([[.013, -.003125, .003]]), gold.boxes)[0])
        self.assertTrue(occupied(np.array([[.013, .003125, -.003]]), silver.boxes)[0])
        # A whole-piece hull incorrectly fills the central bore.
        self.assertTrue(gold.visual.convex_hull.contains([[0, -.003, 0]])[0])
        self.assertFalse(occupied(np.array([[0., -.003, 0.]]), gold.boxes)[0])

    def test_overlap_and_closed_windows_are_rejected(self):
        assembly = CoilAssembly()
        a, b = assembly.bodies
        self.assertLess(clearance(a.boxes, b.boxes+[0, -.005, 0]), 0)
        source = load_template()
        for key, value in (("band_width", 18), ("bridge_height", 11),
                           ("relief_depth", 7), ("layer_clearance", 0), ("outer_width", float("nan"))):
            t = deepcopy(source)
            t[key] = value
            with self.subTest(key=key), self.assertRaises(ValueError):
                CoilAssembly(t)
        for scale in (0, -1, float("nan")):
            with self.assertRaises(ValueError):
                CoilAssembly(scale=scale)

    def test_disjoint_collision_mass_matches_watertight_visual_and_scales(self):
        small, large = CoilAssembly(scale=1), CoilAssembly(scale=3)
        for a, b in zip(small.bodies, large.bodies):
            np.testing.assert_allclose(np.sum(np.prod(a.boxes[:, 1]-a.boxes[:, 0], axis=1)), a.visual.volume, rtol=1e-10)
            self.assertAlmostEqual(b.visual.volume/a.visual.volume, 27)
            np.testing.assert_allclose(b.visual.moment_inertia, a.visual.moment_inertia*243, rtol=1e-10, atol=1e-18)
            for i, cell in enumerate(a.boxes):
                if i:
                    self.assertGreaterEqual(clearance(a.boxes[:i], cell[None]), -1e-12)

    def test_export_preserves_two_single_free_bodies_and_exact_collision_sizes(self):
        with tempfile.TemporaryDirectory() as tmp:
            assembly, report = generate_assets(tmp)
            for body, info in zip(assembly.bodies, report["bodies"]):
                folder = Path(tmp)/body.name
                root = ET.parse(folder/f"{body.name}.urdf").getroot()
                self.assertEqual(len(root.findall("link")), 1)
                self.assertEqual(root.findall("joint"), [])
                self.assertEqual(root.find("link/inertial/origin").attrib["xyz"], "0 0 0")
                self.assertGreater(np.linalg.eigvalsh(info["inertia_kg_m2"]).min(), 0)
                nodes = root.findall("link/collision")
                self.assertEqual(len(nodes), len(body.boxes))
                sizes = np.array([np.fromstring(n.find("geometry/box").attrib["size"], sep=" ") for n in nodes])
                np.testing.assert_allclose(sizes, body.boxes[:, 1]-body.boxes[:, 0], atol=1e-12)
                self.assertTrue((folder/root.find("link/visual/geometry/mesh").attrib["filename"]).is_file())
            self.assertEqual(len(trimesh.load(Path(tmp)/"assembly.glb").geometry), 2)

    def test_preview_and_catalog_agree_and_remain_unqualified(self):
        card = load_card("cast_coil")
        with initialize_config_dir(config_dir=str(ROOT/"configs"), version_base="1.3"):
            cfg = compose(config_name="cast_coil_preview")
        self.assertEqual(cfg.task.variant, card["baseline"]["asset_id"])
        self.assertEqual(cfg.task.scale, card["baseline"]["scene_scale"])
        self.assertEqual(cfg.env.renderer.type, "nyx")
        self.assertEqual(cfg.env.presentation.background, "compact_lab")
        self.assertEqual(card["physics"]["qualification"], "unqualified")


if __name__ == "__main__":
    unittest.main()
