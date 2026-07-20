from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Mapping, Sequence

from .subgoal import PlannedSubgoal


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
