#!/usr/bin/env python3
"""Publish preflighted difficulty packages and an immutable native batch dispatch.

Writes new task directories only. Does not activate the global 39-instance release,
commit, upload images, launch a model, or inherit qualification from a different run.
"""
import argparse
import json
from pathlib import Path
import shutil
import sys
import tempfile
import tomllib
import yaml
from agent_batch_contract import FORMAT, component, digest, inventory, read, save, validate, locked
from helper_assignment import validate_manifest, planned_trials
from sample_difficulty_instances import verify_source
from topogym_versions import identity, require_task, task_lock

ROOT=Path(__file__).resolve().parents[1]

def portable_compose(path):
    data=yaml.safe_load(path.read_text())
    for service in data.get('services',{}).values():
        labels=service.get('labels',{})
        if isinstance(labels,dict):
            service['labels']={k:v for k,v in labels.items() if not k.startswith('topogym.')}
            service['labels'].update({'topogym.batch.owner':'${TOPOGYM_BATCH_OWNER}', 'topogym.batch':'${TOPOGYM_BATCH}'})
        env=service.setdefault('environment',{})
        if 'NVIDIA_VISIBLE_DEVICES' in env: env['NVIDIA_VISIBLE_DEVICES']='${TOPOGYM_GPU_UUID:-0}'
        for device in service.get('deploy',{}).get('resources',{}).get('reservations',{}).get('devices',[]):
            if device.get('driver')=='nvidia':
                device.pop('count',None); device['device_ids']=['${TOPOGYM_GPU_UUID:-0}']
        if 'user' in service: service['user']='${TOPOGYM_RUN_UID:-1000}:${TOPOGYM_RUN_GID:-1000}'
    for net in data.get('networks',{}).values():
        if isinstance(net,dict) and isinstance(net.get('labels'),dict):
            net['labels']={k:v for k,v in net['labels'].items() if not k.startswith('topogym.')}
    path.write_text(yaml.safe_dump(data,sort_keys=False))

def publish(run, repository, batch, helper, **options):
    with locked(Path(repository)/'.native-publish.lock'):
        return _publish(run,repository,batch,helper,**options)

