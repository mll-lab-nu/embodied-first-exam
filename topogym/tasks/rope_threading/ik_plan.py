"""Build and audit a complete CPU IK plan; no FEM execution or video recording."""
import argparse
import hashlib
import json
from pathlib import Path
from types import SimpleNamespace

from hydra import compose, initialize_config_dir
import mujoco
import numpy as np
from scipy.spatial.transform import Rotation

from topogym.robot.assets import robot_asset
from .geometry import ThreadingLayout, route_crossings
from .reference_actions import ReferenceThreadingActions, ending_lift
from .reference_ik import MarginAwareThreadingIK, JOINT_MARGIN_RAD, free_hand_clearance
from .reference_motion import load_motion
from .reference_preflight import model_with_fixtures


ROOT = Path(__file__).resolve().parents[3]
REFERENCE = ROOT/"runs/environment-solvability/rope_threading/reference_motion_v1"


def offline_controller(cfg, qpos):
    model = mujoco.MjModel.from_xml_path(robot_asset(cfg.robot_control))
    data = mujoco.MjData(model)
    data.qpos[:] = qpos
    mujoco.mj_forward(model, data)
    arms = {}
    for index, side in enumerate(("left", "right")):
        body = data.body(f"{side}/gripper_link")
        pos, quat, q = body.xpos.copy(), body.xquat.copy(), qpos[index*8:index*8+6].copy()
        arms[side] = SimpleNamespace(hand_pos=lambda p=pos: p, hand_quat=lambda q=quat: q,
                                    arm_qpos=lambda q=q: q)
    return SimpleNamespace(cfg=cfg.robot_control, arms=arms, left=arms["left"])


def target_position(actions, time, phase, side_index, hand, lift):
    point = np.asarray(hand[:3])+[0., 0., .0009]
    if side_index == 1 and phase >= 49:
        point += ending_lift(time, actions.summary["stages"][49]["start_s"], lift)
    point += free_hand_clearance(time, phase, actions.summary["stages"], ("left", "right")[side_index])
    return point


def goal_evidence(reference):
    layout = ThreadingLayout()
    nodes = layout.transform(reference["rope_nodes"][-1])
    crossings = route_crossings(nodes, layout.rings(), layout.radius)
    route = [hit["ring"]+("+" if hit["sign"] > 0 else "-") for hit in crossings]
    return dict(scope="author reference final state, not a new physical result",
        expected_route=["R1-", "R2+", "R3+"], reference_route=route,
        crossings=crossings, both_grippers_released=not bool(reference["equality"][-1, 2:].any()),
        endpoint_positions_table_frame_m=nodes[[0, -1]].tolist(),
        endpoint_skin_clearance_m=(nodes[[0, -1], 2]-layout.radius).tolist(),
        execution_requirements=["all six contact-gated acquisitions and six releases",
            "material route R1-/R2+/R3+ retained after release",
            "both endpoint skin heights in [-0.00005, 0.003] m above the table",
            "robot surfaces withdrawn from every ring aperture",
            "native collision, deformation, grasp-following and settling checks pass"],
        physical_execution_verified=False)


