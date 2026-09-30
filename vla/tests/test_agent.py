"""VLAAgent chunk queueing, reset and chunk validation with a real Panda action spec."""
import numpy as np
import pytest

import topogym
from vla.gym.adapter import Adapter
from vla.gym.agent import VLAAgent
from vla.gym.client import LocalClient, PolicyError
from vla.models.dummy import HoldVLA
from vla.protocol import ActionChunk


@pytest.fixture(scope="module")
def action_spec():
    with topogym.make("buzz_wire_3d") as env:
        return env.action_spec


def config(chunk_size, execute_steps):
    return dict(spec=dict(name="hold", embodiment="panda_robotiq", cameras=["agentview"], state_keys=["joint"],
                          action_space="joint_abs", control_hz=15, chunk_size=chunk_size,
                          execute_steps=execute_steps))


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


@pytest.mark.parametrize("execute_steps", [0, 16])
def test_execute_steps_must_fit_the_chunk(action_spec, execute_steps):
    with pytest.raises(ValueError):
        agent_for(Recorder(config(15, 8)), action_spec, execute_steps)
