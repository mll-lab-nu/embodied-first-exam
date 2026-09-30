"""Keep the shoes horizontal after the flip to guide the passive ring.

This is a kinematic candidate generator. Gravity and the passive ring still
require an independent physical execution from the settled task birth.
"""
import fcl
import numpy as np
from scipy.optimize import least_squares
from scipy.spatial.transform import Rotation

from .coupled import CoupledHorseshoeIK
from .oracle import expand_coupled_plan
from topogym.planning.rigid_reference.feedback import body_pose, relative_pose
from topogym.planning.rigid_reference.geometry import interpolate, pose_dict


class LevelIK(CoupledHorseshoeIK):
    def __init__(self, checker, offsets, seed, *, joint_margin=.15):
        super().__init__(checker,offsets,seed)
        self.joint_margin=np.broadcast_to(np.asarray(joint_margin,dtype=float), (len(self.indices),)).copy()
        if (not np.isfinite(self.joint_margin).all() or np.any(self.joint_margin<0)
                or np.any(2*self.joint_margin>=self.limits[:,1]-self.limits[:,0])):
            raise ValueError('Invalid per-joint reserve')
        self.near_shapes=[s for s in checker.shapes if s[1] in
                          ('right/upper_forearm_link','right/lower_forearm_link','right/gripper_base')]

    def clearance_penalty(self, q):
        full=self.seed.copy();full[self.indices]=q
        pose=self.checker.fk.solve(full)
        ps=np.asarray(pose['position_world_m']).reshape(-1,3)
        rs=Rotation.from_quat(np.asarray(pose['orientation_wxyz']).reshape(-1,4)[:,[1,2,3,0]])
        for _,_,index,_,obj in self.near_shapes:obj.setTransform(fcl.Transform(rs[index].as_matrix(),ps[index]))
        base=[s for s in self.near_shapes if s[1]=='right/gripper_base']
        result=[]
        for name in ('right/upper_forearm_link','right/lower_forearm_link'):
            gap=min(fcl.distance(a[4],b[4],fcl.DistanceRequest(),fcl.DistanceResult())
                    for a in self.near_shapes if a[1]==name for b in base)
            result.append(60*max(0.,.005-gap))
        return result

    def constrained(self, relative, normal, center, previous, *, half_size, avoid_forearm, tilt_tolerance=0.):
        rp,rr=relative
        def residual(q):
            bodies,hands=self.poses(q)
            p,r=relative_pose(bodies['left'],bodies['right'])
            delta=(hands['left'][0]+hands['right'][0])/2-center
            up=bodies['left'][1].apply([0,0,1]);normal_error=up-normal
            if tilt_tolerance:
                dot=float(np.clip(up@normal,-1.,1.));angle=np.arccos(dot)
                if angle<=tilt_tolerance:normal_error=np.zeros(3)
                else:
                    lateral=up-dot*normal;lateral/=np.linalg.norm(lateral)
                    normal_error=up-(np.cos(tilt_tolerance)*normal+np.sin(tilt_tolerance)*lateral)
            collision=self.clearance_penalty(q) if avoid_forearm else []
            return np.r_[20*(p-rp),(r*rr.inv()).as_rotvec(),
                         normal_error,
                         10*np.sign(delta)*np.maximum(np.abs(delta)-half_size,0.),
                         collision,.00005*(q-previous)]
        hard_end=14 if avoid_forearm else 12
        def stop(intermediate_result):
            e=intermediate_result.fun
            if np.linalg.norm(e[:3])/20<1e-6 and np.linalg.norm(e[3:9])<1e-5 and np.linalg.norm(e[9:hard_end])<1e-5:
                raise StopIteration
        fit=least_squares(residual,previous,callback=stop,
            bounds=(self.limits[:,0]+self.joint_margin,self.limits[:,1]-self.joint_margin),max_nfev=140,
            ftol=1e-9,xtol=1e-9,gtol=1e-9)
        e=residual(fit.x)
        if np.linalg.norm(e[:3])/20>1e-5 or np.linalg.norm(e[3:9])>2e-4 or np.linalg.norm(e[9:12])>1e-4:
            raise ValueError(f'Horizontal coupled IK residual: {e[:12].tolist()}')
        return fit.x

    def world_frame(self, reference, q):
        bodies,_=self.poses(q)
        p,r=bodies['left'];lp,lr=reference['horseshoe_left'];turn=r*lr.inv()
        world={n:(p+turn.apply(bp-lp),turn*br) for n,(bp,br) in reference.items()}
        full=self.seed.copy();full[self.indices]=q
        checked=self.checker.check(full,contacts={s:'horseshoe_'+s for s in self.offsets},body_poses=world)
        if not checked['passed']:raise ValueError(str(checked))
        return dict(qpos=full.tolist(),bodies={n:pose_dict(p) for n,p in world.items()})


