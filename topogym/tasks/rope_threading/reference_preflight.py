"""CPU kinematic screening; never a certificate of physical execution."""
import argparse
import json
from pathlib import Path
from types import SimpleNamespace

import mujoco
import numpy as np
from hydra import compose, initialize_config_dir

from topogym.robot.assets import robot_asset
from topogym.tasks.knot_untying.control import BoundedAlohaIK
from .geometry import ThreadingLayout
from .reference_actions import ReferenceThreadingActions, ending_lift


def model_with_fixtures(cfg):
    spec = mujoco.MjSpec.from_file(robot_asset(cfg.robot_control))
    table = cfg.env.world.table
    mount = np.asarray(cfg.env.robot_mount.pos)
    spec.worldbody.add_geom(name="audit_table", type=mujoco.mjtGeom.mjGEOM_BOX,
        pos=np.asarray(table.pos)-mount, size=np.asarray(table.size)/2, contype=1, conaffinity=1)
    h = float(cfg.robot_control.robot.base_riser_height_m)
    for sign in (-1,1):
        spec.worldbody.add_geom(name=f"audit_riser_{sign}", type=mujoco.mjtGeom.mjGEOM_BOX,
            pos=[sign*.519,-.019,h/2], size=[.05,.06,h/2], contype=1, conaffinity=1)
    layout = ThreadingLayout()
    for ring in layout.rings():
        theta = np.arange(65)*2*np.pi/64
        points = np.asarray(ring["center_m"])+ring["radius_m"]*(
            np.cos(theta)[:,None]*ring["basis_u"]+np.sin(theta)[:,None]*ring["basis_v"])
        for i in range(64):
            spec.worldbody.add_geom(name=f'audit_{ring["name"]}_{i}', type=mujoco.mjtGeom.mjGEOM_CAPSULE,
                fromto=np.r_[points[i],points[i+1]],size=[ring["tube_radius_m"],0,0],contype=1,conaffinity=1)
        for kind in ("stand","base"):
            g=ring[kind]; pos=layout.transform(g["position"]);size=g["size"]
            args=dict(name=f'audit_{ring["name"]}_{kind}',contype=1,conaffinity=1)
            if kind=="stand":
                spec.worldbody.add_geom(type=mujoco.mjtGeom.mjGEOM_CAPSULE,
                    fromto=np.r_[pos-[0,0,size[1]],pos+[0,0,size[1]]],size=[size[0],0,0],**args)
            else:
                spec.worldbody.add_geom(type=mujoco.mjtGeom.mjGEOM_BOX,pos=pos,size=size,**args)
    return spec.compile()


def screen(output, *, ending_lift_m=0., interval=.25):
    project=Path(__file__).resolve().parents[3]
    with initialize_config_dir(config_dir=str(project/"configs"),version_base="1.3"):
        cfg=compose(config_name="rope_threading_soft_start_preview")
    model=model_with_fixtures(cfg);data=mujoco.MjData(model)
    actions=ReferenceThreadingActions(project/"runs/environment-solvability/rope_threading/reference_motion_v1")
    original=mujoco.MjModel.from_xml_path(robot_asset(cfg.robot_control)); home=mujoco.MjData(original)
    home.qpos[:]=actions.reference["qpos"][0];mujoco.mj_forward(original,home)
    arms={}
    for i,side in enumerate(("left","right")):
        body=home.body(f"{side}/gripper_link")
        pos,quat,q=body.xpos.copy(),body.xquat.copy(),home.qpos[i*8:i*8+6].copy()
        arms[side]=SimpleNamespace(hand_pos=lambda p=pos:p,hand_quat=lambda q=quat:q,arm_qpos=lambda q=q:q)
    ik=BoundedAlohaIK(None,SimpleNamespace(cfg=cfg.robot_control,arms=arms,left=arms["left"]))
    collisions=[]; failures=[];samples=[]
    for t in np.arange(0,actions.cutoff,interval):
        q,h,_,phase=actions._sample(t)
        if ending_lift_m and phase>=49:
            correction=ending_lift(t,actions.summary["stages"][49]["start_s"],ending_lift_m)
            try:
                q[8:14]=ik.solve("right",h[1,:3]+[0,0,.0009]+correction,h[1,3:],seed=q[8:14])
            except ValueError as exc:
                failures.append(dict(source_time_s=float(t),error=str(exc)))
                continue
        data.qpos[:]=q;mujoco.mj_forward(model,data)
        contacts=[c for c in data.contact if c.dist<-.0005]
        if contacts:
            c=min(contacts,key=lambda c:c.dist)
            collisions.append(dict(source_time_s=float(t),phase=phase,depth_m=float(-c.dist),
                geom_names=[model.geom(i).name for i in (c.geom1,c.geom2)],
                body_names=[model.body(model.geom_bodyid[i]).name for i in (c.geom1,c.geom2)],
                position_m=c.pos.tolist()))
        samples.append(q.copy())
    result=dict(scope="sampled MuJoCo kinematic screen with capsule-ring proxies; not physical execution",
        interval_s=interval,ending_lift_m=ending_lift_m,samples=len(samples),
        penetrating_samples=len(collisions),ik_failures=failures,
        collisions=collisions,clear=not collisions and not failures)
    output.parent.mkdir(parents=True,exist_ok=True)
    if output.exists():
        raise FileExistsError(output)
    output.write_text(json.dumps(result,indent=2)+"\n")
    return {k:v for k,v in result.items() if k!="collisions"}


if __name__=="__main__":
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument("output",type=Path)
    p.add_argument("--ending-lift",type=float,default=0.)
    p.add_argument("--interval",type=float,default=.25)
    a=p.parse_args()
    print(json.dumps(screen(a.output,ending_lift_m=a.ending_lift,interval=a.interval),indent=2))
