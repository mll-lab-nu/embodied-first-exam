from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from topogym.tasks.legacy.peeling import PeelingScene


@dataclass(frozen=True)
class PeelingPuzzleState:
    peeled: tuple[str, ...]
    remaining: tuple[str, ...]
    active_films: tuple[str, ...]
    blocked_by: dict[str, tuple[str, ...]]

    @property
    def is_terminal(self) -> bool:
        return len(self.remaining) == 0

    def reward(self, *, success_bonus: float = 10.0) -> float:
        return (float(success_bonus) if self.is_terminal else 0.0) - float(len(self.remaining))

    def to_info(self) -> dict[str, Any]:
        return {
            "peeled": list(self.peeled),
            "remaining": list(self.remaining),
            "active_films": list(self.active_films),
            "blocked_by": {name: list(blockers) for name, blockers in self.blocked_by.items()},
            "terminal": bool(self.is_terminal),
        }


@dataclass(frozen=True)
class PeelingPuzzleEvaluator:
    """Evaluate the Level 1 symbolic peeling state."""

    def classify(self, peeling_scene: PeelingScene) -> PeelingPuzzleState:
        layout = peeling_scene.layout
        peeled = tuple(peeling_scene.peeled)
        remaining = tuple(name for name in layout.film_names() if name not in peeled)
        blocked_by = {
            name: layout.higher_overlapping_films(name, peeled=peeled)
            for name in remaining
        }
        active = layout.active_film_names(peeled=peeled)
        return PeelingPuzzleState(
            peeled=peeled,
            remaining=remaining,
            active_films=active,
            blocked_by=blocked_by,
        )

    def is_success(self, peeling_scene: PeelingScene) -> bool:
        return self.classify(peeling_scene).is_terminal
