"""Keyhole topology, true aperture collision, inertia and export checks."""
from copy import deepcopy
from pathlib import Path
import tempfile
import unittest
import xml.etree.ElementTree as ET

from hydra import compose, initialize_config_dir
import numpy as np
import trimesh

from topogym.tasks.cast_keyhole.geometry import KeyholeAssembly, generate_assets, geometry_report, load_template
from topogym.tasks.catalog import load_card

ROOT = Path(__file__).resolve().parents[1]


class CastKeyholeChecks(unittest.TestCase):
    def test_open_fork_and_single_closed_bore_have_valid_initial_clearance(self):
        report = geometry_report(KeyholeAssembly())
        self.assertTrue(report["passed"])
        self.assertEqual([p["euler_number"] for p in report["pieces"]], [2, 0])
        self.assertEqual([p["components"] for p in report["pieces"]], [1, 1])
        self.assertAlmostEqual(report["minimum_initial_surface_clearance_m"], .0039)
        self.assertTrue(report["human_reference_solution_documented"])
        self.assertFalse(report["extraction_route_verified"])
        self.assertFalse(report["measured_replica"])

    def test_silver_aperture_is_open_in_collisions_but_separated_from_external_notch(self):
        silver = KeyholeAssembly(scale=1).bodies[1]
        probes = np.array([[0,0,.0201], [0,0,-.0251], [0,0,-.0331], [.011,0,.0001]])
        expected = [False, True, False, True]
        np.testing.assert_array_equal(silver.visual.contains(probes), expected)
        occupied = np.any([c.contains(probes) for c in silver.collision], axis=0)
        np.testing.assert_array_equal(occupied, expected)
        self.assertTrue(silver.visual.convex_hull.contains(probes[:1])[0])

    def test_gold_has_a_continuous_external_exit(self):
        assembly = KeyholeAssembly(scale=1)
        gold = assembly.bodies[0]
        # Gold local width maps to assembly y, length to z. Bottom slot exits
        # through z < -35 mm, including the gold's -47 mm assembly translation.
        points = np.array([[0,0,z-.047] for z in np.linspace(-.034,-.040,13)])
        self.assertFalse(gold.visual.contains(points).any())
        self.assertFalse(any(c.contains(points).any() for c in gold.collision))

    def test_collision_partition_volume_com_and_inertia_match_visual(self):
        small, large = KeyholeAssembly(scale=1), KeyholeAssembly(scale=3)
        for a,b in zip(small.bodies, large.bodies):
            volumes = np.array([c.volume for c in a.collision])
            self.assertAlmostEqual(volumes.sum(), a.visual.volume, places=15)
            com = np.average([c.center_mass for c in a.collision], weights=volumes, axis=0)
            np.testing.assert_allclose(com, a.visual.center_mass, atol=1e-12)
            inertia = np.zeros((3,3))
            for c in a.collision:
                delta = c.center_mass-com
                inertia += c.moment_inertia+c.volume*(np.dot(delta,delta)*np.eye(3)-np.outer(delta,delta))
            np.testing.assert_allclose(inertia, a.visual.moment_inertia, rtol=1e-9, atol=1e-18)
            self.assertAlmostEqual(b.visual.volume/a.visual.volume, 27)
            np.testing.assert_allclose(b.visual.moment_inertia, a.visual.moment_inertia*243, rtol=1e-9, atol=1e-18)

    def test_invalid_scale_and_overlapping_initial_pose_are_rejected(self):
        for scale in (0,-1,float("nan")):
            with self.assertRaises(ValueError):
                KeyholeAssembly(scale=scale)
        for key,value in (("thickness",0),("arc_segments",2),("gold_offset_z",float("nan"))):
            t = deepcopy(load_template())
            t[key] = value
            with self.subTest(key=key), self.assertRaises(ValueError):
                KeyholeAssembly(t)
        with tempfile.TemporaryDirectory() as tmp:
            t = deepcopy(load_template())
            t["gold_offset_z"] = -8.8
            with self.assertRaises(ValueError):
                generate_assets(tmp, template=t)

    def test_export_preserves_single_links_and_convex_partition(self):
        with tempfile.TemporaryDirectory() as tmp:
            assembly, report = generate_assets(tmp)
            for source, info in zip(assembly.bodies, report["bodies"]):
                folder = Path(tmp)/source.name
                root = ET.parse(folder/f"{source.name}.urdf").getroot()
                self.assertEqual(len(root.findall("link")), 1)
                self.assertEqual(root.findall("joint"), [])
                nodes = root.findall("link/collision/geometry/mesh")
                self.assertEqual(len(nodes), len(source.collision))
                self.assertGreater(np.linalg.eigvalsh(info["inertia_kg_m2"]).min(), 0)
                for node, original in zip(nodes, source.collision):
                    exported = trimesh.load(folder/node.get("filename"), force="mesh")
                    self.assertTrue(exported.is_convex)
                    self.assertTrue(exported.is_watertight)
                    np.testing.assert_allclose(exported.bounds+info["origin_m"], original.bounds, atol=1e-8)
            self.assertEqual(len(trimesh.load(Path(tmp)/"assembly.glb").geometry), 2)

    def test_preview_and_card_agree_without_claiming_physics_qualification(self):
        card = load_card("cast_keyhole")
        with initialize_config_dir(config_dir=str(ROOT/"configs"), version_base="1.3"):
            cfg = compose(config_name="cast_keyhole_preview")
        self.assertEqual(cfg.task.variant, card["baseline"]["asset_id"])
        self.assertEqual(cfg.task.initial_relative_pose_id, card["baseline"]["initial_relative_pose_id"])
        self.assertEqual(cfg.task.scale, card["baseline"]["scene_scale"])
        self.assertEqual(cfg.task.yaw_deg, card["baseline"]["layout"]["yaw_deg"])
        self.assertEqual(cfg.env.renderer.type, "nyx")
        self.assertEqual(cfg.env.genesis.precision, "64")
        self.assertEqual(cfg.env.presentation.background, "compact_lab")
        self.assertEqual(card["physics"]["qualification"], "unqualified")


if __name__ == "__main__":
    unittest.main()
