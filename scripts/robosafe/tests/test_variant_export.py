"""Request variants keep separate allocation, fresh proof, source and oracle identity."""
import copy
import hashlib
import importlib.util
import json
from pathlib import Path
import sys
import tempfile
import types
import unittest
from unittest.mock import patch

HERE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(HERE))


def module(name):
    spec = importlib.util.spec_from_file_location('variant_' + name, HERE / (name + '.py'))
    out = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(out)
    return out


M, G, F = module('import_admission'), module('gen_tasks'), module('make_instances')
COMMIT, IMAGE = 'a' * 40, 'b' * 64


class VariantExportTests(unittest.TestCase):
    def raw(self):
        key = dict(family='family', robot='ur5e_2f85', member='hazard', seed=0, interface='control', variant='goal')
        row = {**key, 'source_commit': COMMIT, 'image_id': IMAGE, 'provenance_matches': True, 'all_required_gates': True, 'reference_pass': True,
               'allowed_in_frozen_tree': True, 'native_record': 'native.json'}
        native = {g: True for g in M.REQUIRED_GATES}
        native.update(source_commit=COMMIT, admitted=True, image_id=IMAGE, image_revision_label=COMMIT,
            installed_package_only=True, package_path='/usr/local/lib/python3.11/site-packages/robosafebench/__init__.py',
            process_environment={'PYTHONPATH': ''}, variant='goal', status='complete',
            expected_member_tiers=[{'member': 'hazard', 'evidence': None}, {'member': 'benign', 'evidence': None}],
            expected_variant_members=['hazard'],
            variant_scope={'schema': 1, 'variant_members': ['hazard'], 'control_members': ['benign']},
            cases=[{'strategy': 'reference', 'pass': True, 'key': key, 'admission_variant': 'goal', 'admission_control': False},
                   {'strategy': 'reference', 'pass': True, 'key': {**key, 'member': 'benign', 'variant': None},
                    'admission_variant': 'goal', 'admission_control': True}])
        return row, native

    def test_import_never_relabels_variant_controls_as_default_admission(self):
        row, native = self.raw()
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            (root / 'native.json').write_text(json.dumps(native))
            self.assertEqual(len(M.accepted_rows([row], COMMIT, root, IMAGE, 'goal')), 1)
            self.assertEqual(M.accepted_rows([row], COMMIT, root, IMAGE), [])
            control = {**row, 'member': 'benign', 'variant': None}
            self.assertEqual(M.accepted_rows([control], COMMIT, root, IMAGE), [])
            self.assertEqual(M.accepted_rows([row], COMMIT, root, IMAGE, 'early'), [])
            self.assertEqual(M.accepted_rows([row], COMMIT, root, None, 'goal'), [])
            wrong = copy.deepcopy(native); wrong['cases'].pop()
            (root / 'native.json').write_text(json.dumps(wrong))
            self.assertEqual(M.accepted_rows([row], COMMIT, root, IMAGE, 'goal'), [])
            wrong = copy.deepcopy(native); wrong.pop('variant')
            (root / 'native.json').write_text(json.dumps(wrong))
            self.assertEqual(M.accepted_rows([control], COMMIT, root, IMAGE), [])
            native['cases'][1]['key']['variant'] = 'goal'
            (root / 'native.json').write_text(json.dumps(native))
            self.assertEqual(M.accepted_rows([row], COMMIT, root, IMAGE, 'goal'), [])

    def test_default_and_goal_have_independent_member_seed_sets(self):
        index = {'f01': {'rsb': 'family', 'robot': 'ur5e_2f85', 'instances': {
            'i00': {'member': 'hazard'}, 'i01': {'member': 'hazard', 'variant': 'goal'}}}}
        row, _ = self.raw()
        row['native_sha256'] = 'checksum'
        default = M.build_families(index, [row], 'ur5e_2f85', {'family'})['family']
        goal = M.build_families(index, [row], 'ur5e_2f85', {'family'}, 'goal')['family']
        self.assertFalse(default['ok'])
        self.assertEqual(goal['allowed_seeds'], {'hazard': [0]})
        self.assertEqual(goal['variant'], 'goal')

    def test_combined_default_schema_requires_complete_actual_image_scope(self):
        row, native = self.raw()
        row.pop('allowed_in_frozen_tree')
        row['variant'] = None
        native['variant'] = None
        native['expected_variant_members'] = []
        native.pop('variant_scope')
        for case in native['cases']:
            case['key']['variant'] = None
            case.pop('admission_variant'); case.pop('admission_control')
        with tempfile.TemporaryDirectory() as td:
            root = Path(td); path = root / 'native.json'
            path.write_text(json.dumps(native))
            self.assertEqual(len(M.accepted_rows([row], COMMIT, root, IMAGE)), 1)
            native['cases'].pop()
            path.write_text(json.dumps(native))
            self.assertEqual(M.accepted_rows([row], COMMIT, root, IMAGE), [])

    def test_generator_requires_exact_variant_and_current_source(self):
        fam = {'rsb': 'family'}
        member = {'member': 'hazard', 'variant': 'goal'}
        goal = {'ok': True, 'variant': 'goal', 'candidate_source_commit': COMMIT,
                'allowed_seeds': {'hazard': [0]}, 'candidate_image_id': IMAGE, 'clock': 'paused'}
        with tempfile.TemporaryDirectory() as td, patch.object(G, 'HERE', Path(td)):
            (Path(td) / 'families.json').write_text(json.dumps({'robosafebench_commit': COMMIT}))
            self.assertFalse(G.family_admission({'family': {'ok': True}}, fam, member))
            adm = {'family': {'ok': False, 'variants': {'goal': goal}}}
            self.assertTrue(G.family_admission(adm, fam, member)['ok'])
            bad = copy.deepcopy(adm); bad['family']['variants']['goal']['candidate_source_commit'] = 'c' * 40
            self.assertFalse(G.family_admission(bad, fam, member))
            self.assertFalse(G.family_admission(adm, fam, {**member, 'variant': 'early'}))
            bad = copy.deepcopy(adm); bad['family']['variants']['goal'].pop('candidate_image_id')
            self.assertFalse(G.family_admission(bad, fam, member))

    def test_new_default_admission_pin_cannot_move_to_another_candidate(self):
        family = {'rsb': 'family', 'robot': 'ur5e_2f85'}
        member = {'member': 'hazard', 'seed': 0}
        entry = {'ok': True, 'candidate_source_commit': COMMIT, 'candidate_image_id': IMAGE,
                 'allowed_seeds': {'hazard': [0]}, 'clock': 'paused'}
        with tempfile.TemporaryDirectory() as td, patch.object(G, 'HERE', Path(td)), patch.object(F, 'HERE', Path(td)):
            root = Path(td)
            (root / 'families.json').write_text(json.dumps({'robosafebench_commit': COMMIT}))
            (root / 'admission_ur5e_2f85.json').write_text(json.dumps({'families': {'family': entry}}))
            self.assertTrue(G.family_admission({'family': entry}, family, member)['ok'])
            self.assertTrue(F.served(family, member, commit=COMMIT, image_id=IMAGE))
            self.assertFalse(F.served(family, member, commit='c' * 40, image_id=IMAGE))
            self.assertFalse(F.served(family, member, commit=COMMIT, image_id='c' * 64))
            self.assertFalse(F.served(family, {**member, 'seed': 1}, commit=COMMIT, image_id=IMAGE))
            for missing in ('candidate_source_commit', 'candidate_image_id', 'clock'):
                wrong = {k: v for k, v in entry.items() if k != missing}
                self.assertFalse(G.family_admission({'family': wrong}, family, member))
            (root / 'families.json').write_text(json.dumps({'robosafebench_commit': 'c' * 40}))
            self.assertFalse(G.family_admission({'family': entry}, family, member))
            self.assertFalse(G.family_admission({'family': {'ok': True}}, family, member))

    def test_realtime_admission_does_not_borrow_paused_reference_or_certificate(self):
        row, native = self.raw()
        row['clock'] = 'realtime'
        for case in native['cases']:
            case['key']['clock'] = 'realtime'
        with tempfile.TemporaryDirectory() as td, patch.object(G, 'HERE', Path(td)):
            root = Path(td); (root / 'native.json').write_text(json.dumps(native))
            (root / 'families.json').write_text(json.dumps({'robosafebench_commit': COMMIT}))
            self.assertEqual(M.accepted_rows([row], COMMIT, root, IMAGE, 'goal'), [])
            self.assertEqual(len(M.accepted_rows([row], COMMIT, root, IMAGE, 'goal', 'realtime')), 1)
            member = {'member': 'hazard', 'variant': 'goal'}
            goal = {'ok': True, 'variant': 'goal', 'clock': 'paused',
                    'candidate_source_commit': COMMIT, 'candidate_image_id': IMAGE}
            admission = {'family': {'variants': {'goal': goal}}}
            self.assertFalse(G.family_admission(admission, {'rsb': 'family'}, member, clock='realtime'))
            goal['clocks'] = {'realtime': {**goal, 'clock': 'realtime'}}
            self.assertTrue(G.family_admission(admission, {'rsb': 'family'}, member, clock='realtime')['ok'])
            native['cases'][1]['key']['clock'] = 'paused'
            (root / 'native.json').write_text(json.dumps(native))
            self.assertEqual(M.accepted_rows([row], COMMIT, root, IMAGE, 'goal', 'realtime'), [])

    def test_actual_image_proof_binds_frozen_bytes_and_cannot_relabel_old_images(self):
        instance = {'key': {'family': 'family', 'member': 'hazard'}, 'state_sha': 'start',
                    'robosafebench_commit': COMMIT}
        oracle = {'arrays': []}
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            for name in ('instances', 'oracles', 'image_provenance'):
                (root / name).mkdir()
            for name, value in (('instances', instance), ('oracles', oracle)):
                (root / name / 'f01-i00.json').write_text(json.dumps(value))
            self.assertIn('no matching', G.frozen_image_fault(root, 'f01', 'i00', instance, oracle, IMAGE))
            proof = {'schema': 1, 'image_id': IMAGE, 'source_commit': COMMIT,
                'instance_key': instance['key'], 'start_sha': 'start', 'native_source_overlay': False,
                'instance_sha256': hashlib.sha256((root / 'instances/f01-i00.json').read_bytes()).hexdigest(),
                'oracle_sha256': hashlib.sha256((root / 'oracles/f01-i00.json').read_bytes()).hexdigest()}
            (root / 'image_provenance/f01-i00.json').write_text(json.dumps(proof))
            self.assertIsNone(G.frozen_image_fault(root, 'f01', 'i00', instance, oracle, IMAGE))
            self.assertIn('another candidate', G.frozen_image_fault(root, 'f01', 'i00', instance, oracle, 'c' * 64))
            (root / 'oracles/f01-i00.json').write_text(json.dumps({'arrays': [], 'plan': ['different']}))
            self.assertIn('checksum', G.frozen_image_fault(root, 'f01', 'i00', instance, oracle, IMAGE))
            instance['robosafebench_image_id'] = 'c' * 64
            self.assertIn('another or unknown', G.frozen_image_fault(root, 'f01', 'i00', instance, oracle, IMAGE))

    def test_variant_registry_cannot_use_a_default_frozen_instance_or_oracle(self):
        member = {'member': 'hazard', 'seed': 0, 'variant': 'goal'}
        key = {'family': 'family', 'member': 'hazard', 'robot': 'ur5e_2f85', 'seed': 0, 'interface': 'control'}
        registry = {'robosafebench_commit': COMMIT, 'robosafebench_version': '0.5.4',
                    'families': {'f01': {'rsb': 'family', 'robot': 'ur5e_2f85', 'instances': {'i00': member}}}}
        instance = {'key': key, 'robosafebench_commit': COMMIT, 'robosafebench_version': '0.5.4', 'state_sha': 'state'}
        with tempfile.TemporaryDirectory() as td, patch.object(G, 'HERE', Path(td)):
            root = Path(td); (root / 'instances').mkdir()
            (root / 'families.json').write_text(json.dumps(registry))
            p = root / 'instances/f01-i00.json'
            p.write_text(json.dumps(instance))
            self.assertIn('key', G.frozen_source_fault('f01', 'i00'))
            instance['key'] = {**key, 'variant': 'goal'}; p.write_text(json.dumps(instance))
            self.assertIsNone(G.frozen_source_fault('f01', 'i00'))
            oracle = {'instance_key': key, 'start_sha': 'state', 'robosafebench_commit': COMMIT, 'robosafebench_version': '0.5.4'}
            self.assertIn('another frozen instance', G.oracle_identity_fault(root, 'f01', 'i00', instance, oracle))

    def test_selection_preserves_default_ids_and_allocates_independent_variant_ids(self):
        fam = types.SimpleNamespace(track='G', title='fixture', domain='test', hazard_class='test',
            response='leave_step', robots=(F.ROBOT,), members=('hazard_embedded', 'benign'),
            variants=lambda member: ('early', 'goal') if member == 'hazard_embedded' else (), evidence_levels=lambda member: ())
        fake = types.ModuleType('robosafebench')
        fake.families = types.SimpleNamespace(registry=lambda: {'g_embed_powerbank': fam})
        with patch.dict(sys.modules, {'robosafebench': fake}):
            before = F.selection()
            after = F.selection(variants=['early', 'goal'])
            additions = []
            for slug, family in before.items():
                for nn, key in family['instances'].items():
                    self.assertEqual(after[slug]['instances'][nn], key)
                additions += [key for key in after[slug]['instances'].values() if key.get('variant')]
            self.assertTrue(additions)
            self.assertTrue(all(key['variant'] in ('early', 'goal') for key in additions))
            with tempfile.TemporaryDirectory() as td, patch.object(F, 'HERE', Path(td)):
                (Path(td) / 'families.json').write_text(json.dumps({'families': after}))
                self.assertEqual(after, F.selection())

    def test_pruned_image_text_helper_is_checksummed_without_native_source_overlay(self):
        fake = types.ModuleType('robosafebench'); fake.__path__ = []
        with tempfile.TemporaryDirectory() as td:
            helper = Path(td) / 'prompts.py'
            helper.write_text('def task_brief(*args): return ' + repr(F.END_SENTENCE) + '\n')
            env = {'RCB_RSB_FREEZE_PROMPTS': str(helper), 'RCB_RSB_FREEZE_PROMPTS_SHA256': 'wrong'}
            with patch.dict(sys.modules, {'robosafebench': fake, 'robosafebench.harness': None}), patch.dict(__import__('os').environ, env):
                with self.assertRaisesRegex(RuntimeError, 'checksummed'):
                    F.task_text(None, None)
                with patch.dict(__import__('os').environ, {'RCB_RSB_FREEZE_PROMPTS_SHA256': hashlib.sha256(helper.read_bytes()).hexdigest()}):
                    self.assertEqual(F.task_text(None, None), F.EXIT_SENTENCE)


if __name__ == '__main__':
    unittest.main()
