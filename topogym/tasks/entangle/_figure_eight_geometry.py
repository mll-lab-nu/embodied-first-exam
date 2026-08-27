"""Figure-8 control points for docx 3.3, laid on the table with one OPEN rope.

The docx draws a closed elastic band twisted into an 8. Built that way (closed
FEM tube, `world/closed_band.py`, spike 2026-08-21) the 8 does not hold: the two
strands at the crossing sit 40 mm apart, far outside contact range, so there is
no barrier and the band springs flat within 0.25 s of release. The task here is
the same reading on an open rope lying flat: gravity presses the over strand
onto the under strand, and tabletop friction is what holds the shape.

The curve is two teardrops joined at one crossing point. Each teardrop is a
circle plus the two tangent lines from the crossing to it, so both strands leave
the crossing at the same half-angle ``phi`` from the axis and cross each other
at ``2 * phi``. The closed lobe is a full teardrop; the open lobe is cut off at
the bottom so the two rope ends sit ``end_gap`` apart -- wider than the
gripper's clearance rule (`rope.free_end_connector.min_clearance`), so either
end can be grasped without the fingers straddling the other plug.

Rope order, and which end is the OVER end, is fixed by construction:

    end 0 --(open lobe, one side)--> crossing [OVER, +over_lift]
          --> closed lobe, all the way round
          --> crossing [UNDER, on the table]
          --(open lobe, other side)--> end 1

So end 0's strand is the one on top at the crossing. The verifier measures that
rather than trusting it (`over_at < 0.5` on the measured self-crossing).

Local frame: ``a`` runs along the 8's axis from the crossing toward the closed
lobe, ``b`` is the in-plane perpendicular (to the left when looking along ``a``).
``heading_deg`` rotates that axis in the task frame and ``center`` places the
crossing. Default heading 0 puts the closed lobe at +x, i.e. away from the
robot, and the two graspable ends toward it.

Pure numpy: `tests/check_band_untwist_geometry.py` loads this file by path so
the offline gate runs without Genesis.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

# Index of the rope end whose strand passes OVER at the crossing, by construction.
OVER_END = 0


@dataclass(frozen=True)
class FigureEightSpec:
    """All lengths in metres, angles in degrees; see the module docstring."""

    closed_lobe_radius: float
    open_lobe_radius: float
    end_gap: float
    half_angle_deg: float
    over_lift: float
    base_z: float
    center: tuple[float, float] = (0.0, 0.0)
    heading_deg: float = 0.0
    # Control points along each lobe's arc, per 90 degrees of arc.
    arc_points_per_quarter: int = 3
    # How far from the crossing the over strand is already back on the table,
    # along the tangent line. Sets the ramp length of the over_lift bump.
    lift_ramp: float = 0.030

    def __post_init__(self) -> None:
        if self.closed_lobe_radius <= 0.0 or self.open_lobe_radius <= 0.0:
            raise ValueError("lobe radii must be positive.")
        if not 0.0 < self.half_angle_deg < 90.0:
            raise ValueError(f"half_angle_deg must be in (0, 90), got {self.half_angle_deg}.")
        if not 0.0 < self.end_gap < 2.0 * self.open_lobe_radius:
            raise ValueError(
                f"end_gap {self.end_gap} must be positive and below the open lobe's "
                f"diameter {2.0 * self.open_lobe_radius}, or the lobe cannot be cut there."
            )
        if self.over_lift <= 0.0:
            raise ValueError("over_lift must be positive.")
        if self.lift_ramp <= 0.0:
            raise ValueError("lift_ramp must be positive.")

    @property
    def half_angle(self) -> float:
        return float(np.radians(self.half_angle_deg))

    def tangent_length(self, radius: float) -> float:
        """Crossing to the tangent point on a lobe circle of ``radius``."""

        return float(radius / np.tan(self.half_angle))

    def lobe_center_distance(self, radius: float) -> float:
        return float(radius / np.sin(self.half_angle))

    @property
    def end_cut_angle(self) -> float:
        """Half the angular width of the open lobe's cut, about its centre (rad)."""

        return float(np.arcsin(self.end_gap / (2.0 * self.open_lobe_radius)))


def _arc(center, radius: float, start: float, end: float, points: int) -> np.ndarray:
    """``points`` samples on a circle from angle ``start`` to ``end`` inclusive."""

    angles = np.linspace(start, end, int(points))
    return np.column_stack(
        [center[0] + radius * np.cos(angles), center[1] + radius * np.sin(angles)]
    )


def _arc_points(spec: FigureEightSpec, sweep: float) -> int:
    return max(3, int(round(abs(sweep) / (0.5 * np.pi) * spec.arc_points_per_quarter)) + 1)


