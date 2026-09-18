"""Physical execution seeded from certified IK to prevent redundant-arm branch drift."""
from __future__ import annotations
import argparse
from scipy.optimize import least_squares
from .family_runtime import (Path, json, np, Rotation, array, config, sha, save,
    admitted, build_scene, clearance_samples, OmegaConf, time, Kinematics)
from .family_motion import OUTPUT, FAMILIES


def execute(folder, substeps=10, backend="cuda"):
    folder = Path(folder); trace, cert = admitted(folder)
    check = json.loads((folder / "robot_audit.json").read_text())
    if not check["passed"] or check["certificate_sha256"] != sha(folder / "certificate.json"):
        raise ValueError("A current robot clearance check is required")
    output = folder / ("physics" if substeps==10 else f"physics_substeps{substeps}")
    if (output / "report.json").exists(): raise ValueError("Preserve the existing physics run")
    output.mkdir(parents=True, exist_ok=True)
    cfg = config(); cfg.env.cameras = {}; cfg.env.renderer.type = "rasterizer"
    cfg.env.sim.dt = .005; cfg.env.sim.substeps = substeps; cfg.env.genesis.precision = "64"
    cfg.env.genesis.backend=backend
    OmegaConf.save(cfg, output / "config.yaml", resolve=True)
    import genesis as gs
    from topogym.utils.franka import initialize_franka_controller
    from topogym.robot.gripper import robotiq_joint_targets
    gs.init(backend=gs.cuda if backend=="cuda" else gs.cpu, precision="64", logging_level="warning", seed=0)
    task = build_scene(folder, cfg)
    cage_radius=float(json.loads((folder/"assets/asset_report.json").read_text())["maximum_radial_extent_m"])
    c = initialize_franka_controller(scene=task.scene, manifest=task.manifest, robot_cfg=cfg.robot_control, settle_steps=0)
    ball = task.ball; solver = task.scene.sim.rigid_solver
    q = np.array(trace["frames"][0]["qpos"])
    for name, value in robotiq_joint_targets(.0054).items():
        name = {"right_driver_joint":"finger_joint1", "left_driver_joint":"finger_joint2"}.get(name, "r85_"+name)
        q[c.robot.get_joint(name).qs_idx_local[0]] = value
    c.robot.set_qpos(q, zero_velocity=True); c.robot.control_dofs_position(q[:7], c.arm_dofs)
    c.set_gripper(.0044, steps=0)
    fingers = {c.robot.get_link(n).idx for n in ("left_finger", "right_finger")}
    robot_links = {link.idx for link in c.robot.links if link.idx!=c.robot.base_link_idx}
    fixtures = {task.cage.base_link_idx, task.mount.base_link_idx, task.manifest.get("table").base_link_idx}
    step_count=0; phase="pregrasp_contact"; welded=False; rows=[]; grasp_event=None
    max_cage_pen=0.; max_robot_pen=0.; max_pen=0.; max_tracking=0.; started=time.monotonic()
    guide_kin=Kinematics(); guide_kin.q=q.copy()
    maximum_ik_position_error=0.; maximum_ik_rotation_error=0.
    def pose(): return array(ball.get_pos()), Rotation.from_quat(array(ball.get_quat())[[1,2,3,0]])
    def record():
        p, r = pose()
        rows.append(dict(physics_step=step_count, time_s=step_count*.005, phase=phase,
            ball_position_m=p.tolist(), ball_quaternion_xyzw=r.as_quat().tolist(), robot_qpos=array(c.robot.get_qpos()).tolist(),
            linear_speed_m_s=float(np.linalg.norm(array(ball.get_vel()))), angular_speed_rad_s=float(np.linalg.norm(array(ball.get_ang()))),
            grasp_constraint_active=welded))
    def step():
        nonlocal step_count, max_cage_pen, max_robot_pen, max_pen
        task.scene.step(); step_count+=1
        ct=solver.collider.get_contacts(as_tensor=True,to_torch=True)
        la,lb,pen=(array(ct[k]) for k in ("link_a","link_b","penetration"))
        mask=((la==ball.base_link_idx)&(lb==task.cage.base_link_idx))|((lb==ball.base_link_idx)&(la==task.cage.base_link_idx))
        robot_mask=(np.isin(la,list(robot_links))&np.isin(lb,list(fixtures)))|(np.isin(lb,list(robot_links))&np.isin(la,list(fixtures)))
        max_cage_pen=max(max_cage_pen,float(pen[mask].max(initial=0)))
        max_robot_pen=max(max_robot_pen,float(pen[robot_mask].max(initial=0)))
        max_pen=max(max_pen,float(pen[(la==ball.base_link_idx)|(lb==ball.base_link_idx)].max(initial=0)))
        if max_cage_pen>.00015 or max_robot_pen>.00015: raise ValueError("Physical cage/robot penetration exceeded limit")
        if step_count%2==0:
            record()
            if not np.isfinite(np.r_[rows[-1]["robot_qpos"],rows[-1]["ball_position_m"]]).all(): raise ValueError("Nonfinite physical state")
        if step_count%400==0: print(f"physics {step_count*.005:.1f}s {phase}; wall {time.monotonic()-started:.1f}s",flush=True)
    def drive_hand(position, rotation, steps=2, guide=None):
        nonlocal maximum_ik_position_error, maximum_ik_rotation_error
        # Use the already certified arm branch as the redundant IK seed.
        # Only position targets are sent to the physical controller; no pose resets.
        seed=np.array(c.arm_qpos() if guide is None else guide, dtype=float)
        guide_kin.q=array(c.robot.get_qpos()).copy()
        def residual(arm):
            guide_kin.q[:7]=arm
            p,r=guide_kin.forward()
            return np.r_[20*(p-position),(r*rotation.inv()).as_rotvec(),.00005*(arm-seed)]
        limits=guide_kin.model.jnt_range[:7]
        solution=least_squares(residual,seed,bounds=(limits[:,0]+1e-6,limits[:,1]-1e-6),
            max_nfev=100,ftol=1e-11,xtol=1e-11,gtol=1e-11)
        error=residual(solution.x)
        pe=float(np.linalg.norm(error[:3])/20);re=float(np.linalg.norm(error[3:6]))
        jump=float(np.max(abs(solution.x-c.arm_qpos())))
        maximum_ik_position_error=max(maximum_ik_position_error,pe)
        maximum_ik_rotation_error=max(maximum_ik_rotation_error,re)
        if pe>1e-5 or re>1e-4 or jump>.3:
            raise ValueError(f"Guided IK failed: position={pe}, rotation={re}, joint_jump={jump}")
        if any(contact.dist<-.0001 for contact in guide_kin.data.contact):
            raise ValueError("Guided IK robot self collision")
        c.robot.control_dofs_position(solution.x,c.arm_dofs)
        for _ in range(steps):step()
    def move(a,b,hp,hr,speed=.012,angular=.4,segment=None):
        nonlocal max_tracking
        a,b=np.array(a),np.array(b);ra,rb=Rotation.from_quat(a[3:]),Rotation.from_quat(b[3:]);delta=(rb*ra.inv()).as_rotvec()
        duration=max(np.linalg.norm(b[:3]-a[:3])/speed,np.linalg.norm(delta)/angular,.25)*1.875
        count=max(2,int(np.ceil(duration/.01)))
        if segment is None:
            reference=np.array([trace["frames"][0]["qpos"][:7]]*2)
        else:
            group=[j for j,row in enumerate(trace["frames"]) if row["segment"]==segment]
            start=max(0,group[0]-int(segment>0))
            reference=np.array([row["qpos"][:7] for row in trace["frames"][start:group[-1]+1]])
        fractions=np.linspace(0,1,len(reference))
        for i in range(1,count+1):
            t=i/count;u=10*t**3-15*t**4+6*t**5
            p=task.origin+task.rotation.apply(a[:3]+u*(b[:3]-a[:3]));r=task.rotation*Rotation.from_rotvec(u*delta)*ra
            guide=np.array([np.interp(u,fractions,reference[:,j]) for j in range(7)])
            drive_hand(p+r.apply(hp),r*hr,guide=guide)
            max_tracking=max(max_tracking,float(np.linalg.norm(pose()[0]-p)))
        for _ in range(20):step()
    record(); result=dict(passed=False,complete=False)
    try:
        for _ in range(80):
            step();ct=c.robot.get_contacts(with_entity=ball)
            touched=set(array(ct["link_a"]).tolist())|set(array(ct["link_b"]).tolist())
            if fingers.issubset(touched):break
        else:raise ValueError("No simultaneous bilateral finger contact")
        p,r=pose();hp=r.inv().apply(c.hand_pos()-p);hr=r.inv()*Rotation.from_quat(c.hand_quat()[[1,2,3,0]])
        solver.add_weld_constraint(c.ee_link.idx,ball.base_link_idx);welded=True
        grasp_event=dict(physics_step=step_count,finger_links=sorted(fingers),simultaneous_contact=True)
        phase="hold_grasp"
        for _ in range(100):step()
        p,r=pose();actual=np.r_[task.rotation.inv().apply(p-task.origin),(task.rotation.inv()*r).as_quat()]
        path=trace["proposed_path"]
        phase="align_with_verified_path";move(actual,path[0],hp,hr)
        for i,(a,b) in enumerate(zip(path[:-1],path[1:])):
            phase=trace["extraction_phases"][i]
            move(a,b,hp,hr,segment=i)
        points,radii=clearance_samples(task.layout);p,r=pose();world=r.apply(points)+p
        margin=float(np.min(np.linalg.norm(world[:,:2]-task.origin[:2],axis=1)-radii)-cage_radius)
        if margin<.003:raise ValueError("Hedgehog not fully outside before placement")
        result["outside_margin_before_release_m"]=margin
        for j,(label,a,b) in enumerate(zip(trace["release_phases"],trace["release_path"][:-1],trace["release_path"][1:])):
            phase=label;move(a,b,hp,hr,speed=.03,angular=.6,segment=len(path)-1+j)
        phase="release";solver.delete_weld_constraint(c.ee_link.idx,ball.base_link_idx);welded=False;c.open_gripper(steps=0)
        for _ in range(150):step()
        hand_p=c.hand_pos();hand_r=Rotation.from_quat(c.hand_quat()[[1,2,3,0]])
        for t in np.linspace(0,1,100):drive_hand(hand_p+[0,0,.08*t],hand_r)
        phase="final_settle"
        for _ in range(1000):step()
        if rows[-1]["physics_step"]!=step_count:record()
        p,r=pose();world=r.apply(points)+p
        margin=float(np.min(np.linalg.norm(world[:,:2]-task.origin[:2],axis=1)-radii)-cage_radius)
        speed=float(np.linalg.norm(array(ball.get_vel())));angular=float(np.linalg.norm(array(ball.get_ang())))
        result.update(passed=bool(margin>.003 and speed<.001 and angular<np.deg2rad(.5)
            and max_cage_pen<.0001 and max_robot_pen<.0001),complete=True,grasp_released=True,
            outside_margin_after_release_m=margin,final_linear_speed_m_s=speed,final_angular_speed_rad_s=angular)
    except Exception as exc:
        result.update(passed=False,error=str(exc),failed_phase=phase);print(f"FAILED: {exc}",flush=True)
    finally:
        if welded:solver.delete_weld_constraint(c.ee_link.idx,ball.base_link_idx)
        result.update(physics_steps=step_count,simulated_seconds=step_count*.005,dt=.005,substeps=substeps,
            precision_bits=64,backend=backend,pregrasp_start=True,assisted_grasp=True,contact_gate=grasp_event,
            live_object_pose_overwrites=False,live_robot_pose_overwrites=False,geometry_modified=True,
            max_cage_penetration_m=max_cage_pen,max_robot_fixture_penetration_m=max_robot_pen,
            max_all_ball_contact_penetration_m=max_pen,max_position_tracking_error_m=max_tracking,
            loaded_collision_audit=task.loaded_audit,asset_manifest_sha256=sha(folder/"assets/sha256.json"),
            ik_sha256=sha(folder/"ik_before_geometry.json"),runner_sha256=sha(Path(__file__)),
            runner_module="family_guided_runtime.py",controller="physical_position_control_with_certified_branch_guided_ik",
            runtime_dependency_sha256={"family_runtime.py":sha(Path(__file__).with_name("family_runtime.py"))},
            maximum_ik_position_error_m=maximum_ik_position_error,maximum_ik_rotation_error_rad=maximum_ik_rotation_error)
        save(output/"trajectory.json",rows);save(output/"report.json",result)
        print(json.dumps(result,indent=2),flush=True)
    if not result["passed"]:raise ValueError("Complete physical run did not pass")


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('family', choices=FAMILIES)
    parser.add_argument('--output', type=Path, default=OUTPUT)
    parser.add_argument('--substeps', type=int, default=10)
    parser.add_argument('--backend', choices=('cpu','cuda'), default='cpu')
    args=parser.parse_args()
    execute(args.output/args.family,args.substeps,args.backend)


if __name__=='__main__':main()
