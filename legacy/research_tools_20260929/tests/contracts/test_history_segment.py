"""history_storage="segment": complete checkpoints only at the episode start and at segment starts."""
from dataclasses import replace

import numpy as np
import pytest


@pytest.fixture
def segment_env(local_env):
    local_env._config = replace(local_env.config, history_storage="segment")
    local_env.reset(seed=4)
    return local_env


def position(env):
    return env.observe()["robot"]["arm"]["joint_position_rad"].copy()


def test_only_the_first_tick_is_complete_and_it_restores_the_birth_state(segment_env):
    birth = segment_env.state_history[0].ref
    start = position(segment_env)
    segment_env.step({"target": 2.})
    segment_env.step({"target": -1.})
    worlds = [segment_env._history.get(s.state_id).world is not None for s in segment_env.state_history]
    assert worlds == [True] + [False] * (len(worlds) - 1)
    _, info = segment_env.privileged.rewind_to(birth)
    assert info["state_id"] == birth.state_id and info["physics_step"] == 0
    np.testing.assert_array_equal(position(segment_env), start)


def test_a_segment_start_checkpoint_is_a_rewind_target_and_other_ticks_are_not(segment_env):
    segment_env.step({"target": 2.})
    anchor = segment_env.state_history[-1].ref
    segment_env._checkpoint_current()                      # what SegmentRunner._begin does
    expected = position(segment_env)
    segment_env.step({"target": -1.})
    middle = segment_env.state_history[-2].ref
    before, history = segment_env.observe(), segment_env.state_history
    with pytest.raises(ValueError, match="segment start"):
        segment_env.privileged.rewind_to(middle)
    assert segment_env.observe() is before and segment_env.state_history == history   # refused before any change
    segment_env.privileged.rewind_to(anchor)
    np.testing.assert_array_equal(position(segment_env), expected)


def test_segment_runner_marks_its_start_as_a_checkpoint(segment_env, tmp_path):
    from topogym.simulator import SegmentRunner
    segment_env.step({"target": 1.})
    runner = SegmentRunner(segment_env, tmp_path / "run")
    assert segment_env._history.get(segment_env.state_history[-1].state_id).world is not None
    runner.close()
