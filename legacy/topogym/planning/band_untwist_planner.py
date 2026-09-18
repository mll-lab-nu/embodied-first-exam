"""Oracle for `band_untwist` (docx 3.3): plan on the measured rope, run the first move.

The rope lies crossed over itself once or twice (figure-8, "6", twist, O|-|O).
Every move is the same grasp-lift-carry-place on a plug: grasp the plug whose
strand is ON TOP at a crossing, lift until the rope from the plug to just past
that crossing hangs below the hand, carry it round, lay it down beside the rest
-- the standing rule every entangle oracle in this repo follows (never pull a
strand out from underneath). Which plug, how far up and where to land come from
the move model `band_untwist_sequence.py`, planned afresh on the settled,
measured centreline before every move; only the plan's first move is run.

Three modes, one machine:

- ``oracle``: the plan's first move.
- ``wrong_end``: at the crossing the oracle would undo, grasp the plug on the
  UNDER pass's side instead and flip it the same way -- the docx's "flipped from
  the wrong side". On the figure-8 that is today's contrast: 1 -> 2.
- ``one_move``: the oracle with a budget of one move (`BandUntwistRule.budget_cap`):
  on a two-move spawn it leaves a crossing, which shows that the judge wants
  every crossing gone.

Kept from the one-crossing planner: `place_beside` / `stay_strand_xy` /
`point_to_polyline`, today's figure-8 landing rule, which
`_figure_eight_geometry.predicted_place` replays and
`tests/check_band_untwist_sequence.py` compares the move model against.

Pure numpy; no Genesis.
"""

from __future__ import annotations

from dataclasses import dataclass, replace

import math

import numpy as np

from . import band_untwist_sequence as sequence
from .subgoal import PlannedSubgoal
from .waypoint import EpisodePlan, WaypointPlan, WaypointTarget


@dataclass(frozen=True)
class BandUntwistMoveCommand:
    """One grasp-lift-carry-place on one rope end (world frame)."""

    end: int  # rope end grasped (0 or 1)
    other_end: int
    grasped_over_end: bool  # False only for the wrong_end contrast
    grasp_xy: tuple[float, float]
    place_xy: tuple[float, float]
    crossing_xy: tuple[float, float]  # the deepest crossing the move lifts: its landing circle's centre
    crossing_z_gap: float
    lift_z: float
    # Rope arc from the plug to the deepest crossing it lifts -- what hangs below
    # the hand once the crossing is lifted, and what sets the lift height.
    crossing_arc: float
    carry: tuple[float, float, float]
    cross: tuple[float, float, float]
    settle: tuple[float, float, float]
    crossing_count_before: int
    # From the plan this move opens: its length, the crossing sequence the model
    # expects once this move is done, and the landing's margins.
    planned_moves: int = 1
    predicted_sequence: tuple = ()
    swing_deg: float = 0.0
    slack: float = 0.0
    lay_down_clearance: float = 0.0
    # How far the laid rope may bow off its chord, and the room the bowed
    # lines keep from the crossings this move leaves (inf when it leaves none).
    bend: float = 0.0
    room: float = float("inf")
    # "lay": carry_up / cross_over / place_down; "flip": FLIP_SEGMENTS points
    # on a half circle about ``axis`` (world, unit, horizontal), the last one
    # labelled place_down. ``path`` is what the demo executes, in order.
    kind: str = "lay"
    path: tuple = ()
    axis: tuple[float, float, float] = (0.0, 0.0, 0.0)
    flip_radius: float = 0.0


def point_to_polyline(point, polyline) -> float:
    """Smallest distance from ``point`` to the segments of ``polyline`` (xy)."""

    p = np.asarray(point, dtype=float)[:2]
    poly = np.asarray(polyline, dtype=float)[:, :2]
    if len(poly) == 1:
        return float(np.linalg.norm(p - poly[0]))
    a, b = poly[:-1], poly[1:]
    d = b - a
    length_sq = np.einsum("ij,ij->i", d, d)
    t = np.clip(np.einsum("ij,ij->i", p - a, d) / np.maximum(length_sq, 1e-18), 0.0, 1.0)
    return float(np.linalg.norm(p - (a + t[:, None] * d), axis=1).min())


