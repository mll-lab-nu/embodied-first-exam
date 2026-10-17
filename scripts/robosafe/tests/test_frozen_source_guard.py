"""Changing the registry pin cannot publish old instances or unrelated oracle rows."""
import hashlib
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import gen_tasks as G
import gen_realtime as R


class FrozenSourceGuardTests(unittest.TestCase):
    def setUp(self):
        self.folder = tempfile.TemporaryDirectory()
        self.root = Path(self.folder.name)
        self.commit,self.version = 'a'*40,'0.5.4.dev1'
        self.registry = {'robosafebench_commit':self.commit,'robosafebench_version':self.version,
            'families':{'a01':{'rsb':'family','robot':'ur5e_2f85','instances':{'i00':{'member':'hazard','seed':0}}}}}
        self.key = dict(family='family',robot='ur5e_2f85',member='hazard',seed=0,interface='control')
        self.instance = dict(key=self.key,state_sha='start',robosafebench_commit=self.commit,robosafebench_version=self.version)
        self.oracle = dict(instance_key=self.key,start_sha='start',robosafebench_commit=self.commit,robosafebench_version=self.version,
            result={'pass':True},nop={'pass':False},done_at_once={'pass':False},arrays=[])
        self.write('families.json',self.registry)
        self.write('instances/a01-i00.json',self.instance)
        self.write('oracles/a01-i00.json',self.oracle)
        self.patch_g = patch.object(G,'HERE',self.root);self.patch_g.start()
        self.patch_r = patch.object(R,'HERE',self.root);self.patch_r.start()

    def tearDown(self):
        self.patch_g.stop();self.patch_r.stop();self.folder.cleanup()

    def write(self,name,value):
        path = self.root/name;path.parent.mkdir(parents=True,exist_ok=True)
        path.write_text(json.dumps(value))

    def test_current_pin_does_not_upgrade_old_source_or_version(self):
        self.assertIsNone(G._own_fault('a01','i00'))
        self.write('instances/a01-i00.json',{**self.instance,'robosafebench_commit':'b'*40})
        self.assertIn('another simulator source',G._own_fault('a01','i00'))
        self.write('instances/a01-i00.json',{**self.instance,'robosafebench_version':'0.5.3'})
        self.assertIn('another simulator version',G._own_fault('a01','i00'))

    def test_matching_seed_is_required_for_both_instance_and_oracle(self):
        self.write('instances/a01-i00.json',{**self.instance,'key':{**self.key,'seed':1}})
        self.assertIn('registry member or seed',G._own_fault('a01','i00'))
        self.write('instances/a01-i00.json',self.instance)
        self.write('oracles/a01-i00.json',{**self.oracle,'instance_key':{**self.key,'seed':1}})
        self.assertIn('oracle belongs',G._own_fault('a01','i00'))

    def test_old_oracle_requires_matching_checksummed_external_identity(self):
        old = {k:v for k,v in self.oracle.items() if k not in ('instance_key','start_sha','robosafebench_commit','robosafebench_version')}
        self.write('oracles/a01-i00.json',old)
        self.assertIn('no recorded matching',G._own_fault('a01','i00'))
        proof = {k:self.oracle[k] for k in ('instance_key','start_sha','robosafebench_commit','robosafebench_version')}
        proof.update(instance_sha256=hashlib.sha256((self.root/'instances/a01-i00.json').read_bytes()).hexdigest(),
            oracle_sha256=hashlib.sha256((self.root/'oracles/a01-i00.json').read_bytes()).hexdigest())
        self.write('oracle_provenance/a01-i00.json',proof)
        self.assertIsNone(G._own_fault('a01','i00'))
        self.write('oracles/a01-i00.json',{**old,'plan':['another-row']})
        self.assertIn('checksum mismatch',G._own_fault('a01','i00'))

    def test_realtime_requires_current_standard_and_matching_own_identity(self):
        instance = {**self.instance,'key':{**self.key,'clock':'realtime'},'state_sha':'rt-start'}
        oracle = {**self.oracle,'instance_key':instance['key'],'start_sha':'rt-start'}
        self.write('instances_rt/a01-i00.json',instance)
        self.write('oracles_rt/a01-i00.json',oracle)
        self.assertIsNone(R.rt_fault('a01','i00'))
        self.write('oracles_rt/a01-i00.json',{**oracle,'robosafebench_commit':'b'*40})
        self.assertIn('another frozen instance or source',R.rt_fault('a01','i00'))


if __name__ == '__main__': unittest.main()
