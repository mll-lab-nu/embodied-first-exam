#!/usr/bin/env python3
"""Private low-tier candidate tests; no Task success or dynamics claim."""
from pathlib import Path
import sys
import tempfile
from types import SimpleNamespace as NS
import unittest
from unittest.mock import patch

import fcl
import numpy as np
from scipy.spatial.transform import Rotation

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from topogym.planning import oracle_ik as ik
from topogym.planning.rope_threading.kinematics import CONTACT_IN_TCP_M
from topogym.planning.oracle_path import SceneCandidateCheck, Shape, joint_samples
from topogym.solvers.genesis_kinematics import GenesisIKSolver


def fixture(tier='very_easy'):
    group = NS(hand_link='hand', arm_joints=('joint',), arm_limits_rad=((-2., 2.),),
               grasp=NS(finger_links=('finger',)))
    entity = NS(n_qs=1, get_qpos=lambda: np.zeros(1))
    robot = NS(entity=entity, groups={'arm': group}, _q_indices={'arm': [0]})
    return NS(_task=NS(variation_id=tier), _robot=robot)


def precise_failure(self, **kwargs):
    if kwargs['position_tolerance_m'] < .0013:
        raise ValueError('Unreachable EE pose: position residual=0.00127 m, orientation=0.0182 rad')
    return np.array([.2])


class CandidateTests(unittest.TestCase):
    def setUp(self):
        mocked = patch.object(ik.OracleIKSolver, '_pose_error', return_value=dict(
            position_residual_m=.00127, orientation_residual_rad=.0182))
        mocked.start()
        self.addCleanup(mocked.stop)

    def test_original_tiers_and_public_solver_keep_strict_failure(self):
        for tier in ('easy', 'medium', 'hard'):
            env = fixture(tier)
            with ik.below_easy_scope(env), patch.object(GenesisIKSolver, 'solve_checked', new=precise_failure):
                with self.assertRaisesRegex(ValueError, 'Unreachable EE pose'):
                    ik.OracleIKSolver(env._robot.entity).solve_checked(link_name='hand')

    def test_both_low_tiers_accept_only_after_path_check_and_write_evidence(self):
        for tier in ('very_easy', 'easier', 'rope_threading_very_easy'):
            env = fixture(tier)
            with tempfile.TemporaryDirectory() as tmp:
                with ik.below_easy_scope(env, tmp) as scope, patch.object(GenesisIKSolver, 'solve_checked', new=precise_failure):
                    calls = []
                    def validate(a, b):
                        calls.append((a.copy(), b.copy()))
                        return dict(passed=True, samples=41)
                    scope.validator = NS(check=validate)
                    q = ik.OracleIKSolver(env._robot.entity).solve_checked(link_name='hand')
                    np.testing.assert_equal(q, [.2])
                    self.assertEqual(len(calls), 3)
                    self.assertTrue(scope.records[-1]['passed'])
                    self.assertIn('0.00127', scope.records[-1]['precise_rejection'])
                self.assertTrue((Path(tmp)/'ik_candidates.json').exists())
            self.assertIsNone(ik.active_scope())

    def test_small_pose_error_does_not_override_collision(self):
        env = fixture()
        with ik.below_easy_scope(env) as scope, patch.object(GenesisIKSolver, 'solve_checked', new=precise_failure):
            scope.validator = NS(check=lambda *a: dict(passed=False, reason='swept_collision'))
            with self.assertRaisesRegex(ValueError, 'No checked IK candidate in the current search'):
                ik.OracleIKSolver(env._robot.entity).solve_checked(link_name='hand')
            self.assertEqual(len(scope.records[-1]['rejected']), 3)

    def test_nesting_and_exception_restore_scope(self):
        env = fixture()
        with self.assertRaisesRegex(RuntimeError, 'stop'):
            with ik.below_easy_scope(env) as outer:
                with ik.below_easy_scope(env) as inner:
                    self.assertIs(inner, outer)
                self.assertIs(ik.active_scope(env._robot.entity), outer)
                self.assertIsNone(ik.active_scope(object()))
                raise RuntimeError('stop')
        self.assertIsNone(ik.active_scope())

    def test_malformed_input_is_not_retried(self):
        env = fixture()
        with ik.below_easy_scope(env) as scope, patch.object(GenesisIKSolver, 'solve_checked', side_effect=ValueError('bad quaternion')) as solve:
            with self.assertRaisesRegex(ValueError, 'bad quaternion'):
                ik.OracleIKSolver(env._robot.entity).solve_checked(link_name='hand')
            self.assertEqual(solve.call_count, 1)
            self.assertFalse(scope.records)

    def test_coupled_workspace_preference_cannot_bypass_path_or_pose_budget(self):
        env = fixture()
        strict = [1e-5, 1e-4, 1e-5]
        residuals = [.002, .02, .015]
        self.assertFalse(ik.accept_coupled_candidate(env._robot, [0.], [.2], residuals, strict))
        with ik.below_easy_scope(env) as scope:
            scope.validator = NS(check=lambda *a: dict(passed=True))
            self.assertTrue(ik.accept_coupled_candidate(env._robot, [0.], [.2], residuals, strict))
            self.assertFalse(ik.accept_coupled_candidate(env._robot, [0.], [.2], [.01, .02, 0], strict))
            self.assertFalse(ik.accept_coupled_candidate(env._robot, [0.], [.2], [np.nan, 0., 0.], strict))
            scope.validator = NS(check=lambda *a: dict(passed=False, reason='swept_collision'))
            self.assertFalse(ik.accept_coupled_candidate(env._robot, [0.], [.2], residuals, strict))

    def test_actual_grasp_transform_includes_orientation_error(self):
        nominal = (np.zeros(3), Rotation.identity())
        actual_tcp = (np.array([.102, 0., 0.]), Rotation.from_euler('z', .08))
        p, r = ik.pose_from_grasp(actual_tcp, [.1, 0., 0.], Rotation.identity())
        self.assertGreater(np.linalg.norm(p-nominal[0]), .007)
        np.testing.assert_allclose(p+r.apply([.1, 0., 0.]), actual_tcp[0])

    def test_public_action_bounds_are_checked_before_geometry(self):
        env = fixture()
        with ik.below_easy_scope(env) as scope:
            scope.public_bounds = {'arm': np.array([[-.1, .1]])}
            with patch.object(scope, 'validator') as geometry:
                self.assertEqual(scope.check([0.], [.2])['reason'], 'public_joint_limits')
                geometry.check.assert_not_called()

    def test_only_numeric_stop_residue_moves_inside_float32_limits(self):
        env = fixture()
        env._robot.groups['arm'].arm_limits_rad = ((-np.pi, np.pi),)
        solver = ik.OracleIKSolver(env._robot.entity)
        with ik.below_easy_scope(env):
            for value in (-np.pi, np.pi):
                q = solver._bounded_roundoff(np.array([value]))
                self.assertLessEqual(abs(float(np.float32(q[0]))), np.pi)
                self.assertLess(abs(q[0]-value), 1e-6)
            np.testing.assert_equal(solver._bounded_roundoff(np.array([np.pi+.001])), [np.pi+.001])


