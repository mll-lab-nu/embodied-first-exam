"""Portable native batch plans and verdicts. Offline readers use only stdlib."""
from __future__ import annotations
from collections import Counter
import copy
from contextlib import contextmanager
import fcntl
import hashlib
import json
import os
from pathlib import Path
import re
import tempfile
import struct
import zlib

FORMAT = 'topogym-native-batch-v1'
# Terminal execution may still need a human verdict; it must not trigger a rerun.
TERMINAL = {'solved', 'unsolved', 'pending_review', 'invalid_submission', 'over_token_budget'}


def validate_token_budget(budget):
    if (not isinstance(budget, dict) or set(budget) != {'input_tokens', 'output_tokens', 'enforcement'}
            or budget['enforcement'] != 'post_run_score'
            or any(type(budget[k]) is not int or budget[k] <= 0 for k in ('input_tokens', 'output_tokens'))):
        raise ValueError('token budget needs positive input/output counts and post_run_score enforcement')
    return budget


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(',', ':'), allow_nan=False).encode()).hexdigest()


def sha(path):
    h = hashlib.sha256()
    with Path(path).open('rb') as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b''): h.update(block)
    return h.hexdigest()


def read(path):
    with Path(path).open() as stream: return json.load(stream)


def save(path, value):
    path = Path(path); path.parent.mkdir(parents=True, exist_ok=True)
    fd, name = tempfile.mkstemp(prefix='.batch-', dir=path.parent)
    try:
        with os.fdopen(fd, 'w') as stream:
            json.dump(value, stream, indent=2, sort_keys=True, allow_nan=False); stream.write('\n')
        os.replace(name, path)
    finally:
        if os.path.exists(name): os.unlink(name)


def component(value):
    if not isinstance(value, str) or not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_-]{0,199}', value):
        raise ValueError('invalid batch/task component')
    return value


def relative(value):
    p = Path(value)
    if not value or p.is_absolute() or p.as_posix() != value or '..' in p.parts or '\\' in value or any(ord(c) < 32 for c in value):
        raise ValueError('invalid relative evidence path')
    return p


def files(root):
    root = Path(root)
    if root.is_symlink() or not root.is_dir(): raise ValueError('missing/symlinked evidence root')
    for p in sorted(root.rglob('*')):
        if p.is_symlink() or (not p.is_file() and not p.is_dir()): raise ValueError('links/special files in evidence')
        if p.is_file(): yield p


def inventory(root):
    return {p.relative_to(root).as_posix(): sha(p) for p in files(root)}


@contextmanager
def locked(path, *, blocking=True):
    path = Path(path); path.parent.mkdir(parents=True, exist_ok=True)
    with path.open('a') as stream:
        try: fcntl.flock(stream, fcntl.LOCK_EX | (0 if blocking else fcntl.LOCK_NB))
        except BlockingIOError: raise ValueError('another process owns this batch/login operation') from None
        try: yield stream
        finally: fcntl.flock(stream, fcntl.LOCK_UN)


