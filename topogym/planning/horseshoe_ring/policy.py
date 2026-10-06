"""Measured Horseshoe manipulation through ordinary public actions only."""
import numpy as np
from scipy.spatial.transform import Rotation

from topogym.planning.rigid_reference.feedback import body_pose, tcp_pose, relative_pose
from topogym.planning.rigid_reference.geometry import interpolate


class HorseshoePolicy:
    def __init__(self, grasps, *, part='pickup', fold=None, support=None, planner=None, settle_tilt_deg=0., settle_axis='y', settle_secondary_y_deg=0., settle_translation=(0.,0.,0.), fold_tracking_m=.001, post_fold_hold_s=2., withdrawal_mode='full', withdrawal_parameters=None):
        self.grasps, self.part, self.fold = grasps, part, fold
        self.support=support
        self.planner=planner
        self.settle_tilt_deg=float(settle_tilt_deg)
        self.settle_axis=settle_axis
        self.settle_secondary_y_deg=float(settle_secondary_y_deg)
        self.settle_translation=np.asarray(settle_translation,dtype=float)
        self.fold_tracking_m=float(fold_tracking_m)
        if isinstance(post_fold_hold_s,bool) or not np.isfinite(post_fold_hold_s) or not 0<=post_fold_hold_s<=10:
            raise ValueError('Post-fold hold must be between 0 and 10 seconds')
        self.post_fold_hold_s=float(post_fold_hold_s)
        self.withdrawal_mode=withdrawal_mode
        self.withdrawal_parameters=dict(speed_m_s=.004,tracking_m=.0015,stage_motion_m=.012,
            maximum_stages=200,search_seed=922,
            support_tracking_m=None,
            position_bias_limit_m=.03,
            rotation_bias_limit_rad=.15,
            position_integral_gain_s_inv=2.,
            position_velocity_gain_s=0.,
            position_velocity_filter_s=0.,
            tracking_stall_timeout_s=None,
            rebase_support_each_stage=False,
            gate_support_tracking=True,
            exit_goal_mode='all_axes',
            robot_puzzle_clearance_m=.0005,
            joint_search_goal_tube=False,
            refine_short_stage_prefix=False,
            refine_ik_compensation=False,
            prefer_reference_exit_guide=False,
            direct_axis_exit_first=False,
            puzzle_contact_limit_m=None,
            check_static_passive_links=True,
            passive_contact_names=['horseshoe_left','chain_upper_1','chain_lower_1'])
        if withdrawal_parameters:
            unknown=set(withdrawal_parameters)-self.withdrawal_parameters.keys()
            if unknown:raise ValueError(f'Unknown withdrawal parameters: {unknown}')
            self.withdrawal_parameters.update(withdrawal_parameters)
        if not isinstance(self.withdrawal_parameters['check_static_passive_links'],bool):
            raise ValueError('Static passive topology option must be boolean')
        if not isinstance(self.withdrawal_parameters['joint_search_goal_tube'],bool):
            raise ValueError('Joint goal tube search option must be boolean')
        if not isinstance(self.withdrawal_parameters['refine_short_stage_prefix'],bool):
            raise ValueError('Short-stage prefix refinement option must be boolean')
        if not isinstance(self.withdrawal_parameters['refine_ik_compensation'],bool):
            raise ValueError('IK compensation refinement option must be boolean')
        if not isinstance(self.withdrawal_parameters['prefer_reference_exit_guide'],bool):
            raise ValueError('Reference exit guide preference must be boolean')
        if not isinstance(self.withdrawal_parameters['direct_axis_exit_first'],bool):
            raise ValueError('Direct axis exit preference must be boolean')
        if not isinstance(self.withdrawal_parameters['rebase_support_each_stage'],bool):
            raise ValueError('Support rebasing option must be boolean')
        if not isinstance(self.withdrawal_parameters['gate_support_tracking'],bool):
            raise ValueError('Support tracking gate option must be boolean')
        if self.withdrawal_parameters['exit_goal_mode'] not in ('all_axes','reference','reference_pivot'):
            raise ValueError('Exit goal mode must be all_axes, reference or reference_pivot')
        support_tracking=self.withdrawal_parameters['support_tracking_m']
        if support_tracking is not None and (not np.isfinite(float(support_tracking))
                or not .00005<=float(support_tracking)<=.005):
            raise ValueError('Support tracking tolerance must be between 0.05 and 5 mm')
        bias_limit=float(self.withdrawal_parameters['position_bias_limit_m'])
        if not np.isfinite(bias_limit) or not .001<=bias_limit<=.10:
            raise ValueError('Position feedback bias limit must be between 1 and 100 mm')
        rotation_limit=float(self.withdrawal_parameters['rotation_bias_limit_rad'])
        if not np.isfinite(rotation_limit) or not .01<=rotation_limit<=.4:
            raise ValueError('Rotation feedback bias limit must be between 0.01 and 0.4 rad')
        for key,high in (('position_integral_gain_s_inv',4.),('position_velocity_gain_s',1.),
                         ('position_velocity_filter_s',2.)):
            value=float(self.withdrawal_parameters[key])
            if not np.isfinite(value) or not 0<=value<=high:raise ValueError(f'Invalid {key}')
        stall=self.withdrawal_parameters['tracking_stall_timeout_s']
        if stall is not None and (not np.isfinite(float(stall)) or not .1<=float(stall)<=30.):
            raise ValueError('Tracking stall window must be between 0.1 and 30 seconds')
        clearance=float(self.withdrawal_parameters['robot_puzzle_clearance_m'])
        if not np.isfinite(clearance) or not .00005<=clearance<=.0005:
            raise ValueError('Invalid robot/puzzle planning clearance')
        contact=self.withdrawal_parameters['puzzle_contact_limit_m']
        if contact is not None and (isinstance(contact,bool) or not np.isfinite(float(contact))
                                    or not 0<float(contact)<=.001):
            raise ValueError('Puzzle planning contact must be within the native 1 mm limit')
        for key in ('speed_m_s','tracking_m','stage_motion_m'):
            value=float(self.withdrawal_parameters[key])
            if not np.isfinite(value) or value<=0:raise ValueError(f'Invalid {key}')
        if not 1<=int(self.withdrawal_parameters['maximum_stages'])<=1000:
            raise ValueError('Withdrawal stage count must be between 1 and 1000')
        self.phase = 'created'
        self.diagnostics = {}

    def initialize(self, context):
        spec = context['action_spec']
        if spec['robot_id'] != 'aloha' or spec['mode'] != 'EE_ABS':
            raise ValueError('HorseshoePolicy requires ALOHA EE_ABS')
        if context['mode'] != 'unlimited':
            raise ValueError('Measured oracle requires explicitly granted world observations')
        self.dt = context['timing_spec']['control_dt_s']
        self.grip = {side:float(g.get('open_position_m',.027)) for side,g in self.grasps.items()}
        self.program = None
        self.bias = {s:np.zeros(3) for s in self.grasps}
        self.angle_bias = {s:np.zeros(3) for s in self.grasps}
        self.held_entities={s:'horseshoe_'+s for s in self.grasps}
        self.nominal_tcp={}
        self.velocity_feedback_state={}

    def act(self, observation):
        self.obs = observation
        if self.program is None:self.program=self.actions()
        return next(self.program,None)

    def time(self):return self.obs['state']['sim_time_s']
    def tcp(self):return {s:tcp_pose(self.obs['robot'][s]) for s in self.grasps}
    def bodies(self):return {s:body_pose(self.obs['privileged']['world']['bodies'][n]) for s,n in self.held_entities.items()}
    def command(self, poses, *, nominal=None):
        self.nominal_tcp=nominal or {}
        return {s:dict(position_world_m=p.tolist(),orientation_wxyz=r.as_quat()[[3,0,1,2]].tolist(),
                       gripper_position_m=self.grip[s]) for s,(p,r) in poses.items()}

    def hold(self, seconds):
        start=self.time()
        while self.time()-start<seconds-1e-8:yield {}

    def move(self, target, seconds, phase, *, tracking_timeout_s=5.):
        self.phase=phase;start=self.time();initial=self.tcp()
        while True:
            t=min(1.,(self.time()-start+self.dt)/seconds);u=t**3*(10+t*(-15+6*t))
            yield self.command({s:interpolate(initial[s],target[s],u) for s in target})
            if t>=1.:break
        yield from self.hold(.35)
        started=self.time();bias={s:np.zeros(3) for s in target};angles={s:np.zeros(3) for s in target}
        while True:
            actual=self.tcp()
            errors={s:float(np.linalg.norm(actual[s][0]-target[s][0])) for s in target}
            self.diagnostics=dict(tcp_errors_m=errors)
            if max(errors.values())<.0005:break
            if self.time()-started>tracking_timeout_s:raise RuntimeError(f'TCP tracking failed: {errors}')
            commands={}
            for s,(p,r) in target.items():
                bias[s]=np.clip(bias[s]+2*self.dt*(p-actual[s][0]),-.015,.015)
                angles[s]=np.clip(angles[s]+2*self.dt*(r*actual[s][1].inv()).as_rotvec(),-.08,.08)
                commands[s]=(p+bias[s],Rotation.from_rotvec(angles[s])*r)
            yield self.command(commands)

    def approach_joints(self, seconds):
        final={s:np.asarray(g['pre_qpos'])[(0 if s=='left' else 8):][:6] for s,g in self.grasps.items()}
        yield from self.move_joints(final,seconds,'approach_above_shoes')

    def move_joints(self, final, seconds, phase):
        self.phase=phase;start=self.time()
        initial={s:np.asarray(self.obs['robot'][s]['joint_position_rad']) for s in final}
        while True:
            t=min(1.,(self.time()-start+self.dt)/seconds);u=t**3*(10+t*(-15+6*t))
            yield {s:dict(joint_position_rad=(initial[s]+u*(final[s]-initial[s])).tolist(),
                          gripper_position_m=self.grip[s]) for s in final}
            if t>=1.:break
        yield from self.hold(.5)

    def feedback_velocity(self, side, filter_s):
        """Filter control-period displacement rather than substep-end jitter."""
        name=self.held_entities[side]
        body=self.obs['privileged']['world']['bodies'][name]
        if filter_s<=0:return np.asarray(body['linear_velocity_m_s'])
        now=self.time();position=np.asarray(body['position_m'])
        previous=self.velocity_feedback_state.get(side)
        if previous is None or previous['body']!=name or now<previous['time_s']:
            previous=dict(body=name,time_s=now,position_m=position.copy(),velocity_m_s=np.zeros(3))
            self.velocity_feedback_state[side]=previous
        elif now>previous['time_s']:
            elapsed=now-previous['time_s']
            average=(position-previous['position_m'])/elapsed
            alpha=-np.expm1(-elapsed/filter_s)
            previous['velocity_m_s']+=alpha*(average-previous['velocity_m_s'])
            previous.update(time_s=now,position_m=position.copy())
        # Two adjacent stages may consume the same observation. Do not
        # differentiate or decay it twice without an intervening physics tick.
        return previous['velocity_m_s'].copy()

    def follow_bodies(self, target, seconds, phase, *, pose_at=None, tracking_m=.002, tracking_limits=None,
                      progress_sides=None, fixed_sides=(), position_bias_limit_m=.03,
                      rotation_bias_limit_rad=.15,
                      position_integral_gain_s_inv=2.,position_velocity_gain_s=0.,
                      position_velocity_filter_s=0.,tracking_stall_timeout_s=None):
        self.phase=phase;start=self.time();initial=self.bodies();progress=0.;last_progress=start
        tracking_limits=tracking_limits or {}
        progress_sides=set(target if progress_sides is None else progress_sides)
        if not progress_sides or not progress_sides<=set(target):raise ValueError('Invalid tracking gate hands')
        fixed_sides=set(fixed_sides)
        if not fixed_sides<=set(target):raise ValueError('Invalid fixed target hands')
        while True:
            desired=pose_at(progress) if pose_at else {s:interpolate(initial[s],target[s],progress) for s in target}
            for side in fixed_sides:desired[side]=target[side]
            actual=self.bodies();commands={};errors={};nominal={};damping={}
            for s,(p,r) in desired.items():
                ep=p-actual[s][0];er=(r*actual[s][1].inv()).as_rotvec()
                self.bias[s]=np.clip(self.bias[s]+position_integral_gain_s_inv*self.dt*ep,
                                     -position_bias_limit_m,position_bias_limit_m)
                self.angle_bias[s]=np.clip(self.angle_bias[s]+2*self.dt*er,
                                           -rotation_bias_limit_rad,rotation_bias_limit_rad)
                cr=Rotation.from_rotvec(self.angle_bias[s]+.5*er)*r
                velocity=(self.feedback_velocity(s,position_velocity_filter_s)
                          if position_velocity_gain_s else np.zeros(3))
                damping[s]=np.clip(position_velocity_gain_s*velocity,-.02,.02)
                commands[s]=(p+self.bias[s]+.5*ep-damping[s]+cr.apply(self.offsets[s][0]),cr*self.offsets[s][1])
                nominal[s]=(p+r.apply(self.offsets[s][0]),r*self.offsets[s][1])
                errors[s]=float(np.linalg.norm(ep)+.10*np.linalg.norm(er))
            self.diagnostics=dict(progress=progress,material_tracking_errors_m=errors,
                                  progress_gated_hands=sorted(progress_sides),
                                  fixed_body_target_hands=sorted(fixed_sides),
                                  position_bias_m={s:self.bias[s].tolist() for s in desired},
                                  position_bias_limit_m=position_bias_limit_m,
                                  rotation_bias_rad={s:self.angle_bias[s].tolist() for s in desired},
                                  rotation_bias_limit_rad=rotation_bias_limit_rad,
                                  position_integral_gain_s_inv=position_integral_gain_s_inv,
                                  position_velocity_gain_s=position_velocity_gain_s,
                                  position_velocity_filter_s=position_velocity_filter_s,
                                  tracking_stall_timeout_s=tracking_stall_timeout_s,
                                  velocity_feedback_m={s:v.tolist() for s,v in damping.items()})
            if all(errors[side]<tracking_limits.get(side,tracking_m) for side in progress_sides):
                if progress>=1.:break
                progress=min(1.,progress+self.dt/seconds)
                last_progress=self.time()
            if tracking_stall_timeout_s is None:
                stalled=self.time()-start>seconds*4+10
            else:
                # The enclosing qualification stage still has its hard
                # 50 s budget. Intermittent forward progress is not a stall.
                stalled=self.time()-last_progress>tracking_stall_timeout_s
            if stalled:raise RuntimeError(f'Object tracking stalled: {self.diagnostics}')
            yield self.command(commands,nominal=nominal)

    def turn_pair(self, angle_deg, seconds, phase, *, axis=None):
        initial=self.bodies();center=np.mean([p for p,r in initial.values()],axis=0)
        def poses(u):
            turn=Rotation.from_euler(axis or self.settle_axis,angle_deg*u,degrees=True)
            return {s:(center+turn.apply(p-center),turn*r) for s,(p,r) in initial.items()}
        yield from self.follow_bodies(poses(1.),seconds,phase,pose_at=poses)

    def follow_fold(self):
        self.phase='flip_and_fold';start=self.time();last_progress=start;progress=0.
        # Reference phase 0..1000 is the narrow flip. Give it 20 s, the
        # remaining fold 35 s. Measured tracking gates the reference clock.
        while True:
            i=min(len(self.fold)-2,int(progress));u=min(1.,progress-i)
            target={s:interpolate(self.fold[i]['horseshoe_'+s],self.fold[i+1]['horseshoe_'+s],u) for s in self.grasps}
            actual=self.bodies();commands={};errors={};nominal={}
            for s,(p,r) in target.items():
                ep=p-actual[s][0];er=(r*actual[s][1].inv()).as_rotvec()
                self.bias[s]=np.clip(self.bias[s]+3*self.dt*ep,-.04,.04)
                self.angle_bias[s]=np.clip(self.angle_bias[s]+3*self.dt*er,-.2,.2)
                cr=Rotation.from_rotvec(self.angle_bias[s]+.5*er)*r
                commands[s]=(p+self.bias[s]+.5*ep+cr.apply(self.offsets[s][0]),cr*self.offsets[s][1])
                nominal[s]=(p+r.apply(self.offsets[s][0]),r*self.offsets[s][1])
                errors[s]=float(np.linalg.norm(ep)+.10*np.linalg.norm(er))
            self.diagnostics=dict(reference_index=progress,material_tracking_errors_m=errors)
            if max(errors.values())<self.fold_tracking_m:
                if progress>=len(self.fold)-1:break
                rate=50. if progress<1000 else (len(self.fold)-1000)/35.
                progress=min(len(self.fold)-1,progress+self.dt*rate)
                last_progress=self.time()
            if self.time()-last_progress>30.:raise RuntimeError(f'Fold stopped making progress: {self.diagnostics}')
            if self.time()-start>360.:raise RuntimeError(f'Fold tracking stalled: {self.diagnostics}')
            yield self.command(commands,nominal=nominal)

    def support_pair(self):
        """Place the upper shoe on the held lower shoe and free the left hand."""
        if self.support is None:raise ValueError('Support requires a checked target pose')
        initial=self.bodies();lp,lr=initial['left']
        suspended=bool(getattr(self,'suspended_upper',False))
        table_supported=bool(getattr(self,'table_supported',False))
        if suspended or table_supported:self.support=[initial['left'],initial['left']]
        knots=[initial['left'],*self.support[1:]]
        def poses(u):
            progress=u*(len(knots)-1);index=min(len(knots)-2,int(progress))
            p,r=interpolate(knots[index],knots[index+1],progress-index);turn=r*lr.inv()
            return {s:(p+turn.apply(bp-lp),turn*br) for s,(bp,br) in initial.items()}
        stationary=(np.linalg.norm(self.support[-1][0]-self.support[0][0])<1e-8
                    and (self.support[-1][1]*self.support[0][1].inv()).magnitude()<1e-8)
        if stationary:
            # The fold already reached this checked support orientation.
            # Preserve the measured rest pose instead of integrating a new
            # correction into a nearly saturated wrist.
            dp=np.linalg.norm(lp-self.support[-1][0])
            dr=(lr*self.support[-1][1].inv()).magnitude()
            if dp>.005 or dr>.05:raise RuntimeError('Measured fold endpoint is outside the stationary support neighbourhood')
            self.phase='stationary_support'
        else:
            yield from self.follow_bodies(poses(1.),12.,'orient_horizontal_stack',pose_at=poses)
        self.phase='stack_settle';yield from self.hold(2.)
        before=self.bodies()
        self.grip['left']=.027
        self.phase='release_upper_shoe';yield {'left':dict(gripper_position_m=.027)}
        yield from self.hold(1.)
        if self.planner is None:raise ValueError('Support handoff requires checked free-hand retreat')
        retreat=self.planner.withdraw_left(self.obs,allow_release_contact=suspended or table_supported,
                                          joint_retreat=getattr(self,'joint_release_retreat',False))
        if not retreat.get('joint_retreat'):
            yield from self.move({'left':body_pose(retreat['target_tcp'])},3.,'withdraw_left_hand')
        if retreat.get('free_transit'):
            indices=self.planner.robot._q_indices['left'][:6]
            for index,q in enumerate(retreat['free_transit']['waypoints'][1:]):
                target=np.asarray(q)[indices]
                current=np.asarray(self.obs['robot']['left']['joint_position_rad'])
                seconds=max(.5,float(np.max(np.abs(target-current)))/.3)
                yield from self.move_joints({'left':target},seconds,f'clear_left_hand_{index}')
        self.phase='support_settle';yield from self.hold(3.)
        if suspended or table_supported:
            # At an inverted support angle gravity can open the pair instead
            # of clamping the ring. The released shoe is free to hang from
            # the original chains. Wait for its measured motion and the
            # ring's motion to settle before planning the next grasp.
            turns=[None]
            if getattr(self,'release_turn',None) is not None:turns.append(self.release_turn)
            for turn in turns:
                tracking=.002
                if turn is not None:
                    from .settling import plan_supported_tilt
                    plan=plan_supported_tilt(self.planner,self.obs,axis=turn.get('axis','tool'),angle_deg=turn.get('angle_deg',60.))
                    tracking=float(turn.get('tracking_m',.003))
                    for index,row in enumerate(plan['poses'][1:]):
                        yield from self.follow_bodies({'right':body_pose(row['right_pose'])},.1,
                            f'turn_supported_pair_{index}',tracking_m=tracking,position_bias_limit_m=.05)
                    yield from self.follow_bodies({'right':body_pose(plan['poses'][-1]['right_pose'])},3.,
                        'hold_supported_turn',tracking_m=tracking,position_bias_limit_m=.05)
                started=self.time();stable=0.;support=self.bodies()['right']
                while stable<.5:
                    yield from self.follow_bodies({'right':support},.25,
                        'settle_table_supported_pair' if table_supported else 'settle_suspended_pair',tracking_m=tracking)
                    world=self.obs['privileged']['world']['bodies']
                    quiet=all(np.linalg.norm(world[n]['linear_velocity_m_s'])<.005 and
                              np.linalg.norm(world[n]['angular_velocity_rad_s'])<.05
                              for n in ('horseshoe_left','target_ring'))
                    stable=stable+.25 if quiet else 0.
                    if self.time()-started>30.:raise RuntimeError('Released shoe and ring did not become quiet')
        hands=self.obs['privileged']['world']['grasp']['hands']
        if hands['left']['binding'] is not None or not hands['right']['binding']:
            raise RuntimeError('Support handoff did not release only the left hand')
        after=self.bodies()
        displacement=float(np.linalg.norm(after['left'][0]-before['left'][0]))
        turn=float((after['left'][1]*before['left'][1].inv()).magnitude())
        self.diagnostics=dict(upper_shoe_displacement_m=displacement,upper_shoe_rotation_rad=turn)
        self.diagnostics['support_mode']=('table' if table_supported else
                                         'suspended_from_original_chains' if suspended else 'horizontal_stack')
        if table_supported:
            p,r=after['left']
            gap=float((r.apply(self.planner.task.placement_vertices['horseshoe_left'])+p)[:,2].min())-self.planner.checker.table_height
            self.diagnostics['upper_table_gap_m']=gap
            if not -.0008<=gap<=.003:raise RuntimeError(f'Upper shoe did not settle at the table: {gap}')
        elif not suspended and (displacement>.04 or turn>.2):raise RuntimeError(f'Upper shoe did not remain supported: {self.diagnostics}')
        self.phase='support_complete'

    def gravity_settle_folded(self):
        """Keep both shoes held and let gravity relocate the unheld ring."""
        from .settling import plan_folded_tilt, folded_ring_metric
        from topogym.utils.io import write_json_atomic
        params=self.settling_parameters
        sample_duration=float(params.get('sample_duration_s',.25))
        tracking=float(params.get('tracking_m',.002))
        feedback=dict(position_bias_limit_m=float(params.get('position_bias_limit_m',.03)))
        self.phase='plan_folded_gravity_settle'
        before=folded_ring_metric(self.planner,self.obs)
        plan=plan_folded_tilt(self.planner,self.obs,params['angle_deg'],
            translation_m=params.get('translation_m',(0.,0.,0.)),roll_deg=params.get('roll_deg',0.),yaw_deg=params.get('yaw_deg',0.))
        poses=[{s:body_pose(row['shoes'][s]) for s in self.grasps} for row in plan['poses']]
        for index,target in enumerate(poses[1:]):
            yield from self.follow_bodies(target,sample_duration,f'tilt_folded_pair_{index}',tracking_m=tracking,**feedback)
        yield from self.follow_bodies(poses[-1],float(params.get('hold_s',8.)),
                                      'hold_folded_pair_for_gravity',tracking_m=tracking,**feedback)
        tilted=folded_ring_metric(self.planner,self.obs)
        write_json_atomic(self.planner.directory/'tilted_observation.json',self.obs)
        restore=params.get('restore',True)
        if restore:
            for index,target in enumerate(poses[-2::-1]):
                yield from self.follow_bodies(target,sample_duration,f'restore_folded_pair_{index}',tracking_m=tracking,**feedback)
            yield from self.follow_bodies(poses[0],2.,'settle_restored_folded_pair',tracking_m=tracking,**feedback)
        after=folded_ring_metric(self.planner,self.obs)
        write_json_atomic(self.planner.directory/('restored_observation.json' if restore else 'handoff_observation.json'),self.obs)
        improved=(after['longitudinal_position_m']>=after['reference_longitudinal_position_m']-.025
                  or after['maximum_separating_gap_m']>.005)
        actual=self.bodies();target=poses[0] if restore else poses[-1]
        errors={s:float(np.linalg.norm(actual[s][0]-target[s][0])+.10*(actual[s][1]*target[s][1].inv()).magnitude()) for s in target}
        self.gravity_result=dict(passed=improved if restore else max(errors.values())<tracking,
            material_tracking_tolerance_m=tracking,
            ring_relocated=improved,restored=restore,body_target_errors_m=errors,before=before,tilted=tilted,after=after,
            scope='measured gravity settling' if restore else 'orientation prepared for suspended handoff; no ring relocation requirement')
        write_json_atomic(self.planner.directory/'gravity_result.json',self.gravity_result)
        self.diagnostics=dict(gravity_result=self.gravity_result)
        self.phase='folded_gravity_settle_complete'

    def clear_remainder_for_table_pickup(self):
        from .placement import clear_remainder_for_table_pickup
        plan=clear_remainder_for_table_pickup(self.planner,self.obs)
        for index,row in enumerate(plan['poses'][1:]):
            target=body_pose(row)
            distance=float(np.linalg.norm(target[0]-self.bodies()['right'][0]))
            yield from self.follow_bodies({'right':target},max(.5,distance/.008),
                f'clear_remainder_{index}',tracking_m=.0015)
        self.phase='clear_remainder_settle'
        yield from self.hold(2.)
        self.table_pickup_clearance_result=plan

    def lift_ring_for_transport(self):
        from .placement import lift_ring_from_table
        plan=lift_ring_from_table(self.planner,self.obs)
        yield from self.follow_bodies({'left':body_pose(plan['samples'][-1]['pose'])},4.,
                                     'lift_ring_from_table',tracking_m=.0015)
        p,r=self.bodies()['left']
        gap=float((r.apply(self.planner.task.placement_vertices['target_ring'])+p)[:,2].min())-self.planner.checker.table_height
        if gap<.01:raise RuntimeError('Measured ring did not lift clear of the table')

    def lift_ring_from_birth(self):
        """Contact diagnostic with free chains; a clear endpoint alone is insufficient.

        Every command goes through native IK and the workflow's physical
        guard. The independently audited execution must validate the contact
        prefix; this is not a collision-free object-space lift certificate.
        """
        from topogym.utils.io import write_json_atomic
        initial=self.bodies()['left'];rows=[]
        for height in (.002,.005,.01,.02,.04,.08):
            current=self.bodies()['left']
            target=(initial[0]+[0,0,height],initial[1])
            seconds=max(2.,float(np.linalg.norm(target[0]-current[0])/.001))
            yield from self.follow_bodies({'left':target},seconds,f'birth_contact_lift_{height:.3f}',tracking_m=.0015)
            bodies,_=self.planner.observed(self.obs)
            p,r=bodies['target_ring'];ring=r.apply(self.planner.task.placement_vertices['target_ring'])+p
            remainder=np.vstack([r.apply(self.planner.task.placement_vertices[n])+p
                for n,(p,r) in bodies.items() if n!='target_ring'])
            gap=max(float((ring@axis).min()-(remainder@axis).max()) for axis in (*np.eye(3),*-np.eye(3)))
            rows.append(dict(requested_lift_m=height,maximum_separating_gap_m=gap,state=self.obs['state']))
            write_json_atomic(self.planner.directory/'birth_contact_lift.json',dict(
                separated=gap>=.005,samples=rows,scope='measured contact lift; full task and independent audit pending'))
            if gap>=.005:
                self.birth_ring_separated=True;self.phase='birth_ring_free';return
        raise RuntimeError('Contact lift did not separate the ring from the complete remainder')

    def grasp_ring(self):
        if self.planner is None:raise ValueError('Ring grasp needs read-only planning capabilities')
        self.phase='plan_ring_grasp'
        plan=self.planner.ring_grasp(self.obs,'left',choice=getattr(self,'ring_grasp_choice',None),
            require_pivot_endpoint=getattr(self,'require_ring_pivot',False))
        self.grip['left']=plan['open_position_m']
        if plan.get('transit_plan'):
            indices=self.planner.robot._q_indices['left'][:6]
            for index,q in enumerate(plan['transit_plan']['waypoints'][1:]):
                target=np.asarray(q)[indices]
                current=np.asarray(self.obs['robot']['left']['joint_position_rad'])
                seconds=max(.5,float(np.max(np.abs(target-current)))/.3)
                yield from self.move_joints({'left':target},seconds,f'approach_ring_via_{index}')
        else:
            yield from self.move_joints({'left':np.asarray(plan['pre_joint_position_rad'])},4.,'approach_ring')
        yield from self.move({'left':body_pose(plan['target_tcp'])},3.,'descend_to_ring')
        self.phase='close_on_ring';self.grip['left']=.002
        yield {'left':dict(gripper_position_m=.002)}
        yield from self.hold(1.)
        binding=self.obs['privileged']['world']['grasp']['hands']['left']['binding']
        if not binding or binding['target'][0]!='target_ring':raise RuntimeError('No bilateral ring grasp was acquired')
        self.held_entities['left']='target_ring'
        self.offsets['left']=relative_pose(self.bodies()['left'],self.tcp()['left'])
        self.bias['left'][:]=0.;self.angle_bias['left'][:]=0.
        self.phase='ring_grasp_complete';yield from self.hold(1.)

    def release_support_and_lift(self):
        """Let the free assembly move while the left hand retains the ring."""
        from topogym.utils.io import write_json_atomic
        hands=self.obs['privileged']['world']['grasp']['hands']
        if not hands['left']['binding'] or hands['left']['binding']['target'][0]!='target_ring':
            raise ValueError('Support release requires an observed left ring grasp')
        if getattr(self,'release_translation_m',None) is not None:
            from .settling import plan_held_pair_translation
            plan=plan_held_pair_translation(self.planner,self.obs,self.release_translation_m)
            target={s:body_pose(p) for s,p in plan['samples'][-1]['poses'].items()}
            yield from self.follow_bodies(target,max(1.,np.linalg.norm(plan['translation_m'])/.01),
                'relocate_before_support_release',tracking_m=.003,position_bias_limit_m=.05)
        self.phase='release_right_support';self.grip['right']=.027
        yield {'right':dict(gripper_position_m=.027)}
        yield from self.hold(1.)
        write_json_atomic(self.planner.directory/'released_support_observation.json',self.obs)
        plan=self.planner.withdraw_released_hand(self.obs,'right')
        indices=self.planner.robot._q_indices['right'][:6]
        for index,q in enumerate(plan['free_transit']['waypoints'][1:]):
            target=np.asarray(q)[indices]
            current=np.asarray(self.obs['robot']['right']['joint_position_rad'])
            yield from self.move_joints({'right':target},max(.5,float(np.max(np.abs(target-current)))/.3),
                                       f'withdraw_right_support_{index}')
        self.held_entities.pop('right',None)
        self.phase='released_remainder_settle';yield from self.hold(3.)
        if getattr(self,'level_released_ring',False):
            first=self.bodies()['left'];tcp=self.tcp()['left']
            down=np.array([0.,0.,-1.]);jaw=tcp[1].apply([0.,1.,0.]);jaw[2]=0.
            if np.linalg.norm(jaw)<1e-6:jaw=np.array([0.,1.,0.])
            jaw/=np.linalg.norm(jaw)
            desired=Rotation.from_matrix(np.column_stack([down,jaw,np.cross(down,jaw)]))
            delta=(desired*tcp[1].inv()).as_rotvec()
            def leveling(u):
                turn=Rotation.from_rotvec(u*delta)
                return {'left':(tcp[0]+turn.apply(first[0]-tcp[0]),turn*first[1])}
            # The free shoes and chains receive no pose targets. Their
            # response is validated by the native per-tick physical guard.
            yield from self.follow_bodies(leveling(1.),12.,'level_ring_over_free_remainder',
                pose_at=leveling,tracking_m=.003,position_bias_limit_m=.05,
                tracking_stall_timeout_s=10.)
            yield from self.hold(3.)
            write_json_atomic(self.planner.directory/'leveled_ring_observation.json',self.obs)
        yield from self.lift_ring_from_birth()
        self.support_released=True
        write_json_atomic(self.planner.directory/'released_ring_observation.json',self.obs)

    def reposition_lower(self):
        from .alignment import plan_lower_reposition
        from topogym.utils.io import write_json_atomic
        self.phase='plan_lower_reposition'
        plan=plan_lower_reposition(self.planner,self.obs)
        ring=self.bodies()['left'];initial=self.bodies()['right']
        self.bias['left'][:]=0.;self.angle_bias['left'][:]=0.
        self.bias['right'][:]=0.;self.angle_bias['right'][:]=0.
        poses=[body_pose(row) for row in plan['poses']]
        fraction=getattr(self,'reposition_fraction',1.)
        lower_tracking_m=getattr(self,'reposition_tracking_m',.0015)
        bias_limit=getattr(self,'reposition_bias_limit_m',.03)
        feedback=dict(position_bias_limit_m=bias_limit,
            position_integral_gain_s_inv=getattr(self,'reposition_integral_gain_s_inv',2.),
            position_velocity_gain_s=getattr(self,'reposition_velocity_gain_s',0.))
        tracking_limits={'right':lower_tracking_m}
        # Truncate the certified free edge, retaining its separate contact
        # release prefix. The full path's passive-body response is not assumed.
        poses[-1]=interpolate(poses[-2],poses[-1],fraction)
        for index,target in enumerate(poses[1:]):
            current=self.bodies()['right']
            motion=np.linalg.norm(target[0]-current[0])+.15*(target[1]*current[1].inv()).magnitude()
            yield from self.follow_bodies({'left':ring,'right':target},max(.5,float(motion/.002)),
                                         f'reposition_lower_{index}',tracking_m=.0015,
                                         tracking_limits=tracking_limits,**feedback)
        yield from self.follow_bodies({'left':ring,'right':target},2.,'hold_repositioned_lower',tracking_m=.0015,
                                     tracking_limits=tracking_limits,**feedback)
        actual=self.bodies();error=float(np.linalg.norm(actual['right'][0]-target[0])+
                .15*(actual['right'][1]*target[1].inv()).magnitude())
        ring_error=float(np.linalg.norm(actual['left'][0]-ring[0])+
                .10*(actual['left'][1]*ring[1].inv()).magnitude())
        self.lower_reposition_result=dict(passed=error<.003 and ring_error<.003,
            requested_free_edge_fraction=fraction,
            lower_progress_tracking_limit_m=lower_tracking_m,
            **feedback,
            lower_material_error_m=error,ring_material_error_m=ring_error,
            lower_translation_m=(actual['right'][0]-initial[0]).tolist(),
            state=self.obs['state'],scope='measured held-body reposition; no extraction or passive alignment claim')
        write_json_atomic(self.planner.directory/'lower_reposition_result.json',self.lower_reposition_result)

    def withdraw_ring(self):
        if self.withdrawal_mode in ('staged','joint-staged'):
            self.planner.withdrawal_use_joint=self.withdrawal_mode=='joint-staged'
            yield from self.withdraw_ring_staged()
            return
        self.phase='plan_ring_withdrawal'
        plan=self.planner.withdrawal(self.obs)
        for index,row in enumerate(plan['poses'][1:]):
            target=body_pose(row);current=self.bodies()['left']
            motion=np.linalg.norm(target[0]-current[0])+.10*(target[1]*current[1].inv()).magnitude()
            release=index<plan.get('release_prefix_edges',0)
            yield from self.follow_bodies({'left':target},max(.5 if release else .3,float(motion/(.002 if release else .012))),
                                          f'withdraw_ring_{index}',tracking_m=.0002 if release else .002)
        self.phase='ring_withdrawal_settle';yield from self.hold(2.)
        self.phase='ring_withdrawal_complete'

    def withdraw_ring_staged(self):
        # The right arm's last fold joint target does not hold the support
        # body against changing contact loads. Keep its measured pose under
        # the same ordinary-action feedback as the ring throughout withdrawal.
        self.support_hold=None
        for stage in range(int(self.withdrawal_parameters['maximum_stages'])):
            if (yield from self.withdraw_ring_once(stage)):return
        raise RuntimeError('Ring withdrawal exhausted its measured-state stage budget')

    def withdraw_ring_once(self, stage):
        """One measured short stage, also used by the existing rewind workflow."""
        params=self.withdrawal_parameters
        if getattr(self,'support_hold',None) is None:
            self.support_hold=self.bodies()['right']
            self.offsets['right']=relative_pose(self.support_hold,self.tcp()['right'])
            self.bias['right'][:]=0.;self.angle_bias['right'][:]=0.
        elif params['rebase_support_each_stage']:
            # The planner freezes this same measured lower-shoe pose for the
            # new short stage. Retain grasp calibration and load compensation;
            # only replace the support target through ordinary robot actions.
            self.support_hold=self.bodies()['right']
        tracking_limits=({'right':float(params['support_tracking_m'])}
                         if params.get('support_tracking_m') is not None else None)
        progress_sides=None if params['gate_support_tracking'] else ('left',)
        feedback={k:params[k] for k in ('position_bias_limit_m','rotation_bias_limit_rad','position_integral_gain_s_inv',
                                       'position_velocity_gain_s','position_velocity_filter_s',
                                       'tracking_stall_timeout_s')}
        self.planner.withdrawal_parameters=params
        self.planner.withdrawal_use_joint=self.withdrawal_mode=='joint-staged'
        self.phase=f'plan_ring_stage_{stage}'
        plan=self.planner.withdrawal_stage(self.obs)
        if plan.get('pivot_reached'):
            params['exit_goal_mode']='reference'
            self.planner.withdrawal_stage_state=None
            self.phase='reference_pivot_complete'
            self.diagnostics=plan
            yield from self.hold(.25)
            return False
        if plan.get('separated'):
            self.phase='ring_withdrawal_settle';yield from self.hold(2.)
            self.phase='ring_withdrawal_complete'
            return True
        for index,row in enumerate(plan['poses'][1:]):
            target=body_pose(row);current=self.bodies()['left']
            motion=np.linalg.norm(target[0]-current[0])+.10*(target[1]*current[1].inv()).magnitude()
            yield from self.follow_bodies({'left':target,'right':self.support_hold},max(.5,float(motion/params['speed_m_s'])),
                f'withdraw_ring_stage_{stage}_{index}',tracking_m=params['tracking_m'],
                tracking_limits=tracking_limits,progress_sides=progress_sides,fixed_sides=('right',),
                **feedback)
        yield from self.follow_bodies({'left':target,'right':self.support_hold},.25,
            f'settle_ring_stage_{stage}',tracking_m=params['tracking_m'],
            tracking_limits=tracking_limits,progress_sides=progress_sides,fixed_sides=('right',),
            **feedback)
        return False

    def place_in_goal(self):
        yield from self.place_ring()
        yield from self.place_remainder()
        yield from self.verify_goal()

    def place_ring(self):
        self.phase='plan_ring_placement'
        ring=self.planner.place_ring(self.obs)
        for index,row in enumerate(ring['poses'][1:]):
            target=body_pose(row);current=self.bodies()['left']
            motion=np.linalg.norm(target[0]-current[0])+.10*(target[1]*current[1].inv()).magnitude()
            yield from self.follow_bodies({'left':target},max(.3,float(motion/.015)),f'place_ring_{index}',
                                          tracking_m=getattr(self,'place_tracking_m',.002))
    def place_remainder(self):
        self.phase='plan_remainder_placement'
        remainder=self.planner.place_remainder(self.obs)
        self.bias['right'][:]=0.;self.angle_bias['right'][:]=0.
        for index,row in enumerate(remainder['poses'][1:]):
            target=body_pose(row);current=self.bodies()['right']
            motion=np.linalg.norm(target[0]-current[0])+.10*(target[1]*current[1].inv()).magnitude()
            yield from self.follow_bodies({'right':target},max(.3,float(motion/.012)),f'place_remainder_{index}')
    def verify_goal(self):
        self.phase='verify_raw_goal';start=self.time();stable=0.
        while stable<float(self.planner.task.config['stable_duration_s'])+self.dt:
            reached,failure,metrics=self.planner.measure_goal(self.obs)
            self.diagnostics=dict(raw_goal_reached=reached,failure=failure,metrics=metrics,stable_time_s=stable)
            if failure:raise RuntimeError(f'Goal validation failed: {failure}')
            stable=stable+self.dt if reached else 0.
            if self.time()-start>12.:raise RuntimeError('Fixed placement goal did not become stable')
            yield {}
        self.phase='raw_goal_complete'

    def actions(self):
        self.phase='open_at_home'
        yield {s:dict(gripper_position_m=self.grip[s]) for s in self.grasps}
        yield from self.hold(.6)
        target={s:(np.asarray(g['tcp_position_m']),Rotation.from_quat(np.roll(g['tcp_quaternion_wxyz'],-1)))
                for s,g in self.grasps.items()}
        yield from self.approach_joints(4.)
        # Small contact adjustments can keep converging beyond five seconds.
        # Preserve the 0.5 mm endpoint requirement and allow that convergence.
        yield from self.move(target,3.,'descend_to_band',tracking_timeout_s=10.)
        self.phase='close_and_confirm'
        self.grip={s:.002 for s in self.grasps}
        yield {s:dict(gripper_position_m=.002) for s in self.grasps}
        yield from self.hold(1.)
        hands=self.obs['privileged']['world']['grasp']['hands']
        for side in self.grasps:
            binding=hands[side]['binding']
            if not binding or binding['target'][0]!='horseshoe_'+side:
                raise RuntimeError(f'No confirmed shoe grasp for {side}: {hands[side]}')
        bodies,tcp=self.bodies(),self.tcp()
        self.offsets={s:relative_pose(bodies[s],tcp[s]) for s in self.grasps}
        yield from self.follow_bodies({s:(p+[0,0,.18],r) for s,(p,r) in bodies.items()},8.,'lift_assembly')
        self.phase='lifted_settle';yield from self.hold(2.)
        self.phase='pickup_complete'
        if self.settle_tilt_deg:
            initial=self.bodies()
            yield from self.follow_bodies({s:(p+self.settle_translation,r) for s,(p,r) in initial.items()},
                                          5.,'translate_for_ring_settle')
            yield from self.turn_pair(self.settle_tilt_deg,7.,'tilt_to_hang_ring')
            if self.settle_secondary_y_deg:
                yield from self.turn_pair(self.settle_secondary_y_deg,10.,'tip_ring_toward_chains',axis='y')
            self.phase='tilted_ring_settle';yield from self.hold(3.)
            if self.settle_secondary_y_deg:
                yield from self.turn_pair(-self.settle_secondary_y_deg,10.,'undo_secondary_tilt',axis='y')
            yield from self.turn_pair(-self.settle_tilt_deg,7.,'restore_horizontal_pair')
            yield from self.follow_bodies(initial,5.,'return_after_ring_settle')
            self.phase='ring_settle_complete';yield from self.hold(3.)
        if self.part in ('fold','support','grasp_ring','extract','solve'):
            if self.fold is None:raise ValueError('Fold execution requires a checked reference')
            target={s:self.fold[0]['horseshoe_'+s] for s in self.grasps}
            yield from self.follow_bodies(target,5.,'align_fold_entry')
            yield from self.follow_fold()
            self.phase='folded_settle';yield from self.hold(self.post_fold_hold_s)
            self.phase='fold_complete'
        if self.part in ('support','grasp_ring','extract','solve'):yield from self.support_pair()
        if self.part in ('grasp_ring','extract','solve'):yield from self.grasp_ring()
        if self.part in ('extract','solve'):yield from self.withdraw_ring()
        if self.part=='solve':yield from self.place_in_goal()
