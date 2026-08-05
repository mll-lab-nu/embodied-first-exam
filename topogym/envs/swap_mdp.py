from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import numpy as np

from topogym.verification import SwapPuzzleEvaluator

try:
    import gymnasium as gym
    from gymnasium import spaces
except ImportError:  # pragma: no cover - optional dependency in docs/env_setup.sh
    gym = None
    spaces = None


def _as_numpy(value) -> np.ndarray:
    if hasattr(value, "detach"):
        return value.detach().cpu().numpy()
    return np.asarray(value)


def _xyz(value) -> np.ndarray:
    return _as_numpy(value).reshape(-1, 3)[0].astype(np.float32)


@dataclass(frozen=True)
class SwapRewardWeights:
    reach: float = 1.0
    place: float = 2.0
    lift: float = 1.0
    success: float = 10.0
    action: float = 0.01
    step: float = 0.01


class SwapMdpEnv(gym.Env if gym is not None else object):
    """Single-env Gymnasium wrapper for the physical Swap scene.

    MVP action convention:
        action = [dx, dy, dz, gripper]

    The first three entries are normalized end-effector deltas in [-1, 1],
    scaled by robot_control.action_protocol.max_delta_xyz. The gripper entry is
    continuous: -1 means closed, +1 means open.
    """

    metadata = {"render_modes": []}

    def __init__(
        self,
        *,
        swap_scene,
        controller,
        robot_cfg,
        max_episode_steps: int = 150,
        reward_weights: SwapRewardWeights | None = None,
        success_tolerance_xy: float = 0.04,
        lift_height: float = 0.07,
    ) -> None:
        self.swap_scene = swap_scene
        self.scene = swap_scene.scene
        self.manifest = swap_scene.manifest
        self.layout = swap_scene.layout
        self.controller = controller
        self.robot_cfg = robot_cfg
        self.max_episode_steps = int(max_episode_steps)
        self.reward_weights = reward_weights or SwapRewardWeights()
        self.success_tolerance_xy = float(success_tolerance_xy)
        self.puzzle_evaluator = SwapPuzzleEvaluator(tolerance_xy=self.success_tolerance_xy)
        self.lift_height = float(lift_height)
        self.step_index = 0
        self._rng = np.random.default_rng()
        self._initial_scene_state = self._capture_scene_state()

        self.block_names = list(self.layout.cfg.blocks.keys())
        self.target_block_name = self.layout.block_to_move
        self.target_block = self.manifest.get(self.target_block_name)
        self.target_center = self.layout.block_center_for_slot(
            self.layout.target_slot, self.target_block_name
        ).astype(np.float32)
        self.source_center = self.layout.block_center_for_slot(
            self.layout.source_slot, self.target_block_name
        ).astype(np.float32)

        protocol = self.robot_cfg.action_protocol
        self.max_delta_xyz = float(protocol.max_delta_xyz)
        workspace = protocol.workspace
        self.workspace_low = np.array(
            [workspace.x[0], workspace.y[0], workspace.z[0]], dtype=np.float32
        )
        self.workspace_high = np.array(
            [workspace.x[1], workspace.y[1], workspace.z[1]], dtype=np.float32
        )
        self.control_steps = int(self.robot_cfg.control_loop.steps_per_action)

        self.num_actions = 4
        self.num_obs = len(self._build_obs())
        if spaces is not None:
            self.action_space = spaces.Box(
                low=-1.0, high=1.0, shape=(self.num_actions,), dtype=np.float32
            )
            self.observation_space = spaces.Box(
                low=-np.inf, high=np.inf, shape=(self.num_obs,), dtype=np.float32
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
        self._restore_scene_state()
        self.controller.reset_home()
        obs = self._build_obs()
        return obs, self._build_info(reward_terms={})

    def step(self, action):
        action = np.asarray(action, dtype=np.float32).reshape(self.num_actions)
        clipped = np.clip(action, -1.0, 1.0)

        hand = self.controller.hand_pos().astype(np.float32)
        delta = clipped[:3] * self.max_delta_xyz
        ee_target = np.clip(hand + delta, self.workspace_low, self.workspace_high)

        open_qpos = float(self.robot_cfg.gripper.open_qpos)
        closed_qpos = float(self.robot_cfg.gripper.closed_qpos)
        gripper_alpha = 0.5 * (float(clipped[3]) + 1.0)
        gripper_qpos = closed_qpos + gripper_alpha * (open_qpos - closed_qpos)

        self.controller.set_gripper(gripper_qpos)
        self.controller.move_ee_to(ee_target, steps=self.control_steps)
        self.step_index += 1

        obs = self._build_obs()
        reward, reward_terms = self._compute_reward(clipped)
        success = self._is_success()
        terminated = success
        truncated = self.step_index >= self.max_episode_steps
        info = self._build_info(reward_terms=reward_terms)
        return obs, reward, terminated, truncated, info

    def close(self) -> None:
        return None

    def sample_random_action(self) -> np.ndarray:
        if self.action_space is not None:
            return self.action_space.sample()
        return self._rng.uniform(-1.0, 1.0, size=(self.num_actions,)).astype(np.float32)

    def _capture_scene_state(self):
        get_state = getattr(self.scene, "get_state", None)
        if get_state is None:
            return None
        try:
            return get_state()
        except Exception:
            return None

    def _restore_scene_state(self) -> None:
        if self._initial_scene_state is None:
            return
        reset = getattr(self.scene, "reset", None)
        if reset is None:
            return
        try:
            reset(self._initial_scene_state)
        except TypeError:
            try:
                reset(state=self._initial_scene_state)
            except TypeError:
                reset()

    def _block_pos(self, name: str) -> np.ndarray:
        return _xyz(self.manifest.get(name).get_pos())

    def _build_obs(self) -> np.ndarray:
        hand = self.controller.hand_pos().astype(np.float32)
        gripper = np.array(
            [self.controller.current_gripper_qpos / float(self.robot_cfg.gripper.open_qpos)],
            dtype=np.float32,
        )
        block_positions = [self._block_pos(name) for name in self.block_names]
        target_block_pos = self._block_pos(self.target_block_name)
        obs_parts = [
            hand,
            gripper,
            *block_positions,
            target_block_pos - hand,
            self.target_center - target_block_pos,
            self.target_center[:2] - hand[:2],
            np.array([self._is_lifted(target_block_pos)], dtype=np.float32),
        ]
        return np.concatenate(obs_parts).astype(np.float32)

    def _compute_reward(self, action: np.ndarray) -> tuple[float, dict[str, float]]:
        weights = self.reward_weights
        hand = self.controller.hand_pos().astype(np.float32)
        block = self._block_pos(self.target_block_name)
        reach_dist = float(np.linalg.norm((block - hand)[:3]))
        place_dist = float(np.linalg.norm((self.target_center - block)[:2]))
        is_lifted = self._is_lifted(block)
        success = self._is_success()

        terms = {
            "reach": -reach_dist,
            "place": -place_dist,
            "lift": is_lifted,
            "success": float(success),
            "action": -float(np.linalg.norm(action)),
            "step": -1.0,
        }
        reward = (
            weights.reach * terms["reach"]
            + weights.place * terms["place"]
            + weights.lift * terms["lift"]
            + weights.success * terms["success"]
            + weights.action * terms["action"]
            + weights.step * terms["step"]
        )
        return float(reward), terms

    def _is_lifted(self, block_pos: np.ndarray | None = None) -> float:
        if block_pos is None:
            block_pos = self._block_pos(self.target_block_name)
        return float(block_pos[2] >= self.source_center[2] + self.lift_height)

    def _is_success(self) -> bool:
        return self.puzzle_evaluator.is_success(self.swap_scene)

    def _topology_state(self) -> dict[str, Any]:
        state = self.puzzle_evaluator.classify(self.swap_scene).to_info()
        state.update(
            {
                "target_slot": self.layout.target_slot,
                "source_slot": self.layout.source_slot,
                "block_to_move": self.target_block_name,
            }
        )
        return state

    def _build_info(self, *, reward_terms: dict[str, float]) -> dict[str, Any]:
        block = self._block_pos(self.target_block_name)
        topology_state = self._topology_state()
        success = bool(topology_state["terminal"])
        return {
            "success": success,
            "terminal": success,
            "is_lifted": bool(self._is_lifted(block)),
            "target_block_pos": block.copy(),
            "target_center": self.target_center.copy(),
            "reward_terms": reward_terms,
            "topology_state": topology_state,
            "step_index": self.step_index,
        }


class RslRlSwapAdapter:
    """Small rsl-rl VecEnv adapter around the single-env SwapMdpEnv."""

    def __init__(self, env: SwapMdpEnv, *, device: str = "cpu", auto_reset: bool = True) -> None:
        import torch

        self.env = env
        self.num_envs = 1
        self.num_obs = env.num_obs
        self.num_actions = env.num_actions
        self.max_episode_length = env.max_episode_steps
        self.device = torch.device(device)
        self.auto_reset = bool(auto_reset)
        self.episode_length_buf = torch.zeros(self.num_envs, dtype=torch.long, device=self.device)
        self.cfg = {"task": "swap", "adapter": "RslRlSwapAdapter"}
        obs, _ = self.env.reset()
        self._obs = self._obs_tensor(obs)

    def get_observations(self):
        return self._tensor_dict(self._obs)

    def reset(self):
        obs, _ = self.env.reset()
        self.episode_length_buf.zero_()
        self._obs = self._obs_tensor(obs)
        return self.get_observations()

    def step(self, actions):
        import torch

        action = actions.detach().to("cpu").numpy().reshape(self.num_envs, self.num_actions)[0]
        obs, reward, terminated, truncated, info = self.env.step(action)
        self.episode_length_buf += 1

        reward_t = torch.tensor([reward], dtype=torch.float32, device=self.device)
        done_t = torch.tensor([terminated or truncated], dtype=torch.bool, device=self.device)
        timeout_t = torch.tensor([truncated and not terminated], dtype=torch.bool, device=self.device)
        self._obs = self._obs_tensor(obs)
        extras = {
            "time_outs": timeout_t,
            "log": {
                "swap/reward": reward_t.mean(),
                "swap/success": torch.tensor(float(info["success"]), device=self.device),
                "swap/is_lifted": torch.tensor(float(info["is_lifted"]), device=self.device),
            },
            "raw_info": info,
        }

        if bool(done_t.item()) and self.auto_reset:
            reset_obs, _ = self.env.reset()
            self.episode_length_buf.zero_()
            self._obs = self._obs_tensor(reset_obs)

        return self.get_observations(), reward_t, done_t, extras

    def _obs_tensor(self, obs):
        import torch

        return torch.as_tensor(obs, dtype=torch.float32, device=self.device).reshape(1, -1)

    def _tensor_dict(self, obs_tensor):
        try:
            from tensordict import TensorDict
        except ImportError:
            return {"policy": obs_tensor}
        return TensorDict({"policy": obs_tensor}, batch_size=[self.num_envs])
