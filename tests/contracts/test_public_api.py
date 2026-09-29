"""Owner construction and operator interaction are distinct local interfaces."""
import subprocess
import sys
import pytest
import topogym


def test_catalog_is_lazy_and_has_all_tasks():
    code = "import topogym,sys; assert len(topogym.env_list())==13; assert 'genesis' not in sys.modules; assert 'torch' not in sys.modules"
    subprocess.run([sys.executable, "-c", code], check=True)
    assert topogym.env_list() == sorted(topogym.env_list())
    assert len(topogym.env_list(details=True)) == 13


@pytest.mark.parametrize("task", topogym.env_list())
@pytest.mark.parametrize("mode", ["EE", "JOINT"])
def test_make_specs_without_building(task, mode):
    with topogym.make(task, observation_mode=mode) as env:
        assert env._world is None
        assert env.observation_spec["mode"] == mode
        cameras = env.observation_spec["rgb"]
        assert len(cameras) == (4 if env.action_spec["robot_id"] == "aloha" else 3)
        assert all(c["shape"] == [480, 848, 3] for c in cameras.values())
        assert not hasattr(env, "last_seed")


def test_unknown_task_rejected_before_engine_build():
    with pytest.raises(ValueError):
        topogym.make("not_a_task")


@pytest.mark.parametrize("privileged", [False, True])
def test_operator_never_has_reset_or_seed_mutation(local_env, privileged):
    operator = local_env.interaction(privileged=privileged)
    for name in ("reset", "make", "close", "seed", "config", "last_seed", "privileged"):
        assert not hasattr(operator, name)
    old = local_env.state_history[0].ref
    operator.step({"target": 1.})
    if privileged:
        operator.rewind_to(old)
        with pytest.raises(TypeError):
            operator.rewind_to(old, seed=5)
    else:
        with pytest.raises(PermissionError):
            operator.rewind_to(old)
    # Reset is exclusively an owner operation; it may select a different seed.
    _, info = local_env.reset(seed=9)
    assert info["seed"] == 9
    with pytest.raises(RuntimeError, match="expired"):
        operator.step({"target": 0.})
    with pytest.raises(ValueError, match="different episode"):
        local_env.interaction(privileged=True).rewind_to(old)
