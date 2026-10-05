#!/usr/bin/env python3
"""One helper configuration: prepare, native lanes, seal, standard tar, optional HF.

Website import belongs to the receiver. No automatic experiment reruns, task
publication, credential upload, or host-wide process/container cleanup.
"""
from contextlib import ExitStack
import argparse
import json
import os
from pathlib import Path
import shutil
import signal
import subprocess
import sys
import tarfile
import tempfile
import time
from types import SimpleNamespace

from agent_batch_contract import read, save, validate, digest, sha, locked, linked_rerun, package, outcome_counts, select_agent, match_assignment
from agent_batch_delivery import selected, verify_tree, unpack

ROOT=Path(__file__).resolve().parents[1]


def failure_details(cfg, plan):
    """Expose safe, specific account diagnostics instead of only ValueError."""
    from account_failure_check import ACCOUNT_MESSAGES
    path=Path(cfg['jobs_dir'])/(plan['batch']+'-stop.json')
    try:
        code=read(path).get('code')
    except (OSError,ValueError,AttributeError):
        code=None
    if code in ACCOUNT_MESSAGES:
        return dict(error_code=code,message=ACCOUNT_MESSAGES[code],budget_scope='account')
    return dict(error_code='workflow_failed',message='批次执行或交付未完成；请检查 workflow.log、lane 日志与 trial 结果。')


def location(value, base):
    if not isinstance(value,str) or not value or any(ord(c)<32 for c in value):
        raise ValueError('expected a nonempty file/directory path')
    p=Path(value).expanduser()
    return (p if p.is_absolute() else base/p).resolve()


def load_config(path):
    path=Path(path).resolve(); cfg=read(path)
    allowed={'schema_version','assignment','jobs_dir','auth','lanes','images','hf_token_file',
             'upload','allow_partial','background','notes_file','rerun_assignments','model_selection'}
    if not isinstance(cfg,dict) or set(cfg)-allowed or cfg.get('schema_version')!=1:
        raise ValueError('invalid helper config; model/tasks/budgets belong in the maintainer assignment')
    cfg=dict(cfg)
    choice=cfg.get('model_selection')
    if choice is not None and (not isinstance(choice,dict) or set(choice)!={'model','effort'}
                              or any(not isinstance(v,str) or not v for v in choice.values())):
        raise ValueError('model_selection needs model and effort')
    for key in ('assignment','jobs_dir'): cfg[key]=str(location(cfg[key],path.parent))
    jobs=Path(cfg['jobs_dir'])
    if jobs.name!='agents': raise ValueError('jobs_dir must end in /agents')
    for key,default in (('upload',True),('allow_partial',False),('background',True)):
        cfg.setdefault(key,default)
        if type(cfg[key]) is not bool: raise ValueError(key+' must be boolean')
    for key in ('hf_token_file','notes_file'):
        cfg[key]=str(location(cfg[key],path.parent)) if cfg.get(key) else None
    cfg['rerun_assignments']=[str(location(p,path.parent)) for p in cfg.get('rerun_assignments',[])]
    lanes=cfg.get('lanes',[{'gpu':'0'}])
    if not isinstance(lanes,list) or not 1<=len(lanes)<=128: raise ValueError('provide 1..128 GPU lanes')
    resolved=[]
    for lane in lanes:
        if not isinstance(lane,dict) or set(lane)-{'gpu','auth'}: raise ValueError('invalid lane')
        gpu=str(lane.get('gpu','0'))
        if not gpu or not all(c.isalnum() or c=='-' for c in gpu): raise ValueError('invalid GPU selection')
        auth=dict(lane.get('auth',cfg.get('auth',{})))
        key='auth_file' if auth.get('method')=='subscription' else 'env_file'
        if auth.get('method') not in ('subscription','api-key') or set(auth)!={'method',key}:
            raise ValueError('auth needs subscription/auth_file or api-key/env_file')
        auth[key]=str(location(auth[key],path.parent))
        if key=='auth_file' and Path(auth[key]).name!='auth.json': raise ValueError('subscription file must be named auth.json')
        resolved.append(dict(gpu=gpu,auth=auth))
    cfg['lanes']=resolved; cfg.pop('auth',None)
    images=cfg.get('images',{})
    if not isinstance(images,dict) or set(images)-{'archives','pull_missing'}: raise ValueError('invalid images config')
    cfg['images']={'archives':[str(location(p,path.parent)) for p in images.get('archives',[])],
                   'pull_missing':images.get('pull_missing',False)}
    if type(cfg['images']['pull_missing']) is not bool: raise ValueError('pull_missing must be boolean')
    private=[path,Path(cfg['assignment']),*[Path(l['auth'].get('auth_file',l['auth'].get('env_file'))) for l in resolved]]
    if cfg['hf_token_file']: private.append(Path(cfg['hf_token_file']))
    if any(p.is_relative_to(jobs) or p.is_relative_to(jobs.with_name('agents_mirror')) for p in private):
        raise ValueError('configuration and credentials must stay outside evidence directories')
    return cfg


