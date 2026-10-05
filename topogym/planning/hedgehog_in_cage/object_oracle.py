"""Constructive object-only witness for the current waisted-window cage.

The oracle includes every authored collision and visible surface, the mount,
and the table. It issues no simulator commands. Robot and physical execution
qualifications must be supplied separately.
"""
from pathlib import Path

import numpy as np
import trimesh
from scipy.spatial.transform import Rotation

from topogym.planning.rigid_reference.feedback import body_pose, relative_pose
from topogym.planning.rigid_reference.geometry import (
    RigidPathChecker, combine_meshes, freeze_scene, matrix, pose_dict,
)
from topogym.planning.rigid_reference.rrt import connect_search
from topogym.planning.rigid_reference.search import check_path


def frozen_problem(output, *, seed=0, variation="medium"):
    variation = variation.removeprefix("hedgehog_in_cage_")
    task, spec, scene, meshes, report = freeze_scene(
        "hedgehog_in_cage", variation, seed, Path(output)/"assets")
    revisions = {
        "easy": "simulator_v1", "medium": "waisted4_dark_wood_v1", "hard": "fixed_v3_s5_post",
        "very_easy": "below_easy_v2", "easier": "below_easy_v2",
    }
    if variation not in revisions or task.model_revision != revisions[variation]:
        raise ValueError("Unrecognized Hedgehog variant/model revision")
    poses = {name: body_pose(p) for name, p in report["initial_poses"].items()}
    frame = poses["hedgehog_cage"]
    obstacles = []
    for name, mesh in meshes.items():
        if name == "hedgehog_ball":
            continue
        m = mesh.copy()
        m.apply_transform(matrix(*relative_pose(frame, poses[name])))
        obstacles.append(m)
    table = scene.env.world.table
    m = trimesh.creation.box(table.size)
    m.metadata["components"] = [dict(name="table", first_face=0, face_count=len(m.faces))]
    m.apply_transform(matrix(*relative_pose(frame, (np.array(table.pos), Rotation.identity()))))
    obstacles.append(m)
    report["asset_report"] = spec.metadata["asset_report"]
    report["frame"] = "hedgehog_cage"
    return task, meshes["hedgehog_ball"], combine_meshes(obstacles), frame, relative_pose(
        frame, poses["hedgehog_ball"]), report


def shorten(checker, path):
    """Deterministic farthest-visible shortcutting, with certified edges."""
    result, i = [path[0]], 0
    while i < len(path)-1:
        j = len(path)-1
        while j > i+1 and not checker.edge(path[i], path[j])["passed"]:
            j -= 1
        result.append(path[j])
        i = j
    return result


