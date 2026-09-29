#!/usr/bin/env python3
"""Zero-physics key-pose check for one Fiber Bundling variant (seed 0).

Checks, with Genesis IK/FK and FCL only: an open-hand path from home to the
sheath grasp and a straight descent; for every strand in its initial shape, the
combing key poses (select, approach, press, release, retract, center) joined by
FK-checked joint references; and the axial feed. Strands are held rigid in the
grasped-link frame, so this is not evidence about how they deform. The physics
step count must stay 0. Not a Task proof.
"""
import argparse
import hashlib
import json
from pathlib import Path
import sys
import time
import traceback

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import numpy as np
import torch

from topogym.simulator import Env, SimulatorConfig
from topogym.planning.fiber_bundling.keyframes import GRASP_LINK, link_pose, strand_measures
from topogym.planning.fiber_bundling.kinematics import STRAND_MARGIN_M, FiberIK
from topogym.planning.fiber_bundling.stages import COMBS, FEED, PICKUPS, plan_comb, plan_feed, plan_pickup
from topogym.planning.buzz_wire_3d.policy import rotation


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def summarize(kin, plan, limits):
    refs = plan["refs"]
    q = np.array([row["qpos"][:7] for row in refs])
    strand_gaps = []
    for row in refs[::10]+refs[-1:]:
        kin.clearance(np.asarray(row["qpos"]))  # places the robot shapes
        strand_gaps.append(kin.held_gaps((np.asarray(row["position_m"]), rotation(row["quaternion_wxyz"])))[1]
                           + STRAND_MARGIN_M)
    return dict(keyframes=[row["label"] for row in plan["keyframes"]],
                rejected_edges=plan["rejected_shortcuts"], joint_references=len(refs),
                planned_s=refs[-1]["time_s"],
                minimum_clearance_m=min(edge["minimum_clearance_m"] for edge in plan["edges"]),
                minimum_gripper_strand_distance_m=float(min(strand_gaps)),
                minimum_joint_limit_margin_rad=float(np.minimum(q-limits[:, 0], limits[:, 1]-q).min()),
                maximum_joint_step_rad=float(np.abs(np.diff(q, axis=0)).max()) if len(q) > 1 else 0.)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("variant", choices=("easy", "medium", "hard"))
    parser.add_argument("--config", type=Path, required=True, help="SimulatorConfig JSON used by the physics run")
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    torch.set_num_threads(1)
    args.output.mkdir(parents=True, exist_ok=False)
    sources = {str(path.relative_to(ROOT)): sha(path) for path in (ROOT / "topogym").rglob("*.py")}
    sources[str(Path(__file__).resolve().relative_to(ROOT))] = sha(Path(__file__).resolve())
    values = json.loads(args.config.read_text())
    values.update(variation_id=args.variant, enable_rgb=False, enable_privileged=True,
                  work_dir=str(args.output / "scene"))
    report = dict(variant=args.variant, seed=0, passed=False, physical_steps=0, task_success_verified=False,
                  scope="Zero-physics sampled IK/FCL key-pose connections; strands rigid in the grasped-link frame",
                  config=values, source_sha256=sources)
    paths = {}
    started = time.monotonic()
    try:
        with Env(SimulatorConfig(**values)) as env:
            env.reset(seed=0)
            state = env._world.read_state()
            layout = env._task.layout
            kin = FiberIK(env)
            limits = np.asarray(kin.group.arm_limits_rad)
            rows = strand_measures(state, layout)
            report["initial_strands"] = rows
            pickup, errors = None, []
            for parameters in PICKUPS:
                try:
                    pickup = dict(parameters=parameters, **plan_pickup(env, kin, state, **parameters))
                    break
                except ValueError as error:
                    errors.append(dict(parameters=parameters, error=str(error)))
            report["pickup"] = dict(rejected=errors)
            if pickup is None:
                raise ValueError("No pickup candidate passed")
            paths["pickup"] = pickup
            report["pickup"].update(parameters=pickup["parameters"],
                                    free_transfer_points=len(pickup["free_transfer"]),
                                    minimum_descent_clearance_m=min(pickup["descent_clearance_m"]))
            kin.seed = np.asarray(pickup["descent_qpos"][-1])
            report["combs"], failed = [], []
            for strand in np.argsort([-row["max_radius_m"] for row in rows]):
                tried, plan = [], None
                for parameters in COMBS:
                    try:
                        plan = plan_comb(kin, state, layout, parameters, strand=int(strand))
                        break
                    except ValueError as error:
                        tried.append(dict(parameters=parameters, error=str(error)))
                entry = dict(strand=int(strand), fan_deg=rows[strand]["fan_deg"],
                             tip_radius_m=rows[strand]["tip_radius_m"], rejected=tried)
                if plan is None:
                    failed.append(int(strand))
                else:
                    paths[f"comb_strand_{strand:02d}"] = dict(parameters=parameters, **plan)
                    entry.update(parameters=parameters, roll_deg=plan["roll_deg"],
                                 d0_m=plan["geometry"]["d0_m"],
                                 press=summarize(kin, plan["guides"][0], limits),
                                 back=summarize(kin, plan["guides"][1], limits))
                    kin.seed = np.asarray(plan["end_qpos"])
                report["combs"].append(entry)
            feed = plan_feed(kin, state, FEED["front_s_m"], FEED["maximum_front_offset_m"])
            paths["feed"] = feed
            report["feed"] = dict(summarize(kin, feed["plan"], limits),
                                  maximum_front_offset_m=max(feed["front_offsets_m"]))
            if env._world.physics_step != 0:
                raise AssertionError("A read-only check advanced physics")
            # Other sessions share this worktree. Modules were imported at start, so a
            # later edit does not change this process; record such edits instead.
            report["sources_changed_during_check"] = sorted(
                name for name, digest in sources.items()
                if not (ROOT / name).exists() or sha(ROOT / name) != digest)
            p, r = link_pose(state, GRASP_LINK)
            report.update(passed=not failed, failed_strands=failed, instance_id=env._task.instance_id,
                          grasp_link=GRASP_LINK, initial_grasp_link_pose=[p.tolist(), r.as_quat()[[3, 0, 1, 2]].tolist()])
    except BaseException:
        report["error"] = traceback.format_exc()
        print(report["error"], flush=True)
    report["elapsed_wall_s"] = time.monotonic()-started
    (args.output / "path.json").write_text(json.dumps(paths))
    (args.output / "report.json").write_text(json.dumps(report, indent=2))
    print(json.dumps({k: v for k, v in report.items() if k not in ("source_sha256", "config", "initial_strands")},
                     indent=1), flush=True)
    raise SystemExit(0 if report["passed"] else 1)


if __name__ == "__main__":
    main()
