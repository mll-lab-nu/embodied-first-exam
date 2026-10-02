#!/usr/bin/env python3
"""CPU regressions for the combined public tool; no physics success is implied."""
import importlib.util
import json
from pathlib import Path
import shutil
import sys
import tempfile
from types import SimpleNamespace
import unittest

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT), str(ROOT / "scripts"), str(ROOT / "harbor_templates/topogym/common")]
import rcb_topogym as tool
from topogym.utils.geometry.passage import planar_clearance
from collect_batch_results import classify_trial


class MergeTests(unittest.TestCase):
    def test_checkpoint_bound_preserves_upstream_call_and_gradient_mode(self):
        saved = []
        fem = SimpleNamespace(is_active=True, _ckpt={})
        def save(name):
            saved.append(name)
            fem._ckpt[name] = np.arange(3) + len(saved)
        fem.save_ckpt = save
        sim = SimpleNamespace(fem_solver=fem, requires_grad=True)
        env = SimpleNamespace(_world=SimpleNamespace(scene=SimpleNamespace(sim=sim)))
        self.assertFalse(tool._drop_fem_gradient_checkpoints(env))
        self.assertIs(fem.save_ckpt, save)
        sim.requires_grad = False
        self.assertTrue(tool._drop_fem_gradient_checkpoints(env))
        wrapped = fem.save_ckpt
        self.assertTrue(tool._drop_fem_gradient_checkpoints(env))
        self.assertIs(fem.save_ckpt, wrapped)
        for i in range(200):
            name = str(i)
            fem.save_ckpt(name)
            self.assertEqual(list(fem._ckpt), [name])
            np.testing.assert_array_equal(fem._ckpt[name], np.arange(3) + i + 1)
        self.assertEqual(len(saved), 200)
        fem.is_active = False
        self.assertFalse(tool._drop_fem_gradient_checkpoints(env))
        sim.fem_solver = None
        self.assertFalse(tool._drop_fem_gradient_checkpoints(env))

    def test_vectorized_predicate_matches_reference(self):
        rng = np.random.default_rng(901)
        curves = [np.array(p, dtype=float) for p in (
            [[0,0,0],[1,0,0]], [[0,0,0],[1,0,0],[0,0,0]],
            [[0,0,0],[0,0,1],[1,0,1]],
            [[0,0,0],[1,1,0],[0,1,0],[1,0,0]],
            [[0,0,0],[1,0,0],[2,0,0],[3,0,0]],
        )]
        curves += [np.cumsum(rng.normal(size=(n,3)),axis=0) for n in (3,5,12,30) for _ in range(8)]
        for p in curves:
            material = np.arange(len(p), dtype=float) * .1
            for diameter in (.001,.2,1.):
                with self.subTest(points=len(p), diameter=diameter):
                    expected = planar_clearance(p, material, diameter)
                    actual = tool._vectorized_planar_clearance(p, material, diameter)
                    self.assertEqual(actual[0], expected[0])
                    self.assertEqual(actual[1]['projected_degenerate'], expected[1]['projected_degenerate'])
                    old = expected[1]['minimum_nonlocal_distance_m']
                    new = actual[1]['minimum_nonlocal_distance_m']
                    if old is None:
                        self.assertIsNone(new)
                    else:
                        self.assertAlmostEqual(new, old, places=12)

    def test_vectorized_predicate_rejects_invalid_inputs(self):
        p = np.array([[0.,0,0],[1,0,0],[2,0,0]])
        for material, diameter in (([0,0,1],.1),([0,1],.1),([0,1,2],0),([0,1,2],float('nan'))):
            for fn in (planar_clearance, tool._vectorized_planar_clearance):
                with self.assertRaises(ValueError):
                    fn(p, material, diameter)

    def test_collector_accepts_both_generations_but_not_other_mode(self):
        with tempfile.TemporaryDirectory() as folder:
            job = Path(folder); trial = job/'trial'; (trial/'verifier').mkdir(parents=True)
            row = dict(slug='topogym-test-i00', evaluable_for_task_success=True)
            reward = dict(success=0, finalized=1)
            (trial/'verifier/reward.json').write_text(json.dumps(reward))
            for mode, suffixes in (('unlimited', ('','-privileged')), ('limited', ('-limited','-standard'))):
                for suffix in suffixes:
                    result = dict(task_name=row['slug']+suffix, finished_at='fixture', verifier_result=dict(rewards=reward))
                    (trial/'result.json').write_text(json.dumps(result))
                    self.assertEqual(classify_trial(job, row, mode)[0], 'unsolved')
                    other = 'limited' if mode == 'unlimited' else 'unlimited'
                    self.assertEqual(classify_trial(job, row, other)[0], 'identity_mismatch')

    def test_standard_infrastructure_failure_is_not_an_unsolved_task(self):
        with tempfile.TemporaryDirectory() as folder:
            job = Path(folder); trial = job/'trial'; (trial/'verifier').mkdir(parents=True)
            row = dict(slug='topogym-test-i00', evaluable_for_task_success=True)
            for field in ('infra_error', 'gpu_lost'):
                reward = dict(success=0, finalized=1, **{field:1})
                (trial/'verifier/reward.json').write_text(json.dumps(reward))
                (trial/'result.json').write_text(json.dumps(dict(task_name=row['slug']+'-standard',
                    finished_at='fixture', verifier_result=dict(rewards=reward))))
                self.assertEqual(classify_trial(job, row, 'limited')[0], 'infra_failed')

    def test_frozen_inventory_detects_missing_and_tampered_tooling(self):
        spec = importlib.util.spec_from_file_location('tooling_check', ROOT/'ci_checks/check-topogym-tooling.py')
        checker = importlib.util.module_from_spec(spec); spec.loader.exec_module(checker)
        name = 'topogym-interlocked-claws-hard-i00-standard'
        with tempfile.TemporaryDirectory() as folder:
            target = Path(folder)/name
            shutil.copytree(ROOT/'tasks'/name, target)
            self.assertFalse(checker.check(Path(folder))[1])
            path = target/'environment/sim/rcb_topogym.py'
            original = path.read_bytes()
            path.write_bytes(original+b'\n# changed\n')
            self.assertTrue(checker.check(Path(folder))[1])
            path.unlink()
            self.assertTrue(checker.check(Path(folder))[1])
            path.write_bytes(original)
            metadata = target/'task.toml'
            metadata.write_text(metadata.read_text().replace('[metadata]', '[metadata]\ntooling_version = "unknown"'))
            self.assertTrue(checker.check(Path(folder))[1])


if __name__ == '__main__':
    unittest.main()
