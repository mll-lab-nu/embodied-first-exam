#!/usr/bin/env python3
"""Export an audited native runner and frozen assignments, without private Git history."""
import argparse
import ast
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import tomllib

from agent_batch_contract import read, save, validate, sha, inventory, package, relative, digest, match_assignment
from secret_scan import scan_tree
from topogym_versions import identity, require_task
from helper_bundle import guard

ROOT=Path(__file__).resolve().parents[1]
OMIT={'agents','planning','data','deferred','legacy','redundants','rollout_simulation','__pycache__'}
SCRIPTS=('run_agent_batch.sh','agent_batch_bootstrap.py','agent_batch_images.py','agent_batch_image_build.py','agent_batch_image_probe.py','agent_batch_image_os.py','agent_batch_runtime.py','agent_batch_contract.py','agent_batch_delivery.py',
         'agent_batch_mirror_copy.py','helper_batch.py','setup_agent_batch.sh','finish_agent_batch.py',
         'check_agent_batch.py','check_agent_batch_auth.py','check_agent_batch_hf.py','import_helper_results.py',
         'difficulty_hf_auth.py','helper_log_mirror.py','log_mirror.py','scan_secrets.py','topogym_versions.py',
         'cuda_profiles.py','export_native_helper_release.py')
BRIDGE=('__init__.py','binding.py','contracts.py','packaging.py')


def code_files(root):
    """Public runtime identity inputs plus explicitly selected host-side entrypoints."""
    root=Path(root); names=set()
    for folder in ('topogym','harbor_templates/topogym','images/topogym','requirements'):
        for path in (root/folder).rglob('*'):
            rel=path.relative_to(root)
            if '__pycache__' in rel.parts or path.suffix=='.pyc': continue
            if folder=='topogym' and (set(rel.parts)&OMIT or path.suffix=='.md'): continue
            if any(part.startswith('.env') or part=='.secrets' for part in rel.parts): continue
            if path.is_symlink(): raise ValueError('export input is a symlink: '+str(rel))
            if path.is_file(): names.add(rel.as_posix())
    names.update('scripts/'+name for name in SCRIPTS)
    names.update('topogym/planning/harbor_bridge/'+name for name in BRIDGE)
    names.update(('topogym/planning/__init__.py','ci_checks/check-topogym-tooling.py',
                  'ci_checks/topogym_active_release.json','ci_checks/topogym_tooling_versions.json',
                  'images/difficulty-eval/patch_harbor.py','harbor_agents/__init__.py','harbor_agents/persistent_auth.py',
                  'bash_scripts/run_helper_batch.sh','bash_scripts/import_helper_results.sh',
                  'configs/helpers/native_helper.example.json'))
    # Discover imports of local script modules; do not copy scripts/ wholesale.
    queue=list(names); seen=set()
    while queue:
        name=queue.pop()
        if name in seen: continue
        seen.add(name)
        path=root/name
        if path.suffix!='.py': continue
        for node in ast.walk(ast.parse(path.read_bytes(),filename=name)):
            modules=[]
            if isinstance(node,ast.Import): modules=[alias.name for alias in node.names]
            elif isinstance(node,ast.ImportFrom) and not node.level and node.module: modules=[node.module]
            for module in modules:
                local='scripts/'+module.replace('.','/')+'.py'
                if (root/local).is_file() and local not in names:
                    names.add(local); queue.append(local)
    for name in ('LICENSE','LICENSE.md','COPYING'):
        if (root/name).is_file(): names.add(name)
    return names


def regular(root,name):
    path=root
    for part in relative(name).parts:
        path=path/part
        if path.is_symlink(): raise ValueError('symlink in export input: '+name)
    if not path.is_file(): raise ValueError('missing export dependency: '+name)
    return path


