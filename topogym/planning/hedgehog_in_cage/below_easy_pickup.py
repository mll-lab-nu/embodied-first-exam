"""Checked pickups (private reference data) for the below-easy Hedgehog settings very_easy and easier.

The robot holds S10, the spike that points at it, from outside the cage: the fingers close across the spike near its
tip (theta 90 deg: the approach is perpendicular to the spike), with the measured fingers of the oracle's partial close.
A coaxial grasp (which would make easier's roll about S10 a wrist roll) has no valid IK this close to the robot base.
Object hints: very_easy pulls straight out of the wide window (below_easy_witness.py's route). easier yaws the ball
-20 deg about the vertical, the narrow single-turn exit next to the witness's 80 deg roll about S10, pulls 0.125 m and
moves sideways toward the goal: the roll, or a long pull toward the base, folds the elbow (joint 4) to its limit with
every grasp that passes the approach. recipes.run_medium_oracle executes the pickup unchanged: free-hand route,
approach, contact-weld grasp, 12 mm test lift, measured held route to the unchanged Task goal, hold. The settings were
chosen with check_pickup (an offline plan_held_path on a constructed measured state).

main() (--tier very_easy --output DIR) runs in the task image, with this planning tree on topogym's path, on the
frozen privileged instance (/app/instance.json) and writes DIR/pickup.json and DIR/pickup_check.json. make_pickup
issues no command; it only queries IK/FK (state-preserving, BUG 7).
"""
from copy import deepcopy

import numpy as np
from scipy.spatial.transform import Rotation

from topogym.planning.rigid_reference.feedback import body_pose, relative_pose
from topogym.planning.rigid_reference.geometry import pose_dict

SPIKE = 9   # S10 of the CLASSIC template: the 60 mm spike that points at the robot, about 29 mm outside the cage wall
TEST_LIFT_M = .012   # recipes.run_medium_oracle's lift right after the grasp
SETTINGS = {
    # theta/phi/flip: hand z = cos(theta)(-spike) + sin(theta) n(phi), closing axis y(phi) = phi about the spike from
    # its horizontal normal; flip turns the hand 180 deg about its z (same contact, joint 7 away from its limit).
    # pad_depth_m: the spike axis crosses the pads at this hand z (pads span 0.065-0.094 m, TCP at 0.103 m).
    # route (cage frame, from the test-lifted start): extra lift, one turn of the ball about its centre (axis "z" or
    # "spike", degrees), pulls [azimuth deg, m].
    "very_easy": dict(theta_deg=90., phi_deg=300., flip=True, pad_depth_m=.09, grip_from_tip_m=.006,
                      lift_m=0., turn=None, pulls=((198., .07), (198., .19))),
    "easier": dict(theta_deg=90., phi_deg=300., flip=True, pad_depth_m=.09, grip_from_tip_m=.006,
                   lift_m=0., turn=("z", -20.), pulls=((188., .125), (240., .2))),
}
IK_SEEDS = 8


def spike_frame(env):
    """World pose of the ball, unit axis of the held spike and its tip."""
    from topogym.assets.geometry.hedgehog_in_cage import HedgehogLayout
    from .kinematics import HedgehogIK
    task = env._task
    kin = HedgehogIK(env)
    bp, br = kin.ball_pose
    root, tip = HedgehogLayout(task.template(), float(task.config["scale"])).spike_segments()[SPIKE]
    axis = br.apply((tip - root) / np.linalg.norm(tip - root))
    return kin, (bp, br), axis, bp + br.apply(tip)


def hand_rotation(axis, theta_deg, phi_deg, flip):
    reference = np.cross(axis, [0., 0., 1.])
    reference /= np.linalg.norm(reference)
    y = Rotation.from_rotvec(np.radians(phi_deg) * axis).apply(reference)
    z = np.cos(np.radians(theta_deg)) * -axis + np.sin(np.radians(theta_deg)) * np.cross(axis, y)
    z /= np.linalg.norm(z)
    rotation = Rotation.from_matrix(np.column_stack([np.cross(y, z), y, z]))
    return rotation * Rotation.from_euler("z", 180., degrees=True) if flip else rotation


