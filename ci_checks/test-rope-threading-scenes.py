#!/usr/bin/env python3
"""Offline scene contracts, including physical open-arc topology and risers."""
from pathlib import Path
import sys
import tempfile
import unittest

import numpy as np
import trimesh

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from topogym.assets.geometry.rope_threading import ThreadingLayout, generate_assets, ring_mesh
from topogym.config.registry import task_definition, seeded_variation, variation_registration
from topogym.config.scene import load_scene_config
from topogym.simulator.config import SimulatorConfig
from topogym.tasks.base import TaskSpec


class RopeThreadingScenes(unittest.TestCase):
    def test_five_layouts_keep_source_rope_and_requested_transform(self):
        reference = ThreadingLayout(translation_m=(-.1356786, 0., .0009))
        for tier, count in (("very_easy", 1), ("easier", 1), ("easy", 2), ("medium", 3), ("hard", 3)):
            task = task_definition("rope_threading", tier)()
            layout = ThreadingLayout(**task.config["geometry"])
            np.testing.assert_array_equal(layout.centerline(), reference.centerline())
            self.assertEqual(layout.yaw_deg, 0.)
            self.assertEqual(len(layout.rings()), count)
            self.assertEqual(layout.radius, .004)
            inner = .05 if tier == "hard" else .069
            self.assertAlmostEqual(layout.rings()[0]["radius_m"] - .006, inner)
            self.assertEqual(task.model_revision, variation_registration("rope_threading", tier)["model_revision"])
        np.testing.assert_allclose(reference.centerline()[[0, -1], :2],
                                   [[-.5060053483980946, .05], [.1943214, .05]], atol=1e-10)
        angles = [np.degrees(np.arctan2(r["normal"][1], r["normal"][0])) for r in reference.rings()]
        np.testing.assert_allclose(angles, [0., 36.86989765, 71.56505118], atol=1e-8)

    def test_open_top_is_real_geometry_with_closed_solid_end_caps(self):
        open_layout = ThreadingLayout(ring_ids=("R1",), ring_shape="lower_semicircle")
        ring = open_layout.rings()[0]
        mesh = ring_mesh(ring)
        self.assertTrue(mesh.is_watertight and mesh.is_volume)
        self.assertEqual(mesh.euler_number, 2)
        self.assertLessEqual(mesh.bounds[1, 2], ring["center_m"][2] + .006 + 1e-12)
        # A horizontal ray through the former upper rim must pass unobstructed;
        # the matching lower ray must still hit the physical cradle.
        center = np.asarray(ring["center_m"])
        starts = np.array([center + [-.2, 0., .075], center + [-.2, 0., -.075]])
        hits = mesh.ray.intersects_any(starts, np.tile([1., 0., 0.], (2, 1)))
        np.testing.assert_array_equal(hits, [False, True])
        full = ring_mesh(ThreadingLayout(ring_ids=("R1",)).rings()[0])
        np.testing.assert_array_equal(full.ray.intersects_any(starts, np.tile([1., 0., 0.], (2, 1))), [True, True])
        self.assertEqual(open_layout.required_crossings(), [])

    def test_generated_assets_and_initial_clearance(self):
        with tempfile.TemporaryDirectory() as folder:
            for tier in ("very_easy", "easier", "easy", "medium", "hard"):
                layout = ThreadingLayout(**task_definition("rope_threading", tier)().config["geometry"])
                path = Path(folder) / tier
                report = generate_assets(path, layout)
                self.assertTrue(report["geometry_verified"])
                self.assertEqual(report["initial_crossings"], [])
                self.assertGreater(report["minimum_fixture_gap_lower_bound_m"], 0.)
                self.assertAlmostEqual(report["table_surface_gap_m"], .0003)
                again = generate_assets(Path(folder) / (tier + "_repeat"), layout)
                self.assertEqual(report["files"], again["files"])
                self.assertEqual(sorted(p.stem for p in path.glob("R?.glb")), report["selected_ring_ids"])

    def test_only_threading_aloha_is_raised_and_home_is_preserved(self):
        scene = load_scene_config(SimulatorConfig(task_id="rope_threading"))
        other = load_scene_config(SimulatorConfig(task_id="knot_untying"))
        self.assertEqual(scene.robot_control.robot.base_riser_height_m, .0209)
        self.assertEqual(other.robot_control.robot.get("base_riser_height_m", 0.), 0.)
        self.assertEqual(scene.robot_control.home, other.robot_control.home)
        task = task_definition("rope_threading", "medium")()
        spec = task.finalize_spec(TaskSpec(()), asset_dir=None, scene_config=scene)
        self.assertEqual(len(spec.entities), 2)
        for entity in spec.entities:
            self.assertTrue(entity.fixed)
            self.assertAlmostEqual(entity.position_m[2] - .0209 / 2, .9196429)
            self.assertEqual(entity.morph_options["size"], (.07, .07, .0209))

    def test_enabled_terminals_and_original_tier_sampling(self):
        for tier in ("very_easy", "easier"):
            task = task_definition("rope_threading", tier)()
            self.assertTrue(task.goal_complete)
            self.assertNotIn("Scene preview", task.public_instruction())
            self.assertIn("Success requirements", task.public_instruction())
            for overrides in ({"ring_ids": ["R1", "R2"]}, {"ring_inner_radius_m": .1},
                              {"ring_shape": "closed" if tier == "very_easy" else "lower_semicircle"}):
                with self.assertRaises(ValueError):
                    type(task)({"geometry": overrides})
        for seed, tier in enumerate(("easy", "medium", "hard")):
            self.assertEqual(seeded_variation("rope_threading", seed)["difficulty"], tier)
        self.assertIs(task_definition("rope_threading", "base"), task_definition("rope_threading", "medium"))

    def test_public_goals_distinguish_draping_and_handoff(self):
        drape = task_definition('rope_threading', 'very_easy')().public_instruction()
        thread = task_definition('rope_threading', 'easier')().public_instruction()
        self.assertIn('open top', drape)
        self.assertNotIn('Required directions', drape)
        self.assertIn('while the feeding hand still holds', thread)
        self.assertIn('left robot base', thread)
        self.assertNotIn('green ring', thread)
        for text in (drape, thread):
            self.assertIn('0.5 s', text)
            self.assertIn('release is not required', text)


if __name__ == "__main__":
    unittest.main()
