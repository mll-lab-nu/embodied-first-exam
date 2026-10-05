"""CPU contracts for standard helper commands. No model/physics qualification."""
import copy
import importlib.util
import io
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tarfile
import tempfile
import unittest
from unittest.mock import patch
ROOT=Path(__file__).resolve().parents[1]; sys.path.insert(0,str(ROOT/'scripts')); sys.path.insert(0,str(ROOT))
import agent_batch_contract as c
import agent_batch_delivery as d
import agent_batch_runtime as r

SECRET='synthetic-private-test-key-1234567890'

def fixture(root,batch='fixture',k=3):
    jobs=root/'jobs/agents'; jobs.mkdir(parents=True)
    tasks=[]
    for mode in ('privileged','standard'):
        base='topogym-cast-coil-easy-o00'; name=base+'-'+mode
        package=root/'tasks'/name; package.mkdir(parents=True); (package/'task.toml').write_text('[agent]\ntimeout_sec = 90\n')
        hashes=c.inventory(package)
        tasks.append(dict(name=name,base=base,mode=mode,files=hashes,package_sha256=c.digest(hashes),harbor_checksum=c.digest(hashes),
                          binding_id='a'*64,runtime_binding={'image':{'reference':'fixture:image','id':'sha256:'+'f'*64}},agent_timeout_sec=90,
                          success_artifacts=['verifier/replay.mp4','verifier/replay.last.png']))
    plan=dict(format=c.FORMAT,schema_version=1,batch=batch,helper='fixture',repetitions=k,tasks=tasks,task_bases=[base],trial_count=2*k,
              jobs=[dict(job=batch+'-'+t['mode']+'-'+base,task=t['name'],repetitions=k) for t in tasks],
              agent=dict(name='codex',model='openai/gpt-6-luna',kwargs={'reasoning_effort':'xhigh','version':'0.157.0','web_search':'disabled'}),
              mirror_required=True,upload={'type':'shared-folder'})
    plan['plan_sha256']=c.digest(plan); c.validate(plan)
    c.save(jobs/(batch+'-plan.json'),plan)
    c.save(jobs/(batch+'-metadata.json'),dict(plan_sha256=plan['plan_sha256'],host={},lanes=[],images={},status='finished'))
    for spec,task in zip(plan['jobs'],tasks):
        for i in range(k): trial(jobs,spec,task,plan,i)
        mirror=jobs.with_name('agents_mirror')/spec['job']; mirror.mkdir(parents=True)
        (mirror/'history.txt.v0').write_text('old log '+SECRET)
        c.save(jobs/(spec['job']+'-mirror.json'),{'complete':True})
    return jobs,plan

def trial(jobs,spec,task,plan,i,score=0):
    path=jobs/spec['job']/(task['name']+'__'+str(i)); path.mkdir(parents=True)
    reward=dict(success=score,runtime_binding_ok=1,instance_exact=1)
    if task['mode']=='standard': reward['finalized']=1
    c.save(path/'verifier/reward.json',reward)
    proof=dict(runtime_binding={'binding_id':task['binding_id']},instance_exact=True)
    if task['mode']=='standard':
        for name in ('startup_binding.json','replay.verdict.json'): c.save(path/'verifier'/name,proof)
    else: c.save(path/'verifier/verdict.json',dict(reward=reward,success=bool(score),evidence={'runtime_binding':proof['runtime_binding']}))
    c.save(path/'config.json',dict(task={'path':'/host-a/no-longer-available/tasks/'+task['name']},agent=dict(name='codex',model_name=plan['agent']['model'],kwargs=plan['agent']['kwargs'])))
    c.save(path/'result.json',dict(task_name=task['name'],task_checksum=task['harbor_checksum'],finished_at='2026-10-04T00:00:00Z',verifier_result={'rewards':reward}))
    (path/'agent').mkdir(); (path/'agent/codex.txt').write_text('clean unsolved test\n')
    return path

