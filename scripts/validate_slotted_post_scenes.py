#!/usr/bin/env python3
"""Validate three frozen Slotted Post scenes at main/half timesteps with Nyx evidence."""
import argparse
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from record_initial_scenes import source_files, digest, write_json


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--seconds', type=float, default=10.)
    parser.add_argument('--timeout', type=float, default=7200.)
    parser.add_argument('--no-rgb', action='store_true', help='Physics-only; record Nyx scenes separately')
    parser.add_argument('--tiers', nargs='+', choices=('easy', 'medium', 'hard'), default=['easy', 'medium', 'hard'])
    args = parser.parse_args()
    import math
    if not math.isfinite(args.seconds) or args.seconds <= 2 or abs(args.seconds/.025-round(args.seconds/.025)) > 1e-8:
        parser.error('seconds must be finite, > 2, and a multiple of 0.025')
    if not math.isfinite(args.timeout) or args.timeout <= 0:
        parser.error('timeout must be positive and finite')
    output = args.output.resolve()
    output.mkdir(parents=True, exist_ok=False)
    snapshot = output/'source_snapshot'
    hashes = {}
    for source in source_files(ROOT):
        relative = source.relative_to(ROOT)
        target = snapshot/relative
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, target)
        hashes[str(relative)] = digest(target)
    write_json(output/'source_hashes.json', hashes)
    from slotted_scene_stability import LIMITS
    report = dict(started_at_utc=datetime.now(timezone.utc).isoformat(),
        scope='three fixed scenes; unassisted home hold, not task solution or calibrated difficulty',
        seed=0, duration_s=args.seconds, settling_window_s=2., limits=LIMITS,
        physics_dt_s=[.0025, .00125], solver_substeps=4, control_interval_s=.025,
        enable_rgb=not args.no_rgb, tiers=args.tiers,
        source_snapshot=str(snapshot), source_hashes='source_hashes.json',
        results=[], timestep_comparisons=[], status='running')
    write_json(output/'summary.json', report)
    environment = dict(os.environ, PYTHONPATH=os.pathsep.join((str(snapshot), str(snapshot/'tests'))),
        TOPOGYM_ASSET_ROOT=str(ROOT/'assets'),
        TOPOGYM_VISUAL_ASSET_ROOT=str(ROOT/'.external/nyx-assets'), PYOPENGL_PLATFORM='egl')
    for tier in dict.fromkeys(args.tiers):
        for label, dt in (('main', .0025), ('half', .00125)):
            case = f'{tier}_{label}'
            command = [sys.executable, str(snapshot/'scripts/test_scene_presets.py'),
                '--case', 'slotted_post_ring', '--variation', tier,
                '--probe', 'slotted_stability', '--seconds', str(args.seconds),
                '--physics-dt', str(dt), '--output', str(output/case)]
            if args.no_rgb:
                command += ['--no-rgb']
            result = dict(case=case, variation=tier, physics_dt_s=dt, status='running', command=command)
            report['results'].append(result)
            write_json(output/'summary.json', report)
            print(case, 'running', flush=True)
            with (output/f'{case}.log').open('x') as log:
                try:
                    completed = subprocess.run(command, cwd=snapshot, env=environment,
                        stdout=log, stderr=subprocess.STDOUT, timeout=args.timeout)
                    result['exit_code'] = completed.returncode
                except subprocess.TimeoutExpired:
                    result.update(exit_code=-1, error='case timeout')
            path = output/case/'slotted_post_ring/report.json'
            case_report = json.loads(path.read_text()) if path.exists() else {}
            result.update(status='passed' if result['exit_code'] == 0 and case_report.get('status') == 'passed' else 'failed',
                report=str(path.relative_to(output)), stability=case_report.get('stability'))
            if result['status'] == 'failed':
                result['error'] = case_report.get('traceback', result.get('error', 'see log'))
                # Native aborts bypass Python's finally block; persist a failed
                # report instead of leaving a misleading "running" artifact.
                log_text = (output/f'{case}.log').read_text(errors='replace')
                native_errors = [line for line in log_text.splitlines() if any(
                    code in line for code in ('CUDA_ERROR_OUT_OF_MEMORY', 'cudaErrorInvalidDevice', 'cudaErrorMemoryAllocation'))]
                if native_errors:
                    result['error'] = native_errors[-1]
                if case_report.get('status') == 'running':
                    case_report.update(status='failed', exit_code=result['exit_code'],
                        infrastructure_error=result['error'], complete=False)
                    write_json(path, case_report)
            write_json(output/'summary.json', report)
            print(case, result['status'], flush=True)
            if any(code in result.get('error', '') for code in
                   ('CUDA_ERROR_OUT_OF_MEMORY', 'cudaErrorInvalidDevice', 'cudaErrorMemoryAllocation')):
                report.update(status='infrastructure_blocked',
                    reason=result['error'] + '; remaining cases not started',
                    finished_at_utc=datetime.now(timezone.utc).isoformat())
                write_json(output/'summary.json', report)
                return 1
        import numpy as np
        comparison = dict(variation=tier, limit_m=.002, passed=False)
        if all(r['status'] == 'passed' for r in report['results'][-2:]):
            paths = [output/f'{tier}_{label}/slotted_post_ring/stability_final_points.npz' for label in ('main', 'half')]
            with np.load(paths[0]) as a, np.load(paths[1]) as b:
                comparison['maximum_point_difference_m'] = {
                    key: float(np.linalg.norm(a[key]-b[key], axis=1).max()) for key in a.files}
            comparison['passed'] = max(comparison['maximum_point_difference_m'].values()) <= comparison['limit_m']
        else:
            comparison['reason'] = 'both individual stability runs must pass first'
        report['timestep_comparisons'].append(comparison)
    report['status'] = 'passed' if all(r['status'] == 'passed' for r in report['results']) and all(
        c['passed'] for c in report['timestep_comparisons']) else 'failed'
    report['finished_at_utc'] = datetime.now(timezone.utc).isoformat()
    write_json(output/'summary.json', report)
    return int(report['status'] != 'passed')


if __name__ == '__main__':
    sys.path.insert(0, str(ROOT/'tests'))
    raise SystemExit(main())
