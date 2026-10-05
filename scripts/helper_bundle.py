"""Complete helper evidence archives; verification and extraction need stdlib only."""
from __future__ import annotations
from contextlib import contextmanager
from collections import Counter
import fcntl
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import re
import shutil
import subprocess
import tarfile
import tempfile

from helper_assignment import (atomic_json, component, digest, read_json, validate_assignment,
                               validate_manifest, planned_trials, stem, sample_key, utc, COMPLETE)
from secret_scan import files_under, fingerprint, sha, scan_tree, matches, ScanError

FORMAT='topogym-helper-bundle-v1'
RUN_FILES={'manifest.lock.json','source_identity.json','execution.lock.json','controller.json','image.json',
           'cuda-profile.json','helper-runtime.json','mirror.json','run-created.json','environment-check.json',
           'resource-stop.json','resource-usage.json','exit_codes.tsv','setting.effective.yaml','active-job.json'}
RUN_DIRS={'tasks','instances','build','canary','retry-plans'}

class BundleError(ValueError): pass

def guard():
    root=Path('/host/proc') if Path('/host/proc/meminfo').exists() else Path('/proc')
    data={l.split(':')[0]:int(l.split()[1]) for l in (root/'meminfo').read_text().splitlines()}
    if data['MemAvailable'] <= data['MemTotal']*.10:
        raise BundleError('host memory reached 90%; helper operation stopped')

def relpath(value):
    if not isinstance(value,str) or not value or value.startswith('/') or '\\' in value or any(ord(c)<32 for c in value):
        raise BundleError('unsafe archive path')
    path=PurePosixPath(value)
    if '..' in path.parts or '.' in path.parts or str(path)!=value:
        raise BundleError('noncanonical archive path')
    return value

def safe_path(root, relative):
    relpath(relative); root=Path(root)
    if root.is_symlink(): raise BundleError('symlinked root')
    path=root
    for part in PurePosixPath(relative).parts:
        path/=part
        if path.is_symlink(): raise BundleError('symlinked payload')
    return path

@contextmanager
def exclusive(path):
    path=Path(path); path.parent.mkdir(parents=True,exist_ok=True)
    with path.open('a') as stream:
        try: fcntl.flock(stream,fcntl.LOCK_EX|fcntl.LOCK_NB)
        except BlockingIOError: raise BundleError('another process owns this run or delivery') from None
        try: yield
        finally: fcntl.flock(stream,fcntl.LOCK_UN)

def file_id(path):
    guard(); return dict(size=path.stat().st_size,sha256=sha(path))

def refuse_active(work, batch):
    # Offline completed local runs can be exported without Docker. A run that
    # recorded a Docker controller requires proof that its work has stopped.
    run=work/'runs/difficulty_trials'/batch
    if not (run/'controller.json').exists(): return
    filters=['--filter',f'label=topogym.difficulty-run={batch}',
             '--filter','label=topogym.workspace='+hashlib.sha256(str(work).encode()).hexdigest()]
    try:
        p=subprocess.run(['docker','ps','-q',*filters],capture_output=True,text=True,timeout=30)
    except (OSError,subprocess.TimeoutExpired): raise BundleError('cannot prove Docker writers have stopped') from None
    if p.returncode: raise BundleError('cannot inspect active Docker writers')
    own=os.environ.get('TOPOGYM_CONTROLLER','')
    for ident in p.stdout.split():
        q=subprocess.run(['docker','inspect','--format','{{.Name}} {{index .Config.Labels "topogym.role"}}',ident],capture_output=True,text=True,timeout=30)
        if q.returncode: raise BundleError('cannot inspect writer ownership')
        name,role=q.stdout.strip().split(maxsplit=1)
        if name.lstrip('/')!=own or role!='controller': raise BundleError('batch still has active Docker writers')

def copy_payload(src, dst, records):
    if src.is_symlink(): raise BundleError('symlinked evidence cannot be delivered')
    if src.is_dir():
        dst.mkdir(parents=True,exist_ok=True)
        for item in sorted(src.iterdir()): copy_payload(item,dst/item.name,records)
    elif src.is_file():
        if not src.stat().st_mode & 0o444: raise BundleError('unreadable evidence')
        if any(p in {'.codex','.secrets','.ssh'} or p.startswith('.env') for p in src.parts) or src.name=='auth.json':
            raise BundleError('credential file in evidence; refusing to silently omit it')
        before=fingerprint(src); identity=file_id(src)
        dst.parent.mkdir(parents=True,exist_ok=True)
        with src.open('rb') as inp,dst.open('xb') as out:
            while block:=inp.read(1024*1024): guard(); out.write(block)
        if before!=fingerprint(src) or file_id(dst)!=identity: raise BundleError('source changed during evidence copy')
        records[str(src)]=(before,identity)
    else: raise BundleError('unsupported evidence file type')

