"""Recorded GPU check of execution clocks and shared replay recording, not a solving proof."""
from pathlib import Path
import argparse
import importlib.util
import json
import sys
import traceback

import numpy as np


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--tool', type=Path, required=True)
    parser.add_argument('--task', required=True)
    parser.add_argument('--instance', type=Path)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--steps', type=int, default=5)
    parser.add_argument('--variation')
    parser.add_argument('--seed', type=int, default=0)
    args = parser.parse_args()
    if args.steps < 1:
        parser.error('steps must be positive')
    args.output.mkdir(parents=True, exist_ok=False)
    spec = importlib.util.spec_from_file_location('repair_tool', args.tool)
    tool = importlib.util.module_from_spec(spec); spec.loader.exec_module(tool)
    from topogym.utils.io import sha256_file
    import torch
    torch.set_num_threads(1)
    report = dict(status='running', physical=False, solvability_proven=False,
                  task=args.task, tool_sha256=sha256_file(args.tool), probe_sha256=sha256_file(__file__),
                  gpu=torch.cuda.get_device_name(), instance_sha256=sha256_file(args.instance) if args.instance else None)
    tool.atomic_json(args.output / 'report.json', report)
    session = None
    try:
        selection = dict(instance=args.instance) if args.instance else (
            dict(variation_id=args.variation, seed=args.seed) if args.variation else dict(eval_index=0))
        session = tool.Session(args.task, **selection)
        session.record_start()
        try:
            session.step(np.full(session.action_dim, np.nan))
            raise AssertionError('nonfinite action accepted')
        except ValueError:
            pass
        assert session.n_steps == 0 and len(session._recording) == 0
        before = session.env._world.physics_step
        session.start_video(args.output / 'live.mp4', fps=15)
        for _ in range(args.steps):
            if session.step(session.hold_action()):
                break
        report['physical'] = True
        status = session.status()
        assert status['physics_steps'] == session.env._world.physics_step - before
        assert abs(status['sim_time_s'] - status['physics_steps'] * session.env.config.physics_dt_s) < 1e-12
        # Save execution evidence before video finalization.
        report['live'] = status
        if session.episode_end is not None:
            before_counts = (session.n_steps, session.physics_steps, len(session._recording))
            for _ in range(5):
                assert session.step(session.hold_action())
            assert before_counts == (session.n_steps, session.physics_steps, len(session._recording))
            report['terminal_tail_ignored'] = True
        events = session.env._world.read_state().get('contact_events')
        if events:
            report['contact_coverage'] = dict(substeps_complete=events['substeps_complete'],
                sampled_substeps=events['sampled_substeps'], expected_substeps=events['expected_substeps'],
                snapshots=len(events.get('contact_snapshots') or []),
                maximum_penetration_per_substep_m=[float(np.max(x['contacts']['penetration'], initial=0))
                    for x in events.get('contact_snapshots') or []])
        tool.atomic_json(args.output / 'report.json', report)
        session.stop_video()
        actions = session.record_stop()
        session.save_trajectory(actions, args.output / 'trajectory.npz', meta=dict(live_rows=len(actions)))
        actions, ticks = tool.load_trajectory(args.output / 'trajectory.npz', args.task, session.action_dim, trusted=True)
        assert ticks is not None and int(ticks.sum()) == status['physics_steps']
        session.start_video(args.output / 'replay.mp4', fps=15)
        report['replay'] = session.replay(actions, physics_steps=ticks)
        tool.atomic_json(args.output / 'report.json', report)
        session.stop_video()
        # Verify a trusted partial control period without rounding it to ten ticks.
        session.reset()
        session.start_video(args.output / 'partial.mp4', fps=15)
        session.step(session.hold_action(), _physics_steps=3)
        assert session.physics_steps == 3 or (0 < session.physics_steps < 3 and session.episode_end is not None)
        assert abs(session.sim_time_s - session.physics_steps * session.env.config.physics_dt_s) < 1e-12
        report['partial'] = session.status()
        session.stop_video()
        report['recordings'] = []
        for manifest in args.output.glob('*.recording-*/recording/recording_manifest.json'):
            data = json.loads(manifest.read_text())
            assert data['recording_status'] == 'complete'
            frames = [json.loads(line) for line in (manifest.parent / 'frame_map.jsonl').read_text().splitlines()]
            assert frames[0]['physics_step'] == 0
            assert all(abs(f['source_sim_time_s'] - f['target_video_time_s']) <= 1 / data['fps'] + 1e-9 for f in frames)
            report['recordings'].append(str(manifest.relative_to(args.output)))
        assert len(report['recordings']) == 3
        report.update(status='passed', instance_matches=session.instance_matches, simulator_config=session.config)
    except BaseException as exc:
        report.update(status='failed', error=repr(exc), traceback=traceback.format_exc())
        raise
    finally:
        tool.atomic_json(args.output / 'report.json', report)
        if session is not None:
            session.close()


if __name__ == '__main__':
    main()