def geometry_fixture(*, obstacle=(.5, 0., 0.), payload=False):
    env = fixture()
    checker = SceneCandidateCheck.__new__(SceneCandidateCheck)
    checker.env, checker.robot, checker.native_pairs = env, env._robot, set()
    robot_link = NS(name='hand', idx=0, idx_local=0)
    wall = NS(name='wall', idx=1, idx_local=0)
    poses = {1: (np.asarray(obstacle), Rotation.identity())}
    checker.frames = lambda q: (np.array([[q[0], 0., 0.]]), Rotation.identity(1))
    checker.link_pose = lambda link: poses[link.idx]
    checker.shapes = [Shape('robot', robot_link, 0, np.zeros((1, 3)), fcl.CollisionObject(fcl.Sphere(.03))),
                      Shape('fixture', wall, 1, np.zeros((1, 3)), fcl.CollisionObject(fcl.Sphere(.03)))]
    held = {}
    if payload:
        link = NS(name='body', idx=2, idx_local=0)
        poses[2] = np.array([.3, .3, 0.]), Rotation.identity()
        checker.shapes.append(Shape('payload', link, 2, np.zeros((1, 3)), fcl.CollisionObject(fcl.Sphere(.03))))
        held[('payload', 'body')] = ('arm', 0, np.array([.3, .3, 0.]), Rotation.identity())
    checker.held_links = lambda p, r: held
    return checker


