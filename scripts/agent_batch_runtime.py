#!/usr/bin/env python3
"""Published native batches: immutable dispatch, claims, owned mirror and sealing.

The public entrypoint stays run_agent_batch.sh. Adapted Muse runs have an explicit,
separately recorded harness identity; native-agent assignments are unchanged.
"""
from contextlib import nullcontext
import argparse
import importlib.metadata
import importlib.util
import json
import os
from pathlib import Path
import platform
import signal
import subprocess
import sys
import tempfile
import time
import uuid

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from agent_batch_contract import component, digest, files, locked, package, read, save, sha, validate, write_summary, select_agent
from secret_scan import load_env, load_secrets, scan_tree
from agent_batch_provider import OPENROUTER_KEYS, canonical_model, codex_config, openrouter_credentials

def utc():
    import datetime
    return datetime.datetime.now(datetime.timezone.utc).isoformat(timespec='seconds')

def command(argv, *, env=None, timeout=30):
    result=subprocess.run(list(map(str,argv)),env=env,capture_output=True,text=True,timeout=timeout)
    if result.returncode: raise ValueError('command failed: '+str(argv[0])+' (output retained by the caller where applicable)')
    return result.stdout.strip()

def optional(argv):
    try: return command(argv)
    except (OSError,ValueError,subprocess.TimeoutExpired): return 'unknown (collection failed)'

def credentials(environment):
    env=dict(environment)
    if env.get('ENV_FILE'):
        # Match Harbor dotenv override semantics, before deciding auth/scan inputs.
        envfile=Path(env['ENV_FILE']).expanduser()
        # The unchanged manual names both auth alternatives. A subscription-only
        # helper need not create a dummy API-key file at the conventional path.
        absent_default=(envfile in (Path.home()/'rcb.env',Path.home()/'eai.env') and not envfile.exists()
                        and (Path.home()/'.codex/auth.json').is_file())
        values={} if absent_default else load_env(envfile)
        allowed={'OPENAI_API_KEY','OPENAI_BASE_URL','OPENROUTER_API_KEY','OPENROUTER_API_KEY_FOR_SMOKE','PROVIDER','ANTHROPIC_API_KEY','ANTHROPIC_BASE_URL',
                 'CLAUDE_FORCE_OAUTH','CLAUDE_CODE_OAUTH_TOKEN','CODEX_AUTH_JSON_PATH','CODEX_FORCE_AUTH_JSON'}
        if set(values)-allowed: raise ValueError('ENV_FILE must contain only model credentials/provider settings; keep HF_TOKEN separate')
        env.update(values)
    env.pop('HF_TOKEN',None); env.pop('HUGGING_FACE_HUB_TOKEN',None)
    env=openrouter_credentials(env)
    if (not any(env.get(k) for k in ('OPENAI_API_KEY','ANTHROPIC_API_KEY','CLAUDE_CODE_OAUTH_TOKEN'))
            and not env.get('CODEX_AUTH_JSON_PATH') and (Path.home()/'.codex/auth.json').is_file()):
        env.update(CODEX_AUTH_JSON_PATH=str(Path.home()/'.codex/auth.json'),CODEX_FORCE_AUTH_JSON='1')
    auth=None
    if env.get('CODEX_AUTH_JSON_PATH') or env.get('CODEX_FORCE_AUTH_JSON','').lower() in ('1','true','yes'):
        auth=Path(env.get('CODEX_AUTH_JSON_PATH',str(Path.home()/'.codex/auth.json'))).expanduser().resolve()
        data=read(auth)
        if not (data.get('tokens') or {}).get('access_token'): raise ValueError('subscription auth.json has no access token; run file-backed login')
        env.update(CODEX_AUTH_JSON_PATH=str(auth),CODEX_FORCE_AUTH_JSON='1',TOPOGYM_PERSIST_AUTH='1')
        env.pop('OPENAI_API_KEY',None)
    elif not any(env.get(k) for k in ('OPENAI_API_KEY','ANTHROPIC_API_KEY','CLAUDE_CODE_OAUTH_TOKEN')):
        raise ValueError('no model credentials: set ENV_FILE or explicit subscription auth path')
    return env,auth

