"""Propose compatible TCP traces, solve IK, then recover their scene parameters.

The inverse problem is constrained: grasp transforms and a known geometry family
are supplied. An arbitrary joint trace does not determine a unique puzzle CAD.
Continuous puzzle clearance is inherited through a verified positive similarity;
robot reachability and sampled scene clearance are checked independently.
"""
from __future__ import annotations

import argparse
from copy import deepcopy
import hashlib
import json
from pathlib import Path
import shutil

import numpy as np
from omegaconf import OmegaConf
from scipy.spatial.transform import Rotation
import trimesh

from .ik_trace import ROOT, SOURCE, OUTPUT as FIXED_OUTPUT, command_hash, export_trace
from .independent_motion import IndependentWitness, interpolate
from .robot_clearance import RobotClearance
from .robot_motion import Kinematics, balanced_frame
from .fixed_trace_variants import write_json

OUTPUT = ROOT/"runs/environment-solvability/horseshoe_ring/trace_scene_variants_v1"


def legacy_hash(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True).encode()).hexdigest()


def inverse_initial_similarity(before, after, tolerance=1e-6):
    """Recover s,R,t from two gripper poses and reject inconsistent constraints."""
    rotation = after["left"][1]*before["left"][1].inv()
    old = before["right"][0]-before["left"][0]
    new = after["right"][0]-after["left"][0]
    if np.linalg.norm(old) < 1e-8 or np.linalg.norm(new) < 1e-8:
        raise ValueError("Two distinct grasp anchors are required")
    scale = float(np.linalg.norm(new)/np.linalg.norm(old))
    shift = after["left"][0]-scale*rotation.apply(before["left"][0])
    error = float(np.linalg.norm(after["right"][0]-(scale*rotation.apply(before["right"][0])+shift)))
    angle = float((after["right"][1].inv()*rotation*before["right"][1]).magnitude())
    if max(error, angle) > tolerance:
        raise ValueError("The proposed arms do not define one compatible initial scene")
    return scale, rotation, shift, dict(position_residual_m=error, rotation_residual_rad=angle)


def relative_pose(body, tcp):
    rotation = Rotation.from_quat(body["quat"])
    return rotation.inv().apply(tcp[0]-body["pos"]), rotation.inv()*tcp[1]


def infer_body_from_grasp(tcp, local_grasp, scale):
    rotation = tcp[1]*local_grasp[1].inv()
    return dict(pos=(tcp[0]-rotation.apply(scale*local_grasp[0])).tolist(), quat=rotation.as_quat().tolist())


def wave(i, fold_end):
    return float(np.sin(np.pi*np.clip(i/fold_end, 0, 1))**2) if i < fold_end else 0.


def placement_weight(i, ring_start, final_start):
    """Bring the held assembly back toward the seed workspace during extraction."""
    u = float(np.clip((i-ring_start)/(final_start-ring_start), 0, 1))
    return 1-u*u*(3-2*u)


def scale_fingers(q, scale):
    # The fixed gripper is not scaled; its 8.3 mm rail-to-pad offset is retained.
    return np.clip(.0083+scale*(np.asarray(q)-.0083), .0083, .037)


def adjusted_tips(i, old, tips, proposal, left_release, ring_start, fps):
    result = dict(tips)
    if i > left_release+3*fps:
        u = np.clip((i-left_release-3*fps)/(ring_start-left_release-5*fps), 0, 1)
        u = u*u*(3-2*u)
        ring = old["bodies"]["target_ring"]
        rr = Rotation.from_quat(ring["quat"])
        delta = rr*Rotation.from_euler("x", proposal["ring_grasp_shift_deg"]*u, degrees=True)*rr.inv()
        p, r = tips["left"]
        result["left"] = np.asarray(ring["pos"])+delta.apply(p-ring["pos"]), delta*r
    return result


def common_pose(i, before_left, adjusted_left, origin, center, r0, scale, proposal, fold_end, ring_start, final_start, fps):
    weight = placement_weight(i, ring_start, min(final_start, ring_start+10*fps))
    start_r = Rotation.from_euler("x", proposal["fold_roll_deg"]*wave(i, fold_end), degrees=True)*r0
    # Near the end, anchor the extracting TCP to its known reachable seed pose.
    # Move/rotate the supported assembly to accommodate the new size and grasp.
    end_r = before_left[1]*adjusted_left[1].inv()
    end_center = before_left[0]-end_r.apply(scale*(adjusted_left[0]-origin))
    rotation = end_r*Rotation.from_rotvec((end_r.inv()*start_r).as_rotvec()*weight)
    return weight*center+(1-weight)*end_center, rotation


