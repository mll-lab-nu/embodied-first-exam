"""Standard agents/ + agents_mirror/ archives; no GPU, Harbor or credentials required to receive."""
import argparse
import json
from pathlib import Path
import os
import shutil
import tarfile
import tempfile
from urllib.parse import quote
from agent_batch_contract import check_batch, component, files, locked, read, relative, save, sha, validate, write_summary, related_rerun, linked_rerun, TERMINAL
from secret_scan import scan_tree

def selected(jobs,plan):
    jobs=Path(jobs); b=plan['batch']; expected={j['job'] for j in plan['jobs']}
    retry=related_rerun(jobs,plan)
    # Original tar includes all B-* paths; reject ambiguous batch prefixes.
    for path in sorted(jobs.glob(b+'-*')):
        if retry and (path.name.startswith(retry['batch']+'-') or path.name in (retry['batch']+'.log',retry['batch']+'.summary.md')): continue
        if path.is_symlink(): raise ValueError('symlinked batch evidence')
        if path.is_dir():
            if path.name not in expected: raise ValueError('unexpected prefixed job: '+path.name)
            yield from files(path)
        elif path.is_file() and path.name!=b+'-inventory.json': yield path
        elif not path.is_file(): raise ValueError('special batch evidence')
    for name in (b+'.log',b+'.summary.md'):
        path=jobs/name
        if not path.is_file() or path.is_symlink(): raise ValueError('missing/linked '+name)
        yield path
    mirror=jobs.with_name('agents_mirror')
    for path in sorted(mirror.glob(b+'-*')):
        if retry and path.name in {j['job'] for j in retry['jobs']}: continue
        if path.name not in expected or not path.is_dir() or path.is_symlink(): raise ValueError('unexpected mirror job')
        yield from files(path)

def identities(jobs,plan):
    root=Path(jobs).parent
    return {p.relative_to(root).as_posix():dict(sha256=sha(p),bytes=p.stat().st_size) for p in selected(jobs,plan)}

def report_with_mirror(jobs,plan):
    report=check_batch(jobs,plan); errors=[]
    if plan.get('mirror_required'):
        for spec in plan['jobs']:
            if not (jobs/spec['job']).exists(): continue
            marker=jobs/(spec['job']+'-mirror.json'); mirrored=jobs.with_name('agents_mirror')/spec['job']
            if not marker.exists() or read(marker).get('complete') is not True or not mirrored.is_dir():
                errors.append('mirror incomplete: '+spec['job'])
    report['delivery_errors']=errors
    report['delivery_complete']=report['delivery_complete'] and not errors
    return report

def manifest(plan,metadata,report):
    h=metadata.get('host',{})
    lines=[f"# Helper manifest: {plan['batch']}",'',f"Helper: {plan['helper']}",f"Plan SHA-256: {plan['plan_sha256']}",
        f"Trials: {report['observed_trials']}/{report['planned_trials']}; evaluation_complete={report['evaluation_complete']}; delivery_complete={report['delivery_complete']}",
        f"Selection: {plan.get('instance_selection','unspecified')}; K={plan['repetitions']}",
        f"Per-trial agent seconds: {sorted(set(t['agent_timeout_sec'] for t in plan['tasks']))}; token budget: {json.dumps(plan.get('token_budget'))}",
        f"Repository: {json.dumps(metadata.get('repository',{}),ensure_ascii=False)}",f"Agent: {json.dumps(plan['agent'])}",
        f"Started: {metadata.get('started_at','unknown')}; finished: {metadata.get('finished_at','unknown')}",
        f"Lanes started: {len(metadata.get('lanes',[]))}; same-login subscription lanes are serialized.",'', 'Host/software (unknown means collection failed):','']
    lines.extend(f'- {k}: {v}' for k,v in h.items())
    lines+=['','Images (Id is recorded even when RepoDigests is empty):','```json',json.dumps(metadata.get('images',{}),indent=2),'```',
            '', 'Lane/GPU/auth records:', '```json',json.dumps(metadata.get('lanes',[]),indent=2),'```','',
            'Incidents: '+metadata.get('notes','unknown; helper must supply human notes'),
            'Structured stop/error evidence is retained in agents/<batch>-*.json and per-trial records.',
            '', 'Website: deferred by maintainer; this package is for offline review.']
    return '\n'.join(lines)+'\n'

def seal(jobs,plan,secrets):
    jobs=Path(jobs); b=plan['batch']; metadata=read(jobs/(b+'-metadata.json'))
    if any(l['status']=='running' for l in metadata['lanes']): raise ValueError('cannot seal while lanes are running')
    # First redact all deliverable bytes. Raw protected mirrors remain outside this set.
    redactions=[]
    for path in selected_before_summary(jobs,plan):
        result=scan_tree(path,secrets,redact=True)
        redactions.extend(dict(file=path.relative_to(jobs.parent).as_posix(),**r) for r in result['redactions'])
        if not scan_tree(path,secrets)['clean']: raise ValueError('credential scan failed')
    write_summary(jobs,plan)
    report=report_with_mirror(jobs,plan); save(jobs/(b+'-verdicts.json'),report)
    (jobs/(b+'-MANIFEST.md')).write_text(manifest(plan,metadata,report))
    save(jobs/(b+'-scan.json'),dict(clean=True,redactions=redactions,coverage='all archived regular files and mirror history'))
    for path in selected(jobs,plan):
        if not scan_tree(path,secrets)['clean']: raise ValueError('secret remains in final delivery')
    save(jobs/(b+'-inventory.json'),dict(schema_version=1,plan_sha256=plan['plan_sha256'],files=identities(jobs,plan)))
    return report

