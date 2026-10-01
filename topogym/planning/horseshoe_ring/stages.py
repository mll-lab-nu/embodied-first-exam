"""Horseshoe adapter for the existing live qualification workflow.

Diagnostic rewind uses the public same-episode interface. It is never accepted
as a complete proof; a selected recipe must run continuously from home.
"""
from copy import deepcopy
from dataclasses import replace
from itertools import combinations
import json
import os
from pathlib import Path

import numpy as np
from scipy.spatial.transform import Rotation

from topogym.planning.solvability import Stage, Step
from topogym.planning.rigid_reference.feedback import body_pose, relative_pose
from topogym.utils.io import sha256_file, to_jsonable, write_json_atomic
from .kinematics import HorseshoeIK, CheckedJointPolicy
from .manipulation import ManipulationPlanner
from .oracle import load_reference, expand_coupled_plan
from .policy import HorseshoePolicy


TRACKER_FIELDS=('grip','bias','angle_bias','held_entities','offsets','support_hold')


class ContinuationPolicy(HorseshoePolicy):
    def __init__(self, *args, operation, tracker, **kwargs):
        super().__init__(*args, **kwargs)
        self.operation,self.tracker=operation,deepcopy(tracker)

    def actions(self):
        for name,value in self.tracker.items():setattr(self,name,deepcopy(value))
        if self.operation=='withdraw_one':
            self.withdrawal_finished=yield from self.withdraw_ring_once(self.withdrawal_stage_index)
        elif self.operation=='support_and_grasp':
            yield from self.support_pair()
            yield from self.grasp_ring()
        else:
            yield from getattr(self,self.operation)()


class BirthRingPolicy(HorseshoePolicy):
    """Test a direct contact pickup from the actual settled birth."""
    def actions(self):
        self.offsets={};self.grip={'left':.018,'right':.027}
        self.phase='open_at_home'
        yield {s:dict(gripper_position_m=v) for s,v in self.grip.items()}
        yield from self.hold(.6)
        yield from self.grasp_ring()
        yield from self.lift_ring_from_birth()


