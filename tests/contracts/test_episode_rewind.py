"""Tick history is a single path: privileged rewind discards the old future."""
import numpy as np
import pytest
from topogym.simulator import StateRef


def test_every_physics_tick_is_retained(local_env):
    local_env.step({"target": 2.})
    local_env.step({"target": -1.})
    original = local_env.state_history
    assert [s.physics_step for s in original] == list(range(7))
    # Descending order: each target is still in the valid prefix.
    for state in reversed(original):
        _, info = local_env.privileged.rewind_to(state.ref)
        assert info["physics_step"] == state.physics_step
        assert info["sim_time_s"] == state.sim_time_s
        assert info["state_id"] == state.state_id
        assert len(local_env.state_history) == state.physics_step + 1


def test_rewind_repeats_future_but_invalidates_old_references(local_env):
    local_env.step({"target": 2.})
    anchor = local_env.state_history[-1].ref
    expected = local_env.step({"target": -1.})[0]["robot"]["arm"]["joint_position_rad"].copy()
    future = local_env.state_history[-1].ref
    _, info = local_env.privileged.rewind_to(anchor)
    assert info["branch_id"] == 1 and info["branch_parent_state_id"] == anchor.state_id
    actual = local_env.step({"target": -1.})[0]["robot"]["arm"]["joint_position_rad"]
    np.testing.assert_array_equal(actual, expected)
    assert local_env.state_history[-1].state_id > future.state_id
    with pytest.raises(ValueError):
        local_env.privileged.rewind_to(future)


def test_invalid_restore_is_atomic_and_reset_expires_references(local_env):
    local_env.step({"target": 1.})
    before, history = local_env.observe(), local_env.state_history
    for invalid in (-1, True, "1", StateRef("foreign", 0), StateRef(history[0].episode_id, 10000)):
        with pytest.raises(ValueError):
            local_env.privileged.rewind_to(invalid)
        assert local_env.observe() is before and local_env.state_history == history
    with pytest.raises(TypeError):
        local_env.reset(seed=1, state_id=0)
    access = local_env.privileged
    local_env.reset(seed=4)
    assert len(local_env.state_history) == 1
    assert local_env.state_history[0].episode_id != history[0].episode_id
    with pytest.raises(RuntimeError, match="expired"):
        access.rewind_to(history[0].ref)
    with pytest.raises(ValueError, match="different episode"):
        local_env.privileged.rewind_to(history[0].ref)


def test_terminal_restore_stays_terminal_until_rewound_before_end(local_env):
    for _ in range(4):
        local_env.step({"target": 0.})
    terminal = local_env.state_history[-1].ref
    local_env.privileged.rewind_to(terminal)
    with pytest.raises(RuntimeError):
        local_env.step({"target": 1.})
    local_env.privileged.rewind_to(local_env.state_history[0].ref)
    local_env.step({"target": 1.})
    with pytest.raises(ValueError):
        local_env.privileged.rewind_to(terminal)


def test_mid_action_rewind_cannot_extend_physical_time_limit(local_env):
    for _ in range(4):
        local_env.step({"target": 0.})
    point = next(state for state in local_env.state_history if state.physics_step == 10)
    local_env.privileged.rewind_to(point.ref)
    _, _, terminated, truncated, info = local_env.step({"target": 0.})
    assert not terminated and truncated
    assert info["physics_step"] == local_env.config.max_physics_steps == 12
    assert info["physics_steps"] == 2
    assert info["action_duration_s"] == pytest.approx(.02)
    assert info["control_step"] == 5
