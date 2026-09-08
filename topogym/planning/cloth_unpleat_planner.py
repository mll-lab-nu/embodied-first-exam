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

#: Smallest extension worth driving (half a particle): below this the deficit
#: is within the judge's own resolution and another glide would just add lag.
#: One particle (4 mm) was too coarse: the shipped layout's deficit after the
#: planned pull reads 3.9 mm held, and skipping it left the settled band at a
#: recovered fraction of 0.885 (2026-09-05).
EXTEND_MIN_M = 0.002


def pull_waypoints(
    layout, *, motion: str = "unfold", segments: int = PULL_SEGMENTS, overpull_scale: float = 1.6
) -> list[WaypointTarget]:
    """The end's path, cut into segments the primitive can drive."""

    if motion not in MOTIONS:
        raise ValueError(f"motion must be one of {MOTIONS}, got {motion!r}.")

    segments = max(2, int(segments))
    start = np.asarray(layout.grasp_point(), dtype=float)
    direction = layout.pull_direction()

    distance = layout.pull_distance()
    if motion == "shove":
        distance = -distance
    elif motion == "overpull":
        distance = distance * float(overpull_scale)

    # Steps from THIS motion's distance, not from the nominal pull. Sharing one
    # step count across motions of different lengths would make them different
    # SPEEDS, and then a comparison between them is confounded by the one thing
    # the calibration is supposed to hold fixed. Measured 2026-08-23: overpull
    # ran at 2.4 mm a step against unfold's 1.5 because of exactly this.
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


class PullExtender:
    """Closed loop on the band's spread: pull more until the pleat reads open.

    The planned pull is ``stored x pull_scale`` -- the material the pleat holds,
    on the assumption that all of it comes back out. Measured 2026-09-05 over
    192 envelope corners: flat pleats (crest / width <= 0.8) and the widest
    pleats keep the last 8-10 mm folded as a two-layer remnant, steep ones give
    everything back, and at ``pull_scale`` 0.98 that residual puts the recovered
    fraction under the 0.85 gate. Rather than a hand-written residual or a
    higher ``pull_scale`` floor, this does what a person does: pull the
    computed distance, look at how far the band now reaches, pull the deficit,
    look again.

    Handed to `ClothLinkAttachDragPrimitive.run(extend=...)`, which calls it
    with the current particles after each converged carry. Returns one more
    straight segment along the pull direction, or ``None`` when the band's
    spread has reached the target or the total pull has hit the cap.

    ``target_span`` is where the band's extent along its own axis should end
    up: ``rest_span + target_recovered x (material_length - rest_span)``, the
    same arithmetic as the judge's recovered fraction, measured on the settled
    band -- plus ``recoil_m``. The loop reads the band while it is still HELD
    under tension, and the judge reads it after release and settle; the held
    band is longer by its elastic stretch. Measured 2026-09-05 on the shipped
    layout: 257.9 mm held against 252.9 mm settled, 5 mm (about 2% of the
    band), so a target met while held is missed by 0.08 in recovered fraction
    once let go. ``max_scale`` caps the total pull at that multiple of the
    DESIGN stored material, so an anchor that slides cannot make the loop pull
    for ever.
    """

    def __init__(
        self,
        layout,
        rest_nodes,
        planned,
        *,
        target_recovered: float,
        max_scale: float,
        recoil_m: float = 0.0,
    ) -> None:
        self.layout = layout
        self.axis = int(layout.material_axis)
        self.direction = np.asarray(layout.pull_direction(), dtype=float)
        rest = np.asarray(rest_nodes, dtype=float)[:, self.axis]
        rest_span = float(rest.max() - rest.min())
        material = float(layout.material_length())
        self.target_span = rest_span + float(target_recovered) * (material - rest_span) + float(recoil_m)
        self.cap = float(layout.landmarks()["stored"]) * float(max_scale)
        self.last_target = np.asarray(planned[-1].position, dtype=float)
        self.pulled = float(np.linalg.norm(self.last_target - np.asarray(layout.grasp_point(), dtype=float)))
        self.step_m = float(layout.task_cfg.physical.pull_step_m)
        self.count = 0
        #: ``(span_m, deficit_m, extra_m)`` per call, for the demo's log line.
        self.history: list[tuple[float, float, float]] = []

    def span(self, nodes) -> float:
        along = np.asarray(nodes, dtype=float)[:, self.axis]
        return float(along.max() - along.min())

    def __call__(self, nodes):
        span = self.span(nodes)
        deficit = self.target_span - span
        extra = min(deficit, self.cap - self.pulled)
        if extra < EXTEND_MIN_M:
            self.history.append((span, deficit, 0.0))
            return None
        self.count += 1
        self.pulled += extra
        self.last_target = self.last_target + self.direction * extra
        self.history.append((span, deficit, extra))
        return [
            WaypointTarget(
                label=f"extend_{self.count:02d}",
                position=tuple(float(v) for v in self.last_target),
                steps=max(4, int(round(extra / self.step_m))),
                lifted=False,
                metadata={"span_mm": round(span * 1e3, 1), "deficit_mm": round(deficit * 1e3, 1),
                          "extra_mm": round(extra * 1e3, 1), "pulled_mm": round(self.pulled * 1e3, 1)},
            )
        ]

    def summary(self) -> str:
        return (
            f"extensions={self.count} pulled_mm={self.pulled * 1e3:.1f} cap_mm={self.cap * 1e3:.1f} "
            f"target_span_mm={self.target_span * 1e3:.1f} "
            + " ".join(f"[span={s_ * 1e3:.1f} deficit={d * 1e3:+.1f} extra={e * 1e3:.1f}]" for s_, d, e in self.history)
        )
