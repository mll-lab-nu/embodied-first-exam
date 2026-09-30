#!/usr/bin/env python3
"""CPU workflow contracts. Synthetic Harbor records are NOT physics/model evidence."""
from __future__ import annotations
import ast
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import shutil
import signal
import subprocess
import sys
import tempfile
import unittest
import time
from types import SimpleNamespace
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / "scripts"), str(ROOT / "harbor_templates/topogym/common"), str(ROOT)]
import sample_difficulty_instances as sampler
import difficulty_eval as evaluation
from collect_batch_results import classify_trial, collect_manifest
import rcb_topogym


class SamplingTests(unittest.TestCase):
    def test_selector_mapping_and_validation(self):
        self.assertEqual(sampler.select_tasks("all"), list(sampler.TASK_IDS))
        self.assertEqual(sampler.select_tasks("9, 8-9,cast_coil"), ["cast_coil", "cast_keyhole"])
        for selector in ("", ",8", "8,", "0", "14", "9-8", "all,8", "cube_pick_place", "1,,3"):
            with self.subTest(selector=selector), self.assertRaises(ValueError):
                sampler.select_tasks(selector)

    def test_seed_prefix_tiers_and_subsets(self):
        for task in sampler.TASK_IDS:
            for tier, difficulty in enumerate(sampler.DIFFICULTIES):
                five = list(sampler.sample_seeds(task, difficulty, 20260929, 5))
                self.assertEqual(five[:1], list(sampler.sample_seeds(task, difficulty, 20260929, 1)))
                self.assertEqual(five[:3], list(sampler.sample_seeds(task, difficulty, 20260929, 3)))
                self.assertEqual(len(set(five)), 5)
                self.assertTrue(all(0 <= s < 2**32 and s % 3 == tier for s in five))
        cfg = dict(task_ids=list(sampler.TASK_IDS), sampling_seed=7, samples_per_difficulty=1)
        all_rows = sampler.sample_instances(cfg)
        subset = sampler.sample_instances(dict(cfg, task_ids=["cast_coil"]))
        self.assertEqual(subset, [r for r in all_rows if r["task_id"] == "cast_coil"])
        self.assertEqual(len(all_rows), 39)
        self.assertTrue(all(r["variation_id"] == "seeded" for r in all_rows))
        self.assertFalse(next(r for r in all_rows if r["task_id"] == "orbits")["evaluable_for_task_success"])

    def test_explicit_selection_and_old_eval_index(self):
        old = rcb_topogym.simulator_config("cast_coil", 0)
        self.assertEqual((old["variation_id"], old["seed"]), ("cast_coil_easy", 0))
        cfg = rcb_topogym.simulator_config("cast_coil", variation_id="seeded", seed=4)
        self.assertEqual((cfg["variation_id"], cfg["seed"]), ("seeded", 4))
        for kwargs in (dict(variation_id="seeded"), dict(seed=2), dict(eval_index=0, variation_id="seeded", seed=0), dict(variation_id="seeded", seed=-1)):
            with self.subTest(kwargs=kwargs), self.assertRaises(ValueError):
                rcb_topogym.simulator_config("cast_coil", **kwargs)

    def test_server_deadline_on_owner_thread(self):
        # Execute the actual deadline/tick functions with fake clock/session, without importing Genesis.
        tree = ast.parse((ROOT / "harbor_templates/topogym/limited/environment/sim/server.py").read_text())
        nodes = [n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name in ("deadline_reached", "ctrl_step")]
        class Session:
            episode_end = None
            calls = 0
            def step(self, action): self.calls += 1; return False
        class Clock:
            @staticmethod
            def monotonic(): return 100
        session = Session(); reasons = []
        ns = dict(np=__import__('numpy'), L=type('L',(),{'Recorder':object}), S=session, E=dict(ready=True,done=False,deadline=99), time=Clock, finish=reasons.append)
        exec(compile(ast.Module(body=nodes,type_ignores=[]), '<server functions>', 'exec'), ns)
        self.assertTrue(ns['ctrl_step'](None,None))
        self.assertEqual(session.calls,0)
        self.assertEqual(reasons,['timeout'])
        ns['E']['done']=True
        self.assertFalse(ns['deadline_reached']())

    def test_explicit_scene_trajectory_needs_no_pickle(self):
        from types import SimpleNamespace
        import numpy as np
        session=SimpleNamespace(task='cast_coil',config=dict(task_id='cast_coil',variation_id='seeded',seed=4),
                                eval_index=None,instance_sha='test',action_dim=2,action_layout=['a','b'])
        with tempfile.TemporaryDirectory() as tmp:
            path=Path(tmp)/'trajectory.npz'
            rcb_topogym.Session.save_trajectory(session,np.zeros((3,2)),path)
            result=rcb_topogym._load_traj(str(path))
            self.assertEqual(result['scene_seed'],4)
            self.assertEqual(result['eval_index'],-1)


