"""Versioned helper assignments and shared trial enumeration (no physics imports)."""
from __future__ import annotations
import copy
import datetime as dt
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import tempfile

MODES = ('unlimited', 'limited')
COMPLETE = {'solved', 'unsolved', 'not_evaluable', 'invalid_submission'}

def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(',', ':'), allow_nan=False).encode()).hexdigest()

def utc(): return dt.datetime.now(dt.timezone.utc).isoformat(timespec='seconds')

def component(value):
    if not isinstance(value, str) or not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_-]{0,79}', value):
        raise ValueError('invalid helper identity component')
    return value

def atomic_json(path, value):
    path = Path(path); path.parent.mkdir(parents=True, exist_ok=True)
    fd, temp = tempfile.mkstemp(prefix='.helper-', dir=path.parent)
    try:
        with os.fdopen(fd, 'w') as stream:
            json.dump(value, stream, indent=2, sort_keys=True, allow_nan=False); stream.write('\n')
            stream.flush(); os.fsync(stream.fileno())
        os.replace(temp, path)
    finally:
        if os.path.exists(temp): os.unlink(temp)

def read_json(path):
    with Path(path).open() as stream: return json.load(stream)

def sample_key(row): return (row['task_id'], row['difficulty'], row['sample_id'])

def stem(row, mode):
    return f"d{row['task_number']:02d}-{row['difficulty']}-{row['sample_id']}-{mode}"

def planned_trials(manifest):
    """Legacy manifests keep dual-mode semantics; schema 2 uses explicit identities."""
    samples = {sample_key(row): row for row in manifest['instances']}
    if len(samples) != len(manifest['instances']): raise ValueError('duplicate instance identity')
    if manifest.get('schema_version') == 2:
        pairs = []
        for trial in manifest['trials']:
            key = tuple(trial[k] for k in ('task_id', 'difficulty', 'sample_id'))
            row = samples.get(key)
            if row is None or trial['mode'] not in MODES or trial['trial_id'] != stem(row, trial['mode']):
                raise ValueError('invalid assigned trial')
            pairs.append((row, trial['mode']))
    else:
        pairs = [(row, mode) for row in manifest['instances'] for mode in MODES]
    keys = [(*sample_key(r), mode) for r, mode in pairs]
    if not pairs or len(keys) != len(set(keys)) or manifest.get('trial_count', len(keys)) != len(keys):
        raise ValueError('invalid planned trial count')
    if {sample_key(r) for r, _ in pairs} != set(samples): raise ValueError('unassigned instance')
    return pairs

def modes_for(manifest, row):
    return [mode for sample, mode in planned_trials(manifest) if sample_key(sample) == sample_key(row)]

def validate_manifest(manifest):
    if manifest.get('schema_version') not in (1, 2): raise ValueError('unknown manifest schema')
    if manifest.get('manifest_sha256') != digest({k:v for k,v in manifest.items() if k != 'manifest_sha256'}):
        raise ValueError('manifest digest mismatch')
    for row in manifest['instances']:
        for name in ('task_id', 'difficulty', 'sample_id', 'slug'): component(row[name])
        if row['sample_sha256'] != digest({k:v for k,v in row.items() if k != 'sample_sha256'}):
            raise ValueError('sample digest mismatch')
        if type(row['task_number']) is not int or not 1 <= row['task_number'] <= 13:
            raise ValueError('invalid task number')
        if row['difficulty'] not in ('easy','medium','hard') or type(row['scene_seed']) is not int or not 0 <= row['scene_seed'] < 2**32:
            raise ValueError('invalid difficulty or seed')
    if manifest['instance_count'] != len(manifest['instances']): raise ValueError('instance count mismatch')
    planned_trials(manifest)
    return manifest

