"""Execute and record inverse-designed Keyhole instances without altering the seed.

Each physical run starts pregrasped, uses bounded joint actuation, and enables
grasp-retention welds only after simultaneous bilateral finger contact. Saved
physical states are independently audited before synchronous camera rendering.
"""
from __future__ import annotations
import argparse
from contextlib import ExitStack
import json
from pathlib import Path
import time
from types import SimpleNamespace

from hydra import compose,initialize_config_dir
import numpy as np
from omegaconf import OmegaConf
from scipy.spatial.transform import Rotation
from trimesh.visual.material import PBRMaterial
from trimesh.visual.texture import TextureVisuals

from .inverse_variants import OUTPUT,VARIANTS,geometry_from_record,save,sha
from .geometry import KeyholeBody,write_body
from .collision import CompoundCollision
from .physics_probe import array
from .robot_motion import ROOT,PAD_CENTER,Kinematics,RobotClearance


def load_instance(folder):
    folder=Path(folder).resolve()
    record=json.loads((folder/"geometry.json").read_text())
    motion=json.loads((folder/"robot_motion.json").read_text())
    proof=json.loads((folder/"certificate.json").read_text())
    source=json.loads((folder/"ik_proposal.json").read_text())
    if not (proof.get("passed") and motion["report"].get("sampled_robot_scene_clearance_passed")
            and proof["geometry_sha256"]==sha(folder/"geometry.json")
            and proof["ik_input_sha256"]==sha(folder/"ik_proposal.json")
            and proof["proposal_sha256"]==sha(folder/"proposal.json")
            and motion["report"]["certificate_sha256"]==sha(folder/"certificate.json")
            and motion["frames"]==source["frames"] and len(proof["segments"])==len(motion["frames"])-1
            and all(s["passed"] and s["continuous_gap_lower_bound_m"]>=.00015 for s in proof["segments"])):
        raise ValueError("Incomplete or stale inverse-variant evidence")
    for name,digest in proof["source_fingerprints"].items():
        if sha(Path(__file__).with_name(name))!=digest:raise ValueError(f"Certificate source changed: {name}")
    meshes,cells=geometry_from_record(record)
    return record,motion,proof,meshes,cells


def configuration(render=False):
    with initialize_config_dir(config_dir=str(ROOT/"configs"),version_base="1.3"):
        cfg=compose(config_name="cast_keyhole_aloha",overrides=["env.renderer.type="+("nyx" if render else "rasterizer"),"env.renderer.spp=16"])
    if not render:cfg.env.cameras=OmegaConf.create({})
    return cfg


def build_scene(cfg,folder,record,meshes,cells,initial):
    import genesis as gs
    from topogym.world import StandardTabletopSceneBuilder
    folder=Path(folder);folder.mkdir(parents=True,exist_ok=True)
    builder=StandardTabletopSceneBuilder(cfg.env,cfg.robot_control,
        rigid_options=gs.options.RigidOptions(enable_collision=True,enable_self_collision=True,
            iterations=100,max_collision_pairs=16384,constraint_timeconst=.001))
    base=builder.create(show_viewer=False,include_robot=True,robot_material=gs.materials.Rigid(gravity_compensation=1.))
    mount=np.asarray(cfg.env.robot_mount.pos);bodies={};records=[];audits=[]
    for name,mesh,parts,color in zip(("keyhole_gold","keyhole_silver"),meshes,cells,((.61,.43,.12,1.),(.56,.61,.66,1.))):
        visual=mesh.copy();visual.visual=TextureVisuals(uv=np.zeros((len(visual.vertices),2)),
            material=PBRMaterial(baseColorFactor=color,metallicFactor=.8,roughnessFactor=.3))
        b=KeyholeBody(name,visual,parts,color,[]);item=write_body(folder/name,b,record["density_kg_m3"])
        records.append(item);pose=initial["bodies"][name];r=Rotation.from_quat(pose["quat"])
        entity=base.scene.add_entity(gs.morphs.URDF(file=str((folder/name/f"{name}.urdf").resolve()),
            pos=mount+np.array(pose["pos"])+r.apply(item["origin_m"]),quat=r.as_quat()[[3,0,1,2]],
            fixed=False,align=False,convexify=True,decimate=False,merge_fixed_links=False),
            material=gs.materials.Rigid(friction=.35),surface=gs.surfaces.Default(smooth=False),name=name)
        bodies[name]=base.manifest.add(name,entity)
    builder.finalize(base)
    for item,parts in zip(records,cells):
        entity=bodies[item["name"]]
        if entity.n_dofs!=6 or entity.n_links!=1 or len(entity.geoms)!=len(parts):
            raise ValueError("Unexpected loaded rigid compound")
        bounds_error=0.;volume_error=0.
        for geom,expected in zip(entity.geoms,parts):
            if not geom.is_convex:raise ValueError("Collision cell was not loaded as convex")
            t=np.eye(4);t[:3,:3]=Rotation.from_quat(np.asarray(geom.init_quat)[[1,2,3,0]]).as_matrix();t[:3,3]=geom.init_pos
            loaded=geom.mesh.trimesh.copy().apply_transform(t)
            bounds_error=max(bounds_error,float(np.abs(loaded.bounds+item["origin_m"]-expected.bounds).max()))
            volume_error+=abs(loaded.volume-expected.volume)
        if bounds_error>1e-7 or volume_error>sum(p.volume for p in parts)*1e-5:
            raise ValueError("Runtime collision solids differ from certified geometry")
        audits.append(dict(name=item["name"],passed=True,convex_cells=len(parts),bounds_error_m=bounds_error,volume_error_m3=volume_error))
    save(folder/"body_records.json",records);save(folder/"loaded_collision_audit.json",audits)
    return SimpleNamespace(scene=base.scene,cameras=base.cameras,manifest=base.manifest,bodies=bodies,
                           records=records,mount=mount,loaded_audit=audits)


