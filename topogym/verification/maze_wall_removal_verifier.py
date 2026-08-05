from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import numpy as np

from topogym.tasks.legacy.maze_wall_removal import (
    Cell,
    EdgeKey,
    MazeWallRemovalLayout,
    MazeWallRemovalScene,
)


@dataclass(frozen=True)
class MazeWallRemovalPuzzleState:
    a_cell: Cell
    b_cell: Cell
    initial_blocked_edges: tuple[EdgeKey, ...]
    active_blocked_edges: tuple[EdgeKey, ...]
    removed_edges: tuple[EdgeKey, ...]
    oracle_edges: tuple[EdgeKey, ...]
    invalid_walls: tuple[str, ...]
    duplicate_edges: dict[EdgeKey, tuple[str, ...]]
    optimal_wall_count: int
    current_min_wall_count: int
    component_count: int

    @property
    def is_valid(self) -> bool:
        return not self.invalid_walls and not self.duplicate_edges

    @property
    def is_connected(self) -> bool:
        return self.current_min_wall_count == 0

    @property
    def is_terminal(self) -> bool:
        return self.is_valid and self.is_connected

    @property
    def excess_removed(self) -> int:
        return max(0, len(self.removed_edges) - int(self.optimal_wall_count))

    def reward(self, *, success_bonus: float = 10.0) -> float:
        reward = success_bonus if self.is_terminal else 0.0
        reward -= float(self.current_min_wall_count)
        reward -= 0.25 * float(len(self.removed_edges))
        reward -= 2.0 * float(self.excess_removed)
        reward -= 2.0 * float(len(self.invalid_walls))
        reward -= 2.0 * float(sum(max(0, len(names) - 1) for names in self.duplicate_edges.values()))
        return float(reward)

    def to_info(self) -> dict[str, Any]:
        return {
            "a_cell": list(self.a_cell),
            "b_cell": list(self.b_cell),
            "initial_blocked_edges": [list(edge) for edge in self.initial_blocked_edges],
            "active_blocked_edges": [list(edge) for edge in self.active_blocked_edges],
            "removed_edges": [list(edge) for edge in self.removed_edges],
            "oracle_edges": [list(edge) for edge in self.oracle_edges],
            "invalid_walls": list(self.invalid_walls),
            "duplicate_edges": {str(edge): list(names) for edge, names in self.duplicate_edges.items()},
            "optimal_wall_count": int(self.optimal_wall_count),
            "current_min_wall_count": int(self.current_min_wall_count),
            "component_count": int(self.component_count),
            "is_connected": bool(self.is_connected),
            "is_valid": bool(self.is_valid),
            "terminal": bool(self.is_terminal),
            "excess_removed": int(self.excess_removed),
        }


@dataclass(frozen=True)
class MazeWallRemovalPuzzleEvaluator:
    edge_tolerance_xy: float

    def classify(self, maze_scene: MazeWallRemovalScene) -> MazeWallRemovalPuzzleState:
        layout = maze_scene.layout
        edge_occupancy: dict[EdgeKey, list[str]] = {edge: [] for edge in layout.all_edge_keys()}
        invalid_walls: list[str] = []
        wall_edges = getattr(maze_scene, "wall_edges", maze_scene.instance.initial_blocked_edges)

        for edge in wall_edges:
            name = layout.edge_name(edge)
            entity = maze_scene.manifest.get(name)
            pos = _entity_pos(entity)
            nearest_edge, nearest_dist = self._nearest_edge(layout, pos)
            if nearest_edge is not None and nearest_dist <= float(self.edge_tolerance_xy):
                edge_occupancy[nearest_edge].append(name)
            elif not layout.is_discard_pos(pos):
                invalid_walls.append(name)

        active_edges = tuple(edge for edge, names in edge_occupancy.items() if names)
        duplicate_edges = {
            edge: tuple(names)
            for edge, names in edge_occupancy.items()
            if len(names) > 1
        }
        initial = set(maze_scene.instance.initial_blocked_edges)
        active = set(active_edges)
        removed = tuple(sorted(initial - active))
        current_min, _, _ = maze_scene.solver.min_wall_path(
            active,
            maze_scene.instance.a_cell,
            maze_scene.instance.b_cell,
        )
        return MazeWallRemovalPuzzleState(
            a_cell=maze_scene.instance.a_cell,
            b_cell=maze_scene.instance.b_cell,
            initial_blocked_edges=maze_scene.instance.initial_blocked_edges,
            active_blocked_edges=tuple(sorted(active_edges)),
            removed_edges=removed,
            oracle_edges=maze_scene.instance.oracle_edges,
            invalid_walls=tuple(invalid_walls),
            duplicate_edges=duplicate_edges,
            optimal_wall_count=maze_scene.instance.optimal_wall_count,
            current_min_wall_count=current_min,
            component_count=maze_scene.solver.component_count(active),
        )

    def is_success(self, maze_scene: MazeWallRemovalScene) -> bool:
        return self.classify(maze_scene).is_terminal

    def _nearest_edge(self, layout: MazeWallRemovalLayout, pos: np.ndarray) -> tuple[EdgeKey | None, float]:
        nearest_edge = None
        nearest_dist = float("inf")
        for edge in layout.all_edge_keys():
            edge_pos = layout.edge_pose_for_key(edge, for_wall=True).pos
            dist = float(np.linalg.norm(pos[:2] - edge_pos[:2]))
            if dist < nearest_dist:
                nearest_edge = edge
                nearest_dist = dist
        return nearest_edge, nearest_dist


def _entity_pos(entity) -> np.ndarray:
    value = entity.get_pos()
    if hasattr(value, "detach"):
        value = value.detach().cpu().numpy()
    return np.asarray(value).reshape(-1, 3)[0]
