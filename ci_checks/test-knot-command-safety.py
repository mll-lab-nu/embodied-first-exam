#!/usr/bin/env python3
"""Controller regressions for observed height drift and below-table release targets."""
from pathlib import Path
import json
import sys
from types import SimpleNamespace
import unittest
from unittest.mock import Mock

import numpy as np
from scipy.spatial.transform import Rotation

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from topogym.planning.knot_untying.robot_oracle import COMMAND_TABLE_GAP_M, Runner
from topogym.planning.knot_untying.kinematics import CONTACT_IN_TCP_M


class CommandSafety(unittest.TestCase):
    def test_pregrasp_flip_prefers_less_measured_joint_travel(self):
        r = Runner.__new__(Runner)
        r.motion_options = {}; r.full_q = np.zeros(6)
        r.robot = SimpleNamespace(_q_indices={'left': np.arange(6)},
            observe=lambda: {'left': {'joint_position_rad': np.zeros(6)}})
        r.line = lambda: np.array([[0., 0., 0.], [1., 0., 0.]])
        r.at = lambda line, station: np.array([station, 0., 0.])
        def solve(side, pose, seed):
            # Both jaw flips reach the rope; the first needs a pi wrist turn.
            q = np.zeros(6)
            q[3] = np.pi if pose[1].apply([0., 1., 0.])[1] > 0 else .1
            return q
        r.ik = SimpleNamespace(solve=solve)
        self.assertEqual(r.pose('left', .5)[2], -1)
        r.motion_options = {'grasp_flip': 1}
        self.assertEqual(r.pose('left', .5)[2], 1)
        # Re-aiming a selected flip must preserve that flip.
        self.assertEqual(r.pose('left', .5, (-1,))[2], -1)

    def test_pregrasp_waits_for_measured_orientation_then_descends(self):
        r = Runner.__new__(Runner)
        r.dt = .025; r.motion_options = {'approach_wait_s': .1}
        turn = Rotation.identity(); plans = {'left': (np.array([0., 0., 1.]), turn)}
        count = [0]
        def observation():
            rot = Rotation.from_euler('x', .5 if count[0] < 2 else 0.)
            return {'left': dict(tcp_position_world_m=[0., 0., 1.05],
                                 tcp_orientation_wxyz=rot.as_quat()[[3, 0, 1, 2]])}
        r.robot = SimpleNamespace(observe=observation)
        phases = []
        def step(phase):
            phases.append(phase); count[0] += 1
        r.step = step
        result = r.wait_for_pregrasp(('left',), plans, 'd1:grasp')
        self.assertTrue(result['ready']); self.assertAlmostEqual(result['waited_s'], .05)
        self.assertEqual(phases, ['d1:grasp:approach_settle']*2)
        # A bounded synchronization wait is not a new grasp rejection rule.
        r.motion_options['approach_wait_s'] = 0.; count[0] = 0
        self.assertFalse(r.wait_for_pregrasp(('left',), plans, 'd1:grasp')['ready'])

    def test_grasp_pose_can_tilt_and_rotate_without_moving_pad_contact(self):
        from topogym.planning.knot_untying.kinematics import vertical_pinch
        point = np.array([.2, .1, .94])
        for yaw, tilt in ((0., 0.), (30., 20.), (-30., -20.)):
            tcp, turn = vertical_pinch(point, [1., .3], yaw_deg=yaw, tilt_deg=tilt)
            np.testing.assert_allclose(tcp+turn.apply(CONTACT_IN_TCP_M), point, atol=1e-12)
            if tilt:
                self.assertGreater(np.linalg.norm(turn.apply([1., 0., 0.])-np.array([0., 0., -1.])), .1)

    def test_route_search_can_choose_both_ends_and_a_spatial_pull(self):
        from topogym.planning.knot_untying.route_rule import choose
        line = np.array([[0., 0., 0.], [1., 0., .1], [1., 1., 0.], [0., 1., -.1]])
        stations = np.arange(4.)
        crossings = [dict(segments=(0, 2), parameters=(.5, .5), first_over=False)]
        for end in ('A', 'B'):
            action = choose(line, stations, crossings, 3., end_choice=end, yaw_deg=40., pitch_deg=20.)
            self.assertEqual(action['end'], end)
            self.assertAlmostEqual(action['direction'][2], np.sin(np.deg2rad(20.)))
            self.assertAlmostEqual(np.linalg.norm(action['direction']), 1.)

    def test_spatial_withdrawal_executes_arched_and_sideways_targets(self):
        r = Runner.__new__(Runner)
        points = {'right': np.array([-.2, 0., .1]), 'left': np.array([.2, 0., .1])}
        r.args = SimpleNamespace(max_pull=.15, full_pull=True, speed=.04)
        r.log = [dict(t=0.)]; r.grasps = {}; r.arms_for = lambda _: ('right', 'left')
        r.crossings = lambda: [1]; r.tcp = lambda side: points[side].copy()
        r.contact_point = r.tcp; r.release = Mock()
        def grasp(sides, stations, phase):
            r.grasps = {side: dict(s=s, turn=None) for side, s in zip(sides, stations)}
            return []
        r.grasp = grasp; r.smooth = lambda a, b, speed: [b.copy()]
        pulls = []
        def move(side, targets, turn, phase, **kwargs):
            if phase.endswith(':pull'): pulls.append(targets[-1].copy())
            points[side] = targets[-1].copy()
            r.log.append(dict(t=len(r.log)*.025))
            return True
        r.cartesian = move
        r.withdraw(1, dict(s_anchor=.015, s_pull=1.1, direction=[1., 0., 0.]),
                   dict(lift=.03, path_arch_m=.04, path_lateral_m=.08))
        self.assertGreater(pulls[0][1], .05)
        self.assertGreater(pulls[0][2], .15)
        np.testing.assert_allclose(pulls[-1], [.35, 0., .13], atol=1e-12)

    def test_below_table_target_is_rejected_before_native_step(self):
        r = Runner.__new__(Runner)
        r.q, r.g = {'left': np.zeros(6)}, {'left': .005}
        r.session = SimpleNamespace(episode_end=None, episode_done=False,
            hold_action=lambda: np.zeros(7), robot=SimpleNamespace(arm_slice={'left': slice(0, 6)},
            grip_index={'left': 6}), step=Mock())
        r.command_positions = lambda row: row
        r.ik = SimpleNamespace(gripper_table_clearance=lambda q: {'left': -.017})
        with self.assertRaisesRegex(ValueError, 'Unsafe gripper command'):
            r.step('release')
        r.session.step.assert_not_called()

    def test_cartesian_solver_raises_unsafe_goal_before_acceptance(self):
        r = Runner.__new__(Runner)
        r.full_q = np.zeros(7); r.bias = {'left': np.zeros(3)}; r.g = {'left': .005}
        r.robot = SimpleNamespace(groups={'left': None}, _q_indices={'left': list(range(6))})
        r.session = SimpleNamespace(hold_action=lambda: np.zeros(7),
            robot=SimpleNamespace(arm_slice={'left': slice(0, 6)}, grip_index={'left': 6}))
        r.command_positions = lambda row: row.copy()
        goals = []
        def solve(side, goal, seed):
            goals.append(goal[0].copy())
            q = np.zeros(7); q[:3] = goal[0]
            return q
        r.ik = SimpleNamespace(solve=solve,
            gripper_table_clearance=lambda q, sides=None: {'left': float(q[2])})
        q = r.solve('left', [0, 0, -.017], None)
        self.assertGreaterEqual(q[2], COMMAND_TABLE_GAP_M)
        self.assertEqual(len(goals), 2)
        np.testing.assert_array_equal(goals[0][:2], goals[1][:2])

    def test_release_does_not_subtract_original_lift_from_a_sagged_tcp(self):
        r = Runner.__new__(Runner)
        turn = Rotation.identity()
        rest_z = 1.+.004-turn.apply(CONTACT_IN_TCP_M)[2]
        point = np.array([.2, .1, rest_z+.002])
        r.task = SimpleNamespace(table_height_m=1., layout=SimpleNamespace(rope_radius_m=.004))
        r.grasps = {'left': dict(turn=turn, open=.03)}; r.g = {'left': .005}; r.dt = .025
        r.tcp = lambda side: point.copy()
        r.smooth = lambda a, b, speed: [b.copy()]
        paths = []
        def move(side, targets, turn, phase):
            paths.append((phase, np.asarray(targets).copy())); point[:] = targets[-1]
        r.cartesian = move; r.step = Mock()
        r.release('left', .03, 'release')
        self.assertAlmostEqual(paths[0][1][-1, 2], rest_z)
        self.assertGreater(paths[0][1][-1, 2], rest_z+.002-.03)

    def test_near_floor_seed_within_ik_tolerance_gets_a_safe_upward_retry(self):
        r = Runner.__new__(Runner)
        r.full_q = np.zeros(7)
        r.full_q[2] = .000498  # 2 um below the command margin, above the table
        r.bias = {'left': np.zeros(3)}
        r.g = {'left': .038}
        r.robot = SimpleNamespace(groups={'left': None}, _q_indices={'left': list(range(6))})
        r.session = SimpleNamespace(hold_action=lambda: np.zeros(7),
            robot=SimpleNamespace(arm_slice={'left': slice(0, 6)}, grip_index={'left': 6}))
        r.command_positions = lambda row: row.copy()
        goals = []

        def solve(side, goal, seed):
            goals.append(goal[0].copy())
            q = seed.copy()
            if np.linalg.norm(goal[0]-q[:3]) > 1e-5:
                q[:3] = goal[0]
            return q

        r.ik = SimpleNamespace(solve=solve,
            gripper_table_clearance=lambda q, sides=None: {'left': float(q[2])})
        q = r.solve('left', [0, 0, .000498], None)
        self.assertGreaterEqual(q[2], COMMAND_TABLE_GAP_M)
        self.assertGreater(len(goals), 1)
        np.testing.assert_array_equal(np.asarray(goals)[:, :2], 0.)
        self.assertTrue(np.all(np.diff(np.asarray(goals)[:, 2]) > 0))

        # A solver that remains below the margin must still fail without
        # accepting a command, and preserve the exact attempted targets.
        before = r.full_q.copy()
        r.ik.gripper_table_clearance = lambda q, sides=None: {'left': .000498}
        with self.assertRaisesRegex(ValueError, 'No reachable gripper command') as caught:
            r.solve('left', [0, 0, .000498], None)
        np.testing.assert_array_equal(r.full_q, before)
        detail = json.loads(str(caught.exception).split(': ', 1)[1])
        self.assertEqual(detail['side'], 'left')
        self.assertEqual(detail['required_gap_m'], COMMAND_TABLE_GAP_M)
        self.assertEqual(len(detail['trace']), 4)
        self.assertEqual(detail['trace'][-1]['gap_m'], .000498)

    def test_native_session_owns_floor_and_accepted_targets_seed_next_ik(self):
        from topogym.planning.knot_untying.artifacts import load_tooling
        tooling = load_tooling('knot_untying_hard')
        r = Runner.__new__(Runner)
        r.full_q = np.zeros(7)
        r.bias = {'left': np.zeros(3)}
        r.q, r.g = {'left': np.zeros(6)}, {'left': .038}
        r.robot = SimpleNamespace(groups={'left': None}, _q_indices={'left': list(range(6))})
        previous = np.zeros(7)
        previous[6] = .038
        r.session = s = SimpleNamespace(episode_end=None, episode_done=False,
            robot=SimpleNamespace(arm_slice={'left': slice(0, 6)}, grip_index={'left': 6}),
            sim_time_s=.025, physics_steps=10, n_steps=0, last_guard=None,
            monitor=SimpleNamespace(guard=Mock()))
        s.hold_action = lambda: previous.copy()
        guard = object.__new__(tooling._TableGuard)
        guard.s, guard.table, guard.limit = s, 0., tooling.TABLE_GUARD_MARGIN_M
        guard.points, guard.count, guard.events = {'left': [('tip', None)]}, 0, []
        guard.lowest = lambda row: {'left': float(row[2])}
        s.table_guard = guard
        accepted_rows = []

        def native_step(row):
            accepted = guard.apply(np.asarray(row, np.float32).astype(float), previous)
            previous[:] = accepted
            accepted_rows.append(accepted.copy())
            return False

        s.step = native_step
        r.command_positions = lambda row: row.copy()

        def solve(side, goal, seed):
            q = seed.copy()
            q[:3] = goal[0]
            return q

        r.ik = SimpleNamespace(solve=solve, gripper_table_clearance=Mock(
            side_effect=AssertionError('extra oracle table gate must not run with native R4')))
        r.task = SimpleNamespace(result=SimpleNamespace(metrics={}, terminated=False))
        r.log, r.grasps = [{}], {}
        # Native R4 allows this target; the additional +0.5 mm oracle gate did not.
        r.q['left'] = r.solve('left', [0, 0, -.010], None)
        self.assertAlmostEqual(r.q['left'][2], -.010)
        r.step('test')
        self.assertAlmostEqual(accepted_rows[-1][2], -.010, places=7)
        self.assertEqual(guard.count, 0)
        # Below native R4, let its real implementation clip the commanded path.
        r.q['left'] = r.solve('left', [0, 0, -.025], None)
        r.step('test')
        self.assertEqual(guard.count, 1)
        self.assertAlmostEqual(accepted_rows[-1][2], tooling.TABLE_GUARD_MARGIN_M, delta=1e-5)
        np.testing.assert_array_equal(r.full_q, accepted_rows[-1])
        np.testing.assert_array_equal(r.q['left'], accepted_rows[-1][:6])
        self.assertEqual(r.g['left'], accepted_rows[-1][6])
        r.ik.gripper_table_clearance.assert_not_called()

    def test_withdrawal_height_does_not_accumulate_segment_tracking_error(self):
        r = Runner.__new__(Runner)
        points = {'right': np.array([-.2, 0., .1]), 'left': np.array([.2, 0., .1])}
        r.args = SimpleNamespace(max_pull=.15, full_pull=True, speed=.04)
        r.log = [dict(t=0.)]; r.grasps = {}; r.arms_for = lambda _: ('right', 'left')
        r.crossings = lambda: [1]; r.tcp = lambda side: points[side].copy()
        r.contact_point = r.tcp; r.release = Mock()
        def grasp(sides, stations, phase):
            r.grasps = {side: dict(s=s, turn=None) for side, s in zip(sides, stations)}
            return []
        r.grasp = grasp; r.smooth = lambda a, b, speed: [b.copy()]
        pulls = []
        def move(side, targets, turn, phase, **kwargs):
            if phase.endswith(':pull'): pulls.append(targets[-1].copy())
            points[side] = targets[-1]-[0, 0, .003]  # measured lag after every segment
            r.log.append(dict(t=len(r.log)*.025))
            return True
        r.cartesian = move
        r.withdraw(1, dict(s_anchor=.015, s_pull=1.1, direction=[1., 0.]), dict(lift=.03))
        self.assertEqual(len(pulls), 3)
        np.testing.assert_allclose(np.asarray(pulls)[:, 2], .13)

    def test_spread_finishes_both_unequal_paths_and_preserves_planned_height(self):
        r = Runner.__new__(Runner)
        points = {'left': np.array([-.3, 0., .1]), 'right': np.array([.3, 0., .1])}
        r.length = 1.3; r.args = SimpleNamespace(end_offset=.035, speed=.04)
        r.q = {side: p.copy() for side, p in points.items()}; r.log = [dict(t=0.)]
        r.arms_for = lambda _: ('left', 'right'); r.crossings = lambda: []
        r.tcp = lambda side: points[side].copy(); r.contact_point = r.tcp; r.release = Mock()
        def grasp(sides, stations, phase):
            r.grasps = {side: dict(s=s, turn=None) for side, s in zip(sides, stations)}
            return []
        r.grasp = grasp
        def smooth(a, b, speed):
            return np.linspace(a, b, (3 if b[0] < 0 else 4))[1:]
        r.smooth = smooth
        def move(side, path, turn, phase):
            points[side] = path[-1]-[0, 0, .003 if side == 'left' else .008]
            r.q[side] = points[side].copy()
        r.cartesian = move; r.solve = lambda side, p, turn: p.copy()
        commands = []
        def step(phase):
            commands.append({side: q.copy() for side, q in r.q.items()})
            for side, q in r.q.items(): points[side] = q-[0, 0, .003 if side == 'left' else .008]
            r.log.append(dict(t=len(r.log)*.025))
        r.step = step
        r.straighten(2, dict(straighten=.9))
        self.assertEqual(len(commands), 6)  # two complete 3-step pairs, not two truncated pairs
        for index in (2, 5):
            for side in points: self.assertAlmostEqual(commands[index][side][2], .115)


if __name__ == '__main__':
    unittest.main()