def set_objects(task,frame):
    for item in task.records:
        pose=frame["bodies"][item["name"]];r=Rotation.from_quat(pose["quat"])
        body=task.bodies[item["name"]]
        body.set_pos(task.mount+np.array(pose["pos"])+r.apply(item["origin_m"]))
        body.set_quat(r.as_quat()[[3,0,1,2]])


def actual_objects(task):
    poses=[];result={}
    for item in task.records:
        body=task.bodies[item["name"]];r=Rotation.from_quat(array(body.get_quat())[[1,2,3,0]])
        p=array(body.get_pos())-task.mount-r.apply(item["origin_m"])
        poses.append((r.as_matrix(),p));result[item["name"]]=dict(pos=p.tolist(),quat=r.as_quat().tolist())
    return poses,result


def execute(folder):
    folder=Path(folder).resolve();record,motion,proof,meshes,cells=load_instance(folder)
    output=folder/"physics"
    if (output/"report.json").exists():raise ValueError("Preserve existing physical evidence; use a new variant output for another attempt")
    output.mkdir(parents=True,exist_ok=True);cfg=configuration()
    OmegaConf.save(cfg,output/"config.yaml",resolve=True)
    import genesis as gs
    from topogym.robot import initialize_robot_controller
    gs.init(backend=gs.cuda,precision="64",logging_level="warning",seed=0)
    task=build_scene(cfg,output/"assets",record,meshes,cells,motion["frames"][0])
    controller=initialize_robot_controller(scene=task.scene,manifest=task.manifest,robot_cfg=cfg.robot_control,settle_steps=0)
    robot=controller.robot;solver=task.scene.sim.rigid_solver
    q0=np.array(motion["frames"][0]["qpos"]);q0[[6,7,14,15]]=.0127
    robot.set_qpos(q0);set_objects(task,motion["frames"][0])
    armids=np.array(controller.left.arm_dofs+controller.right.arm_dofs)
    fingers=[controller.left.dofs_idx[6],controller.right.dofs_idx[6]]
    robot.set_dofs_kp(np.full(12,100000.),armids);robot.set_dofs_kv(np.full(12,2000.),armids)
    robot.set_dofs_kp(np.full(2,2000.),fingers);robot.set_dofs_kv(np.full(2,124.),fingers)
    robot.control_dofs_position([.0105,.0105],fingers)
    dt=float(cfg.env.sim.dt);fps=motion["fps"];duration=(len(motion["frames"])-1)/fps
    qarray=np.array([f["qpos"] for f in motion["frames"]]);collision=CompoundCollision(*cells)
    attached={};aborted=None;trace=[];maxpen=0.;mingap=float("inf");maxerror=0.;started=time.monotonic()
    initial_poses,initial_bodies=actual_objects(task)
    trace.append(dict(time_s=0.,physics_step=0,qpos=q0.tolist(),bodies=initial_bodies,stage="pregrasp",sat_gap_m=collision.gap(
        initial_poses[0][0].T@initial_poses[1][0],initial_poses[0][0].T@(initial_poses[1][1]-initial_poses[0][1]))))
    total=int(np.ceil((duration+1.5)/dt))
    for step in range(total):
        now=step*dt;index=np.clip((now-.5)*fps,0,len(qarray)-1);i=min(int(index),len(qarray)-2);u=index-i
        q=(1-u)*qarray[i]+u*qarray[i+1]
        v=(qarray[i+1]-qarray[i])*fps if .5<now<duration+.5 else np.zeros(16)
        robot.control_dofs_position_velocity(q[armids],v[armids],armids);task.scene.step()
        for side,name in zip(("left","right"),("keyhole_gold","keyhole_silver")):
            if side in attached:continue
            finger_links={robot.get_link(f"{side}/{f}_finger_link").idx for f in ("left","right")}
            contacts=robot.get_contacts(with_entity=task.bodies[name])
            touched=set(array(contacts["link_a"]).ravel().tolist())|set(array(contacts["link_b"]).ravel().tolist())
            if finger_links.issubset(touched):
                links=(controller.arms[side].ee_link.idx,task.bodies[name].base_link_idx)
                solver.add_weld_constraint(*links)
                attached[side]=dict(step=step+1,time_s=(step+1)*dt,simultaneous_finger_contacts=sorted(finger_links),links=list(links))
                print(f"{record['id']} contact-gated grasp {side} at {(step+1)*dt:.3f}s",flush=True)
        if now>.12 and len(attached)!=2:aborted="Missing simultaneous bilateral finger contact";break
        depth=array(solver.collider.get_contacts()["penetration"])
        if depth.size:maxpen=max(maxpen,float(depth.max()))
        if (step+1)%10==0 or step==total-1:
            actual_q=array(robot.get_qpos());poses,bodies=actual_objects(task)
            if not np.isfinite(actual_q).all():aborted="Nonfinite robot state";break
            maxerror=max(maxerror,float(np.abs(actual_q[armids]-q[armids]).max()))
            (rg,tg),(rs,ts)=poses;gap=collision.gap(rg.T@rs,rg.T@(ts-tg));mingap=min(mingap,gap)
            stage="contact_grasp_hold" if now<.5 else ("separated_hold" if now>duration+.5 else motion["frames"][i]["stage"])
            trace.append(dict(time_s=(step+1)*dt,physics_step=step+1,qpos=actual_q.tolist(),bodies=bodies,stage=stage,sat_gap_m=gap))
            if gap<-.0002 or maxpen>.001:aborted=f"Contact limit exceeded: gap={gap}, penetration={maxpen}";break
        if (step+1)%2000==0:print(f"{record['id']} {now+dt:.1f}/{duration+1.5:.1f}s; wall {time.monotonic()-started:.1f}s",flush=True)
    poses,bodies=actual_objects(task);(rg,tg),(rs,ts)=poses;gap=float(collision.gap(rg.T@rs,rg.T@(ts-tg)))
    passed=aborted is None and len(attached)==2 and gap>.02 and mingap>0 and maxpen<.001
    report=dict(passed=bool(passed),variant_id=record["id"],aborted=aborted,physics_steps=step+1,simulated_seconds=(step+1)*dt,
        dt=dt,precision_bits=64,substeps=4,attached=attached,pregrasp_start=True,assisted_weld_grasp=True,
        grasp_assistance_active_at_end=True,friction_only_grasp_verified=False,pose_writes_after_reset=False,
        minimum_sampled_gap_m=mingap,final_separation_lower_bound_m=gap,max_contact_penetration_m=maxpen,
        max_sampled_joint_tracking_error_rad=maxerror,arm_kp=100000.,arm_kv=2000.,
        joint_force_limits=OmegaConf.to_container(cfg.robot_control.controller.force_limit),
        geometry_sha256=sha(folder/"geometry.json"),motion_sha256=sha(folder/"robot_motion.json"),
        runner_sha256=sha(Path(__file__)),loaded_collision_audit=task.loaded_audit,
        robot_execution_verified=bool(passed),formal_demo_qualified=False)
    save(output/"trajectory.json",trace);save(output/"report.json",report)
    print(json.dumps(report,indent=2),flush=True)
    return report


