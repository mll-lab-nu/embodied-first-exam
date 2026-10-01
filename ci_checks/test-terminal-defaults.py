#!/usr/bin/env python3
"""Default success enablement and terminal wiring; no physical solvability claims."""
from math import ceil
from pathlib import Path
import sys
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT), str(ROOT / "scripts")]

from sample_difficulty_instances import TASK_IDS, sample_instances
from topogym.config.registry import (
    TaskSupportError, require_task_support, task_definition, variation_catalog,
)
from topogym.simulator.interaction import public_info


def measured_terminal(state, private, reference):
    """Synthetic measurements isolate Task.update's gate and stability contract."""
    return (state.get("reached", True), state.get("failure"),
            {"evaluation_status": state.get("status", "available")}, private, None)


def operator_result(task):
    result = task.result
    return public_info(dict(task_success=result.task_success, task_terminated=result.terminated,
                            evaluation_status=result.evaluation_status,
                            goal_evaluation_complete=task.goal_complete))


class TerminalDefaultsTests(unittest.TestCase):
    def test_every_integrated_variation_defaults_to_enabled(self):
        for name in TASK_IDS:
            for row in variation_catalog(name):
                variant = row["variation_id"]
                with self.subTest(task=name, variation=variant):
                    if row["status"] != "integrated":
                        with self.assertRaises(TaskSupportError):
                            require_task_support(name, "solve", variant)
                        continue
                    task = task_definition(name, variant)()
                    self.assertIs(task.goal_complete, True)
                    require_task_support(name, "solve", variant)

    def test_all_sampled_tiers_are_enabled_across_sampling_seeds(self):
        for seed in (0, 7, 20260929, 2**32 - 1):
            rows = sample_instances(dict(task_ids=list(TASK_IDS), sampling_seed=seed,
                                         samples_per_difficulty=1))
            self.assertEqual(len(rows), 39)
            for row in rows:
                with self.subTest(seed=seed, task=row["task_id"], tier=row["difficulty"]):
                    self.assertIs(row["evaluable_for_task_success"], True)

    def test_unqualified_instances_keep_success_enabled(self):
        from topogym.tasks.hedgehog_in_cage.qualification import placement_qualification as hedgehog
        from topogym.tasks.cast_keyhole.qualification import placement_qualification as keyhole
        for name, qualifier in (("hedgehog_in_cage", hedgehog), ("cast_keyhole", keyhole)):
            for tier in ("easy", "medium", "hard"):
                with self.subTest(task=name, tier=tier):
                    task = task_definition(name, tier)({"stable_duration_s": .75}, seed=37)
                    self.assertIsNone(qualifier(task))
                    revision = task.terminal_revision
                    task.goal_region_identity = "a region without historical evidence"
                    self.assertIs(task.goal_complete, True)
                    self.assertEqual(task.terminal_revision, revision)

    def test_qualification_is_metadata_not_calibration_or_enablement(self):
        for name in ("hedgehog_in_cage", "cast_keyhole"):
            for record in (None, {"scope": "historical instance only", "evidence": "old/audit.json"}):
                with self.subTest(task=name, record=record), patch(
                    f"topogym.tasks.{name}.qualification.placement_qualification", return_value=record
                ) as qualify:
                    task = task_definition(name, "hard")(seed=37)
                    task.placement_targets = ("target",)
                    task.placement_remainder = ("remainder",)
                    task.goal_region_identity = "unmatched-region"
                    task.public_instruction()
                    self.assertIs(task.goal_complete, True)
                    qualify.assert_not_called()
                    metadata = task.terminal_metadata()
                    self.assertIs(metadata["goal_complete"], True)
                    self.assertFalse(metadata["thresholds_calibrated"])
                    self.assertFalse(metadata["reachability_qualified"])
                    self.assertEqual(metadata.get("qualification"), record)

    def test_default_success_needs_continuous_available_measurements(self):
        for name in TASK_IDS:
            with self.subTest(task=name):
                task = task_definition(name, "hard")(seed=37)
                self.assertFalse(task.result.task_success)
                with patch.object(task, "_evaluate_terminal", side_effect=measured_terminal):
                    # A true raw candidate starts the window; it cannot immediately win.
                    result = task.update(dict(physics_step=1), .25)
                    self.assertFalse(result.task_success)
                    self.assertEqual(operator_result(task)["task_outcome"], "ongoing")
                    result = task.update(dict(physics_step=2, status="unavailable"), .25)
                    self.assertFalse(result.terminated)
                    self.assertEqual(task.stable_time_s, 0.)
                    self.assertIsNone(operator_result(task)["task_success"])
                    result = task.update(dict(physics_step=3, reached=False), .25)
                    self.assertFalse(result.task_success)
                    end = 4 + ceil(task.config["stable_duration_s"] / .25)
                    for step in range(4, end + 1):
                        result = task.update(dict(physics_step=step), .25)
                        self.assertEqual(result.task_success, step == end)
                    self.assertTrue(result.terminated)
                    self.assertEqual(result.reward, 1.)
                    self.assertEqual(operator_result(task)["task_outcome"], "success")
                    # Termination stays latched on later calls.
                    self.assertIs(task.update(dict(physics_step=end + 1, reached=False), .25), result)

    def test_failure_overrides_a_reached_goal_with_the_default_switch(self):
        for name in TASK_IDS:
            with self.subTest(task=name):
                task = task_definition(name, "easy")()
                with patch.object(task, "_evaluate_terminal", side_effect=measured_terminal):
                    result = task.update(dict(physics_step=1, failure="task_failed"), 10.)
                self.assertTrue(result.terminated)
                self.assertFalse(result.task_success)
                self.assertEqual(result.reward, 0.)
                self.assertEqual(operator_result(task)["task_outcome"], "failure")

    def test_old_enablement_revision_cannot_be_restored_as_a_new_instance(self):
        old_revisions = dict(interlocked_claws="placement_region_v1", horseshoe_ring="placement_region_v1",
            slotted_post_ring="placement_region_v1", orbits="placement_region_v1",
            hedgehog_in_cage="hedgehog_placement_v2", cast_keyhole="cast_keyhole_placement_v2",
            rope_threading="terminal_v2", knot_untying="terminal_v3_release_settling",
            lock_picking="terminal_v3_bore_contact")
        for name, revision in old_revisions.items():
            with self.subTest(task=name):
                cls = task_definition(name, "easy")
                task = cls()
                with patch.object(cls, "terminal_revision", revision):
                    saved = cls().get_state()
                with self.assertRaisesRegex(ValueError, "different task, instance or schema"):
                    task.set_state(saved)


if __name__ == "__main__":
    unittest.main()
