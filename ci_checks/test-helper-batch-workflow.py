"""CPU workflow contracts; fake model/GPU/HF, real standard archives and receiver."""
import copy
import importlib.util
import json
import os
from pathlib import Path
import shutil
import sys
import tempfile
import time
import unittest
from unittest.mock import patch

ROOT=Path(__file__).resolve().parents[1]; sys.path[:0]=[str(ROOT/'scripts'),str(ROOT)]
spec=importlib.util.spec_from_file_location('native_fixture',ROOT/'ci_checks/test-native-agent-batch.py')
fixture=importlib.util.module_from_spec(spec); spec.loader.exec_module(fixture)
import helper_batch as h
import agent_batch_contract as c
import agent_batch_delivery as d

BUDGET=dict(input_tokens=150000000,output_tokens=10000000,enforcement='post_run_score')


class Workflow(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory(); self.root=Path(self.temp.name)
        self.jobs,self.plan=fixture.fixture(self.root)
        self.assignment=self.root/'assignment.json'; c.save(self.assignment,self.plan)
        self.env=self.root/'rcb.env'; self.env.write_text('OPENAI_API_KEY='+fixture.SECRET+'\n'); self.env.chmod(0o600)
        self.config=self.root/'helper.json'
        self.cfg=dict(schema_version=1,assignment=str(self.assignment),jobs_dir=str(self.jobs),
                      auth=dict(method='api-key',env_file=str(self.env)),lanes=[{'gpu':'0'},{'gpu':'1'}],background=False,upload=False)
        c.save(self.config,self.cfg)
    def tearDown(self): self.temp.cleanup()
    def repin(self):
        self.plan.pop('plan_sha256'); self.plan['plan_sha256']=c.digest(self.plan); c.validate(self.plan)
        c.save(self.assignment,self.plan); c.save(self.jobs/'fixture-plan.json',self.plan)
        md=c.read(self.jobs/'fixture-metadata.json'); md['plan_sha256']=self.plan['plan_sha256']; c.save(self.jobs/'fixture-metadata.json',md)
    def test_config_pins_maintainer_settings_and_keeps_secrets_outside(self):
        loaded=h.load_config(self.config); self.assertEqual(len(loaded['lanes']),2)
        env=h.lane_environment(loaded,loaded['lanes'][0]); self.assertEqual(env['ENV_FILE'],str(self.env))
        self.cfg['model']='different'; c.save(self.config,self.cfg)
        with self.assertRaisesRegex(ValueError,'maintainer'): h.load_config(self.config)
        del self.cfg['model']; self.cfg['auth']['env_file']=str(self.jobs/'private.env'); c.save(self.config,self.cfg)
        with self.assertRaisesRegex(ValueError,'outside'): h.load_config(self.config)
    def test_whole_workflow_then_retry_does_not_run_models_again(self):
        def completed(*a): d.seal(self.jobs,self.plan,{'test':fixture.SECRET.encode()}); return [0,0]
        with patch.object(h,'bootstrap'),patch.object(h,'prepare') as prepare,patch.object(h,'run_lanes',side_effect=completed) as lanes:
            with patch.object(sys,'argv',['helper_batch.py','--config',str(self.config)]): self.assertEqual(h.main(),0)
            self.assertEqual(lanes.call_count,1)
            with patch.object(sys,'argv',['helper_batch.py','--config',str(self.config)]): self.assertEqual(h.main(),0)
            self.assertEqual(lanes.call_count,1); self.assertEqual(prepare.call_count,1)
        folder=self.jobs.parent/'upload_fixture'
        self.assertEqual({p.name for p in folder.iterdir()},{'fixture__fixture.tar.gz','fixture__fixture.tar.gz.sha256','MANIFEST.md'})
        archive=folder/'fixture__fixture.tar.gz'
        shutil.rmtree(self.jobs); shutil.rmtree(self.root/'tasks')
        receipt=d.receive(archive,self.plan,self.root/'received',require_complete=True)
        self.assertEqual(receipt['report']['observed_trials'],6)
    def test_partial_needs_explicit_choice_and_preserves_original(self):
        next(self.jobs.glob('*/*/result.json')).unlink(); d.seal(self.jobs,self.plan,{'test':fixture.SECRET.encode()})
        folder=self.jobs.parent/'upload_fixture'
        with self.assertRaisesRegex(ValueError,'incomplete'): h.bundle(self.jobs,self.plan,folder)
        self.assertFalse(folder.exists())
        archive,report=h.bundle(self.jobs,self.plan,folder,allow_partial=True)
        self.assertFalse(report['delivery_complete']); self.assertTrue(archive.is_file())
    def test_archive_mutation_is_rejected_on_retry(self):
        d.seal(self.jobs,self.plan,{'test':fixture.SECRET.encode()})
        folder=self.jobs.parent/'upload_fixture'; h.bundle(self.jobs,self.plan,folder)
        (folder/'MANIFEST.md').write_text('changed')
        with self.assertRaisesRegex(ValueError,'MANIFEST'): h.bundle(self.jobs,self.plan,folder)
    def test_usage_at_limit_missing_and_over_budget(self):
        self.plan['token_budget']=BUDGET.copy()
        for task in self.plan['tasks']: task['success_artifacts']=[]
        self.repin()
        records=sorted(self.jobs.glob('*/*/result.json'))
        for path in records:
            result=c.read(path); result['agent_result']={'n_input_tokens':150000000,'n_output_tokens':10000000}; c.save(path,result)
        self.assertTrue(c.check_batch(self.jobs,self.plan)['evaluation_complete'])
        path=records[0]; raw=c.read(path); raw['agent_result']['n_input_tokens']=150000001
        raw['verifier_result']['rewards']['success']=1; c.save(path,raw)
        reward=c.read(path.parent/'verifier/reward.json'); reward['success']=1; c.save(path.parent/'verifier/reward.json',reward)
        proof=c.read(path.parent/'verifier/verdict.json'); proof.update(success=True,reward=reward); c.save(path.parent/'verifier/verdict.json',proof)
        row=c.check_batch(self.jobs,self.plan)['rows'][0]
        self.assertEqual((row['status'],row['success'],row['raw_success']),('over_token_budget',0,1))
        self.assertEqual(c.read(path)['verifier_result']['rewards']['success'],1)
        raw['agent_result']['n_input_tokens']=None; c.save(path,raw)
        report=c.check_batch(self.jobs,self.plan); self.assertFalse(report['evaluation_complete']); self.assertEqual(report['rows'][0]['status'],'usage_missing')
        raw['agent_result']={'n_input_tokens':0,'n_output_tokens':10000001}; c.save(path,raw)
        self.assertEqual(c.check_batch(self.jobs,self.plan)['rows'][0]['status'],'over_token_budget')
        raw['agent_result']['n_output_tokens']=True; c.save(path,raw)
        self.assertEqual(c.check_batch(self.jobs,self.plan)['rows'][0]['status'],'usage_missing')
    def test_current_sweep_has_180_fixed_trials_and_twelve_hours(self):
        import yaml
        import sample_difficulty_instances as sampling
        setting=ROOT/'configs/sweeps/helper_oracle_reference.yaml'; cfg=yaml.safe_load(setting.read_text())
        rows=sampling.sample_instances(cfg)
        self.assertEqual(len(rows),30); self.assertEqual(len(rows)*len(cfg['modes'])*cfg['native_batch']['repetitions'],180)
        self.assertFalse({'knot_untying','slotted_post_ring','orbits'} & {r['task_id'] for r in rows})
        self.assertTrue(all(r['scene_seed']==0 and r['variation_id']==r['difficulty'] and not r['draws'] for r in rows))
        self.assertEqual(cfg['agent_wall_clock_s'],43200); self.assertEqual(cfg['native_batch']['token_budget'],BUDGET)
        # Exercise manifest validation with lightweight source isolation, not a GPU snapshot.
        source=dict(sha256='a'*64,files={})
        with patch.object(sampling,'snapshot_source',return_value=source),patch.object(sampling,'sample_instances',return_value=rows),patch('topogym_versions.identity',return_value={}):
            manifest=sampling.prepare_manifest(self.root/'plan',setting=setting)
        self.assertEqual(manifest['settings']['native_batch']['model'],'openai/gpt-6-sol')
    def test_rerun_cannot_change_budget(self):
        from create_agent_batch_rerun import create
        self.plan['token_budget']=BUDGET.copy(); self.repin()
        child=create(self.plan,c.check_batch(self.jobs,self.plan))
        child['token_budget']['input_tokens']+=1; child.pop('plan_sha256'); child['plan_sha256']=c.digest(child)
        with self.assertRaisesRegex(ValueError,'settings'): c.linked_rerun(self.plan,child)
    def test_hf_only_uploads_three_files_and_retry_skips_commit(self):
        self.plan['upload']={'type':'hf','repo_id':'test/private','prefix':'helpers/fixture/fixture'}; self.repin()
        for task,spec in zip(self.plan['tasks'],self.plan['jobs']):
            fixture.pending_review(sorted((self.jobs/spec['job']).iterdir())[0],task)
        d.seal(self.jobs,self.plan,{'test':fixture.SECRET.encode()}); folder=self.jobs.parent/'upload_fixture'; h.bundle(self.jobs,self.plan,folder)
        cfg=h.load_config(self.config); state=self.root/'state'; state.mkdir()
        class Hub:
            remote={}; commits=0
            def call(obj,action,**kw):
                if action=='private': return True
                if action=='head': return 'rev'+str(obj.commits)
                if action=='info': return {p:obj.remote[p] for p in kw['paths'] if p in obj.remote}
                if action=='commit':
                    obj.commits+=1
                    obj.remote={rel:dict(size=Path(path).stat().st_size,sha256=c.sha(path)) for rel,path in kw['files']}
                    from difficulty_hf_auth import HFError
                    raise HFError('network_error',retryable=True)  # remote committed, response was lost
        hub=Hub()
        with patch.object(h,'hf_access',return_value=hub),patch.object(h.time,'sleep'):
            self.assertTrue(h.upload(cfg,self.plan,state)['remote_verified'])
            receipt=c.read(state/'hf-receipt.json')
            self.assertEqual(receipt['pending_review_trials'],2); self.assertEqual(receipt['scored_trials'],4)
            self.assertTrue(h.upload(cfg,self.plan,state)['remote_verified'])
            self.assertEqual(hub.commits,1); self.assertEqual(len(hub.remote),3)
            next(iter(hub.remote.values()))['sha256']='bad'
            with self.assertRaisesRegex(ValueError,'different'): h.upload(cfg,self.plan,state)
    def test_hf_receiver_pins_revision_and_requires_only_read_access(self):
        import io
        import import_helper_results as receiver
        from difficulty_results_hf import file_identity
        self.plan['upload']={'type':'hf','repo_id':'test/private','prefix':'helpers/fixture/fixture'}; self.repin()
        for task,spec in zip(self.plan['tasks'],self.plan['jobs']):
            fixture.pending_review(sorted((self.jobs/spec['job']).iterdir())[0],task)
        d.seal(self.jobs,self.plan,{'test':fixture.SECRET.encode()})
        folder=self.jobs.parent/'upload_fixture'; h.bundle(self.jobs,self.plan,folder)
        prefix=self.plan['upload']['prefix']; remote={prefix+'/'+p.name:p for p in folder.iterdir()}
        calls=[]
        class Hub:
            head='a'*40
            def call(obj,action,**kw):
                calls.append((action,kw))
                if action=='private': return True
                if action=='head': return obj.head
                if action=='info': return {p:file_identity(remote[p]) for p in kw['paths'] if p in remote}
                if action=='download': shutil.copyfile(remote[kw['path']],kw['destination'])
        hub=Hub(); work=self.root/'receiver'; out=work/'downloads'/self.plan['batch']
        archive,receipt=receiver.download(self.plan,out,hub)
        self.assertEqual(receipt['revision'],'a'*40)
        verified=receiver.verify(archive,self.plan,require_complete=True)
        self.assertTrue(verified['delivery_complete']); self.assertEqual(verified['status_counts']['pending_review'],2)
        argv=['import_helper_results.py','--assignment',str(self.assignment),'--work-dir',str(work),
              '--phase','import','--require-complete']
        with patch.object(sys,'argv',argv),patch.object(sys,'stdout',io.StringIO()) as output:
            self.assertEqual(receiver.main(),0)
        imported=json.loads(output.getvalue())
        self.assertEqual(imported['pending_review_trials'],2); self.assertEqual(imported['scored_trials'],4)
        accepted=c.read(work/'accepted/fixture/receipt.json')
        self.assertEqual(accepted['report']['status_counts']['pending_review'],2)
        self.assertIn('pending review: 2',(work/'accepted/fixture/review/README.md').read_text())
        self.assertTrue(all(kw['write'] is False for action,kw in calls if action=='auth'))
        self.assertEqual(sum(action=='download' for action,_ in calls),3)
        hub.head='b'*40
        receiver.download(self.plan,out,hub)
        self.assertEqual(sum(action=='download' for action,_ in calls),3)
        self.assertEqual([kw['revision'] for action,kw in calls if action=='info'],['a'*40,'a'*40])
        with self.assertRaisesRegex(ValueError,'different publication'):
            receiver.download(self.plan,out,hub,revision='b'*40)
        archive.write_bytes(b'corrupt')
        with self.assertRaisesRegex(ValueError,'differs'):
            receiver.download(self.plan,out,hub)
        with self.assertRaisesRegex(ValueError,'max-download'):
            receiver.download(self.plan,self.root/'size-limited',hub,max_bytes=1)
    def test_helper_config_initialization_is_exclusive_and_does_not_bootstrap(self):
        target=self.root/'new-config.json'
        argv=['helper_batch.py','--init-config','--config',str(target),'--assignment',str(self.assignment),
              '--jobs-dir',str(self.jobs),'--env-file',str(self.env)]
        with patch.object(h,'bootstrap') as bootstrap,patch.object(sys,'argv',argv):
            self.assertEqual(h.main(),0); bootstrap.assert_not_called()
            self.assertEqual(h.main(),2)
        self.assertEqual(h.load_config(target)['lanes'][0]['auth']['method'],'api-key')
        self.assertEqual(target.stat().st_mode&0o077,0)
    def test_runtime_export_closure_omits_oracle_solutions(self):
        from export_native_helper_release import code_files
        names=code_files(ROOT)
        self.assertIn('scripts/import_helper_results.py',names)
        self.assertIn('scripts/helper_assignment.py',names)
        self.assertIn('topogym/planning/harbor_bridge/binding.py',names)
        self.assertFalse(any(n.startswith('scripts/oracle_runners/') for n in names))
        self.assertFalse(any(n.startswith('topogym/planning/cast_coil/') for n in names))
        self.assertFalse(any(n.startswith(('runs/','.codex/','.git/')) for n in names))
    def test_release_accepts_external_assignment_only_with_matching_packages(self):
        import export_native_helper_release as release
        self.plan['release']={'example':'runtime'}; self.repin()
        c.save(self.root/'helper-release.json',dict(schema_version=1,kind='native-helper-release',
            runtime_only=False,release=self.plan['release'],files={},assignments={}))
        with patch.object(release,'identity',return_value=self.plan['release']):
            self.assertTrue(release.verify_release(self.root,self.plan)['verified'])
            path=self.root/'tasks'/self.plan['tasks'][0]['name']/'task.toml'; path.write_text('changed')
            with self.assertRaises(ValueError): release.verify_release(self.root,self.plan)
    def test_background_config_and_inherited_credentials(self):
        cfg=h.load_config(self.config)
        with patch.dict(os.environ,{'HF_TOKEN':'never-pass','MODEL':'wrong','CODEX_AUTH_JSON_PATH':'wrong','OPENAI_API_KEY':'wrong'}):
            env=h.lane_environment(cfg,cfg['lanes'][0])
        self.assertNotIn('HF_TOKEN',env); self.assertNotIn('MODEL',env); self.assertNotIn('OPENAI_API_KEY',env); self.assertNotIn('CODEX_AUTH_JSON_PATH',env)
    def test_real_lane_processes_get_gpu_assignment(self):
        root=self.root/'fake-runner'; (root/'scripts').mkdir(parents=True)
        (root/'scripts/run_agent_batch.sh').write_text('#!/bin/bash\ntest -z "${HF_TOKEN:-}" || exit 9\nprintf "%s" "$GPU_DEVICE" > "$(dirname "$JOBS")/gpu-$GPU_DEVICE"\n')
        state=self.root/'state'; state.mkdir(); cfg=h.load_config(self.config)
        with patch.object(h,'ROOT',root): self.assertEqual(h.run_lanes(cfg,self.plan,state),[0,0])
        self.assertEqual((self.jobs.parent/'gpu-0').read_text(),'0'); self.assertEqual((self.jobs.parent/'gpu-1').read_text(),'1')
    def test_background_handoff_reaches_delivery_without_repeating_prepare(self):
        # Child runs real orchestration/sealing/archive code with fake model/GPU steps.
        wrapper=self.root/'fixture-python'
        wrapper.write_text('#!'+sys.executable+'\n'+
            'import sys\n'+f'sys.path[:0]=[{str(ROOT/"scripts")!r},{str(ROOT)!r}]\n'+
            'sys.argv.pop(1)\nimport helper_batch as h\nimport agent_batch_delivery as d\n'+
            'from pathlib import Path\nh.bootstrap=lambda:None\n'+
            'def fake_lanes(cfg,plan,state):\n'+f'    d.seal(Path(cfg["jobs_dir"]),plan,{{"test":{fixture.SECRET.encode()!r}}})\n    return [0,0]\n'+
            'h.run_lanes=fake_lanes\nraise SystemExit(h.main())\n')
        wrapper.chmod(0o700); self.cfg['background']=True; c.save(self.config,self.cfg)
        with patch.object(h,'bootstrap'),patch.object(h,'prepare') as prep,patch.object(sys,'executable',str(wrapper)),patch.object(sys,'argv',['helper_batch.py','--config',str(self.config)]):
            self.assertEqual(h.main(),0); self.assertEqual(prep.call_count,1)
        state=self.jobs.parent/'.helper-pipeline/fixture/status.json'
        deadline=time.monotonic()+15
        while time.monotonic()<deadline:
            status=c.read(state)
            if status['stage'] in ('complete','failed'): break
            time.sleep(.05)
        self.assertEqual(status['stage'],'complete',(state.parent/'workflow.log').read_text())
        self.assertTrue(status['delivery']['delivery_complete'])
        try: os.waitpid(status['worker']['pid'],0)
        except ChildProcessError: pass
        # A finished supervisor record must not block a delivery-only restart.
        with patch.object(h,'bootstrap'),patch.object(h,'prepare') as prep,patch.object(h,'run_lanes') as lanes,patch('agent_batch_runtime.live',return_value=True),patch.object(sys,'argv',['helper_batch.py','--config',str(self.config)]):
            self.assertEqual(h.main(),0); prep.assert_not_called(); lanes.assert_not_called()


if __name__=='__main__': unittest.main()
