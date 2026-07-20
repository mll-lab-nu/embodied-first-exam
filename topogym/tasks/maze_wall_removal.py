from __future__ import annotations

from collections import deque
from dataclasses import dataclass, field
from math import pi
from typing import Any

import genesis as gs
import numpy as np
from omegaconf import OmegaConf

from topogym.core import EntityManifest
from topogym.tasks._visuals import box_entity_enabled
from topogym.world import (
    StandardTabletopSceneBuilder,
    materials,
    TabletopBaseScene,
    tabletop_frames_from_config,
)


Cell = tuple[int, int]
EdgeKey = tuple[int, int, int, int]


def _list(value):
    if OmegaConf.is_config(value):
        value = OmegaConf.to_container(value, resolve=True)
    return value


def _entity_pos(entity) -> np.ndarray:
    value = entity.get_pos()
    if hasattr(value, "detach"):
        value = value.detach().cpu().numpy()
    return np.asarray(value).reshape(-1, 3)[0]


def _yaw_quat(yaw: float) -> tuple[float, float, float, float]:
    half = 0.5 * float(yaw)
    return (float(np.cos(half)), 0.0, 0.0, float(np.sin(half)))


def _weighted_choice(rng: np.random.Generator, items, weights):
    weights = np.asarray(weights, dtype=float)
    weights = weights / weights.sum()
    return items[int(rng.choice(len(items), p=weights))]


@dataclass(frozen=True)
class MazeEdgePose:
    pos: np.ndarray
    size: np.ndarray
    yaw: float
    orientation: str


@dataclass(frozen=True)
class MazeWallRemovalLayout:
    """Geometry for a cell maze whose walls live on adjacent-cell edges."""

    cfg: Any
    task_origin: tuple[float, float, float] = (0.0, 0.0, 0.0)

    @property
    def coordinate_frame(self) -> str:
        return str(getattr(self.cfg, "coordinate_frame", "world"))

    def position_to_world(self, position) -> np.ndarray:
        result = np.asarray(_list(position), dtype=float).copy()
        if result.shape != (3,):
            raise ValueError(f"Maze position must have shape (3,), got {result}.")
        if self.coordinate_frame == "task":
            result += np.asarray(self.task_origin, dtype=float)
        elif self.coordinate_frame != "world":
            raise ValueError(
                f"Unsupported maze coordinate_frame={self.coordinate_frame!r}."
            )
        return result

    def world_z(self, z: float) -> float:
        if self.coordinate_frame == "task":
            return float(self.task_origin[2]) + float(z)
        if self.coordinate_frame == "world":
            return float(z)
        raise ValueError(
            f"Unsupported maze coordinate_frame={self.coordinate_frame!r}."
        )

    @property
    def rows(self) -> int:
        return int(self.cfg.grid.rows)

    @property
    def cols(self) -> int:
        return int(self.cfg.grid.cols)

    @property
    def wall_count(self) -> int:
        return len(self.all_edge_keys())

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
        return f"maze_cell_{row}_{col}"

    def cell_color(self, cell: Cell, *, a_cell: Cell, b_cell: Cell) -> tuple[float, float, float]:
        if cell == a_cell:
            return tuple(float(v) for v in self.cfg.markers.a_cell_color)
        if cell == b_cell:
            return tuple(float(v) for v in self.cfg.markers.b_cell_color)
        parity = (int(cell[0]) + int(cell[1])) % 2
        colors = _list(self.cfg.grid.colors)
        return tuple(float(v) for v in colors[parity])

    def edge_key(self, cell_a, cell_b) -> EdgeKey:
        a = (int(cell_a[0]), int(cell_a[1]))
        b = (int(cell_b[0]), int(cell_b[1]))
        if abs(a[0] - b[0]) + abs(a[1] - b[1]) != 1:
            raise ValueError(f"Maze wall edge cells must be adjacent, got {a} and {b}.")
        first, second = sorted((a, b))
        return (first[0], first[1], second[0], second[1])

    def edge_index(self, edge_key: EdgeKey) -> int:
        return self.all_edge_keys().index(tuple(edge_key))

    def edge_name(self, edge_key: EdgeKey) -> str:
        return f"maze_wall_{self.edge_index(edge_key):02d}"

    def all_cells(self) -> tuple[Cell, ...]:
        return tuple((row, col) for row in range(self.rows) for col in range(self.cols))

    def all_edge_keys(self) -> tuple[EdgeKey, ...]:
        keys: list[EdgeKey] = []
        for row in range(self.rows):
            for col in range(self.cols):
                if col + 1 < self.cols:
                    keys.append(self.edge_key((row, col), (row, col + 1)))
                if row + 1 < self.rows:
                    keys.append(self.edge_key((row, col), (row + 1, col)))
        return tuple(keys)

    def edge_pose_for_key(self, edge_key: EdgeKey, *, for_wall: bool = True) -> MazeEdgePose:
        row_a, col_a, row_b, col_b = edge_key
        center_a = self.cell_center(row_a, col_a)
        center_b = self.cell_center(row_b, col_b)
        pos = 0.5 * (center_a + center_b)
        pos[2] = self.world_z(
            self.cfg.wall_block.z if for_wall else self.cfg.edge_slots.z
        )

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

        return MazeEdgePose(pos=pos, size=size, yaw=yaw, orientation=orientation)

    def discard_pos(self, index: int) -> np.ndarray:
        center = self.position_to_world(self.cfg.discard.pos)
        tray_size = np.asarray(_list(self.cfg.discard.size), dtype=float)
        block_size = np.asarray(_list(self.cfg.wall_block.size), dtype=float)
        columns = max(1, int(getattr(self.cfg.discard, "columns", 4)))
        spacing_x = float(getattr(self.cfg.discard, "spacing_x", block_size[1] * 1.9))
        spacing_y = float(getattr(self.cfg.discard, "spacing_y", block_size[0] * 1.2))
        col = int(index) % columns
        row = int(index) // columns
        x0 = center[0] - 0.5 * min(tray_size[0], spacing_x * max(1, columns - 1))
        y0 = center[1] + 0.5 * tray_size[1] - spacing_y
        return np.array(
            [
                x0 + col * spacing_x,
                y0 - row * spacing_y,
                self.world_z(self.cfg.wall_block.z),
            ]
        )

    def is_discard_pos(self, pos: np.ndarray) -> bool:
        center = self.position_to_world(self.cfg.discard.pos)
        tray_size = np.asarray(_list(self.cfg.discard.size), dtype=float)
        half = tray_size[:2] * 0.5
        return bool(
            abs(float(pos[0] - center[0])) <= half[0]
            and abs(float(pos[1] - center[1])) <= half[1]
        )


