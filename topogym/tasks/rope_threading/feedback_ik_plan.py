"""Offline R2 handoff witness from a measured failure snapshot.

This is NOT a runtime controller or a FEM rollout. The left pivot changes the
free tail in unknown ways. The rigid-tail prediction below is explicitly a
planning hypothesis; execution must pause, observe again, and rebuild the
right approach. All coordinates passed to the planner are robot-model metres.
"""
import argparse
import hashlib
import json
from pathlib import Path

import mujoco
import numpy as np
from omegaconf import OmegaConf
from scipy.spatial.transform import Rotation, Slerp

from .ik_plan import ROOT, REFERENCE, offline_controller
from .reference_actions import ReferenceThreadingActions
from .reference_ik import MarginAwareThreadingIK
from .reference_preflight import model_with_fixtures


GRASP_OFFSET = np.array([.14537, 0., .00125])
PIVOT_AXIS = np.array([-.6, .8, 0.])
R2_CENTER = np.array([.01, .17, .3109])
R2_NORMAL = np.array([.8, .6, 0.])
JOIN_SOURCE_S = 224.3845


def smoothstep(u):
    return u**3*(10.+u*(-15.+6.*u))


def pivot_pose(position, orientation, anchor, angle_rad):
    """Rotate the hand about a material point, preserving that point exactly."""
    local = orientation.inv().apply(np.asarray(anchor)-position)
    rotated = Rotation.from_rotvec(PIVOT_AXIS*angle_rad)*orientation
    return np.asarray(anchor)-rotated.apply(local), rotated


def grasp_pose(tip, tangent, azimuth_deg=28.):
    """Choose an approach around the measured tail; local Z follows -tangent.

    The finger-symmetric +pi tool orientation leaves room for the next pose.
    IK must separately select the negative wrist-bend branch of that pose to
    join the source joints continuously; matching hand poses alone is not enough.
    """
    tangent = np.asarray(tangent, dtype=float)
    if tangent.shape != (3,) or not np.isfinite(tangent).all() or np.linalg.norm(tangent) < 1e-8:
        raise ValueError("A finite, nonzero measured tail tangent is required")
    tangent = tangent/np.linalg.norm(tangent)
    base = np.cross(tangent, [0., 1., 0.])
    if np.linalg.norm(base) < 1e-6:
        raise ValueError("Tail is outside this approach family's orientation domain")
    base /= np.linalg.norm(base)
    angle = np.deg2rad(azimuth_deg)
    x = base*np.cos(angle)+np.cross(tangent, base)*np.sin(angle)
    rotation = (Rotation.from_matrix(np.column_stack([x, np.cross(tangent, x), tangent]))
                *Rotation.from_rotvec([np.pi, 0., 0.]))
    return np.asarray(tip)-rotation.apply(GRASP_OFFSET), rotation


def carry_tip(start, end, fraction, detour=(.04, -.04, 0.)):
    """Carry the material tip around R3, retaining its R2 exit-side sign."""
    return ((1-fraction)*np.asarray(start)+fraction*np.asarray(end)
            +np.asarray(detour)*np.sin(np.pi*fraction)**2)


def snapshot_from_run(run, cfg):
    if not np.allclose(cfg.env.robot_mount.euler, 0.):
        raise ValueError("Snapshot conversion currently requires an unrotated mount")
    last = json.loads((run/"contact_trace.json").read_text())[-1]
    with np.load(run/"trajectory.npz") as trajectory, np.load(run/"mesh.npz") as mesh:
        centers = trajectory["final_nodes"][mesh["material_rings"]].mean(1)
    if centers.shape != (801, 3):
        raise ValueError("Expected the recorded 10-subdivision, 81-material-point rope")
    centers -= np.asarray(cfg.env.robot_mount.pos)
    qpos = np.concatenate([np.r_[last["robot"][side]["arm_qpos"],
                                    last["robot"][side]["finger_qpos"]]
                           for side in ("left", "right")])
    tangent = centers[-1]-centers[-11]
    tangent /= np.linalg.norm(tangent)
    return dict(qpos=qpos.tolist(), anchor=centers[770].tolist(),
                tip=centers[-1].tolist(), tangent=tangent.tolist())


