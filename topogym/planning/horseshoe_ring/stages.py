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
import sys

import numpy as np
from scipy.spatial.transform import Rotation

from topogym.planning.solvability import Stage, Step
from topogym.planning.rigid_reference.feedback import body_pose, relative_pose
from topogym.utils.io import sha256_file, to_jsonable, write_json_atomic
from topogym.utils.grasp import held_finger_contact_mask
from .kinematics import HorseshoeIK, CheckedJointPolicy
from .manipulation import ManipulationPlanner
from .oracle import load_reference, expand_coupled_plan
from .policy import HorseshoePolicy


TRACKER_FIELDS=('grip','bias','angle_bias','held_entities','offsets','support_hold','velocity_feedback_state')


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
        elif self.operation=='support_release':
            yield from self.support_pair()
        elif self.operation=='grasp_ring':
            yield from self.grasp_ring()
            if self.release_support:yield from self.release_support_and_lift()
            elif self.table_pickup:yield from self.lift_ring_for_transport()
        elif self.operation=='table_support':
            from .table_support import execute_table_support
            yield from execute_table_support(self, self.table_support_guide,
                                             tracking_m=self.table_tracking_m)
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
           reposition_parameters=None, require_prefix_replay=False, ring_grasp_choice=None,
           require_ring_pivot=False, native_robot_contacts=False, table_supported=False,
           table_pickup_after_release=False):
    """Bind the five prefix inputs and any optional withdrawal guide by hash."""
    if not isinstance(native_robot_contacts, bool):
        raise ValueError('Native robot contact screening option must be boolean')
    if not isinstance(table_supported, bool) or table_supported and not native_robot_contacts:
        raise ValueError('Table support requires native robot contact screening')
    if (not isinstance(table_pickup_after_release,bool) or table_pickup_after_release and
            not (folded_settling and suspended_handoff and native_robot_contacts)):
        raise ValueError('Table pickup requires a checked suspended release')
    out=context.output;holder=[None];shared={};attempt=[0]
    prefix_clearance_m=.0001 if native_robot_contacts else .0005
    monitor=(out/'private/horseshoe_monitor.jsonl').open('x',buffering=1)
    identity=dict(config=to_jsonable(env.config),seed=context.identity['seed'],
        instance_id=env._task.instance_id,from_default_home=True,
        native_robot_contact_screening_from_handoff=native_robot_contacts,
        native_robot_contact_screening_at_approach=table_pickup_after_release,
        prefix_robot_puzzle_clearance_m=prefix_clearance_m,
        table_supported_handoff=table_supported,
        terminal=env._task.terminal_metadata(),
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

    # The task tooling's rule R1 (rcb_topogym.CONTACT_RULE, rules 2026-10-03) replaced TopoGym's any-tick 1 mm task
    # contact limit: a non-held task contact fails above 3 mm at once, or once it stays above 1 mm for 0.25 s (held
    # fingers 4 mm / 2 mm). The stage gate keeps its own limits with the same persistence over consecutive ticks.
    rule=getattr(sys.modules.get('rcb_topogym'),'CONTACT_RULE',None) or dict(
        deep_m=.003,sustained_m=.001,held_deep_m=.004,held_sustained_m=.002,window_s=.25)
    window=max(1,int(np.ceil(rule['window_s']/env.config.physics_dt_s-1e-12)))
    persisted=dict(step=None,over=0,held_over=0)

    def common(row, limit=.001):
        world=row['world'];task_links={i for name in env._task.placement_vertices
                                       for i in world['bodies'][name]['link_indices']}
        contacts=world['contacts']
        involved=(np.isin(contacts['link_a'],list(task_links)) |
                  np.isin(contacts['link_b'],list(task_links)))
        held=held_finger_contact_mask(contacts,identity['grasp_finger_links'],task_links,world.get('grasp'))
        penetration=np.asarray(contacts['penetration'])
        depth=float(penetration[involved & ~held].max(initial=0.))
        held_depth=float(penetration[involved & held].max(initial=0.))
        held_limit=float(identity['terminal']['contact_penetration']['held_finger_contacts_m'])
        step=row['state']['physics_step']
        if step!=persisted['step']:  # the same tick checked again (next stage's entry) keeps its counts
            follows=persisted['step'] is not None and step==persisted['step']+1
            persisted.update(step=step,
                over=(persisted['over'] if follows else 0)+1 if depth>limit else 0,
                held_over=(persisted['held_over'] if follows else 0)+1 if held_depth>held_limit else 0)
        result=row['task']['result']
        return dict(task_not_failed=not (result['terminated'] and not result['task_success']),
                    task_contact_within_stage_limit=depth<=rule['deep_m'] and persisted['over']<window,
                    held_finger_contact_within_task_limit=(held_depth<=rule['held_deep_m'] and
                                                           persisted['held_over']<window),
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
        if table_supported:names+=('table_support_guide',)
        if 'prefix_replay' in parameters:names+=('prefix_replay',)
        elif require_prefix_replay:raise ValueError('This recipe requires a hash-bound action prefix')
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
        fold_data=json.loads(paths['fold'].read_text())
        fold=expand_coupled_plan(reference,fold_data)
        support_data=json.loads(paths['support'].read_text())
        if not support_data['passed']:raise ValueError('Unverified support input')
        support=[body_pose(row['bodies']['horseshoe_left']) for row in support_data['trajectory']]
        if table_pickup_after_release:
            from .native_contacts import ContactHorseshoeIK
            checker=ContactHorseshoeIK(env,puzzle_clearance_m=prefix_clearance_m,ordinary_limit_m=.001)
            checker.observed_grasp=env._world.read_state()['grasp']
        else:
            checker=HorseshoeIK(env,puzzle_clearance_m=prefix_clearance_m)
        for row in json.loads(paths['approach'].read_text()):
            permitted={s:'horseshoe_'+s for s in grasps} if row['phase']=='descend' and row['fraction']>.85 else {}
            checked=checker.check(np.asarray(row['qpos']),contacts=permitted)
            if not checked['passed']:raise ValueError(f'Approach recheck: {checked}')
        planner=ManipulationPlanner(env,out/'planning/prefix',checker,reference=reference,fold_end_index=meta['fold_end_index'])
        policy=HorseshoePolicy(grasps,part='fold' if folded_settling else 'grasp_ring',fold=fold,support=support,planner=planner,fold_tracking_m=.002,
                              post_fold_hold_s=fold_data.get('post_fold_hold_s',2.))
        replayed='prefix_replay' in paths
        if replayed:
            if direct_birth:raise ValueError('Action prefix and direct birth are separate recipes')
            from .prefix_replay import ReplayPrefixPolicy,validate_replay
            replay=json.loads(paths['prefix_replay'].read_text())
            validate_replay(replay,env.config,context.identity['seed'])
            if set(replay['expected_end']['bodies'])!=set(env._task.placement_vertices):
                raise ValueError('Replay endpoint must cover every puzzle body')
            policy=ReplayPrefixPolicy(grasps,replay=replay,planner=planner)
            shared['replayed_prefix']=True
        if direct_birth:
            planner.reference=None
            policy=BirthRingPolicy(grasps,planner=planner)
        policy.ring_grasp_choice=deepcopy(ring_grasp_choice)
        policy.require_ring_pivot=require_ring_pivot
        shared.update(grasps=grasps,reference=reference,fold_end_index=meta['fold_end_index'],support=support)
        if table_supported:
            shared['table_support_guide']=json.loads(paths['table_support_guide'].read_text())
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
        def prefix_exit(row):
            checks=holding_shoes(row) if folded_settling and not replayed else holding(row)
            if replayed:checks['replay_endpoint_matched']=getattr(policy,'replay_result',{}).get('passed',False)
            return checks
        return Stage('prefix','grasp',dict(parameters=parameters),lambda row:CheckedJointPolicy(policy,env._robot),
                     lambda row:dict(default_home=row['state']['physics_step']==0),common,
                     prefix_exit,max(200.,len(replay['controls'])*env.config.physics_dt_s+1.) if replayed else 200.)

    def continuation(operation, budget, *, stage_index=None):
        def build(parameters):
            attempt[0]+=1
            values=dict(parameters);limit=float(values.pop('contact_limit_m',.001 if native_robot_contacts else .0008))
            if not 0<limit<=.001:raise ValueError('Stage contact limit must be at most 1 mm')
            checker_type=HorseshoeIK
            checker_options=dict(puzzle_clearance_m=parameters.get('robot_puzzle_clearance_m',.0005))
            if native_robot_contacts and (operation in ('support_and_grasp','support_release','grasp_ring',
                    'clear_remainder_for_table_pickup','lift_ring_for_transport','withdraw_one','place_ring','place_remainder')
                    or table_supported and operation=='table_support'
                    or table_pickup_after_release and operation=='gravity_settle_folded'):
                from .native_contacts import ContactHorseshoeIK
                checker_type=ContactHorseshoeIK
                checker_options['ordinary_limit_m']=limit
            checker=checker_type(env,**checker_options)
            planner=ManipulationPlanner(env,out/f'planning/{operation}_{attempt[0]:03}',checker,
                reference=shared['reference'],fold_end_index=shared['fold_end_index'])
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
                if set(values)-{'angle_deg','translation_m','hold_s','sample_duration_s','roll_deg','yaw_deg','restore','position_bias_limit_m','tracking_m'}:raise ValueError('Unexpected gravity-settling parameters')
                if not isinstance(values.get('restore',True),bool):raise ValueError('restore must be boolean')
                hold=float(values.get('hold_s',8.))
                if not np.isfinite(hold) or not 0<hold<=30:raise ValueError('Gravity hold must be within 30 seconds')
                duration=float(values.get('sample_duration_s',.25))
                # oraclefix2: down to 0.02 s per 0.5 deg sample (25 deg/s). Hard under Harbor's 2.5 ms x 10 physics: at 0.05 s
                # the ring slides 43 mm along the lower band during the tilt and wedges between the right fingers; a fast
                # tilt with a 1 s hold leaves it free (lab oraclefix2/exp/X3e). Joints stay far below the standard step limit.
                if not np.isfinite(duration) or not .02<=duration<=1.:raise ValueError('Tilt sample duration must be within 0.02 to 1 seconds')
                bias_limit=float(values.get('position_bias_limit_m',.03))
                if not np.isfinite(bias_limit) or not .001<=bias_limit<=.10:
                    raise ValueError('Tilt position feedback bias must be between 1 and 100 mm')
                tracking=float(values.get('tracking_m',.002))
                if isinstance(values.get('tracking_m'),bool) or not np.isfinite(tracking) or not .0005<=tracking<=.005:
                    raise ValueError('Tilt material tracking tolerance must be between 0.5 and 5 mm')
                policy.settling_parameters=values
            elif operation in ('support_and_grasp','support_release'):
                policy.suspended_upper=values.pop('suspended_upper',False)
                policy.table_supported=values.pop('table_supported',False)
                policy.joint_release_retreat=values.pop('joint_release_retreat',False)
                policy.active_ring_pickup=values.pop('active_ring_pickup',False)
                policy.release_turn=values.pop('release_turn',None)
                if policy.release_turn is not None:
                    turn=policy.release_turn
                    if (not policy.suspended_upper or not isinstance(turn,dict)
                            or set(turn)-{'axis','angle_deg','tracking_m'}
                            or turn.get('axis','tool') not in ('tool','x','y','z')
                            or not np.isfinite(float(turn.get('angle_deg',60.)))
                            or not 0<abs(float(turn.get('angle_deg',60.)))<=90
                            or not np.isfinite(float(turn.get('tracking_m',.003)))
                            or not .0005<=float(turn.get('tracking_m',.003))<=.005):
                        raise ValueError('Invalid supported release turn')
                policy.ring_grasp_choice=deepcopy(ring_grasp_choice)
                policy.require_ring_pivot=require_ring_pivot
                if (not isinstance(policy.suspended_upper,bool) or not isinstance(policy.table_supported,bool)
                        or not isinstance(policy.joint_release_retreat,bool)
                        or not isinstance(policy.active_ring_pickup,bool)
                        or policy.active_ring_pickup and (operation!='support_release' or not policy.suspended_upper)
                        or policy.joint_release_retreat and not (policy.suspended_upper or policy.table_supported)
                        or policy.suspended_upper and policy.table_supported or values):
                    raise ValueError('Invalid support handoff parameters')
            elif operation=='grasp_ring':
                policy.ring_grasp_choice=deepcopy(values.pop('choice',ring_grasp_choice))
                policy.require_ring_pivot=False
                policy.table_pickup=table_pickup_after_release
                policy.release_support=values.pop('release_support',False)
                policy.level_released_ring=values.pop('level_released_ring',False)
                policy.release_translation_m=values.pop('release_translation_m',None)
                if not isinstance(policy.release_support,bool) or policy.release_support and policy.table_pickup:
                    raise ValueError('Support release requires an active suspended pickup')
                if (not isinstance(policy.level_released_ring,bool)
                        or policy.level_released_ring and not policy.release_support):
                    raise ValueError('Ring leveling requires released support')
                if policy.release_translation_m is not None:
                    shift=np.asarray(policy.release_translation_m,dtype=float)
                    if (not policy.release_support or shift.shape!=(3,) or not np.isfinite(shift).all()
                            or not 0<np.linalg.norm(shift)<=.4):
                        raise ValueError('Invalid relocation before support release')
                if values:raise ValueError('Unexpected ring pickup parameters')
            elif operation=='table_support':
                policy.table_tracking_m=float(values.pop('tracking_m',.0015))
                if not np.isfinite(policy.table_tracking_m) or not .0005<=policy.table_tracking_m<=.0015:
                    raise ValueError('Table tracking tolerance must be within 0.5 and 1.5 mm')
                if values:raise ValueError('Unexpected table transport parameters')
                policy.table_support_guide=shared['table_support_guide']
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
            elif operation=='place_ring':
                # oraclefix2 (below-easy): the held ring's material tracking gate of the placement route, default 2 mm.
                # very_easy's larger ring is carried 2.0-2.1 mm off the route after 20 % of it and the gate then stalls
                # the clock (lab hsbe/exp/X2_very_easy).
                tracking=values.pop('tracking_m',.002)
                if isinstance(tracking,bool) or not np.isfinite(float(tracking)) or not .0005<=float(tracking)<=.005:
                    raise ValueError('Placement tracking tolerance must be between 0.5 and 5 mm')
                policy.place_tracking_m=float(tracking)
                if values:raise ValueError('Unexpected placement parameters')
            elif operation!='withdraw_one' and values:raise ValueError('Unexpected placement parameters')
            holder[0]=policy
            free_ring_operations=('support_release','clear_remainder_for_table_pickup','grasp_ring')
            condition=(holding_shoes if operation in ('gravity_settle_folded','table_support') else
                       handoff_invariant if operation in ('support_and_grasp',*free_ring_operations) else holding)
            entry=(holding_shoes if operation in ('gravity_settle_folded','table_support','support_and_grasp','support_release')
                   else handoff_invariant if operation in free_ring_operations else holding)
            def holding_ring(row):
                binding=row['world']['grasp']['hands']['left']['binding']
                return dict(left_holds_ring=bool(binding and binding['target'][0]=='target_ring'))
            if shared.get('support_released'):
                condition=entry=holding_ring
            elif operation=='grasp_ring' and policy.release_support:
                # Acquisition starts with the hand free. Once the right hand
                # is opened, the left ring binding must remain present.
                def condition(row):
                    hands=row['world']['grasp']['hands']
                    return handoff_invariant(row) if hands['right']['binding'] else holding_ring(row)
            def invariant(row):return dict(common(row,limit),**condition(row))
            def exit(row):
                result=holding_shoes(row) if operation in ('gravity_settle_folded','table_support') else holding(row)
                if shared.get('support_released') or operation=='grasp_ring' and policy.release_support:
                    result=holding_ring(row)
                    if operation=='grasp_ring':
                        result['support_released_and_ring_extracted']=getattr(policy,'support_released',False)
                if operation in ('support_release','clear_remainder_for_table_pickup'):
                    result=handoff_invariant(row)
                    result['left_is_free']=row['world']['grasp']['hands']['left']['binding'] is None
                    from .settling import folded_ring_metric
                    # A hanging ring can be grasped and extracted under contact.
                    # Separation is checked after that extraction, not before
                    # the free hand is allowed to approach it.
                    if not getattr(policy,'active_ring_pickup',False):
                        result['ring_is_separated']=folded_ring_metric(planner,policy.obs)['maximum_separating_gap_m']>=.02
                    if operation=='clear_remainder_for_table_pickup':
                        result['support_clearance_completed']=getattr(policy,'table_pickup_clearance_result',{}).get('passed',False)
                if operation=='table_support':
                    result['table_transport_reached']=getattr(policy,'table_support_result',{}).get('passed',False)
                if operation=='gravity_settle_folded':
                    key='ring_relocated' if values.get('restore',True) else 'handoff_orientation_reached'
                    result[key]=getattr(policy,'gravity_result',{}).get('passed',False)
                if operation=='withdraw_one':
                    # The default-enabled native goal may terminate an
                    # extraction segment before its local generator finishes.
                    # Invariants and grasp checks still apply to every tick.
                    result['short_stage_completed']=(policy.withdrawal_finished is not None
                        or row['task']['result']['task_success'])
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
        if folded_settling and not shared.get('replayed_prefix'):
            gravity_candidates=tuple(dict(angle_deg=120.,yaw_deg=yaw,translation_m=[0.,.08,0.],
                                          hold_s=8.,sample_duration_s=.1) for yaw in (30.,60.))
            if suspended_handoff:
                gravity_candidates=tuple(dict(angle_deg=angle,yaw_deg=30.,translation_m=[0.,.08,0.],
                    hold_s=8.,sample_duration_s=.1,restore=False) for angle in (120.,135.))
                if handoff_candidates is not None:gravity_candidates=tuple(handoff_candidates)
            yield Step('orient_for_handoff' if suspended_handoff else 'gravity_settle_folded',
                       gravity_candidates,continuation('gravity_settle_folded',240.))
            shared['previous']=holder[0]
            if table_supported:
                yield Step('table_support',({'tracking_m':.0015},),continuation('table_support',600.))
                shared['previous']=holder[0]
            operation='support_release' if table_pickup_after_release else 'support_and_grasp'
            yield Step(operation,({'table_supported':True} if table_supported else
                                          {'suspended_upper':True} if suspended_handoff else {},),
                       continuation(operation,120. if suspended_handoff else 60.))
            shared['previous']=holder[0]
            if table_pickup_after_release and getattr(holder[0],'active_ring_pickup',False):
                table_pickup_after_release=False
                yield Step('grasp_ring',({'choice':ring_grasp_choice},),continuation('grasp_ring',240.))
                shared['previous']=holder[0]
                if getattr(holder[0],'support_released',False):
                    shared['support_released']=True
                    yield Step('place_ring',({},),continuation('place_ring',500.))
                    shared['previous']=holder[0]
                    yield Step('verify_goal',({},),continuation('verify_goal',15.))
                    return
            if table_pickup_after_release:
                yield Step('clear_remainder_for_table_pickup',({},),continuation('clear_remainder_for_table_pickup',120.))
                shared['previous']=holder[0]
                yield Step('grasp_ring',({'choice':ring_grasp_choice},),continuation('grasp_ring',120.))
                shared['previous']=holder[0]
        if table_pickup_after_release:
            if shared.get('replayed_prefix'):
                yield Step('lift_ring_for_transport',({},),continuation('lift_ring_for_transport',120.))
                shared['previous']=holder[0]
            yield Step('place_ring',({},),continuation('place_ring',500.))
            shared['previous']=holder[0]
            yield Step('verify_goal',({},),continuation('verify_goal',15.))
            return
        if lower_reposition:
            yield Step('reposition_lower',(reposition_parameters or {},),continuation('reposition_lower',180.))
            shared['previous']=holder[0]
        parameters=dict(passive_contact_names=[] if folded_settling else ['horseshoe_left'],stage_motion_m=.004,speed_m_s=.002,
                        tracking_m=.0015,maximum_stages=600,
                        contact_limit_m=.001 if native_robot_contacts else .0008,search_seed=922)
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


def pivot_reference_stages(env, context):
    """Try the reference eye-turn milestone before requesting a free ring."""
    candidates=(dict(angle_deg=90.,yaw_deg=0.,translation_m=[0.,.10,-.04],
                     hold_s=8.,sample_duration_s=.1,restore=False),)
    return stages(env,context,folded_settling=True,suspended_handoff=True,
        handoff_candidates=candidates,lower_reposition=True,
        reposition_parameters=dict(fraction=1.,lower_tracking_m=.002,position_bias_limit_m=.05),
        withdrawal_defaults=dict(rebase_support_each_stage=False,gate_support_tracking=False,
            position_bias_limit_m=.06,exit_goal_mode='reference_pivot',search_seed=950,
            passive_contact_names=['horseshoe_left','chain_upper_1','chain_lower_1']))


def filtered_pivot_reference_stages(env, context, *, tracking_stall_timeout_s=None):
    """Damp the pivot using filtered measured control-period body velocity."""
    candidates=(dict(angle_deg=90.,yaw_deg=0.,translation_m=[0.,.10,-.04],
                     hold_s=8.,sample_duration_s=.1,restore=False),)
    return stages(env,context,folded_settling=True,suspended_handoff=True,
        handoff_candidates=candidates,lower_reposition=True,
        reposition_parameters=dict(fraction=1.,lower_tracking_m=.002,position_bias_limit_m=.05),
        withdrawal_defaults=dict(rebase_support_each_stage=False,gate_support_tracking=False,
            position_bias_limit_m=.06,position_integral_gain_s_inv=2.,
            position_velocity_gain_s=.25,position_velocity_filter_s=.1,
            tracking_stall_timeout_s=tracking_stall_timeout_s,
            maximum_stages=1000,exit_goal_mode='reference_pivot',search_seed=950,
            passive_contact_names=['horseshoe_left','chain_upper_1','chain_lower_1']))


def patient_pivot_reference_stages(env, context):
    """Use a no-progress watchdog inside the unchanged 50 s stage budget."""
    return filtered_pivot_reference_stages(env,context,tracking_stall_timeout_s=10.)


def patient_direct_exit_stages(env, context):
    """Use the measured feedback grasp and attempt its exit without repositioning."""
    candidates=(dict(angle_deg=90.,yaw_deg=0.,translation_m=[0.,.10,-.04],
                     hold_s=8.,sample_duration_s=.1,restore=False),)
    return stages(env,context,folded_settling=True,suspended_handoff=True,
        handoff_candidates=candidates,
        withdrawal_defaults=dict(rebase_support_each_stage=False,gate_support_tracking=False,
            position_bias_limit_m=.06,position_integral_gain_s_inv=2.,
            position_velocity_gain_s=.25,position_velocity_filter_s=.1,
            tracking_stall_timeout_s=10.,maximum_stages=1000,
            exit_goal_mode='all_axes',search_seed=970,
            passive_contact_names=['horseshoe_left','chain_upper_1','chain_lower_1']))


def patient_upward_pivot_stages(env, context, *, adaptive_grasp=False, native_robot_contacts=False):
    """Try an alternate ring grasp and pivot while keeping the lower shoe fixed."""
    candidates=(dict(angle_deg=90.,yaw_deg=0.,translation_m=[0.,.10,-.04],
                     hold_s=8.,sample_duration_s=.1,restore=False),)
    return stages(env,context,folded_settling=True,suspended_handoff=True,
        handoff_candidates=candidates,
        native_robot_contacts=native_robot_contacts,
        ring_grasp_choice=None if adaptive_grasp else
            dict(angle_deg=295.,approach_sign=1,flip=-1,tangent_roll_deg=40.),
        require_ring_pivot=adaptive_grasp,
        withdrawal_defaults=dict(rebase_support_each_stage=False,gate_support_tracking=False,
            robot_puzzle_clearance_m=.0001,
            position_bias_limit_m=.06,position_integral_gain_s_inv=2.,
            position_velocity_gain_s=.25,position_velocity_filter_s=.1,
            tracking_stall_timeout_s=10.,maximum_stages=1000,
            exit_goal_mode='reference_pivot',search_seed=985,joint_search_goal_tube=adaptive_grasp,
            passive_contact_names=['horseshoe_left','chain_upper_1','chain_lower_1']))


def adaptive_upward_pivot_stages(env, context):
    """Select the ring grasp from the actual handoff and screen its pivot endpoint."""
    return patient_upward_pivot_stages(env,context,adaptive_grasp=True)


def contact_upward_pivot_stages(env, context):
    """Use native contact classification after the unchanged fixed-grip handoff."""
    return patient_upward_pivot_stages(env,context,native_robot_contacts=True)


def gravity_release_table_pickup_stages(env, context):
    """Fold and transfer the ring, using gravity or an active suspended pickup."""
    return stages(env,context,folded_settling=True,suspended_handoff=True,
        handoff_candidates=(dict(angle_deg=90.,yaw_deg=0.,translation_m=[0.,.10,-.04],
            hold_s=8.,sample_duration_s=.1,restore=False),),
        native_robot_contacts=True,table_pickup_after_release=True,
        ring_grasp_choice=dict(tcp_backoff_m=.01531))


def zero_angle_ring_grasp_stages(env, context):
    """Use the grasp screened for both pivot and complete ring withdrawal.

    Candidate geometry is supplied by the scene owner. This recipe uses only
    measured observations, native planning and ordinary robot actions.
    """
    return stages(env,context,folded_settling=True,suspended_handoff=True,
        handoff_candidates=(dict(angle_deg=90.,yaw_deg=0.,translation_m=[0.,.10,-.04],
            hold_s=8.,sample_duration_s=.1,restore=False),),
        native_robot_contacts=True,
        ring_grasp_choice=dict(angle_deg=0.,approach_sign=1,flip=-1,tangent_roll_deg=0.),
        require_ring_pivot=True,
        withdrawal_defaults=dict(rebase_support_each_stage=False,gate_support_tracking=False,
            robot_puzzle_clearance_m=.0001,position_bias_limit_m=.1,
            rotation_bias_limit_rad=.3,position_integral_gain_s_inv=2.,
            position_velocity_gain_s=.25,position_velocity_filter_s=.1,
            tracking_stall_timeout_s=30.,maximum_stages=1000,
            exit_goal_mode='reference_pivot',search_seed=1005,joint_search_goal_tube=True,
            refine_short_stage_prefix=True,refine_ik_compensation=True,direct_axis_exit_first=True,
            passive_contact_names=['horseshoe_left','chain_upper_1','chain_lower_1']))


def reference_tube_exit_stages(env, context):
    """Keep the existing pivot recipe, then prefer reference-exit search tubes.

    The switch only changes search proposals at the measured pivot milestone.
    Each candidate still replans from its actual observation and uses the same
    geometry, contact, grasp, action and independent qualification checks.
    """
    original=contact_upward_pivot_stages(env,context)
    switched=False
    try:
        for step in original:
            if (not switched and step.name.startswith('withdraw_')
                    and step.candidates
                    and step.candidates[0].get('exit_goal_mode')=='reference'):
                candidates=tuple(dict(parameters,search_seed=995+i,
                    joint_search_goal_tube=True,
                    passive_contact_names=['horseshoe_left','chain_upper_1','chain_lower_1'])
                    for i,parameters in enumerate(step.candidates))
                step=replace(step,candidates=candidates)
                write_json_atomic(Path(context.output)/'reference_exit_search_switch.json',
                    dict(step=step.name,candidates=candidates,
                         scope='Search proposals only, after measured reference pivot; physical exit and native goal remain unverified'))
                switched=True
            yield step
    finally:
        original.close()


def patient_reference_tube_exit_stages(env, context):
    """Refine checked exit prefixes and allow slow contact response after pivot.

    The home, fold, handoff and pivot recipe remains unchanged. Only measured
    post-pivot withdrawal candidates receive these planner/controller options.
    """
    original=reference_tube_exit_stages(env,context)
    recorded=False
    try:
        for step in original:
            if (step.name.startswith('withdraw_') and step.candidates
                    and step.candidates[0].get('exit_goal_mode')=='reference'):
                candidates=tuple(dict(parameters,
                    speed_m_s=min(float(parameters['speed_m_s']),.001),
                    tracking_stall_timeout_s=30.,position_bias_limit_m=.1,
                    refine_short_stage_prefix=True,
                    passive_contact_names=['horseshoe_left','chain_upper_1','chain_lower_1'])
                    for parameters in step.candidates)
                step=replace(step,candidates=candidates)
                if not recorded:
                    write_json_atomic(Path(context.output)/'patient_reference_exit_switch.json',
                        dict(step=step.name,candidates=candidates,
                             scope='Checked short-prefix refinement and ordinary feedback only; native physical qualification remains required'))
                    recorded=True
            yield step
    finally:
        original.close()


def rotation_compensated_reference_exit_stages(env, context):
    """Allow bounded rotational load compensation after the measured pivot."""
    original=patient_reference_tube_exit_stages(env,context)
    recorded=False
    try:
        for step in original:
            if (step.name.startswith('withdraw_') and step.candidates
                    and step.candidates[0].get('exit_goal_mode')=='reference'):
                candidates=tuple(dict(parameters,rotation_bias_limit_rad=.3)
                                 for parameters in step.candidates)
                step=replace(step,candidates=candidates)
                if not recorded:
                    write_json_atomic(Path(context.output)/'rotation_compensation_exit_switch.json',
                        dict(step=step.name,candidates=candidates,
                             scope='Ordinary target generation only; no change to native gains, forces, constraints or acceptance'))
                    recorded=True
            yield step
    finally:
        original.close()


def canonical_first_reference_exit_stages(env, context):
    """Try the reference suffix locally before searching an exit detour."""
    original=rotation_compensated_reference_exit_stages(env,context)
    recorded=False
    try:
        for step in original:
            if (step.name.startswith('withdraw_') and step.candidates
                    and step.candidates[0].get('exit_goal_mode')=='reference'):
                candidates=tuple(dict(parameters,prefer_reference_exit_guide=index==0)
                                 for index,parameters in enumerate(step.candidates))
                step=replace(step,candidates=candidates)
                if not recorded:
                    write_json_atomic(Path(context.output)/'canonical_first_exit_switch.json',
                        dict(step=step.name,candidates=candidates,
                             scope='Reference suffix is a local guide; measured IK/contact checks and physical qualification remain mandatory, joint-search fallbacks retained'))
                    recorded=True
            yield step
    finally:
        original.close()


def direct_first_reference_exit_stages(env, context):
    """Check a dense Cartesian exit before planning a longer joint detour."""
    original=rotation_compensated_reference_exit_stages(env,context)
    recorded=False
    try:
        for step in original:
            if (step.name.startswith('withdraw_') and step.candidates
                    and step.candidates[0].get('exit_goal_mode')=='reference'):
                candidates=tuple(dict(parameters,direct_axis_exit_first=True)
                                 for parameters in step.candidates)
                step=replace(step,candidates=candidates)
                if not recorded:
                    write_json_atomic(Path(context.output)/'direct_axis_exit_switch.json',
                        dict(step=step.name,candidates=candidates,
                             scope='Dense checked direct exit proposals only; native physics and success unchanged'))
                    recorded=True
            yield step
    finally:
        original.close()


def native_limit_reference_exit_stages(env, context):
    """Use the native ordinary-contact ceiling for post-pivot candidates."""
    original=canonical_first_reference_exit_stages(env,context)
    recorded=False
    try:
        for step in original:
            if (step.name.startswith('withdraw_') and step.candidates
                    and step.candidates[0].get('exit_goal_mode')=='reference'):
                candidates=tuple(dict(parameters,contact_limit_m=.001,direct_axis_exit_first=True)
                                 for parameters in step.candidates)
                step=replace(step,candidates=candidates)
                if not recorded:
                    write_json_atomic(Path(context.output)/'native_contact_exit_switch.json',
                        dict(step=step.name,candidates=candidates,
                             scope='Planner and per-tick stage guard use the unchanged native 1mm ordinary limit; native qualified fingers remain2mm. Direct checked exit fallback enabled.'))
                    recorded=True
            yield step
    finally:
        original.close()


def refined_native_limit_reference_exit_stages(env, context):
    """Refine IK feedback reduction only after the measured reference pivot."""
    original=native_limit_reference_exit_stages(env,context)
    recorded=False
    try:
        for step in original:
            if (step.name.startswith('withdraw_') and step.candidates
                    and step.candidates[0].get('exit_goal_mode')=='reference'):
                candidates=tuple(dict(parameters,refine_ik_compensation=True)
                                 for parameters in step.candidates)
                step=replace(step,candidates=candidates)
                if not recorded:
                    write_json_atomic(Path(context.output)/'refined_ik_exit_switch.json',
                        dict(step=step.name,candidates=candidates,
                             scope='Fine feedback-compensation reduction after native IK rejection; measured seed, IK tolerances, physics and success remain unchanged.'))
                    recorded=True
            yield step
    finally:
        original.close()


def table_supported_stages(env, context):
    """Transport the folded pair toward the table before releasing the upper shoe."""
    return stages(env,context,folded_settling=True,suspended_handoff=True,
        native_robot_contacts=True,table_supported=True,
        handoff_candidates=(dict(angle_deg=90.,yaw_deg=0.,translation_m=[0.,.10,-.04],
                                hold_s=8.,sample_duration_s=.1,restore=False),),
        withdrawal_defaults=dict(rebase_support_each_stage=False,gate_support_tracking=False,
            robot_puzzle_clearance_m=.0001,position_bias_limit_m=.06,
            position_integral_gain_s_inv=2.,position_velocity_gain_s=.25,
            position_velocity_filter_s=.1,tracking_stall_timeout_s=10.,maximum_stages=1000,
            exit_goal_mode='all_axes',search_seed=995,joint_search_goal_tube=True,
            passive_contact_names=['horseshoe_left','chain_upper_1','chain_lower_1']))


def replayed_grasp_stages(env, context):
    """Reproduce a checked grasp with ordinary controls, then plan its exit."""
    return stages(env,context,require_prefix_replay=True,
        withdrawal_defaults=dict(rebase_support_each_stage=False,gate_support_tracking=False,
            position_bias_limit_m=.06,position_integral_gain_s_inv=2.,
            position_velocity_gain_s=.25,position_velocity_filter_s=.1,
            tracking_stall_timeout_s=10.,maximum_stages=1000,
            exit_goal_mode='all_axes',search_seed=970,
            passive_contact_names=['horseshoe_left','chain_upper_1','chain_lower_1']))
