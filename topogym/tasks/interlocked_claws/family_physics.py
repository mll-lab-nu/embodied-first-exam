"""Force-driven contact and settling checks for explicit convex compounds.

The fixture tests use MuJoCo and no robot. They cannot qualify a bimanual run;
the robot runner separately keeps the original ALOHA actuator force limits.
"""
import argparse
import hashlib
import json
from pathlib import Path
import xml.etree.ElementTree as ET

import mujoco
import numpy as np
from scipy.spatial.transform import Rotation

from .family_models import FamilyModel, COLORS, FAMILIES, pose, rot

ROOT=Path(__file__).resolve().parents[3]


def values(numbers):
    return " ".join(f"{float(v):.15g}" for v in np.asarray(numbers).ravel())


def quat(matrix):
    return Rotation.from_matrix(np.asarray(matrix)).as_quat()[[3,0,1,2]]


def save(path, value):
    Path(path).write_text(json.dumps(value,indent=2,allow_nan=False)+"\n")


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def contact_time(family):
    return .0005 if family.startswith("orthogonal_gate") else .001


def base_xml(dt,contact_time_s=.001):
    root=ET.Element("mujoco",model="claw_family_physics")
    ET.SubElement(root,"compiler",angle="radian",autolimits="true")
    ET.SubElement(root,"option",timestep=str(dt),integrator="implicitfast",solver="Newton",
                  iterations="100",tolerance="1e-10",cone="elliptic",impratio="10",gravity="0 0 -9.81")
    default=ET.SubElement(root,"default")
    ET.SubElement(default,"geom",friction=".5 .005 .0001",condim="4",solref=f"{contact_time_s} 1",
                  solimp=".99 .999 .001 .5 2",margin="0",gap="0")
    world=ET.SubElement(root,"worldbody")
    ET.SubElement(world,"geom",name="table",type="plane",size="1.5 1.5 .05",rgba=".36 .42 .43 1",
                  friction=".5 .005 .0001",condim="4",solref=f"{contact_time_s} 1",solimp=".99 .999 .001 .5 2")
    return root


def add_part(root, model, index, transform, fixed=False):
    part=model.parts[index]
    world=root.find("worldbody")
    body=ET.SubElement(world,"body",name=part.name,pos=values(transform[:3,3]),quat=values(quat(transform[:3,:3])))
    if not fixed:
        ET.SubElement(body,"freejoint",name=part.name+"_free")
    props=part.mesh.mass_properties
    I=props.inertia
    ET.SubElement(body,"inertial",pos=values(props.center_mass),mass=str(props.mass),
        fullinertia=values([I[0,0],I[1,1],I[2,2],I[0,1],I[0,2],I[1,2]]))
    for j,item in enumerate(part.boxes):
        t=np.asarray(item["pose"])
        ET.SubElement(body,"geom",name=f"{part.name}_box_{j}",type="box",size=values(np.asarray(item["size"])/2),
                      pos=values(t[:3,3]),quat=values(quat(t[:3,:3])),rgba=values(COLORS[index]),
                      mass="0",friction=".5 .005 .0001",condim="4",solref=f"{contact_time(model.family)} 1",solimp=".99 .999 .001 .5 2")
    return body


def body_pose(data, body_id):
    return pose(data.xpos[body_id],data.xmat[body_id].reshape(3,3))


def contact_metrics(model,data):
    pair_depth=table_depth=force=0.
    pair_contacts=0
    for c in data.contact:
        names=[model.body(model.geom_bodyid[g]).name for g in (c.geom1,c.geom2)]
        penetration=max(0.,-float(c.dist))
        if set(names)=={"piece_0","piece_1"}:
            pair_depth=max(pair_depth,penetration);pair_contacts+=1
        elif any(n.startswith("piece_") for n in names):
            table_depth=max(table_depth,penetration)
    for i in range(data.ncon):
        wrench=np.zeros(6);mujoco.mj_contactForce(model,data,i,wrench)
        force=max(force,float(np.linalg.norm(wrench[:3])))
    return dict(pair_depth_m=pair_depth,table_depth_m=table_depth,contact_force_n=force,pair_contacts=pair_contacts)


