from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Mapping, Sequence

import numpy as np

from .subgoal import PlannedSubgoal


def arc_route_points(start, end, sweep: float, samples: int | None = None) -> list:
    """The points of a circular arc from ``start`` to ``end``, ``start`` excluded.

    A route that has to be a fixed LENGTH -- a rope's rest shape, where the
    length is the whole point -- cannot be written as a list of coordinates and
    still be adjustable: rope_winding's spawn arc was ten hand-computed points,
    and every change of turn count needs a different length between the same two
    ends. One sweep angle says it instead, and the arithmetic is here rather than
    in the config comment where it cannot be checked.

    ``sweep`` is in radians, signed, counter-clockwise seen from +z, and it is
    the free parameter: with the ends fixed, a bigger sweep bulges the arc and
    lengthens it (length = chord * sweep / (2 sin(sweep/2))). z is interpolated
    linearly, so a level route stays level.
    """

    start = np.asarray(start, dtype=float)
    end = np.asarray(end, dtype=float)
    sweep = float(sweep)
    chord = end[:2] - start[:2]
    span = float(np.linalg.norm(chord))
    if span <= 1e-9:
        raise ValueError("an arc route point needs two distinct ends.")
    if not 1e-6 < abs(sweep) < 2.0 * np.pi - 1e-6:
        raise ValueError(
            f"arc sweep must be within (0, 360) degrees, got {np.degrees(sweep):.1f}."
        )
    radius = span / (2.0 * np.sin(abs(sweep) / 2.0))
    middle = 0.5 * (start[:2] + end[:2])
    normal = np.array([-chord[1], chord[0]], dtype=float) / span
    # Two circles of this radius pass through both ends. Which one is the arc
    # depends on the sweep's sign AND on whether it is the minor or the major
    # arc, so rather than case-split, take the centre whose actual sweep is the
    # one asked for.
    height = float(np.sqrt(max(radius * radius - 0.25 * span * span, 0.0)))
    for offset in (height, -height):
        centre = middle + normal * offset
        first = float(np.arctan2(start[1] - centre[1], start[0] - centre[0]))
        last = float(np.arctan2(end[1] - centre[1], end[0] - centre[0]))
        turned = (last - first) % (2.0 * np.pi)
        if sweep < 0.0:
            turned -= 2.0 * np.pi
        if abs(turned - sweep) < 1e-6:
            break
    else:  # pragma: no cover - unreachable for a valid sweep
        raise ValueError(f"no arc of {np.degrees(sweep):.1f} degrees joins those ends.")
    if samples is None:
        # ~2 degrees a step: the sagitta against the true circle is then under
        # 0.1 mm at any radius this repo uses, so the rope mesh is built on a
        # circle rather than on a coarse chord chain.
        samples = max(8, int(round(abs(np.degrees(sweep)) / 2.0)))
    fractions = np.linspace(0.0, 1.0, int(samples) + 1)[1:]
    return [
        np.array(
            [
                centre[0] + radius * np.cos(first + sweep * t),
                centre[1] + radius * np.sin(first + sweep * t),
                float(start[2] + (end[2] - start[2]) * t),
            ],
            dtype=float,
        )
        for t in fractions
    ]