@dataclass(frozen=True)
class MazeWallRemovalInstance:
    a_cell: Cell
    b_cell: Cell
    initial_blocked_edges: tuple[EdgeKey, ...]
    active_blocked_edges: tuple[EdgeKey, ...]
    oracle_edges: tuple[EdgeKey, ...]
    optimal_wall_count: int
    seed: int

    def to_info(self) -> dict[str, Any]:
        return {
            "a_cell": list(self.a_cell),
            "b_cell": list(self.b_cell),
            "initial_blocked_edges": [list(edge) for edge in self.initial_blocked_edges],
            "active_blocked_edges": [list(edge) for edge in self.active_blocked_edges],
            "oracle_edges": [list(edge) for edge in self.oracle_edges],
            "optimal_wall_count": int(self.optimal_wall_count),
            "seed": int(self.seed),
        }


@dataclass(frozen=True)
class MazeGraphSolver:
    rows: int
    cols: int

    def edge_key(self, cell_a: Cell, cell_b: Cell) -> EdgeKey:
        first, second = sorted((tuple(cell_a), tuple(cell_b)))
        return (first[0], first[1], second[0], second[1])

    def neighbors(self, cell: Cell) -> tuple[Cell, ...]:
        row, col = cell
        result: list[Cell] = []
        if row > 0:
            result.append((row - 1, col))
        if row + 1 < self.rows:
            result.append((row + 1, col))
        if col > 0:
            result.append((row, col - 1))
        if col + 1 < self.cols:
            result.append((row, col + 1))
        return tuple(result)

    def connected(self, blocked_edges: set[EdgeKey] | tuple[EdgeKey, ...], a_cell: Cell, b_cell: Cell) -> bool:
        blocked = set(blocked_edges)
        visited = {tuple(a_cell)}
        stack = [tuple(a_cell)]
        while stack:
            cell = stack.pop()
            if cell == tuple(b_cell):
                return True
            for neighbor in self.neighbors(cell):
                if neighbor in visited or self.edge_key(cell, neighbor) in blocked:
                    continue
                visited.add(neighbor)
                stack.append(neighbor)
        return False

    def min_wall_path(
        self,
        blocked_edges: set[EdgeKey] | tuple[EdgeKey, ...],
        a_cell: Cell,
        b_cell: Cell,
    ) -> tuple[int, tuple[EdgeKey, ...], tuple[Cell, ...]]:
        blocked = set(blocked_edges)
        start = tuple(a_cell)
        goal = tuple(b_cell)
        dist: dict[Cell, int] = {start: 0}
        prev: dict[Cell, tuple[Cell, EdgeKey]] = {}
        queue: deque[Cell] = deque([start])

        while queue:
            cell = queue.popleft()
            if cell == goal:
                break
            for neighbor in self.neighbors(cell):
                edge = self.edge_key(cell, neighbor)
                cost = 1 if edge in blocked else 0
                next_dist = dist[cell] + cost
                if next_dist >= dist.get(neighbor, 1_000_000):
                    continue
                dist[neighbor] = next_dist
                prev[neighbor] = (cell, edge)
                if cost == 0:
                    queue.appendleft(neighbor)
                else:
                    queue.append(neighbor)

        if goal not in dist:
            return 1_000_000, (), ()

        cells: list[Cell] = [goal]
        path_edges: list[EdgeKey] = []
        current = goal
        while current != start:
            previous, edge = prev[current]
            path_edges.append(edge)
            cells.append(previous)
            current = previous
        path_edges.reverse()
        cells.reverse()
        oracle_edges = tuple(edge for edge in path_edges if edge in blocked)
        return int(dist[goal]), oracle_edges, tuple(cells)

    def component_count(self, blocked_edges: set[EdgeKey] | tuple[EdgeKey, ...]) -> int:
        blocked = set(blocked_edges)
        unseen = {(row, col) for row in range(self.rows) for col in range(self.cols)}
        count = 0
        while unseen:
            count += 1
            start = unseen.pop()
            stack = [start]
            while stack:
                cell = stack.pop()
                for neighbor in self.neighbors(cell):
                    if neighbor not in unseen or self.edge_key(cell, neighbor) in blocked:
                        continue
                    unseen.remove(neighbor)
                    stack.append(neighbor)
        return count