def _publish(run, repository, batch, helper, *, repetitions=None, model=None, effort=None, agent=None, upload=None, task_bases=None):
    run=Path(run).resolve(); repository=Path(repository).resolve(); component(batch); component(helper)
    dispatch=repository/'configs/helper_batches'/(batch+'.json')
    if dispatch.exists(): raise ValueError('batch dispatch already exists; preserve it')
    manifest=validate_manifest(read(run/'manifest.lock.json')); verify_source(run)
    preset=manifest['settings'].get('native_batch',{})
    repetitions=repetitions if repetitions is not None else preset.get('repetitions',3)
    model=model or preset.get('model','openai/gpt-6-luna')
    effort=effort or preset.get('effort','xhigh'); agent=agent or preset.get('agent','codex')
    if identity(repository)!=manifest['release']: raise ValueError('publish checkout differs from the prepared release definition')
    if read(run/'source_identity.json')['sha256']!=manifest['source_sha256']: raise ValueError('source identity mismatch')
    if task_bases is not None and (not task_bases or len(task_bases)!=len(set(task_bases)) or set(task_bases)-{r['slug'] for r in manifest['instances']}):
        raise ValueError('unknown/duplicate task base selection')
    records=[]; targets=[]
    # Validate every input before publishing anything.
    for row,mode in planned_trials(manifest):
        if task_bases is not None and row['slug'] not in task_bases: continue
        proof=read(run/'build'/row['slug']/'preflight.ok.json'); prepared=read(run/'build'/row['slug']/'prepared.json')
        from agent_batch_contract import sha
        if proof.get('passed') is not True or proof.get('evidence_identity',{}).get('prepared_sha256')!=sha(run/'build'/row['slug']/'prepared.json'):
            raise ValueError('missing or stale preflight: '+row['slug'])
        evidence=proof['evidence_identity']
        if (proof.get('files')!=prepared['files'] or evidence.get('probe_version')!=5
                or evidence.get('image')!=read(run/'image.json')
                or evidence.get('probe_sha256')!=sha(run/'source/scripts/difficulty_eval.py')
                or evidence.get('tool_sha256')!=sha(run/'tasks'/(row['slug']+'-privileged')/'environment/rcb_topogym.py')
                or not evidence.get('gpu_profile') or not evidence.get('client_image')):
            raise ValueError('preflight provenance differs from frozen package/runtime')
        for rel,h in prepared['files'].items():
            from agent_batch_contract import relative
            if sha(run/relative(rel))!=h: raise ValueError('prepared package changed')
        suffix='standard' if mode=='limited' else 'privileged'; name=row['slug']+'-'+suffix
        src=run/'tasks'/name; dst=repository/'tasks'/name
        if dst.exists() and not dst.is_dir(): raise ValueError('published task path is not a directory: '+name)
        require_task(src,run/'source',inspect_docker=True)
        actual=read(src/('environment/sim/instance.json' if suffix=='standard' else 'environment/instance.json'))
        if (actual['task'],actual['seed'],actual['variation_id'])!=(row['task_id'],row['scene_seed'],row['variation_id']): raise ValueError('sample selection changed')
        targets.append((src,dst,row,suffix,proof))
    with tempfile.TemporaryDirectory(prefix='.batch-publish-',dir=repository) as td:
        stage=Path(td)
        for src,dst,row,mode,proof in targets:
            inventory(src)  # reject links before copying
            copy=stage/dst.name; shutil.copytree(src,copy)
            for compose in copy.rglob('docker-compose.yaml'): portable_compose(compose)
            require_task(copy,repository,inspect_docker=True)
            hashes=inventory(copy); lock=task_lock(copy); cfg=tomllib.loads((copy/'task.toml').read_text())
            if manifest['settings'].get('agent_wall_clock_s',cfg['agent']['timeout_sec'])!=cfg['agent']['timeout_sec']:
                raise ValueError('prepared task budget differs from the frozen sweep')
            if dst.exists() and inventory(dst)!=hashes: raise ValueError('refusing to overwrite different published task: '+dst.name)
            from harbor.models.task.task import Task
            from topogym.simulator.frozen_binding import binding_id
            records.append(dict(name=dst.name,base=row['slug'],mode=mode,task_id=row['task_id'],difficulty=row['difficulty'],
                scene_seed=row['scene_seed'],variation_id=row['variation_id'],sample_sha256=row['sample_sha256'],files=hashes,package_sha256=digest(hashes),
                harbor_checksum=Task(copy).checksum,
                binding_id=binding_id(lock),runtime_binding=lock,agent_timeout_sec=cfg['agent']['timeout_sec'],
                preflight=proof,success_artifacts=['verifier/replay.mp4','verifier/replay.last.png']))
        kwargs={'reasoning_effort':effort,'web_search':'disabled'} if agent=='codex' else {'reasoning_effort':effort,'disallowed_tools':'WebSearch,WebFetch'}
        if agent=='codex': kwargs['version']='0.157.0'
        plan=dict(format=FORMAT,schema_version=1,batch=batch,helper=helper,release=manifest['release'],repetitions=repetitions,
                  instance_selection=manifest['settings'].get('instance_selection','sampled'),images=read(run/'image.json').get('images',{}),
                  task_bases=list(dict.fromkeys(t['base'] for t in records)),tasks=records,trial_count=len(records)*repetitions,
                  jobs=[dict(job=batch+'-'+t['mode']+'-'+t['base'],task=t['name'],repetitions=repetitions) for t in records],
                  agent=dict(name=agent,model=model,kwargs=kwargs),mirror_required=True,upload=upload or {'type':'shared-folder'})
        if preset.get('token_budget'): plan['token_budget']=preset['token_budget']
        runner_names=['scripts/'+name for name in ('run_agent_batch.sh','agent_batch_runtime.py','agent_batch_contract.py','agent_batch_delivery.py',
            'agent_batch_mirror_copy.py','helper_log_mirror.py','log_mirror.py','secret_scan.py','scan_secrets.py','account_failure_check.py','topogym_versions.py',
            'helper_batch.py','setup_agent_batch.sh','finish_agent_batch.py','check_agent_batch_auth.py','check_agent_batch_hf.py',
            'difficulty_hf_auth.py','difficulty_results_hf.py','helper_bundle.py')]
        runner_names+=['bash_scripts/run_helper_batch.sh']
        runner_names+=['harbor_agents/persistent_auth.py','images/difficulty-eval/patch_harbor.py','requirements/difficulty-eval-controller.lock','topogym/utils/process_limits.py']
        plan['runner_files']={name:sha(repository/name) for name in runner_names}
        plan['plan_sha256']=digest(plan); validate(plan)
        dataset=repository/'tasks/dataset.toml'
        from harbor.models.task.task import Task
        old_dataset=dataset.read_text()
        parsed=tomllib.loads(old_dataset); namespace=parsed['dataset']['name'].split('/')[0]
        old_records={t['name'].split('/')[-1]:t for t in parsed.get('tasks',[])}
        if len(old_records)!=len(parsed.get('tasks',[])): raise ValueError('duplicate dataset task names')
        addition=''
        for t in records:
            checksum=t['harbor_checksum']
            if t['name'] in old_records:
                if old_records[t['name']].get('digest')!='sha256:'+checksum or not (repository/'tasks'/t['name']).is_dir():
                    raise ValueError('existing dataset digest/package differs: '+t['name'])
                continue
            addition+='\n[[tasks]]\nname = '+json.dumps(namespace+'/'+t['name'])+'\ndigest = '+json.dumps('sha256:'+checksum)+'\n'
        # Compute all dependencies before the first mutation. Dispatch is the commit marker;
        # interrupted publication has no runnable dispatch and preserves added evidence.
        for _,dst,_,_,_ in targets:
            if not dst.exists():
                dst.parent.mkdir(parents=True,exist_ok=True); (stage/dst.name).rename(dst)
        (stage/'dataset.toml').write_text(old_dataset+addition)
        (stage/'dataset.toml').replace(dataset)
        save(repository/'configs/helper_batches'/(batch+'.source.json'),dict(source_sha256=manifest['source_sha256'],manifest_sha256=manifest['manifest_sha256']))
        save(dispatch,plan)
    return dispatch

def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--run',type=Path,required=True); p.add_argument('--repository',type=Path,default=ROOT)
    p.add_argument('--batch',required=True); p.add_argument('--helper',required=True); p.add_argument('--repetitions',type=int)
    p.add_argument('--model'); p.add_argument('--effort')
    p.add_argument('--agent',choices=('codex','claude-code')); p.add_argument('--upload-spec',type=Path)
    p.add_argument('--task-base',action='append',help='publish a selected smoke subset; repeatable, exact manifest slug')
    a=p.parse_args()
    try:
        print(publish(a.run,a.repository,a.batch,a.helper,repetitions=a.repetitions,model=a.model,effort=a.effort,agent=a.agent,upload=read(a.upload_spec) if a.upload_spec else None,task_bases=a.task_base))
    except (OSError,ValueError,KeyError) as e: p.exit(2,'Publication blocked: '+str(e)+'\n')

if __name__=='__main__': main()