def best_ik(kin, tcp, rotation):
    """Deterministic multi-seed IK; the solution with the largest clearance and joint margin."""
    limits = np.asarray(kin.group.arm_limits_rad)
    home = np.asarray(kin.group.home[:7])
    rng = np.random.default_rng(0)
    seeds = [home, np.array([0., .1, 0., -2.4, 0., 2.5, .785]), np.array([-.4, .2, 0., -2.3, 0., 2.5, .3])]
    seeds += [np.clip(home + rng.normal(0., .6, 7), limits[:, 0] + .12, limits[:, 1] - .12) for _ in range(IK_SEEDS)]
    best = None
    for arm in seeds:
        seed = kin.seed.copy()
        seed[:7] = arm
        try:
            q = kin.solve((tcp, rotation), seed)
        except ValueError:
            continue
        q[7:] = kin.seed[7:]
        gaps = kin.gaps(q)
        margin = float(np.minimum(q[:7] - limits[:, 0], limits[:, 1] - q[:7]).min())
        score = min(min(gaps.values()), .02) + .1 * min(margin, .2)
        if best is None or score > best[0]:
            best = (score, q, gaps, margin)
    if best is None:
        raise ValueError("No IK solution for the below-easy grasp")
    return best[1:]


def make_pickup(env, variation):
    """The pickup for run_medium_oracle; env must hold the measured fingers of the oracle's partial close."""
    cfg = SETTINGS[variation]
    kin, (bp, br), axis, tip = spike_frame(env)
    rotation = hand_rotation(axis, cfg["theta_deg"], cfg["phi_deg"], cfg["flip"])
    grip = tip - cfg["grip_from_tip_m"] * axis
    tcp_in_hand = np.asarray(kin.group.tcp_position_in_hand_m)
    tcp = grip + (tcp_in_hand[2] - cfg["pad_depth_m"]) * rotation.apply([0., 0., 1.])
    q, gaps, margin = best_ik(kin, tcp, rotation)
    hand = tcp - rotation.apply(tcp_in_hand)
    state = env._world.read_state()
    cage = body_pose(state["bodies"]["hedgehog_cage"])
    p, r = relative_pose(cage, (bp + [0., 0., TEST_LIFT_M], br))
    hints = []
    if cfg["lift_m"]:
        p = p + [0., 0., cfg["lift_m"]]
        hints.append((p, r))
    if cfg["turn"]:
        name, degrees = cfg["turn"]
        turn_axis = cage[1].inv().apply(axis) if name == "spike" else np.array([0., 0., 1.])
        r = Rotation.from_rotvec(np.radians(degrees) * turn_axis) * r
        hints.append((p, r))
    for azimuth, distance in cfg["pulls"]:
        hints.append((p + distance * np.array([np.cos(np.radians(azimuth)), np.sin(np.radians(azimuth)), 0.]), r))
    return dict(
        spike=SPIKE, grasp=dict(cfg, turn=cfg["turn"] and list(cfg["turn"]), pulls=[list(v) for v in cfg["pulls"]]),
        hand_in_ball=pose_dict(relative_pose((bp, br), (hand, rotation))),
        grip_point_in_ball=br.inv().apply(grip - bp).tolist(), qpos=q.tolist(),
        grasp_gaps_m=gaps, grasp_joint_margin_rad=margin,
        minimum_approach_clearance_m=.0003, pregrasp_distance_m=.045,
        object_path_hints=[pose_dict(h) for h in hints], preserve_waypoints=True,
        held_path_clearance_m=.0005, departure_clearance_m=.00005,
        scope=f"Complete default-home one-grasp attempt ({variation}): S10 held from outside the cage, "
              "design route of below_easy_witness.py, then the unchanged Task goal")


