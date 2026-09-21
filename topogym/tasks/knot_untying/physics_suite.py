"""Run the planned local-physics matrix sequentially, stopping at failed gates.

Each case builds a fresh scene in a separate process. A new parameter profile
must use a new output root; completed evidence is never overwritten.
"""
import argparse
from dataclasses import asdict
import json
from pathlib import Path
import subprocess
import sys

from .diagnostics import LIMITS
from .physics_review import evidence_satisfies_case, write_review


def cases():
    result = [(f'free_settle_{i}', 'P1', ['--seconds', '10', '--extend-to', '30', '--seed', str(7+i)])
              for i in range(3)]
    result += [('contact_slide_0', 'P2', ['--mode', 'contact_slide', '--seconds', '15']),
               ('lift_release_0', 'P2', ['--mode', 'lift_release', '--seconds', '14']),
               ('feed_release_0', 'P2', ['--mode', 'feed_release', '--seconds', '20'])]
    for mode, seconds in [('free', '10'), ('feed', '20')]:
        for variant, flags in [('half_step', ['--dt', '.0025']), ('refined', ['--refined']),
                               ('tighter', ['--tighter'])]:
            result.append((f'{mode}_{variant}', 'P3', ['--mode', 'free_settle' if mode == 'free' else 'feed_release',
                                                       '--seconds', seconds, *flags]))
    for label, flags in [('x_plus', ['--x-offset', '.005']), ('x_minus', ['--x-offset', '-.005']),
                         ('yaw_plus', ['--yaw', '5']), ('yaw_minus', ['--yaw', '-5'])]:
        result.append((f'perturb_{label}', 'P3', ['--seconds', '10', *flags]))
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--friction-eps', type=float, default=.01)
    parser.add_argument('--through', choices=('P1', 'P2', 'P3'), default='P3')
    parser.add_argument('--family', choices=('overhand_trefoil', 'figure_eight', 'double_overhand'))
    args = parser.parse_args()
    root = args.output.resolve()
    root.mkdir(parents=True, exist_ok=True)
    chosen = [(name, phase, flags) for name, phase, flags in cases() if phase <= args.through]
    from .physics_probe import make_config
    from omegaconf import OmegaConf
    template = make_config(argparse.Namespace(dt=.005, x_offset=0., yaw=0., refined=False,
                                              tighter=False, friction_eps=args.friction_eps, family=args.family))
    spec = dict(friction_eps_m_s=args.friction_eps, limits=asdict(LIMITS), cases=chosen,
                robot_grasp_included=False, maximum_concurrent_gpu_cases=1,
                template_configuration=OmegaConf.to_container(template, resolve=True))
    spec_path = root/'suite_spec.json'
    if not spec_path.exists() and any(root.glob('*/report.json')):
        raise ValueError('A new suite requires a new output root; existing probes cannot be silently adopted')
    # Normalise tuples before comparison with a prior JSON snapshot.
    spec = json.loads(json.dumps(spec))
    if spec_path.exists() and json.loads(spec_path.read_text()) != spec:
        raise ValueError('Use a new output root for a changed validation profile or matrix')
    spec_path.write_text(json.dumps(spec, indent=2)+'\n')
    for name, phase, flags in chosen:
        folder = root/name
        report_path = folder/'report.json'
        if not report_path.exists():
            if (folder/'progress.json').exists():
                raise RuntimeError(f'{name} has unfinished evidence; inspect its process before restarting')
            folder.mkdir(exist_ok=True)
            if phase == 'P3' and name.startswith('free_'):
                # Compare the same physical horizon if the baseline needed an
                # extension; never compare 30 s against 10 s.
                baseline = json.loads((root/'free_settle_0/report.json').read_text())
                flags = list(flags)
                flags[flags.index('--seconds')+1] = str(baseline['simulated_seconds'])
            command = [sys.executable, '-m', 'topogym.tasks.knot_untying.physics_probe',
                       '--output', str(folder), '--friction-eps', str(args.friction_eps), *flags]
            if args.family:
                command += ['--family', args.family]
            (root/'suite_progress.json').write_text(json.dumps(dict(phase=phase, case=name, state='running'))+'\n')
            print(f'{phase}: {name}', flush=True)
            with (folder/'process.log').open('w') as log:
                process = subprocess.run(command, stdout=log, stderr=subprocess.STDOUT, check=False)
            if not report_path.exists():
                report_path.write_text(json.dumps(dict(passed=False, error=f'Process exited {process.returncode}; see process.log',
                                                       simulated_seconds=0.), indent=2)+'\n')
        report = json.loads(report_path.read_text())
        write_review(root)
        if not evidence_satisfies_case(name, report):
            (root/'suite_progress.json').write_text(json.dumps(dict(phase=phase, case=name, state='failed_gate'))+'\n')
            raise SystemExit(f'{name} did not pass; later gates were not executed')
    result = write_review(root)
    passed = all(result['phases'][phase] for phase in ('P1', 'P2', 'P3') if phase <= args.through)
    (root/'suite_progress.json').write_text(json.dumps(dict(
        state='matrix_complete' if passed else 'failed_comparison_gate', through=args.through,
        individual_cases_completed=True, complete_physics_suite_passed=False,
        failed_comparisons=[name for name, report in result['comparisons'].items() if not report['passed']]))+'\n')
    if not passed:
        raise SystemExit('The individual cases completed but a comparison gate did not pass')


if __name__ == '__main__':
    main()
