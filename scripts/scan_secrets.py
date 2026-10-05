#!/usr/bin/env python3
"""Scan saved records: 0=clean, 1=residual secrets, 2=incomplete/error.

--redact replaces secrets in text and independently rescans before success.
Binary/compressed hits block redaction. Credential values never enter reports.
"""
import argparse
import json
from pathlib import Path
import sys
import zipfile
from secret_scan import load_env, load_secrets, scan_tree

def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('dir')
    parser.add_argument('--env-file', action='append', default=[])
    parser.add_argument('--var', action='append', default=[])
    parser.add_argument('--codex-auth', action='append', default=[])
    parser.add_argument('--process-env', action='store_true')
    parser.add_argument('--redact', action='store_true')
    parser.add_argument('--report', type=Path)
    args = parser.parse_args(argv)
    try:
        native=[]; target=Path(args.dir).resolve()
        if target.name=='agents':
            from agent_batch_contract import read, validate
            from agent_batch_delivery import verify_tree
            for path in sorted(target.glob('*-plan.json')):
                value=read(path)
                if value.get('format')!='topogym-native-batch-v1': continue
                plan=validate(value)
                # Refuse changing logs under active writers or silently repairing
                # evidence that changed after sealing.
                verify_tree(target.parent,plan); native.append(plan)
        # The fixed manual passes both conventional alternatives even when only
        # one authentication method is used. Missing custom paths remain errors;
        # load_secrets still rejects the case where no credential was loaded.
        skipped=[]
        def present(paths,defaults):
            result=[]
            for value in paths:
                path=Path(value).expanduser()
                if path in defaults and not path.exists(): skipped.append(str(path))
                else: result.append(value)
            return result
        secrets = load_secrets(env_files=present(args.env_file,(Path.home()/'rcb.env',Path.home()/'eai.env')), variables=args.var,
                               auth_files=present(args.codex_auth,(Path.home()/'.codex/auth.json',)), process_env=args.process_env)
        first = scan_tree(args.dir, secrets, redact=args.redact)
        result = scan_tree(args.dir, secrets) if args.redact else first
        result['redactions'] = first['redactions']
        if skipped: result['unused_missing_auth_files']=skipped
        if native:
            mirror=target.with_name('agents_mirror')
            if mirror.exists():
                before=scan_tree(mirror,secrets,redact=args.redact)
                after=scan_tree(mirror,secrets)
                result['mirror']=after; result['mirror']['redactions']=before['redactions']
                result['clean']=result['clean'] and after['clean']
            if args.redact and result['clean']:
                from agent_batch_delivery import seal
                for plan in native: seal(target,plan,secrets)
        if args.report: args.report.write_text(json.dumps(result, indent=2)+'\n')
        print(json.dumps(result, sort_keys=True))
        return 0 if result['clean'] else 1
    except (OSError, ValueError, EOFError, zipfile.BadZipFile):
        print('ERROR: credential scan incomplete; delivery blocked', file=sys.stderr)
        return 2

if __name__ == '__main__': raise SystemExit(main())
