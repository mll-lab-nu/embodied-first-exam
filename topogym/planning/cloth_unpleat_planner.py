"""Where the hand goes to pull the pleat out (docx 1.2「展开单个褶皱」).

The gripper takes the band's free END and drags it away from the fold, along the
table. The tension runs down the flat tail into the pleat; table friction on the
far half is what holds the anchor while the fold feeds its material out.

**The distance is arithmetic, not a choice.** If the anchor holds, the end travels
exactly the material the pleat stores, which is the band's material length minus
its plan span. `pull_scale` is the only slack in it, for the fact that friction
lets the anchor creep a little.

docx 1.2 has the gripper pinch the pleat's standing crest. This task does not:
the pleat lies flat in this simulator (Genesis 1.2.1 ignores `bending_compliance`,
so nothing holds a crease -- the sweep is recorded in the task config), and there
is no standing edge to pinch.

Three motions come out of the same geometry so the judge's thresholds have
something on both sides:

- ``unfold`` is the task;
- ``shove`` pulls the end the WRONG WAY, toward the fold. The band bunches and
  the pleat keeps its material -- a wrong action that moves the same amount of
  cloth as the right one;
- ``overpull`` keeps going past the point where the pleat has given everything
  back, which is where the whole band starts sliding. It is what a judge reading
  length alone cannot tell from success, and the reason `band_shift` is recorded.
"""

from __future__ import annotations

import numpy as np

from topogym.planning.subgoal import PlannedSubgoal
from topogym.planning.waypoint import EpisodePlan, WaypointPlan, WaypointTarget

#: Straight segments the pull is cut into. The path is a straight line, so this
#: buys nothing geometrically -- it exists so the primitive reports its follow
#: error several times across the pull instead of once at the end, which is what
#: catches an anchor that let go halfway.
PULL_SEGMENTS = 8

MOTIONS = ("unfold", "shove", "overpull")


def pull_waypoints(
    layout, *, motion: str = "unfold", segments: int = PULL_SEGMENTS, overpull_scale: float = 1.6
) -> list[WaypointTarget]:
    """The end's path, cut into segments the primitive can drive."""

    if motion not in MOTIONS:
        raise ValueError(f"motion must be one of {MOTIONS}, got {motion!r}.")

    segments = max(2, int(segments))
    per_segment = max(1, int(round(layout.pull_steps() / segments)))
    start = np.asarray(layout.grasp_point(), dtype=float)
    direction = layout.pull_direction()

    distance = layout.pull_distance()
    if motion == "shove":
        distance = -distance
    elif motion == "overpull":
        distance = distance * float(overpull_scale)

    out: list[WaypointTarget] = []
    for index in range(1, segments + 1):
        fraction = index / segments
        point = start + direction * (distance * fraction)
        out.append(
            WaypointTarget(
                label=f"pull_{index:02d}",
                position=tuple(float(v) for v in point),
                steps=per_segment,
                # Nothing leaves the table: the whole point is that the pull is
                # in the plane and friction does the holding.
                lifted=False,
                metadata={
                    "fraction": round(fraction, 4),
                    "travel_mm": round(float(distance * fraction) * 1e3, 2),
                },
            )
        )
    return out


def plan_cloth_unpleat(
    layout, *, motion: str = "unfold", segments: int = PULL_SEGMENTS, overpull_scale: float = 1.6
):
    """Plan one unpleat. Returns ``(waypoints, EpisodePlan)``.

    The waypoints are targets for the grasped material in world coordinates --
    where the cloth has to go, not where the hand has to be. The primitive owns
    the offset between the two, because it also owns the promise that the pads
    stop above the cloth and never touch it.
    """

    waypoints = pull_waypoints(
        layout, motion=motion, segments=segments, overpull_scale=overpull_scale
    )
    marks = layout.landmarks()
    subgoal = PlannedSubgoal(
        subgoal_id=f"unpleat_{motion}",
        kind="unpleat_cloth",
        entity=str(layout.task_cfg.cloth.name),
        target={
            "grasp": tuple(float(v) for v in layout.grasp_point()),
            "place": tuple(float(v) for v in waypoints[-1].position),
        },
        tolerance=float(layout.task_cfg.cloth.particle_size),
        metadata={"motion": motion, "stored_m": float(marks["stored"])},
    )
    waypoint_plan = WaypointPlan(
        plan_id=f"cloth_unpleat_{motion}",
        waypoints=tuple(waypoints),
        metadata={
            "planner": "cloth_unpleat_edge_pull",
            "motion": motion,
            "segments": segments,
            "pull_m": float(layout.pull_distance()),
            "steps": int(layout.pull_steps()),
        },
    )
    episode_plan = EpisodePlan(
        task_id="cloth_unpleat",
        subgoals=(subgoal,),
        waypoint_plan=waypoint_plan,
        plan_id=f"cloth_unpleat_{motion}",
        metadata={
            "stored_m": float(marks["stored"]),
            "step_m": float(layout.pull_distance() / layout.pull_steps()),
        },
    )
    return waypoints, episode_plan
