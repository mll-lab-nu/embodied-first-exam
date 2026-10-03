"""Measured-state ring withdrawal with native imported convex geometry.

The route checks are sampled manipulation diagnostics. In particular the
small initial contact-release neighbourhood is not a positive-clearance
certificate; a subsequent continuous physical execution must validate it.
"""
import fcl
import numpy as np
import time
from collections import Counter
from dataclasses import replace
from scipy.spatial.transform import Rotation
from scipy.optimize import linprog

from topogym.planning.buzz_wire_3d.kinematics import distance
from topogym.planning.rigid_reference.feedback import relative_pose, tcp_pose
from topogym.planning.rigid_reference.geometry import interpolate, pose_dict
from topogym.planning.rigid_reference.rrt import connect_search
from topogym.utils.io import write_json_atomic


class HeldRingPath:
    def __init__(self, planner, observation, *, passive_contact_names=()):
        self.planner=planner
        self.checker=planner.checker
        self.bodies,self.seed=planner.observed(observation)
        self.passive_contact_names=tuple(passive_contact_names)
        self.contact_limit_m=getattr(planner,'withdrawal_parameters',{}).get('puzzle_contact_limit_m')
        if self.contact_limit_m is not None:
            self.contact_limit_m=float(self.contact_limit_m)
            native_limit=float(planner.task.terminal_metadata()['contact_penetration']['other_contacts_m'])
            if not np.isfinite(self.contact_limit_m) or not 0<self.contact_limit_m<=native_limit:
                raise ValueError('Puzzle planning contact exceeds the native contact limit')
        if any(n not in planner.task.placement_remainder for n in self.passive_contact_names):
            raise ValueError('Only released remainder bodies may be contact-planning participants')
        if self.passive_contact_names:
            hands=observation['privileged']['world']['grasp']['hands']
            bound={h['binding']['target'][0] for h in hands.values() if h['binding']}
            if bound.intersection(self.passive_contact_names):
                raise ValueError('A held body cannot be treated as a passive contact participant')
        self.start=self.bodies['target_ring']
        self.offset=relative_pose(self.start,tcp_pose(observation['robot']['left']))
        self.vertices=planner.task.placement_vertices['target_ring']
        self.radius=float(np.linalg.norm(self.vertices,axis=1).max())
        self.queries=0
        self.cache={}
        self.rejections=Counter()
        self.started=time.monotonic()
        self.deadline=self.started+900.
        for name,(p,r) in self.bodies.items():
            objects,manager=self.checker.bodies[name]
            for obj in objects:obj.setTransform(fcl.Transform(r.as_matrix(),p))
            manager.update()
        self.initial_penetration_m=self.penetration(self.start)
        initial_limit=.0005 if self.contact_limit_m is None else self.contact_limit_m
        if self.initial_penetration_m>initial_limit:
            raise ValueError(f'Ring contact starts beyond its {initial_limit:g} m planning tolerance')

    def set_ring(self, pose):
        self.bodies['target_ring']=pose
        # Other four objects remain at their measured poses for this plan.
        p,r=pose;objects,manager=self.checker.bodies['target_ring']
        for obj in objects:obj.setTransform(fcl.Transform(r.as_matrix(),p))
        manager.update()

    def penetration(self, pose):
        self.set_ring(pose)
        ring=self.checker.bodies['target_ring'][1]
        depth=0.
        for name,(_,obstacle) in self.checker.bodies.items():
            if name=='target_ring' or name in self.passive_contact_names:continue
            data=fcl.CollisionData(request=fcl.CollisionRequest(num_max_contacts=256,enable_contact=True))
            ring.collide(obstacle,data,fcl.defaultCollisionCallback)
            depth=max(depth,max((float(c.penetration_depth) for c in data.result.contacts),default=0.))
        return depth

    def motion(self, a, b):
        return float(np.linalg.norm(a[0]-b[0])+self.radius*(a[1]*b[1].inv()).magnitude())

    def check(self, pose, seed=None, *, minimum_clearance_m=.00005):
        self.queries+=1
        if self.queries%200==0:
            write_json_atomic(self.planner.directory/'ring_search_progress.json',
                dict(queries=self.queries,elapsed_s=time.monotonic()-self.started,rejections=dict(self.rejections)))
        if time.monotonic()>self.deadline:raise TimeoutError('Ring search exceeded its 900 s wall-clock budget')
        p,r=pose
        key=tuple(np.round(np.r_[p,r.as_quat(),minimum_clearance_m],10))
        if seed is None and key in self.cache:return self.cache[key]
        if (r.apply(self.vertices)+p)[:,2].min()<self.checker.table_height+.0005:
            self.rejections['ring_table']+=1
            return dict(passed=False,reason='ring_table')
        self.set_ring(pose)
        ring=self.checker.bodies['target_ring'][1]
        gap=min(distance(ring,obstacle) for name,(_,obstacle) in self.checker.bodies.items()
                if name!='target_ring' and name not in self.passive_contact_names)
        escape=self.motion(pose,self.start)<=.003
        if gap<minimum_clearance_m:
            if not escape and self.contact_limit_m is None:
                self.rejections['ring_obstacle']+=1
                return dict(passed=False,reason='ring_obstacle',clearance_m=gap)
            depth=self.penetration(pose)
            limit=(max(.00001,self.initial_penetration_m+1e-6)
                   if self.contact_limit_m is None else self.contact_limit_m)
            if depth>limit:
                self.rejections['contact_release_penetration']+=1
                return dict(passed=False,reason='contact_release_penetration',penetration_m=depth)
        op,orr=self.offset
        try:
            q=self.checker.solve('left',(p+r.apply(op),r*orr),self.seed if seed is None else seed)
        except ValueError as error:
            self.rejections['ik']+=1
            return dict(passed=False,reason='ik',error=str(error))
        # The stationary right fingers may support the upper shoe through
        # ordinary contact. Only the lower shoe is welded to that hand.
        checked=self.checker.check(q,
            contacts={'left':'target_ring','right':('horseshoe_left','horseshoe_right')})
        self.rejections.update(checked['issues'])
        result=dict(**checked,qpos=q.tolist(),ring_clearance_m=gap,contact_release_neighbourhood=escape,
                    puzzle_contact_limit_m=self.contact_limit_m)
        if seed is None:self.cache[key]=result
        return result

    def edge(self, start, end):
        previous=None;rows=[]
        count=max(1,int(np.ceil(self.motion(start,end)/.00075)))
        for u in np.linspace(0,1,count+1):
            checked=self.check(interpolate(start,end,u),previous)
            if not checked['passed']:return dict(passed=False,progress=float(u),check=checked)
            q=np.asarray(checked['qpos'])
            if previous is not None and np.abs(q-previous).max()>.15:
                return dict(passed=False,reason='joint_branch_change')
            previous=q;rows.append(checked)
        return dict(passed=True,samples=len(rows),scope='sampled imported-convex/IK checks; physical validation required')

    def ordered_audit(self, path, *, release_prefix_edges=0):
        previous=self.seed.copy();samples=0
        for index,(a,b) in enumerate(zip(path[:-1],path[1:])):
            spacing=.0001 if index<release_prefix_edges else .00075
            count=max(1,int(np.ceil(self.motion(a,b)/spacing)))
            for u in np.linspace(0,1,count+1):
                checked=self.check(interpolate(a,b,u),previous,
                    minimum_clearance_m=0. if index<release_prefix_edges else .00005)
                if not checked['passed']:return dict(passed=False,edge=index,progress=float(u),check=checked)
                q=np.asarray(checked['qpos'])
                if np.abs(q-previous).max()>.15:
                    return dict(passed=False,edge=index,reason='joint_branch_change')
                previous=q;samples+=1
        return dict(passed=True,samples=samples,maximum_material_sample_step_m=.00075)

    def contact_escape(self, *, minimal=True):
        """Linearize all nearby convex pairs, then check each small twist.

        Contact normals alone miss the opposite surface when its current
        clearance is only a few micrometres. Nearby positive distances are
        therefore constraints too. Each proposed step is independently
        checked; the linear programme itself is not an edge certificate.
        A global search may request a larger checked prefix to start away
        from the contact boundary. Measured short stages use minimal motion.
        """
        if self.contact_limit_m is not None:
            # A contact motion does not require an artificial positive gap
            # before it can start. Each proposed pose still checks penetration,
            # and execution checks the actual passive response at every tick.
            checked=self.check(self.start)
            if not checked['passed']:raise ValueError('Measured contact start failed native planning checks')
            return [self.start]
        path=[self.start];rows=[]
        def signed_clearance(pose):
            self.set_ring(pose);ring=self.checker.bodies['target_ring'][1]
            gap=min(distance(ring,m) for n,(_,m) in self.checker.bodies.items()
                    if n!='target_ring' and n not in self.passive_contact_names)
            return -self.penetration(pose) if gap<0 else gap
        gap=signed_clearance(self.start)
        for iteration in range(30):
            if gap>.00006:
                result=dict(passed=True,poses=[pose_dict(p) for p in path],iterations=rows,
                            final_clearance_m=gap,passive_contact_names=list(self.passive_contact_names),
                            minimal_motion=bool(minimal),
                            scope='sampled contact-release twists against the fixed obstacles; passive-contact response requires physics')
                write_json_atomic(self.planner.directory/'contact_escape_plan.json',result)
                return path
            p,r=path[-1];self.set_ring(path[-1]);constraints=[];clearances=[]
            for name,(objects,_) in self.checker.bodies.items():
                if name=='target_ring' or name in self.passive_contact_names:continue
                for a in self.checker.bodies['target_ring'][0]:
                    for b in objects:
                        nearest=fcl.DistanceResult()
                        d=fcl.distance(a,b,fcl.DistanceRequest(enable_nearest_points=True),nearest)
                        if d>=.001:continue
                        if d>=0:
                            one,two=map(np.asarray,nearest.nearest_points)
                            normal=one-two;normal/=max(np.linalg.norm(normal),1e-12)
                            constraints.append(np.r_[normal,np.cross(one-p,normal)/self.radius]);clearances.append(d)
                        else:
                            contacts=fcl.CollisionResult()
                            fcl.collide(a,b,fcl.CollisionRequest(num_max_contacts=8,enable_contact=True),contacts)
                            for contact in contacts.contacts:
                                normal=np.asarray(contact.normal);point=np.asarray(contact.pos);depths=[]
                                for sign in (1.,-1.):
                                    a.setTransform(fcl.Transform(r.as_matrix(),p+sign*1e-5*normal))
                                    probe=fcl.CollisionResult()
                                    fcl.collide(a,b,fcl.CollisionRequest(num_max_contacts=8,enable_contact=True),probe)
                                    depths.append(max((c.penetration_depth for c in probe.contacts),default=0.))
                                a.setTransform(fcl.Transform(r.as_matrix(),p))
                                if depths[0]>=depths[1]:normal=-normal
                                constraints.append(np.r_[normal,np.cross(point-p,normal)/self.radius])
                                clearances.append(-float(contact.penetration_depth))
            if not constraints:break
            fit=linprog(np.r_[np.zeros(6),-1.],A_ub=np.c_[-np.asarray(constraints),np.ones(len(constraints))],
                b_ub=np.asarray(clearances),bounds=[(-.002,.002)]*6+[(-.01,.01)],method='highs')
            if not fit.success:break
            # Use only as much of the maximizing twist as clearance needs.
            # Executing the full LP extremum at every measured stage can
            # move several millimetres away from the guide, exhausting the
            # next short stage merely returning towards it.
            accepted=None;fallback=None
            fractions=(1/128,1/64,1/32,1/16,1/8,1/4,1/2,1.) if minimal else (1.,.5,.25,.125,.0625)
            for fraction in fractions:
                delta=fraction*fit.x[:6]
                candidate=(p+delta[:3],Rotation.from_rotvec(delta[3:]/self.radius)*r)
                new_gap=signed_clearance(candidate)
                if new_gap<=gap+1e-7:continue
                audit=self.ordered_audit([*path,candidate],release_prefix_edges=len(path))
                if not audit['passed']:continue
                row=dict(iteration=iteration,constraints=len(constraints),predicted_clearance_m=float(fit.x[6]),
                         actual_clearance_m=new_gap,fraction=fraction,audit=audit)
                if fallback is None or new_gap>fallback[1]:fallback=(candidate,new_gap,row)
                if new_gap>.00006:
                    accepted=(candidate,new_gap,row);break
            if accepted is None:accepted=fallback
            if accepted is None:break
            candidate,gap,row=accepted;rows.append(row);path.append(candidate)
        write_json_atomic(self.planner.directory/'contact_escape_plan.json',
            dict(passed=False,poses=[pose_dict(p) for p in path],iterations=rows,final_clearance_m=gap,
                 passive_contact_names=list(self.passive_contact_names),minimal_motion=bool(minimal)))
        raise ValueError('Local contact-release search did not reach positive clearance')