def audit(folder):
    folder=Path(folder).resolve();record,motion,proof,meshes,cells=load_instance(folder)
    output=folder/"physics";report=json.loads((output/"report.json").read_text())
    if not report["passed"] or report["pose_writes_after_reset"]:raise ValueError("A passing continuous physical run is required")
    if report["geometry_sha256"]!=sha(folder/"geometry.json") or report["motion_sha256"]!=sha(folder/"robot_motion.json"):
        raise ValueError("Physical run used different geometry or control")
    hashes={n:sha(output/n) for n in ("report.json","trajectory.json")}
    trace=json.loads((output/"trajectory.json").read_text());kin=Kinematics(configuration().robot_control)
    check=RobotClearance(kin,cells);collision=CompoundCollision(*cells);errors=[];mingap=float("inf");tailv=tailw=0.;previous=None
    for i,frame in enumerate(trace):
        kin.q=np.array(frame["qpos"])
        bodies=[(Rotation.from_quat(frame["bodies"][n]["quat"]).as_matrix(),np.array(frame["bodies"][n]["pos"])) for n in ("keyhole_gold","keyhole_silver")]
        bad=check.violations(bodies)
        if bad:errors.append(dict(frame=i,violations=bad[:5]))
        (rg,tg),(rs,ts)=bodies;gap=collision.gap(rg.T@rs,rg.T@(ts-tg));mingap=min(mingap,gap)
        if gap<=0:errors.append(dict(frame=i,interpiece_gap_m=gap))
        if previous and frame["time_s"]>trace[-1]["time_s"]-.5:
            elapsed=frame["time_s"]-previous[0]
            for (r,t),(pr,pt) in zip(bodies,previous[1]):
                tailv=max(tailv,float(np.linalg.norm(t-pt)/elapsed))
                tailw=max(tailw,float(Rotation.from_matrix(r@pr.T).magnitude()/elapsed))
        previous=(frame["time_s"],bodies)
        if i%300==0:print(f"{record['id']} audit {i+1}/{len(trace)}",flush=True)
    if gap<.02 or tailv>.001 or tailw>.01:errors.append("Final separation/rest failed")
    if any(sha(output/n)!=h for n,h in hashes.items()):errors.append("Inputs changed during audit")
    result=dict(passed=not errors,errors=errors,states_checked=len(trace),state_sampling_s=.01,
        minimum_sampled_gap_m=mingap,final_separation_lower_bound_m=gap,tail_max_speed_m_s=tailv,tail_max_angular_speed_rad_s=tailw,
        source_sha256=hashes,scope="independent convex robot/self/table/puzzle checks on saved actual physics states",
        pregrasp_start=True,assisted_weld_grasp=True,grasp_assistance_active_at_end=True,formal_demo_qualified=False)
    save(output/"audit.json",result);print(json.dumps({k:v for k,v in result.items() if k!="errors"},indent=2),flush=True)
    return result