def selected_before_summary(jobs,plan):
    # Empty and interrupted batches still get the same summary/log contract.
    for suffix in ('.log','.summary.md'):
        path=jobs/(plan['batch']+suffix)
        if not path.exists(): path.touch()
    return selected(jobs,plan)

def verify_tree(root,expected):
    root=Path(root); validate(expected); jobs=root/'agents'; b=expected['batch']
    if read(jobs/(b+'-plan.json'))!=expected: raise ValueError('received plan differs from maintainer original')
    inv=read(jobs/(b+'-inventory.json'))
    if inv.get('schema_version')!=1 or inv.get('plan_sha256')!=expected['plan_sha256']: raise ValueError('inventory identity mismatch')
    if identities(jobs,expected)!=inv['files']: raise ValueError('archive file set/content differs from sealed inventory')
    metadata=read(jobs/(b+'-metadata.json'))
    if metadata.get('plan_sha256')!=expected['plan_sha256'] or any(l['status']=='running' for l in metadata['lanes']):
        raise ValueError('batch metadata identity or lifecycle incomplete')
    report=report_with_mirror(jobs,expected)
    if read(jobs/(b+'-verdicts.json'))!=report: raise ValueError('received verdict report differs from raw trial records')
    return report

def unpack(archive,dest,expected,*,reruns=(),max_bytes=1024**4,max_files=1000000):
    """Streaming extraction rejects links/devices/duplicates/traversal before writing."""
    archive=Path(archive); dest=Path(dest)
    checksum=archive.with_name(archive.name+'.sha256').read_text().strip().split()
    if len(checksum)!=2 or checksum[1].lstrip('*')!=archive.name or checksum[0]!=sha(archive): raise ValueError('archive checksum mismatch')
    allowed={'agents','agents_mirror'}; seen=set(); total=0
    with tarfile.open(archive,'r|gz') as tar:
        for member in tar:
            name=member.name.rstrip('/') if member.isdir() else member.name
            rel=relative(name)
            if rel.parts[0] not in allowed or name in seen or not (member.isfile() or member.isdir()): raise ValueError('unsafe/duplicate archive member')
            seen.add(name); total+=member.size
            if len(seen)>max_files or total>max_bytes or member.size<0: raise ValueError('archive exceeds limits')
            path=dest/rel
            if member.isdir(): path.mkdir(parents=True,exist_ok=True); continue
            path.parent.mkdir(parents=True,exist_ok=True)
            with tar.extractfile(member) as inp,path.open('xb') as out: shutil.copyfileobj(inp,out,1024*1024)
    # No untracked file can hide outside the B-* selection in the tar.
    plans=[expected,*[linked_rerun(expected,r) for r in reruns]]; expected_files=set(); reports=[]
    for plan in plans:
        b=plan['batch']; inv=read(dest/'agents'/(b+'-inventory.json'))
        expected_files.update(inv['files']); expected_files.add('agents/'+b+'-inventory.json')
        reports.append(verify_tree(dest,plan))
    all_files={p.relative_to(dest).as_posix() for p in files(dest)}
    if all_files != expected_files: raise ValueError('unlisted archive files or unauthorized rerun; supply maintainer rerun assignment')
    return combined(reports,plans)

def combined(reports,plans):
    report=dict(reports[0])
    if len(plans)==1: return report
    replacements={}
    for child,result in zip(plans[1:],reports[1:]):
        for spec in child['jobs']:
            original=[r for r in child['rerun']['trials'] if r['task']==spec['task']]
            rows=[r for r in result['rows'] if r['job']==spec['job']]
            for before,after in zip(original,rows): replacements[(before['job'],before['repetition'])]=after
    covered=[]
    for row in report['rows']:
        after=row if row['status'] in TERMINAL else replacements.get((row['job'],row['repetition']),row)
        covered.append(after['status'] in TERMINAL and not after['missing_artifacts'])
    report['rerun_reports']=reports[1:]
    report['delivery_complete']=all(covered) and not any(r['errors'] or r['delivery_errors'] for r in reports)
    report['original_evaluation_complete']=report['evaluation_complete']
    report['evaluation_complete']=not any(r['errors'] for r in reports) and all((row if row['status'] in TERMINAL else replacements.get((row['job'],row['repetition']),row))['status'] in TERMINAL for row in report['rows'])
    return report

