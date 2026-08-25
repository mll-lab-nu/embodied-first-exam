"""Where the hand goes to pay the roll out (docx 1.3「展开自身卷曲的布带」).

The gripper takes the flat run's free END and drags it away from the dispenser,
along the table. Every bit of rotation is absorbed by the roll turning on the bar;
the wrist never turns. That is what keeps the gripper's pose relative to the cloth
fixed, which orbiting the roll cannot do -- orbiting would ask the wrist to follow
through 720 degrees for two turns, past the last joint's travel.

**The distance is arithmetic, not a choice.** If the bar holds, the end travels
exactly the material the roll stores. `pull_scale` is the only slack in it.

This plans ONE stroke, from wherever the free end is NOW. As shipped an episode
is a single continuous stroke -- two turns on an 8 mm bar store ~161 mm and the
arm reaches that -- so the loop runs once. The per-stroke shape is kept because
a larger `turns` puts the travel past what the arm can reach, and because the
starting point has to come from a measurement either way: reaching for a position
the cloth has left is how `cloth_unpleat`'s first run failed.

**The stroke is slow on purpose.** `fix_particles_to_link` is a kinematic bind,
so the caught particles go exactly where the hand goes and there is no force to
tune; what limits stretch is how fast PBD propagates that displacement into the
rest of the cloth, roughly an edge per iteration against ~35 particles of band.
At 1.2's 1.5 mm a step the tension had not reached the roll before the hand moved
again and the band stretched into a thin strip (measured 2026-08-24). The speed
lives in `physical.pull_step_m`, which this module reads rather than sets.

Three motions come out of the same geometry so the judge's thresholds have
something on both sides:

- ``unroll`` is the task;
- ``shove`` pulls the end the WRONG WAY, toward the dispenser. The band bunches
  and the roll keeps its material -- a wrong action that moves the same amount of
  cloth as the right one;
- ``overpull`` keeps going past the point where the roll has given everything
  back. In 1.2 that was where the whole band started sliding; here the bar holds
  the band, so what it stresses instead is the roll's grip on the bar -- the
  failure this scene has and that one did not.

  A caveat worth stating rather than hiding: the overpull end point is outside
  the envelope 1.2 measured the arm reaching (+0.152 on y), so the arm stalls
  against its own reach limit partway through while still holding the cloth. That
  is not a defect for this purpose -- a stalled arm gripping the end IS sustained
  tension on an empty roll, which is the state being probed -- but it does mean
  the reading is "as far as the arm got", not `overpull_scale` times the travel.
"""

from __future__ import annotations

import numpy as np

from topogym.planning.subgoal import PlannedSubgoal
from topogym.planning.waypoint import EpisodePlan, WaypointPlan, WaypointTarget

#: Straight segments one stroke is cut into. Same reason as in `cloth_unpleat`:
#: the path is straight, so this buys nothing geometrically -- it exists so the
#: primitive reports its follow error several times across the stroke instead of
#: once at the end, which is what catches a roll that let go halfway.
PULL_SEGMENTS = 8

MOTIONS = ("unroll", "shove", "overpull")

#: How close the HAND can get to the bar's centre line before the gripper fouls
#: the dispenser. Measured 2026-08-25, not derived: commanded past it, the hand
#: stopped dead at 57 mm from the bar centre and stayed there for six segments
#: while the commands ran on to 175 mm beyond. It is the gripper's own extent
#: plus the bar, so it does not follow from the bar radius alone.
SHOVE_BAR_CLEARANCE = 0.057