def recording_motion(folder,kinematic=False):
    record,motion,proof,meshes,cells=load_instance(folder)
    if kinematic:return motion,record,meshes,cells
    folder=Path(folder);output=folder/"physics";audit_report=json.loads((output/"audit.json").read_text())
    physics=json.loads((output/"report.json").read_text())
    if not audit_report["passed"]:raise ValueError("Physical audit must pass before recording")
    if any(sha(output/n)!=h for n,h in audit_report["source_sha256"].items()):raise ValueError("Stale physical audit")
    trace=json.loads((output/"trajectory.json").read_text());times=np.array([f["time_s"] for f in trace])
    fps=12;targets=np.arange(0,times[-1]+1e-8,1/fps);indices=[int(np.argmin(abs(times-t))) for t in targets];indices[-1]=len(trace)-1
    kin=Kinematics(configuration().robot_control);frames=[];phases=[]
    for j,i in enumerate(indices):
        row=trace[i];kin.q=np.array(row["qpos"])
        tips={side:dict(pos=kin.pose(side)[0].tolist(),quat=Rotation.from_matrix(kin.pose(side)[1]).as_quat().tolist()) for side in ("left","right")}
        frames.append(dict(row,source_trace_index=i,grasp_targets=tips))
        if not phases or phases[-1]["name"]!=row["stage"]:phases.append(dict(name=row["stage"],frame=j,time_s=j/fps))
    report=dict(passed=True,variant_id=record["id"],physics_steps=physics["physics_steps"],
        kinematic_replay=False,robot_execution_verified=True,pregrasp_start=True,assisted_weld_grasp=True,
        grasp_assistance_active_at_end=True,physical_source_sha256=audit_report["source_sha256"],
        geometry_sha256=sha(folder/"geometry.json"),certificate_sha256=sha(folder/"certificate.json"),
        source_physical_audit_passed=True,sampled_robot_scene_clearance_passed=True,formal_demo_qualified=False)
    return dict(fps=fps,frames=frames,phases=phases,report=report),record,meshes,cells


