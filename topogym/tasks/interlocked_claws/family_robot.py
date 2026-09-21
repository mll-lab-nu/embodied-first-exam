"""ALOHA IK and force-limited execution for authored Claw B0/C0 prototypes.

Pregrasp welds are explicit assistance. New plans end at stable separation;
historical placement/release plans retain their recorded objective.
"""
import argparse
import json
from pathlib import Path
import xml.etree.ElementTree as ET

import mujoco
import numpy as np
from omegaconf import OmegaConf
from scipy.spatial.transform import Rotation

from topogym.robot.assets import robot_asset
from topogym.tasks.cast_coil.robot_plan import Kinematics, PAD_CENTER
from .variants import _base_config
from .family_models import FamilyModel, Segment, pose, rot
from .family_physics import add_part, base_xml, body_pose, quat, values, save, sha,contact_time


def assembly_poses(family, seconds, settings):
    rel,phase=family.relative_pose(seconds)
    yaw=settings["yaw"]
    if settings.get("counter_rotate",0):
        # Accumulate segment rotations without wrapping at +/-180 degrees.
        remaining=max(0.,seconds);turn=0.
        for segment in family.segments:
            u=float(np.clip(remaining/segment.duration,0,1))
            u=u**3*(10-15*u+6*u*u)
            delta=Rotation.from_matrix(segment.end[:3,:3]@segment.start[:3,:3].T).as_rotvec()
            turn+=np.rad2deg(delta[2])*u
            remaining-=segment.duration
            if remaining<=0:break
        yaw+=settings["counter_rotate"]*turn
    if family.family.startswith("orthogonal_gate"):
        yaw*=np.rad2deg(np.arctan2(rel[1,0],rel[0,0]))
    yaw+=settings.get("yaw_offset",0.)
    tilt_x=settings.get("tilt_x",0)
    if "tilt_x_fade_start_s" in settings:
        u=np.clip((seconds-settings["tilt_x_fade_start_s"])/(settings["tilt_x_fade_end_s"]-settings["tilt_x_fade_start_s"]),0,1)
        tilt_x*=1-u*u*u*(10-15*u+6*u*u)
    R=(rot("z",yaw)*rot("y",settings.get("tilt_y",0))*rot("x",tilt_x)).as_matrix()
    if "axis_rotation_xyz_deg" in settings:
        R=rot("xyz",settings["axis_rotation_xyz_deg"]).as_matrix()@R
    shift=np.array([0,settings.get("y_compensation",0)*np.clip((seconds-11)/5,0,1),0])
    compensation=R@(settings["fraction"]*(rel[:3,3]-family.initial[1][:3,3]))
    if not settings.get("compensate_z",True):compensation[2]=0
    root=pose(np.asarray(settings["center"])+shift-compensation,R)
    return [root,root@rel],phase