def lane_environment(cfg,lane):
    env=dict(os.environ)
    for key in ('ENV_FILE','OPENAI_API_KEY','OPENAI_BASE_URL','OPENROUTER_API_KEY','ANTHROPIC_API_KEY',
                'ANTHROPIC_BASE_URL','CLAUDE_FORCE_OAUTH','CLAUDE_CODE_OAUTH_TOKEN','CODEX_FORCE_AUTH_JSON',
                'CODEX_AUTH_JSON_PATH','HF_TOKEN','HUGGING_FACE_HUB_TOKEN','HF_TOKEN_PATH','HF_HOME','HF_ENDPOINT',
                'TOPOGYM_BATCH_PYTHON','AGENT','MODEL','EFFORT','AK','K','MODES','AGENT_CONFIG','WAIT_FOR',
                'GATEWAY','GATEWAY_RAW','LOG_MIRROR','MEM_GUARD','SEQ'):
        env.pop(key,None)
    env.update(JOBS=cfg['jobs_dir'],BATCH_ASSIGNMENT=cfg['assignment'],GPU_DEVICE=lane['gpu'],
               PATH=str(ROOT/'.venv-agent-batch/bin')+os.pathsep+str(ROOT/'.tools/agent-batch/node_modules/.bin')+os.pathsep+env.get('PATH',''),
               PYTHONDONTWRITEBYTECODE='1',HF_HUB_DISABLE_IMPLICIT_TOKEN='1')
    auth=lane['auth']
    if auth['method']=='subscription': env.update(CODEX_FORCE_AUTH_JSON='1',CODEX_AUTH_JSON_PATH=auth['auth_file'])
    else: env['ENV_FILE']=auth['env_file']
    if cfg.get('model_selection'):
        env.update(MODEL=cfg['model_selection']['model'],EFFORT=cfg['model_selection']['effort'])
    return env


def run_command(argv,*,env=None,output=None):
    result=subprocess.run(list(map(str,argv)),cwd=ROOT,env=env,stdout=output,stderr=subprocess.STDOUT if output else None)
    if result.returncode: raise ValueError('step failed: '+Path(str(argv[0])).name+'; see private workflow log')


def bootstrap():
    python=ROOT/'.venv-agent-batch/bin/python'
    if not (ROOT/'.venv-agent-batch').exists(): run_command(['bash',ROOT/'scripts/setup_agent_batch.sh'])
    if not python.is_file(): raise ValueError('incomplete runner installation; preserve it and repair setup before retrying')
    # Re-exec after first install; HF subprocesses need the pinned interpreter too.
    if Path(sys.prefix).resolve()!=(ROOT/'.venv-agent-batch').resolve():
        os.execv(str(python),[str(python),str(Path(__file__).resolve()),*sys.argv[1:]])
    from agent_batch_runtime import tooling
    tooling()


