"""Layout checks for the two-cable braid scene (`swap_crossing_sign`, shared with
`untangle_continuous`): pure numpy on a generated ``BraidSpec``, no Genesis.

The scene builder, the randomizer's reject step, the offline gate and the demo's
start-up print all read the same rows from here, so they cannot disagree. The
offline gate loads this file by path (``topogym.tasks_legacy`` imports Genesis), so it
must import nothing beyond numpy and ``topogym.generation.braid``.

Rows, metres throughout (the numbers are for the frozen default layout):

- ``end_separation``   the two plugs spawn side by side at ``x_end``, one lane
                       pitch apart; the builder refuses anything under the
                       gripper's ``min_clearance`` (0.070).
- ``crossing_window``  the lane swap's x length after clipping to
                       ``braid_span``; ``braid.py``'s steepness rule
                       (>= 0.6 x lane pitch, i.e. flatter than ~59 deg).
- ``free_tail``        straight run between the swap window and the plug; the
                       plug body (pin + flange + half column, 0.029) plus the
                       rope's follow band (0.012) must land on it.
- ``footprint_x``      the plug's pin tip (``x_end`` + plug body) inside the
                       workspace, and the anchored end inside it too.
- ``footprint_y``      lanes plus the plug's flange inside the workspace by
                       ``workspace.margin``.
- ``strip_cover``      the outlets at ``x_start`` inside the power strip's length.
- ``lift_height``      the oracle's first move lifts the plug until the crossing
                       -- hanging below the hand -- clears the other rope:
                       other rope's top + arc from the crossing to the plug +
                       ``pinch.lift_clearance``, against the workspace ceiling.
                       An estimate (the planner uses the settled centreline; on
                       band_untwist the same kind of estimate ran +-26 mm), not
                       an upper bound.
- ``lane_entry_gap``   the separate move lays the lifted rope back along its
                       own lane, plug overshot by ``pinch.lane_overshoot``; but
                       after one crossing the *other* rope's tail runs in that
                       same lane. The laid rope is a straight line from its
                       anchor (on the lane) to the overshot plug, so where the
                       other rope enters the lane (end of its swap window) the
                       gap is only overshoot x (that x - x_start) / (place x -
                       x_start). Against the separation threshold plus two rope
                       diameters of bow allowance. With overshoot 0.040 and the
                       crossing at 0.30 of the span this was 21 mm, and the
                       laid rope's bow closed it (2026-09-06 sweep, 3/10 seeds);
                       0.090 gives 48 mm. Only defined for one crossing.
"""

from __future__ import annotations

import numpy as np

from topogym.generation.braid import BraidSpec, crossing_window_at

# Steepness rule shared with ``braid.verify_braid_spec``.
MIN_WINDOW_PER_LANE = 0.6
# Straight run the plug and the rope's follow band need before the free end.
MIN_FREE_TAIL = 0.050


def last_crossing_arc(spec: BraidSpec, strand: int | None = None) -> tuple[int, float]:
    """``(strand, arc)``: the strand on top at the crossing nearest the free end
    and the length of its control polyline from that crossing to the free end.

    Top-down (xy) arc: the over strand's spawn bump collapses when it settles
    onto the strand below, and the planner measures the settled rope.
    """

    if not spec.crossings:
        raise ValueError("last_crossing_arc: the braid has no crossing.")
    crossing = spec.crossings[-1]
    strand = int(crossing.over_strand if strand is None else strand)
    points = np.asarray(spec.control_points[strand], dtype=float)
    x_center = float(spec.layout.x_start) + float(crossing.position_frac) * (
        float(spec.layout.x_end) - float(spec.layout.x_start)
    )
    index = int(np.argmin(np.abs(points[:, 0] - x_center)))
    tail = points[index:, :2]
    return strand, float(np.linalg.norm(np.diff(tail, axis=0), axis=1).sum())


def predicted_lift(spec: BraidSpec, tube_radius: float, lift_clearance: float) -> float:
    """Task z the oracle's separate move lifts to, estimated from the spawn geometry."""

    over, arc = last_crossing_arc(spec)
    others = [
        np.asarray(p, dtype=float)[:, 2].max()
        for s, p in spec.control_points.items()
        if int(s) != over
    ]
    obstacle_top = (max(others) if others else float(spec.layout.base_z)) + float(tube_radius)
    return obstacle_top + arc + float(lift_clearance)


