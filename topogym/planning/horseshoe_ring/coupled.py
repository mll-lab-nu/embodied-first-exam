"""Coupled ALOHA IK with free common puzzle orientation and bounded workspace.

The relative rigid reference is a constraint; the joint posture is chosen
continuously near the preceding solution. Queries use native Genesis FK.
"""
import numpy as np
from scipy.optimize import least_squares
from scipy.spatial.transform import Rotation

from topogym.planning.rigid_reference.feedback import relative_pose
from topogym.planning.rigid_reference.geometry import pose_dict
from topogym.planning.oracle_ik import accept_coupled_candidate, active_scope


class CoupledHorseshoeIK:
    def __init__(self, checker, offsets, seed):
        self.checker,self.offsets,self.seed=checker,offsets,np.asarray(seed).copy()
        robot=checker.robot
        self.indices=np.concatenate([robot._q_indices[s][:6] for s in offsets])
        self.limits=np.concatenate([robot.groups[s].arm_limits_rad for s in offsets])
        self.links={s:robot.entity.get_link(robot.groups[s].hand_link).idx_local for s in offsets}

    def poses(self,q):
        full=self.seed.copy();full[self.indices]=q
        result=self.checker.fk.solve(full)
        ps=np.asarray(result['position_world_m']).reshape(-1,3)
        rs=Rotation.from_quat(np.asarray(result['orientation_wxyz']).reshape(-1,4)[:,[1,2,3,0]])
        bodies,hands={},{}
        for side,index in self.links.items():
            group=self.checker.robot.groups[side]
            tr=rs[index]*Rotation.from_quat(np.roll(group.tcp_orientation_in_hand_wxyz,-1))
            tp=ps[index]+rs[index].apply(group.tcp_position_in_hand_m)
            dp,dr=self.offsets[side];r=tr*dr.inv()
            bodies[side]=(tp-r.apply(dp),r);hands[side]=(tp,tr)
        return bodies,hands

    def solve(self,relative,center,previous):
        p,r=relative
        def residual(q):
            bodies,hands=self.poses(q)
            ap,ar=relative_pose(bodies['left'],bodies['right'])
            midpoint=(hands['left'][0]+hands['right'][0])/2
            delta=midpoint-center
            workspace=np.sign(delta)*np.maximum(np.abs(delta)-[.03,.03,.02],0.)
            return np.r_[20*(ap-p),(ar*r.inv()).as_rotvec(),10*workspace,.00003*(q-previous)]
        lower,upper=self.limits[:,0]+.05,self.limits[:,1]-.05
        seed=np.clip(previous,lower+1e-8,upper-1e-8)
        def stop(intermediate_result):
            e=intermediate_result.fun
            if np.linalg.norm(e[:3])/20<1e-6 and np.linalg.norm(e[3:6])<1e-5 and np.linalg.norm(e[6:9])/10<1e-6:
                raise StopIteration
        result=least_squares(residual,seed,bounds=(lower,upper),max_nfev=120,
                            ftol=1e-10,xtol=1e-10,gtol=1e-10,callback=stop)
        error=residual(result.x)
        start, goal = self.seed.copy(), self.seed.copy()
        start[self.indices], goal[self.indices] = previous, result.x
        if not accept_coupled_candidate(self.checker.robot, start, goal,
                [np.linalg.norm(error[:3])/20, np.linalg.norm(error[3:6]), np.linalg.norm(error[6:9])/10],
                [1e-5, 1e-4, 1e-5]):
            raise ValueError(f'Coupled IK residual: {error[:9].tolist()}')
        return result.x,self.poses(result.x)[0]

    def plan(self,frames,*,stride=20,progress=None):
        q=self.seed[self.indices].copy()
        _,hands=self.poses(q);center=(hands['left'][0]+hands['right'][0])/2
        output=[];failure=None
        for i in sorted(set(range(0,len(frames),stride))|{len(frames)-1}):
            reference=frames[i]
            try:
                q,bodies=self.solve(relative_pose(reference['horseshoe_left'],reference['horseshoe_right']),center,q)
                lp,lr=reference['horseshoe_left'];wp,wr=bodies['left']
                common=wr*lr.inv()
                world={n:(wp+common.apply(p-lp),common*r) for n,(p,r) in reference.items()}
                if active_scope(self.checker.robot.entity) is not None:
                    # Both held shoes come from FK; the right shoe is not an
                    # exact copy of the relative reference after approximate IK.
                    world.update({'horseshoe_'+s: pose for s, pose in bodies.items()})
                full=self.seed.copy();full[self.indices]=q
                check=self.checker.check(full,contacts={s:'horseshoe_'+s for s in self.offsets},body_poses=world)
                output.append(dict(reference_index=i,qpos=full.tolist(),bodies={n:pose_dict(p) for n,p in world.items()},**check))
                if not check['passed']:
                    failure=dict(index=i,reason='collision',checks=check);break
                if progress:progress(i)
            except ValueError as error:
                failure=dict(index=i,reason='ik',error=str(error));break
        return dict(passed=failure is None,frames=output,failure=failure,
                    scope='relative-path-preserving sampled native coupled IK; dynamic execution not established')
