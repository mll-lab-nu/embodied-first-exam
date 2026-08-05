from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import numpy as np

from topogym.tasks.legacy.maze_wall_removal import (
    EdgeKey,
    MazeGraphSolver,
    MazeWallGenerator,
    MazeWallRemovalInstance,
    MazeWallRemovalLayout,
)
from topogym.verification import MazeWallRemovalPuzzleState

try:
    import gymnasium as gym
    from gymnasium import spaces
except ImportError:  # pragma: no cover - optional dependency in env setup
    gym = None
    spaces = None


@dataclass(frozen=True)
class MazeWallRemovalRewardWeights:
    success: float = 10.0
    progress: float = 2.0
    remove: float = 0.25
    excess: float = 2.0
    invalid: float = 1.0
    step: float = 0.03


class MazeWallRemovalHighLevelEnv(gym.Env if gym is not None else object):
    """Discrete MDP for choosing which maze wall to remove.

    Action convention:
        action = edge_index

    Each valid action removes the wall block currently occupying that edge. The
    episode ends when A and B are connected in the cell adjacency graph.
    """

    metadata = {"render_modes": []}

    def __init__(
        self,
        *,
        task_cfg,
        seed: int | None = None,
        max_episode_steps: int | None = None,
        reward_weights: MazeWallRemovalRewardWeights | None = None,
    ) -> None:
        self.task_cfg = task_cfg
        self.layout = MazeWallRemovalLayout(task_cfg)
        self.solver = MazeGraphSolver(rows=self.layout.rows, cols=self.layout.cols)
        self.generator = MazeWallGenerator(layout=self.layout, solver=self.solver)
        self.max_episode_steps = int(max_episode_steps or self.task_cfg.mdp.max_episode_steps)
        self.reward_weights = reward_weights or self._weights_from_cfg()
        self._rng = np.random.default_rng(seed)

        self.edge_keys = tuple(self.layout.all_edge_keys())
        self.num_actions = len(self.edge_keys)
        self.num_cells = self.layout.rows * self.layout.cols
        self.num_obs = self.num_actions + 2 * self.num_cells + 2

        self.step_index = 0
        self.instance: MazeWallRemovalInstance | None = None
        self.active_blocked_edges: set[EdgeKey] = set()

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
        episode_seed = int(self._rng.integers(0, np.iinfo(np.int32).max))
        self.instance = self.generator.sample(seed=episode_seed)
        self.active_blocked_edges = set(self.instance.active_blocked_edges)
        self.step_index = 0
        obs = self._build_obs()
        return obs, self._build_info(reward_terms={})

    def step(self, action):
        edge_index = int(np.asarray(action).reshape(()))
        invalid = False
        removed_edge = None
        previous_min = self._current_min_wall_count()

        if edge_index < 0 or edge_index >= self.num_actions:
            invalid = True
        else:
            edge = self.edge_keys[edge_index]
            if edge not in self.active_blocked_edges:
                invalid = True
            else:
                self.active_blocked_edges.remove(edge)
                removed_edge = edge

        self.step_index += 1
        state = self._state()
        reward, reward_terms = self._compute_reward(
            state,
            previous_min=previous_min,
            invalid=invalid,
        )
        terminated = state.is_terminal
        truncated = self.step_index >= self.max_episode_steps
        obs = self._build_obs()
        info = self._build_info(
            reward_terms=reward_terms,
            invalid_action=invalid,
            removed_edge=removed_edge,
        )
        return obs, reward, terminated, truncated, info

    def close(self) -> None:
        return None

    def sample_random_action(self) -> int:
        if self.action_space is not None:
            return int(self.action_space.sample())
        return int(self._rng.integers(0, self.num_actions))

    def oracle_actions(self) -> tuple[int, ...]:
        self._require_instance()
        return tuple(self.layout.edge_index(edge) for edge in self.instance.oracle_edges)

    def action_to_edge(self, action: int) -> EdgeKey:
        return self.edge_keys[int(action)]

    def edge_to_action(self, edge_key: EdgeKey) -> int:
        return self.layout.edge_index(edge_key)

    def _weights_from_cfg(self) -> MazeWallRemovalRewardWeights:
        reward_cfg = self.task_cfg.mdp.reward
        return MazeWallRemovalRewardWeights(
            success=float(reward_cfg.success),
            progress=float(reward_cfg.progress),
            remove=float(reward_cfg.remove),
            excess=float(reward_cfg.excess),
            invalid=float(reward_cfg.invalid),
            step=float(reward_cfg.step),
        )

    def _require_instance(self) -> None:
        if self.instance is None:
            raise RuntimeError("Call reset() before using this env.")

    def _cell_flat_index(self, cell: tuple[int, int]) -> int:
        return int(cell[0]) * self.layout.cols + int(cell[1])

    def _build_obs(self) -> np.ndarray:
        self._require_instance()
        active_mask = [1.0 if edge in self.active_blocked_edges else 0.0 for edge in self.edge_keys]
        a_onehot = [0.0] * self.num_cells
        b_onehot = [0.0] * self.num_cells
        a_onehot[self._cell_flat_index(self.instance.a_cell)] = 1.0
        b_onehot[self._cell_flat_index(self.instance.b_cell)] = 1.0
        min_wall = self._current_min_wall_count()
        progress_scalars = [
            float(min_wall) / max(1.0, float(self.instance.optimal_wall_count)),
            float(len(self._removed_edges())) / max(1.0, float(self.num_actions)),
        ]
        return np.asarray(active_mask + a_onehot + b_onehot + progress_scalars, dtype=np.float32)

    def _state(self) -> MazeWallRemovalPuzzleState:
        self._require_instance()
        active = tuple(sorted(self.active_blocked_edges))
        removed = tuple(sorted(set(self.instance.initial_blocked_edges) - self.active_blocked_edges))
        current_min = self._current_min_wall_count()
        return MazeWallRemovalPuzzleState(
            a_cell=self.instance.a_cell,
            b_cell=self.instance.b_cell,
            initial_blocked_edges=self.instance.initial_blocked_edges,
            active_blocked_edges=active,
            removed_edges=removed,
            oracle_edges=self.instance.oracle_edges,
            invalid_walls=(),
            duplicate_edges={},
            optimal_wall_count=self.instance.optimal_wall_count,
            current_min_wall_count=current_min,
            component_count=self.solver.component_count(active),
        )

    def _current_min_wall_count(self) -> int:
        self._require_instance()
        cost, _, _ = self.solver.min_wall_path(
            self.active_blocked_edges,
            self.instance.a_cell,
            self.instance.b_cell,
        )
        return int(cost)

    def _removed_edges(self) -> tuple[EdgeKey, ...]:
        self._require_instance()
        return tuple(sorted(set(self.instance.initial_blocked_edges) - self.active_blocked_edges))

    def _compute_reward(
        self,
        state: MazeWallRemovalPuzzleState,
        *,
        previous_min: int,
        invalid: bool,
    ) -> tuple[float, dict[str, float]]:
        weights = self.reward_weights
        progress = float(max(0, previous_min - state.current_min_wall_count))
        terms = {
            "success": float(state.is_terminal),
            "progress": progress,
            "remove": -float(len(state.removed_edges)),
            "excess": -float(state.excess_removed),
            "invalid": -float(invalid),
            "step": -1.0,
        }
        reward = (
            weights.success * terms["success"]
            + weights.progress * terms["progress"]
            + weights.remove * terms["remove"]
            + weights.excess * terms["excess"]
            + weights.invalid * terms["invalid"]
            + weights.step * terms["step"]
        )
        return float(reward), terms

    def _build_info(
        self,
        *,
        reward_terms: dict[str, float],
        invalid_action: bool = False,
        removed_edge: EdgeKey | None = None,
    ) -> dict[str, Any]:
        state = self._state()
        return {
            "success": state.is_terminal,
            "terminal": state.is_terminal,
            "invalid_action": bool(invalid_action),
            "removed_edge": removed_edge,
            "reward_terms": reward_terms,
            "topology_state": state.to_info(),
            "step_index": self.step_index,
        }
