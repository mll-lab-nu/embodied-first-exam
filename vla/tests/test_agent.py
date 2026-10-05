"""VLAAgent chunk queueing, reset and chunk validation with a real Panda action spec."""
import numpy as np
import pytest

import topogym
from vla.gym.adapter import Adapter
from vla.gym.agent import MAX_HOLD_STEPS, VLAAgent
from vla.gym.client import LocalClient, PolicyError
from vla.models.dummy import HoldVLA
from vla.protocol import ActionChunk


@pytest.fixture(scope="module")
def action_spec():
    with topogym.make("buzz_wire_3d") as env:
        return env.action_spec


def config(chunk_size, execute_steps, action_space="joint_abs", reach_tolerance_m=0.0):
    return dict(spec=dict(name="hold", embodiment="panda_robotiq", cameras=["agentview"],
                          action_space=action_space, control_hz=15, chunk_size=chunk_size,
                          execute_steps=execute_steps, reach_tolerance_m=reach_tolerance_m))


class Recorder(HoldVLA):
    """HoldVLA that records resets and observation steps, optionally returning a fixed chunk."""

    def __init__(self, config, actions=None):
        super().__init__(config)
        self.actions, self.seeds, self.steps, self.episode_ids = actions, [], [], []

    def reset(self, seed):
        self.seeds.append(seed)

    def infer(self, obs):
        self.steps.append(obs.step)
        self.episode_ids.append(obs.episode_id)
        return super().infer(obs) if self.actions is None else ActionChunk(self.actions)


def agent_for(model, action_spec, execute_steps):
    return VLAAgent(LocalClient(model), Adapter(action_spec, model.spec), execute_steps)


def inputs(action_spec):
    limits = np.asarray(action_spec["groups"]["arm"]["joint_limits_rad"])
    robot = {"arm": {"joint_position_rad": limits.mean(axis=1), "finger_position_rad": np.array([0.4, 0.4])}}
    return {"agentview": np.zeros((480, 848, 3), np.uint8)}, robot


def test_h15_k8_infers_three_times_in_twenty_acts(action_spec):
    model = Recorder(config(15, 8))
    agent = agent_for(model, action_spec, 8)
    agent.reset(0, "go", "e")
    rgb, robot = inputs(action_spec)
    actions = [agent.act(rgb, robot) for _ in range(20)]
    assert agent.inference_calls == 3 and model.steps == [0, 8, 16]
    np.testing.assert_allclose(actions[-1]["arm"]["joint_position_rad"], robot["arm"]["joint_position_rad"],
                               atol=1e-6)


def test_reset_clears_the_queue_seeds_the_policy_and_keeps_the_env_episode_id(action_spec):
    model = Recorder(config(15, 8))
    agent = agent_for(model, action_spec, 8)
    rgb, robot = inputs(action_spec)
    agent.reset(4, "go", "episode-a")
    agent.act(rgb, robot)
    agent.reset(5, "go", "episode-b")
    agent.act(rgb, robot)
    assert model.seeds == [4, 5] and model.steps == [0, 0] and agent.inference_calls == 1
    assert model.episode_ids == ["episode-a", "episode-b"]


@pytest.mark.parametrize("actions", [np.zeros((14, 8), np.float32), np.zeros((15, 7), np.float32),
                                     np.full((15, 8), np.nan, np.float32)])
def test_malformed_chunks_raise_policy_error(action_spec, actions):
    agent = agent_for(Recorder(config(15, 8), actions), action_spec, 8)
    agent.reset(0, "go", "e")
    with pytest.raises(PolicyError):
        agent.act(*inputs(action_spec))


def test_clipped_rows_are_counted_once_per_row_and_reset_per_episode(action_spec):
    limits = np.asarray(action_spec["groups"]["arm"]["joint_limits_rad"])
    inside = np.r_[limits.mean(axis=1), 0.5]
    actions = np.stack([np.r_[limits[:, 1] + 1.0, 0.5], inside, np.r_[limits.mean(axis=1), 1.5], inside])
    agent = agent_for(Recorder(config(4, 4), actions.astype(np.float32)), action_spec, 4)
    agent.reset(0, "go", "e")
    for _ in range(4):
        agent.act(*inputs(action_spec))
    assert agent.clipped == 2 and type(agent.clipped) is int  # written to results.jsonl
    agent.reset(1, "go", "e")
    assert agent.clipped == 0


