"""Horseshoe adapter for the existing live qualification workflow.

Diagnostic rewind uses the public same-episode interface. It is never accepted
as a complete proof; a selected recipe must run continuously from home.
"""
from copy import deepcopy
import json
from pathlib import Path

import numpy as np

from topogym.planning.solvability import Stage, Step
from topogym.planning.rigid_reference.feedback import body_pose
from topogym.utils.io import sha256_file, to_jsonable, write_json_atomic
from .kinematics import HorseshoeIK, CheckedJointPolicy
from .manipulation import ManipulationPlanner
from .oracle import load_reference, expand_coupled_plan
from .policy import HorseshoePolicy


TRACKER_FIELDS=('grip','bias','angle_bias','held_entities','offsets')


class ContinuationPolicy(HorseshoePolicy):
    def __init__(self, *args, operation, tracker, **kwargs):
        super().__init__(*args, **kwargs)
        self.operation,self.tracker=operation,deepcopy(tracker)

    def actions(self):
        for name,value in self.tracker.items():setattr(self,name,deepcopy(value))
        yield from getattr(self,self.operation)()


def stages(env, context):
    """Require a prefix selection binding the five oracle input files by hash."""
    out=context.output;holder=[None];shared={};attempt=[0]
    monitor=(out/'private/horseshoe_monitor.jsonl').open('x',buffering=1)
    identity=dict(config=to_jsonable(env.config),seed=context.identity['seed'],
        instance_id=env._task.instance_id,from_default_home=True,
        contact_link_names={str(link.idx):f'{name}/{link.name}' for name,entity in env._world.entities.items()
                            for link in getattr(entity,'links',())},
        grasp_finger_links={s:[int(env._robot.entity.get_link(n).idx) for n in g.grasp.finger_links]
                            for s,g in env._robot.groups.items()})
    write_json_atomic(out/'horseshoe_runtime_identity.json',identity)
    last_phase=[None]

    def tick(row):
        policy=holder[0]
        phase=policy.phase if policy else 'created'
        item=dict(state=row['state'],world=row['world'],task=row['task'],phase=phase,
                  diagnostics=policy.diagnostics if policy else {})
        monitor.write(json.dumps(to_jsonable(item),allow_nan=False)+'\n')
        if phase!=last_phase[0] or row['state']['physics_step']%100==0:
            write_json_atomic(out/'progress.json',item)
        if phase!=last_phase[0]:print(phase,row['state']['sim_time_s'],flush=True)
        last_phase[0]=phase

    unsubscribe=env.add_state_sink(tick);tick(env.tick_record())

    def common(row, limit=.001):
        world=row['world'];task_links={i for name in env._task.placement_vertices
                                       for i in world['bodies'][name]['link_indices']}
        contacts=world['contacts']
        depth=max((float(d) for a,b,d in zip(contacts['link_a'],contacts['link_b'],contacts['penetration'])
                   if a in task_links or b in task_links),default=0.)
        result=row['task']['result']
        return dict(task_not_failed=not (result['terminated'] and not result['task_success']),
                    task_contact_within_stage_limit=depth<=limit)

    def holding(row):
        hands=row['world']['grasp']['hands']
        return {side+'_holds_expected_body':bool(hands[side]['binding'] and
                    hands[side]['binding']['target'][0]==name)
                for side,name in (('left','target_ring'),('right','horseshoe_right'))}

    def prefix(parameters):
        paths={}
        inputs=out/'oracle_inputs';inputs.mkdir(exist_ok=True)
        for name in ('grasps','reference','fold','support','approach'):
            item=parameters[name];source=Path(item['path'])
            if sha256_file(source)!=item['sha256']:raise ValueError(f'Changed {name} input')
            destination=inputs/(name+'.json')
            if destination.exists() and sha256_file(destination)!=item['sha256']:
                raise ValueError(f'Changed frozen {name} input')
            if not destination.exists():destination.write_bytes(source.read_bytes())
            paths[name]=destination
        selection=json.loads(paths['grasps'].read_text())
        grasps={s:selection[s]['candidates'][0] for s in ('left','right')}
        reference,meta=load_reference(paths['reference'],env._task.assembly)
        fold=expand_coupled_plan(reference,json.loads(paths['fold'].read_text()))
        support_data=json.loads(paths['support'].read_text())
        if not support_data['passed']:raise ValueError('Unverified support input')
        support=[body_pose(row['bodies']['horseshoe_left']) for row in support_data['trajectory']]
        checker=HorseshoeIK(env)
        for row in json.loads(paths['approach'].read_text()):
            permitted={s:'horseshoe_'+s for s in grasps} if row['phase']=='descend' and row['fraction']>.85 else {}
            checked=checker.check(np.asarray(row['qpos']),contacts=permitted)
            if not checked['passed']:raise ValueError(f'Approach recheck: {checked}')
        planner=ManipulationPlanner(env,out/'planning/prefix',checker,reference=reference,fold_end_index=meta['fold_end_index'])
        policy=HorseshoePolicy(grasps,part='grasp_ring',fold=fold,support=support,planner=planner,fold_tracking_m=.002)
        shared.update(grasps=grasps,reference=reference,fold_end_index=meta['fold_end_index'])
        holder[0]=policy
        return Stage('prefix','grasp',dict(parameters=parameters),lambda row:CheckedJointPolicy(policy,env._robot),
                     lambda row:dict(default_home=row['state']['physics_step']==0),common,holding,200.)

    def continuation(operation, budget):
        def build(parameters):
            attempt[0]+=1
            checker=HorseshoeIK(env)
            planner=ManipulationPlanner(env,out/f'planning/{operation}_{attempt[0]:03}',checker,
                reference=shared['reference'],fold_end_index=shared['fold_end_index'])
            values=dict(parameters);limit=float(values.pop('contact_limit_m',.0008))
            if not 0<limit<=.001:raise ValueError('Stage contact limit must be at most 1 mm')
            tracker={name:deepcopy(getattr(shared['previous'],name)) for name in TRACKER_FIELDS}
            policy=ContinuationPolicy(shared['grasps'],operation=operation,tracker=tracker,planner=planner,
                withdrawal_mode='joint-staged',withdrawal_parameters=values if operation=='withdraw_ring' else None)
            if operation!='withdraw_ring' and values:raise ValueError('Unexpected placement parameters')
            holder[0]=policy
            def invariant(row):return dict(common(row,limit),**holding(row))
            def exit(row):
                result=holding(row)
                if operation=='withdraw_ring':result['withdrawal_completed']=policy.phase=='ring_withdrawal_complete'
                if operation=='verify_goal':result['raw_goal_stable']=policy.phase=='raw_goal_complete' or row['task']['result']['task_success']
                return result
            return Stage(operation,'interaction',dict(parameters=parameters),lambda row:CheckedJointPolicy(policy,env._robot),
                         holding,invariant,exit,budget)
        return build

    try:
        yield Step('prefix',(),prefix)
        shared['previous']=holder[0]
        candidates=tuple(dict(passive_contact_names=names,stage_motion_m=.004,speed_m_s=.002,
                              tracking_m=.0015,maximum_stages=300,contact_limit_m=.0008)
                         for names in (['horseshoe_left'],['horseshoe_left','chain_upper_1']))
        yield Step('withdraw',candidates,continuation('withdraw_ring',800.))
        shared['previous']=holder[0]
        yield Step('place_ring',({},),continuation('place_ring',500.))
        shared['previous']=holder[0]
        yield Step('place_remainder',({},),continuation('place_remainder',120.))
        shared['previous']=holder[0]
        yield Step('verify_goal',({},),continuation('verify_goal',15.))
    finally:
        unsubscribe();monitor.close()
