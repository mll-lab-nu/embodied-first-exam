"""Conservative whole-piece separation, with both rigid bodies held quiet."""
import numpy as np
from scipy.spatial.transform import Rotation


def separation_candidate(state, vertices, *, minimum_separation_m=.01):
    """A separating plane proves the entire pieces are disjoint and unlinked.

    Test world axes, both body axes and the centre direction. This is a
    sufficient condition, not a complete convex-hull distance computation.
    Surface distance alone is insufficient: an interlocked pair can have a gap.
    """
    clouds, rotations, linear, angular = [], [], [], []
    for name, local in vertices.items():
        body = state["bodies"][name]
        p = np.asarray(body["position_m"], float)
        q = np.asarray(body["quaternion_wxyz"], float)
        v = np.asarray(body["linear_velocity_m_s"], float)
        w = np.asarray(body["angular_velocity_rad_s"], float)
        if not np.isfinite(np.r_[p, q, v, w]).all() or np.linalg.norm(q) < 1e-12:
            return False, "Non-finite or invalid physical state", {}
        r = Rotation.from_quat(q[[1, 2, 3, 0]])
        clouds.append(r.apply(local)+p)
        rotations.append(r.as_matrix().T)
        linear.append(float(np.linalg.norm(v)))
        angular.append(float(np.linalg.norm(w)))
    if len(clouds) != 2:
        raise ValueError("Claws requires exactly two complete piece geometries")
    delta = clouds[1].mean(0)-clouds[0].mean(0)
    axes = np.vstack([np.eye(3), *rotations, delta/max(np.linalg.norm(delta), 1e-12)])
    a, b = (points@axes.T for points in clouds)
    gap = float(np.maximum(b.min(0)-a.max(0), a.min(0)-b.max(0)).max())
    separated = gap >= minimum_separation_m
    quiet = max(linear) <= .001 and max(angular) <= .02
    return separated and quiet, None, dict(
        evaluation_status="available", separated=separated, quiet=quiet,
        separating_plane_gap_m=gap, minimum_separation_m=minimum_separation_m,
        maximum_linear_speed_m_s=max(linear), maximum_angular_speed_rad_s=max(angular),
        holding_allowed=True, goal_kind="whole_piece_separation")
