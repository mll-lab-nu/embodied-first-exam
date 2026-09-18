"""Continuously bound interpiece clearance on the recorded joint interpolation."""
import argparse
import json
from pathlib import Path
import time

import numpy as np

from .collision import ClawCollision
from .geometry import ClawAssembly
from .reference import ReferenceMotion


def point_motion_radii(assembly, motion):
    radii = np.zeros((2, 16))
    for i, piece in enumerate(assembly.reference["pieces"]):
        vertices = assembly.bodies[i].mesh.vertices
        grasp = motion.grasps[i]
        radius = float(np.linalg.norm(vertices@grasp[:3, :3].T+grasp[:3, 3], axis=1).max())
        k = piece["gripper_body"]
        while k:
            body = assembly.reference["bodies"][k]
            for joint in reversed(body["joints"]):
                if joint["type"] != 3 or np.linalg.norm(joint["position"]) != 0:
                    raise ValueError("Bound assumes the source's zero-pivot revolute arm joints")
                radii[i, joint["qpos"]] = radius
            radius += float(np.linalg.norm(body["position"]))
            k = body["parent"]
    return radii


def audit(output):
    output = Path(output); output.mkdir(parents=True, exist_ok=True)
    assembly, motion = ClawAssembly(), ReferenceMotion()
    collision = ClawCollision(assembly)
    radii = point_motion_radii(assembly, motion)
    samples, leaves, failures = {}, [], []
    started = time.monotonic()

    def sample(t):
        if t not in samples:
            q, _, poses, held, _ = motion.sample(t)
            samples[t] = (q, float(collision.clearance(poses)), held)
        return samples[t]

    def interval(a, b, depth=0):
        mid = (a+b)/2
        qa, ga, _ = sample(a); qb, gb, _ = sample(b); qm, gm, held = sample(mid)
        # Linear q interpolation on this original saved interval. For a held
        # part, sum revolute arc-length bounds; released parts are stationary.
        travel = float(np.sum(radii*np.asarray(held)[:, None]*np.maximum(abs(qa-qm), abs(qb-qm))))
        if min(ga, gb, gm) < 0:
            failures.append(dict(start=a, end=b, minimum_sampled_clearance_m=min(ga, gb, gm)))
        elif gm-travel > 1e-8:
            leaves.append(dict(start=a, end=b, clearance_lower_bound_m=gm-travel))
        elif depth >= 20:
            failures.append(dict(start=a, end=b, reason="unresolved continuous bound"))
        else:
            interval(a, mid, depth+1); interval(mid, b, depth+1)

    for i, (a, b) in enumerate(zip(motion.times[:-1], motion.times[1:])):
        # Release boundaries preserve the exact saved object pose; check both
        # sides explicitly, while midpoint held flags define the interval.
        interval(float(a), float(b))
        if i % 250 == 0:
            print(f"Reference {i}/{len(motion.times)-1}; queries {len(samples)}; failures {len(failures)}", flush=True)
    straight = []
    poses = [b.pose.copy() for b in assembly.bodies]
    for axis in range(3):
        for sign in (-1, 1):
            first = None
            for distance in np.linspace(.001, .4, 400):
                changed = poses[1].copy(); changed[axis, 3] += sign*distance
                if collision.clearance([poses[0], changed]) < 0:
                    first = float(distance); break
            straight.append(dict(axis="xyz"[axis], sign=sign, first_intersection_sample_m=first,
                                 sample_spacing_m=.001))
    report = dict(passed=not failures, scope="continuous interpiece surface-clearance bound for source joint-linear playback",
        source_motion_sha256=motion.sha256, source_intervals=len(motion.times)-1, queries=len(samples),
        certified_leaf_intervals=len(leaves), minimum_sampled_clearance_m=min(s[1] for s in samples.values()),
        minimum_certified_clearance_m=min((l["clearance_lower_bound_m"] for l in leaves), default=None),
        failures=failures, straight_translation_controls=straight,
        robot_collision_certified=False, dynamics_certified=False, wall_seconds=time.monotonic()-started)
    (output/"reference_audit.json").write_text(json.dumps(report, indent=2)+"\n")
    (output/"continuous_intervals.json").write_text(json.dumps(leaves)+"\n")
    print(json.dumps(report, indent=2), flush=True)
    return report


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if not audit(args.output)["passed"]:
        raise SystemExit(1)
