#!/usr/bin/env python3
"""Check a frozen knot candidate's complete restore, home hold and pickup IK.

Uses the selected native Session and shared recorder. A successful check is
initial-state evidence, not a robot grasp/solution or Harbor qualification.
"""
from pathlib import Path
import argparse
import json
import sys
import traceback
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from topogym.planning.knot_untying.artifacts import load_tooling, validate_instance
from topogym.planning.knot_untying.cli import freeze_sources, supervise
from topogym.utils.io import write_json_atomic, to_jsonable


def worker(args):
    import numpy as np
    from topogym.assets.geometry.knot_untying import projected_crossings, template_diagram_matches
    from topogym.planning.knot_untying.robot_oracle import Runner, TIERS
    from topogym.planning.knot_untying.route_rule import choose, only_local_loops
    from topogym.planning.knot_untying.simplified_policy import BELOW_EASY, reachable_withdrawal
    from topogym.recording import RecordingSession
    from topogym.recording.encoding import probe
    from topogym.recording.segment import save_rgb

    instance = json.loads(args.instance.read_text())
    variation = instance['simulator']['variation_id']
    validate_instance(args.instance, variation)
    report = dict(status='running', scope='native initial-state restore, short home hold and read-only pickup IK',
                  instance=str(args.instance), variation=variation, full_solution_verified=False)
    session = None
    try:
        session = load_tooling(variation, args.tooling).Session('knot_untying', instance=args.instance)
        env = session.env
        runner = Runner(SimpleNamespace(variation=variation, instance=args.instance, output=args.output), session=session)
        family = env._task.layout.family
        initial_sha = session.state_sha()
        first = np.asarray(env._world.read_state()['fem']['rope']['position_m']).copy()

        def sample():
            state = env._world.read_state()['fem']['rope']
            points = np.asarray(state['position_m'])
            crossing = projected_crossings(runner.line())
            return dict(time_s=session.sim_time_s, crossings=crossing,
                        authored_projection_matches=template_diagram_matches(crossing, family),
                        maximum_node_displacement_m=float(np.linalg.norm(points-first, axis=1).max()),
                        maximum_speed_m_s=float(np.linalg.norm(state['velocity_m_s'], axis=1).max()),
                        finite=bool(np.isfinite(points).all()), task_result=to_jsonable(env._task.result))

        report.update(instance_exact=session.instance_exact, instance_matches=session.instance_matches,
                      initial_state_sha=initial_sha, samples=[sample()])
        frame = env.sensor_frame()
        report['initial_frames'] = save_rgb(args.output, 'initial', frame)
        write_json_atomic(args.output/'report.json', report)
        line = runner.line()
        crossing = projected_crossings(line)
        grasps = []
        try:
            if only_local_loops(crossing, runner.stations):
                stations = (.035, runner.length-.035)
            else:
                route = (reachable_withdrawal(runner, TIERS[variation]) if variation in BELOW_EASY else
                         choose(line, runner.stations, crossing, runner.length))
                if route is None:
                    raise ValueError('No under-crossing pickup candidate')
                report['pickup_route'] = route
                stations = (route['s_anchor'], route['s_pull'])
            sides = runner.arms_for(stations)
            for side, station in zip(sides, stations):
                selected, opening = runner.grasp_site(station)
                tcp, turn, flip, joints = runner.pose(side, selected)
                grasps.append(dict(side=side, requested_station_m=station, selected_station_m=selected,
                                   opening_m=opening, tcp_m=tcp.tolist(), orientation_xyzw=turn.as_quat().tolist(),
                                   pregrasp_joints_rad=joints.tolist(), flip=flip))
            report['pickup_ik'] = dict(reachable=True, grasps=grasps,
                                       scope='read-only endpoints; no continuous approach or physical grasp certificate')
        except (ValueError, RuntimeError) as error:
            report['pickup_ik'] = dict(reachable=False, grasps=grasps, error=str(error))
        assert session.physics_steps == 0
        session.record_start()
        with RecordingSession(args.output/'recording', metadata=dict(scope=report['scope'])) as recording:
            recording.append(frame)
            for index in range(args.steps):
                ended = session.step(session.hold_action())
                frame = env.sensor_frame()
                recording.append(frame)
                if index % 10 == 9 or ended:
                    report['samples'].append(sample())
                    write_json_atomic(args.output/'report.json', report)
                if ended:
                    break
            report['samples'].append(sample())
            report['final_frames'] = save_rgb(args.output, 'after_hold', frame)
            recording.append_final(frame)
        actions = session.record_stop()
        session.save_trajectory(actions, args.output/'hold_trajectory.npz')
        report['executed_steps'] = session.n_steps
        report['safety'] = session.safety(episode=True)
        report['videos'] = {p.stem: probe(p, decode=True) for p in (args.output/'recording/videos').glob('*.mp4')}
        session.reset()
        report['reset_state_sha'] = session.state_sha()
        report['reset_exact'] = report['reset_state_sha'] == initial_sha
        samples = report['samples']
        report['checks'] = dict(
            fresh_process_restore_exact=session.instance_exact,
            reset_exact=report['reset_exact'],
            pickup_ik_reachable=report['pickup_ik']['reachable'],
            requested_hold_completed=report['executed_steps'] == args.steps,
            crossing_diagram_preserved=all(row['authored_projection_matches'] for row in samples),
            initially_unsolved_and_no_failure=all(not row['task_result']['terminated'] for row in samples),
            finite=all(row['finite'] for row in samples),
            drift_under_5mm=max(row['maximum_node_displacement_m'] for row in samples) <= .005,
            final_speed_under_10mm_s=samples[-1]['maximum_speed_m_s'] <= .010)
        report['status'] = 'passed' if all(report['checks'].values()) else 'failed'
    except BaseException:
        report.update(status='error', error=traceback.format_exc())
        raise
    finally:
        write_json_atomic(args.output/'report.json', report)
        if session is not None:
            session.close()
    return 0 if report['status'] == 'passed' else 1


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--instance', type=Path, required=True)
    p.add_argument('--tooling', type=Path, required=True)
    p.add_argument('--output', type=Path, required=True)
    p.add_argument('--steps', type=int, default=40)
    p.add_argument('--worker', action='store_true', help=argparse.SUPPRESS)
    args = p.parse_args()
    args.instance, args.tooling, args.output = args.instance.resolve(), args.tooling.resolve(), args.output.resolve()
    if args.steps < 1:
        p.error('--steps must be positive')
    if args.worker:
        return worker(args)
    args.output.mkdir(parents=True, exist_ok=False)
    source = freeze_sources(args.output, args.tooling)
    command = [sys.executable, str(source/'scripts/check_knot_initial_states.py'), '--worker',
               '--instance', str(args.instance), '--tooling', str(source/'oracle_tooling'/args.tooling.name),
               '--output', str(args.output), '--steps', str(args.steps)]
    write_json_atomic(args.output/'command.json', command)
    return supervise(command, args.output, source)


if __name__ == '__main__':
    raise SystemExit(main())
