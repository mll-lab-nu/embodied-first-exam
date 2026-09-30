#!/usr/bin/env python3
"""Freeze and execute a Horseshoe oracle diagnostic from default ALOHA home.

No RGB; explicit CPU timing matches the existing finite-instance proof runs.
Pickup is a diagnostic and is never reported as a completed task proof.
"""
import argparse
import json
import os
from pathlib import Path
import subprocess
import signal
import sys
import time
import traceback

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))


def worker(args):
    if args.part=='geometry':
        from topogym.planning.rigid_reference.geometry import freeze_scene
        from topogym.planning.horseshoe_ring.oracle import load_reference,certify_reference
        from topogym.utils.io import write_json_atomic
        task,spec,scene,meshes,identity=freeze_scene('horseshoe_ring',args.variant,args.seed,args.output/'scene')
        frames,source=load_reference(args.reference,task.assembly)
        report=certify_reference(meshes,frames,progress=lambda i,q,g:print(i,q,g,flush=True),
                                 initial_geometry=spec.metadata['asset_report'])
        write_json_atomic(args.output/'object_certificate.json',dict(reference=source,scene=identity,**report))
        if not report['passed']:raise ValueError('Object reference failed current-asset certification')
        return
    import torch
    torch.set_num_threads(1)
    from topogym.simulator import Env,SimulatorConfig,SegmentRunner
    from topogym.planning.horseshoe_ring.policy import HorseshoePolicy
    from topogym.planning.horseshoe_ring.kinematics import HorseshoeIK,CheckedJointPolicy
    from topogym.planning.rigid_reference.geometry import interpolate
    from topogym.planning.rigid_reference.feedback import tcp_pose
    from topogym.utils.io import to_jsonable,write_json_atomic
    from topogym.utils.grasp import GraspAssistConfig,GraspTarget
    import numpy as np
    from scipy.spatial.transform import Rotation
    out=args.output
    requested=json.loads(args.grasps.read_text()) if args.grasps else None
    centers={s:tuple(requested[s]['candidates'][0]['point_local_m']) if requested else (0.,-.06,0.)
             for s in ('left','right')}
    targets=tuple(GraspTarget('horseshoe_'+s,'horseshoe_'+s,center_m=centers[s],radius_m=.04) for s in ('left','right'))
    if args.part in ('grasp_ring','extract','solve'):targets+= (GraspTarget('target_ring','target_ring',radius_m=.09),)
    config=SimulatorConfig(task_id='horseshoe_ring',variation_id=args.variant,robot_id='aloha',
        compute_backend='cpu',enable_rgb=False,enable_privileged=True,control_mode='JOINT_ABS',
        physics_dt_s=.025,solver_substeps=40,control_decimation=1,max_physics_steps=args.max_physics_steps,
        work_dir=out/'scene',grasp_assist=GraspAssistConfig(model='contact_weld_v1',targets=targets,
            max_tcp_distance_m=.09 if args.part in ('grasp_ring','extract','solve') else .06))
    report=dict(status='running',part=args.part,config=to_jsonable(config),seed=args.seed,
                accepted_proof=False,task_success=False,from_default_home=True,events=[])
    write_json_atomic(out/'run_report.json',report)
    try:
        with Env(config) as env:
            env.reset(seed=args.seed)
            report.update(instance_id=env._task.instance_id,initial_robot=to_jsonable(env._robot.observe()))
            report['contact_link_names']={str(link.idx):f'{name}/{link.name}' for name,entity in env._world.entities.items()
                                          for link in getattr(entity,'links',())}
            report['grasp_finger_links']={s:[int(env._robot.entity.get_link(n).idx) for n in g.grasp.finger_links]
                                         for s,g in env._robot.groups.items()}
            # Preserve the actual runtime identities even if a resource stop
            # prevents the worker's final report from being written.
            write_json_atomic(out/'run_report.json',report)
            if args.part=='plan' and args.reference:
                from topogym.planning.horseshoe_ring.oracle import load_reference
                from topogym.planning.horseshoe_ring.kinematics import plan_oracle
                reference,identity=load_reference(args.reference,env._task.assembly)
                if args.retarget_plan:
                    from topogym.planning.horseshoe_ring.level import retarget_horizontal_fold
                    from topogym.planning.rigid_reference.feedback import body_pose,relative_pose
                    state=env._world.read_state()
                    offsets={s:relative_pose(body_pose(state['bodies']['horseshoe_'+s]),
                        (np.asarray(row['candidates'][0]['tcp_position_m']),
                         Rotation.from_quat(np.roll(row['candidates'][0]['tcp_quaternion_wxyz'],-1))))
                        for s,row in requested.items()}
                    candidate=retarget_horizontal_fold(HorseshoeIK(env),offsets,
                        json.loads(args.retarget_plan.read_text()),
                        progress=lambda phase,index:print(phase,index,flush=True))
                    planned=dict(passed=candidate['passed'],fold_plan=candidate,grasps=requested)
                else:
                    planned=plan_oracle(env,reference[:identity['fold_end_index']+1],progress=lambda row:print(row,flush=True))
                if planned['passed'] and args.level_after_flip:
                    from topogym.planning.horseshoe_ring.level import plan_horizontal_fold
                    from topogym.planning.rigid_reference.feedback import body_pose,relative_pose
                    state=env._world.read_state()
                    offsets={s:relative_pose(body_pose(state['bodies']['horseshoe_'+s]),
                        (np.asarray(row['candidates'][0]['tcp_position_m']),
                         Rotation.from_quat(np.roll(row['candidates'][0]['tcp_quaternion_wxyz'],-1))))
                        for s,row in planned['grasps'].items()}
                    initial=planned['fold_plan']
                    planned['fold_plan']=plan_horizontal_fold(HorseshoeIK(env),reference[:identity['fold_end_index']+1],
                        offsets,initial,center=args.level_center,joint_margin=args.joint_margin,
                        progress=lambda phase,index:print(phase,index,flush=True))
                    planned['initial_fold_plan']=initial
                    planned['passed']=planned['fold_plan']['passed']
                write_json_atomic(out/'oracle_plan.json',dict(reference=identity,**planned))
                if not planned['passed']:raise ValueError('No complete fold candidate in the planning budget')
                write_json_atomic(out/'grasp_selection.json',planned['grasps'])
                write_json_atomic(out/'fold_plan.json',planned['fold_plan'])
                report['status']='fold_ik_candidate_passed'
                return
            ik=HorseshoeIK(env)
            if args.grasps:
                selection=requested
                grasps={s:selection[s]['candidates'][0] for s in ('left','right')}
            else:
                selection={}
                for s in ('left','right'):
                    rows,rejected=ik.grasp_candidates(env._task,env._world.read_state(),s)
                    selection[s]=dict(candidates=rows,rejected=rejected)
                    if not rows:raise ValueError(f'No collision-free grasp candidate for {s}: {rejected}')
                grasps={s:selection[s]['candidates'][0] for s in selection}
            write_json_atomic(out/'grasp_selection.json',selection)
            # Read-only, sampled native IK of the actual Cartesian approach.
            q=ik.seed.copy()
            for s,g in grasps.items():q[env._robot._q_indices[s][6:]]=g.get('open_position_m',.027)
            initial={s:tcp_pose(v) for s,v in env._robot.observe().items()}
            paths=[]
            q_start=q.copy();q_end=q.copy()
            for s,g in grasps.items():
                indices=env._robot._q_indices[s][:6]
                q_end[indices]=np.asarray(g['pre_qpos'])[indices]
            for u in np.linspace(0,1,101):
                q=q_start+u*(q_end-q_start);checked=ik.check(q)
                paths.append(dict(phase='above',fraction=u,qpos=q.tolist(),**checked))
                if not checked['passed']:
                    write_json_atomic(out/'approach_plan.json',paths)
                    raise ValueError(f'Joint approach collision: {paths[-1]}')
            initial={s:(np.asarray(g['tcp_position_m'])+[0,0,.08],Rotation.from_quat(np.roll(g['tcp_quaternion_wxyz'],-1))) for s,g in grasps.items()}
            for phase,height in (('descend',0.),):
                target={s:(np.asarray(g['tcp_position_m'])+[0,0,height],Rotation.from_quat(np.roll(g['tcp_quaternion_wxyz'],-1))) for s,g in grasps.items()}
                for u in np.linspace(0,1,61)[1:]:
                    for s in grasps:q=ik.solve(s,interpolate(initial[s],target[s],u),q)
                    checked=ik.check(q,contacts={s:'horseshoe_'+s for s in grasps} if phase=='descend' and u>.85 else None)
                    paths.append(dict(phase=phase,fraction=u,qpos=q.tolist(),**checked))
                    if not checked['passed']:
                        write_json_atomic(out/'approach_plan.json',paths)
                        raise ValueError(f'Approach collision: {paths[-1]}')
                initial=target
            write_json_atomic(out/'approach_plan.json',paths)
            if args.part=='plan':
                report['status']='ik_candidate_passed'
                return
            fold=None
            if args.part in ('fold','support','grasp_ring','extract','solve'):
                from topogym.planning.horseshoe_ring.oracle import load_reference,expand_coupled_plan
                reference,reference_identity=load_reference(args.reference,env._task.assembly)
                fold=expand_coupled_plan(reference,json.loads(args.fold_plan.read_text()))
            support=None
            if args.support_plan:
                from topogym.planning.rigid_reference.feedback import body_pose
                support_data=json.loads(args.support_plan.read_text())
                if not support_data['passed']:raise ValueError('Support plan failed its checks')
                support=[body_pose(f['bodies']['horseshoe_left']) for f in support_data['trajectory']]
                if len(support)<2:raise ValueError('Support motion needs at least two poses')
            planner=None
            if args.part in ('support','grasp_ring','extract','solve'):
                from topogym.planning.horseshoe_ring.manipulation import ManipulationPlanner
                planner=ManipulationPlanner(env,out/'online_plans',ik,reference=reference,
                    fold_end_index=reference_identity['fold_end_index'])
            policy=CheckedJointPolicy(HorseshoePolicy(grasps,part=args.part,fold=fold,support=support,planner=planner,
                                                     settle_tilt_deg=args.settle_tilt_deg,
                                                     settle_axis=args.settle_axis,
                                                     settle_secondary_y_deg=args.settle_secondary_y_deg,
                                                     settle_translation=args.settle_translation,
                                                     withdrawal_mode=args.withdrawal_mode,
                                                     fold_tracking_m=args.fold_tracking_m),env._robot)
            with SegmentRunner(env,out,prepared_output=True) as runner:
                with (out/'private/horseshoe_monitor.jsonl').open('x',buffering=1) as monitor:
                    last=[None]
                    def tick(row):
                        item=dict(state=row['state'],world=row['world'],task=row['task'],phase=policy.phase,diagnostics=policy.diagnostics)
                        monitor.write(json.dumps(to_jsonable(item),allow_nan=False)+'\n')
                        report['events'].extend(to_jsonable(row['world']['grasp']['events']))
                        if policy.phase!=last[0] or row['state']['physics_step']%100==0:
                            write_json_atomic(out/'progress.json',item)
                        if policy.phase!=last[0]:
                            print(policy.phase,row['state']['sim_time_s'],flush=True);last[0]=policy.phase
                    env.add_state_sink(tick);tick(env.tick_record())
                    result=runner.run_policy(request_id='horseshoe-'+args.part,policy=policy,
                        submission_hash=runner.env._task.instance_id,mode='unlimited',state_fields=('world',))
                    report.update(segment=to_jsonable(result),final_world=to_jsonable(env._world.read_state()),
                        final_robot=to_jsonable(env._robot.observe()),
                        task_result=to_jsonable(env._task.result),task_success=bool(env._task.result.task_success),
                        last_phase=policy.phase,physics_steps=env._world.physics_step)
                    if result['reason']!='policy_done' and not report['task_success']:
                        segments=json.loads((out/'report.json').read_text()).get('segments',[])
                        report['policy_errors']=segments[-1].get('errors',[]) if segments else []
                        raise RuntimeError(f"Incomplete {args.part}: {result['reason']}; {report['policy_errors']}")
                    report['status']=args.part+'_diagnostic_passed'
    except BaseException:
        report.update(status='failed',error=traceback.format_exc());raise
    finally:
        write_json_atomic(out/'run_report.json',report)


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output',type=Path,required=True)
    parser.add_argument('--variant',choices=('easy','medium','hard'),default='easy')
    parser.add_argument('--seed',type=int,default=0)
    parser.add_argument('--part',choices=('geometry','plan','pickup','fold','support','grasp_ring','extract','solve'),default='pickup')
    parser.add_argument('--grasps',type=Path)
    parser.add_argument('--reference',type=Path)
    parser.add_argument('--fold-plan',type=Path)
    parser.add_argument('--retarget-plan',type=Path,help='Retarget a checked horizontal plan with wrist reserve and a small tilt')
    parser.add_argument('--support-plan',type=Path)
    parser.add_argument('--level-after-flip',action='store_true',help='Plan a horizontal fold after the initial flip')
    parser.add_argument('--level-center',type=float,nargs=3,default=(-.22,.08,1.32),metavar=('X','Y','Z'))
    parser.add_argument('--joint-margin',type=float,default=.15,help='Joint reserve in radians for the horizontal planner')
    parser.add_argument('--settle-tilt-deg',type=float,default=0.)
    parser.add_argument('--settle-axis',choices=('x','y','z'),default='y')
    parser.add_argument('--settle-secondary-y-deg',type=float,default=0.)
    parser.add_argument('--settle-translation',type=float,nargs=3,default=(0.,0.,0.))
    parser.add_argument('--fold-tracking-m',type=float,default=.001)
    parser.add_argument('--withdrawal-mode',choices=('full','staged','joint-staged'),default='full')
    parser.add_argument('--max-physics-steps',type=int,default=48000,
                        help='Episode tick budget; does not change the 25 ms / 40-substep physics profile')
    parser.add_argument('--worker',action='store_true',help=argparse.SUPPRESS)
    args=parser.parse_args();args.output=args.output.resolve()
    if args.max_physics_steps<1:parser.error('--max-physics-steps must be positive')
    if args.part=='geometry' and args.reference is None:parser.error('--part geometry requires --reference body_poses.json')
    if args.level_after_flip and (args.part!='plan' or args.reference is None):parser.error('--level-after-flip requires --part plan and --reference')
    if args.retarget_plan and (args.part!='plan' or args.reference is None or args.grasps is None or args.level_after_flip):
        parser.error('--retarget-plan requires --part plan, --reference and --grasps, without --level-after-flip')
    if args.part in ('fold','support','grasp_ring','extract','solve') and (args.reference is None or args.fold_plan is None):parser.error('Fold execution requires --reference and --fold-plan')
    if args.part in ('support','grasp_ring','extract','solve') and args.support_plan is None:parser.error('Support execution requires --support-plan')
    if args.worker:return worker(args)
    args.output.mkdir(parents=True,exist_ok=False)
    from scripts.test_policy_cube_transfer import snapshot
    source=snapshot(args.output)
    (args.output/'source_manifest.json').rename(args.output/'run_source_manifest.json')
    command=[sys.executable,str(source/'scripts/run_horseshoe_policy.py'),'--worker','--output',str(args.output),
             '--variant',args.variant,'--seed',str(args.seed),'--part',args.part,'--settle-tilt-deg',str(args.settle_tilt_deg),
             '--settle-translation',*[str(v) for v in args.settle_translation],'--fold-tracking-m',str(args.fold_tracking_m),
             '--settle-axis',args.settle_axis,'--settle-secondary-y-deg',str(args.settle_secondary_y_deg),
             '--withdrawal-mode',args.withdrawal_mode,'--max-physics-steps',str(args.max_physics_steps)]
    if args.level_after_flip:command+=['--level-after-flip','--level-center',*[str(v) for v in args.level_center],
                                      '--joint-margin',str(args.joint_margin)]
    if args.grasps:
        target=args.output/'requested_grasps.json';target.write_bytes(args.grasps.read_bytes())
        command+=['--grasps',str(target)]
    if args.reference:
        target=args.output/'requested_reference.json';target.write_bytes(args.reference.read_bytes())
        command+=['--reference',str(target)]
    if args.fold_plan:
        target=args.output/'requested_fold_plan.json';target.write_bytes(args.fold_plan.read_bytes())
        command+=['--fold-plan',str(target)]
    if args.retarget_plan:
        target=args.output/'requested_retarget_plan.json';target.write_bytes(args.retarget_plan.read_bytes())
        command+=['--retarget-plan',str(target)]
    if args.support_plan:
        target=args.output/'requested_support_plan.json';target.write_bytes(args.support_plan.read_bytes())
        command+=['--support-plan',str(target)]
    (args.output/'invocation.json').write_text(json.dumps(dict(command=command),indent=2))
    with (args.output/'runtime.log').open('x') as log:
        process=subprocess.Popen(command,cwd=source,stdout=log,stderr=subprocess.STDOUT,start_new_session=True,
            env=dict(os.environ,PYTHONPATH=str(source),OMP_NUM_THREADS='1',OPENBLAS_NUM_THREADS='1',MKL_NUM_THREADS='1'))
        import psutil
        psutil.cpu_percent()
        try:
            with (args.output/'resources.jsonl').open('x',buffering=1) as resources:
                while process.poll() is None:
                    time.sleep(1)
                    mem=psutil.virtual_memory()
                    row=dict(time=time.time(),memory_percent=100*(1-mem.available/mem.total),
                             available_bytes=mem.available,cpu_percent=psutil.cpu_percent())
                    resources.write(json.dumps(row)+'\n')
                    if row['memory_percent']>=90:
                        (args.output/'resource_stop.json').write_text(json.dumps(row,indent=2))
                        print('Paused at resource limit',row,flush=True)
                        raise SystemExit(90)
        except KeyboardInterrupt:
            (args.output/'interruption.json').write_text(json.dumps(dict(status='interrupted',accepted_proof=False)))
            raise
        finally:
            if process.poll() is None:
                os.killpg(process.pid,signal.SIGTERM)
                try:process.wait(timeout=10)
                except subprocess.TimeoutExpired:
                    os.killpg(process.pid,signal.SIGKILL)
                    process.wait()
    print(f'exit={process.returncode}; {args.output}',flush=True)
    raise SystemExit(process.returncode)


if __name__=='__main__':main()
