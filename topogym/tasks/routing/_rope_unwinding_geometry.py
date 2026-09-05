"""rope_unwinding's layout rules and feasibility checks, numpy only.

Kept apart from `rope_unwinding.py` so the offline gate
(`tests/check_rope_unwinding_geometry.py`) and the variation harness can load
them without Genesis: `cable_routing.py` imports Genesis at module level, which
is why the gate runs the planner against a stand-in layout. Everything here
takes that same layout surface -- an object with `fixture_pos`, `route_point`,
`route_polyline`, `world_z` and a `cfg` -- so the real `RopeUnwindingLayout`
and the test stand-in read the same rows.

Task-frame metres unless a name says world.
"""

from __future__ import annotations

import numpy as np

from topogym.planning.rope_winding_planner import (
    SLACK_BAND,
    WindingSpec,
    free_end_winding_delta,
    plan_rope_winding_route,
    spawn_winding,
    taut_demand,
)

# Rules shared with rope_winding (post height, wrap-height window, target x
# clearance, forced-orbit view) live in `_winding_post_geometry`; re-exported
# here so the offline gate and the rng test keep importing them from this
# module.
from ._winding_post_geometry import (  # noqa: F401
    PALM_ABOVE_PADS,
    PLUG_TARGET_CLEARANCE,
    TOP_MARGIN,
    WORKSPACE_MARGIN,
    hand_reach,
    oracle_view as _oracle_view,
    plug_spawn_task_xy,
    post_top_task_z,
    target_x_from_frac,
    target_x_windows,
    wind_z_bounds,
    wind_z_from_frac,
    workspace_margin,
)

# The board-level leg after the anchor (see the task yaml's `routes.initial`).
LEAD_IN = 0.040
HELIX_STANDOFF = 0.002

# Clearances the rows below ask for: anchor to the wrap circle, wrap gap.
ANCHOR_CLEARANCE = 0.020
# Skin-to-skin gap between consecutive wraps. Measured with tetgen on the spawn
# tube (2026-09-04): with two or more wraps the surface self-intersects at a
# 2 mm gap (climb 0.010) almost everywhere and at 3 mm (0.011) when three
# wraps sit high on the post; 4 mm (0.012) tetrahedralises at every corner of
# the envelope. Independent of the anchor's distance.
WRAP_GAP_MIN = 0.004


def _sign(cfg) -> float:
    return 1.0 if str(cfg.winding.direction).lower() == "ccw" else -1.0


def mirror_sign(cfg) -> float:
    """+1 for a ccw wrap, -1 for cw: the y factor the layout applies to every fixture.

    `winding.direction: cw` IS the mirror layout (task doc section 1): the yaml's
    fixture positions are written for the ccw instance, and a cw instance is
    that scene reflected in the robot's x axis (y -> -y, wrap sense flipped).
    Both the Franka's base and the workspace box sit symmetrically about y = 0,
    so every feasibility row reads the same for the two senses.
    """

    return _sign(cfg)


def fixture_task_pos(cfg, name: str) -> np.ndarray:
    """Task-frame position of a fixture, mirrored for a cw wrap (see `mirror_sign`)."""

    fixture = cfg.fixtures[str(name)]
    return np.array(
        [float(fixture.x), mirror_sign(cfg) * float(fixture.y), float(fixture.z)], dtype=float
    )


