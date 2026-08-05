from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import numpy as np

from topogym.tasks import OneStrokeLayout
from topogym.verification import OneStrokePuzzleState

try:
    import gymnasium as gym
    from gymnasium import spaces
except ImportError:  # pragma: no cover - optional dependency in env setup
    gym = None
    spaces = None


@dataclass(frozen=True)
class OneStrokeHighLevelRewardWeights:
    success: float = 10.0
    progress: float = 1.0
    invalid: float = 1.0
    step: float = 0.05


class OneStrokeHighLevelEnv(gym.Env if gym is not None else object):
    """Discrete OneStroke MDP over wall placements.

    Action convention:
        action = edge_index

    Each action places one wall block on one adjacent-cell edge. The env tracks
    only the puzzle topology, not the Franka or Genesis physics scene.
    """

    metadata = {"render_modes": []}

    def __init__(
        self,
        *,
        task_cfg,
        seed: int | None = None,
        random_reset: bool = True,
        max_episode_steps: int = 24,
        wall_block_count: int | None = None,
        reward_weights: OneStrokeHighLevelRewardWeights | None = None,
    ) -> None:
        self.task_cfg = task_cfg
        self.layout = OneStrokeLayout(task_cfg)
        self.random_reset = bool(random_reset)
        self.max_episode_steps = int(max_episode_steps)
        self.wall_block_count = int(wall_block_count or self.layout.wall_count)
        self.reward_weights = reward_weights or OneStrokeHighLevelRewardWeights()
        self._rng = np.random.default_rng(seed)

        self.edge_keys = tuple(self.layout.all_edge_keys())
        self.num_actions = len(self.edge_keys)
        self.num_obs = self.layout.rows * self.layout.cols + self.num_actions + 1

        self.step_index = 0
        self.cell_labels = self.layout.cell_labels()
        self.placed_edges: set[tuple[int, int, int, int]] = set()
        self.supply_count = self.wall_block_count

        if spaces is not None:
            self.action_space = spaces.Discrete(self.num_actions)
            self.observation_space = spaces.Box(
                low=0.0,
                high=1.0,
                shape=(self.num_obs,),
                dtype=np.float32,
            )
        else:
            self.action_space = None
            self.observation_space = None

    def reset(self, *, seed: int | None = None, options: dict | None = None):
        del options
        if gym is not None:
            super().reset(seed=seed)
        if seed is not None:
            self._rng = np.random.default_rng(seed)
        self.step_index = 0
        self.cell_labels = self._sample_labels() if self.random_reset else self.layout.cell_labels()
        self.placed_edges.clear()
        self.supply_count = self.wall_block_count
        obs = self._build_obs()
        return obs, self._build_info(reward_terms={})

    def step(self, action):
        edge_index = int(np.asarray(action).reshape(()))
        invalid = False
        placed_edge = None

        if edge_index < 0 or edge_index >= self.num_actions:
            invalid = True
        else:
            placed_edge = self.edge_keys[edge_index]
            if placed_edge in self.placed_edges:
                invalid = True
            else:
                self.placed_edges.add(placed_edge)
                self.supply_count -= 1
                if self.supply_count <= 0:
                    self.supply_count = self.wall_block_count

        self.step_index += 1
        obs = self._build_obs()
        state = self._state()
        reward, reward_terms = self._compute_reward(state, invalid=invalid)
        terminated = state.is_terminal
        truncated = self.step_index >= self.max_episode_steps
        info = self._build_info(
            reward_terms=reward_terms,
            invalid_action=invalid,
            placed_edge=placed_edge,
        )
        return obs, reward, terminated, truncated, info

    def close(self) -> None:
        return None

    def sample_random_action(self) -> int:
        if self.action_space is not None:
            return int(self.action_space.sample())
        return int(self._rng.integers(0, self.num_actions))

    def action_to_edge(self, action: int) -> tuple[int, int, int, int]:
        return self.edge_keys[int(action)]

    def edge_to_action(self, edge_key: tuple[int, int, int, int]) -> int:
        return self.edge_keys.index(edge_key)

    def _sample_labels(self) -> tuple[tuple[str, ...], ...]:
        rows = self.layout.rows
        cols = self.layout.cols
        cells = [(row, col) for row in range(rows) for col in range(cols)]
        color_a = self.layout.color_a_label()
        color_b = self.layout.color_b_label()
        empty = str(getattr(getattr(self.task_cfg, "puzzle", None), "empty_label", "gray"))

        max_region = max(2, min(4, (rows * cols) // 2))
        for _ in range(200):
            a_count = int(self._rng.integers(2, max_region + 1))
            b_count = int(self._rng.integers(2, max_region + 1))
            if a_count + b_count > rows * cols:
                continue
            region_a = self._grow_region(cells, count=a_count, blocked=set())
            region_b = self._grow_region(cells, count=b_count, blocked=region_a)
            if len(region_b) != b_count:
                continue

            labels = [[empty for _ in range(cols)] for _ in range(rows)]
            for row, col in region_a:
                labels[row][col] = color_a
            for row, col in region_b:
                labels[row][col] = color_b
            candidate = tuple(tuple(row) for row in labels)
            if not self._state_for(candidate, placed_edges=()).is_terminal:
                return candidate

        return self.layout.cell_labels()

    def _grow_region(
        self,
        cells: list[tuple[int, int]],
        *,
        count: int,
        blocked: set[tuple[int, int]],
    ) -> set[tuple[int, int]]:
        available = [cell for cell in cells if cell not in blocked]
        if not available:
            return set()
        seed = available[int(self._rng.integers(0, len(available)))]
        region = {seed}
        frontier = set(self._neighbors(*seed)) - blocked - region
        while len(region) < count and frontier:
            options = tuple(frontier)
            cell = options[int(self._rng.integers(0, len(options)))]
            frontier.remove(cell)
            region.add(cell)
            frontier.update(set(self._neighbors(*cell)) - blocked - region)
        return region

    def _neighbors(self, row: int, col: int) -> tuple[tuple[int, int], ...]:
        neighbors: list[tuple[int, int]] = []
        if row > 0:
            neighbors.append((row - 1, col))
        if row + 1 < self.layout.rows:
            neighbors.append((row + 1, col))
        if col > 0:
            neighbors.append((row, col - 1))
        if col + 1 < self.layout.cols:
            neighbors.append((row, col + 1))
        return tuple(neighbors)

    def _build_obs(self) -> np.ndarray:
        label_values = {
            str(getattr(getattr(self.task_cfg, "puzzle", None), "empty_label", "gray")): 0.0,
            self.layout.color_a_label(): 0.5,
            self.layout.color_b_label(): 1.0,
        }
        cells = [
            label_values.get(str(label), 0.0)
            for row in self.cell_labels
            for label in row
        ]
        edge_mask = [1.0 if edge in self.placed_edges else 0.0 for edge in self.edge_keys]
        supply = [float(self.supply_count) / max(1, float(self.wall_block_count))]
        return np.asarray(cells + edge_mask + supply, dtype=np.float32)

    def _state(self) -> OneStrokePuzzleState:
        return self._state_for(self.cell_labels, placed_edges=tuple(sorted(self.placed_edges)))

    def _state_for(
        self,
        cell_labels: tuple[tuple[str, ...], ...],
        *,
        placed_edges: tuple[tuple[int, int, int, int], ...],
    ) -> OneStrokePuzzleState:
        return OneStrokePuzzleState(
            cell_labels=cell_labels,
            placed_edges=placed_edges,
            unused_walls=(),
            invalid_walls=(),
            duplicate_edges={},
            color_a=self.layout.color_a_label(),
            color_b=self.layout.color_b_label(),
        )

    def _compute_reward(
        self,
        state: OneStrokePuzzleState,
        *,
        invalid: bool,
    ) -> tuple[float, dict[str, float]]:
        weights = self.reward_weights
        terms = {
            "success": float(state.is_terminal),
            "progress": -float(state.unseparated_component_count()),
            "invalid": -float(invalid),
            "step": -1.0,
        }
        reward = (
            weights.success * terms["success"]
            + weights.progress * terms["progress"]
            + weights.invalid * terms["invalid"]
            + weights.step * terms["step"]
        )
        return float(reward), terms

    def _build_info(
        self,
        *,
        reward_terms: dict[str, float],
        invalid_action: bool = False,
        placed_edge: tuple[int, int, int, int] | None = None,
    ) -> dict[str, Any]:
        state = self._state()
        return {
            "success": state.is_terminal,
            "terminal": state.is_terminal,
            "invalid_action": bool(invalid_action),
            "placed_edge": placed_edge,
            "remaining_supply": self.supply_count,
            "reward_terms": reward_terms,
            "topology_state": state.to_info(),
            "step_index": self.step_index,
        }
