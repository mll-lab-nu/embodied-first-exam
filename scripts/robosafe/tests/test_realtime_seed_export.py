"""Public realtime seeds stay isolated and cannot reuse another seed's oracle or admission."""
import json
import hashlib
from pathlib import Path
import sys
import tempfile
import types
import unittest
from unittest.mock import patch

HERE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(HERE))
import gen_realtime as R
import make_rt_instances as M


class RealtimeSeedExportTests(unittest.TestCase):
    def test_fr3_revealed_label_readmission_preserves_other_holds(self):
        self.assertTrue(M.serves('fr3_2f85','d_label_revealed'))
        self.assertEqual(len(M.REALTIME_ROBOT_FAMILIES['fr3_2f85']),9)
        self.assertFalse(M.serves('fr3_2f85','d_pan_smoke'))
        self.assertFalse(M.serves('fr3_2f85','d_pot_boils_over'))
        self.assertIn(('d_hand_enters','hazard',1,'fr3_2f85'),M.REALTIME_KEY_HELD)
        self.assertIn(('a_pet_appliance','hazard_hidden/closer','fr3_2f85'),M.REALTIME_HIDDEN_HELD)

    def test_fr3_readmission_proof_pins_all_six_full_gate_records(self):
        root = HERE/'admission_evidence'
        proof = json.loads((root/'fr3_c02_r3_paired17_proof.json').read_text())
        for clock in ('paused','realtime'):
            runs = proof['clocks'][clock]['runs']
            self.assertEqual({r['seed'] for r in runs},{0,1,2})
            for row in runs:
                data = (root/row['path']).read_bytes()
                self.assertEqual(hashlib.sha256(data).hexdigest(),row['sha256'])
                native = json.loads(data)
                self.assertEqual(native['image_id'],proof['image_id'])
                self.assertEqual(native['source_commit'],proof['source_commit'])
                self.assertTrue(native['admitted'])
                self.assertTrue(all(native[gate] is True for gate in proof['required_checks']))

    def test_explicit_seed_selects_its_hold_instead_of_canonical_seed(self):
        fam={'rsb':'d_hand_enters','robot':'fr3_2f85',
             'instances':{'i00':{'member':'hazard','seed':0}}}
        for held in (R.hidden_held,M.rt_hidden_held):
            self.assertIsNone(held(fam,'i00'))
            self.assertIn('seed-1',held(fam,'i00',1))
            self.assertIsNone(held(fam,'i00',2))

    def test_seed_plan_requires_corresponding_standard_and_realtime_oracle(self):
        slug,nn='c01','i00'
        if 'robosafebench_commit' not in json.loads((HERE/'instances_rt'/f'{slug}-{nn}.json').read_text()):
            self.skipTest('c01-i00 is a 0.5.3 instance in this release (robosafe_commit): no 0.5.4 pair to render')
        family=json.loads((HERE/'families.json').read_text())['families'][slug]
        std=json.loads((HERE/'instances'/f'{slug}-{nn}.json').read_text())
        inst=json.loads((HERE/'instances_rt'/f'{slug}-{nn}.json').read_text())
        oracle=json.loads((HERE/'oracles'/f'{slug}-{nn}.json').read_text())
        ort=json.loads((HERE/'oracles_rt'/f'{slug}-{nn}.json').read_text())
        std['key']['seed']=inst['key']['seed']=1
        std['robosafebench_commit']=inst['robosafebench_commit']
        std['robosafebench_version']=inst['robosafebench_version']
        oracle.update(plan=[{'type':'decline','row':[],'text':'seed-one-only'}],arrays=[])
        ort.update(instance_key=inst['key'],start_sha=inst['state_sha'],robosafebench_commit=inst['robosafebench_commit'],
            robosafebench_version=inst['robosafebench_version'])
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder)
            (root/'make_rt_instances.py').write_text((HERE/'make_rt_instances.py').read_text())
            for sub,obj in (('instances',std),('instances_rt',inst),('oracles',oracle),('oracles_rt',ort)):
                path=root/'seeds/1'/sub/f'{slug}-{nn}.json';path.parent.mkdir(parents=True,exist_ok=True)
                path.write_text(json.dumps(obj))
            with patch.object(R,'HERE',root),patch.object(R.G,'files_of',return_value={}):
                files=R.plan(slug,family,nn,'0.5.4',seed=1)[R.task_dir(slug,nn)]
                self.assertEqual(json.loads(files['environment/sim/instance.json'][0])['key']['seed'],1)
                self.assertEqual(json.loads(files['solution/oracle.json'][0])['plan'],oracle['plan'])
                ort['robosafebench_commit']='another-candidate'
                (root/'seeds/1/oracles_rt'/f'{slug}-{nn}.json').write_text(json.dumps(ort))
                with self.assertRaisesRegex(RuntimeError,'another frozen instance or source'):
                    R.plan(slug,family,nn,'0.5.4',seed=1)
                std['key']['seed']=0
                (root/'seeds/1/instances'/f'{slug}-{nn}.json').write_text(json.dumps(std))
                with self.assertRaisesRegex(RuntimeError,'frozen seed'):
                    R.plan(slug,family,nn,'0.5.4',seed=1)

    def test_freeze_rejects_misfiled_standard_seed_before_running_simulator(self):
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder);path=root/'seeds/1/instances/c01-i00.json'
            path.parent.mkdir(parents=True);path.write_text(json.dumps({'key':{'seed':0}}))
            with patch.object(M,'HERE',root),patch.dict(sys.modules,{'numpy':types.SimpleNamespace()}):
                with self.assertRaisesRegex(RuntimeError,'standard seed'):
                    M.one_task('c01','i00',False,folder,seed=1)

    def test_seed_cannot_overwrite_canonical_task_directory(self):
        with patch.object(sys,'argv',['gen_realtime.py','render','--seed','1']):
            with self.assertRaisesRegex(SystemExit,'elsewhere than tasks'):
                R.main()


if __name__=='__main__':unittest.main()
