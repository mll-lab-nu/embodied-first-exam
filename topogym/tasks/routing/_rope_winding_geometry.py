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
    target_x_windows,
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


def _with_target(layout, x: float | None = None, y: float | None = None):
    """A copy of the layout with C moved (task-frame x / y) and a straight run to C."""

    import copy

    cfg = copy.deepcopy(layout.cfg)
    try:
        from omegaconf import OmegaConf

        if OmegaConf.is_config(cfg):
            OmegaConf.set_readonly(cfg, False)
    except ImportError:
        pass
    if x is not None:
        cfg.fixtures.C.x = float(x)
    if y is not None:
        cfg.fixtures.C.y = float(y)
    cfg.winding.to_c_route = "straight"
    view = copy.copy(layout)
    object.__setattr__(view, "cfg", cfg)
    return view


def _short_arc_contains(start: float, end: float, bearing: float) -> bool:
    """Does the short arc from ``start`` to ``end`` (radians) pass through ``bearing``?"""

    span = math.atan2(math.sin(end - start), math.cos(end - start))
    offset = math.atan2(math.sin(bearing - start), math.cos(bearing - start))
    if span >= 0.0:
        return 0.0 <= offset <= span
    return span <= offset <= 0.0


def exit_and_opposite_bearings(layout) -> tuple[float, float]:
    """Bearings about the post (radians) of the wrap's tangential exit point and
    of the ray opposite the anchor -- the two that decide whether a straight
    run to C changes the count. Neither depends on where C is."""

    view = _with_target(layout)
    spec = WindingSpec.from_config(view.cfg)
    _, plan = plan_rope_winding_route(view)
    center = task_xy(view, view.fixture_pos(spec.post))
    anchor = task_xy(view, view.fixture_pos("S"))
    exit_point = next(task_xy(view, wp.position) for wp in plan.waypoints if wp.label == "wind_exit")
    exit_bearing = math.atan2(exit_point[1] - center[1], exit_point[0] - center[0])
    opposite = math.atan2(anchor[1] - center[1], anchor[0] - center[0]) + math.pi
    return exit_bearing, opposite


def straight_run_clear(layout, target_xy, exit_bearing: float, opposite: float) -> bool:
    """Does the straight run from the wrap's exit to ``target_xy`` stay clear of the
    ray opposite the anchor? Seen from the post the segment sweeps the short arc
    between the two bearings, so it crosses the ray exactly when that arc holds it."""

    center = task_xy(layout, layout.fixture_pos(str(layout.cfg.winding.post)))
    bearing = math.atan2(float(target_xy[1]) - center[1], float(target_xy[0]) - center[0])
    return not _short_arc_contains(exit_bearing, bearing, opposite)


# Resolution of the scans that find where C may sit.
TARGET_STEP = 0.002


def _x_windows_at(layout, y: float, exit_bearing: float, opposite: float) -> list[tuple[float, float]]:
    """x intervals at height ``y`` where C keeps clear of the plug spawn AND the
    straight run to it stays clear of the ray opposite the anchor."""

    view = _with_target(layout, y=y)
    windows = []
    for lo, hi in target_x_windows(view):
        xs = np.arange(lo, hi + 1e-9, TARGET_STEP)
        if xs[-1] < hi - 1e-9:
            xs = np.append(xs, hi)
        start, prev = None, None
        for x in xs:
            ok = straight_run_clear(view, (x, y), exit_bearing, opposite)
            if ok and start is None:
                start = float(x)
            elif not ok and start is not None:
                windows.append((start, float(prev)))
                start = None
            prev = x
        if start is not None:
            windows.append((start, float(xs[-1])))
    return [(a, b) for a, b in windows if b > a]


def target_y_windows(layout) -> list[tuple[float, float]]:
    """Where C's y may fall: the yaml's `y_range`, keeping only the heights at
    which some x in `x_range` both clears the plug spawn and keeps the straight
    run clear of the ray opposite the anchor.

    The count the verdict reads moves whenever the free end crosses that ray,
    and the run to C is part of the path. rope_unwinding fixes a wrong straight
    run by going round the far side of the post; on a WOUND rope that detour
    drags the wraps backwards most of a turn with the arm folded at its own
    base (corner c1052, 2026-09-05: the plug was pulled out of the hand). So
    rope_winding places C where the straight run already counts right. The
    ray is a bearing about the post, so which heights work depends on the
    anchor and the post together -- hence y is derived too, before x.
    """

    lo, hi = (float(v) for v in layout.cfg.fixtures.C.y_range)
    exit_bearing, opposite = exit_and_opposite_bearings(layout)
    ys = np.arange(lo, hi + 1e-9, TARGET_STEP)
    if ys[-1] < hi - 1e-9:
        ys = np.append(ys, hi)
    windows, start, prev = [], None, None
    for y in ys:
        ok = bool(_x_windows_at(layout, float(y), exit_bearing, opposite))
        if ok and start is None:
            start = float(y)
        elif not ok and start is not None:
            windows.append((start, float(prev)))
            start = None
        prev = y
    if start is not None:
        windows.append((start, float(ys[-1])))
    return [(a, b) for a, b in windows if b > a]


def target_x_windows_straight(layout) -> list[tuple[float, float]]:
    """x intervals for C at its current y (see `target_y_windows`)."""

    exit_bearing, opposite = exit_and_opposite_bearings(layout)
    return _x_windows_at(layout, float(layout.cfg.fixtures.C.y), exit_bearing, opposite)


def _from_frac(windows, frac: float) -> float:
    total = sum(b - a for a, b in windows)
    run = float(frac) * total
    for a, b in windows:
        if run <= b - a:
            return float(a + run)
        run -= b - a
    return float(windows[-1][1])


def target_y_from_frac(layout, frac: float) -> float:
    windows = target_y_windows(layout)
    if not windows:
        plug = plug_spawn_task_xy(layout)
        raise ValueError(
            f"target window is empty: with the plug spawning at ({plug[0]:+.3f}, {plug[1]:+.3f}) no "
            f"(x, y) in the C box keeps clear of it and lets the straight run to C close on the target winding."
        )
    return _from_frac(windows, frac)


def target_x_from_frac(layout, frac: float) -> float:
    """Map a unit fraction onto `target_x_windows_straight`, by length."""

    windows = target_x_windows_straight(layout)
    if not windows:
        plug = plug_spawn_task_xy(layout)
        raise ValueError(
            f"target x window is empty at C.y={float(layout.cfg.fixtures.C.y):+.3f}: with the plug spawning "
            f"at x={plug[0]:+.3f} no x in {[float(v) for v in layout.cfg.fixtures.C.x_range]} keeps clear "
            "of it and lets the straight run to C close on the target winding."
        )
    return _from_frac(windows, frac)


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
    detours = float(sum(1 for l in labels if l == "to_C_around"))
    rows.append(("run_to_c_is_straight", detours, 0.0, detours == 0.0))
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
    "TARGET_STEP",
    "WRAP_GAP_MIN",
    "arc_length",
    "rope_winding_checks",
    "spawn_arc_chord",
    "sweep_from_slack",
    "exit_and_opposite_bearings",
    "straight_run_clear",
    "target_x_from_frac",
    "target_x_windows_straight",
    "target_y_from_frac",
    "target_y_windows",
]