class ResultTests(unittest.TestCase):
    def test_completion_is_not_job_file_existence(self):
        row = dict(slug="topogym-cast-coil-easy-s00", evaluable_for_task_success=True)
        with tempfile.TemporaryDirectory() as tmp:
            job = Path(tmp) / "job"
            self.assertEqual(classify_trial(job,row,"unlimited")[0],"pending")
            job.mkdir(); (job / "result.json").write_text('{}')
            self.assertEqual(classify_trial(job,row,"unlimited")[0],"interrupted")
            trial=job/'truncated__id'; (trial/'verifier').mkdir(parents=True)
            result=dict(task_name='topogym/'+row['slug'],finished_at='2026-09-29T00:00:00Z',verifier_result={'rewards':{'success':0}})
            (trial/'result.json').write_text(json.dumps(result))
            reward=trial/'verifier/reward.json'; reward.write_text('{"success":0,"grader_error":0}')
            self.assertEqual(classify_trial(job,row,"unlimited")[0],"unsolved")
            self.assertEqual(classify_trial(job,dict(row,evaluable_for_task_success=False),"unlimited")[0],"not_evaluable")
            reward.write_text('{"success":0,"missing_trajectory":1}')
            self.assertEqual(classify_trial(job,row,"unlimited")[0],"invalid_submission")
            result['exception_info']={'exception_type':'CancelledError'}; (trial/'result.json').write_text(json.dumps(result))
            self.assertEqual(classify_trial(job,row,"unlimited")[0],"interrupted")

    def test_package_budgets_and_twins_without_physics(self):
        import tomllib
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp); tasks=root/'tasks'; build=root/'build'; slug='topogym-cast-coil-easy-s00'
            (build/slug).mkdir(parents=True)
            # Fixed text-generation fixture; no ignored run data or simulation is required.
            shutil.copy(ROOT/'ci_checks/fixtures/difficulty_eval_describe.json',build/slug/'describe.json')
            p=subprocess.run([sys.executable,str(ROOT/'scripts/topogym_mk_task.py'),'cast_coil','--instance',str(ROOT/'tasks/topogym-cast-coil-i00/environment/instance.json'),
                '--slug',slug,'--tasks-root',str(tasks),'--build-root',str(build),'--reuse-describe','--agent-wall-clock-s','21600'],capture_output=True,text=True)
            self.assertEqual(p.returncode,0,p.stdout+p.stderr)
            p=subprocess.run([sys.executable,str(ROOT/'scripts/topogym_mk_limited.py'),'cast_coil','-','--unlimited-task',str(tasks/slug),'--tasks-root',str(tasks),
                '--build-root',str(build),'--agent-wall-clock-s','21600'],capture_output=True,text=True)
            self.assertEqual(p.returncode,0,p.stdout+p.stderr)
            u=tomllib.loads((tasks/slug/'task.toml').read_text()); l=tomllib.loads((tasks/(slug+'-limited')/'task.toml').read_text())
            self.assertEqual((u['agent']['timeout_sec'],l['agent']['timeout_sec']),(21600,21600))
            self.assertEqual(u['verifier']['timeout_sec'],65700)
            self.assertEqual(l['verifier']['collect'][0]['timeout_sec'],45000)
            self.assertEqual((tasks/slug/'environment/instance.json').read_bytes(),(tasks/(slug+'-limited')/'environment/sim/instance.json').read_bytes())
            for folder in (tasks/slug,tasks/(slug+'-limited')):
                harbor_python=ROOT/'.venv-harbor/bin/python'
                if harbor_python.exists():
                    p=subprocess.run([str(harbor_python),'-c',
                        'import sys; from harbor.models.task.task import Task; t=Task(sys.argv[1]); assert t.config.agent.timeout_sec==21600',str(folder)],capture_output=True,text=True)
                    self.assertEqual(p.returncode,0,p.stdout+p.stderr)
                for check in ('check-task-structure','check-task-fields','check-dockerfile','check-instruction','check-verifier-isolation','check-limited-texts'):
                    p=subprocess.run(['bash',str(ROOT/'ci_checks'/f'{check}.sh'),str(folder)],capture_output=True,text=True,
                                     env=dict(os.environ,PATH=str(Path(sys.executable).parent)+os.pathsep+os.environ['PATH']))
                    self.assertEqual(p.returncode,0,p.stdout+p.stderr)


