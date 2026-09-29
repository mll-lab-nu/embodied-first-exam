"""Initialization is an owner lifecycle operation before checkpoint/RGB birth."""
from dataclasses import replace
import pytest


def declare_frozen(env, monkeypatch):
    from topogym.tasks.base import TaskSpec, InitialStateSpec
    monkeypatch.setattr(env._task_class, "declare", lambda *a: TaskSpec((),
        initial_state=InitialStateSpec("fixture.json", "0"*64)))


def test_initial_state_precedes_first_history_and_observation(local_env, monkeypatch):
    import topogym.world.initial_state as initial
    env = local_env
    old = env.interaction(privileged=True)
    declare_frozen(env, monkeypatch)
    monkeypatch.setattr(initial, "scene_identity", lambda *args: {})
    calls = []
    def restore(world, robot, declaration, *, identity):
        assert env.state_history == ()
        world.position, world.physics_step = 4., 97
        calls.append(1)
        return {"initialization_advance_calls": 0, "source_physics_step": 97}
    monkeypatch.setattr(initial, "restore_declared_initial_state", restore)
    obs, info = env.reset(seed=4)
    assert calls == [1] and info["physics_step"] == 0
    assert env._world.position == 4. and len(env.state_history) == 1
    assert env._history.get(0).world[1] == 4.
    assert obs["robot"]["arm"]["joint_position_rad"][0] == 4.
    assert env.episode_metadata["initial_state"]["source_physics_step"] == 97
    assert not hasattr(env.interaction(), "restore_initial_state")
    assert not hasattr(env.interaction(privileged=True), "restore_initial_state")
    with pytest.raises(RuntimeError):
        old.observe()


def test_import_failure_publishes_no_episode(local_env, monkeypatch):
    import topogym.world.initial_state as initial
    env = local_env
    old = env.interaction()
    declare_frozen(env, monkeypatch)
    monkeypatch.setattr(initial, "scene_identity", lambda *args: {})
    def fail(*args, **kwargs):
        raise ValueError("corrupt initial archive")
    monkeypatch.setattr(initial, "restore_declared_initial_state", fail)
    with pytest.raises(ValueError, match="corrupt"):
        env.reset(seed=4)
    assert env.state_history == () and env._world is None
    with pytest.raises(RuntimeError):
        old.observe()


def test_reset_warmup_conflict_is_explicit(local_env, monkeypatch):
    env = local_env
    declare_frozen(env, monkeypatch)
    monkeypatch.setattr(env, "_config", replace(env.config, reset_physics_steps=1))
    with pytest.raises(ValueError, match="reset_physics_steps == 0"):
        env.reset(seed=4)
    assert env.state_history == () and env._world is None
