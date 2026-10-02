"""Read-only plans for manipulating the ring after the shoes are supported."""
from pathlib import Path
import json

import numpy as np
from scipy.spatial.transform import Rotation

from topogym.planning.rigid_reference.feedback import body_pose, tcp_pose, relative_pose
from topogym.planning.rigid_reference.geometry import interpolate, pose_dict
from topogym.utils.io import write_json_atomic


class ManipulationPlanner:
    def __init__(self, env, directory, checker, *, reference=None, fold_end_index=None):
        self.task,self.robot,self.checker=env._task,env._robot,checker
        self.directory=Path(directory)
        self.directory.mkdir(parents=True,exist_ok=True)
        self.reference,self.fold_end_index=reference,fold_end_index

    def withdrawal(self, observation):
        from .ring_route import plan_withdrawal
        if self.reference is None:raise ValueError('Withdrawal requires an object-reference guide')
        return plan_withdrawal(self,observation,self.reference,self.fold_end_index)

    def withdrawal_stage(self, observation):
        from .ring_route import plan_withdrawal_stage
        return plan_withdrawal_stage(self,observation,self.reference,self.fold_end_index)

    def place_ring(self, observation):
        from .placement import place_ring
        return place_ring(self,observation)

    def place_remainder(self, observation):
        from .placement import place_remainder
        return place_remainder(self,observation)

    def measure_goal(self, observation):
        return self.task.evaluate_goal_region(observation['privileged']['world'],self.task.goal_region)

    def observed(self, observation):
        if hasattr(self.checker, 'observe_contacts'):
            self.checker.observe_contacts(observation)
        bodies={n:body_pose(observation['privileged']['world']['bodies'][n]) for n in self.checker.bodies}
        q=self.checker.seed.copy()
        for side,state in observation['robot'].items():
            measured=np.asarray(state['joint_position_rad'])
            limits=np.asarray(self.robot.groups[side].arm_limits_rad)
            projected=np.clip(measured,limits[:,0],limits[:,1])
            correction=float(np.abs(projected-measured).max())
            # The constrained physics solve can leave nanoradian limit
            # residue. Only the read-only planning seed is projected; actual
            # observations and commands retain their original provenance.
            if correction>1e-6:
                raise ValueError(f'Observed {side} joint-limit violation exceeds 1 microradian: {correction}')
            if correction:
                with (self.directory/'joint_seed_projections.jsonl').open('a') as stream:
                    stream.write(json.dumps(dict(side=side,observed_arm_rad=measured.tolist(),
                        planned_seed_arm_rad=projected.tolist(),maximum_correction_rad=correction))+'\n')
            q[self.robot._q_indices[side][:6]]=projected
            q[self.robot._q_indices[side][6:]]=state['finger_position_m']
        return bodies,q

    def withdraw_left(self, observation, *, allow_release_contact=False):
        """Check a short free-hand retreat from the measured released stack."""
        bodies,seed=self.observed(observation)
        start=tcp_pose(observation['robot']['left'])
        outward=start[0]-bodies['horseshoe_left'][0];outward[2]=0.
        outward/=max(float(np.linalg.norm(outward)),1e-9)
        attempts=[]
        deltas=[np.array([0.,0.,.03]),np.array([0.,0.,.02]),
                .04*outward+[0,0,.01],.03*outward+[0,0,.02]]
        if allow_release_contact:
            # The released shoe and supporting hand continue settling.
            # Leave enough space for that motion before waiting for quiet.
            deltas=[sign*length*axis for length in (.08,.06,.04,.03)
                    for axis in np.eye(3) for sign in (1.,-1.)]+[
                    -.08*start[1].apply([1.,0.,0.]),*deltas]
        def depth():
            import fcl
            data=fcl.CollisionData(request=fcl.CollisionRequest(num_max_contacts=256,enable_contact=True))
            self.checker.by_arm['left'].collide(self.checker.bodies['horseshoe_left'][1],data,fcl.defaultCollisionCallback)
            return max((float(c.penetration_depth) for c in data.result.contacts),default=0.)
        self.checker.check(seed,body_poses=bodies)
        initial_depth=depth() if allow_release_contact else 0.
        for delta in deltas:
            target=(start[0]+delta,start[1]);q=seed.copy();rows=[];cleared=False;peak=initial_depth
            try:
                for u in np.linspace(0,1,61):
                    previous=q.copy()
                    q=self.checker.solve('left',interpolate(start,target,u),q)
                    checked=self.checker.check(q,body_poses=bodies,
                        contacts={'right':('horseshoe_left','horseshoe_right')})
                    if not checked['passed']:
                        permitted=allow_release_contact and not cleared and checked['issues']==['left/horseshoe_left'] and u<1.
                        if not permitted:raise ValueError(str(checked))
                        current_depth=depth();peak=max(peak,current_depth)
                        if current_depth>max(.00001,initial_depth)+.000001:
                            raise ValueError('Released-body penetration increased along retreat')
                    else:cleared=True
                    if np.abs(q-previous).max()>.15:raise ValueError('Joint branch changed')
                    rows.append(q.tolist())
                free_transit=None
                if allow_release_contact:
                    from .joint_transit import plan_transit
                    home=q.copy()
                    home[self.robot._q_indices['left'][:6]]=self.robot.groups['left'].home[:6]
                    goals=[home]
                    for waist in (-1.,1.,-1.5,1.5):
                        candidate=home.copy();candidate[self.robot._q_indices['left'][0]]=waist
                        goals.append(candidate)
                    for delta in ([0.,-.16,.08],[0.,.16,.08],[.14,0.,.10],[-.12,0.,.10],[0.,0.,.18]):
                        try:goals.append(self.checker.solve('left',(target[0]+delta,target[1]),q))
                        except ValueError:continue
                    transit_errors=[]
                    # Prefer a checked direct retreat across all endpoints.
                    # A timed RRT for an earlier endpoint must not preempt an
                    # available direct route merely because CPU load changed.
                    for direct_only in (True,False):
                        for goal in goals:
                            from topogym.planning.buzz_wire_3d.kinematics import distance
                            checked=self.checker.check(goal,body_poses=bodies,
                                contacts={'right':('horseshoe_left','horseshoe_right')})
                            if not checked['passed']:continue
                            clearance=min(distance(self.checker.by_arm['left'],manager)
                                          for _,manager in self.checker.bodies.values())
                            clearance=min(clearance,distance(self.checker.by_arm['left'],self.checker.by_arm['right']))
                            if clearance<.05:continue
                            try:free_transit=plan_transit(self,q,goal,bodies,seconds=10.,direct_only=direct_only)
                            except ValueError as error:transit_errors.append(str(error));continue
                            free_transit['endpoint_minimum_clearance_m']=clearance
                            free_transit['selection_preference']='checked_direct_then_rrt'
                            break
                        if free_transit is not None:break
                    if free_transit is None:raise ValueError(f'No further free retreat: {transit_errors}')
                result=dict(passed=True,target_tcp=pose_dict(target),joint_samples=rows,
                            free_transit=free_transit,
                            observed_bodies={n:pose_dict(v) for n,v in bodies.items()},attempts=attempts,
                            release_contact=allow_release_contact,initial_release_penetration_m=initial_depth,
                            maximum_release_penetration_m=peak,
                            scope='sampled free-hand retreat; initial released-body contact may only decrease; physical validation required')
                write_json_atomic(self.directory/'free_hand_plan.json',result)
                return result
            except ValueError as error:attempts.append(dict(translation_m=delta.tolist(),error=str(error)))
        write_json_atomic(self.directory/'free_hand_plan.json',dict(passed=False,attempts=attempts))
        raise ValueError('No checked free-hand retreat from the released stack')

    def withdrawal_anchors(self, bodies, grasp_tcp, seed):
        """Diagnostic checkpoints; an alternate route may avoid these poses."""
        if self.reference is None:return None
        hp,hr=bodies['horseshoe_right']
        offset=relative_pose(bodies['target_ring'],grasp_tcp)
        loop=self.task.assembly.loops['target_ring'];center=loop.center-self.task.body_origins['target_ring']
        symmetries=[Rotation.identity()]+[loop.rotation*Rotation.from_rotvec(np.pi*axis)*loop.rotation.inv()
                                         for axis in np.eye(3)]
        indices=[self.fold_end_index,min(len(self.reference)-1,self.fold_end_index+80),len(self.reference)-1]
        attempts=[]
        for symmetry in symmetries:
            q=seed.copy();q[self.robot._q_indices['left'][6:]]=.008+loop.wire_radius;rows=[]
            try:
                for index in indices:
                    rp,rr=relative_pose(self.reference[index]['horseshoe_right'],self.reference[index]['target_ring'])
                    r=hr*rr;p=hp+hr.apply(rp)+r.apply(center-symmetry.apply(center));r=r*symmetry
                    q=self.checker.solve('left',(p+r.apply(offset[0]),r*offset[1]),q)
                    checked=self.checker.check(q,body_poses=dict(bodies,target_ring=(p,r)),
                        contacts={'left':'target_ring','right':('horseshoe_left','horseshoe_right')})
                    if not checked['passed']:raise ValueError(str(checked))
                    rows.append(dict(reference_index=index,qpos=q.tolist(),ring_pose=pose_dict((p,r))))
                return dict(passed=True,symmetry_wxyz=symmetry.as_quat()[[3,0,1,2]].tolist(),samples=rows)
            except ValueError as error:
                attempts.append(dict(symmetry_wxyz=symmetry.as_quat()[[3,0,1,2]].tolist(),
                                     reached=len(rows),error=str(error)))
        return dict(passed=False,attempts=attempts)

    def pivot_anchors(self, observation, grasp_tcp, seed):
        """Screen pivot endpoints for a hypothetical grasp; no connecting-path claim."""
        from .ring_route import HeldRingPath,reference_pivot_goals
        if self.reference is None:raise ValueError('Pivot screening requires a reference')
        checker=HeldRingPath(self,observation,
            passive_contact_names=['horseshoe_left','chain_upper_1','chain_lower_1'])
        checker.offset=relative_pose(checker.start,grasp_tcp)
        q=seed.copy();q[self.robot._q_indices['left'][6:]]=.008+self.task.assembly.loops['target_ring'].wire_radius
        goals,metadata=reference_pivot_goals(self,checker.bodies,self.reference)
        rows=[]
        for goal,description in zip(goals,metadata):
            checked=checker.check(goal,seed=q)
            rows.append(dict(goal=description,check=checked))
        return dict(passed=any(row['check']['passed'] for row in rows),endpoints=rows,
                    scope='hypothetical held-ring pivot endpoints; connecting path and physics unvalidated')

    def ring_grasp(self, observation, side='left', *, choice=None, require_pivot_endpoint=False):
        """Check a grasp and approach, optionally fixing selected parameters."""
        if not isinstance(require_pivot_endpoint,bool) or (require_pivot_endpoint and side!='left'):
            raise ValueError('Pivot screening requires the left ring hand')
        options={'angle_deg':tuple(np.arange(0.,360.,15.)),
                 'approach_sign':(-1,1),'flip':(1,-1),
                 'tangent_roll_deg':(0.,-45.,45.,-90.,90.),
                 'approach_distance_m':(.04,.08)}
        if choice is not None:
            if (not isinstance(choice,dict) or not choice or set(choice)-set(options)
                    or any(isinstance(v,bool) or not isinstance(v,(int,float,np.integer,np.floating))
                           or not np.isfinite(v) for v in choice.values())):
                raise ValueError('Invalid ring grasp candidate restriction')
            for key,value in choice.items():
                valid=(0<=value<360 if key=='angle_deg' else
                       -90<=value<=90 if key=='tangent_roll_deg' else value in options[key])
                if not valid:raise ValueError('Invalid ring grasp candidate restriction')
                options[key]=(value,)
        bodies,seed=self.observed(observation)
        other='right' if side=='left' else 'left'
        # The supporting hand can touch both stacked shoes, while the grasp
        # manager continues to bind only its original lower shoe.
        contacts={other:('horseshoe_left','horseshoe_right')}
        p,r=bodies['target_ring'];loop=self.task.assembly.loops['target_ring']
        center=loop.center-self.task.body_origins['target_ring']
        hand=tcp_pose(observation['robot'][side]);candidates=[];attempts=[];transit_searches=0
        for angle in options['angle_deg']:
            a=np.deg2rad(angle)
            point=center+loop.rotation.apply([loop.radii[0]*np.cos(a),loop.radii[1]*np.sin(a),0.])
            radial=r.apply(loop.rotation.apply([np.cos(a)/loop.radii[0],np.sin(a)/loop.radii[1],0.]))
            radial/=np.linalg.norm(radial)
            for approach_sign in options['approach_sign']:
                normal=approach_sign*r.apply(loop.rotation.apply([0.,0.,1.]))
                for flip in options['flip']:
                    tangent=np.cross(normal,flip*radial)
                    for roll in options['tangent_roll_deg']:
                        twist=Rotation.from_rotvec(np.deg2rad(roll)*tangent)
                        direction=twist.apply(normal);jaw=twist.apply(flip*radial)
                        turn=Rotation.from_matrix(np.column_stack([direction,jaw,np.cross(direction,jaw)]))
                        target=(p+r.apply(point)+turn.apply([-.01381,0.,.00055]),turn)
                        for approach_distance in options['approach_distance_m']:
                            pre=(target[0]-approach_distance*direction,turn)
                            # A round wire permits different approach angles
                            # around its tangent. This avoids confining both
                            # palms to the space beneath the supported shoes.
                            score=float(np.linalg.norm(pre[0]-hand[0])+3*(target[0][2]-p[2])+.0002*abs(roll))
                            candidates.append((score,angle,approach_sign,flip,roll,approach_distance,point,pre,target))
        for _,angle,sign,flip,roll,approach_distance,point,pre,target in sorted(candidates,key=lambda row:row[0]):
            q=seed.copy();q[self.robot._q_indices[side][6:]]=.018
            record=dict(angle_deg=angle,approach_sign=sign,flip=flip,tangent_roll_deg=roll,approach_distance_m=approach_distance)
            try:
                pre_q=self.checker.solve(side,pre,q)
                target_q=self.checker.solve(side,target,pre_q)
                for pose_q,allowed in ((pre_q,contacts),(target_q,{**contacts,side:'target_ring'})):
                    checked=self.checker.check(pose_q,contacts=allowed,body_poses=bodies)
                    if not checked['passed']:raise ValueError(('target ' if allowed.get(side) else 'pre ')+str(checked))
                for opening in np.linspace(.018,.008+loop.wire_radius,6):
                    closing=target_q.copy();closing[self.robot._q_indices[side][6:]]=opening
                    checked=self.checker.check(closing,contacts={**contacts,side:'target_ring'},body_poses=bodies)
                    if not checked['passed']:raise ValueError('closing '+str(checked))
                pivot=self.pivot_anchors(observation,target,target_q) if require_pivot_endpoint else None
                if pivot is not None and not pivot['passed']:
                    raise ValueError('No reachable pivot endpoint for this grasp')
                # Explicitly check the free arm's joint transit and its final
                # straight approach. All puzzle bodies remain obstacles.
                transit=[];transit_error=None
                for u in np.linspace(0,1,61):
                    sample=q+u*(pre_q-q)
                    checked=self.checker.check(sample,contacts=contacts,body_poses=bodies)
                    if not checked['passed']:
                        transit_error='transit '+str(checked);break
                    transit.append(sample.tolist())
                q=pre_q.copy();descent=[]
                for u in np.linspace(0,1,41)[1:]:
                    q=self.checker.solve(side,interpolate(pre,target,u),q)
                    allowed={**contacts,side:'target_ring'} if approach_distance*(1-u)<.017 else contacts
                    checked=self.checker.check(q,contacts=allowed,body_poses=bodies)
                    if not checked['passed']:raise ValueError('approach '+str(checked))
                    descent.append(q.tolist())
                transit_plan=None
                if transit_error:
                    if transit_searches>=4:raise ValueError(transit_error)
                    from .joint_transit import plan_transit
                    transit_searches+=1
                    initial=seed.copy();initial[self.robot._q_indices[side][6:]]=.018
                    transit_plan=plan_transit(self,initial,pre_q,bodies,side=side,seconds=20.)
                    transit=transit_plan['waypoints']
                anchors=self.withdrawal_anchors(bodies,target,target_q)
                result=dict(passed=True,side=side,**record,point_local_m=point.tolist(),
                            open_position_m=.018,pre_tcp=pose_dict(pre),target_tcp=pose_dict(target),
                            pre_joint_position_rad=pre_q[self.robot._q_indices[side][:6]].tolist(),
                            observed_bodies={n:pose_dict(v) for n,v in bodies.items()},
                            joint_transit=transit,transit_plan=transit_plan,approach=descent,attempts=attempts,
                            withdrawal_anchors=anchors,
                            pivot_anchors=pivot,
                            scope='sampled native IK/collision plan; bilateral acquisition requires physical execution')
                write_json_atomic(self.directory/'ring_grasp_plan.json',result)
                self.selected_ring_grasp=result
                return result
            except ValueError as error:
                attempts.append(dict(**record,error=str(error)))
        write_json_atomic(self.directory/'ring_grasp_plan.json',dict(passed=False,attempts=attempts))
        raise ValueError('No checked ring grasp from the supported physical state')