def validate(plan):
    if plan.get('format') != FORMAT or plan.get('schema_version') != 1: raise ValueError('unsupported native batch plan')
    if plan.get('plan_sha256') != digest({k: v for k, v in plan.items() if k != 'plan_sha256'}): raise ValueError('batch plan changed')
    component(plan['batch']); component(plan['helper'])
    if type(plan.get('helper_selects_model',False)) is not bool: raise ValueError('helper_selects_model must be boolean')
    if plan.get('helper_selects_model') and plan['agent']['name']!='codex':
        raise ValueError('helper model selection currently requires the Codex runner')
    if 'assignment_sha256' in plan:
        if not plan.get('helper_selects_model') or not re.fullmatch('[a-f0-9]{64}',plan['assignment_sha256']):
            raise ValueError('invalid model selection assignment binding')
    if 'token_budget' in plan: validate_token_budget(plan['token_budget'])
    k = plan['repetitions']
    if type(k) is not int or not 1 <= k <= 10000: raise ValueError('invalid repetition count')
    names = set(); bases = set()
    for task in plan['tasks']:
        name = component(task['name']); mode = task['mode']; base = component(task['base'])
        if mode not in ('privileged', 'standard') or name != base + '-' + mode or name in names: raise ValueError('duplicate/invalid task selection')
        names.add(name); bases.add(base)
        if not task['files'] or task['package_sha256'] != digest(task['files']): raise ValueError('invalid package digest')
        for rel, h in task['files'].items():
            relative(rel)
            if not re.fullmatch('[a-f0-9]{64}', h): raise ValueError('invalid package file hash')
        if task['agent_timeout_sec'] <= 0: raise ValueError('invalid agent budget')
    if not names or sorted(bases) != sorted(plan['task_bases']): raise ValueError('invalid task bases')
    retry=plan.get('rerun')
    counts=Counter(row['task'] for row in retry['trials']) if retry else {}
    expected = [dict(job=plan['batch']+'-'+t['mode']+'-'+t['base'], task=t['name'], repetitions=counts[t['name']] if retry else k) for t in plan['tasks']]
    if plan['jobs'] != expected or plan['trial_count'] != sum(j['repetitions'] for j in expected): raise ValueError('invalid job/trial plan')
    for job in expected: component(job['job'])
    if retry:
        if plan['batch']!=component(retry['batch'])+'-rerun' or not re.fullmatch('[a-f0-9]{64}',retry['plan_sha256']): raise ValueError('invalid rerun parent')
        ids=[(row['job'],row['repetition']) for row in retry['trials']]
        if len(ids)!=len(set(ids)) or set(counts)!=names or any(type(n) is not int or n<1 for _,n in ids): raise ValueError('invalid rerun mapping')
    if plan['agent']['name'] not in ('codex', 'claude-code'): raise ValueError('native Harbor agents required')
    if not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_./:-]+', plan['agent']['model']): raise ValueError('invalid model')
    if any(not re.fullmatch(r'[a-z_]+', k) or not re.fullmatch(r'[A-Za-z0-9_.,-]+', str(v)) for k,v in plan['agent']['kwargs'].items()):
        raise ValueError('invalid agent options')
    target = plan['upload']
    if target['type'] == 'hf':
        if not re.fullmatch(r'[A-Za-z0-9_-]+/[A-Za-z0-9_.-]+', target['repo_id']) or '..' in target['repo_id']: raise ValueError('invalid HF target')
        if target['prefix'] != f"helpers/{plan['helper']}/{plan['batch']}": raise ValueError('HF prefix differs from dispatch')
    elif target['type'] != 'shared-folder': raise ValueError('unsupported delivery target')
    if 'image_sources' in plan:
        from agent_batch_images import references, validate_sources
        validate_sources(plan['image_sources'],references(plan))
    return plan


def select_agent(assignment, *, model=None, effort=None, agent=None):
    """Resolve only the model/effort explicitly delegated by the maintainer."""
    validate(assignment)
    selected=copy.deepcopy(assignment['agent'])
    if agent is not None and agent!=selected['name']: raise ValueError('AGENT differs from dispatch')
    if model is not None: selected['model']=model
    if effort is not None:
        if effort=='default': selected['kwargs'].pop('reasoning_effort',None)
        else: selected['kwargs']['reasoning_effort']=effort
    if selected==assignment['agent']: return assignment
    if not assignment.get('helper_selects_model') or 'assignment_sha256' in assignment or assignment.get('rerun'):
        raise ValueError('model/effort are fixed for this assignment')
    if not selected['model'].startswith('openai/'):
        raise ValueError('helper model selection currently supports Codex openai/ models')
    if selected['kwargs'].get('reasoning_effort','default') not in ('none','minimal','low','medium','high','xhigh','max','default'):
        raise ValueError('invalid reasoning effort')
    plan=copy.deepcopy(assignment); plan.pop('plan_sha256')
    plan.update(agent=selected,assignment_sha256=assignment['plan_sha256'])
    plan['plan_sha256']=digest(plan)
    return validate(plan)


