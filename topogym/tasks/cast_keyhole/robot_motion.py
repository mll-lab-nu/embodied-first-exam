"""Dual-arm IK for the certified current Keyhole instance, with explicit grasps.

All poses use canonical plate origins and the robot's local tabletop frame.
The output is a pregrasp kinematic rehearsal, not a force-driven execution.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

import fcl
from hydra import compose, initialize_config_dir
import mujoco
import numpy as np
from scipy.optimize import least_squares
from scipy.spatial.transform import Rotation
import trimesh

from topogym.robot.assets import robot_asset
from .collision import CompoundCollision
from .instance_solution import require_current_instance_certificate
from .solution import load_solution
from .trajectory_probe import schedule

ROOT=Path(__file__).resolve().parents[3]
PAD_CENTER=np.array([.14381,0.,-.00355])
GRASP_POINTS=np.array([[-10.6,-31.,0.],[0.,29.7,0.]])*.003
GRASP_ROTATIONS=np.array([[[0,0,1],[1,0,0],[0,1,0]],[[0,0,-1],[-1,0,0],[0,1,0]]],dtype=float)


class Kinematics:
    def __init__(self,cfg):
        self.model=mujoco.MjModel.from_xml_path(robot_asset(cfg))
        self.data=mujoco.MjData(self.model)
        mujoco.mj_resetDataKeyframe(self.model,self.data,0)
        self.q=self.data.qpos.copy()
        self.indices={s:[int(self.model.joint(f"{s}/{n}").qposadr[0]) for n in cfg.robot.arm_joint_names]
                      for s in ("left","right")}
        self.limits=np.asarray(cfg.robot.arm_joint_limits)

    def pose(self,side):
        self.data.qpos[:]=self.q
        mujoco.mj_forward(self.model,self.data)
        b=self.model.body(f"{side}/gripper_link").id
        r=self.data.xmat[b].reshape(3,3).copy()
        return self.data.xpos[b].copy()+r@PAD_CENTER,r

    def solve(self,side,position,rotation):
        indices=self.indices[side]
        def residual(q):
            self.q[indices]=q
            p,r=self.pose(side)
            return np.r_[10*(p-position),Rotation.from_matrix(rotation@r.T).as_rotvec()]
        result=least_squares(residual,self.q[indices].copy(),
            bounds=(self.limits[:,0]+1e-6,self.limits[:,1]-1e-6),max_nfev=160,
            ftol=1e-11,xtol=1e-11,gtol=1e-11)
        e=residual(result.x)
        return float(np.linalg.norm(e[:3])/10),float(np.linalg.norm(e[3:]))


def balanced_pose(r,t,roll,center):
    """Keep the grasp midpoint fixed and the two hands ordered left to right."""
    gp,sp=GRASP_POINTS
    x=t+r@sp-gp;x/=np.linalg.norm(x)
    z=np.array([0.,0.,1.]);z-=x*np.dot(x,z);z/=np.linalg.norm(z)
    y=np.cross(z,x)
    w=Rotation.from_rotvec([roll,0,0]).as_matrix()@np.column_stack([x,y,z]).T
    offset=np.asarray(center)-w@(gp+t+r@sp)/2
    return [(w,offset),(w@r,offset+w@t)]


def bodies_from_fk(kin):
    result=[]
    for i,side in enumerate(("left","right")):
        p,h=kin.pose(side)
        r=h@GRASP_ROTATIONS[i].T
        result.append((r,p-r@GRASP_POINTS[i]))
    return result


class RobotClearance:
    """Check every robot collider against every convex puzzle cell, including containment."""
    def __init__(self,kin,cells):
        self.kin=kin;self.geoms=[]
        m=kin.model
        for i in range(m.ngeom):
            if not (m.geom_contype[i] or m.geom_conaffinity[i]):continue
            if m.geom_type[i]==mujoco.mjtGeom.mjGEOM_MESH:
                mesh=m.mesh(m.geom_dataid[i]);v=m.mesh_vert[mesh.vertadr[0]:mesh.vertadr[0]+mesh.vertnum[0]]
                hull=trimesh.convex.convex_hull(v)
                shape=self.convex(hull);v=hull.vertices
            elif m.geom_type[i]==mujoco.mjtGeom.mjGEOM_SPHERE:
                radius=m.geom_size[i,0];shape=fcl.Sphere(radius)
                v=trimesh.bounds.corners(np.array([[-radius]*3,[radius]*3]))
            else:raise ValueError("Unsupported ALOHA collision shape")
            self.geoms.append((i,m.body(m.geom_bodyid[i]).name,fcl.CollisionObject(shape),v))
        self.pieces=[[(fcl.CollisionObject(self.convex(c)),c.vertices) for c in cs] for cs in cells]
        self.request=fcl.CollisionRequest(num_max_contacts=8,enable_contact=True)

    @staticmethod
    def convex(mesh):
        return fcl.Convex(mesh.vertices,len(mesh.faces),
            np.column_stack([np.full(len(mesh.faces),3),mesh.faces]).reshape(-1))

    def violations(self,bodies):
        m,d=self.kin.model,self.kin.data
        d.qpos[:]=self.kin.q;mujoco.mj_forward(m,d)
        bad=[]
        for c in d.contact:
            if c.dist<-.0001:
                bad.append(dict(kind="self",a=m.body(m.geom_bodyid[c.geom1]).name,
                    b=m.body(m.geom_bodyid[c.geom2]).name,depth_m=float(-c.dist)))
        puzzle=[]
        for name,parts,(r,t) in zip(("gold","silver"),self.pieces,bodies):
            for obj,v in parts:
                obj.setTransform(fcl.Transform(r,t));v=v@r.T+t
                puzzle.append((name,obj,v.min(0),v.max(0)))
        for i,name,obj,v in self.geoms:
            r,t=d.geom_xmat[i].reshape(3,3),d.geom_xpos[i]
            obj.setTransform(fcl.Transform(r,t));v=v@r.T+t;lo,hi=v.min(0),v.max(0)
            if lo[2]<-.001 and "base_link" not in name:
                bad.append(dict(kind="table",robot=name,depth_m=float(-lo[2])))
            for part,other,pl,ph in puzzle:
                if np.any(lo>ph) or np.any(hi<pl):continue
                result=fcl.CollisionResult();fcl.collide(obj,other,self.request,result)
                depth=max((c.penetration_depth for c in result.contacts),default=0.)
                if result.is_collision and depth>.0003:
                    bad.append(dict(kind="puzzle",robot=name,puzzle=part,depth_m=float(depth)))
        return bad


def solve_frame(kin,r,t,roll,center):
    targets=balanced_pose(r,t,roll,center)
    errors=[]
    for i,side in enumerate(("left","right")):
        w,p=targets[i]
        errors.append(kin.solve(side,p+w@GRASP_POINTS[i],w@GRASP_ROTATIONS[i]))
    kin.q[[6,7,14,15]]=.0128
    return errors,bodies_from_fk(kin)


def solve_coupled(kin,r,t,center):
    """Solve relative SE(3) and hand midpoint together, leaving common rotation free."""
    indices=np.r_[kin.indices["left"],kin.indices["right"]]
    limits=np.tile(kin.limits,(2,1));previous=kin.q[indices].copy()
    def residual(q):
        kin.q[indices]=q
        (rg,tg),(rs,ts)=bodies_from_fk(kin)
        lp=tg+rg@GRASP_POINTS[0];rp=ts+rs@GRASP_POINTS[1]
        return np.r_[20*(rg.T@(ts-tg)-t),Rotation.from_matrix(rg.T@rs@r.T).as_rotvec(),
                     10*((lp+rp)/2-center),.00003*(q-previous)]
    result=least_squares(residual,previous,bounds=(limits[:,0]+1e-6,limits[:,1]-1e-6),
        max_nfev=150,ftol=1e-11,xtol=1e-11,gtol=1e-11)
    e=residual(result.x)
    return (float(np.linalg.norm(e[:3])/20),float(np.linalg.norm(e[3:6]))),bodies_from_fk(kin)


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--solution",type=Path,required=True)
    parser.add_argument("--certificate",type=Path,required=True)
    parser.add_argument("--output",type=Path,required=True)
    parser.add_argument("--roll",type=float,default=-1.57)
    parser.add_argument("--center",type=float,nargs=3,default=[0.,0.,.28])
    parser.add_argument("--fps",type=int,default=12)
    args=parser.parse_args()
    require_current_instance_certificate(args.solution,args.certificate)
    data,meshes,cells,motions=load_solution(args.solution)
    with initialize_config_dir(config_dir=str(ROOT/"configs"),version_base="1.3"):
        cfg=compose(config_name="cast_keyhole_aloha")
    kin=Kinematics(cfg.robot_control);check=RobotClearance(kin,cells);collision=CompoundCollision(*cells)
    boundaries=schedule(motions,speed=.065,angular_speed=.55)
    frames=[];phases=[];max_error=np.zeros(2);min_gap=float("inf")
    for i,m in enumerate(motions):
        stage=data["motions"][i]["stage"]
        if not phases or phases[-1]["name"]!=stage:
            phases.append(dict(name=stage,frame=len(frames),time_s=len(frames)/args.fps))
        count=int(np.ceil((boundaries[i+1]-boundaries[i])*args.fps))
        for s in np.linspace(0,1,count+1)[int(i>0):]:
            u=10*s**3-15*s**4+6*s**5;r,t=m.pose(u)
            if not frames:
                seed_errors,_=solve_frame(kin,r,t,args.roll,args.center)
                if np.max(seed_errors)>1e-5:raise RuntimeError(f"Invalid initial IK: {seed_errors}")
            errors,bodies=solve_coupled(kin,r,t,np.array(args.center))
            max_error=np.maximum(max_error,errors)
            if max_error[0]>.00002 or max_error[1]>.0001:
                raise RuntimeError(f"Unreachable {i}, {s}: {errors}")
            bad=check.violations(bodies)
            if bad:raise RuntimeError(f"Robot collision {i}, {s}: {bad}")
            (rg,tg),(rs,ts)=bodies;gap=collision.gap(rg.T@rs,rg.T@(ts-tg));min_gap=min(min_gap,gap)
            if gap<.00015:raise RuntimeError(f"Actual FK clearance failed: {gap}")
            poses={n:dict(pos=p.tolist(),quat=Rotation.from_matrix(w).as_quat().tolist())
                   for n,(w,p) in zip(("keyhole_gold","keyhole_silver"),bodies)}
            targets={side:dict(pos=kin.pose(side)[0].tolist(),quat=Rotation.from_matrix(kin.pose(side)[1]).as_quat().tolist())
                     for side in ("left","right")}
            frames.append(dict(qpos=kin.q.tolist(),bodies=poses,stage=stage,motion=i,u=float(u),grasp_targets=targets))
        print(f"IK {i+1}/{len(motions)}; {len(frames)} frames",flush=True)
    interpolation_samples=0
    for i,(a,b) in enumerate(zip(frames,frames[1:])):
        qa,qb=np.array(a["qpos"]),np.array(b["qpos"])
        count=max(2,int(np.ceil(np.max(np.abs(qb-qa))/.003)))
        for u in np.linspace(0,1,count+1)[1:-1]:
            kin.q=(1-u)*qa+u*qb;bodies=bodies_from_fk(kin)
            bad=check.violations(bodies)
            if bad:raise RuntimeError(f"Joint interpolation collision after frame {i}: {bad}")
            (rg,tg),(rs,ts)=bodies
            gap=collision.gap(rg.T@rs,rg.T@(ts-tg));min_gap=min(min_gap,gap)
            if gap<.00015:raise RuntimeError(f"Joint interpolation violates clearance after frame {i}: {gap}")
            interpolation_samples+=1
    report=dict(scope=__doc__,passed=True,scene_scale=3.,pregrasp_start=True,
        physics_steps=0,kinematic_replay=True,robot_execution_verified=False,formal_demo_qualified=False,
        sampled_robot_scene_clearance_passed=True,robot_clearance_scope="sampled frames only",
        max_relative_ik_position_error_m=float(max_error[0]),max_relative_ik_rotation_error_rad=float(max_error[1]),
        minimum_sampled_fk_gap_m=min_gap,grasp_points_m=GRASP_POINTS.tolist(),
        grasp_rotations=GRASP_ROTATIONS.tolist(),common_roll_rad=args.roll,grasp_midpoint_m=args.center,
        solver="coupled 12-joint least squares: relative pose, fixed hand midpoint, minimum joint change",
        joint_interpolation_samples=interpolation_samples,max_checked_joint_interval_rad=.003,
        pose_source="actual MuJoCo gripper FK and fixed rigid grasp transforms",
        solution_sha256=hashlib.sha256(args.solution.read_bytes()).hexdigest(),
        template_sha256=hashlib.sha256((ROOT/"assets/tasks/cast_keyhole/diagram_reference_v1/template.json").read_bytes()).hexdigest())
    args.output.parent.mkdir(parents=True,exist_ok=True)
    args.output.write_text(json.dumps(dict(fps=args.fps,frames=frames,phases=phases,report=report),allow_nan=False)+"\n")
    print(json.dumps(report,indent=2))


if __name__=="__main__":main()
