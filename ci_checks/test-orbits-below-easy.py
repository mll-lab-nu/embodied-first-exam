#!/usr/bin/env python3
"""Orbits variants: actual assets, topology and terminal contracts; no solve claim."""
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
        task, spec, folder = self.scenes[tier]
        with np.load(folder/'cord_volume.npz') as volume:
            points = volume['spawn']+task.origin
        return dict(
            bodies={e.name: dict(position_m=np.array(e.position_m),
                quaternion_wxyz=np.array(e.quaternion_wxyz),
                linear_velocity_m_s=np.zeros(3), angular_velocity_rad_s=np.zeros(3))
                for e in spec.entities if e.name != 'cord'},
            fem=dict(cord=dict(position_m=points, velocity_m_s=np.zeros_like(points))),
            ipc=dict(native_valid=True, volume_ratio=dict(cord=dict(minimum=1., maximum=1.)),
                     attachment_residual_m=dict(cord_handle_start=0., cord_handle_end=0.)))

    def placed_state(self, tier):
        """Synthetic measurement fixture for the predicate, not a simulated solution."""
        state = self.initial_state(tier)
        task = self.scenes[tier][0]
        center = np.r_[task.goal_region.center_xy_m, task.table_height_m+.04]
        count = len(state['fem']['cord']['position_m'])
        points = np.tile(center, (count, 1))
        points[:, 0] += np.linspace(-.06, .06, count)
        state['fem']['cord']['position_m'] = points
        state['bodies']['handle']['position_m'] = center-task.placement_vertices['handle'].mean(axis=0)
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
        for tier, rings in (('very_easy', 0), ('easier', 1)):
            task, spec, _ = self.scenes[tier]
            l = task.layout
            self.assertAlmostEqual(l.base_length_m, .306)
            self.assertAlmostEqual(l.ball_z+l.ball_radius_m, .15045)
            self.assertAlmostEqual(l.handle_x_m, .32)
            self.assertAlmostEqual(2*(l.ring_radius_m-l.ring_tube_radius_m), .1394)
            names = {e.name for e in spec.entities if e.name in task.placement_remainder}
            self.assertEqual(names, {'base', 'stopper_ball', 'post_1'} |
                             ({'ring_1', 'post_2'} if rings else set()))
            self.assertAlmostEqual(spec.metadata['geometry_report']['cord_length_m'], .80, delta=.0002)

    def test_actual_geometry_and_material_volume(self):
        for tier, (task, spec, folder) in self.scenes.items():
            self.assertTrue(spec.metadata['geometry_report']['passed'])
            self.assertTrue(all(spec.metadata['geometry_report']['checks'].values()))
            self.assertEqual({a.name for a in spec.attachments}, {'cord_handle_start', 'cord_handle_end'})
            cord = next(e for e in spec.entities if e.name == 'cord')
            self.assertEqual(cord.physics_model, 'fem_elastic')
            self.assertFalse(cord.fixed)
            self.assertFalse(next(e for e in spec.entities if e.name == 'handle').fixed)
            with np.load(folder/'cord_volume.npz') as volume:
                for key in ('rest', 'spawn'):
                    points = volume[key][volume['elements']]
                    self.assertTrue(np.all(np.linalg.det(points[:, 1:]-points[:, :1]) > 0), (tier, key))

    def test_friction_option_reaches_genesis_and_old_instances_are_distinct(self):
        from topogym.world.physics.ipc import scene_options
        from topogym.tasks.orbits.common import OrbitsTask
        for tier, (task, spec, _) in self.scenes.items():
            options = scene_options(spec.physics_options['ipc'])
            self.assertEqual(options.contact_eps_velocity, .001)
            self.assertEqual(options.contact_d_hat, .0002)
            # The old identity must not accept native dumps from the new physics.
            class PreviousRevision(type(task)):
                model_revision = 'below_easy_v1_fem_soft50_fine_v1'
            old = PreviousRevision(seed=0)
            self.assertNotEqual(old.instance_id, type(task)(seed=0).instance_id)
        for tier in ('easy', 'medium', 'hard', 'base'):
            self.assertIs(task_definition('orbits', tier).declare, OrbitsTask.declare)

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
                state['fem']['cord']['velocity_m_s'][0, 0] = .00101 if step == 6 else .00099
                result = task.update(state, .1)
                self.assertEqual(result.task_success, step >= 12, (tier, step))
                if step == 6:
                    self.assertEqual(task.stable_time_s, 0.)

    def test_initial_topology_has_one_or_two_ball_letters(self):
        for tier, count in (('very_easy', 1), ('easier', 2)):
            task, _, folder = self.scenes[tier]
            from scipy.spatial.transform import Rotation
            line = np.load(folder/'cord_centerline.npy')
            line = Rotation.from_euler('z', -task.config['yaw_deg'], degrees=True).apply(line)
            word, _, ball_letters = Fixture(task.layout, ring_pts=180).describe(line)
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
            handle_only['bodies']['handle'] = placed['bodies']['handle']
            self.assertFalse(task.evaluate_state(handle_only)[0])
            one_node_outside = deepcopy(placed)
            one_node_outside['fem']['cord']['position_m'][0] += [1., 0., 0.]
            self.assertFalse(task.evaluate_state(one_node_outside)[0])
            fixture_in_goal = deepcopy(placed)
            fixture_in_goal['bodies']['post_1']['position_m'][:2] = task.goal_region.center_xy_m
            self.assertFalse(task.evaluate_state(fixture_in_goal)[0])

    def test_motion_missing_evidence_and_broken_connection_cannot_pass(self):
        for tier, (task, _, _) in self.scenes.items():
            state = self.placed_state(tier)
            state['fem']['cord']['velocity_m_s'][0, 0] = .002
            self.assertFalse(task.evaluate_state(state)[0])
            state = self.placed_state(tier)
            state['ipc']['attachment_residual_m']['cord_handle_end'] = .003
            reached, failure, _ = task.evaluate_state(state)
            self.assertFalse(reached)
            self.assertEqual(failure, 'connection_or_volume_invalid')
            state = self.placed_state(tier)
            state.pop('ipc')
            reached, _, metrics = task.evaluate_state(state)
            self.assertFalse(reached)
            self.assertEqual(metrics['evaluation_status'], 'unavailable')

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
