#!/usr/bin/env python3
"""Freeze and execute the approved Claws low tiers using Env/SegmentRunner."""
import argparse
import json
import os
from pathlib import Path
import signal
import subprocess
import sys
import time
import traceback

ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT))


def worker(args):
    import numpy as np
    import torch
    from topogym.simulator import Env, SimulatorConfig, SegmentRunner
    from topogym.tasks.interlocked_claws.common import recommended_grasp_assist
    from topogym.planning.interlocked_claws.simplified_policy import SimplifiedClawsPolicy
    from topogym.planning.interlocked_claws.simplified_preflight import prepare
    from topogym.planning.interlocked_claws.simplified_routes import reference
    from topogym.simulator.rollout_simulation.segment_contract import fingerprint
    from topogym.utils.io import to_jsonable, write_json_atomic
    output=args.output
    report=dict(status='running',started=time.time(),variant=args.variant,seed=args.seed,
                task_success=False,from_task_pregrasp=True,geometry_path_verified=False,
                robot_execution_verified=False,qualification='one frozen instance; assisted grasp; not a difficulty ranking')
    write_json_atomic(output/'run_report.json',report)
    try:
        _,_,_,_,geo=reference(args.variant)
        write_json_atomic(output/'geometry_report.json',geo)
        report['geometry_path_verified']=True
        if args.part=='geometry':
            report['status']='geometry_passed'
            return
        torch.set_num_threads(1)
        config=SimulatorConfig(task_id='interlocked_claws',variation_id=args.variant,seed=args.seed,
            control_mode='EE_ABS',observation_mode='EE',enable_privileged=True,enable_rgb=not args.no_rgb,
            compute_backend=args.compute_backend,physics_dt_s=args.physics_dt,
            control_decimation=args.control_decimation,solver_substeps=args.solver_substeps,
            max_physics_steps=round(args.episode_seconds/args.physics_dt),work_dir=output/'scene',
            grasp_assist=recommended_grasp_assist(args.variant,args.seed))
        report['config']=to_jsonable(config)
        write_json_atomic(output/'run_report.json',report)
        with Env(config) as env:
            env.reset()
            report.update(instance_id=env._task.instance_id,asset_sha256=to_jsonable(env._asset_build.sha256),
                          terminal=env._task.terminal_metadata(),initial_task=to_jsonable(env._task.result))
            policy=SimplifiedClawsPolicy(part='acquire')
            report['events']=[];report['segments']=[]
            with SegmentRunner(env,output,prepared_output=True) as runner:
                with (output/'private/claws_monitor.jsonl').open('x',buffering=1) as monitor:
                    last=[None,-1.]
                    def tick(row):
                        record=dict(state=row['state'],phase=policy.phase,grasp=row['world']['grasp'],
                                    bodies={n:row['world']['bodies'][n] for n in ('piece_0','piece_1')},
                                    tracking=policy.tracking,task_result=env._task.result)
                        report['events'].extend(to_jsonable(row['world']['grasp']['events']))
                        monitor.write(json.dumps(to_jsonable(record),allow_nan=False)+'\n')
                        t=float(row['state']['sim_time_s'])
                        if policy.phase!=last[0] or t-last[1]>=1.:
                            write_json_atomic(output/'progress.json',record)
                            print(policy.phase,round(t,3),policy.tracking,flush=True)
                            last[:]=[policy.phase,t]
                    env.add_state_sink(tick)
                    manifest=json.loads((output/'run_source_manifest.json').read_text())
                    for part in ('acquire','solve'):
                        if part=='solve':
                            if args.part=='acquire': break
                            print('planning_native_ik_and_collision',flush=True)
                            motions,initial,offsets,audit=prepare(env,args.variant)
                            write_json_atomic(output/'preflight.json',audit)
                            if not audit['passed']: raise RuntimeError('Robot preflight failed; see preflight.json')
                            report['sampled_robot_path_verified']=True
                            policy=SimplifiedClawsPolicy(motions=motions,initial=initial,offsets=offsets)
                        result=runner.run_policy(request_id='claws-'+args.variant+'-'+part,policy=policy,
                            submission_hash=fingerprint(dict(source=manifest,variant=args.variant,part=part)),
                            mode='unlimited',state_fields=('world',))
                        report['segments'].append(to_jsonable(result))
                        if not result.get('evidence_complete') or not result.get('physics_tick_complete'):
                            raise RuntimeError('Incomplete execution evidence')
                        if part=='acquire' and result['reason']!='policy_done':
                            raise RuntimeError('Acquisition failed: '+result['reason'])
                    world=env._world.read_state()
                    report.update(task_success=bool(env._task.result.task_success),
                        task_result=to_jsonable(env._task.result),final_world=to_jsonable(world),
                        simulation_time_s=env._world.sim_time_s,physics_steps=env._world.physics_step,
                        last_phase=policy.phase,phase_endpoints=policy.samples,
                        statistics=runner._evidence.statistics())
                    success=report['task_success'] if args.part=='solve' else policy.completed
                    report['robot_execution_verified']=success and args.part=='solve'
                    if not success: raise RuntimeError('Reference did not reach Task success: '+str(report['segments'][-1]['reason']))
                    report['status']='passed' if args.part=='solve' else 'acquisition_passed'
    except BaseException:
        report.update(status='failed',error=traceback.format_exc())
        raise
    finally:
        report['wall_time_s']=time.time()-report['started']
        write_json_atomic(output/'run_report.json',report)


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--variant',choices=['very_easy','easier'],required=True)
    parser.add_argument('--output',type=Path,required=True)
    parser.add_argument('--part',choices=['geometry','acquire','solve'],default='solve')
    parser.add_argument('--seed',type=int,default=0)
    parser.add_argument('--compute-backend',choices=['cpu','cuda'],default='cuda')
    parser.add_argument('--no-rgb',action='store_true')
    parser.add_argument('--physics-dt',type=float,default=.0025)
    parser.add_argument('--control-decimation',type=int,default=10)
    parser.add_argument('--solver-substeps',type=int,default=4)
    parser.add_argument('--episode-seconds',type=float,default=600.)
    parser.add_argument('--worker',action='store_true',help=argparse.SUPPRESS)
    args=parser.parse_args();args.output=args.output.resolve()
    if args.worker: return worker(args)
    args.output.mkdir(parents=True,exist_ok=False)
    from scripts.test_policy_cube_transfer import snapshot
    source=snapshot(args.output)
    (args.output/'source_manifest.json').rename(args.output/'run_source_manifest.json')
    command=[sys.executable,str(source/'scripts/oracle_runners/run_interlocked_claws_simplified_policy.py'),
             '--worker','--variant',args.variant,'--output',str(args.output),'--part',args.part,
             '--seed',str(args.seed),'--compute-backend',args.compute_backend,'--physics-dt',str(args.physics_dt),
             '--control-decimation',str(args.control_decimation),'--solver-substeps',str(args.solver_substeps),
             '--episode-seconds',str(args.episode_seconds)]
    if args.no_rgb:command.append('--no-rgb')
    (args.output/'invocation.json').write_text(json.dumps(dict(command=command),indent=2)+'\n')
    import psutil
    with (args.output/'runtime.log').open('x') as log,(args.output/'resources.jsonl').open('x',buffering=1) as resources:
        process=subprocess.Popen(command,cwd=source,stdout=log,stderr=subprocess.STDOUT,start_new_session=True,
            env=dict(os.environ,PYTHONPATH=str(source),OMP_NUM_THREADS='1',OPENBLAS_NUM_THREADS='1',
                     TOPOGYM_VISUAL_ASSET_ROOT=str(ROOT/'.external/nyx-assets')))
        try:
            while process.poll() is None:
                row=dict(time=time.time(),cpu_percent=psutil.cpu_percent(),memory_percent=psutil.virtual_memory().percent)
                resources.write(json.dumps(row)+'\n')
                if row['memory_percent']>=90:raise RuntimeError('System memory reached 90%')
                time.sleep(1)
        finally:
            if process.poll() is None:
                os.killpg(process.pid,signal.SIGTERM)
                try:process.wait(timeout=10)
                except subprocess.TimeoutExpired:os.killpg(process.pid,signal.SIGKILL);process.wait()
    print('exit=',process.returncode,str(args.output),flush=True)
    raise SystemExit(process.returncode)


if __name__=='__main__':main()
