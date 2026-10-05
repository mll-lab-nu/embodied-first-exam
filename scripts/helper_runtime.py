"""Helper execution provenance and independently owned agent-record mirror."""
from contextlib import contextmanager, suppress
import os
from pathlib import Path
import platform
import time
import uuid
from helper_assignment import atomic_json, read_json, utc

@contextmanager
def record(evaluation):
    if not evaluation.helper_assignment:
        yield; return
    run=evaluation.run; path=run/'helper-runtime.json'
    value=read_json(path) if path.exists() else dict(schema_version=1,helper=evaluation.helper_assignment['helper'],invocations=[])
    host={}
    mounted=Path('/run/topogym-launch/host-info.tsv')
    if mounted.is_file():
        for line in mounted.read_text().splitlines():
            if '\t' in line:
                k,v=line.split('\t',1); host[k]=v
    else:
        host=dict(system=platform.platform(),cpu=platform.processor() or 'unknown',cpu_count=os.cpu_count(),
                  memory_kib=next((l.split()[1] for l in Path('/proc/meminfo').read_text().splitlines() if l.startswith('MemTotal:')), 'unknown'))
    invocation=dict(started_at=utc(),phase=evaluation.args.phase,host=host,lane_count=1,gpu_requested=evaluation.args.gpu_device,
                    auth=evaluation.args.auth,status='running')
    if os.environ.get('TOPOGYM_CONTROLLER_LOG'):
        invocation['controller_log']=os.environ['TOPOGYM_CONTROLLER_LOG']
    value['invocations'].append(invocation); atomic_json(path,value)
    try:
        yield
    except BaseException as error:
        invocation.update(status='error',error_type=type(error).__name__)
        raise
    else: invocation['status']='returned'
    finally:
        invocation['finished_at']=utc(); atomic_json(path,value)

@contextmanager
def mirror(evaluation):
    if not evaluation.helper_assignment:
        yield; return
    run=evaluation.run; metadata=run/'mirror.json'
    required=evaluation.helper_assignment['mirror']=='required'
    destination=evaluation.work/'jobs/difficulty_trials_mirror'/evaluation.args.run_id
    destination.mkdir(parents=True,exist_ok=True)
    commands=evaluation.commands
    ident='tg-helper-mirror-'+uuid.uuid4().hex
    marker='.ready-'+uuid.uuid4().hex
    image=(evaluation.delivery.images['client']['image'] if evaluation.delivery else evaluation.image)
    labels=dict(evaluation.resource_labels(), **{'topogym.role':'mirror'})
    opts=[]
    for k,v in labels.items(): opts+=['--label',f'{k}={v}']
    base=['docker','run','--network','none','--read-only','--user','0:0','--tmpfs','/tmp',*opts,
          '--mount',f'type=bind,src={evaluation.jobs},dst=/src,readonly',
          '--mount',f'type=bind,src={destination},dst=/mirror',
          '--mount',f'type=bind,src={evaluation.source}/scripts/log_mirror.py,dst=/log_mirror.py,readonly',
          '--mount',f'type=bind,src={evaluation.source}/scripts/helper_log_mirror.py,dst=/mirror-tool.py,readonly']
    command=['python','/mirror-tool.py','--src','/src','--mirror','/mirror','--strict']
    started=False
    try:
        code,_=commands.run_command([*base,'-d','--name',ident,image,*command,'--ready-file','/mirror/'+marker],
                                     log=run/'mirror.log',append=True,timeout=30)
        if code: raise ValueError('helper mirror could not start')
        started=True; deadline=time.monotonic()+30
        while not (destination/marker).is_file():
            _,status=commands.run_command(['docker','inspect','--format','{{.State.Running}}',ident],capture=True,check=True,timeout=10)
            if status.strip()!='true' or time.monotonic()>deadline: raise ValueError('helper mirror not ready')
            time.sleep(.2)
        atomic_json(metadata,dict(status='recording',required=required,container=ident,updated_at=utc()))
    except Exception:
        atomic_json(metadata,dict(status='unavailable',required=required,updated_at=utc()))
        if started: commands.run_command(['docker','rm','-f',ident],timeout=30)
        if required: raise
        yield; return
    try:
        yield
    finally:
        healthy=False
        try:
            _,status=commands.run_command(['docker','inspect','--format','{{.State.Running}}',ident],capture=True,check=True,timeout=15)
            healthy=status.strip()=='true'
        finally:
            commands.run_command(['docker','rm','-f',ident],timeout=30)
        code,_=commands.run_command([*base,'--rm',image,*command,'--once'],log=run/'mirror.log',append=True,timeout=120)
        # Root-owned raw evidence is read-only to the helper. Readable file modes
        # originate from the mirror process, not from weakening job permissions.
        atomic_json(metadata,dict(status='complete' if healthy and code==0 else 'incomplete',required=required,updated_at=utc()))
        if required and (not healthy or code): raise ValueError('helper mirror incomplete; raw evidence retained')