def stages(env, context, *, folded_settling=False, suspended_handoff=False, direct_birth=False,
           handoff_candidates=None, lower_reposition=False, withdrawal_defaults=None,
           reposition_parameters=None):
    """Bind the five prefix inputs and any optional withdrawal guide by hash."""
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

    def loop_linkages(world):
        loops={}
        for name,loop in env._task.assembly.loops.items():
            p,r=body_pose(world['bodies'][loop.body])
            loops[name]=replace(loop,center=p+r.apply(loop.center-env._task.body_origins[loop.body]),
                                rotation=r*loop.rotation)
        return {a+'|'+b:loops[a].linking(loops[b]) for a,b in combinations(loops,2)
                if loops[a].body!=loops[b].body}

    initial_linkages=loop_linkages(env.tick_record()['world'])

    def common(row, limit=.001):
        world=row['world'];task_links={i for name in env._task.placement_vertices
                                       for i in world['bodies'][name]['link_indices']}
        contacts=world['contacts']
        depth=max((float(d) for a,b,d in zip(contacts['link_a'],contacts['link_b'],contacts['penetration'])
                   if a in task_links or b in task_links),default=0.)
        result=row['task']['result']
        return dict(task_not_failed=not (result['terminated'] and not result['task_success']),
                    task_contact_within_stage_limit=depth<=limit,
                    all_closed_loop_linkages_preserved=loop_linkages(world)==initial_linkages)

    def holding(row):
        hands=row['world']['grasp']['hands']
        return {side+'_holds_expected_body':bool(hands[side]['binding'] and
                    hands[side]['binding']['target'][0]==name)
                for side,name in (('left','target_ring'),('right','horseshoe_right'))
                if not direct_birth or side=='left'}

    def holding_shoes(row):
        hands=row['world']['grasp']['hands']
        return {side+'_holds_expected_shoe':bool(hands[side]['binding'] and
                    hands[side]['binding']['target'][0]=='horseshoe_'+side) for side in ('left','right')}

    def handoff_invariant(row):
        hands=row['world']['grasp']['hands']
        return dict(right_holds_lower=bool(hands['right']['binding'] and hands['right']['binding']['target'][0]=='horseshoe_right'),
            left_binding_valid=hands['left']['binding'] is None or hands['left']['binding']['target'][0] in ('horseshoe_left','target_ring'))

    def prefix(parameters):
        paths={}
        inputs=out/'oracle_inputs';inputs.mkdir(exist_ok=True)
        names=('grasps','reference','fold','support','approach')
        if 'withdrawal_guide' in parameters:
            names+=('withdrawal_guide',)
        for name in names:
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
        policy=HorseshoePolicy(grasps,part='fold' if folded_settling else 'grasp_ring',fold=fold,support=support,planner=planner,fold_tracking_m=.002)
        if direct_birth:
            planner.reference=None
            policy=BirthRingPolicy(grasps,planner=planner)
        shared.update(grasps=grasps,reference=reference,fold_end_index=meta['fold_end_index'],support=support)
        if 'withdrawal_guide' in paths:
            guide=json.loads(paths['withdrawal_guide'].read_text())
            if not guide.get('passed') or len(guide.get('poses',()))<2:
                raise ValueError('Invalid sampled withdrawal guide input')
            if lower_reposition and guide.get('after_lower_reposition') is not True:
                raise ValueError('Repositioning requires an explicitly marked post-reposition guide')
            anchor=body_pose(guide['observed_bodies']['horseshoe_right'])
            poses=[relative_pose(anchor,body_pose(row)) for row in guide['poses']]
            index=int(guide['release_prefix_edges'])+1
            if not 0<index<len(poses):raise ValueError('Invalid withdrawal guide release prefix')
            shared['guide_state']=dict(index=index,stage=0,stride=1,symmetry=Rotation.identity(),relative_guide=poses)
            write_json_atomic(out/'withdrawal_guide_scope.json',dict(
                application_stage='after_reposition_lower' if lower_reposition else 'after_ring_grasp',
                scope='hash-bound planning hint relative to held lower shoe; every short stage rechecks measured poses, IK and collisions; no replay or proof credit'))
        holder[0]=policy
        return Stage('prefix','grasp',dict(parameters=parameters),lambda row:CheckedJointPolicy(policy,env._robot),
                     lambda row:dict(default_home=row['state']['physics_step']==0),common,
                     holding_shoes if folded_settling else holding,200.)

    def continuation(operation, budget, *, stage_index=None):
        def build(parameters):
            attempt[0]+=1
            checker=HorseshoeIK(env,puzzle_clearance_m=parameters.get('robot_puzzle_clearance_m',.0005))
            planner=ManipulationPlanner(env,out/f'planning/{operation}_{attempt[0]:03}',checker,
                reference=shared['reference'],fold_end_index=shared['fold_end_index'])
            values=dict(parameters);limit=float(values.pop('contact_limit_m',.0008))
            if not 0<limit<=.001:raise ValueError('Stage contact limit must be at most 1 mm')
            replan=bool(values.pop('replan',False))
            if operation=='withdraw_one' and not replan and shared.get('guide_state') is not None:
                planner.withdrawal_stage_state=deepcopy(shared['guide_state'])
            tracker={name:deepcopy(getattr(shared['previous'],name)) for name in TRACKER_FIELDS
                     if hasattr(shared['previous'],name)}
            policy=ContinuationPolicy(shared['grasps'],operation=operation,tracker=tracker,planner=planner,support=shared['support'],
                withdrawal_mode='joint-staged',withdrawal_parameters=values if operation=='withdraw_one' else None)
            policy.withdrawal_stage_index=stage_index
            policy.withdrawal_finished=None
            policy.replanned=replan or shared.get('guide_state') is None
            if operation=='gravity_settle_folded':
                if set(values)-{'angle_deg','translation_m','hold_s','sample_duration_s','roll_deg','yaw_deg','restore'}:raise ValueError('Unexpected gravity-settling parameters')
                if not isinstance(values.get('restore',True),bool):raise ValueError('restore must be boolean')
                hold=float(values.get('hold_s',8.))
                if not np.isfinite(hold) or not 0<hold<=30:raise ValueError('Gravity hold must be within 30 seconds')
                duration=float(values.get('sample_duration_s',.25))
                if not np.isfinite(duration) or not .05<=duration<=1.:raise ValueError('Tilt sample duration must be within 0.05 to 1 seconds')
                policy.settling_parameters=values
            elif operation=='support_and_grasp':
                policy.suspended_upper=values.pop('suspended_upper',False)
                if not isinstance(policy.suspended_upper,bool) or values:raise ValueError('Invalid support handoff parameters')
            elif operation=='reposition_lower':
                policy.reposition_fraction=float(values.pop('fraction',1.))
                policy.reposition_tracking_m=float(values.pop('lower_tracking_m',.0015))
                policy.reposition_bias_limit_m=float(values.pop('position_bias_limit_m',.03))
                policy.reposition_integral_gain_s_inv=float(values.pop('position_integral_gain_s_inv',2.))
                policy.reposition_velocity_gain_s=float(values.pop('position_velocity_gain_s',0.))
                if values or not np.isfinite(policy.reposition_fraction) or not .1<=policy.reposition_fraction<=1.:
                    raise ValueError('Reposition fraction must be within 0.1 and 1')
                if not np.isfinite(policy.reposition_tracking_m) or not .00005<=policy.reposition_tracking_m<=.003:
                    raise ValueError('Lower-shoe progress tracking limit must be within 0.05 and 3 mm')
                if not np.isfinite(policy.reposition_bias_limit_m) or not .001<=policy.reposition_bias_limit_m<=.10:
                    raise ValueError('Reposition feedback bias limit must be within 1 and 100 mm')
                if not np.isfinite(policy.reposition_integral_gain_s_inv) or not 0<=policy.reposition_integral_gain_s_inv<=4.:
                    raise ValueError('Reposition integral gain must be within 0 and 4 per second')
                if not np.isfinite(policy.reposition_velocity_gain_s) or not 0<=policy.reposition_velocity_gain_s<=1.:
                    raise ValueError('Reposition velocity feedback must be within 0 and 1 second')
            elif operation!='withdraw_one' and values:raise ValueError('Unexpected placement parameters')
            holder[0]=policy
            condition=(holding_shoes if operation=='gravity_settle_folded' else
                       handoff_invariant if operation=='support_and_grasp' else holding)
            entry=holding_shoes if operation in ('gravity_settle_folded','support_and_grasp') else holding
            def invariant(row):return dict(common(row,limit),**condition(row))
            def exit(row):
                result=holding_shoes(row) if operation=='gravity_settle_folded' else holding(row)
                if operation=='gravity_settle_folded':
                    key='ring_relocated' if values.get('restore',True) else 'handoff_orientation_reached'
                    result[key]=getattr(policy,'gravity_result',{}).get('passed',False)
                if operation=='withdraw_one':result['short_stage_completed']=policy.withdrawal_finished is not None
                if operation=='reposition_lower':result['lower_target_reached']=getattr(policy,'lower_reposition_result',{}).get('passed',False)
                if operation=='verify_goal':result['raw_goal_stable']=policy.phase=='raw_goal_complete' or row['task']['result']['task_success']
                return result
            return Stage(operation,'interaction',dict(parameters=parameters),lambda row:CheckedJointPolicy(policy,env._robot),
                         entry,invariant,exit,budget)
        return build

    try:
        input_file=os.environ.get('TOPOGYM_HORSESHOE_ORACLE_INPUTS')
        prefix_candidates=(json.loads(Path(input_file).read_text()),) if input_file else ()
        yield Step('prefix',prefix_candidates,prefix)
        shared['previous']=holder[0]
        if direct_birth:
            yield Step('place_ring',({},),continuation('place_ring',500.))
            shared['previous']=holder[0]
            yield Step('verify_goal',({},),continuation('verify_goal',15.))
            return
        if folded_settling:
            gravity_candidates=tuple(dict(angle_deg=120.,yaw_deg=yaw,translation_m=[0.,.08,0.],
                                          hold_s=8.,sample_duration_s=.1) for yaw in (30.,60.))
            if suspended_handoff:
                gravity_candidates=tuple(dict(angle_deg=angle,yaw_deg=30.,translation_m=[0.,.08,0.],
                    hold_s=8.,sample_duration_s=.1,restore=False) for angle in (120.,135.))
                if handoff_candidates is not None:gravity_candidates=tuple(handoff_candidates)
            yield Step('orient_for_handoff' if suspended_handoff else 'gravity_settle_folded',
                       gravity_candidates,continuation('gravity_settle_folded',240.))
            shared['previous']=holder[0]
            yield Step('support_and_grasp',({'suspended_upper':True} if suspended_handoff else {},),
                       continuation('support_and_grasp',120. if suspended_handoff else 60.))
            shared['previous']=holder[0]
        if lower_reposition:
            yield Step('reposition_lower',(reposition_parameters or {},),continuation('reposition_lower',180.))
            shared['previous']=holder[0]
        parameters=dict(passive_contact_names=[] if folded_settling else ['horseshoe_left'],stage_motion_m=.004,speed_m_s=.002,
                        tracking_m=.0015,maximum_stages=600,contact_limit_m=.0008,search_seed=922)
        if withdrawal_defaults:parameters.update(withdrawal_defaults)
        stagnant=0;recovery_steps=0
        for index in range(1000):
            if index>=int(parameters['maximum_stages']):
                raise ValueError(f"Withdrawal exhausted {parameters['maximum_stages']} measured short stages")
            old=shared.get('guide_state')
            candidates=(dict(parameters,replan=stagnant>=3),
                        dict(parameters,replan=True,speed_m_s=.001,stage_motion_m=.002,
                             passive_contact_names=['chain_upper_1','chain_lower_1'] if suspended_handoff else
                                                   parameters['passive_contact_names'] or ['horseshoe_left'],
                             search_seed=int(parameters['search_seed'])+1),
                        dict(parameters,replan=True,passive_contact_names=['horseshoe_left','chain_upper_1','chain_lower_1'] if suspended_handoff else ['horseshoe_left','chain_upper_1'],
                             search_seed=int(parameters['search_seed'])+2))
            yield Step(f'withdraw_{index:03}',candidates,continuation('withdraw_one',50.,stage_index=index))
            policy=holder[0];shared['previous']=policy
            shared['guide_state']=deepcopy(getattr(policy.planner,'withdrawal_stage_state',None))
            parameters.update(policy.withdrawal_parameters)
            new=shared['guide_state']
            stagnant=stagnant+1 if not policy.replanned and old and new and old['index']==new['index'] else 0
            if policy.withdrawal_finished:break
            # A conservative retry is a local recovery, not a permanent
            # reduction of the remaining route's progress budget. After
            # three successful short stages, retry the nominal checked
            # step; every candidate still undergoes the same geometry and
            # per-tick physical guards, and the slower fallback remains.
            recovery_steps=recovery_steps+1 if parameters['stage_motion_m']<.004 else 0
            if recovery_steps>=3:
                parameters['stage_motion_m']=min(.004,2*parameters['stage_motion_m'])
                parameters['speed_m_s']=min(.002,2*parameters['speed_m_s'])
                recovery_steps=0
        else:raise ValueError('Withdrawal exhausted 1000 measured short stages')
        yield Step('place_ring',({},),continuation('place_ring',500.))
        shared['previous']=holder[0]
        yield Step('place_remainder',({},),continuation('place_remainder',120.))
        shared['previous']=holder[0]
        yield Step('verify_goal',({},),continuation('verify_goal',15.))
    finally:
        unsubscribe();monitor.close()


