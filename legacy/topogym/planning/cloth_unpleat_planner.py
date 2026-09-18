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

from dataclasses import replace

import numpy as np

from topogym.planning.subgoal import PlannedSubgoal
from topogym.planning.waypoint import EpisodePlan, WaypointPlan, WaypointTarget

#: Straight segments the pull is cut into. The path is a straight line, so this
#: buys nothing geometrically -- it exists so the primitive reports its follow
#: error several times across the pull instead of once at the end, which is what
#: catches an anchor that let go halfway.
PULL_SEGMENTS = 8

MOTIONS = ("unfold", "shove", "overpull", "single_pull")

#: Motions that drive only the FIRST leg. With two pleats the task takes a pull
#: continuously from the tail, so stopping after the first stroke should leave the far pleat closed -- the
#: anti-shortcut control that replaced `pull_side` when the 2026-09-08 review took
#: "which end to pull" out of the task. On a one-pleat layout it is the task
#: itself, and the sweep records it as such rather than as a failure.
FIRST_LEG_ONLY = ("single_pull",)

#: Smallest extension worth driving (half a particle): below this the deficit
#: is within the judge's own resolution and another glide would just add lag.
#: One particle (4 mm) was too coarse: the shipped layout's deficit after the
#: planned pull reads 3.9 mm held, and skipping it left the settled band at a
#: recovered fraction of 0.885 (2026-09-05).
EXTEND_MIN_M = 0.002


def _extend_step(layout) -> float:
    """Largest single closed-loop extension, metres (`physical.pull_extend_step_m`).

    5 mm since 2026-09-05. Each extension is followed by `carry_settle_steps` of
    holding still, so a cross that needs twenty of them spends most of its
    episode waiting; the 2026-09-13 duration review made it a knob.
    """
    return float(layout.task_cfg.physical.get("pull_extend_step_m", 0.005))


def pull_waypoints(
    layout,
    *,
    motion: str = "unfold",
    index: int = 0,
    segments: int = PULL_SEGMENTS,
    overpull_scale: float = 1.6,
    start=None,
    distance=None,
) -> list[WaypointTarget]:
    """One pull's path for the grasped end, cut into segments the primitive drives.

    ``index`` picks which pull: a one-pleat layout has one, a two-pleat layout has
    two from the tail, opening the nearer pleat first. The labels carry the index
    so the two legs do not collide in the recorded episode.
    """

    if motion not in MOTIONS:
        raise ValueError(f"motion must be one of {MOTIONS}, got {motion!r}.")

    segments = max(2, int(segments))
    index = int(index)
    start = np.asarray(layout.grasp_point(index) if start is None else start, dtype=float)
    direction = layout.pull_direction(index)

    distance = layout.pull_distance(index) if distance is None else float(distance)
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
    tag = f"pull{index + 1}_" if getattr(layout, "pull_count", 1) > 1 else "pull_"

    out: list[WaypointTarget] = []
    for step_index in range(1, segments + 1):
        fraction = step_index / segments
        point = start + direction * (distance * fraction)
        out.append(
            WaypointTarget(
                label=f"{tag}{step_index:02d}",
                position=tuple(float(v) for v in point),
                steps=per_segment,
                # Nothing leaves the table: the whole point is that the pull is
                # in the plane and friction does the holding.
                lifted=False,
                metadata={
                    "leg": index,
                    "fraction": round(fraction, 4),
                    "travel_mm": round(float(distance * fraction) * 1e3, 2),
                },
            )
        )
    return out


