from __future__ import annotations

from dataclasses import dataclass, field
from math import pi
from typing import Any

import genesis as gs
import numpy as np
from omegaconf import OmegaConf

from topogym.core import EntityManifest
from topogym.tasks._visuals import box_entity_enabled
from topogym.world import StandardTabletopSceneBuilder, TabletopBaseScene, materials


def _list(value):
    if OmegaConf.is_config(value):
        value = OmegaConf.to_container(value, resolve=True)
    return value


@dataclass(frozen=True)
class EdgeSlotPose:
    pos: np.ndarray
    size: np.ndarray
    yaw: float
    orientation: str


@dataclass(frozen=True)
class OneStrokeLayout:
    """Cell-grid, supply-tray, and wall-slot geometry for OneStroke."""

    cfg: Any
    task_origin: tuple[float, float, float] = (0.0, 0.0, 0.0)

    @property
    def coordinate_frame(self) -> str:
        return str(getattr(self.cfg, "coordinate_frame", "world"))

    def position_to_world(self, position) -> np.ndarray:
        pos = np.asarray(_list(position), dtype=float)
        if self.coordinate_frame == "world":
            return pos
        if self.coordinate_frame == "task":
            return pos + np.asarray(self.task_origin, dtype=float)
        raise ValueError(
            f"Unsupported OneStroke coordinate_frame={self.coordinate_frame!r}; "
            "expected 'world' or 'task'."
        )

    def world_z(self, z: float) -> float:
        if self.coordinate_frame == "world":
            return float(z)
        if self.coordinate_frame == "task":
            return float(self.task_origin[2]) + float(z)
        raise ValueError(
            f"Unsupported OneStroke coordinate_frame={self.coordinate_frame!r}; "
            "expected 'world' or 'task'."
        )

    @property
    def rows(self) -> int:
        return int(self.cfg.grid.rows)

    @property
    def cols(self) -> int:
        return int(self.cfg.grid.cols)

    @property
    def wall_count(self) -> int:
        return int(self.cfg.wall_block.count)

    def cell_center(self, row: int, col: int) -> np.ndarray:
        top_left = self.position_to_world(self.cfg.grid.top_left_cell_pos)
        cell_size = np.asarray(_list(self.cfg.grid.cell_size), dtype=float)
        gap = float(self.cfg.grid.cell_gap)
        return np.array(
            [
                top_left[0] + col * (cell_size[0] + gap),
                top_left[1] - row * (cell_size[1] + gap),
                top_left[2],
            ],
            dtype=float,
        )

    def cell_name(self, row: int, col: int) -> str:
        return f"cell_{row}_{col}"

    def cell_color(self, row: int, col: int) -> tuple[float, float, float]:
        return tuple(self.cfg.grid.colors[int(row)][int(col)])

    def cell_labels(self) -> tuple[tuple[str, ...], ...]:
        puzzle = getattr(self.cfg, "puzzle", None)
        if puzzle is not None and hasattr(puzzle, "labels"):
            return tuple(tuple(str(label) for label in row) for row in _list(puzzle.labels))

        labels: list[list[str]] = []
        known: dict[tuple[float, float, float], str] = {}
        next_label = ord("A")
        for row in range(self.rows):
            label_row: list[str] = []
            for col in range(self.cols):
                color = tuple(round(float(value), 4) for value in self.cell_color(row, col))
                if color not in known:
                    known[color] = chr(next_label) if len(known) < 2 else "gray"
                    next_label += 1
                label_row.append(known[color])
            labels.append(label_row)
        return tuple(tuple(row) for row in labels)

    def color_a_label(self) -> str:
        puzzle = getattr(self.cfg, "puzzle", None)
        return str(getattr(puzzle, "color_a", "A"))

    def color_b_label(self) -> str:
        puzzle = getattr(self.cfg, "puzzle", None)
        return str(getattr(puzzle, "color_b", "B"))

    def supply_block_name(self, index: int) -> str:
        return f"wall_block_{int(index)}"

    def supply_block_pos(self, index: int) -> np.ndarray:
        start = self.position_to_world(self.cfg.supply.block_start_pos)
        spacing = float(self.cfg.supply.block_spacing)
        return np.array([start[0], start[1] - index * spacing, start[2]], dtype=float)

    def edge_slot_pose(self, edge) -> EdgeSlotPose:
        cell_a = _list(edge.cell_a)
        cell_b = _list(edge.cell_b)
        return self.edge_pose_for_cells(cell_a, cell_b)

    def edge_pose_for_cells(self, cell_a, cell_b) -> EdgeSlotPose:
        row_a, col_a = int(cell_a[0]), int(cell_a[1])
        row_b, col_b = int(cell_b[0]), int(cell_b[1])
        center_a = self.cell_center(row_a, col_a)
        center_b = self.cell_center(row_b, col_b)

        dr = abs(row_a - row_b)
        dc = abs(col_a - col_b)
        if dr + dc != 1:
            raise ValueError(
                f"OneStroke edge slot must connect adjacent cells; got {cell_a} and {cell_b}."
            )

        pos = 0.5 * (center_a + center_b)
        pos[2] = self.world_z(self.cfg.edge_slots.z)
        cell_size = np.asarray(_list(self.cfg.grid.cell_size), dtype=float)
        width = float(self.cfg.edge_slots.width)
        height = float(self.cfg.edge_slots.height)
        length_padding = float(self.cfg.edge_slots.length_padding)

        if row_a == row_b:
            orientation = "vertical"
            size = np.array([width, cell_size[1] + length_padding, height], dtype=float)
            yaw = 0.5 * pi
        else:
            orientation = "horizontal"
            size = np.array([cell_size[0] + length_padding, width, height], dtype=float)
            yaw = 0.0

        return EdgeSlotPose(pos=pos, size=size, yaw=yaw, orientation=orientation)

    def edge_key(self, cell_a, cell_b) -> tuple[int, int, int, int]:
        a = (int(cell_a[0]), int(cell_a[1]))
        b = (int(cell_b[0]), int(cell_b[1]))
        if abs(a[0] - b[0]) + abs(a[1] - b[1]) != 1:
            raise ValueError(f"OneStroke edge cells must be adjacent, got {a} and {b}.")
        first, second = sorted((a, b))
        return (first[0], first[1], second[0], second[1])

    def all_edge_keys(self) -> tuple[tuple[int, int, int, int], ...]:
        keys: list[tuple[int, int, int, int]] = []
        for row in range(self.rows):
            for col in range(self.cols):
                if col + 1 < self.cols:
                    keys.append(self.edge_key((row, col), (row, col + 1)))
                if row + 1 < self.rows:
                    keys.append(self.edge_key((row, col), (row + 1, col)))
        return tuple(keys)

    def edge_pose_for_key(self, edge_key: tuple[int, int, int, int]) -> EdgeSlotPose:
        row_a, col_a, row_b, col_b = edge_key
        return self.edge_pose_for_cells((row_a, col_a), (row_b, col_b))

    def target_edge_keys(self) -> tuple[tuple[int, int, int, int], ...]:
        return tuple(self.edge_key(edge.cell_a, edge.cell_b) for edge in self.cfg.edge_slots.targets)

    def edge_support_name(self, edge_key: tuple[int, int, int, int]) -> str:
        return "edge_support_" + "_".join(str(value) for value in edge_key)

    def edge_support_enabled(self) -> bool:
        return bool(getattr(self.cfg.edge_slots, "collision", True))

    def edge_support_visualization_enabled(self) -> bool:
        return bool(getattr(self.cfg.edge_slots, "visualization", False))

    def board_top_z(self) -> float:
        board_pos = self.position_to_world(self.cfg.board.pos)
        board_size = np.asarray(_list(self.cfg.board.size), dtype=float)
        return float(board_pos[2] + 0.5 * board_size[2])

    def edge_support_top_z(self) -> float:
        return float(
            self.world_z(self.cfg.edge_slots.z)
            + 0.5 * float(self.cfg.edge_slots.height)
        )

    def wall_placement_floor_z(self) -> float:
        if self.edge_support_enabled():
            return self.edge_support_top_z()
        return self.board_top_z()

    def wall_target_center_z(self) -> float:
        return float(
            self.wall_placement_floor_z()
            + 0.5 * float(self.cfg.wall_block.size[2])
        )

    def is_supply_pos(self, pos: np.ndarray) -> bool:
        tray_pos = self.position_to_world(self.cfg.supply.pos)
        tray_size = np.asarray(_list(self.cfg.supply.size), dtype=float)
        half = tray_size[:2] * 0.5
        return bool(
            abs(float(pos[0] - tray_pos[0])) <= half[0]
            and abs(float(pos[1] - tray_pos[1])) <= half[1]
        )


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

    def classify(self, one_scene: "OneStrokeScene") -> OneStrokePuzzleState:
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

    def is_success(self, one_scene: "OneStrokeScene") -> bool:
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


