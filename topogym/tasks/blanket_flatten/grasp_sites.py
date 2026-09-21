"""Choose a visible material boundary near an occluded blanket corner."""
import numpy as np
from scipy.spatial import cKDTree


def carry_waypoints_xy(start, target, base_xy, radial_limits, *, lane_x):
    """Route a carry chord through the forward lane if it crosses the base zone."""
    start, target, base = (np.asarray(p, dtype=float) for p in (start, target, base_xy))
    low, high = map(float, radial_limits)

    def minimum_radius(a, b):
        delta = b-a
        norm = float(delta@delta)
        alpha = float(np.clip((base-a)@delta/norm, 0., 1.)) if norm else 0.
        return float(np.linalg.norm(a+alpha*delta-base))

    path = [target]
    if minimum_radius(start, target) < low:
        path = [np.array([lane_x, start[1]]), np.array([lane_x, target[1]]), target]
    points = [start, *path]
    if any(minimum_radius(a, b) < low-1e-6 for a, b in zip(points, points[1:])) or any(
            np.linalg.norm(p-base) > high+1e-6 for p in points):
        raise ValueError('No valid carry path through the configured forward lane')
    return [p.copy() for p in path]


def reachable_target_xy(target, base_xy, radial_limits, *, margin=.015):
    """Keep a boundary-opening waypoint inside the calibrated radial range."""
    target, base = np.asarray(target, dtype=float), np.asarray(base_xy, dtype=float)
    low, high = map(float, radial_limits)
    if not 0 < low < high or not 0 <= margin < (high-low)/2:
        raise ValueError('Invalid radial workspace or margin')
    delta = target-base
    radius = float(np.linalg.norm(delta))
    if low <= radius <= high:
        return target.copy()
    direction = delta/radius if radius else np.array([1., 0.])
    return base+direction*(low+margin if radius < low else high-margin)


def exposed_boundary_site(positions, material_uv, corner, half_extents, *,
                          material_radius, spatial_radius=.008, maximum_occlusion=.003,
                          base_xy=None, radial_limits=None, corner_reason='occluded'):
    positions, uv = np.asarray(positions), np.asarray(material_uv)
    half_extents = np.asarray(half_extents)
    distance = np.linalg.norm(uv-uv[corner], axis=1)
    boundary = np.any(np.isclose(np.abs(uv), half_extents, atol=1e-5, rtol=0), axis=1)
    if radial_limits is not None:
        radius = np.linalg.norm(positions[:, :2]-np.asarray(base_xy), axis=1)
        boundary &= (radius >= radial_limits[0]) & (radius <= radial_limits[1])
    candidates = np.flatnonzero(boundary & (distance <= material_radius))
    candidates = candidates[np.argsort(distance[candidates], kind='stable')]
    tree = cKDTree(positions[:, :2])
    for index in candidates:
        near = tree.query_ball_point(positions[index, :2], spatial_radius)
        occlusion = float(positions[near, 2].max()-positions[index, 2])
        if occlusion <= maximum_occlusion:
            return dict(particle=int(index), material_distance_from_corner_m=float(distance[index]),
                        overhead_depth_m=occlusion, material_uv_m=uv[index].tolist(),
                        maximum_occlusion_m=float(maximum_occlusion),
                        method='material_corner' if index == corner else f'exposed_boundary_near_{corner_reason}_corner')
    return None