def auth_secrets(env,auth,history=None):
    # Do not mutate os.environ or pass secrets through process arguments.
    secrets={k:env[k].encode() for k in ('OPENAI_API_KEY',*OPENROUTER_KEYS,'ANTHROPIC_API_KEY','CLAUDE_CODE_OAUTH_TOKEN') if env.get(k)}
    for i,path in enumerate([p for p in (auth,history) if p and p.exists()]):
        for k,v in load_secrets(auth_files=[path]).items(): secrets[f'{i}_{k}']=v
    if not secrets: raise ValueError('no scan credentials loaded')
    return secrets

def settings(plan,bases,env):
    validate(plan)
    if sorted(bases)!=sorted(plan['task_bases']) or len(bases)!=len(set(bases)): raise ValueError('CLI task bases differ from dispatch')
    wanted={'AGENT':plan['agent']['name'],'MODEL':plan['agent']['model'],
            'EFFORT':str(plan['agent']['kwargs'].get('reasoning_effort','default')),'K':str(plan['repetitions']),'SEQ':'1'}
    for k,v in wanted.items():
        if k in env and env[k]!=v: raise ValueError(k+' differs from dispatch')
    for k in ('AK','AGENT_CONFIG','WAIT_FOR','GATEWAY','GATEWAY_RAW'):
        if env.get(k) not in (None,'','0'): raise ValueError(k+' is not part of this published dispatch')
    for k in ('MEM_GUARD','LOG_MIRROR'):
        if env.get(k,'1')!='1': raise ValueError(k+' is required for published helper batches')
    modes=set(t['mode'] for t in plan['tasks'])
    supplied=env.get('MODES')
    if supplied and {dict(limited='standard',unlimited='privileged').get(m,m) for m in supplied.split()}!=modes:
        raise ValueError('MODES differs from dispatch')

def tooling():
    if importlib.metadata.version('harbor')!='0.23.0': raise ValueError('run setup_agent_batch.sh: Harbor 0.23.0 required')
    marker=Path(sys.prefix)/'topogym-runner.json'
    if not marker.exists(): raise ValueError('fixed bootstrap receipt missing; run setup_agent_batch.sh in this checkout')
    receipt=read(marker)
    if (set(receipt.get('files',{}))!={'images/difficulty-eval/patch_harbor.py','requirements/difficulty-eval-controller.lock','scripts/patch_agent_batch_providers.py'}
            or set(receipt.get('modules',{}))!={'harbor.agents.installed.codex','harbor.environments.docker.docker'}):
        raise ValueError('invalid fixed bootstrap receipt')
    for path,wanted in receipt['files'].items():
        if sha(ROOT/path)!=wanted: raise ValueError('installed runner dependencies/patch differ from checkout')
    for module,wanted in receipt['modules'].items():
        if sha(Path(importlib.util.find_spec(module).origin))!=wanted: raise ValueError('installed Harbor source changed')

def image_records(plan):
    from agent_batch_images import verified_records
    return verified_records(plan,ROOT)

def host_info():
    import psutil
    return dict(system=platform.platform(),cpu=platform.processor(),cpu_count=os.cpu_count(),memory_bytes=psutil.virtual_memory().total,
        gpu=optional(['nvidia-smi','--query-gpu=index,uuid,name,driver_version,memory.total','--format=csv']),
        cuda_driver_capability=optional(['nvidia-smi']),docker=optional(['docker','--version']),compose=optional(['docker','compose','version']),
        harbor=importlib.metadata.version('harbor'),python=sys.version.split()[0],codex=optional(['codex','--version']))

def live(lane):
    import psutil
    try:
        process=psutil.Process(lane['pid'])
        return process.create_time()==lane['process_start'] and process.status() not in (psutil.STATUS_ZOMBIE,psutil.STATUS_DEAD)
    except psutil.Error: return False

