"""Generator integration, reproducibility, rejection and mechanism invariants."""
from dataclasses import asdict
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import numpy as np
from omegaconf import OmegaConf

from topogym.generation.variant_rng import VariantRng, VARIANT_RNG_VERSION
from topogym.generation.variant_episode import build_variant_episode
from topogym.tasks.lock_picking import variants as v


class LockVariantChecks(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.base = v.base_config()

    def sample(self, seed, **options):
        return v.sample(seed, config=self.base, **options)

    def test_shared_entry_changes_real_geometry_and_covers_fixed_families(self):
        identities, layouts, families = set(), set(), set()
        for seed in range(32):
            cfg, spec = build_variant_episode(self.base, 'lock_picking', seed)
            proof, keyframes = v.check_geometry(cfg)
            row = v.prototype(cfg.task.randomization.family_id)
            self.assertEqual(cfg.task.geometry.slots, row['geometry']['slots'])
            self.assertEqual(proof['tab_count'], 3)
            self.assertGreaterEqual(cfg.task.geometry.pitch, .15)
            self.assertEqual(proof['certificate']['minimum_required_decoupling_retreats'], row['necessary_retreats'])
            self.assertEqual(sum(b['depth'] < a['depth'] for a,b in zip(keyframes,keyframes[1:])), row['necessary_retreats'])
            identities.add(spec.stable_id())
            layouts.add(v.canonical(v.plain(cfg.task.geometry)))
            families.add(cfg.task.randomization.family_id)
        self.assertEqual(len(identities), 32)
        self.assertEqual(len(layouts), 32)
        self.assertEqual(families, set(v.FAMILIES))

    def test_order_global_rng_and_output_do_not_change_identity(self):
        expected = {s:v.canonical(asdict(self.sample(s)[1])) for s in (7,1,42)}
        np.random.seed(4321)
        np.random.random(100)
        other = OmegaConf.create(v.plain(self.base))
        other.run.output = '/tmp/unrelated-output'
        other.task.variation = list(reversed(other.task.variation))
        actual = {s:v.canonical(asdict(self.sample(s)[1])) for s in (42,7,1)}
        self.assertEqual(expected, actual)
        for s in expected:
            cfg, _ = v.sample(s, config=other)
            self.assertEqual(cfg.task.instance_id, self.sample(s)[0].task.instance_id)
        self.assertEqual(VARIANT_RNG_VERSION, 1)
        self.assertEqual(VariantRng(0).stream('golden').random(), .062484451052847945)

    def test_retry_and_appearance_do_not_change_family_or_motion_parameters(self):
        original, _ = self.sample(1)
        for attempt in (1,2,3):
            retry, _ = self.sample(1, attempt=attempt)
            self.assertEqual(retry.task.randomization.family_id, original.task.randomization.family_id)
            self.assertEqual(retry.task.visual, original.task.visual)
            self.assertNotEqual(retry.task.geometry, original.task.geometry)
        plain, _ = self.sample(1, appearance=False)
        self.assertEqual(original.task.geometry, plain.task.geometry)
        self.assertEqual(original.task.rotor_stops, plain.task.rotor_stops)
        self.assertNotEqual(original.task.visual, plain.task.visual)

    def test_nine_representatives_and_parameter_corners(self):
        for family in v.FAMILIES:
            for anchor, (radius,pitch) in v.ANCHORS.items():
                cfg, _ = self.sample(0, family=family, representative=True, anchor=anchor)
                v.check_geometry(cfg)
                self.assertAlmostEqual(cfg.task.geometry.pitch*1000, pitch)
                self.assertAlmostEqual(cfg.task.geometry.disc_radius*1000, radius)
            cfg, _ = self.sample(0, family=family)
            for radius in (0.,1.):
                for pitch in (0.,1.):
                    cfg.task.randomization.radius_fraction = radius
                    cfg.task.randomization.pitch_fraction = pitch
                    v.derive(cfg.task)
                    v.check_geometry(cfg)

    def test_input_not_mutated_and_scene_overrides_are_rejected(self):
        cfg, _ = self.sample(4)
        before = v.canonical(v.plain(cfg))
        v.sample(8, config=cfg)
        self.assertEqual(before, v.canonical(v.plain(cfg)))
        cfg.task.variant = 'limited_two_retreats'
        with self.assertRaisesRegex(ValueError, 'variant'):
            v.check_geometry(cfg)
        cfg.task.variant = 'aligned_entry'
        cfg.task.geometry.pitch = .149
        with self.assertRaisesRegex(ValueError, 'geometry'):
            v.check_geometry(cfg)

    def test_real_ik_rejects_unreachable_draw_then_reproduces_accepted_draw(self):
        cfg, _ = self.sample(1)
        _, route = v.check_geometry(cfg)
        with self.assertRaisesRegex(RuntimeError, 'IK failed'):
            v.check_ik(cfg, route)
        first = v.generate(1, config=self.base)
        second = v.generate(1, config=self.base)
        self.assertEqual(first, second)
        self.assertGreater(first['accepted_attempt'], 0)
        self.assertEqual(len(first['rejected_attempts']), first['accepted_attempt'])
        self.assertEqual(first['validation']['physics']['status'], 'not_run')
        with self.assertRaisesRegex(RuntimeError, '1 attempts') as caught:
            v.generate(1, max_attempts=1, config=self.base)
        self.assertIn('IK failed', caught.exception.rejections[0]['reason'])

    def test_restore_without_pool_or_resampling_and_tamper_detection(self):
        instance = v.generate(0, family='F1', representative=True, config=self.base)
        with tempfile.TemporaryDirectory() as directory:
            out = v.write_instance(instance, Path(directory)/'one', assets=False)
            with patch.object(v, 'catalog', side_effect=AssertionError('No mutable pool on restore')):
                cfg, spec, restored = v.load_instance(out)
                v.check_geometry(cfg)
                v.check_ik(cfg, restored['keyframes'])
            self.assertEqual(restored, instance)
            self.assertEqual(asdict(spec), instance['spec'])
            path = out/'instance.json'
            data = json.loads(path.read_text())
            data['spec']['resolved_config']['task']['geometry']['pitch'] = .149
            v.save(path, data)
            with self.assertRaisesRegex(ValueError, 'checksum'):
                v.load_instance(out)

    def test_bounded_failure_and_invalid_parameters(self):
        with patch.object(v, 'check_ik', side_effect=ValueError('unreachable')):
            with self.assertRaisesRegex(RuntimeError, '2 attempts') as caught:
                v.generate(2, max_attempts=2, config=self.base)
            self.assertEqual(len(caught.exception.rejections), 2)
        for seed in (-1,True,1.5):
            with self.assertRaises(ValueError): self.sample(seed)
        for family in ('F0','F4'):
            with self.assertRaises(ValueError): self.sample(0,family=family)
        cfg, _ = self.sample(0)
        cfg.task.randomization.radius_fraction = float('nan')
        with self.assertRaises(ValueError): v.validate_parameters(cfg.task)
        with self.assertRaisesRegex(ValueError, 'demos'):
            v.metadata_path(v.ROOT/'demos/lock_picking/rejected')


if __name__ == '__main__':
    unittest.main()
