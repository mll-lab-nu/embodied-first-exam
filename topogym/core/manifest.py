from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class EntityManifest:
    """Name-to-Genesis-handle registry shared across builders and controllers."""

    entities: dict[str, Any] = field(default_factory=dict)

    def add(self, name: str, entity: Any) -> Any:
        if name in self.entities:
            raise KeyError(f"Entity {name!r} is already registered.")
        self.entities[name] = entity
        return entity

    def get(self, name: str) -> Any:
        try:
            return self.entities[name]
        except KeyError as exc:
            available = ", ".join(sorted(self.entities))
            raise KeyError(f"Unknown entity {name!r}. Available: {available}") from exc

    def as_dict(self) -> dict[str, Any]:
        return dict(self.entities)
