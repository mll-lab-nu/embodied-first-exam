#!/usr/bin/env python3
"""Read-only HF target check or three-file remote hash receipt for standard tar.

Does not create datasets or upload. The helper can keep using the documented hf CLI.
"""
import argparse
import json
from pathlib import Path
import tarfile
import tempfile
from urllib.parse import quote
from agent_batch_contract import read, validate, save, linked_rerun, component, outcome_counts
from agent_batch_delivery import unpack, external_manifest
from difficulty_results_hf import Hub, file_identity
from helper_bundle import guard
from difficulty_hf_auth import resolve_token, HFError

def access(target, hub, *, write=True):
    hub.call('auth',write=write)
    if not hub.call('private'): raise ValueError('maintainer must provide an existing private HF dataset')
    head=hub.call('head')
    return dict(repo_id=target['repo_id'],prefix=target['prefix'],revision=head,private=True,
                access='write' if write else 'read',
                url=f"https://huggingface.co/datasets/{target['repo_id']}/tree/{head or 'main'}/{quote(target['prefix'],safe='/')}")

def check(folder,plan,args,hub=None):
    target=plan['upload']
    if target['type']!='hf': raise ValueError('assignment does not use HF')
    retries=[linked_rerun(plan,read(path)) for path in getattr(args,'rerun_assignment',())]
    if hub is None:
        token,_=resolve_token(args)
        state=folder.parent/'.batch-hf-state'/plan['batch']; state.mkdir(parents=True,exist_ok=True)
        hub=Hub(token,target['repo_id'],state,guard)
    result=access(target,hub); head=result['revision']
    archive=folder/(plan['batch']+'__'+plan['helper']+'.tar.gz')
    with tempfile.TemporaryDirectory(prefix='native-hf-check-') as td:
        report=unpack(archive,Path(td),plan,reruns=retries)
        notes=external_manifest(folder/'MANIFEST.md',Path(td)/'agents'/(plan['batch']+'-MANIFEST.md'),plan)
    paths=[archive,archive.with_name(archive.name+'.sha256'),folder/'MANIFEST.md']
    expected={p.name:file_identity(p,guard) for p in paths}
    remote=hub.call('info',paths=[target['prefix']+'/'+p.name for p in paths],revision=head)
    for p in paths:
        actual=remote.get(target['prefix']+'/'+p.name); want=expected[p.name]
        if not actual and not args.verify_uploaded: continue
        if not actual or actual['size']!=want['size'] or not (actual.get('sha256')==want['sha256'] or
                (not actual.get('sha256') and actual.get('git_blob_sha1')==want['git_blob_sha1'])):
            raise ValueError('remote missing or different: '+p.name)
    return dict(result,files=expected,remote_verified=args.verify_uploaded,delivery_complete=report['delivery_complete'],helper_manifest=notes,
                **outcome_counts(report))

def main():
    p=argparse.ArgumentParser(description=__doc__); p.add_argument('--assignment',type=Path)
    p.add_argument('--rerun-assignment',type=Path,action='append',default=[],help='maintainer authorization for reruns included in the archive')
    p.add_argument('--folder',type=Path); p.add_argument('--verify-uploaded',action='store_true')
    p.add_argument('--check-access',action='store_true',help='check only target permissions; no GPU, model or result files')
    p.add_argument('--access',choices=('read','write'),default='write')
    p.add_argument('--repo-id'); p.add_argument('--helper'); p.add_argument('--batch')
    p.add_argument('--receipt',type=Path)
    tokens=p.add_mutually_exclusive_group(); tokens.add_argument('--hf-token-file',type=Path); tokens.add_argument('--hf-token-env')
    a=p.parse_args()
    try:
        if a.check_access:
            if a.folder or a.verify_uploaded or a.rerun_assignment: raise ValueError('access check does not inspect result files')
            if a.assignment:
                if a.repo_id or a.helper or a.batch: raise ValueError('target must come from assignment or explicit fields, not both')
                target=validate(read(a.assignment))['upload']
                if target['type']!='hf': raise ValueError('assignment does not use HF')
            else:
                import re
                component(a.helper); component(a.batch)
                if a.helper!=a.helper.lower(): raise ValueError('helper ID must be lowercase')
                if not a.repo_id or not re.fullmatch(r'[A-Za-z0-9_-]+/[A-Za-z0-9_.-]+',a.repo_id) or '..' in a.repo_id:
                    raise ValueError('provide a valid --repo-id')
                target=dict(repo_id=a.repo_id,prefix=f'helpers/{a.helper}/{a.batch}')
            token,_=resolve_token(a)
            with tempfile.TemporaryDirectory(prefix='native-hf-access-') as td:
                result=access(target,Hub(token,target['repo_id'],Path(td),guard),write=a.access=='write')
        else:
            if not a.assignment or not a.folder: raise ValueError('result check requires --assignment and --folder')
            if a.repo_id or a.helper or a.batch or a.access!='write': raise ValueError('target/access options require --check-access')
            result=check(a.folder,validate(read(a.assignment)),a)
        if a.receipt: save(a.receipt,result)
        print(json.dumps(result,indent=2)); return 0
    except (ValueError,OSError,KeyError,TypeError,tarfile.TarError,HFError) as e: p.exit(2,'HF check failed: '+str(e)+'\n')

if __name__=='__main__': raise SystemExit(main())