def match_assignment(expected, actual):
    """Verify the recorded choice against the trusted assignment, without relaxing task/budget hashes."""
    validate(expected); validate(actual)
    if expected==actual: return actual
    candidate=select_agent(expected,agent=actual['agent']['name'],model=actual['agent']['model'],
                           effort=actual['agent']['kwargs'].get('reasoning_effort','default'))
    if candidate!=actual: raise ValueError('received plan differs from maintainer original or authorized model selection')
    return actual

def linked_rerun(parent,child):
    validate(parent); validate(child)
    if parent.get('helper_selects_model') and 'assignment_sha256' not in parent:
        parent=select_agent(parent,model=child['agent']['model'],effort=child['agent']['kwargs'].get('reasoning_effort','default'))
    retry=child.get('rerun') or {}
    if retry.get('batch')!=parent['batch'] or retry.get('plan_sha256')!=parent['plan_sha256'] or parent.get('rerun'):
        raise ValueError('rerun is not bound to this original batch')
    originals={t['name']:t for t in parent['tasks']}; jobs={j['job']:j for j in parent['jobs']}
    if (any(t!=originals.get(t['name']) for t in child['tasks']) or child['agent']!=parent['agent']
            or child.get('token_budget')!=parent.get('token_budget')): raise ValueError('rerun changed experiment settings')
    for row in retry['trials']:
        job=jobs.get(row['job'])
        if not job or row['task']!=job['task'] or not 1<=row['repetition']<=job['repetitions']: raise ValueError('rerun refers to an unplanned trial')
    return child

def related_rerun(jobs,plan):
    path=Path(jobs)/(plan['batch']+'-rerun-plan.json')
    return linked_rerun(plan,read(path)) if not plan.get('rerun') and path.exists() else None


def package(root, task):
    path = Path(root)/'tasks'/task['name']
    if inventory(path) != task['files']: raise ValueError('published task package changed: '+task['name'])
    return path

def media_container_valid(path):
    """Cheap offline corruption check, not visual/physics or full-frame qualification."""
    path=Path(path); size=path.stat().st_size
    with path.open('rb') as stream:
        if path.suffix=='.png':
            if stream.read(8)!=b'\x89PNG\r\n\x1a\n': return False
            seen_header=seen_data=False
            while stream.tell()<size:
                header=stream.read(8)
                if len(header)!=8: return False
                length,kind=struct.unpack('>I4s',header)
                if length>size-stream.tell()-4: return False
                if not seen_header and (kind!=b'IHDR' or length!=13): return False
                crc=zlib.crc32(kind); remaining=length
                while remaining:
                    data=stream.read(min(remaining,1024*1024))
                    if not data: return False
                    if kind==b'IHDR':
                        if len(data)!=13 or not all(struct.unpack('>II',data[:8])): return False
                        seen_header=True
                    crc=zlib.crc32(data,crc); remaining-=len(data)
                trailer=stream.read(4)
                if len(trailer)!=4 or crc!=struct.unpack('>I',trailer)[0]: return False
                if kind==b'IDAT': seen_data=True
                if kind==b'IEND': return seen_header and seen_data and length==0 and stream.tell()==size
            return False
        if path.suffix=='.mp4':
            boxes=set(); offset=0
            while offset<size:
                stream.seek(offset); header=stream.read(8)
                if len(header)!=8: return False
                length,kind=struct.unpack('>I4s',header); minimum=8
                if length==1:
                    extra=stream.read(8)
                    if len(extra)!=8: return False
                    length=struct.unpack('>Q',extra)[0]; minimum=16
                elif length==0: length=size-offset
                if length<minimum or offset+length>size: return False
                if kind in (b'ftyp',b'moov',b'mdat') and length==minimum: return False
                boxes.add(kind); offset+=length
            return {b'ftyp',b'moov',b'mdat'}<=boxes
    return size>0


