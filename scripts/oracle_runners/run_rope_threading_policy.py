#!/usr/bin/env python3
"""Run an explicitly exploratory simplified-threading policy from ALOHA home.

Uses native FEM/IPC, shared contact-gated soft grasp, and SegmentRunner's
continuous evidence/recording. Pickup and task success are distinct results.
"""
import argparse
import json
import os
from pathlib import Path
import signal
import subprocess
import sys
import time
import traceback

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))


def worker(args):
    import torch
    from topogym.simulator import Env, SimulatorConfig, SegmentRunner
    from topogym.tasks.rope_threading.simplified import recommended_grasp_assist
    from topogym.planning.rope_threading.policy import ThreadingPolicy
    from topogym.simulator.rollout_simulation.segment_contract import fingerprint
    from topogym.utils.io import to_jsonable, write_json_atomic
    torch.set_num_threads(1)
    config = SimulatorConfig(task_id='rope_threading', variation_id=args.variant, seed=args.seed,
        control_mode='JOINT_ABS', observation_mode='EE', enable_privileged=True,
        enable_rgb=not args.no_rgb, compute_backend='cuda', history_storage='segment',
        physics_dt_s=args.physics_dt, solver_substeps=args.solver_substeps, control_decimation=1,
        max_physics_steps=round(args.episode_seconds/args.physics_dt), work_dir=args.output/'scene',
        ipc_options=dict(newton_tolerance=1e-4, linear_system_tolerance=1e-5,
                         collision_detection_method='linear_bvh'),
        grasp_assist=recommended_grasp_assist(args.variant))
    report = dict(status='building', started=time.time(), variant=args.variant, seed=args.seed,
        config=to_jsonable(config), from_default_home=True, task_success=False, pickup_passed=False,
        qualification='unqualified', scope='exploratory contact-gated robot execution; explicit solver timing',
        part=args.part, speed_scale=args.speed_scale, grasp_events=[])
    write_json_atomic(args.output/'run_report.json', report)
    try:
        with Env(config) as env:
            env.reset()
            report.update(status='running', instance=to_jsonable(env.episode_metadata),
                          initial_robot=to_jsonable(env._robot.observe()),
                          initial_task=to_jsonable(env._task.result))
            write_json_atomic(args.output/'run_report.json', report)
            with SegmentRunner(env, args.output, prepared_output=True) as runner:
                policy = ThreadingPolicy(env, part=args.part, speed_scale=args.speed_scale)
                last = [None, -1.]
                def tick(row):
                    report['grasp_events'].extend(to_jsonable(row['world']['grasp']['events']))
                    now = row['state']['sim_time_s']
                    if policy.phase != last[0] or now-last[1] >= .25:
                        write_json_atomic(args.output/'progress.json', dict(state=row['state'], phase=policy.phase,
                            tracking=policy.tracking, task=to_jsonable(env._task.result),
                            grasp=row['world']['grasp'], ipc=row['world']['ipc']))
                        write_json_atomic(args.output/'planning.json', policy.planning)
                        print(policy.phase, round(now, 4), policy.tracking, flush=True)
                        last[:] = [policy.phase, now]
                env.add_state_sink(tick)
                segment = runner.run_policy(request_id='from-home', policy=policy,
                    submission_hash=fingerprint(dict(variant=args.variant, part=args.part, seed=args.seed,
                                                      speed_scale=args.speed_scale)),
                    mode='unlimited', state_fields=('world',))
                report.update(segment=to_jsonable(segment), task_result=to_jsonable(env._task.result),
                    task_success=bool(env._task.result.task_success), pickup_passed=policy.pickup_passed,
                    physics_steps=env._world.physics_step, simulation_time_s=env._world.sim_time_s,
                    last_phase=policy.phase, statistics=runner._evidence.statistics())
                complete = bool(segment.get('evidence_complete') and segment.get('physics_tick_complete'))
                report['status'] = ('task_success' if report['task_success'] and complete else
                    'task_failure' if env._task.result.terminated and not report['task_success'] else
                    'pickup_passed' if args.part == 'pickup' and policy.pickup_passed and complete else 'incomplete')
    except BaseException as error:
        report.update(status='error', error=f'{type(error).__name__}: {error}', traceback=traceback.format_exc())
        raise
    finally:
        report['elapsed_s'] = time.time()-report['started']
        write_json_atomic(args.output/'run_report.json', report)
    if report['status'] not in {'task_success', 'pickup_passed'}:
        raise SystemExit(1)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--variant', choices=('very_easy', 'easier'), required=True)
    parser.add_argument('--output', type=lambda p: Path(p).resolve(), required=True)
    parser.add_argument('--part', choices=('pickup', 'solve'), default='solve')
    parser.add_argument('--seed', type=int, default=0)
    parser.add_argument('--physics-dt', type=float, default=.0025)
    parser.add_argument('--solver-substeps', type=int, default=4)
    parser.add_argument('--episode-seconds', type=float, default=120.)
    parser.add_argument('--wall-timeout', type=float, default=7200.)
    parser.add_argument('--speed-scale', type=float, default=1.)
    parser.add_argument('--no-rgb', action='store_true')
    parser.add_argument('--worker', action='store_true', help=argparse.SUPPRESS)
    args = parser.parse_args()
    if args.worker:
        return worker(args)
    if min(args.physics_dt, args.episode_seconds, args.wall_timeout) <= 0 or args.solver_substeps < 1 or not 0 < args.speed_scale <= 3:
        parser.error('Timing and substeps must be positive')
    args.output.mkdir(parents=True, exist_ok=False)
    from scripts.test_policy_cube_transfer import snapshot
    source = snapshot(args.output)
    (args.output/'source_manifest.json').rename(args.output/'run_source_manifest.json')
    command = [sys.executable, str(source/'scripts/oracle_runners/run_rope_threading_policy.py'),
               *sys.argv[1:], '--worker']
    (args.output/'invocation.json').write_text(json.dumps(dict(command=command), indent=2)+'\n')
    import psutil
    os.sched_setaffinity(0, sorted(os.sched_getaffinity(0))[:4])
    start, stop = time.time(), None
    with (args.output/'runtime.log').open('x') as log, (args.output/'resources.jsonl').open('x', buffering=1) as resources:
        child = subprocess.Popen(command, cwd=ROOT, stdout=log, stderr=subprocess.STDOUT,
            start_new_session=True, env=dict(os.environ, PYTHONPATH=str(source), OMP_NUM_THREADS='1',
                OPENBLAS_NUM_THREADS='1', MKL_NUM_THREADS='1', PYOPENGL_PLATFORM='egl',
                TOPOGYM_VISUAL_ASSET_ROOT=str(ROOT/'.external/nyx-assets')))
        try:
            while child.poll() is None:
                row = dict(pid=child.pid, elapsed_s=time.time()-start, cpu_percent=psutil.cpu_percent(),
                           memory_percent=psutil.virtual_memory().percent)
                resources.write(json.dumps(row)+'\n')
                if row['memory_percent'] >= 90 or row['elapsed_s'] >= args.wall_timeout:
                    stop = 'memory_limit' if row['memory_percent'] >= 90 else 'wall_timeout'
                    break
                time.sleep(1)
        finally:
            if child.poll() is None:
                os.killpg(child.pid, signal.SIGTERM)
                try:
                    child.wait(timeout=10)
                except subprocess.TimeoutExpired:
                    os.killpg(child.pid, signal.SIGKILL)
                    child.wait()
    result = dict(exit_code=child.returncode, stop_reason=stop, elapsed_s=time.time()-start)
    (args.output/'process_result.json').write_text(json.dumps(result, indent=2)+'\n')
    print(json.dumps(result), flush=True)
    raise SystemExit(child.returncode if child.returncode >= 0 else 1)


if __name__ == '__main__':
    main()
