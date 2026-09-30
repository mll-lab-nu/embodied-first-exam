"""快照与输出消费者不能修改物理源数据；只编写，未运行。"""
from dataclasses import FrozenInstanceError
from types import SimpleNamespace

import numpy as np
import pytest

from topogym.simulator.history import Transition
from topogym.sensors.observation import SensorSuite
from topogym.utils.snapshots import freeze, thaw


def test_nested_snapshot_detaches_from_reused_simulator_buffers():
    buffer = np.arange(12, dtype=np.float64).reshape(4, 3)
    source = {"robot": {"positions": buffer}, "labels": ["before"]}
    saved = freeze(source)
    buffer[:] = -1
    source["labels"].append("after")
    np.testing.assert_array_equal(saved["robot"]["positions"], np.arange(12).reshape(4, 3))
    assert saved["labels"] == ("before",)
    assert not np.shares_memory(buffer, saved["robot"]["positions"])


def test_consumer_cannot_mutate_mapping_or_reenable_array_writes():
    snapshot = freeze({"rgb": np.zeros((2, 2, 3), dtype=np.uint8)})
    with pytest.raises(TypeError):
        snapshot["extra"] = 1
    with pytest.raises(ValueError):
        snapshot["rgb"][0, 0, 0] = 99
    with pytest.raises(ValueError):
        snapshot["rgb"].setflags(write=True)


def test_noncontiguous_array_snapshot_keeps_values_and_dtype():
    source = np.arange(24, dtype=np.float32).reshape(4, 6)[:, ::2]
    snapshot = freeze(source)
    assert snapshot.shape == source.shape
    assert snapshot.dtype == np.float32
    np.testing.assert_array_equal(snapshot, source)
    assert not np.shares_memory(snapshot, source)


def test_thaw_produces_independent_owner_copy():
    snapshot = freeze({"state": np.array([1.0, 2.0]), "nested": [{"value": 3}]})
    editable = thaw(snapshot)
    editable["state"][0] = 9.0
    editable["nested"][0]["value"] = 7
    np.testing.assert_array_equal(snapshot["state"], [1.0, 2.0])
    assert snapshot["nested"][0]["value"] == 3


def test_object_array_is_rejected_instead_of_leaking_mutable_references():
    value = np.empty(1, dtype=object)
    value[0] = {"mutable": []}
    with pytest.raises(TypeError, match="Object arrays"):
        freeze(value)


def test_transition_owns_frozen_command_and_observation_records():
    command = np.array([0.5])
    measured = np.array([0.1])
    record = Transition(
        episode_id="episode-A", branch_id=0, previous_state_id=0, state_id=1,
        control_step=1, physics_step=1, sim_time_s=0.01, physics_steps=1,
        action_duration_s=0.01, observation=freeze({"q": np.zeros(1)}),
        action=freeze({"target": command}), next_observation=freeze({"q": measured}),
        reward=0.0, terminated=False, truncated=False, info=freeze({}),
    )
    command[:] = 9.0
    measured[:] = 8.0
    np.testing.assert_array_equal(record.action["target"], [0.5])
    np.testing.assert_array_equal(record.next_observation["q"], [0.1])
    with pytest.raises(FrozenInstanceError):
        record.state_id = 2
    with pytest.raises(ValueError):
        record.action["target"].setflags(write=True)


def test_same_tick_restore_changes_cached_state_without_mutating_previous_frame():
    """缓存按episode/branch/state识别；物理时间相同也不能返回旧图。"""
    class Camera:
        def __init__(self):
            self.buffer = np.zeros((2, 2, 3), dtype=np.uint8)
            self.cached = None
            self.calls = 0
            self.res = (2, 2)
            self.fov = 60.0
            self.transform = np.eye(4)

        def render(self, *, rgb):
            assert rgb is True
            self.calls += 1
            if self.cached is None:
                self.cached = self.buffer.copy()
            return self.cached

        def invalidate_frame(self):
            self.cached = None

    camera = Camera()
    position = np.array([1., 2., 3.])
    world = SimpleNamespace(physics_step=7, sim_time_s=0.07, cameras={"front": camera},
                            read_state=lambda: {"bodies": {"object": {"position_m": position}},
                                                "physics_step": 7, "sim_time_s": .07})
    robot = SimpleNamespace(observe=lambda: {"arm": {"joint_position_rad": np.array([0.1])}})
    task = SimpleNamespace(observe=lambda: {"value": 1.0})
    sensors = SensorSuite(world, robot, enable_rgb=True)
    observation, first = sensors.sample(episode_id="A", branch_id=0, state_id=7, task=task)
    cached_observation, cached_frame = sensors.sample(episode_id="A", branch_id=0, state_id=7, task=task)
    assert cached_observation is observation
    assert cached_frame is first
    assert camera.calls == 1
    np.testing.assert_allclose(first.camera_metadata["front"]["K_px"],
        [[3 ** .5, 0., 1.], [0., 3 ** .5, 1.], [0., 0., 1.]])
    np.testing.assert_array_equal(first.camera_metadata["front"]["T_world_from_camera_cv"],
                                 np.diag([1., -1., -1., 1.]))
    camera.buffer[:] = 99
    position[:] = 9.
    restored_observation, restored = sensors.sample(episode_id="A", branch_id=1, state_id=50, task=task)
    assert camera.calls == 2
    assert restored.physics_step == first.physics_step == 7
    assert restored.sim_time_s == first.sim_time_s == 0.07
    assert restored.branch_id != first.branch_id
    np.testing.assert_array_equal(first.rgb["front"], np.zeros((2, 2, 3), dtype=np.uint8))
    np.testing.assert_array_equal(restored.rgb["front"], np.full((2, 2, 3), 99, dtype=np.uint8))
    np.testing.assert_array_equal(restored_observation["rgb"]["front"], restored.rgb["front"])
    assert "world" not in observation
    assert "world" not in restored_observation
