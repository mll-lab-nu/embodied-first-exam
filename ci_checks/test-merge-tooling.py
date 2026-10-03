#!/usr/bin/env python3
"""CPU regressions for the combined public tool; no physics success is implied."""
import importlib.util
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT), str(ROOT / "scripts"), str(ROOT / "harbor_templates/topogym/common")]
import rcb_topogym as tool
from topogym.utils.geometry.passage import planar_clearance
from collect_batch_results import classify_trial


class MergeTests(unittest.TestCase):
    def test_local_v11_grasp_packages_keep_their_own_identity_and_image(self):
        spec = importlib.util.spec_from_file_location('local_v11_check', ROOT/'ci_checks/check-topogym-tooling.py')
        checker = importlib.util.module_from_spec(spec); spec.loader.exec_module(checker)
        for family, suffix in ((f, m) for f in ('lock-picking', 'buzz-wire-3d', 'fiber-bundling')
                               for m in ('privileged', 'standard')):
            with self.subTest(family=family, mode=suffix), tempfile.TemporaryDirectory() as folder:
                name = f'topogym-{family}-very-easy-i00-{suffix}'
                task = Path(folder)/name
                shutil.copytree(ROOT/'tasks'/name, task)
                with patch.object(checker, 'current_image', return_value='future-image'):
                    self.assertFalse(checker.check(Path(folder))[1])
                grader = task/'tests/grade.py'
                original = grader.read_bytes()
                grader.write_bytes(original + b'\n# changed\n')
                self.assertTrue(checker.check(Path(folder))[1])
                grader.write_bytes(original)
                image_file = task/('environment/Dockerfile' if suffix == 'privileged' else 'environment/docker-compose.yaml')
                original_image = image_file.read_text()
                self.assertIn('topogym-local/', original_image)
                image_file.write_text(original_image.replace('topogym-local/', 'wrong-image/'))
                self.assertTrue(any('image' in e for e in checker.check(Path(folder))[1]))

    def test_owner_sensor_adapter_coexists_with_deferred_rgb(self):
        from topogym.simulator.env import Env
        from topogym.simulator.config import SimulatorConfig
        from topogym.sensors.observation import SensorSuite
        from topogym.planning.calibration_tools.rendering import DevelopmentSensors
        calls = []
        class Camera:
            res = (4, 4)
            fov = 60.
            transform = np.eye(4)
            def render(self, **kwargs):
                calls.append(1)
                return np.zeros((4, 4, 3), dtype=np.uint8)
        world = SimpleNamespace(cameras={'test': Camera()}, physics_step=0, sim_time_s=0.)
        robot, task = SimpleNamespace(observe=lambda: {}), SimpleNamespace(observe=lambda: {})
        for factory in (SensorSuite, DevelopmentSensors):
            with self.subTest(factory=factory.__name__):
                calls.clear()
                env = Env(SimulatorConfig(task_id='cast_keyhole', variation_id='very_easy'), sensor_factory=factory)
                env._sensors = env._sensor_factory(world, robot, enable_rgb=True)
                env._task, env._episode_id, env._state_id = task, 'fixture', 0
                env.defer_rgb = True
                with patch.object(env, '_require_ready'):
                    env.observe()
                    self.assertEqual(calls, [])
                    env.sensor_frame()
                    # The developer adapter still delegates explicit captures
                    # to its separate camera-selection path.
                    self.assertEqual(len(calls), 1 if factory is SensorSuite else 0)

    def test_frozen_generation_stays_frozen_and_checks_its_image(self):
        spec = importlib.util.spec_from_file_location('tooling_frozen_check', ROOT/'ci_checks/check-topogym-tooling.py')
        checker = importlib.util.module_from_spec(spec); spec.loader.exec_module(checker)
        # A frozen generation in the repository: tooling v10 (Jianwen's simpler claws variants on 0.2.10) since v11.
        name = 'topogym-interlocked-claws-easier-i00-standard'
        with tempfile.TemporaryDirectory() as folder:
            target = Path(folder)/name
            shutil.copytree(ROOT/'tasks'/name, target)
            # A historical generation must stay valid even after the current image changes.
            with patch.object(checker, 'current_image', return_value='future-image'):
                self.assertFalse(checker.check(Path(folder))[1])
            path = target/'environment/sim/rcb_topogym.py'
            original = path.read_bytes()
            path.write_bytes(original+b'\n# tampered\n')
            self.assertTrue(checker.check(Path(folder))[1])
            path.write_bytes(original)
        # The imported remote generation keeps its pinned image: a downgrade fails.
        name = 'topogym-interlocked-claws-hard-i00-standard'
        image = checker.current_image().rsplit(':', 1)[1]
        with tempfile.TemporaryDirectory() as folder:
            target = Path(folder)/name
            shutil.copytree(ROOT/'tasks'/name, target)
            self.assertFalse(checker.check(Path(folder))[1])
            compose = target/'environment/docker-compose.yaml'
            compose.write_text(compose.read_text().replace(image, '0.2.10-cu128'))
            self.assertTrue(any('image' in error for error in checker.check(Path(folder))[1]))

    def protocol_check(self, task, *, strict=False):
        env = dict(os.environ)
        env.pop('RCB_PROTOCOL_STRICT', None)
        if strict:
            env['RCB_PROTOCOL_STRICT'] = '1'
        return subprocess.run(
            [sys.executable, str(ROOT/'ci_checks/check-protocol-v1.py'), str(task)],
            env=env, capture_output=True, text=True, timeout=20)

    def test_protocol_accepts_23_but_rejects_unknown_versions(self):
        with tempfile.TemporaryDirectory() as folder:
            task = Path(folder)/'topogym-fixture-easy-i00-standard'
            task.mkdir()
            meta = task/'task.toml'
            for version, expected in (('2.2', 0), ('2.3', 0), ('99.0', 1)):
                with self.subTest(version=version):
                    meta.write_text('[metadata]\nmode = "standard"\noracle = "full"\n'
                                    f'protocol = "eai-standard/{version}"\n')
                    result = self.protocol_check(task)
                    self.assertEqual(result.returncode, expected, result.stdout + result.stderr)

    def test_protocol_23_keeps_upstream_hard_failures(self):
        with tempfile.TemporaryDirectory() as folder:
            task = Path(folder)/'topogym-fixture-easy-i00-standard'
            task.mkdir()
            meta = task/'task.toml'
            valid = '[metadata]\nmode = "standard"\nprotocol = "eai-standard/2.3"\noracle = "full"\n'
            meta.write_text(valid.replace('oracle = "full"\n', ''))
            result = self.protocol_check(task)
            self.assertEqual(result.returncode, 1, result.stdout + result.stderr)
            self.assertIn('missing `oracle`', result.stdout)
            meta.write_text(valid)
            (task/'results').mkdir()
            result = self.protocol_check(task)
            self.assertEqual(result.returncode, 1, result.stdout + result.stderr)
            self.assertIn('results/ in a task directory', result.stdout)

    def test_protocol_frozen_instance_warns_but_strict_mode_fails(self):
        task = ROOT/'tasks/topogym-interlocked-claws-i00-limited'
        result = self.protocol_check(task)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn('legacy: TopoGym pre-v1.0 frozen instance', result.stdout)
        result = self.protocol_check(task, strict=True)
        self.assertEqual(result.returncode, 1, result.stdout + result.stderr)

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
        name = 'topogym-interlocked-claws-i00-limited'   # unversioned: the tier dirs are tooling v4 since their re-render
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
