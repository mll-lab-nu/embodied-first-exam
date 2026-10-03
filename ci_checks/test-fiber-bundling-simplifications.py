#!/usr/bin/env python3
"""Symmetric reset geometry and existing-scene compatibility, without physics."""
from dataclasses import asdict
from pathlib import Path
import sys
import tempfile
import unittest
import xml.etree.ElementTree as ET

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from topogym.assets.geometry.fiber_bundling import FiberLayout, minimum_fiber_clearance
from topogym.assets.geometry.fiber_bundling_simplified import SymmetricFiberLayout
from topogym.config.registry import task_definition, seeded_variation
from topogym.tasks.fiber_bundling.common import recommended_grasp_assist


class SimplifiedFiberChecks(unittest.TestCase):
    def test_opposed_and_equilateral_cross_sections(self):
        for count in (2, 3):
            for seed in (0, 1, 7, 42):
                layout = SymmetricFiberLayout(seed=seed, fiber_count=count)
                paths = np.array(layout.fibers())
                np.testing.assert_allclose(paths[:, :, 1:].sum(axis=0), 0., atol=1e-15)
                np.testing.assert_allclose(paths[:, :, 0], np.tile(paths[0, :, 0], (count, 1)))
                radii = np.linalg.norm(paths[:, :, 1:], axis=-1)
                for a in range(count):
                    for b in range(a + 1, count):
                        distance = np.linalg.norm(paths[a, :, 1:] - paths[b, :, 1:], axis=-1)
                        np.testing.assert_allclose(distance, radii[a] * (2 if count == 2 else np.sqrt(3)))
                np.testing.assert_allclose(np.linalg.norm(np.diff(paths, axis=1), axis=-1).sum(axis=1), .08)
                self.assertGreater(minimum_fiber_clearance(paths, layout.fiber_radius_m), 0.)

    def test_reference_dimensions_and_seed_reproducibility(self):
        for count in (2, 3):
            simplified = SymmetricFiberLayout(seed=7, fiber_count=count)
            original = FiberLayout(seed=7, fiber_count=4)
            for key, value in asdict(original).items():
                if key != "fiber_count":
                    self.assertEqual(asdict(simplified)[key], value)
            np.testing.assert_array_equal(simplified.fibers()[0], original.fibers()[0])
            np.testing.assert_array_equal(simplified.fibers(), simplified.fibers())
            self.assertFalse(np.array_equal(simplified.fibers(), SymmetricFiberLayout(seed=8, fiber_count=count).fibers()))

    def test_passive_assets_and_original_fixture_poses(self):
        with tempfile.TemporaryDirectory() as directory:
            specs = {}
            for variant, count in (("very_easy", 2), ("easier", 3), ("easy", 4)):
                task = task_definition("fiber_bundling", variant)(seed=0)
                folder = Path(directory) / variant
                spec = task.declare(folder, .9196429)
                specs[variant] = spec
                root = ET.parse(folder / "bundle.xml").getroot()
                bodies = root.findall(".//body")
                self.assertEqual(sum(b.get("name", "").startswith("fiber_") for b in bodies), count * 10)
                self.assertIsNone(root.find("actuator"))
                self.assertIsNone(root.find(".//freejoint"))
                self.assertTrue(all(j.get("stiffness") == "0" for j in root.findall(".//joint")))
                roles = spec.entities[0].contact_roles
                self.assertEqual(sum(r == "fiber_strand" for r in roles.values()), count * 10)
                self.assertEqual(task.terminal_revision, "terminal_v4_fiber_ring_plane")
            for variant in ("very_easy", "easier"):
                # The bundle changes; ring, support and cradle retain their entire declarations.
                for actual, reference in zip(specs[variant].entities, specs["easy"].entities):
                    self.assertEqual(actual.name, reference.name)
                    self.assertEqual(actual.position_m, reference.position_m)
                    self.assertEqual(actual.quaternion_wxyz, reference.quaternion_wxyz)
                    self.assertEqual(actual.morph_options, reference.morph_options)

    def test_new_entries_do_not_change_existing_seeded_tiers(self):
        for seed, tier, count in ((0, "easy", 4), (1, "medium", 8), (2, "hard", 16)):
            self.assertEqual(seeded_variation("fiber_bundling", seed)["difficulty"], tier)
            task = task_definition("fiber_bundling", tier)(seed=0)
            self.assertIs(task.layout_class, FiberLayout)
            self.assertEqual(task.config["geometry"]["fiber_count"], count)
        self.assertIs(task_definition("fiber_bundling", "base"), task_definition("fiber_bundling", "medium"))

    def test_counts_cannot_be_overridden(self):
        for variant in ("very_easy", "easier"):
            with self.assertRaises(ValueError):
                task_definition("fiber_bundling", variant)({"geometry": {"fiber_count": 4}})
        with self.assertRaises(ValueError):
            FiberLayout(fiber_count=2)
        for count in (1, 4, True, 2.5):
            with self.assertRaises(ValueError):
                SymmetricFiberLayout(fiber_count=count)

    def test_only_new_settings_recommend_contact_gated_sheath_grasp(self):
        for variant in ("very_easy", "easier"):
            assist = recommended_grasp_assist(variant)
            self.assertEqual(assist.model, "contact_weld_v1")
            self.assertEqual(len(assist.targets), 1)
            target = assist.targets[0]
            self.assertEqual((target.entity, target.link), ("fiber_bundle", "trunk_04"))
            self.assertEqual(target.center_m, (.02, 0., 0.))
            self.assertEqual(target.radius_m, .025)
        for variant in ("base", "easy", "medium", "hard"):
            self.assertIsNone(recommended_grasp_assist(variant))


if __name__ == "__main__":
    unittest.main()
