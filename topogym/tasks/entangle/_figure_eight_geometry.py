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

``over_end=1`` (the variation axis) mirrors the local ``b`` component and
reverses the point order. The two plugs then sit exactly where they sat before,
and it is end 1's strand that passes over: same footprint, opposite topology,
so nothing in the picture but the crossing itself says which end to grasp.

Local frame: ``a`` runs along the 8's axis from the crossing toward the closed
lobe, ``b`` is the in-plane perpendicular (to the left when looking along ``a``).
``heading_deg`` rotates that axis in the task frame and ``center`` places the
crossing. Default heading 0 puts the closed lobe at +x, i.e. away from the
robot, and the two graspable ends toward it.

Pure numpy: `tests/check_band_untwist_geometry.py` loads this file by path so
the offline gate runs without Genesis. The landing rows of `figure_eight_checks`
import `topogym.planning.band_untwist_planner` (also Genesis-free) locally, so
the offline check replays the oracle's own `place_beside`.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

# Index of the rope end whose strand passes OVER at the crossing when the spec
# leaves ``over_end`` at its default; ``FigureEightSpec.over_end`` is the truth.
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
    # Which end's strand passes over at the crossing (module docstring).
    over_end: int = 0

    def __post_init__(self) -> None:
        if self.closed_lobe_radius <= 0.0 or self.open_lobe_radius <= 0.0:
            raise ValueError("lobe radii must be positive.")
        if int(self.over_end) not in (0, 1):
            raise ValueError(f"over_end must be 0 or 1, got {self.over_end}.")
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
    if int(spec.over_end) == 1:
        # Mirror about the axis, then walk the rope the other way: the ends keep
        # their places (the figure is symmetric in b) and the raised pass moves
        # onto the strand that now belongs to end 1.
        points = points.copy()
        points[:, 1] *= -1.0
        points = points[::-1].copy()
        over_mask = over_mask[::-1].copy()
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


def open_half_arc(spec: FigureEightSpec) -> float:
    """Rope length from the crossing to either end: the open lobe's tangent plus
    its arc up to the cut. The same for both ends, so it is also the arc the
    planner has to lift clear of the table (`band_untwist_planner.py`)."""

    r_o = spec.open_lobe_radius
    return float(spec.tangent_length(r_o) + r_o * (np.pi - spec.end_cut_angle - spec.half_angle))


def figure_eight_expected_arc_length(spec: FigureEightSpec) -> float:
    """Analytic rope length: tangents plus arcs, ignoring the crossing bump."""

    phi = spec.half_angle
    r_c = spec.closed_lobe_radius
    closed = 2.0 * spec.tangent_length(r_c) + r_c * 2.0 * (np.pi - phi)
    return float(closed + 2.0 * open_half_arc(spec))


# ----------------------------------------------------------------- variation
# The randomizer's derive / validate hooks (`band_untwist.py`) and the offline
# gate (`tests/check_band_untwist_geometry.py`, Genesis-free) share these, so the
# envelope is judged by one set of formulas.


def chord_turn_radii(points: np.ndarray) -> np.ndarray:
    """Circumradius of each consecutive point triple, in 3D (collinear -> inf).

    In 3D rather than the xy plane so the crossing bump counts: its three points
    are collinear from above but form a corner in the vertical, and that corner
    tightens when ``lift_ramp`` is clamped to a short tangent.
    """

    p = np.asarray(points, dtype=float)
    a, b, c = p[:-2], p[1:-1], p[2:]
    ab, bc, ca = np.linalg.norm(b - a, axis=1), np.linalg.norm(c - b, axis=1), np.linalg.norm(a - c, axis=1)
    cross = np.linalg.norm(np.cross(b - a, c - a), axis=1)
    with np.errstate(divide="ignore", invalid="ignore"):
        return np.where(cross < 1e-12, np.inf, ab * bc * ca / (2.0 * cross))


def end_gap_bounds(open_lobe_radius: float, min_clearance: float, max_ratio: float) -> tuple[float, float]:
    """Where the two rope ends may sit: no closer than the gripper's clearance,
    no wider than ``max_ratio`` of the open lobe's diameter (at 1.0 the cut is
    the full diameter and the lobe has no arc left)."""

    return float(min_clearance), float(max_ratio * 2.0 * open_lobe_radius)


def end_gap_from_frac(open_lobe_radius: float, frac: float, min_clearance: float, max_ratio: float) -> float:
    lo, hi = end_gap_bounds(open_lobe_radius, min_clearance, max_ratio)
    if not hi >= lo:
        raise ValueError(
            f"No end_gap fits an open lobe of radius {open_lobe_radius:.4f}: the gripper needs "
            f"{lo:.3f}, the lobe allows at most {hi:.3f}."
        )
    return float(lo + min(max(float(frac), 0.0), 1.0) * (hi - lo))


def predicted_lift(spec: FigureEightSpec, tube_radius: float, lift_clearance: float) -> float:
    """Hand height (task z) the oracle will ask for, estimated from the spawn geometry.

    `band_untwist_planner.plan_untwist_move`: ``scene_top + max(lift_clearance,
    crossing_arc + lift_clearance)``. Here the scene top is the bump apex plus
    the tube radius and ``crossing_arc`` is the analytic open half; the planner
    uses the settled centerline's measured crossing instead. Measured 2026-09-03
    over seeds 0-9: the real lift was within -24 / +26 mm of this (higher at
    large half angles), so it is an estimate, not a bound -- keep the workspace
    ceiling row's headroom well above 30 mm.
    """

    scene_top = float(spec.base_z) + float(spec.over_lift) + float(tube_radius)
    return float(scene_top + max(float(lift_clearance), open_half_arc(spec) + float(lift_clearance)))


