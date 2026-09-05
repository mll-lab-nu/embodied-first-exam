"""rope_winding's layout rules and feasibility checks, numpy only.

Kept apart from `rope_winding.py` so the offline gate
(`tests/check_rope_winding_geometry.py`) and the variation harness can load
them without Genesis (`cable_routing.py` imports Genesis at module level).
Everything takes the layout surface the planner uses, so the real
`RopeWindingLayout` and the test stand-in read the same rows. Rules shared
with rope_unwinding come from `_winding_post_geometry`.

Task-frame metres unless a name says world.
"""

from __future__ import annotations

import math

import numpy as np

from topogym.planning.rope_winding_planner import (
    SLACK_BAND,
    WindingSpec,
    free_end_winding_delta,
    plan_rope_winding_route,
    spawn_winding,
    taut_demand,
)

from ._winding_post_geometry import (
    PALM_ABOVE_PADS,
    PLUG_TARGET_CLEARANCE,
    TOP_MARGIN,
    WORKSPACE_MARGIN,
    hand_reach,
    oracle_view,
    plug_spawn_task_xy,
    post_top_task_z,
    task_xy,
    workspace_margin,
)

# Consecutive wraps: the outlet's underside is half a rope below the orbit
# height and the previous wrap's top half a rope above its own, so the gap is
# `climb - 2 * rope.radius`; 0.008 shipped with a gap of exactly zero and the
# second turn kept failing there. 0.002 is the planned envelope's floor
# (climb 0.010), untested on the GPU -- the corner subset runs it first.
WRAP_GAP_MIN = 0.002
# The spawn arc passes the post on its south side; this far from the axis it
# neither touches the post nor reads as a wrap (baseline 0.188).
ARC_POST_CLEARANCE = 0.060
# The sweep the slack rule may solve to. Below 60 degrees the arc is nearly a
# chord (the rope would have to be shorter than the taut path allows); above
# 300 it curls back on itself.
SWEEP_RANGE_DEG = (60.0, 300.0)


def spawn_arc_chord(layout) -> float:
    """Straight-line distance from the anchor S to the plug's spawn point (xy)."""

    anchor = np.asarray(layout.route_point({"fixture": "S", "relation": "center"}), dtype=float)
    plug = np.asarray(layout.route_polyline("initial")[-1], dtype=float)
    return float(np.linalg.norm(anchor[:2] - plug[:2]))


def arc_length(chord: float, sweep_deg: float) -> float:
    theta = math.radians(sweep_deg)
    return chord * theta / (2.0 * math.sin(0.5 * theta))


def sweep_from_slack(layout, slack: float | None = None) -> float:
    """The spawn arc's sweep (degrees) that gives the rope `slack` over the
    route's tightest moment.

    The arc's ends are fixed (S and the plug spawn point), so its sweep IS the
    rope's length: length = chord * theta / (2 sin(theta / 2)). The rope is
    tightest with every turn on the post and the plug held over C
    (`taut_demand`); the task keeps (length - need) / need inside
    `SLACK_BAND` and this solves for the band's middle by bisection on the
    same arithmetic the arc code uses. The plan is made with the oracle's own
    orbit sense (a forced contrast orbit must not move the rope's length).
    """

    layout = oracle_view(layout)
    spec = WindingSpec.from_config(layout.cfg)
    _, plan = plan_rope_winding_route(layout)
    need, _ = taut_demand(layout, spec, plan.waypoints)
    low, high = SLACK_BAND
    target = need * (1.0 + (0.5 * (low + high) if slack is None else float(slack)))
    chord = spawn_arc_chord(layout)
    lo, hi = 1.0, 359.0
    for _ in range(60):
        mid = 0.5 * (lo + hi)
        if arc_length(chord, mid) < target:
            lo = mid
        else:
            hi = mid
    return float(0.5 * (lo + hi))


