#!/usr/bin/env python3
"""Below-easy Hedgehog settings: registration and object-level design intent; no physics.

The design checks rebuild the frozen task geometry (about one minute in total).
"""
from pathlib import Path
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from topogym.config.registry import seeded_variation, task_definition
from topogym.planning.hedgehog_in_cage.below_easy_witness import check_variant
from topogym.tasks.hedgehog_in_cage.below_easy import HedgehogBelowEasyTask


class Registration(unittest.TestCase):
    def test_difficulty_aliases_select_the_settings(self):
        for name in ("very_easy", "easier"):
            cls = task_definition("hedgehog_in_cage", name)
            self.assertEqual(cls.variation_id, f"hedgehog_in_cage_{name}")
            self.assertEqual(cls.difficulty, name)
            self.assertTrue(issubclass(cls, HedgehogBelowEasyTask))

    def test_seeded_sampling_keeps_the_three_tiers(self):
        drawn = {seeded_variation("hedgehog_in_cage", seed)["difficulty"] for seed in range(12)}
        self.assertEqual(drawn, {"easy", "medium", "hard"})

    def test_settings_share_the_cage_and_differ_only_in_ball_pose(self):
        very_easy, easier = (task_definition("hedgehog_in_cage", n)() for n in ("very_easy", "easier"))
        self.assertEqual(very_easy.config["cage"], easier.config["cage"])
        self.assertNotEqual(very_easy.config["ball_pose"], easier.config["ball_pose"])
        easy = task_definition("hedgehog_in_cage", "easy")()
        self.assertEqual(len({easy.instance_id, very_easy.instance_id, easier.instance_id}), 3)

    def test_named_settings_cannot_be_overridden(self):
        cls = task_definition("hedgehog_in_cage", "very_easy")
        for override in ({"cage": {"windows": [[180., 116.]], "collar_height_mm": 18.}},
                         {"ball_pose": {"position_m": [0., 0., 0.], "quaternion_wxyz": [1., 0., 0., 0.]}}):
            with self.subTest(override=override), self.assertRaises(ValueError):
                cls(override)

    def test_public_goal_matches_the_easy_tier(self):
        easy = task_definition("hedgehog_in_cage", "easy")().public_instruction()
        for name in ("very_easy", "easier"):
            self.assertEqual(task_definition("hedgehog_in_cage", name)().public_instruction(), easy)


class DesignIntent(unittest.TestCase):
    """very_easy exits by translation; easier is blocked until one roll about the exit axis."""

    def test_very_easy_exits_by_translation(self):
        with tempfile.TemporaryDirectory() as folder:
            report = check_variant("very_easy", Path(folder))
        self.assertTrue(report["initial_free"])
        self.assertTrue(report["translation_exit_at_rest"])
        self.assertEqual(report["design"], "very_easy")

    def test_easier_needs_one_roll(self):
        with tempfile.TemporaryDirectory() as folder:
            report = check_variant("easier", Path(folder))
        self.assertTrue(report["initial_free"])
        self.assertFalse(report["translation_exit_at_rest"])
        self.assertEqual(report["design"], "easier")
        self.assertGreaterEqual(abs(report["roll_deg"]), 30)


if __name__ == "__main__":
    unittest.main()