def xml_scene(family, initial, dt, asset_dir=None):
    cfg=OmegaConf.create(_base_config())
    root=ET.parse(robot_asset(cfg.robot_control)).getroot()
    for k in list(root.findall("keyframe")):root.remove(k)
    root.remove(root.find("option"))
    settings=base_xml(dt,contact_time(family.family))
    root.append(settings.find("option"))
    for body in root.findall(".//body"):body.set("gravcomp","1")
    if family.family.startswith("orthogonal_gate") or family.family=="helical_claws_balanced_v2":
        # MuJoCo includes this compensation inside the joint actuator force
        # limiter, rather than adding an unlimited passive drive afterward.
        for joint in root.findall("worldbody//joint"):joint.set("actuatorgravcomp","true")
    # Keep the original joint actuator force limits, tuning only PD gains.
    for p in root.findall("default/default/default/position"):
        if p.get("kp")!="2000":p.set("kp","4000");p.set("kv","110")
    world=root.find("worldbody")
    for g in settings.find("worldbody"):world.append(g)
    for i,p in enumerate(initial):
        body=add_part(root,family,i,p)
        if asset_dir is not None:
            for g in body.findall("geom"):g.set("group","3")
            ET.SubElement(root.find("asset"),"mesh",name=f"part_visual_{i}",file=str((Path(asset_dir)/f"piece_{i}.obj").resolve()))
            ET.SubElement(body,"geom",name=f"part_visual_{i}",type="mesh",mesh=f"part_visual_{i}",contype="0",conaffinity="0",mass="0",group="2",rgba=values((.74,.40,.24,1) if i==0 else (.20,.53,.61,1)))
        part=family.parts[i]
        relative=pose(PAD_CENTER)@np.linalg.inv(part.grasp)
        ET.SubElement(root.find("equality"),"weld",name=f"grasp_{i}",body1=f"{part.side}/gripper_link",body2=f"piece_{i}",
            relpose=values(np.r_[relative[:3,3],quat(relative[:3,:3])]),solref=".003 1",solimp=".999 .9999 .001 .5 2",torquescale=".1")
    ET.SubElement(world,"light",pos="0 -1 2",dir="0 .3 -1",diffuse=".8 .8 .8",castshadow="true")
    ET.SubElement(world,"light",pos="1 1 1.5",dir="-.3 -.3 -1",diffuse=".5 .5 .5")
    visual=ET.SubElement(root,"visual")
    ET.SubElement(visual,"global",offwidth="1280",offheight="960")
    ET.SubElement(visual,"quality",shadowsize="2048",offsamples="4")
    ET.SubElement(visual,"headlight",diffuse=".5 .5 .5",ambient=".35 .35 .35",specular=".2 .2 .2")
    return root


def set_initial(model,data,q,poses):
    data.qpos[:16]=q
    for i,p in enumerate(poses):
        j=model.joint(f"piece_{i}_free").qposadr[0]
        data.qpos[j:j+7]=np.r_[p[:3,3],quat(p[:3,:3])]
    mujoco.mj_forward(model,data)


def contacts(model,data,family):
    out=[]
    for c in data.contact:
        if c.dist>=0:continue
        names=[model.body(model.geom_bodyid[g]).name for g in (c.geom1,c.geom2)]
        geoms=[model.geom(g).name for g in (c.geom1,c.geom2)]
        if all(n=="world" or n.endswith("base_link") for n in names):continue
        kind="robot_self"
        if set(names)=={"piece_0","piece_1"}:kind="pair"
        elif any(n.startswith("piece_") for n in names):
            idx=int(next(n for n in names if n.startswith("piece_")).split("_")[1])
            other=next(n for n in names if not n.startswith("piece_"))
            if other=="world":kind="part_table"
            elif other.startswith(family.parts[idx].side+"/") and "finger" in other:kind="grasp"
            else:kind="robot_part"
        elif "world" in names:kind="robot_table"
        out.append(dict(kind=kind,depth_m=float(-c.dist),bodies=names,geoms=geoms))
    return out


def robot_support_contacts(model,data,threshold_n=.01):
    """Contacts that would make a released part lean on or hang from a robot."""
    result=[]
    for i,c in enumerate(data.contact):
        names=[model.body(model.geom_bodyid[g]).name for g in (c.geom1,c.geom2)]
        if any(n.startswith("piece_") for n in names) and any("/" in n for n in names):
            wrench=np.zeros(6);mujoco.mj_contactForce(model,data,i,wrench)
            force=float(np.linalg.norm(wrench[:3]))
            if force>threshold_n:result.append(dict(bodies=names,force_n=force))
    return result