def _rotate_about(pivot, point, angle: float) -> np.ndarray:
    pivot = np.asarray(pivot, dtype=float)
    offset = np.asarray(point, dtype=float) - pivot
    c, s = np.cos(angle), np.sin(angle)
    return pivot + np.array([c * offset[0] - s * offset[1], s * offset[0] + c * offset[1]])


PLACE_SWEEP_STEP = np.radians(0.5)
PLACE_SWEEP_MAX = np.radians(150.0)

#: The hand is kept within CROSS_TAUT x the lifted rope of the lift point at
#: the carry and cross-over waypoints, so the rope is not over-stretched.
#: Carried at the full lift height (scene top + lifted arc) the hand sits
#: sqrt(chord^2 + H^2) from the lift point: 1.26-1.43x the lifted rope on
#: every cell of the envelope, at the cross-over AND already at the carry pose
#: above the plug. Where the rope beyond the lift point is free (the
#: figure-8's closed lobe) it slides 8-9 cm and absorbs that; where it is
#: anchored (the "6" with the stem on top: loop plus a short tail to the parked
#: plug) the HAND gives instead and stops 78-90 mm short of its landing (seed
#: 11, filmed 2026-09-12). Lowered so that the 3D distance is CROSS_TAUT x the
#: lifted rope, the same cell solved with a 9 mm landing error. Not below the
#: height that keeps the lifted crossing (4 cm past the lift point)
#: CROSS_RIDE_MIN above the table in the straight-tail picture -- measured at
#: the cross-over pose the crossing rode 18-36 mm for a modelled 30, and
#: cleared. Until 2026-09-13 only the cross-over of a one-move episode was
#: lowered; the alternating twist's first move (two-move episode, taut lay)
#: dragged the rope past its lift point 4-9 cm into the second move's landing
#: zone by the same mechanism (`band_untwist_zh.md` §8.7), so every move's
#: carry and cross-over now follow the rule. The wrong_end contrast keeps the
#: full height (it lays a strand across the other on purpose).
CROSS_TAUT = 0.95
CROSS_RIDE_MIN = 0.030

#: How far past ``reach.max_hand_dist`` a landing may be when planning on the
#: measured rope. The spawn check lets a landing sit right at that limit, and
#: 2 mm of settling then puts the same landing just over it with no other
#: landing left (corner c474, 2026-09-11: 0.7796 m at spawn, no move on the
#: settled rope). The runtime limit is for a re-planned move that lands far
#: from where the spawn plan said, not for judging the spawn's own landing again.
RUNTIME_REACH_HEADROOM = 0.02

#: A flip's half circle is executed as this many straight segments (30 deg each).
FLIP_SEGMENTS = 6