def collect(root,batch):
    import csv
    from collect_batch_results import collect_manifest
    run=root/'runs/difficulty_trials'/batch; jobs=root/'jobs/difficulty_trials'/batch
    collect_manifest(run/'manifest.lock.json',jobs,copy_artifacts=False)
    rows=[json.loads(l) for l in (run/'trials.jsonl').read_text().splitlines()]
    for row in rows:
        for key in ('job','harbor_trial'):
            if row.get(key): row[key]=Path(row[key]).relative_to(root).as_posix()
    (run/'trials.jsonl').write_text(''.join(json.dumps(r,sort_keys=True)+'\n' for r in rows))
    with (run/'summary.csv').open('w') as stream:
        writer=csv.DictWriter(stream,fieldnames=list(rows[0])); writer.writeheader(); writer.writerows(rows)
    latest={}
    for row in rows: latest[(*sample_key(row),row['mode'])]=row
    counts=Counter(r['status'] for r in latest.values())
    return rows,dict(planned_trials=len(latest),attempts=sum(bool(r['harbor_trial']) or r['status']=='interrupted' for r in rows),
                     completed_trials=sum(v for k,v in counts.items() if k in COMPLETE),
                     evaluation_complete=all(r['status'] in COMPLETE for r in latest.values()),status_counts=dict(counts))

def path_map(root,batch,manifest):
    entries=[]; jobs=root/'jobs/difficulty_trials'/batch; run=root/'runs/difficulty_trials'/batch
    for row,mode in planned_trials(manifest):
        prefix=stem(row,mode); task=run/'tasks'/(row['slug']+('-standard' if mode=='limited' else '-privileged'))
        for job in sorted(jobs.glob(prefix+'-a[0-9][0-9][0-9]')):
            for trial in sorted(p for p in job.iterdir() if p.is_dir()):
                if not (trial/'result.json').exists() and not (trial/'config.json').exists(): continue
                files={p.relative_to(root).as_posix():file_id(p) for p in files_under(task)} if task.is_dir() else {}
                entries.append(dict(trial_id=prefix,job=job.relative_to(root).as_posix(),trial=trial.relative_to(root).as_posix(),
                                    task=task.relative_to(root).as_posix() if task.is_dir() else None,task_files=files))
    return dict(schema_version=1,entries=entries)

def check_payload(root,bundle,expected=None):
    assignment=validate_assignment(read_json(root/'delivery/assignment.json'))
    if expected is not None and assignment!=validate_assignment(expected): raise BundleError('received assignment differs from maintainer assignment')
    if (assignment['assignment_sha256'],assignment['batch'],assignment['helper']['id'])!=(bundle['assignment_sha256'],bundle['batch'],bundle['helper']):
        raise BundleError('bundle assignment identity mismatch')
    run=root/'runs/difficulty_trials'/bundle['batch']
    manifest=validate_manifest(read_json(run/'manifest.lock.json'))
    if manifest!=assignment['manifest']: raise BundleError('run manifest differs from assignment')
    source=read_json(run/'source_identity.json')
    if digest(source['files'])!=source['sha256'] or source['sha256']!=manifest['source_sha256']:
        raise BundleError('source identity mismatch')
    execution=run/'execution.lock.json'
    if execution.exists():
        data=read_json(execution); wanted=assignment['agent']
        for k in ('provider','agent','model','agent_args'):
            if data.get(k)!=wanted[k]: raise BundleError('recorded execution differs from assignment')
        if data.get('auth') not in wanted['auth_methods']: raise BundleError('recorded auth differs from assignment')
    for row in manifest['instances']:
        marker=run/'build'/row['slug']/'prepared.json'
        if marker.exists():
            for rel,expected_sha in read_json(marker)['files'].items():
                path=safe_path(run,rel)
                if not path.is_file() or sha(path)!=expected_sha: raise BundleError('frozen task evidence missing or changed')
    index=read_json(root/'delivery/path-map.json')
    if index!=path_map(root,bundle['batch'],manifest): raise BundleError('path mapping differs from actual assigned jobs')
    prefixes=[stem(row,mode) for row,mode in planned_trials(manifest)]+['canary']
    jobs=root/'jobs/difficulty_trials'/bundle['batch']
    for job in jobs.iterdir():
        if not job.is_dir() or not any(re.fullmatch(re.escape(prefix)+r'-a[0-9]{3}',job.name) for prefix in prefixes):
            raise BundleError('unassigned job in batch evidence')
    for entry in index['entries']:
        safe_path(root,entry['trial']); safe_path(root,entry['job'])
        if not entry['task'] or not entry['task_files'] or not execution.is_file():
            raise BundleError('started trial is missing frozen task/execution evidence')
        sample=next(row for row,mode in planned_trials(manifest) if stem(row,mode)==entry['trial_id'])
        if not (run/'build'/sample['slug']/'prepared.json').is_file():
            raise BundleError('started trial is missing prepared task hashes')
        if entry['task']:
            task=safe_path(root,entry['task'])
            for rel,ident in entry['task_files'].items():
                path=safe_path(root,rel)
                if not path.is_relative_to(task) or not path.is_file() or file_id(path)!=ident:
                    raise BundleError('mapped task identity changed')
    report=read_json(root/'delivery/scan-report.json')
    if report.get('clean') is not True or not report.get('scanned_files'): raise BundleError('missing successful delivery scan')
    return assignment