@dataclass
class OneStrokeScene:
    scene: Any
    manifest: EntityManifest
    layout: OneStrokeLayout
    cameras: dict = field(default_factory=dict)
    tabletop: TabletopBaseScene | None = None


class OneStrokeSceneBuilder:
    """Build the common table plus a OneStroke cell board and wall supply."""

    def __init__(self, env_cfg, task_cfg, robot_cfg, *, rigid_options=None) -> None:
        self.env_cfg = env_cfg
        self.task_cfg = task_cfg
        self.robot_cfg = robot_cfg
        self.rigid_options = rigid_options

    def build(self, *, show_viewer: bool = False) -> OneStrokeScene:
        tabletop_builder = StandardTabletopSceneBuilder(
            self.env_cfg,
            self.robot_cfg,
            rigid_options=self.rigid_options,
        )
        tabletop = tabletop_builder.create(show_viewer=show_viewer)
        scene = tabletop.scene
        manifest = tabletop.manifest

        layout = OneStrokeLayout(
            self.task_cfg,
            task_origin=tabletop.frames.task_origin,
        )
        self._add_board(scene, manifest, layout)
        self._add_cells(scene, manifest, layout)
        self._add_edge_slots(scene, manifest, layout)
        self._add_supply(scene, manifest, layout)

        tabletop_builder.finalize(tabletop)
        return OneStrokeScene(
            scene=scene,
            manifest=manifest,
            layout=layout,
            cameras=tabletop.cameras,
            tabletop=tabletop,
        )

    def _add_board(
        self,
        scene,
        manifest: EntityManifest,
        layout: OneStrokeLayout,
    ) -> None:
        if not box_entity_enabled(self.task_cfg.board):
            return
        manifest.add(
            self.task_cfg.board.name,
            scene.add_entity(
                gs.morphs.Box(
                    pos=tuple(layout.position_to_world(self.task_cfg.board.pos)),
                    size=tuple(self.task_cfg.board.size),
                    fixed=True,
                ),
                surface=materials.plastic("board", self.task_cfg.board.color),
                name=self.task_cfg.board.name,
            ),
        )

    def _add_cells(self, scene, manifest: EntityManifest, layout: OneStrokeLayout) -> None:
        cell_size = tuple(self.task_cfg.grid.cell_size)
        for row in range(layout.rows):
            for col in range(layout.cols):
                name = layout.cell_name(row, col)
                manifest.add(
                    name,
                    scene.add_entity(
                        gs.morphs.Box(
                            pos=tuple(layout.cell_center(row, col)),
                            size=cell_size,
                            fixed=True,
                        ),
                        surface=materials.plastic("marker", layout.cell_color(row, col)),
                        name=name,
                    ),
                )

    def _add_edge_slots(self, scene, manifest: EntityManifest, layout: OneStrokeLayout) -> None:
        # Every legal cell boundary gets the same invisible collision support.
        # Supporting only oracle target edges would leak the solution through
        # the physical scene even if those supports were not rendered.
        if not layout.edge_support_enabled():
            return
        for edge_key in layout.all_edge_keys():
            pose = layout.edge_pose_for_key(edge_key)
            name = layout.edge_support_name(edge_key)
            manifest.add(
                name,
                scene.add_entity(
                    gs.morphs.Box(
                        pos=tuple(pose.pos),
                        size=tuple(pose.size),
                        fixed=True,
                        visualization=layout.edge_support_visualization_enabled(),
                        collision=True,
                    ),
                    surface=materials.plastic("marker", self.task_cfg.edge_slots.color),
                    name=name,
                ),
            )

    def _add_supply(self, scene, manifest: EntityManifest, layout: OneStrokeLayout) -> None:
        if box_entity_enabled(self.task_cfg.supply):
            manifest.add(
                self.task_cfg.supply.name,
                scene.add_entity(
                    gs.morphs.Box(
                        pos=tuple(layout.position_to_world(self.task_cfg.supply.pos)),
                        size=tuple(self.task_cfg.supply.size),
                        fixed=True,
                    ),
                    surface=materials.plastic("board", self.task_cfg.supply.color),
                    name=self.task_cfg.supply.name,
                ),
            )
        for index in range(layout.wall_count):
            name = layout.supply_block_name(index)
            manifest.add(
                name,
                scene.add_entity(
                    gs.morphs.Box(
                        pos=tuple(layout.supply_block_pos(index)),
                        size=tuple(self.task_cfg.wall_block.size),
                    ),
                    surface=materials.plastic("object", self.task_cfg.wall_block.color),
                    name=name,
                ),
            )
