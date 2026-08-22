"""Two-move oracle for `swap_crossing_sign` (docx 3.2).

The task's whole content is *which rope ends up on top*, and with one arm that is
decided by one thing: the rope placed last is the rope on top. So the sequence is
forced, not chosen:

    1. separate   take the upper rope off, so the stack is genuinely undone
                  (crossing count 1 -> 0, ropes measured apart)
    2. cover      lay the other rope across it -- placed last, therefore on top

Move 1 is not a new motion. It is exactly what the untangle oracle already does
with the same scene, so it is delegated to `plan_next_untangle_continuous_move`
rather than reimplemented. Only move 2 is new here, and it differs from move 1 in
one respect: move 1 aims the rope *into its own lane*, away from the other rope,
while move 2 aims it *past* the other rope's free end, so the two must cross.

There is a standing rule behind this shape: **every grasp is on a rope with
nothing lying on top of it.** Move 1 grasps the upper rope; move 2 grasps a rope
that has just been freed. Pulling the lower rope out from under the upper one
would reach the same end state in a single move, but it asks the solver to slide
one rope out from beneath another and makes "did it pass through" the thing the
episode hinges on. See the task module's docstring.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

import numpy as np

from .subgoal import PlannedSubgoal
from .untangle_continuous_planner import (
    UntangleContinuousMoveCommand,
    plan_next_untangle_continuous_move,
)
from .waypoint import EpisodePlan, WaypointPlan, WaypointTarget


def _free_end_xy(rope_scene, polyline: np.ndarray, strand_index: int) -> tuple[float, float]:
    """Free-end position, from the rigid fitting when there is one.

    Same reasoning as the untangle planner: the centerline's last bin is a
    particle centroid and inherits whatever the tail did while settling, which
    was measured drifting ~9.5 mm on the FEM backend. The welded fitting's pose
    is exact on both backends.
    """

    connector = getattr(rope_scene, "free_end_connectors", {}).get(strand_index)
    if connector is None:
        return float(polyline[-1, 0]), float(polyline[-1, 1])
    raw = connector.get_pos()
    if hasattr(raw, "detach"):
        raw = raw.detach().cpu().numpy()
    position = np.asarray(raw, dtype=float).reshape(-1)
    return float(position[0]), float(position[1])


def _chord_crossing_fraction(start_xy, end_xy, obstacle: np.ndarray) -> float | None:
    """Where along `start -> end` that straight chord first meets `obstacle`.

    Returned as a fraction in 0..1, or None when the planned path does not cross
    the other rope at all -- which means the placement would not build a crossing
    and the caller should say so rather than run the move.

    This is a *prediction*, made before the rope has moved, and it is what sets
    the lift height: the rope has to be carried high enough that the point which
    will become the crossing clears the rope underneath, and that point is a good
    150 mm of arc back from the hand.
    """

    p0 = np.asarray(start_xy, dtype=float)
    p1 = np.asarray(end_xy, dtype=float)
    d = p1 - p0
    best: float | None = None
    for index in range(len(obstacle) - 1):
        q0 = obstacle[index, :2]
        q1 = obstacle[index + 1, :2]
        e = q1 - q0
        denominator = d[0] * e[1] - d[1] * e[0]
        if abs(denominator) < 1e-12:
            continue
        diff = q0 - p0
        t = (diff[0] * e[1] - diff[1] * e[0]) / denominator
        u = (diff[0] * d[1] - diff[1] * d[0]) / denominator
        if 0.0 <= t <= 1.0 and 0.0 <= u <= 1.0:
            best = t if best is None else min(best, t)
    return best


def _distance_to_polyline(point_xy, polyline: np.ndarray) -> float:
    """Closest top-down distance from a point to a rope's centerline."""

    p = np.asarray(point_xy, dtype=float)
    a = polyline[:-1, :2]
    b = polyline[1:, :2]
    ab = b - a
    length_sq = np.einsum("ij,ij->i", ab, ab)
    length_sq = np.where(length_sq < 1e-18, 1e-18, length_sq)
    t = np.clip(np.einsum("ij,ij->i", p[None, :] - a, ab) / length_sq, 0.0, 1.0)
    closest = a + t[:, None] * ab
    return float(np.linalg.norm(closest - p[None, :], axis=1).min())


