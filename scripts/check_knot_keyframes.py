"""CPU kinematic check: knot object-level routes as ALOHA pin/pull and end-spread grasps.

Reads band_tracks.json of a passing object-only run. Bands engaged together form
one decision (HULK pin + pull, or the Reidemeister end spread). For every arm
assignment and jaw flip it solves native IK for the pregrasp (80 mm above), the
grasp, every sampled band position (TCP follows the band centre, rotation held
from the grasp) and the lift-off after release, and checks both arms together
(table, same-arm, inter-arm, joint limits). No rope physics and no rope collision.

Usage: .venv-gs121-nyx/bin/python scripts/check_knot_keyframes.py --variation knot_untying_medium \
           --tracks runs/test_results/knot_object_route_20260930/medium_cl_v2_coarse_eps1mm/band_tracks.json \
           --output runs/test_results/knot_ik_keyframes_20260930/medium.json
"""
import argparse
import itertools
import json
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

OPEN_M, ON_ROPE_M = .027, .0118  # gripper command: partly open (38 mm gap) / pads touching an 8 mm rope


def build(variation):
    from topogym.simulator.config import SimulatorConfig
    from topogym.config.scene import load_scene_config
    from topogym.world.genesis_world import GenesisWorld
    from topogym.robot.joint_position import make_robot
    from topogym.planning.knot_untying.kinematics import KnotIK
    cfg = load_scene_config(SimulatorConfig(task_id="knot_untying", robot_id="aloha", variation_id=variation,
                                            compute_backend="cpu", enable_rgb=False))
    world = GenesisWorld.from_tabletop(cfg.env, cfg.robot_control, compute_backend="cpu")
    world.build()
    robot = make_robot(world.entities["robot"], cfg.robot_control)
    robot.reset_home()
    table = cfg.env.world.table
    return KnotIK(world, robot, float(table.pos[2]+table.size[2]/2))


def plan_band(ik, side, band, flip, seed):
    """Joint path of one arm for one band, or (None, reason)."""
    from topogym.planning.knot_untying.kinematics import vertical_pinch, CONTACT_IN_TCP_M
    first = band["samples"][0]
    p0, turn = vertical_pinch(first["p"], first["tangent_xy"], flip)
    lift = np.array([0., 0., .08])
    rows = []
    try:
        q = ik.solve(side, (p0+lift, turn), seed)
        rows.append(("pregrasp", band["engage_s"], q.copy(), OPEN_M))
        q = ik.solve(side, (p0, turn), q)
        rows.append(("grasp", band["engage_s"], q.copy(), OPEN_M))
        for sample in band["samples"]:
            q = ik.solve(side, (np.asarray(sample["p"])-turn.apply(CONTACT_IN_TCP_M), turn), q)
            rows.append(("follow", sample["t"], q.copy(), ON_ROPE_M))
        q = ik.solve(side, (np.asarray(band["samples"][-1]["p"])-turn.apply(CONTACT_IN_TCP_M)+lift, turn), q)
        rows.append(("retreat", band["release_s"], q.copy(), OPEN_M))
    except ValueError as error:
        return None, f"ik at {len(rows)} ({['pregrasp', 'grasp'][min(len(rows), 1)] if len(rows) < 2 else 'follow/retreat'}): {str(error)[:120]}"
    return rows, None


def combined(ik, plans, home):
    """Check both arms at each row of the longest plan, holding the other arm at its nearest-in-time row."""
    worst, failures = dict(table_clearance_m=np.inf, inter_arm_gap_m=np.inf), []
    times = sorted({row[1] for rows in plans.values() for row in rows})
    for t in times:
        q = home.copy()
        for side, rows in plans.items():
            row = min(rows, key=lambda r: abs(r[1]-t))
            idx = ik.robot._q_indices[side]
            q[idx[:6]] = row[2][idx[:6]]
            q[idx[6:]] = row[3]
        c = ik.check(q)
        worst["table_clearance_m"] = min(worst["table_clearance_m"], c["table_clearance_m"])
        worst["inter_arm_gap_m"] = min(worst["inter_arm_gap_m"], c["inter_arm_gap_m"])
        if not c["passed"]:
            failures.append(dict(t=t, issues=c["issues"]))
    return worst, failures


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--variation", required=True)
    parser.add_argument("--tracks", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    bands = json.loads(args.tracks.read_text())
    ik = build(args.variation)
    home = ik.seed.copy()
    decisions = {}
    for band in bands:
        decisions.setdefault(round(band["engage_s"], 1), []).append(band)
    report = dict(variation=args.variation, tracks=str(args.tracks), scope="sampled native IK and FCL meshes (arms, table); rope not a collision body; no physics",
                  grasp="vertical pinch, jaws across the rope, pad contact on the centre line; pregrasp/retreat 80 mm above",
                  decisions=[])
    for t0, group in sorted(decisions.items()):
        names = [b["name"] for b in group]
        options = []
        for sides in itertools.permutations(("left", "right"), len(group)):
            for flips in itertools.product((1, -1), repeat=len(group)):
                plans, reasons = {}, {}
                for band, side, flip in zip(group, sides, flips):
                    rows, reason = plan_band(ik, side, band, flip, home)
                    if rows is None:
                        reasons[band["name"]] = f"{side} flip {flip}: {reason}"
                    else:
                        plans[side] = rows
                if reasons:
                    options.append(dict(assignment=dict(zip(names, sides)), flips=dict(zip(names, flips)), passed=False, ik_failures=reasons))
                    continue
                worst, failures = combined(ik, plans, home)
                jump = max(float(np.abs(np.diff([r[2] for r in rows], axis=0)).max()) for rows in plans.values())
                options.append(dict(assignment=dict(zip(names, sides)), flips=dict(zip(names, flips)),
                                    passed=not failures, collision_failures=failures[:5], max_joint_step_rad=jump, **worst,
                                    tcp_rows={side: [dict(kind=r[0], t=r[1], q=np.round(r[2][ik.robot._q_indices[side][:6]], 5).tolist(),
                                                          gripper_m=r[3]) for r in rows] for side, rows in plans.items()}))
        good = [o for o in options if o["passed"]]
        best = min(good, key=lambda o: o["max_joint_step_rad"]) if good else None
        report["decisions"].append(dict(t=t0, bands=names, passed=best is not None, chosen=best,
                                        rejected=[{k: v for k, v in o.items() if k != "tcp_rows"} for o in options if o is not best]))
        line = f"t={t0:5.1f} {names}: " + (f"OK {best['assignment']} flips {best['flips']} table {best['table_clearance_m']*1000:.1f} mm, "
                                         f"arms {best['inter_arm_gap_m']*1000:.0f} mm, max joint step {best['max_joint_step_rad']:.2f} rad"
                                         if best else "NO feasible assignment")
        print(line, flush=True)
        if not best:
            for o in options:
                print("   ", o["assignment"], o["flips"], o.get("ik_failures") or o.get("collision_failures"))
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=1, default=float)+"\n")


if __name__ == "__main__":
    main()
