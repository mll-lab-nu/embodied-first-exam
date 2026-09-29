"""Convex tabletop placement volumes; all coordinates are world metres."""
from dataclasses import asdict, dataclass
import numpy as np


def points3(points):
    points = np.asarray(points, dtype=float)
    if points.ndim != 2 or points.shape[1] != 3 or not len(points) or not np.isfinite(points).all():
        raise ValueError("Expected nonempty finite Nx3 points")
    return points


@dataclass(frozen=True)
class GoalRegion:
    center_xy_m: tuple
    half_size_m: tuple
    table_height_m: float
    placement_height_m: float
    separator_normal_xy: tuple
    separator_offset_m: float
    separation_margin_m: float = .02
    yaw_deg: float = 0.
    boundary_margin_m: float = .001
    penetration_tolerance_m: float = .001

    def __post_init__(self):
        for key in ("center_xy_m", "half_size_m", "separator_normal_xy"):
            value = np.asarray(getattr(self, key), dtype=float)
            if value.shape != (2,) or not np.isfinite(value).all():
                raise ValueError(f"{key} must be a finite pair")
            object.__setattr__(self, key, tuple(value.tolist()))
        for key, value in asdict(self).items():
            if not np.isfinite(value).all():
                raise ValueError(f"Non-finite region {key}")
        if (self.placement_height_m <= 0 or self.boundary_margin_m < 0
                or self.penetration_tolerance_m < 0 or self.separation_margin_m <= 0
                or min(self.half_size_m) <= self.boundary_margin_m):
            raise ValueError("Invalid region extents/margins")
        n = np.asarray(self.separator_normal_xy)
        if not np.isclose(np.linalg.norm(n), 1., atol=1e-9, rtol=0):
            raise ValueError("Separator normal must be unit length")
        # Entire visible rectangle must be on the target side, not just its center.
        radius = np.abs(self.rotation.T @ n) @ np.asarray(self.half_size_m)
        if np.dot(self.center_xy_m, n)-radius < self.separator_offset_m+self.separation_margin_m-1e-12:
            raise ValueError("Region overlaps the system side of the separator")

    @property
    def rotation(self):
        angle = np.radians(self.yaw_deg)
        c, s = np.cos(angle), np.sin(angle)
        return np.array([[c, -s], [s, c]])

    def contains(self, points):
        p = points3(points)
        xy = (p[:, :2]-self.center_xy_m) @ self.rotation
        return bool(np.all(np.abs(xy) <= np.asarray(self.half_size_m)-self.boundary_margin_m+1e-12)
                    and np.all(p[:, 2] >= self.table_height_m-self.penetration_tolerance_m-1e-12)
                    and np.all(p[:, 2] <= self.table_height_m+self.placement_height_m+1e-12))

    def system_side(self, points):
        p = points3(points)
        return bool(np.all(p[:, :2] @ self.separator_normal_xy <= self.separator_offset_m+1e-12))

    def observation(self, targets, remainder):
        return dict(instruction=(f"Place all parts of {', '.join(targets)} inside the green dashed region; "
                                 f"keep {', '.join(remainder)} on the system side of the separator."),
                    target_entities=list(targets), remainder_entities=list(remainder),
                    goal_region=asdict(self))


def placement_measurements(region, target_points, remainder_points):
    if not target_points or not remainder_points:
        raise ValueError("Both target and remainder geometry must be explicitly supplied")
    if set(target_points) & set(remainder_points):
        raise ValueError("Target and remainder identities overlap")
    inside = {name: region.contains(p) for name, p in target_points.items()}
    separate = {name: region.system_side(p) for name, p in remainder_points.items()}
    return dict(all_target_inside=all(inside.values()), remainder_on_system_side=all(separate.values()),
                target_inside=inside, remainder_on_side=separate)
