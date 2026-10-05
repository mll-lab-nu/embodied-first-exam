#!/usr/bin/env python3
"""Fixed helper assignments, complete evidence bundles and offline acceptance."""
from __future__ import annotations
import argparse
import json
import os
from pathlib import Path
import sys
import tarfile
import zipfile
from helper_assignment import (create_assignment, validate_assignment, read_json, atomic_json,
                               component, digest, retry_targets)
from helper_bundle import export_bundle, verify_bundle, BundleError, guard
from helper_import import import_bundle
from secret_scan import load_secrets, ScanError

ROOT=Path(__file__).resolve().parents[1]

class Parser(argparse.ArgumentParser):
    def error(self,message): super().error('invalid helper arguments; use helper <command> --help')

def parser():
    p=Parser(description=__doc__); commands=p.add_subparsers(dest='command',required=True)
    for name in ('assign','retry-plan','export','verify','import','upload'):
        s=commands.add_parser(name)
        s.add_argument('--work-dir',type=Path,default=Path.cwd()/'topogym-work')
        if name=='assign': s.add_argument('--spec',type=Path,required=True)
        elif name=='retry-plan':
            s.add_argument('--assignment',type=Path,required=True)
            s.add_argument('--trial-id',action='append',required=True)
            s.add_argument('--reason',required=True)
        elif name=='export':
            s.add_argument('--run-id',required=True)
            s.add_argument('--env-file',type=Path,action='append',default=[])
            s.add_argument('--var',action='append',default=[])
            s.add_argument('--codex-auth',type=Path,action='append',default=[])
            s.add_argument('--redact-pii',action='store_true')
        else:
            s.add_argument('--archive',type=Path,required=True)
            if name in ('verify','import'):
                s.add_argument('--assignment',type=Path,help='compare with the maintainer original (recommended)')
                s.add_argument('--require-complete',action='store_true')
            if name=='upload':
                sources=s.add_mutually_exclusive_group()
                sources.add_argument('--hf-token-file',type=Path)
                sources.add_argument('--hf-token-env')
                s.add_argument('--hf-dry-run',action='store_true')
    return p

def execute(args):
    work=args.work_dir.expanduser().resolve()
    if args.command=='assign':
        assignment=create_assignment(read_json(args.spec),ROOT)
        target=work/'assignments'/assignment['batch']/'assignment.json'
        if target.exists(): raise BundleError('assignment already exists; use a new batch')
        atomic_json(target,assignment)
        return dict(assignment=str(target),assignment_sha256=assignment['assignment_sha256'],planned_trials=assignment['manifest']['trial_count'])
    if args.command=='retry-plan':
        assignment=validate_assignment(read_json(args.assignment))
        plan=dict(schema_version=1,assignment_sha256=assignment['assignment_sha256'],trial_ids=args.trial_id,reason=args.reason)
        target=work/'assignments'/assignment['batch']/'retry-plans'/(digest(plan)+'.json')
        atomic_json(target,plan); retry_targets(target,assignment)
        return dict(retry_plan=str(target))
    if args.command=='export':
        component(args.run_id); run=work/'runs/difficulty_trials'/args.run_id
        auths=list(args.codex_auth)
        location=run/'scan-auth-location.json'
        if not auths and location.exists(): auths=[Path(read_json(location)['path'])]
        if not auths:
            default=Path(os.environ.get('CODEX_HOME',str(Path.home()/'.codex')))/'auth.json'
            if default.is_file(): auths=[default]
        for auth in tuple(auths): auths.extend(sorted(auth.parent.glob('.scan-auth-*.json')))
        secrets=load_secrets(env_files=args.env_file,variables=args.var,auth_files=auths,process_env=True,pii=args.redact_pii)
        launch_key=os.environ.get('TOPOGYM_LAUNCH_KEY')
        if launch_key: secrets['MODEL_API_KEY']=launch_key.encode()
        archive=export_bundle(work,args.run_id,secrets,pii=args.redact_pii)
        bundle=verify_bundle(archive)
        return dict(archive=str(archive),checksum=str(archive)+'.sha256',manifest=str(archive.parent/'MANIFEST.md'),
                    delivery_ready=True,summary=bundle['summary'])
    if args.command in ('verify','import'):
        expected=read_json(args.assignment) if args.assignment else None
        if args.command=='import': return import_bundle(args.archive,work,expected=expected,require_complete=args.require_complete)
        bundle=verify_bundle(args.archive,expected=expected)
        if args.require_complete and not bundle['summary']['evaluation_complete']: raise BundleError('archive valid but evaluation incomplete')
        return dict(bundle,archive_verified=True,expected_assignment_verified=expected is not None)
    if args.command=='upload':
        from helper_upload import upload_bundle
        return upload_bundle(args.archive,work,args)
    raise BundleError('unsupported command')

def main(argv=None):
    os.umask(0o077)
    try:
        args=parser().parse_args(argv); guard()
        result=execute(args)
        print(json.dumps(result,indent=2,sort_keys=True)); return 0
    except (OSError,ValueError,KeyError,TypeError,EOFError,tarfile.TarError,zipfile.BadZipFile) as error:
        # Public exceptions have controlled messages; raw OS/JSON errors can
        # contain credential source paths or document contents.
        from difficulty_hf_auth import HFError
        message=str(error) if isinstance(error,(BundleError,ScanError,HFError)) else type(error).__name__
        print('ERROR: helper operation failed: '+message,file=sys.stderr); return 2
    except KeyboardInterrupt:
        print('Interrupted; source evidence retained',file=sys.stderr); return 130

if __name__=='__main__': raise SystemExit(main())
