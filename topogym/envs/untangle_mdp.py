from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import numpy as np
from omegaconf import OmegaConf


try:
    import gymnasium as gym
    from gymnasium import spaces
except ImportError:  # pragma: no cover - optional dependency in env setup
    gym = None
    spaces = None


Hole = tuple[int, int]
RopePath = tuple[Hole, ...]
Crossing = tuple[int, int, int]


def _list(value):
    if OmegaConf.is_config(value):
        value = OmegaConf.to_container(value, resolve=True)
    return value


def _point_to_hole(point) -> Hole:
    point = _list(point)
    if isinstance(point, dict):
        point = _list(point["hole"])
    return (int(point[0]), int(point[1]))


def _point_lift(point) -> float:
    point = _list(point)
    if not isinstance(point, dict):
        return 0.0
    return float(point.get("layer", 0.0)) + float(point.get("z_offset", 0.0))


@dataclass(frozen=True)
class UntangleTopologyState:
    rope_names: tuple[str, ...]
    rope_paths: tuple[RopePath, ...]
    crossings: tuple[Crossing, ...]
    knots: tuple[tuple[int, int], ...]
    endpoint_overlaps: tuple[Hole, ...] = ()

    @property
    def is_terminal(self) -> bool:
        return not self.crossings and not self.knots and not self.endpoint_overlaps

    @property
    def crossing_count(self) -> int:
        return len(self.crossings) + len(self.knots)

    @property
    def conflict_count(self) -> int:
        return self.crossing_count + len(self.endpoint_overlaps)

    def to_info(self) -> dict[str, Any]:
        return {
            "rope_names": list(self.rope_names),
            "rope_paths": [[list(hole) for hole in path] for path in self.rope_paths],
            "crossings": [
                {
                    "pair": [self.rope_names[first], self.rope_names[second]],
                    "over": self.rope_names[over],
                }
                for first, second, over in self.crossings
            ],
            "knots": [
                [self.rope_names[first], self.rope_names[second]]
                for first, second in self.knots
            ],
            "endpoint_overlaps": [list(hole) for hole in self.endpoint_overlaps],
            "terminal": self.is_terminal,
            "crossing_count": self.crossing_count,
            "conflict_count": self.conflict_count,
        }


@dataclass(frozen=True)
class UntangleHighLevelRewardWeights:
    success: float = 10.0
    crossing: float = 1.0
    wrong_rope: float = 2.0
    invalid: float = 1.0
    pin_overlap: float = 2.0
    step: float = 0.05