def human_manifest(bundle,assignment):
    return '\n'.join(['# TopoGym helper delivery','',f"Batch: {bundle['batch']}",f"Helper: {bundle['helper']}",
        f"Bundle: {bundle['bundle_id']}",f"Assignment SHA256: {bundle['assignment_sha256']}",
        f"Created: {bundle['created_at']}",f"Evaluation complete: {bundle['summary']['evaluation_complete']}",
        f"Planned trials: {bundle['summary']['planned_trials']}",f"Completed trials: {bundle['summary']['completed_trials']}",
        'Latest status counts: '+json.dumps(bundle['summary']['status_counts'],sort_keys=True),
        'Agent: '+json.dumps(assignment['agent'],sort_keys=True),
        'Source: '+json.dumps(assignment['source'],sort_keys=True),'',
        'All original jobs and attempts are retained. Text redactions are listed in delivery/redaction-report.json.',
        'Host/software/times/events: delivery/helper_manifest.json and the frozen run metadata.',
        'Upload success does not imply evaluation completion.',''])

def export_bundle(work,batch,secrets,*,pii=False):
    work=Path(work).resolve(); component(batch)
    run=work/'runs/difficulty_trials'/batch
    owner=run.stat() if run.is_dir() else None
    try:
        return _export_bundle(work,batch,secrets,pii=pii)
    finally:
        if owner is not None and os.geteuid()==0:
            # Only our delivery tree changes ownership, never source evidence.
            outgoing=work/'outgoing'; target=outgoing/('upload_'+batch)
            for directory in (outgoing,target):
                if directory.exists() and not directory.is_symlink(): os.chown(directory,owner.st_uid,owner.st_gid)
            if target.is_dir() and not target.is_symlink():
                for path in target.rglob('*'):
                    if not path.is_symlink(): os.chown(path,owner.st_uid,owner.st_gid)


