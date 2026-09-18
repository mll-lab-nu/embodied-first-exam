"""Where the hand goes to fold the sheet corner to corner (docx 1.1「折角」).

The trajectory is not a free choice. The grasped corner is joined to the fold
line by a fixed length of material, so it can only travel on a circle centred on
that line: reach further out and the hand is stretching the cloth, cut inside and
the sheet sags onto the table and gets towed sideways. Both were measured on
2026-08-19, from opposite sides -- a 40 mm vertical lift needed 147 mm of
material against the 141 available, and an 80 mm apex left the sheet 61 mm short
and dragged it. Once the motion was written as a rotation about the fold line,
the two parameters that had been tuning those failures (`fold_lift`,
`fold_arc_height`) stopped existing.

What remains is a speed and a sampling density, and neither is free either:

- **speed** is calibrated (3.6 mm a step) and lives in the task config, not here.
  `ClothFoldLayout.fold_steps()` turns it into a step count for whatever arc the
  layout produces.
- **sampling** is set by how far a straight line may stray from the arc. The
  executing primitive interpolates in straight lines between waypoints, so the
  waypoints have to be close enough that the chords hug the circle.

Three control motions share the machinery (`run.motion`): ``drag`` follows the
arc's plan-view projection without ever leaving the table -- docx 1.1's
"sliding it along without lifting" -- while ``fixed_corner`` plans as if the
instruction always named the baseline corner and ``fixed_fold`` plans as if it
always said corner-to-corner, each ignoring one of the two things the sentence
is the only source of. All three are judged against the instructed fold and are
supposed to fail: `fixed_corner` three times in four, `fixed_fold` two times in
three (it is right only when the drawn fraction was 1.0).
"""

from __future__ import annotations

import numpy as np

from topogym.planning.subgoal import PlannedSubgoal
from topogym.planning.waypoint import EpisodePlan, WaypointPlan, WaypointTarget

#: Straight segments per half turn. The chord's worst deviation from the arc is
#: R(1 - cos(pi/2N)); at 12 segments on a 138.6 mm radius that is 0.84 mm, under
#: a quarter of a particle. Raising it costs waypoints and buys nothing the
#: solver can resolve.
FOLD_SEGMENTS = 12
#: What `run.motion` may be.
MOTIONS = ("fold", "drag", "fixed_corner", "fixed_fold")
#: The corner `fixed_corner` always folds: the yaml's baseline.
FIXED_CORNER = "far_left"
#: The extent `fixed_fold` always folds: corner onto corner, the yaml's baseline.
FIXED_FRACTION = 1.0


def execution_layout(layout, motion: str = "fold"):
    """The layout the hand actually plans and executes from.

    Identical to ``layout`` for `fold` and `drag`; for `fixed_corner` it is the
    same sheet with the baseline corner taken and for `fixed_fold` the same
    sheet folded corner to corner, whatever the instruction said. The judge
    keeps using the instructed layout, which is what makes them fail.
    """

    if motion not in MOTIONS:
        raise ValueError(f"run.motion must be one of {MOTIONS}, got {motion!r}.")
    if motion == "fixed_corner":
        return layout.with_corner(FIXED_CORNER)
    if motion == "fixed_fold":
        return layout.with_fold_fraction(FIXED_FRACTION)
    return layout


def arc_point(layout, fraction: float, *, lifted: bool = True) -> np.ndarray:
    """Where the grasped corner should be, ``fraction`` through the half turn.

    Rotation about the fold line: the corner rises to the line's height on the
    near side and comes down on the far side, staying a constant length of
    material away from the line the whole way. ``lifted=False`` keeps the same
    plan-view point at the sheet's resting height (the `drag` control).
    """

    theta = np.pi * float(fraction)
    radius = layout.fold_radius()
    centre = np.asarray(layout.fold_point(), dtype=float)
    normal = np.asarray(layout.fold_normal(), dtype=float)
    xy = centre + normal * (radius * float(np.cos(theta)))
    height = radius * float(np.sin(theta)) if lifted else 0.0
    return np.array([xy[0], xy[1], layout.rest_z() + height])