def render(folder,kinematic=False):
    folder=Path(folder).resolve();motion,record,meshes,cells=recording_motion(folder,kinematic)
    output=folder/("kinematic_recording" if kinematic else "recording")
    if (output/"replay_report.json").exists():raise ValueError("A complete recording already exists; preserve it")
    output.mkdir(parents=True,exist_ok=True);save(output/"render_motion.json",motion)
    import genesis as gs
    import imageio.v2 as imageio
    from PIL import Image,ImageDraw
    from topogym.robot import initialize_robot_controller
    from topogym.world.aloha_cameras import CAMERA_NAMES,configure_aloha_rig
    cfg=configuration(render=True);camera_report=configure_aloha_rig(cfg,keep=("detail","oblique"),low_pitch_offset_deg=20)
    OmegaConf.save(cfg,output/"config.yaml",resolve=True)
    gs.init(backend=gs.cuda,precision="64",logging_level="warning",seed=0)
    task=build_scene(cfg,output/"assets",record,meshes,cells,motion["frames"][0])
    controller=initialize_robot_controller(scene=task.scene,manifest=task.manifest,robot_cfg=cfg.robot_control,settle_steps=0)
    max_fk_error=0.;camera_poses=[]
    def pose(frame):
        nonlocal max_fk_error
        controller.robot.set_qpos(np.array(frame["qpos"]));set_objects(task,frame)
        task.scene.visualizer.update_visual_states(force_render=True)
        for n in CAMERA_NAMES[2:]:task.cameras[n].move_to_attach()
        for side,target in frame["grasp_targets"].items():
            arm=controller.arms[side];q=arm.hand_quat()
            p=arm.hand_pos()+Rotation.from_quat(q[[1,2,3,0]]).apply(PAD_CENTER)
            error=float(np.linalg.norm(p-task.mount-target["pos"]));max_fk_error=max(max_fk_error,error)
            if error>.00002:raise ValueError("Recorded Genesis robot differs from the checked FK")
    pose(motion["frames"][0]);camera_report["initial_camera_checks"]={}
    for n,c in task.cameras.items():
        rgb=c.render(force_render=True)[0].copy();Image.fromarray(rgb).save(output/f"initial_{n}.png")
        camera_report["initial_camera_checks"][n]=dict(transform=np.asarray(c.transform).tolist(),intrinsics=np.asarray(c.intrinsics).tolist())
    save(output/"camera_report.json",camera_report)
    names=[*CAMERA_NAMES,"detail","oblique"]
    with ExitStack() as stack:
        writers={n:stack.enter_context(imageio.get_writer(output/f"{n}.mp4",fps=motion["fps"],codec="libx264",quality=7,
            macro_block_size=1,ffmpeg_params=["-threads","2"],ffmpeg_log_level="error")) for n in names+["four_views"]}
        for i,frame in enumerate(motion["frames"]):
            pose(frame);grid=Image.new("RGB",(1280,720))
            for n in names:
                rgb=task.cameras[n].render(force_render=True)[0].copy();writers[n].append_data(rgb)
                if n in CAMERA_NAMES:
                    j=CAMERA_NAMES.index(n);tile=Image.fromarray(rgb).resize((640,360));draw=ImageDraw.Draw(tile)
                    draw.rectangle((0,0,640,25),fill=(20,28,35));draw.text((12,7),n,fill="white");grid.paste(tile,((j%2)*640,(j//2)*360))
            writers["four_views"].append_data(np.asarray(grid));camera_poses.append({n:np.asarray(task.cameras[n].transform).tolist() for n in CAMERA_NAMES})
            if i%24==0:print(f"{record['id']} render {i+1}/{len(motion['frames'])}: {frame['stage']}",flush=True)
    for n in ("detail","oblique"):Image.fromarray(task.cameras[n].render(force_render=True)[0]).save(output/f"final_{n}.png")
    report=dict(motion["report"],frames=len(motion["frames"]),fps=motion["fps"],duration_s=len(motion["frames"])/motion["fps"],
        renderer="nyx",maximum_genesis_pad_fk_error_m=max_fk_error,loaded_collision_audit=task.loaded_audit,
        render_motion_sha256=sha(output/"render_motion.json"),rendering_physics_steps=0,phases=motion["phases"])
    save(output/"replay_report.json",report);save(output/"camera_poses.json",camera_poses)
    print(f"Complete recording: {output}",flush=True)


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument("action",choices=("physics","audit","render"))
    p.add_argument("--variant",choices=VARIANTS,required=True);p.add_argument("--root",type=Path,default=OUTPUT)
    p.add_argument("--kinematic",action="store_true");a=p.parse_args();folder=a.root/a.variant
    if a.action=="physics":result=execute(folder)
    elif a.action=="audit":result=audit(folder)
    else:render(folder,a.kinematic);return
    if not result["passed"]:raise SystemExit(1)


if __name__=="__main__":main()
