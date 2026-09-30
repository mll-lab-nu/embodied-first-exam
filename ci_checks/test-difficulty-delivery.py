#!/usr/bin/env python3
"""Delivery contracts: no model calls; fake daemon tests are not GPU evidence."""
import asyncio
from contextlib import contextmanager
import importlib.util
import json
import os
from pathlib import Path
import socket
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT/'scripts'), str(ROOT)]
import difficulty_delivery as delivery
import difficulty_release as release
import difficulty_eval as evaluation
import sample_difficulty_instances as sampling
from harbor_agents.persistent_auth import persist_auth


class DeliveryContracts(unittest.TestCase):
    def test_default_and_explicit_relative_work_directory(self):
        with tempfile.TemporaryDirectory() as tmp:
            self.assertEqual(delivery.safe_work_dir(None, tmp), Path(tmp)/'topogym-work')
        for bad in ('/tmp/a:b', '/tmp/a,b', '/tmp/a\nb'):
            with self.assertRaises(ValueError): delivery.safe_work_dir(bad)

    def test_compose_preserves_isolation_and_fixes_gpu_and_identity(self):
        document = {'services': {'main': {}, 'sim': {'volumes': ['./sim:/srv:ro'], 'deploy': {
            'resources': {'reservations': {'devices': [{'driver':'nvidia','count':1,'capabilities':['gpu']}]}}}}}}
        labels = delivery.resource_labels('workspace-a','same-run','release-a',owner='controller-a')
        got = delivery.decorate_compose(document, labels, 'GPU-test', uid=123, gid=456)
        self.assertNotIn('deploy', got['services']['main'])
        sim = got['services']['sim']
        self.assertEqual(sim['user'], '123:456')
        self.assertEqual(sim['volumes'], ['./sim:/srv:ro'])
        self.assertEqual(sim['deploy']['resources']['reservations']['devices'][0],
                         {'driver':'nvidia','device_ids':['GPU-test'],'capabilities':['gpu']})
        self.assertEqual(sim['labels']['topogym.owner'], '${TOPOGYM_CONTROLLER}')
        self.assertEqual(got['networks']['default']['labels']['topogym.workspace'], 'workspace-a')

    def test_runtime_hash_ignores_sampling_and_controller_changes(self):
        files = {'topogym/tasks/base.py':'a','assets/robots/a.urdf':'b','scripts/difficulty_eval.py':'c',
                 'configs/sweeps/difficulty_eval.yaml':'d','requirements/difficulty-eval-runtime.lock':'e',
                 'topogym/planning/policy.py':'f','topogym/README.md':'g'}
        before = release.digest(release.runtime_files(files))
        files['scripts/difficulty_eval.py']='different'; files['configs/sweeps/difficulty_eval.yaml']='different'
        self.assertEqual(before,release.digest(release.runtime_files(files)))
        files['requirements/difficulty-eval-runtime.lock']='different'
        self.assertNotEqual(before,release.digest(release.runtime_files(files)))

    def test_source_archive_without_git_and_release_tampering(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp)/'src'; root.mkdir(); (root/'.dockerignore').write_text('**\n')
            (root/'topogym').mkdir(); (root/'topogym/code.py').write_text('value=1\n')
            info=release.build_info(root)
            out=Path(tmp)/'out'; out.mkdir()
            with patch.object(sampling.subprocess,'run',side_effect=AssertionError('Git must not run')):
                frozen=sampling.snapshot_source(out,root)
            self.assertEqual(frozen['release_id'],info['release_id'])
            self.assertIsNone(frozen['git_head'])
            (root/'topogym/code.py').write_text('changed')
            with self.assertRaisesRegex(ValueError,'differs'):
                sampling.snapshot_source(Path(tmp)/'out2',root)

    def test_resource_cleanup_only_matches_owned_work(self):
        class Commands:
            def __init__(self): self.calls=[]
            def run_command(self,args,**kwargs):
                self.calls.append(args)
                return 0, ('abc123\n' if args[:3]==['docker','ps','-aq'] else '')
        obj=object.__new__(delivery.Delivery); obj.commands=Commands(); obj.owner='mine'
        obj.cleanup()
        self.assertIn('label=topogym.role=work',obj.commands.calls[0])
        self.assertIn('label=topogym.owner=mine',obj.commands.calls[0])
        self.assertEqual(obj.commands.calls[1],['docker','rm','-f','abc123'])

    def test_active_gpu_owner_is_never_reaped(self):
        obj=object.__new__(delivery.Delivery)
        obj.gpu_uuid='GPU-one'; obj.owner='new'; obj.workspace='b'; obj.run_id='same'; obj.release_id='r'; obj.lock_id=None
        def inspect(name):
            if name=='new': return {'Image':'controller-image'}
            if name=='old': return {'State':{'Running':True}}
            return {'Id':'lock-id','Config':{'Labels':{'topogym.role':'gpu-lock','topogym.owner':'old'}}}
        obj.inspect=inspect
        calls=[]
        obj.command=lambda args,**kw: (calls.append(args) or (1,'conflict'))
        with self.assertRaisesRegex(ValueError,'active controller'):
            with obj.gpu_lock(): self.fail('must not acquire')
        self.assertEqual(len(calls),1)

    def test_host_gpu_index_is_not_reused_inside_controller(self):
        obj=object.__new__(delivery.Delivery)
        obj.gpu_device='2'; obj.gpu_uuid=None; obj.owner='mine'; obj.workspace='w'; obj.run_id='r'; obj.release_id='v'
        obj.commands=type('Commands',(),{'env':{}})()
        calls=[]
        obj.command=lambda args,**kw: (calls.append(args) or (0,'GPU-selected\n'))
        self.assertEqual(obj.resolve_gpu(),'GPU-selected')
        self.assertNotIn('-i',calls[0])
        self.assertEqual(obj.commands.env['TOPOGYM_GPU_UUID'],'GPU-selected')

    def test_stale_gpu_lock_cleanup_and_release_use_ids(self):
        obj=object.__new__(delivery.Delivery)
        obj.gpu_uuid='GPU-one'; obj.owner='new'; obj.workspace='b'; obj.run_id='same'; obj.release_id='r'; obj.lock_id=None
        obj.inspect=lambda name: ({'Image':'controller-image'} if name=='new' else None if name=='old' else
            {'Id':'old-lock-id','Config':{'Labels':{'topogym.role':'gpu-lock','topogym.owner':'old'}}})
        calls=[]; creates=0
        def command(args,**kw):
            nonlocal creates
            calls.append(args)
            if args[1]=='create':
                creates+=1; return (1,'conflict') if creates==1 else (0,'new-lock-id\n')
            return 0,''
        obj.command=command; cleaned=[]; obj.cleanup=lambda owner=None: cleaned.append(owner or 'new')
        with obj.gpu_lock(): self.assertEqual(obj.lock_id,'new-lock-id')
        self.assertEqual(cleaned,['old','new'])
        self.assertIn(['docker','rm','old-lock-id'],calls)
        self.assertIn(['docker','rm','-f','new-lock-id'],calls)

    def test_refresh_is_private_atomic_and_rejects_other_accounts(self):
        with tempfile.TemporaryDirectory() as tmp:
            p=Path(tmp)/'auth.json'; p.write_text(json.dumps({'tokens':{'account_id':'mine','access_token':'old'}}))
            class Environment:
                account='mine'
                async def download_file(self,remote,local):
                    Path(local).write_text(json.dumps({'tokens':{'account_id':self.account,'access_token':'new'}}))
            env=Environment()
            asyncio.run(persist_auth(env,'/private/auth.json',p))
            self.assertEqual(json.loads(p.read_text())['tokens']['access_token'],'new')
            self.assertEqual(p.stat().st_mode & 0o777,0o600)
            before=p.read_bytes(); env.account='someone-else'
            with self.assertRaises(ValueError): asyncio.run(persist_auth(env,'/private/auth.json',p))
            self.assertEqual(before,p.read_bytes())
            self.assertEqual([x.name for x in p.parent.iterdir()],['auth.json'])


