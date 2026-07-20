from __future__ import annotations

from dataclasses import dataclass

from .subgoal import PlannedSubgoal
from .waypoint import EpisodePlan, WaypointPlan, WaypointTarget


@dataclass(frozen=True)
class SwapMoveCommand:
    """Resolved pick-place move for the Swap task."""

    block_name: str
    source_slot: int
    target_slot: int
    source_xy: tuple[float, float]
    target_xy: tuple[float, float]

    def to_episode_plan(self) -> EpisodePlan:
        subgoal = PlannedSubgoal(
            subgoal_id=f"{self.block_name}_{self.source_slot}_to_{self.target_slot}",
            kind="pick_place",
            entity=self.block_name,
            target={
                "source_slot": self.source_slot,
                "target_slot": self.target_slot,
                "source_xy": self.source_xy,
                "target_xy": self.target_xy,
            },
        )
        waypoint_plan = WaypointPlan(
            plan_id="swap_pick_place",
            waypoints=(
                WaypointTarget(
                    label="source_pick",
                    position=(self.source_xy[0], self.source_xy[1], 0.0),
                    metadata={"slot": self.source_slot, "entity": self.block_name},
                ),
                WaypointTarget(
                    label="target_place",
                    position=(self.target_xy[0], self.target_xy[1], 0.0),
                    metadata={"slot": self.target_slot, "entity": self.block_name},
                ),
            ),
            metadata={"planner": "swap_oracle_pick_place"},
        )
        return EpisodePlan(
            task_id="swap",
            subgoals=(subgoal,),
            waypoint_plan=waypoint_plan,
            plan_id="swap_oracle_pick_place",
            metadata={
                "block_name": self.block_name,
                "source_slot": self.source_slot,
                "target_slot": self.target_slot,
            },
        )


def plan_swap_move(
    layout,
    *,
    block_name: str | None = None,
    source_slot: int | None = None,
    target_slot: int | None = None,
) -> tuple[SwapMoveCommand, EpisodePlan]:
    """Resolve a Swap oracle move without touching Genesis state."""

    resolved_block = str(block_name or layout.block_to_move)
    resolved_source = int(layout.source_slot if source_slot is None else source_slot)
    resolved_target = int(layout.target_slot if target_slot is None else target_slot)

    block_names = tuple(layout.block_names())
    slot_indices = tuple(layout.slot_indices())
    if resolved_block not in block_names:
        raise ValueError(f"Unknown block {resolved_block!r}; choices: {block_names}.")
    if resolved_source not in slot_indices or resolved_target not in slot_indices:
        raise ValueError(f"Slots must be chosen from {slot_indices}.")
    if resolved_source == resolved_target:
        raise ValueError("source_slot and target_slot must be different.")

    source_xy = tuple(float(value) for value in layout.slot_xy(resolved_source))
    target_xy = tuple(float(value) for value in layout.slot_xy(resolved_target))
    command = SwapMoveCommand(
        block_name=resolved_block,
        source_slot=resolved_source,
        target_slot=resolved_target,
        source_xy=source_xy,
        target_xy=target_xy,
    )
    return command, command.to_episode_plan()
