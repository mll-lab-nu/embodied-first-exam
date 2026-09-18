"""Find a reachable stable placement after the certified cage extraction."""
import json

import numpy as np
from omegaconf import OmegaConf
from scipy.spatial.transform import Rotation
import trimesh

from .geometry import ROOT
from .plan_escape import interpolate
from .stability import array


def main():
    out = ROOT / "runs/environment_bootstrap/hedgehog_in_cage/classic_wood"
    plan = json.loads((out / "robot_escape_plan.json").read_text())
    source = json.loads((out / plan["source_object_path"]).read_text())
    cfg = OmegaConf.load(out / "config.yaml")
    cfg.env.cameras = {}
    cfg.env.renderer.type = "rasterizer"
    cfg.task.yaw_deg = plan["cage_yaw_deg"]
    cfg.task.mount_height_m = plan["mount_height_m"]
    import genesis as gs
    from .scene import HedgehogSceneBuilder
    from topogym.utils.franka import initialize_franka_controller
    from topogym.robot.gripper import robotiq_joint_targets
    gs.init(backend=gs.cuda, logging_level="warning", seed=0)
    task = HedgehogSceneBuilder(cfg.env, cfg.task, cfg.robot_control).build(asset_dir=out / "assets", reuse_assets=True)
    c = initialize_franka_controller(scene=task.scene, manifest=task.manifest, robot_cfg=cfg.robot_control, settle_steps=0)
    solver = task.scene.sim.rigid_solver
    cage_r = Rotation.from_euler("z", plan["cage_yaw_deg"], degrees=True)
    rel_p = np.asarray(plan["selected"]["hand_position_in_ball"])
    rel_r = Rotation.from_quat(plan["selected"]["hand_quaternion_in_ball_xyzw"])
    full = array(c.robot.get_qpos()).copy()
    full[:7] = np.load(out / "robot_escape_plan.npz")["arm_qpos"][-1]
    for name, value in robotiq_joint_targets(.0055).items():
        name = {"right_driver_joint": "finger_joint1", "left_driver_joint": "finger_joint2"}.get(name, "r85_" + name)
        full[c.robot.get_joint(name).qs_idx_local[0]] = value
    fingers = {c.robot.get_link(n).idx for n in ("left_finger", "right_finger")}
    def check(a, b):
        for q in interpolate(a, b, .004):
            p = task.cage_origin + cage_r.apply(q[:3])
            r = cage_r * Rotation.from_quat(q[3:])
            task.hedgehog.set_pos(p)
            task.hedgehog.set_quat(r.as_quat()[[3, 0, 1, 2]])
            hand_r = r * rel_r
            target, error = c.robot.inverse_kinematics(link=c.ee_link, pos=p + r.apply(rel_p),
                quat=hand_r.as_quat()[[3, 0, 1, 2]], init_qpos=c.robot.get_qpos(),
                dofs_idx_local=c.arm_dofs, max_samples=1, max_solver_iters=300,
                pos_tol=1e-5, rot_tol=1e-4, return_error=True)
            if np.linalg.norm(array(error)) > .001 or np.max(np.abs(array(target)[:7] - c.arm_qpos())) > .35:
                return "ik"
            c.robot.set_qpos(target)
            for ga, gb in array(c.robot.detect_collision()).reshape(-1, 2):
                la, lb = solver.geoms[int(ga)].link.idx, solver.geoms[int(gb)].link.idx
                if (la in fingers and lb == task.hedgehog.base_link_idx) or (lb in fingers and la == task.hedgehog.base_link_idx):
                    continue
                return f"collision:{solver.links[la].name}/{solver.links[lb].name}"
        return None
    start = np.asarray(source["path"][-1])
    carry = start.copy()
    carry[:3] = [.31, 0, .02]
    c.robot.set_qpos(full)
    failure = check(start, carry)
    if failure:
        raise RuntimeError(f"Carry: {failure}")
    carry_joints = array(c.robot.get_qpos()).copy()
    mesh = trimesh.load(out / "assets/hedgehog.obj", force="mesh")
    transforms, probabilities = trimesh.poses.compute_stable_poses(mesh,
        center_mass=[-.000414292204428, -.000889212536333, -.00210514331518], sigma=0, n_samples=1)
    candidates = []
    for index, (transform, probability) in enumerate(zip(transforms, probabilities)):
        if probability < .02:
            continue
        for yaw in range(0, 360, 30):
            world_r = Rotation.from_euler("z", yaw, degrees=True) * Rotation.from_matrix(transform[:3, :3])
            if transform[2, 3] + world_r.apply(rel_p)[2] < .12:
                continue
            local_r = cage_r.inv() * world_r
            angle = (local_r * Rotation.from_quat(carry[3:]).inv()).magnitude()
            candidates.append((angle, index, yaw, probability, local_r))
    for _, index, yaw, probability, rotation in sorted(candidates, key=lambda x: x[0]):
        c.robot.set_qpos(carry_joints)
        oriented = carry.copy()
        oriented[3:] = rotation.as_quat()
        release = oriented.copy()
        bottom = float((cage_r * rotation).apply(mesh.vertices)[:, 2].min())
        release[2] = float(cfg.env.frames.table_surface.origin[2]) - bottom + .0015 - task.cage_origin[2]
        failure = check(carry, oriented) or check(oriented, release)
        print(json.dumps(dict(stable_pose=index, yaw=yaw, failure=failure)), flush=True)
        if failure is None:
            result = dict(found=True, scope="isolated_kinematic_placement", stable_pose=index,
                yaw_deg=yaw, stable_pose_probability=float(probability),
                path=[q.tolist() for q in (start, carry, oriented, release)],
                phases=["carry_to_release_location", "orient_for_placement", "lower_to_table"])
            (out / "robot_release_plan.json").write_text(json.dumps(result, indent=2) + "\n")
            return
    raise RuntimeError("No collision-free stable placement")


if __name__ == "__main__":
    main()
