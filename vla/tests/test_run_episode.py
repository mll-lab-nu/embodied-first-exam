"""run_episode error rows with a scripted in-memory Env (no GPU): an environment fault keeps its cause."""
import json

import numpy as np
import pytest

import topogym
from topogym.sensors.observation import SensorFrame
from vla.gym.client import LocalClient
from vla.gym.run_eval import run_episode
from vla.models.dummy import HoldVLA

CONFIG = dict(spec=dict(name="hold", embodiment="panda_robotiq", cameras=["agentview"],
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


class RejectingEnv(FaultingEnv):
    """An Env whose first action is rejected as invalid (physics does not advance); later steps run to the limit."""

    def __init__(self, action_spec):
        super().__init__(action_spec)
        self.actions = []

    def observe(self):
        obs = super().observe()
        obs["robot"]["arm"].update(tcp_position_world_m=np.array([0.5, 0.0, 1.2]),
                                   tcp_orientation_wxyz=np.array([1.0, 0.0, 0.0, 0.0]))
        return obs

    def step(self, action):
        self.actions.append(action)
        if len(self.actions) == 1:
            raise ValueError("Unreachable EE pose: position residual=0.00026 m, orientation=0.0007 rad")
        info = dict(task_outcome="ongoing", termination_reason="time_limit", evaluation_status="available")
        return self.observe(), 0.0, False, len(self.actions) == 3, info


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


class FarVLA(HoldVLA):
    """Targets 10 cm in front of the measured TCP, which FarTargetEnv cannot reach."""

    def infer(self, obs):
        chunk = super().infer(obs)
        chunk.actions[:, 0] += 0.1
        return chunk


class FarTargetEnv(RejectingEnv):
    """Rejects any EE target more than 1 mm from the measured TCP (as an IK miss); stops after 3 accepted steps."""

    def step(self, action):
        self.actions.append(action)
        if np.linalg.norm(np.subtract(action["arm"]["position_world_m"], [0.5, 0.0, 1.2])) > 1e-3:
            raise ValueError("Unreachable EE pose: position residual=0.1 m, orientation=0 rad")
        accepted = sum(np.linalg.norm(np.subtract(a["arm"]["position_world_m"], [0.5, 0.0, 1.2])) <= 1e-3
                       for a in self.actions)
        info = dict(task_outcome="ongoing", termination_reason="time_limit", evaluation_status="available")
        return self.observe(), 0.0, False, accepted == 3, info


def test_an_unreachable_ee_target_is_skipped_by_holding_the_arm(action_spec):
    env = FarTargetEnv(action_spec)
    spec = dict(CONFIG["spec"], action_space="ee_abs", reach_tolerance_m=0.005)
    model = FarVLA(dict(spec=spec))
    row = run_episode(env, LocalClient(model), model.spec, 0, "go", 4, None)
    assert row["outcome"] == "time_limit" and row["skipped_actions"] == 3 and row["control_steps"] == 3
    positions = [action["arm"]["position_world_m"] for action in env.actions]
    np.testing.assert_allclose(positions[0::2], [[0.6, 0.0, 1.2]] * 3, atol=1e-6)  # the model's targets
    np.testing.assert_allclose(positions[1::2], [[0.5, 0.0, 1.2]] * 3, atol=1e-6)  # the holds that ran


def test_a_rejected_joint_action_ends_the_episode_as_invalid(action_spec):
    row = episode(RejectingEnv(action_spec))
    assert row["outcome"] == "invalid_action" and "Unreachable" in row["error"]