class LauncherBoundary(unittest.TestCase):
    def test_default_mounts_explicit_override_credentials_and_exit_code(self):
        with tempfile.TemporaryDirectory(prefix='delivery launch ') as tmp:
            root=Path(tmp); bind=root/'docker.sock'; sock=socket.socket(socket.AF_UNIX)
            self.addCleanup(sock.close)
            try:
                sock.bind(str(bind))
            except PermissionError:
                # Restricted CI may forbid bind; this test only stats the socket.
                bind=Path('/var/run/docker.sock')
                if not bind.is_socket(): self.skipTest('no Unix socket available for launcher metadata probe')
            binary=root/'bin'; binary.mkdir(); record=root/'record.jsonl'
            executable=binary/'docker'
            executable.write_text('#!'+sys.executable+'\n'+r'''
import hashlib,json,os,sys
from pathlib import Path
a=sys.argv[1:]; r=Path(os.environ['RECORD'])
with r.open('a') as f: f.write(json.dumps(a)+'\n')
if a[:2]==['context','inspect']: print('unix://'+os.environ['SOCKET'])
elif a[:1]==['info']: print('[]')
elif a[:2]==['image','inspect']: print('cached')
elif a[:1]==['create']:
 mounts=[a[i+1] for i,x in enumerate(a) if x=='--mount']
 private=next(x for x in mounts if 'dst=/run/topogym-launch' in x).split('src=',1)[1].split(',dst=')[0]
 p=Path(private)
 args=p.joinpath('args').read_bytes().decode().split('\0')[:-1]
 proof={'args_hash':hashlib.sha256(p.joinpath('args').read_bytes()).hexdigest(),
        'work':p.joinpath('work-dir').read_text(), 'private_mode':p.stat().st_mode & 0o777,
        'key_hash':hashlib.sha256(p.joinpath('api-key').read_bytes()).hexdigest()}
 Path(os.environ['PROOF']).write_text(json.dumps(proof))
 print('created')
elif a[:1]==['start']: sys.exit(int(os.environ.get('EXIT_CODE','0')))
''')
            executable.chmod(0o755)
            key='delivery-private-test-key'
            env=dict(os.environ,PATH=str(binary)+os.pathsep+os.environ['PATH'],RECORD=str(record),SOCKET=str(bind),
                     PROOF=str(root/'proof.json'),OPENAI_API_KEY=key,TOPOGYM_AUTH_DIR=str(root/'auth'),EXIT_CODE='7')
            common=['bash',str(ROOT/'bash_scripts/run_difficulty_trials.sh'),'--controller-image','registry/example@sha256:'+'a'*64,
                    '--phase','plan','--run-id','test','--api-key',key]
            for extra,expected in (([],root/'topogym-work'),(['--work-dir','other dir'],root/'other dir')):
                result=subprocess.run(common+extra,cwd=root,env=env,text=True,capture_output=True)
                self.assertEqual(result.returncode,7,result.stdout+result.stderr)
                proof=json.loads((root/'proof.json').read_text())
                self.assertEqual(proof['work'],str(expected)); self.assertEqual(proof['private_mode'],0o700)
                self.assertEqual(proof['key_hash'],__import__('hashlib').sha256(key.encode()).hexdigest())
                self.assertNotIn(key,record.read_text()+result.stdout+result.stderr)
                creates=[json.loads(x) for x in record.read_text().splitlines() if json.loads(x)[:1]==['create']]
                self.assertNotIn('--gpus',creates[-1])
                self.assertIn('HOME=/tmp/topogym-home',creates[-1])
            # A prebuilt-image startup bundle has no scripts/ or source checkout.
            bundle=root/'startup'; bundle.mkdir()
            (bundle/'run_difficulty_trials.sh').write_bytes((ROOT/'bash_scripts/run_difficulty_trials.sh').read_bytes())
            (bundle/'controller-image.txt').write_text('registry/example@sha256:'+'a'*64+'\n')
            result=subprocess.run(['bash',str(bundle/'run_difficulty_trials.sh'),'check','--help'],
                                  cwd=root,env=env,text=True,capture_output=True)
            self.assertEqual(result.returncode,7,result.stdout+result.stderr)
            creates=[json.loads(x) for x in record.read_text().splitlines() if json.loads(x)[:1]==['create']]
            self.assertNotIn('--gpus',creates[-1])


if __name__=='__main__': unittest.main(verbosity=2)
