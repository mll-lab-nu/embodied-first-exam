"""ALOHA kinematic rehearsal of the certified five-body geometric witness.

This generates joint and object poses, not forces or an executed grasp policy.
The geometric certificate covers the puzzle; robot checks have a separate scope.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

from hydra import compose, initialize_config_dir
import mujoco
import numpy as np
from scipy.optimize import least_squares
from scipy.spatial.transform import Rotation

from topogym.robot.assets import robot_asset
from .independent_motion import interpolate

ROOT = Path(__file__).resolve().parents[3]
PAD_CENTER = np.array([.14381, 0., -.00355])


class Kinematics:
    def __init__(self, cfg):
        self.model = mujoco.MjModel.from_xml_path(robot_asset(cfg))
        self.data = mujoco.MjData(self.model)
        mujoco.mj_resetDataKeyframe(self.model, self.data, 0)
        self.q = self.data.qpos.copy()
        self.indices = {s: [int(self.model.joint(f"{s}/{n}").qposadr[0])
                           for n in cfg.robot.arm_joint_names] for s in ("left", "right")}
        self.limits = np.asarray(cfg.robot.arm_joint_limits)

    def pose(self, side):
        self.data.qpos[:] = self.q
        mujoco.mj_forward(self.model, self.data)
        body = self.model.body(f"{side}/gripper_link").id
        rotation = self.data.xmat[body].reshape(3, 3).copy()
        return self.data.xpos[body].copy()+rotation@PAD_CENTER, Rotation.from_matrix(rotation)

    def solve(self, side, position, rotation):
        indices = self.indices[side]
        target = rotation.as_matrix()

        def residual(q):
            self.q[indices] = q
            p, r = self.pose(side)
            return np.r_[10*(p-position), Rotation.from_matrix(target@r.as_matrix().T).as_rotvec()]

        result = least_squares(residual, self.q[indices].copy(),
            bounds=(self.limits[:, 0]+1e-6, self.limits[:, 1]-1e-6), max_nfev=160,
            ftol=1e-11, xtol=1e-11, gtol=1e-11)
        error = residual(result.x)
        return float(np.linalg.norm(error[:3])/10), float(np.linalg.norm(error[3:]))


def balanced_frame(frame, origin):
    """Share the relative shoe rotation between both arms, keeping their midpoint fixed.

    The witness uses the continuous positive X-to-Y axis branch for the right
    shoe. Applying one common rigid transform preserves all internal distances.
    """
    q = np.asarray(frame["horseshoe_right"]["quat"])
    if q[0]+q[1] < 0:
        q = -q
    v, norm = q[:3], np.linalg.norm(q[:3])
    rotation = Rotation.from_rotvec(-np.arctan2(norm, q[3])*v/norm) if norm > 1e-12 else Rotation.identity()
    midpoint = (np.asarray(frame["horseshoe_left"]["pos"])+frame["horseshoe_right"]["pos"])/2
    offset = np.asarray(origin)-rotation.apply(midpoint)
    return {n: dict(pos=(rotation.apply(p["pos"])+offset).tolist(),
                    quat=(rotation*Rotation.from_quat(p["quat"])).as_quat().tolist()) for n, p in frame.items()}


def point_pose(frame, name, local_point, local_rotation):
    pose = frame[name]
    rotation = Rotation.from_quat(pose["quat"])
    return rotation.apply(local_point)+pose["pos"], rotation*local_rotation


def build_motion(path, certificate, cfg, *, fps=12):
    if not certificate["passed"]:
        raise ValueError("Rehearsal requires a complete certified extraction")
    h, ring = path['template']['horseshoe'], path['template']['target_ring']
    if h.get('outline_power', 2.) != 2. or h.get('waist_depth', 0.) != 0. or 'terminal_tip_mm' in h or \
            ring.get('centerline_radii', [ring['centerline_radius']]*2) != [ring['centerline_radius']]*2:
        raise ValueError('Shape variants need geometry-derived grasp frames and a new robot IK/collision check; the baseline grasp recipe does not apply')
    digest = hashlib.sha256(json.dumps(path["frames"], sort_keys=True).encode()).hexdigest()
    if digest != certificate["frames_sha256"]:
        raise ValueError("Witness differs from the certified frames")
    if hashlib.sha256(json.dumps(path["template"], sort_keys=True).encode()).hexdigest() != certificate["template_sha256"]:
        raise ValueError("Witness template differs from its certificate")
    if path.get("scale", 2.) != certificate["scale"]:
        raise ValueError("Witness scale differs from its certificate")
    model = Kinematics(cfg.robot_control)
    from .robot_clearance import RobotClearance
    clearance = RobotClearance(cfg.robot_control, path["template"], path.get("scale", 2.))
    transfer_plans = []
    frames, phases, errors = [], [], []
    centers = np.asarray(path["centers"])
    if not np.allclose(centers, clearance.puzzle.centers, atol=1e-9, rtol=0):
        raise ValueError("Witness COMs differ from the collision geometry")
    source = path["frames"]
    end_fold = int(path["fold_end_index"])
    origin = np.array([0., .05, .20])  # relative to the ALOHA pair's local tabletop frame
    h = path["template"]["horseshoe"]
    unit = path.get("scale", 2.)/1000
    shoe_center = (path["template"]["chain"]["eye_to_link_center"]+h["eye_offset_x"]
                   +h["ellipse_radii"][0]*np.cos(np.radians(h["mouth_half_angle_deg"])))*unit
    points = [np.array([-shoe_center-.032, -.029*np.sqrt(3), 0.]),
              np.array([shoe_center+.032, .029*np.sqrt(3), 0.])]
    grasp_rotations = []
    for angle in (90, -90):
        x = np.array([np.cos(np.radians(angle)), np.sin(np.radians(angle)), 0.])
        y = np.array([0., 0., 1.])
        grasp_rotations.append(Rotation.from_matrix(np.column_stack([x, y, np.cross(x, y)])))

    def solve(side, p, r):
        error = model.solve(side, np.asarray(p), r)
        errors.append(error)
        if error[0] > .0005 or error[1] > .005:
            raise RuntimeError(f"Unreachable {side} target in {phases[-1]['name']}: {error}")

    def begin(name):
        phases.append(dict(name=name, frame=len(frames), time_s=len(frames)/fps))

    def transfer(side, target, held, source_index):
        end = model.q.copy()
        indices = slice(0, 6) if side == "left" else slice(8, 14)
        end[indices] = target
        trajectory, report = clearance.joint_transfer(model.q, end, side, held, fps=fps)
        report["start_frame"] = len(frames)
        transfer_plans.append(report)
        for q in trajectory:
            model.q = q.copy()
            append(held, source_index)

    def append(body_poses, source_index, targets=None):
        frames.append(dict(qpos=model.q.tolist(), bodies=body_poses,
                           source_index=float(source_index), stage=phases[-1]["name"],
                           grasp_targets=targets or {}))

    def follow_shoes(index):
        k = min(int(index), len(source)-2)
        frame = balanced_frame(interpolate(source[k], source[k+1], index-k), origin)
        targets = {}
        for i, side in enumerate(("left", "right")):
            p, r = point_pose(frame, f"horseshoe_{side}", points[i]-centers[i], grasp_rotations[i])
            solve(side, p, r)
            targets[side] = dict(pos=p.tolist(), quat=r.as_quat().tolist())
        model.q[[6, 7, 14, 15]] = .0123
        append(frame, index, targets)

    begin("预置双臂抓持")
    follow_shoes(0.)
    for _ in range(fps-1):
        append(frames[-1]["bodies"], 0., frames[-1]["grasp_targets"])
    split = next(i for i, f in enumerate(source[:end_fold])
                 if i > 500 and Rotation.from_quat(f["horseshoe_right"]["quat"]).as_matrix()[1, 0] > .02)
    for name, lo, hi, seconds in (("翻转马蹄", 0, split, 8), ("双臂折合", split, end_fold, 12)):
        begin(name)
        for index in np.linspace(lo, hi, seconds*fps+1)[1:]:
            follow_shoes(float(index))

    held = frames[-1]["bodies"]
    left_held = model.pose("left")
    right_held = model.pose("right")
    # Keep the left shoe supported while the right changes to a grasp of both
    # bands. The ungrasped shoe remains connected through the two chain links;
    # maintaining this pose during the transfer is a kinematic assumption.
    rp, rr = right_held
    band_left = np.array([-shoe_center, .058, 0.])
    band_right = np.array([shoe_center, .058, 0.])
    lp, _ = point_pose(held, "horseshoe_left", band_left-centers[0], grasp_rotations[0])
    rp_new, _ = point_pose(held, "horseshoe_right", band_right-centers[1], grasp_rotations[1])
    combined = (lp+rp_new)/2
    separation = abs(np.dot(rp_new-lp, rr.apply([0, 1, 0])))
    combined_opening = .0083+(separation+.008)/2
    if combined_opening > .037:
        raise RuntimeError("The combined support exceeds the ALOHA gripper opening")
    begin("双臂交接支撑")
    for u in np.linspace(0, 1, fps+1)[1:]:
        model.q[14:16] = (1-u)*.0123+u*.014
        append(held, end_fold)
    for u in np.linspace(0, 1, fps+1)[1:]:
        solve("right", rp-u*.025*rr.apply([1, 0, 0]), rr)
        append(held, end_fold)
    for u in np.linspace(0, 1, fps+1)[1:]:
        model.q[14:16] = (1-u)*.014+u*.037
        append(held, end_fold)
    x, y = np.array([np.sqrt(3)/2, -.5, 0.]), np.array([0., 0., -1.])
    rr = Rotation.from_quat(held["horseshoe_right"]["quat"])*Rotation.from_matrix(np.column_stack([x, y, np.cross(x, y)]))
    right_pre = combined-.035*rr.apply([1, 0, 0])
    right_trial = Kinematics(cfg.robot_control)
    error = right_trial.solve("right", right_pre, rr)
    if error[0] > .0005 or error[1] > .005:
        raise RuntimeError(f"Combined-grasp approach IK failed: {error}")
    right_home = np.asarray(cfg.robot_control.home.right[:6])
    transfer("right", right_home, held, end_fold)
    transfer("right", right_trial.q[8:14], held, end_fold)
    for u in np.linspace(0, 1, fps+1)[1:]:
        solve("right", (1-u)*right_pre+u*combined, rr)
        append(held, end_fold)
    for u in np.linspace(0, 1, fps+1)[1:]:
        model.q[14:16] = (1-u)*.037+u*combined_opening
        append(held, end_fold)
    begin("左臂换抓圆环")
    for u in np.linspace(0, 1, fps+1)[1:]:
        model.q[6:8] = (1-u)*.0123+u*.014
        append(held, end_fold)
    # Withdraw the released gripper before changing its orientation.
    for u in np.linspace(0, 1, fps+1)[1:]:
        solve("left", left_held[0]-u*.08*left_held[1].apply([1, 0, 0]), left_held[1])
        append(held, end_fold)
    for u in np.linspace(0, 1, fps+1)[1:]:
        model.q[6:8] = (1-u)*.014+u*.037
        append(held, end_fold)
    home = np.asarray(cfg.robot_control.home.left[:6])
    transfer("left", home, held, end_fold)

    radial = np.array([0., np.sin(np.radians(174)), -np.cos(np.radians(174))])
    normal = np.array([1., 0., 0.])
    turn = Rotation.from_rotvec(np.cross(normal, radial)*np.radians(-24))
    x, y = turn.apply(-radial), turn.apply(normal)
    ring_grasp = Rotation.from_matrix(np.column_stack([x, y, np.cross(x, y)]))
    ring_point = radial*path["template"]["target_ring"]["centerline_radius"]*unit-centers[-1]
    p, r = point_pose(held, "target_ring", ring_point, ring_grasp)
    # Find the approach using the same IK branch as the complete ring motion.
    trial = Kinematics(cfg.robot_control)
    initial_error = trial.solve("left", p, r)
    if max(initial_error) > .005:
        raise RuntimeError(f"Ring grasp IK failed: {initial_error}")
    # A lateral approach from below stays outside the two vertical shoe bands
    # and avoids the wrist limit encountered by approaching along tool X.
    approach = p+np.array([0., 0., -.04])
    approach_error = trial.solve("left", approach, r)
    if approach_error[0] > .0005 or approach_error[1] > .005:
        raise RuntimeError(f"Ring approach IK failed: {approach_error}")
    approach_q = trial.q[:6].copy()
    transfer("left", approach_q, held, end_fold)
    for u in np.linspace(0, 1, fps+1)[1:]:
        solve("left", (1-u)*approach+u*p, r)
        append(held, end_fold)
    for u in np.linspace(0, 1, fps+1)[1:]:
        model.q[6:8] = (1-u)*.037+u*.0111
        append(held, end_fold)

    begin("调整圆环并脱出")
    for index in np.linspace(end_fold, len(source)-1, 15*fps+1)[1:]:
        k = min(int(index), len(source)-2)
        frame = balanced_frame(interpolate(source[k], source[k+1], index-k), origin)
        p, r = point_pose(frame, "target_ring", ring_point, ring_grasp)
        solve("left", p, r)
        append(frame, index, {"left": dict(pos=p.tolist(), quat=r.as_quat().tolist())})
    begin("圆环已分离")
    for _ in range(2*fps):
        append(frames[-1]["bodies"], len(source)-1, frames[-1]["grasp_targets"])

    self_contacts, scene_violations = [], []
    for i, frame in enumerate(frames):
        model.data.qpos[:] = frame["qpos"]
        mujoco.mj_forward(model.model, model.data)
        for c in model.data.contact:
            if c.dist < -.0001:
                self_contacts.append(dict(frame=i, penetration_m=float(-c.dist),
                    a=model.model.body(model.model.geom_bodyid[c.geom1]).name,
                    b=model.model.body(model.model.geom_bodyid[c.geom2]).name))
        scene_violations.extend(dict(frame=i, stage=frame["stage"], **v)
                                for v in clearance.violations(frame["qpos"], frame["bodies"]))
    return dict(fps=fps, phases=phases, frames=frames,
        report=dict(scope="kinematic_robot_and_object_pose_rehearsal", physics_steps=0,
            dynamic_execution_verified=False, robot_execution_verified=False,
            contact_assignment_force_verified=False, robot_puzzle_collision_verified=False,
            source_frames_sha256=certificate["frames_sha256"], source_certificate_passed=True,
            source_template_sha256=certificate["template_sha256"], scene_scale=certificate["scale"],
            common_transform="Continuous half-rotation balancing; same rigid transform applied to all five puzzle parts",
            pad_center_gripper_link_m=PAD_CENTER.tolist(), paired_tabletop_origin=origin.tolist(),
            maximum_ik_position_error_m=float(np.max(errors, axis=0)[0]),
            maximum_ik_rotation_error_rad=float(np.max(errors, axis=0)[1]),
            maximum_joint_frame_step_rad=float(np.abs(np.diff(np.array([f["qpos"] for f in frames])[:, [0,1,2,3,4,5,8,9,10,11,12,13]], axis=0)).max()),
            sampled_robot_scene_clearance_passed=not scene_violations,
            sampled_robot_scene_violations=scene_violations,
            robot_scene_sampling_hz=fps, robot_puzzle_overlap_tolerance_m=.0003,
            robot_self_overlap_tolerance_m=.0001, table_overlap_tolerance_m=.001,
            transfer_plans=transfer_plans,
            sampled_robot_self_contacts=self_contacts, combined_finger_qpos_m=float(combined_opening)))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--witness", type=Path, default=ROOT/"runs/environment-solvability/horseshoe_ring/tutorial_solvable_v3")
    parser.add_argument("--output", type=Path, default=ROOT/"runs/environment_bootstrap/horseshoe_ring/aloha_full/robot_motion.json")
    parser.add_argument("--fps", type=int, default=12)
    args = parser.parse_args()
    with initialize_config_dir(config_dir=str(ROOT/"configs"), version_base="1.3"):
        cfg = compose(config_name="horseshoe_ring_aloha")
    motion = build_motion(json.loads((args.witness/"body_poses.json").read_text()),
        json.loads((args.witness/"certificate.json").read_text()), cfg, fps=args.fps)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(motion, ensure_ascii=False)+"\n")
    summary = {k: v for k, v in motion["report"].items() if k != "transfer_plans"}
    summary.update(frames=len(motion["frames"]), duration_s=len(motion["frames"])/args.fps)
    print(json.dumps(summary, indent=2, ensure_ascii=False), flush=True)
    if not summary["sampled_robot_scene_clearance_passed"]:
        raise SystemExit("Robot scene checks failed; do not publish this rehearsal")


if __name__ == "__main__":
    main()