def braid_checks(
    spec: BraidSpec,
    *,
    tube_radius: float,
    min_clearance: float,
    plug_ahead: float,
    flange_radius: float,
    strip_half_length: float,
    workspace_x: tuple[float, float],
    workspace_y: tuple[float, float],
    workspace_z_max: float,
    workspace_margin: float,
    lift_clearance: float,
    lane_overshoot: float,
    place_pullback: float,
    separation_threshold: float,
) -> list[tuple[str, float, float, bool]]:
    """``[(name, measured, limit, ok)]``: what a buildable, solvable braid needs."""

    layout = spec.layout
    points = {int(s): np.asarray(p, dtype=float) for s, p in spec.control_points.items()}
    free_ends = [p[-1, :2] for p in points.values()]
    separation = float("inf")
    for a in range(len(free_ends)):
        for b in range(a + 1, len(free_ends)):
            separation = min(separation, float(np.linalg.norm(free_ends[a] - free_ends[b])))

    spacing = float(layout.channel_spacing)
    windows = [
        crossing_window_at(c.position_frac, len(spec.crossings), layout) for c in spec.crossings
    ]
    window = min(windows) if windows else float("inf")
    min_window = MIN_WINDOW_PER_LANE * spacing

    total_x = float(layout.x_end) - float(layout.x_start)
    if spec.crossings:
        last = spec.crossings[-1]
        swap_end = float(layout.x_start) + float(last.position_frac) * total_x + 0.5 * windows[-1]
    else:
        swap_end = float(layout.x_start)
    free_tail = float(layout.x_end) - swap_end

    footprint_x = float(
        min(
            workspace_x[1] - (float(layout.x_end) + float(plug_ahead)),
            float(layout.x_start) - workspace_x[0],
        )
    )
    all_y = np.concatenate([p[:, 1] for p in points.values()])
    footprint_y = float(
        min(
            workspace_y[1] - (all_y.max() + float(flange_radius)),
            (all_y.min() - float(flange_radius)) - workspace_y[0],
        )
    )
    outlet_y = np.array([p[0, 1] for p in points.values()])
    strip_cover = float(strip_half_length - np.abs(outlet_y).max())

    lift = predicted_lift(spec, tube_radius, lift_clearance) if spec.crossings else 0.0

    # Straight-line gap between the laid rope and the other rope's lane where
    # that rope enters it (see the module docstring). inf when not applicable.
    place_x = float(layout.x_end) - float(place_pullback)
    if len(spec.crossings) == 1 and place_x > float(layout.x_start):
        lane_entry_gap = float(lane_overshoot) * (swap_end - float(layout.x_start)) / (
            place_x - float(layout.x_start)
        )
    else:
        lane_entry_gap = float("inf")
    min_entry_gap = float(separation_threshold) + 4.0 * float(tube_radius)
    return [
        ("end_separation", separation, float(min_clearance), separation >= min_clearance - 1e-9),
        ("crossing_window", window, min_window, window >= min_window - 1e-9),
        ("free_tail", free_tail, MIN_FREE_TAIL, free_tail >= MIN_FREE_TAIL - 1e-9),
        ("footprint_x", footprint_x, 0.0, footprint_x >= -1e-9),
        ("footprint_y", footprint_y, float(workspace_margin), footprint_y >= workspace_margin - 1e-9),
        ("strip_cover", strip_cover, float(tube_radius), strip_cover >= tube_radius - 1e-9),
        ("lift_height", lift, float(workspace_z_max), lift <= workspace_z_max + 1e-9),
        ("lane_entry_gap", lane_entry_gap, min_entry_gap, lane_entry_gap >= min_entry_gap - 1e-9),
    ]


__all__ = [
    "MIN_FREE_TAIL",
    "MIN_WINDOW_PER_LANE",
    "braid_checks",
    "last_crossing_arc",
    "predicted_lift",
]