def _run_drop(family,index,dt,output):
    part=family.parts[index]
    # Axial handles are not feet. Test the balanced claws lying on their
    # crowns, which is their intended unconstrained resting orientation.
    euler=[89.,-1.5,9.] if family.family=="helical_claws_balanced_v2" else [1.0,-1.5,9.]
    rotation=rot("xyz",euler).as_matrix()
    duration=20. if family.family=="helical_claws_balanced_v2" else 5.
    bottom=float((part.mesh.vertices@rotation.T)[:,2].min())
    root=base_xml(dt,contact_time(family.family))
    add_part(root,family,index,pose([0,0,-bottom+.002],rotation))
    xml=ET.tostring(root,encoding="unicode")
    (output/f"drop_{index}.xml").write_text(xml)
    model=mujoco.MjModel.from_xml_string(xml);data=mujoco.MjData(model)
    mujoco.mj_forward(model,data)
    rows=[];max_depth=max_force=0.;tail=[]
    for step in range(round(duration/dt)+1):
        metrics=contact_metrics(model,data)
        max_depth=max(max_depth,metrics["table_depth_m"]);max_force=max(max_force,metrics["contact_force_n"])
        if data.time>=duration-.5:
            tail.append(data.qvel.copy())
        if step%round(.05/dt)==0:
            rows.append(dict(time_s=float(data.time),qpos=data.qpos.tolist(),qvel=data.qvel.tolist()))
        if step<round(duration/dt):
            mujoco.mj_step(model,data);mujoco.mj_forward(model,data)
    speed=float(max(np.linalg.norm(v[:3]) for v in tail))
    angular=float(max(np.linalg.norm(v[3:]) for v in tail))
    passed=bool(np.isfinite(data.qpos).all() and speed<.001 and angular<.02 and max_depth<.0005)
    save(output/f"drop_{index}_states.json",rows)
    return dict(name=f"drop_{index}",passed=passed,max_penetration_m=max_depth,max_contact_force_n=max_force,
                initial_rotation_xyz_deg=euler,initial_bottom_clearance_m=.002,
                maximum_tail_speed_m_s=speed,maximum_tail_angular_speed_rad_s=angular,final_qpos=data.qpos.tolist(),
                pose_writes_after_initialization=False,duration_s=duration)


