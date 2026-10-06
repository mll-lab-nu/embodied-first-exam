"""Authored below-easy Blanket shapes, in the existing flat material coordinates.

Build PBD rest lengths and visual supports on the flat sheet. The continuous
fold targets serve both a management-only static preview and bounded-velocity
physical preparation. Only the latter can produce a qualified frozen state.
"""
from dataclasses import asdict, dataclass

import numpy as np

from .blanket_flatten import BlanketLayout, generate_flat_binding


REVISION = "corner_folds_scene_preview_v1"


@dataclass(frozen=True)
class CornerFoldProfile:
    half_fold: bool = False
    corner_leg_m: float = .28
    layer_gap_m: float = .016
    table_clearance_m: float = .004


def profile_for(variation):
    if variation == "very_easy":
        return CornerFoldProfile()
    if variation == "easier":
        return CornerFoldProfile(half_fold=True, corner_leg_m=.22)
    raise ValueError("Corner-fold preview requires very_easy or easier")


def _turn_over(points, normal, offset, axis_height, radius, *, bend_start=None, progress=1.):
    """Turn a half-plane through a finite-radius 180-degree material bend.

    Straight regions preserve lengths exactly. The bend is parameterized by
    arc length; its sampled chords can be shorter than the material edges.
    Packet layers share a bend center and use their own radii. Their free edges
    slide by the different arc lengths, retaining clearance and layer order.
    """
    result = points.copy()
    normal = np.asarray(normal, dtype=float)
    distance = points[:, :2] @ normal - offset
    radius = np.broadcast_to(radius, distance.shape)
    start = -np.pi*radius/2 if bend_start is None else bend_start
    angle = np.clip((distance-start) / radius, 0., np.pi*progress)
    tail = np.maximum(distance-start-np.pi*progress*radius, 0.)
    turned = start + radius*np.sin(angle) + tail*np.cos(angle)
    active = distance > start
    result[active, :2] += ((turned-distance)[:, None]*normal)[active]
    result[active, 2] = (axis_height-radius*np.cos(angle)+tail*np.sin(angle))[active]
    return result


def folded_positions(uv, length=.60, width=.48, profile=None, *, half_progress=1., corner_progress=1.):
    """Map one continuous sheet; positive X / negative Y is the turned corner.

    Easier folds the left half over the right half, recenters the resulting
    rectangle at the same table XY, then turns BOTH layers at the free corner.
    No new mesh, rest shape, disconnected flap or hidden support is created.
    """
    profile = profile or CornerFoldProfile()
    uv = np.asarray(uv, dtype=float)
    values = (length, width, profile.corner_leg_m, profile.layer_gap_m,
              profile.table_clearance_m)
    if uv.ndim != 2 or uv.shape[1] != 2 or not np.isfinite(uv).all():
        raise ValueError("Expected finite Nx2 material coordinates")
    if not np.isfinite(values).all() or min(values) <= 0:
        raise ValueError("Fold dimensions must be positive and finite")
    if any(not np.isfinite(t) or not 0 <= t <= 1 for t in (half_progress, corner_progress)):
        raise ValueError("Fold progress must be between zero and one")
    if profile.half_fold and half_progress < 1 and corner_progress > 0:
        raise ValueError("Complete the half fold before turning the packet corner")
    packet_length = length/2 if profile.half_fold else length
    if profile.corner_leg_m + np.pi*profile.layer_gap_m >= min(packet_length, width):
        raise ValueError("Keep the corner bend clear of the opposite packet edges")
    if (np.abs(uv) > np.array([length, width])/2 + 1e-8).any():
        raise ValueError("Material coordinates lie outside the blanket")
    points = np.column_stack((uv, np.zeros(len(uv))))
    gap = profile.layer_gap_m
    if profile.half_fold:
        points = _turn_over(points, [-1., 0.], 0., gap/2, gap/2, progress=half_progress)
        points[:, 0] -= length/4*half_progress
        if half_progress < 1:
            points[:, 2] += profile.table_clearance_m
            return points
    normal = np.array([1., -1.])/np.sqrt(2)
    offset = (packet_length/2 + width/2 - profile.corner_leg_m)/np.sqrt(2)
    height = 1.5*gap if profile.half_fold else gap/2
    points = _turn_over(points, normal, offset, height, height-points[:, 2],
        bend_start=-np.pi*height/2 if profile.half_fold else None, progress=corner_progress)
    points[:, 2] += profile.table_clearance_m
    return points


def generate(variation, layout=None):
    """Return a display mesh with the same topology and UVs as the flat asset."""
    layout = layout or BlanketLayout()
    profile = profile_for(variation)
    _, faces, uv, _, _ = generate_flat_binding(layout)
    positions = folded_positions(uv, layout.length_m, layout.width_m, profile)
    return positions, faces, uv, dict(revision=REVISION, variation=variation,
        profile=asdict(profile), scope="authored_static_scene_preview",
        material_area_m2=layout.length_m*layout.width_m,
        full_robot_solve_verified=False, physical_initial_state_qualified=False)
