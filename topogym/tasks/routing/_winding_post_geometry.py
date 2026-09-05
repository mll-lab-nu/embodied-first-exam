"""Layout rules shared by the two winding-post tasks (rope_winding, rope_unwinding).

Both tasks wind a FEM rope on the same post between the same three fixtures
(anchor terminal S, post, target bullseye C), so the rules that only depend
on the post -- how high the lowest wrap may sit, where the target may lie
relative to the plug's spawn point, how the feasibility rows see a forced
orbit -- live here once. numpy only: no Genesis, so the offline gates and the
variation harness can import this next to the planner.

Everything takes the layout surface the planner uses -- an object with
`fixture_pos`, `route_point`, `route_polyline`, `world_z`,
`position_to_world` and a `cfg` -- so the real Layouts and the test stand-in
read the same numbers. Task-frame metres unless a name says world.
"""

from __future__ import annotations

import copy

import numpy as np

from topogym.primitives.pick_place import HAND_TO_PAD_Z

# Underside of the hand's collision body above the finger pads (`hand_c` z lower
# bound 0.0259 against HAND_TO_PAD_Z): what would hit the post's top while the
# hand orbits below it. Same number the offline gates have used since 08-26.
PALM_ABOVE_PADS = HAND_TO_PAD_Z - 0.0259

# The spiral must end this far below the post's top (the gateway that changes
# winding is never used by the oracle), and the lowest wrap's centreline stays
# in this window; the upper end is capped by the wrap count and climb.
TOP_MARGIN = 0.010
WIND_Z_LO = 0.035
WIND_Z_HI = 0.055

# Spawn geometry to the hand's workspace edge; plug spawn to the target
# bullseye (plug flange radius 0.015 + half the bullseye's long side 0.020 +
# 5 mm -- the plug must not spawn on the target it is to be placed on; the
# bullseye has no collision body, so this is task meaning, not contact).
WORKSPACE_MARGIN = 0.040
PLUG_TARGET_CLEARANCE = 0.040


def post_top_task_z(cfg) -> float:
    post = cfg.fixtures[str(cfg.winding.post)]
    return float(post.z) + 0.5 * float(post.height)


def wraps_on_post(cfg) -> int:
    """How many wraps the spiral holds at its fullest: the spawned ones for
    rope_unwinding (`start_turns`, `turns` = 0), the wound ones for
    rope_winding (`turns`, `start_turns` = 0)."""

    winding = cfg.winding
    return max(int(getattr(winding, "start_turns", 0) or 0), int(winding.turns))


def wind_z_bounds(cfg) -> tuple[float, float]:
    """Where the lowest wrap's centreline may sit for the drawn wraps and climb.

    Upper end: the top wrap's upper edge stays `TOP_MARGIN` under the post top.
    Raises when the window is empty (a rejected draw).
    """

    winding = cfg.winding
    wraps = wraps_on_post(cfg)
    cap = (
        post_top_task_z(cfg)
        - TOP_MARGIN
        - float(cfg.rope.radius)
        - wraps * float(winding.climb_per_turn)
    )
    hi = min(WIND_Z_HI, cap)
    if hi < WIND_Z_LO:
        raise ValueError(
            f"wind_z_start window is empty: {wraps} wraps of "
            f"{float(winding.climb_per_turn):.3f} leave the lowest wrap at most {cap:.3f} "
            f"under the post top, below the {WIND_Z_LO:.3f} floor."
        )
    return WIND_Z_LO, hi


def wind_z_from_frac(cfg, frac: float) -> float:
    lo, hi = wind_z_bounds(cfg)
    return float(lo + float(frac) * (hi - lo))


def task_xy(layout, world_point) -> np.ndarray:
    """A world point's task-frame xy (the layouts add the task origin)."""

    origin = np.asarray(layout.position_to_world(np.zeros(3)), dtype=float)
    return np.asarray(world_point, dtype=float)[:2] - origin[:2]


def plug_spawn_task_xy(layout) -> np.ndarray:
    """Task-frame xy of the plug's spawn point (the spawn route's last point)."""

    spawn = np.asarray(layout.route_polyline("initial"), dtype=float)
    return task_xy(layout, spawn[-1])