def gravity_stages(env, context):
    """Try measured post-fold ring settling before releasing either shoe."""
    return stages(env,context,folded_settling=True)


def suspended_stages(env, context):
    """Keep the inverted pose while releasing the upper shoe onto its chains."""
    return stages(env,context,folded_settling=True,suspended_handoff=True)


def direct_stages(env, context):
    """Ordinary ring grasp and contact lift from settled birth, then placement."""
    return stages(env,context,direct_birth=True)


def vertical_stages(env, context):
    """Test handoff with both shoe bends pointing along gravity."""
    candidates=(dict(angle_deg=90.,yaw_deg=0.,translation_m=[0.,.10,-.04],
                     hold_s=8.,sample_duration_s=.1,restore=False),)
    return stages(env,context,folded_settling=True,suspended_handoff=True,
                  handoff_candidates=candidates)


def reposition_stages(env, context):
    """Vertical ring acquisition, then move the right-held shoe toward the upper."""
    candidates=(dict(angle_deg=90.,yaw_deg=0.,translation_m=[0.,.10,-.04],
                     hold_s=8.,sample_duration_s=.1,restore=False),)
    return stages(env,context,folded_settling=True,suspended_handoff=True,
                  handoff_candidates=candidates,lower_reposition=True)


def close_clearance_stages(env, context):
    """The measured 120-degree grasp with a positive 0.1 mm robot/puzzle margin."""
    return stages(env,context,folded_settling=True,suspended_handoff=True,
        withdrawal_defaults=dict(robot_puzzle_clearance_m=.0001,search_seed=924,
            passive_contact_names=['horseshoe_left','chain_upper_1','chain_lower_1']))


