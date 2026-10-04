#!/usr/bin/env python3
"""Scan saved records: 0=clean, 1=residual secrets, 2=incomplete/error.

--redact replaces secrets in text and independently rescans before success.
Binary/compressed hits block redaction. Credential values never enter reports.
"""
import argparse
import json
from pathlib import Path
import sys
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
        secrets = load_secrets(env_files=args.env_file, variables=args.var,
                               auth_files=args.codex_auth, process_env=args.process_env)
        first = scan_tree(args.dir, secrets, redact=args.redact)
        result = scan_tree(args.dir, secrets) if args.redact else first
        result['redactions'] = first['redactions']
        if args.report: args.report.write_text(json.dumps(result, indent=2)+'\n')
        print(json.dumps(result, sort_keys=True))
        return 0 if result['clean'] else 1
    except (OSError, ValueError, EOFError):
        print('ERROR: credential scan incomplete; delivery blocked', file=sys.stderr)
        return 2

if __name__ == '__main__': raise SystemExit(main())