def plan_cover_move(
    rope_scene,
    state,
    polylines: dict[int, np.ndarray],
    *,
    moved: int,
    covered: int,
    lift_clearance: float,
    place_pullback: float,
    tail_clearance: float,
    max_taut_ratio: float,
    cover_overshoot: float,
    place_clearance: float = 0.0,
) -> tuple[UntangleContinuousMoveCommand, EpisodePlan] | None:
    """Lay `moved` across `covered`, landing past its free end.

    Refuses (returns None) unless the scene is currently separated. Covering a
    rope that is still stacked would not flip anything -- it would just re-seat
    the same relationship -- and running it anyway would make the episode's log
    claim a move that could not have done what it says.
    """

    if state.crossing_count != 0 or not state.is_separated:
        return None

    polyline = polylines[moved]
    obstacle = polylines[covered]
    grasp_xy = _free_end_xy(rope_scene, polyline, moved)
    covered_xy = _free_end_xy(rope_scene, obstacle, covered)

    anchor = np.asarray(polyline[0], dtype=float)
    segments = np.linalg.norm(np.diff(polyline, axis=0), axis=1)
    rope_arc = float(segments.sum())
    rope_radius = float(rope_scene.layout.cfg.rope.radius)

    # Aim past the other rope's free end, on the side away from this rope's own
    # anchor lane. Landing short of it would leave the two side by side with no
    # crossing at all; the overshoot is what guarantees the paths must meet.
    side = 1.0 if covered_xy[1] >= float(anchor[1]) else -1.0
    place_x = float(rope_scene.layout.braid_layout().x_end) - float(place_pullback)

    def aim(overshoot: float) -> tuple[float, float]:
        return (place_x, covered_xy[1] + side * float(overshoot))

    # Same clamp as the untangle move, and it bites harder here: with
    # `braid.length: 1` the rope leaves the spawn already ~99% extended
    # (measured arc 0.4376 m against a 0.4334 m chord), so a target aimed past
    # the other rope's free end is always further than the rope can reach. The
    # clamp keeps the bearing and pulls the hand in along it, which is what buys
    # the height back.
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

    # The place target is clamped *first*, and the crossing is predicted against
    # the clamped one. Predicting against the raw target would describe a rope
    # longer than this rope: the aim point is past what it can reach, so the
    # contact would sit at a different arclength than the one the lift height is
    # then computed from -- an error in the safe direction, but an error.
    place_z = float(rope_scene.layout.world_z(0.0)) + rope_radius

    # Aiming past the other rope's *free end* is not the same as landing clear of
    # its *body*, and the clamp is what pulls them apart: it drags the placement
    # back along the anchor->target ray, and back is where the other rope's tail
    # still is. Measured on the first run, the hand came down alongside that tail
    # and the fingers knocked it aside.
    #
    # So the overshoot is searched rather than fixed: widen the aim until the
    # clamped landing point is `place_clearance` clear of the other rope's
    # centerline, and keep the first one that is. Widening costs lift -- a wider
    # aim makes the two paths meet earlier, which leaves more rope hanging below
    # the hand -- so this takes the *smallest* overshoot that clears, not the
    # largest.
    place_xy = aim(cover_overshoot)
    settle = within_reach((place_xy[0], place_xy[1], place_z))
    achieved_clearance = _distance_to_polyline(settle[:2], obstacle)
    if place_clearance > 0.0 and achieved_clearance < float(place_clearance):
        step = 0.01
        for extra in np.arange(step, float(cover_overshoot) + 0.16 + step, step):
            candidate_xy = aim(float(cover_overshoot) + float(extra))
            candidate = within_reach((candidate_xy[0], candidate_xy[1], place_z))
            candidate_clearance = _distance_to_polyline(candidate[:2], obstacle)
            if candidate_clearance > achieved_clearance:
                place_xy, settle, achieved_clearance = (
                    candidate_xy,
                    candidate,
                    candidate_clearance,
                )
            if achieved_clearance >= float(place_clearance):
                break

    crossing_fraction = _chord_crossing_fraction(anchor[:2], settle[:2], obstacle)
    if crossing_fraction is None:
        # The clamp pulled the placement back to the near side of the other rope,
        # so this move would put the two side by side instead of across each
        # other. Raising `cover_overshoot` does not fix it -- the clamp scales the
        # aim point along the same bearing, so a further target lands on the same
        # ray. The rope is simply too short to reach past the other one from where
        # it is anchored.
        return None
    # Arc from the predicted crossing back to the hand. That length hangs below
    # the hand during the traverse, so it -- not the grasp point -- is what sets
    # how high the rope has to be carried.
    cover_arc = float(1.0 - crossing_fraction) * rope_arc

    # Grasping the free end leaves nothing past the grip; kept so the command
    # reports it honestly and a future mid-rope grasp would too.
    tail_arc = 0.0
    obstacle_top = float(obstacle[:, 2].max()) + rope_radius
    lift_z = obstacle_top + max(
        float(lift_clearance),
        cover_arc + float(lift_clearance),
        tail_arc + float(tail_clearance),
    )

    carry = within_reach((grasp_xy[0], grasp_xy[1], lift_z))
    cross = within_reach((carry[0], settle[1], lift_z))

    command = UntangleContinuousMoveCommand(
        strand_index=moved,
        under_strand=covered,
        grasp_arclength=1.0,
        grasp_xy=grasp_xy,
        place_xy=place_xy,
        # No crossing exists yet -- that is the precondition checked above.
        crossing_z_gap=0.0,
        lift_z=lift_z,
        tail_arc=tail_arc,
        crossing_arc=cover_arc,
        carry=(float(carry[0]), float(carry[1]), float(carry[2])),
        cross=(float(cross[0]), float(cross[1]), float(cross[2])),
        settle=(float(settle[0]), float(settle[1]), float(settle[2])),
        crossing_count_before=int(state.crossing_count),
    )
    subgoal = PlannedSubgoal(
        subgoal_id=f"cover_s{covered}_with_s{moved}",
        kind="lay_strand_across_strand",
        entity=rope_scene.layout.strand_name(moved),
        target={
            "strand_index": moved,
            "covered_strand": covered,
            "grasp_xy": list(grasp_xy),
            "place_xy": list(place_xy),
            "predicted_crossing_fraction": float(crossing_fraction),
            "place_clearance": float(achieved_clearance),
        },
    )
    waypoint_plan = WaypointPlan(
        plan_id="swap_crossing_sign_cover",
        waypoints=(
            WaypointTarget(
                label="grasp",
                position=(grasp_xy[0], grasp_xy[1], float(polyline[-1, 2])),
                metadata={"strand": moved, "arclength": 1.0},
            ),
            WaypointTarget(
                label="carry",
                position=(float(carry[0]), float(carry[1]), float(carry[2])),
                metadata={
                    "clearance_above_scene": float(lift_clearance),
                    "cover_arc": cover_arc,
                    "pulled_back": float(grasp_xy[0] - carry[0]),
                },
            ),
            WaypointTarget(
                label="cross",
                position=(float(cross[0]), float(cross[1]), float(cross[2])),
                metadata={"place_y": place_xy[1]},
            ),
            WaypointTarget(
                label="place",
                position=(float(settle[0]), float(settle[1]), float(settle[2])),
                metadata={"place_y": place_xy[1]},
            ),
        ),
        metadata={"planner": "swap_crossing_sign_cover"},
    )
    episode_plan = EpisodePlan(
        task_id="swap_crossing_sign",
        subgoals=(subgoal,),
        waypoint_plan=waypoint_plan,
        plan_id="swap_crossing_sign_cover",
        metadata={
            "strand_index": moved,
            "covered_strand": covered,
            "predicted_crossing_fraction": float(crossing_fraction),
            # How far the hand comes down from the other rope's centerline. The
            # thing this has to beat is the gripper's own footprint, not the
            # rope's radius -- it is the fingers that hit it.
            "place_clearance": float(achieved_clearance),
            "place_clearance_target": float(place_clearance),
        },
    )
    return command, episode_plan