def target_x_windows(layout) -> list[tuple[float, float]]:
    """Where the target C's x may fall: the yaml's `x_range` minus the disk of
    `PLUG_TARGET_CLEARANCE` about the plug's spawn point (at C's y).

    Where the plug spawns depends on the post and the anchor (and, for
    rope_unwinding, the wrap count and sense), so the disk may cut the range
    anywhere: the result is the list of surviving intervals, low to high.
    Empty when the disk covers the whole range (a rejected draw). C's y is
    read through the layout, so a mirrored layout (rope_unwinding's cw) is
    handled without knowing about mirrors.
    """

    cfg = layout.cfg
    lo, hi = (float(v) for v in cfg.fixtures.C.x_range)
    plug = plug_spawn_task_xy(layout)
    target_y = float(task_xy(layout, layout.fixture_pos("C"))[1])
    dy = target_y - float(plug[1])
    half = PLUG_TARGET_CLEARANCE**2 - dy * dy
    if half <= 0.0:
        return [(lo, hi)]
    half = float(np.sqrt(half))
    left, right = float(plug[0]) - half, float(plug[0]) + half
    windows = []
    if left > lo:
        windows.append((lo, min(left, hi)))
    if right < hi:
        windows.append((max(right, lo), hi))
    return [(a, b) for a, b in windows if b > a]


def target_x_from_frac(layout, frac: float) -> float:
    """Map a unit fraction onto the surviving windows, by length."""

    windows = target_x_windows(layout)
    if not windows:
        plug = plug_spawn_task_xy(layout)
        raise ValueError(
            f"target x window is empty: the plug spawns at x={plug[0]:+.3f}, and every x in "
            f"{[float(v) for v in layout.cfg.fixtures.C.x_range]} is within "
            f"{PLUG_TARGET_CLEARANCE:.3f} m of it at C.y={float(layout.cfg.fixtures.C.y):+.3f}."
        )
    total = sum(b - a for a, b in windows)
    run = float(frac) * total
    for a, b in windows:
        if run <= b - a:
            return float(a + run)
        run -= b - a
    return float(windows[-1][1])


def oracle_view(layout):
    """The layout as the oracle plans it: `winding.orbit_direction` cleared.

    The rows judge the layout, not the policy. A forced orbit sense is the
    task's contrast pair (`orbit_direction: same` / `opposite` in a sweep),
    which must not make a feasible layout read as infeasible -- 2026-09-04
    every rope_unwinding wrong_way cell was rejected 21 times because
    `free_end_reads_target` planned with the wrong-way orbit.
    """

    if getattr(layout.cfg.winding, "orbit_direction", None) is None:
        return layout
    cfg = copy.deepcopy(layout.cfg)
    try:
        from omegaconf import OmegaConf

        if OmegaConf.is_config(cfg):
            OmegaConf.set_readonly(cfg, False)
    except ImportError:  # the test stand-in's plain dict nodes
        pass
    cfg.winding.orbit_direction = None
    view = copy.copy(layout)
    object.__setattr__(view, "cfg", cfg)
    return view


def hand_reach(layout, waypoints) -> float:
    """Farthest any planned waypoint sits from the Franka base (`reach.base_xy`)."""

    points = np.asarray([wp.position for wp in waypoints], dtype=float)
    base_xy = np.asarray([float(v) for v in layout.cfg.reach.base_xy], dtype=float)
    origin = np.asarray(layout.position_to_world(np.zeros(3)), dtype=float)
    return float(np.linalg.norm(points[:, :2] - origin[:2] - base_xy, axis=1).max())


def workspace_margin(layout, world_points) -> float:
    """Smallest distance from any of `world_points` to the workspace box's x / y edges
    (the box is the task yaml's literal copy of `manipulation_space.workspace`)."""

    pts = np.asarray(world_points, dtype=float).reshape(-1, 3)
    origin = np.asarray(layout.position_to_world(np.zeros(3)), dtype=float)
    xy = pts[:, :2] - origin[:2]
    workspace = layout.cfg.workspace
    wx = (float(workspace.x[0]), float(workspace.x[1]))
    wy = (float(workspace.y[0]), float(workspace.y[1]))
    return float(
        min(
            (xy[:, 0] - wx[0]).min(),
            (wx[1] - xy[:, 0]).min(),
            (xy[:, 1] - wy[0]).min(),
            (wy[1] - xy[:, 1]).min(),
        )
    )


__all__ = [
    "PALM_ABOVE_PADS",
    "PLUG_TARGET_CLEARANCE",
    "TOP_MARGIN",
    "WIND_Z_HI",
    "WIND_Z_LO",
    "WORKSPACE_MARGIN",
    "hand_reach",
    "oracle_view",
    "plug_spawn_task_xy",
    "post_top_task_z",
    "target_x_from_frac",
    "target_x_windows",
    "task_xy",
    "wind_z_bounds",
    "wind_z_from_frac",
    "workspace_margin",
    "wraps_on_post",
]