def batch_log(jobs,b,message):
    with (jobs/(b+'.log')).open('a') as stream: stream.write(f'[{utc()}] {message}\n')
    print(message,flush=True)

def stop(jobs,b,reason,*,code=None):
    save(jobs/(b+'-stop.json'),dict(reason=reason,at=utc(),**({'code':code} if code else {})))

class Mirror:
    def __init__(self,jobs,spec,plan,owner,private,env,*,resume=False):
        self.jobs=jobs; self.spec=spec; self.plan=plan; self.owner=owner; self.env=env
        self.raw=private/spec['job']; self.raw.mkdir(mode=0o700,exist_ok=resume)
        self.job=jobs/spec['job']; self.job.mkdir(exist_ok=resume)
        self.name='tg-batch-mirror-'+owner
        self.image=plan.get('images',{}).get('client',{}).get('image') or plan['tasks'][0]['runtime_binding']['image']['reference']
        self.args=['docker','run','--network','none','--read-only','--user','0:0','--tmpfs','/tmp',
            '--label','topogym.batch.owner='+owner,'--label','topogym.batch='+plan['batch'],'--label','topogym.role=mirror',
            '--mount',f'type=bind,src={self.job},dst=/src/{spec["job"]},readonly',
            '--mount',f'type=bind,src={self.raw},dst=/mirror',
            '--mount',f'type=bind,src={ROOT}/scripts,dst=/s,readonly']
        self.tool=['python3','/s/helper_log_mirror.py','--src','/src','--mirror','/mirror','--strict','--protect-root']
    def start(self):
        command([*self.args,'-d','--name',self.name,'--entrypoint','python3',self.image,*self.tool[1:],'--ready-file','/mirror/.ready'])
        try:
            deadline=time.monotonic()+30
            while True:
                if command(['docker','inspect','--format','{{.State.Running}}',self.name])!='true': raise ValueError('mirror failed before ready')
                probe=subprocess.run(['docker','exec',self.name,'test','-f','/mirror/.ready'],capture_output=True)
                if probe.returncode==0: break
                if time.monotonic()>deadline: raise ValueError('mirror readiness timed out')
                time.sleep(.2)
        except BaseException:
            command(['docker','rm','-f',self.name]); raise
    def finish(self,secrets,*,allow_interrupted=False):
        try: healthy=command(['docker','inspect','--format','{{.State.Running}}',self.name])=='true'
        except ValueError:
            if not allow_interrupted: raise
            healthy=False
        removed=subprocess.run(['docker','rm','-f',self.name],capture_output=True)
        if removed.returncode and not allow_interrupted: raise ValueError('mirror stop failed')
        command([*self.args,'--rm','--entrypoint','python3',self.image,*self.tool[1:],'--once'],timeout=60)
        dest=Path(str(self.jobs)+'_mirror')/self.spec['job']; dest.mkdir(parents=True,exist_ok=False)
        with tempfile.TemporaryDirectory(prefix='.batch-scan-',dir=self.raw.parent) as td:
            secret=Path(td)/'scan.json'; save(secret,{k:v.decode() for k,v in secrets.items()}); secret.chmod(0o600)
            command(['docker','run','--rm','--network','none','--read-only','--user','0:0','--tmpfs','/tmp',
                '--mount',f'type=bind,src={self.raw},dst=/raw,readonly', '--mount',f'type=bind,src={dest},dst=/out',
                '--mount',f'type=bind,src={self.job},dst=/job','--mount',f'type=bind,src={ROOT}/scripts,dst=/s,readonly',
                '--mount',f'type=bind,src={td},dst=/secrets,readonly','--entrypoint','python3',self.image,
                '/s/agent_batch_mirror_copy.py','--job',self.spec['job'],'--uid',str(os.getuid()),'--gid',str(os.getgid())],timeout=60)
        if not healthy and not allow_interrupted: raise ValueError('mirror stopped during execution; evidence retained but delivery incomplete')
        return healthy

