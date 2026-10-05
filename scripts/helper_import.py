"""Receive helper evidence without executing bundled code or requiring a GPU."""
from __future__ import annotations
import json
import html
import os
from pathlib import Path
import shutil
import tempfile
from urllib.parse import quote
from helper_assignment import read_json, atomic_json, utc, COMPLETE
from helper_bundle import (verify_bundle, safe_path, file_id, BundleError, exclusive,
                           path_map, collect_for_verification)

def build_reports(payload,reports,bundle):
    """Links point to preserved files; no code or model log is interpreted as HTML."""
    reports.mkdir(parents=True,exist_ok=True)
    batch=bundle['batch']; run=payload/'runs/difficulty_trials'/batch
    rows=[json.loads(l) for l in (run/'trials.jsonl').read_text().splitlines()]
    inventory=read_json(payload/'inventory.json')
    lines=['# Helper acceptance report','',f'Batch: `{batch}`',f"Bundle: `{bundle['bundle_id']}`",'',
           'Archive integrity: verified',f"Evaluation complete: **{bundle['summary']['evaluation_complete']}**",'',
           '| Task | Difficulty | Sample | Mode | Attempt | Status | Evidence |','|---|---|---|---|---|---|---|']
    for index,row in enumerate(rows,1):
        page=reports/'trials'/f'{index:05d}.md'; page.parent.mkdir(exist_ok=True)
        prefix=row['job']+'/'
        files=[rel for rel in inventory if rel.startswith(prefix)]
        detail=[f"# {row['task_id']} {row['difficulty']} {row['mode']}",'',
                f"Attempt: {row['attempt']}; status: **{row['status']}**",'',
                'These are received records. No agent code or simulator was executed during import.','']
        for rel in sorted(files):
            target=os.path.relpath(payload/rel,page.parent)
            label=html.escape(rel.removeprefix(prefix)).replace('[','\\[').replace(']','\\]')
            detail.append(f'- [{label}]({quote(target,safe="/._-")})')
        if not files: detail.append('No job files were produced for this planned trial.')
        page.write_text('\n'.join(detail)+'\n')
        lines.append(f"| {row['task_id']} | {row['difficulty']} | {row['sample_id']} | {row['mode']} | {row['attempt']} | {row['status']} | [files](trials/{index:05d}.md) |")
    lines+=['','All attempts remain available; partial/infra records do not imply a completed evaluation.',
            '[File inventory](../payload/inventory.json) · [Host and execution manifest](../payload/delivery/helper_manifest.json)',
            '[Path mapping](../payload/delivery/path-map.json) · [Redactions](../payload/delivery/redaction-report.json)','']
    (reports/'README.md').write_text('\n'.join(lines))
    # A neutral descriptor for site adapters; raw job/task names are unchanged.
    atomic_json(reports/'site-input.json',dict(schema_version=1,batch=batch,bundle_id=bundle['bundle_id'],
                payload='../payload',jobs=f'../payload/jobs/difficulty_trials/{batch}',
                path_map='../payload/delivery/path-map.json',trials=rows,summary=bundle['summary']))

def import_bundle(archive,work,*,expected=None,require_complete=False):
    work=Path(work).resolve(); incoming=work/'imports'; incoming.mkdir(parents=True,exist_ok=True)
    with exclusive(incoming/'.lock'):
        stage=Path(tempfile.mkdtemp(prefix='.import-',dir=incoming)); payload=stage/'payload'
        try:
            bundle=verify_bundle(archive,expected=expected,extract_to=payload)
            if require_complete and not bundle['summary']['evaluation_complete']:
                raise BundleError('archive valid but evaluation incomplete; retry without --require-complete to receive partial evidence')
            batch=incoming/bundle['batch']; batch.mkdir(exist_ok=True)
            destination=batch/bundle['bundle_id']
            index_path=batch/'index.json'
            index=read_json(index_path) if index_path.exists() else dict(schema_version=1,assignment_sha256=bundle['assignment_sha256'],bundles={},terminal_files={})
            if index['assignment_sha256']!=bundle['assignment_sha256']: raise BundleError('batch already belongs to another assignment')
            inventory=read_json(payload/'inventory.json')
            for rel,ident in index['terminal_files'].items():
                if inventory.get(rel)!=ident: raise BundleError('new delivery changes or omits previously accepted terminal evidence')
            if destination.exists():
                # Compare the existing payload too: an earlier receipt is not proof
                # that local imported files have remained intact.
                for rel,ident in inventory.items():
                    p=safe_path(destination/'payload',rel)
                    if not p.is_file() or file_id(p)!=ident: raise BundleError('previously imported payload changed')
                if read_json(destination/'payload/BUNDLE.json')!=bundle or read_json(destination/'payload/inventory.json')!=inventory:
                    raise BundleError('previously imported control metadata changed')
                receipt=read_json(destination/'receipt.json')
                if expected is not None and not receipt['expected_assignment_verified']:
                    receipt['expected_assignment_verified']=True
                    atomic_json(destination/'receipt.json',receipt)
            else:
                build_reports(payload,stage/'reports',bundle)
                receipt=dict(schema_version=1,batch=bundle['batch'],bundle_id=bundle['bundle_id'],import_complete=True,
                             expected_assignment_verified=expected is not None,accepted_at=utc(),summary=bundle['summary'],
                             directory=str(destination),report=str(destination/'reports/README.md'),
                             site_adapter_status='descriptor_ready; external review-site integration not verified')
                atomic_json(stage/'receipt.json',receipt)
                stage.rename(destination)
            rows=[json.loads(l) for l in (destination/'payload/runs/difficulty_trials'/bundle['batch']/'trials.jsonl').read_text().splitlines()]
            for row in rows:
                if row['status'] in COMPLETE:
                    index['terminal_files'].update({rel:ident for rel,ident in inventory.items() if rel.startswith(row['job']+'/')})
            index['bundles'][bundle['bundle_id']]=dict(imported_at=receipt['accepted_at'],summary=bundle['summary'])
            atomic_json(index_path,index)
            return receipt
        finally:
            if stage.exists(): shutil.rmtree(stage)