def pending_review(path,task):
    """Synthetic v16 verifier evidence in the same two layouts as the graders."""
    reward=c.read(path/'verifier/reward.json')
    reward.update(success=0,success_pending_review=1,review_events=1,review_max_depth_mm=3.4)
    c.save(path/'verifier/reward.json',reward)
    result=c.read(path/'result.json'); result['verifier_result']['rewards']=reward; c.save(path/'result.json',result)
    review=dict(pending=True,frames=['review_frames/step_00003.png'])
    events=dict(count=1,events=[dict(step=3,depth_mm=3.4)])
    if task['mode']=='privileged':
        review['replays']=[None,events]
        proof=c.read(path/'verifier/verdict.json'); proof.update(reward=reward,success=False)
        proof['evidence']['review']=review; c.save(path/'verifier/verdict.json',proof)
    else:
        review.update(live=events,replay=None); c.save(path/'verifier/review.json',review)
    frame=path/'verifier/review_frames/step_00003.png'; frame.parent.mkdir()
    frame.write_bytes(b'synthetic review frame; not physics evidence')


def pack(root,jobs,plan):
    b=plan['batch']; archive=root/(b+'__fixture.tar.gz')
    # Execute the original tar selection, including all B-* sidecars.
    script='tar -czf "$ARCHIVE" agents/"$B"-* agents/"$B".log agents/"$B".summary.md $(ls -d agents_mirror/"$B"-* 2>/dev/null)'
    subprocess.run(['bash','-c',script],cwd=jobs.parent,env=dict(os.environ,B=b,ARCHIVE=str(archive)),check=True)
    archive.with_name(archive.name+'.sha256').write_text(c.sha(archive)+'  '+archive.name+'\n')
    return archive