def continuous_pull_waypoints(
    layout, *, motion: str = "unfold", segments: int = PULL_SEGMENTS, overpull_scale: float = 1.6
) -> list[WaypointTarget]:
    """Keep the same attachment while traversing every requested pleat's stroke.

    Each segment starts at the preceding command, not at a newly observed cloth
    edge or a design grasp. Thus no release, regrasp, or positional jump occurs
    at the boundary between pleats.
    """
    count = 1 if motion in FIRST_LEG_ONLY else int(getattr(layout, "pull_count", 1))
    start = layout.grasp_point(0)
    out = []
    diagonal = (getattr(layout, "is_cross", False)
                and str(layout.task_cfg.cloth.cross.get("corner_path", "sequential")) == "diagonal")
    if diagonal:
        delta = sum(layout.pull_direction(i) * layout.pull_distance(i) for i in range(count))
        delta *= -1 if motion == "shove" else overpull_scale if motion == "overpull" else 1
        steps = max(4, int(round(np.linalg.norm(delta) / float(layout.task_cfg.physical.pull_step_m))))
        for step in range(1, segments + 1):
            out.append(WaypointTarget(label=f"cross_diagonal_{step:02d}",
                                     position=tuple(np.asarray(start) + delta * step / segments),
                                     steps=max(1, round(steps / segments)), lifted=False,
                                     metadata={"fraction": step / segments, "axes": count}))
    else:
        for index in range(count):
            segment = pull_waypoints(layout, motion=motion, index=index, segments=segments,
                                     overpull_scale=overpull_scale, start=start)
            out.extend(segment)
            start = segment[-1].position
    lift = float(layout.task_cfg.cloth.cross.get("pull_lift", 0.0)) if getattr(layout, "is_cross", False) else 0.0
    if lift > 0:
        original_start = np.asarray(layout.grasp_point(0), dtype=float)
        raised = original_start + [0, 0, lift]
        steps = max(4, int(round(lift / float(layout.task_cfg.physical.pull_step_m))))
        lower = out[-1].position
        out = [WaypointTarget(label="cross_peel_lift", position=tuple(raised), steps=steps, lifted=True)] + [
            replace(point, position=(point.position[0], point.position[1], point.position[2] + lift), lifted=True)
            for point in out
        ] + [WaypointTarget(label="cross_peel_lower", position=lower, steps=steps, lifted=False)]
    return out


