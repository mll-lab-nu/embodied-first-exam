"""Physical, contact-gated robot extraction with three calibrated camera streams.

The episode starts at a declared pregrasp reset. After time zero only joint
actuators and a contact-gated grasp constraint act on the free hedgehog.
"""
import argparse
import hashlib
import json

import numpy as np
from omegaconf import OmegaConf
from scipy.spatial.transform import Rotation

from .geometry import ROOT, clearance_samples
from .stability import array


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output",default="runs/environment_bootstrap/hedgehog_in_cage/classic_wood")
    parser.add_argument("--record",action="store_true")
    args=parser.parse_args()
    out=ROOT/args.output
    plan=json.loads((out/"robot_escape_plan.json").read_text())
    if not plan["found"]:
        raise ValueError("No collision-checked robot plan")
    evidence=[]
    for h in (.0005,.00025):
        f=out/f"stability_v2_escape_supported_h{h:.7f}_t10_noslip5.json"
        report=json.loads(f.read_text())
        if not report["complete"] or not report["all_passed"] or not report["initial_impact_covered"]:
            raise ValueError(f"Stability prerequisite has not passed: {f}")
        evidence.append(f.name)
    path_report=json.loads((out/plan["source_object_path"]).read_text())
    if not path_report["found"]:
        raise ValueError("Object path is not verified")
    path=[np.asarray(q) for q in path_report["path"]]
    release_plan=json.loads((out/"robot_release_plan.json").read_text())
    if not release_plan["found"]:
        raise ValueError("No collision-checked placement plan")
    cfg=OmegaConf.load(out/"config.yaml")
    cfg.env.sim.dt=.005
    cfg.env.sim.substeps=10
    cfg.task.physics=dict(constraint_timeconst=.0012,friction=.3,iterations=100,noslip_iterations=5)
    cfg.task.yaw_deg=plan["cage_yaw_deg"]
    cfg.task.mount_height_m=plan["mount_height_m"]
    cfg.task.initial_pose=dict(position_m=path[0][:3].tolist(),quaternion_wxyz=path[0][[6,3,4,5]].tolist())
    camera_names=("agentview","front_oblique","wrist")
    if args.record:
        reference=OmegaConf.load(ROOT/"configs/lock_picking_baseline.yaml")
        shared=OmegaConf.load(ROOT/"configs/env_configs/world_tabletop_v1.yaml")
        cfg.env.cameras=OmegaConf.create({name:OmegaConf.to_container(
            shared.cameras.wrist if name=="wrist" else reference.env.cameras[name],resolve=True)
            for name in camera_names})
        for name in camera_names:
            cfg.env.cameras[name].res=[960,720]
        cfg.env.cameras.agentview.lookat=[-.06,.10,1.18]
        cfg.env.cameras.front_oblique.lookat=[-.02,.10,1.17]
        cfg.env.renderer.type="nyx"
        cfg.env.renderer.spp=24
    else:
        cfg.env.cameras={}
        cfg.env.renderer.type="rasterizer"
    OmegaConf.save(cfg,out/"extraction_config.yaml",resolve=True)
    import genesis as gs
    import imageio.v2 as imageio
    from .scene import HedgehogSceneBuilder
    from topogym.utils.franka import initialize_franka_controller
    from topogym.robot.gripper import robotiq_joint_targets
    gs.init(backend=gs.cuda,logging_level="warning",seed=0)
    task=HedgehogSceneBuilder(cfg.env,cfg.task,cfg.robot_control).build(asset_dir=out/"assets",reuse_assets=True)
    c=initialize_franka_controller(scene=task.scene,manifest=task.manifest,robot_cfg=cfg.robot_control,settle_steps=0)
    ball=task.hedgehog
    solver=task.scene.sim.rigid_solver
    full=array(c.robot.get_qpos()).copy()
    full[:7]=np.load(out/"robot_escape_plan.npz")["arm_qpos"][0]
    for name,value in robotiq_joint_targets(.0054).items():
        name={"right_driver_joint":"finger_joint1","left_driver_joint":"finger_joint2"}.get(name,"r85_"+name)
        full[c.robot.get_joint(name).qs_idx_local[0]]=value
    c.robot.set_qpos(full,zero_velocity=True)
    c.robot.control_dofs_position(full[:7],c.arm_dofs)
    c.set_gripper(.0044,steps=0)
    cage_r=Rotation.from_euler("z",float(cfg.task.yaw_deg),degrees=True)
    fingers={c.robot.get_link(n).idx for n in ("left_finger","right_finger")}
    writers={name:imageio.get_writer(out/f"extraction_{name}.mp4",fps=20,
        codec="libx264",quality=8,macro_block_size=1,ffmpeg_log_level="error") for name in camera_names} if args.record else {}
    trace=(out/("extraction_states.jsonl" if args.record else "extraction_dry_states.jsonl")).open("w")
    step_count=0
    phase="pregrasp_contact"
    welded=False
    max_cage_penetration=0.
    max_all_penetration=0.
    max_cage_force=0.
    max_robot_fixture_penetration=0.
    max_tracking_error=0.
    rendered_phases=set()
    result={"success":False,"complete":False}
    robot_links={link.idx for link in c.robot.links if link.idx!=c.robot.base_link_idx}
    fixture_links={task.cage.base_link_idx,task.manifest.get("hedgehog_mount").base_link_idx,
        task.manifest.get("table").base_link_idx}
    def pose():
        return array(ball.get_pos()),Rotation.from_quat(array(ball.get_quat())[[1,2,3,0]])
    def render():
        for name,writer in writers.items():
            frame=task.cameras[name].render()[0]
            writer.append_data(frame)
            if phase not in rendered_phases:
                imageio.imwrite(out/f"extraction_{phase}_{name}.jpg",frame,quality=90)
        rendered_phases.add(phase)
    def step():
        nonlocal step_count,max_cage_penetration,max_all_penetration,max_cage_force,max_robot_fixture_penetration
        task.scene.step()
        step_count+=1
        contacts=solver.collider.get_contacts(as_tensor=True,to_torch=True)
        la,lb=array(contacts["link_a"]),array(contacts["link_b"])
        pen=array(contacts["penetration"])
        forces=np.linalg.norm(array(contacts["force"]),axis=-1)
        ball_mask=(la==ball.base_link_idx)|(lb==ball.base_link_idx)
        mask=ball_mask & ((la==task.cage.base_link_idx)|(lb==task.cage.base_link_idx))
        robot_fixture_mask=(np.isin(la,list(robot_links))&np.isin(lb,list(fixture_links))) | (np.isin(lb,list(robot_links))&np.isin(la,list(fixture_links)))
        robot_pen=float(pen[robot_fixture_mask].max(initial=0))
        max_robot_fixture_penetration=max(max_robot_fixture_penetration,robot_pen)
        cage_pen=float(pen[mask].max(initial=0))
        max_cage_penetration=max(max_cage_penetration,cage_pen)
        max_all_penetration=max(max_all_penetration,float(pen[ball_mask].max(initial=0)))
        max_cage_force=max(max_cage_force,float(forces[mask].max(initial=0)))
        if step_count%4==0:
            p,r=pose()
            row=dict(time_s=step_count*.005,phase=phase,ball_position_m=p.tolist(),
                ball_quaternion_xyzw=r.as_quat().tolist(),robot_qpos=array(c.robot.get_qpos()).tolist(),
                cage_penetration_m=cage_pen,max_cage_penetration_m=max_cage_penetration,
                linear_speed_m_s=float(np.linalg.norm(array(ball.get_vel()))),
                angular_speed_rad_s=float(np.linalg.norm(array(ball.get_ang()))),grasp_constraint_active=welded)
            trace.write(json.dumps(row)+"\n")
            (out/"extraction_latest_state.json").write_text(json.dumps(row,indent=2)+"\n")
        if step_count%10==0:
            render()
        if cage_pen>.00015:
            raise RuntimeError(f"Cage penetration exceeded dynamic gate: {cage_pen*1000:.3f} mm")
        if robot_pen>.00015:
            raise RuntimeError(f"Robot/fixture penetration: {robot_pen*1000:.3f} mm")
        if step_count%200==0:
            print(json.dumps(dict(time_s=step_count*.005,phase=phase,max_cage_penetration_m=max_cage_penetration)),flush=True)
    def drive_hand(position,rotation,steps=2):
        target,error=c.robot.inverse_kinematics(link=c.ee_link,pos=position,quat=rotation.as_quat()[[3,0,1,2]],
            init_qpos=c.robot.get_qpos(),dofs_idx_local=c.arm_dofs,max_samples=1,max_solver_iters=300,
            pos_tol=1e-5,rot_tol=1e-4,return_error=True)
        if np.linalg.norm(array(error))>.002:
            raise RuntimeError(f"IK error: {array(error).tolist()}")
        if np.max(np.abs(array(target)[:7]-c.arm_qpos()))>.3:
            raise RuntimeError("IK branch discontinuity")
        c.robot.control_dofs_position(target[:7],c.arm_dofs)
        for _ in range(steps):step()
    def move_ball(a,b,relative_hand_p,relative_hand_r,speed=.012,angular_speed=.4):
        nonlocal max_tracking_error
        ra,rb=Rotation.from_quat(a[3:]),Rotation.from_quat(b[3:])
        delta=(rb*ra.inv()).as_rotvec()
        duration=max(np.linalg.norm(b[:3]-a[:3])/speed,np.linalg.norm(delta)/angular_speed,.25)*1.875
        n=max(2,int(np.ceil(duration/.01)))
        for i in range(1,n+1):
            t=i/n;u=10*t**3-15*t**4+6*t**5
            local_p=a[:3]+u*(b[:3]-a[:3]);local_r=Rotation.from_rotvec(u*delta)*ra
            p=task.cage_origin+cage_r.apply(local_p);r=cage_r*local_r
            drive_hand(p+r.apply(relative_hand_p),r*relative_hand_r)
            actual,_=pose()
            max_tracking_error=max(max_tracking_error,float(np.linalg.norm(actual-p)))
        for _ in range(20):step()
    render()
    try:
        contact_seen=False
        for _ in range(80):
            step()
            ct=c.robot.get_contacts(with_entity=ball)
            touched=set(array(ct["link_a"]).tolist())|set(array(ct["link_b"]).tolist())
            if fingers.issubset(touched):
                contact_seen=True
                break
        if not contact_seen:
            raise RuntimeError("No simultaneous bilateral finger contact; grasp assist was not activated")
        p,r=pose()
        relative_hand_p=r.inv().apply(c.hand_pos()-p)
        relative_hand_r=r.inv()*Rotation.from_quat(c.hand_quat()[[1,2,3,0]])
        solver.add_weld_constraint(c.ee_link.idx,ball.base_link_idx)
        welded=True
        phase="hold_grasp"
        for _ in range(100):step()
        p,r=pose()
        actual_start=np.r_[cage_r.inv().apply(p-task.cage_origin),(cage_r.inv()*r).as_quat()]
        phase="align_with_verified_path"
        move_ball(actual_start,path[0],relative_hand_p,relative_hand_r)
        phase="rotate_and_extract"
        for a,b in zip(path[:-1],path[1:]):move_ball(a,b,relative_hand_p,relative_hand_r)
        points,radii=clearance_samples(task.layout)
        p,r=pose();world=r.apply(points)+p
        outside_margin=float(np.min(np.linalg.norm(world[:,:2]-task.cage_origin[:2],axis=1)-radii)-.0675)
        if outside_margin<.003:
            raise RuntimeError(f"Not fully outside: margin={outside_margin}")
        result["outside_margin_before_release_m"]=outside_margin
        result["fully_extracted"]=True
        placement=[np.asarray(q) for q in release_plan["path"]]
        for label,a,b in zip(release_plan["phases"],placement[:-1],placement[1:]):
            phase=label
            move_ball(a,b,relative_hand_p,relative_hand_r,speed=.03,angular_speed=.6)
        phase="release"
        solver.delete_weld_constraint(c.ee_link.idx,ball.base_link_idx)
        welded=False
        c.open_gripper(steps=0)
        for _ in range(150):step()
        hand_p=c.hand_pos();hand_r=Rotation.from_quat(c.hand_quat()[[1,2,3,0]])
        for t in np.linspace(0,1,100):drive_hand(hand_p+[0,0,.08*t],hand_r)
        phase="final_settle"
        for _ in range(1000):step()
        final_speed=float(np.linalg.norm(array(ball.get_vel())))
        final_angular_speed=float(np.linalg.norm(array(ball.get_ang())))
        p,r=pose();world=r.apply(points)+p
        outside_margin=float(np.min(np.linalg.norm(world[:,:2]-task.cage_origin[:2],axis=1)-radii)-.0675)
        result.update(success=bool(outside_margin>.003 and max_cage_penetration<.0001 and max_robot_fixture_penetration<.0001
                and final_speed<.001 and final_angular_speed<np.deg2rad(.5)),fully_extracted=bool(outside_margin>.003),
            outside_margin_after_release_m=outside_margin,grasp_released=True,
            final_linear_speed_m_s=final_speed,final_angular_speed_rad_s=final_angular_speed,complete=True)
    except Exception as exc:
        result.update(success=False,error=str(exc),failed_phase=phase)
        result.setdefault("fully_extracted",False)
        print("FAILED "+str(exc),flush=True)
    finally:
        if welded:
            solver.delete_weld_constraint(c.ee_link.idx,ball.base_link_idx)
        trace.close()
        for writer in writers.values():writer.close()
        result.update(scope="single_pregrasp_instance",simulated_seconds=step_count*.005,
            geometry_modified=False,initial_pose_changed=True,pregrasp_reset=True,
            grasp_assistance="weld enabled only after simultaneous bilateral finger contact; removed on release",
            live_object_pose_overwrites=False,live_robot_pose_overwrites=False,
            cage_yaw_deg=float(cfg.task.yaw_deg),mount_height_m=float(cfg.task.mount_height_m),
            max_cage_penetration_m=max_cage_penetration,max_all_ball_contact_penetration_m=max_all_penetration,
            max_cage_contact_force_n=max_cage_force,max_position_tracking_error_m=max_tracking_error,
            max_robot_fixture_penetration_m=max_robot_fixture_penetration,
            stability_evidence=evidence,object_path_source=plan["source_object_path"],
            renderer=str(cfg.env.renderer.type),camera_names=list(writers),video_created=args.record,
            asset_manifest_sha256=hashlib.sha256((out/"assets/sha256.json").read_bytes()).hexdigest())
        f=out/("extraction_result.json" if args.record else "extraction_dry_result.json")
        f.write_text(json.dumps(result,indent=2)+"\n")
        print(json.dumps(result),flush=True)


if __name__=="__main__":
    main()