def load_seed(source):
    source = Path(source)
    motion = json.loads((source/"robot_motion.json").read_text())
    cfg = OmegaConf.load(source/"config.yaml")
    geometry = json.loads((source/"geometry_evidence/body_poses.json").read_text())
    certificate = json.loads((source/"geometry_evidence/certificate.json").read_text())
    if not certificate["passed"] or legacy_hash(geometry["frames"]) != certificate["frames_sha256"]:
        raise ValueError("Seed geometric witness differs from its positive certificate")
    if legacy_hash(geometry["template"]) != certificate["template_sha256"] or geometry["scale"] != certificate["scale"]:
        raise ValueError("Seed geometry differs from its certificate")
    origin = np.asarray(motion["report"]["paired_tabletop_origin"])
    kin = Kinematics(cfg.robot_control)
    tips = []
    last_index = -1.
    for frame in motion["frames"]:
        index = frame["source_index"]
        if index < last_index:
            raise ValueError("The source witness index must be monotonic")
        last_index = index
        k = min(int(index), len(geometry["frames"])-2)
        reference = balanced_frame(interpolate(geometry["frames"][k], geometry["frames"][k+1], index-k), origin)
        for name, body in frame["bodies"].items():
            if (np.linalg.norm(np.asarray(reference[name]["pos"])-body["pos"]) > 1e-9 or
                (Rotation.from_quat(reference[name]["quat"]).inv()*Rotation.from_quat(body["quat"])).magnitude() > 1e-9):
                raise ValueError("Saved object motion is not a sample of the certified path")
        kin.q = np.asarray(frame["qpos"])
        tips.append({side: kin.pose(side) for side in ("left", "right")})
    return motion, cfg, geometry, tips