def _export_bundle(work,batch,secrets,*,pii=False):
    work=Path(work).resolve(); component(batch); run=work/'runs/difficulty_trials'/batch
    if not run.is_dir(): raise BundleError('helper run missing')
    with exclusive(run/'.lock'):
        refuse_active(work,batch)
        assignment=validate_assignment(read_json(run/'assignment.json'))
        if assignment['batch']!=batch: raise BundleError('batch mismatch')
        mirror=read_json(run/'mirror.json') if (run/'mirror.json').exists() else {'status':'not_started'}
        jobs=work/'jobs/difficulty_trials'/batch
        if assignment['mirror']=='required' and jobs.is_dir() and any(jobs.iterdir()) and mirror.get('status')!='complete':
            raise BundleError('required mirror is incomplete; retain records and repair collection before exporting')
        outgoing=work/'outgoing'/('upload_'+batch); outgoing.mkdir(parents=True,exist_ok=True)
        staging=Path(tempfile.mkdtemp(prefix='.preparing-',dir=outgoing)); root=staging/'payload'; root.mkdir()
        copied={}; dst_run=root/'runs/difficulty_trials'/batch; dst_run.mkdir(parents=True)
        for item in sorted(run.iterdir()):
            if item.name in RUN_DIRS or item.name in RUN_FILES or item.suffix=='.log' or item.name.startswith('resource-stop.'):
                copy_payload(item,dst_run/item.name,copied)
        for folder in ('jobs/difficulty_trials','jobs/difficulty_trials_mirror'):
            src=work/folder/batch; dst=root/folder/batch
            if src.exists(): copy_payload(src,dst,copied)
            elif folder=='jobs/difficulty_trials': dst.mkdir(parents=True)
        # Only individually referenced controller/environment logs, never all logs.
        references=[]
        runtime=read_json(run/'helper-runtime.json') if (run/'helper-runtime.json').exists() else {}
        for invocation in runtime.get('invocations',[]):
            if invocation.get('controller_log'): references.append(invocation['controller_log'])
        if (run/'environment-check.json').exists():
            check=read_json(run/'environment-check.json')
            if check.get('log'): references.append(check['log'])
        for value in set(references):
            path=Path(value)
            if not path.is_relative_to(work/'logs') or path.is_symlink(): raise BundleError('invalid run log reference')
            if path.is_file(): copy_payload(path,root/path.relative_to(work),copied)
        rows,summary=collect(root,batch)
        atomic_json(root/'delivery/assignment.json',assignment)
        atomic_json(root/'delivery/path-map.json',path_map(root,batch,assignment['manifest']))
        atomic_json(root/'delivery/helper_manifest.json',dict(helper=assignment['helper'],source=assignment['source'],runtime=runtime,
                    mirror=mirror,summary=summary,attempts=rows))
        # Original identity files must remain verifiable. PII redaction is limited
        # to jobs/mirrors so it cannot invalidate the maintainer's assignment.
        pii_redactions=[]
        if pii:
            for folder in ('jobs/difficulty_trials','jobs/difficulty_trials_mirror'):
                target=root/folder/batch
                if target.exists() and any(target.rglob('*')):
                    pii_redactions+=scan_tree(target,secrets,redact=True,pii=True,guard=guard)['redactions']
        first=scan_tree(root,secrets,redact=True,guard=guard)
        report=scan_tree(root,secrets,guard=guard)
        if not report['clean']: raise BundleError('residual credentials; delivery blocked')
        atomic_json(root/'delivery/scan-report.json',report)
        atomic_json(root/'delivery/redaction-report.json',dict(redactions=first['redactions'],pii_redactions=pii_redactions,
                    pii_scope='job and mirror text only' if pii else 'not requested'))
        for src,(before,identity) in copied.items():
            path=Path(src)
            if fingerprint(path)!=before or file_id(path)!=identity: raise BundleError('source changed during export')
        inventory={p.relative_to(root).as_posix():file_id(p) for p in files_under(root)}
        directories=sorted(p.relative_to(root).as_posix() for p in root.rglob('*') if p.is_dir())
        bundle=dict(format=FORMAT,schema_version=1,batch=batch,helper=assignment['helper']['id'],
                    assignment_sha256=assignment['assignment_sha256'],inventory_sha256=digest(inventory),
                    directories=directories,summary=summary,delivery_ready=True,
                    exporter_sha256=sha(Path(__file__)))
        # Time is deliberately outside content identity; identical snapshots can reuse it.
        bundle['bundle_id']=digest(bundle)
        destination=outgoing/bundle['bundle_id']
        if destination.exists():
            archive=next(destination.glob('*.tar.gz'))
            verify_bundle(archive,expected=assignment)
            shutil.rmtree(staging)
            return archive
        bundle['created_at']=utc()
        check_payload(root,bundle,assignment)
        atomic_json(root/'inventory.json',inventory); atomic_json(root/'BUNDLE.json',bundle)
        name=f"{batch}__{assignment['helper']['id']}__{bundle['bundle_id']}.tar.gz"
        result=staging/'sealed'; result.mkdir(); archive=result/name
        with tarfile.open(archive,'w:gz') as tar:
            for path in sorted(root.rglob('*')):
                guard(); tar.add(path,arcname=path.relative_to(root).as_posix(),recursive=False)
        (result/(name+'.sha256')).write_text(sha(archive)+'  '+name+'\n')
        (result/'MANIFEST.md').write_text(human_manifest(bundle,assignment))
        verify_bundle(archive,expected=assignment)
        result.rename(destination)
        shutil.rmtree(staging)
        return destination/name