def plan_object_path(output, *, seed=0, iterations=20000, clearance_m=.001):
    task, ball, fixed, frame, initial, report = frozen_problem(output, seed=seed)
    entry = RigidPathChecker(fixed, ball)
    checker = RigidPathChecker(fixed, ball, margin_m=clearance_m)
    band = report["asset_report"]["window_band_center_m"]
    raised = (np.array([0., 0., band]), initial[1])
    outside = (np.array([0., -.23, band]), initial[1])
    report.update(status="searching", scope="finite-instance object-only constructive witness",
        accepted_proof=False, robot_ik_verified=False, robot_execution_verified=False,
        task_success=False, clearance_requested_m=clearance_m,
        distance_error_assumption_m=checker.error,
        interpolation="linear translation and shortest quaternion SLERP per edge",
        entry_margin_m=entry.margin, route=None)
    if not entry.initial_free(initial):
        report["status"] = "initial_geometry_invalid"
        return report
    prefix = check_path(entry, [initial, raised])
    report["initial_lift_certificate"] = prefix
    if not prefix["passed"] or not checker.initial_free(raised) or not checker.initial_free(outside):
        report["status"] = "lift_or_search_endpoint_invalid"
        return report
    rng = np.random.default_rng(seed)
    lower, upper = np.array([-.05, -.23, band-.07]), np.array([.05, .03, band+.05])
    def sample(rng):
        return rng.uniform(lower, upper), Rotation.random(random_state=rng)
    route, evidence = connect_search(checker, raised, outside, sample,
        rng=rng, iterations=iterations)
    report["search"] = dict(evidence, lower_m=lower.tolist(), upper_m=upper.tolist(), seed=seed)
    if not route:
        report["status"] = "no_route_in_finite_search"
        return report
    route = shorten(checker, route)
    # The full ball must fit the current placement region, including its spikes.
    region = task.goal_region
    goal_world = np.r_[region.center_xy_m, region.table_height_m+region.placement_height_m/2]
    goal = (frame[1].inv().apply(goal_world-frame[0]), outside[1])
    route.append(goal)
    certificate = check_path(checker, route)
    world_vertices = frame[0]+frame[1].apply(goal[0]+goal[1].apply(task.placement_vertices["hedgehog_ball"]))
    contained = region.contains(world_vertices)
    report["placement_geometry_contained"] = bool(contained)
    report["exit_certificate"] = certificate
    if not certificate["passed"] or not contained:
        report["status"] = "placement_extension_invalid"
        return report
    report.update(status="object_witness_verified", mechanism_geometry_path_verified=True,
        placement_path_verified=True, queries=entry.queries+checker.queries,
        route=dict(frame="hedgehog_cage", moving="hedgehog_ball",
                   poses=[pose_dict(p) for p in [initial, *route]],
                   prefix_certificate=prefix, transport_certificate=certificate),
        limitations=["Numerical FCL distances assume the stated 1 micrometre error budget",
                     "No robot, gripper, contact dynamics, or Task success qualification"])
    return report


def audit_object_path(witness, output):
    """Rebuild geometry and replay the supplied poses, ignoring success flags.

    The initial lift has a separate small clearance because the ball begins
    0.2 mm above its support. Every later edge must meet the requested transport
    margin. Neither an altered asset nor a substituted initial state is valid.
    """
    task, ball, fixed, frame, initial, frozen = frozen_problem(output, seed=witness["seed"])
    identity = ("task_id", "variation_id", "model_revision", "terminal_revision",
                "instance_id", "initial_poses", "goal_region", "asset_sha256")
    from topogym.utils.io import to_jsonable
    if any(to_jsonable(witness.get(key)) != to_jsonable(frozen[key]) for key in identity):
        raise ValueError("Witness identity differs from the rebuilt task/geometry")
    route = witness["route"]
    if route["frame"] != "hedgehog_cage" or route["moving"] != "hedgehog_ball":
        raise ValueError("Incorrect route frame or target")
    poses = [body_pose(p) for p in route["poses"]]
    if len(poses) < 3:
        raise ValueError("Witness omits the initial lift or transport")
    raised = (np.array([0., 0., frozen["asset_report"]["window_band_center_m"]]), initial[1])
    for actual, expected in zip(poses[:2], (initial, raised)):
        if (np.linalg.norm(actual[0]-expected[0]) > 1e-10
                or (actual[1]*expected[1].inv()).magnitude() > 1e-10):
            raise ValueError("Witness changes the task start or initial lift endpoint")
    margin = float(witness["clearance_requested_m"])
    if not np.isfinite(margin) or margin < .00005:
        raise ValueError("Invalid transport margin")
    entry = RigidPathChecker(fixed, ball)
    checker = RigidPathChecker(fixed, ball, margin_m=margin)
    start_free = entry.initial_free(poses[0])
    lift = check_path(entry, poses[:2])
    transport = check_path(checker, poses[1:])
    p, r = poses[-1]
    vertices = frame[0]+frame[1].apply(p+r.apply(task.placement_vertices["hedgehog_ball"]))
    contained = task.goal_region.contains(vertices)
    passed = start_free and lift["passed"] and transport["passed"] and contained
    return dict(status="object_witness_verified" if passed else "object_witness_rejected",
                passed=bool(passed), identity_matched=True, initial_free=start_free,
                lift=lift, transport=transport, all_target_vertices_in_goal=contained,
                accepted_robot_proof=False, task_success=False)