def build_plan(family_name, settings_path, output, sample_dt=.05, full=False, objective=None):
    objective=objective or ("separate" if family_name=="helical_claws_balanced_v2" or not full else "disassemble_release")
    if objective not in ("separate","disassemble_release"):raise ValueError(objective)
    full=objective=="disassemble_release"
    if family_name=="helical_claws_balanced_v2" and full:
        raise ValueError("The balanced helical revision is a separation-only task")
    if family_name=="orthogonal_gate_balanced_v2" and full:
        from .family_balanced_robot import build_plan as build_balanced_plan
        return build_balanced_plan(settings_path,output,sample_dt)
    output=Path(output);output.mkdir(parents=True,exist_ok=False)
    settings=json.loads(Path(settings_path).read_text())
    family=FamilyModel(family_name);family.save(output/"assets")
    cfg=OmegaConf.create(_base_config());k=Kinematics(cfg.robot_control)
    k.q=np.asarray(settings["q"][0]).copy()
    first,_=assembly_poses(family,0,settings)
    root=xml_scene(family,first,.0005,output/"assets")
    xml=ET.tostring(root,encoding="unicode");(output/"scene.xml").write_text(xml)
    model=mujoco.MjModel.from_xml_string(xml);data=mujoco.MjData(model)
    phases=[];rows=[];bad=[];max_p=max_a=max_step=0.
    duration=family.duration+1.
    schedule=[]
    for t in np.arange(0,duration+sample_dt/2,sample_dt):
        targets,phase=assembly_poses(family,max(0,t-1),settings)
        schedule.append((float(t),targets,"pregrasp_hold" if t<1 else phase,True,None))
    last=schedule[-1][1]
    if full:
        if family_name=="helical_crown":
            rotations=[rot("z",-20)*rot("y",45),rot("z",0)]
            xy=[[-.08,-.12],[.20,-.20]]
        else:
            rotations=[rot("z",90),rot("y",45)*rot("z",180)*rot("x",90)]
            xy=[[.10,-.55],[-.24,-.24]]
        placed=[]
        for part,r,position in zip(family.parts,rotations,xy):
            bottom=float(r.apply(part.mesh.vertices)[:,2].min())
            placed.append(pose([*position,-bottom+.004],r))
        raised=[p.copy() for p in placed]
        for i,p in enumerate(raised):p[2,3]=max(last[i][2,3],p[2,3]+.15)
        moves=[("carry_apart",5.,raised),("lower_to_table",7.,placed)]
        for phase,length,ends in moves:
            segments=[Segment(phase,length,a,b) for a,b in zip(last,ends)]
            for local in np.arange(sample_dt,length+sample_dt/2,sample_dt):
                schedule.append((duration+float(local),[s.at(local/length) for s in segments],phase,True,None))
            duration+=length;last=ends
        released_at=duration
        start_tcp=[p@part.grasp for part,p in zip(family.parts,last)]
        end_tcp=[p.copy() for p in start_tcp]
        for part,p in zip(family.parts,end_tcp):
            retreat=.05 if family_name.startswith("orthogonal_gate") and part.side=="left" else .07
            p[:3,3]+=-p[:3,0]*retreat+np.array([0,0,retreat])
        segments=[Segment("open_and_retreat",4.,a,b) for a,b in zip(start_tcp,end_tcp)]
        for local in np.arange(sample_dt,9.+sample_dt/2,sample_dt):
            tcps=[s.at(min(1,local/4)) for s in segments]
            schedule.append((duration+float(local),last,"open_and_retreat" if local<4 else "free_settle",False,tcps))
        duration+=9.
    else:
        released_at=None
        for local in np.arange(sample_dt,1.5+sample_dt/2,sample_dt):
            schedule.append((duration+float(local),last,"separated_hold",True,None))
        duration+=1.5
    for t,targets,phase,held,override in schedule:
        previous=k.q.copy()
        for i,(part,p) in enumerate(zip(family.parts,targets)):
            target=override[i] if override is not None else p@part.grasp
            pe,ae=k.solve(part.side,target[:3,3],Rotation.from_matrix(target[:3,:3]))
            max_p=max(max_p,pe);max_a=max(max_a,ae)
            if pe>1e-5 or ae>1e-4:
                save(output/"failure.json",dict(time_s=float(t),phase=phase,side=part.side,position_m=pe,angle_rad=ae))
                save(output/"partial_diagnostics.json",dict(rows=rows,collision_failures=bad))
                raise RuntimeError(f"Unreachable at {t}: {part.side} {pe} {ae}")
            for name in ("left_finger","right_finger"):
                fraction=1 if held else max(0,1-(t-released_at)/.6)
                k.q[k.model.joint(f"{part.side}/{name}").qposadr[0]]=fraction*part.finger+(1-fraction)*.037
        if rows:max_step=max(max_step,float(np.max(np.abs(k.q-previous))))
        set_initial(model,data,k.q,targets)
        cs=contacts(model,data,family)
        invalid=[c for c in cs if c["kind"]!="grasp" and c["depth_m"]>.0001]
        if invalid:bad.append(dict(time_s=float(t),phase=phase,contacts=invalid))
        rows.append(dict(time_s=float(t),phase=phase,q=k.q.tolist(),poses=[p.tolist() for p in targets],held=held))
    report=dict(family=family_name,objective=objective,scope="complete IK with pregrasp and release" if full else "complete separation IK with pregrasp and final hold",sample_dt_s=sample_dt,max_position_error_m=max_p,max_angle_error_rad=max_a,
                max_joint_step_rad=max_step,collision_frames=len(bad),collision_failures=bad,passed=not bad)
    save(output/"plan.json",dict(family=family_name,objective=objective,settings=settings,release_time_s=released_at,duration_s=duration,rows=rows,report=report))
    save(output/"report.json",report)
    print(json.dumps({k:v for k,v in report.items() if k!="collision_failures"},indent=2))
    return report