def prepare(cfg,plan,state):
    from agent_batch_runtime import image_records, credentials, command
    from check_agent_batch_auth import canary
    if (ROOT/'helper-release.json').is_file():
        from export_native_helper_release import verify_release
        verify_release(ROOT,plan)
    for task in plan['tasks']: package(ROOT,task)
    for rel,value in plan.get('runner_files',{}).items():
        if sha(ROOT/rel)!=value: raise ValueError('published runner differs from checkout: '+rel)
    command(['docker','info']); command(['docker','compose','version'])
    for archive in cfg['images']['archives']: run_command(['docker','image','load','--input',archive])
    if cfg['images']['pull_missing']:
        refs={v['image'] for v in plan.get('images',{}).values()}
        for task in plan['tasks']:
            refs.update(task['runtime_binding'][k]['reference'] for k in ('image','agent_image') if k in task['runtime_binding'])
        for ref in sorted(refs):
            if 'build' in plan.get('image_sources',{}).get(ref,{}): continue
            if subprocess.run(['docker','image','inspect',ref],stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL).returncode:
                run_command(['docker','pull',ref])
    from agent_batch_images import ensure_images
    ensure_images(plan,ROOT)
    image_records(plan)
    if cfg['upload'] and plan['upload']['type']=='hf': hf_access(cfg,plan,state)
    seen=set()
    for lane in cfg['lanes']:
        command(['nvidia-smi','-i',lane['gpu'],'--query-gpu=uuid','--format=csv,noheader'])
        auth=lane['auth']; identity=digest(auth)
        if identity in seen:
            if auth['method']=='subscription': print('Shared subscription cache: these lanes execute serially.',flush=True)
            continue
        env=lane_environment(cfg,lane)
        if auth['method']=='subscription' and not Path(auth['auth_file']).exists():
            if not sys.stdin.isatty(): raise ValueError('first subscription login needs a terminal; rerun without nohup')
            profile=Path(auth['auth_file']).parent; profile.mkdir(parents=True,exist_ok=True,mode=0o700)
            run_command(['codex','-c','cli_auth_credentials_store="file"','login','--device-auth'],env=dict(env,CODEX_HOME=str(profile)))
        credentials(env)
        save(state/('auth-canary-'+identity+'.json'),canary(plan,env)); seen.add(identity)


def hf_access(cfg,plan,state):
    from difficulty_hf_auth import read_token
    from difficulty_results_hf import Hub
    from helper_bundle import guard
    if not cfg['hf_token_file']: raise ValueError('HF upload requires hf_token_file; target comes from the assignment')
    hub=Hub(read_token(cfg['hf_token_file']),plan['upload']['repo_id'],state,guard)
    hub.call('auth')
    if not hub.call('private'): raise ValueError('maintainer must provide an existing private HF dataset')
    return hub


def run_lanes(cfg,plan,state):
    from helper_bundle import guard
    children=[]
    with ExitStack() as stack:
        try:
            for i,lane in enumerate(cfg['lanes']):
                log=stack.enter_context((state/f'lane-{i}.log').open('ab'))
                children.append(subprocess.Popen(['bash',str(ROOT/'scripts/run_agent_batch.sh'),plan['batch'],*plan['task_bases']],
                    cwd=ROOT,env=lane_environment(cfg,lane),stdin=subprocess.DEVNULL,stdout=log,stderr=subprocess.STDOUT))
            while any(p.poll() is None for p in children): guard(); time.sleep(.5)
            return [p.returncode for p in children]
        finally:
            # Signal only our lane processes; native runner owns its Harbor/Docker cleanup.
            for p in children:
                if p.poll() is None: p.terminate()
            for p in children:
                try: p.wait(timeout=60)
                except subprocess.TimeoutExpired:
                    raise ValueError('lane cleanup still running; use explicit recovery after it exits') from None


