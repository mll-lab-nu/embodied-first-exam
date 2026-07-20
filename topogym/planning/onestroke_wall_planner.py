from __future__ import annotations

from dataclasses import dataclass

from .subgoal import PlannedSubgoal
from .waypoint import EpisodePlan, WaypointPlan, WaypointTarget

EdgeKey = tuple[int, int, int, int]


def edge_name(edge_key: EdgeKey) -> str:
    row_a, col_a, row_b, col_b = edge_key
    return f"({row_a},{col_a})-({row_b},{col_b})"


@dataclass(frozen=True)
class OneStrokeWallCommand:
    """One physical wall-block placement in a OneStroke separator plan."""

    wall_index: int
    block_name: str
    edge_key: EdgeKey
    target_xy: tuple[float, float]
    target_yaw: float
    orientation: str

    @property
    def edge_label(self) -> str:
        return edge_name(self.edge_key)


def _separator_edge_keys(layout) -> tuple[EdgeKey, ...]:
    labels = layout.cell_labels()
    color_a = layout.color_a_label()
    separator: list[EdgeKey] = []

    # Prefer the configured target order.  Filtering keeps helper gray-vs-blue
    # targets out of the default red/blue separator plan.
    configured_edges = tuple(layout.target_edge_keys())
    candidate_edges = configured_edges or layout.all_edge_keys()
    for edge_key in candidate_edges:
        row_a, col_a, row_b, col_b = edge_key
        if (str(labels[row_a][col_a]) == color_a) != (
            str(labels[row_b][col_b]) == color_a
        ):
            separator.append(edge_key)
    return tuple(separator)


def plan_onestroke_separator(
    layout,
    *,
    max_walls: int | None = None,
) -> tuple[tuple[OneStrokeWallCommand, ...], EpisodePlan]:
    """Plan the full rigid wall-block separator sequence."""

    edge_keys = _separator_edge_keys(layout)
    if len(edge_keys) > layout.wall_count:
        raise ValueError(
            f"Separator needs {len(edge_keys)} walls, "
            f"but only {layout.wall_count} are configured."
        )
    if max_walls is not None:
        if int(max_walls) <= 0:
            raise ValueError("max_walls must be positive.")
        edge_keys = edge_keys[: int(max_walls)]

    commands: list[OneStrokeWallCommand] = []
    subgoals: list[PlannedSubgoal] = []
    waypoints: list[WaypointTarget] = []
    for wall_index, edge_key in enumerate(edge_keys):
        pose = layout.edge_pose_for_key(edge_key)
        block_name = layout.supply_block_name(wall_index)
        target_xy = (float(pose.pos[0]), float(pose.pos[1]))
        command = OneStrokeWallCommand(
            wall_index=wall_index,
            block_name=block_name,
            edge_key=edge_key,
            target_xy=target_xy,
            target_yaw=float(pose.yaw),
            orientation=str(pose.orientation),
        )
        commands.append(command)
        subgoals.append(
            PlannedSubgoal(
                subgoal_id=f"{block_name}_to_{command.edge_label}",
                kind="place_wall",
                entity=block_name,
                target={
                    "edge_key": edge_key,
                    "target_xy": target_xy,
                    "target_yaw": command.target_yaw,
                    "orientation": command.orientation,
                },
            )
        )
        waypoints.append(
            WaypointTarget(
                label=f"wall_{wall_index:02d}_{command.edge_label}",
                position=(target_xy[0], target_xy[1], 0.0),
                yaw=command.target_yaw,
                metadata={
                    "entity": block_name,
                    "edge_key": edge_key,
                    "orientation": command.orientation,
                },
            )
        )

    waypoint_plan = WaypointPlan(
        plan_id="onestroke_separator_wall_sequence",
        waypoints=tuple(waypoints),
        metadata={"planner": "onestroke_separator"},
    )
    episode_plan = EpisodePlan(
        task_id="onestroke",
        subgoals=tuple(subgoals),
        waypoint_plan=waypoint_plan,
        plan_id="onestroke_separator_wall_sequence",
        metadata={"planned_walls": len(commands)},
    )
    return tuple(commands), episode_plan
