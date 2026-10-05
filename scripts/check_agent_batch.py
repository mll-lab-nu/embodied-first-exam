#!/usr/bin/env python3
"""Check every planned native Harbor trial, including missing jobs and K repeats."""
import argparse
import json
from pathlib import Path
from agent_batch_contract import read, check_batch, write_summary
from agent_batch_delivery import report_with_mirror

def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--jobs', type=Path, required=True); p.add_argument('--batch', required=True)
    p.add_argument('--assignment', type=Path); p.add_argument('--require-complete', action='store_true')
    p.add_argument('--write-summary', action='store_true')
    a=p.parse_args()
    try:
        plan=read(a.jobs/(a.batch+'-plan.json'))
        if plan['batch'] != a.batch: raise ValueError('batch identity mismatch')
        if a.assignment and read(a.assignment)!=plan: raise ValueError('received plan differs from maintainer assignment')
        if a.write_summary:
            if (a.jobs/(a.batch+'-inventory.json')).exists(): raise ValueError('sealed summary is immutable; use finish_agent_batch for explicit resealing')
            write_summary(a.jobs,plan)
        report=report_with_mirror(a.jobs,plan)
        print(json.dumps(report,indent=2))
        return 1 if a.require_complete and not report['delivery_complete'] else 0
    except (ValueError,OSError,KeyError,TypeError) as e:
        p.exit(2, 'Cannot verify batch: '+str(e)+'\n')

if __name__=='__main__': raise SystemExit(main())
