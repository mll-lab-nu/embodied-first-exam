"""Constructive separation witnesses, recertified against frozen Claws geometry.

Only complete separation is required. These object routes neither command a
robot nor certify physical execution. Both visible and collision surfaces count.
"""
import json
from pathlib import Path

import numpy as np
import trimesh
from scipy.spatial.transform import Rotation

from topogym.planning.rigid_reference.feedback import body_pose, relative_pose
from topogym.planning.rigid_reference.geometry import (
    RigidPathChecker, freeze_scene, matrix, pose_dict,
)
from topogym.planning.rigid_reference.search import check_path
from topogym.utils.io import to_jsonable

REVISIONS = {"easy": "pregrasp_weld_v2", "medium": "opposed_pregrasp_wide2_v1", "hard": "pregrasp_scaled_inset3mm_weld_v4"}
ROUTES = Path(__file__).with_name("reference_routes.json")


def frozen_problem(output, *, variation, seed=0):
    variation = variation.removeprefix("interlocked_claws_")
    task, spec, scene, meshes, report = freeze_scene("interlocked_claws", variation, seed, Path(output)/"assets")
    if variation not in REVISIONS or task.model_revision != REVISIONS[variation]:
        raise ValueError("Unrecognized Claws variant/model revision")
    target, = task.placement_targets
    other, = task.placement_remainder
    poses = {name: body_pose(p) for name, p in report["initial_poses"].items()}
    table = scene.env.world.table
    mesh = trimesh.creation.box(table.size)
    mesh.metadata["components"] = [dict(name="table", first_face=0, face_count=len(mesh.faces))]
    mesh.apply_transform(matrix(np.array(table.pos), Rotation.identity()))
    report.update(asset_report=to_jsonable(spec.metadata["asset_report"]), target=target, other=other,
                  frame="target piece authored frame", variation=variation)
    return task, meshes, poses, mesh, report


def world_pose(base, relative):
    p, r = base
    q, s = relative
    return p+r.apply(q), r*s


def authored_easy_route(task):
    """Sample the authored coupled-screw segments; each sample is a relative pose."""
    from topogym.assets.geometry.interlocked_claws import FamilyModel
    model = FamilyModel(task.geometry_family)
    poses = []
    for segment in model.segments:
        count = max(4, int(np.ceil(segment.rotation_angle/np.deg2rad(5.))))
        for u in np.linspace(0., 1., count+1)[1:]:
            t = segment.at(u)
            poses.append((t[:3, 3].copy(), Rotation.from_matrix(t[:3, :3])))
    return poses, dict(source="FamilyModel.segments", segments=[s.name for s in model.segments])


def reference_route(variation):
    data = json.loads(ROUTES.read_text())[variation]
    return [body_pose(p) for p in data["poses"]], {k: v for k, v in data.items() if k != "poses"}


def separation_route(task, variation):
    if variation == "easy":
        return authored_easy_route(task)
    return reference_route(variation)


