#!/usr/bin/env python3
"""Publish prepared difficulty packages and an immutable native batch dispatch.

Writes new task directories only. Does not activate the global 39-instance release,
commit, upload images, launch a model, or inherit qualification from a different run.
Preflight is required by default; an explicit maintainer reason may waive missing
preflight evidence. Existing passes still undergo all provenance checks.
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

def _publish(run, repository, batch, helper, *, repetitions=None, model=None, effort=None, agent=None, upload=None, task_bases=None, helper_selects_model=False, image_sources=None, skip_preflight_reason=None):
    run=Path(run).resolve(); repository=Path(repository).resolve(); component(batch); component(helper)
    if skip_preflight_reason is not None:
        if not isinstance(skip_preflight_reason,str) or not skip_preflight_reason.strip():
            raise ValueError('skipping preflight needs a nonempty maintainer reason')
        skip_preflight_reason=skip_preflight_reason.strip()
    if helper!=helper.lower(): raise ValueError('helper ID must be lowercase')
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
        proof_path=run/'build'/row['slug']/'preflight.ok.json'
        prepared=read(run/'build'/row['slug']/'prepared.json')
        from agent_batch_contract import sha
        if proof_path.exists():
            proof=read(proof_path)
            if proof.get('passed') is not True or proof.get('evidence_identity',{}).get('prepared_sha256')!=sha(run/'build'/row['slug']/'prepared.json'):
                raise ValueError('missing or stale preflight: '+row['slug'])
            evidence=proof['evidence_identity']
            if (proof.get('files')!=prepared['files'] or evidence.get('probe_version')!=5
                    or evidence.get('image')!=read(run/'image.json')
                    or evidence.get('probe_sha256')!=sha(run/'source/scripts/difficulty_eval.py')
                    or evidence.get('tool_sha256')!=sha(run/'tasks'/(row['slug']+'-privileged')/'environment/rcb_topogym.py')
                    or not evidence.get('gpu_profile') or not evidence.get('client_image')):
                raise ValueError('preflight provenance differs from frozen package/runtime')
        elif skip_preflight_reason is not None:
            proof=dict(passed=False,status='skipped',reason=skip_preflight_reason,
                       scope='preflight_incomplete',solvability_proven=False,
                       attempted=(proof_path.parent/'preflight.log').is_file())
        else:
            raise ValueError('missing preflight: '+row['slug'])
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
        if agent=='muse-openrouter':
            from harbor_agents.muse_transport.launch import VERSION
            kwargs={'version':VERSION,'reasoning_effort':effort}
        if effort=='default': kwargs.pop('reasoning_effort',None)
        if agent=='codex': kwargs['version']='0.157.0'
        plan=dict(format=FORMAT,schema_version=1,batch=batch,helper=helper,release=manifest['release'],repetitions=repetitions,
                  instance_selection=manifest['settings'].get('instance_selection','sampled'),images=read(run/'image.json').get('images',{}),
                  task_bases=list(dict.fromkeys(t['base'] for t in records)),tasks=records,trial_count=len(records)*repetitions,
                  jobs=[dict(job=batch+'-'+t['mode']+'-'+t['base'],task=t['name'],repetitions=repetitions) for t in records],
                  agent=dict(name=agent,model=model,kwargs=kwargs),mirror_required=True,upload=upload or {'type':'shared-folder'})
        if preset.get('token_budget'): plan['token_budget']=preset['token_budget']
        if agent=='muse-openrouter': plan['harness_protocol']='muse-openrouter-adapted-v1'
        if skip_preflight_reason is not None:
            plan['preflight_policy']=dict(required=False,reason=skip_preflight_reason,
                passed_task_bases=sorted({t['base'] for t in records if t['preflight']['passed']}),
                unchecked_task_bases=sorted({t['base'] for t in records if not t['preflight']['passed']}))
        if helper_selects_model: plan['helper_selects_model']=True
        if image_sources is not None:
            from agent_batch_images import validate_sources, references
            plan['image_sources']=validate_sources(image_sources,references(plan))
            from agent_batch_image_build import materials
            for reference,source in image_sources.items():
                if 'build' not in source: continue
                build_manifest,_=materials(repository,source['build'])
                if build_manifest['reference_image']!={'reference':reference,'id':references(plan)[reference]}:
                    raise ValueError('build recipe is for a different prepared image')
                for task in records:
                    if task['runtime_binding']['image']['reference']==reference and task['runtime_binding']['runtime']!=source['build']['expected']['runtime']:
                        raise ValueError('build contents differ from prepared runtime')
        runner_names=['scripts/'+name for name in ('run_agent_batch.sh','agent_batch_bootstrap.py','agent_batch_images.py','agent_batch_image_build.py','agent_batch_image_probe.py','agent_batch_image_os.py','agent_batch_runtime.py','agent_batch_contract.py','agent_batch_delivery.py',
            'agent_batch_mirror_copy.py','helper_log_mirror.py','log_mirror.py','secret_scan.py','scan_secrets.py','account_failure_check.py','topogym_versions.py',
            'helper_batch.py','setup_agent_batch.sh','finish_agent_batch.py','check_agent_batch_auth.py','check_agent_batch_hf.py',
            'difficulty_hf_auth.py','difficulty_results_hf.py','helper_bundle.py','export_native_helper_release.py',
            'import_helper_results.py','collect_batch_results.py','helper_assignment.py')]
        runner_names+=['bash_scripts/run_helper_batch.sh']
        runner_names+=['scripts/agent_batch_provider.py','scripts/patch_agent_batch_providers.py','scripts/configure_agent_batch.py','scripts/agent_batch_host.py']
        runner_names+=['harbor_agents/persistent_auth.py','images/difficulty-eval/patch_harbor.py','requirements/difficulty-eval-controller.lock','topogym/utils/process_limits.py']
        runner_names+=['harbor_agents/muse_openrouter.py']
        runner_names += [p.relative_to(repository).as_posix() for p in (repository/'harbor_agents/muse_transport').iterdir()
                         if p.is_file() and p.suffix!='.pyc']
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
    p.add_argument('--helper-selects-model',action='store_true',help='delegate MODEL/EFFORT selection to helper; tasks, budgets and AGENT stay fixed')
    p.add_argument('--image-sources',type=Path,help='maintainer JSON mapping frozen image references to pinned registry/archive downloads')
    p.add_argument('--agent',choices=('codex','claude-code','muse-openrouter')); p.add_argument('--upload-spec',type=Path)
    p.add_argument('--task-base',action='append',help='publish a selected smoke subset; repeatable, exact manifest slug')
    p.add_argument('--skip-preflight-reason',help='maintainer-only: publish prepared packages without full preflight; record the reason and retain existing passes')
    a=p.parse_args()
    try:
        print(publish(a.run,a.repository,a.batch,a.helper,repetitions=a.repetitions,model=a.model,effort=a.effort,agent=a.agent,upload=read(a.upload_spec) if a.upload_spec else None,task_bases=a.task_base,helper_selects_model=a.helper_selects_model,image_sources=read(a.image_sources) if a.image_sources else None,skip_preflight_reason=a.skip_preflight_reason))
    except (OSError,ValueError,KeyError) as e: p.exit(2,'Publication blocked: '+str(e)+'\n')

if __name__=='__main__': main()
