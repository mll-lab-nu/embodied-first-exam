"""Instance identity, legacy seed compatibility, rejection and artifact recovery."""
from dataclasses import asdict
import json
from pathlib import Path
import shutil
import tempfile
import unittest
from unittest.mock import patch

from omegaconf import OmegaConf

from topogym.tasks.catalog import load_card
from topogym.tasks.fiber_bundling.generation import (
    build_episode, save_instance, load_instance, configuration, GenerationRejected,
)
from topogym.tasks.fiber_bundling.variants import sample_parameters, validate_parameters


class FiberGenerationChecks(unittest.TestCase):
    def test_seed_mapping_unchanged_and_named_axes_independent(self):
        # Golden values predate the new instance wrapper; changing the wrapper
        # must not silently change the old geometry sampler's scenes.
        p = sample_parameters(0)
        self.assertEqual((p['family_id'], p['fiber_count']), ('sparse', 4))
        self.assertEqual(p['ring_inner_radius_m'], .014401711409862464)
        for family in ('sparse', 'standard', 'dense'):
            a = sample_parameters(21, family)
            b = sample_parameters(21, family, retry=1)
            self.assertEqual(a['ring_inner_radius_m'], sample_parameters(21)['ring_inner_radius_m'])
            self.assertEqual(a['family_id'], b['family_id'])
            self.assertNotEqual(a['ring_inner_radius_m'], b['ring_inner_radius_m'])

    def test_order_independence_and_common_spec(self):
        first = {seed: asdict(build_episode(seed)[1]) for seed in (1, 4, 0)}
        for seed in (0, 4, 1):
            cfg, spec = build_episode(seed)
            self.assertEqual(first[seed], asdict(spec))
            self.assertEqual(spec.resolved_config['configuration'], configuration(cfg))
            self.assertTrue(spec.variant.instruction)
            self.assertFalse(spec.resolved_config['validation']['dataset_ready'])
            self.assertEqual(spec.resolved_config['validation']['full_physics'], 'not_run')
        self.assertNotEqual(first[1]['resolved_config']['instance_sha256'], first[4]['resolved_config']['instance_sha256'])
        self.assertEqual(load_card('fiber_bundling')['variant_generation']['episode_factory'],
                         'topogym.tasks.fiber_bundling.generation:build_episode')

    def test_fixed_library_does_not_redesign_shapes(self):
        for family, count in [('sparse', 4), ('standard', 8), ('dense', 16)]:
            cfg, a = build_episode(0, family_id=family, mode='fixed')
            _, b = build_episode(80, family_id=family, mode='fixed')
            self.assertEqual(a.resolved_config['instance_sha256'], b.resolved_config['instance_sha256'])
            self.assertNotEqual(a.stable_id(), b.stable_id())
            self.assertEqual(cfg.task.geometry.fiber_count, count)
            self.assertEqual(cfg.task.geometry.ring_inner_radius_m, .0135)
            self.assertEqual(cfg.task.geometry.seed, 7)

    def test_rejection_is_bounded_reproducible_and_keeps_requested_family(self):
        from topogym.tasks.fiber_bundling.generation import inspect_candidate
        calls = []
        def reject_once(cfg):
            calls.append(int(cfg.task.geometry.fiber_count))
            if len(calls) == 1:
                raise ValueError('synthetic geometry rejection')
            return inspect_candidate(cfg)
        with patch('topogym.tasks.fiber_bundling.generation.inspect_candidate', side_effect=reject_once):
            _, spec = build_episode(0, family_id='sparse')
        self.assertEqual(spec.variant.parameters['accepted_attempt'], 1)
        self.assertEqual(spec.variant.parameters['ring_inner_radius_m'], sample_parameters(0, 'sparse', retry=1)['ring_inner_radius_m'])
        self.assertEqual(spec.resolved_config['rejected_attempts'][0]['reason'], 'synthetic geometry rejection')
        with patch('topogym.tasks.fiber_bundling.generation.inspect_candidate', side_effect=ValueError('synthetic invalid layout')):
            with self.assertRaises(GenerationRejected) as result:
                build_episode(2, max_attempts=2)
            self.assertEqual(len(result.exception.attempts), 2)
            self.assertTrue(all(a['parameters']['family_id'] == 'dense' for a in result.exception.attempts))

    def test_invalid_requests_fail_before_writing(self):
        for seed in (-1, True, 1.5, '2'):
            with self.assertRaises(ValueError): build_episode(seed)
        with self.assertRaises(ValueError): build_episode(0, family_id='invented_motion_family')
        with self.assertRaises(ValueError): build_episode(0, mode='random_ik')
        for changed in ({'fiber_count': 16}, {'ring_inner_radius_m': float('nan')},
                        {'shape_seed': 2}, {'generator_version': 'unknown'}):
            with self.assertRaises(ValueError): validate_parameters(dict(sample_parameters(0), **changed))

    def test_saved_instance_is_relocatable_and_detects_corruption_without_resampling(self):
        from topogym.tasks.fiber_bundling.run_config import load_run_config
        with tempfile.TemporaryDirectory() as name:
            root = Path(name)
            spec = save_instance(root/'a', 0, mode='fixed')
            shutil.copytree(root/'a', root/'relocated')
            with patch('topogym.tasks.fiber_bundling.generation.sample_parameters', side_effect=AssertionError('must not sample')):
                cfg, loaded = load_instance(root/'relocated')
            self.assertEqual(spec, loaded)
            self.assertEqual(cfg.run.output, str(root/'relocated'))
            self.assertEqual(configuration(OmegaConf.load(root/'a/config.yaml')), configuration(cfg))
            self.assertEqual(configuration(load_run_config(root/'relocated/config.yaml')), configuration(cfg))
            asset = root/'relocated/assets/bundle.xml'
            asset.write_text(asset.read_text() + '\n')
            with self.assertRaisesRegex(ValueError, 'artifact changed'): load_instance(root/'relocated')
            with self.assertRaisesRegex(ValueError, 'artifact changed'): load_run_config(root/'relocated/config.yaml')
            with self.assertRaises(FileExistsError): save_instance(root/'a', 0, mode='fixed')


if __name__ == '__main__':
    unittest.main()
