"""Continuous collision checks for independently moving horseshoe puzzle parts."""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import time

import fcl
import numpy as np
from scipy.spatial.transform import Rotation, Slerp

from .geometry import HorseshoeAssembly, geometry_report
from .solvability import collision_object, outer_collision_mesh


def interpolate(a, b, t):
    if not 0 <= t <= 1 or set(a) != set(b):
        raise ValueError("Interpolation requires matching bodies and t in [0, 1]")
    result = {}
    for name in a:
        p = (1-t)*np.asarray(a[name]["pos"])+t*np.asarray(b[name]["pos"])
        q = Slerp([0, 1], Rotation.from_quat([a[name]["quat"], b[name]["quat"]]))([t]).as_quat()[0]
        result[name] = dict(pos=p.tolist(), quat=q.tolist())
    return result


class IndependentWitness:
    def __init__(self, template, scale=2.):
        self.assembly = HorseshoeAssembly(template, scale)
        self.names = [b.name for b in self.assembly.bodies]
        self.centers = np.array([b.visual.center_mass for b in self.assembly.bodies])
        self.meshes = [outer_collision_mesh(b).apply_translation(-c)
                       for b, c in zip(self.assembly.bodies, self.centers)]
        self.radii = np.array([np.linalg.norm(m.vertices, axis=1).max() for m in self.meshes])
        self.objects = [collision_object(m) for m in self.meshes]
        self.pairs = [(i, j) for i in range(len(self.names)) for j in range(i+1, len(self.names))]
        self.request = fcl.DistanceRequest()
        self.calls = 0

    def validate(self, frame):
        if set(frame) != set(self.names):
            raise ValueError("Witness body names differ from the template")
        for pose in frame.values():
            p, q = np.asarray(pose["pos"]), np.asarray(pose["quat"])
            if p.shape != (3,) or q.shape != (4,) or not np.isfinite(np.r_[p, q]).all():
                raise ValueError("Each pose needs finite XYZ and an XYZW quaternion")
            if abs(np.linalg.norm(q)-1) > 1e-6:
                raise ValueError("Witness quaternions must have unit length")

    def distances(self, frame):
        for name, obj in zip(self.names, self.objects):
            pose = frame[name]
            obj.setTransform(fcl.Transform(Rotation.from_quat(pose["quat"]).as_matrix(), np.asarray(pose["pos"])))
        self.calls += 1
        return np.array([fcl.distance(self.objects[i], self.objects[j], self.request, fcl.DistanceResult())
                         for i, j in self.pairs])

    def motion_bounds(self, a, b):
        return np.array([np.linalg.norm(np.array(b[n]["pos"])-a[n]["pos"])
            +radius*(Rotation.from_quat(a[n]["quat"]).inv()*Rotation.from_quat(b[n]["quat"])).magnitude()
            for n, radius in zip(self.names, self.radii)])

    def goal(self, frame):
        bounds = []
        for n, m in zip(self.names, self.meshes):
            vertices = Rotation.from_quat(frame[n]["quat"]).apply(m.vertices)+frame[n]["pos"]
            bounds.append(np.array([vertices.min(0), vertices.max(0)]))
        target = bounds[self.names.index("target_ring")]
        obstacles = [b for n, b in zip(self.names, bounds) if n != "target_ring"]
        obstacle = np.array([np.min([b[0] for b in obstacles], axis=0), np.max([b[1] for b in obstacles], axis=0)])
        gaps = np.maximum(target[0]-obstacle[1], obstacle[0]-target[1])
        return dict(separated=bool(gaps.max() > 0), separation_m=float(gaps.max()),
                    target_bounds_m=target.tolist(), assembly_bounds_m=obstacle.tolist())

    def certify(self, frames, *, margin_m=.0001, max_depth=18, relative_clearance_fraction=0.):
        if len(frames) < 2 or not np.isfinite(margin_m) or margin_m <= 0:
            raise ValueError("Need two frames and a positive finite margin")
        if not np.isfinite(relative_clearance_fraction) or not 0 <= relative_clearance_fraction < 1:
            raise ValueError("Relative clearance fraction must lie in [0,1)")
        for frame in frames:
            self.validate(frame)
        initial = all(np.allclose(frames[0][n]["pos"], c, atol=1e-9, rtol=0)
            and np.allclose(Rotation.from_quat(frames[0][n]["quat"]).as_matrix(), np.eye(3), atol=1e-9)
            for n, c in zip(self.names, self.centers))
        geometry = geometry_report(self.assembly)
        intervals, failures = [], []
        pair_lower = np.full(len(self.pairs), np.inf)
        started = time.monotonic()

        def check(a, b, da, db, segment, lo=0., hi=1., depth=0):
            travel = self.motion_bounds(a, b)
            lower = np.minimum(da, db)-.5*np.array([travel[i]+travel[j] for i, j in self.pairs])
            if lower.min() >= margin_m and np.all(lower >= np.minimum(da,db)*relative_clearance_fraction):
                np.minimum(pair_lower, lower, out=pair_lower)
                intervals.append(dict(segment=segment, interval=[lo, hi], lower_bound_m=float(lower.min())))
                return True
            if min(da.min(), db.min()) <= margin_m or depth >= max_depth:
                failures.append(dict(segment=segment, interval=[lo, hi],
                    endpoint_clearance_m=float(min(da.min(), db.min())),
                    reason="clearance_below_margin" if min(da.min(), db.min()) <= margin_m else "subdivision_limit"))
                return False
            mid = interpolate(a, b, .5)
            dm = self.distances(mid)
            return check(a, mid, da, dm, segment, lo, (lo+hi)/2, depth+1) and check(mid, b, dm, db, segment, (lo+hi)/2, hi, depth+1)

        valid = initial and geometry["passed"]
        if valid:
            da = self.distances(frames[0])
            for i, (a, b) in enumerate(zip(frames[:-1], frames[1:])):
                db = self.distances(b)
                if not check(a, b, da, db, i):
                    valid = False
                    break
                da = db
                if i % 100 == 0:
                    print(f"Certified {i+1}/{len(frames)-1} independent-motion segments", flush=True)
        goal = self.goal(frames[-1])
        return dict(passed=bool(valid and goal["separated"]), continuous_collision_free=bool(valid),
            initial_matches_template=bool(initial), initial_geometry_passed=geometry["passed"], goal=goal,
            scope="independent_rigid_body_geometric_path", robot_execution_verified=False,
            dynamic_execution_verified=False, lab_obstacle_collision_verified=False,
            requested_margin_m=margin_m, minimum_clearance_lower_bound_m=min((x["lower_bound_m"] for x in intervals), default=None),
            relative_clearance_fraction=relative_clearance_fraction,
            collision_cover="Actual band pieces, circumscribed 24-sided cylinders and subdivision-2 spheres",
            interpolation="Each body COM translates linearly and its orientation follows shortest quaternion SLERP",
            interval_method="Endpoint gaps minus half the sum of both bodies' uniform surface-travel bounds",
            failures=failures, intervals=intervals, distance_evaluations=self.calls,
            wall_seconds=time.monotonic()-started, scale=self.assembly.scale,
            minimum_pair_clearance_lower_bounds_m={self.names[i]+'--'+self.names[j]:
                (float(v) if np.isfinite(v) else None) for (i,j),v in zip(self.pairs,pair_lower)},
            implementation_sha256={name:hashlib.sha256(Path(__file__).with_name(name).read_bytes()).hexdigest()
                for name in ('geometry.py','solvability.py','independent_motion.py')},
            template_sha256=hashlib.sha256(json.dumps(self.assembly.template, sort_keys=True).encode()).hexdigest(),
            frames_sha256=hashlib.sha256(json.dumps(frames, sort_keys=True).encode()).hexdigest())


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("path", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--margin-mm", type=float, default=.1)
    args = parser.parse_args()
    path = json.loads(args.path.read_text())
    witness = IndependentWitness(path["template"], path.get("scale", 2.))
    report = witness.certify(path["frames"], margin_m=args.margin_mm/1000)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2)+"\n")
    print({k: v for k, v in report.items() if k != "intervals"}, flush=True)


if __name__ == "__main__":
    main()