def trial_verdict(trial, task, agent=None):
    """Return explicit invalid states; never infer completion from job/result.json."""
    trial = Path(trial)
    result = read(trial/'result.json')
    if Path(result.get('task_name', '')).name != task['name']: return 'identity_mismatch', {}, []
    if result.get('task_checksum') != task['harbor_checksum']: return 'identity_mismatch', {}, []
    if not result.get('finished_at'): return 'interrupted', {}, []
    from account_failure_check import check
    if check(str(trial))['stop']: return 'infra_failed', {}, []
    exc = (result.get('exception_info') or {}).get('exception_type')
    if exc and exc not in ('AgentTimeout', 'AgentTimeoutError'): return 'infra_failed', {}, []
    reward = read(trial/'verifier/reward.json')
    if type(reward.get('success')) not in (int, float) or reward['success'] not in (0, 1): return 'invalid_verdict', reward, []
    pending_review = reward.get('success_pending_review') == 1
    if pending_review and reward['success'] != 0: return 'invalid_verdict', reward, []
    recorded = (result.get('verifier_result') or {}).get('rewards') or {}
    # Harbor records reward.txt as `reward`; some versions retain numeric JSON fields.
    score = recorded.get('success', recorded.get('reward'))
    if score != reward['success']: return 'verdict_mismatch', reward, []
    for key in recorded.keys() & reward.keys():
        if recorded[key] != reward[key]: return 'verdict_mismatch', reward, []
    if any(reward.get(k) for k in ('infra_error','grader_error','gpu_lost','missing_log')): return 'infra_failed', reward, []
    if reward.get('instance_mismatch'): return 'not_evaluable', reward, []
    cfg = read(trial/'config.json')
    for key in ('timeout_multiplier','agent_timeout_multiplier','verifier_timeout_multiplier'):
        if cfg.get(key, 1) not in (None,1): return 'identity_mismatch', reward, []
    config_task = cfg.get('task') or {}
    if Path(config_task.get('path', '')).name != task['name']: return 'identity_mismatch', reward, []
    if agent:
        acfg = cfg.get('agent') or {}
        if acfg.get('name') != agent['name'] or acfg.get('model_name') != agent['model']: return 'identity_mismatch', reward, []
        kwargs = acfg.get('kwargs') or {}
        if any(str(kwargs.get(k)) != str(v) for k,v in agent['kwargs'].items()): return 'identity_mismatch', reward, []
        if acfg.get('override_timeout_sec') not in (None, task['agent_timeout_sec']): return 'identity_mismatch', reward, []
        if acfg.get('max_timeout_sec') is not None: return 'identity_mismatch', reward, []
    invalid = any(reward.get(k) for k in ('missing_trajectory','bad_trajectory','wrong_family'))
    if invalid: return 'invalid_submission', reward, []
    if task['mode'] == 'standard' and reward.get('finalized') != 1: return 'infra_failed', reward, []
    if reward.get('runtime_binding_ok') != 1: return 'not_evaluable', reward, []
    required = ['verifier/replay.verdict.json','verifier/startup_binding.json'] if task['mode']=='standard' else ['verifier/verdict.json']
    for rel in required:
        proof = read(trial/rel)
        if task['mode'] == 'privileged':
            if proof.get('reward') != reward or proof.get('success') != bool(reward['success']): return 'verdict_mismatch', reward, []
            proof = dict(proof.get('evidence') or {}, instance_exact=reward.get('instance_exact') == 1)
        ident = (proof.get('runtime_binding') or {}).get('binding_id')
        if ident != task['binding_id'] or proof.get('instance_exact') is not True: return 'identity_mismatch', reward, []
    missing = []
    if reward['success'] == 1:
        missing = [rel for rel in task.get('success_artifacts', ['verifier/replay.mp4']) if not (trial/rel).is_file() or not (trial/rel).stat().st_size]
        missing += [rel+' (invalid media container)' for rel in task.get('success_artifacts',[]) if rel not in missing and not media_container_valid(trial/rel)]
    status = 'pending_review' if pending_review else ('solved' if reward['success']==1 else 'unsolved')
    return status, reward, missing


