"""Assembly task: separated tabletop reset, reversed certified path, pose goal."""

from dataclasses import dataclass

import numpy as np
from scipy.spatial.transform import Rotation

from .verification import CompoundCollision, Motion, assembly_route, certify_motion

DEFAULT_XY_OFFSET = np.array([-0.12, 0.18])
ASSEMBLY_PHASES = {
    "approach_align",
    "assembly_insert",
    "assembly_quarter_turn",
    "assembly_close",
    "place_assembly",
}


def assembly_phase_name(name):
    return {"prototype_extract": "assembly_insert",
            "prototype_quarter_turn": "assembly_quarter_turn",
            "prototype_slide": "assembly_close"}.get(name, "assembly_reverse_" + name)


def required_assembly_phases(family=None):
    if family is None:
        return set(ASSEMBLY_PHASES)
    from .inverse_design import variant_route
    return {"approach_align", "place_assembly"} | {
        assembly_phase_name(m.name) for m in variant_route(family)}


def route_lift(assembly, origin, rotation, route, nominal=.08, clearance=.01):
    """Conservative table clearance over the complete relative motion route.

    Mid-interval displacement is bounded by the same material speed used by
    the piece certificate. A larger eccentric pivot can require a higher lift.
    All coordinates here are relative to a tabletop at z=0.
    """
    from .verification import box_corners
    points = box_corners(assembly.bodies[1].boxes)
    lower = float("inf")
    for motion in route:
        speed = motion.point_speed_bound(points)
        n = max(1, int(np.ceil(speed/.001)))
        sampled = min(float((rotation.apply(points @ r.T + t) + origin)[:, 2].min())
                      for r, t in (motion.pose(u) for u in np.linspace(0,1,n+1)))
        lower = min(lower, sampled-speed/(2*n))
    lift = max(float(nominal), float(clearance)-lower)
    return dict(lift_m=lift, minimum_route_table_clearance_m=lower+lift,
                requested_clearance_m=clearance, method="sampled height minus material-displacement bound")


@dataclass
class ReverseMotion:
    name: str
    source: Motion

    @property
    def duration_s(self):
        return self.source.duration_s

    def pose(self, u):
        return self.source.pose(1 - u)

    def point_speed_bound(self, corners):
        return self.source.point_speed_bound(corners)

    def to_dict(self):
        return dict(
            name=self.name, reverse_of=self.source.to_dict(), duration_s=self.duration_s
        )


def initial_poses(assembly, origin, rotation, xy_offset=DEFAULT_XY_OFFSET):
    """Origins in the caller's frame; both pieces rest on the same plane."""
    offset = np.asarray(xy_offset, dtype=float)
    if offset.shape != (2,) or not np.isfinite(offset).all():
        raise ValueError("Expected finite x/y separation")
    final_r, _ = assembly_route(assembly)[-1].pose(1)
    silver_r = rotation * Rotation.from_matrix(final_r)
    gold_bottom = float(rotation.apply(assembly.bodies[0].visual.vertices)[:, 2].min())
    silver_bottom = float(
        silver_r.apply(assembly.bodies[1].visual.vertices)[:, 2].min()
    )
    silver_p = np.asarray(origin) + [*offset, gold_bottom - silver_bottom]
    poses = [(rotation, np.asarray(origin)), (silver_r, silver_p)]
    if min(xy_surface_gaps(assembly, poses)) < 0.01:
        raise ValueError("Both x and y initial surface gaps must be at least 10 mm")
    return poses


def xy_surface_gaps(assembly, poses):
    bounds = []
    for body, (r, p) in zip(assembly.bodies, poses):
        vertices = r.apply(body.visual.vertices) + p
        bounds.append((vertices.min(axis=0), vertices.max(axis=0)))
    a, b = bounds
    return np.maximum(b[0] - a[1], a[0] - b[1])[:2].tolist()


def motions(assembly, poses):
    rg, pg = poses[0]
    rs, ps = poses[1]
    forward = assembly_route(assembly)
    final_r, final_t = forward[-1].pose(1)
    if not np.allclose((rg.inv() * rs).as_matrix(), final_r):
        raise ValueError(
            "Initial silver orientation must match the separated route end"
        )
    route = [Motion("approach_align", 2.0, final_r, rg.inv().apply(ps - pg), final_t)]
    route.extend(
        ReverseMotion(assembly_phase_name(m.name), m)
        for m in reversed(forward)
    )
    collision = CompoundCollision(*(b.boxes for b in assembly.bodies))
    certificates = [certify_motion(collision, m, margin_m=0.0002) for m in route]
    if not all(c["passed"] for c in certificates):
        raise ValueError(
            "Assembly approach or reversed path fails continuous collision check"
        )
    return route, certificates


def goal_metrics(gold_origin, gold_rotation, silver_origin, silver_rotation):
    position = float(np.linalg.norm(np.asarray(silver_origin) - gold_origin))
    angle = float((gold_rotation.inv() * silver_rotation).magnitude())
    return dict(
        final_relative_position_error_m=position,
        final_relative_rotation_error_rad=angle,
        goal_assembled=position < 0.001 and angle < 0.02,
    )