@dataclass(frozen=True)
class SwapCrossingSignRule:
    """separate, then cover -- with `cover_with` deciding *which* rope covers.

    The two modes are the task's contrast pair, and they differ by one field on
    purpose: same two moves, same motions, same number of grasps, near enough the
    same end layout. The only thing that differs is which rope goes back on top,
    which is precisely the quantity the task grades. That makes the baseline a
    measurement rather than an assertion -- `restack_same` is expected to run to
    completion and be judged a failure.

        other   lay the *other* rope on top      -> sign flips, success
        same    put the same rope back on top    -> sign unchanged, failure
    """

    cover_with: str = "other"

    def decide(
        self,
        rope_scene,
        state,
        polylines: dict[int, np.ndarray],
        *,
        pinch_cfg,
        separated_strand: int | None,
    ) -> tuple[UntangleContinuousMoveCommand, EpisodePlan] | None:
        if separated_strand is None:
            # Move 1. The untangle oracle picks the strand the detector measured
            # on top, which is the one that can be taken off without dragging it
            # out from under anything.
            return plan_next_untangle_continuous_move(
                rope_scene,
                state,
                polylines,
                lift_clearance=float(pinch_cfg.lift_clearance),
                grasp_offset=float(pinch_cfg.grasp_offset),
                place_pullback=float(pinch_cfg.place_pullback),
                tail_clearance=float(pinch_cfg.tail_clearance),
                max_taut_ratio=float(pinch_cfg.max_taut_ratio),
                lane_overshoot=float(pinch_cfg.lane_overshoot),
            )

        if self.cover_with == "same":
            moved = int(separated_strand)
        else:
            others = [index for index in sorted(polylines) if index != int(separated_strand)]
            if not others:
                return None
            moved = others[0]
        covered = next(
            (index for index in sorted(polylines) if index != moved),
            None,
        )
        if covered is None:
            return None

        return plan_cover_move(
            rope_scene,
            state,
            polylines,
            moved=moved,
            covered=covered,
            lift_clearance=float(pinch_cfg.lift_clearance),
            place_pullback=float(pinch_cfg.place_pullback),
            tail_clearance=float(pinch_cfg.tail_clearance),
            max_taut_ratio=float(pinch_cfg.max_taut_ratio),
            cover_overshoot=float(pinch_cfg.cover_overshoot),
            place_clearance=float(pinch_cfg.place_clearance),
        )


_MODES = {
    "oracle": SwapCrossingSignRule(cover_with="other"),
    "restack_same": SwapCrossingSignRule(cover_with="same"),
}


def make_swap_crossing_sign_rule(mode: str) -> SwapCrossingSignRule:
    """`run.oracle_mode` -> rule."""

    try:
        return _MODES[str(mode)]
    except KeyError:
        raise ValueError(
            f"unknown oracle_mode {mode!r}; expected one of {sorted(_MODES)}"
        ) from None
