"""Conservative capsule-cover clearance for every interpolated reference pose."""

import numpy as np
from scipy.spatial import cKDTree
from scipy.spatial.transform import Rotation

from topogym.tasks._rigid_geometry import disk_linking_number


def sample_capsules(segments, spacing=0.0015):
    groups = {}
    for a, b, r, _ in segments:
        count = max(1, int(np.ceil(np.linalg.norm(b - a) / spacing)))
        points = np.linspace(a, b, count + 1)
        groups.setdefault(r, []).append(points)
    return {r: np.concatenate(p) for r, p in groups.items()}


class ClearanceOracle:
    def __init__(self, wire, spacing=0.0015):
        if not np.isfinite(spacing) or spacing <= 0:
            raise ValueError("Positive cover spacing required")
        self.wire, self.spacing = wire, spacing
        self.fixed = {
            r: cKDTree(p)
            for r, p in sample_capsules([
                row for row in wire.fixed_capsules()
                if not (row[3] == "stop" and wire.layout.end_stop_shape == "block_mount")
            ], spacing).items()
        }
        from .supports import fixture_boxes
        self.boxes = fixture_boxes(wire)
        self.tool = sample_capsules(wire.layout.tool_capsules(), spacing)
        self.radius = max(
            np.linalg.norm(p, axis=1).max() + r for r, p in self.tool.items()
        )
        self.box_low = np.array(
            [-wire.layout.base_size_m[0] / 2, -wire.layout.base_size_m[1] / 2, 0.0]
        )
        self.box_high = np.array(
            [
                wire.layout.base_size_m[0] / 2,
                wire.layout.base_size_m[1] / 2,
                wire.layout.base_size_m[2],
            ]
        )

    def clearance(self, position, rotation):
        minimum = float("inf")
        for radius, points in self.tool.items():
            world = rotation.apply(points) + position
            for fixed_radius, tree in self.fixed.items():
                distance = (
                    tree.query(world)[0].min() - radius - fixed_radius - self.spacing
                )
                minimum = min(minimum, float(distance))
            for centre, size, rot, _ in self.boxes:
                local = rot.inv().apply(world - centre)
                delta = np.maximum(abs(local) - size / 2, 0.0)
                minimum = min(minimum, float(np.linalg.norm(delta, axis=1).min()
                                            - radius - self.spacing / 2))
        return minimum


def verify_route(wire):
    oracle = ClearanceOracle(wire, spacing=wire.layout.clearance_cover_m)
    values = np.array(
        [oracle.clearance(p, r) for p, r in zip(wire.positions, wire.rotations)]
    )
    # Every point on a straight-translation / SLERP interval is at most this
    # distance from its nearest endpoint, including all points of the tool.
    translation = np.linalg.norm(np.diff(wire.positions, axis=0), axis=1) / 2
    angles = (wire.rotations[:-1].inv() * wire.rotations[1:]).magnitude()
    motion = translation + 2 * oracle.radius * np.sin(angles / 4)
    bounds = np.minimum(values[:-1], values[1:]) - motion
    # Tighten inconclusive displacement bounds on the SAME linear/SLERP
    # trajectory. This never accepts a sampled collision or changes the path.
    extra_values, depths = [], []

    def refine(p0, r0, c0, p1, r1, c1, depth=0):
        angle = (r0.inv() * r1).magnitude()
        displacement = np.linalg.norm(p1 - p0) / 2 + 2 * oracle.radius * np.sin(
            angle / 4
        )
        bound = min(c0, c1) - displacement
        if bound > 0.001 or min(c0, c1) <= 0.001 or depth >= 12:
            depths.append(depth)
            return bound
        pm = (p0 + p1) / 2
        rm = r0 * Rotation.from_rotvec((r0.inv() * r1).as_rotvec() / 2)
        cm = oracle.clearance(pm, rm)
        extra_values.append(cm)
        return min(
            refine(p0, r0, c0, pm, rm, cm, depth + 1),
            refine(pm, rm, cm, p1, r1, c1, depth + 1),
        )

    for i in np.flatnonzero(bounds <= 0.001):
        bounds[i] = refine(
            wire.positions[i],
            wire.rotations[i],
            values[i],
            wire.positions[i + 1],
            wire.rotations[i + 1],
            values[i + 1],
        )
    # Close the fixed wire through the solid base to inspect the threaded state.
    first, last = wire.rail[0], wire.rail[-1]
    closure = np.vstack(
        (
            wire.rail,
            [last[0], last[1], wire.layout.base_size_m[2] / 2],
            [first[0], first[1], wire.layout.base_size_m[2] / 2],
        )
    )
    linking = [
        disk_linking_number(p, r.apply([0, 0, 1]), wire.layout.loop_radius_m, closure)
        for p, r in zip(wire.positions, wire.rotations)
    ]
    _, singular, _ = np.linalg.svd(
        wire.rail - wire.rail.mean(axis=0), full_matrices=False
    )
    out_of_plane = float(singular[-1] / np.sqrt(len(wire.rail)))
    checks = dict(
        continuous_tool_clearance=bool(bounds.min() > 0.001),
        threaded_throughout=all(abs(n) == 1 for n in linking),
        genuinely_spatial=out_of_plane > 0.015,
        endpoints_captive=wire.layout.end_stop_radius_m
        > wire.layout.loop_radius_m - wire.layout.loop_tube_radius_m,
    )
    return dict(
        passed=all(checks.values()),
        checks=checks,
        scope="geometric feasibility of full loop + stem + grip against rail + end stops + base",
        method="capsule centreline sample covers + rigid-motion interval displacement bounds",
        cover_spacing_m=oracle.spacing,
        reference_poses=len(values),
        minimum_pose_clearance_lower_bound_m=float(
            min(values.min(), min(extra_values, default=float("inf")))
        ),
        adaptive_midpoint_evaluations=len(extra_values),
        maximum_subdivision_depth=max(depths, default=0),
        maximum_interval_displacement_bound_m=float(motion.max()),
        minimum_continuous_clearance_lower_bound_m=float(bounds.min()),
        worst_interval=int(np.argmin(bounds)),
        best_fit_plane_rms_m=out_of_plane,
        linking_numbers=sorted(set(linking)),
        robot_reachability_verified=False,
        physical_execution_verified=False,
        applies_to="generated solids and piecewise linear / SLERP witness only; rectangular grips use a conservative enclosing capsule",
    )
