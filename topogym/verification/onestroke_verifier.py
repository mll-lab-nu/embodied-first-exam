from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import numpy as np

from topogym.tasks.legacy.onestroke import OneStrokeLayout, OneStrokeScene


@dataclass(frozen=True)
class OneStrokePuzzleState:
    """Discrete wall placement state for OneStroke."""

    cell_labels: tuple[tuple[str, ...], ...]
    placed_edges: tuple[tuple[int, int, int, int], ...]
    unused_walls: tuple[str, ...]
    invalid_walls: tuple[str, ...]
    duplicate_edges: dict[tuple[int, int, int, int], tuple[str, ...]]
    color_a: str = "A"
    color_b: str = "B"

    @property
    def is_valid(self) -> bool:
        return not self.invalid_walls and not self.duplicate_edges

    @property
    def is_terminal(self) -> bool:
        return self.is_valid and self.separates_colors()

    def separates_colors(self) -> bool:
        rows = len(self.cell_labels)
        cols = len(self.cell_labels[0]) if rows else 0
        blocked = set(self.placed_edges)
        visited: set[tuple[int, int]] = set()

        for start_row in range(rows):
            for start_col in range(cols):
                start = (start_row, start_col)
                if start in visited:
                    continue
                stack = [start]
                visited.add(start)
                labels: set[str] = set()
                while stack:
                    row, col = stack.pop()
                    labels.add(str(self.cell_labels[row][col]))
                    for next_cell in _neighbor_cells(row, col, rows, cols):
                        edge = _edge_key_from_cells((row, col), next_cell)
                        if edge in blocked or next_cell in visited:
                            continue
                        visited.add(next_cell)
                        stack.append(next_cell)
                if self.color_a in labels and self.color_b in labels:
                    return False
        return True

    def reward(self, *, success_bonus: float = 10.0) -> float:
        penalty = float(self.unseparated_component_count())
        penalty += 2.0 * float(len(self.invalid_walls))
        penalty += 2.0 * float(sum(max(0, len(names) - 1) for names in self.duplicate_edges.values()))
        return (success_bonus if self.is_terminal else 0.0) - penalty

    def unseparated_component_count(self) -> int:
        rows = len(self.cell_labels)
        cols = len(self.cell_labels[0]) if rows else 0
        blocked = set(self.placed_edges)
        visited: set[tuple[int, int]] = set()
        count = 0
        for start_row in range(rows):
            for start_col in range(cols):
                start = (start_row, start_col)
                if start in visited:
                    continue
                stack = [start]
                visited.add(start)
                labels: set[str] = set()
                while stack:
                    row, col = stack.pop()
                    labels.add(str(self.cell_labels[row][col]))
                    for next_cell in _neighbor_cells(row, col, rows, cols):
                        edge = _edge_key_from_cells((row, col), next_cell)
                        if edge in blocked or next_cell in visited:
                            continue
                        visited.add(next_cell)
                        stack.append(next_cell)
                if self.color_a in labels and self.color_b in labels:
                    count += 1
        return count

    def to_info(self) -> dict[str, Any]:
        return {
            "cell_labels": [list(row) for row in self.cell_labels],
            "placed_edges": [list(edge) for edge in self.placed_edges],
            "unused_walls": list(self.unused_walls),
            "invalid_walls": list(self.invalid_walls),
            "duplicate_edges": {str(edge): list(names) for edge, names in self.duplicate_edges.items()},
            "unseparated_components": self.unseparated_component_count(),
            "is_valid": self.is_valid,
            "terminal": self.is_terminal,
        }


@dataclass(frozen=True)
class OneStrokePuzzleEvaluator:
    """Map wall-block poses to the OneStroke discrete puzzle state."""

    edge_tolerance_xy: float
    wall_tolerance_z: float | None = None
    wall_tolerance_tilt: float | None = None

    def classify(self, one_scene: OneStrokeScene) -> OneStrokePuzzleState:
        layout = one_scene.layout
        edge_occupancy: dict[tuple[int, int, int, int], list[str]] = {
            edge: [] for edge in layout.all_edge_keys()
        }
        unused_walls: list[str] = []
        invalid_walls: list[str] = []

        for index in range(layout.wall_count):
            name = layout.supply_block_name(index)
            entity = one_scene.manifest.get(name)
            pos = _entity_pos(entity)
            nearest_edge, nearest_dist = self._nearest_edge(layout, pos)
            if nearest_edge is not None and nearest_dist <= float(self.edge_tolerance_xy):
                expected_z = layout.wall_target_center_z()
                z_ok = (
                    self.wall_tolerance_z is None
                    or abs(float(pos[2]) - expected_z) <= float(self.wall_tolerance_z)
                )
                tilt = _entity_tilt(entity)
                tilt_ok = (
                    self.wall_tolerance_tilt is None
                    or (
                        tilt is not None
                        and tilt <= float(self.wall_tolerance_tilt)
                    )
                )
                if z_ok and tilt_ok:
                    edge_occupancy[nearest_edge].append(name)
                else:
                    invalid_walls.append(name)
            elif layout.is_supply_pos(pos):
                unused_walls.append(name)
            else:
                invalid_walls.append(name)

        placed_edges = tuple(edge for edge, names in edge_occupancy.items() if names)
        duplicate_edges = {
            edge: tuple(names)
            for edge, names in edge_occupancy.items()
            if len(names) > 1
        }
        return OneStrokePuzzleState(
            cell_labels=layout.cell_labels(),
            placed_edges=placed_edges,
            unused_walls=tuple(unused_walls),
            invalid_walls=tuple(invalid_walls),
            duplicate_edges=duplicate_edges,
            color_a=layout.color_a_label(),
            color_b=layout.color_b_label(),
        )

    def is_success(self, one_scene: OneStrokeScene) -> bool:
        return self.classify(one_scene).is_terminal

    def _nearest_edge(
        self,
        layout: OneStrokeLayout,
        pos: np.ndarray,
    ) -> tuple[tuple[int, int, int, int] | None, float]:
        nearest_edge = None
        nearest_dist = float("inf")
        for edge in layout.all_edge_keys():
            edge_pos = layout.edge_pose_for_key(edge).pos
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


def _entity_tilt(entity) -> float | None:
    get_quat = getattr(entity, "get_quat", None)
    if get_quat is None:
        return None
    value = get_quat()
    if hasattr(value, "detach"):
        value = value.detach().cpu().numpy()
    quat = np.asarray(value).reshape(-1, 4)[0].astype(float)
    norm = float(np.linalg.norm(quat))
    if norm <= 1e-8:
        return None
    _, x, y, _ = quat / norm
    local_z_world_z = 1.0 - 2.0 * (x * x + y * y)
    return float(np.arccos(np.clip(local_z_world_z, -1.0, 1.0)))


def _neighbor_cells(row: int, col: int, rows: int, cols: int) -> tuple[tuple[int, int], ...]:
    neighbors: list[tuple[int, int]] = []
    if row > 0:
        neighbors.append((row - 1, col))
    if row + 1 < rows:
        neighbors.append((row + 1, col))
    if col > 0:
        neighbors.append((row, col - 1))
    if col + 1 < cols:
        neighbors.append((row, col + 1))
    return tuple(neighbors)


def _edge_key_from_cells(cell_a, cell_b) -> tuple[int, int, int, int]:
    first, second = sorted(((int(cell_a[0]), int(cell_a[1])), (int(cell_b[0]), int(cell_b[1]))))
    return (first[0], first[1], second[0], second[1])
