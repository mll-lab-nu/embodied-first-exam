"""Export measured arm trajectories and descriptive phase metrics.

Path length, stage count and grasp count do not certify manipulation difficulty.
"""
import argparse
import json
from pathlib import Path

import numpy as np


def export_motion(source, output):
    source, output = Path(source), Path(output)
    samples = json.loads((source/'contact_trace.json').read_text())
    report = json.loads((source/'report.json').read_text())
    if not samples:
        return None
    times = np.asarray([s['time_s'] for s in samples])
    if not np.all(np.diff(times) > 0):
        raise ValueError('Robot observation timestamps must be strictly increasing')
    arrays = dict(times_s=times, stage=np.asarray([s['stage'] for s in samples]))
    for side in ('left', 'right'):
        for field in ('arm_qpos', 'finger_qpos', 'hand_pos', 'hand_quat_wxyz'):
            arrays[f'{side}_{field}'] = np.asarray([s['robot'][side][field] for s in samples])
        arrays[f'{side}_tool_m'] = np.asarray([s[f'{side}_tool'] for s in samples])
        arrays[f'{side}_holding'] = np.asarray([side in s['owners'].values() for s in samples])
        if all('commanded_arm_qpos' in s for s in samples):
            arrays[f'{side}_commanded_arm_qpos'] = np.asarray([s['commanded_arm_qpos'][side] for s in samples])
    stages = {}
    # Summarize at 20 Hz so an almost stationary solver jitter is not presented
    # as useful manipulation travel. Raw 200 Hz observations remain in NPZ.
    selected = np.r_[0, np.flatnonzero(np.diff(np.floor(times/.05+1e-8)) > 0)+1]
    selected = np.unique(np.r_[selected, len(times)-1])
    for a, b in zip(selected[:-1], selected[1:]):
        stage = str(arrays['stage'][b])
        row = stages.setdefault(stage, dict(duration_s=0., left_tool_path_m=0., right_tool_path_m=0.,
                                           both_holding_s=0.))
        dt = float(times[b]-times[a])
        row['duration_s'] += dt
        for side in ('left', 'right'):
            row[f'{side}_tool_path_m'] += float(np.linalg.norm(arrays[f'{side}_tool_m'][b]-arrays[f'{side}_tool_m'][a]))
        if all(arrays[f'{side}_holding'][a] and arrays[f'{side}_holding'][b] for side in ('left', 'right')):
            row['both_holding_s'] += dt
    actuation = report['actuation']
    grasps = [e for e in actuation['events'] if e['event'] == 'contact_then_assisted_grasp']
    result = dict(scope='descriptive measured motion; no difficulty or precision qualification',
        untying_verified=bool(report.get('untying_verified')), stages=stages,
        recorded_duration_s=float(times[-1]), raw_observations=len(times),
        path_sampling_period_s=.05, physical_grasp_events=len(grasps),
        observed_regrasps=max(0, len(grasps)-len({e['owner'] for e in grasps})),
        route_id=actuation.get('route_id', actuation.get('route')),
        commanded_joint_targets_available='left_commanded_arm_qpos' in arrays,
        force_control_verified=False, continuous_precision_verified=False, difficulty_qualified=False)
    output.mkdir(parents=True, exist_ok=True)
    np.savez_compressed(output/'robot_motion.npz', **arrays)
    (output/'execution_metrics.json').write_text(json.dumps(result, indent=2)+'\n')
    return result


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('source', type=Path)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    print(json.dumps(export_motion(args.source, args.output), indent=2))
