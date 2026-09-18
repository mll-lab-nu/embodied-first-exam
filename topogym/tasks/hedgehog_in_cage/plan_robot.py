"""Check fixed-spike grasps in an isolated kinematic planning scene."""
import argparse
import json

import numpy as np
from omegaconf import OmegaConf
from scipy.spatial.transform import Rotation

from .geometry import ROOT
from .stability import array


def hand_in_ball(roll, grip_point, pad_offset):
    # S2 points along body -X; the hand approaches along body +X.
    z = np.array([1.,0.,0.])
    y = np.array([0.,np.cos(roll),np.sin(roll)])
    rotation = Rotation.from_matrix(np.column_stack([np.cross(y,z),y,z]))
    return grip_point-rotation.apply(pad_offset), rotation


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", default="runs/environment_bootstrap/hedgehog_in_cage/classic_wood")
    parser.add_argument("--path", default="escape_upper.json")
    parser.add_argument("--yaw", type=float, default=-130.)
    parser.add_argument("--mount-height", type=float, default=.10)
    parser.add_argument("--inset", type=float, default=-.006,
        help="Pad center inset from S2 tip; negative still overlaps the 37.5 mm long pads")
    args=parser.parse_args()
    output=ROOT/args.output
    solution=json.loads((output/args.path).read_text())
    if not solution["found"]:
        raise ValueError("No verified object path")
    cfg=OmegaConf.load(output/"config.yaml")
    cfg.env.cameras={}
    cfg.env.renderer.type="rasterizer"
    cfg.task.yaw_deg=args.yaw
    cfg.task.mount_height_m=args.mount_height
    q0=np.asarray(solution["path"][0])
    cfg.task.initial_pose=dict(position_m=q0[:3].tolist(),quaternion_wxyz=q0[[6,3,4,5]].tolist())
    import genesis as gs
    from .scene import HedgehogSceneBuilder
    from .plan_escape import interpolate
    from topogym.utils.franka import initialize_franka_controller
    from topogym.robot.gripper import robotiq_joint_targets
    gs.init(backend=gs.cuda,logging_level="warning",seed=0)
    task=HedgehogSceneBuilder(cfg.env,cfg.task,cfg.robot_control).build(asset_dir=output/"assets",reuse_assets=True)
    c=initialize_franka_controller(scene=task.scene,manifest=task.manifest,robot_cfg=cfg.robot_control,settle_steps=0)
    robot=c.robot
    full=array(robot.get_qpos()).copy()
    for name,value in robotiq_joint_targets(.0055).items():
        name={"right_driver_joint":"finger_joint1","left_driver_joint":"finger_joint2"}.get(name,"r85_"+name)
        full[robot.get_joint(name).qs_idx_local[0]]=value
    robot.set_qpos(full)
    offset=Rotation.from_quat(c.hand_quat()[[1,2,3,0]]).inv().apply(c.grasp_center_pos()-c.hand_pos())
    grip_point=task.layout.spike_segments()[1][1]+np.array([args.inset,0,0])
    cage_r=Rotation.from_euler("z",args.yaw,degrees=True)
    raw=[np.asarray(q) for q in solution["path"]]
    poses=np.asarray([q for a,b in zip(raw[:-1],raw[1:]) for q in interpolate(a,b,.004)])
    allowed_links={robot.get_link(n).idx for n in ("left_finger","right_finger")}
    solver=task.scene.sim.rigid_solver
    def forbidden_contacts():
        problems=[]
        for ga,gb in array(robot.detect_collision()).reshape(-1,2):
            la,lb=solver.geoms[int(ga)].link.idx,solver.geoms[int(gb)].link.idx
            if (la in allowed_links and lb==task.hedgehog.base_link_idx) or (lb in allowed_links and la==task.hedgehog.base_link_idx):
                continue
            problems.append([int(ga),int(gb),solver.links[la].name,solver.links[lb].name])
        return problems
    results=[]
    for roll_deg in range(0,360,30):
        rel_p,rel_r=hand_in_ball(np.deg2rad(roll_deg),grip_point,offset)
        robot.set_qpos(full)
        trajectory=[]; failure=None
        for index,q in enumerate(poses):
            ball_p=task.cage_origin+cage_r.apply(q[:3]);ball_r=cage_r*Rotation.from_quat(q[3:])
            task.hedgehog.set_pos(ball_p);task.hedgehog.set_quat(ball_r.as_quat()[[3,0,1,2]])
            hand_p=ball_p+ball_r.apply(rel_p);hand_r=ball_r*rel_r
            target,error=robot.inverse_kinematics(link=c.ee_link,pos=hand_p,quat=hand_r.as_quat()[[3,0,1,2]],
                init_qpos=robot.get_qpos(),dofs_idx_local=c.arm_dofs,max_samples=10 if index==0 else 1,
                max_solver_iters=300,pos_tol=1e-5,rot_tol=1e-4,return_error=True)
            error=array(error)
            if np.linalg.norm(error)>.001:
                failure=dict(index=index,reason="ik",error=error.tolist());break
            if index and np.max(np.abs(array(target)[:7]-trajectory[-1]))>.35:
                failure=dict(index=index,reason="ik_branch_jump");break
            robot.set_qpos(target)
            contacts=forbidden_contacts()
            if contacts:
                failure=dict(index=index,reason="collision",pairs=contacts);break
            trajectory.append(array(target)[:7].tolist())
        row=dict(roll_deg=roll_deg,checked_poses=len(trajectory),total_poses=len(poses),failure=failure,
            hand_position_in_ball=rel_p.tolist(),hand_quaternion_in_ball_xyzw=rel_r.as_quat().tolist(),
            grip_point_in_ball=grip_point.tolist(),pad_offset_in_hand=offset.tolist())
        results.append(row)
        print(json.dumps(row),flush=True)
        if failure is None:
            np.savez(output/"robot_escape_plan.npz",ball_poses=poses,arm_qpos=trajectory)
            report=dict(found=True,cage_yaw_deg=args.yaw,mount_height_m=args.mount_height,spike="S2",selected=row,
                scope="isolated_kinematic_grasp_path_only",live_simulation_pose_overwrites=False,
                source_object_path=args.path,candidates=results)
            (output/"robot_escape_plan.json").write_text(json.dumps(report,indent=2)+"\n")
            return
    (output/"robot_escape_plan.json").write_text(json.dumps(dict(found=False,cage_yaw_deg=args.yaw,candidates=results),indent=2)+"\n")


if __name__=="__main__":
    main()