class UntangleHighLevelEnv(gym.Env if gym is not None else object):
    """Discrete Untangle MDP over endpoint moves.

    Action convention:
        action = rope_index, endpoint_index, target_hole_index flattened to int.

    Moving the rope that is currently over a crossing can remove that crossing.
    Moving the rope underneath a crossing marks that pair as knotted in this
    high-level topology model.
    """

    metadata = {"render_modes": []}

    def __init__(
        self,
        *,
        task_cfg,
        seed: int | None = None,
        random_reset: bool = True,
        max_episode_steps: int = 12,
        reward_weights: UntangleHighLevelRewardWeights | None = None,
    ) -> None:
        self.task_cfg = task_cfg
        self.rows = int(task_cfg.holes.rows)
        self.cols = int(task_cfg.holes.cols)
        self.random_reset = bool(random_reset)
        self.max_episode_steps = int(max_episode_steps)
        self.reward_weights = reward_weights or UntangleHighLevelRewardWeights()
        self._rng = np.random.default_rng(seed)

        self.rope_names = tuple(str(strand.name) for strand in task_cfg.rope.strands)
        self.rope_count = len(self.rope_names)
        self.hole_count = self.rows * self.cols
        self.num_actions = self.rope_count * 2 * self.hole_count
        pair_count = self.rope_count * (self.rope_count - 1) // 2
        self.num_obs = self.rope_count * 2 * 2 + pair_count + 1

        self.step_index = 0
        self.rope_paths: list[RopePath] = []
        self.over_orders: dict[tuple[int, int], int] = {}
        self.knots: set[tuple[int, int]] = set()

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
        self.knots.clear()
        if self.random_reset:
            self.rope_paths, self.over_orders = self._sample_random_paths()
        else:
            self.rope_paths = list(self._paths_from_config())
            self.over_orders = self._over_orders_from_config()
        obs = self._build_obs()
        return obs, self._build_info(reward_terms={})

    def step(self, action):
        action_index = int(np.asarray(action).reshape(()))
        rope_index, endpoint_index, target_hole = self.action_to_move(action_index)
        state, next_paths, next_over_orders, invalid, wrong_rope = self._preview_move_data(
            rope_index,
            endpoint_index,
            target_hole,
            action_index=action_index,
        )
        if not invalid:
            self.rope_paths = next_paths
            self.over_orders = next_over_orders
            self.knots = set(state.knots)

        self.step_index += 1
        reward, reward_terms = self._compute_reward(
            state,
            invalid=invalid,
            wrong_rope=wrong_rope,
        )
        terminated = state.is_terminal
        truncated = self.step_index >= self.max_episode_steps
        obs = self._build_obs()
        info = self._build_info(
            reward_terms=reward_terms,
            invalid_action=invalid,
            wrong_rope=wrong_rope,
            move=(rope_index, endpoint_index, target_hole),
        )
        return obs, reward, terminated, truncated, info

    def close(self) -> None:
        return None

    def sample_random_action(self) -> int:
        if self.action_space is not None:
            return int(self.action_space.sample())
        return int(self._rng.integers(0, self.num_actions))

    def action_to_move(self, action: int) -> tuple[int, int, Hole]:
        action = int(action)
        hole_index = action % self.hole_count
        endpoint_index = (action // self.hole_count) % 2
        rope_index = action // (self.hole_count * 2)
        row = hole_index // self.cols
        col = hole_index % self.cols
        return rope_index, endpoint_index, (row, col)

    def move_to_action(self, rope_index: int, endpoint_index: int, target_hole: Hole) -> int:
        row, col = target_hole
        hole_index = int(row) * self.cols + int(col)
        return int(rope_index) * self.hole_count * 2 + int(endpoint_index) * self.hole_count + hole_index

    def topology_state(self) -> UntangleTopologyState:
        return self._state()

    def preview_move(
        self,
        rope_index: int,
        endpoint_index: int,
        target_hole: Hole,
    ) -> tuple[UntangleTopologyState, bool, bool]:
        state, _, _, invalid, wrong_rope = self._preview_move_data(
            rope_index,
            endpoint_index,
            target_hole,
        )
        return state, invalid, wrong_rope

    def _sample_random_paths(self) -> tuple[list[RopePath], dict[tuple[int, int], int]]:
        if self.rope_count < 3:
            raise ValueError("UntangleHighLevelEnv expects at least three ropes.")

        crossing_pair = tuple(self._rng.choice(self.rope_count, size=2, replace=False))
        vertical_rope, horizontal_rope = int(crossing_pair[0]), int(crossing_pair[1])
        over_rope = int(self._rng.choice([vertical_rope, horizontal_rope]))

        row = int(self._rng.integers(1, max(2, self.rows - 1)))
        col = int(self._rng.integers(1, max(2, self.cols - 1)))
        paths: list[RopePath] = [((0, 0), (0, 1)) for _ in range(self.rope_count)]
        paths[vertical_rope] = ((0, col), (self.rows - 1, col))
        paths[horizontal_rope] = ((row, 0), (row, self.cols - 1))

        unused = [index for index in range(self.rope_count) if index not in (vertical_rope, horizontal_rope)]
        for index, rope_index in enumerate(unused):
            safe_row = 0 if row != 0 else self.rows - 1
            start_col = max(0, self.cols - 2 - index)
            end_col = min(self.cols - 1, start_col + 1)
            paths[rope_index] = ((safe_row, start_col), (safe_row, end_col))

        key = (min(vertical_rope, horizontal_rope), max(vertical_rope, horizontal_rope))
        return paths, {key: over_rope}

    def _paths_from_config(self) -> tuple[RopePath, ...]:
        paths: list[RopePath] = []
        for strand in self.task_cfg.rope.strands:
            paths.append(tuple(_point_to_hole(point) for point in strand.points))
        return tuple(paths)

    def _over_orders_from_config(self) -> dict[tuple[int, int], int]:
        lifts = [
            max((_point_lift(point) for point in strand.points), default=0.0)
            for strand in self.task_cfg.rope.strands
        ]
        over_orders: dict[tuple[int, int], int] = {}
        for first, second in self._crossing_pairs_for_paths(self.rope_paths):
            over_orders[(first, second)] = first if lifts[first] >= lifts[second] else second
        return over_orders

    def _refreshed_over_orders(
        self,
        paths: list[RopePath],
        old_over_orders: dict[tuple[int, int], int],
        *,
        moved_rope: int,
    ) -> dict[tuple[int, int], int]:
        current_pairs = set(self._crossing_pairs_for_paths(paths))
        return {
            pair: old_over_orders.get(pair, moved_rope if moved_rope in pair else pair[0])
            for pair in current_pairs
        }

    def _preview_move_data(
        self,
        rope_index: int,
        endpoint_index: int,
        target_hole: Hole,
        *,
        action_index: int | None = None,
    ) -> tuple[
        UntangleTopologyState,
        list[RopePath],
        dict[tuple[int, int], int],
        bool,
        bool,
    ]:
        invalid = (
            (action_index is not None and (action_index < 0 or action_index >= self.num_actions))
            or rope_index < 0
            or rope_index >= self.rope_count
            or endpoint_index not in (0, 1)
            or not self._is_valid_hole(target_hole)
        )
        paths = list(self.rope_paths)
        over_orders = dict(self.over_orders)
        knots = set(self.knots)
        wrong_rope = False

        if not invalid and self._target_occupied_by_other_endpoint(
            paths,
            rope_index=rope_index,
            endpoint_index=endpoint_index,
            target_hole=target_hole,
        ):
            invalid = True

        if not invalid:
            old_crossings = self._crossings_for(paths, over_orders)
            involved = [crossing for crossing in old_crossings if rope_index in crossing[:2]]
            wrong_rope = any(crossing[2] != rope_index for crossing in involved)
            if wrong_rope:
                for first, second, _ in involved:
                    knots.add((min(first, second), max(first, second)))

            path = list(paths[rope_index])
            start = target_hole if endpoint_index == 0 else path[0]
            end = target_hole if endpoint_index == 1 else path[-1]
            paths[rope_index] = (start, end)
            over_orders = self._refreshed_over_orders(
                paths,
                over_orders,
                moved_rope=rope_index,
            )

        crossings = self._crossings_for(paths, over_orders)
        state = UntangleTopologyState(
            rope_names=self.rope_names,
            rope_paths=tuple(paths),
            crossings=tuple(crossings),
            knots=tuple(sorted(knots)),
            endpoint_overlaps=self._endpoint_overlap_holes(paths),
        )
        return state, paths, over_orders, invalid, wrong_rope

    def _state(self) -> UntangleTopologyState:
        return UntangleTopologyState(
            rope_names=self.rope_names,
            rope_paths=tuple(self.rope_paths),
            crossings=tuple(self._crossings()),
            knots=tuple(sorted(self.knots)),
            endpoint_overlaps=self._endpoint_overlap_holes(self.rope_paths),
        )

    def _crossings(self) -> list[Crossing]:
        return self._crossings_for(self.rope_paths, self.over_orders)

    def _crossings_for(
        self,
        paths: list[RopePath],
        over_orders: dict[tuple[int, int], int],
    ) -> list[Crossing]:
        crossings: list[Crossing] = []
        for first, second in self._crossing_pairs_for_paths(paths):
            over = over_orders.get((first, second), first)
            crossings.append((first, second, over))
        return crossings

    def _crossing_pairs_for_paths(self, paths: list[RopePath]) -> list[tuple[int, int]]:
        pairs: list[tuple[int, int]] = []
        for first in range(len(paths)):
            for second in range(first + 1, len(paths)):
                if self._paths_cross(paths[first], paths[second]):
                    pairs.append((first, second))
        return pairs

    def _paths_cross(self, path_a: RopePath, path_b: RopePath) -> bool:
        internal_a = set(path_a[1:-1])
        internal_b = set(path_b[1:-1])
        if (internal_a & set(path_b)) or (internal_b & set(path_a)):
            return True
        for point in internal_a:
            if any(_point_on_segment(point, start, end) for start, end in zip(path_b, path_b[1:])):
                return True
        for point in internal_b:
            if any(_point_on_segment(point, start, end) for start, end in zip(path_a, path_a[1:])):
                return True
        for a0, a1 in zip(path_a, path_a[1:]):
            for b0, b1 in zip(path_b, path_b[1:]):
                if _segments_cross(a0, a1, b0, b1):
                    return True
        return False

    def _is_valid_hole(self, hole: Hole) -> bool:
        row, col = hole
        return 0 <= row < self.rows and 0 <= col < self.cols

    def _target_occupied_by_other_endpoint(
        self,
        paths: list[RopePath],
        *,
        rope_index: int,
        endpoint_index: int,
        target_hole: Hole,
    ) -> bool:
        for other_rope_index, path in enumerate(paths):
            endpoints = ((0, path[0]), (1, path[-1]))
            for other_endpoint_index, hole in endpoints:
                if other_rope_index == rope_index and other_endpoint_index == endpoint_index:
                    continue
                if hole == target_hole:
                    return True
        return False

    def _endpoint_overlap_holes(self, paths: list[RopePath]) -> tuple[Hole, ...]:
        occupied: dict[Hole, int] = {}
        overlaps: set[Hole] = set()
        for path in paths:
            for hole in (path[0], path[-1]):
                occupied[hole] = occupied.get(hole, 0) + 1
                if occupied[hole] > 1:
                    overlaps.add(hole)
        return tuple(sorted(overlaps))

    def _build_obs(self) -> np.ndarray:
        values: list[float] = []
        row_den = max(1, self.rows - 1)
        col_den = max(1, self.cols - 1)
        for path in self.rope_paths:
            for hole in (path[0], path[-1]):
                values.extend([float(hole[0]) / row_den, float(hole[1]) / col_den])

        crossings = {(first, second): over for first, second, over in self._crossings()}
        for first in range(self.rope_count):
            for second in range(first + 1, self.rope_count):
                over = crossings.get((first, second))
                if over is None:
                    values.append(0.0)
                elif over == first:
                    values.append(0.5)
                else:
                    values.append(1.0)
        values.append(min(1.0, float(len(self.knots))))
        return np.asarray(values, dtype=np.float32)

    def _compute_reward(
        self,
        state: UntangleTopologyState,
        *,
        invalid: bool,
        wrong_rope: bool,
    ) -> tuple[float, dict[str, float]]:
        weights = self.reward_weights
        terms = {
            "success": float(state.is_terminal),
            "crossing": -float(state.crossing_count),
            "wrong_rope": -float(wrong_rope),
            "invalid": -float(invalid),
            "pin_overlap": -float(len(state.endpoint_overlaps)),
            "step": -1.0,
        }
        reward = (
            weights.success * terms["success"]
            + weights.crossing * terms["crossing"]
            + weights.wrong_rope * terms["wrong_rope"]
            + weights.invalid * terms["invalid"]
            + weights.pin_overlap * terms["pin_overlap"]
            + weights.step * terms["step"]
        )
        return float(reward), terms

    def _build_info(
        self,
        *,
        reward_terms: dict[str, float],
        invalid_action: bool = False,
        wrong_rope: bool = False,
        move: tuple[int, int, Hole] | None = None,
    ) -> dict[str, Any]:
        state = self._state()
        move_info = None
        if move is not None:
            rope_index, endpoint_index, target_hole = move
            rope_name = self.rope_names[rope_index] if 0 <= rope_index < self.rope_count else "<invalid>"
            move_info = {
                "rope": rope_name,
                "endpoint": "start" if endpoint_index == 0 else "end",
                "target_hole": list(target_hole),
            }
        return {
            "success": state.is_terminal,
            "terminal": state.is_terminal,
            "invalid_action": bool(invalid_action),
            "wrong_rope": bool(wrong_rope),
            "move": move_info,
            "reward_terms": reward_terms,
            "topology_state": state.to_info(),
            "step_index": self.step_index,
        }


def _segments_cross(a0: Hole, a1: Hole, b0: Hole, b1: Hole) -> bool:
    # Coordinates are grid-space (x=col, y=row). Endpoint touches are not
    # counted as crossings; only proper segment intersections matter.
    if len({a0, a1, b0, b1}) < 4:
        return False

    pa0 = np.array([a0[1], a0[0]], dtype=float)
    pa1 = np.array([a1[1], a1[0]], dtype=float)
    pb0 = np.array([b0[1], b0[0]], dtype=float)
    pb1 = np.array([b1[1], b1[0]], dtype=float)

    oa = _orient(pa0, pa1, pb0)
    ob = _orient(pa0, pa1, pb1)
    oc = _orient(pb0, pb1, pa0)
    od = _orient(pb0, pb1, pa1)
    return bool(oa * ob < 0.0 and oc * od < 0.0)


def _orient(a: np.ndarray, b: np.ndarray, c: np.ndarray) -> float:
    return float((b[0] - a[0]) * (c[1] - a[1]) - (b[1] - a[1]) * (c[0] - a[0]))


def _point_on_segment(point: Hole, start: Hole, end: Hole) -> bool:
    if point == start or point == end:
        return False
    p = np.array([point[1], point[0]], dtype=float)
    a = np.array([start[1], start[0]], dtype=float)
    b = np.array([end[1], end[0]], dtype=float)
    if abs(_orient(a, b, p)) > 1e-8:
        return False
    return bool(
        min(a[0], b[0]) < p[0] < max(a[0], b[0])
        or min(a[1], b[1]) < p[1] < max(a[1], b[1])
    )