def bundle(jobs,plan,folder,*,reruns=(),allow_partial=False):
    from helper_bundle import guard
    plans=[plan,*reruns]
    for p in plans: verify_tree(jobs.parent,p)
    name=plan['batch']+'__'+plan['helper']+'.tar.gz'
    if folder.exists():
        if {p.name for p in folder.iterdir()}!={name,name+'.sha256','MANIFEST.md'}:
            raise ValueError('preserve unexpected files in upload folder; choose a separate jobs directory')
        archive=folder/name
    else:
        with tempfile.TemporaryDirectory(prefix='.helper-pack-',dir=folder.parent) as temp:
            stage=Path(temp)/'upload'; stage.mkdir()
            archive=stage/name; payload={}
            for p in plans:
                for path in selected(jobs,p): payload[path.relative_to(jobs.parent).as_posix()]=path
                inv=jobs/(p['batch']+'-inventory.json'); payload[inv.relative_to(jobs.parent).as_posix()]=inv
            directories=set()
            for rel in payload:
                directories.update(str(p) for p in Path(rel).parents if str(p)!='.')
            for p in plans:
                for spec in p['jobs']:
                    for root in (jobs,jobs.with_name('agents_mirror')):
                        path=root/spec['job']
                        if path.is_dir(): directories.add(path.relative_to(jobs.parent).as_posix())
            with tarfile.open(archive,'w:gz') as out:
                for rel in sorted(directories): guard(); out.add(jobs.parent/rel,arcname=rel,recursive=False)
                for rel,path in sorted(payload.items()): guard(); out.add(path,arcname=rel,recursive=False)
            (stage/(name+'.sha256')).write_text(sha(archive)+'  '+name+'\n')
            shutil.copyfile(jobs/(plan['batch']+'-MANIFEST.md'),stage/'MANIFEST.md')
            # Seal the local upload folder only after a complete round-trip verification.
            with tempfile.TemporaryDirectory(prefix='.helper-verify-',dir=folder.parent) as td:
                report=unpack(archive,Path(td),plan,reruns=reruns)
            if not allow_partial and not report['delivery_complete']: raise ValueError('batch incomplete; preserved jobs, no complete delivery claimed')
            stage.rename(folder); archive=folder/name
    with tempfile.TemporaryDirectory(prefix='.helper-verify-',dir=folder.parent) as td:
        report=unpack(archive,Path(td),plan,reruns=reruns)
        if (folder/'MANIFEST.md').read_bytes()!=(Path(td)/'agents'/(plan['batch']+'-MANIFEST.md')).read_bytes():
            raise ValueError('external MANIFEST differs from archive')
    if not allow_partial and not report['delivery_complete']: raise ValueError('batch incomplete')
    return archive,report


def deliver(cfg,plan,state,*,recover=False):
    jobs=Path(cfg['jobs_dir']); folder=jobs.parent/('upload_'+plan['batch'])
    retries=[linked_rerun(plan,read(p)) for p in cfg['rerun_assignments']]
    if not folder.exists():
        for assignment in [cfg['assignment'],*cfg['rerun_assignments']]:
            for lane in {digest(l['auth']):l for l in cfg['lanes']}.values():
                argv=[sys.executable,ROOT/'scripts/finish_agent_batch.py','--jobs',jobs,'--assignment',assignment]
                if recover: argv+=['--recover']
                if cfg['notes_file']: argv+=['--notes-file',cfg['notes_file']]
                run_command(argv,env=lane_environment(cfg,lane))
    archive,report=bundle(jobs,plan,folder,reruns=retries,allow_partial=cfg['allow_partial'])
    receipt=dict(batch=plan['batch'],plan_sha256=plan['plan_sha256'],archive=str(archive),sha256=sha(archive),
                 delivery_complete=report['delivery_complete'],upload='pending' if plan['upload']['type']=='hf' else 'shared-folder',
                 **outcome_counts(report))
    save(state/'delivery.json',receipt)
    return receipt


def upload_once(cfg,plan,state):
    from check_agent_batch_hf import check
    folder=Path(cfg['jobs_dir']).parent/('upload_'+plan['batch'])
    hub=hf_access(cfg,plan,state)
    args=SimpleNamespace(verify_uploaded=False,rerun_assignment=cfg['rerun_assignments'])
    before=check(folder,plan,args,hub)
    if not cfg['allow_partial'] and not before['delivery_complete']: raise ValueError('incomplete upload blocked')
    paths=[plan['upload']['prefix']+'/'+name for name in before['files']]
    remote=hub.call('info',paths=paths,revision=before['revision'])
    if len(remote)!=len(paths):
        hub.call('commit',parent=before['revision'],files=[(plan['upload']['prefix']+'/'+name,str(folder/name)) for name in before['files']],
                 message='Helper batch '+plan['batch'])
    args.verify_uploaded=True
    receipt=check(folder,plan,args,hub); save(state/'hf-receipt.json',receipt)
    return receipt


