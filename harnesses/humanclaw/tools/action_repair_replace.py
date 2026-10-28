#!/usr/bin/env python3
"""Replace repaired episodes or explicitly prune audited invalid owned shards.

There is one physical copy of the new data. The previous repair path becomes a
symlink so recorded absolute paths and validation receipts keep working. A small
transaction receipt supports recovery; it does not retain old rollout payloads.
"""
from __future__ import annotations

import argparse
import ast
from collections import Counter
from concurrent.futures import ThreadPoolExecutor
import fcntl
import hashlib
import importlib
import json
import math
import os
from pathlib import Path
import shutil
import stat
from statistics import fmean
import sys
import time
import types
from typing import Any, Iterable
import uuid

OWN_ROOT = Path('/gscratch/scrubbed/hengyil6/humanclaw-analysis/experiments')
CAMPAIGN = 'action-repair-azure-20261021'


def read(path):
    return json.loads(Path(path).read_text())


def digest(path):
    h = hashlib.sha256()
    with Path(path).open('rb') as f:
        for block in iter(lambda: f.read(1024 * 1024), b''):
            h.update(block)
    return h.hexdigest()


def write(path, value):
    path = Path(path)
    temporary = path.with_name(path.name + '.tmp-' + uuid.uuid4().hex)
    try:
        with temporary.open('x') as f:
            json.dump(value, f, indent=2, ensure_ascii=False, allow_nan=False)
            f.write('\n')
            f.flush()
            os.fsync(f.fileno())
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)


def checked_path(path, root):
    """Reject traversal and symlinked ancestors below the authorized root."""
    path = Path(path)
    relative = path.relative_to(root)
    if '..' in relative.parts:
        raise ValueError('Path traversal')
    cursor = root
    for part in relative.parts:
        cursor /= part
        if cursor.is_symlink():
            raise ValueError(f'Symlink in replacement path: {cursor}')
    return path


def inventory(root):
    """Check inode identity across rename; measure old data without following links."""
    entries, inodes = [], {}
    for directory, dirs, files in os.walk(root, followlinks=False):
        for path in [Path(directory), *(Path(directory) / n for n in files),
                     *(Path(directory) / n for n in dirs if (Path(directory) / n).is_symlink())]:
            s = path.lstat()
            if s.st_uid != os.getuid():
                raise ValueError(f'Replacement contains data not owned by this account: {path}')
            kind = stat.S_IFMT(s.st_mode)
            relative = str(path.relative_to(root))
            # GPFS updates a moved directory's mtime when its '..' changes.
            # Ignore only the root directory's mtime, never payload timestamps.
            mtime = None if relative == '.' and kind == stat.S_IFDIR else s.st_mtime_ns
            entries.append((relative, s.st_dev, s.st_ino, kind,
                            s.st_size, mtime, os.readlink(path) if path.is_symlink() else None))
            key = (s.st_dev, s.st_ino)
            if key not in inodes:
                inodes[key] = [s.st_size, s.st_blocks * 512, s.st_nlink, 0, kind]
            inodes[key][3] += 1
    fingerprint = hashlib.sha256(json.dumps(sorted(entries)).encode()).hexdigest()
    return {'version': 2, 'sha256': fingerprint, 'entries': len(entries),
            'allocated_bytes': sum(v[1] for v in inodes.values()),
            'reclaimable_bytes_estimate': sum(v[1] for v in inodes.values()
                if v[4] == stat.S_IFDIR or v[2] <= v[3])}


