"""Summarize completed evidence in Markdown/JSON, keeping unrun gates explicit."""
import argparse
import json
from pathlib import Path


EXPECTED = {
    'P1': ['free_settle_0', 'free_settle_1', 'free_settle_2'],
    'P2': ['contact_slide_0', 'lift_release_0', 'feed_release_0'],
    'P3': ['free_half_step', 'feed_half_step', 'free_refined', 'feed_refined',
           'free_tighter', 'feed_tighter', 'perturb_x_plus', 'perturb_x_minus',
           'perturb_yaw_plus', 'perturb_yaw_minus'],
    'P4': ['robot_grasp'],
}


def evidence_satisfies_case(name, report):
    if name == 'robot_grasp':
        return bool(report.get('passed') and report.get('robot_grasp_qualified'))
    required = 20. if name.startswith('feed_') else 14. if name.startswith('lift_') else 15. if name.startswith('contact_') else 10.
    return bool(report.get('passed') and report.get('simulated_seconds', 0.) >= required-1e-8)


def compare_centerlines(first, second):
    """Interpolate in initial material arc length, never in the deformed arc."""
    import numpy as np
    with np.load(first/'trajectory.npz') as a, np.load(second/'trajectory.npz') as b:
        # NPZ indexing decompresses the entire array. Read each array once,
        # rather than decompressing megabytes for every material sample.
        times_a, times_b = a['times'], b['times']
        centers_a, centers_b = a['centerlines'], b['centerlines']
        initial_a, initial_b = a['initial_centerline'], b['initial_centerline']
        def normalized_arc(points):
            s = np.r_[0., np.cumsum(np.linalg.norm(np.diff(points, axis=0), axis=1))]
            return s/s[-1]
        sa, sb = normalized_arc(initial_a), normalized_arc(initial_b)
        end_time_a, end_time_b = float(times_a[-1]), float(times_b[-1])
        if abs(end_time_a-end_time_b) > 1e-6:
            return dict(passed=False, reason='Different physical durations cannot be compared')
        differences = []
        # Compare matched physical samples throughout, plus the final hold.
        for i, t in enumerate(times_a):
            j = int(np.argmin(abs(times_b-t)))
            if abs(float(times_b[j]-t)) > 1e-6:
                continue
            other = np.column_stack([np.interp(sa, sb, centers_b[j, :, k]) for k in range(3)])
            distance = np.linalg.norm(centers_a[i]-other, axis=1)
            differences.append(dict(time_s=float(t), rms_m=float(np.sqrt(np.mean(distance**2))),
                                    max_m=float(distance.max())))
    if not differences:
        return dict(passed=False, reason='No matching timestamps')
    final = differences[-1]
    spec = json.loads((first/'validation_spec.json').read_text())
    required_times = [final['time_s']]
    if spec['experiment'] == 'feed_release':
        required_times += [5., 7., 9., 11., 13., 15.]
    key_states = [min(differences, key=lambda d: abs(d['time_s']-t)) for t in required_times]
    from .diagnostics import LIMITS
    return dict(passed=all(abs(s['time_s']-t) < 1e-6 and s['rms_m'] < LIMITS.comparison_rms_m
                           and s['max_m'] < LIMITS.comparison_max_m for s, t in zip(key_states, required_times)),
                final=final, key_states=key_states, trajectory_max_rms_m=max(d['rms_m'] for d in differences),
                trajectory_max_m=max(d['max_m'] for d in differences),
                samples=differences, criterion='key motion reversals and final hold, aligned in time and material arc')