class GeometryTests(unittest.TestCase):
    def test_endpoints_clear_but_interior_collision_rejected(self):
        checker = geometry_fixture()
        result = checker.check([0.], [1.])
        self.assertFalse(result['passed'])
        self.assertEqual(result['reason'], 'swept_collision')
        self.assertGreater(result['sample'], 1)
        self.assertTrue(geometry_fixture(obstacle=(.5, .2, 0.)).check([0.], [1.])['passed'])

    def test_payload_follows_actual_fk_into_obstacle(self):
        checker = geometry_fixture(obstacle=(.8, .3, 0.), payload=True)
        result = checker.check([0.], [1.])
        self.assertFalse(result['passed'])
        self.assertIn('payload/body', result['pair'])

    def test_limits_nonfinite_and_invalid_sampling_rejected(self):
        self.assertEqual(geometry_fixture().check([0.], [2.1])['reason'], 'joint_limits')
        for a, b in (([np.nan], [0.]), ([0.], [np.inf]), ([0.], [0., 1.])):
            with self.assertRaises(ValueError):
                list(joint_samples(a, b))
        with self.assertRaises(ValueError):
            list(joint_samples([0.], [1.], 0.))

    def test_existing_moving_collision_is_not_approved_by_zero_mesh_depth(self):
        checker = geometry_fixture(obstacle=(.01, 0., 0.))
        with patch.object(checker, 'penetration', return_value=1e-9):
            self.assertFalse(checker.check([0.], [.01])['passed'])
            self.assertTrue(checker.check([0.], [0.])['passed'])

    def test_passive_payload_requires_both_measured_finger_forces(self):
        checker = geometry_fixture(payload=True)
        del checker.held_links  # Exercise the real measured-contact reader.
        payload = checker.shapes[-1].link
        payload.is_fixed = False
        checker.robot.groups['arm'].grasp.finger_links = ('finger_a', 'finger_b')
        links = dict(hand=NS(idx=0, idx_local=0), finger_a=NS(idx=3), finger_b=NS(idx=4))
        checker.robot.entity.get_link = links.__getitem__
        contacts = dict(link_a=[3, 4], link_b=[2, 2], force=[[1., 0., 0.], [-1., 0., 0.]], penetration=[.0001, .0001])
        checker.env._world = NS(read_state=lambda: dict(contacts=contacts))
        p, r = checker.frames([0.])
        self.assertIn(('payload', 'body'), checker.held_links(p, r))
        contacts['force'][1] = [0., 0., 0.]
        self.assertFalse(checker.held_links(p, r))


class EECompilerTests(unittest.TestCase):
    def setUp(self):
        mocked = patch.object(ik.OracleIKSolver, '_pose_error', return_value=dict(
            position_residual_m=.002, orientation_residual_rad=.02))
        mocked.start()
        self.addCleanup(mocked.stop)

    def fixture(self):
        from topogym.robot.joint_position import JointPositionRobot
        robot = JointPositionRobot.__new__(JointPositionRobot)
        robot.groups = {s: NS(name=s, hand_link=s+'/hand', arm_joints=(s+'/arm',),
            arm_limits_rad=((-1., 1.),), finger_joints=(s+'/finger',), actuated_fingers=(s+'/finger',),
            gripper_field='gripper_position_m', gripper_limits=(0., .05),
            tcp_position_in_hand_m=[0., 0., 0.], tcp_orientation_in_hand_wxyz=[1., 0., 0., 0.])
            for s in ('left', 'right')}
        robot.description = NS(robot_id='aloha', groups=tuple(robot.groups.values()))
        robot._q_indices = robot._indices = dict(left=[0, 1], right=[2, 3])
        robot.entity = NS(n_qs=4, get_qpos=lambda: np.zeros(4),
            get_joint=lambda n: NS(qs_idx_local=[1 if n.startswith('left') else 3]))
        robot.observe = lambda: {s: dict(joint_position_rad=np.zeros(1),
            tcp_position_world_m=np.zeros(3), tcp_orientation_wxyz=[1., 0., 0., 0.]) for s in robot.groups}
        targets = {s: dict(joint_position_rad=[.1], gripper_position_m=.02) for s in robot.groups}
        robot.capture_state = lambda: NS(targets=targets)
        return NS(_robot=robot, _task=NS(variation_id='easier'))

    @staticmethod
    def solve(self, **kwargs):
        if kwargs.get('position_tolerance_m', 1e-4) < .002:
            raise ValueError('Unreachable EE pose: test')
        q = kwargs['initial_qpos'].copy()
        q[0 if kwargs['link_name'].startswith('left') else 2] = .2
        return q

    def test_combined_sweep_includes_other_arm_and_both_grippers(self):
        env = self.fixture()
        seen = []
        def check(a, b):
            seen.append(b.copy())
            return dict(passed=True)
        action = {'left': dict(position_world_m=[.1, 0., 0.], orientation_wxyz=[1., 0., 0., 0.],
                               gripper_position_m=.04)}
        with ik.below_easy_scope(env) as scope, patch.object(GenesisIKSolver, 'solve_checked', new=self.solve):
            scope.validator = NS(check=check)
            native = ik.compile_oracle_action(env, action, 'EE_ABS')
        np.testing.assert_allclose(seen[-1], [.2, .04, .1, .02])
        self.assertEqual(native['left']['gripper_position_m'], .04)
        self.assertNotIn('right', native)

    def test_individually_valid_arms_do_not_bypass_combined_collision(self):
        env = self.fixture()
        action = {s: dict(position_world_m=[.1, 0., 0.], orientation_wxyz=[1., 0., 0., 0.])
                  for s in ('left', 'right')}
        with ik.below_easy_scope(env) as scope, patch.object(GenesisIKSolver, 'solve_checked', new=self.solve):
            scope.validator = NS(check=lambda a, b: dict(passed=not bool(np.any(b[[1, 3]]))))
            with self.assertRaisesRegex(ValueError, 'Combined oracle EE path rejected'):
                ik.compile_oracle_action(env, action, 'EE_ABS')

    def test_bad_other_arm_input_is_rejected_before_any_ik_query(self):
        env = self.fixture()
        action = dict(left=dict(position_world_m=[.1, 0., 0.], orientation_wxyz=[1., 0., 0., 0.]),
                      right=dict(gripper_position_m=.2))
        with ik.below_easy_scope(env), patch.object(GenesisIKSolver, 'solve_checked') as solve:
            with self.assertRaisesRegex(ValueError, 'Invalid native gripper'):
                ik.compile_oracle_action(env, action, 'EE_ABS')
            solve.assert_not_called()