def reporting(plan, entry):
    """Reuse the pinned reporting code without importing the GPU simulator."""
    source = Path(plan['source_variants'][entry['source_variant']]['prepared_source'])
    pins = read(source / 'repair_source.json')['files']
    package = source / 'src/humanclaw_bench'
    for name in ('experiments/report.py', 'experiments/artifacts.py', 'evaluation/metrics/episode.py'):
        if digest(package / name) != pins['src/humanclaw_bench/' + name]:
            raise ValueError('Frozen reporting source changed')
    alias = '_replacement_report_' + entry['source_variant'][:16]
    if alias not in sys.modules:
        module = types.ModuleType(alias)
        module.__path__ = [str(package / 'experiments')]
        sys.modules[alias] = module
    report = importlib.import_module(alias + '.report')
    # Only these pure reporting functions are needed. Their original ASTs avoid
    # importing collision/robotics dependencies on a login node.
    names = {'_finite_mean', '_rate', 'aggregate_metric_files'}
    tree = ast.parse((package / 'evaluation/metrics/episode.py').read_text())
    functions = [n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name in names]
    if {n.name for n in functions} != names:
        raise ValueError('Pinned metrics aggregators are missing')
    scope = dict(json=json, math=math, Path=Path, fmean=fmean, Any=Any, Iterable=Iterable)
    exec(compile(ast.Module(body=functions, type_ignores=[]), str(package / 'evaluation/metrics/episode.py'), 'exec'), scope)
    return report, scope['aggregate_metric_files']


def replacement(plan, entry, *, apply=False):
    root = OWN_ROOT.resolve()
    if Path(plan['destination_root']).resolve() != root:
        raise ValueError('Not the authorized owned results root')
    suite, shard = entry['suite'], entry['shard']
    if any(Path(v).name != v or v in ('.', '..') for v in (suite, shard)):
        raise ValueError('Invalid suite or shard')
    repair = checked_path(root / suite / CAMPAIGN / 'results' / shard, root)
    if Path(entry['destination']).resolve() != repair:
        raise ValueError('Repair destination differs from plan')
    validated = repair / 'validated_result.json'
    if not validated.is_file():
        return {'index': entry['index'], 'status': 'not_ready'}
    with (repair / 'replacement.lock').open('a') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        return _replace_locked(plan, entry, root, repair, apply)


def prune_confirmed_original(plan, entry, *, apply=False):
    """Explicit opt-in: remove the audited bad owned copy before its rerun."""
    root = OWN_ROOT.resolve()
    if Path(plan['destination_root']).resolve() != root:
        raise ValueError('Not the authorized owned results root')
    suite, shard = entry['suite'], entry['shard']
    if any(Path(v).name != v or v in ('.', '..') for v in (suite, shard)):
        raise ValueError('Invalid suite or shard')
    target = checked_path(root / suite / 'results' / shard, root)
    repair = checked_path(root / suite / CAMPAIGN / 'results' / shard, root)
    if Path(entry['destination']).resolve() != repair:
        raise ValueError('Repair destination differs from plan')
    old = root / Path(entry['local_copy_run']).relative_to(Path(plan['destination_root']))
    old.relative_to(target)
    if old.name != entry['old_run_id'] or old.parents[3] != target:
        raise ValueError('Original run/shard layout mismatch')
    receipt_path = repair / 'original_prune_receipt.json'
    if not target.exists() and not receipt_path.exists():
        return {'index': entry['index'], 'status': 'owned_original_absent'}
    repair.mkdir(parents=True, exist_ok=True)
    with (repair / 'replacement.lock').open('a') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        if (repair / 'validated_result.json').is_file():
            return {'index': entry['index'], 'status': 'retained_validated_episode'}
        receipt = read(receipt_path) if receipt_path.exists() else None
        identity = {'index': entry['index'], 'target': str(target),
                    'old_run_id': entry['old_run_id'], 'old_run_sha256': entry['old_run_sha256']}
        if receipt and any(receipt.get(k) != v for k, v in identity.items()):
            raise ValueError('Original prune receipt identity mismatch')
        if receipt and receipt['status'] == 'original_deleted_before_rerun':
            if target.exists():
                raise ValueError('Data appeared after original deletion; refusing to delete it')
            return {**receipt, 'already_applied': True}
        episode_name = old.parents[2].name
        additional = []
        if target.exists():
            if any(d.is_dir() and d.name not in (episode_name, 'batch_attempts') for d in target.iterdir()):
                raise ValueError('Old shard contains another episode')
            found = list(target.glob('*/rollout_*/experiment_runs/*/run.json'))
            extras = [f for f in found if f != old / 'run.json']
            if extras and receipt is None:
                if digest(old / 'run.json') != entry['old_run_sha256']:
                    raise ValueError('Owned old result differs from audited original')
                selected = read(old / 'run.json')
                episode = selected.get('metadata', {}).get('episode')
                for path in extras:
                    checked_path(path, root)
                    data = read(path)
                    reference = Path(entry['source_run']).parent / path.parent.name / 'run.json'
                    if (path.parent.parent != old.parent or not episode
                            or data.get('metadata', {}).get('episode') != episode
                            or data.get('status') not in ('completed', 'failed', 'interrupted', 'running')
                            or 'action_repair' in data.get('metadata', {})
                            or not data.get('started_at_utc')
                            or data['started_at_utc'] > selected['started_at_utc']
                            or digest(path) != digest(reference)):
                        raise ValueError('Old shard contains an unverified additional run')
                    additional.append({'run_id': path.parent.name, 'sha256': digest(path),
                                       'status': data['status'], 'source_manifest': str(reference)})
            elif extras:
                allowed = {r['run_id']: r['sha256'] for r in receipt.get('additional_original_attempts',
                           receipt.get('additional_failed_attempts', []))}
                if any(f.parent.parent != old.parent or digest(f) != allowed.get(f.parent.name) for f in extras):
                    raise ValueError('Additional run changed during interrupted cleanup')
        if receipt is None:
            checked_path(old, root)
            if digest(old / 'run.json') != entry['old_run_sha256']:
                raise ValueError('Owned old result differs from audited original')
            receipt = {**identity, 'cohort': entry['cohort'], 'shard': shard,
                       'status': 'prepared', 'old_data': inventory(target),
                       'additional_original_attempts': additional,
                       'prepared_at_unix': time.time(), 'coauthor_original_modified': False,
                       'reason': 'Explicit user authorization to delete audited invalid originals before rerunning',
                       'tool_sha256': digest(__file__)}
            if not apply:
                return {**receipt, 'status': 'ready_to_prune'}
            write(receipt_path, receipt)
        if not apply:
            return receipt
        if target.exists():
            checked_path(target, root)
            shutil.rmtree(target)
        receipt.update(status='original_deleted_before_rerun', finished_at_unix=time.time())
        write(receipt_path, receipt)
        return receipt