def figure_eight_local_points(spec: FigureEightSpec) -> tuple[np.ndarray, np.ndarray]:
    """Control points ``(N, 3)`` in the local ``(a, b, z)`` frame, plus a mask of
    which points belong to the over strand's crossing bump.

    ``z`` is ``base_z`` everywhere except the over strand's pass through the
    crossing, which is raised by ``over_lift`` and ramped back down over
    ``lift_ramp`` on either side.
    """

    phi = spec.half_angle
    up = np.array([np.cos(phi), np.sin(phi)])  # toward closed lobe, +b side
    up_m = np.array([np.cos(phi), -np.sin(phi)])  # toward closed lobe, -b side

    r_c, r_o = spec.closed_lobe_radius, spec.open_lobe_radius
    t_c, t_o = spec.tangent_length(r_c), spec.tangent_length(r_o)
    c_closed = np.array([spec.lobe_center_distance(r_c), 0.0])
    c_open = np.array([-spec.lobe_center_distance(r_o), 0.0])
    # The ramp feet must stay on the tangent lines, short of the tangent points.
    ramp = min(spec.lift_ramp, 0.8 * min(t_c, t_o))

    # Tangent points. A tangent from an external point at distance d touches a
    # circle of radius r at angle acos(r / d) from the centre->point direction;
    # here r / d = sin(phi), so that angle is pi/2 - phi. The closed lobe sees
    # the crossing at angle pi from its centre, the open lobe at angle 0.
    tangent_open_plus = -t_o * up_m  # +b side of the open lobe
    tangent_open_minus = -t_o * up  # -b side of the open lobe
    tangent_closed_plus = t_c * up  # +b side of the closed lobe
    tangent_closed_minus = t_c * up_m  # -b side of the closed lobe

    cut = spec.end_cut_angle
    tangent_angle = 0.5 * np.pi - phi
    # Open lobe, +b half: from the cut point (end 0) round to the tangent point.
    open_plus = _arc(
        c_open, r_o, np.pi - cut, tangent_angle, _arc_points(spec, np.pi - cut - tangent_angle)
    )
    # Open lobe, -b half: from the tangent point round to the cut point (end 1).
    open_minus = _arc(
        c_open, r_o, -tangent_angle, -(np.pi - cut), _arc_points(spec, np.pi - cut - tangent_angle)
    )
    # Closed lobe: from the -b tangent point round the far side to the +b one.
    closed = _arc(
        c_closed,
        r_c,
        -(np.pi - tangent_angle),
        (np.pi - tangent_angle),
        _arc_points(spec, 2.0 * (np.pi - tangent_angle)),
    )

    # The tangent-point samples from the arcs coincide with the analytic tangent
    # points; keep the arc's copies and add the crossing approach explicitly.
    assert np.allclose(open_plus[-1], tangent_open_plus, atol=1e-9)
    assert np.allclose(open_minus[0], tangent_open_minus, atol=1e-9)
    assert np.allclose(closed[0], tangent_closed_minus, atol=1e-9)
    assert np.allclose(closed[-1], tangent_closed_plus, atol=1e-9)

    origin = np.zeros(2)
    z0 = float(spec.base_z)
    lift = float(spec.over_lift)

    def flat(xy: np.ndarray) -> np.ndarray:
        return np.column_stack([xy, np.full(len(xy), z0)])

    # Over pass: ramp foot, apex at the crossing, ramp foot.
    over_pass = np.array(
        [
            [*(-ramp * up_m), z0],
            [*origin, z0 + lift],
            [*(ramp * up_m), z0],
        ]
    )
    # Under pass: the crossing itself, flat.
    under_pass = np.array([[*origin, z0]])

    points = np.concatenate(
        [
            flat(open_plus[:-1]),
            flat(tangent_open_plus[None, :]),
            over_pass,
            flat(tangent_closed_minus[None, :]),
            flat(closed[1:-1]),
            flat(tangent_closed_plus[None, :]),
            under_pass,
            flat(tangent_open_minus[None, :]),
            flat(open_minus[1:]),
        ],
        axis=0,
    )
    over_mask = np.zeros(len(points), dtype=bool)
    start = len(open_plus) - 1 + 1
    over_mask[start : start + 3] = True
    return points, over_mask


def figure_eight_control_points(spec: FigureEightSpec) -> np.ndarray:
    """Control points ``(N, 3)`` in the task frame (xy rotated by heading, plus
    ``center``; z untouched)."""

    local, _mask = figure_eight_local_points(spec)
    theta = np.radians(spec.heading_deg)
    rot = np.array([[np.cos(theta), -np.sin(theta)], [np.sin(theta), np.cos(theta)]])
    xy = local[:, :2] @ rot.T + np.asarray(spec.center, dtype=float)[None, :]
    return np.column_stack([xy, local[:, 2]])


def figure_eight_end_separation(spec: FigureEightSpec) -> float:
    """Straight-line distance between the two rope ends."""

    points = figure_eight_control_points(spec)
    return float(np.linalg.norm(points[0, :2] - points[-1, :2]))


def polyline_arc_length(points: np.ndarray) -> float:
    return float(np.linalg.norm(np.diff(np.asarray(points, dtype=float), axis=0), axis=1).sum())


def figure_eight_expected_arc_length(spec: FigureEightSpec) -> float:
    """Analytic rope length: tangents plus arcs, ignoring the crossing bump."""

    phi = spec.half_angle
    r_c, r_o = spec.closed_lobe_radius, spec.open_lobe_radius
    closed = 2.0 * spec.tangent_length(r_c) + r_c * 2.0 * (np.pi - phi)
    open_half = spec.tangent_length(r_o) + r_o * (np.pi - spec.end_cut_angle - phi)
    return float(closed + 2.0 * open_half)