class NativeTests(unittest.TestCase):
    def setUp(self): self.temp=tempfile.TemporaryDirectory(); self.root=Path(self.temp.name); self.jobs,self.plan=fixture(self.root)
    def tearDown(self): self.temp.cleanup()
    def trials(self): return sorted(self.jobs.glob('*/*__*/result.json'))
    def mark_pending(self):
        marked=[]
        for task,spec in zip(self.plan['tasks'],self.plan['jobs']):
            path=sorted((self.jobs/spec['job']).iterdir())[0]
            pending_review(path,task); marked.append(path)
        return marked
    def test_pending_review_is_complete_but_unscored_in_both_modes(self):
        paths=self.mark_pending(); before={p:c.inventory(p) for p in paths}
        report=c.write_summary(self.jobs,self.plan)
        self.assertEqual(report['status_counts'],{'pending_review':2,'unsolved':4})
        self.assertTrue(report['evaluation_complete']); self.assertTrue(report['delivery_complete'])
        self.assertEqual(c.outcome_counts(report),dict(solved_trials=0,unsolved_trials=4,scored_trials=4,pending_review_trials=2))
        for row in report['rows']:
            if row['status']=='pending_review':
                self.assertIsNone(row['success']); self.assertEqual(row['raw_success'],0)
                self.assertTrue(row['success_pending_review'])
        text=(self.jobs/'fixture.summary.md').read_text()
        self.assertIn('0/4 solved; pending review: 2',text)
        self.assertIn('| pending_review | — |',text)
        self.assertEqual(before,{p:c.inventory(p) for p in paths})
    def test_pending_review_does_not_bypass_validation(self):
        self.mark_pending()
        for task,spec in zip(self.plan['tasks'],self.plan['jobs']):
            path=sorted((self.jobs/spec['job']).iterdir())[0]
            reward=c.read(path/'verifier/reward.json'); result=c.read(path/'result.json')
            for changes,expected in (({'infra_error':1},'infra_failed'),({'runtime_binding_ok':0},'not_evaluable'),
                                     ({'instance_mismatch':1},'not_evaluable'),({'success':1},'invalid_verdict')):
                with self.subTest(mode=task['mode'],changes=changes):
                    changed=dict(reward,**changes); c.save(path/'verifier/reward.json',changed)
                    updated=copy.deepcopy(result); updated['verifier_result']['rewards']=changed; c.save(path/'result.json',updated)
                    self.assertEqual(c.trial_verdict(path,task,self.plan['agent'])[0],expected)
            c.save(path/'verifier/reward.json',reward); c.save(path/'result.json',result)
            result['verifier_result']['rewards']['success_pending_review']=0; c.save(path/'result.json',result)
            self.assertEqual(c.trial_verdict(path,task,self.plan['agent'])[0],'verdict_mismatch')
    def test_pending_review_is_not_selected_for_rerun(self):
        from create_agent_batch_rerun import create
        paths=self.mark_pending()
        with self.assertRaisesRegex(ValueError,'no incomplete'):
            create(self.plan,c.check_batch(self.jobs,self.plan))
        missing=next(p for p in self.trials() if p.parent not in paths); missing.unlink()
        child=create(self.plan,c.check_batch(self.jobs,self.plan))
        self.assertEqual(child['trial_count'],1)
        self.assertEqual(child['rerun']['trials'][0]['repetition'],2)
    def test_pending_review_keeps_budget_checks_and_raw_score(self):
        self.mark_pending()
        self.plan['token_budget']=dict(input_tokens=100,output_tokens=10,enforcement='post_run_score')
        self.plan.pop('plan_sha256'); self.plan['plan_sha256']=c.digest(self.plan)
        for path in self.trials():
            result=c.read(path); result['agent_result']=dict(n_input_tokens=100,n_output_tokens=10); c.save(path,result)
        path=self.trials()[0]; original=c.read(path)
        for usage,expected in ((dict(n_input_tokens=100,n_output_tokens=10),'pending_review'),
                               (dict(n_input_tokens=101,n_output_tokens=10),'over_token_budget'),
                               (dict(n_input_tokens=100,n_output_tokens=11),'over_token_budget'),
                               (dict(n_input_tokens=None,n_output_tokens=10),'usage_missing')):
            with self.subTest(usage=usage):
                data=copy.deepcopy(original); data['agent_result']=usage; c.save(path,data)
                row=c.check_batch(self.jobs,self.plan)['rows'][0]
                self.assertEqual(row['status'],expected); self.assertEqual(row['raw_success'],0)
                self.assertTrue(row['success_pending_review'])
                self.assertEqual(row['success'],0 if expected=='over_token_budget' else None)
                self.assertEqual(c.read(path.parent/'verifier/reward.json')['success_pending_review'],1)
    def test_pending_review_round_trip_preserves_evidence_and_counts(self):
        paths=self.mark_pending(); before={p.relative_to(self.jobs):c.inventory(p) for p in paths}
        d.seal(self.jobs,self.plan,{'test':SECRET.encode()}); archive=pack(self.root,self.jobs,self.plan)
        self.assertIn('pending review: 2',(self.jobs/'fixture-MANIFEST.md').read_text())
        destination=self.root/'received'; receipt=d.receive(archive,self.plan,destination,require_complete=True)
        self.assertEqual(receipt['report']['status_counts'],{'pending_review':2,'unsolved':4})
        self.assertEqual(before,{p:c.inventory(destination/'agents'/p) for p in before})
        self.assertIn('0/4 solved; pending review: 2',(destination/'review/README.md').read_text())
        pages=[p.read_text() for p in (destination/'review').glob('trial-*.md')]
        self.assertEqual(sum('held for human review' in p for p in pages),2)
        self.assertEqual(sum('review_frames/step_00003.png' in p for p in pages),2)
    def test_authorized_rerun_pending_review_is_counted_without_overwriting_original(self):
        from create_agent_batch_rerun import create
        self.mark_pending(); missing=self.trials()[1]; missing.unlink()
        original=d.report_with_mirror(self.jobs,self.plan); child=create(self.plan,original)
        spec=child['jobs'][0]; task=child['tasks'][0]; path=trial(self.jobs,spec,task,child,0)
        pending_review(path,task)
        rerun=c.check_batch(self.jobs,child); rerun['delivery_errors']=[]
        report=d.combined([original,rerun],[self.plan,child])
        self.assertEqual(c.outcome_counts(report)['pending_review_trials'],3)
        self.assertEqual(c.outcome_counts(report)['scored_trials'],3)
        self.assertTrue(report['delivery_complete']); self.assertTrue(report['evaluation_complete'])
        self.assertEqual(report['rows'],original['rows']); self.assertFalse(missing.exists())
    def test_all_k_and_missing_job(self):
        self.assertTrue(c.check_batch(self.jobs,self.plan)['evaluation_complete'])
        self.trials()[0].unlink()
        report=c.check_batch(self.jobs,self.plan); self.assertEqual(report['planned_trials'],6); self.assertFalse(report['evaluation_complete'])
        shutil.rmtree(self.jobs/self.plan['jobs'][1]['job'])
        report=c.check_batch(self.jobs,self.plan); self.assertEqual(report['status_counts']['pending'],3)
    def test_wrong_binding_and_conflicting_rewards(self):
        path=self.trials()[0].parent; proof=c.read(path/'verifier/verdict.json'); proof['evidence']['runtime_binding']['binding_id']='b'*64
        c.save(path/'verifier/verdict.json',proof)
        self.assertEqual(c.check_batch(self.jobs,self.plan)['status_counts']['identity_mismatch'],1)
        result=c.read(path/'result.json'); result['verifier_result']['rewards']['success']=1; c.save(path/'result.json',result)
        self.assertEqual(c.check_batch(self.jobs,self.plan)['status_counts']['verdict_mismatch'],1)
    def test_success_without_media_incomplete_delivery(self):
        path=self.trials()[0].parent
        for rel in ('result.json','verifier/reward.json','verifier/verdict.json'):
            data=c.read(path/rel)
            if rel=='result.json': data['verifier_result']['rewards']['success']=1
            elif rel.endswith('reward.json'): data['success']=1
            else: data['reward']['success']=1; data['success']=True
            c.save(path/rel,data)
        report=c.check_batch(self.jobs,self.plan)
        self.assertTrue(report['evaluation_complete']); self.assertFalse(report['delivery_complete'])
        (path/'verifier/replay.mp4').write_bytes(b'broken video file')
        (path/'verifier/replay.last.png').write_bytes(b'broken picture')
        report=c.check_batch(self.jobs,self.plan)
        self.assertFalse(report['delivery_complete']); self.assertIn('invalid media container',str(report['rows']))
    def test_infra_timeout_and_budget(self):
        path=self.trials()[0]
        data=c.read(path); data['exception_info']={'exception_type':'AgentTimeoutError'}; c.save(path,data)
        self.assertTrue(c.check_batch(self.jobs,self.plan)['evaluation_complete'])
        cfg=c.read(path.parent/'config.json'); cfg['agent_timeout_multiplier']=2; c.save(path.parent/'config.json',cfg)
        self.assertFalse(c.check_batch(self.jobs,self.plan)['evaluation_complete'])
    def test_account_failure(self):
        path=self.trials()[0].parent/'agent/codex.txt'; path.write_text(json.dumps({'type':'turn.failed','error':{'message':'401 Unauthorized'}})+'\n')
        self.assertEqual(c.check_batch(self.jobs,self.plan)['status_counts']['infra_failed'],1)
    def test_seal_original_scan_tar_receive(self):
        report=d.seal(self.jobs,self.plan,{'test':SECRET.encode()}); self.assertTrue(report['delivery_complete'])
        env=self.root/'rcb.env'; env.write_text('OPENAI_API_KEY='+SECRET+'\n')
        # These are the original helper commands. Scanner automatically includes sibling mirror.
        for flags in (['--redact'],[]):
            subprocess.run([sys.executable,ROOT/'scripts/scan_secrets.py',self.jobs,'--env-file',env,*flags],check=True,capture_output=True)
        archive=pack(self.root,self.jobs,self.plan)
        self.assertNotIn(SECRET,(self.jobs.with_name('agents_mirror')/self.plan['jobs'][0]['job']/'history.txt.v0').read_text())
        shutil.rmtree(self.jobs.parent); shutil.rmtree(self.root/'tasks')
        dest=self.root/'receiver/jobs'; receipt=d.receive(archive,self.plan,dest,require_complete=True)
        self.assertEqual(receipt['report']['observed_trials'],6); self.assertTrue((dest/'review/README.md').exists())
        self.assertEqual(d.receive(archive,self.plan,dest,require_complete=True),receipt)
        self.assertEqual(len(list((dest/'review').glob('trial-*.md'))),6)
    def test_sealed_mutation_and_expected_assignment(self):
        d.seal(self.jobs,self.plan,{'test':SECRET.encode()})
        changed=copy.deepcopy(self.plan); changed['helper']='someone-else'; changed.pop('plan_sha256'); changed['plan_sha256']=c.digest(changed)
        with self.assertRaisesRegex(ValueError,'maintainer'): d.verify_tree(self.jobs.parent,changed)
        self.trials()[0].write_text('{}')
        with self.assertRaisesRegex(ValueError,'inventory'): d.verify_tree(self.jobs.parent,self.plan)
    def test_extra_prefixed_batch_blocked(self):
        (self.jobs/'fixture-other-job').mkdir()
        with self.assertRaises(ValueError): d.seal(self.jobs,self.plan,{'test':SECRET.encode()})
    def test_archive_traversal_and_links(self):
        for kind in ('traversal','link','duplicate'):
            archive=self.root/(kind+'.tar.gz')
            with tarfile.open(archive,'w:gz') as tar:
                entry=tarfile.TarInfo('../escape' if kind=='traversal' else 'agents/file')
                if kind=='link': entry.type=tarfile.SYMTYPE; entry.linkname='/etc/passwd'
                tar.addfile(entry)
                if kind=='duplicate': tar.addfile(entry)
            archive.with_name(archive.name+'.sha256').write_text(c.sha(archive)+'  '+archive.name+'\n')
            dest=self.root/kind; dest.mkdir()
            with self.assertRaises(ValueError): d.unpack(archive,dest,self.plan)
    def test_env_file_auth_resolved_before_scanning(self):
        auth=self.root/'auth.json'; c.save(auth,{'tokens':{'access_token':'synthetic-token-12345'}})
        env=self.root/'rcb.env'; env.write_text('CODEX_FORCE_AUTH_JSON=1\nCODEX_AUTH_JSON_PATH='+str(auth)+'\n')
        resolved,path=r.credentials({'ENV_FILE':str(env),'HF_TOKEN':'not-for-agent'})
        self.assertEqual(path,auth); self.assertNotIn('HF_TOKEN',resolved); self.assertTrue(r.auth_secrets(resolved,path))
        env.write_text('HF_TOKEN=no\n')
        with self.assertRaises(ValueError): r.credentials({'ENV_FILE':str(env)})
    def test_dispatch_override_rejected(self):
        for env in ({'K':'1'},{'MODEL':'different/model'},{'LOG_MIRROR':'0'},{'MODES':'limited'}):
            with self.assertRaises(ValueError): r.settings(self.plan,self.plan['task_bases'],env)
        r.settings(self.plan,self.plan['task_bases'],{'K':'3','MODES':'limited unlimited'})
    def test_fixed_oracle_selection(self):
        import yaml
        import sample_difficulty_instances as s
        cfg=yaml.safe_load((ROOT/'configs/sweeps/oracle_reference.yaml').read_text())
        rows=s.sample_instances(cfg)
        self.assertEqual(len(rows),39)
        self.assertTrue(all(row['scene_seed']==0 and row['variation_id']==row['difficulty'] and row['draws']=={} for row in rows))
    def test_no_seal_under_writers(self):
        mp=self.jobs/'fixture-metadata.json'; data=c.read(mp); data['lanes']=[{'status':'running'}]; c.save(mp,data)
        with self.assertRaisesRegex(ValueError,'running'): d.seal(self.jobs,self.plan,{'test':SECRET.encode()})
    def test_authorized_rerun_preserves_original_and_requires_dispatch(self):
        import types
        import check_agent_batch_hf as hf
        from create_agent_batch_rerun import create
        self.plan['upload']={'type':'hf','repo_id':'test/private','prefix':'helpers/fixture/fixture'}
        self.plan.pop('plan_sha256'); self.plan['plan_sha256']=c.digest(self.plan)
        c.save(self.jobs/'fixture-plan.json',self.plan)
        metadata=c.read(self.jobs/'fixture-metadata.json'); metadata['plan_sha256']=self.plan['plan_sha256']
        c.save(self.jobs/'fixture-metadata.json',metadata)
        missing=self.trials()[0]; missing.unlink()
        child=create(self.plan,c.check_batch(self.jobs,self.plan)); self.assertEqual(child['trial_count'],1)
        d.seal(self.jobs,self.plan,{'test':SECRET.encode()})
        c.save(self.jobs/(child['batch']+'-plan.json'),child)
        c.save(self.jobs/(child['batch']+'-metadata.json'),dict(plan_sha256=child['plan_sha256'],host={},lanes=[],images={}))
        spec=child['jobs'][0]; task=child['tasks'][0]; trial(self.jobs,spec,task,child,0)
        mirror=self.jobs.with_name('agents_mirror')/spec['job']; mirror.mkdir(); (mirror/'history.txt').write_text('rerun')
        c.save(self.jobs/(spec['job']+'-mirror.json'),{'complete':True})
        d.seal(self.jobs,child,{'test':SECRET.encode()})
        self.assertFalse(d.verify_tree(self.jobs.parent,self.plan)['evaluation_complete'])
        archive=pack(self.root,self.jobs,self.plan)
        with tempfile.TemporaryDirectory() as td:
            with self.assertRaisesRegex(ValueError,'unlisted'): d.unpack(archive,Path(td),self.plan)
        received=d.receive(archive,self.plan,self.root/'receive',require_complete=True,reruns=[child])
        self.assertTrue(received['report']['delivery_complete']); self.assertFalse(received['report']['original_evaluation_complete'])
        self.assertFalse(missing.exists())
        shutil.copy(self.jobs/'fixture-MANIFEST.md',self.root/'MANIFEST.md')
        class Hub:
            def call(self,action,**kw):
                return {'auth':None,'private':True,'head':'fixture-revision','info':{}}[action]
        args=types.SimpleNamespace(verify_uploaded=False,rerun_assignment=[])
        with self.assertRaisesRegex(ValueError,'unlisted'): hf.check(self.root,self.plan,args,Hub())
        authorization=self.root/'authorized-rerun.json'; c.save(authorization,child)
        args.rerun_assignment=[authorization]
        self.assertTrue(hf.check(self.root,self.plan,args,Hub())['delivery_complete'])
    def test_token_rotations_keep_private_scan_history(self):
        import asyncio
        from harbor_agents.persistent_auth import persist_auth
        auth=self.root/'auth.json'; history=self.root/'private-history.json'
        c.save(auth,{'tokens':{'account_id':'fixture-account','access_token':'old-access','refresh_token':'old-refresh'}})
        class Env:
            async def download_file(self,remote,path): c.save(path,{'tokens':{'account_id':'fixture-account','access_token':'new-access','refresh_token':'new-refresh'}})
        with patch.dict(os.environ,{'TOPOGYM_AUTH_HISTORY':str(history)}): asyncio.run(persist_auth(Env(),'remote',auth))
        self.assertEqual(set(c.read(history)['tokens'].values()),{'old-access','old-refresh','new-access','new-refresh'})
        self.assertEqual(history.stat().st_mode&0o777,0o600)
    def test_remote_hf_private_and_hash_checks(self):
        import types
        import check_agent_batch_hf as hf
        from difficulty_results_hf import file_identity
        d.seal(self.jobs,self.plan,{'test':SECRET.encode()}); archive=pack(self.root,self.jobs,self.plan)
        shutil.copy(self.jobs/'fixture-MANIFEST.md',self.root/'MANIFEST.md')
        plan=copy.deepcopy(self.plan); plan['upload']={'type':'hf','repo_id':'test/private','prefix':'helpers/fixture/fixture'}
        # Target selection is normally frozen at publication; this unit isolates
        # private/remote hashing, using the original plan for local verification.
        original=hf.unpack
        files=[archive,archive.with_name(archive.name+'.sha256'),self.root/'MANIFEST.md']
        class Hub:
            private=True; changed=False
            def call(self,action,**kw):
                if action=='private': return self.private
                if action=='head': return 'fixture-revision'
                if action=='info':
                    return {plan['upload']['prefix']+'/'+p.name:dict(size=p.stat().st_size,sha256='bad' if self.changed else c.sha(p)) for p in files}
        hub=Hub(); args=types.SimpleNamespace(verify_uploaded=True)
        with patch.object(hf,'unpack',lambda a,b,p,**kw:original(a,b,self.plan,**kw)):
            self.assertTrue(hf.check(self.root,plan,args,hub)['remote_verified'])
            hub.changed=True
            with self.assertRaisesRegex(ValueError,'different'): hf.check(self.root,plan,args,hub)
            hub.private=False
            with self.assertRaisesRegex(ValueError,'private'): hf.check(self.root,plan,args,hub)
    def test_publication_checks_proof_before_writing_and_pins_packages(self):
        import types
        import publish_agent_batch as pub
        repository=self.root/'publisher'; repository.mkdir(); (repository/'tasks').mkdir()
        (repository/'tasks/dataset.toml').write_text('[dataset]\nname="fixture"\nversion="1"\n')
        for folder in ('scripts','bash_scripts','requirements','images/difficulty-eval','harbor_agents','topogym/utils'):
            dst=repository/folder; dst.mkdir(parents=True,exist_ok=True)
            for p in (ROOT/folder).iterdir():
                if p.is_file(): shutil.copyfile(p,dst/p.name)
        run=self.root/'prepared'; run.mkdir()
        (run/'source/scripts').mkdir(parents=True); (run/'source/scripts/difficulty_eval.py').write_text('# synthetic probe\n')
        row=dict(slug='topogym-cast-coil-easy-o00',task_id='cast_coil',difficulty='easy',sample_id='s00',task_number=8,scene_seed=0,variation_id='easy')
        row['sample_sha256']=c.digest(row)
        manifest=dict(schema_version=1,instances=[row],instance_count=1,trial_count=2,release={'name':'synthetic'},source_sha256='a'*64,
            settings=dict(agent_wall_clock_s=43200,native_batch=dict(repetitions=3,agent='codex',model='openai/gpt-6-sol',effort='xhigh',
                token_budget=dict(input_tokens=150000000,output_tokens=10000000,enforcement='post_run_score'))))
        manifest['manifest_sha256']=c.digest(manifest); c.save(run/'manifest.lock.json',manifest)
        c.save(run/'source_identity.json',{'sha256':'a'*64}); c.save(run/'image.json',{'images':{}})
        for mode in ('privileged','standard'):
            p=run/'tasks'/(row['slug']+'-'+mode); actor=p/('environment/sim' if mode=='standard' else 'environment'); actor.mkdir(parents=True)
            c.save(actor/'instance.json',dict(task='cast_coil',seed=0,variation_id='easy'))
            (p/'task.toml').write_text('[agent]\ntimeout_sec=43200\n')
            if mode=='privileged': (actor/'rcb_topogym.py').write_text('# synthetic tooling\n')
            (p/'environment/docker-compose.yaml').write_text('services:\n  main:\n    labels: {topogym.old: old-host}\n    user: "1:2"\n    environment: {NVIDIA_VISIBLE_DEVICES: GPU-old}\n')
        prepared={'files':{p.relative_to(run).as_posix():c.sha(p) for p in c.files(run/'tasks')}}
        build=run/'build'/row['slug']; c.save(build/'prepared.json',prepared)
        c.save(build/'preflight.ok.json',{'passed':True,'evidence_identity':{'prepared_sha256':'stale'}})
        task_module=types.ModuleType('harbor.models.task.task')
        task_module.Task=lambda path:types.SimpleNamespace(checksum=c.digest(c.inventory(path)))
        binding=dict(schema_version=1,instance_sha256='0'*64,asset_files={},tooling_sha256='0'*64,runtime={'source':{'sha256':'0'*64,'files':1}},image={'reference':'fixture','id':'sha256:'+'0'*64},creation_source={})
        with patch.object(pub,'identity',return_value=manifest['release']),patch.object(pub,'verify_source'),patch.object(pub,'require_task') as require,patch.object(pub,'task_lock',return_value=binding),patch.dict(sys.modules,{'harbor.models.task.task':task_module}):
            with self.assertRaisesRegex(ValueError,'preflight'): pub.publish(run,repository,'publish','fixture')
            self.assertEqual(list((repository/'tasks').iterdir()),[repository/'tasks/dataset.toml'])
            proof=dict(passed=True,files=prepared['files'],evidence_identity=dict(prepared_sha256=c.sha(build/'prepared.json'),probe_version=5,
                image=c.read(run/'image.json'),probe_sha256=c.sha(run/'source/scripts/difficulty_eval.py'),
                tool_sha256=c.sha(run/'tasks'/(row['slug']+'-privileged')/'environment/rcb_topogym.py'),gpu_profile='fixture, not GPU evidence',client_image={'id':'synthetic'}))
            c.save(build/'preflight.ok.json',proof)
            dispatch=pub.publish(run,repository,'publish','fixture'); plan=c.validate(c.read(dispatch))
            self.assertEqual(plan['trial_count'],6); self.assertEqual(require.call_count,4)
            self.assertEqual(plan['agent']['model'],'openai/gpt-6-sol')
            self.assertEqual(plan['token_budget'],manifest['settings']['native_batch']['token_budget'])
            self.assertTrue(all(t['agent_timeout_sec']==43200 for t in plan['tasks']))
            for task in plan['tasks']: c.package(repository,task)
            text=(repository/'tasks'/plan['tasks'][0]['name']/'environment/docker-compose.yaml').read_text()
            self.assertNotIn('GPU-old',text); self.assertIn('TOPOGYM_GPU_UUID',text)
            dataset=(repository/'tasks/dataset.toml').read_text()
            smoke=pub.publish(run,repository,'smoke','fixture',repetitions=1,task_bases=[row['slug']])
            self.assertEqual(c.read(smoke)['trial_count'],2)
            self.assertEqual(dataset,(repository/'tasks/dataset.toml').read_text())
    def test_auth_canary_uses_temporary_profile_and_persists_same_account(self):
        from check_agent_batch_auth import canary
        auth=self.root/'auth.json'; c.save(auth,{'tokens':{'account_id':'fixture','access_token':'old'}})
        tool=self.root/'bin/codex'; tool.parent.mkdir()
        tool.write_text('#!'+sys.executable+'\n'+'''import json,os,pathlib,sys
if '--version' in sys.argv: print('codex-cli 0.157.0'); raise SystemExit
assert 'HF_TOKEN' not in os.environ
p=pathlib.Path(os.environ['CODEX_HOME'])/'auth.json'
data=json.loads(p.read_text()); data['tokens']['access_token']='rotated'; p.write_text(json.dumps(data))
print(json.dumps({'type':'turn.completed'}))
'''); tool.chmod(0o755)
        result=canary(self.plan,dict(PATH=str(tool.parent),CODEX_AUTH_JSON_PATH=str(auth),HF_TOKEN='not-for-model'))
        self.assertTrue(result['passed']); self.assertEqual(c.read(auth)['tokens']['access_token'],'rotated')
    @unittest.skipUnless(shutil.which('ffmpeg'),'ffmpeg required only for generating real media fixtures')
    def test_real_media_and_truncation(self):
        video=self.root/'clip.mp4'; picture=self.root/'clip.png'
        subprocess.run(['ffmpeg','-v','error','-f','lavfi','-i','color=size=64x64:rate=10','-frames:v','2','-threads','1',str(video)],check=True)
        subprocess.run(['ffmpeg','-v','error','-i',str(video),'-frames:v','1','-threads','1',str(picture)],check=True)
        self.assertTrue(c.media_container_valid(video)); self.assertTrue(c.media_container_valid(picture))
        for path in (video,picture):
            data=path.read_bytes(); path.write_bytes(data[:-8]); self.assertFalse(c.media_container_valid(path))
    def test_relocated_task_map_does_not_use_original_host(self):
        from trial_task_paths import original_task
        d.seal(self.jobs,self.plan,{'test':SECRET.encode()}); archive=pack(self.root,self.jobs,self.plan)
        dest=self.root/'other-host/jobs'; d.receive(archive,self.plan,dest,require_complete=True)
        moved=self.root/'other-host/checkout/tasks'; moved.parent.mkdir(); shutil.copytree(self.root/'tasks',moved)
        d.bind_tasks(dest,self.plan,moved)
        trial_path=dest/'agents'/self.trials()[0].parent.relative_to(self.jobs)
        self.assertEqual(original_task(trial_path),moved/self.plan['tasks'][0]['name'])
        (moved/self.plan['tasks'][0]['name']/'task.toml').write_text('changed')
        with self.assertRaisesRegex(ValueError,'changed'): original_task(trial_path)

if __name__=='__main__': unittest.main()
