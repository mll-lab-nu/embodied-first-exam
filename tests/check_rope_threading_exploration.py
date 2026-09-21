"""Exploration can defer qualification, never fabricate a certificate or release."""
import json
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest

import numpy as np

from topogym.tasks.rope_threading.physics_probe import classify_execution, validate_execution_mode
from topogym.tasks.rope_threading.reference_actions import ReferenceThreadingActions

REFERENCE = Path(__file__).resolve().parents[1]/"runs/environment-solvability/rope_threading/reference_motion_v1"


class ExplorationChecks(unittest.TestCase):
    def test_explicit_reason_is_required_and_cannot_be_a_certificate(self):
        with self.assertRaises(ValueError):
            validate_execution_mode("full_threading", None, None)
        with self.assertRaises(ValueError):
            validate_execution_mode("full_threading", None, " ")
        with self.assertRaises(ValueError):
            validate_execution_mode("reference_prefix", None, "defer settling")
        with self.assertRaises(ValueError):
            validate_execution_mode("full_threading", Path("qualification.json"), "defer settling")
        validate_execution_mode("full_threading", None, "User requests full trial before settling qualification")

    def test_regular_full_mode_still_rejects_failed_qualification(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp)/"qualification.json"
            path.write_text(json.dumps(dict(passed=False)))
            with self.assertRaises(ValueError):
                validate_execution_mode("full_threading", path, None)

    def test_completed_trial_cannot_be_promoted_even_if_all_run_checks_pass(self):
        report = dict(passed=True, complete_physics_suite_passed=False,
            actuation=dict(passed=True, checks=dict(source_sequence_complete=True, post_release_observed=True)))
        classify_execution(report, "full_threading", "User defers qualification")
        self.assertTrue(report["full_task_observed"])
        self.assertFalse(report["full_threading_verified"])
        self.assertFalse(report["full_demo"])

    def test_failed_physical_check_remains_failed_when_motion_finishes(self):
        report = dict(passed=False, checks=dict(settled_max_speed=False), complete_physics_suite_passed=False,
            actuation=dict(passed=True, checks=dict(source_sequence_complete=True, post_release_observed=True)))
        classify_execution(report, "full_threading", "User defers qualification")
        self.assertFalse(report["passed"])
        self.assertFalse(report["checks"]["settled_max_speed"])
        self.assertTrue(report["full_task_observed"])
        self.assertFalse(report["full_demo"])

    def test_interrupted_actions_are_not_completed(self):
        report = dict(passed=False, complete_physics_suite_passed=False,
            actuation=dict(passed=False, checks=dict(source_sequence_complete=False, post_release_observed=False)))
        classify_execution(report, "full_threading", "User defers qualification")
        self.assertFalse(report["full_sequence_completed"])
        self.assertFalse(report["full_task_observed"])

    @unittest.skipUnless((REFERENCE/"reference_motion.npz").is_file(), "Offline reference unavailable")
    def test_full_execution_keeps_attachment_at_the_prefix_release_time(self):
        for prefix in (False, True):
            with self.subTest(prefix=prefix):
                opened, targets = [], []
                actions = ReferenceThreadingActions(REFERENCE, speed=3., prefix=prefix)
                actions.source_time, actions.last_time, actions.event_index = 24.99, 9.045, 1
                actions.owners, actions.closed, actions.offsets = {3: "right"}, {"right": .011}, {3: np.zeros((1, 3))}
                arms = {side: SimpleNamespace(set_arm_qpos=lambda q: None, set_gripper=lambda q: None,
                    open_gripper=lambda side=side: opened.append(side), hand_pos=lambda: np.zeros(3),
                    hand_quat=lambda: np.array([1., 0., 0., 0.])) for side in ("left", "right")}
                actions.controller = SimpleNamespace(arms=arms)
                actions.task = SimpleNamespace(layout=SimpleNamespace(transform=np.asarray))
                actions.ik = SimpleNamespace(solve_reference=lambda side, position, quat, q: q.copy())
                actions.bands = [SimpleNamespace(release=lambda: None,
                    _handle=SimpleNamespace(update_targets=targets.append)) for _ in range(4)]
                actions.update(9.051)
                if prefix:
                    self.assertEqual(actions.owners, {})
                    self.assertIn("right", opened)
                else:
                    self.assertEqual(actions.owners, {3: "right"})
                    self.assertNotIn("right", opened)
                    self.assertEqual(len(targets), 1)
                    self.assertIsNone(actions.completion_time)


if __name__ == "__main__":
    unittest.main()
