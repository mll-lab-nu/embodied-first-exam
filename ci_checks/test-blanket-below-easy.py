#!/usr/bin/env python3
"""Corner-fold geometry/registration contracts; runtime evidence is separate."""
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

import numpy as np
from scipy.spatial import cKDTree

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from topogym.assets.geometry.blanket_corner_folds import folded_positions, generate, profile_for
from topogym.assets.geometry.blanket_flatten import BlanketLayout, generate_flat_binding
from topogym.config.registry import TIER_ORDER, task_definition, variation_registration
from topogym.evaluation.cloth_metrics import footprint_area
from topogym.tasks.blanket_flatten.corner_preparation import CornerFoldPreparation
from topogym.world.initial_state import validate_initial_state_qualification
from topogym.world.physics.cloth_preparation import ClothPreparation, PreparationConfig


class CornerFoldContracts(unittest.TestCase):
    def test_new_aliases_leave_base_and_seeded_tiers_unchanged(self):
        self.assertEqual(TIER_ORDER, ("easy", "medium", "hard"))
        self.assertEqual(variation_registration("blanket_flatten", "base")["variation_id"],
                         "blanket_flatten_easy")
        for tier in ("very_easy", "easier"):
            cls = task_definition("blanket_flatten", tier)
            self.assertEqual(cls.variation_id, "blanket_flatten_"+tier)
            self.assertIs(task_definition("blanket_flatten", cls.variation_id), cls)
            self.assertEqual(variation_registration("blanket_flatten", tier)["pool"], "experimental")

    def test_same_material_scale_placement_texture_and_goal_as_easy(self):
        easy = task_definition("blanket_flatten", "easy").defaults
        for tier in ("very_easy", "easier"):
            task = task_definition("blanket_flatten", tier)({"initialization_mode": "flat_for_preparation"})
            for key in ("length_m", "width_m", "mesh_spacing_m", "particle_size_m", "center_xy_m",
                        "material", "table_friction", "color", "texture", "minimum_coverage_ratio",
                        "maximum_stretch_ratio", "maximum_height_m", "maximum_speed_m_s",
                        "maximum_drift_m", "stable_duration_s"):
                self.assertEqual(task.config[key], easy[key], (tier, key))
            self.assertNotIn("corner_colors", task.config["texture"])
            with tempfile.TemporaryDirectory() as tmp:
                spec = task.declare(Path(tmp)/"assets", .9196429)
                self.assertIsNone(spec.initial_state)
                self.assertEqual(len(spec.entities), 1)
                self.assertEqual(spec.entities[0].physics_model, "pbd_cloth")

    def test_flat_start_and_continuous_inextensible_fold_targets(self):
        _, faces, uv, _, _ = generate_flat_binding(BlanketLayout())
        edges = np.unique(np.sort(faces[:, [[0, 1], [1, 2], [2, 0]]].reshape(-1, 2)), axis=0)
        rest = np.linalg.norm(uv[edges[:, 0]]-uv[edges[:, 1]], axis=1)
        for tier in ("very_easy", "easier"):
            profile = profile_for(tier)
            flat = folded_positions(uv, profile=profile, half_progress=0., corner_progress=0.)
            np.testing.assert_allclose(flat[:, :2], uv, atol=1e-15)
            np.testing.assert_allclose(flat[:, 2], profile.table_clearance_m)
            path = ([(t, 0.) for t in np.linspace(0, 1, 9)] if profile.half_fold else [])
            path += [(1., t) for t in np.linspace(0, 1, 9)]
            for half, corner in path:
                xyz = folded_positions(uv, profile=profile, half_progress=half, corner_progress=corner)
                lengths = np.linalg.norm(xyz[edges[:, 0]]-xyz[edges[:, 1]], axis=1)
                self.assertLessEqual(float(np.max(lengths/rest)), 1+1e-10)
                self.assertGreaterEqual(float(xyz[:, 2].min()), profile.table_clearance_m-1e-12)
            if profile.half_fold:
                near = folded_positions(uv, profile=profile, half_progress=1-1e-9, corner_progress=0.)
                end = folded_positions(uv, profile=profile, corner_progress=0.)
                self.assertLess(float(np.abs(near-end).max()), 1e-8)

    def test_final_fold_is_unsolved_without_nonlocal_layer_overlap(self):
        # Finer than the authored visual grid, covering the nested packet bend.
        uv = np.array(np.meshgrid(np.linspace(-.3, .3, 101), np.linspace(-.24, .24, 81))).reshape(2, -1).T
        for tier in ("very_easy", "easier"):
            p, f, _, _ = generate(tier)
            self.assertLess(footprint_area(p, f)/(.6*.48), .9)
            xyz = folded_positions(uv, profile=profile_for(tier))
            pairs = cKDTree(xyz).query_pairs(.032, output_type="ndarray")
            pairs = pairs[np.linalg.norm(uv[pairs[:, 0]]-uv[pairs[:, 1]], axis=1) > .032]
            gap = np.linalg.norm(xyz[pairs[:, 0]]-xyz[pairs[:, 1]], axis=1).min()
            self.assertGreaterEqual(gap, .016-1e-12)

    def test_preparation_uses_common_lower_release_and_qualification(self):
        self.assertIs(CornerFoldPreparation.run, ClothPreparation.run)
        self.assertIs(CornerFoldPreparation.tick, ClothPreparation.tick)
        self.assertIs(CornerFoldPreparation.drive, ClothPreparation.drive)
        for tier, expected in (("very_easy", ["corner_fold"]), ("easier", ["half_fold", "corner_fold"])):
            task = task_definition("blanket_flatten", tier)({"initialization_mode": "flat_for_preparation"})
            task.material_uv = np.array([[0., 0.]])
            controller = CornerFoldPreparation.__new__(CornerFoldPreparation)
            controller.task, controller.profile = task, profile_for(tier)
            with patch.object(controller, "drive") as drive:
                controller.form(np.array([0., 0., .1]))
                self.assertEqual([call.args[0] for call in drive.call_args_list], expected)
                for call in drive.call_args_list:
                    for t in (0., .5, 1.):
                        self.assertTrue(np.isfinite(call.args[1](t)).all())

    def test_preview_pose_is_not_accepted_as_a_frozen_state(self):
        for scope in ("released_stable", "scene_layout"):
            with self.assertRaises(ValueError):
                validate_initial_state_qualification(dict(passed=True, scope=scope,
                    scene_layout_passed=True, preparation=dict(completed=True, position_writes=1)), scope)

    def test_original_gathered_formation_targets_are_unchanged(self):
        from topogym.assets.geometry.blanket_gathered import GatheredProfile, preparation_target
        uv = np.array([[u, v] for u in np.linspace(-.3, .3, 9) for v in np.linspace(-.24, .24, 9)])
        origin = np.array([-.1356786, .15, 1.0196429])
        for tier in TIER_ORDER:
            task = task_definition("blanket_flatten", tier)({"initialization_mode": "flat_for_preparation"})
            task.layout, task.material_uv = BlanketLayout(), uv
            controller = ClothPreparation.__new__(ClothPreparation)
            controller.task = task
            controller.cfg = PreparationConfig()
            controller.profile = GatheredProfile(**task.config["gathered_profile"])
            with patch.object(controller, "drive") as drive:
                controller.form(origin)
                stages = drive.call_args_list
                self.assertEqual([c.args[0] for c in stages], ["gather"] if tier == "easy" else ["gather", "twist"])
                for call in stages:
                    for t in (0., .33, 1.):
                        gather, twist = (t, 0.) if call.args[0] == "gather" else (1., t)
                        expected = preparation_target(uv, .6, .48, gather, twist, controller.profile)
                        expected[:, 2] -= expected[:, 2].min()
                        np.testing.assert_array_equal(call.args[1](t), expected+origin)


if __name__ == "__main__":
    unittest.main()