def plan_horizontal_fold(checker, reference, offsets, initial_plan, *, center, joint_margin=.15, progress=None):
    """Reorient after reference 1000, then fold with the upper shoe horizontal."""
    flip=1000
    first=next(row for row in initial_plan['frames'] if row['reference_index']==flip)
    solver=LevelIK(checker,offsets,np.asarray(first['qpos']),joint_margin=joint_margin)
    q=solver.seed[solver.indices].copy()
    initial={n:body_pose(v) for n,v in first['bodies'].items()}
    normal0=initial['horseshoe_left'][1].apply([0,0,1])
    delta=Rotation.align_vectors([[0.,0.,1.]],[normal0])[0].as_rotvec()
    _,hands=solver.poses(q);center0=(hands['left'][0]+hands['right'][0])/2
    relative=relative_pose(initial['horseshoe_left'],initial['horseshoe_right'])
    bridge=[]
    for u in np.linspace(0,1,101):
        q=solver.constrained(relative,Rotation.from_rotvec(delta*u).apply(normal0),
            center0+(np.asarray(center)-center0)*min(1.,3*u),q,
            half_size=np.array([.10,.10,.025]),avoid_forearm=False)
        bridge.append(dict(fraction=float(u),**solver.world_frame(initial,q)))
        if progress and len(bridge)%20==0:progress('reorient',float(u))
    _,hands=solver.poses(q);center=(hands['left'][0]+hands['right'][0])/2
    samples=[]
    for index in sorted(set(range(flip,len(reference),20))|{len(reference)-1}):
        frame=reference[index]
        tilt=.35*min(1.,(len(reference)-1-index)/(len(reference)-1-2400))
        q=solver.constrained(relative_pose(frame['horseshoe_left'],frame['horseshoe_right']),
            np.array([0.,0.,1.]),center,q,half_size=np.array([.20,.20,.025]),avoid_forearm=True,
            tilt_tolerance=tilt)
        samples.append(dict(reference_index=index,**solver.world_frame(frame,q)))
        if progress:progress('horizontal_fold',index)
    dense=expand_coupled_plan(reference,initial_plan)[:flip+1]
    lp,lr=initial['horseshoe_left']
    for a,b in zip(bridge[:-1],bridge[1:]):
        for u in np.linspace(0,1,6)[1:]:
            p,r=interpolate(body_pose(a['bodies']['horseshoe_left']),body_pose(b['bodies']['horseshoe_left']),u)
            turn=r*lr.inv()
            dense.append({n:(p+turn.apply(bp-lp),turn*br) for n,(bp,br) in initial.items()})
    cursor=0
    for index in range(flip+1,len(reference)):
        while cursor+1<len(samples)-1 and samples[cursor+1]['reference_index']<index:cursor+=1
        a,b=samples[cursor:cursor+2]
        u=(index-a['reference_index'])/(b['reference_index']-a['reference_index'])
        p,r=interpolate(body_pose(a['bodies']['horseshoe_left']),body_pose(b['bodies']['horseshoe_left']),u)
        lp,lr=reference[index]['horseshoe_left'];turn=r*lr.inv()
        dense.append({n:(p+turn.apply(bp-lp),turn*br) for n,(bp,br) in reference[index].items()})
    audit=checker.plan_fold(dense,offsets,seed=initial_plan['frames'][0]['qpos'],stride=4)
    return dict(passed=audit['passed'],failure=audit['failure'],dense_audit=audit,
                joint_margin_rad=joint_margin,maximum_shoe_tilt_rad=.35,final_shoe_tilt_rad=0.,
                reorientation=bridge,horizontal_samples=samples,
                world_frames=[{n:pose_dict(p) for n,p in frame.items()} for frame in dense],
                scope='sampled native IK with self collision; passive dynamics unverified')