def supported_vertical_stages(env, context):
    """Keep the ring's tracking gate tight while tolerating measured support load."""
    candidates=(dict(angle_deg=90.,yaw_deg=0.,translation_m=[0.,.10,-.04],
                     hold_s=8.,sample_duration_s=.1,restore=False),)
    return stages(env,context,folded_settling=True,suspended_handoff=True,
        handoff_candidates=candidates,
        withdrawal_defaults=dict(support_tracking_m=.003,search_seed=924,
            passive_contact_names=['horseshoe_left','chain_upper_1','chain_lower_1']))


def partial_reposition_stages(env, context):
    """Move through the measured free prefix, then replan ring withdrawal."""
    candidates=(dict(angle_deg=90.,yaw_deg=0.,translation_m=[0.,.10,-.04],
                     hold_s=8.,sample_duration_s=.1,restore=False),)
    return stages(env,context,folded_settling=True,suspended_handoff=True,
        handoff_candidates=candidates,lower_reposition=True,
        reposition_parameters=dict(fraction=.65),
        withdrawal_defaults=dict(support_tracking_m=.003,search_seed=924,
            passive_contact_names=['horseshoe_left','chain_upper_1','chain_lower_1']))


def reference_reposition_stages(env, context):
    """Partial lower-shoe motion, then exit toward the reference's free end."""
    candidates=(dict(angle_deg=90.,yaw_deg=0.,translation_m=[0.,.10,-.04],
                     hold_s=8.,sample_duration_s=.1,restore=False),)
    return stages(env,context,folded_settling=True,suspended_handoff=True,
        handoff_candidates=candidates,lower_reposition=True,
        reposition_parameters=dict(fraction=.65),
        withdrawal_defaults=dict(support_tracking_m=.003,exit_goal_mode='reference',search_seed=924,
            passive_contact_names=['horseshoe_left','chain_upper_1','chain_lower_1']))


