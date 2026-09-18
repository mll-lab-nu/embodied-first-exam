"""Spawn geometry for swap_crossing_sign's three-rope, two-crossing cell (Genesis-free).

Scene. Three ropes leave the power strip. One of them (rope 0, "the straight
one") runs straight out along +x. The other two leave the strip further along
it, run straight out for a while, then turn once and go diagonally across the
straight one, ending at their plugs on its far side. So there are exactly two
crossings, one per pair -- rope 0 with rope 1, rope 0 with rope 2 -- at two
different places along rope 0, and ropes 1 and 2 never touch each other.

At spawn the two diagonal ropes lie ON TOP of the straight one, which is what
makes the task three moves rather than five: the oracle lifts each diagonal rope
away (neither is pinned, so both are free to lift), and then lays the straight
one across both in a single move, which is the only move that has to be placed
precisely. Measured 2026-09-12: a laid tail settles 7-9 cm from the straight
chord the planner draws, and that error can be absorbed when only one lay has to
land right (re-planning simply picks another landing), but not when a second lay
depends on where the first one ended up -- which is what the lane-swap
construction of `_swap_crossing_sign_scene.py` needs for two crossings, and why
its two-crossing episodes failed on GPU five times.

This module builds only that one cell. The one-crossing cells keep the lane-swap
construction, which is proven on GPU.

Every function here is a pure function of numbers, so the variation hooks, the
offline gates and the offline sequence planner all build the ropes the scene
builder will build.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

#: Straight run kept at the anchored end before a rope may turn (it sits inside
#: the strip's outlet, and the builder anchors this stretch).
ANCHOR_RUN = 0.03
#: Control-point pitch along each straight stretch. The spline is fitted to these
#: points, so they have to be dense enough to hold the line.
STEP = 0.02
#: Smallest angle of the single corner each diagonal rope has, in degrees, as the
#: turn away from its outgoing run. A sharper corner than this reads as a kink and
#: is where a swept tube pinches on itself (`untangle_continuous.rope_mesh`).
MAX_TURN_DEG = 50.0
#: Two ropes that do not cross keep at least this much daylight between their
#: centre lines, away from the crossings. Two rope radii (8 mm) plus the 16 mm the
#: judge calls "apart", plus a little.
SPAWN_CLEARANCE = 0.030
#: How far from a crossing a point has to be before it counts towards the clearance
#: above -- at the crossing itself the two ropes are meant to touch.
CROSSING_SKIP = 0.05
#: The two crossings sit at least this far apart along the straight rope, so the
#: judge (which merges hits of one pair within its merge radius) and the oracle
#: (which lifts one crossing clear at a time) see two separate places.
CROSSING_GAP_MIN = 0.080
#: A plug may not sit on a rope: its flange plus a rope radius plus a margin.
PLUG_OFF_ROPE = 0.035


@dataclass(frozen=True)
class CrossedPairCrossing:
    """One crossing, in the form `expected_code` reads (index = order along rope 0)."""

    index: int
    over_strand: int
    under_strand: int
    position: tuple[float, float]


@dataclass(frozen=True)
class CrossedPairSpec:
    """What the builder needs: the control points, and what was built where."""

    n_strands: int
    control_points: dict[int, np.ndarray]
    crossings: tuple[CrossedPairCrossing, ...]
    word: tuple[int, ...] = ()  # no braid word here; kept so logs can print it


def _line(a, b, *, step: float = STEP) -> list[np.ndarray]:
    """Points along a->b at ~``step``, including a, excluding b."""

    a, b = np.asarray(a, dtype=float), np.asarray(b, dtype=float)
    n = max(1, int(np.ceil(float(np.linalg.norm(b - a)) / step)))
    return [a + (b - a) * t for t in np.linspace(0.0, 1.0, n + 1)[:-1]]


def straight_rope(*, x_start: float, y: float, x_end: float, z: float) -> np.ndarray:
    """Rope 0: out of the strip and straight along +x."""

    pts = _line((x_start, y), (x_end, y)) + [np.array([x_end, y])]
    return np.column_stack([np.asarray(pts, dtype=float), np.full(len(pts), z)])


def diagonal_leg(*, y: float, turn_x: float, cross_x: float, y_straight: float, tail: float):
    """Where a diagonal rope turns, where it crosses rope 0, and where its plug lands.

    Parameterised by the crossing rather than by the plug: the rope runs out at its
    own y, turns at ``turn_x``, and goes straight through ``(cross_x, y_straight)``,
    continuing ``tail`` further along the same line to its plug. Turning is what
    sets the angle, and the angle is what a swept tube can or cannot hold, so it is
    the quantity the derivation gets to control.
    """

    turn = np.array([turn_x, y], dtype=float)
    cross = np.array([cross_x, y_straight], dtype=float)
    leg = cross - turn
    length = float(np.linalg.norm(leg))
    if length < 1e-9:
        return turn, cross, cross
    direction = leg / length
    return turn, cross, cross + direction * float(tail)


def diagonal_rope(*, x_start: float, y: float, turn_x: float, cross_x: float, y_straight: float,
                  tail: float, z: float) -> np.ndarray:
    """One of the two ropes that cross rope 0: straight out, one turn, across, on to its plug."""

    turn, _cross, plug = diagonal_leg(y=y, turn_x=turn_x, cross_x=cross_x, y_straight=y_straight, tail=tail)
    turn = np.array([max(float(turn[0]), x_start + ANCHOR_RUN), y])
    pts = _line((x_start, y), turn) + _line(turn, plug) + [plug]
    return np.column_stack([np.asarray(pts, dtype=float), np.full(len(pts), z)])


def turn_angle_deg(*, y: float, turn_x: float, cross_x: float, y_straight: float) -> float:
    """How far the single corner turns the rope away from its outgoing run, in degrees."""

    return float(np.degrees(np.arctan2(abs(y_straight - y), max(cross_x - turn_x, 1e-9))))


def turn_x_for_angle(*, y: float, cross_x: float, y_straight: float, angle_deg: float) -> float:
    """The latest turn that still keeps the corner at or under ``angle_deg``."""

    return float(cross_x - abs(y_straight - y) / max(np.tan(np.radians(angle_deg)), 1e-9))


def spec_from_leaves(cfg) -> CrossedPairSpec:
    """The task yaml's ``crossed_pair:`` leaves -> the three ropes the builder will make.

    ``cfg`` is the config node (OmegaConf) or a plain dict of the same leaves.
    Rope 0 is the straight one; ropes 1 and 2 cross it, rope 1 nearer the strip.
    Both of them lie on top of rope 0 at spawn.
    """

    x_start = float(cfg["x_start"])
    base_z, over = float(cfg["base_z"]), float(cfg["over_lift"])
    y0 = float(cfg["center_y"])
    ropes = {0: straight_rope(x_start=x_start, y=y0, x_end=float(cfg["x_end"]), z=base_z)}
    crossings = []
    for k, (dy, turn, x_cross, tail) in enumerate(
        (
            (float(cfg["anchor_dy_1"]), float(cfg["turn_x_1"]), float(cfg["cross_x_1"]), float(cfg["tail_1"])),
            (float(cfg["anchor_dy_2"]), float(cfg["turn_x_2"]), float(cfg["cross_x_2"]), float(cfg["tail_2"])),
        ),
        start=1,
    ):
        y = y0 + dy
        ropes[k] = diagonal_rope(x_start=x_start, y=y, turn_x=turn, cross_x=x_cross,
                                 y_straight=y0, tail=tail, z=base_z)
        # The diagonal rope lies over the straight one: lift it at the crossing,
        # the way the lane-swap construction lifts its over-strand.
        near = np.linalg.norm(ropes[k][:, :2] - np.array([x_cross, y0])[None], axis=1) < 0.03
        ropes[k][near, 2] = base_z + over
        crossings.append(CrossedPairCrossing(index=k - 1, over_strand=k, under_strand=0,
                                             position=(x_cross, y0)))
    order = sorted(crossings, key=lambda c: c.position[0])
    crossings = tuple(
        CrossedPairCrossing(index=i, over_strand=c.over_strand, under_strand=c.under_strand, position=c.position)
        for i, c in enumerate(order)
    )
    return CrossedPairSpec(n_strands=3, control_points=ropes, crossings=crossings)


def derive_leaves(cfg, *, strip_half_length: float, workspace_x, workspace_y, workspace_margin: float) -> None:
    """Unit draws -> an arrangement that already satisfies the checks below.

    Written as a construction rather than as a rejection test, because every
    constraint here has a direction: a crossing too near the strip leaves no room
    to turn into it, a corner too sharp is a kink the tube cannot hold, a plug too
    far out is off the table. Each is solved for in turn, so a draw is reshaped
    instead of thrown away and the rope-count axis keeps its proportions.

    Reads ``cross_u_1/2``, ``anchor_u_1/2``, ``tail_u_1/2`` and ``center_y_u``
    (each 0..1) and writes the leaves ``spec_from_leaves`` reads.
    """

    x_start, x_end = float(cfg["x_start"]), float(cfg["x_end"])
    # Where the two diagonal ropes leave the strip, both on the same side of rope 0:
    # rope 1 nearer to it, rope 2 a further step away, so the two never meet.
    near = float(cfg["anchor_dy_near"])
    # Which side of the straight rope the two come from is a coin flip, so the
    # scene does not always read the same way round.
    side = -1.0 if float(cfg["mirror_u"]) < 0.5 else 1.0
    dy_1 = side * (near + 0.03 * float(cfg["anchor_u_1"]))
    dy_2 = dy_1 + side * (float(cfg["anchor_dy_step"]) + 0.03 * float(cfg["anchor_u_2"]))
    cfg["anchor_dy_1"], cfg["anchor_dy_2"] = float(dy_1), float(dy_2)

    # Rope 0's line, and with it both crossings, may shift sideways as far as the
    # strip still covers all three outlets.
    room = max(strip_half_length - abs(dy_2) - float(cfg["tube_radius"]), 0.0)
    cfg["center_y"] = float((2.0 * float(cfg["center_y_u"]) - 1.0) * room)
    y0 = float(cfg["center_y"])

    # A rope can only turn into its crossing gently if it has room to climb: the
    # corner limit fixes how much run each one needs before it, which is what puts
    # a floor under where its crossing may sit.
    def earliest_crossing(dy: float) -> float:
        return x_start + ANCHOR_RUN + abs(dy) / float(np.tan(np.radians(MAX_TURN_DEG))) + 0.01

    first_lo = earliest_crossing(dy_1)
    first_hi = x_end - CROSSING_GAP_MIN - 0.12
    cross_1 = first_lo + max(first_hi - first_lo, 0.0) * float(cfg["cross_u_1"])
    second_lo = max(cross_1 + CROSSING_GAP_MIN, earliest_crossing(dy_2))
    second_hi = x_end - 0.06
    cross_2 = second_lo + max(second_hi - second_lo, 0.0) * float(cfg["cross_u_2"])
    cfg["cross_x_1"], cfg["cross_x_2"] = float(cross_1), float(cross_2)

    plug_0 = np.array([x_end, y0])
    placed: list[np.ndarray] = [plug_0]
    for k, cross, dy in ((1, cross_1, dy_1), (2, cross_2, dy_2)):
        # Turn early enough that the corner stays under the kink limit, and never
        # inside the anchored run.
        latest = turn_x_for_angle(y=y0 + dy, cross_x=cross, y_straight=y0, angle_deg=MAX_TURN_DEG)
        turn_x = float(max(min(latest, cross - 0.04), x_start + ANCHOR_RUN))
        cfg[f"turn_x_{k}"] = turn_x
        # How far past the crossing the plug may sit: inside the workspace, and far
        # enough from the plugs already placed for the gripper to close on one plug
        # without the next one between its fingers.
        direction = np.array([cross - turn_x, -dy], dtype=float)
        direction /= max(float(np.linalg.norm(direction)), 1e-9)
        cross_xy = np.array([cross, y0])
        edge_y = workspace_y[1] - workspace_margin if direction[1] > 0 else workspace_y[0] + workspace_margin
        room = min(
            (workspace_x[1] - workspace_margin - cross) / max(direction[0], 1e-9),
            (edge_y - y0) / direction[1] if abs(direction[1]) > 1e-9 else float("inf"),
        )
        options = [
            t for t in np.arange(0.07, min(0.18, room) + 1e-9, 0.005)
            if all(float(np.linalg.norm(cross_xy + direction * t - other)) >= float(cfg["plug_gap_min"])
                   for other in placed)
        ]
        tail = options[int(float(cfg[f"tail_u_{k}"]) * (len(options) - 1))] if options else max(min(0.12, room), 0.07)
        cfg[f"tail_{k}"] = float(tail)
        placed.append(cross_xy + direction * tail)


def scene_checks(spec: CrossedPairSpec, cfg, *, min_plug_gap: float, plug_ahead: float,
                 flange_radius: float, workspace_x, workspace_y,
                 workspace_margin: float, merge_radius: float) -> list[tuple[str, float, float, bool]]:
    """``[(name, measured, limit, ok)]`` for one spawn, before anything is built.

    - ``crossing_count``   exactly two crossings, read off the control points by
                           the same reader the judge uses.
    - ``crossing_gap``     distance between the two crossings: they have to be two
                           places, not one (the judge merges hits of a pair within
                           its merge radius, and the oracle lifts one clear at a time).
    - ``spawn_clearance``  closest approach of two ropes away from the crossings.
    - ``plug_gap``         closest pair of plugs (the gripper's span).
    - ``plug_off_rope``    no plug sits on a rope: a crossing has to be rope on
                           rope (decision 2026-09-12).
    - ``turn_angle``       the single corner of each diagonal rope, against the
                           kink limit a swept tube can hold.
    - ``footprint_x`` / ``footprint_y``  ropes and plugs inside the workspace.
    """

    from topogym.planning.rope_crossings import find_crossings

    dense = {k: densify(v, 0.005) for k, v in spec.control_points.items()}
    found = find_crossings(dense, merge_radius=merge_radius)
    positions = [c.position for c in spec.crossings]
    gap = (
        float(np.hypot(positions[0][0] - positions[1][0], positions[0][1] - positions[1][1]))
        if len(positions) > 1 else float("inf")
    )

    clearance = float("inf")
    ropes = sorted(dense)
    for i, a in enumerate(ropes):
        for b in ropes[i + 1:]:
            pa, pb = dense[a][:, :2], dense[b][:, :2]
            keep_a = np.ones(len(pa), dtype=bool)
            keep_b = np.ones(len(pb), dtype=bool)
            for position in positions:
                keep_a &= np.linalg.norm(pa - np.asarray(position)[None], axis=1) > CROSSING_SKIP
                keep_b &= np.linalg.norm(pb - np.asarray(position)[None], axis=1) > CROSSING_SKIP
            if keep_a.any() and keep_b.any():
                clearance = min(clearance, float(
                    np.linalg.norm(pa[keep_a][:, None] - pb[keep_b][None], axis=2).min()))

    plugs = {k: v[-1, :2] for k, v in dense.items()}
    plug_gap = min(
        float(np.linalg.norm(plugs[a] - plugs[b]))
        for i, a in enumerate(ropes) for b in ropes[i + 1:]
    )
    plug_off = float("inf")
    for k, plug in plugs.items():
        for other in ropes:
            if other == k:
                continue
            plug_off = min(plug_off, float(np.linalg.norm(dense[other][:, :2] - plug[None], axis=1).min()))

    y0 = float(cfg["center_y"])
    turns = [
        turn_angle_deg(y=y0 + float(cfg[f"anchor_dy_{k}"]), turn_x=float(cfg[f"turn_x_{k}"]),
                       cross_x=float(cfg[f"cross_x_{k}"]), y_straight=y0)
        for k in (1, 2)
    ]
    # Same reading as the lane-swap construction's rows: in x the plug's pin tip
    # must be inside the far edge and the anchored end inside the near one (the
    # anchor sits in the strip, 2.5 cm from the edge, so this limit is 0, not the
    # margin); in y the widest point of a plug's flange keeps the margin.
    xs = np.concatenate([v[:, 0] for v in dense.values()])
    ys = np.concatenate([v[:, 1] for v in dense.values()])
    room_x = min(
        workspace_x[1] - (max(float(p[0]) for p in plugs.values()) + plug_ahead),
        float(xs.min()) - workspace_x[0],
    )
    room_y = min(
        workspace_y[1] - (float(ys.max()) + flange_radius),
        (float(ys.min()) - flange_radius) - workspace_y[0],
    )

    return [
        ("crossing_count", float(len(found)), 2.0, len(found) == 2),
        ("crossing_gap", gap, CROSSING_GAP_MIN, gap >= CROSSING_GAP_MIN - 1e-9),
        ("spawn_clearance", clearance, SPAWN_CLEARANCE, clearance >= SPAWN_CLEARANCE - 1e-9),
        ("plug_gap", plug_gap, min_plug_gap, plug_gap >= min_plug_gap - 1e-9),
        ("plug_off_rope", plug_off, PLUG_OFF_ROPE, plug_off >= PLUG_OFF_ROPE - 1e-9),
        ("turn_angle", float(max(turns)), MAX_TURN_DEG, max(turns) <= MAX_TURN_DEG + 1e-9),
        ("footprint_x", room_x, 0.0, room_x >= -1e-9),
        ("footprint_y", room_y, workspace_margin, room_y >= workspace_margin - 1e-9),
    ]


def densify(points: np.ndarray, step: float = 0.005) -> np.ndarray:
    """Linear resampling at ~``step`` (keeps every control point)."""

    out = [np.asarray(points[0], dtype=float)]
    for a, b in zip(points[:-1], points[1:]):
        n = max(1, int(np.ceil(float(np.linalg.norm(b[:2] - a[:2])) / step)))
        for t in np.linspace(0.0, 1.0, n + 1)[1:]:
            out.append(a + (b - a) * t)
    return np.stack(out, axis=0)


__all__ = [
    "ANCHOR_RUN",
    "CROSSING_GAP_MIN",
    "MAX_TURN_DEG",
    "PLUG_OFF_ROPE",
    "SPAWN_CLEARANCE",
    "CrossedPairCrossing",
    "CrossedPairSpec",
    "diagonal_leg",
    "densify",
    "diagonal_rope",
    "scene_checks",
    "spec_from_leaves",
    "straight_rope",
    "turn_angle_deg",
    "turn_x_for_angle",
]
