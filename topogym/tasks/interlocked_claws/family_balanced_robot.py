"""Sequential table release for compact, congruent orthogonal windows.

Place the key while holding the frame, release and withdraw the key hand back
through the aperture, and only then carry the frame to its own resting place.
This keeps the small closed frame from being carried across a threaded arm.
"""
import json
from pathlib import Path
import xml.etree.ElementTree as ET

import mujoco
import numpy as np
from omegaconf import OmegaConf
from scipy.spatial.transform import Rotation

from .family_models import FamilyModel,Segment,pose,rot
from .family_robot import assembly_poses,xml_scene,set_initial,contacts
from .family_physics import save
from .variants import _base_config
from topogym.tasks.cast_coil.robot_plan import Kinematics


def build_plan(settings_path,output,sample_dt=.05):
    output=Path(output);output.mkdir(parents=True,exist_ok=False)
    settings=json.loads(Path(settings_path).read_text())
    family=FamilyModel("orthogonal_gate_balanced_v2");family.save(output/"assets")
    schedule=[]
    def append(t,parts,held,phase,tools=None):
        tools=tools or [p@part.grasp for p,part in zip(parts,family.parts)]
        schedule.append(dict(time_s=float(t),poses=[p.copy() for p in parts],
                             held_parts=list(held),phase=phase,tools=tools))
    duration=family.duration+1.
    for t in np.arange(0,duration+sample_dt/2,sample_dt):
        parts,phase=assembly_poses(family,max(0,t-1),settings)
        append(t,parts,[True,True],"pregrasp_hold" if t<1 else phase)
    last=schedule[-1]["poses"]
    relative=family.relative_pose(family.duration)[0]
    # A common rigid transform lowers the extracted key to table height while
    # preserving its clearance to the held frame and the second aperture.
    key_rotation=rot("z",settings.get("placement_yaw",60))*rot("y",45)*rot("x",90)
    bottom=float(key_rotation.apply(family.parts[1].mesh.vertices)[:,2].min())
    key=pose([*settings.get("key_placement_xy",[-.16,-.05]),-bottom+.004],key_rotation)
    cage=key@np.linalg.inv(relative)
    move=Segment("place_key_with_frame",7.,last[0],cage)
    for local in np.arange(sample_dt,7+sample_dt/2,sample_dt):
        root=move.at(local/7);append(duration+local,[root,root@relative],[True,True],move.name)
    duration+=7;key_release=duration
    last=[cage,key];tools=[p@part.grasp for p,part in zip(last,family.parts)]
    left_retreat=tools[1].copy();left_retreat[:3,3]-=.11*left_retreat[:3,0]
    move=Segment("release_key_and_withdraw_left",4.,tools[1],left_retreat)
    for local in np.arange(sample_dt,4+sample_dt/2,sample_dt):
        append(duration+local,last,[True,False],move.name,[tools[0],move.at(local/4)])
    duration+=4
    frame_rotation=rot("x",90)
    bottom=float(frame_rotation.apply(family.parts[0].mesh.vertices)[:,2].min())
    frame_placed=pose([*settings.get("frame_placement_xy",[.28,-.24]),-bottom+.004],frame_rotation)
    raised=frame_placed.copy();raised[2,3]=max(cage[2,3],frame_placed[2,3]+.18)
    # An optional measured settling prediction is used only for planning robot
    # clearance after the key is released. The executor does not write this pose
    # into the simulator; it independently integrates both free bodies.
    settled_key=np.asarray(settings.get("settled_key_pose",key))
    for phase,length,end in [("carry_frame",10.,raised),("lower_frame",6.,frame_placed)]:
        move=Segment(phase,length,last[0],end)
        for local in np.arange(sample_dt,length+sample_dt/2,sample_dt):
            frame=move.at(local/length)
            append(duration+local,[frame,settled_key],[True,False],phase,[frame@family.parts[0].grasp,left_retreat])
        duration+=length;last=[end,settled_key]
    frame_release=duration
    right_start=frame_placed@family.parts[0].grasp
    right_retreat=right_start.copy();right_retreat[:3,3]-=.06*right_retreat[:3,0];right_retreat[2,3]+=.04
    move=Segment("release_frame_and_retreat",4.,right_start,right_retreat)
    for local in np.arange(sample_dt,8+sample_dt/2,sample_dt):
        append(duration+local,last,[False,False],move.name if local<4 else "free_settle",
               [move.at(min(1,local/4)),left_retreat])
    duration+=8
    releases=[frame_release,key_release]
    k=Kinematics(OmegaConf.create(_base_config()).robot_control);k.q=np.asarray(settings["q"][0]).copy()
    xml=ET.tostring(xml_scene(family,schedule[0]["poses"],.00025,output/"assets"),encoding="unicode")
    (output/"scene.xml").write_text(xml);model=mujoco.MjModel.from_xml_string(xml);data=mujoco.MjData(model)
    rows=[];bad=[];max_p=max_a=max_step=0.
    for sample in schedule:
        previous=k.q.copy();t=sample["time_s"]
        for i,part in enumerate(family.parts):
            target=sample["tools"][i]
            pe,ae=k.solve(part.side,target[:3,3],Rotation.from_matrix(target[:3,:3]))
            max_p=max(max_p,pe);max_a=max(max_a,ae)
            if pe>1e-5 or ae>1e-4:
                save(output/"failure.json",dict(time_s=t,phase=sample["phase"],side=part.side,position_m=pe,angle_rad=ae))
                save(output/"partial_diagnostics.json",dict(rows=rows,collision_failures=bad))
                raise RuntimeError(f"Unreachable at {t} {sample['phase']}: {part.side} {pe} {ae}")
            fraction=1 if sample["held_parts"][i] else max(0,1-(t-releases[i])/.6)
            for name in ("left_finger","right_finger"):
                k.q[k.model.joint(f"{part.side}/{name}").qposadr[0]]=fraction*part.finger+(1-fraction)*.037
        if rows:max_step=max(max_step,float(np.max(np.abs(k.q-previous))))
        set_initial(model,data,k.q,sample["poses"])
        invalid=[c for c in contacts(model,data,family) if c["kind"]!="grasp" and c["depth_m"]>.0001]
        if invalid:bad.append(dict(time_s=t,phase=sample["phase"],contacts=invalid))
        rows.append(dict(time_s=t,phase=sample["phase"],q=k.q.tolist(),
                         poses=[p.tolist() for p in sample["poses"]],held_parts=sample["held_parts"]))
    report=dict(family=family.family,scope="complete sequential-release IK with pregrasp",sample_dt_s=sample_dt,
                max_position_error_m=max_p,max_angle_error_rad=max_a,max_joint_step_rad=max_step,
                collision_frames=len(bad),collision_failures=bad,passed=not bad)
    save(output/"plan.json",dict(family=family.family,settings=settings,release_time_s=frame_release,
                                release_times_s=releases,duration_s=duration,rows=rows,report=report))
    save(output/"report.json",report)
    print(json.dumps({k:v for k,v in report.items() if k!="collision_failures"},indent=2),flush=True)
    return report
