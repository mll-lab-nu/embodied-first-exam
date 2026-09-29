"""Certify continuous geometric clearance using a collision-query protocol."""
from __future__ import annotations

import numpy as np


def certify_motion(collision, motion, *, margin_m, max_depth=22):
    """Prove separation over every motion interval, or fail closed.

    ``collision`` supplies local ``moving_corners`` and ``gap(rotation,
    translation)``: a finite signed lower bound on pairwise separation in metres.
    ``motion`` supplies pose(u), point_speed_bound(corners), name and to_dict().
    Its speed bound is material displacement per normalized progress u, rather
    than physical time. A midpoint gap g and bound L*du/2 certify g-L*du/2 over
    that interval. This certifies authored geometry, not physical execution.
    """
    if not np.isfinite(margin_m) or margin_m <= 0:
        raise ValueError("The certificate requires a positive margin")
    if isinstance(max_depth, bool) or not isinstance(max_depth, int) or max_depth < 0:
        raise ValueError("max_depth must be a nonnegative integer")
    corners = np.asarray(collision.moving_corners, dtype=float)
    if corners.ndim != 2 or corners.shape[1:] != (3,) or not len(corners) or not np.isfinite(corners).all():
        raise ValueError("Collision moving_corners must be finite (N, 3) material points")
    speed = float(motion.point_speed_bound(corners))
    if not np.isfinite(speed) or speed < 0:
        raise ValueError("Motion requires a finite nonnegative material speed bound")
    pending, count, leaves = [(0., 1., 0)], 0, 0
    lower, minimum_sample = float("inf"), float("inf")
    witness = None

    def query(u):
        gap = float(collision.gap(*motion.pose(u)))
        if not np.isfinite(gap):
            raise ValueError("Collision gap must be finite")
        return gap

    for endpoint in (0., 1.):
        gap = query(endpoint)
        minimum_sample = min(minimum_sample, gap)
        count += 1
        if gap < margin_m:
            witness = dict(u=endpoint, gap_m=gap, reason="endpoint violates margin")
            break
    while pending and witness is None:
        a, b, depth = pending.pop()
        u = (a+b)/2
        gap = query(u)
        count += 1
        minimum_sample = min(minimum_sample, gap)
        bound = gap-speed*(b-a)/2
        if bound >= margin_m:
            leaves += 1
            lower = min(lower, bound)
        elif gap < margin_m:
            witness = dict(u=u, gap_m=gap, reason="sample violates margin")
        elif depth >= max_depth:
            witness = dict(u=u, gap_m=gap, reason="continuous interval unresolved")
        else:
            pending.extend(((u, b, depth+1), (a, u, depth+1)))
    return dict(name=motion.name, passed=witness is None, method="SAT plus adaptive material-displacement bound",
        margin_m=margin_m, pose_queries=count, certified_intervals=leaves,
        minimum_sample_sat_gap_m=minimum_sample,
        certified_separation_lower_bound_m=lower if witness is None else None,
        witness=witness, motion=motion.to_dict())
