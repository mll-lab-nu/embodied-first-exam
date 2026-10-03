#!/usr/bin/env python3
"""Below-easy Horseshoe settings: registration and object-level design intent; no physics."""
from pathlib import Path
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from topogym.config.registry import seeded_variation, task_definition
from topogym.planning.horseshoe_ring.below_easy_witness import PHASES_DEG, assembly, check_variant, passing_phases
from topogym.tasks.horseshoe_ring.below_easy import HorseshoeBelowEasyTask, ring


class Registration(unittest.TestCase):
    def test_difficulty_aliases_select_the_settings(self):
        for name in ("very_easy", "easier"):
            cls = task_definition("horseshoe_ring", name)
            self.assertEqual(cls.variation_id, f"horseshoe_ring_{name}")
            self.assertEqual(cls.difficulty, name)
            self.assertTrue(issubclass(cls, HorseshoeBelowEasyTask))

    def test_seeded_sampling_keeps_the_three_tiers(self):
        drawn = {seeded_variation("horseshoe_ring", seed)["difficulty"] for seed in range(12)}
        self.assertEqual(drawn, {"easy", "medium", "hard"})

    def test_settings_differ_only_in_the_ring(self):
        very_easy, easier = (task_definition("horseshoe_ring", n)() for n in ("very_easy", "easier"))
        self.assertEqual({k for k in very_easy.config if very_easy.config[k] != easier.config[k]}, {"ring"})
        self.assertEqual((very_easy.config["ring"], easier.config["ring"]), (ring(144., 144.), ring(146., 120.)))
        easy = task_definition("horseshoe_ring", "easy")()
        self.assertEqual(len({easy.instance_id, very_easy.instance_id, easier.instance_id}), 3)

    def test_named_settings_cannot_be_overridden(self):
        with self.assertRaises(ValueError):
            task_definition("horseshoe_ring", "very_easy")({"ring": ring(150., 150.)})

    def test_public_goal_matches_the_easy_tier(self):
        easy = task_definition("horseshoe_ring", "easy")().public_instruction()
        for name in ("very_easy", "easier"):
            self.assertEqual(task_definition("horseshoe_ring", name)().public_instruction(), easy)


class DesignIntent(unittest.TestCase):
    """The ring leaves by sliding along the chains over one shoe once its bore holds the shoe's
    section: at every phase (very_easy), only after a turn (easier), never (easy)."""

    def test_easy_ring_passes_at_no_phase(self):
        self.assertEqual(passing_phases(assembly(task_definition("horseshoe_ring", "easy")())), [])

    def test_very_easy_slides_off_at_every_phase(self):
        report = check_variant("very_easy")
        self.assertTrue(report["start"]["entangled"])
        self.assertEqual(report["passing_phases"], len(PHASES_DEG))
        self.assertEqual(report["design"], "very_easy")

    def test_easier_needs_one_turn(self):
        report = check_variant("easier")
        self.assertTrue(report["start"]["entangled"])
        self.assertLess(0, report["passing_phases"])
        self.assertLess(report["passing_phases"], len(PHASES_DEG) / 2)
        self.assertEqual(report["design"], "easier")


if __name__ == "__main__":
    unittest.main()