def rope_unwinding_checks(layout) -> list[tuple[str, float, float, bool]]:
    """``[(name, measured, limit, ok)]`` for a spawnable, solvable layout.

    One list for the randomizer's reject step, the offline gate, the corner
    harness and the demo's start-up print. Runs the real planner on the layout
    (no scene), so the reach and slack rows read the oracle's actual waypoints.
    """

    layout = _oracle_view(layout)
    cfg = layout.cfg
    spec = WindingSpec.from_config(cfg)
    winding = cfg.winding
    post = cfg.fixtures[spec.post]
    rope_r = float(cfg.rope.radius)
    sign = _sign(cfg)
    post_top = post_top_task_z(cfg)
    origin_z = layout.world_z(0.0)

    center_xy = np.asarray(layout.fixture_pos(spec.post), dtype=float)[:2]
    anchor_xy = np.asarray(layout.fixture_pos("S"), dtype=float)[:2]
    target_xy = np.asarray(layout.fixture_pos("C"), dtype=float)[:2]
    helix_radius = float(post.radius) + rope_r + HELIX_STANDOFF
    wrap_band = float(post.radius) + 3.0 * rope_r

    spawn = np.asarray(layout.route_polyline("initial"), dtype=float)
    radial = np.linalg.norm(spawn[:, :2] - center_xy[None, :], axis=1)
    on_post = radial <= wrap_band
    last_on = int(np.flatnonzero(on_post)[-1])
    # The tail proper starts one point after the wrap; the very first arc point
    # is still inside the band by construction (it leaves along the tangent).
    tail_radial = radial[last_on + 2 :] if last_on + 2 < len(radial) else radial[last_on + 1 :]
    plug_xy = spawn[-1, :2]

    # Spawn polyline in the task frame against the workspace box (a literal
    # copy of `manipulation_space.workspace` in the task yaml).
    origin_xy = np.asarray(layout.position_to_world(np.zeros(3)), dtype=float)[:2]
    spawn_xy = spawn[:, :2] - origin_xy
    workspace = cfg.workspace
    wx = (float(workspace.x[0]), float(workspace.x[1]))
    wy = (float(workspace.y[0]), float(workspace.y[1]))
    ws_margin = float(
        min(
            (spawn_xy[:, 0] - wx[0]).min(),
            (wx[1] - spawn_xy[:, 0]).min(),
            (spawn_xy[:, 1] - wy[0]).min(),
            (wy[1] - spawn_xy[:, 1]).min(),
        )
    )

    _, plan = plan_rope_winding_route(layout)
    points = np.asarray([wp.position for wp in plan.waypoints], dtype=float)
    labels = [str(wp.label) for wp in plan.waypoints]
    orbit_z = np.array([p[2] for p, l in zip(points, labels) if l.startswith("wind_t")])
    palm_clear = (float(orbit_z.min()) - origin_z + PALM_ABOVE_PADS) - post_top
    # The planner's waypoints are world points; the base is a task-frame point.
    base_xy = np.asarray([float(v) for v in cfg.reach.base_xy], dtype=float)
    reach = float(np.linalg.norm(points[:, :2] - origin_xy - base_xy, axis=1).max())
    need, _ = taut_demand(layout, spec, plan.waypoints)
    length = float(np.sum(np.linalg.norm(np.diff(spawn, axis=0), axis=1)))
    slack = (length - need) / need
    spawn_reading = spawn_winding(layout, spec)
    delta = free_end_winding_delta(
        [spawn[-1]] + list(points), np.asarray(layout.fixture_pos(spec.post)), np.asarray(layout.fixture_pos("S"))
    )

    ge = [
        ("anchor_clears_post", float(np.linalg.norm(anchor_xy - center_xy)) - (LEAD_IN + helix_radius), ANCHOR_CLEARANCE),
        (
            "wraps_below_post_top",
            post_top - TOP_MARGIN - (float(winding.wind_z_start) + int(winding.start_turns) * float(winding.climb_per_turn) + rope_r),
            0.0,
        ),
        ("bottom_wrap_above_base", float(winding.wind_z_start) - rope_r - float(post.base_height), 0.0),
        ("wrap_gap", float(winding.climb_per_turn) - 2.0 * rope_r, WRAP_GAP_MIN),
        ("tail_clears_post", float(tail_radial.min()) - wrap_band, 0.0),
        ("spawn_in_workspace", ws_margin, WORKSPACE_MARGIN),
        ("plug_clears_target", float(np.linalg.norm(plug_xy - target_xy)), PLUG_TARGET_CLEARANCE),
        ("palm_clears_post_top", palm_clear, 0.0),
    ]
    rows = [(name, value, limit, value >= limit - 1e-9) for name, value, limit in ge]
    max_reach = float(cfg.reach.max_hand_dist)
    rows.append(("hand_reach", reach, max_reach, reach <= max_reach + 1e-9))
    low, high = SLACK_BAND
    rows.append(("slack_in_band", slack, low, low - 1e-9 <= slack <= high + 1e-9))
    rows.append(("spawn_reads_start_turns", abs(spawn_reading - sign * int(winding.start_turns)), 1e-6, abs(spawn_reading - sign * int(winding.start_turns)) < 1e-6))
    rows.append(("free_end_reads_target", abs(spawn_reading + delta - spec.target_winding), 1e-6, abs(spawn_reading + delta - spec.target_winding) < 1e-6))
    return rows


__all__ = [
    "HELIX_STANDOFF",
    "LEAD_IN",
    "PALM_ABOVE_PADS",
    "fixture_task_pos",
    "mirror_sign",
    "plug_spawn_task_xy",
    "post_top_task_z",
    "rope_unwinding_checks",
    "target_x_windows",
    "target_x_from_frac",
    "wind_z_bounds",
    "wind_z_from_frac",
]