def plan_cloth_unpleat(
    layout, *, motion: str = "unfold", segments: int = PULL_SEGMENTS, overpull_scale: float = 1.6
):
    """Plan one unpleat. Returns ``(legs, EpisodePlan)``.

    ``legs`` contains the initial path: one continuous grasp for a parallel
    pair or cross corner, separate grasps for the cross edge diagnostic. Cross
    corner repair is adaptive: the caller re-observes the other material ends
    only if the settled result still fails the two-axis/layer judge.

    The waypoints are targets for the grasped material in world coordinates --
    where the cloth has to go, not where the hand has to be. The primitive owns
    the offset between the two, because it also owns the promise that the pads
    stop above the cloth and never touch it.
    """

    count = 1 if motion in FIRST_LEG_ONLY else int(getattr(layout, "pull_count", 1))
    continuous = getattr(layout, "continuous_grasp", True)
    legs = [
        continuous_pull_waypoints(
            layout, motion=motion, segments=segments, overpull_scale=overpull_scale
        )
    ] if continuous else [pull_waypoints(layout, motion=motion, index=i, segments=segments,
                                        overpull_scale=overpull_scale) for i in range(count)]
    marks = layout.landmarks()
    stored = [float(p["stored"]) for p in marks["pleats"]]
    subgoals = tuple(
        PlannedSubgoal(
            subgoal_id=f"unpleat_{motion}_{index + 1}",
            kind="unpleat_cloth",
            entity=str(layout.task_cfg.cloth.name),
            target={
                "grasp": tuple(float(v) for v in layout.grasp_point(index)),
                "place": tuple(float(v) for v in leg[-1].position),
            },
            tolerance=float(layout.task_cfg.cloth.particle_size),
            metadata={
                "motion": motion,
                "leg": index,
                "stored_m": (sum(layout.pull_distance(i) for i in range(count)) if continuous
                             else layout.pull_distance(index)) / float(layout.task_cfg.physical.pull_scale),
            },
        )
        for index, leg in enumerate(legs)
    )
    waypoint_plan = WaypointPlan(
        plan_id=f"cloth_unpleat_{motion}",
        waypoints=tuple(point for leg in legs for point in leg),
        metadata={
            "planner": "cloth_unpleat_edge_pull",
            "motion": motion,
            "segments": segments,
            "legs": len(legs),
            "continuous_grasp": continuous,
            "adaptive_repair_corners": bool(getattr(layout, "is_cross", False)
                and continuous and motion == "unfold"
                and layout.task_cfg.cloth.cross.get("repair_corners", False)),
            "pleats": int(marks["count"]),
            "pull_mm": [round(layout.pull_distance(i) * 1e3, 1) for i in range(count)],
            "steps": [int(layout.pull_steps(i)) for i in range(count)],
        },
    )
    episode_plan = EpisodePlan(
        task_id="cloth_unpleat",
        subgoals=subgoals,
        waypoint_plan=waypoint_plan,
        plan_id=f"cloth_unpleat_{motion}",
        metadata={
            "stored_mm": [round(v * 1e3, 1) for v in stored],
            "step_m": float(layout.pull_distance(0) / layout.pull_steps(0)),
        },
    )
    return legs, episode_plan


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

    ``rest_nodes`` is the episode's original settled cloud on every leg. The
    target adds the cumulative design material of all pleats attempted so far;
    the preceding release cannot erase its unpaid length. ``recoil_m`` is an
    additional held-span allowance. ``max_scale`` allocates travel per pleat and the
    demo also intersects that cap with room from the observed grasp. The second
    leg may spend the first leg's unused allocation: ``previous_pulled`` records
    what the earlier grasps commanded, keeping the total budget unchanged.

    For a continuous grasp across both pleats, ``index`` identifies the last
    pleat to open and ``start_point`` is the ORIGINAL grasp. This counts the
    entire commanded displacement against the cumulative travel cap.

    With ``require_local_flat``, the oracle tracks initially elevated particles
    selected geometrically after remeshing. A remaining elevated fold requests
    5 mm increments even if elastic stretch elsewhere satisfied the global
    span. This is simulation supervision, not a point-cloud-only policy: it
    uses stable particle identities, never a guessed rectangular grid.
    """

    def __init__(
        self,
        layout,
        rest_nodes,
        planned,
        *,
        index: int = 0,
        target_recovered: float,
        max_scale: float,
        recoil_m: float = 0.0,
        require_local_flat: bool = False,
        previous_pulled: float = 0.0,
        start_point=None,
    ) -> None:
        self.layout = layout
        self.index = int(index)
        self.axis = int(layout.material_axis)
        self.direction = np.asarray(layout.pull_direction(self.index), dtype=float)
        rest = np.asarray(rest_nodes, dtype=float)[:, self.axis]
        rest_span = float(rest.max() - rest.min())
        # rest_nodes is the episode's initial settled cloud for EVERY leg.
        # Re-basing on the preceding release silently forgave its unpaid material.
        cumulative = sum(float(layout.pull_distance(i)) / float(layout.task_cfg.physical.pull_scale)
                         for i in range(self.index + 1))
        self.target_span = rest_span + float(target_recovered) * cumulative + float(recoil_m)
        self.cap = cumulative * float(max_scale) - float(previous_pulled)
        self.last_target = np.asarray(planned[-1].position, dtype=float)
        self.pulled = float(
            np.linalg.norm(self.last_target - np.asarray(
                layout.grasp_point(self.index) if start_point is None else start_point, dtype=float))
        )
        self.step_m = float(layout.task_cfg.physical.pull_step_m)
        self.count = 0
        #: ``(span_m, deficit_m, extra_m)`` per call, for the demo's log line.
        self.history: list[tuple[float, float, float]] = []
        self.fold_indices = np.array([], dtype=int)
        self.local_height = float("nan")
        self.table_z = float(layout.table_z)
        if require_local_flat:
            # Tag the elevated material geometrically AFTER solver remeshing.
            # Particle identities remain fixed during the episode; no rectangular
            # grid or guessed material ordering is used here.
            cloud = np.asarray(rest_nodes, dtype=float)
            centre = np.asarray(layout.band_centre(), dtype=float)
            along = (cloud[:, self.axis] - centre[self.axis]) * layout.band_sign
            particle = float(layout.task_cfg.cloth.particle_size)
            selected = np.zeros(len(cloud), dtype=bool)
            for pleat in layout.landmarks()["pleats"][-(self.index + 1):]:
                selected |= (along >= pleat["crest_s"] - particle) & (along <= pleat["landing_s"] + particle)
            selected &= cloud[:, 2] > layout.table_z + 0.75 * particle
            self.fold_indices = np.flatnonzero(selected)
            if not self.fold_indices.size:
                raise ValueError("no elevated material in the target pleat at episode start")
            self.flat_height = float(layout.table_z) + 1.125 * particle
        self.stop_reason = "not_called"

    def span(self, nodes) -> float:
        along = np.asarray(nodes, dtype=float)[:, self.axis]
        return float(along.max() - along.min())

    def __call__(self, nodes):
        span = self.span(nodes)
        deficit = self.target_span - span
        local_closed = False
        if self.fold_indices.size:
            self.local_height = float(np.quantile(np.asarray(nodes)[self.fold_indices, 2], 0.95))
            local_closed = self.local_height > self.flat_height
            if local_closed:
                deficit = max(deficit, _extend_step(self.layout))
        extra = min(deficit, self.cap - self.pulled)
        if self.fold_indices.size:
            extra = min(extra, _extend_step(self.layout))
        if extra < EXTEND_MIN_M:
            self.stop_reason = "target" if deficit < EXTEND_MIN_M else "cap"
            self.history.append((span, deficit, 0.0))
            return None
        self.count += 1
        self.pulled += extra
        self.last_target = self.last_target + self.direction * extra
        self.history.append((span, deficit, extra))
        return [
            WaypointTarget(
                label=f"extend{self.index + 1}_{self.count:02d}",
                position=tuple(float(v) for v in self.last_target),
                steps=max(4, int(round(extra / self.step_m))),
                lifted=False,
                metadata={"span_mm": round(span * 1e3, 1), "deficit_mm": round(deficit * 1e3, 1),
                          "extra_mm": round(extra * 1e3, 1), "pulled_mm": round(self.pulled * 1e3, 1)},
            )
        ]

    def summary(self) -> str:
        return (
            f"through_pleat={self.index + 1} extensions={self.count} pulled_mm={self.pulled * 1e3:.1f} "
            f"cap_mm={self.cap * 1e3:.1f} "
            f"stop={self.stop_reason} "
            f"local_height_mm={(self.local_height - self.table_z) * 1e3:.1f} "
            f"target_span_mm={self.target_span * 1e3:.1f} "
            + " ".join(f"[span={s_ * 1e3:.1f} deficit={d * 1e3:+.1f} extra={e * 1e3:.1f}]" for s_, d, e in self.history)
        )


class CrossPullExtender(PullExtender):
    """Independent material deficit on each orthogonal axis, last fold first."""

    def __init__(self, layout, rest_nodes, planned, *, index, start_point, material_nodes,
                 max_drift_m=0.0, anchor_ends=None, anchor_reference_nodes=None,
                 direction_sign=1.0, **kwargs):
        from topogym.tasks_legacy.deformation._cloth_cross_geometry import cross_dimensions
        kwargs.pop("previous_pulled", None)
        kwargs.pop("require_local_flat", None)
        super().__init__(layout, rest_nodes, planned, index=index, start_point=start_point,
                         require_local_flat=False, **kwargs)
        # -1 pulls this axis from the sheet's OTHER edge, away from the free end:
        # the second-round repair that takes the corner opposite the ones already
        # used, so its tow runs the other way and cancels the first one's
        # (2026-09-13 proposal). Extensions must follow the same sign.
        self.direction = self.direction * float(direction_sign)
        self.axis = layout.pull_axis(index)
        self.material_nodes = np.asarray(material_nodes)
        # Same anchor watch as `CrossCornerExtender`, for the repair legs: the
        # material corner opposite the grasped one (``anchor_ends`` is that
        # corner's sign pair, as `observe_corner` takes it). The 2026-09-13 drift
        # trial stopped the corner leg at 21.7 mm and the repair leg then towed
        # the sheet another 37 mm on its own, so the watch has to be on both.
        self.max_drift_m = float(max_drift_m)
        self.anchor_drift = 0.0
        self.anchor_rest = None
        if anchor_ends is not None:
            dims = cross_dimensions(layout.task_cfg)
            xy = layout.band_centre().copy()
            for i in range(2):
                xy[layout.pull_axis(i)] += anchor_ends[i] * layout.pull_end_sign(i) * (
                    dims[1 - i][0] / 2 - float(layout.task_cfg.grasp.edge_inset))
            self.anchor_ids = np.linalg.norm(self.material_nodes[:, :2] - xy, axis=1) < 0.03
            # Measured from where the anchor corner is when THIS leg starts, not
            # from birth: an earlier leg has already moved the sheet (that is why
            # this leg exists), and the 2026-09-13 second trial read a 40.8 mm
            # "drift" on a repair leg before it had pulled anything.
            reference = np.asarray(rest_nodes if anchor_reference_nodes is None else anchor_reference_nodes)
            if self.anchor_ids.any():
                self.anchor_rest = np.median(reference[self.anchor_ids, :2], axis=0)
        length, span = cross_dimensions(layout.task_cfg)[1 - index]
        # Geometry fixes the full material dimension. A previous orthogonal
        # pull cannot erase this axis's shortfall by changing its reference.
        self.target_span = length + float(kwargs.get("recoil_m", 0.0))
        self.cap = (length - span) * float(kwargs["max_scale"])
        cloud = np.asarray(rest_nodes)
        particle = float(layout.task_cfg.cloth.particle_size)
        selected = cloud[:, 2] > layout.table_z + 0.75 * particle
        if index == 0:
            fold = layout.task_cfg.cloth.cross.first
            _, first_span = cross_dimensions(layout.task_cfg)[0]
            along = (cloud[:, layout.material_axis] - layout.band_centre()[layout.material_axis]) * layout.band_sign
            # The first fold is deliberately still closed at this stage. Judge
            # the second fold's wings, excluding the crossing and first strip.
            lo = float(fold.lead) - float(fold.depth) - float(fold.radius) - first_span / 2
            hi = float(fold.lead) + float(fold.radius) - first_span / 2
            selected &= (along < lo - 2 * particle) | (along > hi + 2 * particle)
        self.fold_indices = np.flatnonzero(selected)
        if not self.fold_indices.size:
            raise ValueError("cross fold has no elevated material after settling")
        self.flat_height = layout.table_z + 1.125 * particle

    def span(self, nodes):
        from topogym.verification.cloth_unpleat_verifier import material_dimensions
        cloth = self.layout.task_cfg.cloth
        spans, _ = material_dimensions(self.material_nodes, nodes, particle_size=float(cloth.particle_size),
                                       material_axis=self.layout.material_axis,
                                       length=float(cloth.material_length), width=float(cloth.width))
        return spans[1 - self.index]

    def __call__(self, nodes):
        if self.anchor_rest is not None:
            self.anchor_drift = float(np.linalg.norm(
                np.median(np.asarray(nodes)[self.anchor_ids, :2], axis=0) - self.anchor_rest))
            if self.max_drift_m > 0.0 and self.anchor_drift > self.max_drift_m:
                self.stop_reason = "drift"
                return None
        return super().__call__(nodes)

    def summary(self) -> str:
        return super().summary() + f" anchor_drift_mm={self.anchor_drift * 1000:.1f}"


class CrossCornerExtender:
    """Keep the free corner bound while paying each material axis's deficit."""

    def __init__(self, layout, rest_nodes, planned, *, index, start_point, material_nodes,
                 max_scale, recoil_m=0.0, max_drift_m=0.0, **kwargs):
        from topogym.tasks_legacy.deformation._cloth_cross_geometry import cross_dimensions
        self.layout = layout
        self.material_nodes = np.asarray(material_nodes)
        # The sheet's anchor: the material corner diagonally opposite the grasped
        # one, which nothing but table friction holds. A pull that unfolds the
        # sheet leaves it where it was; a pull that tows the sheet moves it by the
        # tow. Watched per extension so the leg can give up the corner early --
        # 2026-09-13 review: a cross sheet pulled from one corner slid 42-83 mm,
        # a band 2-9 mm, and slowing the pull did not change it. ``max_drift_m``
        # 0 turns the watch off.
        self.max_drift_m = float(max_drift_m)
        anchor_xy = layout.band_centre().copy()
        for i in range(2):
            anchor_xy[layout.pull_axis(i)] -= layout.pull_end_sign(i) * (cross_dimensions(layout.task_cfg)[1-i][0] / 2)
        self.anchor_ids = np.linalg.norm(self.material_nodes[:, :2] - anchor_xy, axis=1) < 0.03
        self.anchor_rest = np.median(np.asarray(rest_nodes)[self.anchor_ids, :2], axis=0) if self.anchor_ids.any() else None
        self.anchor_drift = 0.0
        self.last_target = np.asarray(planned[-1].position)
        self.active_count = index + 1
        self.dims = cross_dimensions(layout.task_cfg)
        self.targets = np.array([d[0] + recoil_m for d in self.dims])[::-1]
        self.caps = np.array([(d[0] - d[1]) * max_scale for d in self.dims])[::-1]
        self.spent = np.array([float((self.last_target - start_point) @ layout.pull_direction(i))
                               for i in range(2)])
        self.cap = float(self.caps[:self.active_count].sum())
        self.pulled = float(self.spent.sum())
        self.count = 0
        self.history = []
        self.stop_reason = "not_called"
        self.masks = []
        cloth = layout.task_cfg.cloth
        self.flat_height = layout.table_z + 1.125 * float(cloth.particle_size)
        for i, key in enumerate(("second", "first")):
            f = cloth.cross[key]
            coordinate = (self.material_nodes[:, layout.pull_axis(i)]
                          - layout.band_centre()[layout.pull_axis(i)]) * layout.pull_end_sign(i)
            coordinate += self.dims[1-i][0] / 2
            self.masks.append((coordinate >= float(f.lead))
                              & (coordinate <= float(f.lead + f.depth + 2*np.pi*f.radius)))

    def __call__(self, nodes):
        from topogym.verification.cloth_unpleat_verifier import material_dimensions
        from topogym.tasks_legacy.deformation._cloth_unpleat_geometry import pull_room
        cloth = self.layout.task_cfg.cloth
        spans, _ = material_dimensions(self.material_nodes, nodes, particle_size=float(cloth.particle_size),
                                       material_axis=self.layout.material_axis,
                                       length=float(cloth.material_length), width=float(cloth.width))
        deficits = self.targets - np.asarray(spans)[::-1]
        heights = np.array([np.quantile(np.asarray(nodes)[mask, 2], 0.95) for mask in self.masks])
        wanted = np.maximum(deficits, np.where(heights > self.flat_height, _extend_step(self.layout), 0.0))
        extras = np.zeros(2)
        for i in range(self.active_count):
            room = pull_room(self.layout.task_cfg, self.last_target[:2] - self.layout.origin[:2],
                             direction=self.layout.pull_direction(i)[:2])
            extras[i] = min(wanted[i], self.caps[i] - self.spent[i], room, _extend_step(self.layout))
        self.history.append((np.asarray(spans)[::-1].tolist(), deficits.tolist(),
                             (heights - self.layout.table_z).tolist()))
        if self.anchor_rest is not None:
            self.anchor_drift = float(np.linalg.norm(
                np.median(np.asarray(nodes)[self.anchor_ids, :2], axis=0) - self.anchor_rest))
            if self.max_drift_m > 0.0 and self.anchor_drift > self.max_drift_m:
                self.stop_reason = "drift"
                return None
        axis = int(np.argmax(extras))
        if extras[axis] < EXTEND_MIN_M:
            self.stop_reason = "target" if max(wanted[:self.active_count]) < EXTEND_MIN_M else "cap"
            return None
        extra = float(extras[axis])
        self.count += 1
        self.spent[axis] += extra
        self.pulled = float(self.spent.sum())
        self.last_target = self.last_target + self.layout.pull_direction(axis) * extra
        return [WaypointTarget(label=f"cross_extend{axis + 1}_{self.count:02d}",
                               position=tuple(float(v) for v in self.last_target),
                               steps=max(4, int(round(extra / float(self.layout.task_cfg.physical.pull_step_m)))),
                               lifted=False, metadata={"axis": self.layout.pull_axis(axis), "extra_mm": extra * 1000})]

    def summary(self):
        return (f"through_pleat={self.active_count} extensions={self.count} "
                f"pulled_mm={self.pulled * 1000:.1f} cap_mm={self.cap * 1000:.1f} "
                f"stop={self.stop_reason} per_axis_mm={(self.spent * 1000).tolist()} "
                f"anchor_drift_mm={self.anchor_drift * 1000:.1f} "
                f"last_reading={self.history[-1] if self.history else None}")
