"""Where the held material goes, phase by phase, for ring_transfer (docx 2.6).

The oracle is a sequence of gateway crossings the layout derives from the
goal: `layout.crossings()` gives `[(B, on), (A, off)]` for the A->B transfer.
Each crossing becomes one phase with its own grasp:

- **on**  : the far cap is HOOKED on both open fingers (two bands,
            `grasp.spread` apart) and follows `far_cap_path` -- swing round the
            anchor, rise, carry over the target's head, descend on its far side.
            The anchor post is the second hand that keeps the loop open; a loop
            lifted off both posts hangs vertical and cannot be put around
            anything (measured 2026-08-24).
- **off** : the near cap is pinched where it hugs the anchor, lifted over the
            anchor's head and shifted past it, then let go.

Waypoints are targets for the HELD MATERIAL in the task frame; the demo owns the
hand offset (`physical.hand_above`) and the lateral finger offsets.

Motions, so the judge has both sides:
- ``transfer``       the task: on B, then off A;
- ``carry``          the same task by the other route (user's proposal,
                     2026-08-25): hook the loop next to A with the fingers
                     spread, lift it over A's head, carry it hanging, lasso B
                     from the side (the bottom U meets B's shaft and the strands
                     part around it), lower, release. No stretch, no second
                     anchor, any post spacing;
- ``drape_outside``  the on-phase lands the cap on B's NEAR side and there is no
                     off-phase: the loop ends up beside B, still on A -- the
                     projection looks like an enclosure and the winding says no;
- ``lift_only``      the off-phase alone: the loop leaves A without ever having
                     been put on B, and ends around nothing.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from topogym.planning.subgoal import PlannedSubgoal
from topogym.planning.waypoint import EpisodePlan, WaypointPlan, WaypointTarget

MOTIONS = ("transfer", "carry", "drape_outside", "lift_only")
HOOK_BANDS = ("hook_left", "hook_right")
NEAR_BAND = "near"
LIFT_BANDS = ("lift_left", "lift_right")


@dataclass(frozen=True)
class GraspPhase:
    """One grasp -> path -> release. `bands` are the follow bands to attach."""

    name: str
    kind: str  # "hook" (fingers open inside the loop) | "pinch"
    post: str  # the post this phase crosses
    bands: tuple[str, ...]
    waypoints: tuple[WaypointTarget, ...]
    anchor_xy: tuple[float, float]  # the post the strands run from; sets the yaw
    fixed_yaw: float | None = None  # carry: the wrist does not turn

    def yaw_at(self, xy) -> float:
        """Wrist yaw: fingers ACROSS the pull direction from the anchor."""

        if self.fixed_yaw is not None:
            return float(self.fixed_yaw)
        direction = np.asarray(xy, dtype=float)[:2] - np.asarray(self.anchor_xy, dtype=float)
        return float(np.arctan2(direction[1], direction[0]))


def _targets(points, labels, *, lifted) -> tuple[WaypointTarget, ...]:
    return tuple(
        WaypointTarget(label=str(label), position=tuple(float(v) for v in point), lifted=lifted)
        for label, point in zip(labels, points)
    )


def on_phase(layout, *, drape_outside: bool = False) -> GraspPhase:
    path = layout.far_cap_path()
    if drape_outside:
        # Land on the target's NEAR side instead of its far side: same height,
        # same swing, the cap simply stops short of the post.
        target = layout.target
        ring = layout.ring
        direction = target.center - layout.anchor.center
        direction = direction / float(np.linalg.norm(direction))
        near = target.center - (target.head_radius + ring.tube_radius + float(layout.task_cfg.transfer.landing_clearance)) * direction
        carry_z = float(layout.task_cfg.transfer.carry_z)
        path = [item for item in path if item[0] not in ("carry", "descend")]
        path.append(("carry", np.array([near[0], near[1], carry_z])))
        path.append(("descend", np.array([near[0], near[1], ring.tube_radius])))
    labels = [label for label, _ in path[1:]]
    points = [point for _, point in path[1:]]
    return GraspPhase(
        name=f"on_{layout.target.name}",
        kind="hook",
        post=layout.target.name,
        bands=HOOK_BANDS,
        waypoints=_targets(points, labels, lifted=True),
        anchor_xy=tuple(float(v) for v in layout.anchor.center),
    )


def off_phase(layout, *, start_xy=None) -> GraspPhase:
    """Lift the near cap over the anchor's head and shift it past the post.

    `start_xy` is where the near band actually is (observed after the on-phase);
    the design value is the anchor's outer surface.
    """

    anchor, target, ring = layout.anchor, layout.target, layout.ring
    toward = target.center - anchor.center
    toward = toward / float(np.linalg.norm(toward))
    if start_xy is None:
        start_xy = anchor.center - (anchor.radius + ring.tube_radius) * toward
    start_xy = np.asarray(start_xy, dtype=float)[:2]
    lift = np.array([start_xy[0], start_xy[1], layout.lift_z()])
    shifted = lift + float(layout.task_cfg.transfer.shift) * np.array([toward[0], toward[1], 0.0])
    return GraspPhase(
        name=f"off_{anchor.name}",
        kind="pinch",
        post=anchor.name,
        bands=(NEAR_BAND,),
        waypoints=_targets([lift, shifted], ["lift", "shift"], lifted=True),
        # Fingers across the anchor->target line: the strand hugging the anchor's
        # outer surface runs perpendicular to that line, so the pads land on
        # either side of it.
        anchor_xy=tuple(float(v) for v in (start_xy - toward)),
    )


def carry_phase(layout) -> GraspPhase:
    """Lift next to A, carry hanging, lasso B from the side, put down."""

    path = layout.carry_path()
    heading = layout.target.center - layout.anchor.center
    yaw = float(np.arctan2(heading[1], heading[0]))
    labels = [label for label, _ in path[1:]]
    points = [point for _, point in path[1:]]
    return GraspPhase(
        name=f"carry_{layout.anchor.name}_to_{layout.target.name}",
        kind="hook",
        post=layout.target.name,
        bands=LIFT_BANDS,
        waypoints=_targets(points, labels, lifted=True),
        anchor_xy=tuple(float(v) for v in layout.anchor.center),
        fixed_yaw=yaw,
    )


def plan_ring_transfer(layout, *, motion: str = "transfer"):
    """Plan one episode. Returns ``(phases, EpisodePlan)``."""

    if motion not in MOTIONS:
        raise ValueError(f"motion must be one of {MOTIONS}, got {motion!r}.")
    if motion == "transfer":
        phases = [on_phase(layout), off_phase(layout)]
    elif motion == "carry":
        phases = [carry_phase(layout)]
    elif motion == "drape_outside":
        phases = [on_phase(layout, drape_outside=True)]
    else:
        phases = [off_phase(layout)]

    subgoals = tuple(
        PlannedSubgoal(
            subgoal_id=phase.name,
            kind=f"ring_{phase.kind}",
            entity="ring",
            target={"post": phase.post, "end": phase.waypoints[-1].position},
            metadata={"bands": list(phase.bands)},
        )
        for phase in phases
    )
    waypoints = tuple(
        WaypointTarget(
            label=f"{phase.name}:{wp.label}", position=wp.position, lifted=wp.lifted, metadata={"phase": phase.name}
        )
        for phase in phases
        for wp in phase.waypoints
    )
    plan = EpisodePlan(
        task_id="ring_transfer",
        subgoals=subgoals,
        waypoint_plan=WaypointPlan(
            plan_id=f"ring_transfer_{motion}",
            waypoints=waypoints,
            metadata={"planner": "ring_transfer_hook_then_lift", "motion": motion, "crossings": layout.crossings()},
        ),
        plan_id=f"ring_transfer_{motion}",
        metadata={"motion": motion},
    )
    return phases, plan


__all__ = ["GraspPhase", "HOOK_BANDS", "LIFT_BANDS", "MOTIONS", "NEAR_BAND", "carry_phase", "off_phase", "on_phase", "plan_ring_transfer"]