def plan_withdrawal_stage(planner, observation, reference, fold_end_index):
    """Execute at most 12 mm of a checked guide before observing passive motion.

    This is a contact policy candidate, not a geometry certificate. Released
    bodies remain fully dynamic and collision-active in the simulator. Their
    measured poses participate in every new robot collision check.
    """
    parameters=getattr(planner,'withdrawal_parameters',{})
    passive=parameters.get('passive_contact_names',('horseshoe_left','chain_upper_1','chain_lower_1'))
    checker=HeldRingPath(planner,observation,passive_contact_names=passive)
    measured=checker.bodies.copy();hp,hr=measured['horseshoe_right']
    direction=(hr*reference[-1]['horseshoe_right'][1].inv()).apply([-1.,0.,0.])
    remainder=np.vstack([r.apply(planner.task.placement_vertices[n])+p for n,(p,r) in measured.items() if n!='target_ring'])
    rp,rr=checker.start;ring=rr.apply(checker.vertices)+rp
    directions=[direction,*np.eye(3),*-np.eye(3)]
    gaps=[float((ring@axis).min()-(remainder@axis).max()) for axis in directions]
    separating_index=int(np.argmax(gaps))
    if gaps[separating_index]>=.005:
        state=getattr(planner,'withdrawal_stage_state',None) or dict(stage=0,index=0)
        result=dict(passed=True,separated=True,stage=state['stage'],reference_index=state['index'],
            separating_direction=np.asarray(directions[separating_index]).tolist(),
            separating_gap_m=gaps[separating_index],observed_bodies={n:pose_dict(v) for n,v in measured.items()},
            scope='measured whole-geometry separating plane; subsequent motion still requires physical validation')
        write_json_atomic(planner.directory/f"ring_stage_{state['stage']:03d}.json",result)
        return result
    if parameters.get('exit_goal_mode')=='reference_pivot':
        goals,metadata=reference_pivot_goals(planner,measured,reference)
        errors=[checker.motion(checker.start,goal) for goal in goals]
        closest=int(np.argmin(errors))
        if errors[closest]<.003:
            # This is only an intermediate planning milestone. Separation
            # and the native placement goal retain their independent tests.
            result=dict(passed=True,separated=False,pivot_reached=True,
                pivot_material_error_m=errors[closest],pivot_goal=metadata[closest],
                observed_bodies={n:pose_dict(v) for n,v in measured.items()},
                scope='measured reference pivot reached; extraction remains unverified')
            write_json_atomic(planner.directory/'reference_pivot_reached.json',result)
            return result
    guide=[]
    for frame in reference:
        p,r=relative_pose(frame['horseshoe_right'],frame['target_ring'])
        guide.append((hp+hr.apply(p),hr*r))
    loop=planner.task.assembly.loops['target_ring']
    center=loop.center-planner.task.body_origins['target_ring']
    state=getattr(planner,'withdrawal_stage_state',None)
    prefer_reference=(parameters.get('prefer_reference_exit_guide',False)
                      and parameters.get('exit_goal_mode')=='reference')
    if state is None and getattr(planner,'withdrawal_use_joint',False) and not prefer_reference:
        route=plan_joint_withdrawal(planner,observation,reference)
        relative_guide=[relative_pose(measured['horseshoe_right'],
            (np.asarray(row['position_m']),Rotation.from_quat(np.roll(row['quaternion_wxyz'],-1))))
            for row in route['poses']]
        state=dict(index=route['release_prefix_edges']+1,stage=0,stride=1,
            symmetry=Rotation.identity(),relative_guide=relative_guide)
        planner.withdrawal_stage_state=state
    if state is None:
        symmetries=[Rotation.identity()]+[
            loop.rotation*Rotation.from_rotvec(np.pi*axis)*loop.rotation.inv() for axis in np.eye(3)]
        choices=[]
        for symmetry in symmetries:
            indices=range(fold_end_index,len(guide)) if prefer_reference else range(0,len(guide),4)
            for index in indices:
                p,r=guide[index]
                candidate=(p+r.apply(center-symmetry.apply(center)),r*symmetry)
                choices.append((checker.motion(checker.start,candidate),index,symmetry))
        _,index,symmetry=min(choices,key=lambda row:row[0])
        state=dict(index=index,symmetry=symmetry,stage=0,stride=4)
        if prefer_reference:state['guide_source']='canonical_reference_exit'
        planner.withdrawal_stage_state=state
    if 'relative_guide' in state:
        guide=[(hp+hr.apply(p),hr*r) for p,r in state['relative_guide']]
    else:
        guide=[(p+r.apply(center-state['symmetry'].apply(center)),r*state['symmetry']) for p,r in guide]
    result=dict(passed=False,separated=False,stage=state['stage'],reference_index=state['index'],
        observed_bodies={n:pose_dict(v) for n,v in measured.items()},
        scope='short sampled contact-policy candidate; physical execution and independent audit required')
    if state.get('guide_source'):result['guide_source']=state['guide_source']
    destination=planner.directory/f"ring_stage_{state['stage']:03d}.json"
    initial=checker.check(checker.start)
    if not initial['passed']:
        write_json_atomic(destination,dict(result,initial=initial))
        raise ValueError('Measured ring state failed stage-entry checks')
    escape=checker.contact_escape();path=list(escape);release_edges=len(path)-1
    budget=float(parameters.get('stage_motion_m',.012));travel=0.;failure=None
    index=state['index']
    while index<len(guide) and travel<budget-1e-7:
        target=guide[index];motion=checker.motion(path[-1],target)
        if motion<.0005:
            index+=state['stride'];continue
        fraction=min(1.,(budget-travel)/motion)
        candidate=interpolate(path[-1],target,fraction)
        audit=checker.ordered_audit([*path,candidate],release_prefix_edges=release_edges)
        if not audit['passed']:
            failure=audit
            # Keep the largest checked prefix when the next guide pose is
            # blocked by a passive object at its currently measured pose.
            best=None;lower=0.;upper=1.
            for shorten in (.5,.25,.125):
                shorter=interpolate(path[-1],candidate,shorten)
                trial=checker.ordered_audit([*path,shorter],release_prefix_edges=release_edges)
                if trial['passed']:
                    best=shorter;lower=shorten;break
                upper=shorten
            if parameters.get('refine_short_stage_prefix',False):
                # Coarse fractions can discard a useful checked prefix:
                # e.g. 0.74 mm passes and 1.48 mm fails, but 1.25 mm passes
                # the same checks and exceeds the 1 mm progress threshold.
                # Every retained prefix is audited in its entirety. This
                # search does not assume unchecked space is collision-free.
                for _ in range(6):
                    shorten=(lower+upper)/2
                    shorter=interpolate(path[-1],candidate,shorten)
                    trial=checker.ordered_audit([*path,shorter],release_prefix_edges=release_edges)
                    if trial['passed']:best=shorter;lower=shorten
                    else:upper=shorten
            if best is not None:
                path.append(best);travel+=fraction*motion*lower
            break
        path.append(candidate);travel+=fraction*motion
        if fraction>=1.:index=min(index+state['stride'],len(guide)-1)
        else:break
    result.update(passed=travel>.001,poses=[pose_dict(p) for p in path],
        release_prefix_edges=release_edges,guide_travel_m=travel,next_reference_index=index,
        stopped_before=failure,passive_contact_names=list(checker.passive_contact_names),
        queries=checker.queries,ordered_audit=checker.ordered_audit(path,release_prefix_edges=release_edges))
    write_json_atomic(destination,result)
    if not result['passed']:raise ValueError('No useful checked withdrawal stage from measured state')
    state['index']=index;state['stage']+=1
    return result