@dataclass(frozen=True)
class MazeWallGenerator:
    layout: MazeWallRemovalLayout
    solver: MazeGraphSolver

    def sample(self, seed: int | None = None) -> MazeWallRemovalInstance:
        if seed is None:
            seed = int(np.random.default_rng().integers(0, np.iinfo(np.int32).max))
        rng = np.random.default_rng(seed)
        attempts = int(getattr(self.layout.cfg.maze, "max_resample_attempts", 500))
        for attempt in range(attempts):
            instance = self._sample_once(rng, seed=int(seed) + attempt)
            if instance is not None:
                return instance
        raise RuntimeError(
            "Could not sample a valid maze_wall_removal instance. "
            "Relax wall_density, required removals, or straight-run constraints."
        )

    def _sample_once(self, rng: np.random.Generator, *, seed: int) -> MazeWallRemovalInstance | None:
        open_tree = set(self._random_spanning_tree(rng))
        all_edges = set(self.layout.all_edge_keys())
        cells = list(self.layout.all_cells())
        a_cell, b_cell = self._sample_points(rng, cells)
        if a_cell is None or b_cell is None:
            return None

        tree_path = self._open_path_edges(open_tree, a_cell, b_cell)
        if not tree_path:
            return None

        min_remove = int(getattr(self.layout.cfg.maze, "min_required_removals", 1))
        max_remove = int(getattr(self.layout.cfg.maze, "max_required_removals", 3))
        forced_count = int(rng.integers(min_remove, max_remove + 1))
        forced_count = min(forced_count, len(tree_path))
        forced_closed = set(rng.choice(len(tree_path), size=forced_count, replace=False).tolist())
        forced_edges = {tree_path[index] for index in forced_closed}

        blocked = set(all_edges - open_tree)
        blocked.update(forced_edges)
        target_count = self._target_blocked_count(total_edges=len(all_edges), minimum=len(forced_edges))
        self._adjust_density(rng, blocked, all_edges, forced_edges, target_count)

        if self.solver.connected(blocked, a_cell, b_cell):
            return None

        optimal, oracle_edges, _ = self.solver.min_wall_path(blocked, a_cell, b_cell)
        if optimal < min_remove or optimal > max_remove:
            return None

        max_run = int(getattr(self.layout.cfg.maze, "max_straight_run", 0))
        if max_run > 0 and self._max_straight_run(blocked) > max_run:
            return None

        active = tuple(sorted(blocked))
        return MazeWallRemovalInstance(
            a_cell=a_cell,
            b_cell=b_cell,
            initial_blocked_edges=active,
            active_blocked_edges=active,
            oracle_edges=tuple(sorted(oracle_edges)),
            optimal_wall_count=optimal,
            seed=seed,
        )

    def _random_spanning_tree(self, rng: np.random.Generator) -> tuple[EdgeKey, ...]:
        start = (
            int(rng.integers(0, self.layout.rows)),
            int(rng.integers(0, self.layout.cols)),
        )
        turn_bias = float(getattr(self.layout.cfg.maze, "turn_bias", 0.55))
        turn_bias = float(np.clip(turn_bias, 0.05, 0.95))
        visited = {start}
        stack: list[tuple[Cell, tuple[int, int] | None]] = [(start, None)]
        edges: list[EdgeKey] = []

        while stack:
            cell, last_dir = stack[-1]
            choices = [neighbor for neighbor in self.solver.neighbors(cell) if neighbor not in visited]
            if not choices:
                stack.pop()
                continue
            weights = []
            for neighbor in choices:
                direction = (neighbor[0] - cell[0], neighbor[1] - cell[1])
                if last_dir is None:
                    weights.append(1.0)
                elif direction == last_dir:
                    weights.append(max(0.05, 1.0 - turn_bias))
                else:
                    weights.append(max(0.05, turn_bias))
            neighbor = _weighted_choice(rng, choices, weights)
            edge = self.solver.edge_key(cell, neighbor)
            direction = (neighbor[0] - cell[0], neighbor[1] - cell[1])
            edges.append(edge)
            visited.add(neighbor)
            stack.append((neighbor, direction))
        return tuple(edges)

    def _sample_points(self, rng: np.random.Generator, cells: list[Cell]) -> tuple[Cell | None, Cell | None]:
        min_dist = int(getattr(self.layout.cfg.maze, "min_manhattan_distance", 1))
        max_dist = int(getattr(self.layout.cfg.maze, "max_manhattan_distance", self.layout.rows + self.layout.cols))
        for _ in range(200):
            a_cell = cells[int(rng.integers(0, len(cells)))]
            b_cell = cells[int(rng.integers(0, len(cells)))]
            if a_cell == b_cell:
                continue
            dist = abs(a_cell[0] - b_cell[0]) + abs(a_cell[1] - b_cell[1])
            if min_dist <= dist <= max_dist:
                return a_cell, b_cell
        return None, None

    def _open_path_edges(self, open_edges: set[EdgeKey], a_cell: Cell, b_cell: Cell) -> tuple[EdgeKey, ...]:
        parent: dict[Cell, tuple[Cell, EdgeKey]] = {}
        queue = deque([a_cell])
        visited = {a_cell}
        while queue:
            cell = queue.popleft()
            if cell == b_cell:
                break
            for neighbor in self.solver.neighbors(cell):
                edge = self.solver.edge_key(cell, neighbor)
                if edge not in open_edges or neighbor in visited:
                    continue
                visited.add(neighbor)
                parent[neighbor] = (cell, edge)
                queue.append(neighbor)
        if b_cell not in visited:
            return ()
        current = b_cell
        edges: list[EdgeKey] = []
        while current != a_cell:
            previous, edge = parent[current]
            edges.append(edge)
            current = previous
        edges.reverse()
        return tuple(edges)

    def _target_blocked_count(self, *, total_edges: int, minimum: int) -> int:
        density = float(getattr(self.layout.cfg.maze, "wall_density", 0.42))
        target = int(round(float(total_edges) * np.clip(density, 0.05, 0.95)))
        return max(int(minimum), min(int(total_edges) - 1, target))

    def _adjust_density(
        self,
        rng: np.random.Generator,
        blocked: set[EdgeKey],
        all_edges: set[EdgeKey],
        forced_edges: set[EdgeKey],
        target_count: int,
    ) -> None:
        while len(blocked) > target_count:
            candidates = tuple(sorted(blocked - forced_edges))
            if not candidates:
                return
            blocked.remove(candidates[int(rng.integers(0, len(candidates)))])
        while len(blocked) < target_count:
            candidates = tuple(sorted(all_edges - blocked))
            if not candidates:
                return
            blocked.add(candidates[int(rng.integers(0, len(candidates)))])

    def _max_straight_run(self, blocked: set[EdgeKey]) -> int:
        max_run = 0
        for col in range(self.layout.cols - 1):
            run = 0
            for row in range(self.layout.rows):
                edge = self.solver.edge_key((row, col), (row, col + 1))
                run = run + 1 if edge in blocked else 0
                max_run = max(max_run, run)
        for row in range(self.layout.rows - 1):
            run = 0
            for col in range(self.layout.cols):
                edge = self.solver.edge_key((row, col), (row + 1, col))
                run = run + 1 if edge in blocked else 0
                max_run = max(max_run, run)
        return max_run


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

    def classify(self, maze_scene: "MazeWallRemovalScene") -> MazeWallRemovalPuzzleState:
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

    def is_success(self, maze_scene: "MazeWallRemovalScene") -> bool:
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


