"""run_episode error rows with a scripted in-memory Env (no GPU): an environment fault keeps its cause."""
import json

import numpy as np
import pytest

import topogym
from topogym.sensors.observation import SensorFrame
from vla.gym.client import LocalClient
from vla.gym.run_eval import run_episode
from vla.models.dummy import HoldVLA

CONFIG = dict(spec=dict(name="hold", embodiment="panda_robotiq", cameras=["agentview"], state_keys=["joint"],
                        action_space="joint_abs", control_hz=40, chunk_size=4, execute_steps=4))


@pytest.fixture(scope="module")
def action_spec():
    with topogym.make("buzz_wire_3d") as env:
        return env.action_spec


class FaultingEnv:
    """Owner and operator views of one Env whose first step faults, like topogym's Env + Interaction."""

    def __init__(self, action_spec):
        self.action_spec, self._fault_detail, self.sinks, self.episode_metadata = action_spec, None, [], {}

    def reset(self, seed):
        pass

    def interaction(self):
        return self

    def observe(self):
        limits = np.asarray(self.action_spec["groups"]["arm"]["joint_limits_rad"])
        robot = {"arm": {"joint_position_rad": limits.mean(axis=1), "finger_position_rad": np.zeros(2)}}
        return {"rgb": {"agentview": np.zeros((16, 16, 3), np.uint8)}, "robot": robot,
                "state": {"episode_id": "e", "sim_time_s": 0.0}}

    def sensor_frame(self):
        return SensorFrame("e", 0, 0, 0, 0.0, {"agentview": np.zeros((16, 16, 3), np.uint8)}, {})

    def add_frame_sink(self, sink):
        self.sinks.append(sink)
        return self.sinks.clear

    def step(self, action):
        try:
            for sink in self.sinks:
                sink(self.sensor_frame())  # repeats the initial state id, which the recording rejects
            self._fault_detail = dict(stage="physics", error="FloatingPointError: nan in qpos")
        except ValueError as error:
            self._fault_detail = dict(stage="output", error=f"ValueError: {error}")
        raise RuntimeError("Environment execution failed; consult owner evidence")


def episode(env, video_dir=None):
    model = HoldVLA(CONFIG)
    return run_episode(env, LocalClient(model), model.spec, 0, "go", 4, video_dir)


def test_env_error_row_keeps_the_fault_cause(action_spec):
    row = episode(FaultingEnv(action_spec))
    assert row["outcome"] == "env_error" and row["control_steps"] == 0 and row["tracking_error_unit"] == "rad"
    assert "physics" in row["error"] and "FloatingPointError: nan in qpos" in row["error"]


def test_recording_fault_still_returns_the_row(action_spec, tmp_path):
    row = episode(FaultingEnv(action_spec), tmp_path / "seed_0")
    assert row["outcome"] == "env_error" and "ValueError" in row["error"]
    manifest = json.loads((tmp_path / "seed_0" / "recording_manifest.json").read_text())
    assert manifest["recording_status"] == "incomplete"