def validate_assignment(data):
    if data.get('schema_version') != 1 or data.get('format') != 'topogym-helper-assignment':
        raise ValueError('unsupported helper assignment')
    if data.get('assignment_sha256') != digest({k:v for k,v in data.items() if k != 'assignment_sha256'}):
        raise ValueError('assignment digest mismatch')
    component(data['batch']); component(data['helper']['id'])
    manifest = validate_manifest(data['manifest'])
    if manifest['schema_version'] != 2: raise ValueError('assignment requires explicit trials')
    agent = data['agent']
    if agent['provider'] not in ('openai','openrouter') or not isinstance(agent['model'], str):
        raise ValueError('invalid model provider')
    if not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_./:-]+', agent['model']): raise ValueError('invalid model name')
    expected = 'codex' if agent['provider'] == 'openai' else 'harbor_agents.codex_openrouter:CodexOpenRouter'
    if agent['agent'] != expected: raise ValueError('unsupported assigned agent')
    if (agent['provider'] == 'openai' and not agent['model'].startswith('openai/')) or (agent['provider'] == 'openrouter' and not agent['model'].startswith('openrouter/')):
        raise ValueError('model prefix differs from provider')
    fields = {}
    for arg in agent['agent_args']:
        if not re.fullmatch(r'(version|reasoning_effort)=[A-Za-z0-9._-]+', arg): raise ValueError('invalid agent argument')
        k,v=arg.split('=',1)
        if k in fields: raise ValueError('duplicate agent argument')
        fields[k]=v
    if set(fields) != {'version','reasoning_effort'}: raise ValueError('pin agent version and reasoning_effort')
    if not agent['auth_methods'] or set(agent['auth_methods']) - {'subscription','api-key'}:
        raise ValueError('invalid authentication methods')
    if agent['provider'] == 'openrouter' and 'subscription' in agent['auth_methods']: raise ValueError('OpenRouter needs API authentication')
    if data['cuda_flavor'] not in ('cu128','cu130') or data['mirror'] not in ('required','optional'):
        raise ValueError('invalid runtime policy')
    budget=manifest['settings']['agent_wall_clock_s']
    if type(budget) is not int or not 1 <= budget <= 21600 or manifest['settings']['concurrency'] != 1:
        raise ValueError('invalid helper budget/concurrency')
    target=data['upload']
    if target['type'] == 'hf':
        if not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_-]*/[A-Za-z0-9][A-Za-z0-9_.-]*', target['repo_id']): raise ValueError('invalid HF dataset')
        if '..' in target['repo_id']: raise ValueError('invalid HF dataset')
        for part in target['prefix'].split('/'): component(part)
    elif target['type'] != 'shared-folder': raise ValueError('unsupported upload target')
    return data

def create_assignment(spec, root):
    import sample_difficulty_instances as sampling
    from difficulty_release import source_files
    from topogym_versions import identity
    root=Path(root)
    allowed={'batch','helper','tasks','difficulties','modes','samples_per_difficulty','sampling_seed',
             'agent_wall_clock_s','agent','cuda_flavor','mirror','upload','repository'}
    if set(spec)-allowed: raise ValueError('unknown assignment spec keys')
    tiers=spec.get('difficulties',['easy','medium','hard']); modes=spec.get('modes',list(MODES))
    if not tiers or len(tiers)!=len(set(tiers)) or set(tiers)-set(sampling.DIFFICULTIES): raise ValueError('invalid difficulty selection')
    if not modes or len(modes)!=len(set(modes)) or set(modes)-set(MODES): raise ValueError('invalid mode selection')
    cfg=dict(schema_version=1, task_ids=sampling.select_tasks(spec['tasks']), difficulties=tiers, modes=modes,
             samples_per_difficulty=spec.get('samples_per_difficulty',1), sampling_seed=spec.get('sampling_seed',20260929),
             agent_wall_clock_s=spec['agent_wall_clock_s'], concurrency=1)
    if type(cfg['samples_per_difficulty']) is not int or not 1 <= cfg['samples_per_difficulty'] <= 10000: raise ValueError('invalid sample count')
    if type(cfg['sampling_seed']) is not int or not 0 <= cfg['sampling_seed'] < 2**32: raise ValueError('invalid sampling seed')
    files=source_files(root)
    rows=[r for r in sampling.sample_instances(cfg,root) if r['difficulty'] in tiers]
    trials=[dict(zip(('task_id','difficulty','sample_id'),sample_key(r)),mode=m,trial_id=stem(r,m)) for r in rows for m in modes]
    manifest=dict(schema_version=2,task_mapping_version=1,release=identity(root),task_selector=spec['tasks'],settings=cfg,
                  source_sha256=digest(files),instances=rows,instance_count=len(rows),trial_count=len(trials),trials=trials)
    manifest['manifest_sha256']=digest(manifest)
    if files!=source_files(root): raise ValueError('source changed while assigning; retry from frozen release')
    def git(*args):
        p=subprocess.run(['git',*args],cwd=root,capture_output=True,text=True)
        return p.stdout.strip() if p.returncode==0 else None
    result=dict(schema_version=1,format='topogym-helper-assignment',batch=spec['batch'],helper=spec['helper'],created_at=utc(),
                source=dict(repository=spec.get('repository','TopoGym'),branch=git('branch','--show-current'),commit=git('rev-parse','HEAD')),
                manifest=manifest,agent=spec['agent'],cuda_flavor=spec.get('cuda_flavor','cu128'),mirror=spec.get('mirror','required'),
                upload=spec.get('upload',{'type':'shared-folder'}))
    result['assignment_sha256']=digest(result)
    return validate_assignment(result)

