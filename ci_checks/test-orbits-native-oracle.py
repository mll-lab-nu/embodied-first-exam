#!/usr/bin/env python3
"""Action-boundary regressions; these tests provide no physical success evidence."""
from pathlib import Path
from types import SimpleNamespace
import sys
import unittest

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from topogym.planning.orbits.native_session import NativeOrbits, EpisodeFinished
from topogym.planning.harbor_bridge.packaging import collect_helpers


class FakeSession:
    def __init__(self, accepted_fraction=1.):
        self.accepted_fraction = accepted_fraction
        self.accepted = np.zeros(14, dtype=np.float32)
        self.action_layout = list(range(14))
        self.robot = SimpleNamespace(arm_slice={'left': slice(0, 6), 'right': slice(7, 13)},
                                     clip=lambda row: row)
        self.episode_done = False
        self.episode_end = None
        self.calls = []

    def hold_action(self):
        return self.accepted.copy()

    def step(self, row):
        self.calls.append((self.accepted.copy(), row.copy()))
        self.accepted += self.accepted_fraction*(row-self.accepted)
        return False


def controller(fraction=1.):
    oracle = NativeOrbits.__new__(NativeOrbits)
    oracle.session = FakeSession(fraction)
    oracle.joint_step = .039
    oracle.dt = .025
    oracle.command_q = lambda row: row.copy()
    oracle.collision_check = lambda q: {'passed': True}
    oracle.record_progress = lambda **kwargs: None
    return oracle


class ActionBoundary(unittest.TestCase):
    def test_reanchors_after_native_guard_without_overshooting_endpoint(self):
        oracle = controller(.5)
        target = np.zeros(14, dtype=np.float32)
        target[:6], target[7:13] = .20, -.13
        oracle.reach_row(target, 'guarded_move')
        self.assertGreater(len(oracle.session.calls), 5)
        for accepted, requested in oracle.session.calls:
            self.assertEqual(requested.dtype, np.float32)
            self.assertLessEqual(float(np.max(np.abs(requested-accepted))), .039+1e-7)
            self.assertTrue(np.all(requested[:6] <= target[:6]))
            self.assertTrue(np.all(requested[7:13] >= target[7:13]))
        np.testing.assert_allclose(oracle.session.accepted, target, atol=2e-6, rtol=0)

    def test_unreachable_guarded_target_has_a_bounded_failure(self):
        oracle = controller(0.)
        with self.assertRaisesRegex(RuntimeError, 'did not converge'):
            oracle.reach_row(np.full(14, .1, dtype=np.float32), 'blocked', max_seconds=.1)
        self.assertEqual(len(oracle.session.calls), 4)

    def test_fixture_collision_rejects_before_physics(self):
        oracle = controller()
        oracle.collision_check = lambda q: {'passed': False, 'fixture_contacts': [('finger', 'ring_1')]}
        with self.assertRaisesRegex(RuntimeError, 'Unsafe command'):
            oracle.submit(np.ones(14, dtype=np.float32)*.01, 'collision')
        self.assertEqual(oracle.session.calls, [])

    def test_terminal_episode_never_receives_an_extra_action(self):
        oracle = controller()
        oracle.session.episode_end = 'success'
        with self.assertRaises(EpisodeFinished):
            oracle.submit(oracle.session.hold_action(), 'after_success')
        self.assertEqual(oracle.session.calls, [])

    def test_private_package_has_no_alternative_physics_runner(self):
        files = collect_helpers(ROOT, 'topogym.planning.orbits.native_session')
        self.assertIn('topogym/planning/orbits/native_session.py', files)
        for name in files:
            self.assertNotIn('/legacy/', name)
            self.assertNotIn('/rope_sim.py', name)
            self.assertNotIn('/aloha_ik.py', name)
            self.assertNotIn('import mujoco', files[name].read_text())

    def test_catalog_limits_native_callback_to_the_two_new_tiers(self):
        from topogym.planning.harbor_bridge.catalog import session_callback
        for tier in ('very_easy', 'easier'):
            self.assertEqual(session_callback('orbits', tier),
                             'topogym.planning.orbits.native_session:run_feedback_policy')
        for tier in ('easy', 'medium', 'hard'):
            self.assertIsNone(session_callback('orbits', tier))


if __name__ == '__main__':
    unittest.main()