def plan_handoff(cfg, snapshot, join_qpos, *, dt=.02, pivot_deg=6., azimuth_deg=28.,
                 post_pivot_tip=None, post_pivot_tangent=None):
    """Return a conditional trajectory, with mandatory execution gates.

    Passing measured post-pivot geometry replaces the prediction for approach
    planning only. The saved prefix remains an offline witness, not a command
    to execute a second pivot. The capture aperture and tip-to-hand offset must
    also be measured before the post-capture path is rebuilt at runtime.
    """
    if not np.isfinite([dt, pivot_deg, azimuth_deg]).all() or not 0 < dt <= .05:
        raise ValueError("Planning sample period must be in (0, .05] seconds")
    if (post_pivot_tip is None) != (post_pivot_tangent is None):
        raise ValueError("Supply both post-pivot tip position and tangent")
    q = np.asarray(snapshot["qpos"], dtype=float).copy()
    anchor, tip, tangent = [np.asarray(snapshot[k], dtype=float) for k in ("anchor", "tip", "tangent")]
    if q.shape != (16,) or not np.isfinite(np.r_[q, anchor, tip, tangent]).all():
        raise ValueError("Invalid handoff snapshot")
    ik = MarginAwareThreadingIK(None, offline_controller(cfg, q))
    p_left, r_left = ik.pose("left", q[:6])
    rotation = Rotation.from_rotvec(PIVOT_AXIS*np.deg2rad(pivot_deg))
    predicted = post_pivot_tip is None
    tip_after = anchor+rotation.apply(tip-anchor) if predicted else np.asarray(post_pivot_tip)
    tangent_after = rotation.apply(tangent) if predicted else np.asarray(post_pivot_tangent)
    grasp_p, grasp_r = grasp_pose(tip_after, tangent_after, azimuth_deg)
    grasp_q = ik.solve("right", grasp_p, grasp_r.as_quat(scalar_first=True),
                       seed=[-.7, .2, -.4, -2.3, -1.4, -1.])
    pre_q = ik.solve("right", grasp_p-.06*grasp_r.apply([1., 0., 0.]),
                     grasp_r.as_quat(scalar_first=True), seed=grasp_q)
    rows, times, names, stages = [q.copy()], [0.], ["initial"], []
    anchor_errors = []

    def segment(name, duration, command, gate=None):
        start = times[-1]
        for local_time in np.linspace(0., duration, int(np.ceil(duration/dt))+1)[1:]:
            command(float(smoothstep(local_time/duration)))
            rows.append(q.copy())
            times.append(start+float(local_time))
            names.append(name)
        stages.append(dict(name=name, start_s=start, end_s=times[-1], gate_after=gate))

    def joints(indices, goal):
        initial = q[indices].copy()
        return lambda u: q.__setitem__(indices, initial*(1-u)+np.asarray(goal)*u)

    def cartesian(side, position, orientation):
        indices = slice(0, 6) if side == "left" else slice(8, 14)
        q[indices] = ik.solve(side, position, orientation.as_quat(scalar_first=True), seed=q[indices])

    segment("right_narrow_open", .5, joints(slice(14, 16), [.018, .018]))
    left_local = r_left.inv().apply(anchor-p_left)

    def pivot(u):
        p, r = pivot_pose(p_left, r_left, anchor, np.deg2rad(pivot_deg)*u)
        cartesian("left", p, r)
        actual_p, actual_r = ik.pose("left", q[:6])
        anchor_errors.append(float(np.linalg.norm(actual_p+actual_r.apply(left_local)-anchor)))

    segment("left_pivot_about_node77", 3., pivot,
            "STOP: reobserve actual free tip/tangent and replan; rigid prediction is not executable evidence")
    segment("right_empty_hand_transit", 14., joints(slice(8, 14), pre_q))
    segment("right_approach_tip", 4., lambda u: cartesian("right",
            grasp_p-.06*(1-u)*grasp_r.apply([1., 0., 0.]), grasp_r),
            "STOP: align to current tip; rescreen any updated target before closing")
    segment("right_contact_gated_close", 2., joints(slice(14, 16), [.011, .011]),
            "STOP closing at bilateral native contact; engage public attachment in measured hand frame")
    segment("dual_hold_check", .5, lambda u: None,
            "Require right attachment and stable measured follow before releasing left")
    # Opening to the shared .037 m target here intersects R2. Unpinch narrowly,
    # then withdraw; an actual execution must also check loss of left contact.
    segment("left_small_unpinch", .5, joints(slice(6, 8), q[6:8]+.0003),
            "Release left assistance only after right hold confirmation; verify left contact clears")
    lp, lr = ik.pose("left", q[:6])
    segment("left_axial_withdraw", 4., lambda u: cartesian("left",
            lp-.10*u*lr.apply([1., 0., 0.]), lr))
    segment("left_open_outside_ring", .5, joints(slice(6, 8), join_qpos[6:8]))
    segment("left_return_to_reference", 3., joints(slice(0, 6), join_qpos[:6]))
    end_p, end_r = ik.pose("right", join_qpos[8:14])
    end_tip = end_p+end_r.apply(GRASP_OFFSET)
    rotations = Slerp([0., 1.], Rotation.concatenate([grasp_r, end_r]))
    carry_points = []

    def carry(u):
        target = carry_tip(tip_after, end_tip, u)
        carry_points.append(target)
        r = rotations(u)
        cartesian("right", target-r.apply(GRASP_OFFSET), r)

    segment("right_carry_around_R3", 5., carry,
            "Recheck actual rope route R1-/R2+ and measured hold before resuming source phase 36")
    arm_indices = [0, 1, 2, 3, 4, 5, 8, 9, 10, 11, 12, 13]
    return dict(time=np.asarray(times), qpos=np.asarray(rows), stage=np.asarray(names),
        stages=stages, ik=ik, tip_after=tip_after, tangent_after=tangent_after,
        pivot_anchor=anchor, pivot_anchor_local=left_local,
        predicted_tail=predicted, pivot_deg=pivot_deg, azimuth_deg=azimuth_deg,
        max_pivot_anchor_error_m=max(anchor_errors),
        maximum_join_joint_difference_rad=float(np.abs(q[arm_indices]-join_qpos[arm_indices]).max()),
        minimum_carry_tip_R2_exit_distance_m=float(((np.asarray(carry_points)-R2_CENTER)@R2_NORMAL).min()))