def place_beside(
    crossing_xy, grasp_xy, other_xy, stay_strand, *, clearance: float
) -> tuple[float, float]:
    """Today's figure-8 landing (the regression reference): on the circle about
    the crossing through the other end, from ``clearance`` past the other end on
    the far side from the grasp, swept on until ``clearance`` from every segment
    of ``stay_strand`` (the staying strand, other end to crossing).

    Raises ``ValueError`` if no point within ``PLACE_SWEEP_MAX`` clears the strand.
    """

    pivot = np.asarray(crossing_xy, dtype=float)
    other = np.asarray(other_xy, dtype=float)
    radius = float(np.linalg.norm(other - pivot))
    if radius < 1e-9:
        raise ValueError("the other end sits on the crossing; no placement circle.")
    angle = 2.0 * np.arcsin(min(1.0, float(clearance) / (2.0 * radius)))
    grasp = np.asarray(grasp_xy, dtype=float)
    far_sign = max(
        (1.0, -1.0),
        key=lambda s: float(np.linalg.norm(_rotate_about(pivot, other, s * angle) - grasp)),
    )
    stay = np.asarray(stay_strand, dtype=float)[:, :2]
    swept = 0.0
    while swept <= PLACE_SWEEP_MAX:
        candidate = _rotate_about(pivot, other, far_sign * (angle + swept))
        if point_to_polyline(candidate, stay) >= float(clearance) - 1e-9:
            return float(candidate[0]), float(candidate[1])
        swept += PLACE_SWEEP_STEP
    raise ValueError(
        f"no landing point on the circle about the crossing (radius {radius:.3f}) is "
        f"{clearance:.3f} clear of the staying strand within {np.degrees(PLACE_SWEEP_MAX):.0f} deg."
    )


def stay_strand_xy(polyline: np.ndarray, *, other_end: int, stay_at: float) -> np.ndarray:
    """The xy polyline of the strand left on the table: from ``other_end`` along
    the rope to normalized arc ``stay_at``, that vertex included."""

    polyline = np.asarray(polyline, dtype=float)
    segments = np.linalg.norm(np.diff(polyline[:, :2], axis=0), axis=1)
    arc = np.concatenate([[0.0], np.cumsum(segments)])
    arc = arc / max(float(arc[-1]), 1e-12)
    if int(other_end) == 0:
        keep = arc <= float(stay_at) + 1e-9
        keep[min(int(np.searchsorted(arc, float(stay_at))), len(arc) - 1)] = True
    else:
        keep = arc >= float(stay_at) - 1e-9
        keep[max(int(np.searchsorted(arc, float(stay_at), side="right")) - 1, 0)] = True
    return polyline[keep, :2]