def plot_trace(folder):
    if not (folder/'trace.json').exists():
        return
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    import numpy as np
    trace = json.loads((folder/'trace.json').read_text())
    if not trace:
        return
    t = [s['time_s'] for s in trace]
    fig, ax = plt.subplots(1, 3, figsize=(13, 3.3), layout='constrained')
    for key, label in [('rms_speed_m_s', 'RMS'), ('max_speed_m_s', 'Maximum')]:
        ax[0].semilogy(t, [max(1e-8, s[key])*1000 for s in trace], label=label)
    ax[0].axhline(1., color='C0', linestyle=':')
    ax[0].axhline(5., color='C1', linestyle=':')
    ax[0].set(xlabel='Simulation time (s)', ylabel='Native speed (mm/s)')
    ax[0].legend()
    ax[1].plot(t, [s['min_J'] for s in trace])
    ax[1].axhline(.2, color='r', linestyle=':')
    ax[1].set(xlabel='Simulation time (s)', ylabel='Minimum det(F)')
    with np.load(folder/'trajectory.npz') as data:
        initial, final = data['initial_centerline'], data['centerlines'][-1]
        if (folder/'mesh.npz').exists():
            with np.load(folder/'mesh.npz') as mesh:
                slices = mesh['material_slices'] if 'material_slices' in mesh else [(0, len(initial))]
        else:
            slices = [(0, len(initial))]
        for i, (start, end) in enumerate(slices):
            ax[2].plot(initial[start:end, 0]*1000, initial[start:end, 1]*1000, '--', color='gray',
                       label='Initial' if i == 0 else None)
            ax[2].plot(final[start:end, 0]*1000, final[start:end, 1]*1000, color='C2',
                       label='Final' if i == 0 else None)
    ax[2].set(xlabel='World x (mm)', ylabel='World y (mm)', aspect='equal')
    ax[2].legend()
    for axis in ax:
        axis.grid(alpha=.2)
    fig.savefig(folder/'diagnostics.png', dpi=160)
    plt.close(fig)


def plot_refinement(root):
    import numpy as np
    import matplotlib.pyplot as plt
    pairs = [('free_settle_0', 'free_refined', 'Free settling'),
             ('feed_release_0', 'feed_refined', 'Feed / release')]
    if not all((root/name/'trajectory.npz').exists() for first, second, _ in pairs for name in (first, second)):
        return
    fig, axes = plt.subplots(2, 2, figsize=(10, 7), layout='constrained')
    for row, (first, second, label) in enumerate(pairs):
        with np.load(root/first/'trajectory.npz') as a, np.load(root/second/'trajectory.npz') as b:
            initial, initial_b = a['initial_centerline'], b['initial_centerline']
            coarse, fine = a['centerlines'][-1], b['centerlines'][-1]
        arc = np.r_[0., np.cumsum(np.linalg.norm(np.diff(initial, axis=0), axis=1))]
        arc_b = np.r_[0., np.cumsum(np.linalg.norm(np.diff(initial_b, axis=0), axis=1))]
        interpolated = np.column_stack([np.interp(arc/arc[-1], arc_b/arc_b[-1], fine[:, i]) for i in range(3)])
        error = np.linalg.norm(coarse-interpolated, axis=1)*1000
        axes[row, 0].plot(coarse[:, 0]*1000, coarse[:, 1]*1000, label='Baseline mesh')
        axes[row, 0].plot(fine[:, 0]*1000, fine[:, 1]*1000, '--', label='Refined mesh')
        axes[row, 0].set(title=label, xlabel='World x (mm)', ylabel='World y (mm)', aspect='equal')
        axes[row, 0].legend()
        axes[row, 1].plot(arc, error, color='C3')
        axes[row, 1].axhline(5., color='black', linestyle=':', label='Maximum difference limit')
        axes[row, 1].axvspan(0., .18, color='gray', alpha=.15)
        axes[row, 1].axvspan(arc[-1]-.18, arc[-1], color='gray', alpha=.15)
        axes[row, 1].set(xlabel='Initial material arc (m)', ylabel='3D centerline difference (mm)',
                         title='Final state; gray regions are free tails')
        axes[row, 1].legend()
    for axis in axes.ravel():
        axis.grid(alpha=.2)
    fig.savefig(root/'refinement_comparison.png', dpi=160)
    plt.close(fig)


