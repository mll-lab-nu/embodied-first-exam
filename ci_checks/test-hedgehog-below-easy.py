#!/usr/bin/env python3
"""Below-easy Hedgehog settings: registration, object-level design intent and the oracle's private inputs; no physics.

The design checks rebuild the frozen task geometry (about one minute in total).
"""
from pathlib import Path
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from topogym.config.registry import seeded_variation, task_definition
from topogym.planning.hedgehog_in_cage.below_easy_witness import GRIP_LENGTH_M, check_variant
from topogym.tasks.hedgehog_in_cage.below_easy import HedgehogBelowEasyTask, cage


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

    def test_settings_differ_only_in_the_window_width(self):
        very_easy, easier = (task_definition("hedgehog_in_cage", n)() for n in ("very_easy", "easier"))
        self.assertEqual({k for k in very_easy.config if very_easy.config[k] != easier.config[k]}, {"cage"})
        self.assertEqual((very_easy.config["cage"], easier.config["cage"]), (cage(118.), cage(108.)))
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
    """A spike points at the robot from outside the cage; very_easy exits by translation,
    easier only after one roll about that spike's axis."""

    def test_very_easy_exits_by_translation(self):
        with tempfile.TemporaryDirectory() as folder:
            report = check_variant("very_easy", Path(folder))
        self.assertTrue(report["initial_free"])
        self.assertGreaterEqual(report["held_spike"]["outside_m"], GRIP_LENGTH_M)
        self.assertTrue(report["translation_exit_at_rest"])
        self.assertEqual(report["design"], "very_easy")

    def test_easier_needs_one_roll(self):
        with tempfile.TemporaryDirectory() as folder:
            report = check_variant("easier", Path(folder))
        self.assertTrue(report["initial_free"])
        self.assertGreaterEqual(report["held_spike"]["outside_m"], GRIP_LENGTH_M)
        self.assertFalse(report["translation_exit_at_rest"])
        self.assertEqual(report["design"], "easier")
        self.assertGreaterEqual(abs(report["roll_deg"]), 30)


class Oracle(unittest.TestCase):
    """The robot oracle holds S10 from outside the cage and follows one checked pickup per setting."""

    def pickups(self):
        import json
        from topogym.planning.harbor_bridge.references import reference_data
        for name in ("very_easy", "easier"):
            files, _ = reference_data(ROOT, "hedgehog_in_cage", name, 0)
            self.assertEqual(list(files), [f"topogym/planning/harbor_bridge/reference_data/hedgehog_in_cage/{name}/pickup.json"])
            yield name, json.loads(Path(next(iter(files.values()))).read_text())

    def test_both_settings_use_the_below_easy_dispatcher(self):
        from topogym.planning.harbor_bridge.catalog import session_callback
        for name in ("very_easy", "easier"):
            self.assertEqual(session_callback("hedgehog_in_cage", name),
                             "topogym.planning.harbor_bridge.below_easy:run_feedback_policy")

    def test_pickups_hold_the_robot_facing_spike_near_its_tip(self):
        import numpy as np
        from topogym.assets.geometry.hedgehog_in_cage import HedgehogLayout
        from topogym.planning.hedgehog_in_cage.below_easy_pickup import SPIKE
        for name, pickup in self.pickups():
            task = task_definition("hedgehog_in_cage", name)()
            root, tip = HedgehogLayout(task.template(), float(task.config["scale"])).spike_segments()[SPIKE]
            axis = (tip - root) / np.linalg.norm(tip - root)
            grip = np.asarray(pickup["grip_point_in_ball"])
            self.assertEqual(pickup["spike"], SPIKE)
            self.assertLess(np.linalg.norm(np.cross(grip, axis)), 1e-9)
            self.assertLess(np.linalg.norm(tip) - grip @ axis, GRIP_LENGTH_M)
            self.assertEqual(len(pickup["qpos"]), 15)

    def test_only_easier_turns_the_ball(self):
        """very_easy leaves by translation; easier turns the ball once, 20 deg about the vertical, before its pull."""
        import numpy as np
        from scipy.spatial.transform import Rotation
        for name, pickup in self.pickups():
            rest = Rotation.from_quat(np.asarray(HedgehogBelowEasyTask.defaults["ball_pose"]["quaternion_wxyz"])[[1, 2, 3, 0]])
            for hint in pickup["object_path_hints"]:
                turn = (Rotation.from_quat(np.asarray(hint["quaternion_wxyz"])[[1, 2, 3, 0]]) * rest.inv()).as_rotvec()
                if name == "very_easy":
                    self.assertLess(np.degrees(np.linalg.norm(turn)), .5)
                else:
                    self.assertAlmostEqual(np.degrees(np.linalg.norm(turn)), 20., delta=.5)
                    self.assertGreater(-turn[2] / np.linalg.norm(turn), .999)


if __name__ == "__main__":
    unittest.main()