def check_pickup(env, pickup, output):
    """Offline plan_held_path from a constructed measured state: the grasp IK, lifted by TEST_LIFT_M with the ball.

    A planning check only; the oracle plans again from the measured state after its real test lift."""
    from .held_oracle import plan_held_path
    kin, (bp, br), axis, tip = spike_frame(env)
    relp, relr = body_pose(pickup["hand_in_ball"])
    rotation = br * relr
    tcp = bp + br.apply(relp) + rotation.apply(kin.group.tcp_position_in_hand_m)
    q = np.asarray(pickup["qpos"], float)
    for u in np.linspace(0., 1., 13)[1:]:
        q = kin.solve((tcp + [0., 0., TEST_LIFT_M * u], rotation), q)
        q[7:] = kin.seed[7:]
    state = deepcopy(env._world.read_state())
    joints = state["articulations"]["robot"]["joints"]
    for joint in kin.robot.entity.joints:
        if joint.name in joints:
            joints[joint.name]["position"] = [float(q[i]) for i in joint.qs_idx_local]
    state["bodies"]["hedgehog_ball"] = dict(state["bodies"]["hedgehog_ball"], position_m=(bp + [0., 0., TEST_LIFT_M]).tolist(),
                                            quaternion_wxyz=br.as_quat()[[3, 0, 1, 2]].tolist())
    report = plan_held_path(env, output, measured_state=state, clearance_m=pickup["held_path_clearance_m"],
                            wrist_envelope=True, max_turn_deg=180., iterations=30000,
                            grip_point_in_ball=pickup["grip_point_in_ball"],
                            object_path_hints=pickup["object_path_hints"], preserve_waypoints=True,
                            departure_clearance_m=pickup["departure_clearance_m"])
    rows = report.get("rows") or []
    joints_q = np.asarray([row["qpos"][:7] for row in rows]) if rows else np.zeros((0, 7))
    return dict(status=report["status"], rows=len(rows),
                minimum_gaps_m={k: min(row["gaps"][k] for row in rows) for k in rows[0]["gaps"]} if rows else None,
                minimum_joint_margin_rad=min(row["joint_margin_rad"] for row in rows) if rows else None,
                joint_range=dict(minimum=joints_q.min(0).tolist(), maximum=joints_q.max(0).tolist()) if rows else None,
                certificate=report.get("certificate"), failure={k: report.get(k) for k in ("reason", "gaps", "joint_margin_rad",
                                                                                          "joint_step_rad", "endpoint")})


def main():
    import argparse
    import json
    import sys
    from pathlib import Path
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--tier", required=True, choices=tuple(SETTINGS))
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--instance", default="/app/instance.json")
    args = parser.parse_args()
    sys.path.insert(0, "/opt/tools")
    import rcb_topogym
    from topogym.planning.base import ActionSequencePolicy
    from topogym.planning.standard_rate import rate_limited_runner
    session = rcb_topogym.Session("hedgehog_in_cage", instance=args.instance, strict=True)
    session.record_start()
    # The oracle's partial close (recipes.run_medium_oracle), so the IK sees the measured fingers it will use.
    rate_limited_runner(session).run_policy(request_id="partial_close", submission_hash="below_easy_pickup",
        policy=ActionSequencePolicy([{"arm": {"gripper_position_rad": .6}}] + [{}] * 399), state_fields=("world",))
    pickup = make_pickup(session.env, args.tier)
    pickup["source"] = dict(instance_id=session.env._task.instance_id, instance_sha=session.instance_sha,
                            tool="topogym/planning/hedgehog_in_cage/below_easy_pickup.py")
    args.output.mkdir(parents=True, exist_ok=True)
    check = check_pickup(session.env, pickup, args.output / "held_check")
    (args.output / "pickup.json").write_text(json.dumps(pickup, indent=2) + "\n")
    (args.output / "pickup_check.json").write_text(json.dumps(check, indent=2) + "\n")
    print(json.dumps(dict(tier=args.tier, status=check["status"], rows=check["rows"],
                          minimum_joint_margin_rad=check["minimum_joint_margin_rad"])))


if __name__ == "__main__":
    main()