@dataclass
class MazeWallRemovalScene:
    scene: Any
    manifest: EntityManifest
    layout: MazeWallRemovalLayout
    solver: MazeGraphSolver
    instance: MazeWallRemovalInstance
    wall_edges: tuple[EdgeKey, ...]
    cameras: dict = field(default_factory=dict)
    tabletop: TabletopBaseScene | None = None


class MazeWallRemovalSceneBuilder:
    """Build the tabletop maze wall-removal scene."""

    def __init__(
        self,
        env_cfg,
        task_cfg,
        robot_cfg,
        *,
        seed: int | None = None,
        rigid_options=None,
    ) -> None:
        self.env_cfg = env_cfg
        self.task_cfg = task_cfg
        self.robot_cfg = robot_cfg
        self.seed = seed
        self.rigid_options = rigid_options
        frames = tabletop_frames_from_config(env_cfg)
        self.layout = MazeWallRemovalLayout(
            task_cfg,
            task_origin=frames.task_origin,
        )
        self.solver = MazeGraphSolver(rows=self.layout.rows, cols=self.layout.cols)
        self.generator = MazeWallGenerator(layout=self.layout, solver=self.solver)
        self.instance = self.generator.sample(seed=seed)

    def build(self, *, show_viewer: bool = False) -> MazeWallRemovalScene:
        tabletop_builder = StandardTabletopSceneBuilder(
            self.env_cfg,
            self.robot_cfg,
            rigid_options=self.rigid_options,
        )
        tabletop = tabletop_builder.create(show_viewer=show_viewer)
        scene = tabletop.scene
        manifest = tabletop.manifest

        self._add_board(scene, manifest)
        self._add_cells(scene, manifest)
        self._add_edge_slots(scene, manifest)
        if bool(getattr(self.task_cfg.discard, "visible", False)):
            self._add_discard(scene, manifest)
        self._add_walls(scene, manifest)
        tabletop_builder.finalize(tabletop)
        maze_scene = MazeWallRemovalScene(
            scene=scene,
            manifest=manifest,
            layout=self.layout,
            solver=self.solver,
            instance=self.instance,
            wall_edges=self.instance.initial_blocked_edges,
            cameras=tabletop.cameras,
            tabletop=tabletop,
        )
        self.apply_instance(maze_scene, self.instance)
        return maze_scene

    def apply_instance(self, maze_scene: MazeWallRemovalScene, instance: MazeWallRemovalInstance) -> None:
        active_edges = set(instance.active_blocked_edges)
        for edge in instance.initial_blocked_edges:
            block = maze_scene.manifest.get(self.layout.edge_name(edge))
            index = self.layout.edge_index(edge)
            if edge in active_edges:
                pose = self.layout.edge_pose_for_key(edge, for_wall=True)
                jitter_xy = float(getattr(self.task_cfg.wall_block, "jitter_xy", 0.0))
                jitter_yaw = float(getattr(self.task_cfg.wall_block, "jitter_yaw", 0.0))
                rng = np.random.default_rng(instance.seed + index)
                pos = np.asarray(pose.pos, dtype=float)
                if jitter_xy > 0.0:
                    pos[:2] += rng.uniform(-jitter_xy, jitter_xy, size=2)
                yaw = float(pose.yaw)
                if jitter_yaw > 0.0:
                    yaw += float(rng.uniform(-jitter_yaw, jitter_yaw))
            else:
                pos = self.layout.discard_pos(index)
                yaw = 0.5 * pi
            block.set_pos(tuple(pos), zero_velocity=True)
            block.set_quat(_yaw_quat(yaw), zero_velocity=True, relative=False)
        maze_scene.instance = instance

    def _add_board(self, scene, manifest: EntityManifest) -> None:
        if not box_entity_enabled(self.task_cfg.board):
            return
        manifest.add(
            self.task_cfg.board.name,
            scene.add_entity(
                gs.morphs.Box(
                    pos=tuple(self.layout.position_to_world(self.task_cfg.board.pos)),
                    size=tuple(self.task_cfg.board.size),
                    fixed=True,
                ),
                surface=materials.plastic("board", self.task_cfg.board.color),
                name=self.task_cfg.board.name,
            ),
        )

    def _add_cells(self, scene, manifest: EntityManifest) -> None:
        cell_size = tuple(self.task_cfg.grid.cell_size)
        for row in range(self.layout.rows):
            for col in range(self.layout.cols):
                cell = (row, col)
                name = self.layout.cell_name(row, col)
                manifest.add(
                    name,
                    scene.add_entity(
                        gs.morphs.Box(
                            pos=tuple(self.layout.cell_center(row, col)),
                            size=cell_size,
                            fixed=True,
                        ),
                        surface=materials.plastic(
                            "marker",
                            self.layout.cell_color(
                                cell,
                                a_cell=self.instance.a_cell,
                                b_cell=self.instance.b_cell,
                            ),
                        ),
                        name=name,
                    ),
                )

    def _add_edge_slots(self, scene, manifest: EntityManifest) -> None:
        visualization = bool(getattr(self.task_cfg.edge_slots, "visualization", True))
        collision = bool(getattr(self.task_cfg.edge_slots, "collision", True))
        if not visualization and not collision:
            return
        for index, edge in enumerate(self.layout.all_edge_keys()):
            pose = self.layout.edge_pose_for_key(edge, for_wall=False)
            name = f"maze_edge_slot_{index:02d}"
            manifest.add(
                name,
                scene.add_entity(
                    gs.morphs.Box(
                        pos=tuple(pose.pos),
                        size=tuple(pose.size),
                        fixed=True,
                        visualization=visualization,
                        collision=collision,
                    ),
                    surface=materials.plastic("marker", self.task_cfg.edge_slots.color),
                    name=name,
                ),
            )

    def _add_discard(self, scene, manifest: EntityManifest) -> None:
        manifest.add(
            self.task_cfg.discard.name,
            scene.add_entity(
                gs.morphs.Box(
                    pos=tuple(self.layout.position_to_world(self.task_cfg.discard.pos)),
                    size=tuple(self.task_cfg.discard.size),
                    fixed=True,
                ),
                surface=materials.plastic("board", self.task_cfg.discard.color),
                name=self.task_cfg.discard.name,
            ),
        )

    def _add_walls(self, scene, manifest: EntityManifest) -> None:
        wall_size = tuple(self.task_cfg.wall_block.size)
        for edge in self.instance.initial_blocked_edges:
            name = self.layout.edge_name(edge)
            index = self.layout.edge_index(edge)
            manifest.add(
                name,
                scene.add_entity(
                    gs.morphs.Box(pos=tuple(self.layout.discard_pos(index)), size=wall_size),
                    surface=materials.plastic("object", self.task_cfg.wall_block.color),
                    name=name,
                ),
            )