def reference_pivot_goals(planner, bodies, reference):
    """Reach the reference turn around the eyes before requesting separation."""
    hp,hr=bodies['horseshoe_right']
    loop=planner.task.assembly.loops['target_ring']
    center=loop.center-planner.task.body_origins['target_ring']
    symmetries=[Rotation.identity()]+[
        loop.rotation*Rotation.from_rotvec(np.pi*axis)*loop.rotation.inv() for axis in np.eye(3)]
    goals=[];metadata=[]
    for offset in (80,):
        index=min(len(reference)-1,planner.fold_end_index+offset)
        rp,rr=relative_pose(reference[index]['horseshoe_right'],reference[index]['target_ring'])
        p,r=hp+hr.apply(rp),hr*rr
        for symmetry_index,symmetry in enumerate(symmetries):
            goal=(p+r.apply(center-symmetry.apply(center)),r*symmetry)
            goals.append(goal)
            metadata.append(dict(reference_index=index,symmetry_index=symmetry_index,pose=pose_dict(goal)))
    return goals,metadata


def direct_axis_withdrawal(planner, observation):
    """Try short Cartesian translations before a joint-space exit detour.

    Every retained path uses the original ordered IK/contact audit and keeps
    the measured passive-loop linkages at the same dense pose samples. Free
    bodies are still only planning snapshots; execution must check their
    actual response after each short stage.
    """
    parameters=getattr(planner,'withdrawal_parameters',{})
    passive=parameters.get('passive_contact_names',())
    checker=HeldRingPath(planner,observation,passive_contact_names=passive)
    measured=checker.bodies.copy();p,r=checker.start
    ring=r.apply(checker.vertices)+p
    remainder=np.vstack([rot.apply(planner.task.placement_vertices[name])+pos
        for name,(pos,rot) in measured.items() if name!='target_ring'])
    candidates=sorted((max(0.,float((remainder@axis).max()-(ring@axis).min())+.008),index,axis)
                      for index,axis in enumerate(np.r_[np.eye(3),-np.eye(3)]))
    loop=planner.task.assembly.loops['target_ring']
    def world_loop(shape,pos,rot):
        return replace(shape,center=pos+rot.apply(shape.center-planner.task.body_origins[shape.body]),
                       rotation=rot*shape.rotation)
    passive_loops={name:world_loop(shape,*measured[shape.body])
        for name,shape in planner.task.assembly.loops.items() if shape.body in passive}
    initial={name:world_loop(loop,p,r).linking(shape) for name,shape in passive_loops.items()}
    rows=[]
    for travel,index,axis in candidates:
        goal=(p+travel*axis,r)
        count=max(1,int(np.ceil(travel/.00075)))
        poses=[interpolate(checker.start,goal,float(u)) for u in np.linspace(0,1,count+1)]
        topology_failure=None
        for sample,(pos,rot) in enumerate(poses):
            current=world_loop(loop,pos,rot)
            if any(current.linking(shape)!=initial[name] for name,shape in passive_loops.items()):
                topology_failure=sample;break
        if topology_failure is not None:
            rows.append(dict(axis_index=index,travel_m=travel,passed=False,
                             reason='static_passive_linkage',sample=topology_failure))
            continue
        audit=checker.ordered_audit(poses)
        rows.append(dict(axis_index=index,travel_m=travel,passed=audit['passed'],ordered_audit=audit))
        if not audit['passed']:continue
        result=dict(passed=True,poses=[pose_dict(pose) for pose in poses],ordered_audit=audit,
            joint_knots=[],queries=checker.queries,release_prefix_edges=0,
            passive_contact_names=list(passive),contact_release=True,
            static_passive_loop_linkages_preserved_at_pose_checks=True,
            static_passive_loop_linkages=initial,static_passive_loop_samples=len(poses),
            actual_passive_topology_requires_physical_audit=True,
            joint_search_goal_tube=bool(parameters.get('joint_search_goal_tube',False)),
            guide_source='direct_cartesian_axis_exit',axis_index=index,translation_m=travel,
            scope='Sampled ordered Cartesian IK/contact and static-loop checks; physical exit remains unverified')
        write_json_atomic(planner.directory/'direct_axis_exit_candidates.json',dict(passed=True,rows=rows))
        return result
    checker.set_ring(checker.start)
    write_json_atomic(planner.directory/'direct_axis_exit_candidates.json',dict(passed=False,rows=rows))
    return None