def fold_waypoints(
    layout, *, segments: int = FOLD_SEGMENTS, motion: str = "fold"
) -> list[WaypointTarget]:
    """The arc, cut into straight segments the primitive can drive.

    Steps are shared out over the segments so the whole motion runs at the
    calibrated speed regardless of how many segments there are. `drag` keeps
    the same segments and step count with every point at the resting height.
    """

    if motion not in MOTIONS:
        raise ValueError(f"run.motion must be one of {MOTIONS}, got {motion!r}.")
    lifted_motion = motion != "drag"
    segments = max(2, int(segments))
    total = layout.fold_steps()
    per_segment = max(1, int(round(total / segments)))
    out: list[WaypointTarget] = []
    for index in range(1, segments + 1):
        fraction = index / segments
        out.append(
            WaypointTarget(
                label=f"arc_{index:02d}",
                position=tuple(
                    float(v) for v in arc_point(layout, fraction, lifted=lifted_motion)
                ),
                steps=per_segment,
                # The half-way waypoint is the apex; everything between the first
                # and the last has the cloth off the table. A drag never lifts.
                lifted=lifted_motion and index < segments,
                metadata={"fraction": round(fraction, 4)},
            )
        )
    return out


def plan_cloth_fold(layout, *, segments: int = FOLD_SEGMENTS, motion: str = "fold"):
    """Plan one corner fold. Returns ``(waypoints, EpisodePlan)``.

    ``layout`` is what the hand executes from -- pass `execution_layout(...)`
    for the control motions. The waypoints are grasp-point targets in world
    coordinates -- where the material has to go, not where the hand has to be.
    The primitive owns the offset between the two, because it also owns the
    promise that the pads stop above the cloth and never touch it.
    """

    waypoints = fold_waypoints(layout, segments=segments, motion=motion)
    grasp = layout.grasp_point()
    target = layout.fold_target()
    subgoal = PlannedSubgoal(
        subgoal_id=f"fold_corner_to_corner_{motion}",
        kind="fold_cloth",
        entity="fold_cloth",
        target={
            "grasp": tuple(float(v) for v in grasp),
            "place": tuple(float(v) for v in target),
            "fold_line_point": tuple(float(v) for v in layout.fold_point()),
            "fold_line_normal": tuple(float(v) for v in layout.fold_normal()),
        },
        tolerance=float(layout.task_cfg.success.particle_error_mean_max),
        metadata={
            "grasp_at": str(layout.task_cfg.grasp.at),
            "corner": str(layout.corner),
            "motion": motion,
        },
    )
    waypoint_plan = WaypointPlan(
        plan_id=f"cloth_fold_corner_arc_{motion}",
        waypoints=tuple(waypoints),
        metadata={
            "planner": "cloth_fold_corner_arc",
            "motion": motion,
            "segments": segments,
            "radius_m": float(layout.fold_radius()),
            "steps": int(layout.fold_steps()),
        },
    )
    episode_plan = EpisodePlan(
        task_id="cloth_fold",
        subgoals=(subgoal,),
        waypoint_plan=waypoint_plan,
        plan_id=f"cloth_fold_corner_arc_{motion}",
        metadata={
            "material_m": float(layout.material_distance()),
            "step_m": float(np.pi * layout.fold_radius() / layout.fold_steps()),
        },
    )
    return waypoints, episode_plan


def chord_error(layout, *, segments: int = FOLD_SEGMENTS) -> float:
    """Worst distance from a chord to the arc it replaces, in metres.

    Exposed so the offline check can assert it stays under a particle rather than
    trusting the comment on `FOLD_SEGMENTS`.
    """

    return float(layout.fold_radius() * (1.0 - np.cos(np.pi / (2 * max(2, int(segments))))))