def generate(proposal, seed, output):
    motion, cfg, geometry, seed_tips = seed
    output = Path(output)/proposal["id"]
    output.mkdir(parents=True, exist_ok=True)
    write_json(output/"proposal.json", proposal)
    phases = {p["name"]: p["frame"] for p in motion["phases"]}
    fold_end = phases["双臂交接支撑"]
    left_release = phases["左臂换抓圆环"]
    ring_start = phases["调整圆环并脱出"]
    final_start = phases["圆环已分离"]
    origin = np.asarray(motion["report"]["paired_tabletop_origin"])
    rot0 = Rotation.from_euler("z", proposal["yaw_deg"], degrees=True)
    scale = proposal["tcp_scale"]
    center = origin+np.asarray(proposal["translation_m"])
    kin = Kinematics(cfg.robot_control)
    kin.q = np.asarray(motion["frames"][0]["qpos"]).copy()
    tips, joint_trace, errors = [], [], []
    for i, old in enumerate(motion["frames"]):
        # The known solution identifies the joint branch at every sample. A
        # purely previous-frame seed can switch branches through an unladen
        # transfer's wrist singularity and fail much later in the extraction.
        kin.q = np.asarray(old["qpos"], dtype=float).copy()
        adjusted = adjusted_tips(i, old, seed_tips[i], proposal, left_release, ring_start, motion["fps"])
        current_center, turn = common_pose(i, seed_tips[i]["left"], adjusted["left"], origin, center, rot0, scale,
            proposal, fold_end, ring_start, final_start, motion["fps"])
        targets = {}
        for side in ("left", "right"):
            p, r = adjusted[side]
            targets[side] = (current_center+turn.apply(scale*(p-origin)), turn*r)
            err = kin.solve(side, *targets[side])
            errors.append(err)
            if err[0] > 1e-5 or err[1] > 1e-5:
                report = dict(passed=False, stage="ik_rejected", frame=i, phase=old["stage"], side=side,
                              position_error_m=err[0], rotation_error_rad=err[1], proposal=proposal)
                write_json(output/"result.json", report)
                return report
        kin.q[[6, 7, 14, 15]] = scale_fingers(np.asarray(old["qpos"])[[6, 7, 14, 15]], scale)
        joint_trace.append(kin.q.copy())
        tips.append({side: kin.pose(side) for side in ("left", "right")})
    q = np.asarray(joint_trace)
    step = float(np.abs(np.diff(q[:, [0,1,2,3,4,5,8,9,10,11,12,13]], axis=0)).max())
    # Infer the scene only after a complete reachable robot trace exists.
    recovered_scale, recovered_r, shift, fit = inverse_initial_similarity(seed_tips[0], tips[0])
    recovered_center = recovered_scale*recovered_r.apply(origin)+shift
    family = FIXED_OUTPUT/"variants"/proposal["chain_family"]
    family_report = json.loads((family/"compatibility.json").read_text())
    family_certificate = json.loads((family/"geometric_certificate.json").read_text())
    template = json.loads((family/"template.json").read_text())
    if (not family_report["passed"] or not family_certificate["passed"] or
        family_certificate["frames_sha256"] != legacy_hash(geometry["frames"]) or
        family_certificate["template_sha256"] != legacy_hash(template)):
        raise ValueError("The selected geometry family lacks a matching complete certificate")
    original_model = IndependentWitness(template, geometry["scale"])
    template["template_id"] = "horseshoe_trace_scene_"+proposal["id"]
    template["geometry_status"] = "Scene inferred from a varied robot trace; numerical geometry evidence stored with this instance"
    scene_scale = geometry["scale"]*recovered_scale
    puzzle = IndependentWitness(template, scene_scale)
    cover_error = max(float(np.abs(new.vertices-old.vertices*recovered_scale).max())
                      for old, new in zip(original_model.meshes, puzzle.meshes))
    if cover_error > 1e-10:
        raise ValueError("The new conservative collision cover is not the certified similarity")
    frames, common_transforms = [], []
    for i, old in enumerate(motion["frames"]):
        adjusted = adjusted_tips(i, old, seed_tips[i], proposal, left_release, ring_start, motion["fps"])
        current_center, turn = common_pose(i, seed_tips[i]["left"], adjusted["left"], origin, recovered_center,
            recovered_r, recovered_scale, proposal, fold_end, ring_start, final_start, motion["fps"])
        common_transforms.append(dict(center_m=current_center.tolist(), rotation_xyzw=turn.as_quat().tolist(),
                                      source_index=old["source_index"]))
        bodies = {name: dict(pos=(current_center+turn.apply(recovered_scale*(np.asarray(pose["pos"])-origin))).tolist(),
                            quat=(turn*Rotation.from_quat(pose["quat"])).as_quat().tolist())
                  for name, pose in old["bodies"].items()}
        frames.append(dict(qpos=joint_trace[i].tolist(), bodies=bodies, stage=old["stage"],
            source_index=old["source_index"], grasp_targets={s: dict(pos=tips[i][s][0].tolist(), quat=tips[i][s][1].as_quat().tolist())
                                                           for s in ("left", "right")}))
    checker = RobotClearance(cfg.robot_control, template, scene_scale)
    transfer_repairs = []
    for transfer in motion["report"]["transfer_plans"]:
        a, count, side = transfer["start_frame"], transfer["frames"], transfer["side"]
        b = a+count
        columns = slice(0, 6) if side == "left" else slice(8, 14)
        jump = float(np.abs(np.diff(np.asarray(joint_trace[a-1:b])[:, columns], axis=0)).max())
        bad = any(checker.violations(frames[i]["qpos"], frames[i]["bodies"], side=side, first_only=True) for i in range(a, b))
        if jump <= .2 and not bad:
            continue
        try:
            trajectory, repair = checker.joint_transfer(joint_trace[a-1], joint_trace[b-1], side, frames[a]["bodies"], fps=motion["fps"])
        except RuntimeError as exc:
            report = dict(passed=False, stage="transfer_replanning_rejected", frame=a, side=side, reason=str(exc), proposal=proposal)
            write_json(output/"result.json", report)
            return report
        path_q = np.vstack([joint_trace[a-1], trajectory])
        lengths = np.r_[0., np.cumsum(np.linalg.norm(np.diff(path_q[:, columns], axis=0), axis=1))]
        for i, distance in enumerate(np.linspace(0, lengths[-1], count+1)[1:], a):
            value = np.array([np.interp(distance, lengths, path_q[:, j]) for j in range(16)])
            joint_trace[i] = value
            frames[i]["qpos"] = value.tolist()
            kin.q = value
            tips[i] = {s: kin.pose(s) for s in ("left", "right")}
            frames[i]["grasp_targets"] = {s: dict(pos=tips[i][s][0].tolist(), quat=tips[i][s][1].as_quat().tolist()) for s in tips[i]}
        repair.update(start_frame=a, output_frames=count)
        transfer_repairs.append(repair)
    q = np.asarray(joint_trace)
    step = float(np.abs(np.diff(q[:, [0,1,2,3,4,5,8,9,10,11,12,13]], axis=0)).max())
    if step > .35:
        k, j = np.unravel_index(np.abs(np.diff(q[:, [0,1,2,3,4,5,8,9,10,11,12,13]], axis=0)).argmax(), (len(q)-1, 12))
        report = dict(passed=False, stage="joint_branch_jump", maximum_step_rad=step, frame=int(k+1),
                      arm_joint_column=int(j), phase=motion["frames"][k+1]["stage"], proposal=proposal)
        write_json(output/"result.json", report)
        return report
    # Check the inverse grasp constraints over every held segment, not just t=0.
    grasps = {s: relative_pose(motion["frames"][0]["bodies"]["horseshoe_"+s], seed_tips[0][s]) for s in ("left", "right")}
    support = {n: relative_pose(motion["frames"][left_release-1]["bodies"][n], seed_tips[left_release-1]["right"])
               for n in ("horseshoe_left", "horseshoe_right")}
    ring_grasp = relative_pose(motion["frames"][ring_start-1]["bodies"]["target_ring"], seed_tips[ring_start-1]["left"])
    ring_delta = Rotation.from_euler("x", proposal["ring_grasp_shift_deg"], degrees=True)
    ring_grasp = ring_delta.apply(ring_grasp[0]), ring_delta*ring_grasp[1]
    reconstruction_errors = []
    for i, frame in enumerate(frames):
        held = []
        if i < fold_end:
            held.extend((s, "horseshoe_"+s, grasps[s]) for s in ("left", "right"))
        elif i < left_release:
            held.append(("left", "horseshoe_left", grasps["left"]))
        if i >= left_release:
            held.extend(("right", n, g) for n, g in support.items())
        if i >= ring_start-1:
            held.append(("left", "target_ring", ring_grasp))
        for side, name, grasp in held:
            recovered = infer_body_from_grasp(tips[i][side], grasp, recovered_scale)
            target = frame["bodies"][name]
            reconstruction_errors.append((float(np.linalg.norm(np.asarray(recovered["pos"])-target["pos"])),
                float((Rotation.from_quat(recovered["quat"]).inv()*Rotation.from_quat(target["quat"])).magnitude())))
    reconstruction = np.max(reconstruction_errors, axis=0)
    if reconstruction.max() > 1e-5:
        raise ValueError(f"Inverse grasp constraints disagree: {reconstruction}")
    violations = []
    minimum_table_height = float("inf")
    for i, frame in enumerate(frames):
        violations.extend(dict(frame=i, **v) for v in checker.violations(frame["qpos"], frame["bodies"]))
        for name, mesh in zip(puzzle.names, puzzle.meshes):
            pose = frame["bodies"][name]
            z = Rotation.from_quat(pose["quat"]).apply(trimesh.bounds.corners(mesh.bounds))[:, 2]+pose["pos"][2]
            minimum_table_height = min(minimum_table_height, float(z.min()))
    goal = puzzle.goal(frames[-1]["bodies"])
    minimum_bound = family_certificate["minimum_clearance_lower_bound_m"]*recovered_scale
    passed = not violations and minimum_table_height > .001 and goal["separated"]
    replay = dict(fps=motion["fps"], phases=motion["phases"], frames=frames,
        report=dict(scope="inverse_scene_kinematic_rehearsal", physics_steps=0, dynamic_execution_verified=False,
            robot_execution_verified=False, source_template_sha256=legacy_hash(template), scene_scale=scene_scale,
            source_certificate_passed=True, source_frames_sha256=family_certificate["frames_sha256"],
            paired_tabletop_origin=recovered_center.tolist(),
            sampled_robot_scene_clearance_passed=not violations, sampled_robot_scene_violations=violations,
            maximum_ik_position_error_m=float(np.max(errors, axis=0)[0]),
            maximum_ik_rotation_error_rad=float(np.max(errors, axis=0)[1]), maximum_joint_frame_step_rad=step,
            transfer_plans=transfer_repairs,
            inverse_grasp_max_position_error_m=float(reconstruction[0]), inverse_grasp_max_rotation_error_rad=float(reconstruction[1])))
    scene = dict(inferred_from="FK of the proposed complete IK trace's two initial grasp anchors",
        scale_ratio=recovered_scale, scene_scale=scene_scale, rotation_xyzw=recovered_r.as_quat().tolist(),
        translation_m=shift.tolist(), puzzle_origin_in_robot_mount_m=recovered_center.tolist(),
        fit=fit, chain_family=proposal["chain_family"], template="template.json",
        inverse_problem_note="Initial TCPs infer pose and scale; chain dimensions are selected from independently certified families, not uniquely determined by IK")
    proof = dict(passed=bool(minimum_bound > 0 and goal["separated"]),
        scope="Continuous puzzle clearance transferred under one common positive similarity at every time",
        source_certificate="geometry_evidence/source_certificate.json", source_template="geometry_evidence/source_template.json",
        source_body_poses="geometry_evidence/body_poses.json", template_sha256=legacy_hash(template),
        robot_frames_sha256=legacy_hash(frames), scale_ratio=recovered_scale,
        cover_similarity_max_error_m=cover_error, minimum_clearance_lower_bound_m=minimum_bound, goal=goal,
        interpolation="Source independent-body COM/SLERP interpolation and source_index time map, followed by the smooth common similarity; do not substitute direct interpolation of exported scene COM samples",
        common_transform=dict(file="common_transforms.json", seed_center_m=origin.tolist(),
            interpolation="Between samples: interpolate center linearly, rotation by shortest SLERP, and source_index linearly through the full dense source witness"),
        geometric_argument="All five puzzle bodies receive the same rotation/translation and positive scale; every pairwise surface distance equals source distance times scale",
        robot_continuous_collision_verified=False, dynamic_execution_verified=False)
    report = dict(passed=passed, stage="qualified" if passed else "scene_clearance_rejected", proposal=proposal,
        source_command_sha256=command_hash(motion), variant_command_sha256=command_hash(replay),
        command_changed=command_hash(motion) != command_hash(replay),
        maximum_arm_joint_change_rad=float(np.abs(q[:, [0,1,2,3,4,5,8,9,10,11,12,13]]-np.asarray([f["qpos"] for f in motion["frames"]])[:, [0,1,2,3,4,5,8,9,10,11,12,13]]).max()),
        scene=scene, geometry=proof, robot=replay["report"], minimum_sampled_puzzle_table_height_m=minimum_table_height,
        straight_pull_both_directions_blocked=family_report["straight_pull_both_directions_blocked"],
        physical_execution_verified=False)
    write_json(output/"template.json", template)
    write_json(output/"inferred_scene.json", scene)
    write_json(output/"geometry_certificate.json", proof)
    write_json(output/"common_transforms.json", common_transforms)
    (output/"robot_motion.json").write_text(json.dumps(replay, ensure_ascii=False)+"\n")
    write_json(output/"result.json", report)
    evidence = output/"geometry_evidence"
    evidence.mkdir(exist_ok=True)
    shutil.copyfile(family/"geometric_certificate.json", evidence/"source_certificate.json")
    shutil.copyfile(family/"template.json", evidence/"source_template.json")
    family_witness = deepcopy(geometry)
    family_witness["template"] = json.loads((family/"template.json").read_text())
    family_witness["centers"] = original_model.centers.tolist()
    (evidence/"body_poses.json").write_text(json.dumps(family_witness)+"\n")
    shutil.copyfile(family/"straight_pull_controls.json", evidence/"straight_pull_controls.json")
    (evidence/"certificate.json").write_text(json.dumps(proof)+"\n")
    derived_cfg = deepcopy(cfg)
    derived_cfg.task.template_path = str((output/"template.json").resolve())
    derived_cfg.task.variant = template["template_id"]
    derived_cfg.task.scale = scene_scale
    world_center = np.asarray(cfg.env.robot_mount.pos)+recovered_center
    derived_cfg.task.center_xy_m = world_center[:2].tolist()
    derived_cfg.task.yaw_deg = float(recovered_r.as_euler("xyz", degrees=True)[2])
    bottom = min(recovered_r.apply(b.visual.vertices)[:, 2].min() for b in puzzle.assembly.bodies)
    derived_cfg.task.initial_lift_m = float(recovered_center[2]+bottom-derived_cfg.task.initial_floor_clearance_m)
    derived_cfg.run.output = str(output.resolve())
    OmegaConf.save(derived_cfg, output/"config.yaml", resolve=True)
    export_trace(output, output)
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, default=SOURCE)
    parser.add_argument("--output", type=Path, default=OUTPUT)
    parser.add_argument("--proposals", type=Path, required=True)
    args = parser.parse_args()
    seed = load_seed(args.source)
    args.output.mkdir(parents=True, exist_ok=True)
    results = []
    for proposal in json.loads(args.proposals.read_text()):
        result = generate(proposal, seed, args.output)
        results.append(result)
        print(f"{proposal['id']}: {result['stage']}", flush=True)
    write_json(args.output/"summary.json", dict(results=results, qualified=sum(r["passed"] for r in results),
        scope="Trajectory proposals, inverse scene fit, continuous puzzle proof and sampled robot checks; no force execution"))
    from .inverse_review import write_review
    write_review(args.output)


if __name__ == "__main__":
    main()
