from __future__ import annotations

from dataclasses import dataclass

from .subgoal import PlannedSubgoal
from .waypoint import EpisodePlan, WaypointPlan, WaypointTarget

EdgeKey = tuple[int, int, int, int]


def maze_edge_name(edge_key: EdgeKey) -> str:
    row_a, col_a, row_b, col_b = edge_key
    return f"({row_a},{col_a})-({row_b},{col_b})"


@dataclass(frozen=True)
class MazeWallRemovalCommand:
    """One physical wall-block removal in a Maze Wall Removal plan."""

    move_index: int
    block_name: str
    edge_key: EdgeKey
    discard_index: int
    source_xy: tuple[float, float]
    discard_xy: tuple[float, float]
    wall_yaw: float
    orientation: str

    @property
    def edge_label(self) -> str:
        return maze_edge_name(self.edge_key)


def plan_maze_wall_removals(
    layout,
    instance,
    *,
    max_walls: int | None = None,
) -> tuple[tuple[MazeWallRemovalCommand, ...], EpisodePlan]:
    """Resolve a seeded maze oracle into auditable wall-removal commands."""

    edge_keys = tuple(instance.oracle_edges)
    if max_walls is not None:
        if int(max_walls) <= 0:
            raise ValueError("max_walls must be positive.")
        edge_keys = edge_keys[: int(max_walls)]

    active_edges = set(instance.active_blocked_edges)
    commands: list[MazeWallRemovalCommand] = []
    subgoals: list[PlannedSubgoal] = []
    waypoints: list[WaypointTarget] = []
    for move_index, edge_key in enumerate(edge_keys, start=1):
        edge_key = tuple(edge_key)
        if edge_key not in active_edges:
            raise ValueError(
                f"Oracle edge {maze_edge_name(edge_key)} is not an active wall."
            )
        block_name = layout.edge_name(edge_key)
        source_pose = layout.edge_pose_for_key(edge_key, for_wall=True)
        discard_pos = layout.discard_pos(move_index - 1)
        source_xy = (float(source_pose.pos[0]), float(source_pose.pos[1]))
        discard_xy = (float(discard_pos[0]), float(discard_pos[1]))
        command = MazeWallRemovalCommand(
            move_index=move_index,
            block_name=block_name,
            edge_key=edge_key,
            discard_index=move_index - 1,
            source_xy=source_xy,
            discard_xy=discard_xy,
            wall_yaw=float(source_pose.yaw),
            orientation=str(source_pose.orientation),
        )
        commands.append(command)
        subgoals.append(
            PlannedSubgoal(
                subgoal_id=f"{block_name}_remove_to_discard_{move_index - 1}",
                kind="remove_wall",
                entity=block_name,
                target={
                    "edge_key": edge_key,
                    "edge_label": command.edge_label,
                    "discard_index": command.discard_index,
                    "discard_xy": discard_xy,
                    "orientation": command.orientation,
                },
            )
        )
        waypoints.extend(
            (
                WaypointTarget(
                    label=f"pick_{block_name}_{command.edge_label}",
                    position=(source_xy[0], source_xy[1], 0.0),
                    yaw=command.wall_yaw,
                    metadata={
                        "entity": block_name,
                        "edge_key": edge_key,
                        "orientation": command.orientation,
                    },
                ),
                WaypointTarget(
                    label=f"discard_{move_index - 1}_{block_name}",
                    position=(discard_xy[0], discard_xy[1], 0.0),
                    yaw=command.wall_yaw,
                    metadata={
                        "entity": block_name,
                        "discard_index": command.discard_index,
                    },
                ),
            )
        )

    waypoint_plan = WaypointPlan(
        plan_id="maze_wall_removal_oracle_sequence",
        waypoints=tuple(waypoints),
        metadata={
            "planner": "maze_wall_removal_oracle",
            "planned_removals": len(commands),
        },
    )
    episode_plan = EpisodePlan(
        task_id="maze_wall_removal",
        subgoals=tuple(subgoals),
        waypoint_plan=waypoint_plan,
        plan_id="maze_wall_removal_oracle_sequence",
        metadata={
            "planned_removals": len(commands),
            "optimal_wall_count": int(instance.optimal_wall_count),
            "a_cell": tuple(instance.a_cell),
            "b_cell": tuple(instance.b_cell),
            "instance_seed": int(instance.seed),
        },
    )
    return tuple(commands), episode_plan
