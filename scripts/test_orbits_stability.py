#!/usr/bin/env python3
"""Run passive Orbits tiers in isolated processes from a fixed source snapshot."""

import argparse
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import shutil
import signal
import subprocess
import sys
import time

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from topogym.utils.io import sha256_file, write_json_atomic


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', required=True, type=Path)
    parser.add_argument('--tiers', nargs='+', choices=('easy', 'medium', 'hard'), default=['easy', 'medium', 'hard'])
    parser.add_argument('--duration', type=float, default=10.)
    parser.add_argument('--window', type=float, default=2.)
    parser.add_argument('--dt', type=float, default=.0025)
    parser.add_argument('--seed', type=int, default=0)
    parser.add_argument('--timeout', type=float, default=7200.)
    parser.add_argument('--min-free-gib', type=float, default=12.)
    parser.add_argument('--gpu-wait-timeout', type=float, default=900.)
    parser.add_argument('--visual-asset-root', type=Path, default=ROOT/'.external/nyx-assets')
    args = parser.parse_args()
    import math
    if not all(math.isfinite(x) and x > 0 for x in (args.duration, args.window, args.dt, args.timeout,
                                                  args.min_free_gib, args.gpu_wait_timeout)):
        parser.error('Timing values must be positive and finite')
    if args.duration <= args.window or not 0 <= args.seed < 2**32:
        parser.error('Duration must exceed window; seed must be in [0, 2**32)')
    if (abs(args.duration/(10*args.dt)-round(args.duration/(10*args.dt))) > 1e-8 or
            abs(args.window/args.dt-round(args.window/args.dt)) > 1e-8):
        parser.error('Duration must cover whole control steps; window must cover whole physics ticks')
    root = args.output.resolve()
    root.mkdir(parents=True, exist_ok=False)
    source = root/'source'
    source.mkdir()
    for name in ('topogym', 'tests', 'scripts'):
        shutil.copytree(ROOT/name, source/name, ignore=shutil.ignore_patterns('__pycache__', '*.pyc'))
    shutil.copy2(ROOT/'pyproject.toml', source/'pyproject.toml')
    hashes = {str(p.relative_to(source)): sha256_file(p) for p in sorted(source.rglob('*')) if p.is_file()}
    write_json_atomic(root/'source_hashes.json', hashes)
    report = dict(started_at_utc=datetime.now(timezone.utc).isoformat(), status='running',
                  scope='Initial-scene passive stability; not a task solution or difficulty qualification',
                  arguments=vars(args), results=[])
    write_json_atomic(root/'run.json', report)
    environment = dict(os.environ, PYTHONPATH=str(source)+os.pathsep+str(source/'tests'),
                       PYOPENGL_PLATFORM='egl', TOPOGYM_ASSET_ROOT=str(ROOT/'assets'),
                       TOPOGYM_VISUAL_ASSET_ROOT=str(args.visual_asset_root.resolve()),
                       TOPOGYM_ORBITS_OUTPUT=str(root/'validation'),
                       TOPOGYM_ORBITS_DURATION=str(args.duration), TOPOGYM_ORBITS_WINDOW=str(args.window),
                       TOPOGYM_ORBITS_DT=str(args.dt), TOPOGYM_ORBITS_SEED=str(args.seed))
    for tier in dict.fromkeys(args.tiers):
        command = [sys.executable, '-m', 'pytest', '-q', '-s', '-o', 'addopts=',
                   f'tests/integration/test_orbits_stability.py::test_passive_stability[{tier}]',
                   f'--junitxml={root/tier}_junit.xml']
        item = dict(tier=tier, command=command, status='waiting_for_gpu_memory')
        report['results'].append(item)
        write_json_atomic(root/'run.json', report)
        deadline = time.monotonic()+args.gpu_wait_timeout
        try:
            while True:
                probe = subprocess.run(['nvidia-smi', '--query-gpu=memory.free', '--format=csv,noheader,nounits'],
                                       capture_output=True, text=True, check=False)
                if probe.returncode:
                    item.update(status='hardware_unavailable', error=probe.stderr or probe.stdout)
                    break
                free = float(probe.stdout.strip().splitlines()[0])/1024
                item['last_free_gib'] = free
                write_json_atomic(root/'run.json', report)
                if free >= args.min_free_gib:
                    item['status'] = 'running'
                    break
                if time.monotonic() >= deadline:
                    item.update(status='gpu_memory_timeout')
                    break
                print(f'{tier}: waiting for GPU memory ({free:.1f} GiB free, {args.min_free_gib:.1f} required)', flush=True)
                time.sleep(min(15., max(0., deadline-time.monotonic())))
        except (OSError, ValueError, IndexError) as exc:
            item.update(status='hardware_unavailable', error=str(exc))
        except KeyboardInterrupt:
            item['status'] = report['status'] = 'interrupted'
            write_json_atomic(root/'run.json', report)
            raise
        if item['status'] != 'running':
            write_json_atomic(root/'run.json', report)
            continue
        write_json_atomic(root/'run.json', report)
        with (root/f'{tier}.log').open('w') as stream:
            process = subprocess.Popen(command, cwd=source, env=environment,
                                       stdout=stream, stderr=subprocess.STDOUT, start_new_session=True)
            try:
                code = process.wait(timeout=args.timeout)
                item.update(status='passed' if code == 0 else 'failed', exit_code=code)
            except (subprocess.TimeoutExpired, KeyboardInterrupt) as exc:
                os.killpg(process.pid, signal.SIGTERM)
                try:
                    process.wait(timeout=10)
                except subprocess.TimeoutExpired:
                    os.killpg(process.pid, signal.SIGKILL)
                    process.wait()
                item.update(status='timeout' if isinstance(exc, subprocess.TimeoutExpired) else 'interrupted')
                if isinstance(exc, KeyboardInterrupt):
                    report['status'] = 'interrupted'
                    write_json_atomic(root/'run.json', report)
                    raise
        # Native CUDA aborts bypass Python finally blocks. Preserve that outcome
        # in the evidence report instead of leaving a completed process 'running'.
        evidence_path = root/'validation'/tier/'report.json'
        if evidence_path.exists():
            evidence = json.loads(evidence_path.read_text())
            if evidence['status'] == 'running':
                evidence.update(status='failed', driver_status=item['status'],
                                process_exit_code=process.returncode,
                                failure_scope='process ended before test could finalize evidence')
                write_json_atomic(evidence_path, evidence)
        write_json_atomic(root/'run.json', report)
        print(tier, item['status'], flush=True)
    statuses = {row['status'] for row in report['results']}
    report['status'] = ('passed' if statuses == {'passed'} else
                        'blocked' if statuses <= {'passed', 'gpu_memory_timeout', 'hardware_unavailable'} else 'failed')
    write_json_atomic(root/'run.json', report)
    return int(report['status'] != 'passed')


if __name__ == '__main__':
    raise SystemExit(main())