def measured_support_reference_stages(env, context):
    """Rebase the right support target to the geometry used by each short plan."""
    candidates=(dict(angle_deg=90.,yaw_deg=0.,translation_m=[0.,.10,-.04],
                     hold_s=8.,sample_duration_s=.1,restore=False),)
    return stages(env,context,folded_settling=True,suspended_handoff=True,
        handoff_candidates=candidates,lower_reposition=True,
        reposition_parameters=dict(fraction=.65),
        withdrawal_defaults=dict(support_tracking_m=.003,rebase_support_each_stage=True,
            exit_goal_mode='reference',search_seed=924,
            passive_contact_names=['horseshoe_left','chain_upper_1','chain_lower_1']))


def ring_tracking_reference_stages(env, context):
    """Advance on ring tracking while retaining measured right support feedback."""
    candidates=(dict(angle_deg=90.,yaw_deg=0.,translation_m=[0.,.10,-.04],
                     hold_s=8.,sample_duration_s=.1,restore=False),)
    return stages(env,context,folded_settling=True,suspended_handoff=True,
        handoff_candidates=candidates,lower_reposition=True,
        reposition_parameters=dict(fraction=.65),
        withdrawal_defaults=dict(rebase_support_each_stage=True,gate_support_tracking=False,
            exit_goal_mode='reference',search_seed=924,
            passive_contact_names=['horseshoe_left','chain_upper_1','chain_lower_1']))