def verify_release(root,plan=None):
    root=Path(root).resolve(); manifest=read(root/'helper-release.json')
    if manifest.get('schema_version')!=1 or manifest.get('kind')!='native-helper-release':
        raise ValueError('unsupported helper release manifest')
    for name,want in manifest['files'].items():
        if sha(regular(root,name))!=want: raise ValueError('helper release file changed: '+name)
    if identity(root)!=manifest['release']: raise ValueError('helper release runtime identity changed')
    if plan is not None:
        validate(plan)
        if manifest['runtime_only'] or plan.get('release')!=manifest['release']:
            raise ValueError('assignment needs matching frozen tasks and runtime')
        pinned=manifest['assignments'].get(plan['batch'])
        if pinned and pinned!=plan['plan_sha256']:
            original=read(root/'configs/helper_batches'/(plan['batch']+'.json'))
            if original['plan_sha256']!=pinned: raise ValueError('bundled assignment was changed')
            match_assignment(original,plan)
        # A separately issued batch/rerun may reuse these exact packages and tools.
        for task in plan['tasks']: package(root,task)
        for name,want in plan.get('runner_files',{}).items():
            if manifest['files'].get(name)!=want: raise ValueError('assignment runner differs from release')
    return dict(verified=True,runtime_only=manifest['runtime_only'],files=len(manifest['files']),
                assignments=manifest['assignments'])


