#!/usr/bin/env python3
"""Below-easy Slotted Post settings: registration and object-level design intent; no physics."""
from pathlib import Path
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from topogym.assets.geometry.slotted_post_ring import make_meshes
from topogym.config.registry import seeded_variation, task_definition
from topogym.planning.slotted_post_ring.below_easy_witness import check_variant
from topogym.tasks.slotted_post_ring.below_easy import SlottedBelowEasyTask, ring_band_runs


class Registration(unittest.TestCase):
    def test_difficulty_aliases_select_the_settings(self):
        for name in ("very_easy", "easier"):
            cls = task_definition("slotted_post_ring", name)
            self.assertEqual(cls.variation_id, f"slotted_post_ring_{name}")
            self.assertEqual(cls.difficulty, name)
            self.assertTrue(issubclass(cls, SlottedBelowEasyTask))

    def test_seeded_sampling_keeps_the_three_tiers(self):
        drawn = {seeded_variation("slotted_post_ring", seed)["difficulty"] for seed in range(12)}
        self.assertEqual(drawn, {"easy", "medium", "hard"})

    def test_settings_differ_only_in_the_cord_route(self):
        easy, very_easy, easier = (task_definition("slotted_post_ring", n)() for n in ("easy", "very_easy", "easier"))
        self.assertEqual({k for k in very_easy.config if very_easy.config[k] != easier.config[k]}, {"cord_route"})
        self.assertEqual((very_easy.config["cord_route"], easier.config["cord_route"]), ("under_ring", "loop_over_ring"))
        self.assertEqual(very_easy.config["geometry"], easy.config["geometry"])
        self.assertEqual(len({easy.instance_id, very_easy.instance_id, easier.instance_id}), 3)

    def test_named_settings_cannot_be_overridden(self):
        for override in ({"cord_route": "loop_over_ring"}, {"geometry": {"ring_major_radius_m": .07}}):
            with self.subTest(override=override), self.assertRaises(ValueError):
                task_definition("slotted_post_ring", "very_easy")(override)

    def test_public_goal_matches_the_easy_tier(self):
        easy = task_definition("slotted_post_ring", "easy")().public_instruction()
        for name in ("very_easy", "easier"):
            self.assertEqual(task_definition("slotted_post_ring", name)().public_instruction(), easy)


class DesignIntent(unittest.TestCase):
    """The ring starts around the post; only cord passing over it can hold it: on both sides in
    easy, nowhere in very_easy, only the far loop carrying bead 2 in easier."""

    def test_easy_cord_passes_over_the_ring_on_both_sides(self):
        layout = task_definition("slotted_post_ring", "easy")().make_layout()
        self.assertEqual(ring_band_runs(layout, make_meshes(layout)[1]), [(-1, "over"), (1, "over")])

    def test_very_easy_ring_lifts_straight_off(self):
        report = check_variant("very_easy")
        self.assertTrue(report["geometry_passed"])
        self.assertEqual(report["design"], "very_easy")
        self.assertTrue(report["lift"]["passed"])

    def test_easier_needs_the_loop_passed_through_first(self):
        report = check_variant("easier")
        self.assertTrue(report["geometry_passed"])
        self.assertEqual(report["design"], "easier")
        self.assertGreater(report["widest_gap_m"], report["bead_diameter_m"])


class Oracle(unittest.TestCase):
    """Wiring and fingertip sizes of the below-easy oracle (below_easy_oracle.py); no physics."""

    def test_both_settings_dispatch_to_the_slotted_session(self):
        from topogym.planning.harbor_bridge.catalog import BELOW_EASY_FAMILIES, session_callback
        from topogym.planning.harbor_bridge.references import reference_data
        self.assertIn("slotted_post_ring", BELOW_EASY_FAMILIES)
        for tier in ("very_easy", "easier"):
            self.assertEqual(session_callback("slotted_post_ring", tier),
                             "topogym.planning.harbor_bridge.below_easy:run_feedback_policy")
            files, _ = reference_data(ROOT, "slotted_post_ring", tier, 0)
            self.assertEqual(files, {})   # closed loop from the measured state; no recorded inputs
        self.assertIsNone(session_callback("slotted_post_ring", "easy"))

    def test_launcher_portability_check_admits_both_settings(self):
        import subprocess
        result = subprocess.run([sys.executable, str(ROOT / "ci_checks/check-oracle-portability.py"), "--families",
                                 "slotted_post_ring", "--tiers", "very_easy", "easier"], capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn("slotted_post_ring easier: passed", result.stdout)

    def test_public_session_runs_very_easy_only(self):
        from types import SimpleNamespace
        from topogym.planning.slotted_post_ring.public_session import run_feedback_policy
        with self.assertRaisesRegex(ValueError, "No Slotted Post easier oracle"):
            run_feedback_policy(SimpleNamespace(), Path("unused"), variation="easier")
        with self.assertRaisesRegex(ValueError, "below-easy settings only"):
            run_feedback_policy(SimpleNamespace(), Path("unused"), variation="easy")

    def test_fingertip_pinch_fits_the_tube(self):
        from topogym.planning.slotted_post_ring import below_easy_oracle as O
        layout = task_definition("slotted_post_ring", "very_easy")().make_layout()
        gap = lambda q: 2 * (q - O.TIP_OFFSET_M)   # distance between the fingertips at native finger target q
        tube = 2 * layout.ring_tube_radius_m
        self.assertGreater(gap(O.PINCH_OPEN_M) - tube, .008)   # at least 4 mm beside the tube on each side
        self.assertLess(gap(O.PINCH_CLOSED_M), tube)           # the tube stops the closing fingers: they squeeze it
        self.assertLess(gap(O.PINCH_OPEN_M), 2 * (.037 - O.TIP_OFFSET_M))   # within the gripper's range


if __name__ == "__main__":
    unittest.main()