def check_batch(jobs, plan):
    validate(plan); jobs = Path(jobs); tasks = {t['name']:t for t in plan['tasks']}
    rows = []; errors = []; expected_jobs = {j['job'] for j in plan['jobs']}
    rerun=related_rerun(jobs,plan)
    related_jobs={j['job'] for j in rerun['jobs']} if rerun else set()
    # Sidecar files are deliberately ignored; unknown prefixed directories are not.
    for path in jobs.glob(plan['batch']+'-*'):
        if path.is_dir() and path.name not in expected_jobs | related_jobs:
            errors.append('unexpected job: '+path.name)
    for spec in plan['jobs']:
        job = jobs/spec['job']; found = sorted(p for p in job.iterdir() if p.is_dir()) if job.is_dir() else []
        found = [p for p in found if (p/'config.json').exists() or (p/'result.json').exists() or '__' in p.name]
        if len(found)>spec['repetitions']: errors.append('extra trials: '+spec['job'])
        for i in range(max(len(found), spec['repetitions'])):
            row = dict(job=spec['job'], task=spec['task'], repetition=i+1, trial=None, status='pending', missing_artifacts=[])
            if i < len(found):
                trial = found[i]; row['trial'] = trial.relative_to(jobs).as_posix()
                try:
                    status, reward, missing = trial_verdict(trial, tasks[spec['task']], plan['agent'])
                    row.update(status=status, success=reward.get('success'), missing_artifacts=missing)
                    if status == 'pending_review':
                        row.update(success=None, raw_success=reward['success'], success_pending_review=True)
                    if status in TERMINAL and 'token_budget' in plan:
                        usage=read(trial/'result.json').get('agent_result') or {}
                        counts={key:usage.get('n_'+key) for key in ('input_tokens','output_tokens')}
                        row.update(raw_success=reward.get('success'), token_usage=counts, over_token_budget=None)
                        if any(type(n) is not int or n<0 for n in counts.values()):
                            row.update(status='usage_missing',success=None)
                        else:
                            over=any(n>plan['token_budget'][key] for key,n in counts.items())
                            row['over_token_budget']=over
                            if over: row.update(status='over_token_budget',success=0)
                except (OSError, ValueError, TypeError, KeyError, AttributeError): row['status']='invalid_record'
            elif job.exists(): row['status']='interrupted'
            rows.append(row)
    counts = dict(Counter(r['status'] for r in rows))
    complete = not errors and len(rows)==plan['trial_count'] and all(r['status'] in TERMINAL for r in rows)
    report=dict(schema_version=1, batch=plan['batch'], plan_sha256=plan['plan_sha256'], planned_trials=plan['trial_count'],
                observed_trials=sum(r['trial'] is not None for r in rows), status_counts=counts, rows=rows, errors=errors,
                evaluation_complete=complete, delivery_complete=complete and not any(r['missing_artifacts'] for r in rows))
    if plan.get('helper_selects_model'):
        report.update(actual_agent=plan['agent'],assignment_sha256=plan.get('assignment_sha256',plan['plan_sha256']))
    return report


def outcome_counts(report):
    """Count final scored outcomes separately from completed trials awaiting review."""
    counts = report.get('effective_status_counts', report['status_counts'])
    solved, unsolved = counts.get('solved', 0), counts.get('unsolved', 0)
    return dict(solved_trials=solved, unsolved_trials=unsolved, scored_trials=solved+unsolved,
                pending_review_trials=counts.get('pending_review', 0))


def outcome_summary(report):
    counts = outcome_counts(report)
    return (f"Scored trials (solved/unsolved only): {counts['solved_trials']}/{counts['scored_trials']} solved; "
            f"pending review: {counts['pending_review_trials']}. "
            "Completion describes execution/delivery, not human approval; pending review is excluded from scores.")


def write_summary(jobs, plan):
    report = check_batch(jobs, plan); jobs = Path(jobs); b = plan['batch']
    save(jobs/(b+'-verdicts.json'), report)
    lines = [f'# {b}', '', f"Planned: {report['planned_trials']}; observed: {report['observed_trials']}; evaluation complete: {report['evaluation_complete']}; delivery complete: {report['delivery_complete']}", '',
             outcome_summary(report), '', '| Task | Repetition | Status | Score | Raw trial |', '|---|---:|---|---:|---|']
    for row in report['rows']:
        score = row.get('success')
        lines.append(f"| {row['task']} | {row['repetition']} | {row['status']} | {score if score is not None else '—'} | {row['trial'] or 'not started'} |")
    lines += ['', *report['errors']]
    (jobs/(b+'.summary.md')).write_text('\n'.join(lines)+'\n')
    return report