def stroke_waypoints(
    layout,
    *,
    motion: str = "unroll",
    segments: int = PULL_SEGMENTS,
    overpull_scale: float = 1.6,
) -> list[WaypointTarget]:
    """One stroke's path, cut into segments the primitive can drive.

    Starts from ``layout.grasp_point()``, which is the free end AS MEASURED, not
    as designed. 1.2's first run died on exactly this distinction.
    """

    if motion not in MOTIONS:
        raise ValueError(f"motion must be one of {MOTIONS}, got {motion!r}.")

    segments = max(2, int(segments))
    start = np.asarray(layout.grasp_point(), dtype=float)
    direction = layout.pull_direction()

    distance = layout.stroke_distance()
    if motion == "shove":
        # Bounded by the fixture, not by the nominal stroke reversed. Measured
        # 2026-08-25: the full reversal sent the hand to y=-0.228 and it stalled
        # at -0.053 with `arm_pos_err_mm=177`, grinding the band into 11 layers
        # and putting cloth under the table for three segments (536 particle-
        # steps) -- the only motion of the three that penetrated at all. The
        # gripper cannot pass the dispenser, so the distractor has to stop short
        # of it. What is left is the room actually available, which is what a
        # wrong action gets in this scene.
        axis = layout.material_axis
        room = abs(float(start[axis]) - float(layout.bar_centre()[axis]))
        distance = -min(distance, max(0.0, room - SHOVE_BAR_CLEARANCE))
    elif motion == "overpull":
        distance = distance * float(overpull_scale)

    # Steps from THIS motion's distance, not from the nominal stroke. Sharing one
    # step count across motions of different lengths would make them different
    # SPEEDS, and then a comparison between them is confounded by the one thing
    # the calibration is supposed to hold fixed. Measured on 1.2, 2026-08-23:
    # overpull ran at 2.4 mm a step against unfold's 1.5 because of exactly this.
    steps = max(4, int(round(abs(distance) / float(layout.task_cfg.physical.pull_step_m))))
    per_segment = max(1, int(round(steps / segments)))

    out: list[WaypointTarget] = []
    for index in range(1, segments + 1):
        fraction = index / segments
        point = start + direction * (distance * fraction)
        out.append(
            WaypointTarget(
                label=f"pull_{index:02d}",
                position=tuple(float(v) for v in point),
                steps=per_segment,
                # Nothing leaves the table. Lifting is a different action with a
                # different failure -- it peels the roll off the bar rather than
                # turning it -- and the whole design here is that the pull stays
                # in the plane and the bar does the holding.
                lifted=False,
                metadata={
                    "fraction": round(fraction, 4),
                    "travel_mm": round(float(distance * fraction) * 1e3, 2),
                },
            )
        )
    return out


def plan_cloth_unroll(
    layout,
    *,
    stroke: int = 1,
    motion: str = "unroll",
    segments: int = PULL_SEGMENTS,
    overpull_scale: float = 1.6,
):
    """Plan ONE stroke of an unroll. Returns ``(waypoints, EpisodePlan)``.

    ``stroke`` is 1-based and used for labelling only -- where the stroke starts
    comes from the layout's measured free end, so calling this twice with the
    same index after re-observing gives two different (and correct) plans.

    The waypoints are targets for the grasped material in world coordinates --
    where the cloth has to go, not where the hand has to be. The primitive owns
    the offset between the two, because it also owns the promise that the pads
    stop above the cloth and never touch it.
    """

    stroke = max(1, int(stroke))
    waypoints = stroke_waypoints(
        layout, motion=motion, segments=segments, overpull_scale=overpull_scale
    )
    marks = layout.landmarks()
    plan_id = f"cloth_unroll_{motion}_s{stroke:02d}"
    subgoal = PlannedSubgoal(
        subgoal_id=f"unroll_{motion}_s{stroke:02d}",
        kind="unroll_cloth",
        entity=str(layout.task_cfg.cloth.name),
        target={
            "grasp": tuple(float(v) for v in layout.grasp_point()),
            "place": tuple(float(v) for v in waypoints[-1].position),
        },
        tolerance=float(layout.task_cfg.cloth.particle_size),
        metadata={
            "motion": motion,
            "stroke": stroke,
            "strokes": int(layout.stroke_count()),
            "rolled_m": float(marks["rolled"]),
        },
    )
    waypoint_plan = WaypointPlan(
        plan_id=plan_id,
        waypoints=tuple(waypoints),
        metadata={
            "planner": "cloth_unroll_end_pull",
            "motion": motion,
            "stroke": stroke,
            "strokes": int(layout.stroke_count()),
            "segments": segments,
            "stroke_m": float(layout.stroke_distance()),
            "steps": int(layout.stroke_steps()),
        },
    )
    episode_plan = EpisodePlan(
        task_id="cloth_unroll",
        subgoals=(subgoal,),
        waypoint_plan=waypoint_plan,
        plan_id=plan_id,
        metadata={
            "rolled_m": float(marks["rolled"]),
            "pull_total_m": float(layout.pull_total()),
            "step_m": float(layout.stroke_distance() / layout.stroke_steps()),
        },
    )
    return waypoints, episode_plan
