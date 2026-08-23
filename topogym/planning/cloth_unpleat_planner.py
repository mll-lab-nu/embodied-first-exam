"""Where the hand goes to spread the pleat out (docx 1.2「展开单个褶皱」).

The crest is joined to the lower crease by a fixed length of cloth, so it can
only travel on a circle centred on that crease -- exactly the constraint
`cloth_fold_planner` derives its arc from, and for exactly the same reason: reach
further out and the hand is stretching the cloth, cut inside and the material
sags onto the table and gets shoved sideways. Here the sweep starts partway round
(the crest is already up in the air) and ends flat, so it is a partial turn where
`cloth_fold`'s is a half turn.

docx 1.2 calls the motion 「一次水平拖拽」. That is the intent; the circle is what
the intent works out to. On the shipped layout a straight line from the crest to
its flat target passes 34 mm inside the arc, which is most of the pleat.

Three motions are planned from the same geometry so the judge's thresholds have
something on both sides, the way `cloth_fold`'s were calibrated:

- ``unfold`` is the task;
- ``press`` pushes the crest straight down, which docx names as the shortcut that
  passes a height test and should fail on layers and on length;
- ``overpull`` runs the arc and then keeps going in a straight line, to show
  what towing the whole band looks like against a judge that only reads spread
  length.
"""

from __future__ import annotations

import numpy as np

from topogym.planning.subgoal import PlannedSubgoal
from topogym.planning.waypoint import EpisodePlan, WaypointPlan, WaypointTarget

#: Straight segments over the sweep. The chord's worst deviation from the arc is
#: R(1 - cos(theta/2N)); at 10 segments over 149 degrees on a 57 mm radius that
#: is 0.48 mm, an eighth of a particle -- `check_cloth_unpleat_geometry.py`
#: asserts it rather than trusting this line. More segments cost waypoints and
#: buy nothing the solver can resolve.
DRAG_SEGMENTS = 10

MOTIONS = ("unfold", "press", "overpull")


def arc_point(layout, angle: float, radius: float | None = None) -> np.ndarray:
    """Where the crest sits at ``angle`` about the crease, in world.

    The arc lies in the vertical plane containing the band's own length axis, so
    it turns with the band rather than being pinned to world x.

    ``radius`` defaults to the taut one. The sweep passes a growing value instead
    -- see `drag_waypoints`.
    """

    crease = np.asarray(layout.crease_point(), dtype=float)
    radius = layout.arc_radius() if radius is None else float(radius)
    point = crease.copy()
    point[layout.material_axis] = (
        crease[layout.material_axis] + radius * float(np.cos(angle))
    )
    point[2] = layout.rest_z() + radius * float(np.sin(angle))
    return point