def write_review(root):
    root = Path(root)
    root.mkdir(parents=True, exist_ok=True)
    experiments, rows = {}, []
    for phase, names in EXPECTED.items():
        for name in names:
            folder = root/name
            report_path = folder/'report.json'
            if report_path.exists():
                report = json.loads(report_path.read_text())
                state = 'passed' if evidence_satisfies_case(name, report) else 'failed'
                failed = [key for key, value in report.get('checks', {}).items() if not value]
                if report.get('error'):
                    failed.append(report['error'])
                if report.get('passed') and state != 'passed':
                    failed.append('Evidence duration or robot qualification is insufficient for this case')
                for key, value in report.get('actuation', {}).get('checks', {}).items():
                    if not value:
                        failed.append(key)
                plot_trace(folder)
                details = f"{report.get('simulated_seconds', 0):.3f} s; " + (', '.join(failed) or 'Local checks passed')
                link = f'[report]({name}/report.json)'
                if (folder/'diagnostics.png').exists():
                    link += f' · [plot]({name}/diagnostics.png)'
            else:
                state = 'running' if (folder/'progress.json').exists() else 'not_run'
                details, link = '尚无完整验收结果', ''
                if state == 'running':
                    progress = json.loads((folder/'progress.json').read_text())
                    details = f"已观察 {progress['time_s']:.3f} s"
            experiments[name] = dict(phase=phase, status=state)
            rows.append(f'| {phase} | {name} | {state} | {details.replace(chr(124), "/")} | {link} |')
    comparisons = {}
    for mode in ('free', 'feed'):
        base = root/('free_settle_0' if mode == 'free' else 'feed_release_0')
        for variant in ('half_step', 'refined', 'tighter'):
            other = root/f'{mode}_{variant}'
            if (base/'trajectory.npz').exists() and (other/'trajectory.npz').exists():
                comparisons[f'{mode}_{variant}'] = compare_centerlines(base, other)
    phases = {phase: all(experiments[name]['status'] == 'passed' for name in names)
              for phase, names in EXPECTED.items()}
    phases['P3'] &= len(comparisons) == 6 and all(c['passed'] for c in comparisons.values())
    auxiliary = {}
    auxiliary_rows = []
    for folder in sorted(root.iterdir()):
        if not folder.is_dir() or folder.name in experiments:
            continue
        if (folder/'report.json').exists():
            report = json.loads((folder/'report.json').read_text())
            plot_trace(folder)
            details = (str(report.get('error')) if report.get('error') else
                       f"{report.get('simulated_seconds', 0):.3f} s; local passed={report.get('passed', False)}")
            link = f'[report]({folder.name}/report.json)'
            if (folder/'diagnostics.png').exists():
                link += f' · [plot]({folder.name}/diagnostics.png)'
            auxiliary[folder.name] = dict(completed=True, error=report.get('error'),
                                         local_checks_passed=report.get('passed', False))
        elif (folder/'progress.json').exists():
            details = '运行中'
            link = f'[progress]({folder.name}/progress.json)'
            auxiliary[folder.name] = dict(completed=False)
        else:
            continue
        auxiliary_rows.append(f'| {folder.name} | {str(details).replace(chr(124), "/")} | {link} |')
    result = dict(complete_physics_suite_passed=all(phases.values()), phases=phases,
                  experiments=experiments, comparisons=comparisons,
                  auxiliary_probes=auxiliary,
                  full_untying_demo_qualified=False,
                  scope='Local FEM fixture tests do not certify robot interaction or untying')
    (root/'result.json').write_text(json.dumps(result, indent=2)+'\n')
    comparison_rows = []
    for name, comparison in comparisons.items():
        state = 'passed' if comparison['passed'] else 'failed'
        if 'key_states' in comparison:
            rms = max(s['rms_m'] for s in comparison['key_states'])*1000
            maximum = max(s['max_m'] for s in comparison['key_states'])*1000
            detail = f'RMS {rms:.3f} mm / max {maximum:.3f} mm'
        else:
            detail = comparison.get('reason', 'incomplete')
        comparison_rows.append(f'| {name} | {state} | {detail} |')
    plot_refinement(root)
    page = '# 解绳结物理验收\n\n未运行项目不计为通过。局部夹具测试不认证机器人抓持。\n\n'
    page += '[汇总 JSON](result.json)\n\n'
    page += ('完整物理验收通过' if result['complete_physics_suite_passed'] else '完整物理验收尚未通过')+'\n\n'
    page += ' / '.join(f'{phase}: '+('通过' if value else '未通过 / 未完成') for phase, value in phases.items())+'\n\n'
    if comparison_rows:
        page += '## 数值精度对照\n\n所有关键停留态须满足 RMS < 2 mm、max < 5 mm。\n\n'
        page += '| 对照 | 状态 | 结果 |\n| --- | --- | --- |\n'+'\n'.join(comparison_rows)+'\n\n'
    if (root/'refinement_comparison.png').exists():
        page += '[网格加密对照](refinement_comparison.png)\n\n'
    page += '## 独立物理实验\n\n| 阶段 | 实验 | 状态 | 结果 | 证据 |\n| --- | --- | --- | --- | --- |\n'
    page += '\n'.join(rows)+'\n\n## 诊断与接入试跑（不替代阶段验收）\n\n'
    page += '| 实验 | 结果 | 证据 |\n| --- | --- | --- |\n'+'\n'.join(auxiliary_rows)+'\n'
    (root/'README.md').write_text(page)
    return result


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('root', type=Path)
    print(json.dumps(write_review(parser.parse_args().root), indent=2))
