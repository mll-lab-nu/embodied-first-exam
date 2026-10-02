"""Object-level checks for the below-easy Hedgehog settings (very_easy, easier).

very_easy: held at its resting orientation, the ball leaves the cage by translation alone.
easier:    no translation-only exit exists at the resting orientation; after a lift, one in-place
           roll about the exit axis (cage x) opens a straight exit.

Geometry is the frozen task scene (every visual and collision surface, mount and table) in the
cage frame. Two separate questions are answered:

1. Is the outside reachable by translation at the resting orientation? A breadth-first search on
   a 2 mm translation grid with intersection tests only. "No" means no grid route: a channel
   narrower than the grid step can be missed, so this is a design check, not an impossibility proof.
2. A concrete route, certified edge by edge with RigidPathChecker at a stated surface margin:
   lift, (easier only) roll, then a straight horizontal pull toward the robot.

No robot, gripper, IK or physics is involved.
"""
from collections import deque
from pathlib import Path

import fcl
import numpy as np
from scipy.spatial.transform import Rotation

from topogym.planning.rigid_reference.geometry import RigidPathChecker, matrix, pose_dict
from .object_oracle import frozen_problem
from .variant_oracle import initial_free

GRID_STEP_M = .002
LIFT_MARGIN_M = .0002       # the ball starts 0.5 mm above its support
MARGIN_M = .001             # certified clearance while rolling and pulling
LIFTS_M = tuple(np.arange(0., .0601, .005))
PULL_AZIMUTHS_DEG = tuple(range(150, 211, 2))   # 180 deg = toward the robot (cage frame -x)
ROLLS_DEG = tuple(sorted((a for a in range(-150, 151, 5) if abs(a) >= 15), key=abs))


def _collides(checker, pose):
    fixed, moving = checker.pair.objects
    fixed.setTransform(fcl.Transform())
    t = matrix(*pose)
    moving.setTransform(fcl.Transform(t[:3, :3], t[:3, 3]))
    return fcl.collide(fixed, moving, fcl.CollisionRequest(), fcl.CollisionResult()) > 0


def translation_reachable(checker, start, outside_radius_m, *, step=GRID_STEP_M, height_m=.12):
    """True if a grid route at fixed orientation leads from ``start`` to a pose whose ball centre
    is farther than ``outside_radius_m`` from the cage axis, i.e. entirely beside the cage."""
    origin, rotation = np.asarray(start[0], float), start[1]
    reach, top = int(np.ceil(outside_radius_m / step)) + 1, int(np.ceil(height_m / step))
    seen, queue = {(0, 0, 0)}, deque([(0, 0, 0)])
    while queue:
        cell = queue.popleft()
        p = origin + step * np.asarray(cell)
        if np.hypot(p[0], p[1]) > outside_radius_m:
            return True
        for d in ((1, 0, 0), (-1, 0, 0), (0, 1, 0), (0, -1, 0), (0, 0, 1), (0, 0, -1)):
            nxt = (cell[0] + d[0], cell[1] + d[1], cell[2] + d[2])
            if nxt in seen or max(abs(nxt[0]), abs(nxt[1])) > reach or not 0 <= nxt[2] <= top:
                continue
            seen.add(nxt)
            if not _collides(checker, (origin + step * np.asarray(nxt), rotation)):
                queue.append(nxt)
    return False


def straight_pull(lift, pull, start, outside_radius_m):
    """First certified [start, raised, outside] route: vertical lift, then a horizontal pull."""
    p0, r = start
    for height in LIFTS_M:
        raised = (p0 + [0., 0., height], r)
        lifted = lift.edge(start, raised) if height else dict(passed=True)
        if not lifted["passed"]:
            return None
        for azimuth in sorted(PULL_AZIMUTHS_DEG, key=lambda a: abs(a - 180)):
            d = np.array([np.cos(np.radians(azimuth)), np.sin(np.radians(azimuth)), 0.])
            out = (raised[0] + d * (outside_radius_m + .01), r)
            pulled = pull.edge(raised, out)
            if pulled["passed"]:
                return dict(lift_m=float(height), azimuth_deg=azimuth, poses=[start, raised, out],
                            clearance_lower_bound_m=pulled["clearance_lower_bound_m"])
    return None