def screen_plan(cfg, plan, interval=.005):
    model = model_with_fixtures(cfg)
    model.geom_margin[:] = .003  # Also request nearby separated pairs.
    data = mujoco.MjData(model)
    times, qpos = plan["time"], plan["qpos"]
    sample_times = np.unique(np.r_[times, np.arange(0., times[-1], interval), times[-1]])
    per_stage, worst, negative = {}, None, 0
    pivot_error, carry_distance = 0., float("inf")
    for t in sample_times:
        data.qpos[:] = [np.interp(t, times, qpos[:, j]) for j in range(16)]
        mujoco.mj_forward(model, data)
        name = str(plan["stage"][min(np.searchsorted(times, t), len(times)-1)])
        if name == "left_pivot_about_node77":
            hand = data.body("left/gripper_link")
            anchor = hand.xpos+hand.xmat.reshape(3, 3)@plan["pivot_anchor_local"]
            pivot_error = max(pivot_error, float(np.linalg.norm(anchor-plan["pivot_anchor"])))
        if name == "right_carry_around_R3":
            hand = data.body("right/gripper_link")
            tip = hand.xpos+hand.xmat.reshape(3, 3)@GRASP_OFFSET
            carry_distance = min(carry_distance, float((tip-R2_CENTER)@R2_NORMAL))
        if len(data.contact):
            contact = min(data.contact, key=lambda c: c.dist)
            item = dict(time_s=float(t), distance_m=float(contact.dist), stage=name,
                pair=[model.geom(g).name or model.body(model.geom_bodyid[g]).name
                      for g in (contact.geom1, contact.geom2)])
            negative += int(contact.dist < 0.)
            if worst is None or item["distance_m"] < worst["distance_m"]:
                worst = item
            if name not in per_stage or item["distance_m"] < per_stage[name]["distance_m"]:
                per_stage[name] = item
    arms = qpos[:, [0, 1, 2, 3, 4, 5, 8, 9, 10, 11, 12, 13]].reshape(-1, 2, 6)
    limits = plan["ik"].joint_limits
    margin = float(np.minimum(arms-limits[:, 0], limits[:, 1]-arms).min())
    max_step = float(np.abs(np.diff(arms, axis=0)).max())
    max_speed = float((np.abs(np.diff(arms, axis=0))/np.diff(times)[:, None, None]).max())
    checks = dict(no_sampled_negative_contacts=negative == 0, joint_margin=margin >= .02-1e-9,
        joint_continuity=max_step < .05, planned_joint_speed=max_speed <= .8,
        pivot_anchor_position=plan["max_pivot_anchor_error_m"] <= .0002,
        interpolated_pivot_anchor_position=pivot_error <= .0002,
        interpolated_carry_tip_stays_R2_exit_side=carry_distance > .004,
        carry_tip_stays_R2_exit_side=plan["minimum_carry_tip_R2_exit_distance_m"] > .004,
        join_reference_joint_branch=plan["maximum_join_joint_difference_rad"] <= 1e-6)
    return dict(sampled_kinematic_checks_passed=all(checks.values()), checks=checks,
        physical_execution_verified=False, automatically_executable=False,
        scope="conditional CPU IK, robot self/fixture capsule collision proxies; no rope dynamics or CCD",
        sample_count=len(sample_times), sample_period_s=interval, negative_contact_samples=negative,
        worst_contact=worst, per_stage_nearest_contact=per_stage,
        minimum_joint_margin_rad=margin, max_joint_step_rad=max_step,
        max_planned_joint_speed_rad_s=max_speed,
        max_ik_position_error_m=plan["ik"].max_position_residual,
        max_ik_orientation_error_rad=plan["ik"].max_rotation_residual,
        max_pivot_anchor_error_m=plan["max_pivot_anchor_error_m"],
        max_interpolated_pivot_anchor_error_m=pivot_error,
        minimum_interpolated_carry_tip_R2_exit_distance_m=carry_distance,
        maximum_join_joint_difference_rad=plan["maximum_join_joint_difference_rad"],
        minimum_carry_tip_R2_exit_distance_m=plan["minimum_carry_tip_R2_exit_distance_m"])