def _replace_locked(plan, entry, root, repair, apply):
    verified = read(repair / 'validated_result.json')
    result = verified['result']
    if (verified.get('status') != 'completed' or result.get('ok') is not True
            or result.get('errors') or not result.get('trace', {}).get('ok')
            or result.get('trace', {}).get('warnings') or result.get('model_calls', 0) < 1):
        raise ValueError('New run is not fully validated')
    attempt = checked_path(Path(verified['attempt']).resolve(), root)
    if attempt.parent != repair or not attempt.name.startswith('attempt-'):
        raise ValueError('Attempt is outside the matching repaired shard')
    target = checked_path(root / entry['suite'] / 'results' / entry['shard'], root)
    source = attempt / 'rollout'
    old_relative = Path(entry['local_copy_run']).relative_to(Path(plan['destination_root']))
    old_run = root / old_relative
    old_run.relative_to(target)
    if old_run.parent.name != 'experiment_runs' or old_run.parent.parent.name != 'rollout_00':
        raise ValueError('Unexpected old run layout')
    episode_name = old_run.parents[2].name
    new_id = Path(result['run']).name
    if not new_id.startswith('run_') or new_id == entry['old_run_id']:
        raise ValueError('New run must retain its distinct identity')
    relative_run = Path(episode_name) / 'rollout_00' / 'experiment_runs' / new_id
    canonical_run = target / relative_run
    tomb = target.with_name('.' + target.name + '.replaced-' + new_id)
    checked_path(tomb, root)
    journal_path = repair / 'replacement_transaction.json'
    receipt_path = repair / 'replacement_receipt.json'
    if receipt_path.exists():
        receipt = read(receipt_path)
        if (receipt.get('status') != 'replaced_old_deleted' or
                digest(canonical_run / 'run.json') != result['run_sha256'] or
                not source.is_symlink() or source.resolve() != target):
            raise ValueError('Installed replacement differs from receipt')
        return {**receipt, 'already_applied': True}

    journal = read(journal_path) if journal_path.exists() else None
    if journal:
        expected = {'index': entry['index'], 'source': str(source), 'target': str(target),
                    'tomb': str(tomb), 'new_run_sha256': result['run_sha256']}
        if any(journal.get(k) != v for k, v in expected.items()):
            raise ValueError('Replacement transaction identity mismatch')
    else:
        checked_path(source, root)
        if not source.is_dir() or tomb.exists():
            raise ValueError('Missing new payload or unexpected prior staging directory')
        new_run = source / relative_run
        if Path(result['run']).resolve() != new_run.resolve():
            raise ValueError('New run does not match episode layout')
        manifest = read(new_run / 'run.json')
        md = manifest['metadata']
        if (digest(new_run / 'run.json') != result['run_sha256'] or
                manifest.get('run_id') != new_id or manifest.get('status') != 'completed' or
                not isinstance(manifest.get('outcome', {}).get('task_success'), bool) or
                md.get('action_repair', {}).get('old_run_id') != entry['old_run_id'] or
                str(md.get('episode_id')) != str(entry['episode']) or md.get('harness') != 'codex'):
            raise ValueError('New manifest identity or completion mismatch')
        if list(source.glob('*/rollout_*/experiment_runs/*/run.json')) != [new_run / 'run.json']:
            raise ValueError('Replacement must contain exactly one episode and run')
        old_inventory = {'allocated_bytes': 0, 'reclaimable_bytes_estimate': 0, 'entries': 0}
        if target.exists():
            checked_path(old_run, root)
            if digest(old_run / 'run.json') != entry['old_run_sha256']:
                raise ValueError('Owned old result differs from audited original')
            if any(d.is_dir() and d.name not in (episode_name, 'batch_attempts') for d in target.iterdir()):
                raise ValueError('Old shard contains another episode')
            if list(target.glob('*/rollout_*/experiment_runs/*/run.json')) != [old_run / 'run.json']:
                raise ValueError('Old shard contains additional runs')
            old_inventory = inventory(target)
        report, aggregate_metrics = reporting(plan, entry)
        trace = report.validate_trace(new_run)
        if not trace['ok'] or trace['warnings']:
            raise ValueError('New trace/artifact verification failed before replacement')
        preview = {'index': entry['index'], 'cohort': entry['cohort'], 'shard': entry['shard'],
                   'status': 'ready', 'source': str(source), 'target': str(target), 'tomb': str(tomb),
                   'old_run_id': entry['old_run_id'], 'old_run_sha256': entry['old_run_sha256'],
                   'new_run_id': new_id, 'new_run_sha256': result['run_sha256'],
                   'canonical_run': str(canonical_run), 'old_data': old_inventory,
                   'old_copy_present': target.exists(), 'provider_change': plan['provider_change'],
                   'coauthor_original_modified': False, 'replacement_tool_sha256': digest(__file__)}
        if not apply:
            return preview
        # Build fresh shard summaries from the new run; never carry old scores forward.
        collection = report.summarize_runs(source, write=False)
        collection['root'] = str(target)
        write(source / 'experiment_summary.json', collection)
        write(source / 'metrics_summary.json', aggregate_metrics(source, write_summary=False))
        journal = {**preview, 'status': 'prepared', 'new_inventory': inventory(source),
                   'started_at_unix': time.time()}
        write(journal_path, journal)

    if not apply:
        return journal
    report, _ = reporting(plan, entry)
    installed = canonical_run.is_dir() and digest(canonical_run / 'run.json') == result['run_sha256']
    if not installed:
        if target.exists():
            if tomb.exists() or digest(old_run / 'run.json') != entry['old_run_sha256']:
                raise ValueError('Old target changed during replacement')
            os.replace(target, tomb)
        elif journal['old_copy_present'] and not tomb.is_dir():
            raise ValueError('Original target unexpectedly disappeared')
        if source.is_symlink() or not source.is_dir():
            raise ValueError('New payload missing while original is staged')
        if inventory(source)['sha256'] != journal['new_inventory']['sha256']:
            raise ValueError('New payload changed before installation')
        target.parent.mkdir(parents=True, exist_ok=True)
        os.replace(source, target)
    if source.is_symlink():
        if source.resolve() != target:
            raise ValueError('Repair alias points elsewhere')
    elif not source.exists():
        source.symlink_to(target, target_is_directory=True)
    else:
        raise ValueError('Unexpected second copy of repaired payload')
    if inventory(target)['sha256'] != journal['new_inventory']['sha256']:
        raise ValueError('Payload changed during installation; original retained for recovery')
    trace = report.validate_trace(canonical_run)
    if not trace['ok'] or trace['warnings']:
        raise ValueError('Installed trace verification failed; original retained for recovery')
    journal.update(status='installed_verified', installed_at_unix=time.time())
    write(journal_path, journal)
    if tomb.exists():
        checked_path(tomb, root)
        shutil.rmtree(tomb)  # Only this exact, verified, user-owned episode is deleted.
    receipt = {**journal, 'status': 'replaced_old_deleted', 'finished_at_unix': time.time()}
    write(receipt_path, receipt)
    write(journal_path, receipt)
    return receipt


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('plan', type=Path)
    parser.add_argument('--index', type=int, action='append')
    parser.add_argument('--apply', action='store_true')
    parser.add_argument('--prune-invalid-originals', action='store_true')
    parser.add_argument('--workers', type=int, default=4)
    args = parser.parse_args()
    plan = read(args.plan)
    if args.apply:
        policy = read(args.plan.parent / 'replacement_policy.json')
        if (policy.get('replace_owned_results') is not True or policy.get('delete_replaced_data') is not True
                or Path(policy['owned_root']).resolve() != OWN_ROOT.resolve()):
            raise ValueError('Explicit owned-result replacement policy is missing')
        if args.prune_invalid_originals and policy.get('delete_confirmed_invalid_before_rerun') is not True:
            raise ValueError('Explicit deletion-before-rerun authorization is missing')
    if args.prune_invalid_originals:
        if not 1 <= args.workers <= 8:
            raise ValueError('Use one to eight independent deletion workers')
        entries = [e for e in plan['entries'] if args.index is None or e['index'] in args.index]
        def process(entry):
            try:
                return prune_confirmed_original(plan, entry, apply=args.apply)
            except Exception as exc:
                return {'index': entry['index'], 'status': 'error', 'error': str(exc)}
        counts, errors, removed = Counter(), [], 0
        with ThreadPoolExecutor(max_workers=args.workers) as pool:
            for number, result in enumerate(pool.map(process, entries), 1):
                counts[result['status']] += 1
                if result['status'] == 'error':
                    errors.append(result)
                    print(json.dumps(result), flush=True)
                if result['status'] == 'original_deleted_before_rerun' and not result.get('already_applied'):
                    removed += result['old_data']['allocated_bytes']
                if number % 25 == 0:
                    print(json.dumps({'checked': number, 'counts': counts, 'deleted_old_bytes': removed}), flush=True)
        print(json.dumps({'counts': counts, 'deleted_old_bytes': removed, 'errors': errors}), flush=True)
        return 1 if errors else 0
    counts, errors = Counter(), []
    for entry in plan['entries']:
        if args.index is not None and entry['index'] not in args.index:
            continue
        try:
            receipt = replacement(plan, entry, apply=args.apply)
            counts[receipt['status']] += 1
            if receipt['status'] != 'not_ready':
                print(json.dumps({k: receipt.get(k) for k in ('index', 'status', 'canonical_run', 'old_data', 'already_applied')}), flush=True)
        except Exception as exc:
            errors.append({'index': entry['index'], 'error': str(exc), 'type': type(exc).__name__})
            print(json.dumps(errors[-1]), flush=True)
    print(json.dumps({'counts': counts, 'errors': errors}), flush=True)
    return 1 if errors else 0


if __name__ == '__main__':
    raise SystemExit(main())