def upload(cfg,plan,state):
    from difficulty_hf_auth import HFError
    for attempt in range(4):
        try: return upload_once(cfg,plan,state)
        except HFError as error:
            if not error.retryable or attempt==3: raise
            # Re-query the remote hashes after a lost commit response, never blindly overwrite.
            print('HF temporary failure; rechecking remote files before retry.',flush=True)
            time.sleep(min(5*2**attempt,20))


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--config',type=Path,required=True)
    p.add_argument('--init-config',action='store_true',help='create a private config, without running/installing anything')
    p.add_argument('--assignment',type=Path); p.add_argument('--jobs-dir',type=Path)
    auth=p.add_mutually_exclusive_group(); auth.add_argument('--auth-file',type=Path); auth.add_argument('--env-file',type=Path)
    p.add_argument('--hf-token-file',type=Path); p.add_argument('--gpu',default='0')
    p.add_argument('--phase',choices=('all','prepare','deliver','upload','status'),default='all')
    p.add_argument('--foreground',action='store_true',help='keep the workflow attached after authentication')
    p.add_argument('--recover',action='store_true',help='explicitly finalize dead lanes; only with --phase deliver')
    p.add_argument('--worker',action='store_true',help=argparse.SUPPRESS)
    a=p.parse_args(); os.umask(0o077)
    try:
        if a.init_config:
            if not a.assignment or not a.jobs_dir: raise ValueError('config creation needs --assignment and --jobs-dir')
            plan=select_agent(read(a.assignment),model=os.environ.get('MODEL'),effort=os.environ.get('EFFORT'),agent=os.environ.get('AGENT'))
            cfg=dict(schema_version=1,assignment=str(a.assignment.resolve()),
                jobs_dir=str(a.jobs_dir.expanduser().resolve()),lanes=[dict(gpu=a.gpu)],
                auth=dict(method='api-key',env_file=str(a.env_file.expanduser().resolve())) if a.env_file else
                     dict(method='subscription',auth_file=str((a.auth_file or Path('~/.codex/auth.json')).expanduser().resolve())),
                images=dict(archives=[],pull_missing=False),upload=plan['upload']['type']=='hf',
                hf_token_file=str(a.hf_token_file.expanduser().resolve()) if a.hf_token_file else None,
                allow_partial=False,background=True,notes_file=None,rerun_assignments=[])
            cfg['model_selection']=dict(model=plan['agent']['model'],effort=plan['agent']['kwargs'].get('reasoning_effort','default'))
            if cfg['upload'] and not cfg['hf_token_file']: raise ValueError('HF assignment requires --hf-token-file path')
            a.config.parent.mkdir(parents=True,exist_ok=True,mode=0o700)
            with a.config.open('x') as stream: json.dump(cfg,stream,indent=2); stream.write('\n')
            load_config(a.config)
            print('Created '+str(a.config.resolve()))
            print('Model selection: '+json.dumps(cfg['model_selection'])+'; saved for every trial in this batch')
            return 0
        if any((a.assignment,a.jobs_dir,a.auth_file,a.env_file,a.hf_token_file)) or a.gpu!='0':
            raise ValueError('local settings are provided during --init-config, then read from --config')
        if a.recover and a.phase!='deliver': raise ValueError('--recover requires --phase deliver')
        cfg=load_config(a.config); plan=select_agent(read(cfg['assignment']),**cfg.get('model_selection',{}))
        recorded=Path(cfg['jobs_dir'])/(plan['batch']+'-plan.json')
        if recorded.exists() and read(recorded)!=plan:
            raise ValueError('model or assignment differs from existing batch; preserve records and use a new batch')
        state=Path(cfg['jobs_dir']).parent/'.helper-pipeline'/plan['batch']
        if a.phase=='status':
            print(json.dumps(read(state/'status.json') if (state/'status.json').exists() else {'stage':'not_started'},indent=2)); return 0
        bootstrap(); state.mkdir(parents=True,exist_ok=True,mode=0o700)
        from agent_batch_runtime import utc,live
        identity=dict(plan_sha256=plan['plan_sha256'],config_sha256=digest(cfg))
        with locked(state/'workflow.lock',blocking=a.worker):
            old=read(state/'status.json') if (state/'status.json').exists() else {}
            if old and old.get('plan_sha256')!=plan['plan_sha256']: raise ValueError('workflow assignment changed')
            if (old.get('stage') not in ('complete','failed','prepared','already_sealed')
                    and old.get('worker') and old['worker']['pid']!=os.getpid() and live(old['worker'])):
                raise ValueError('helper workflow is already running')
            if a.worker and old.get('config_sha256')!=identity['config_sha256']: raise ValueError('config changed between prepare and worker')
            import psutil
            status=dict(identity,worker=dict(pid=os.getpid(),process_start=psutil.Process().create_time()),phase=a.phase,stage='starting',updated_at=utc())
            def mark(stage,**extra):
                status.update(stage=stage,updated_at=utc(),**extra); save(state/'status.json',status); print(stage,flush=True)
            try:
                if a.phase in ('all','prepare'):
                    sealed=(Path(cfg['jobs_dir'])/(plan['batch']+'-inventory.json')).exists()
                    if not sealed:
                        if not a.worker:
                            mark('preparing'); prepare(cfg,plan,state)
                        if a.phase=='prepare': mark('prepared'); return 0
                        if cfg['background'] and not a.foreground and not a.worker:
                            with (state/'workflow.log').open('ab') as log:
                                child=subprocess.Popen([sys.executable,str(Path(__file__).resolve()),'--config',str(a.config.resolve()),'--worker'],
                                    cwd=ROOT,stdin=subprocess.DEVNULL,stdout=log,stderr=subprocess.STDOUT,start_new_session=True)
                            mark('background',worker=dict(pid=child.pid,process_start=psutil.Process(child.pid).create_time()))
                            print('Status/log: '+str(state)); return 0
                        mark('running'); codes=run_lanes(cfg,plan,state); status['lane_exit_codes']=codes
                    elif a.phase=='prepare': mark('already_sealed'); return 0
                if a.phase in ('all','deliver'):
                    mark('delivering'); status['delivery']=deliver(cfg,plan,state,recover=a.recover)
                if a.phase=='upload' or (a.phase=='all' and cfg['upload'] and plan['upload']['type']=='hf'):
                    if plan['upload']['type']!='hf': raise ValueError('assignment uses shared-folder; no HF destination')
                    mark('uploading'); status['hf']=upload(cfg,plan,state)
                    print('HF results: '+status['hf']['url'],flush=True)
                    if (state/'delivery.json').exists():
                        receipt=read(state/'delivery.json')
                        receipt.update(upload='verified',hf_revision=status['hf']['revision'],hf_repo_id=status['hf']['repo_id'])
                        save(state/'delivery.json',receipt); status['delivery']=receipt
                mark('complete'); print(json.dumps(status,indent=2)); return 0
            except BaseException as error:
                details=failure_details(cfg,plan)
                mark('failed',error=type(error).__name__,**details)
                print(details['message'],file=sys.stderr)
                raise
    except (OSError,ValueError,KeyError,TypeError,subprocess.TimeoutExpired,tarfile.TarError) as error:
        print('Helper workflow stopped: '+str(error),file=sys.stderr); return 2
    except KeyboardInterrupt:
        print('Helper workflow interrupted; preserve records and inspect status before recovery.',file=sys.stderr); return 130


if __name__=='__main__':
    def interrupted(signum,frame): raise KeyboardInterrupt()
    signal.signal(signal.SIGTERM,interrupted)
    raise SystemExit(main())