def write_figures(output, reference, planned, limits):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    layout = ThreadingLayout()
    colors = ["#10a6b1", "#55a84f", "#905bc2"]
    phases = [11, 24, 31, 37, 44, 50]
    titles = ["Right tip through R1", "Left takes node 77", "Left passes R2",
              "Right passes R3", "Withdraw: temporary extra R3 crossing", "Goal: released, threaded through all 3"]
    fig = plt.figure(figsize=(15, 9))
    for n, (phase, title) in enumerate(zip(phases, titles), 1):
        ax = fig.add_subplot(2, 3, n, projection="3d")
        index = np.flatnonzero(reference["phase"] == phase)[-1]
        nodes = layout.transform(reference["rope_nodes"][index])
        for ring, color in zip(layout.rings(), colors):
            theta = np.linspace(0., 2*np.pi, 129)
            points = np.asarray(ring["center_m"])+ring["radius_m"]*(
                np.cos(theta)[:, None]*ring["basis_u"]+np.sin(theta)[:, None]*ring["basis_v"])
            ax.plot(*points.T, color=color, linewidth=4)
            ax.text(*ring["center_m"], ring["name"], color=color)
        ax.plot(*nodes.T, color="#c96d22", linewidth=2.7)
        ax.scatter(*nodes[[0]].T, color="black", s=25)
        ax.scatter(*nodes[[-1]].T, color="#db2842", s=25)
        ax.set(xlim=(-.4, .4), ylim=(-.32, .5), zlim=(0., .46),
               xlabel="X (m)", ylabel="Y (m)", zlabel="Z (m)")
        ax.view_init(elev=23, azim=-38)
        ax.set_box_aspect((.8, .82, .46))
        ax.set_title(f"{title}\nsource t={reference['time'][index]:.2f} s", fontsize=10)
    fig.suptitle("AUTHOR REFERENCE rope geometry — desired sequence, NOT a new physics rollout", fontsize=14)
    fig.tight_layout()
    fig.savefig(output/"reference_sequence.png", dpi=160)
    plt.close(fig)
    fig, axes = plt.subplots(2, 1, figsize=(11, 6), sharex=True)
    time = reference["time"]
    axes[0].plot(time, np.rad2deg(reference["qpos"][:, 13]), label="original reference")
    axes[0].plot(time, np.rad2deg(planned[:, 13]), label="planned IK", linewidth=1.1)
    axes[0].axhline(np.rad2deg(limits[5, 0]), color="red", linestyle="--", label="physical lower limit")
    axes[0].set(ylabel="Right wrist roll (deg)")
    axes[0].legend()
    for q, label in [(reference["qpos"], "original minimum margin"), (planned, "planned minimum margin")]:
        arm = q[:, [0, 1, 2, 3, 4, 5, 8, 9, 10, 11, 12, 13]].reshape(-1, 2, 6)
        margin = np.minimum(arm-limits[:, 0], limits[:, 1]-arm).min(axis=(1, 2))
        axes[1].plot(time, np.rad2deg(margin), label=label)
    axes[1].set(xlabel="Author reference time (s)", ylabel="Nearest joint limit (deg)", ylim=(-.2, 5))
    axes[1].legend()
    fig.tight_layout()
    fig.savefig(output/"joint_margin.png", dpi=160)
    plt.close(fig)


