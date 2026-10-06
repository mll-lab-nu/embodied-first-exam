"""GPU startup and post-job stop contracts; no model calls or physics rollout."""
from contextlib import ExitStack
import copy
import importlib.util
import io
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(ROOT/'scripts'),str(ROOT)]
import agent_batch_contract as c
import agent_batch_delivery as delivery
import agent_batch_host as host
import agent_batch_runtime as runner
spec=importlib.util.spec_from_file_location('batch_fixture',ROOT/'ci_checks/test-native-agent-batch.py')
fixture=importlib.util.module_from_spec(spec); spec.loader.exec_module(fixture)
SECRET=fixture.SECRET


class GPUCheckTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory(); self.root=Path(self.tmp.name)
        self.jobs,self.plan=fixture.fixture(self.root)
        self.env=dict(TOPOGYM_GPU_UUID='GPU-test',OPENAI_API_KEY=SECRET)
        for task in self.plan['tasks']:
            name='main' if task['mode']=='privileged' else 'sim'
            service=dict(runtime='nvidia',shm_size='2gb',environment={'NVIDIA_DRIVER_CAPABILITIES':'all'},
                         deploy={'resources':{'reservations':{'devices':[{'driver':'nvidia','capabilities':['gpu'],
                                 'device_ids':['${TOPOGYM_GPU_UUID:-0}']}]}}})
            if name=='sim': service['image']='fixture:image'
            c.save(self.root/'tasks'/task['name']/'environment/docker-compose.yaml',{'services':{name:service}})

    def tearDown(self): self.tmp.cleanup()

    def check(self):
        return host.require_gpu_containers(self.plan,self.root,self.env,self.root/'checks',{'model':SECRET.encode()})

    def test_uses_declared_gpu_settings_in_both_modes_once_and_no_container_credentials(self):
        self.assertEqual(len(host.gpu_configurations(self.plan,self.root)),1)
        calls=[]
        def execute(argv,**kw):
            calls.append(argv)
            config=c.read(Path(argv[argv.index('-f')+1]))['services']['gpucheck']
            self.assertEqual(config['runtime'],'nvidia')
            self.assertEqual(config['image'],'fixture:image')
            self.assertEqual(config['environment']['NVIDIA_DRIVER_CAPABILITIES'],'all')
            self.assertNotIn(SECRET,json.dumps(config)); self.assertNotIn(SECRET,str(argv))
            self.assertEqual(kw['env']['TOPOGYM_GPU_UUID'],'GPU-test')
            return subprocess.CompletedProcess(argv,0,'TOPOGYM_GPU_CHECK {}\n' if 'run' in argv else '', '')
        with patch.object(host.subprocess,'run',side_effect=execute): result=self.check()
        self.assertTrue(result['passed']); self.assertEqual(len(result['checks']),1)
        self.assertEqual(len(result['checks'][0]['tasks']),2)
        self.assertEqual(len(calls),2); self.assertIn('down',calls[-1])
        self.assertEqual(calls[0][3],calls[1][3])

    def test_gpu_failure_retains_redacted_error_and_cleans_only_own_project(self):
        responses=[subprocess.CompletedProcess([],1,'','unknown or invalid runtime name: nvidia '+SECRET),
                   subprocess.CompletedProcess([],0,'','')]
        with patch.object(host.subprocess,'run',side_effect=responses) as run:
            with self.assertRaisesRegex(ValueError,'No model request or trial was started') as error: self.check()
        self.assertNotIn(SECRET,str(error.exception)); self.assertIn('nvidia',str(error.exception))
        self.assertIn('down',run.call_args.args[0])
        self.assertTrue(run.call_args.args[0][3].startswith('topogym-gpu-check-'))
        summary=c.read(next((self.root/'checks').glob('*/summary.json')))
        self.assertFalse(summary['passed'])
        log=Path(summary['checks'][0]['log'])
        self.assertNotIn(SECRET,log.read_text()); self.assertEqual(log.stat().st_mode & 0o777,0o600)

    def test_timeout_retains_partial_diagnostic_and_cleans_up(self):
        with patch.object(host.subprocess,'run',side_effect=[subprocess.TimeoutExpired('docker',90,output=b'partial output'),
                                                           subprocess.CompletedProcess([],0,'','')]) as run:
            with self.assertRaisesRegex(ValueError,'timed out'): self.check()
        self.assertEqual(run.call_count,2)
        self.assertIn('partial output',next((self.root/'checks').glob('*/probe-0.log')).read_text())

    def test_zero_exit_without_cuda_marker_and_failed_cleanup_are_rejected(self):
        for out,cleanup_rc in [('',0),('TOPOGYM_GPU_CHECK {}',1)]:
            with self.subTest(out=out,cleanup_rc=cleanup_rc),patch.object(host.subprocess,'run',side_effect=[
                subprocess.CompletedProcess([],0,out,''),subprocess.CompletedProcess([],cleanup_rc,'','cleanup failed')]):
                with self.assertRaises(ValueError): self.check()


class JobCheckTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory(); self.root=Path(self.tmp.name)
        self.jobs,self.plan=fixture.fixture(self.root); self.spec=self.plan['jobs'][0]
        self.trial=next((self.jobs/self.spec['job']).iterdir())

    def tearDown(self): self.tmp.cleanup()

    def check(self): return runner.check_job_execution(self.jobs,self.plan,self.spec,{'model':SECRET.encode()})

    def test_valid_zero_scores_continue(self): self.assertTrue(self.check()['passed'])

    def test_harbor_runtime_exception_is_failure_and_redacted(self):
        result=c.read(self.trial/'result.json')
        result['exception_info']=dict(exception_type='RuntimeError',exception_message='unknown runtime nvidia '+SECRET)
        c.save(self.trial/'result.json',result); (self.trial/'verifier/reward.json').unlink()
        report=self.check()
        self.assertFalse(report['passed']); self.assertEqual(report['status_counts']['infra_failed'],1)
        self.assertIn('nvidia',report['failures'][0]['message']); self.assertNotIn(SECRET,json.dumps(report))

    def test_missing_trial_result_reward_and_usage_each_stop(self):
        for kind in ('trial','result','reward','usage'):
            with self.subTest(kind=kind):
                with tempfile.TemporaryDirectory() as td:
                    jobs,plan=fixture.fixture(Path(td)); spec=plan['jobs'][0]
                    trial=next((jobs/spec['job']).iterdir())
                    if kind=='trial': shutil.rmtree(trial)
                    elif kind=='result': (trial/'result.json').unlink()
                    elif kind=='reward': (trial/'verifier/reward.json').unlink()
                    else:
                        plan['token_budget']=dict(input_tokens=100,output_tokens=100,enforcement='post_run_score')
                        plan.pop('plan_sha256'); plan['plan_sha256']=c.digest(plan)
                    self.assertFalse(runner.check_job_execution(jobs,plan,spec,{'model':SECRET.encode()})['passed'])

    def test_pending_review_and_scored_agent_timeout_do_not_stop(self):
        fixture.pending_review(self.trial,self.plan['tasks'][0])
        result=c.read(self.trial/'result.json'); result['exception_info']={'exception_type':'AgentTimeoutError'}
        c.save(self.trial/'result.json',result)
        self.assertTrue(self.check()['passed'])


class LaneTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory(); self.root=Path(self.tmp.name)
        self.jobs,self.plan=fixture.fixture(self.root)
        self.saved=self.root/'saved'; self.saved.mkdir()
        for spec in self.plan['jobs']:
            shutil.move(self.jobs/spec['job'],self.saved/spec['job'])
        # Leave task packages, but start with an entirely unclaimed batch.
        shutil.rmtree(self.jobs.parent); self.jobs.mkdir(parents=True)
        self.assignment=self.root/'assignment.json'; c.save(self.assignment,self.plan)
        self.started=[]

    def tearDown(self): self.tmp.cleanup()

    def harness(self,*,broken=False,gpu_failure=False):
        stack=ExitStack(); self.addCleanup(stack.close)
        stack.enter_context(patch.dict(os.environ,{'PATH':os.environ['PATH'],'JOBS':str(self.jobs),'OPENAI_API_KEY':SECRET},clear=True))
        stack.enter_context(patch.object(runner,'ROOT',self.root))
        stack.enter_context(patch.object(runner,'tooling'))
        stack.enter_context(patch.object(runner,'image_records',return_value={}))
        stack.enter_context(patch.object(runner,'host_info',return_value={}))
        stack.enter_context(patch.object(runner,'optional',return_value='fixture'))
        stack.enter_context(patch('agent_batch_images.ensure_images'))
        stack.enter_context(patch('topogym_versions.require_task'))
        def command(argv,**kw): return 'GPU-test' if argv[0]=='nvidia-smi' else ''
        stack.enter_context(patch.object(runner,'command',side_effect=command))
        self.canary=stack.enter_context(patch('check_agent_batch_auth.canary',return_value={'passed':True}))
        self.gpu=stack.enter_context(patch.object(host,'require_gpu_containers',side_effect=ValueError('fixture GPU unavailable') if gpu_failure else None))
        class Mirror:
            def __init__(mirror,jobs,spec,plan,owner,private,env):
                mirror.job=jobs/spec['job'];mirror.job.mkdir();mirror.destination=jobs.with_name('agents_mirror')/spec['job']
            def start(mirror): pass
            def finish(mirror,secrets): mirror.destination.mkdir(parents=True);return True
        stack.enter_context(patch.object(runner,'Mirror',Mirror))
        def guarded(argv,output,**kwargs):
            job=argv[argv.index('--job-name')+1];self.started.append(job)
            shutil.copytree(self.saved/job,self.jobs/job,dirs_exist_ok=True)
            if broken:
                for path in (self.jobs/job).glob('*/result.json'):
                    result=c.read(path);result['exception_info']={'exception_type':'RuntimeError','exception_message':'unknown or invalid runtime name: nvidia'}
                    c.save(path,result);(path.parent/'verifier/reward.json').unlink()
            (output/'runtime.log').write_text('Synthetic Harbor exit zero\n')
            return 0
        stack.enter_context(patch('topogym.utils.process_limits.run_guarded',side_effect=guarded))

    def run_lane(self): return runner.run(self.plan['batch'],self.plan['task_bases'],self.assignment)

    def test_gpu_failure_precedes_canary_registration_claims_and_seal(self):
        self.harness(gpu_failure=True)
        with self.assertRaisesRegex(ValueError,'GPU unavailable'): self.run_lane()
        self.canary.assert_not_called(); self.assertEqual(self.started,[])
        for name in ('fixture-plan.json','fixture-metadata.json','fixture-inventory.json','.claims'):
            self.assertFalse((self.jobs/name).exists(),name)

    def test_zero_exit_with_trial_exceptions_stops_after_first_job_and_seals_partial(self):
        self.harness(broken=True)
        self.assertEqual(self.run_lane(),1)
        self.assertEqual(self.started,[self.plan['jobs'][0]['job']])
        stop=c.read(self.jobs/'fixture-stop.json'); self.assertEqual(stop['code'],'trial_execution_failure')
        execution=c.read(self.jobs/(self.started[0]+'-execution.json'))
        self.assertEqual(execution['harbor_returncode'],0); self.assertEqual(execution['returncode'],2)
        report=delivery.verify_tree(self.jobs.parent,self.plan)
        self.assertFalse(report['delivery_complete'])
        self.assertEqual(report['status_counts'],{'infra_failed':3,'pending':3})
        self.assertEqual(c.read(self.jobs/'fixture-metadata.json')['lanes'][0]['returncode'],1)
        self.assertIn('finished rc=1',(self.jobs/'fixture.log').read_text())
        started=list(self.started)
        self.assertEqual(self.run_lane(),1);self.assertEqual(self.started,started)

    def test_unsolved_trials_complete_both_jobs_and_sealed_inventory_matches(self):
        self.harness()
        self.assertEqual(self.run_lane(),0)
        self.assertEqual(len(self.started),2)
        self.assertFalse((self.jobs/'fixture-stop.json').exists())
        report=delivery.verify_tree(self.jobs.parent,self.plan)
        self.assertTrue(report['delivery_complete']); self.assertEqual(report['status_counts'],{'unsolved':6})


if __name__=='__main__': unittest.main()