def run_job(jobs,plan,spec,env,auth,private):
    from topogym.utils.process_limits import run_guarded
    from topogym_versions import require_task
    from account_failure_check import check
    task=next(t for t in plan['tasks'] if t['name']==spec['task'])
    task_dir=package(ROOT,task)
    # Keep every package/input/runtime hash check. The host image may be rebuilt
    # only when the assignment explicitly pins and verifies equivalent contents.
    require_task(task_dir,ROOT,inspect_docker=False)
    current_images=image_records(plan)
    if current_images!=read(jobs/(plan['batch']+'-metadata.json'))['images']:
        raise ValueError('batch images changed after lane registration')
    # Preserve the native runner's BuildKit cache workaround: same-size task
    # files copied with identical mtimes otherwise collide in shared contexts.
    stamp=time.time_ns()
    for i,path in enumerate(sorted(task_dir.rglob('*'))): os.utime(path,ns=(stamp+i,stamp+i),follow_symlinks=False)
    owner=uuid.uuid4().hex
    env=dict(env,TOPOGYM_BATCH_OWNER=owner,TOPOGYM_BATCH=plan['batch'],TOPOGYM_RUN_UID=str(os.getuid()),TOPOGYM_RUN_GID=str(os.getgid()),
             TOPOGYM_RESOURCE_LABELS=json.dumps({'topogym.batch.owner':owner,'topogym.batch':plan['batch']}))
    history=private/('auth-history-'+owner+'.json'); env['TOPOGYM_AUTH_HISTORY']=str(history)
    auth_status=private/('auth-status-'+owner+'.json'); env['TOPOGYM_AUTH_STATUS']=str(auth_status)
    secrets=auth_secrets(env,auth)
    save(jobs/(spec['job']+'-execution.json'),dict(owner=owner,status='starting',started_at=utc()))
    mirror=Mirror(jobs,spec,plan,owner,private,env); mirror.start()
    supervision=private/('supervision-'+owner); supervision.mkdir()
    agent_name=plan['agent']['name']
    if agent_name=='muse-openrouter':
        from harbor_agents.muse_transport.launch import IMPORT_PATH
        agent_name=IMPORT_PATH
    argv=['harbor','run','-p',str(ROOT/'tasks'),'-i',spec['task'],'-a',agent_name,'-m',plan['agent']['model'],
          '-n','1','-k',str(spec['repetitions']),'-y','-o',str(jobs),'--job-name',spec['job']]
    for k,v in plan['agent']['kwargs'].items(): argv+=['--ak',f'{k}={v}']
    if plan['agent']['name']=='codex' and plan['agent']['model'].startswith('openrouter/'):
        argv+=['--ak','config='+json.dumps(codex_config(plan['agent']['model']),separators=(',',':'))]
    # Dotenv has already been parsed as data. Do not let Harbor overwrite forced auth
    # with a second load, or save a credential-file path in trial configuration.
    rc=2
    try:
        rc=run_guarded(argv,supervision,cwd=ROOT,env=env)
        if auth_status.exists():
            save(jobs/(spec['job']+'-auth-status.json'),read(auth_status)); rc=2
    finally:
        # Docker children survive process group death. Only this job's labelled
        # resources may be stopped. A nonempty list also marks this job incomplete.
        remaining=command(['docker','ps','-q','--filter','label=topogym.batch.owner='+owner,'--filter','label=topogym.role!=mirror']).split()
        if remaining:
            command(['docker','stop','--time','10',*remaining],timeout=45); rc=2
        secrets.update(auth_secrets(env,auth,history))
        mirror.finish(secrets)
        for path in files(supervision):
            target=jobs/(spec['job']+'-'+path.name)
            target.write_bytes(path.read_bytes())
            scan_tree(target,secrets,redact=True)
        save(jobs/(spec['job']+'-mirror.json'),dict(complete=True,owner=owner,finished_at=utc(),returncode=rc))
        save(jobs/(spec['job']+'-execution.json'),dict(owner=owner,status='finished',finished_at=utc(),returncode=rc))
    trials=[p for p in mirror.job.iterdir() if p.is_dir()]
    accounts=[check(str(p)) for p in trials]
    save(jobs/(spec['job']+'-account-check.json'),dict(trials=accounts))
    failure=next((item for item in accounts if item['stop']),None)
    if failure:
        stop(jobs,plan['batch'],failure['message'],code=failure['code'])
        batch_log(jobs,plan['batch'],failure['message'])
    elif rc:
        stop(jobs,plan['batch'],'Harbor/resource failure; preserve all jobs and request a separate rerun assignment',
             code='harbor_or_resource_failure')
    else:
        for item in accounts:
            for warning in item['warnings']: batch_log(jobs,plan['batch'],warning)
    return rc

