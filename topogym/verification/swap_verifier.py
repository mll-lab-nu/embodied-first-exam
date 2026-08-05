from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import numpy as np

from topogym.tasks.legacy.swap import SwapScene


@dataclass(frozen=True)
class SwapPuzzleState:
    """Discrete slot assignment for Swap, independent from the robot."""

    assignment: dict[str, int | None]
    target_assignment: dict[str, int]
    empty_slots: tuple[int, ...]
    invalid_blocks: tuple[str, ...]
    duplicate_slots: dict[int, tuple[str, ...]]

    @property
    def is_valid(self) -> bool:
        return not self.invalid_blocks and not self.duplicate_slots

    @property
    def mismatched_blocks(self) -> tuple[str, ...]:
        return tuple(
            name
            for name, target_slot in self.target_assignment.items()
            if self.assignment.get(name) != target_slot
        )

    @property
    def is_terminal(self) -> bool:
        return self.is_valid and not self.mismatched_blocks

    def reward(self, *, success_bonus: float = 10.0) -> float:
        penalty = float(len(self.mismatched_blocks))
        penalty += 2.0 * float(len(self.invalid_blocks))
        penalty += 2.0 * float(sum(max(0, len(names) - 1) for names in self.duplicate_slots.values()))
        return (success_bonus if self.is_terminal else 0.0) - penalty

    def to_info(self) -> dict[str, Any]:
        return {
            "assignment": dict(self.assignment),
            "target_assignment": dict(self.target_assignment),
            "empty_slots": list(self.empty_slots),
            "invalid_blocks": list(self.invalid_blocks),
            "duplicate_slots": {slot: list(names) for slot, names in self.duplicate_slots.items()},
            "mismatched_blocks": list(self.mismatched_blocks),
            "is_valid": self.is_valid,
            "terminal": self.is_terminal,
        }


@dataclass(frozen=True)
class SwapPuzzleEvaluator:
    """Map continuous block poses to the discrete Swap puzzle state."""

    tolerance_xy: float

    def classify(self, swap_scene: SwapScene) -> SwapPuzzleState:
        layout = swap_scene.layout
        slot_xy = {
            int(slot.index): layout.slot_pos(int(slot.index))[:2]
            for slot in layout.cfg.slots
        }
        target_assignment = layout.target_assignment()

        assignment: dict[str, int | None] = {}
        invalid_blocks: list[str] = []
        occupied: dict[int, list[str]] = {slot_index: [] for slot_index in slot_xy}
        for block_name in layout.cfg.blocks.keys():
            pos = _entity_pos(swap_scene.manifest.get(block_name))
            distances = {
                slot_index: float(np.linalg.norm(pos[:2] - xy))
                for slot_index, xy in slot_xy.items()
            }
            nearest_slot = min(distances, key=distances.get)
            if distances[nearest_slot] <= float(self.tolerance_xy):
                assignment[str(block_name)] = int(nearest_slot)
                occupied[int(nearest_slot)].append(str(block_name))
            else:
                assignment[str(block_name)] = None
                invalid_blocks.append(str(block_name))

        duplicate_slots = {
            slot_index: tuple(names)
            for slot_index, names in occupied.items()
            if len(names) > 1
        }
        empty_slots = tuple(
            slot_index
            for slot_index, names in occupied.items()
            if not names
        )
        return SwapPuzzleState(
            assignment=assignment,
            target_assignment=target_assignment,
            empty_slots=empty_slots,
            invalid_blocks=tuple(invalid_blocks),
            duplicate_slots=duplicate_slots,
        )

    def is_success(self, swap_scene: SwapScene) -> bool:
        return self.classify(swap_scene).is_terminal

    def reward(self, swap_scene: SwapScene) -> float:
        return self.classify(swap_scene).reward()


def _entity_pos(entity) -> np.ndarray:
    value = entity.get_pos()
    if hasattr(value, "detach"):
        value = value.detach().cpu().numpy()
    return np.asarray(value).reshape(-1, 3)[0]


@dataclass(frozen=True)
class SwapSuccessChecker:
    """Simple first success check: moved block center is near target slot."""

    tolerance_xy: float

    def is_success(self, swap_scene: SwapScene) -> bool:
        return SwapPuzzleEvaluator(tolerance_xy=self.tolerance_xy).is_success(swap_scene)