@pytest.mark.parametrize("execute_steps", [0, 16])
def test_execute_steps_must_fit_the_chunk(action_spec, execute_steps):
    with pytest.raises(ValueError):
        agent_for(Recorder(config(15, 8)), action_spec, execute_steps)


@pytest.fixture(scope="module")
def aloha_spec():
    with topogym.make("cast_coil") as env:
        return env.action_spec


def aloha_config():
    return dict(spec=dict(name="hold", embodiment="aloha", cameras=["cam_high"],
                          action_space="ee_abs", control_hz=16.667, chunk_size=2, execute_steps=2,
                          reach_tolerance_m=0.005))


def ee_row(left, right):
    """Both arms' targets with identity orientation; the left gripper open, the right one closed."""
    return np.r_[left, 1, 0, 0, 0, 1, 0, 1.0, right, 1, 0, 0, 0, 1, 0, 0.0].astype(np.float32)


ROWS = np.stack([ee_row([0.5, 0.0, 1.2], [-0.5, 0.0, 1.2]), ee_row([0.6, 0.0, 1.2], [-0.6, 0.0, 1.2])])
RGB = {"cam_high": np.zeros((480, 848, 3), np.uint8)}


def aloha_robot(left, right):
    return {arm: {"tcp_position_world_m": np.array(position, float), "tcp_orientation_wxyz": np.array([1.0, 0, 0, 0]),
                  "finger_position_m": np.array([0.02, 0.02])} for arm, position in (("left", left), ("right", right))}


def targets(action):
    return [action["left"]["position_world_m"], action["right"]["position_world_m"]]


def test_a_target_is_held_until_both_arms_reach_it_and_each_target_gets_its_own_hold_budget(aloha_spec):
    agent = agent_for(Recorder(aloha_config(), ROWS), aloha_spec, 2)
    agent.reset(0, "go", "e")
    left_only = aloha_robot([0.5, 0.0, 1.2], [0.0, 0.0, 1.0])  # the right arm is far from both targets
    executed = [targets(agent.act(RGB, left_only)) for _ in range(2 * (MAX_HOLD_STEPS + 1) + 1)]
    expected = [ROWS[0]] * (MAX_HOLD_STEPS + 1) + [ROWS[1]] * (MAX_HOLD_STEPS + 1) + [ROWS[0]]
    np.testing.assert_allclose(executed, [[row[:3], row[10:13]] for row in expected], atol=1e-6)
    assert agent.inference_calls == 2
    agent.reset(0, "go", "e")
    agent.act(RGB, left_only)
    reached = aloha_robot([0.502, 0.0, 1.2], [-0.5, 0.003, 1.2])
    np.testing.assert_allclose(targets(agent.act(RGB, reached)), [ROWS[1][:3], ROWS[1][10:13]], atol=1e-6)


def test_a_rejected_target_is_skipped_for_the_unreachable_arm_only(aloha_spec):
    agent = agent_for(Recorder(aloha_config(), ROWS), aloha_spec, 2)
    agent.reset(0, "go", "e")
    robot = aloha_robot([0.45, 0.0, 1.2], [0.0, 0.0, 1.0])
    tried = []

    def step(action):  # the right target is unreachable; any action that holds the right arm is accepted
        tried.append(targets(action))
        if not np.allclose(action["right"]["position_world_m"], [0.0, 0.0, 1.0]):
            raise ValueError("Unreachable EE pose")
        return "stepped"

    agent.act(RGB, robot)
    action, result = agent.skip(robot, step)
    assert result == "stepped" and agent.skipped == 1 and len(tried) == 2  # hold left (rejected), hold right
    np.testing.assert_allclose(targets(action), [[0.5, 0.0, 1.2], [0.0, 0.0, 1.0]], atol=1e-6)
    assert action["left"]["gripper_position_m"] == 0.037 and action["right"]["gripper_position_m"] == 0.002
    moved = aloha_robot([0.5, 0.0, 1.2], [0.0, 0.0, 1.0])  # the left arm reached its target; the right one held
    np.testing.assert_allclose(targets(agent.act(RGB, moved)), [ROWS[1][:3], ROWS[1][10:13]], atol=1e-6)

