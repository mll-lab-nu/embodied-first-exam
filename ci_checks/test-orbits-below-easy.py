#!/usr/bin/env python3
"""Orbits below-easy variants (rigid link chain cord): actual assets, topology and terminal contracts; no solve claim."""
from copy import deepcopy
from dataclasses import asdict
from pathlib import Path
import hashlib
import sys
import tempfile
import unittest

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from topogym.assets.geometry.orbits import OrbitsLayout, make_meshes
from topogym.config.registry import task_definition, variation_registration, seeded_variation
from topogym.config.scene import load_scene_config
from topogym.planning.orbits.invariant import Fixture
from topogym.simulator import SimulatorConfig


class OrbitsBelowEasy(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.folder = tempfile.TemporaryDirectory()
        cls.scenes = {}
        for tier in ('very_easy', 'easier'):
            task = task_definition('orbits', tier)(seed=0)
            scene = load_scene_config(SimulatorConfig(task_id='orbits', variation_id=tier))
            table = scene.env.world.table
            height = float(table.pos[2]+table.size[2]/2)
            folder = Path(cls.folder.name)/tier
            spec = task.declare(folder, height)
            spec = task.finalize_spec(spec, asset_dir=folder, scene_config=scene)
            cls.scenes[tier] = task, spec, folder

    @classmethod
    def tearDownClass(cls):
        cls.folder.cleanup()

    def initial_state(self, tier):
        """The declared birth poses: fixture bodies, and the handle and every chain link at rest."""
        from scipy.spatial.transform import Rotation
        task, spec, _ = self.scenes[tier]
        yaw = Rotation.from_euler('z', task.config['yaw_deg'], degrees=True)
        rest = lambda position, turn: dict(position_m=np.asarray(position, float), quaternion_wxyz=turn.as_quat()[[3, 0, 1, 2]],
                                           linear_velocity_m_s=np.zeros(3), angular_velocity_rad_s=np.zeros(3))
        roots = task.link_roots
        links = {'handle': rest(task.origin, yaw)}
        for i, name in enumerate(task.link_names):
            along, _ = Rotation.align_vectors([roots[i+1]-roots[i]], [[1., 0., 0.]])
            links[name] = rest(yaw.apply(roots[i])+task.origin, yaw*along)
        bodies = {e.name: rest(e.position_m, Rotation.from_quat(np.r_[e.quaternion_wxyz[1:], e.quaternion_wxyz[0]]))
                  for e in spec.entities if e.name in task.placement_remainder}
        bodies['cord'] = links['handle']
        return dict(bodies=bodies, articulations=dict(cord=dict(links=links)))

    def placed_state(self, tier):
        """Synthetic measurement fixture for the predicate, not a simulated solution: the birth chain and handle turned
        45 deg about the vertical (easier's 1.25 m loop and handle span 0.44 x 0.42 m, more than the goal's 0.40 m side) and moved whole onto
        the goal centre, so the eye tie is kept."""
        from scipy.spatial.transform import Rotation
        state = deepcopy(self.initial_state(tier))
        task = self.scenes[tier][0]
        links = state['articulations']['cord']['links']
        points, _ = task.cord_points(state)
        pivot = np.r_[(points[:, :2].min(0)+points[:, :2].max(0))/2, 0.]
        turn = Rotation.from_euler('z', 45, degrees=True)
        for link in links.values():
            link['position_m'] = turn.apply(link['position_m']-pivot)+pivot
            link['quaternion_wxyz'] = (turn*Rotation.from_quat(np.r_[link['quaternion_wxyz'][1:], link['quaternion_wxyz'][0]])).as_quat()[[3, 0, 1, 2]]
        points, _ = task.cord_points(state)
        shift = np.r_[np.asarray(task.goal_region.center_xy_m)-(points[:, :2].min(0)+points[:, :2].max(0))/2, 0.]
        for link in links.values():
            link['position_m'] = link['position_m']+shift
        return state

    def test_registered_aliases_and_fixed_model_identity(self):
        for tier, rings in (('very_easy', 0), ('easier', 1)):
            task, spec, _ = self.scenes[tier]
            record = variation_registration('orbits', tier)
            self.assertIs(task_definition('orbits', 'orbits_'+tier), type(task))
            self.assertEqual(record['difficulty'], tier)
            self.assertEqual(record['pool'], 'below_easy')
            self.assertEqual(record['model_revision'], task.model_revision)
            self.assertEqual(task.layout.ring_count, rings)
            contract = spec.metadata['orbits_scene_contract']
            self.assertEqual(contract['post_count'], rings+1)
            self.assertEqual(len(contract['ring_centers_world_m']), rings)
            self.assertFalse(contract['solution_verified'])
            self.assertFalse(contract['difficulty_qualified'])
        self.assertNotEqual(self.scenes['very_easy'][0].instance_id, self.scenes['easier'][0].instance_id)

    def test_approved_dimensions_and_no_hidden_extra_parts(self):
        # easier is resized for the standard solution (user, 2026-10-07): a gripper reaches down through the ring hole to
        # the bight around the ring's support post, and the cord loop is long enough to pass around the whole ring.
        expected = dict(very_easy=dict(base=(.306, .1955), handle=.32, aperture=.1394, spacing=.0952, bight=.035, cord=.90),
                        easier=dict(base=(.36, .26), handle=.42, aperture=.22, spacing=.165, bight=.07, cord=1.25))
        for tier, rings in (('very_easy', 0), ('easier', 1)):
            task, spec, _ = self.scenes[tier]
            l, want = task.layout, expected[tier]
            self.assertAlmostEqual(l.base_length_m, want['base'][0])
            self.assertAlmostEqual(l.base_width_m, want['base'][1])
            # Thin base (user, 2026-10-07): a handle dragged toward the fixture caught on the 20.4 mm edge.
            self.assertAlmostEqual(l.base_height_m, .002)
            self.assertAlmostEqual(l.ball_z+l.ball_radius_m, .15045)
            self.assertAlmostEqual(l.handle_x_m, want['handle'])
            self.assertAlmostEqual(2*(l.ring_radius_m-l.ring_tube_radius_m), want['aperture'])
            self.assertAlmostEqual(l.post_spacing_m, want['spacing'])
            self.assertAlmostEqual(l.bight_radius_m, want['bight'])
            names = {e.name for e in spec.entities if e.name in task.placement_remainder}
            self.assertEqual(names, {'base', 'stopper_ball', 'post_1'} |
                             ({'ring_1', 'post_2'} if rings else set()))
            self.assertAlmostEqual(spec.metadata['geometry_report']['cord_length_m'], want['cord'], delta=.0002)

    def test_actual_geometry_and_closed_chain(self):
        import xml.etree.ElementTree as ET
        for tier, (task, spec, folder) in self.scenes.items():
            self.assertTrue(spec.metadata['geometry_report']['passed'])
            self.assertTrue(all(spec.metadata['geometry_report']['checks'].values()))
            self.assertEqual(task.physics_model, 'rigid_articulated')
            self.assertEqual(spec.attachments, ())
            self.assertEqual(spec.physics_options, {'rigid': {'enable_self_collision': True, 'constraint_solver': 'CG'}})
            cord = next(e for e in spec.entities if e.name == 'cord')
            self.assertEqual((cord.morph_type, cord.fixed), ('mjcf', False))
            self.assertNotIn('handle', {e.name for e in spec.entities})
            root = ET.parse(cord.asset_path).getroot()
            tie = root.find('equality/connect')
            self.assertEqual((tie.get('site1'), tie.get('site2')), ('tip_a', 'tip_b'))
            # Two branches from the handle meet at the middle: link m-1 ends at tip_a, link m starts at tip_b.
            self.assertEqual(root.find(f".//body[@name='{task.link_names[task.tie_link-1]}']/site").get('name'), 'tip_a')
            self.assertEqual(root.find(f".//body[@name='{task.link_names[task.tie_link]}']/site").get('name'), 'tip_b')
            self.assertEqual({b.get('name') for b in root.find('worldbody/body').findall('body')},
                             {task.link_names[0], task.link_names[-1]})
            self.assertEqual(len(root.findall('.//joint[@type="ball"]')), len(task.link_names))
            # A stiff cord: every bend joint springs back toward the authored loop, k = E pi r^4 / (4 L).
            stiffness = [float(j.get('stiffness')) for j in root.findall('.//joint[@type="ball"]')]
            want = task.YOUNG_MODULUS_PA*np.pi*task.CHAIN_RADIUS_M**4/(4*task.link_lengths)
            np.testing.assert_allclose(sorted(stiffness), sorted(want), rtol=1e-6)
            self.assertTrue(np.all((task.link_lengths > .0155) & (task.link_lengths < .0175)), tier)
            # Both chain ends start above the handle top, beside its two eyes.
            l = task.layout
            for end in (task.link_roots[0], task.link_roots[-1]):
                self.assertGreaterEqual(end[2], l.clearance_m+l.handle_height_m+task.CHAIN_RADIUS_M-1e-9)
                self.assertLess(abs(end[0]-l.eyes[0, 0]), .03)

    def test_chain_identity_and_original_tiers_keep_the_fem_cord(self):
        from topogym.tasks.orbits.common import OrbitsTask
        for tier, (task, _, _) in self.scenes.items():
            class PreviousRevision(type(task)):
                model_revision = 'below_easy_v3_thin_base_friction1mm_v1'
            self.assertNotEqual(PreviousRevision(seed=0).instance_id, type(task)(seed=0).instance_id)
        for tier in ('easy', 'medium', 'hard', 'base'):
            definition = task_definition('orbits', tier)
            self.assertIs(definition.declare, OrbitsTask.declare)
            self.assertEqual(definition.physics_model, 'fem_ipc')

    def test_half_second_goal_window_resets_after_a_speed_spike(self):
        for tier, (original, _, _) in self.scenes.items():
            task = deepcopy(original)
            self.assertEqual(task.config['stable_duration_s'], .5)
            state = self.placed_state(tier)
            state['physics_step'] = 0
            task.initialize(state)
            # 0.4 s quiet, a speed spike, then a fresh 0.5 s window.
            for step in range(1, 14):
                state['physics_step'] = step
                link = state['articulations']['cord']['links']['link_05']
                link['linear_velocity_m_s'] = np.array([.0101 if step == 6 else .0099, 0., 0.])
                result = task.update(state, .1)
                self.assertEqual(result.task_success, step >= 12, (tier, step))
                if step == 6:
                    self.assertEqual(task.stable_time_s, 0.)

    def test_initial_topology_has_one_or_two_ball_letters(self):
        for tier, count in (('very_easy', 1), ('easier', 2)):
            task = self.scenes[tier][0]
            word, _, ball_letters = Fixture(task.layout, ring_pts=180).describe(task.link_roots)
            self.assertEqual(ball_letters, count, (tier, word))

    def test_birth_state_is_not_success(self):
        for tier, (task, _, _) in self.scenes.items():
            reached, failure, metrics = task.evaluate_state(self.initial_state(tier))
            self.assertFalse(reached)
            self.assertIsNone(failure)
            self.assertEqual(metrics['evaluation_status'], 'available')

    def test_entire_target_and_fixed_remainder_are_required(self):
        for tier, (task, _, _) in self.scenes.items():
            placed = self.placed_state(tier)
            self.assertTrue(task.evaluate_state(placed)[0])
            handle_only = self.initial_state(tier)
            handle_only['articulations']['cord']['links']['handle'] = placed['articulations']['cord']['links']['handle']
            self.assertFalse(task.evaluate_state(handle_only)[0])
            one_link_outside = deepcopy(placed)
            one_link_outside['articulations']['cord']['links']['link_10']['position_m'] += [1., 0., 0.]
            self.assertFalse(task.evaluate_state(one_link_outside)[0])
            fixture_in_goal = deepcopy(placed)
            fixture_in_goal['bodies']['post_1']['position_m'][:2] = task.goal_region.center_xy_m
            self.assertFalse(task.evaluate_state(fixture_in_goal)[0])

    def test_motion_and_a_broken_middle_tie_cannot_pass(self):
        for tier, (task, _, _) in self.scenes.items():
            state = self.placed_state(tier)
            state['articulations']['cord']['links']['link_20']['linear_velocity_m_s'] = np.array([.011, 0., 0.])
            self.assertFalse(task.evaluate_state(state)[0])
            state = self.placed_state(tier)
            state['articulations']['cord']['links']['handle']['angular_velocity_rad_s'] = np.array([0., 0., .03])
            self.assertFalse(task.evaluate_state(state)[0])
            state = self.placed_state(tier)
            half = state['articulations']['cord']['links'][task.link_names[task.tie_link]]
            half['position_m'] = half['position_m']+[.003, 0., 0.]
            reached, failure, metrics = task.evaluate_state(state)
            self.assertFalse(reached)
            self.assertEqual(failure, 'connection_invalid')
            self.assertGreater(metrics['tie_residual_m'], .002)

    def test_rebuild_same_seed_has_identical_assets_and_goal(self):
        for tier, (original, _, folder) in self.scenes.items():
            task = task_definition('orbits', tier)(seed=0)
            second = Path(self.folder.name)/(tier+'_rebuild')
            scene = load_scene_config(SimulatorConfig(task_id='orbits', variation_id=tier))
            spec = task.declare(second, original.table_height_m)
            task.finalize_spec(spec, asset_dir=second, scene_config=scene)
            self.assertEqual(task.instance_id, original.instance_id)
            self.assertEqual(asdict(task.goal_region), asdict(original.goal_region))
            hashes = lambda p: {f.name: hashlib.sha256(f.read_bytes()).hexdigest() for f in p.iterdir() if f.is_file()}
            self.assertEqual(hashes(folder), hashes(second))

    def test_named_variants_reject_geometry_and_material_profile_overrides(self):
        for tier in self.scenes:
            for override in ({'geometry': {'ring_count': 4}}, {'linear_scale': .5},
                             {'cord_profile': 'reference'}):
                with self.subTest(tier=tier, override=override), self.assertRaises(ValueError):
                    task_definition('orbits', tier)(override)

    def test_existing_tiers_seeded_and_reference_are_preserved(self):
        self.assertEqual(variation_registration('orbits', 'base')['variation_id'], 'orbits_reference85')
        for seed in range(12):
            self.assertEqual(seeded_variation('orbits', seed)['difficulty'], ('easy', 'medium', 'hard')[seed % 3])
        for tier, count in (('easy', 2), ('medium', 3), ('hard', 4)):
            task = task_definition('orbits', tier)()
            l = OrbitsLayout(**task.config['geometry']).scaled(.85)
            self.assertEqual(l.ring_count, count)
            self.assertAlmostEqual(l.ring_radius_m, .066*.85)
            self.assertEqual(task.config['cord_profile'], 'compact_external_handle_v1')

    def test_public_goal_describes_the_single_post_and_shared_completion(self):
        single = self.scenes['very_easy'][0].public_instruction()
        ring = self.scenes['easier'][0].public_instruction()
        self.assertIn('the fixed post, stopper ball and base', single)
        self.assertIn('the rings, posts and fixed assembly', ring)
        for text in (single, ring):
            self.assertIn('entire cord and wooden handle', text)
            self.assertIn('0.5', text)

    def test_zero_ring_layout_and_invalid_ring_counts(self):
        l = OrbitsLayout(ring_count=0).validate()
        self.assertEqual(l.ring_z.size, 0)
        self.assertEqual(l.ring_x.size, 0)
        self.assertEqual(set(make_meshes(l)[0]), {'base', 'post_1', 'stopper_ball', 'handle', 'cord'})
        for count in (-1, 5, True, 1.5):
            with self.subTest(count=count), self.assertRaises(ValueError):
                OrbitsLayout(ring_count=count).validate()


if __name__ == '__main__':
    unittest.main()