def helix_route_points(
    start,
    center,
    radius: float,
    turns: float,
    climb: float,
    sign: float,
    *,
    z_start: float | None = None,
    samples_per_turn: int | None = None,
) -> list:
    """A rope route that is already wound on a post, ``start`` excluded.

    rope_unwinding's spawn shape (task book 2.5): the rope runs from ``start``
    (the anchor) straight to the post's circle of ``radius`` about ``center``,
    meeting it TANGENTIALLY, then goes ``turns`` times around in the sense of
    ``sign`` (+1 counter-clockwise seen from +z), rising ``climb`` per turn from
    ``z_start`` (default: the start point's own z). The first point returned is
    the tangent point itself, at ``z_start``; the last is the top of the helix.

    Written as one entry so that the number of turns is a config number the
    planner also reads (`winding.start_turns`), rather than a list of hand-typed
    coordinates that has to be regenerated whenever it changes.
    """

    start = np.asarray(start, dtype=float)
    center = np.asarray(center, dtype=float)
    radius = float(radius)
    sign = 1.0 if float(sign) >= 0.0 else -1.0
    turns = float(turns)
    if turns <= 0.0:
        raise ValueError(f"a helix route point needs turns > 0, got {turns}.")
    offset = start[:2] - center[:2]
    distance = float(np.linalg.norm(offset))
    if distance <= radius:
        raise ValueError(
            f"the helix's start point is {distance:.4f} from the post axis, inside "
            f"the {radius:.4f} wrap radius; it has to approach from outside."
        )
    # Of the two tangent points seen from `start`, the one where the circle's
    # tangent in the winding sense points AWAY from `start`: the rope arrives
    # along that tangent and keeps going around.
    bearing = float(np.arctan2(offset[1], offset[0]))
    first = bearing + sign * float(np.arccos(radius / distance))
    base_z = float(start[2]) if z_start is None else float(z_start)
    if samples_per_turn is None:
        samples_per_turn = 180  # ~2 degrees a step, as `arc_route_points`
    count = max(8, int(round(turns * int(samples_per_turn))))
    fractions = np.linspace(0.0, 1.0, count + 1)
    sweep = sign * 2.0 * np.pi * turns
    return [
        np.array(
            [
                center[0] + radius * np.cos(first + sweep * t),
                center[1] + radius * np.sin(first + sweep * t),
                base_z + climb * turns * t,
            ],
            dtype=float,
        )
        for t in fractions
    ]


@dataclass(frozen=True)
class WaypointTarget:
    """One physical target point for a primitive or motion executor."""

    label: str
    position: tuple[float, float, float]
    steps: int | None = None
    yaw: float | None = None
    lifted: bool = False
    metadata: Mapping[str, Any] = field(default_factory=dict)

    @classmethod
    def from_sequence(
        cls,
        label: str,
        position: Sequence[float],
        *,
        steps: int | None = None,
        yaw: float | None = None,
        lifted: bool = False,
        metadata: Mapping[str, Any] | None = None,
    ) -> "WaypointTarget":
        if len(position) != 3:
            raise ValueError("WaypointTarget position must contain 3 values.")
        return cls(
            label=str(label),
            position=tuple(float(value) for value in position),
            steps=None if steps is None else int(steps),
            yaw=None if yaw is None else float(yaw),
            lifted=bool(lifted),
            metadata=dict(metadata or {}),
        )

    def metadata_dict(self) -> dict[str, Any]:
        return dict(self.metadata)


@dataclass(frozen=True)
class WaypointPlan:
    """Ordered waypoints for one primitive execution sequence."""

    waypoints: tuple[WaypointTarget, ...]
    plan_id: str = "default"
    metadata: Mapping[str, Any] = field(default_factory=dict)

    def limited(self, max_waypoints: int | None) -> "WaypointPlan":
        if max_waypoints is None:
            return self
        max_i = max(0, int(max_waypoints))
        return WaypointPlan(
            waypoints=self.waypoints[:max_i],
            plan_id=self.plan_id,
            metadata=dict(self.metadata),
        )

    def labels(self) -> tuple[str, ...]:
        return tuple(waypoint.label for waypoint in self.waypoints)

    def metadata_dict(self) -> dict[str, Any]:
        return dict(self.metadata)


@dataclass(frozen=True)
class EpisodePlan:
    """High-level subgoals plus the waypoint expansion used for execution."""

    task_id: str
    subgoals: tuple[PlannedSubgoal, ...] = ()
    waypoint_plan: WaypointPlan | None = None
    plan_id: str = "default"
    metadata: Mapping[str, Any] = field(default_factory=dict)

    @property
    def waypoints(self) -> tuple[WaypointTarget, ...]:
        if self.waypoint_plan is None:
            return ()
        return self.waypoint_plan.waypoints

    def metadata_dict(self) -> dict[str, Any]:
        return dict(self.metadata)