class CommandTests(unittest.TestCase):
    def test_resource_limit_stops_owned_process_only(self):
        unrelated = subprocess.Popen([sys.executable, '-c', 'import time; time.sleep(120)'], start_new_session=True)
        try:
            for cpu, memory in ((90, 10), (10, 90)):
                with self.subTest(cpu=cpu, memory=memory), tempfile.TemporaryDirectory() as tmp:
                    run = Path(tmp)
                    commands = evaluation.Commands(dict(os.environ), run)
                    with patch('psutil.cpu_percent', return_value=cpu), patch('psutil.virtual_memory', return_value=SimpleNamespace(percent=memory)):
                        with self.assertRaisesRegex(evaluation.EvaluationError, '90%'):
                            commands.run_command([sys.executable, '-c', 'import time; time.sleep(120)'], monitor=True)
                    record = json.loads((run / 'resource-stop.json').read_text())
                    self.assertEqual((record['cpu_percent'], record['memory_percent']), (cpu, memory))
                    with self.assertRaises(ProcessLookupError):
                        os.kill(record['pid'], 0)
                    self.assertIsNone(commands.child)
                    self.assertIsNone(unrelated.poll())
        finally:
            unrelated.terminate()
            unrelated.wait(timeout=5)


class WorkflowTests(unittest.TestCase):
    """Run the Python scheduler via both entries with stubs; no Docker or model."""
    def setUp(self):
        folder=ROOT/'runs/test_results'; folder.mkdir(parents=True,exist_ok=True)
        self.tmp=tempfile.TemporaryDirectory(prefix='difficulty_contract_',dir=folder)
        self.root=Path(self.tmp.name)
        for name in ('scripts','bash_scripts','harbor_templates','topogym','configs','images','requirements','ci_checks'):
            shutil.copytree(ROOT/name,self.root/name,ignore=shutil.ignore_patterns('__pycache__','*.pyc'))
        shutil.copy(ROOT/'.dockerignore',self.root/'.dockerignore')
        self.bin=self.root/'mock-bin'; self.bin.mkdir()
        self.run=self.root/'runs/difficulty_trials/check'
        self.jobs=self.root/'jobs/difficulty_trials/check'
        self.env=dict(os.environ,TOPOGYM_EVAL_PYTHON=sys.executable,TOPOGYM_HARBOR=str(self.bin/'harbor'),
                      PATH=str(self.bin)+os.pathsep+os.environ['PATH'],FAKE_RUN=str(self.run))
        for key in ('OPENAI_API_KEY','OPENROUTER_API_KEY','CODEX_FORCE_AUTH_JSON','CODEX_AUTH_JSON_PATH'):
            self.env.pop(key,None)
        self.script=self.root/'bash_scripts/run_difficulty_trials.sh'
        self.executable('nvidia-smi',"print('24000, 0')")
        self.executable('docker',"""import json,os,sys
from pathlib import Path
if sys.argv[1:3]==['image','inspect']:
    d=json.loads((Path(os.environ['FAKE_RUN'])/'image.json').read_text())
    print(json.dumps([{'Id':d['id'],'Config':{'Labels':{'topogym.source':d['source_sha256']}}}]))
""")
        self.executable('harbor',"""import hashlib,json,os,sys,time
from pathlib import Path
args=sys.argv[1:]
def arg(k): return args[args.index(k)+1]
job=Path(arg('-o'))/arg('--job-name'); task=Path(arg('-p'))
assert arg('-n')==arg('-k')=='1' and arg('--max-retries')=='0'
assert not any(os.environ.get('OPENAI_API_KEY','NEVER-IN-ARGV') in a for a in args)
proof={'model':arg('-m'),'agent':arg('-a'),'key_hash':hashlib.sha256(os.environ.get('OPENAI_API_KEY',os.environ.get('OPENROUTER_API_KEY','')).encode()).hexdigest(),
       'force_auth':os.environ.get('CODEX_FORCE_AUTH_JSON'),'auth_path':os.environ.get('CODEX_AUTH_JSON_PATH'),'agent_args':[args[i+1] for i,a in enumerate(args) if a=='--ak']}
(job/'launch-proof.json').write_text(json.dumps(proof))
if os.environ.get('FAKE_HARBOR_MODE')=='interrupt' and not job.name.startswith('canary'):
    (job/'started.marker').write_text(str(os.getpid())); time.sleep(120)
trial=job/'deliberately-truncated__abc'; (trial/'verifier').mkdir(parents=True)
limited=task.name.endswith('-limited'); reward={'success':1 if 'canary' in task.name else 0,'grader_error':0}
if limited: reward['finalized']=1
(trial/'verifier/reward.json').write_text(json.dumps(reward))
(trial/'result.json').write_text(json.dumps({'task_name':'topogym/'+task.name,'task_id':{'path':str(task)},'finished_at':'2026-09-29T00:00:00Z','verifier_result':{'rewards':reward}}))
print(os.environ.get('OPENAI_API_KEY','stub subscription: no key'))
""")
        p=self.call('--phase','plan','--tasks','8')
        self.assertEqual(p.returncode,0,p.stdout+p.stderr)
        manifest=json.loads((self.run/'manifest.lock.json').read_text())
        (self.run/'image.json').write_text(json.dumps(dict(id='sha256:stub',source_sha256=manifest['source_sha256'])))
        for row in manifest['instances']:
            build=self.run/'build'/row['slug']; (build/'smoke/initial_rgb').mkdir(parents=True)
            # Canary only copies this file in the stub test, no physical image is implied.
            (build/'smoke/initial_rgb/camera.png').write_bytes(b'synthetic test image')
            (build/'prepared.json').write_text('{"files":{}}')
            (build/'preflight.ok.json').write_text('{"synthetic_test_only":true}')
            for suffix in ('','-limited'):
                path=self.run/'tasks'/(row['slug']+suffix); path.mkdir(parents=True)
        self.key='contract-test-'+os.urandom(24).hex()

    def tearDown(self):
        self.tmp.cleanup()

    def executable(self,name,body):
        p=self.bin/name; p.write_text('#!'+sys.executable+'\n'+body+'\n'); p.chmod(0o755)

    def call(self,*args,env=None):
        return subprocess.run(['bash',str(self.script),'--run-id','check',*args],env=env or self.env,capture_output=True,text=True,timeout=45)

    def test_python_entry_defaults_and_bash_compatibility(self):
        entry = [sys.executable, str(self.root / 'scripts/difficulty_eval.py')]
        direct = subprocess.run([*entry, '--list-tasks'], env=self.env, capture_output=True, text=True, timeout=10)
        self.assertEqual(direct.returncode, 0, direct.stderr)
        self.assertEqual(direct.stdout, self.call('--list-tasks').stdout)
        p = subprocess.run([*entry, '--run-id', 'defaults', '--phase', 'plan'], env=self.env, capture_output=True, text=True, timeout=30)
        self.assertEqual(p.returncode, 0, p.stdout + p.stderr)
        run = self.root / 'runs/difficulty_trials/defaults'
        manifest = (run / 'manifest.lock.json').read_bytes()
        data = json.loads(manifest)
        self.assertEqual((data['instance_count'], data['trial_count']), (39, 78))
        self.assertEqual(data['settings']['task_ids'], list(sampler.TASK_IDS))
        self.assertEqual((data['settings']['samples_per_difficulty'], data['settings']['agent_wall_clock_s']), (1, 21600))
        p = self.call('--run-id', 'defaults', '--phase', 'plan', '--resume')
        self.assertEqual(p.returncode, 0, p.stdout + p.stderr)
        self.assertEqual(manifest, (run / 'manifest.lock.json').read_bytes())
        self.assertFalse(self.jobs.exists())

    def test_preparation_phases_and_collection_do_not_require_credentials(self):
        for phase in ('prepare', 'preflight'):
            p = self.call('--phase', phase, '--resume')
            self.assertEqual(p.returncode, 0, p.stdout + p.stderr)
        p = self.call('--phase', 'collect', '--resume')
        self.assertEqual(p.returncode, 2, p.stdout + p.stderr)  # all trials still pending
        self.assertFalse(self.jobs.exists())
        build = next((self.run / 'build').iterdir())
        (build / 'preflight.ok.json').unlink()
        (build / 'prepared.json').unlink()
        p = self.call('--phase', 'preflight', '--resume')
        self.assertEqual(p.returncode, 2, p.stdout + p.stderr)
        self.assertIn('phase incomplete', p.stderr)
        (build / 'prepared.json').write_text(json.dumps({'files':{'image.json':'changed-package-hash'}}))
        p = self.call('--phase', 'preflight', '--resume')
        self.assertEqual(p.returncode, 2, p.stdout + p.stderr)
        self.assertIn('prepared package changed', p.stderr)

    def test_run_and_gpu_locks_reject_duplicate_owners(self):
        for path, message, args in (
            (self.run / '.lock', 'another invocation', ('--phase', 'plan')),
            (self.run.parent / '.gpu.lock', 'GPU execution lock', ('--phase', 'prepare')),
        ):
            with self.subTest(path=path), evaluation.lock(path, 'test owns lock'):
                p = self.call(*args, '--resume')
                self.assertEqual(p.returncode, 2, p.stdout + p.stderr)
                self.assertIn(message, p.stderr)
        p = self.call('--phase', 'prepare', '--resume')
        self.assertEqual(p.returncode, 0, p.stdout + p.stderr)
        self.assertFalse(self.jobs.exists())

    def test_all_blocks_models_after_partial_prepare_failure(self):
        build = next((self.run / 'build').iterdir())
        (build / 'prepared.json').unlink()
        # Keep a stale preflight marker to ensure it cannot bypass failed preparation.
        p = self.call('--phase', 'all', '--resume', '--model', 'contract-model', '--api-key', self.key)
        self.assertEqual(p.returncode, 2, p.stdout + p.stderr)
        self.assertIn('prepare phase incomplete', p.stderr)
        self.assertIn(build.name, p.stderr)
        self.assertNotIn('Preflight:', p.stdout)
        self.assertTrue((build / 'prepare.log').is_file())
        self.assertTrue((self.run / 'summary.md').is_file())
        self.assertFalse((self.run / 'canary').exists())
        self.assertFalse(self.jobs.exists())

    def test_all_blocks_models_after_partial_preflight_failure_and_resumes(self):
        build = next((self.run / 'build').iterdir())
        marker = build / 'preflight.ok.json'
        proof = marker.read_bytes()
        marker.unlink()
        args = ('--phase', 'all', '--resume', '--model', 'contract-model', '--api-key', self.key)
        p = self.call(*args)
        self.assertEqual(p.returncode, 2, p.stdout + p.stderr)
        self.assertIn('preflight phase incomplete', p.stderr)
        self.assertIn(build.name, p.stderr)
        self.assertTrue((build / 'preflight.log').is_file())
        self.assertTrue((self.run / 'summary.md').is_file())
        self.assertFalse((self.run / 'canary').exists())
        self.assertFalse(self.jobs.exists())
        # Simulate the missing sample passing a subsequent check, preserving prior evidence.
        marker.write_bytes(proof)
        previous_smoke = next(build.glob('smoke.previous.*'))
        shutil.copytree(previous_smoke, build / 'smoke')
        p = self.call(*args)
        self.assertEqual(p.returncode, 0, p.stdout + p.stderr)
        self.assertEqual(len(list(self.jobs.glob('*/launch-proof.json'))), 7)  # canary + six trials
        self.assertTrue(previous_smoke.is_dir())

    def test_direct_run_cannot_bypass_incomplete_preparation_or_preflight(self):
        build = next((self.run / 'build').iterdir())
        for phase, filename in (('prepare', 'prepared.json'), ('preflight', 'preflight.ok.json')):
            with self.subTest(phase=phase):
                marker = build / filename
                proof = marker.read_bytes()
                marker.unlink()
                try:
                    p = self.call('--phase', 'run', '--resume', '--model', 'contract-model', '--api-key', self.key)
                    self.assertEqual(p.returncode, 2, p.stdout + p.stderr)
                    self.assertIn(phase + ' phase incomplete', p.stderr)
                    self.assertFalse((self.run / 'canary').exists())
                    self.assertFalse(self.jobs.exists())
                finally:
                    marker.write_bytes(proof)

    def test_api_key_precedence_resume_and_no_secret_output(self):
        env=dict(self.env,OPENAI_API_KEY='inherited-unused-key',CODEX_FORCE_AUTH_JSON='1',CODEX_AUTH_JSON_PATH='/invalid/host/auth.json')
        dotenv=self.root/'input.env'; dotenv.write_text('OPENAI_API_KEY=file-unused-key\n')
        args=('--phase','run','--resume','--model','contract-model','--api-key',self.key,'--env-file',str(dotenv))
        p=self.call(*args,env=env); self.assertEqual(p.returncode,0,p.stdout+p.stderr)
        trials=[json.loads(line) for line in (self.run/'trials.jsonl').read_text().splitlines()]
        self.assertEqual(len(trials),6); self.assertTrue(all(r['status']=='unsolved' for r in trials))
        for proof in self.jobs.glob('*/launch-proof.json'):
            d=json.loads(proof.read_text()); self.assertEqual(d['key_hash'],hashlib.sha256(self.key.encode()).hexdigest())
            self.assertIsNone(d['force_auth']); self.assertIsNone(d['auth_path'])
            self.assertIn('config={"forced_login_method":"api"}',d['agent_args'])
        for root in (self.run,self.jobs):
            for p in root.rglob('*'):
                if p.is_file(): self.assertNotIn(self.key.encode(),p.read_bytes(),str(p))
        before=sorted(str(p) for p in self.jobs.glob('*/launch-proof.json'))
        p=self.call(*args,env=env); self.assertEqual(p.returncode,0,p.stdout+p.stderr)
        self.assertEqual(before,sorted(str(p) for p in self.jobs.glob('*/launch-proof.json')))
        p=self.call('--phase','plan','--resume','--samples-per-difficulty','3')
        self.assertNotEqual(p.returncode,0); self.assertIn('immutable',p.stderr)

    def test_subscription_isolation_and_conflicts(self):
        auth=self.root/'subscription.json'; auth.write_text(json.dumps({'tokens':{'access_token':'test-subscription-token-not-real-123456789'}}))
        env=dict(self.env,OPENAI_API_KEY='unused-api-test-key')
        p=self.call('--phase','run','--resume','--auth','subscription','--auth-json',str(auth),'--model','openai/contract-model',env=env)
        self.assertEqual(p.returncode,0,p.stdout+p.stderr)
        for proof in self.jobs.glob('*/launch-proof.json'):
            d=json.loads(proof.read_text()); self.assertEqual(d['force_auth'],'1'); self.assertEqual(d['auth_path'],str(auth))
            self.assertEqual(d['key_hash'],hashlib.sha256(b'').hexdigest())
        p=self.call('--phase','run','--resume','--auth','subscription','--api-key','anything','--model','contract-model')
        self.assertNotEqual(p.returncode,0); self.assertIn('conflicts',p.stderr)
        p=self.call('--phase','run','--resume','--api-key','--model','contract-model')
        self.assertNotEqual(p.returncode,0); self.assertIn('TTY',p.stderr)

    def test_signal_keeps_attempt_and_explicit_retry_creates_new_one(self):
        env=dict(self.env,FAKE_HARBOR_MODE='interrupt')
        args=['bash',str(self.script),'--run-id','check','--phase','run','--resume','--model','contract-model','--api-key',self.key]
        proc=subprocess.Popen(args,env=env,stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True,start_new_session=True)
        try:
            deadline=time.monotonic()+30
            while not list(self.jobs.glob('*/started.marker')):
                if proc.poll() is not None or time.monotonic()>deadline: self.fail('stub trial did not start: '+repr(proc.communicate(timeout=1)))
                time.sleep(.1)
            proc.send_signal(signal.SIGTERM); out,err=proc.communicate(timeout=25)
            self.assertEqual(proc.returncode,130,out+err)
            first=next(self.jobs.glob('*/started.marker')).parent
            self.assertTrue(first.exists())
            p=self.call('--phase','run','--resume','--model','contract-model','--api-key',self.key)
            self.assertEqual(p.returncode,2,p.stdout+p.stderr)  # unfinished old attempt remains visible
            self.assertFalse((self.jobs/(first.name[:-3]+'002')).exists())
            p=self.call('--phase','run','--resume','--rerun-incomplete','--model','contract-model','--api-key',self.key)
            self.assertEqual(p.returncode,0,p.stdout+p.stderr)  # latest attempts complete; interrupted history retained
            self.assertTrue((self.jobs/(first.name[:-3]+'002')).exists())
            self.assertTrue(first.exists())
        finally:
            if proc.poll() is None:
                os.killpg(proc.pid,signal.SIGTERM); proc.wait(timeout=20)


if __name__ == '__main__':
    unittest.main(verbosity=2)