def drag_waypoints(
    layout, *, motion: str = "unfold", segments: int = DRAG_SEGMENTS, overpull_scale: float = 1.6
) -> list[WaypointTarget]:
    """The crest's path, cut into straight segments the primitive can drive."""

    if motion not in MOTIONS:
        raise ValueError(f"motion must be one of {MOTIONS}, got {motion!r}.")

    segments = max(2, int(segments))
    total = layout.drag_steps()
    per_segment = max(1, int(round(total / segments)))
    start = layout.start_angle()

    if motion == "press":
        # Straight down onto the crease's own height, over the same number of
        # steps. Nothing about it follows the material: that is the point.
        crest = np.asarray(layout.crest_point(), dtype=float)
        floor = layout.rest_z() + float(layout.task_cfg.cloth.particle_size)
        return [
            WaypointTarget(
                label=f"press_{index:02d}",
                position=(
                    float(crest[0]),
                    float(crest[1]),
                    float(crest[2] + (floor - crest[2]) * index / segments),
                ),
                steps=per_segment,
                lifted=index < segments,
                metadata={"fraction": round(index / segments, 4)},
            )
            for index in range(1, segments + 1)
        ]

    # `unfold` sweeps the crest round to flat. `overpull` runs that same sweep and
    # then keeps going in a straight line along +x, which is what towing the band
    # looks like: the material is already taut at the end of the arc, so anything
    # past it pulls the whole band rather than opening anything. Continuing to
    # ROTATE instead would drive the crest down through the table, which is a
    # different and less interesting wrong answer.
    #
    # The radius opens out over the sweep rather than being taut from step one.
    # An authored pleat sags before anything touches it, which leaves the crest
    # closer to the crease than its arm of cloth is long; commanding the taut
    # radius immediately would pull that slack out in a single step. Where the
    # pleat has not sagged the two radii are equal and this is the plain circle.
    inner, taut = layout.start_radius(), layout.arc_radius()
    out: list[WaypointTarget] = []
    for index in range(1, segments + 1):
        fraction = index / segments
        angle = start * (1.0 - fraction)
        radius = inner + (taut - inner) * fraction
        out.append(
            WaypointTarget(
                label=f"arc_{index:02d}",
                position=tuple(float(v) for v in arc_point(layout, angle, radius)),
                steps=per_segment,
                # Everything before the last waypoint has the crest off the table.
                lifted=index < segments,
                metadata={
                    "fraction": round(fraction, 4),
                    "angle_deg": round(float(np.degrees(angle)), 2),
                    "radius_mm": round(float(radius) * 1e3, 2),
                },
            )
        )
    if motion == "overpull":
        extra = layout.arc_length() * (float(overpull_scale) - 1.0)
        flat = np.asarray(arc_point(layout, 0.0, taut), dtype=float)
        tow_segments = max(1, int(round(segments * (float(overpull_scale) - 1.0))))
        for index in range(1, tow_segments + 1):
            towed = flat.copy()
            towed[layout.material_axis] += extra * index / tow_segments
            out.append(
                WaypointTarget(
                    label=f"tow_{index:02d}",
                    position=tuple(float(v) for v in towed),
                    steps=per_segment,
                    lifted=False,
                    metadata={"tow_m": round(float(extra * index / tow_segments), 4)},
                )
            )
    return out


def plan_cloth_unpleat(
    layout, *, motion: str = "unfold", segments: int = DRAG_SEGMENTS, overpull_scale: float = 1.6
):
    """Plan one unpleat. Returns ``(waypoints, EpisodePlan)``.

    The waypoints are crest targets in world coordinates -- where the material
    has to go, not where the hand has to be. The primitive owns the offset
    between the two, because it also owns the promise that the pads stop above
    the cloth and never touch it.
    """

    waypoints = drag_waypoints(
        layout, motion=motion, segments=segments, overpull_scale=overpull_scale
    )
    marks = layout.landmarks()
    subgoal = PlannedSubgoal(
        subgoal_id=f"unpleat_{motion}",
        kind="unpleat_cloth",
        entity=str(layout.task_cfg.cloth.name),
        target={
            "grasp": tuple(float(v) for v in layout.crest_point()),
            "place": tuple(float(v) for v in waypoints[-1].position),
            "crease": tuple(float(v) for v in layout.crease_point()),
        },
        tolerance=float(layout.task_cfg.cloth.particle_size),
        metadata={"motion": motion, "stored_m": float(marks["stored"])},
    )
    waypoint_plan = WaypointPlan(
        plan_id=f"cloth_unpleat_{motion}",
        waypoints=tuple(waypoints),
        metadata={
            "planner": "cloth_unpleat_crest_arc",
            "motion": motion,
            "segments": segments,
            "start_radius_m": float(layout.start_radius()),
            "radius_m": float(layout.arc_radius()),
            "steps": int(layout.drag_steps()),
        },
    )
    episode_plan = EpisodePlan(
        task_id="cloth_unpleat",
        subgoals=(subgoal,),
        waypoint_plan=waypoint_plan,
        plan_id=f"cloth_unpleat_{motion}",
        metadata={
            "arm_m": float(layout.arm_length()),
            "step_m": float(layout.arc_length() / layout.drag_steps()),
        },
    )
    return waypoints, episode_plan


def chord_error(layout, *, segments: int = DRAG_SEGMENTS) -> float:
    """Worst distance from a chord to the arc it replaces, in metres.

    Exposed so the offline check can assert it stays well under a particle rather
    than trusting the comment on `DRAG_SEGMENTS`.
    """

    half = abs(layout.start_angle()) / (2 * max(2, int(segments)))
    return float(layout.arc_radius() * (1.0 - np.cos(half)))