def check_variant(variation, output, *, seed=0):
    """Design report for one below-easy setting: 'very_easy', 'easier', or why neither."""
    task, ball, fixed, frame, initial, report = frozen_problem(output, seed=seed, variation=variation)
    outside = report["asset_report"]["cage_geometry"]["outer_radius_m"] + float(
        np.linalg.norm(ball.vertices, axis=1).max()) + .005
    entry = RigidPathChecker(fixed, ball)
    lift = RigidPathChecker(fixed, ball, margin_m=LIFT_MARGIN_M)
    pull = RigidPathChecker(fixed, ball, margin_m=MARGIN_M)
    result = dict(variation_id=task.variation_id, instance_id=task.instance_id, seed=seed,
                  frame="hedgehog_cage", initial_pose=pose_dict(initial),
                  initial_free=bool(initial_free(entry, initial)), grid_step_m=GRID_STEP_M,
                  margin_m=MARGIN_M, scope="ball-only object geometry; no robot, gripper, IK or physics")
    if not result["initial_free"]:
        return dict(result, design="invalid_initial_pose")
    result["translation_exit_at_rest"] = translation_reachable(entry, initial, outside)
    if result["translation_exit_at_rest"]:
        route = straight_pull(lift, pull, initial, outside)
        return dict(result, design="very_easy" if route else "very_easy_without_certified_pull",
                    route=_public(route))
    p0, r0 = initial
    for height in LIFTS_M[1:]:
        raised = (p0 + [0., 0., height], r0)
        if not lift.edge(initial, raised)["passed"]:
            break
        for angle in ROLLS_DEG:
            turned = (raised[0], Rotation.from_rotvec(np.radians(angle) * np.array([1., 0., 0.])) * r0)
            rolled = pull.edge(raised, turned)
            if not rolled["passed"]:
                continue
            route = straight_pull(lift, pull, turned, outside)
            if route:
                route["poses"] = [initial, raised, *route["poses"]]
                return dict(result, design="easier", roll_lift_m=float(height), roll_deg=angle,
                            roll_clearance_lower_bound_m=rolled["clearance_lower_bound_m"], route=_public(route))
    return dict(result, design="blocked")


def _public(route):
    return None if route is None else dict(route, poses=[pose_dict(p) for p in route["poses"]])


def settle_check(variation, output, *, seconds=3., seed=0):
    """Hold the robot at home on CPU and report how far the resting ball moves under gravity."""
    from topogym.planning.rigid_reference.feedback import body_pose
    from topogym.simulator import Env, SimulatorConfig
    config = SimulatorConfig(task_id="hedgehog_in_cage", variation_id=variation, compute_backend="cpu",
                             enable_rgb=False, physics_dt_s=.025, solver_substeps=40, control_decimation=1,
                             max_physics_steps=None, work_dir=Path(output) / "scene")
    with Env(config) as env:
        env.reset(seed=seed)
        hold = {name: {"joint_position_rad": list(group["joint_position_rad"])}
                for name, group in env._robot.observe().items()}
        start = body_pose(env._world.read_state()["bodies"]["hedgehog_ball"])
        for _ in range(int(round(seconds / config.physics_dt_s))):
            env.step(hold)
        end = body_pose(env._world.read_state()["bodies"]["hedgehog_ball"])
        task = env._task
        return dict(variation_id=task.variation_id, instance_id=task.instance_id, seconds=seconds,
                    physics_dt_s=config.physics_dt_s, solver_substeps=config.solver_substeps, backend="cpu",
                    ball_translation_mm=float(np.linalg.norm(end[0] - start[0]) * 1000),
                    ball_rotation_deg=float(np.degrees((end[1] * start[1].inv()).magnitude())),
                    terminated=bool(task.result.terminated), reason=task.result.reason)


if __name__ == "__main__":
    import argparse
    from topogym.utils.io import write_json_atomic
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--variant", required=True, choices=("very_easy", "easier"))
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--settle-seconds", type=float, default=0., help="also run a CPU gravity settle")
    args = parser.parse_args()
    report = check_variant(args.variant, args.output)
    if args.settle_seconds:
        report["settle"] = settle_check(args.variant, args.output, seconds=args.settle_seconds)
    write_json_atomic(args.output / "below_easy_check.json", report)
    print(report["variation_id"], report["design"], report.get("settle", ""))