class RopeRouteTests(unittest.TestCase):
    def policy(self, tier, *, reject_collision=False):
        from topogym.planning.rope_threading.policy import ThreadingPolicy
        policy = ThreadingPolicy.__new__(ThreadingPolicy)
        q = np.zeros(16)
        q[8:11] = [.15, 0., .15]
        robot = NS(entity=object(), _q_indices={'left': list(range(8)), 'right': list(range(8, 16))})
        policy.env = NS(_robot=robot, _task=NS(difficulty=tier, variation_id=tier))
        policy.fingers = dict(left=.02, right=.02)
        policy.qpos = lambda: q.copy()
        policy.tcp = lambda side: (q[8:11].copy(), Rotation.identity())
        policy.planning = []
        def solve(side, pose, seed):
            if pose[0][2] > .28:
                raise ValueError('test workspace ceiling')
            result = seed.copy()
            result[8:14] = np.r_[pose[0], pose[1].as_rotvec()]
            return result
        policy.kin = NS(solve=solve, check=lambda q: dict(passed=not reject_collision,
            issues=['ring_or_support'] if reject_collision else []))
        return policy

    def test_both_tiers_choose_a_complete_checked_route(self):
        for tier in ('very_easy', 'easier'):
            policy = self.policy(tier)
            route = policy.plan_ring_transfer(np.array([0., 0., .2]))
            trials = policy.planning[-1]['candidates']
            self.assertTrue(trials[-1]['accepted'])
            self.assertTrue(all(not t['accepted'] for t in trials[:-1]))
            self.assertEqual(route[-1][0], 'lower_onto_cradle' if tier == 'very_easy' else 'feed_tail_through_ring')

    def test_easier_feeding_hand_stays_on_entrance_side(self):
        policy = self.policy('easier')
        center = np.array([0., 0., .2])
        route = policy.plan_ring_transfer(center)
        contacts = [p+r.apply(CONTACT_IN_TCP_M) for _, (p, r), _, _ in route]
        # Only the tail passes the plane (ring normal +x); the hand stops 35 mm or more before it.
        self.assertTrue(all(c[0]-center[0] >= .035-1e-9 for c in contacts))
        self.assertAlmostEqual(contacts[0][0]-center[0], .13)

    def test_unreachable_or_colliding_alternatives_report_search_failure(self):
        policy = self.policy('very_easy', reject_collision=True)
        with self.assertRaisesRegex(RuntimeError, 'current search'):
            policy.plan_ring_transfer(np.array([0., 0., .2]))
        # 3 carry heights x 3 yaws x 3 jaw tilts; the old 18 included raises above the ring.
        self.assertEqual(len(policy.planning[-1]['candidates']), 27)
        self.assertTrue(all(not x['accepted'] for x in policy.planning[-1]['candidates']))

    def test_very_easy_route_stays_below_ring_centre_and_ends_on_rim(self):
        policy = self.policy('very_easy')
        center = np.array([0., 0., .2])
        route = policy.plan_ring_transfer(center)
        self.assertEqual([name for name, *_ in route[:2]], ['carry_beside_cradle', 'slide_tail_through_cradle'])
        contacts = [p+r.apply(CONTACT_IN_TCP_M) for _, (p, r), _, _ in route]
        self.assertTrue(all(c[2] < center[2] for c in contacts))
        self.assertAlmostEqual(contacts[-1][2]-center[2], -.066)
        self.assertAlmostEqual(contacts[0][0]-center[0], .10)


if __name__ == '__main__':
    unittest.main()
