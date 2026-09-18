"""Geometric witnesses for the three-links-per-span horseshoe prototype.

This is a configuration-space experiment, not a robot controller. Independent
bodies follow coordinated transforms; no simulator joints are added. A witness
only qualifies the stated geometry and interpolated path, not frictional
execution or arbitrary horseshoe products.

Uses python-fcl, available in the baseline .venv-gs121 planning environment.
The rendering environment can replay saved poses without importing this module.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import time

import fcl
import numpy as np
from scipy.spatial.transform import Rotation
import trimesh

from .geometry import HorseshoeAssembly, geometry_report, load_template
from .witness_motion import fold_transforms, interpolate

GROUPS = (
    ("horseshoe_left", "chain_upper_1", "chain_lower_1"),
    ("chain_upper_2", "chain_lower_2"),
    ("horseshoe_right", "chain_upper_3", "chain_lower_3"),
    ("target_ring",),
)
PAIRS = ((0, 1), (0, 2), (1, 2), (0, 3), (1, 3), (2, 3))


def outer_collision_mesh(body):
    """A conservative polyhedral cover of the actual URDF compound geometry.

    Band convex pieces are used verbatim. Cylinder side planes lie outside the
    analytic cylinders; sphere face planes lie outside the analytic spheres.
    Thus a positive separation of these covers implies separation of the URDF
    capsule union, without substituting a hull across a ring aperture.
    """
    pieces = [p.copy() for p in body.convex]
    unit_sphere = trimesh.creation.icosphere(subdivisions=2)
    plane_radius = np.einsum("ij,ij->i", unit_sphere.face_normals, unit_sphere.triangles_center).min()
    unit_sphere.apply_scale(1./plane_radius)
    for loop in body.loops:
        points = loop.points()
        for a, b in zip(points, np.roll(points, -1, axis=0)):
            sphere = unit_sphere.copy().apply_scale(loop.wire_radius).apply_translation(a)
            pieces.append(sphere)
            length = np.linalg.norm(b-a)
            cylinder = trimesh.creation.cylinder(radius=loop.wire_radius/np.cos(np.pi/24),
                                                height=length, sections=24)
            transform = trimesh.geometry.align_vectors([0, 0, 1], (b-a)/length)
            transform[:3, 3] = (a+b)/2
            pieces.append(cylinder.apply_transform(transform))
    return trimesh.util.concatenate(pieces)


def collision_object(mesh):
    model = fcl.BVHModel()
    model.beginModel(len(mesh.vertices), len(mesh.faces))
    model.addSubModel(mesh.vertices, mesh.faces)
    model.endModel()
    return fcl.CollisionObject(model)


class WitnessModel:
    def __init__(self, template=None, *, scale=2.0, conservative=True):
        self.assembly = HorseshoeAssembly(template, scale)
        if self.assembly.template["chain"]["links_per_span"] != 3:
            raise ValueError("This witness family requires exactly three links per span")
        self.pivot = self.assembly.template["chain"]["link_radii"][0]*self.assembly.unit
        self.conservative = conservative
        self.meshes = {b.name: outer_collision_mesh(b) if conservative else b.visual.copy()
                       for b in self.assembly.bodies}
        self.group_meshes = [trimesh.util.concatenate([self.meshes[n] for n in names]) for names in GROUPS]
        self.objects = [collision_object(mesh) for mesh in self.group_meshes]
        self.request = fcl.DistanceRequest()
        self.calls = 0

    def distances(self, state):
        for obj, (rotation, position) in zip(self.objects, fold_transforms(state, self.pivot)):
            obj.setTransform(fcl.Transform(rotation, position))
        self.calls += 1
        return np.array([fcl.distance(self.objects[a], self.objects[b], self.request, fcl.DistanceResult())
                         for a, b in PAIRS])

    def initial_internal_clearance(self):
        values = []
        for group in GROUPS:
            objects = [collision_object(self.meshes[n]) for n in group]
            for i, a in enumerate(objects):
                for b in objects[i+1:]:
                    values.append(fcl.distance(a, b, self.request, fcl.DistanceResult()))
        return min(values)

    def motion_bounds(self, a, b):
        """Uniform whole-interval bounds on travel of any covered material point.

        Joint angles, translation and target SLERP have constant parameter
        rates. Each expression is a derivative norm bound integrated over the
        unit interval, hence half the bound applies from the nearer endpoint.
        """
        da = abs(b[0]-a[0])
        p = self.pivot
        middle_radius = np.linalg.norm(self.group_meshes[1].vertices-[-p, 0, 0], axis=1).max()
        right_radius = np.linalg.norm(self.group_meshes[2].vertices-[p, 0, 0], axis=1).max()
        ring_radius = np.linalg.norm(self.group_meshes[3].vertices, axis=1).max()
        angle = (Rotation.from_quat(a[4:]).inv()*Rotation.from_quat(b[4:])).magnitude()
        offset = max(np.linalg.norm(np.asarray(v[1:4])-[-p, 0, 0]) for v in (a, b))
        return np.array([0., .5*da*middle_radius, da*(right_radius+p),
            .5*da*(ring_radius+offset)+np.linalg.norm(np.asarray(b[1:4])-a[1:4])+ring_radius*angle])

    def separated_goal(self, state):
        bounds = []
        for mesh, (r, p) in zip(self.group_meshes, fold_transforms(state, self.pivot)):
            vertices = mesh.vertices@r.T+p
            bounds.append(np.array([vertices.min(axis=0), vertices.max(axis=0)]))
        obstacle = np.array([np.min([b[0] for b in bounds[:3]], axis=0),
                             np.max([b[1] for b in bounds[:3]], axis=0)])
        ring = bounds[3]
        gaps = np.maximum(ring[0]-obstacle[1], obstacle[0]-ring[1])
        return dict(separated=bool(gaps.max() > 0), separating_axis=int(gaps.argmax()),
                    separation_m=float(gaps.max()), target_bounds_m=ring.tolist(), assembly_bounds_m=obstacle.tolist())


def certify_path(model, path, *, margin_m=.0002, max_depth=18):
    """Adaptive continuous-path separation proof using conservative distance bounds.

    A sampled non-contact path alone is insufficient. Every accepted interval
    subtracts the maximum intervening surface travel from its endpoint gaps.
    Unresolved intervals and collisions both fail certification.
    """
    if len(path) < 2 or margin_m <= 0:
        raise ValueError("Certification requires at least two states and a positive margin")
    if not model.conservative:
        raise ValueError("Certification must use covers of the actual collision primitives")
    path = [np.asarray(q, dtype=float) for q in path]
    for q in path:
        fold_transforms(q, model.pivot)
    start_is_template = np.allclose(path[0][:4], 0., atol=1e-10) and np.allclose(
        Rotation.from_quat(path[0][4:]).as_matrix(), np.eye(3), atol=1e-10)
    initial = geometry_report(model.assembly)
    internal = model.initial_internal_clearance()
    failures, intervals = [], []
    calls_start = model.calls
    started = time.monotonic()

    def check(a, b, da, db, segment, lo, hi, depth):
        bounds = model.motion_bounds(a, b)
        pair_travel = np.array([bounds[i]+bounds[j] for i, j in PAIRS])
        lower = np.minimum(da, db)-.5*pair_travel
        if lower.min() >= margin_m:
            intervals.append(dict(segment=segment, interval=[lo, hi], lower_bounds_m=lower.tolist()))
            return True
        if min(da.min(), db.min()) <= margin_m or depth >= max_depth:
            failures.append(dict(segment=segment, interval=[lo, hi], minimum_endpoint_clearance_m=float(min(da.min(), db.min())),
                                 reason="clearance_below_margin" if min(da.min(), db.min()) <= margin_m else "subdivision_limit"))
            return False
        middle = interpolate(a, b, .5)
        dm = model.distances(middle)
        mid = (lo+hi)/2
        return check(a, middle, da, dm, segment, lo, mid, depth+1) and check(middle, b, dm, db, segment, mid, hi, depth+1)

    valid = start_is_template and initial["passed"] and internal > margin_m
    if valid:
        da = model.distances(path[0])
        for i, (a, b) in enumerate(zip(path[:-1], path[1:])):
            db = model.distances(b)
            if not check(a, b, da, db, i, 0., 1., 0):
                valid = False
                break
            da = db
            if i % 50 == 0:
                print(f"Certified {i+1}/{len(path)-1} path segments", flush=True)
    goal = model.separated_goal(path[-1])
    collision_free = bool(valid)
    valid = valid and goal["separated"]
    lower = np.array([entry["lower_bounds_m"] for entry in intervals])
    return dict(passed=bool(valid), scope="geometric_existence_witness_for_declared_compound_geometry",
        robot_execution_verified=False, dynamic_execution_verified=False,
        continuous_collision_free=collision_free, requested_margin_m=margin_m,
        minimum_interval_clearance_lower_bound_m=float(lower.min()) if lower.size else None,
        minimum_target_clearance_lower_bound_m=float(lower[:, 3:].min()) if lower.size else None,
        fixed_internal_clearance_m=float(internal), initial_matches_template=bool(start_is_template),
        initial_geometry_passed=initial["passed"], goal=goal, failures=failures,
        interpolation="linear fold angle and middle-frame target translation; shortest quaternion SLERP",
        collision_cover="band convex pieces + circumscribed 24-sided cylinders + circumscribed subdivision-2 icospheres",
        interval_method="endpoint distances minus half the uniform pair surface-travel bound",
        distance_evaluations=model.calls-calls_start, certified_intervals=len(intervals),
        wall_seconds=time.monotonic()-started, intervals=intervals)


def export_body_poses(model, path):
    result = []
    for state in path:
        frame = {}
        for names, (r, p) in zip(GROUPS, fold_transforms(state, model.pivot)):
            for name in names:
                frame[name] = dict(translation_m=p.tolist(), quaternion_xyzw=Rotation.from_matrix(r).as_quat().tolist())
        result.append(frame)
    return result


def write_artifacts(output, model, path, result):
    output = Path(output)
    output.mkdir(parents=True, exist_ok=True)
    template = model.assembly.template
    serialized = json.dumps(template, sort_keys=True).encode()
    result.update(template_sha256=hashlib.sha256(serialized).hexdigest(), scale=model.assembly.scale,
                  path_sha256=hashlib.sha256(json.dumps(path).encode()).hexdigest())
    (output/"template.json").write_text(json.dumps(template, indent=2)+"\n")
    (output/"witness_path.json").write_text(json.dumps(path, indent=2)+"\n")
    (output/"body_poses.json").write_text(json.dumps(export_body_poses(model, path), indent=2)+"\n")
    (output/"certificate.json").write_text(json.dumps(result, indent=2)+"\n")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--path", type=Path, required=True)
    parser.add_argument("--template", type=Path)
    parser.add_argument("--scale", type=float, default=2.)
    parser.add_argument("--radius-mm", type=float)
    parser.add_argument("--margin-mm", type=float, default=.2)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    template = load_template(args.template)
    if args.radius_mm is not None:
        template["target_ring"]["centerline_radius"] = args.radius_mm
    path = json.loads(args.path.read_text())
    if isinstance(path, dict):
        path = path["states"]
    model = WitnessModel(template, scale=args.scale)
    result = certify_path(model, path, margin_m=args.margin_mm/1000)
    write_artifacts(args.output, model, path, result)
    print(json.dumps({k: v for k, v in result.items() if k != "intervals"}, indent=2), flush=True)
    if not result["passed"]:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
