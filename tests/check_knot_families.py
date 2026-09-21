"""Fixed family identity, geometry safety, and reproducible config checks."""
from argparse import Namespace
from copy import deepcopy
from dataclasses import replace
import json
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch

import numpy as np
from omegaconf import OmegaConf
import trimesh

from topogym.tasks.knot_untying.geometry import (
    FAMILY_KNOTS, KnotLayout, generate_assets, inspect_geometry, projected_crossings,
    template_diagram_matches,
)
from topogym.tasks.knot_untying.physics_probe import make_config
from topogym.tasks.knot_untying.family_actions import (
    FamilyUntyingActions, ROUTES, first_under_grasp, material_arc,
    initial_grasp_sites, route_for_config, support_material_site,
)


def config(family, seed=None, profile=None):
    return make_config(Namespace(family=family, appearance_seed=seed, route_profile=profile, dt=.005,
        x_offset=0., y_offset=0., yaw=0., refined=False, tighter=False, friction_eps=.001))


class KnotFamilyChecks(unittest.TestCase):
    def test_observed_pitched_regrasp_avoids_robot_and_table(self):
        from topogym.tasks.knot_untying.control import BoundedAlohaIK
        from topogym.tasks.knot_untying.robot_clearance import checked_grasp_approach
        fixtures = json.loads((Path(__file__).parent/'fixtures/knot_observed_regrasps.json').read_text())
        for fixture in fixtures:
            with self.subTest(family=fixture['family']):
                cfg = make_config(Namespace(family=fixture['family'], route_profile=fixture['profile'],
                    robot='aloha', robot_coupling='external_articulation', dt=.005, x_offset=0., y_offset=0.,
                    yaw=0., refined=False, tighter=False, friction_eps=.001))
                cfg.robot_control.home = fixture['home']
                states = fixture['robot']
                arms = {side: SimpleNamespace(
                    arm_qpos=lambda s=s: np.array(s['arm_qpos']),
                    gripper_qpos=lambda s=s: np.array(s['finger_qpos']),
                    hand_pos=lambda s=s: np.array(s['hand_pos']),
                    hand_quat=lambda s=s: np.array(s['hand_quat_wxyz'])) for side, s in states.items()}
                controller = SimpleNamespace(cfg=cfg.robot_control, arms=arms, left=arms['left'])
                actions = FamilyUntyingActions(cfg)
                actions.controller, actions.ik = controller, BoundedAlohaIK(None, controller)
                actions.regrasps, actions.approaches = 1, {}
                actions.monitor = SimpleNamespace(last_centers=None, floor=fixture['floor_height_m'],
                    count=round(fixture['source_time_s']/.005), dt=.005)
                candidates = {c['band']: c for c in fixture['candidates']}
                actions.arc = np.zeros(max(candidates)+1)
                actions.ring_indices = list(range(len(actions.arc)))
                sign = 1 if actions.route.working_end == 0 else -1
                for band, c in candidates.items():
                    actions.arc[band] = fixture['under_arc_m']+sign*c['inward_margin_m']
                choices = sorted((abs(c['inward_margin_m']-.025), band) for band, c in candidates.items())
                actions._pull_band_candidates = Mock(return_value=choices)
                actions.band_pose = lambda band, side: (np.array(candidates[band]['point_m']),
                                                         np.array(candidates[band]['quat_wxyz']))
                support = fixture['support_band']
                actions.pull_band, actions.support_band = choices[0][1], support
                actions.owners = {support: 'right'}
                original_joints = {side: arm.arm_qpos() for side, arm in arms.items()}
                with patch('topogym.tasks.knot_untying.family_actions.first_under_grasp',
                           return_value=fixture['under_arc_m']+sign*.025):
                    actions._prepare_grasp('left')
                self.assertEqual(actions.pull_band, fixture['expected_selected_band'])
                selected = next(e for e in actions.events if e['event'] == 'observed_regrasp_candidate_selected')
                self.assertEqual(selected['pitch_deg'], fixture['expected_pitch_deg'])
                self.assertEqual(actions.grasp_hover_height, fixture['expected_hover_m'])
                self.assertEqual(actions.owners, {support: 'right'})
                for side, arm in arms.items():
                    np.testing.assert_array_equal(arm.arm_qpos(), original_joints[side])
                # This same reachable grasp, lowered through the table, must be
                # rejected before any command or grasp ownership is changed.
                if fixture['family'] == 'figure_eight':
                    point, quat = actions.grasp_target
                    with self.assertRaisesRegex(ValueError, 'table clearance'):
                        checked_grasp_approach(actions.ik, controller, 'left', point-[0., 0., .004], quat, .018,
                                               floor_height_m=actions.monitor.floor)

    def test_opening_clearance_shift_retains_anchor_until_completion(self):
        actions = FamilyUntyingActions(config('double_overhand',
            profile='double_overhand_support_shift_checked_v7'))
        actions.arc = np.array([0., 1.])
        actions.ring_indices, actions.pull_band, actions.support_band = [0, 1], 0, 1
        actions.owners = {0: 'left', 1: 'right'}
        quat = np.array([1., 0., 0., 0.])
        actions.motion = {'left': (np.array([0., 0., .94]), quat),
                          'right': (np.array([.2, 0., 1.08]), quat)}
        actions.ik = SimpleNamespace(previous={'right': np.zeros(6)}, solve=Mock())
        actions._pull_band_candidates = Mock(return_value=[(.003, 8)])
        actions.release = Mock()
        actions._record_motion = Mock()
        actions._transition = Mock()
        actions._finish_or_extend_opening(46.2)
        actions.release.assert_not_called()
        self.assertEqual(actions.owners, {0: 'left', 1: 'right'})
        np.testing.assert_allclose(actions.phase_targets['right'][1], [.32, 0., 1.08])
        self.assertEqual(actions._transition.call_args.args[0], 'open_upper_clearance_shift')
        actions.arc = np.array([0., .3])
        with self.assertRaisesRegex(RuntimeError, 'exhaust anchored material slack'):
            actions._finish_or_extend_opening(46.2)
        actions.arc = np.array([0., 1.])
        del actions.owners[0]
        with self.assertRaisesRegex(RuntimeError, 'both physical grasps'):
            actions._finish_or_extend_opening(46.2)
        actions.owners[0] = 'left'
        actions.opening_clearance_shift_completed = True
        actions._finish_or_extend_opening(53.4)
        actions.release.assert_called_once_with('left', 53.4)

    def test_support_spread_keeps_grasps_and_rejects_exhausted_slack(self):
        actions = FamilyUntyingActions(config('figure_eight', profile='figure8_support_spread_checked_v5'))
        actions.arc = np.array([0., .6])
        actions.ring_indices, actions.pull_band, actions.support_band = [0, 1], 0, 1
        actions.owners = {0: 'left', 1: 'right'}
        quat = np.array([1., 0., 0., 0.])
        actions.motion = {'left': (np.array([0., 0., .94]), quat),
                          'right': (np.array([.25, 0., .94]), quat)}
        actions.draw_tool_height = actions.support_hold_height = .943
        actions._record_motion = Mock()
        actions._transition = Mock()
        actions.release = Mock()
        actions.ik = SimpleNamespace(previous={'right': np.zeros(6)}, solve=Mock())
        actions._begin_regrasp(54., 'strokes_per_grasp')
        actions.release.assert_not_called()
        self.assertEqual(actions.owners, {0: 'left', 1: 'right'})
        self.assertEqual(actions.regrasps, 0)
        np.testing.assert_allclose(actions.phase_targets['right'][1], [.40, 0., .943])
        self.assertAlmostEqual(actions.motion['left'][0][2], .943)
        self.assertEqual(actions._transition.call_args.args[0], 'spread_before_regrasp')
        actions.arc = np.array([0., .35])
        actions._transition.reset_mock()
        with self.assertRaisesRegex(RuntimeError, 'exhaust material slack'):
            actions._begin_regrasp(54., 'strokes_per_grasp')
        actions.release.assert_not_called()
        actions._transition.assert_not_called()

    def test_higher_checked_hover_preserves_cartesian_speed_bound(self):
        actions = FamilyUntyingActions(config('figure_eight', profile='figure8_support_spread_checked_v5'))
        actions.phase, actions.grasp_hover_height = 'left_approach', .08
        actions._transition = Mock()
        actions._advance(70.)
        phase, duration, _ = actions._transition.call_args.args
        self.assertEqual(phase, 'left_lower')
        self.assertLessEqual(1.5*.08/duration+.006, .03000001)

    def test_measured_robot_overlap_detects_recorded_gripper_base_collision(self):
        import mujoco
        from scipy.spatial.transform import Rotation
        from topogym.robot.assets import robot_asset
        from topogym.tasks.knot_untying.control import BoundedAlohaIK
        from topogym.tasks.knot_untying.robot_clearance import (
            checked_grasp_approach, measured_robot_overlap,
        )
        from topogym.tasks.knot_untying.robot_probe import TOOL_OFFSET
        cfg = make_config(Namespace(family='figure_eight', route_profile='figure8_support_spread_checked_v5',
            robot='aloha', robot_coupling='external_articulation', dt=.005, x_offset=0., y_offset=0.,
            yaw=0., refined=False, tighter=False, friction_eps=.001))
        model = mujoco.MjModel.from_xml_path(robot_asset(cfg.robot_control))
        data = mujoco.MjData(model)
        # Actual v6 joints at 61.21 s: the two gripper bases overlap despite
        # valid arm limits. This fixture needs no native physics/GPU or run files.
        joints = {
            'left': [0.8455047011, 0.5356491208, -0.2083897293, -0.0000597850,
                     1.2479164600, 2.3432438374, 0.0180006158, 0.0180014633],
            'right': [-0.6680212617, 0.7884669900, -0.5555825830, 0.0001257739,
                      1.3429208994, -0.2771850526, 0.0128554273, 0.0128552821],
        }
        names = list(cfg.robot_control.robot.arm_joint_names)+list(cfg.robot_control.robot.finger_joint_names)
        for side, values in joints.items():
            for name, value in zip(names, values):
                data.qpos[model.joint(f'{side}/{name}').qposadr[0]] = value
        mujoco.mj_forward(model, data)
        arms = {}
        for side, values in joints.items():
            body = model.body(f'{side}/gripper_link').id
            p = data.xpos[body].copy()
            q = Rotation.from_matrix(data.xmat[body].reshape(3, 3)).as_quat()[[3, 0, 1, 2]]
            arms[side] = SimpleNamespace(arm_qpos=lambda values=values: np.array(values[:6]),
                gripper_qpos=lambda values=values: np.array(values[6:]),
                hand_pos=lambda p=p: p, hand_quat=lambda q=q: q)
        controller = SimpleNamespace(cfg=cfg.robot_control, arms=arms, left=arms['left'])
        ik = BoundedAlohaIK(None, controller)
        overlap = measured_robot_overlap(ik, controller)
        self.assertAlmostEqual(overlap['penetration_m'], .00103895748, places=7)
        self.assertEqual(set(overlap['bodies']), {'left/gripper_base', 'right/gripper_base'})
        old_previous = {s: q.copy() for s, q in ik.previous.items()}
        old_data, old_margins = ik.data.qpos.copy(), ik.model.geom_margin.copy()
        quat = arms['left'].hand_quat()
        target = arms['left'].hand_pos()+Rotation.from_quat(quat[[1, 2, 3, 0]]).apply(TOOL_OFFSET)
        with self.assertRaisesRegex(ValueError, 'No robot-clear regrasp approach'):
            checked_grasp_approach(ik, controller, 'left', target, quat, .018)
        np.testing.assert_array_equal(ik.data.qpos, old_data)
        np.testing.assert_array_equal(ik.model.geom_margin, old_margins)
        for side in old_previous:
            np.testing.assert_array_equal(ik.previous[side], old_previous[side])

    def test_regrasp_tracking_is_bounded_and_stops_on_physical_contact(self):
        actions = FamilyUntyingActions(config('figure_eight', profile='figure8_local_curve_tracking_v4'))
        actions.regrasps, actions.pull_band = 1, 0
        actions.bands = [SimpleNamespace(indices=np.array([0]))]
        positions = np.array([[.001, 0., .927]])
        actions.monitor = SimpleNamespace(last_positions=positions)
        quat = np.array([1., 0., 0., 0.])
        origin = np.array([0., 0., .93])
        actions.grasp_target, actions.grasp_target_origin = (origin.copy(), quat), origin.copy()
        actions.grasp_tracking_last_time = 64.
        actions._track_regrasp_translation('left', 64.1)
        self.assertAlmostEqual(np.linalg.norm(actions.grasp_target[0]-origin), .0006)
        np.testing.assert_array_equal(actions.monitor.last_positions, [[.001, 0., .927]])
        np.testing.assert_array_equal(actions.grasp_target[1], quat)
        self.assertFalse(actions.owners)
        tracked = actions.grasp_target[0].copy()
        actions.owners[0] = 'left'
        actions._track_regrasp_translation('left', 64.2)
        np.testing.assert_array_equal(actions.grasp_target[0], tracked)
        actions.owners.clear()
        actions.monitor.last_positions = np.array([[.02, 0., .93]])
        with self.assertRaisesRegex(RuntimeError, '10 mm tracking envelope'):
            actions._track_regrasp_translation('left', 64.3)
        np.testing.assert_array_equal(actions.grasp_target[0], tracked)

    def test_opening_extension_keeps_anchor_and_enforces_lift_budget(self):
        actions = FamilyUntyingActions(config('double_overhand', profile='double_overhand_anchored_clearance_v5'))
        actions.arc = np.array([0., 1.])
        actions.ring_indices, actions.pull_band, actions.support_band = [0, 1], 0, 1
        actions.owners = {0: 'left', 1: 'right'}
        quat = np.array([1., 0., 0., 0.])
        actions.motion = {'left': (np.array([0., 0., .94]), quat),
                          'right': (np.array([.2, 0., 1.]), quat)}
        actions.ik = SimpleNamespace(previous={'right': np.zeros(6)}, solve=Mock())
        actions._pull_band_candidates = Mock(return_value=[])
        actions.release = Mock()
        actions._record_motion = Mock()
        actions._transition = Mock()
        actions._finish_or_extend_opening(38.2)
        actions.release.assert_not_called()
        self.assertEqual(actions.pull_band, 0)
        self.assertEqual(actions.owners, {0: 'left', 1: 'right'})
        actions._pull_band_candidates.assert_called_with(minimum_separation_m=.14)
        actions._transition.assert_called_with('open_upper_clearance', 2., 38.2)
        self.assertAlmostEqual(actions.phase_targets['right'][1][2], 1.02)
        self.assertAlmostEqual(actions.opening_extra_lift, .02)
        actions.opening_extra_lift = .08
        with self.assertRaisesRegex(RuntimeError, 'budget exhausted'):
            actions._finish_or_extend_opening(46.2)
        actions.release.assert_not_called()
        actions._pull_band_candidates.return_value = [(.003, 8)]
        actions._finish_or_extend_opening(46.2)
        actions.release.assert_called_once_with('left', 46.2)
        self.assertEqual(actions.regrasps, 1)
        self.assertEqual(actions._transition.call_args.args[0], 'anchor_regrasp_raise')

    def test_completed_extra_lift_retains_its_new_height(self):
        actions = FamilyUntyingActions(config('double_overhand', profile='double_overhand_anchored_clearance_v5'))
        quat = np.array([1., 0., 0., 0.])
        start, end = np.array([.2, 0., 1.]), np.array([.2, 0., 1.02])
        actions.motion = {'right': (end-np.array([0., 0., .0002]), quat)}
        actions.phase_targets['right'] = (start, end, quat)
        actions.support_hold_height = 1.
        actions.phase = 'open_upper_clearance'
        actions._record_motion = Mock()
        actions._check_support_clearance = Mock()
        actions._finish_or_extend_opening = Mock()
        actions._advance(40.2)
        self.assertAlmostEqual(actions.support_hold_height, 1.02)
        self.assertAlmostEqual(actions.motion['right'][0][2], 1.02)
        actions._finish_or_extend_opening.assert_called_once_with(40.2)

    def test_regrasp_when_held_material_is_outside_the_next_underpass(self):
        for family, held, before, after in [('double_overhand', .33, .325, .525),
                                          ('figure_eight', .70, .725, .475)]:
            actions = FamilyUntyingActions(config(family))
            actions.arc = np.array([0., held, 1.])
            actions.ring_indices, actions.pull_band = [1], 0
            actions.monitor = SimpleNamespace(last_centers=np.zeros((3, 3)))
            with patch('topogym.tasks.knot_untying.family_actions.first_under_grasp', return_value=before):
                self.assertFalse(actions._held_band_reached_underpass())
            with patch('topogym.tasks.knot_untying.family_actions.first_under_grasp', return_value=after):
                self.assertTrue(actions._held_band_reached_underpass())

    def test_adaptive_regrasp_does_not_commit_a_stroke_beyond_material_slack(self):
        actions = FamilyUntyingActions(config('double_overhand', profile='double_overhand_anchored_adaptive_v4'))
        actions.arc = np.array([0., .5, 1.])
        actions.ring_indices, actions.pull_band, actions.support_band = [1, 0], 0, 1
        actions.bands = [SimpleNamespace(indices=np.array([0]))]
        actions.monitor = SimpleNamespace(floor=.92, last_positions=np.array([[.5, 0., .936]]),
            last_centers=np.array([[0., 0., .93], [.5, 0., .93], [.7, 0., .93]]))
        quat = np.array([1., 0., 0., 0.])
        actions.motion = {'left': (np.array([.5, 0., .94]), quat),
                          'right': (np.array([0., 0., .94]), quat)}
        actions.strokes_at_grasp = 1
        actions.draw_direction = np.array([1., 0., 0.])
        actions._record_motion = Mock()
        actions._transition = Mock()
        actions.ik = SimpleNamespace(previous={'left': np.zeros(6)}, solve=Mock())
        self.assertFalse(actions._start_draw(40.))
        actions._transition.assert_not_called()
        actions.ik.solve.assert_not_called()
        self.assertFalse(actions.phase_targets)
        actions.route = replace(actions.route, regrasp_on_material_limits=False)
        with self.assertRaisesRegex(RuntimeError, 'available material slack'):
            actions._start_draw(40.)
        actions._transition.assert_not_called()

    def test_opening_releases_tail_before_planning_understrand_regrasp(self):
        actions = FamilyUntyingActions(config('double_overhand', profile='double_overhand_anchored_open_v3'))
        actions.pull_band, actions.support_band = 0, 1
        actions.owners = {0: 'left', 1: 'right'}
        actions.bands = [SimpleNamespace(release=Mock()), SimpleNamespace(release=Mock())]
        arm = SimpleNamespace(set_gripper=Mock())
        actions.controller = SimpleNamespace(arms={'left': arm})
        actions.motion = {'right': (np.array([0., .2, .99]), np.array([1., 0., 0., 0.]))}
        actions.phase = 'open_upper_shift'
        actions._record_motion = Mock()
        actions._transition = Mock()
        actions._choose_pull_band = Mock(return_value=True)
        actions._prepare_grasp = Mock()
        actions._advance(37.)
        actions.bands[0].release.assert_called_once()
        actions.bands[1].release.assert_not_called()
        self.assertEqual(actions.owners, {1: 'right'})
        arm.set_gripper.assert_called_with(.018)
        self.assertEqual(actions.regrasps, 1)
        self.assertEqual(actions._transition.call_args.args[0], 'anchor_regrasp_raise')
        actions._choose_pull_band.assert_not_called()
        actions.phase = 'anchor_regrasp_raise'
        actions._advance(43.)
        actions._choose_pull_band.assert_called_once()
        actions._prepare_grasp.assert_called_with('left')
        actions._transition.assert_called_with('left_approach', 3., 43.)

    def test_upper_opening_requires_a_physical_tail_anchor(self):
        cfg = config('double_overhand', profile='double_overhand_anchored_open_v3')
        points, arc, indices = initial_grasp_sites(cfg)
        self.assertLess(abs(arc[indices[0]]-.015), .003)
        hits = projected_crossings(points)
        crossings = []
        for hit in hits:
            under = 1 if hit['first_over'] else 0
            ss = [arc[i]+u*(arc[i+1]-arc[i]) for i, u in zip(hit['segments'], hit['parameters'])]
            crossings.append((ss[under], ss[1-under]))
        self.assertLess(abs(arc[indices[1]]-min(crossings)[1]), .003)
        actions = FamilyUntyingActions(cfg)
        actions.pull_band, actions.support_band = 0, 1
        actions.phase = 'left_close'
        actions._record_motion = Mock()
        actions._transition = Mock()
        with self.assertRaisesRegex(RuntimeError, 'both-finger contact'):
            actions._advance(17.)
        actions.owners[0] = 'left'
        actions._advance(17.)
        actions._transition.assert_called_with('anchor_lift', 3., 17.)
        actions.phase = 'anchor_lift'
        actions.bands = [SimpleNamespace(indices=np.array([0]))]
        actions.monitor = SimpleNamespace(floor=.92, last_positions=np.array([[0., 0., .921]]))
        actions._prepare_grasp = Mock()
        with self.assertRaisesRegex(RuntimeError, 'against the table'):
            actions._advance(20.)
        actions._prepare_grasp.assert_not_called()

    def test_switching_family_clears_previous_profile_and_seed(self):
        from topogym.tasks.knot_untying.families import apply_family
        cfg = config('figure_eight', seed=17, profile='figure8_local_curve_narrow_v3')
        apply_family(cfg, 'double_overhand')
        fresh = config('double_overhand')
        self.assertEqual(cfg.task.geometry, fresh.task.geometry)
        self.assertEqual(cfg.task.appearance, fresh.task.appearance)
        self.assertEqual(route_for_config(cfg), route_for_config(fresh))
        self.assertNotIn('route_profile', cfg.task)
        apply_family(cfg, 'double_overhand', route_profile='double_overhand_narrow_v2')
        self.assertEqual(cfg.task.geometry, fresh.task.geometry)
        self.assertEqual(cfg.task.rope, fresh.task.rope)
        self.assertEqual(route_for_config(cfg).approach_finger_qpos_m, .018)

    def test_narrow_approach_does_not_reopen_or_bypass_two_finger_contact(self):
        cfg = config('figure_eight', profile='figure8_local_curve_narrow_v3')
        actions = FamilyUntyingActions(cfg)
        arm = SimpleNamespace(set_gripper=Mock(), hand_pos=lambda: np.zeros(3),
            hand_quat=lambda: np.array([1., 0., 0., 0.]), gripper_qpos=lambda: np.array([.013, .013]))
        actions.controller = SimpleNamespace(arms={'left': arm})
        band = SimpleNamespace(indices=np.array([0, 1]), active=False, _handle=SimpleNamespace(engage=Mock()))
        actions.bands = [band]
        actions.monitor = SimpleNamespace(last_positions=np.zeros((2, 3)))
        actions.contact_distance = .0008
        actions.gaps = Mock(return_value=np.array([np.inf, .0007]))
        actions.close('left', 0, 2., 2., start_qpos=actions.route.approach_finger_qpos_m)
        arm.set_gripper.assert_called_with(.018)
        band._handle.engage.assert_not_called()
        self.assertFalse(actions.owners)
        actions.gaps.return_value = np.array([.0007, .0007])
        actions.close('left', 0, 2.1, 2., start_qpos=actions.route.approach_finger_qpos_m)
        band._handle.engage.assert_called_once()
        self.assertEqual(actions.owners, {0: 'left'})
        arm.set_gripper.assert_called_with(.013)

    def test_local_support_profile_preserves_family_and_material(self):
        base = config('figure_eight')
        cfg = config('figure_eight', profile='figure8_local_curve_v2')
        narrow = config('figure_eight', profile='figure8_local_curve_narrow_v3')
        self.assertEqual(cfg.task.geometry, narrow.task.geometry)
        self.assertEqual(cfg.task.rope, narrow.task.rope)
        self.assertEqual(cfg.task.rope, base.task.rope)
        self.assertNotEqual(cfg.task.variant, base.task.variant)
        layout = KnotLayout(**OmegaConf.to_container(cfg.task.geometry, resolve=True))
        self.assertTrue(inspect_geometry(layout.centerline(), layout)['knot_diagram_verified'])
        points, arc, indices = initial_grasp_sites(cfg)
        target, bounds = support_material_site(points, arc, route_for_config(cfg))
        self.assertTrue(bounds[0] < arc[indices[1]] < bounds[1])
        self.assertLess(abs(arc[indices[1]]-target), .003)
        self.assertGreater(np.linalg.norm(points[indices[0]]-points[indices[1]]), .15)
        with self.assertRaisesRegex(ValueError, 'not registered'):
            config('double_overhand', profile='figure8_local_curve_v2')

    def test_late_underpass_in_free_tail_can_be_regrasped(self):
        cfg = config('figure_eight')
        actions = FamilyUntyingActions(cfg)
        points = KnotLayout(**OmegaConf.to_container(cfg.task.geometry, resolve=True)).centerline()

        def attachment(rope, center, **kwargs):
            index = int(np.argmin(np.linalg.norm(points-center, axis=1)))
            return SimpleNamespace(indices=np.array([index]))

        with patch('topogym.primitives.fem_attachment.FEMRopeAttachment', side_effect=attachment):
            actions.declare(None, None, points, None)
        actions.monitor = SimpleNamespace(last_centers=points)
        # Preserve the material band selected in the recorded canonical settle
        # while adding capacity in the previously excluded free-tail region.
        with patch('topogym.tasks.knot_untying.family_actions.first_under_grasp', return_value=1.0005):
            self.assertTrue(actions._choose_pull_band())
        self.assertAlmostEqual(actions.arc[actions.ring_indices[actions.pull_band]], 1.003849713761583, places=8)
        target = actions.arc[-1]-.045
        with patch('topogym.tasks.knot_untying.family_actions.first_under_grasp', return_value=target):
            self.assertTrue(actions._choose_pull_band())
        self.assertLess(abs(actions.arc[actions.ring_indices[actions.pull_band]]-target), .025)

    def test_placement_uses_held_surface_and_keeps_empty_hand_clear(self):
        actions = FamilyUntyingActions(config('figure_eight'))
        actions._record_motion = Mock()
        actions._transition = Mock()
        actions.owners = {0: 'right'}
        actions.bands = [SimpleNamespace(indices=np.array([0, 1]))]
        actions.monitor = SimpleNamespace(floor=.92,
            last_positions=np.array([[0., 0., .93], [0., 0., .934]]))
        quat = np.array([1., 0., 0., 0.])
        actions.motion = {'left': (np.array([0., 0., 1.02]), quat),
                          'right': (np.array([0., 0., .938]), quat)}
        actions._begin_release(60.)
        start, end, _ = actions.phase_targets['right']
        self.assertAlmostEqual(.93+(end[2]-start[2]), .923)
        self.assertGreater(end[2], .928)
        start, end, _ = actions.phase_targets['left']
        np.testing.assert_array_equal(start, end)

    def test_feed_requires_support_strand_clear_of_table(self):
        actions = FamilyUntyingActions(config('figure_eight'))
        actions.support_band = 0
        actions.bands = [SimpleNamespace(indices=np.array([0, 1]))]
        actions.monitor = SimpleNamespace(floor=.92,
            last_positions=np.array([[0., 0., .921], [0., 0., .925]]))
        with self.assertRaisesRegex(RuntimeError, 'against the table'):
            actions._check_support_clearance()
        actions.monitor.last_positions[:, 2] += .012
        actions._check_support_clearance()

    def test_pregrasp_rejects_rest_extension_allowed_only_under_load(self):
        cfg = config('figure_eight')
        actions = FamilyUntyingActions(cfg)
        points = KnotLayout(**OmegaConf.to_container(cfg.task.geometry, resolve=True)).centerline()
        actions.monitor = SimpleNamespace(
            report=lambda: {'checks': {'total_length': True, 'settled_rms_speed': True}},
            maxima={'max_total_length_relative_change': .03}, last_centers=points)
        actions._choose_pull_band = Mock()
        with self.assertRaisesRegex(RuntimeError, 'total_length'):
            actions._advance(10.)
        actions._choose_pull_band.assert_not_called()
        self.assertFalse(actions.pregrasp_settle_report['mechanical_checks_passed'])

    def test_underpass_grasp_tracks_material_after_scene_rotation(self):
        for family, route in ROUTES.items():
            layout = KnotLayout(**OmegaConf.to_container(config(family).task.geometry, resolve=True))
            points = layout.centerline()
            arc = material_arc(points)
            expected = first_under_grasp(points, arc, route.working_end)
            for angle in (0., .3, 1.57):
                c, s = np.cos(angle), np.sin(angle)
                rotated = points @ np.array([[c, s, 0], [-s, c, 0], [0, 0, 1]])+[.1, -.2, .9]
                actual = first_under_grasp(rotated, arc, route.working_end)
                self.assertAlmostEqual(actual, expected, places=10)
            self.assertGreater(expected, .015)
            self.assertLess(expected, arc[-1]-.015)
        straight = np.column_stack((np.linspace(0, 1, 50), np.zeros((50, 2))))
        self.assertIsNone(first_under_grasp(straight, material_arc(straight), 0))

    def test_trefoil_centerline_retains_original_asset(self):
        path = Path(__file__).resolve().parents[1]/'assets/tasks/knot_untying/trefoil_v1/geometry/centerline.json'
        expected = np.asarray(json.loads(path.read_text())['points_m'])
        np.testing.assert_array_equal(KnotLayout().centerline(), expected)

    def test_three_authored_diagrams_and_mirrors(self):
        for family, (_, _, count) in FAMILY_KNOTS.items():
            layout = KnotLayout(**OmegaConf.to_container(config(family).task.geometry, resolve=True))
            for hand in ('right', 'left'):
                with self.subTest(family=family, hand=hand):
                    chosen = replace(layout, handedness=hand)
                    report = inspect_geometry(chosen.centerline(), chosen)
                    self.assertTrue(report['knot_diagram_verified'])
                    self.assertEqual(report['crossing_count'], count)
                    self.assertEqual(report['diagnostic_closure_crossings'], count)
                    self.assertGreater(report['minimum_nonlocal_surface_gap_m'], .0008)
                    self.assertGreater(report['minimum_bend_radius_m'], 2*chosen.rope_radius_m)
                    for other in FAMILY_KNOTS:
                        self.assertEqual(template_diagram_matches(report['crossings'], other), family == other)

    def test_changed_over_under_is_not_the_authored_knot(self):
        for family in FAMILY_KNOTS:
            layout = KnotLayout(**OmegaConf.to_container(config(family).task.geometry, resolve=True))
            crossing = deepcopy(projected_crossings(layout.centerline()))
            crossing[0]['first_over'] = not crossing[0]['first_over']
            crossing[0]['sign'] *= -1
            self.assertFalse(template_diagram_matches(crossing, family))

    def test_seed_reproducibility_and_material_independence(self):
        for family in FAMILY_KNOTS:
            reference = config(family)
            for seed in (0, 19, 2026):
                a, b = config(family, seed), config(family, seed)
                self.assertEqual(OmegaConf.to_container(a.task), OmegaConf.to_container(b.task))
                self.assertEqual(a.task.rope, reference.task.rope)
                self.assertEqual(a.task.geometry.rope_radius_m, .004)
                layout = KnotLayout(**OmegaConf.to_container(a.task.geometry, resolve=True))
                self.assertTrue(inspect_geometry(layout.centerline(), layout)['knot_diagram_verified'])

    def test_new_family_meshes_are_connected_and_watertight(self):
        for family in ('figure_eight', 'double_overhand'):
            layout = KnotLayout(**OmegaConf.to_container(config(family).task.geometry, resolve=True))
            with TemporaryDirectory() as directory:
                _, report = generate_assets(directory, layout)
                mesh = trimesh.load(Path(directory)/'rope.obj', force='mesh', process=True)
                self.assertEqual(len(mesh.split()), 1)
                self.assertTrue(mesh.is_watertight and mesh.is_winding_consistent)
                self.assertGreater(mesh.volume, 0)
                self.assertEqual(report['physical_endpoints'], 2)
                self.assertFalse(report['physics_qualified'])


if __name__ == '__main__':
    unittest.main()
