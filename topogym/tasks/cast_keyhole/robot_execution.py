"""Attempt bounded joint-control execution with simultaneous-contact-gated welds.

Pregrasp reset is disclosed. After reset, no robot or puzzle poses are written.
The auxiliary welds model grasp retention and do not qualify friction-only grasping.
"""
from __future__ import annotations
import argparse
import hashlib
import json
from pathlib import Path
import time

from hydra import compose,initialize_config_dir
import numpy as np
from omegaconf import OmegaConf
from scipy.spatial.transform import Rotation

from .aloha_demo import canonical_to_entities
from .collision import CompoundCollision
from .geometry import ASSET_ROOT
from .physics_probe import array
from .robot_motion import ROOT
from .solution import canonical_geometry


def run(motion_path,output,speed_factor=1.,geometry_path=None,dt_override=None,backend="cuda"):
    motion=json.loads(Path(motion_path).read_text())
    if not motion["report"].get("sampled_robot_scene_clearance_passed"):
        raise ValueError("Complete checked IK trajectory required")
    variant=None
    if geometry_path is None:
        if motion["report"]["template_sha256"]!=hashlib.sha256((ASSET_ROOT/"template.json").read_bytes()).hexdigest():
            raise ValueError("Stale geometry")
    else:
        from .variant_assets import require_variant
        from .inverse_variants import geometry_from_record
        variant,_=require_variant(geometry_path,motion)
    output=Path(output).resolve();output.mkdir(parents=True,exist_ok=True)
    import genesis as gs
    from topogym.robot import initialize_robot_controller
    from .scene import build_scene
    with initialize_config_dir(config_dir=str(ROOT/"configs"),version_base="1.3"):
        cfg=compose(config_name="cast_keyhole_aloha",overrides=["env.renderer.type=rasterizer"])
    cfg.env.cameras=OmegaConf.create({})
    cfg.env.genesis.backend=backend
    if variant is not None:cfg.task.variant=variant["id"]
    if dt_override is not None:cfg.env.sim.dt=dt_override
    OmegaConf.save(cfg,output/"config.yaml",resolve=True)
    gs.init(backend=gs.cuda if backend=="cuda" else gs.cpu,precision="64",logging_level="warning",seed=0)
    task=build_scene(cfg,output/"assets",geometry_path=geometry_path)
    controller=initialize_robot_controller(scene=task.scene,manifest=task.manifest,robot_cfg=cfg.robot_control,settle_steps=0)
    robot=controller.robot;mount=np.asarray(cfg.env.robot_mount.pos)
    q0=np.asarray(motion["frames"][0]["qpos"]);q0[[6,7,14,15]]=.0127
    robot.set_qpos(q0);canonical_to_entities(task,motion["frames"][0],mount)
    armids=np.array(controller.left.arm_dofs+controller.right.arm_dofs)
    fingerids=[controller.left.dofs_idx[6],controller.right.dofs_idx[6]]
    robot.set_dofs_kp(np.full(12,100000.),armids);robot.set_dofs_kv(np.full(12,2000.),armids)
    robot.set_dofs_kp(np.full(2,2000.),fingerids);robot.set_dofs_kv(np.full(2,124.),fingerids)
    robot.control_dofs_position([.0105,.0105],fingerids)
    solver=task.scene.sim.rigid_solver
    attached={};trace=[];aborted=None
    dt=float(cfg.env.sim.dt);fps=float(motion["fps"])
    duration=(len(motion["frames"])-1)/fps/speed_factor
    if variant is None:_,_,cells=canonical_geometry(3.)
    else:_,cells=geometry_from_record(variant)
    collision=CompoundCollision(*cells)
    rx=Rotation.from_euler("x",90,degrees=True).as_matrix();rz=Rotation.from_euler("z",90,degrees=True).as_matrix()
    transforms=[(rz@rx,np.array([0,0,task.assembly.template["gold_offset_z"]])*task.assembly.unit),(rx,np.zeros(3))]
    maxpen=0.;mingap=float("inf");maxerror=0.;started=time.monotonic()
    def state():
        bodies={};poses=[]
        for item,(a,b) in zip(task.asset_report["bodies"],transforms):
            body=task.bodies[item["name"]];r=Rotation.from_quat(array(body.get_quat())[[1,2,3,0]]).as_matrix()
            t=array(body.get_pos())-mount-r@(np.asarray(item["origin_m"])-b);r=r@a
            poses.append((r,t));bodies[item["name"]]=dict(pos=t.tolist(),quat=Rotation.from_matrix(r).as_quat().tolist())
        return poses,bodies
    for step in range(int(np.ceil((duration+1.5)/dt))):
        now=step*dt;index=np.clip((now-.5)*speed_factor*fps,0,len(motion["frames"])-1)
        i=min(int(index),len(motion["frames"])-2);u=index-i
        qa=np.array(motion["frames"][i]["qpos"]);qb=np.array(motion["frames"][i+1]["qpos"])
        q=(1-u)*qa+u*qb;v=(qb-qa)*fps*speed_factor if .5<now<duration+.5 else np.zeros(16)
        robot.control_dofs_position_velocity(q[armids],v[armids],armids)
        task.scene.step()
        for side,name in zip(("left","right"),("keyhole_gold","keyhole_silver")):
            if side in attached:continue
            fingers={robot.get_link(f"{side}/{f}_finger_link").idx for f in ("left","right")}
            contacts=robot.get_contacts(with_entity=task.bodies[name])
            touched=set(array(contacts["link_a"]).ravel().tolist())|set(array(contacts["link_b"]).ravel().tolist())
            if fingers.issubset(touched):
                links=(controller.arms[side].ee_link.idx,task.bodies[name].base_link_idx)
                solver.add_weld_constraint(*links)
                attached[side]=dict(physics_step=step+1,time_s=(step+1)*dt,simultaneous_finger_contacts=sorted(fingers),links=list(links))
                print(f"Contact-gated grasp {side} at {(step+1)*dt:.3f}s",flush=True)
        if now>.12 and len(attached)!=2:
            aborted="Both fingers did not simultaneously contact each assigned piece";break
        depths=array(solver.collider.get_contacts()["penetration"])
        if depths.size:maxpen=max(maxpen,float(depths.max()))
        actual_q=array(robot.get_qpos())
        if not np.isfinite(actual_q).all():aborted="Non-finite robot state";break
        maxerror=max(maxerror,float(np.max(np.abs(actual_q[armids]-q[armids]))))
        if (step+1)%10==0:
            poses,bodies=state();(rg,tg),(rs,ts)=poses
            gap=collision.gap(rg.T@rs,rg.T@(ts-tg));mingap=min(mingap,gap)
            trace.append(dict(time_s=(step+1)*dt,physics_step=step+1,qpos=actual_q.tolist(),bodies=bodies,
                stage=motion["frames"][i]["stage"],sat_gap_m=gap))
            if gap<-.0005 or maxpen>.001:
                aborted=f"Physical collision tolerance exceeded: gap={gap}, penetration={maxpen}";break
        if (step+1)%2000==0:print(f"Robot {now+dt:.1f}/{duration+1.5:.1f}s; wall {time.monotonic()-started:.1f}s",flush=True)
    poses,bodies=state();(rg,tg),(rs,ts)=poses;gap=float(collision.gap(rg.T@rs,rg.T@(ts-tg)))
    passed=aborted is None and len(attached)==2 and gap>.02 and mingap>-.0005 and maxpen<.001
    report=dict(passed=bool(passed),aborted=aborted,pregrasp_start=True,assisted_weld_grasp=True,
        friction_only_grasp_verified=False,pose_writes_after_reset=False,physics_steps=step+1,
        simulated_seconds=(step+1)*dt,dt=dt,attached=attached,max_contact_penetration_m=maxpen,
        minimum_sampled_sat_gap_m=mingap if np.isfinite(mingap) else None,final_separation_lower_bound_m=gap,
        max_joint_tracking_error_rad=maxerror,arm_kp=100000.,arm_kv=2000.,joint_force_limits=OmegaConf.to_container(cfg.robot_control.controller.force_limit),
        speed_factor=speed_factor,backend=backend,robot_execution_verified=bool(passed),formal_demo_qualified=False,
        motion_sha256=hashlib.sha256(Path(motion_path).read_bytes()).hexdigest(),
        runner_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest())
    if variant is not None:
        report.update(variant_id=variant["id"],geometry_sha256=hashlib.sha256(Path(geometry_path).read_bytes()).hexdigest(),
            loaded_collision_audit=task.asset_report["loaded_collision_audit"])
    (output/"report.json").write_text(json.dumps(report,indent=2,allow_nan=False)+"\n")
    (output/"trajectory.json").write_text(json.dumps(trace,allow_nan=False)+"\n")
    print(json.dumps(report,indent=2),flush=True)
    return report


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument("--motion",type=Path,required=True)
    p.add_argument("--output",type=Path,required=True);p.add_argument("--speed-factor",type=float,default=1.)
    p.add_argument("--geometry",type=Path);p.add_argument("--dt",type=float)
    p.add_argument("--backend",choices=("cuda","cpu"),default="cuda")
    a=p.parse_args()
    if not run(a.motion,a.output,a.speed_factor,a.geometry,a.dt,a.backend)["passed"]:raise SystemExit(1)


if __name__=="__main__":main()
