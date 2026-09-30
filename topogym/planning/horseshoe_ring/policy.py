"""Measured Horseshoe manipulation through ordinary public actions only."""
import numpy as np
from scipy.spatial.transform import Rotation

from topogym.planning.rigid_reference.feedback import body_pose, tcp_pose, relative_pose
from topogym.planning.rigid_reference.geometry import interpolate


class HorseshoePolicy:
    def __init__(self, grasps, *, part='pickup', fold=None, support=None, planner=None, settle_tilt_deg=0., settle_axis='y', settle_secondary_y_deg=0., settle_translation=(0.,0.,0.), fold_tracking_m=.001, withdrawal_mode='full'):
        self.grasps, self.part, self.fold = grasps, part, fold
        self.support=support
        self.planner=planner
        self.settle_tilt_deg=float(settle_tilt_deg)
        self.settle_axis=settle_axis
        self.settle_secondary_y_deg=float(settle_secondary_y_deg)
        self.settle_translation=np.asarray(settle_translation,dtype=float)
        self.fold_tracking_m=float(fold_tracking_m)
        self.withdrawal_mode=withdrawal_mode
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

    def move(self, target, seconds, phase):
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
            if self.time()-started>5.:raise RuntimeError(f'TCP tracking failed: {errors}')
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

    def follow_bodies(self, target, seconds, phase, *, pose_at=None, tracking_m=.002):
        self.phase=phase;start=self.time();initial=self.bodies();progress=0.
        while True:
            desired=pose_at(progress) if pose_at else {s:interpolate(initial[s],target[s],progress) for s in target}
            actual=self.bodies();commands={};errors={};nominal={}
            for s,(p,r) in desired.items():
                ep=p-actual[s][0];er=(r*actual[s][1].inv()).as_rotvec()
                self.bias[s]=np.clip(self.bias[s]+2*self.dt*ep,-.03,.03)
                self.angle_bias[s]=np.clip(self.angle_bias[s]+2*self.dt*er,-.15,.15)
                cr=Rotation.from_rotvec(self.angle_bias[s]+.5*er)*r
                commands[s]=(p+self.bias[s]+.5*ep+cr.apply(self.offsets[s][0]),cr*self.offsets[s][1])
                nominal[s]=(p+r.apply(self.offsets[s][0]),r*self.offsets[s][1])
                errors[s]=float(np.linalg.norm(ep)+.10*np.linalg.norm(er))
            self.diagnostics=dict(progress=progress,material_tracking_errors_m=errors)
            if max(errors.values())<tracking_m:
                if progress>=1.:break
                progress=min(1.,progress+self.dt/seconds)
            if self.time()-start>seconds*4+10:raise RuntimeError(f'Object tracking stalled: {self.diagnostics}')
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
        retreat=self.planner.withdraw_left(self.obs)
        yield from self.move({'left':body_pose(retreat['target_tcp'])},3.,'withdraw_left_hand')
        self.phase='support_settle';yield from self.hold(3.)
        hands=self.obs['privileged']['world']['grasp']['hands']
        if hands['left']['binding'] is not None or not hands['right']['binding']:
            raise RuntimeError('Support handoff did not release only the left hand')
        after=self.bodies()
        displacement=float(np.linalg.norm(after['left'][0]-before['left'][0]))
        turn=float((after['left'][1]*before['left'][1].inv()).magnitude())
        self.diagnostics=dict(upper_shoe_displacement_m=displacement,upper_shoe_rotation_rad=turn)
        if displacement>.04 or turn>.2:raise RuntimeError(f'Upper shoe did not remain supported: {self.diagnostics}')
        self.phase='support_complete'

    def grasp_ring(self):
        if self.planner is None:raise ValueError('Ring grasp needs read-only planning capabilities')
        self.phase='plan_ring_grasp'
        plan=self.planner.ring_grasp(self.obs,'left')
        self.grip['left']=plan['open_position_m']
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
        support=self.bodies()['right']
        self.offsets['right']=relative_pose(support,self.tcp()['right'])
        self.bias['right'][:]=0.;self.angle_bias['right'][:]=0.
        for stage in range(100):
            self.phase=f'plan_ring_stage_{stage}'
            plan=self.planner.withdrawal_stage(self.obs)
            if plan.get('separated'):
                self.phase='ring_withdrawal_settle';yield from self.hold(2.)
                self.phase='ring_withdrawal_complete'
                return
            for index,row in enumerate(plan['poses'][1:]):
                target=body_pose(row);current=self.bodies()['left']
                motion=np.linalg.norm(target[0]-current[0])+.10*(target[1]*current[1].inv()).magnitude()
                yield from self.follow_bodies({'left':target,'right':support},max(.5,float(motion/.004)),
                    f'withdraw_ring_stage_{stage}_{index}',tracking_m=.0015)
            yield from self.follow_bodies({'left':target,'right':support},.25,
                f'settle_ring_stage_{stage}',tracking_m=.0015)
        raise RuntimeError('Ring withdrawal exhausted 100 measured-state stages')

    def place_in_goal(self):
        self.phase='plan_ring_placement'
        ring=self.planner.place_ring(self.obs)
        for index,row in enumerate(ring['poses'][1:]):
            target=body_pose(row);current=self.bodies()['left']
            motion=np.linalg.norm(target[0]-current[0])+.10*(target[1]*current[1].inv()).magnitude()
            yield from self.follow_bodies({'left':target},max(.3,float(motion/.015)),f'place_ring_{index}')
        self.phase='plan_remainder_placement'
        remainder=self.planner.place_remainder(self.obs)
        self.bias['right'][:]=0.;self.angle_bias['right'][:]=0.
        for index,row in enumerate(remainder['poses'][1:]):
            target=body_pose(row);current=self.bodies()['right']
            motion=np.linalg.norm(target[0]-current[0])+.10*(target[1]*current[1].inv()).magnitude()
            yield from self.follow_bodies({'right':target},max(.3,float(motion/.012)),f'place_remainder_{index}')
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
        yield from self.move(target,3.,'descend_to_band')
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
            self.phase='folded_settle';yield from self.hold(2.)
            self.phase='fold_complete'
        if self.part in ('support','grasp_ring','extract','solve'):yield from self.support_pair()
        if self.part in ('grasp_ring','extract','solve'):yield from self.grasp_ring()
        if self.part in ('extract','solve'):yield from self.withdraw_ring()
        if self.part=='solve':yield from self.place_in_goal()
