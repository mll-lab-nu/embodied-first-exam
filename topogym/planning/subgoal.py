from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Mapping


@dataclass(frozen=True)
class PlannedSubgoal:
    """A semantic action target before it is expanded into robot waypoints."""

    subgoal_id: str
    kind: str
    target: Any
    actor: str = "robot"
    entity: str | None = None
    tolerance: float | None = None
    metadata: Mapping[str, Any] = field(default_factory=dict)

    def label(self) -> str:
        if self.entity:
            return f"{self.kind}:{self.entity}:{self.subgoal_id}"
        return f"{self.kind}:{self.subgoal_id}"

    def metadata_dict(self) -> dict[str, Any]:
        return dict(self.metadata)
