from __future__ import annotations

import math
from dataclasses import dataclass

import numpy as np

from .subgoal import PlannedSubgoal
from .waypoint import EpisodePlan, WaypointPlan, WaypointTarget


@dataclass(frozen=True)
class UntangleContinuousMoveCommand:
    """One grasp-lift-place that should remove one top-down crossing."""

    strand_index: int
    under_strand: int
    # Centreline gap at the chosen crossing. Small means the two ropes overlap
    # rather than rest on each other, so "grasp the one on top" is not visually
    # true and the lift has to pull the rope out of the other one.
    crossing_z_gap: float
    grasp_arclength: float  # normalized 0..1 along the grasped strand
    grasp_xy: tuple[float, float]
    place_xy: tuple[float, float]
    lift_z: float
    tail_arc: float  # rope length hanging past the grasp, toward the free end
    # Rope arc from the crossing to the free end -- the part that hangs below the
    # hand and decides how high the lift has to be.
    crossing_arc: float
    # The three hand targets, already clamped to what the rope can actually reach.
    # The planner hands these over rather than the demo rebuilding them from
    # grasp_xy/place_xy/lift_z, because the clamp can move any of them.
    carry: tuple[float, float, float]
    cross: tuple[float, float, float]
    settle: tuple[float, float, float]
    crossing_count_before: int


def _home_lane_y(rope_scene, strand_index: int) -> float:
    """The y lane this strand leaves the power strip in.

    The anchored end pins every strand to a distinct lane, so "put it back in its
    own lane" is always a well-defined, collision-free target: lanes are
    ``channel_spacing`` apart, far wider than the success separation threshold.
    """

    layout = rope_scene.layout.braid_layout()
    offset = 0.5 * (rope_scene.layout.n_strands - 1)
    y = layout.center_y + (int(strand_index) - offset) * layout.channel_spacing
    return float(rope_scene.layout.position_to_world([0.0, y, 0.0])[1])


def _arclength_at_xy(polyline: np.ndarray, xy) -> float:
    """Normalized arc length of the polyline vertex nearest ``xy`` (top-down)."""

    distance = np.linalg.norm(polyline[:, :2] - np.asarray(xy, dtype=float), axis=1)
    return float(int(np.argmin(distance)) / max(1, len(polyline) - 1))


