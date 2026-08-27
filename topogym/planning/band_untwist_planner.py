"""One-move oracle for `band_untwist` (docx 3.3).

The rope lies in a figure-8 with one self-crossing. Whichever strand is on top
at that crossing can be lifted off the other without dragging anything out from
underneath -- the standing rule every entangle oracle in this repo follows. So:

    grasp the end whose strand is ON TOP at the crossing,
    lift that whole strand clear (crossing included),
    carry it across the other strand,
    lay it down beside the other end.

Self-crossing count 1 -> 0. The contrast pair is the same move on the OTHER end
(the under strand): carried across, it lands a second crossing on top of the one
it was underneath, 1 -> 2 -- the docx's "flipped from the wrong side".

Two things differ from the two-rope planners:

- **Which end** is decided from the measured crossing (`SelfCrossing.over_end`),
  never from the generator's intent. What the detector grades is what the
  oracle acts on.
- **No reach clamp.** Nothing is anchored; the rope's fixed point during the
  move is the crossing itself (the under strand stays put under friction). The
  placement is put on the circle about the crossing that passes through the
  other end, so the carried strand ends the move exactly as extended as it
  started -- neither taut nor slack -- and no clamp is needed.

Pure numpy; no Genesis, so `tests/check_band_untwist_geometry.py` exercises it
on synthetic polylines.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from .subgoal import PlannedSubgoal
from .waypoint import EpisodePlan, WaypointPlan, WaypointTarget


@dataclass(frozen=True)
class BandUntwistMoveCommand:
    """One grasp-lift-carry-place on one rope end."""

    end: int  # rope end grasped (0 or 1)
    other_end: int
    grasped_over_end: bool  # was this the strand on top at the crossing
    grasp_xy: tuple[float, float]
    place_xy: tuple[float, float]
    crossing_xy: tuple[float, float]
    crossing_z_gap: float
    lift_z: float
    # Rope arc from the crossing to the grasped end -- what hangs below the hand
    # once the crossing is lifted, and what sets the lift height.
    crossing_arc: float
    carry: tuple[float, float, float]
    cross: tuple[float, float, float]
    settle: tuple[float, float, float]
    crossing_count_before: int


def _rotate_about(pivot, point, angle: float) -> np.ndarray:
    pivot = np.asarray(pivot, dtype=float)
    offset = np.asarray(point, dtype=float) - pivot
    c, s = np.cos(angle), np.sin(angle)
    return pivot + np.array([c * offset[0] - s * offset[1], s * offset[0] + c * offset[1]])


def place_beside(crossing_xy, grasp_xy, other_xy, *, clearance: float) -> tuple[float, float]:
    """Where to lay the grasped end: past the other end, on the far side from
    where it started, ``clearance`` away from it as a chord.

    Both candidate points lie on the circle about the crossing through the other
    end; the one further from the grasp point is the far side.
    """

    pivot = np.asarray(crossing_xy, dtype=float)
    other = np.asarray(other_xy, dtype=float)
    radius = float(np.linalg.norm(other - pivot))
    if radius < 1e-9:
        raise ValueError("the other end sits on the crossing; no placement circle.")
    angle = 2.0 * np.arcsin(min(1.0, float(clearance) / (2.0 * radius)))
    grasp = np.asarray(grasp_xy, dtype=float)
    candidates = [_rotate_about(pivot, other, angle), _rotate_about(pivot, other, -angle)]
    far = max(candidates, key=lambda p: float(np.linalg.norm(p - grasp)))
    return float(far[0]), float(far[1])


def plan_untwist_move(
    rope_scene,
    state,
    polyline: np.ndarray,
    *,
    end: int,
    lift_clearance: float,
    place_clearance: float,
) -> tuple[BandUntwistMoveCommand, EpisodePlan] | None:
    """Lift rope end ``end`` over the other strand and lay it beside the other end.

    Refuses (returns None) unless the rope has exactly one self-crossing: with
    zero there is nothing to undo, with two or more the state is the contrast
    outcome and a further move would only muddle the reading.
    """

    if state.crossing_count != 1:
        return None
    crossing = state.crossings[0]
    end = int(end)
    other = 1 - end
    grasp_xy = rope_scene.connector_xy(end)
    other_xy = rope_scene.connector_xy(other)
    grasped_over = crossing.over_end == end

    polyline = np.asarray(polyline, dtype=float)
    segments = np.linalg.norm(np.diff(polyline, axis=0), axis=1)
    rope_arc = float(segments.sum())
    rope_radius = float(rope_scene.layout.cfg.rope.radius)
    table_z = float(rope_scene.layout.world_z(0.0))

    # Arc from the crossing to the grasped end, along the strand being lifted.
    at = crossing.over_at if grasped_over else crossing.under_at
    crossing_arc = rope_arc * (float(at) if end == 0 else 1.0 - float(at))

    place_xy = place_beside(crossing.position, grasp_xy, other_xy, clearance=place_clearance)

    scene_top = float(polyline[:, 2].max()) + rope_radius
    lift_z = scene_top + max(float(lift_clearance), crossing_arc + float(lift_clearance))
    place_z = table_z + rope_radius

    carry = (grasp_xy[0], grasp_xy[1], lift_z)
    cross = (place_xy[0], place_xy[1], lift_z)
    settle = (place_xy[0], place_xy[1], place_z)

    command = BandUntwistMoveCommand(
        end=end,
        other_end=other,
        grasped_over_end=bool(grasped_over),
        grasp_xy=grasp_xy,
        place_xy=place_xy,
        crossing_xy=(float(crossing.position[0]), float(crossing.position[1])),
        crossing_z_gap=float(crossing.z_gap),
        lift_z=float(lift_z),
        crossing_arc=float(crossing_arc),
        carry=tuple(float(v) for v in carry),
        cross=tuple(float(v) for v in cross),
        settle=tuple(float(v) for v in settle),
        crossing_count_before=int(state.crossing_count),
    )
    subgoal = PlannedSubgoal(
        subgoal_id=f"untwist_end{end}",
        kind="lift_end_across_own_strand",
        entity=rope_scene.layout.strand_name(0),
        target={
            "end": end,
            "grasped_over_end": bool(grasped_over),
            "grasp_xy": list(grasp_xy),
            "place_xy": list(place_xy),
            "crossing_xy": list(command.crossing_xy),
            "crossing_arc": float(crossing_arc),
        },
    )
    waypoint_plan = WaypointPlan(
        plan_id="band_untwist_move",
        waypoints=(
            WaypointTarget(
                label="grasp",
                position=(grasp_xy[0], grasp_xy[1], place_z),
                metadata={"end": end},
            ),
            WaypointTarget(
                label="carry",
                position=command.carry,
                metadata={"clearance_above_scene": float(lift_clearance), "crossing_arc": crossing_arc},
            ),
            WaypointTarget(label="cross", position=command.cross, metadata={}),
            WaypointTarget(
                label="place",
                position=command.settle,
                metadata={"place_clearance": float(place_clearance)},
            ),
        ),
        metadata={"planner": "band_untwist_move"},
    )
    episode_plan = EpisodePlan(
        task_id="band_untwist",
        subgoals=(subgoal,),
        waypoint_plan=waypoint_plan,
        plan_id="band_untwist_move",
        metadata={
            "end": end,
            "grasped_over_end": bool(grasped_over),
            "crossing_arc": float(crossing_arc),
            "lift_above_table": float(lift_z - table_z),
        },
    )
    return command, episode_plan


@dataclass(frozen=True)
class BandUntwistRule:
    """Pick the end to grasp: ``over`` (the strand on top) or ``under``.

    The two modes are the task's contrast pair and differ by one field on
    purpose: same motion, same lift, same landing rule. Only which end is picked
    differs, and that is exactly the quantity the task grades.
    """

    grasp: str = "over"

    def decide(self, rope_scene, state, polyline, *, pinch_cfg):
        if state.crossing_count != 1:
            return None
        over_end = int(state.crossings[0].over_end)
        end = over_end if self.grasp == "over" else 1 - over_end
        return plan_untwist_move(
            rope_scene,
            state,
            polyline,
            end=end,
            lift_clearance=float(pinch_cfg.lift_clearance),
            place_clearance=float(pinch_cfg.place_clearance),
        )


_MODES = {
    "oracle": BandUntwistRule(grasp="over"),
    "wrong_end": BandUntwistRule(grasp="under"),
}


def make_band_untwist_rule(mode: str) -> BandUntwistRule:
    """`run.oracle_mode` -> rule."""

    try:
        return _MODES[str(mode)]
    except KeyError:
        raise ValueError(
            f"unknown oracle_mode {mode!r}; expected one of {sorted(_MODES)}"
        ) from None