def finalize(jobs,plan,metadata,env,auth):
    from agent_batch_delivery import seal
    for lane in metadata['lanes']:
        if lane['status']=='running':
            if live(lane): return None
            raise ValueError('a lane died without cleanup; preserve records and inspect owned containers before sealing')
    # Process death does not imply Docker workloads stopped.
    for spec in plan['jobs']:
        execution=jobs/(spec['job']+'-execution.json')
        if execution.exists():
            owner=read(execution)['owner']
            if command(['docker','ps','-q','--filter','label=topogym.batch.owner='+owner]):
                raise ValueError('owned Docker workload still running; finalization blocked')
    metadata['finished_at']=utc(); metadata['status']='finished'
    save(jobs/(plan['batch']+'-metadata.json'),metadata)
    secrets=auth_secrets(env,auth)
    return seal(jobs,plan,secrets)

def run(batch,bases,assignment):
    import psutil
    os.umask(0o077)
    original=read(assignment)
    env,auth=credentials(dict(os.environ,MODEL=os.environ.get('MODEL',original['agent']['model'])))
    model=canonical_model(env['MODEL'],env.get('PROVIDER'))
    plan=select_agent(original,model=model,effort=env.get('EFFORT'),agent=env.get('AGENT'))
    if plan['batch']!=batch: raise ValueError('dispatch batch differs from command')
    env['MODEL']=model
    settings(plan,bases,env); tooling()
    jobs=Path(os.environ.get('JOBS',str(ROOT/'jobs/agents'))).resolve(); jobs.mkdir(parents=True,exist_ok=True)
    if jobs.name!='agents': raise ValueError('standard delivery requires JOBS ending in /agents')
    env.update(PYTHONPATH=str(ROOT),PYTHONDONTWRITEBYTECODE='1')
    gpu=env.get('GPU_DEVICE','0')
    env['TOPOGYM_GPU_UUID']=command(['nvidia-smi','-i',gpu,'--query-gpu=uuid','--format=csv,noheader'])
    if not env['TOPOGYM_GPU_UUID'].startswith('GPU-') or '\n' in env['TOPOGYM_GPU_UUID']: raise ValueError('select exactly one GPU per lane')
    for task in plan['tasks']: package(ROOT,task)
    for name,wanted in plan.get('runner_files',{}).items():
        from agent_batch_contract import relative
        if sha(ROOT/relative(name))!=wanted: raise ValueError('published runner changed: '+name)
    from agent_batch_images import ensure_images
    ensure_images(plan,ROOT)
    images=image_records(plan)
    private=jobs.parent/'.agent-batch-private'/batch; private.mkdir(parents=True,exist_ok=True,mode=0o700)
    lock=jobs/'.batch-locks'/batch
    with locked(lock):
        pp=jobs/(batch+'-plan.json')
        if pp.exists() and read(pp)!=plan: raise ValueError('batch plan differs; preserve existing records')
        if (jobs/(batch+'-inventory.json')).exists():
            from agent_batch_delivery import verify_tree
            report=verify_tree(jobs.parent,plan); print(json.dumps(report,indent=2)); return 0 if report['delivery_complete'] else 1
        if not pp.exists():
            if list(jobs.glob(batch+'-*')): raise ValueError('unregistered existing batch/prefix collision')
            save(pp,plan)
        mp=jobs/(batch+'-metadata.json')
        metadata=read(mp) if mp.exists() else dict(schema_version=1,batch=batch,started_at=utc(),status='running',plan_sha256=plan['plan_sha256'],
            repository=dict(commit=optional(['git','-C',ROOT,'rev-parse','HEAD']),dirty=bool(optional(['git','-C',ROOT,'status','--porcelain'])),root=str(ROOT)),
            host=host_info(),images=images,lanes=[],notes='Human incidents not supplied; unknown until helper adds them.')
        if metadata['images']!=images: raise ValueError('existing batch uses different local images; preserve it')
        if any(l['status']=='running' and not live(l) for l in metadata['lanes']): raise ValueError('stale lane; inspect before recovery')
        lane=dict(id=uuid.uuid4().hex,pid=os.getpid(),process_start=psutil.Process().create_time(),started_at=utc(),status='running',
                  gpu_uuid=env['TOPOGYM_GPU_UUID'],auth='subscription' if auth else 'api-key',jobs=[])
        metadata['lanes'].append(lane); save(mp,metadata)
    # A refresh token cannot safely rotate in concurrent trials. All lanes using
    # the same cache serialize BEFORE claiming a job; API or separate logins can run in parallel.
    auth_guard=locked(auth.with_name('.agent-batch-auth.lock')) if auth else nullcontext()
    rc=0
    try:
        # This is a short account/model check, not an experimental trial. It is
        # internal to the documented entrypoint and completes before any claim.
        from check_agent_batch_auth import canary
        save(private/('auth-canary-'+lane['id']+'.json'),canary(plan,env))
        with auth_guard:
            for spec in plan['jobs']:
                with locked(lock):
                    if (jobs/(batch+'-stop.json')).exists(): rc=1; break
                    claim=jobs/'.claims'/spec['job']; claim.parent.mkdir(exist_ok=True)
                    if (jobs/spec['job']).exists() or claim.exists(): continue
                    claim.mkdir(); save(claim/'owner.json',dict(lane=lane['id'],at=utc()))
                    metadata=read(mp); next(l for l in metadata['lanes'] if l['id']==lane['id'])['jobs'].append(spec['job']); save(mp,metadata)
                batch_log(jobs,batch,'start '+spec['job']+f" K={spec['repetitions']}")
                if run_job(jobs,plan,spec,env,auth,private): rc=1
                with locked(lock): write_summary(jobs,plan)
    except BaseException as exc:
        rc=2; stop(jobs,batch,'lane failed: '+type(exc).__name__)
        batch_log(jobs,batch,'lane failed; '+type(exc).__name__)
        raise
    finally:
        with locked(lock):
            metadata=read(mp); current=next(l for l in metadata['lanes'] if l['id']==lane['id'])
            current.update(status='returned' if rc==0 else 'failed',finished_at=utc(),returncode=rc); save(mp,metadata)
            batch_log(jobs,batch,'lane '+lane['id']+' finished rc='+str(rc))
            report=finalize(jobs,plan,metadata,env,auth)
            if report is not None and not report['delivery_complete']: rc=1
    return rc

def main():
    p=argparse.ArgumentParser(description=__doc__); p.add_argument('--assignment',type=Path,required=True)
    p.add_argument('batch'); p.add_argument('tasks',nargs='+'); a=p.parse_args()
    def interrupted(signum,frame): raise KeyboardInterrupt('lane interrupted')
    signal.signal(signal.SIGTERM,interrupted)
    try: return run(component(a.batch),a.tasks,a.assignment)
    except (OSError,ValueError,KeyError,ImportError,subprocess.TimeoutExpired) as e: p.exit(2,'Batch blocked: '+str(e)+'\n')

if __name__=='__main__': raise SystemExit(main())