def execute(plan_path,output,dt=.0005):
    plan_path=Path(plan_path);plan=json.loads(plan_path.read_text())
    objective=plan.get("objective","disassemble_release")
    if objective not in ("separate","disassemble_release"):raise ValueError(objective)
    if not plan["report"]["passed"]:raise ValueError("Plan has unresolved collisions")
    output=Path(output);output.mkdir(parents=True,exist_ok=False)
    family=FamilyModel(plan["family"])
    snapshot=json.loads((plan_path.parent/"assets/model.json").read_text())
    for part,record in zip(family.parts,snapshot["parts"]):
        if part.boxes!=record["boxes"] or not np.array_equal(part.grasp,record["grasp"]):
            raise ValueError("Model changed after planning; regenerate and revalidate the plan")
        props=part.mesh.mass_properties
        if not np.isclose(props.mass,record["mass_kg"],rtol=1e-12,atol=1e-15) or not np.allclose(props.inertia,record["inertia"],rtol=1e-12,atol=1e-15):
            raise ValueError("Mass properties changed after planning")
    initial=[np.asarray(p) for p in plan["rows"][0]["poses"]]
    root=xml_scene(family,initial,dt,plan_path.parent/"assets")
    xml=ET.tostring(root,encoding="unicode");(output/"scene.xml").write_text(xml)
    model=mujoco.MjModel.from_xml_string(xml);data=mujoco.MjData(model)
    set_initial(model,data,plan["rows"][0]["q"],initial)
    actuator_q=[model.jnt_qposadr[j] for j in model.actuator_trnid[:,0]]
    data.ctrl[:]=data.qpos[actuator_q]
    mujoco.mj_forward(model,data)
    external_gravity_mask=np.ones(model.nv)
    for j in range(model.njnt):
        if model.jnt_actgravcomp[j]:external_gravity_mask[model.jnt_dofadr[j]]=0
    grasp_ids=[model.equality(f"grasp_{i}").id for i in range(2)]
    release_times=np.asarray([np.inf]*2 if objective=="separate" else plan.get("release_times_s",[plan["release_time_s"]]*2),dtype=float)
    times=np.array([r["time_s"] for r in plan["rows"]]);qs=np.array([r["q"] for r in plan["rows"]])
    steps=round(plan["duration_s"]/dt);stride=round(.05/dt)
    frames=[];vframes=[];eframes=[];tframes=[];phase_frames=[];tail=[]
    depths={};witnesses={};max_p=max_a=max_q=0.;torque=np.zeros(model.nv);force=np.zeros(model.nu);total_drive=np.zeros(model.nv)
    saturation=np.zeros(model.nv,dtype=int);max_weld_p=max_weld_a=0.;released=False;tail_robot_support=0
    tail_separation=float("inf")
    for step in range(steps+1):
        t=float(data.time)
        idx=min(np.searchsorted(times,t,side="right")-1,len(times)-2);idx=max(0,idx)
        u=float(np.clip((t-times[idx])/(times[idx+1]-times[idx]),0,1))
        command=(1-u)*qs[idx]+u*qs[idx+1]
        for i,release_time in enumerate(release_times):
            if t>=release_time:data.eq_active[grasp_ids[i]]=0
        released=not data.eq_active[grasp_ids].any()
        data.ctrl[:]=command[actuator_q]
        mujoco.mj_forward(model,data)
        if step%10==0 and not released:
            for i,part in enumerate(family.parts):
                if not data.eq_active[grasp_ids[i]]:continue
                actual=body_pose(data,model.body(f"piece_{i}").id)
                desired=Segment("sample",1,np.asarray(plan["rows"][idx]["poses"][i]),np.asarray(plan["rows"][idx+1]["poses"][i])).at(u)
                max_p=max(max_p,float(np.linalg.norm(actual[:3,3]-desired[:3,3])))
                max_a=max(max_a,float(Rotation.from_matrix(actual[:3,:3]@desired[:3,:3].T).magnitude()))
                gripper=body_pose(data,model.body(f"{part.side}/gripper_link").id)
                expected=gripper@pose(PAD_CENTER)@np.linalg.inv(part.grasp)
                max_weld_p=max(max_weld_p,float(np.linalg.norm(actual[:3,3]-expected[:3,3])))
                max_weld_a=max(max_weld_a,float(Rotation.from_matrix(actual[:3,:3]@expected[:3,:3].T).magnitude()))
        max_q=max(max_q,float(np.max(np.abs(data.qpos[:16]-command))))
        torque=np.maximum(torque,np.abs(data.qfrc_actuator));force=np.maximum(force,np.abs(data.actuator_force))
        total_drive=np.maximum(total_drive,np.abs(data.qfrc_actuator+external_gravity_mask*data.qfrc_gravcomp))
        for c in contacts(model,data,family):
            kind=c["kind"]
            if c["depth_m"]>depths.get(kind,0):depths[kind]=c["depth_m"];witnesses[kind]=dict(time_s=t,**c)
        if t>=plan["duration_s"]-1:
            speeds=[]
            for i in range(2):
                adr=model.joint(f"piece_{i}_free").dofadr[0]
                speeds.append([float(np.linalg.norm(data.qvel[adr:adr+3])),float(np.linalg.norm(data.qvel[adr+3:adr+6]))])
            tail.append(speeds)
            tail_robot_support+=len(robot_support_contacts(model,data))
            bounds=[]
            for i,part in enumerate(family.parts):
                p=body_pose(data,model.body(f"piece_{i}").id)
                vertices=part.mesh.vertices@p[:3,:3].T+p[:3,3]
                bounds.append(np.array([vertices.min(0),vertices.max(0)]))
            tail_separation=min(tail_separation,float(np.maximum(bounds[0][0]-bounds[1][1],bounds[1][0]-bounds[0][1]).max()))
        if step%stride==0:
            frames.append(data.qpos.copy());vframes.append(data.qvel.copy());eframes.append(data.eq_active.copy());tframes.append(t)
            phase_frames.append(plan["rows"][idx]["phase"])
        if step<steps:
            mujoco.mj_step(model,data);mujoco.mj_forward(model,data)
        if not np.isfinite(data.qpos).all():raise RuntimeError("Nonfinite physics state")
        if step and step%round(5/dt)==0:print(family.family,"t",round(t,2),"depths",depths,"tracking",max_p,max_a,flush=True)
    final=[body_pose(data,model.body(f"piece_{i}").id) for i in range(2)]
    bottoms=[float((part.mesh.vertices@p[:3,:3].T+p[:3,3])[:,2].min()) for part,p in zip(family.parts,final)]
    from types import SimpleNamespace
    from .collision import ClawCollision
    gap=ClawCollision(SimpleNamespace(bodies=family.parts)).clearance(final)
    tail=np.asarray(tail);speeds=tail.max(axis=0)
    warnings={mujoco.mjtWarning(i).name:int(w.number) for i,w in enumerate(data.warning) if w.number}
    drive_limits=[(int(model.jnt_dofadr[j]),float(max(abs(model.jnt_actfrcrange[j])))) for j in range(model.njnt)
                  if model.jnt_actfrclimited[j] and model.jnt_dofadr[j]<16]
    checks=dict(released=bool(released and not data.eq_active[grasp_ids].any()),separated=gap>.04,
        on_table=all(abs(b)<.002 for b in bottoms),settled=bool((speeds[:,0]<.001).all() and (speeds[:,1]<.02).all()),
        held_tracking=bool(max_p<.004 and max_a<.04),pair_contact=depths.get("pair",0)<.0003,
        table_contact=depths.get("part_table",0)<.0005,
        robot_collision=all(depths.get(k,0)<.0005 for k in ("robot_self","robot_part","robot_table")),
        no_simulator_warning=not warnings,
        no_robot_support_in_final_second=tail_robot_support==0,
        total_drive_within_original_limits=all(total_drive[i]<=limit+1e-6 for i,limit in drive_limits))
    if objective=="separate":
        for key in ("released","on_table","no_robot_support_in_final_second"):checks.pop(key)
        checks["separated"]=bool(gap>.02 and tail_separation>.02)
    np.savez_compressed(output/"states.npz",qpos=np.asarray(frames),qvel=np.asarray(vframes),eq_active=np.asarray(eframes),time_s=tframes,phase=phase_frames)
    report=dict(family=family.family,objective=objective,passed=all(checks.values()),checks=checks,engine="MuJoCo",engine_version=mujoco.__version__,dt_s=dt,contact_time_constant_s=contact_time(family.family),
        plan_sha256=sha(plan_path),duration_s=plan["duration_s"],frames=len(frames),fps=20,release_time_s=plan["release_time_s"],release_times_s=[None if np.isinf(t) else float(t) for t in release_times],
        pregrasp=True,grasp="ideal gripper-to-part weld retained during separated hold" if objective=="separate" else "ideal gripper-to-part weld until release",robot_gravity_compensation=True,
        gravity_compensation_inside_actuator_limits=bool(model.jnt_actgravcomp[:16].all()),
        original_joint_force_limits_retained=True,pose_writes_after_initialization=False,final_active_grasps=data.eq_active[grasp_ids].tolist(),
        max_held_position_error_m=max_p,max_held_rotation_error_rad=max_a,max_joint_error_rad=max_q,
        max_weld_position_error_m=max_weld_p,max_weld_rotation_error_rad=max_weld_a,
        max_contact_depth_m=depths,contact_witnesses=witnesses,peak_generalized_actuator_force=torque.tolist(),peak_actuator_output=force.tolist(),
        peak_actuation_plus_gravity_compensation=total_drive.tolist(),drive_limits=drive_limits,
        final_poses=[p.tolist() for p in final],final_bottom_z_m=bottoms,final_pair_clearance_m=gap,
        maximum_last_second_speed=speeds.tolist(),minimum_last_second_aabb_separation_m=tail_separation,warnings=warnings)
    report["final_second_robot_support_contact_samples"]=tail_robot_support
    save(output/"report.json",report)
    print(json.dumps(report,indent=2),flush=True)
    return report


if __name__=="__main__":
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument("--family");p.add_argument("--settings");p.add_argument("--output",required=True)
    p.add_argument("--execute");p.add_argument("--dt",type=float,default=.0005)
    p.add_argument("--objective",choices=("separate","disassemble_release"))
    args=p.parse_args()
    result=execute(args.execute,args.output,args.dt) if args.execute else build_plan(args.family,args.settings,args.output,objective=args.objective)
    if not result["passed"]:raise SystemExit(1)
