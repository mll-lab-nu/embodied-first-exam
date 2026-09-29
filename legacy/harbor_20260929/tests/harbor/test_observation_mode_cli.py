"""CLI access overrides must reach every frozen task without weakening budgets."""
import json

import pytest

from harbor_runners.config import load_config
from harbor_runners.run import build_parser, config_from_args, main
from harbor_runners.task_generator import verify_frozen


@pytest.mark.parametrize("command", ["prepare", "run"])
def test_omitted_mode_preserves_preset_access(command):
    args = build_parser().parse_args([command, "--model", "openrouter/test"])
    config = config_from_args(args)
    expected = load_config(overrides={"model": "openrouter/test"})
    assert config["instances"] == expected["instances"]


@pytest.mark.parametrize("mode,fields", [
    ("limited", []), ("unlimited", ["world", "task"]),
])
def test_cast_coil_rollout_freezes_access_and_10m_3m_per_trial(tmp_path, mode, fields):
    argv = ["prepare", "--root", str(tmp_path), "--run-id", "coil",
            "--experiment", "cast_coil_rollout", "--model", "openrouter/test",
            "--mode", mode, "--difficulty", "easy", "medium", "hard",
            "--seeds", "0", "1", "--attempts", "2", "--concurrency", "1",
            "--input-token-limit", "10000000", "--output-token-limit", "3000000"]
    if fields:
        argv += ["--state-fields", *fields]
    assert main(argv) == 0
    run = tmp_path / "runs/harbor/coil"
    manifest = verify_frozen(run)
    assert manifest["task_count"] == 6 and manifest["expected_trials"] == 12
    config = json.loads((run / "experiment.resolved.json").read_text())
    assert {i["simulator"]["variation_id"] for i in config["instances"]} == {
        "cast_coil_easy", "cast_coil_medium", "cast_coil_hard"}
    for instance in config["instances"]:
        environment = run / "harbor_tasks" / instance["name"] / "environment"
        frozen = json.loads((environment / "instance.json").read_text())
        assert frozen == instance
        assert frozen["mode"] == mode and frozen["state_fields"] == fields
        assert frozen["simulator"]["enable_privileged"] is (mode == "unlimited")
        usage = json.loads((environment / "usage.json").read_text())
        assert usage["mode"] == "observed" and usage["scope"] == "trial"
        assert usage["limits"] == {"input_tokens": 10_000_000, "output_tokens": 3_000_000}


def test_limited_clears_inherited_privileges_after_expansion():
    args = build_parser().parse_args(["run", "--model", "openrouter/test",
        "--experiment", "fiber_bundling_rollout", "--mode", "limited", "--seeds", "0", "1"])
    config = config_from_args(args)
    assert len(config["instances"]) == 2
    for instance in config["instances"]:
        assert instance["mode"] == "limited" and instance["state_fields"] == []
        assert instance["simulator"]["enable_privileged"] is False


@pytest.mark.parametrize("extra,fields", [
    ([], ["world"]), (["--state-fields"], []), (["--state-fields", "task"], ["task"]),
])
def test_unlimited_preserves_or_explicitly_replaces_whitelist(extra, fields):
    args = build_parser().parse_args(["prepare", "--model", "openrouter/test",
        "--experiment", "fiber_bundling_rollout", "--mode", "unlimited", *extra])
    config = config_from_args(args)
    assert config["instances"][0]["state_fields"] == fields


def test_unlimited_does_not_implicitly_publish_all_state():
    args = build_parser().parse_args(["prepare", "--model", "openrouter/test",
        "--experiment", "cast_coil_rollout", "--mode", "unlimited"])
    assert all(i["state_fields"] == [] for i in config_from_args(args)["instances"])


@pytest.mark.parametrize("extra", [
    ["--mode", "limited", "--state-fields", "world"],
    ["--state-fields", "world"],
    ["--mode", "unlimited", "--state-fields", "world", "world"],
])
def test_invalid_privileges_fail_before_credentials_or_launch(tmp_path, monkeypatch, extra):
    import harbor_runners.run as runner

    def unexpected(*args, **kwargs):
        pytest.fail("Invalid access must be rejected before credentials, prepare or launch")

    monkeypatch.setattr(runner, "input_key", unexpected)
    monkeypatch.setattr(runner, "launch", unexpected)
    assert main(["run", "--root", str(tmp_path), "--experiment", "cast_coil_rollout",
                 "--model", "openrouter/test", *extra]) == 2
    assert not (tmp_path / "runs").exists()