def verify_bundle(archive,*,expected=None,extract_to=None,max_bytes=1024**4,max_files=1000000):
    archive=Path(archive)
    if archive.is_symlink() or not archive.is_file(): raise BundleError('archive must be a regular file')
    checksum=archive.with_name(archive.name+'.sha256')
    try: fields=checksum.read_text().strip().split()
    except OSError: raise BundleError('archive checksum file missing') from None
    if len(fields)!=2 or fields[1]!=archive.name or not re.fullmatch('[a-f0-9]{64}',fields[0]) or sha(archive)!=fields[0]:
        raise BundleError('archive SHA256 mismatch')
    before=fingerprint(archive)
    temporary=None
    if extract_to is None:
        temporary=tempfile.TemporaryDirectory(prefix='topogym-helper-verify-'); root=Path(temporary.name)
    else:
        root=Path(extract_to)
        if root.exists() and any(root.iterdir()): raise BundleError('extraction destination must be empty')
        root.mkdir(parents=True,exist_ok=True)
    try:
        seen=set(); payload={}; total=0; dirs=set()
        with tarfile.open(archive,'r|gz') as tar:
            for member in tar:
                guard(); name=relpath(member.name)
                if name in seen or len(seen)>=max_files: raise BundleError('duplicate/excess archive members')
                seen.add(name)
                if not member.isfile() and not member.isdir(): raise BundleError('archive links/devices are not supported')
                if member.size<0 or member.mode & 0o7000: raise BundleError('invalid archive metadata')
                total+=member.size
                if total>max_bytes: raise BundleError('archive expanded size limit exceeded')
                path=safe_path(root,name)
                if member.isdir(): path.mkdir(parents=True,exist_ok=True); dirs.add(name); continue
                path.parent.mkdir(parents=True,exist_ok=True)
                h=hashlib.sha256(); count=0
                with tar.extractfile(member) as inp,path.open('xb') as out:
                    while block:=inp.read(1024*1024):
                        guard(); count+=len(block); h.update(block); out.write(block)
                if count!=member.size: raise BundleError('truncated archive member')
                if name not in ('BUNDLE.json','inventory.json'): payload[name]=dict(size=count,sha256=h.hexdigest())
        if fingerprint(archive)!=before: raise BundleError('archive changed while verifying')
        for name in ('BUNDLE.json','inventory.json'):
            if not (root/name).is_file() or (root/name).stat().st_size>64*1024**2: raise BundleError('missing/oversized control metadata')
        bundle=read_json(root/'BUNDLE.json'); inventory=read_json(root/'inventory.json')
        if bundle.get('format')!=FORMAT or bundle.get('schema_version')!=1: raise BundleError('unsupported helper bundle')
        component(bundle['batch']); component(bundle['helper'])
        if bundle.get('bundle_id')!=digest({k:v for k,v in bundle.items() if k not in ('bundle_id','created_at')}):
            raise BundleError('bundle identity mismatch')
        if inventory!=payload or digest(inventory)!=bundle['inventory_sha256'] or dirs!=set(bundle['directories']):
            raise BundleError('payload inventory mismatch')
        assignment=check_payload(root,bundle,expected)
        rows,summary=collect_for_verification(root,bundle['batch'])
        if summary!=bundle['summary']: raise BundleError('summary contradicts raw trial evidence')
        helper_manifest=read_json(root/'delivery/helper_manifest.json')
        if helper_manifest['summary']!=summary or helper_manifest['attempts']!=rows:
            raise BundleError('helper manifest contradicts raw trial evidence')
        human=archive.parent/'MANIFEST.md'
        if not human.is_file() or human.read_text()!=human_manifest(bundle,assignment): raise BundleError('MANIFEST.md does not match archive')
        return bundle
    finally:
        if temporary: temporary.cleanup()

def collect_for_verification(root,batch):
    from collect_batch_results import manifest_rows, load_json
    run=root/'runs/difficulty_trials'/batch
    manifest=read_json(run/'manifest.lock.json')
    rows=manifest_rows(manifest,root/'jobs/difficulty_trials'/batch,run)
    latest={}
    for row in rows:
        if row['harbor_trial']:
            trial=Path(row['harbor_trial']); result=load_json(trial/'result.json'); reward=load_json(trial/'verifier/reward.json')
            recorded=(result.get('verifier_result') or {}).get('rewards') or {}
            if 'success' in recorded and recorded['success']!=reward.get('success'):
                raise BundleError('contradictory verifier rewards')
        for key in ('job','harbor_trial'):
            if row.get(key): row[key]=Path(row[key]).relative_to(root).as_posix()
        latest[(*sample_key(row),row['mode'])]=row
    supplied=[json.loads(line) for line in (run/'trials.jsonl').read_text().splitlines()]
    if rows!=supplied: raise BundleError('trial ledger contradicts raw evidence')
    counts=Counter(r['status'] for r in latest.values())
    return rows,dict(planned_trials=len(latest),attempts=sum(bool(r['harbor_trial']) or r['status']=='interrupted' for r in rows),
                     completed_trials=sum(v for k,v in counts.items() if k in COMPLETE),
                     evaluation_complete=all(r['status'] in COMPLETE for r in latest.values()),status_counts=dict(counts))