def rope_winding_checks(layout) -> list[tuple[str, float, float, bool]]:
    """``[(name, measured, limit, ok)]`` for a spawnable, solvable layout.

    One list for the randomizer's reject step, the offline gate, the corner
    harness and the demo's start-up print. Runs the real planner on the layout
    (no scene), so the reach and slack rows read the oracle's actual waypoints.
    """

    layout = oracle_view(layout)
    cfg = layout.cfg
    spec = WindingSpec.from_config(cfg)
    winding = cfg.winding
    post = cfg.fixtures[spec.post]
    rope_r = float(cfg.rope.radius)
    post_top = post_top_task_z(cfg)
    origin_z = layout.world_z(0.0)

    center_xy = task_xy(layout, layout.fixture_pos(spec.post))
    target_xy = task_xy(layout, layout.fixture_pos("C"))
    spawn = np.asarray(layout.route_polyline("initial"), dtype=float)
    spawn_xy = spawn[:, :2] - (np.asarray(layout.position_to_world(np.zeros(3)), dtype=float)[:2])
    arc_radial = float(np.linalg.norm(spawn_xy - center_xy[None, :], axis=1).min())
    plug_xy = plug_spawn_task_xy(layout)

    _, plan = plan_rope_winding_route(layout)
    points = np.asarray([wp.position for wp in plan.waypoints], dtype=float)
    labels = [str(wp.label) for wp in plan.waypoints]
    orbit_z = np.array([p[2] for p, l in zip(points, labels) if l.startswith("wind_t")])
    palm_clear = (float(orbit_z.min()) - origin_z + PALM_ABOVE_PADS) - post_top
    need, _ = taut_demand(layout, spec, plan.waypoints)
    length = float(np.sum(np.linalg.norm(np.diff(spawn, axis=0), axis=1)))
    slack = (length - need) / need
    spawn_reading = spawn_winding(layout, spec)
    delta = free_end_winding_delta(
        [spawn[-1]] + list(points),
        np.asarray(layout.fixture_pos(spec.post)),
        np.asarray(layout.fixture_pos("S")),
    )
    sweep_deg = float(cfg.rope.spawn_arc.sweep_deg)

    ge = [
        (
            "wraps_below_post_top",
            post_top - TOP_MARGIN - (float(winding.wind_z_start) + int(winding.turns) * float(winding.climb_per_turn) + rope_r),
            0.0,
        ),
        ("bottom_wrap_above_base", float(winding.wind_z_start) - rope_r - float(post.base_height), 0.0),
        ("wrap_gap", float(winding.climb_per_turn) - 2.0 * rope_r, WRAP_GAP_MIN),
        ("arc_clears_post", arc_radial, ARC_POST_CLEARANCE),
        ("plug_in_workspace", workspace_margin(layout, [spawn[-1]]), WORKSPACE_MARGIN),
        ("plug_clears_target", float(np.linalg.norm(plug_xy - target_xy)), PLUG_TARGET_CLEARANCE),
        ("palm_clears_post_top", palm_clear, 0.0),
    ]
    rows = [(name, value, limit, value >= limit - 1e-9) for name, value, limit in ge]
    rows.append(("spawn_reads_zero", abs(spawn_reading), 1e-6, abs(spawn_reading) < 1e-6))
    rows.append(
        (
            "free_end_reads_target",
            abs(spawn_reading + delta - spec.target_winding),
            1e-6,
            abs(spawn_reading + delta - spec.target_winding) < 1e-6,
        )
    )
    reach = hand_reach(layout, plan.waypoints)
    max_reach = float(cfg.reach.max_hand_dist)
    rows.append(("hand_reach", reach, max_reach, reach <= max_reach + 1e-9))
    low, high = SLACK_BAND
    rows.append(("slack_in_band", slack, low, low - 1e-9 <= slack <= high + 1e-9))
    s_lo, s_hi = SWEEP_RANGE_DEG
    rows.append(("sweep_in_range", sweep_deg, s_lo, s_lo - 1e-9 <= sweep_deg <= s_hi + 1e-9))
    return rows


__all__ = [
    "ARC_POST_CLEARANCE",
    "SWEEP_RANGE_DEG",
    "WRAP_GAP_MIN",
    "arc_length",
    "rope_winding_checks",
    "spawn_arc_chord",
    "sweep_from_slack",
]