def fixed_support_ring_tracking_stages(env, context):
    """Retain the initial support target without gating on its load error."""
    candidates=(dict(angle_deg=90.,yaw_deg=0.,translation_m=[0.,.10,-.04],
                     hold_s=8.,sample_duration_s=.1,restore=False),)
    return stages(env,context,folded_settling=True,suspended_handoff=True,
        handoff_candidates=candidates,lower_reposition=True,
        reposition_parameters=dict(fraction=.65),
        withdrawal_defaults=dict(rebase_support_each_stage=False,gate_support_tracking=False,
            exit_goal_mode='reference',search_seed=924,
            passive_contact_names=['horseshoe_left','chain_upper_1','chain_lower_1']))


def full_reposition_fixed_support_stages(env, context):
    """Complete the checked lower-shoe edge before measured ring withdrawal."""
    candidates=(dict(angle_deg=90.,yaw_deg=0.,translation_m=[0.,.10,-.04],
                     hold_s=8.,sample_duration_s=.1,restore=False),)
    return stages(env,context,folded_settling=True,suspended_handoff=True,
        handoff_candidates=candidates,lower_reposition=True,
        reposition_parameters=dict(fraction=1.,lower_tracking_m=.003),
        withdrawal_defaults=dict(rebase_support_each_stage=False,gate_support_tracking=False,
            exit_goal_mode='reference',search_seed=924,
            passive_contact_names=['horseshoe_left','chain_upper_1','chain_lower_1']))


def compensated_full_reposition_stages(env, context):
    """Allow more Cartesian load compensation within the original robot gains."""
    candidates=(dict(angle_deg=90.,yaw_deg=0.,translation_m=[0.,.10,-.04],
                     hold_s=8.,sample_duration_s=.1,restore=False),)
    return stages(env,context,folded_settling=True,suspended_handoff=True,
        handoff_candidates=candidates,lower_reposition=True,
        reposition_parameters=dict(fraction=1.,lower_tracking_m=.0015,position_bias_limit_m=.05),
        withdrawal_defaults=dict(rebase_support_each_stage=False,gate_support_tracking=False,
            position_bias_limit_m=.05,exit_goal_mode='reference',search_seed=924,
            passive_contact_names=['horseshoe_left','chain_upper_1','chain_lower_1']))


def damped_full_reposition_stages(env, context):
    """Use measured body velocity feedback to damp coupled grasp oscillation."""
    candidates=(dict(angle_deg=90.,yaw_deg=0.,translation_m=[0.,.10,-.04],
                     hold_s=8.,sample_duration_s=.1,restore=False),)
    feedback=dict(position_bias_limit_m=.06,position_integral_gain_s_inv=.75,
                  position_velocity_gain_s=.25)
    return stages(env,context,folded_settling=True,suspended_handoff=True,
        handoff_candidates=candidates,lower_reposition=True,
        reposition_parameters=dict(fraction=1.,lower_tracking_m=.002,**feedback),
        withdrawal_defaults=dict(rebase_support_each_stage=False,gate_support_tracking=False,
            **feedback,exit_goal_mode='reference',search_seed=924,
            passive_contact_names=['horseshoe_left','chain_upper_1','chain_lower_1']))
