"""Current CLASSIC/keyhole geometry witnesses using rechecked historical hints.

Some cage visual meshes join closed components nonmanifoldly. Containment is
checked on every closed collision cell; distances also include all authored
visual surfaces. No mesh or initial pose is modified by this planner.
"""
import json
from pathlib import Path

import numpy as np
import trimesh
from scipy.spatial.transform import Rotation

from topogym.planning.rigid_reference.geometry import RigidPathChecker, combine_meshes, pose_dict
from topogym.planning.rigid_reference.feedback import body_pose
from topogym.planning.rigid_reference.search import check_path
from topogym.planning.rigid_reference.rrt import connect_search
from topogym.utils.io import to_jsonable
from .object_oracle import frozen_problem, shorten


def collision_solids(mesh):
    parts = []
    for component in mesh.metadata["components"]:
        if "/visual_" in component["name"]:
            continue
        first = component["first_face"]
        faces = mesh.faces[first:first+component["face_count"]]
        indices, inverse = np.unique(faces, return_inverse=True)
        # Do not duplicate the entire cage vertex array for every collision
        # cell. Only these vertices participate in this cell's solid.
        part = trimesh.Trimesh(mesh.vertices[indices], inverse.reshape(-1, 3), process=True)
        if not part.is_watertight:
            raise ValueError("A declared collision cell is not closed")
        parts.append(part)
    if not parts:
        raise ValueError("No closed collision geometry")
    return combine_meshes(parts)


def initial_free(checker, pose):
    if checker.clearance(pose) <= checker.margin+checker.error:
        return False
    solid = RigidPathChecker(collision_solids(checker.fixed), collision_solids(checker.moving),
                             margin_m=checker.margin, distance_error_m=checker.error)
    return solid.initial_free(pose)


def reference_route(variation):
    data = json.loads(Path(__file__).with_name("reference_routes.json").read_text())[variation]
    return [(np.asarray(p[:3]), Rotation.from_quat(p[3:])) for p in data["poses"]], data


def plan_variant_object_path(output, *, variation, seed=0, iterations=40000, clearance_m=.0001):
    task, ball, fixed, frame, initial, report = frozen_problem(output, seed=seed, variation=variation)
    checker = RigidPathChecker(fixed, ball, margin_m=clearance_m)
    report.update(status="searching", accepted_proof=False, task_success=False,
                  robot_ik_verified=False, robot_execution_verified=False,
                  clearance_requested_m=clearance_m, distance_error_assumption_m=checker.error,
                  containment="closed collision cells; all visual and collision surfaces checked for intersection")
    if not initial_free(checker, initial):
        report.update(status="initial_geometry_invalid", obstruction=checker.obstruction(initial, checker.clearance(initial)))
        return report
    route, reference = reference_route(variation)
    report["historical_reference"] = reference
    report["reference_recheck"] = check_path(checker, route)
    if not report["reference_recheck"]["passed"]:
        report["status"] = "reference_geometry_rejected"
        return report
    if np.linalg.norm(initial[0]-route[0][0]) < 1e-10 and (initial[1].inv()*route[0][1]).magnitude() < 1e-10:
        path = [initial, *route[1:]]
    else:
        raised = (np.array([0., 0., 0.]), initial[1])
        lift = checker.edge(initial, raised)
        start = raised if lift["passed"] else initial
        rng = np.random.default_rng(seed+10)
        def sample(rng):
            r = (Rotation.from_rotvec(rng.normal(0., .5, 3))*initial[1] if rng.random() < .3
                 else Rotation.random(random_state=rng))
            return rng.uniform([-.02, -.02, -.03], [.045, .02, .045]), r
        prefix, evidence = connect_search(checker, start, route[0], sample, rng=rng,
                                           iterations=iterations, step_m=.01)
        report["prefix_search"] = evidence
        if prefix is None:
            report["status"] = "no_prefix_in_finite_search"
            return report
        path = ([initial] if lift["passed"] else [])+shorten(checker, prefix)+route[1:]
    region = task.goal_region
    goal_world = np.r_[region.center_xy_m, region.table_height_m+region.placement_height_m/2]
    goal = frame[1].inv().apply(goal_world-frame[0])
    # Keep the full ball outside the cylinder while turning toward the goal.
    path += [(np.array([.22, goal[1], path[-1][0][2]]), path[-1][1]), (goal, path[-1][1])]
    certificate = check_path(checker, path)
    vertices = frame[0]+frame[1].apply(path[-1][0]+path[-1][1].apply(task.placement_vertices["hedgehog_ball"]))
    contained = bool(region.contains(vertices))
    report.update(status="object_witness_verified" if certificate["passed"] and contained else "route_rejected",
                  certificate=certificate, all_target_vertices_in_goal=contained,
                  route=dict(frame="hedgehog_cage", moving="hedgehog_ball", poses=[pose_dict(p) for p in path]))
    return report


def audit_variant_object_path(witness, output):
    task, ball, fixed, frame, initial, frozen = frozen_problem(output, seed=witness["seed"],
                                                             variation=witness["variation_id"])
    keys = ("task_id", "variation_id", "model_revision", "terminal_revision", "instance_id",
            "initial_poses", "goal_region", "asset_sha256")
    if any(to_jsonable(witness.get(k)) != to_jsonable(frozen[k]) for k in keys):
        raise ValueError("Witness identity differs from the current instance")
    route = witness["route"]
    if route["frame"] != "hedgehog_cage" or route["moving"] != "hedgehog_ball":
        raise ValueError("Wrong moving body or frame")
    poses = [body_pose(p) for p in route["poses"]]
    if len(poses) < 2 or np.linalg.norm(poses[0][0]-initial[0]) > 1e-10 or (poses[0][1].inv()*initial[1]).magnitude() > 1e-10:
        raise ValueError("Wrong initial pose")
    checker = RigidPathChecker(fixed, ball, margin_m=float(witness["clearance_requested_m"]))
    free = initial_free(checker, initial)
    checked = check_path(checker, poses)
    vertices = frame[0]+frame[1].apply(poses[-1][0]+poses[-1][1].apply(task.placement_vertices["hedgehog_ball"]))
    contained = bool(task.goal_region.contains(vertices))
    passed = free and checked["passed"] and contained
    return dict(status="object_witness_verified" if passed else "rejected", passed=passed,
                identity_matched=True, initial_free=free, certificate=checked,
                all_target_vertices_in_goal=contained, accepted_robot_proof=False, task_success=False)
