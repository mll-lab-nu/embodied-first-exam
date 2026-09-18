"""Check bounded grasp IK and camera setup without running FEM dynamics."""
from argparse import Namespace
from types import SimpleNamespace
import unittest
from unittest import mock

import mujoco
import numpy as np
from scipy.spatial.transform import Rotation

from topogym.robot.assets import robot_asset
from topogym.tasks.knot_untying.control import BoundedAlohaIK
from topogym.tasks.knot_untying.geometry import KnotLayout
from topogym.tasks.knot_untying.physics_probe import make_config
from topogym.tasks.knot_untying.recording import configure_cameras
from topogym.tasks.knot_untying.untying import RobotUntyingActions


class KnotRobotControlChecks(unittest.TestCase):
    def setUp(self):
        self.cfg = make_config(Namespace(robot='aloha', dt=.005, x_offset=0., yaw=0.,
                                         refined=False, tighter=False, friction_eps=.001))
        model = mujoco.MjModel.from_xml_path(robot_asset(self.cfg.robot_control))
        data = mujoco.MjData(model)
        for side in ('left', 'right'):
            indices = [int(model.joint(f'{side}/{name}').qposadr[0])
                       for name in self.cfg.robot_control.robot.arm_joint_names]
            data.qpos[indices] = self.cfg.robot_control.home[side][:6]
        mujoco.mj_forward(model, data)
        mount = np.asarray(self.cfg.env.robot_mount.pos)
        arms = {}
        for side in ('left', 'right'):
            body = model.body(f'{side}/gripper_link').id
            pos = data.xpos[body].copy()+mount
            quat = Rotation.from_matrix(data.xmat[body].reshape(3, 3)).as_quat()[[3, 0, 1, 2]]
            q = np.asarray(self.cfg.robot_control.home[side][:6])
            arms[side] = SimpleNamespace(hand_pos=lambda p=pos: p, hand_quat=lambda r=quat: r,
                                         arm_qpos=lambda angles=q: angles)
        controller = SimpleNamespace(cfg=self.cfg.robot_control, arms=arms, left=arms['left'])
        self.ik = BoundedAlohaIK(None, controller)

    def test_tail_hover_has_an_interior_joint_solution(self):
        target = np.array([-.13877, .04895, 1.1173])
        quat = np.array([.63645, -.30811, .63645, .30811])
        q = self.ik.solve('left', target, quat)
        self.assertGreater(float(np.minimum(q-self.ik.limits[:, 0], self.ik.limits[:, 1]-q).min()), .01)
        position, _ = self.ik.pose('left', q)
        self.assertLess(np.linalg.norm(position-target), .0002)

    def test_unreachable_target_is_rejected(self):
        with self.assertRaisesRegex(ValueError, 'Unreachable'):
            self.ik.solve('left', np.array([5., 0., 2.]), np.array([1., 0., 0., 0.]))

    def test_changed_joint_reference_is_rejected(self):
        controller = self.ik.controller
        position = controller.arms['right'].hand_pos().copy()
        controller.arms['right'].hand_pos = lambda: position+np.array([.01, 0., 0.])
        with self.assertRaisesRegex(ValueError, 'joint references'):
            BoundedAlohaIK(None, controller)

    def test_recording_has_shared_wrist_views_and_knot_detail(self):
        configure_cameras(self.cfg, (640, 360))
        self.assertEqual(set(self.cfg.env.cameras),
                         {'cam_high', 'cam_low', 'cam_left_wrist', 'cam_right_wrist', 'detail'})
        self.assertEqual(self.cfg.env.cameras.cam_left_wrist.attach.link, 'left/gripper_base')
        self.assertEqual(self.cfg.env.cameras.cam_right_wrist.attach.link, 'right/gripper_base')

    def test_understrand_route_rotates_with_the_layout(self):
        original = RobotUntyingActions(route='understrand')
        turned = RobotUntyingActions(route='understrand', yaw_deg=180.)
        np.testing.assert_allclose(turned.pull_direction, -original.pull_direction, atol=1e-12)
        self.assertAlmostEqual(np.linalg.norm(turned.pull_direction), 1.)
        self.assertGreater(turned.pull_direction[0], 0.)
        self.assertLess(turned.pull_direction[1], 0.)
        self.assertGreater(turned.left_withdraw[2], 0.)
        np.testing.assert_array_equal(RobotUntyingActions().pull_direction, [-1., 0., 0.])

    def test_unknown_untying_route_is_rejected(self):
        with self.assertRaisesRegex(ValueError, 'Unknown untying route'):
            RobotUntyingActions(route='unknown')

    def test_adaptive_pull_finishes_without_extra_motion_when_clear(self):
        actions = RobotUntyingActions(route='remote_adaptive')
        actions.monitor = SimpleNamespace(last_centers=np.array([[0., 0., 0.], [1., 0., 0.]]))
        self.assertAlmostEqual(actions.draw_distance(40.), .45)
        self.assertEqual(actions.pull_end, 40.)
        self.assertFalse(actions.finished(50.995))
        self.assertTrue(actions.finished(51.))

    def test_adaptive_pull_completes_a_stroke_before_stopping(self):
        actions = RobotUntyingActions(route='remote_adaptive')
        actions.monitor = SimpleNamespace(last_centers=KnotLayout().centerline())
        self.assertAlmostEqual(actions.draw_distance(40.), .45)
        actions.monitor.last_centers = np.array([[0., 0., 0.], [1., 0., 0.]])
        self.assertAlmostEqual(actions.draw_distance(41.5), .4625)
        self.assertIsNone(actions.pull_end)
        self.assertAlmostEqual(actions.draw_distance(43.), .475)
        self.assertEqual(actions.pull_end, 43.)
        self.assertTrue(actions.finished(54.))

    def test_adaptive_pull_has_a_finite_distance_cap(self):
        actions = RobotUntyingActions(route='remote_adaptive')
        actions.monitor = SimpleNamespace(last_centers=KnotLayout().centerline())
        distances = [actions.draw_distance(t) for t in np.arange(40., 52.005, .005)]
        self.assertLessEqual(max(distances), .55+1e-9)
        self.assertGreaterEqual(min(np.diff(distances)), -1e-12)
        self.assertAlmostEqual(actions.pull_end, 52., places=8)
        self.assertEqual(actions.events[-1]['reason'], 'distance_cap')
        self.assertTrue(actions.finished(63.))

    def spread_actions(self, **kwargs):
        actions = RobotUntyingActions(route='remote_adaptive_spread', **kwargs)
        actions.monitor = SimpleNamespace(last_centers=KnotLayout().centerline())
        quat = np.array([1., 0., 0., 0.])
        actions.motion = {'left': (np.array([-.08, .25, .923]), quat),
                          'right': (np.array([-.25, .045, .923]), quat)}
        actions.grasp_material_length_m = .81
        return actions

    def test_residual_loop_spread_is_bounded_and_keeps_release_window(self):
        actions = self.spread_actions()
        for t in (40., 43., 46., 49., 52.):
            actions.draw_distance(t)
        self.assertIsNone(actions.pull_end)
        self.assertEqual(actions.spread_start, 52.)
        self.assertLessEqual(actions.right_spread_m, .4)
        np.testing.assert_array_equal(actions.right_displacement(52.), [0., 0., 0.])
        self.assertAlmostEqual(actions.right_displacement(62.)[0], actions.right_spread_m/2)
        left = actions.motion['left'][0]+[-.55, 0, .015]
        right = actions.motion['right'][0]+actions.right_displacement(72.)
        self.assertAlmostEqual(np.linalg.norm(left-right), .78)
        actions.draw_distance(71.995)
        self.assertIsNone(actions.pull_end)
        actions.draw_distance(72.)
        self.assertEqual(actions.pull_end, 72.)
        self.assertFalse(actions.finished(82.995))
        self.assertTrue(actions.finished(83.))

    def test_spread_does_not_snap_support_back_when_releasing(self):
        actions = self.spread_actions()
        for t in (40., 43., 46., 49., 52., 72.):
            actions.draw_distance(t)
        with mock.patch.object(actions, 'move') as move, mock.patch.object(actions, 'release'):
            actions.update(78.)
        right_targets = [args[1] for args, _ in move.call_args_list if args[0] == 'right']
        self.assertEqual(len(right_targets), 1)
        np.testing.assert_allclose(right_targets[0], actions.motion['right'][0]+
                                   [actions.right_spread_m+.05, 0, .08])

    def test_spread_rejects_a_target_with_insufficient_material_slack(self):
        actions = self.spread_actions()
        actions.grasp_material_length_m = .75
        for t in (40., 43., 46., 49.):
            actions.draw_distance(t)
        with self.assertRaisesRegex(RuntimeError, 'material slack'):
            actions.draw_distance(52.)

    def test_clear_rope_skips_the_optional_spread(self):
        actions = self.spread_actions()
        actions.monitor.last_centers = np.array([[0., 0., 0.], [1., 0., 0.]])
        actions.draw_distance(40.)
        self.assertIsNone(actions.spread_start)
        self.assertTrue(actions.finished(51.))

    def test_shorter_spread_retains_speed_bound_and_full_release_window(self):
        actions = self.spread_actions(spread_span_m=.65, spread_duration_s=12.)
        for t in (40., 43., 46., 49., 52., 64.):
            actions.draw_distance(t)
        left = actions.motion['left'][0]+[-.55, 0, .015]
        right = actions.motion['right'][0]+actions.right_displacement(64.)
        self.assertAlmostEqual(np.linalg.norm(left-right), .65)
        self.assertLessEqual(1.5*actions.right_spread_m/12., .03)
        self.assertEqual(actions.pull_end, 64.)
        self.assertEqual(actions.specification()['duration_s'], 75.)
        self.assertFalse(actions.finished(74.995))
        self.assertTrue(actions.finished(75.))
        np.testing.assert_array_equal(actions.right_displacement(75.), actions.right_displacement(64.))

    def test_spread_rejects_motion_above_existing_speed_limit(self):
        actions = self.spread_actions(spread_duration_s=2.)
        for t in (40., 43., 46., 49.):
            actions.draw_distance(t)
        with self.assertRaisesRegex(RuntimeError, 'speed limit'):
            actions.draw_distance(52.)

    def test_spread_parameters_must_be_finite_and_positive(self):
        for field in ('spread_span_m', 'spread_duration_s'):
            for value in (0., -1., float('nan'), float('inf')):
                with self.subTest(field=field, value=value), self.assertRaisesRegex(ValueError, 'finite and positive'):
                    RobotUntyingActions(**{field: value})


if __name__ == '__main__':
    unittest.main()