def review(root,plan,report,*,output=None):
    out=output or root/'review'; out.mkdir(parents=True)
    lines=[f"# {plan['batch']}",'',f"Evaluation complete: {report['evaluation_complete']}; delivery complete: {report['delivery_complete']}",'',
           '| Task | Repeat | Status | Evidence |','|---|---:|---|---|']
    for i,row in enumerate(report['rows']):
        page=f'trial-{i+1:04d}.md'; body=[f"# {row['task']} / {row['repetition']}",'',f"Status: {row['status']}",'']
        if 'token_usage' in row:
            body += [f"Score: {row.get('success')}; raw verifier score: {row.get('raw_success')}",
                     f"Tokens: {json.dumps(row['token_usage'])}; over_token_budget: {row.get('over_token_budget')}",'']
        if row['trial']:
            for p in files(root/'agents'/row['trial']):
                rel=os.path.relpath(p,out); body.append(f'- [{p.relative_to(root/"agents"/row["trial"])}]({quote(rel)})')
            mirror=root/'agents_mirror'/row['trial']
            if mirror.is_dir():
                body+=['','Mirror history:','']
                body.extend(f'- [{p.name}]({quote(os.path.relpath(p,out))})' for p in files(mirror))
        (out/page).write_text('\n'.join(body)+'\n')
        lines.append(f"| {row['task']} | {row['repetition']} | {row['status']} | [review]({page}) |")
    (out/'README.md').write_text('\n'.join(lines)+'\n')

def receive(archive,expected,destination,*,require_complete=False,reruns=()):
    destination=Path(destination); destination.parent.mkdir(parents=True,exist_ok=True)
    value=sha(Path(archive))
    with locked(destination.parent/('.'+destination.name+'.receive.lock')):
        if destination.exists():
            receipt=read(destination/'receipt.json')
            if receipt['archive_sha256']!=value or receipt['plan_sha256']!=expected['plan_sha256']: raise ValueError('destination contains a different receipt')
            if receipt.get('rerun_plan_sha256',[])!=[p['plan_sha256'] for p in reruns]: raise ValueError('supply the original rerun authorizations')
            plans=[expected,*reruns]; report=combined([verify_tree(destination,p) for p in plans],plans)
            if require_complete and not report['delivery_complete']: raise ValueError('batch incomplete')
            return receipt
        with tempfile.TemporaryDirectory(prefix='.receive-',dir=destination.parent) as td:
            stage=Path(td)/'jobs'; stage.mkdir(); report=unpack(archive,stage,expected,reruns=reruns)
            if require_complete and not report['delivery_complete']: raise ValueError('batch incomplete; import without --require-complete to retain partial evidence')
            review(stage,expected,report)
            for child,child_plan in zip(report.get('rerun_reports',[]),reruns):
                # Keep every additional attempt browsable without replacing originals.
                child_out=stage/'review'/child['batch']; review(stage,child_plan,child,output=child_out)
                with (stage/'review/README.md').open('a') as stream:
                    stream.write(f"\nAuthorized additional attempts: [{child['batch']}]({child['batch']}/README.md)\n")
            receipt=dict(schema_version=1,archive_sha256=value,plan_sha256=expected['plan_sha256'],rerun_plan_sha256=[p['plan_sha256'] for p in reruns],report=report)
            save(stage/'receipt.json',receipt); stage.rename(destination)
    return receipt

def bind_tasks(destination,plan,tasks_root):
    from agent_batch_contract import package
    tasks_root=Path(tasks_root).resolve()
    mapping={task['name']:str(package(tasks_root.parent,task)) for task in plan['tasks']}
    save(Path(destination)/'local-task-map.json',dict(plan_sha256=plan['plan_sha256'],tasks=mapping))

def main():
    p=argparse.ArgumentParser(description=__doc__); sub=p.add_subparsers(dest='command',required=True)
    for name in ('verify','import'):
        q=sub.add_parser(name); q.add_argument('--archive',type=Path,required=True); q.add_argument('--assignment',type=Path,required=True)
        q.add_argument('--rerun-assignment',type=Path,action='append',default=[])
        q.add_argument('--require-complete',action='store_true')
        if name=='import':
            q.add_argument('--destination',type=Path,required=True)
            q.add_argument('--tasks-root',type=Path,help='optional checkout tasks/ for regrading; offline review does not need it')
    a=p.parse_args()
    try:
        plan=validate(read(a.assignment))
        retries=[linked_rerun(plan,read(path)) for path in a.rerun_assignment]
        if a.command=='import':
            result=receive(a.archive,plan,a.destination,require_complete=a.require_complete,reruns=retries)
            if a.tasks_root: bind_tasks(a.destination,plan,a.tasks_root)
        else:
            with tempfile.TemporaryDirectory(prefix='topogym-verify-') as td: result=unpack(a.archive,Path(td),plan,reruns=retries)
            if a.require_complete and not result['delivery_complete']: raise ValueError('batch incomplete')
        print(json.dumps(result,indent=2)); return 0
    except (OSError,ValueError,KeyError,TypeError,tarfile.TarError) as e: p.exit(2,'Delivery rejected: '+str(e)+'\n')

if __name__=='__main__': raise SystemExit(main())