def plan_joint_withdrawal(planner, observation, reference):
    """Find reachable exit attitudes without prescribing a wrist branch."""
    from .joint_route import plan_free_ring_transport
    bodies,_=planner.observed(observation);hp,hr=bodies['horseshoe_right']
    parameters=getattr(planner,'withdrawal_parameters',{})
    mode=parameters.get('exit_goal_mode','all_axes')
    if mode=='reference_pivot':
        goals,metadata=reference_pivot_goals(planner,bodies,reference)
        result=plan_free_ring_transport(planner,observation,goals,contact_release=True,
            passive_contact_names=parameters.get('passive_contact_names',
                ('horseshoe_left','chain_upper_1','chain_lower_1')))
        result.update(observed_bodies={n:pose_dict(p) for n,p in bodies.items()},
            exit_goal_mode=mode,pivot_goals=metadata,
            method='native_joint_route_to_reference_pivot; no separation claim')
        write_json_atomic(planner.directory/'joint_withdrawal_plan.json',result)
        return result
    if parameters.get('direct_axis_exit_first',False):
        direct=direct_axis_withdrawal(planner,observation)
        if direct is not None:
            direct.update(observed_bodies={n:pose_dict(pose) for n,pose in bodies.items()},
                          exit_goal_mode=mode,method='direct_cartesian_axis_before_joint_search')
            write_json_atomic(planner.directory/'joint_withdrawal_plan.json',direct)
            return direct
    rp,rr=relative_pose(reference[-1]['horseshoe_right'],reference[-1]['target_ring'])
    direction=(hr*reference[-1]['horseshoe_right'][1].inv()).apply([-1.,0.,0.])
    end=hp+hr.apply(rp)
    remainder=np.vstack([r.apply(planner.task.placement_vertices[n])+p
        for n,(p,r) in bodies.items() if n!='target_ring'])
    boundary=float((remainder@direction).max())+.005
    rotation=bodies['target_ring'][1]
    loop=planner.task.assembly.loops['target_ring']
    center=loop.center-planner.task.body_origins['target_ring']
    symmetries=[Rotation.identity()]+[
        loop.rotation*Rotation.from_rotvec(np.pi*axis)*loop.rotation.inv() for axis in np.eye(3)]
    reference_rotation=hr*rr
    rotations=[reference_rotation*symmetry for symmetry in symmetries]
    rotations += [rotation]+[Rotation.from_euler(axis,angle,degrees=True)*rotation
                            for axis in ('x','y','z') for angle in (-90.,-45.,45.,90.)]
    if mode not in ('all_axes','reference'):raise ValueError('Unsupported exit goal mode')
    goals=[]
    for r in rotations:
        for retreat,dz in ((0.,0.),(.025,0.),(.025,-.04),(.05,-.08)):
            p=end+reference_rotation.apply(center)-r.apply(center)+retreat*direction+[0,0,dz]
            gap=boundary-float(((r.apply(planner.task.placement_vertices['target_ring'])+p)@direction).min())
            goals.append((p+max(0.,gap)*direction,r))
    for axis in ((*np.eye(3),*-np.eye(3)) if mode=='all_axes' else ()):
        boundary=float((remainder@axis).max())+.008
        for r in rotations:
            p=bodies['target_ring'][0].copy()
            gap=boundary-float(((r.apply(planner.task.placement_vertices['target_ring'])+p)@axis).min())
            goals.append((p+max(0.,gap)*axis,r))
    result=plan_free_ring_transport(planner,observation,goals,contact_release=True,
        passive_contact_names=getattr(planner,'withdrawal_parameters',{}).get(
            'passive_contact_names',('horseshoe_left','chain_upper_1','chain_lower_1')))
    result.update(observed_bodies={n:pose_dict(p) for n,p in bodies.items()},
                  exit_goal_mode=mode,reference_final_attitudes_included=True,
                  method='joint_search_with_passive_contact_then_dense_cartesian_replay')
    write_json_atomic(planner.directory/'joint_withdrawal_plan.json',result)
    return result