def plan_untwist_move(
    rope_scene,
    state,
    polyline: np.ndarray,
    *,
    lift_clearance: float,
    place_clearance: float,
    wrong_end: bool = False,
    moves_done: int = 0,
) -> tuple[BandUntwistMoveCommand, EpisodePlan] | None:
    """The next move on the measured rope, or None when there is nothing to do
    or the model finds no move (the demo then stops and the judge reads the rope).

    ``polyline`` is the settled centreline in the world frame; the model works in
    the task frame (the arm base and the hand heights are task-frame numbers).
    ``moves_done`` is how many moves this episode has made: a second move is
    planned under the two-move rules even though one crossing is left.
    """

    if state.crossing_count == 0:
        return None
    layout = rope_scene.layout
    origin = np.asarray(layout.task_origin, dtype=float)
    task_poly = np.asarray(polyline, dtype=float) - origin[None, :]
    rope = sequence.Rope.from_points(task_poly)
    radius = float(layout.cfg.rope.radius)
    ws = layout.cfg.workspace
    params = replace(
        layout.model_params(),
        lift_clearance=float(lift_clearance),
        place_clearance=float(place_clearance),
        scene_top=float(task_poly[:, 2].max()) + radius,
        landing_box=((float(ws.x[0]), float(ws.x[1])), (float(ws.y[0]), float(ws.y[1]))),
        max_reach=float(layout.cfg.reach.max_hand_dist) + RUNTIME_REACH_HEADROOM,
    )
    plan = sequence.plan(rope, params, moves_done=moves_done)
    if plan is None or not plan.moves:
        return None
    move = plan.moves[0]
    predicted = plan.predicted[0]
    if wrong_end:
        found = sequence.crossings(rope, merge_radius=params.merge_radius)
        landed = sequence.wrong_end_move(rope, found, move.lift.pivot, params)
        if landed is None:
            return None
        move, after = landed
        predicted = sequence.crossing_sequence(sequence.crossings(after, merge_radius=params.merge_radius))
    found = sequence.crossings(rope, merge_radius=params.merge_radius)
    pivot_xy_task = np.asarray(found[move.lift.pivot].xy if move.lift.pivot >= 0 else move.lift_xy, dtype=float)

    end = int(move.end)
    grasp_xy = rope_scene.connector_xy(end)  # the plug as measured, not the rope's last vertex
    place_xy = (float(move.place_xy[0] + origin[0]), float(move.place_xy[1] + origin[1]))
    table_z = float(layout.world_z(0.0))
    lift_z = table_z + float(move.hand_height)
    place_z = table_z + radius
    crossing_arc = float(move.lift.arc(rope)) - float(lift_clearance)
    carry_z = cross_z = lift_z
    axis3 = (0.0, 0.0, 0.0)
    if move.kind == "flip":
        # The hand travels a half circle in the vertical plane through the
        # plug, perpendicular to the flip axis (the rope's tangent at the
        # pivot), centred on the axis: the plug rises over the axis and comes
        # down at its mirror image. FLIP_STEP_DEG per segment.
        d = np.asarray(move.axis, dtype=float)
        g = np.asarray(grasp_xy, dtype=float) - origin[:2]
        rel = g - np.asarray(move.lift_xy, dtype=float)
        centre = np.asarray(move.lift_xy, dtype=float) + (rel @ d) * d
        n = g - centre
        rho = float(np.linalg.norm(n))
        n = n / max(rho, 1e-12)
        if d[0] * n[1] - d[1] * n[0] < 0.0:  # turn the axis so the plug goes UP over it
            d = -d
        axis3 = (float(d[0]), float(d[1]), 0.0)
        path = []
        for k in range(1, FLIP_SEGMENTS + 1):
            theta = math.pi * k / FLIP_SEGMENTS
            xy = centre + rho * math.cos(theta) * n
            label = "place_down" if k == FLIP_SEGMENTS else f"flip_{int(round(math.degrees(theta)))}"
            path.append((label, (float(xy[0] + origin[0]), float(xy[1] + origin[1]), float(place_z + rho * math.sin(theta)))))
        carry = path[0][1]
        cross = path[-2][1]
        settle = path[-1][1]
        lift_z = place_z + rho
    else:
        # The carry is at the full lift height (the whole lifted rope hangs, so
        # the lifted crossing is off the table -- every GPU success ran this
        # way); the cross-over is lowered only for a LOOSE finishing lay (slack
        # <= slack_max_single: the one-move shapes and the lay that finishes a
        # flip plan), where the full height over-stretches the rope (seed 11).
        # A taut lay (O|-|O's two moves) keeps the full height it was validated at.
        if not wrong_end and float(move.margins.get("slack", 1.0)) <= params.slack_max_single + 1e-9:
            arc = float(move.lift.arc(rope))
            chord = float(np.hypot(move.place_xy[0] - move.lift_xy[0], move.place_xy[1] - move.lift_xy[1]))
            h_taut = float(np.sqrt(max((CROSS_TAUT * arc) ** 2 - chord**2, 0.0)))
            h_ride = CROSS_RIDE_MIN * CROSS_TAUT * arc / float(lift_clearance)
            cross_z = table_z + min(float(move.hand_height), max(h_taut, h_ride))
        carry = (float(grasp_xy[0]), float(grasp_xy[1]), float(carry_z))
        cross = (place_xy[0], place_xy[1], float(cross_z))
        settle = (place_xy[0], place_xy[1], float(place_z))
        path = [("carry_up", carry), ("cross_over", cross), ("place_down", settle)]
    crossing_xy = (float(pivot_xy_task[0] + origin[0]), float(pivot_xy_task[1] + origin[1]))
    command = BandUntwistMoveCommand(
        end=end,
        other_end=1 - end,
        grasped_over_end=not wrong_end,
        grasp_xy=grasp_xy,
        place_xy=place_xy,
        crossing_xy=crossing_xy,
        crossing_z_gap=0.0,
        lift_z=float(lift_z),
        crossing_arc=crossing_arc,
        carry=tuple(float(v) for v in carry),
        cross=tuple(float(v) for v in cross),
        settle=tuple(float(v) for v in settle),
        crossing_count_before=int(state.crossing_count),
        planned_moves=len(plan.moves),
        predicted_sequence=tuple(predicted),
        swing_deg=float(move.margins["rotation_deg"]),
        slack=float(move.margins.get("slack", float("nan"))),
        lay_down_clearance=float(move.margins["lay_down_clearance"]),
        bend=float(move.margins["bend"]),
        room=float(move.margins["room"]),
        kind=str(move.kind),
        path=tuple((label, tuple(float(v) for v in xyz)) for label, xyz in path),
        axis=axis3,
        flip_radius=float(move.margins.get("flip_radius", 0.0)),
    )
    subgoal = PlannedSubgoal(
        subgoal_id=f"untwist_end{end}",
        kind="lift_end_across_own_strand",
        entity=layout.strand_name(0),
        target={
            "end": end,
            "grasped_over_end": not wrong_end,
            "grasp_xy": list(grasp_xy),
            "place_xy": list(place_xy),
            "crossing_xy": list(crossing_xy),
            "crossing_arc": crossing_arc,
        },
    )
    if move.kind == "flip":
        targets = tuple(WaypointTarget(label=label, position=xyz, metadata={}) for label, xyz in command.path)
    else:
        targets = (
            WaypointTarget(
                label="carry",
                position=command.carry,
                metadata={"clearance_above_scene": float(lift_clearance), "crossing_arc": crossing_arc},
            ),
            WaypointTarget(label="cross", position=command.cross, metadata={}),
            WaypointTarget(label="place", position=command.settle, metadata={"place_clearance": float(place_clearance)}),
        )
    waypoint_plan = WaypointPlan(
        plan_id="band_untwist_move",
        waypoints=(WaypointTarget(label="grasp", position=(grasp_xy[0], grasp_xy[1], place_z), metadata={"end": end}), *targets),
        metadata={"planner": "band_untwist_move", "kind": str(move.kind)},
    )
    episode_plan = EpisodePlan(
        task_id="band_untwist",
        subgoals=(subgoal,),
        waypoint_plan=waypoint_plan,
        plan_id="band_untwist_move",
        metadata={
            "end": end,
            "grasped_over_end": not wrong_end,
            "crossing_arc": crossing_arc,
            "lift_above_table": float(lift_z - table_z),
            "planned_moves": len(plan.moves),
        },
    )
    return command, episode_plan


@dataclass(frozen=True)
class BandUntwistRule:
    """``grasp="over"`` is the oracle, ``"under"`` the wrong_end contrast; same
    motion, same lift rule, same landing rule, only the plug differs.
    ``budget_cap`` limits the episode's moves (``one_move``: 1)."""

    grasp: str = "over"
    budget_cap: int | None = None

    def decide(self, rope_scene, state, polyline, *, pinch_cfg, moves_done: int = 0):
        return plan_untwist_move(
            rope_scene,
            state,
            polyline,
            lift_clearance=float(pinch_cfg.lift_clearance),
            place_clearance=float(pinch_cfg.place_clearance),
            wrong_end=self.grasp == "under",
            moves_done=moves_done,
        )


_MODES = {
    "oracle": BandUntwistRule(grasp="over"),
    "wrong_end": BandUntwistRule(grasp="under"),
    "one_move": BandUntwistRule(grasp="over", budget_cap=1),
}


def make_band_untwist_rule(mode: str) -> BandUntwistRule:
    """`run.oracle_mode` -> rule."""

    try:
        return _MODES[str(mode)]
    except KeyError:
        raise ValueError(
            f"unknown oracle_mode {mode!r}; expected one of {sorted(_MODES)}"
        ) from None
