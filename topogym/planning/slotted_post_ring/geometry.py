"""Measurements of the Slotted Post Ring scene from a privileged world observation.

Rigid bodies are read as (center, rotation): the center is the authored mesh's
vertex mean carried by the measured link pose, so it does not depend on where the
asset origin sits. Cord points are means of the FEM vertices at one material
arc length. All functions are pure reads of the observation.
"""
from dataclasses import dataclass
import numpy as np
from .kinematics import rot

PARTS = ("target_ring", "bead_left", "bead_right", "disc_left", "disc_right")
FIXTURES = ("base", "post", "stand_left", "stand_right")


@dataclass(frozen=True)
class SceneGeometry:
    """Instance constants handed to the policy by the runner (no Task object in the policy)."""
    local_centers: dict           # part -> mesh vertex mean in its link frame
    origin_m: tuple               # assembly origin (post base centre on the table)
    table_z_m: float
    disc_radius_m: float
    disc_thickness_m: float
    bead_radius_m: float
    ring_major_radius_m: float
    ring_tube_radius_m: float
    slot_width_m: float
    slot_bottom_m: float          # relative to the origin
    slot_top_m: float
    post_width_m: float
    post_depth_m: float
    post_height_m: float
    base_height_m: float
    rope_radius_m: float
    fixture_boxes_m: dict         # fixed part -> (lower, upper) world corners; the slotted post counts as solid
    goal_center_xy_m: tuple       # the instance's fixed placement square (public in the task instruction)
    goal_half_size_m: tuple
    separator_offset_m: float     # remainder must stay at y below this (separator normal +y)
    disc_normal_local: tuple = (0., 0., 1.)
    standing_discs: bool = False

    @property
    def slot_center(self):
        o = np.asarray(self.origin_m, float)
        return o+[0., 0., (self.slot_bottom_m+self.slot_top_m)/2]

    @property
    def post_front_y(self):
        return self.origin_m[1]-self.post_depth_m/2

    @property
    def post_back_y(self):
        return self.origin_m[1]+self.post_depth_m/2

    @property
    def post_top_z(self):
        return self.origin_m[2]+self.base_height_m+self.post_height_m

    @classmethod
    def from_task(cls, task):
        layout = task.layout
        origin = tuple(float(v) for v in np.r_[task.config["center_xy_m"], task.table_height_m])
        centers = {name: np.asarray(task.placement_vertices[name], float).mean(axis=0).tolist() for name in PARTS}
        return cls(local_centers=centers, origin_m=origin, table_z_m=float(task.table_height_m),
                   disc_radius_m=layout.disc_radius_m, disc_thickness_m=layout.disc_thickness_m,
                   bead_radius_m=layout.bead_radius_m, ring_major_radius_m=layout.ring_major_radius_m,
                   ring_tube_radius_m=layout.ring_tube_radius_m, slot_width_m=layout.slot_width_m,
                   slot_bottom_m=layout.slot_bottom_m, slot_top_m=layout.slot_top_m,
                   post_width_m=layout.post_width_m, post_depth_m=layout.post_depth_m,
                   post_height_m=layout.post_height_m, base_height_m=layout.base_height_m,
                   rope_radius_m=layout.rope_radius_m,
                   fixture_boxes_m={name: ((np.min(task.placement_vertices[name], axis=0)+origin).tolist(),
                                           (np.max(task.placement_vertices[name], axis=0)+origin).tolist())
                                    for name in FIXTURES if name in task.placement_vertices},
                   goal_center_xy_m=tuple(task.goal_region.center_xy_m), goal_half_size_m=tuple(task.goal_region.half_size_m),
                   separator_offset_m=float(task.goal_region.separator_offset_m),
                   # The local v15 discs lie flat; the imported layout used upright discs with an x normal.
                   disc_normal_local=tuple(np.eye(3)[np.argmin(np.ptp(task.placement_vertices["disc_left"], axis=0))]),
                   standing_discs=bool(getattr(layout, "disc_stands", False)))


def body(world, geometry, name):
    """(center, rotation) of a rigid part."""
    b = world["bodies"][name]
    r = rot(b["quaternion_wxyz"])
    return r.apply(geometry.local_centers[name])+np.asarray(b["position_m"], float), r


def speed(world, name):
    return float(np.linalg.norm(world["bodies"][name]["linear_velocity_m_s"]))


def cord_point(world, s_m, half_width_m=.003):
    cord = world["fem"]["cord"]
    s = np.asarray(cord["material_s_m"], float).reshape(-1)
    x = np.asarray(cord["position_m"], float).reshape(-1, 3)
    mask = np.abs(s-s_m) <= half_width_m
    if not mask.any():
        mask = np.argsort(np.abs(s-s_m))[:24]
    return x[mask].mean(axis=0)


def cord_volume_ratio(world):
    return float(world["ipc"]["volume_ratio"]["cord"]["minimum"])


def inplane(direction, normal):
    """Unit projection of direction onto the plane with the given normal."""
    d = np.asarray(direction, float)-np.dot(direction, normal)*np.asarray(normal, float)
    return d/np.linalg.norm(d)


def hand(world, side):
    return world["grasp"]["hands"][side]


def ring_disk(world, geometry):
    """(center, unit normal) of the ring's spanning disk."""
    c, r = body(world, geometry, "target_ring")
    return c, r.apply([0., 0., 1.])


def ring_on_post(world, geometry):
    """Whether the post axis pierces the ring's disk between the base and the post top."""
    c, n = ring_disk(world, geometry)
    if abs(n[2]) < 1e-6:
        return False
    o = np.asarray(geometry.origin_m, float)
    z = c[2]-((o[:2]-c[:2]) @ n[:2])/n[2]
    p = np.array([o[0], o[1], z])
    return bool(np.linalg.norm(p-c) < geometry.ring_major_radius_m and o[2] < z < geometry.post_top_z)


def ring_crossings(world, geometry, step_m=.0025):
    """Material arc lengths (and signs) where the cord pierces the ring's disk inside the tube centreline."""
    c, n = ring_disk(world, geometry)
    s = np.arange(0., float(np.max(world["fem"]["cord"]["material_s_m"])), step_m)
    x = np.array([cord_point(world, v, half_width_m=step_m) for v in s])
    d = (x-c) @ n
    out = []
    for i in np.flatnonzero(np.sign(d[:-1]) != np.sign(d[1:])):
        a = d[i]/(d[i]-d[i+1])
        q = x[i]+a*(x[i+1]-x[i])
        if np.linalg.norm((q-c)-((q-c) @ n)*n) < geometry.ring_major_radius_m:
            out.append((float(s[i]+a*step_m), 1 if d[i] < 0 else -1))
    return out


def box_penetration(points, boxes, margin_m):
    """Deepest intrusion (m, 0 when clear) of points into axis-aligned boxes grown by margin_m."""
    worst = 0.
    for lower, upper in boxes:
        lo, hi = np.asarray(lower)-margin_m, np.asarray(upper)+margin_m
        worst = max(worst, float(np.minimum(points-lo, hi-points).min(axis=1).max()))
    return worst