def build(run, output, *, pivot_deg=6., azimuth_deg=28.):
    output.mkdir(parents=True, exist_ok=False)
    cfg = OmegaConf.load(run/"config.yaml")
    snapshot = snapshot_from_run(run, cfg)
    actions = ReferenceThreadingActions(REFERENCE)
    join, _, _, _ = actions._sample(JOIN_SOURCE_S)
    plan = plan_handoff(cfg, snapshot, join, pivot_deg=pivot_deg, azimuth_deg=azimuth_deg)
    report = screen_plan(cfg, plan)
    report.update(source_run=str(run.resolve()), snapshot_frame="robot model/table frame",
        duration_without_gate_waits_s=float(plan["time"][-1]), resume_source_time_s=JOIN_SOURCE_S,
        stages=plan["stages"], pivot_deg=pivot_deg, grasp_azimuth_deg=azimuth_deg,
        tip_after_pivot_model_m=plan["tip_after"].tolist(),
        post_pivot_geometry_kind="rigid free-tail prediction; must be replaced by physical observation",
        source_reference_sha256=actions.reference_sha256,
        source_input_sha256={name: hashlib.file_digest((run/name).open("rb"), "sha256").hexdigest()
                             for name in ("config.yaml", "contact_trace.json", "trajectory.npz", "mesh.npz")},
        implementation_sha256={str(p.relative_to(ROOT)): hashlib.sha256(p.read_bytes()).hexdigest()
            for p in [Path(__file__), Path(__file__).with_name("reference_ik.py"),
                      Path(__file__).with_name("reference_preflight.py"),
                      ROOT/"topogym/tasks/knot_untying/control.py"]},
        limitations=["No new physics execution, rope contact, grasp capture, or final success proved",
            "Limited fixture clearance needs physical mesh and servo validation",
            "After pivot: reobserve tip/tangent and screen complete approach, not only endpoint",
            "After capture: freeze measured aperture and rebuild carry using measured attachment offset",
            "Source clock must pause at gates; left release requires confirmed right hold",
            "Later reference phases still need actual-rope feedback and physical verification"])
    np.savez_compressed(output/"handoff_trajectory.npz", time_s=plan["time"],
                        qpos=plan["qpos"], stage=plan["stage"])
    (output/"snapshot.json").write_text(json.dumps(snapshot, indent=2)+"\n")
    (output/"report.json").write_text(json.dumps(report, indent=2)+"\n")
    OmegaConf.save(cfg, output/"config.yaml")
    print(json.dumps({k: v for k, v in report.items() if k not in
                      ("stages", "per_stage_nearest_contact", "implementation_sha256")}, indent=2))
    return report


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("source_run", type=Path)
    parser.add_argument("output", type=Path)
    parser.add_argument("--pivot-deg", type=float, default=6.)
    parser.add_argument("--azimuth-deg", type=float, default=28.)
    args = parser.parse_args()
    result = build(args.source_run, args.output, pivot_deg=args.pivot_deg, azimuth_deg=args.azimuth_deg)
    raise SystemExit(0 if result["sampled_kinematic_checks_passed"] else 1)
