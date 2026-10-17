"""Missing evidence must never widen release admission."""
import importlib.util
import json
from pathlib import Path
import tempfile
import unittest

path = Path(__file__).resolve().parents[1] / 'import_admission.py'
spec = importlib.util.spec_from_file_location('admission_import', path)
M = importlib.util.module_from_spec(spec)
spec.loader.exec_module(M)


class AdmissionImportTests(unittest.TestCase):
    def test_camera_gap_holds_member_and_seed_is_not_guessed(self):
        index = {'a': {'rsb':'family', 'robot':'tidybot', 'instances':{
            'i00':{'member':'benign','cameras':'room'}, 'i01':{'member':'benign','cameras':'onboard'}}}}
        room = {'family':'family','robot':'tidybot','member':'benign','seed':2,'cameras':'room',
                'native_record':'record.json','native_sha256':'test'}
        got = M.build_families(index, [room], 'tidybot', {'family'})['family']
        self.assertFalse(got['ok'])
        got = M.build_families(index, [room,{**room,'cameras':'onboard'}], 'tidybot', {'family'})['family']
        self.assertEqual(got['allowed_seeds'], {'benign':[2]})

    def test_stale_commit_and_missing_native_gate_are_rejected(self):
        commit = 'a' * 40
        row = {'family':'family','robot':'ur5e_2f85','member':'hazard','seed':0,
            'interface':'control','source_commit':commit,'all_required_gates':True,
            'reference_pass':True,'allowed_in_frozen_tree':True,'native_record':'native.json'}
        native = {g:True for g in M.REQUIRED_GATES}
        native.update(source_commit=commit,admitted=True,cases=[{'strategy':'reference','pass':True,
            'key':{k:row[k] for k in ('family','robot','member','seed','interface')}}])
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            (root/'native.json').write_text(json.dumps(native))
            self.assertEqual(len(M.accepted_rows([row], commit, root)), 1)
            self.assertEqual(M.accepted_rows([{**row,'member':'benign'}],commit,root), [])
            self.assertEqual(M.accepted_rows([{**row,'source_commit':'b'*40}],commit,root), [])
            del native['damage_reference']
            (root/'native.json').write_text(json.dumps(native))
            self.assertEqual(M.accepted_rows([row],commit,root), [])

    def test_installed_image_identity_and_provenance_are_required(self):
        commit, image = 'a' * 40, 'b' * 64
        row = {'family':'family','robot':'ur5e_2f85','member':'hazard','seed':0,
            'interface':'control','source_commit':commit,'all_required_gates':True,
            'reference_pass':True,'allowed_in_frozen_tree':True,'native_record':'native.json'}
        native = {g:True for g in M.REQUIRED_GATES}
        native.update(source_commit=commit,admitted=True,image_id=image,image_revision_label=commit,
            installed_package_only=True,package_path='/usr/local/lib/python3.11/site-packages/robosafebench/__init__.py',
            process_environment={'PYTHONPATH':''},status='complete',expected_member_tiers=[{'member':'hazard','evidence':None}],
            cases=[{'strategy':'reference','pass':True,
                'key':{k:row[k] for k in ('family','robot','member','seed','interface')}}])
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            (root/'native.json').write_text(json.dumps(native))
            self.assertEqual(len(M.accepted_rows([row],commit,root,'sha256:'+image)),1)
            self.assertEqual(M.accepted_rows([row],commit,root,'c'*64),[])
            native['process_environment']['PYTHONPATH'] = '/source-overlay'
            (root/'native.json').write_text(json.dumps(native))
            self.assertEqual(M.accepted_rows([row],commit,root,image),[])
            native['process_environment']['PYTHONPATH'] = ''
            native['provenance_matches'] = False
            (root/'native.json').write_text(json.dumps(native))
            self.assertEqual(M.accepted_rows([row],commit,root,image),[])

    def test_source_prefix_requires_seven_characters(self):
        self.assertFalse(M.same_commit('a'*40, 'a'))
        self.assertFalse(M.same_commit('a'*40, None))


if __name__ == '__main__':
    unittest.main()