def build(output, *, stride=1, margin=JOINT_MARGIN_RAD, ending_lift_m=.03, speed=3.):
    if stride < 1 or not np.isfinite([margin, ending_lift_m, speed]).all() or ending_lift_m < 0 or speed <= 0:
        raise ValueError("Invalid plan parameters")
    output.mkdir(parents=True, exist_ok=False)
    implementation_hashes = {str(path.relative_to(ROOT)): hashlib.sha256(path.read_bytes()).hexdigest()
        for path in [Path(__file__), Path(__file__).with_name("reference_ik.py"),
                     Path(__file__).with_name("reference_actions.py"),
                     Path(__file__).with_name("reference_preflight.py"),
                     ROOT/"topogym/tasks/knot_untying/control.py"]}
    actions = ReferenceThreadingActions(REFERENCE)
    # Recheck all 51 binary files/arrays and their equality to the cached input.
    verified = load_motion(ROOT/".external/rope-threading-reference")
    for key, value in actions.reference.items():
        if not np.array_equal(value, verified[key]):
            raise ValueError(f"Cached reference differs from verified source: {key}")
    with initialize_config_dir(config_dir=str(ROOT/"configs"), version_base="1.3"):
        cfg = compose(config_name="rope_threading_damped20_compressible_fine_preview")
    ref = actions.reference
    ik = MarginAwareThreadingIK(None, offline_controller(cfg, ref["qpos"][0]), margin=margin)
    indices = np.unique(np.r_[np.arange(0, len(ref["time"]), stride), len(ref["time"])-1])
    time = ref["time"][indices]
    planned = ref["qpos"][indices].copy()
    target_hands = np.zeros((len(indices), 2, 7))
    residuals = np.zeros((len(indices), 2, 3))
    for n, i in enumerate(indices):
        t, phase = ref["time"][i], int(ref["phase"][i])
        for si, side in enumerate(("left", "right")):
            hand = ref["hands"][i, si]
            position = target_position(actions, t, phase, si, hand, ending_lift_m)
            source_q = ref["qpos"][i, si*8:si*8+6]
            quat, delta = ik.reference_target(hand[3:], source_q)
            q = ik.solve_reference(side, position, hand[3:], source_q)
            planned[n, si*8:si*8+6] = q
            actual_pos, actual_rot = ik.pose(side, q)
            target_rot = Rotation.from_quat(quat, scalar_first=True)
            residuals[n, si] = [np.linalg.norm(actual_pos-position),
                (target_rot.inv()*actual_rot).magnitude(), abs(delta)]
            target_hands[n, si] = np.r_[position, quat]
        if n % 2000 == 0:
            print(f"IK {n}/{len(indices)} source={t:.3f}s", flush=True)
    np.savez_compressed(output/"ik_trajectory.npz", source_time_s=time, qpos=planned,
        phase=ref["phase"][indices], target_hands_table_frame=target_hands,
        position_rotation_roll_residuals=residuals)

    # Audit the interpolation that a 5 ms controller at the specified source
    # speed would request, plus every saved knot and the final endpoint.
    sample_times = np.unique(np.r_[time, np.arange(0., time[-1], .005*speed), time[-1]])
    model = model_with_fixtures(cfg)
    data = mujoco.MjData(model)
    collisions, shallow_contacts = [], 0
    min_contact = 0.
    interpolation_position = interpolation_rotation = 0.
    for n, t in enumerate(sample_times):
        q = np.array([np.interp(t, time, planned[:, j]) for j in range(16)])
        data.qpos[:] = q
        mujoco.mj_forward(model, data)
        source_q, hands, _, phase = actions._sample(t)
        for si, side in enumerate(("left", "right")):
            target = target_position(actions, t, phase, si, hands[si], ending_lift_m)
            quat, _ = ik.reference_target(hands[si, 3:], source_q[si*8:si*8+6])
            body = data.body(f"{side}/gripper_link")
            interpolation_position = max(interpolation_position, float(np.linalg.norm(body.xpos-target)))
            interpolation_rotation = max(interpolation_rotation, float((Rotation.from_quat(quat, scalar_first=True).inv()
                *Rotation.from_matrix(body.xmat.reshape(3, 3))).magnitude()))
        if len(data.contact):
            contact = min(data.contact, key=lambda c: c.dist)
            min_contact = min(min_contact, float(contact.dist))
            if contact.dist < 0:
                shallow_contacts += 1
            if contact.dist < -.0005:
                collisions.append(dict(source_time_s=float(t), phase=phase, depth_m=float(-contact.dist),
                    geom_names=[model.geom(g).name for g in (contact.geom1, contact.geom2)]))
        if n % 6000 == 0:
            print(f"collision/interpolation audit {n}/{len(sample_times)}", flush=True)
    arm_indices = [0, 1, 2, 3, 4, 5, 8, 9, 10, 11, 12, 13]
    arms = planned[:, arm_indices].reshape(-1, 2, 6)
    source_arms = ref["qpos"][:, arm_indices].reshape(-1, 2, 6)
    limits = ik.joint_limits
    margins = np.minimum(arms-limits[:, 0], limits[:, 1]-arms)
    original_margins = np.minimum(source_arms-limits[:, 0], limits[:, 1]-source_arms)
    steps = np.abs(np.diff(arms, axis=0))
    rates = steps/np.diff(time)[:, None, None]*speed
    stage_reports = []
    for stage in actions.summary["stages"]:
        mask = ref["phase"][indices] == stage["index"]
        if np.any(mask):
            stage_reports.append(dict(stage, samples=int(mask.sum()),
                minimum_joint_margin_rad=float(margins[mask].min()),
                max_position_error_m=float(residuals[mask, :, 0].max()),
                max_roll_relaxation_rad=float(residuals[mask, :, 2].max())))
    checks = dict(full_source_sampling=stride == 1, all_51_phases=len(stage_reports) == 51,
        all_joint_margins=bool(margins.min() >= margin-1e-9),
        target_position=bool(residuals[:, :, 0].max() <= .0002),
        target_orientation=bool(residuals[:, :, 1].max() <= .002),
        interpolation_position=interpolation_position <= .0002,
        interpolation_orientation=interpolation_rotation <= .002,
        no_large_branch_jump=bool(steps.max() < .05),
        no_sampled_negative_contacts=shallow_contacts == 0,
        no_penetration_above_0_5mm=not collisions)
    report = dict(scope="CPU joint-limited IK and sampled MuJoCo fixture/self-collision screen; no rope dynamics",
        passed=all(checks.values()), checks=checks, physical_execution_verified=False,
        source_reference_sha256=actions.reference_sha256,
        implementation_sha256=implementation_hashes,
        cached_reference_verified_against_51_hashed_source_binaries=True,
        samples=len(indices), duration_source_s=float(time[-1]), stage_count=len(stage_reports),
        joint_safety_margin_rad=margin, minimum_joint_margin_rad=float(margins.min()),
        original_minimum_joint_margin_rad=float(original_margins.min()),
        maximum_pose_position_residual_m=float(residuals[:, :, 0].max()),
        maximum_pose_rotation_residual_rad=float(residuals[:, :, 1].max()),
        maximum_reference_roll_relaxation_rad=float(residuals[:, :, 2].max()),
        max_joint_step_rad=float(steps.max()), max_joint_speed_rad_s_at_requested_speed=float(rates.max()),
        max_joint_speed_rad_s_by_arm_at_requested_speed=rates.max(axis=0).tolist(),
        source_speed_for_audit=speed, ending_lift_m=ending_lift_m,
        empty_hand_clearance=dict(side="left", phases=[40, 49], maximum_z_offset_m=.003),
        collision_audit_samples=len(sample_times), deepest_contact_m=min_contact,
        samples_with_any_negative_contact=shallow_contacts, collisions=collisions,
        max_interpolated_position_error_m=interpolation_position,
        max_interpolated_rotation_error_rad=interpolation_rotation,
        grasp_events=actions.schedule, stages=stage_reports,
        goal=goal_evidence(ref), limitations=[
            "Fixture rings use the source's 64 capsule segments; collision checks are sampled, not continuous CCD.",
            "Finger aperture follows the source. Real contact-gated apertures and material-point corrections require rechecking.",
            "The near-limit reference orientation is deliberately relaxed about local tool X; it is not exact reference-pose tracking.",
            "No actuator torque, velocity-limit or closed-loop dynamic tracking certificate is produced.",
            "Assisted-grasp acquisition, FEM rope threading and stable final release have not been executed by this planner."])
    for file in ("ik_trajectory.npz",):
        report[file+"_sha256"] = hashlib.sha256((output/file).read_bytes()).hexdigest()
    (output/"report.json").write_text(json.dumps(report, indent=2)+"\n")
    if stride == 1:
        write_figures(output, ref, planned, limits)
    print(json.dumps({k: v for k, v in report.items() if k not in ("stages", "collisions", "grasp_events", "goal")}, indent=2))
    return report


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("output", type=Path)
    parser.add_argument("--stride", type=int, default=1, help="Debug subsampling; only 1 can pass the full audit")
    parser.add_argument("--joint-margin", type=float, default=JOINT_MARGIN_RAD)
    parser.add_argument("--ending-lift", type=float, default=.03)
    parser.add_argument("--reference-speed", type=float, default=3.)
    args = parser.parse_args()
    build(args.output, stride=args.stride, margin=args.joint_margin,
          ending_lift_m=args.ending_lift, speed=args.reference_speed)