def retarget_horizontal_fold(checker, offsets, initial_plan, *, progress=None):
    """Reserve wrist pitch while allowing a small support-plane tilt.

    This modifies only the common world transform of every reference frame.
    Relative puzzle geometry remains unchanged. The 0.07 rad support tilt is
    a candidate constraint, not a claim that a released shoe will stay put.
    """
    if not initial_plan.get('passed'):
        raise ValueError('Retargeting requires a previously checked candidate')
    bridge=initial_plan['reorientation']
    samples=initial_plan['horizontal_samples']
    if len(bridge)!=101 or samples[0]['reference_index']!=1000:
        raise ValueError('Unexpected horizontal reference indexing')
    reserve=np.array([.03,.03,.03,.005,.10,.005]*2)
    solver=LevelIK(checker,offsets,np.asarray(bridge[0]['qpos']),joint_margin=reserve)
    rows=[]
    for index,source in enumerate(bridge+samples):
        bodies={n:body_pose(p) for n,p in source['bodies'].items()}
        old_q=np.asarray(source['qpos'])[solver.indices]
        _,hands=solver.poses(old_q)
        center=(hands['left'][0]+hands['right'][0])/2
        previous=old_q if not rows else np.asarray(rows[-1]['qpos'])[solver.indices]
        previous=np.clip(previous,solver.limits[:,0]+reserve+1e-7,solver.limits[:,1]-reserve-1e-7)
        q=solver.constrained(relative_pose(bodies['horseshoe_left'],bodies['horseshoe_right']),
            bodies['horseshoe_left'][1].apply([0.,0.,1.]),center,previous,
            half_size=np.array([.15,.15,.15]),avoid_forearm=index>=101,
            tilt_tolerance=.07*min(1.,index/100.))
        rows.append(dict(fraction=source.get('fraction'),reference_index=source.get('reference_index'),
                         **solver.world_frame(bodies,q)))
        if progress and index%20==0:progress('reserve_retarget',index)
    knots=[(1000+round(row['fraction']*500),row) for row in rows[:101]]
    knots+=[(row['reference_index']+500,row) for row in rows[101:]]
    knots=sorted(dict(knots).items())
    original=initial_plan['world_frames']
    dense=[{n:body_pose(v) for n,v in frame.items()} for frame in original[:1000]]
    cursor=0
    for index in range(1000,len(original)):
        while cursor+1<len(knots)-1 and knots[cursor+1][0]<index:cursor+=1
        a,b=knots[cursor:cursor+2]
        u=(index-a[0])/(b[0]-a[0])
        p,r=interpolate(body_pose(a[1]['bodies']['horseshoe_left']),
                        body_pose(b[1]['bodies']['horseshoe_left']),u)
        source={n:body_pose(v) for n,v in original[index].items()}
        lp,lr=source['horseshoe_left'];turn=r*lr.inv()
        dense.append({n:(p+turn.apply(bp-lp),turn*br) for n,(bp,br) in source.items()})
    audit=checker.plan_fold(dense,offsets,seed=initial_plan['dense_audit']['frames'][0]['qpos'],stride=4)
    return dict(passed=audit['passed'],failure=audit['failure'],dense_audit=audit,
                joint_margin_rad=reserve.tolist(),reserve_applies_after_reference_index=1000,
                maximum_support_tilt_rad=.07,reorientation=rows[:101],horizontal_samples=rows[101:],
                world_frames=[{n:pose_dict(p) for n,p in frame.items()} for frame in dense],
                scope='sampled native IK with per-joint reserve; passive support and extraction unverified')
