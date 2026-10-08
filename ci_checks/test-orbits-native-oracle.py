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

    def test_rounding_past_a_joint_limit_is_clamped_and_larger_excess_still_raises(self):
        from topogym.planning.harbor_bridge.contracts import BridgeError
        oracle = controller()
        lo = float(np.float32(-np.pi))
        oracle.session.robot.clip = lambda row: np.maximum(np.asarray(row, dtype=np.float64), lo)
        oracle.session.accepted[3] = -3.12
        row = oracle.session.hold_action().astype(np.float64)
        row[3] = lo-5e-5  # IK exactly at the model limit (very_easy's left approach)
        oracle.submit(row, 'limit')
        self.assertEqual(float(oracle.session.calls[-1][1][3]), lo)
        row[3] = lo-1e-3
        with self.assertRaisesRegex(BridgeError, 'clipped'):
            oracle.submit(row, 'beyond')
        self.assertEqual(len(oracle.session.calls), 1)

    def test_reach_checks_every_row_and_stages_the_wrist_first_past_a_mid_path_collision(self):
        """very_easy's right approach: both endpoints pass, but the joint-interpolated rows sweep the right gripper past
        the parked left one (0.44 mm, local Harbor run 10-06). Rows are checked before any step; the wrist goes first."""
        oracle = controller()
        target = np.zeros(14)
        target[7], target[11] = .4, .5  # right waist, right wrist_angle

        def check(q):
            swept = .1 < q[7] < .3 and q[11] < .3
            return {'passed': not swept, 'issues': ['inter_arm'] if swept else []}

        oracle.collision_check = check
        oracle.reach_checked(target, 'approach')
        for _, requested in oracle.session.calls:
            self.assertTrue(check(requested)['passed'])
        np.testing.assert_allclose(oracle.session.accepted, target, atol=2e-6, rtol=0)
        oracle = controller()
        oracle.collision_check = lambda q: {'passed': not .1 < q[7] < .3, 'issues': ['inter_arm']}
        with self.assertRaisesRegex(RuntimeError, 'No collision-free joint ordering'):
            oracle.reach_checked(target, 'approach')
        self.assertEqual(oracle.session.calls, [])

    def test_grasp_takes_the_least_tilted_candidate_whose_whole_approach_is_clear(self):
        """very_easy run 6: the upright pregrasp passed at both ends, but its path crossed the parked hand in every
        joint ordering. The next tilt, whose path is clear, is taken; no row is sent for the blocked one."""
        from unittest import mock
        from scipy.spatial.transform import Rotation
        import topogym.planning.orbits.native_session as module

        class Settled(Exception):
            pass

        oracle = controller()
        oracle.robot = SimpleNamespace(_q_indices={'left': list(range(8))},
                                       groups={'left': SimpleNamespace(arm_limits_rad=[[-np.pi, np.pi]]*6)})
        oracle.full_q, oracle.arm_bases = np.zeros(8), {'left': np.array([0., .5, 0.])}
        oracle.bias, oracle.pinch_turns, oracle.grasps, oracle.close_width = {'left': np.zeros(3)}, {}, {}, .0028
        oracle.line = lambda: None
        oracle.at = lambda arc, line=None: np.array([.3, .1, .02])
        oracle.jaws = lambda widths, phase, seconds=.5: None
        tilts = iter(np.repeat([0., 15., 30., 45., 0., 15., 30., 45.], 2))
        oracle.solve_contact_pose = lambda side, point, turn, q: np.r_[.3, 0., 0., 0., next(tilts)/100, 0., 0., 0.]

        def check(q):  # waist through (0.1, 0.2) rad with the wrist angle still below 0.1 rad: crosses the parked hand
            return {'passed': not (.1 < q[0] < .2 and q[4] < .1)}

        def settle(seconds, phase):
            raise Settled(phase)

        oracle.collision_check, oracle.hold = check, settle
        with mock.patch.object(module, 'vertical_pinch', lambda point, tangent, flip: (None, Rotation.identity())):
            with self.assertRaisesRegex(Settled, 'approach_settle'):
                oracle.grasp_one('left', .2)
        self.assertTrue(all(check(row)['passed'] for _, row in oracle.session.calls))
        np.testing.assert_allclose(oracle.session.accepted[:6], [.3, 0., 0., 0., .15, 0.], atol=2e-6)

    def test_move_refuses_an_ik_branch_change_before_stepping(self):
        """very_easy run 8: leaning the right wrist met the forearm-roll limit; the IK answered from another branch
        and walking the joints across swung the gripper and threw the cord. The jump is refused, nothing is sent."""
        from scipy.spatial.transform import Rotation
        oracle = controller()
        oracle.contact = lambda side: (np.zeros(3), Rotation.identity())
        rows = iter([np.r_[np.zeros(7), [0., 0., 0., 3.1, 0., 0.], 0.], np.r_[np.zeros(7), [0., 0., 0., 2.3, .8, 0.], 0.]])
        oracle.solve_contacts = lambda points, turns: next(rows)
        oracle.session.accepted[10] = 3.08
        with self.assertRaisesRegex(RuntimeError, 'IK branch change in lean'):
            oracle.move({'right': np.zeros(3)}, {'right': Rotation.from_rotvec([.05, 0., 0.])}, 'lean')
        self.assertEqual(len(oracle.session.calls), 1)

    def test_grasp_prefers_a_candidate_with_forearm_roll_travel(self):
        """Both candidates have clear approaches; the upright one sits 0.04 rad from the forearm-roll limit, so the
        15-degree one with travel for a later wrist lean is taken."""
        from unittest import mock
        from scipy.spatial.transform import Rotation
        import topogym.planning.orbits.native_session as module

        class Settled(Exception):
            pass

        oracle = controller()
        oracle.robot = SimpleNamespace(_q_indices={'left': list(range(8))},
                                       groups={'left': SimpleNamespace(arm_limits_rad=[[-np.pi, np.pi]]*6)})
        oracle.full_q, oracle.arm_bases = np.zeros(8), {'left': np.array([0., .5, 0.])}
        oracle.bias, oracle.pinch_turns, oracle.grasps, oracle.close_width = {'left': np.zeros(3)}, {}, {}, .0028
        oracle.line = lambda: None
        oracle.at = lambda arc, line=None: np.array([.3, .1, .02])
        oracle.jaws = lambda widths, phase, seconds=.5: None
        rolls = iter(np.repeat([3.1, 1., 1., 1., 1., 1., 1., 1.], 2))
        oracle.solve_contact_pose = lambda side, point, turn, q: np.r_[0., 0., 0., next(rolls), 0., 0., 0., 0.]

        def settle(seconds, phase):
            raise Settled(phase)

        oracle.hold = settle
        with mock.patch.object(module, 'vertical_pinch', lambda point, tangent, flip: (None, Rotation.identity())):
            with self.assertRaisesRegex(Settled, 'approach_settle'):
                oracle.grasp_one('left', .2)
        self.assertAlmostEqual(float(oracle.session.accepted[3]), 1., places=5)

    def test_a_pinch_that_does_not_lift_the_cord_is_retried_once(self):
        """A pinch on a cord lying on its support held 3 times in 5 (2026-10-07); the cord stays where it was, so
        the hand opens, rises 6 cm, forgets its alignment bias and grasps again. A second miss still fails."""
        from scipy.spatial.transform import Rotation
        from topogym.planning.orbits.native_session import GraspNotFollowing
        oracle = controller()
        oracle.bias, oracle.grasps = {'left': np.array([.001, 0., -.003])}, {}
        oracle.contact = lambda side: (np.array([.2, .1, .03]), Rotation.identity())
        phases, attempts = [], []
        oracle.jaws = lambda widths, phase, seconds=.5: phases.append(phase)
        oracle.move = lambda contacts, turns, phase, speed=.04: phases.append((phase, contacts['left'][2]))

        def grasp_one(side, station, pre_height=.06):
            attempts.append(oracle.bias[side].copy())
            oracle.grasps[side] = station
            if len(attempts) < 2:
                raise GraspNotFollowing(f'Physical grasp did not follow: {side}')
            return {side: 'turn'}

        oracle.grasp_one = grasp_one
        self.assertEqual(oracle.grasp_retry('left', .3), {'left': 'turn'})
        self.assertEqual(phases, ['regrasp_open', ('regrasp_lift', .09)])
        np.testing.assert_array_equal(attempts[1], np.zeros(3))
        attempts.clear()
        oracle.grasp_one = lambda side, station, pre_height=.06: (attempts.append(1), (_ for _ in ()).throw(
            GraspNotFollowing(f'Physical grasp did not follow: {side}')))
        with self.assertRaises(GraspNotFollowing):
            oracle.grasp_retry('left', .3)
        self.assertEqual(len(attempts), 2)

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

    def test_support_limited_pads_align_in_plane_then_pinch(self):
        """The cord rests on the support and the pads stop 1.7 mm above its centre: a second height correction has no
        pose above the support (lab, both tiers' first align); the in-plane error still converges and the jaws close."""
        from unittest import mock
        from scipy.spatial.transform import Rotation
        import topogym.planning.orbits.native_session as module
        oracle = controller()
        cord, tracking = np.array([.30, .10, .0229]), np.array([-.002, .001, 0.])
        lift, phases = [0.], []
        oracle.robot = SimpleNamespace(_q_indices={'left': list(range(8))},
                                       groups={'left': SimpleNamespace(arm_limits_rad=[[-np.pi, np.pi]]*6)})
        oracle.full_q, oracle.arm_bases = np.zeros(8), {'left': np.array([0., .5, 0.])}
        oracle.bias, oracle.pinch_turns, oracle.grasps, oracle.close_width = {'left': np.zeros(3)}, {}, {}, .0028
        oracle.line = lambda: None
        oracle.at = lambda arc, line=None: cord+[0., 0., lift[0]]
        oracle.jaws = lambda widths, phase, seconds=.5: phases.append(phase)
        oracle.solve_contact_pose = lambda side, point, turn, q: q
        oracle.reach_row = lambda row, phase, **kwargs: phases.append(phase)
        oracle.hold = lambda seconds, phase: None
        oracle.move = lambda contacts, turns, phase, speed=.04: lift.__setitem__(0, .012 if phase == 'test_lift' else 0.)

        def contact(side):
            pad = cord+oracle.bias[side]+tracking
            pad[2] = cord[2]+.0017+lift[0]
            return pad, Rotation.identity()

        def solve_contacts(contacts, turns):
            if oracle.bias['left'][2] < -.003:
                raise ValueError('No close contact pose above the support surface: left')
            return np.zeros(14)

        oracle.contact, oracle.solve_contacts = contact, solve_contacts
        with mock.patch.object(module, 'vertical_pinch', lambda point, tangent, flip: (None, Rotation.identity())):
            oracle.grasp_one('left', .2)
        self.assertEqual(phases.count('align'), 2)
        self.assertIn('pinch', phases)
        np.testing.assert_allclose(oracle.bias['left'], [.002, -.001, -.0017], atol=1e-9)

    def test_catalog_limits_native_callback_to_the_two_new_tiers(self):
        from topogym.planning.harbor_bridge.catalog import session_callback
        for tier in ('very_easy', 'easier'):
            self.assertEqual(session_callback('orbits', tier),
                             'topogym.planning.orbits.native_session:run_feedback_policy')
        for tier in ('easy', 'medium', 'hard'):
            self.assertIsNone(session_callback('orbits', tier))


class ChainFreeCheck(unittest.TestCase):
    def test_cord_links_leave_the_swept_check_and_the_fixture_stays(self):
        """local very_easy 2026-10-07: a loop link resting on a finger refused every motion of that hand."""
        from unittest import mock
        from topogym.planning.orbits.native_session import chain_free_check

        class Stand:
            def __init__(self, env):
                self.shapes = [SimpleNamespace(entity=e) for e in ('robot', 'cord', 'cord', 'post_1', 'stopper_ball')]
        with mock.patch('topogym.planning.oracle_path.SceneCandidateCheck', Stand):
            kept = [s.entity for s in chain_free_check(None).shapes]
        self.assertEqual(kept, ['robot', 'post_1', 'stopper_ball'])


if __name__ == '__main__':
    unittest.main()
