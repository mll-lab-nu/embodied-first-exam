"""Permission, episode identity and detached detail reads."""
from dataclasses import replace
import pytest


def test_disabled_privilege_is_not_grantable(local_env):
    local_env._config = replace(local_env.config, enable_privileged=False)
    with pytest.raises(PermissionError):
        local_env.privileged
    with pytest.raises(PermissionError):
        local_env.interaction(privileged=True)


def test_detail_whitelist_and_copy_isolation(local_env):
    operator = local_env.interaction(privileged=True)
    for name in ("seed", "scene", "config", "reset", "__dict__"):
        with pytest.raises(ValueError):
            operator.get(name)
    before = operator.observe()
    for name in ("world", "robot", "task", "state_info", "diagnostics", "history"):
        result = operator.get(name)
        if name != "history":
            with pytest.raises(TypeError):
                result["injected"] = 1
    assert operator.observe() is before
    assert "world" not in before


def test_owner_reset_same_seed_rebuilds_and_new_seed_changes_identity(local_env):
    first = local_env.episode_metadata
    local_env.step({"target": 10.})
    _, repeated = local_env.reset(seed=first["seed"])
    assert repeated["episode_id"] != first["episode_id"]
    assert local_env.episode_metadata["instance_id"] == first["instance_id"]
    _, changed = local_env.reset(seed=first["seed"] + 1)
    assert changed["seed"] != first["seed"]
    assert len(local_env.state_history) == 1