def _run_drive(family,dt,output,negative=None):
    root=base_xml(dt,contact_time(family.family))
    base=pose([0,0,.25])
    initial=negative.start if negative else family.initial[1]
    add_part(root,family,0,base,fixed=True)
    add_part(root,family,1,base@initial)
    name=negative.name if negative else "complete_relative_solution"
    xml=ET.tostring(root,encoding="unicode")
    (output/f"{name}.xml").write_text(xml)
    model=mujoco.MjModel.from_xml_string(xml);data=mujoco.MjData(model)
    body=model.body("piece_1").id
    mujoco.mj_forward(model,data)
    mass=float(model.body_mass[body]);inertia=family.parts[1].mesh.moment_inertia
    com=family.parts[1].mesh.center_mass
    rows=[];max_pair=max_force=max_p=max_a=0.;contact_steps=0;force_peak=torque_peak=0.
    duration=(negative.duration if negative else family.duration)+1.5
    previous_p=data.xipos[body].copy();previous_r=data.xmat[body].reshape(3,3).copy()
    previous_target=base@initial
    previous_com=previous_target[:3,3]+previous_target[:3,:3]@com
    for step in range(round(duration/dt)+1):
        t=float(data.time)
        target=(negative.at(max(0.,t-.5)/negative.duration) if negative else family.relative_pose(max(0.,t-.5))[0])
        target=base@target
        R=data.xmat[body].reshape(3,3)
        target_com=target[:3,3]+target[:3,:3]@com
        actual=data.xipos[body].copy()
        v=(actual-previous_p)/dt if step else np.zeros(3)
        w=Rotation.from_matrix(R@previous_r.T).as_rotvec()/dt if step else np.zeros(3)
        vd=(target_com-previous_com)/dt if step else np.zeros(3)
        wd=Rotation.from_matrix(target[:3,:3]@previous_target[:3,:3].T).as_rotvec()/dt if step else np.zeros(3)
        angle=Rotation.from_matrix(target[:3,:3]@R.T).as_rotvec()
        F=mass*(50**2*(target_com-actual)+100*(vd-v))+[0,0,mass*9.81]
        I=R@inertia@R.T
        # The C0 negative control tests a held orientation, not a compliant
        # attempt that can pass by passively rotating against the gate.
        locked_orientation=negative is not None and family.family.startswith("orthogonal_gate")
        frequency=300. if locked_orientation else 60.
        torque_limit=2. if locked_orientation else .7
        torque=I@(frequency**2*angle+2*frequency*(wd-w))+np.cross(w,I@w)
        F*=min(1.,8./max(np.linalg.norm(F),1e-12))
        torque*=min(1.,torque_limit/max(np.linalg.norm(torque),1e-12))
        data.xfrc_applied[body]=np.r_[F,torque]
        force_peak=max(force_peak,float(np.linalg.norm(F)));torque_peak=max(torque_peak,float(np.linalg.norm(torque)))
        metrics=contact_metrics(model,data)
        max_pair=max(max_pair,metrics["pair_depth_m"]);max_force=max(max_force,metrics["contact_force_n"])
        contact_steps+=bool(metrics["pair_contacts"])
        pe=float(np.linalg.norm(target[:3,3]-data.xpos[body]));ae=float(np.linalg.norm(angle))
        max_p=max(max_p,pe);max_a=max(max_a,ae)
        if step%round(.05/dt)==0:
            rows.append(dict(time_s=t,qpos=data.qpos.tolist(),qvel=data.qvel.tolist(),
                position_error_m=pe,rotation_error_rad=ae,force_n=F.tolist(),torque_nm=torque.tolist()))
        previous_p=actual;previous_r=R.copy();previous_target=target.copy();previous_com=target_com.copy()
        if step<round(duration/dt):
            mujoco.mj_step(model,data);mujoco.mj_forward(model,data)
        if not np.isfinite(data.qpos).all():
            break
    blocked=bool(contact_steps>0 and (pe>.005 or ae>.05))
    passed=bool(np.isfinite(data.qpos).all() and max_pair<.0003 and
                (blocked if negative else max_p<.003 and max_a<.03))
    save(output/f"{name}_states.json",rows)
    return dict(name=name,passed=passed,negative_control=negative is not None,blocked=blocked if negative else None,
        final_position_error_m=pe,final_rotation_error_rad=ae,max_position_error_m=max_p,max_rotation_error_rad=max_a,
        max_pair_penetration_m=max_pair,max_contact_force_n=max_force,pair_contact_steps=contact_steps,
        peak_external_force_n=force_peak,peak_external_torque_nm=torque_peak,
        orientation_control_frequency_rad_s=frequency,torque_limit_nm=torque_limit,
        final_qpos=data.qpos.tolist(),pose_writes_after_initialization=False,duration_s=duration)


def bench(family, output, dt=.002):
    if dt not in (.002,.001,.0005,.00025,.000125):
        raise ValueError("Use a declared refinement timestep")
    output=Path(output);output.mkdir(parents=True,exist_ok=False)
    model=FamilyModel(family)
    model.save(output/"assets")
    results=[]
    for i in range(2):
        results.append(_run_drop(model,i,dt,output));print(family,dt,results[-1],flush=True)
    results.append(_run_drive(model,dt,output));print(family,dt,results[-1],flush=True)
    for negative in model.negative_paths():
        results.append(_run_drive(model,dt,output,negative));print(family,dt,results[-1],flush=True)
    report=dict(family=family,passed=all(r["passed"] for r in results),engine="MuJoCo",engine_version=mujoco.__version__,
        dt_s=dt,contact_time_constant_s=contact_time(family),checks=results,scope="force-driven fixture and independent free settling; no robot execution",
        gravity_m_s2=[0,0,-9.81],force_limit_n=8.,positive_torque_limit_nm=.7,
        negative_torque_limit_nm=2. if family.startswith("orthogonal_gate") else .7,
        collision="explicit oriented boxes; identical solid union to visual mesh",pose_writes_after_initialization=False,
        thresholds=dict(pair_penetration_m=.0003,drop_penetration_m=.0005,tracking_m=.003,tracking_rad=.03,
                        tail_speed_m_s=.001,tail_angular_speed_rad_s=.02))
    save(output/"report.json",report)
    return report


if __name__=="__main__":
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument("--family",required=True,choices=FAMILIES)
    p.add_argument("--output",required=True,type=Path)
    p.add_argument("--dt",type=float,default=.002)
    args=p.parse_args()
    if not bench(args.family,args.output,args.dt)["passed"]:
        raise SystemExit(1)