def export(root,output,assignments=(),*,manual=None,runtime_only=False):
    root=Path(root).resolve(); output=Path(output).absolute()
    if output.exists() or output.is_symlink(): raise ValueError('output exists; preserve it and choose a new release directory')
    if output==root or output.is_relative_to(root): raise ValueError('export outside the development repository')
    if bool(assignments)==runtime_only: raise ValueError('choose --assignment or --runtime-only')
    plans=[validate(read(p)) for p in assignments]
    if len({p['batch'] for p in plans})!=len(plans): raise ValueError('duplicate batch assignment')
    expected=identity(root)
    names=code_files(root); task_names=set()
    for plan in plans:
        if plan['release']!=expected: raise ValueError('assignment differs from source release')
        for source in plan.get('image_sources',{}).values():
            if 'build' not in source: continue
            from agent_batch_image_build import materials
            manifest,context=materials(root,source['build'])
            names.add(source['build']['manifest'])
            names.update((context.relative_to(root)/name).as_posix() for name in manifest['files'])
        for name,want in plan.get('runner_files',{}).items():
            if name not in names: raise ValueError('unreviewed runner dependency: '+name)
            if sha(regular(root,name))!=want: raise ValueError('runner changed since assignment: '+name)
        for task in plan['tasks']:
            source=package(root,task); require_task(source,root)
            task_names.add(task['name'])
            names.update('tasks/'+task['name']+'/'+name for name in task['files'])
    manual=Path(manual).resolve() if manual else root/'docs/rcb/SHARING_RUNS.md'
    if not manual.is_file() and not runtime_only:
        raise ValueError('official SHARING_RUNS.md required; provide --manual with the upstream original')
    input_hashes={name:sha(regular(root,name)) for name in sorted(names)}
    output.parent.mkdir(parents=True,exist_ok=True)
    with tempfile.TemporaryDirectory(prefix='.helper-release-',dir=output.parent) as td:
        stage=Path(td)/'release'; stage.mkdir()
        for name,want in input_hashes.items():
            guard()
            dest=stage/name; dest.parent.mkdir(parents=True,exist_ok=True)
            shutil.copy2(regular(root,name),dest)
            if sha(dest)!=want: raise ValueError('source changed during export: '+name)
        manual_hash=None
        if manual.is_file():
            if manual.is_symlink(): raise ValueError('manual must be a regular file')
            manual_hash=sha(manual)
            dest=stage/'docs/SHARING_RUNS.md'; dest.parent.mkdir(parents=True,exist_ok=True)
            shutil.copyfile(manual,dest)
            if sha(dest)!=manual_hash: raise ValueError('manual changed during export')
        # The maintainer's machine-specific smoke guide is not a helper manual.
        for name in ('SHARING_RUNS_3b.md',):
            source=root/'docs/rcb'/name
            if source.is_file():
                dest=stage/'docs'/name; dest.parent.mkdir(parents=True,exist_ok=True); shutil.copyfile(source,dest)
        if plans:
            # A selected dataset contains exactly the packages distributed here.
            catalog=tomllib.loads((root/'tasks/dataset.toml').read_text())
            entries={t['name'].split('/')[-1]:t for t in catalog['tasks']}
            lines=['[dataset]']+[key+' = '+json.dumps(value) for key,value in catalog['dataset'].items()]
            for name in sorted(task_names):
                row=entries[name]
                wanted=next(t['harbor_checksum'] for p in plans for t in p['tasks'] if t['name']==name)
                if row['digest']!='sha256:'+wanted: raise ValueError('dataset checksum differs from assignment')
                lines+=['','[[tasks]]','name = '+json.dumps(row['name']),'digest = '+json.dumps(row['digest'])]
            (stage/'tasks/dataset.toml').write_text('\n'.join(lines)+'\n')
            for plan in plans: save(stage/'configs/helper_batches'/(plan['batch']+'.json'),plan)
        # Source pruning or dependency omissions must not change the runtime identity.
        if identity(stage)!=expected: raise ValueError('export changed public runtime identity')
        for plan in plans:
            for task in plan['tasks']: require_task(package(stage,task),stage)
        result=subprocess.run(['git','rev-parse','HEAD'],cwd=root,capture_output=True,text=True)
        head=result.stdout.strip() if result.returncode==0 else None
        (stage/'README.md').write_text('# TopoGym native helper release\n\n'+
            ('Runtime tools only; no experimental assignment or tasks included.\n\n' if runtime_only else '')+
            ('See docs/SHARING_RUNS.md for the helper workflow.\n' if manual_hash else
             'See docs/SHARING_RUNS_3b.md; an experimental release additionally requires the official manual.\n')+
            'The documented scripts/run_agent_batch.sh entrypoint installs its tools and prepares assigned images automatically.\n'+
            'Locally built images may have no RepoDigest; record their Docker image Id.\n')
        (stage/'.gitignore').write_text('.venv*/\n.tools/\n.secrets/\n.env*\n**/__pycache__/\n*.pyc\njobs/\nruns/\n')
        if not scan_tree(stage,{},allow_empty_secrets=True,guard=guard)['clean']:
            raise ValueError('release credential-pattern scan failed; no export produced')
        manifest=dict(schema_version=1,kind='native-helper-release',runtime_only=runtime_only,release=expected,
                      source_git_head=head,source_files_sha256=digest(input_hashes),official_manual_sha256=manual_hash,
                      assignments={p['batch']:p['plan_sha256'] for p in plans},
                      scan_scope='credential patterns; no assertion about unknown credentials',
                      images={p['batch']:dict(roles=p.get('images',{}),bindings={
                          t['name']:t['runtime_binding'] for t in p['tasks']}) for p in plans},
                      # Validation imports can generate bytecode in the staging tree.
                      # Git ignores those caches; they are not release dependencies.
                      files={name:value for name,value in inventory(stage).items()
                             if '__pycache__' not in Path(name).parts and Path(name).suffix not in ('.pyc','.pyo')})
        save(stage/'helper-release.json',manifest)
        # Detect source edits during the copy/validation, including concurrent sessions.
        if any(sha(regular(root,name))!=want for name,want in input_hashes.items()):
            raise ValueError('source changed during release; use a stable snapshot')
        stage.rename(output)
    return dict(output=str(output),runtime_only=runtime_only,files=len(manifest['files']),
                manifest_sha256=sha(output/'helper-release.json'),assignments=manifest['assignments'])


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--repository',type=Path,default=ROOT); p.add_argument('--output',type=Path,required=True)
    selection=p.add_mutually_exclusive_group(required=True)
    selection.add_argument('--assignment',type=Path,action='append'); selection.add_argument('--runtime-only',action='store_true')
    selection.add_argument('--verify',action='store_true',help='verify the existing release at --output')
    p.add_argument('--manual',type=Path,help='upstream SHARING_RUNS.md; required for a full helper release')
    a=p.parse_args(); os.umask(0o077)
    try:
        result=verify_release(a.output) if a.verify else export(a.repository,a.output,a.assignment or (),manual=a.manual,runtime_only=a.runtime_only)
        print(json.dumps(result,indent=2))
    except (OSError,ValueError,KeyError,TypeError) as error: p.exit(2,'Helper release blocked: '+str(error)+'\n')


if __name__=='__main__': main()