def bind_arguments(args):
    """Reject overrides; authentication and host choices remain helper-owned."""
    if not args.assignment: return
    data=validate_assignment(read_json(args.assignment)); args.helper_assignment=data
    for name, value in [('run_id',data['batch']),('model',data['agent']['model']),('agent',data['agent']['agent']),
                        ('provider',data['agent']['provider']),('cuda_flavor',data['cuda_flavor'])]:
        supplied=getattr(args,name)
        if supplied is not None and supplied!=value: raise ValueError('argument conflicts with assignment: '+name)
        setattr(args,name,value)
    if args.agent_arg and sorted(args.agent_arg)!=sorted(data['agent']['agent_args']): raise ValueError('agent arguments conflict with assignment')
    args.agent_arg=list(data['agent']['agent_args'])
    for name in ('setting','tasks','sampling_seed','samples_per_difficulty','agent_wall_clock_s','concurrency'):
        if getattr(args,name) is not None: raise ValueError('assignment owns experiment setting: '+name)
    auth='api-key' if args.api_key is not None else args.auth
    if auth and auth not in data['agent']['auth_methods']: raise ValueError('authentication is not allowed by assignment')
    if args.rerun_incomplete and not args.retry_plan: raise ValueError('helper rerun requires a maintainer --retry-plan')
    if args.retry_plan and (not args.resume or not args.rerun_incomplete): raise ValueError('--retry-plan requires --resume --rerun-incomplete')

def prepare_run(run, assignment, root, resume):
    import sample_difficulty_instances as sampling
    from difficulty_release import source_files
    run=Path(run); data=validate_assignment(assignment); manifest=data['manifest']
    if run.name!=data['batch']: raise ValueError('batch/run-id mismatch')
    if digest(source_files(Path(root)))!=manifest['source_sha256']: raise ValueError('assignment source differs from this release')
    if (run/'manifest.lock.json').exists():
        if not resume: raise ValueError('helper run exists; use --resume')
        if read_json(run/'manifest.lock.json')!=manifest or read_json(run/'assignment.json')!=data: raise ValueError('immutable helper assignment changed')
        if sampling.verify_source(run)['sha256']!=manifest['source_sha256']: raise ValueError('frozen source changed')
    else:
        run.mkdir(parents=True,exist_ok=True)
        source=sampling.snapshot_source(run,root)
        if source['sha256']!=manifest['source_sha256']: raise ValueError('source changed during helper snapshot')
        atomic_json(run/'source_identity.json',source); atomic_json(run/'assignment.json',data)
        atomic_json(run/'manifest.lock.json',manifest)
        atomic_json(run/'run-created.json',{'created_at':utc()})
    return copy.deepcopy(manifest)

def retry_targets(path, assignment):
    if not path: return set()
    data=read_json(path)
    if data.get('assignment_sha256')!=assignment['assignment_sha256'] or not data.get('reason'):
        raise ValueError('invalid retry plan identity/reason')
    permitted={stem(r,m) for r,m in planned_trials(assignment['manifest'])}|{'canary'}
    ids=data.get('trial_ids',[])
    if not ids or len(ids)!=len(set(ids)) or set(ids)-permitted: raise ValueError('invalid retry trial list')
    return set(ids)