def plan_next_untangle_continuous_move(
    rope_scene,
    state,
    polylines: dict[int, np.ndarray],
    *,
    lift_clearance: float,
    grasp_offset: float,
    place_pullback: float,
    tail_clearance: float,
    max_taut_ratio: float,
    lane_overshoot: float = 0.0,
    grasp_strand: int | None = None,
) -> tuple[UntangleContinuousMoveCommand, EpisodePlan] | None:
    """Pick the next crossing to undo, or None when the state is already terminal.

    **On "reverse the braid word"**: the design doc frames the oracle as applying
    the inverse word. Worked through, that does not survive contact with the
    geometry -- undoing one letter needs *both* involved strands to swap lanes
    back, i.e. two grasps per crossing, which would put the oracle at 2x the
    braid length rather than the promised lower bound. So the word is used for
    what it is actually good for -- the *order* -- and the target comes from the
    geometry instead:

    - order: undo the crossing nearest the free end first. That end is
      unconstrained, so moving it disturbs nothing already sorted. It is the same
      ordering the inverse word prescribes.
    - target: put the over-strand back in its own lane. Every strand has a
      distinct lane at the anchored end, so once each strand lies in its own lane
      the state is untangled *and* separated by construction.

    Closed-loop on the measured crossings rather than open-loop on the word, so a
    move that the physics resolves differently than expected is simply re-planned.
    """

    if state.is_terminal or not state.crossings:
        return None

    # Order: nearest the free end first (largest x). Ties broken by strand index
    # so the same state always yields the same choice -- an oracle that grasps a
    # different rope on otherwise identical runs is not reproducible, and makes
    # "was the grasped one really on top?" impossible to check by eye.
    crossing = max(
        state.crossings,
        key=lambda c: (round(c.position[0], 6), -int(c.over_strand)),
    )
    over = int(crossing.over_strand)

    # `grasp_strand` overrides that choice, including to the strand that is
    # *underneath*. That is not a solving move -- dragging the lower rope cannot
    # undo the crossing -- it is a contact test: the rope being pulled must not
    # pass through the one lying on top of it, no matter how far it is dragged.
    # The destination is still "its own lane", which is well defined for either
    # strand, so the rest of the plan needs no special case.
    if grasp_strand is not None:
        over = int(grasp_strand)
        candidates = [
            c for c in state.crossings
            if over in (int(c.over_strand), int(c.under_strand))
        ]
        if not candidates:
            return None
        crossing = max(candidates, key=lambda c: round(c.position[0], 6))

    polyline = polylines[over]

    # Grasp the rope's free END, via the rigid fitting welded there -- not a band
    # of rope somewhere in the middle.
    #
    # Two reasons, and the second is the one that forced the change. Undoing the
    # crossing nearest the free end only requires moving the rope *past* that
    # crossing, and the end is the natural place to take hold of it -- it is what
    # a person reaches for. And grasping the end leaves **no tail hanging past
    # the grip**: no dangling length to drag through the strand underneath, and
    # no hairpin at the grip where the rope has to double back. Those were two
    # separate problems that turned out to be one, and both disappear here.
    grasp_s = 1.0
    grasp_index = len(polyline) - 1
    grasp_xy = (float(polyline[grasp_index, 0]), float(polyline[grasp_index, 1]))

    # Lift height is set by whichever hangs lowest: the grasp point itself, or the
    # far end of the rope dangling below it.
    #
    # The rope does not end at the grasp point -- everything from there to the free
    # end hangs down, and whatever is still low enough to touch gets dragged
    # sideways through it during the lateral move.
    #
    # **Both clearances are measured from the top of the OTHER ropes, not from the
    # table.** The obstacle is never the table; it is the strands lying on it. An
    # earlier version measured the tail from the table, which put the tail tip at
    # 10 mm while the other ropes' crossings reach 27 mm -- so the tail swept 17 mm
    # deep through them on every single move, shoving the strand underneath
    # sideways. The grasped strand is excluded from the obstacle height: there is
    # no need to clear oneself.
    # Zero by construction now that the grip is at the end; kept in the command so
    # the log still shows it and a future mid-rope grasp would report honestly.
    segments = np.linalg.norm(np.diff(polyline, axis=0), axis=1)
    tail_arc = float(segments[grasp_index:].sum())
    rope_radius = float(rope_scene.layout.cfg.rope.radius)
    others = [p for index, p in polylines.items() if index != over]
    obstacle_top = (
        max(float(p[:, 2].max()) for p in others) + rope_radius
        if others
        else float(rope_scene.layout.world_z(0.0))
    )
    #
    # The arc from the *crossing* back to the free end is the one that decides the
    # lift, and leaving it out is what made the carried end plough straight
    # through the other rope. Clearing the grasp point put the hand 63 mm up while
    # the crossing -- 120-156 mm of rope further back -- never left the table, so
    # the lateral move dragged it sideways through the strand underneath. Hanging
    # roughly straight down from the hand, raising the crossing to `clearance`
    # above the obstacles needs the hand at `crossing_arc + clearance`.
    crossing_index = int(np.argmin(np.linalg.norm(polyline[:, :2] - np.asarray(crossing.position, dtype=float), axis=1)))
    crossing_arc = float(segments[crossing_index:].sum())
    lift_z = obstacle_top + max(
        float(lift_clearance),
        crossing_arc + float(lift_clearance),
        tail_arc + float(tail_clearance),
    )

    # Lay the rope out along its own lane, near full extension.
    #
    # This is what actually undoes the crossing, and it took a while to see why
    # lift-and-put-down did not. Lifting the *grasp point* clear of the other
    # ropes does nothing for the crossing itself, which sits 135-156 mm of arc
    # back from the free end and stays pressed against the strand below the whole
    # time -- so the rope came back down in the same over/under relationship it
    # started in. Lifting high enough to raise the crossing would need ~220 mm,
    # and the rope cannot reach that far from its anchor without being pulled
    # past breaking.
    #
    # Extension does it instead, using the rope's own length as the constraint: a
    # 445 mm rope whose ends are 400 mm apart *in one lane* has nowhere to put a
    # detour into another lane. It is also the natural motion -- you pull a cable
    # straight, you do not lift it out.
    #
    # `place_pullback` is therefore small (tens of mm), only enough to keep the
    # rope off dead-straight. It used to be 120 mm, tuned back when the grasp was
    # mid-rope; at the free end that leaves 140 mm of slack in a 305 mm span, and
    # the rope simply meanders back across.
    # Aim past the lane centre, not at it.
    #
    # The hand reaching the lane centre does not put the *rope* in the lane. The
    # crossing sits 120-156 mm of arc behind the free end, so it trails the hand
    # through the whole lateral traverse and arrives short; measured in the
    # viewer, the moved strand still overlapped the one it was meant to clear
    # when it was put down. Overshooting away from the strand underneath carries
    # the trailing section across the lane boundary as well, and the rope relaxes
    # back toward the lane on release.
    #
    # Cheap in reach terms: the anchor shares this lane, so a y offset is almost
    # perpendicular to the anchor->target direction. 40 mm of overshoot over a
    # 400 mm span costs 2 mm of extension, well inside what `within_reach` allows.
    lane_y = _home_lane_y(rope_scene, over)
    # Whichever of the crossing's two strands is not the one being moved. Named
    # this way rather than `crossing.under_strand` because `grasp_strand` can
    # make the moved strand the lower one.
    other = (
        int(crossing.under_strand)
        if int(crossing.under_strand) != over
        else int(crossing.over_strand)
    )
    away = 1.0 if lane_y >= _home_lane_y(rope_scene, other) else -1.0
    place_xy = (
        float(rope_scene.layout.braid_layout().x_end) - float(place_pullback),
        lane_y + away * float(lane_overshoot),
    )

    # Nothing the hand is told to do may ask the rope to be longer than it is.
    #
    # The rope is 525 mm of arc with its ends 433 mm apart, so it starts out 82%
    # extended and there are only ~92 mm of slack to spend. A 219 mm lift at the
    # free end's own x needs 101% of the rope on the shortest braid -- it would be
    # torn, not lifted. Pulling the hand back toward the anchor buys the height
    # back, so every waypoint gets clamped along the anchor->target direction
    # until it is reachable. The clamp only ever pulls *in*; it never pushes a
    # target further out than asked.
    anchor = np.asarray(polyline[0], dtype=float)
    rope_arc = float(segments.sum())

    def within_reach(target):
        target = np.asarray(target, dtype=float)
        offset = target - anchor
        limit = float(max_taut_ratio) * rope_arc
        planar = float(np.linalg.norm(offset[:2]))
        if float(np.linalg.norm(offset)) <= limit or planar < 1e-9:
            return target
        keep = math.sqrt(max(limit * limit - float(offset[2]) ** 2, 0.0))
        return np.array(
            [anchor[0] + offset[0] / planar * keep, anchor[1] + offset[1] / planar * keep, target[2]],
            dtype=float,
        )

    carry = within_reach((grasp_xy[0], grasp_xy[1], lift_z))
    cross = within_reach((carry[0], place_xy[1], lift_z))
    settle = within_reach((place_xy[0], place_xy[1], float(rope_scene.layout.world_z(0.0)) + rope_radius))

    command = UntangleContinuousMoveCommand(
        strand_index=over,
        # `other`, not `crossing.under_strand`: with `grasp_strand` the moved
        # strand can be the lower one, and then those two are the same strand,
        # which reads as "s1 over s1" in the log.
        under_strand=other,
        grasp_arclength=grasp_s,
        grasp_xy=grasp_xy,
        place_xy=place_xy,
        crossing_z_gap=float(crossing.z_gap),
        lift_z=lift_z,
        tail_arc=tail_arc,
        crossing_arc=crossing_arc,
        carry=(float(carry[0]), float(carry[1]), float(carry[2])),
        cross=(float(cross[0]), float(cross[1]), float(cross[2])),
        settle=(float(settle[0]), float(settle[1]), float(settle[2])),
        crossing_count_before=int(state.crossing_count),
    )
    subgoal = PlannedSubgoal(
        subgoal_id=f"undo_crossing_s{over}_over_s{other}",
        kind="lift_strand_to_home_lane",
        entity=rope_scene.layout.strand_name(over),
        target={
            "strand_index": over,
            "under_strand": other,
            "grasp_xy": list(grasp_xy),
            "place_xy": list(place_xy),
            "crossing_count_before": int(state.crossing_count),
        },
    )
    waypoint_plan = WaypointPlan(
        plan_id="untangle_continuous_lift_move_place",
        waypoints=(
            WaypointTarget(
                label="grasp",
                position=(grasp_xy[0], grasp_xy[1], float(polyline[grasp_index, 2])),
                metadata={"strand": over, "arclength": grasp_s},
            ),
            WaypointTarget(
                label="carry",
                position=(float(carry[0]), float(carry[1]), float(carry[2])),
                metadata={
                    "clearance_above_scene": float(lift_clearance),
                    "crossing_arc": crossing_arc,
                    "pulled_back": float(grasp_xy[0] - carry[0]),
                },
            ),
            WaypointTarget(
                label="cross",
                position=(float(cross[0]), float(cross[1]), float(cross[2])),
                metadata={"home_lane_y": place_xy[1]},
            ),
            WaypointTarget(
                label="place",
                position=(float(settle[0]), float(settle[1]), float(settle[2])),
                metadata={"home_lane_y": place_xy[1]},
            ),
        ),
        metadata={"planner": "untangle_continuous_greedy_free_end_first"},
    )
    episode_plan = EpisodePlan(
        task_id="untangle_continuous",
        subgoals=(subgoal,),
        waypoint_plan=waypoint_plan,
        plan_id="untangle_continuous_greedy_free_end_first",
        metadata={
            "strand_index": over,
            "under_strand": other,
            "crossing_count_before": int(state.crossing_count),
        },
    )
    return command, episode_plan