def predicted_place(
    spec: FigureEightSpec, *, place_clearance: float, lift_clearance: float
) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """The oracle's landing point, replayed on the spawn control points:
    ``(place_xy, stay_strand_xy, contact_xy)``.

    Same ``place_beside`` as `band_untwist_planner.plan_untwist_move`; the
    planner feeds it the settled centerline and the measured crossing, this
    feeds it the control polygon with the crossing at ``spec.center``. The
    strand that stays down is the other end's, plug to crossing. ``contact_xy``
    is where the carried strand leaves the table once lifted: ``lift_clearance``
    of rope past the crossing, on the closed lobe (the planner lifts the
    crossing arc plus that clearance).
    """

    # Local import: `topogym.planning` is Genesis-free, but this module is also
    # loaded by path from the offline gate, which must not pull `topogym.tasks`.
    from topogym.planning.band_untwist_planner import place_beside

    points = figure_eight_control_points(spec)[:, :2]
    center = np.asarray(spec.center, dtype=float)
    at_crossing = np.where(np.linalg.norm(points - center, axis=1) < 1e-9)[0]
    first, last = int(at_crossing.min()), int(at_crossing.max())
    over_end = int(spec.over_end)
    if over_end == 0:
        grasp, other = points[0], points[-1]
        stay = points[last:]
        beyond = points[first + 1 :]
    else:
        grasp, other = points[-1], points[0]
        stay = points[: first + 1]
        beyond = points[:last][::-1]
    arc = np.concatenate([[0.0], np.cumsum(np.linalg.norm(np.diff(beyond, axis=0), axis=1))])
    contact = beyond[min(int(np.searchsorted(arc, float(lift_clearance))), len(beyond) - 1)]
    place = np.asarray(place_beside(center, grasp, other, stay, clearance=place_clearance), dtype=float)
    return place, stay, contact


def _segment_to_polyline(p, q, polyline, samples: int = 100) -> float:
    from topogym.planning.band_untwist_planner import point_to_polyline

    p, q = np.asarray(p, dtype=float), np.asarray(q, dtype=float)
    return float(min(point_to_polyline(p + t * (q - p), polyline) for t in np.linspace(0.0, 1.0, samples)))


def figure_eight_checks(
    spec: FigureEightSpec,
    *,
    tube_radius: float,
    min_clearance: float,
    end_gap_max_ratio: float,
    workspace_x: tuple[float, float],
    workspace_y: tuple[float, float],
    workspace_z_max: float,
    workspace_margin: float,
    lift_clearance: float,
    place_clearance: float,
) -> list[tuple[str, float, float, bool]]:
    """``[(name, measured, limit, ok)]``: what a buildable, solvable figure-8 needs.

    One list for the randomizer's reject step, the offline gate and the demo's
    start-up print, so they cannot disagree. Metres throughout.

    The last two rows replay the oracle's landing (`predicted_place`):
    ``place_clearance`` is the landing point's distance to the strand that
    stays down (the planner sweeps until it clears ``place_clearance``, so this
    fails only when the sweep runs out); ``lay_down_clearance`` is how far the
    carried strand's straight lay-down line stays from that strand, which is
    the number corner c130 (2026-09-04) had at 0.1 mm.
    """

    points = figure_eight_control_points(spec)
    separation = figure_eight_end_separation(spec)
    ratio = float(spec.end_gap) / (2.0 * float(spec.open_lobe_radius))
    radii = chord_turn_radii(points)
    corner = float(np.min(radii[np.isfinite(radii)]))
    footprint = float(
        min(
            (points[:, 0] - workspace_x[0]).min(),
            (workspace_x[1] - points[:, 0]).min(),
            (points[:, 1] - workspace_y[0]).min(),
            (workspace_y[1] - points[:, 1]).min(),
        )
    )
    lift = predicted_lift(spec, tube_radius, lift_clearance)
    bottom = float(spec.base_z) - float(tube_radius)
    min_corner = 3.0 * float(tube_radius)
    try:
        place, stay, contact = predicted_place(
            spec, place_clearance=place_clearance, lift_clearance=lift_clearance
        )
    except ValueError:
        # The sweep ran out: report zero clearance rather than a missing row.
        place_clear, lay_down = 0.0, 0.0
    else:
        from topogym.planning.band_untwist_planner import point_to_polyline

        place_clear = point_to_polyline(place, stay)
        lay_down = _segment_to_polyline(contact, place, stay)
    min_lay_down = 2.0 * float(tube_radius)
    return [
        ("end_separation", separation, float(min_clearance), separation >= min_clearance - 1e-9),
        ("end_gap_ratio", ratio, float(end_gap_max_ratio), ratio <= end_gap_max_ratio + 1e-9),
        ("corner_radius", corner, min_corner, corner >= min_corner - 1e-9),
        ("footprint", footprint, float(workspace_margin), footprint >= workspace_margin - 1e-9),
        ("lift_height", lift, float(workspace_z_max), lift <= workspace_z_max + 1e-9),
        ("bottom_clearance", bottom, 0.0, bottom >= -1e-9),
        ("place_clearance", place_clear, float(place_clearance), place_clear >= place_clearance - 1e-9),
        ("lay_down_clearance", lay_down, min_lay_down, lay_down >= min_lay_down - 1e-9),
    ]
