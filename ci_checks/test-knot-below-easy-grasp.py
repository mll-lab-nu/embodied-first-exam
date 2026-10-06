#!/usr/bin/env python3
"""Regressions for the measured failed easier end grasp; no physical success claims."""
from pathlib import Path
import sys
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch

import numpy as np
from scipy.spatial.transform import Rotation

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from topogym.planning.knot_untying.below_easy_runner import BelowEasyRunner, EndGraspFailure, lift_measurement
from topogym.planning.knot_untying.robot_oracle import Runner


class EndGraspContracts(unittest.TestCase):
    def runner(self, measured, live_target):
        runner = BelowEasyRunner.__new__(BelowEasyRunner)
        runner._end_context = dict(k=1, attempt=0)
        runner.length = 1.
        runner._save_end_attempts = Mock()
        runner.tcp = lambda side: np.array(measured)
        runner.robot = SimpleNamespace(observe=lambda: {
            'left': dict(tcp_orientation_wxyz=[1., 0., 0., 0.], joint_position_rad=np.zeros(6))})
        runner.pose = lambda side, station, flips: (np.array(live_target), Rotation.identity(), 1, np.zeros(6))
        return runner

    def test_measured_28mm_preclose_error_never_closes_jaws(self):
        runner = self.runner([-.0089, -.0263, 0.], [0., 0., 0.])
        plan = dict(left=(np.zeros(3), Rotation.identity(), 1, np.zeros(6)))
        with patch.object(Runner, 'place', return_value=([.035], dict(left=.038), plan, {})), \
                patch.object(Runner, 'pinch') as pinch:
            with self.assertRaises(EndGraspFailure):
                runner.grasp(('left',), (.035,), 'd1:grasp_ends')
            pinch.assert_not_called()
        self.assertAlmostEqual(runner._end_context['alignment']['left']['position_m'], .02776508598942204)

    def test_last_reaim_does_not_count_as_reached(self):
        runner = self.runner([0., 0., 0.], [.012, 0., 0.])
        stale = dict(left=(np.zeros(3), Rotation.identity(), 1, np.zeros(6)))
        with patch.object(Runner, 'place', return_value=([.035], dict(left=.038), stale, {})), \
                patch.object(Runner, 'pinch') as pinch:
            with self.assertRaises(EndGraspFailure):
                runner.grasp(('left',), (.035,), 'd1:grasp_ends')
            pinch.assert_not_called()

    def test_measured_aligned_grasp_can_close(self):
        runner = self.runner([.0005, 0., 0.], [0., 0., 0.])
        plan = dict(left=(np.zeros(3), Rotation.identity(), 1, np.zeros(6)))
        with patch.object(Runner, 'place', return_value=([.035], dict(left=.038), plan, {})), \
                patch.object(Runner, 'pinch', return_value=['placed']) as pinch:
            self.assertEqual(runner.grasp(('left',), (.035,), 'd1:grasp_ends'), ['placed'])
            pinch.assert_called_once()

    def test_successful_approach_air_error_is_not_a_preclose_error(self):
        runner = self.runner([.0136, 0., .04], [0., 0., 0.])
        plan = dict(left=(np.zeros(3), Rotation.identity(), 1, np.zeros(6)))
        tracking = dict(ready=True, errors=dict(left=dict(position_m=.0136, orientation_rad=.08)))
        with patch.object(Runner, 'wait_for_pregrasp', return_value=tracking), \
                patch.object(Runner, 'converge') as converge:
            self.assertTrue(runner.wait_for_pregrasp(('left',), plan, 'd1:grasp')['ready'])
            converge.assert_not_called()
        self.assertEqual(runner._end_context['pregrasp']['errors']['left']['position_m'], .0136)

    def test_unfinished_approach_is_rejected_before_descent(self):
        runner = self.runner([.03, 0., .04], [0., 0., 0.])
        plan = dict(left=(np.zeros(3), Rotation.identity(), 1, np.zeros(6)))
        with patch.object(Runner, 'wait_for_pregrasp', return_value=dict(ready=False, errors={} )):
            with self.assertRaises(EndGraspFailure):
                runner.wait_for_pregrasp(('left',), plan, 'd1:grasp')

    def test_stationary_rope_does_not_pass_a_moving_gripper_probe(self):
        origin = np.zeros(3)
        result = lift_measurement(origin, origin, origin, np.array([0., 0., .015]))
        self.assertFalse(result['followed'])
        # A held material point moves with the actual contact point.
        held = lift_measurement(origin, np.array([0., 0., .014]), origin, np.array([0., 0., .015]))
        self.assertTrue(held['followed'])

    def test_shared_experimental_policies_do_not_change_below_easy_steps(self):
        def initialize(runner, args, *, session):
            runner.joint_step_limit = .04
            runner.limiter = object()
            runner.hover_gate = True
            runner.crush_guard = True
        args = SimpleNamespace(variation='knot_untying_easier')
        with patch.object(Runner, '__init__', initialize):
            runner = BelowEasyRunner(args, session=object())
        self.assertIsNone(runner.limiter)
        self.assertFalse(runner.hover_gate)
        with patch('topogym.planning.knot_untying.below_easy_runner.step_with_joint_limit') as step:
            runner.step('d1:spread')
            step.assert_called_once_with(runner, 'd1:spread', .04)


if __name__ == '__main__':
    unittest.main()
