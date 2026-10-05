#!/usr/bin/env python3
"""Helper acceptance contracts: synthetic files/Harbor/Hub, no physical/model claims."""
from __future__ import annotations
from contextlib import redirect_stdout
import copy
import gzip
import hashlib
import io
import json
import os
from pathlib import Path
import subprocess
import shutil
import sys
import tarfile
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch, Mock
import zipfile

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'scripts'))
import helper_assignment as assignment
import helper_bundle as bundle
import helper_import as receiver
import difficulty_eval as evaluation
import difficulty_results_hf as hf
import helper_upload
import secret_scan as scanner
from trial_task_paths import original_task

SECRET='SYNTHETIC_CREDENTIAL_FOR_HELPER_CONTRACT_0123456789'

class Fixture(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory(); self.base=Path(self.temp.name)
        self.work=self.base/'helper-work'; self.batch='helper-contract'; self.run=self.work/'runs/difficulty_trials'/self.batch
        self.jobs=self.work/'jobs/difficulty_trials'/self.batch; self.run.mkdir(parents=True); self.jobs.mkdir(parents=True)
        self.sample=dict(task_id='cast_coil',task_number=8,difficulty='easy',sample_id='s00',slug='topogym-cast-coil-easy-s00',
                         scene_seed=3,evaluable_for_task_success=True)
        self.sample['sample_sha256']=assignment.digest(self.sample)
        source=dict(files={'scripts/frozen.py':'a'*64},git_head='test')
        source['sha256']=assignment.digest(source['files'])
        self.manifest=dict(schema_version=2,instances=[self.sample],instance_count=1,trial_count=2,
                           source_sha256=source['sha256'],release={'name':'synthetic'},settings={'agent_wall_clock_s':60,'concurrency':1},
                           trials=[dict(task_id='cast_coil',difficulty='easy',sample_id='s00',mode=m,trial_id=assignment.stem(self.sample,m)) for m in assignment.MODES])
        self.manifest['manifest_sha256']=assignment.digest(self.manifest)
        self.agent=dict(provider='openai',agent='codex',model='openai/contract-model',agent_args=['version=0.157.0','reasoning_effort=xhigh'],auth_methods=['api-key','subscription'])
        self.dispatch=dict(schema_version=1,format='topogym-helper-assignment',batch=self.batch,helper={'id':'tester'},
                           source={'commit':'test','repository':'synthetic'},manifest=self.manifest,agent=self.agent,cuda_flavor='cu128',
                           mirror='optional',upload={'type':'shared-folder'})
        self.save_dispatch()
        assignment.atomic_json(self.run/'manifest.lock.json',self.manifest)
        assignment.atomic_json(self.run/'source_identity.json',source)
        assignment.atomic_json(self.run/'execution.lock.json',{k:v for k,v in self.agent.items() if k!='auth_methods'}|{'auth':'api-key'})
        self.task_files={}
        for mode in assignment.MODES:
            task=self.run/'tasks'/(self.sample['slug']+('-standard' if mode=='limited' else '-privileged'))
            task.mkdir(parents=True); (task/'instruction.md').write_text('Synthetic fixed task.\n')
            assignment.atomic_json(task/'task_release.json',{'release':{'name':'synthetic'}})
            for p in task.iterdir(): self.task_files[p.relative_to(self.run).as_posix()]=scanner.sha(p)
            job=self.jobs/(assignment.stem(self.sample,mode)+'-a001'); trial=job/'truncated__abc'
            (trial/'agent').mkdir(parents=True); (trial/'artifacts/app/output').mkdir(parents=True); (trial/'verifier').mkdir()
            (trial/'agent/log.txt').write_text('Credential='+SECRET+'\n')
            (trial/'artifacts/app/output/gen.py').write_text('raise RuntimeError("must never execute on import")\n')
            reward={'success':0,'finalized':1}
            assignment.atomic_json(trial/'verifier/reward.json',reward)
            assignment.atomic_json(trial/'result.json',dict(task_name='topogym/'+task.name,task_id={'path':'/foreign-helper/tasks/'+task.name},
                finished_at='2026-10-04T00:00:00Z',verifier_result={'rewards':reward}))
        assignment.atomic_json(self.run/'build'/self.sample['slug']/'prepared.json',{'files':self.task_files})
        assignment.atomic_json(self.run/'build'/self.sample['slug']/'preflight.ok.json',{'passed':True})
        self.output=redirect_stdout(io.StringIO()); self.output.__enter__()
    def tearDown(self): self.output.__exit__(None,None,None); self.temp.cleanup()
    def save_dispatch(self):
        self.dispatch.pop('assignment_sha256',None); self.dispatch['assignment_sha256']=assignment.digest(self.dispatch)
        assignment.atomic_json(self.run/'assignment.json',self.dispatch)
    def export(self): return bundle.export_bundle(self.work,self.batch,{'TEST_KEY':SECRET.encode()})

class ScannerTests(unittest.TestCase):
    def test_exit_codes_and_default_openai(self):
        with tempfile.TemporaryDirectory() as td:
            root=Path(td); target=root/'record.txt'; target.write_text(SECRET)
            env={'PATH':os.environ['PATH'],'OPENAI_API_KEY':SECRET}
            command=[sys.executable,str(ROOT/'scripts/scan_secrets.py'),str(target),'--process-env']
            found=subprocess.run(command,env=env,capture_output=True,text=True)
            self.assertEqual(found.returncode,1); self.assertNotIn(SECRET,found.stdout+found.stderr)
            target.chmod(0)
            self.assertEqual(subprocess.run(command,env=env,capture_output=True).returncode,2)
            target.chmod(0o600)
            clean=subprocess.run(command+['--redact'],env=env,capture_output=True,text=True)
            self.assertEqual(clean.returncode,0,clean.stderr); self.assertNotIn(SECRET,target.read_text())
            target.unlink()
            self.assertEqual(subprocess.run(command,env=env,capture_output=True).returncode,2)
    def test_stream_boundary_and_binary_preservation(self):
        with tempfile.TemporaryDirectory() as td:
            root=Path(td); p=root/'record.txt'; p.write_bytes(b'a'*(scanner.CHUNK-10)+SECRET.encode()+b' tail')
            scanner.scan_tree(root,{'KEY':SECRET.encode()},redact=True)
            self.assertTrue(scanner.scan_tree(root,{'KEY':SECRET.encode()})['clean'])
            p.unlink(); z=root/'trajectory.npz'
            with zipfile.ZipFile(z,'w',compression=zipfile.ZIP_DEFLATED) as archive: archive.writestr('meta.npy',SECRET)
            before=z.read_bytes()
            self.assertFalse(scanner.scan_tree(root,{'KEY':SECRET.encode()})['clean'])
            with self.assertRaises(scanner.ScanError): scanner.scan_tree(root,{'KEY':SECRET.encode()},redact=True)
            self.assertEqual(z.read_bytes(),before)
            z.rename(root/'trajectory.npz.v0')
            self.assertFalse(scanner.scan_tree(root,{'KEY':SECRET.encode()})['clean'])
            with self.assertRaises(scanner.ScanError): scanner.scan_tree(root,{'KEY':SECRET.encode()},redact=True)
    def test_token_boundaries_preserve_source_identities_and_extra_vars_add(self):
        names=b'"ci_checks/test-task-goal-descriptions.py": "aabbcc"'
        self.assertEqual(scanner.matches(names,{'KEY':SECRET.encode()}),[])
        self.assertTrue(scanner.matches(b'"sk-12345678901234567890"',{'KEY':SECRET.encode()}))
        with patch.dict(os.environ,{'OPENAI_API_KEY':SECRET,'CUSTOM_SECRET':'custom-value'}):
            keys=scanner.load_secrets(process_env=True,variables=['CUSTOM_SECRET'])
        self.assertIn('OPENAI_API_KEY',keys); self.assertIn('CUSTOM_SECRET',keys)

    def test_missing_credentials_empty_and_symlink_rejected(self):
        with self.assertRaises(scanner.ScanError): scanner.load_secrets()
        with tempfile.TemporaryDirectory() as td:
            p=Path(td)
            with self.assertRaises(scanner.ScanError): scanner.scan_tree(p,{'KEY':SECRET.encode()})
            (p/'escape').symlink_to('/etc/passwd')
            with self.assertRaises(scanner.ScanError): scanner.scan_tree(p,{'KEY':SECRET.encode()})

class AssignmentTests(Fixture):
    def test_explicit_modes_and_argument_ownership(self):
        self.manifest['trials']=self.manifest['trials'][1:]; self.manifest['trial_count']=1
        self.manifest.pop('manifest_sha256'); self.manifest['manifest_sha256']=assignment.digest(self.manifest); self.save_dispatch()
        args=evaluation.parse_args(['--assignment',str(self.run/'assignment.json'),'--auth','api-key'])
        self.assertEqual(args.run_id,self.batch); self.assertEqual(args.model,self.agent['model'])
        self.assertEqual([m for _,m in assignment.planned_trials(self.manifest)],['limited'])
        for extra in (['--model','other'],['--tasks','8'],['--agent-wall-clock-s','5'],['--cuda-flavor','cu130'],['--resume','--rerun-incomplete']):
            with self.subTest(extra=extra),self.assertRaises(ValueError): evaluation.parse_args(['--assignment',str(self.run/'assignment.json'),*extra])
    def test_tampering_duplicate_trials_and_retry_scope(self):
        changed=copy.deepcopy(self.dispatch); changed['agent']['model']='openai/other'
        with self.assertRaises(ValueError): assignment.validate_assignment(changed)
        changed=copy.deepcopy(self.manifest); changed['trials'].append(changed['trials'][0]); changed['trial_count']=3
        with self.assertRaises(ValueError): assignment.planned_trials(changed)
        p=self.base/'retry.json'; assignment.atomic_json(p,dict(assignment_sha256=self.dispatch['assignment_sha256'],reason='host OOM',trial_ids=['unknown']))
        with self.assertRaises(ValueError): assignment.retry_targets(p,self.dispatch)
        assignment.atomic_json(p,dict(assignment_sha256=self.dispatch['assignment_sha256'],reason='host OOM',trial_ids=[assignment.stem(self.sample,'limited')]))
        self.assertEqual(assignment.retry_targets(p,self.dispatch),{assignment.stem(self.sample,'limited')})
    def test_hf_collector_understands_single_mode(self):
        self.manifest['trials']=self.manifest['trials'][:1]; self.manifest['trial_count']=1
        self.manifest.pop('manifest_sha256'); self.manifest['manifest_sha256']=assignment.digest(self.manifest)
        assignment.atomic_json(self.run/'manifest.lock.json',self.manifest)
        from collect_batch_results import collect_manifest
        self.assertEqual(collect_manifest(self.run/'manifest.lock.json',self.jobs,copy_artifacts=False),0)
        _,_,_,rows=hf.load_results(self.run)
        self.assertEqual(len(rows),1); self.assertEqual(rows[0]['mode'],'unlimited')

    def test_real_sampling_freezes_only_requested_tier_and_mode(self):
        spec=dict(batch='sampling-contract',helper={'id':'test'},tasks='8',difficulties=['easy'],modes=['limited'],
                  samples_per_difficulty=1,sampling_seed=7,agent_wall_clock_s=60,agent=self.agent)
        value=assignment.create_assignment(spec,ROOT)
        self.assertEqual(value['manifest']['instance_count'],1)
        self.assertEqual([(r['task_id'],r['difficulty'],m) for r,m in assignment.planned_trials(value['manifest'])],
                         [('cast_coil','easy','limited')])
        with patch('difficulty_release.source_files',return_value={'changed':'a'*64}):
            with self.assertRaisesRegex(ValueError,'source differs'):
                assignment.prepare_run(self.base/'sampling-contract',value,ROOT,False)

    def test_helper_keeps_raw_evidence_until_staged_export(self):
        obj=object.__new__(evaluation.DifficultyEvaluation); obj.helper_assignment=self.dispatch
        obj.commands=Mock(); obj.redact_outputs()
        obj.commands.run_command.assert_not_called()

    def test_runner_preserves_attempts_and_obeys_explicit_retry_scope(self):
        # Exercise the real queue; fake only the expensive Docker/model boundaries.
        obj=object.__new__(evaluation.DifficultyEvaluation)
        obj.manifest=self.manifest; obj.helper_assignment=self.dispatch; obj.jobs=self.jobs; obj.source=ROOT
        obj.args=SimpleNamespace(rerun_incomplete=True); obj.retry_ids={assignment.stem(self.sample,'limited')}
        obj.harbor=sys.executable
        for name in ('verify_image','verify_packages','require_phase_complete','canary','gpu_ready','collect'):
            setattr(obj,name,Mock())
        obj.task_dir=lambda row,mode: self.run/'tasks'/(row['slug']+('-standard' if mode=='limited' else '-privileged'))
        import collect_batch_results
        obj.collector=collect_batch_results
        incomplete=self.jobs/'d08-easy-s00-limited-a001/truncated__abc/result.json'; incomplete.unlink()
        def launch(task,job):
            shutil.copytree(self.jobs/'d08-easy-s00-unlimited-a001',self.jobs/job)
            result_path=self.jobs/job/'truncated__abc/result.json'
            value=assignment.read_json(result_path); value['task_name']='topogym/'+task.name
            assignment.atomic_json(result_path,value)
            return 0
        obj.launch_job=Mock(side_effect=launch)
        with patch('topogym_versions.require_task'):
            obj.run_trials()
        self.assertEqual(obj.launch_job.call_count,1)
        self.assertEqual(obj.launch_job.call_args.args[1],'d08-easy-s00-limited-a002')
        self.assertTrue(incomplete.parent.is_dir())
        self.assertTrue((self.jobs/'d08-easy-s00-unlimited-a001').is_dir())

class MirrorTests(unittest.TestCase):
    def test_append_rewrite_disappearance_and_link_failure(self):
        with tempfile.TemporaryDirectory() as td:
            root=Path(td); agent=root/'src/job/trial/agent'; agent.mkdir(parents=True); mirror=root/'mirror'
            log=agent/'record.log'; log.write_text('first')
            binary=agent/'private.bin'; binary.write_bytes(b'private evidence'); binary.chmod(0o600)
            marker=mirror/'ready'
            command=[sys.executable,str(ROOT/'scripts/helper_log_mirror.py'),'--src',str(root/'src'),'--mirror',str(mirror),'--once','--strict','--ready-file',str(marker)]
            def run(): return subprocess.run(command,capture_output=True,text=True)
            self.assertEqual(run().returncode,0); self.assertTrue(marker.exists())
            self.assertEqual((mirror/'job/trial/agent/private.bin.v0').stat().st_mode & 0o777,0o644)
            log.write_text('first plus'); self.assertEqual(run().returncode,0)
            self.assertEqual((mirror/'job/trial/agent/record.log').read_text(),'first plus')
            log.write_text('replaced'); self.assertEqual(run().returncode,0)
            self.assertEqual((mirror/'job/trial/agent/record.log.seg1').read_text(),'replaced')
            log.unlink(); self.assertEqual(run().returncode,0)
            self.assertIn('disappeared',(mirror/'TAMPER.log').read_text())
            (agent/'linked-subdir').symlink_to(root,target_is_directory=True)
            self.assertNotEqual(run().returncode,0)


class BundleTests(Fixture):
    def test_roundtrip_complete_records_relocation_and_idempotency(self):
        archive=self.export(); sealed=bundle.verify_bundle(archive,expected=self.dispatch)
        self.assertTrue(sealed['summary']['evaluation_complete'])
        raw=self.jobs/'d08-easy-s00-unlimited-a001/truncated__abc/agent/log.txt'
        self.assertIn(SECRET,raw.read_text())
        received=receiver.import_bundle(archive,self.base/'different-user-root',expected=self.dispatch,require_complete=True)
        payload=Path(received['directory'])/'payload'
        imported=payload/'jobs/difficulty_trials'/self.batch/'d08-easy-s00-unlimited-a001/truncated__abc'
        self.assertNotIn(SECRET,(imported/'agent/log.txt').read_text())
        self.assertTrue((imported/'artifacts/app/output/gen.py').is_file())
        self.assertTrue(original_task(imported).is_dir())
        self.assertEqual(receiver.import_bundle(archive,self.base/'different-user-root',expected=self.dispatch),received)
        self.assertEqual(self.export(),archive)
        report=Path(received['report']).read_text(); self.assertIn('Evidence',report)
        self.assertTrue((Path(received['directory'])/'reports/site-input.json').exists())
    def test_later_assignment_verification_updates_receipt_and_checks_local_controls(self):
        archive=self.export(); work=self.base/'receiver'
        initial=receiver.import_bundle(archive,work)
        self.assertFalse(initial['expected_assignment_verified'])
        verified=receiver.import_bundle(archive,work,expected=self.dispatch)
        self.assertTrue(verified['expected_assignment_verified'])
        control=Path(verified['directory'])/'payload/BUNDLE.json'
        value=assignment.read_json(control); value['batch']='changed'; assignment.atomic_json(control,value)
        with self.assertRaisesRegex(bundle.BundleError,'control metadata changed'):
            receiver.import_bundle(archive,work,expected=self.dispatch)

    def test_partial_results_retained_and_completion_gate(self):
        trial=self.jobs/'d08-easy-s00-limited-a001/truncated__abc'
        (trial/'result.json').unlink(); (trial/'verifier/reward.json').unlink()
        archive=self.export(); result=bundle.verify_bundle(archive)
        self.assertFalse(result['summary']['evaluation_complete'])
        self.assertEqual(result['summary']['status_counts']['interrupted'],1)
        with self.assertRaises(bundle.BundleError): receiver.import_bundle(archive,self.base/'receiver',require_complete=True)
        receipt=receiver.import_bundle(archive,self.base/'receiver')
        self.assertFalse(receipt['summary']['evaluation_complete'])
    def test_external_assignment_changed_or_source_package_changed(self):
        archive=self.export(); wrong=copy.deepcopy(self.dispatch); wrong['helper']['id']='different'
        wrong.pop('assignment_sha256'); wrong['assignment_sha256']=assignment.digest(wrong)
        with self.assertRaises(bundle.BundleError): bundle.verify_bundle(archive,expected=wrong)
        task=self.run/'tasks'/('topogym-cast-coil-easy-s00-privileged')/'instruction.md'; task.write_text('changed')
        with self.assertRaises(bundle.BundleError): self.export()
    def test_no_cross_batch_credentials_or_cache(self):
        extra=self.work/'jobs/difficulty_trials/another-batch'; extra.mkdir(); (extra/'private.txt').write_text('unrelated')
        (self.run/'source').mkdir(); (self.run/'source/private.env').write_text(SECRET)
        archive=self.export()
        with tarfile.open(archive) as tar:
            names=tar.getnames(); self.assertFalse(any('another-batch' in n or '/source/' in n for n in names))
    def test_corruption_links_empty_jobs_and_run_lock(self):
        with bundle.exclusive(self.run/'.lock'):
            with self.assertRaises(bundle.BundleError): self.export()
        (self.jobs/'d08-easy-s00-unlimited-a001/escape').symlink_to('/etc/passwd')
        with self.assertRaises((bundle.BundleError,scanner.ScanError)): self.export()
        (self.jobs/'d08-easy-s00-unlimited-a001/escape').unlink()
        archive=self.export(); archive.write_bytes(archive.read_bytes()+b'corrupt')
        with self.assertRaises(bundle.BundleError): bundle.verify_bundle(archive)
    def test_malicious_tar_paths_and_duplicates_rejected(self):
        for names in (['../escape'],['same','same']):
            directory=self.base/str(len(names)); directory.mkdir(); path=directory/'malicious.tar.gz'
            with tarfile.open(path,'w:gz') as tar:
                for name in names:
                    info=tarfile.TarInfo(name); info.size=1; tar.addfile(info,io.BytesIO(b'x'))
            path.with_name(path.name+'.sha256').write_text(scanner.sha(path)+'  '+path.name+'\n')
            with self.assertRaises(bundle.BundleError): bundle.verify_bundle(path)
    def test_cli_offline_verify_and_import(self):
        archive=self.export()
        command=['bash',str(ROOT/'bash_scripts/run_difficulty_trials.sh'),'helper','verify','--backend','local','--archive',str(archive),
                 '--assignment',str(self.run/'assignment.json'),'--require-complete']
        env=dict(os.environ,TOPOGYM_EVAL_PYTHON=sys.executable)
        result=subprocess.run(command,cwd=self.base,env=env,capture_output=True,text=True,timeout=30)
        self.assertEqual(result.returncode,0,result.stderr); self.assertIn('"archive_verified": true',result.stdout)
    def test_previously_accepted_terminal_records_cannot_change(self):
        archive=self.export(); receiver.import_bundle(archive,self.base/'receiver')
        (self.jobs/'d08-easy-s00-unlimited-a001/truncated__abc/agent/log.txt').write_text('different terminal history')
        newer=self.export()
        with self.assertRaises(bundle.BundleError): receiver.import_bundle(newer,self.base/'receiver')

    def test_missing_task_or_execution_evidence_blocks_finished_delivery(self):
        path=self.run/'execution.lock.json'; before=path.read_bytes(); path.unlink()
        with self.assertRaises(bundle.BundleError): self.export()
        path.write_bytes(before)
        shutil.rmtree(self.run/'tasks'/('topogym-cast-coil-easy-s00-privileged'))
        with self.assertRaises(bundle.BundleError): self.export()

    def test_ledger_contradiction_and_interrupted_import_recovery(self):
        archive=self.export(); dest=self.base/'receiver'
        receipt=receiver.import_bundle(archive,dest)
        (dest/'imports'/self.batch/'index.json').unlink()  # crash between payload rename and index commit
        self.assertEqual(receiver.import_bundle(archive,dest),receipt)
        index=assignment.read_json(dest/'imports'/self.batch/'index.json')
        self.assertTrue(index['terminal_files'])
        payload=Path(receipt['directory'])/'payload'
        ledger=payload/'runs/difficulty_trials'/self.batch/'trials.jsonl'
        ledger.write_text(ledger.read_text().replace('"unsolved"','"solved"'))
        with self.assertRaisesRegex(bundle.BundleError,'ledger contradicts'):
            bundle.collect_for_verification(payload,self.batch)

    def test_required_mirror_and_mutating_source_block_export(self):
        self.dispatch['mirror']='required'; self.save_dispatch()
        with self.assertRaisesRegex(bundle.BundleError,'mirror'): self.export()
        self.dispatch['mirror']='optional'; self.save_dispatch()
        real_copy=bundle.copy_payload; mutated=False
        def changing(src,dst,records):
            nonlocal mutated
            real_copy(src,dst,records)
            if src.name=='instruction.md' and not mutated:
                src.write_text('changed during snapshot'); mutated=True
        with patch.object(bundle,'copy_payload',side_effect=changing):
            with self.assertRaisesRegex(bundle.BundleError,'source changed'): self.export()


class FakeHub:
    def __init__(self): self.files={}; self.head='0'; self.commits=0; self.lose_response=True
    def call(self,action,**params):
        if action=='auth': return None
        if action=='private': return True
        if action=='head': return self.head
        if action=='read': return json.loads(self.files[params['path']]) if params['path'] in self.files else None
        if action=='info':
            return {p:dict(size=len(self.files[p]),sha256=hashlib.sha256(self.files[p]).hexdigest()) for p in params['paths'] if p in self.files}
        if action=='commit':
            if params['parent']!=self.head: raise hf.HFError('commit_conflict',retryable=True)
            self.files.update({p:Path(local).read_bytes() for p,local in params['files']}); self.commits+=1; self.head=str(self.commits)
            if self.lose_response: self.lose_response=False; raise hf.HFError('network_error',retryable=True)
            return self.head
        raise AssertionError(action)

class UploadTests(Fixture):
    def test_lost_response_idempotency_and_final_marker(self):
        self.dispatch['upload']=dict(type='hf',repo_id='test/private',prefix='helpers'); self.save_dispatch()
        archive=self.export(); hub=FakeHub(); args=SimpleNamespace(hf_dry_run=False)
        result=helper_upload.upload_bundle(archive,self.base/'uploader',args,hub=hub,sleep=lambda _:None)
        self.assertTrue(result['upload_complete']); self.assertEqual(hub.commits,2)
        second=helper_upload.upload_bundle(archive,self.base/'uploader',args,hub=hub)
        self.assertEqual(hub.commits,2); self.assertTrue(second['upload_complete'])
        self.assertTrue(any(p.endswith('UPLOAD_COMPLETE.json') for p in hub.files))
    def test_dry_run_needs_no_token_and_public_dataset_rejected(self):
        self.dispatch['upload']=dict(type='hf',repo_id='test/private',prefix='helpers'); self.save_dispatch(); archive=self.export()
        result=helper_upload.upload_bundle(archive,self.base/'uploader',SimpleNamespace(hf_dry_run=True))
        self.assertFalse(result['upload_complete'])
        hub=FakeHub(); original=hub.call
        hub.call=lambda action,**params: False if action=='private' else original(action,**params)
        with self.assertRaises(hf.HFError): helper_upload.upload_bundle(archive,self.base/'uploader',SimpleNamespace(hf_dry_run=False),hub=hub)

if __name__=='__main__': unittest.main(verbosity=2)
