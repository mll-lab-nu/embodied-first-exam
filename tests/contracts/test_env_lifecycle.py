"""Local Env lifecycle and error boundaries, without an agent or external API."""
import pytest


@pytest.mark.parametrize("stage", ["command", "physics", "task", "checkpoint", "observation"])
def test_fault_boundary_can_only_continue_after_owner_reset(local_env, monkeypatch, stage):
    env = local_env
    targets = {"command": (env._robot, "apply_action"), "physics": (env._world, "advance"),
               "task": (env._task, "update"), "checkpoint": (env._world, "capture_state"),
               "observation": (env._sensors, "sample")}
    obj, name = targets[stage]
    original = getattr(obj, name)
    def fail(*args, **kwargs):
        raise OSError(f"injected {stage} failure")
    # Observation before applying an action is read-only; fail its post-step sample.
    if stage == "observation":
        def fail(*args, **kwargs):
            if env._world.physics_step:
                raise OSError("injected observation failure")
            return original(*args, **kwargs)
    monkeypatch.setattr(obj, name, fail)
    with pytest.raises(OSError):
        env.step({"target": 1.})
    with pytest.raises(RuntimeError, match="faulted"):
        env.step({"target": 1.})
    assert len(env.state_history) == (4 if stage == "observation" else 1)
    monkeypatch.setattr(obj, name, original)
    env.reset(seed=4)
    env.step({"target": 1.})


def test_invalid_seed_preserves_live_episode(local_env):
    before, history = local_env.observe(), local_env.state_history
    for seed in (True, -1, 2**32, 1.5):
        with pytest.raises(ValueError):
            local_env.reset(seed=seed)
        assert local_env.observe() is before and local_env.state_history == history


def test_action_clock_and_read_only_observation(local_env):
    env = local_env
    obs, reward, terminated, truncated, info = env.step({"target": 1.})
    assert info["control_step"] == 1 and info["physics_step"] == 3
    assert info["sim_time_s"] == pytest.approx(.03)
    before = env.state_history
    for _ in range(4):
        assert env.observe() is obs
    assert env.state_history == before
    assert reward == 0 and not terminated and not truncated


def test_invalid_command_has_no_side_effect(local_env):
    before = local_env.observe()
    states = local_env.state_history
    with pytest.raises(ValueError):
        local_env.step({"target": float("nan")})
    assert local_env.observe() is before
    assert local_env.state_history == states


def test_time_limit_and_close(local_env):
    for _ in range(4):
        _, _, terminated, truncated, info = local_env.step({"target": 0.})
    assert not terminated and truncated and info["termination_reason"] == "time_limit"
    with pytest.raises(RuntimeError):
        local_env.step({"target": 0.})
    local_env.close()
    local_env.close()
    with pytest.raises(RuntimeError):
        local_env.reset()


def test_output_failure_requires_reset(local_env):
    def fail(_):
        raise OSError("writer interrupted")
    unsubscribe = local_env.add_transition_sink(fail)
    with pytest.raises(OSError):
        local_env.step({"target": 1.})
    assert local_env.state_history[-1].physics_step == 3
    with pytest.raises(RuntimeError):
        local_env.step({"target": 1.})
    unsubscribe()
    local_env.privileged.rewind_to({"episode_id": local_env.state_history[0].episode_id, "state_id": 0})
    local_env.step({"target": 1.})


def test_mid_action_terminal_records_actual_duration(local_env):
    _, _, terminated, _, info = local_env.step({"target": 100.})
    assert not terminated and info["physics_step"] == 3
    _, _, terminated, truncated, info = local_env.step({"target": 100.})
    assert terminated and not truncated
    assert info["physics_step"] == 4 and info["physics_steps"] == 1
    assert info["action_duration_s"] == pytest.approx(.01)


def test_close_failure_keeps_world_and_prevents_another_active_env(local_env, monkeypatch):
    env = local_env
    world = env._world
    close = world.close

    def fail():
        raise OSError("scene destroy interrupted")

    monkeypatch.setattr(world, "close", fail)
    with pytest.raises(OSError):
        env.close()
    assert env._world is world and not env._closed
    with pytest.raises(RuntimeError, match="faulted"):
        env.step({"target": 0.})
    other = type(env)(env.config)
    try:
        with pytest.raises(RuntimeError, match="active Env"):
            other.reset(seed=4)
    finally:
        other.close()
    monkeypatch.setattr(world, "close", close)
    env.close()
    assert world.closed and env._world is None
