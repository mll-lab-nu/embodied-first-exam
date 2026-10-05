#!/usr/bin/env python3
"""Identity and fail-closed contracts, without running physics or claiming success."""
from copy import deepcopy
import hashlib
import importlib.util
import json
from pathlib import Path
import subprocess
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT), str(ROOT / 'scripts')]
from topogym.simulator import frozen_binding as B
from topogym.planning.harbor_bridge import binding as manager
from topogym.planning.harbor_bridge.batch import plan, assess_job
from topogym.planning.harbor_bridge.contracts import BridgeError, instance_binding
from topogym.planning.harbor_bridge.packaging import package, check_package
from topogym.planning.harbor_bridge.runtime import require_runtime_binding, stream_standard
from topogym_versions import release, task_root

spec = importlib.util.spec_from_file_location('bridge_fixtures', ROOT / 'ci_checks/test-harbor-oracle-bridge.py')
fixtures = importlib.util.module_from_spec(spec)
spec.loader.exec_module(fixtures)


def write(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value))


class RuntimeBinding(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.task, self.instance = fixtures.fixture(self.root)
        self.tool = self.instance.parent / 'rcb_topogym.py'
        self.installed = self.root / 'installed'
        (self.installed / 'topogym').mkdir(parents=True)
        (self.installed / 'topogym/__init__.py').write_text('')
        (self.installed / 'topogym/core.py').write_text('VALUE = 1\n')
        files = {'topogym/' + k: v for k, v in B.tree_hashes(self.installed / 'topogym').items()}
        write(self.installed / 'SOURCE.json', dict(
            sha256=hashlib.sha256(json.dumps(files, sort_keys=True).encode()).hexdigest(), files=len(files)))
        self.runtime = B.installed_runtime(self.installed, check_imports=False)
        self.image = dict(reference='example:1', id='sha256:' + '0'*64, repo_digests=[])
        self.lock = manager.lock_for_task(self.task, self.image, self.runtime)

    def tearDown(self):
        self.temp.cleanup()

    def test_old_creation_source_can_bind_to_new_explicit_runtime(self):
        self.assertNotEqual(self.lock['creation_source'], self.runtime['source'])
        B.check_inputs(self.instance, self.tool, self.lock)
        with patch.object(B, 'installed_runtime', return_value=self.runtime):
            self.assertEqual(B.check_runtime(self.lock), self.runtime)
        self.assertEqual(json.loads(self.instance.read_text())['topogym_source'], self.lock['creation_source'])

    def test_hashing_actual_installed_files_detects_stale_source_metadata(self):
        (self.installed / 'topogym/core.py').write_text('VALUE = 2\n')
        with self.assertRaisesRegex(B.BindingMismatch, 'differ from SOURCE'):
            B.installed_runtime(self.installed, check_imports=False)

    def test_checkout_without_source_record_is_not_a_bound_image(self):
        (self.installed / 'SOURCE.json').unlink()
        with self.assertRaisesRegex(B.BindingMismatch, 'not a bound image'):
            B.installed_runtime(self.installed, check_imports=False)

    def test_loaded_public_module_cannot_shadow_image(self):
        code = '''import importlib.util,sys,types
from pathlib import Path
root, checker = sys.argv[1:]
sys.path.insert(0,root)
import topogym
sys.modules['topogym.world.fake'] = types.SimpleNamespace(__file__='/tmp/checkout/fake.py')
s=importlib.util.spec_from_file_location('binding',checker)
m=importlib.util.module_from_spec(s);s.loader.exec_module(m)
try:m.installed_runtime(root)
except m.BindingMismatch as error:
 assert 'outside the bound image' in str(error)
else:raise AssertionError('shadow module accepted')
'''
        child = subprocess.run([sys.executable, '-I', '-c', code, str(self.installed),
            str(ROOT / 'topogym/simulator/frozen_binding.py')], capture_output=True, text=True, timeout=30)
        self.assertEqual(child.returncode, 0, child.stderr)

    def test_instance_asset_and_tool_mutations_are_rejected(self):
        for path in (self.instance, self.tool, self.instance.parent / 'instance_assets/state.json'):
            old = path.read_bytes()
            try:
                if path == self.instance:
                    inst = json.loads(old); inst['seed'] += 1; write(path, inst)
                else:
                    path.write_bytes(old + b'changed')
                with self.subTest(path=path.name), self.assertRaises(B.BindingMismatch):
                    B.check_inputs(self.instance, self.tool, self.lock)
            finally:
                path.write_bytes(old)

    def test_asset_symlinks_fail_closed(self):
        (self.instance.parent / 'instance_assets/link').symlink_to(self.tool)
        with self.assertRaisesRegex(B.BindingMismatch, 'Symlink'):
            B.check_inputs(self.instance, self.tool, self.lock)

    def test_runtime_dependency_mismatch_is_rejected(self):
        altered = deepcopy(self.runtime); altered['dependencies']['pyuipc'] = 'wrong-build'
        with patch.object(B, 'installed_runtime', return_value=altered), self.assertRaises(B.BindingMismatch):
            B.check_runtime(self.lock)

    def test_incomplete_and_nonhex_identities_fail(self):
        for mutate in (lambda x: x.pop('runtime'), lambda x: x['image'].update(id='example:1'),
                       lambda x: x.update(tooling_sha256='z'*64)):
            bad = deepcopy(self.lock); mutate(bad)
            with self.assertRaises(B.BindingMismatch): B.validate_lock(bad)

    def test_runtime_entry_rejects_unbound_recipe_before_importing_tooling(self):
        with self.assertRaisesRegex(BridgeError, 'No runtime binding'):
            require_runtime_binding({}, self.instance, self.tool)

    def test_moved_tag_is_rejected_before_launch(self):
        changed = {**self.image, 'id': 'sha256:' + '2'*64}
        with patch.object(manager, 'inspect_image', return_value=changed), self.assertRaisesRegex(BridgeError, 'tag moved'):
            manager.check_lock_for_task(self.task, self.lock, inspect_docker=True)

    def test_derived_agent_image_must_have_identical_public_runtime(self):
        (self.task / 'environment/Dockerfile').write_text('FROM example:agent\n')
        agent_image = {**self.image, 'reference': 'example:agent', 'id': 'sha256:' + '3'*64}
        with patch.object(manager, 'inspect_image', side_effect=[self.image, agent_image]), \
                patch.object(manager, 'inspect_runtime', return_value=self.runtime):
            lock = manager.inspect_task(self.task)
        self.assertEqual(lock['agent_image'], agent_image)
        manager.check_lock_for_task(self.task, lock)
        with patch.object(manager, 'inspect_image', side_effect=[self.image, agent_image]), \
                patch.object(manager, 'inspect_runtime', side_effect=[self.runtime, {}]), \
                self.assertRaisesRegex(BridgeError, 'different simulator'):
            manager.inspect_task(self.task)

    def test_missing_image_does_not_publish_partial_catalog(self):
        output = self.root / 'bindings'
        with patch.object(manager, 'inspect_image', side_effect=BridgeError('image absent')):
            with self.assertRaisesRegex(BridgeError, 'image absent'):
                manager.bind_tasks([self.task], output)
        self.assertFalse(output.exists())

    def test_package_adds_identical_bindings_without_changing_frozen_inputs(self):
        original = instance_binding(self.instance)
        result = package(self.task, self.root / 'candidate', kind='existing', runtime_lock=self.lock)
        candidate = Path(result['task'])
        self.assertEqual(instance_binding(candidate / 'environment/instance.json'), original)
        for directory in ('environment', 'tests'):
            self.assertEqual(json.loads((candidate / directory / 'runtime_binding.json').read_text()), self.lock)
        self.assertEqual(check_package(candidate)['status'], 'passed')
        self.assertFalse(result['harbor_qualified'])
        self.assertFalse((self.task / 'environment/runtime_binding.json').exists())

    def test_unbound_package_cannot_start_formal_job(self):
        result = package(self.task, self.root / 'candidate', kind='existing')
        with self.assertRaisesRegex(BridgeError, 'Formal jobs require'):
            plan([result['task']], self.root / 'jobs', 'harbor')

    def test_generator_cannot_overwrite_an_already_bound_active_task(self):
        from topogym_mk_task import require_current_destination, TOOLING_VERSION
        (self.task / 'task.toml').write_text(f'[metadata]\ntooling_version = "{TOOLING_VERSION}"\n')
        write(self.task / 'environment/runtime_binding.json', self.lock)
        with self.assertRaisesRegex(ValueError, 'already has a frozen runtime binding'):
            require_current_destination(self.task)

    def test_preflight_plan_is_exact_load_only_and_uses_image_id(self):
        lock_file = self.root / 'runtime.json'; write(lock_file, self.lock)
        with patch.object(manager.subprocess, 'run', side_effect=AssertionError('planning launched a process')):
            result = manager.preflight(self.task, lock_file, self.root / 'preflight')
        self.assertEqual(result['status'], 'planned')
        self.assertIn(self.image['id'], result['command'])
        self.assertNotIn(self.image['reference'], result['command'])
        self.assertFalse((self.root / 'preflight/startup.json').exists())

    def test_standard_refuses_wrong_service_binding_before_submitting(self):
        robot = SimpleNamespace(spec=lambda: dict(instance_binding_id='wrong'))
        with self.assertRaisesRegex(BridgeError, 'binding'):
            stream_standard(robot, dict(runtime_binding=self.lock, binding=instance_binding(self.instance)), [])

    def test_standard_grader_requires_both_exact_runtime_receipts(self):
        source = (ROOT / 'harbor_templates/topogym/limited/tests/grade.py').read_text()
        for fault in (None, 'startup', 'replay', 'not_exact', 'missing'):
            folder = self.root / str(fault); folder.mkdir()
            write(folder / 'final.json', dict(finalized=True, success=True, replay_success=True,
                                             instance_matches=True, deterministic=True))
            (folder / 'trajectory.npz').write_bytes(b'fixture-only')
            write(folder / 'runtime_binding.json', self.lock)
            for name in ('startup_binding.json', 'replay.verdict.json'):
                row = dict(instance_exact=True, runtime_binding=dict(binding_id=B.binding_id(self.lock)))
                if (fault == 'startup' and name.startswith('startup')) or (fault == 'replay' and name.startswith('replay')):
                    row['runtime_binding']['binding_id'] = 'wrong'
                if fault == 'not_exact': row['instance_exact'] = False
                if fault != 'missing': write(folder / name, row)
            code = source.replace('/data/', str(folder) + '/').replace('/tests/', str(folder) + '/')
            code = code.replace('/logs/verifier', str(folder / 'verifier'))
            exec(compile(code, 'standard_grade', 'exec'), {})
            reward = json.loads((folder / 'verifier/reward.json').read_text())
            self.assertEqual(reward['success'], int(fault is None))
            self.assertEqual(reward['runtime_binding_ok'], int(fault is None))

    def test_success_score_without_binding_is_not_accepted(self):
        path = self.root / 'job/trial/result.json'
        row = dict(finished_at='now', verifier_result=dict(rewards=dict(success=1)))
        write(path, row)
        self.assertEqual(assess_job(path.parent.parent, 'oracle', 0)['status'], 'unbound_result')
        row['verifier_result']['rewards'].update(runtime_binding_ok=1, instance_exact=1)
        write(path, row)
        self.assertEqual(assess_job(path.parent.parent, 'oracle', 0)['status'], 'expected_score')


class ReleaseSelection(unittest.TestCase):
    def test_active_unbuilt_release_never_falls_back_to_published(self):
        self.assertEqual(release(ROOT)['tooling_version'], '16')
        self.assertEqual(release(ROOT, 'published')['tooling_version'], '14')
        with self.assertRaisesRegex(ValueError, 'no frozen task tree'):
            task_root(ROOT)

    def test_all_published_three_tier_twins_share_the_same_instance(self):
        tasks = manager.selected_tasks(selection='published')
        self.assertEqual(len(tasks), 78)
        families = set()
        for task in tasks:
            if task.name.endswith('-standard'): continue
            standard = task.with_name(task.name.removesuffix('-privileged') + '-standard')
            instance = task / 'environment/instance.json'
            self.assertEqual(instance_binding(instance), instance_binding(standard / 'environment/sim/instance.json'))
            self.assertEqual(instance_binding(instance), instance_binding(task / 'tests/instance.json'))
            families.add(json.loads(instance.read_text())['task'])
        self.assertEqual(len(families), 13)


if __name__ == '__main__':
    unittest.main()
