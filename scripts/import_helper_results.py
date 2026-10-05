#!/usr/bin/env python3
"""Receive native helper results at one pinned HF revision; independent of execution."""
import argparse
import json
import os
from pathlib import Path
import re
import shutil
import tarfile
import tempfile

from agent_batch_contract import read, save, validate, locked, linked_rerun
from agent_batch_delivery import unpack, receive
from difficulty_hf_auth import resolve_token, HFError
from difficulty_results_hf import Hub, file_identity
from helper_bundle import guard
from check_agent_batch_hf import access


def matches(actual, expected):
    return (actual['size']==expected['size'] and
            (actual['sha256']==expected['sha256'] if expected.get('sha256') else
             actual['git_blob_sha1']==expected.get('git_blob_sha1')))


def download(plan, folder, hub, *, revision=None, max_bytes=50*1024**3):
    folder=Path(folder); target=plan['upload']
    if target['type']!='hf': raise ValueError('assignment does not use HF')
    info=access(target,hub,write=False)
    head=revision or info['revision']
    if not head or not re.fullmatch(r'[a-f0-9]{40,64}',head): raise ValueError('HF revision must be an existing full commit hash')
    folder.parent.mkdir(parents=True,exist_ok=True)
    name=plan['batch']+'__'+plan['helper']+'.tar.gz'
    names=[name,name+'.sha256','MANIFEST.md']
    with locked(folder.parent/('.'+folder.name+'.download.lock')):
        if folder.is_symlink(): raise ValueError('download directory is a symlink')
        if folder.exists():
            receipt=read(folder/'download-receipt.json')
            if (receipt['plan_sha256']!=plan['plan_sha256'] or receipt['repo_id']!=target['repo_id']
                    or receipt['prefix']!=target['prefix'] or (revision and receipt['revision']!=revision)):
                raise ValueError('download directory belongs to a different publication')
            # Reuse the original revision even if main advanced in the meantime.
            head=receipt['revision']
            if not re.fullmatch(r'[a-f0-9]{40,64}',head): raise ValueError('invalid saved revision')
            if {p.name for p in folder.iterdir()}!=set(names+['download-receipt.json']):
                raise ValueError('unexpected files in download directory')
        paths=[target['prefix']+'/'+n for n in names]
        remote=hub.call('info',paths=paths,revision=head)
        if set(remote)!=set(paths): raise ValueError('HF delivery is missing one or more of the three files')
        sizes=[remote[p]['size'] for p in paths]
        if any(type(n) is not int or n<0 for n in sizes) or sum(sizes)>max_bytes:
            raise ValueError('remote delivery exceeds --max-download-bytes')
        if sizes[1]>4096 or sizes[2]>16*1024**2: raise ValueError('checksum/manifest exceeds size limit')
        if folder.exists():
            for name,path in zip(names,paths):
                local=folder/name
                if local.is_symlink() or not local.is_file() or not matches(file_identity(local,guard),remote[path]):
                    raise ValueError('saved download differs from pinned HF files')
            return folder/names[0],receipt
        if shutil.disk_usage(folder.parent).free<sum(sizes)+64*1024**2:
            raise ValueError('insufficient disk for HF download')
        with tempfile.TemporaryDirectory(prefix='.helper-download-',dir=folder.parent) as td:
            stage=Path(td)/'files'; stage.mkdir(mode=0o700)
            identities={}
            for name,path in zip(names,paths):
                guard(); hub.call('download',path=path,revision=head,destination=str(stage/name))
                identities[name]=file_identity(stage/name,guard)
                if not matches(identities[name],remote[path]): raise ValueError('downloaded file differs from HF hash')
            # The safe unpacker verifies the checksum and validates its basename too.
            info.update(revision=head,url=f"https://huggingface.co/datasets/{target['repo_id']}/tree/{head}/{target['prefix']}")
            receipt=dict(schema_version=1,**info,plan_sha256=plan['plan_sha256'],files=identities)
            save(stage/'download-receipt.json',receipt); stage.rename(folder)
    return folder/names[0],receipt


def verify(archive,plan,*,reruns=(),require_complete=False):
    with tempfile.TemporaryDirectory(prefix='helper-received-verify-') as td:
        root=Path(td); report=unpack(archive,root,plan,reruns=reruns)
        if (archive.parent/'MANIFEST.md').read_bytes()!=(root/'agents'/(plan['batch']+'-MANIFEST.md')).read_bytes():
            raise ValueError('external MANIFEST differs from archive')
    if require_complete and not report['delivery_complete']: raise ValueError('batch incomplete')
    return report


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--assignment',type=Path,required=True)
    p.add_argument('--work-dir',type=Path,required=True)
    p.add_argument('--phase',choices=('all','download','import'),default='all')
    p.add_argument('--revision',help='full HF commit; first download pins main if omitted')
    p.add_argument('--require-complete',action='store_true')
    p.add_argument('--rerun-assignment',type=Path,action='append',default=[])
    p.add_argument('--max-download-bytes',type=int,default=50*1024**3)
    auth=p.add_mutually_exclusive_group(); auth.add_argument('--hf-token-file',type=Path); auth.add_argument('--hf-token-env')
    a=p.parse_args(); os.umask(0o077)
    try:
        plan=validate(read(a.assignment)); retries=[linked_rerun(plan,read(f)) for f in a.rerun_assignment]
        if a.max_download_bytes<=0: raise ValueError('max download size must be positive')
        work=a.work_dir.resolve(); folder=work/'downloads'/plan['batch']
        archive=folder/(plan['batch']+'__'+plan['helper']+'.tar.gz')
        if a.phase!='import':
            token,_=resolve_token(a)
            with tempfile.TemporaryDirectory(prefix='helper-hf-cache-') as td:
                archive,receipt=download(plan,folder,Hub(token,plan['upload']['repo_id'],Path(td),guard),
                                         revision=a.revision,max_bytes=a.max_download_bytes)
        else:
            receipt=read(folder/'download-receipt.json')
            if (receipt['plan_sha256']!=plan['plan_sha256'] or receipt['repo_id']!=plan['upload'].get('repo_id')
                    or receipt['prefix']!=plan['upload'].get('prefix') or (a.revision and a.revision!=receipt['revision'])):
                raise ValueError('saved download identity differs')
            for name,identity in receipt['files'].items():
                from agent_batch_contract import relative
                local=folder/relative(name)
                if local.is_symlink() or file_identity(local,guard)!=identity: raise ValueError('saved download changed')
        report=verify(archive,plan,reruns=retries,require_complete=a.require_complete)
        if a.phase!='download':
            destination=work/'accepted'/plan['batch']
            receive(archive,plan,destination,reruns=retries,require_complete=a.require_complete)
            save(destination/'hf-source.json',receipt)
            receipt=dict(receipt,accepted=str(destination),review=str(destination/'review/README.md'))
        receipt.update(delivery_complete=report['delivery_complete'],observed_trials=report['observed_trials'])
        print(json.dumps(receipt,indent=2)); return 0
    except (OSError,ValueError,KeyError,TypeError,tarfile.TarError) as error:
        p.exit(2,'Helper receipt rejected: '+str(error)+'\n')


if __name__=='__main__': raise SystemExit(main())