def plan_withdrawal(planner, observation, reference, fold_end_index):
    """Guide finite SE(3) search with the independently certified object exit."""
    # The upper shoe and the two chain links are passive. Ring contact may
    # lift the upper shoe or pivot the links through their intact eyes.
    # The robot and held lower shoe remain static collision obstacles.
    checker=HeldRingPath(planner,observation,
                        passive_contact_names=('horseshoe_left','chain_upper_1','chain_lower_1'))
    measured=checker.bodies.copy()
    hp,hr=measured['horseshoe_right']
    turn=hr*reference[-1]['horseshoe_right'][1].inv()
    # Fix the actual held body exactly. The released upper shoe has settled,
    # so aligning a guide through it would distort ring/lower-shoe clearance.
    full_guide=[]
    for frame in reference:
        p,r=relative_pose(frame['horseshoe_right'],frame['target_ring'])
        full_guide.append((hp+hr.apply(p),hr*r))
    # Ellipse half-turn symmetries preserve the solid while selecting the
    # reference orientation closest to the actual material grasp phase.
    loop=planner.task.assembly.loops['target_ring']
    center=loop.center-planner.task.body_origins['target_ring']
    symmetries=[Rotation.identity()]+[
        loop.rotation*Rotation.from_rotvec(np.pi*axis)*loop.rotation.inv() for axis in np.eye(3)]
    matches=[]
    for symmetry in symmetries:
        for index in range(0,len(full_guide),4):
            p,r=full_guide[index];candidate=(p+r.apply(center-symmetry.apply(center)),r*symmetry)
            matches.append((checker.motion(checker.start,candidate),index,symmetry))
    _,reference_start,symmetry=min(matches,key=lambda row:row[0])
    anchors=getattr(planner,'selected_ring_grasp',{}).get('withdrawal_anchors')
    if anchors and anchors.get('passed'):
        symmetry=Rotation.from_quat(np.roll(anchors['symmetry_wxyz'],-1))
        reference_start=fold_end_index
    guide=full_guide[reference_start:]
    guide=[(p+r.apply(center-symmetry.apply(center)),r*symmetry) for p,r in guide]
    initial=checker.check(checker.start)
    attempts=[]
    if not initial['passed']:
        write_json_atomic(planner.directory/'ring_withdrawal_plan.json',dict(passed=False,initial=initial))
        raise ValueError('Measured ring grasp does not satisfy withdrawal geometry checks')
    escape=checker.contact_escape()
    release_edges=len(escape)-1
    search_start=escape[-1]
    # A different physical grasp need not end in the canonical ring attitude.
    # Require a separating plane beyond the entire remainder, then search
    # reachable ring attitudes and heights in that genuinely free halfspace.
    direction=turn.apply([-1.,0.,0.])
    remainder=np.vstack([r.apply(planner.task.placement_vertices[n])+p
        for n,(p,r) in measured.items() if n!='target_ring'])
    boundary=float((remainder@direction).max())+.005
    rotations=[guide[-1][1],checker.start[1]]
    rotations += [guide[-1][1]*s for s in symmetries[1:]]
    rotations += [Rotation.from_euler(axis,angle,degrees=True)*checker.start[1]
                  for axis in ('x','y','z') for angle in (-45.,45.)]
    goals=[]
    for rotation in rotations:
        for retreat,dz in ((0.,0.),(.025,0.),(.025,-.04),(.05,-.08)):
            goal=(guide[-1][0]+retreat*direction+[0,0,dz],rotation)
            if float(((rotation.apply(checker.vertices)+goal[0])@direction).min())>=boundary:
                goals.append(goal)
    searched=0
    for trial,goal in enumerate(goals):
        if searched>=4:break
        endpoint=checker.check(goal)
        if not endpoint['passed']:
            attempts.append(dict(trial=trial,endpoint=endpoint));continue
        searched+=1
        guided=[*escape,*guide[::4],guide[-1],goal]
        try:guided_audit=checker.ordered_audit(guided,release_prefix_edges=release_edges)
        except TimeoutError as error:
            attempts.append(dict(trial=trial,connected=False,error=str(error)));break
        if guided_audit['passed']:
            result=dict(passed=True,poses=[pose_dict(p) for p in guided],ordered_audit=guided_audit,
                        attempts=attempts,method='measured_bridge_then_reference',
                        reference_start_index=reference_start,reference_frame='measured held lower shoe',
                        observed_bodies={n:pose_dict(p) for n,p in measured.items()},
                        initial_convex_penetration_m=checker.initial_penetration_m,
                        release_prefix_edges=release_edges,
                        passive_contact_names=list(checker.passive_contact_names),
                        contact_release_radius_m=.003,queries=checker.queries,
                        scope='sampled contact-planning candidate; upper shoe and chain links may respond to ring contact; dynamics unverified')
            write_json_atomic(planner.directory/'ring_withdrawal_plan.json',result)
            return result
        attempts.append(dict(trial=trial,guided_audit=guided_audit))
        direct=checker.edge(search_start,goal)
        if direct['passed']:
            path=[search_start,goal];search=dict(connected=True,method='direct')
        else:
            def sample(rng):
                if rng.random()<.7:
                    gp,gr=guide[int(rng.integers(len(guide)))]
                    return gp+rng.normal(0,.015,3),Rotation.from_rotvec(rng.normal(0,.25,3))*gr
                pose=interpolate(search_start,goal,rng.random())
                return pose[0]+rng.normal(0,.07,3),Rotation.from_rotvec(rng.normal(0,.6,3))*pose[1]
            try:
                path,search=connect_search(checker,search_start,goal,sample,rng=np.random.default_rng(120+trial),
                    iterations=2000,step_m=.008,
                    progress=lambda row:write_json_atomic(planner.directory/'ring_tree_progress.json',dict(trial=trial,**row)))
            except TimeoutError as error:
                attempts.append(dict(trial=trial,connected=False,error=str(error)))
                break
        attempts.append(dict(trial=trial,search=search))
        if path is None:continue
        path=[*escape,*path[1:]]
        # Recheck the complete ordered route, not just its two search trees.
        audit=checker.ordered_audit(path,release_prefix_edges=release_edges)
        if not audit['passed']:continue
        result=dict(passed=True,poses=[pose_dict(p) for p in path],ordered_audit=audit,attempts=attempts,
                    reference_start_index=reference_start,reference_frame='measured held lower shoe',
                    observed_bodies={n:pose_dict(p) for n,p in measured.items()},
                    initial_convex_penetration_m=checker.initial_penetration_m,
                    release_prefix_edges=release_edges,
                    passive_contact_names=list(checker.passive_contact_names),
                    contact_release_radius_m=.003,queries=checker.queries,
                    scope='sampled contact-planning candidate; upper shoe and chain links may respond to ring contact; dynamics unverified')
        write_json_atomic(planner.directory/'ring_withdrawal_plan.json',result)
        return result
    write_json_atomic(planner.directory/'ring_withdrawal_plan.json',dict(passed=False,attempts=attempts,queries=checker.queries))
    raise ValueError('No checked withdrawal route found within the finite search budget')