def plan_object_path(output, *, variation, seed=0, clearance_m=.001):
    output = Path(output)
    task, meshes, poses, table, report = frozen_problem(output, variation=variation, seed=seed)
    target, other = report["target"], report["other"]
    initial = relative_pose(poses[target], poses[other])
    report.update(status="checking", scope="finite-instance object-only constructive witness",
                  accepted_proof=False, robot_ik_verified=False, robot_execution_verified=False,
                  task_success=False, clearance_requested_m=clearance_m,
                  interpolation="linear translation and shortest quaternion SLERP per edge")
    pair = RigidPathChecker(meshes[target], meshes[other], margin_m=clearance_m)
    report["distance_error_assumption_m"] = pair.error
    if not RigidPathChecker(meshes[target], meshes[other]).initial_free(initial):
        report["status"] = "initial_geometry_invalid"
        return report
    route, provenance = separation_route(task, variation)
    if variation != "easy":
        start = route[0]
        if np.linalg.norm(start[0]-initial[0]) > 1e-9 or (start[1].inv()*initial[1]).magnitude() > 1e-9:
            report.update(status="reference_route_start_mismatch")
            return report
        route = route[1:]
    relative = [initial, *route]
    report["route_provenance"] = provenance
    report["separation_certificate"] = check_path(pair, relative)
    if not report["separation_certificate"]["passed"]:
        report["status"] = "separation_route_rejected"
        return report
    # One world realization: the target stays at its authored pose while the other piece moves.
    other_world = [world_pose(poses[target], p) for p in relative]
    other_table = RigidPathChecker(table, meshes[other], margin_m=clearance_m)
    report["separation_table_certificate"] = check_path(other_table, other_world)
    if not report["separation_table_certificate"]["passed"]:
        report["status"] = "separation_table_rejected"
        return report
    reached, _, metrics = separated_poses(task, {target: poses[target], other: other_world[-1]})
    report.update(status="object_witness_verified" if reached else "separation_goal_rejected",
                  mechanism_geometry_path_verified=True, separation_goal=metrics,
                  queries=pair.queries+other_table.queries,
                  route=dict(frame=target, moving=other, relative_poses=[pose_dict(p) for p in relative],
                             other_world_poses=[pose_dict(p) for p in other_world]),
                  limitations=["Numerical FCL distances assume the stated 1 micrometre error budget",
                               "One world realization with the target fixed; the robot may choose another",
                               "No robot, gripper, contact dynamics, or Task success qualification"])
    return report


def separated_poses(task, poses):
    from topogym.tasks.interlocked_claws.terminal import separation_candidate
    state = dict(bodies={name: dict(**pose_dict(pose), linear_velocity_m_s=[0., 0., 0.],
                                   angular_velocity_rad_s=[0., 0., 0.]) for name, pose in poses.items()})
    return separation_candidate(state, task.placement_vertices,
                                minimum_separation_m=task.config["minimum_separation_m"])


def audit_object_path(witness, output):
    """Rebuild the geometry and replay every certified layer of a submitted witness."""
    task, meshes, poses, table, frozen = frozen_problem(output, variation=witness["variation_id"], seed=witness["seed"])
    keys = ("task_id", "variation_id", "model_revision", "terminal_revision", "instance_id",
            "initial_poses", "goal_region", "asset_sha256")
    if any(to_jsonable(witness.get(k)) != to_jsonable(frozen[k]) for k in keys):
        raise ValueError("Witness identity differs from the rebuilt task/geometry")
    target, other = frozen["target"], frozen["other"]
    route = witness["route"]
    if route["frame"] != target or route["moving"] != other:
        raise ValueError("Incorrect route frame or moving piece")
    margin = float(witness["clearance_requested_m"])
    if not np.isfinite(margin) or margin < .00005:
        raise ValueError("Invalid clearance margin")
    relative = [body_pose(p) for p in route["relative_poses"]]
    initial = relative_pose(poses[target], poses[other])
    if np.linalg.norm(relative[0][0]-initial[0]) > 1e-10 or (relative[0][1].inv()*initial[1]).magnitude() > 1e-10:
        raise ValueError("Witness changes the authored initial relative pose")
    pair = RigidPathChecker(meshes[target], meshes[other], margin_m=margin)
    free = RigidPathChecker(meshes[target], meshes[other]).initial_free(initial)
    separation = check_path(pair, relative)
    other_world = [world_pose(poses[target], p) for p in relative]
    table_check = check_path(RigidPathChecker(table, meshes[other], margin_m=margin), other_world)
    reached, _, metrics = separated_poses(task, {target: poses[target], other: other_world[-1]})
    passed = free and separation["passed"] and table_check["passed"] and reached
    return dict(status="object_witness_verified" if passed else "object_witness_rejected", passed=bool(passed),
                identity_matched=True, initial_free=free, separation=separation, separation_table=table_check,
                separation_goal=metrics, accepted_robot_proof=False, task_success=False)
