"""Owner-side coupled separation route for a verified Claws object witness.

Inputs are the live pregrasp state (both hands holding), the frozen object
witness and the frozen piece meshes. Output is a sampled joint-space route
with per-sample collision, table and joint-limit checks. No pose is set and no
physics is advanced here; execution and its audit are separate.
"""
from pathlib import Path

import numpy as np
from scipy.spatial.transform import Rotation

from topogym.planning.rigid_reference.feedback import body_pose, relative_pose
from topogym.planning.rigid_reference.geometry import interpolate, pose_dict
from topogym.utils.io import to_jsonable, write_json_atomic
from .kinematics import ClawsIK, CoupledClawsIK, densify
from .object_oracle import frozen_problem, separated_poses


def ownership_for(task):
    target, = task.placement_targets
    other, = task.placement_remainder
    return {target: "left", other: "right"}


def plan_relief(target_mesh, other_mesh, current, authored, *, step_m, step_rad, seed=0, margin_m=.0005):
    """Open a just-bound grasp that sagged into contact: pick the nearest nearby relative pose with clearance,
    require the clearance to grow monotonically along that short move, then certify the join to the authored start.
    The pieces may touch at the measured start, so that first move is a monotone-clearance sample, not a certificate."""
    from topogym.planning.rigid_reference.geometry import RigidPathChecker, interpolate
    from topogym.planning.rigid_reference.search import check_path
    probe = RigidPathChecker(target_mesh, other_mesh)
    checker = RigidPathChecker(target_mesh, other_mesh, margin_m=margin_m)
    start_gap = probe.clearance(current)
    direct = check_path(checker, [current, authored])
    if start_gap > margin_m and direct["passed"]:
        return densify([current, authored], step_m=step_m, step_rad=step_rad)[:-1], dict(kind="direct", start_clearance_m=start_gap, certificate=direct)
    rng = np.random.default_rng(seed+17)
    best = None
    for k in range(600):
        scale = (.004, .002, .001)[min(2, k*3//600)]
        cand = (current[0]+rng.normal(0, scale, 3), Rotation.from_rotvec(rng.normal(0, scale*4, 3))*current[1])
        gap = probe.clearance(cand)
        if gap < margin_m*2:
            continue
        samples = [probe.clearance(interpolate(current, cand, u)) for u in np.linspace(0., 1., 9)]
        if any(b < a-1e-6 for a, b in zip(samples, samples[1:])):
            continue
        motion = np.linalg.norm(cand[0]-current[0])+probe.radius*(cand[1]*current[1].inv()).magnitude()
        if best is None or motion < best[0]:
            best = (motion, cand, gap, samples)
    if best is None:
        raise ValueError("No monotone-clearance departure from the measured grasp state")
    motion, departure, gap, samples = best
    join = check_path(checker, [departure, authored])
    if not join["passed"]:
        raise ValueError("Departure pose does not join the authored start with a certified edge")
    poses = densify([current, departure], step_m=step_m, step_rad=step_rad)[:-1]+densify([departure, authored], step_m=step_m, step_rad=step_rad)[:-1]
    return poses, dict(kind="departure_then_join", start_clearance_m=start_gap, departure_clearance_m=gap,
                       departure_motion_m=float(motion), monotone_samples=samples, join_certificate=join)


def plan_held_route(env, witness, output, *, step_m=.004, step_deg=2., progress=None, measured=False,
                    relief_translation_m=.008, relief_rotation_rad=np.deg2rad(5.)):
    """measured=True plans from the live post-acquisition state: the pieces may have sagged in the
    fingers before the assisted grasp bound, so a short relief segment returns the relative pose to the
    authored start before the certified route. Grasp transforms are measured from that live state."""
    output = Path(output)
    task = env._task
    variation = task.variation_id.removeprefix("interlocked_claws_")
    frozen_task, meshes, poses, table, frozen = frozen_problem(output, variation=variation, seed=task.seed)
    if frozen_task.instance_id != task.instance_id or witness["instance_id"] != task.instance_id:
        raise ValueError("Live instance, frozen geometry and witness disagree")
    if witness["status"] != "object_witness_verified":
        raise ValueError("A verified object witness is required")
    if not measured and env._world.physics_step != 0:
        raise ValueError("Route planning must start from the authored pregrasp state")
    target, other = frozen["target"], frozen["other"]
    ownership = ownership_for(task)
    kin = ClawsIK(env, meshes, ownership)
    live = kin.initial_pieces
    authored = relative_pose(poses[target], poses[other])
    relief, relief_report = [], None
    if measured:
        current = relative_pose(live[target], live[other])
        deviation = (float(np.linalg.norm(current[0]-authored[0])), float((current[1].inv()*authored[1]).magnitude()))
        if deviation[0] > relief_translation_m or deviation[1] > relief_rotation_rad:
            raise ValueError(f"Measured relative pose deviates too far from the authored start: {deviation}")
        relief, relief_report = plan_relief(meshes[target], meshes[other], current, authored, step_m=step_m/2,
                                            step_rad=np.deg2rad(step_deg/2), seed=task.seed)
    else:
        for name in (target, other):
            if max(np.linalg.norm(live[name][0]-poses[name][0]), (live[name][1].inv()*poses[name][1]).magnitude()) > 1e-6:
                raise ValueError("Live piece pose differs from the frozen authored pose")
    report = dict(status="planning", instance_id=task.instance_id, variation=variation, seed=task.seed,
                  start="measured_after_acquisition" if measured else "authored_birth",
                  measured_relative_deviation=deviation if measured else None, relief_samples=len(relief), relief=relief_report,
                  ownership=ownership, grasp_offsets={s: pose_dict(o) for s, o in kin.offsets.items()},
                  live_pieces={n: pose_dict(p) for n, p in live.items()},
                  initial_qpos=kin.seed.tolist(), physical_execution_verified=False, task_success=False)
    write_json_atomic(output/"held_plan.json", report)
    # 1. coupled separation along the certified relative path (after the optional relief segment)
    route_poses = [body_pose(p) for p in witness["route"]["relative_poses"]]
    dense, fractions = densify(route_poses, step_m=step_m, step_rad=np.deg2rad(step_deg), with_fraction=True)
    relative = relief+dense
    fractions = [0.]*len(relief)+fractions
    coupled = CoupledClawsIK(kin, target, other)
    if variation == "hard":
        # Pure anchor mode: the minimal correction of the recorded ALOHA motion that satisfies the scaled
        # relative path. No level/upright shaping (they introduced branch jumps); continuity and wrist load
        # are inherited from the recording, as in the historical A0 replay.
        coupled.wrist_weight, coupled.level_weight, coupled.anchor_weight = 0., 0., .06
        coupled.center_radius = np.array([.08, .08, .06])
        report["planner_mode"] = "recorded_anchor"
    level_hints = None
    hints = witness.get("route_provenance", {}).get("target_world_orientation_hints_wxyz")
    if hints:
        # Recorded world orientation hints (hard): nearest route pose -> hint, then per densified sample.
        hint_rotations = [Rotation.from_quat(np.roll(h, -1)) for h in hints]
        level_hints = []
        for f in fractions:
            i = int(min(len(hint_rotations)-2, max(0, np.floor(f)))); u = float(np.clip(f-i, 0., 1.))
            level_hints.append(Rotation.from_rotvec(u*(hint_rotations[i+1]*hint_rotations[i].inv()).as_rotvec())*hint_rotations[i])
        report["level_hints"] = "recorded world orientation of the target piece (per sample, nearest route pose)"
    seeds = centers = None
    prov = witness.get("route_provenance", {})
    if prov.get("recorded_qpos_seeds"):
        qs = np.asarray(prov["recorded_qpos_seeds"], float); cs = np.asarray(prov["recorded_hand_midpoints_m"], float)
        def lerp(table, f):
            i = int(min(len(table)-2, max(0, np.floor(f)))); u = float(np.clip(f-i, 0., 1.))
            return (1-u)*table[i]+u*table[i+1]
        seeds = [lerp(qs, f) for f in fractions]
        centers = [lerp(cs, f) for f in fractions]
        report["recorded_seeds"] = "recorded ALOHA qpos (first sample / retry seeds) and recorded hand midpoints as workspace centres, interpolated along the route"
    separation = coupled.plan(relative, progress=progress, pair_check_from=len(relief), level_hints=level_hints,
                              seeds=seeds, centers=centers)
    report.update(separation=dict(samples=len(relative), passed=separation["passed"], failure=separation["failure"],
                                  scope=separation["scope"]), separation_rows=separation["rows"])
    write_json_atomic(output/"held_plan.json", report)
    if not separation["passed"]:
        report["status"] = "separation_ik_failed"
        write_json_atomic(output/"held_plan.json", report)
        return report
    last = separation["rows"][-1]
    q = np.asarray(last["qpos"])
    pieces = {n: body_pose(p) for n, p in last["pieces"].items()}
    reached, _, metrics = separated_poses(frozen_task, pieces)
    report.update(status="held_ik_route_found" if reached else "separation_goal_rejected",
                  separation_goal=metrics, ik_queries=kin.queries,
                  limitations=["Sampled native IK/FCL checks; no continuous joint-space certificate",
                               "Passive finger geometry and grasp transforms measured at planning start",
                               "No contact dynamics or Task success claim"])
    write_json_atomic(output/"held_plan.json", report)
    return report
