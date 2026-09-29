"""Every task has one reusable rollout; task goals live only in instruction.md."""
import ast
import json
from pathlib import Path

import pytest
import yaml

from harbor_runners.config import expand, load_config, resolve_instances, validate
from harbor_runners.run import main
from harbor_runners.task_generator import prepare, verify_frozen

ROOT = Path(__file__).resolve().parents[2]
PRESETS = ROOT / "configs/harbor/experiments"
tree = ast.parse((ROOT / "topogym/config/variation_records.py").read_text())
RECORDS = next(ast.literal_eval(n.value) for n in tree.body if isinstance(n, ast.Assign)
               and any(getattr(t, "id", None) == "RECORDS" for t in n.targets))
TASKS = sorted({r["task_id"] for r in RECORDS})


@pytest.mark.parametrize("task", TASKS + ["cube_pick_place"])
def test_single_rollout_default_is_complete_and_freezes_task_text(tmp_path, task):
    config = load_config(PRESETS / f"{task}_rollout.yaml", overrides={"model": "openrouter/test"})
    assert len(config["instances"]) == config["attempts"] == config["concurrency"] == 1
    assert config["instances"][0]["simulator"]["seed"] == 0
    run = prepare(config, tmp_path, task)
    assert verify_frozen(run)["expected_trials"] == 1
    resolved = json.loads((run / "experiment.resolved.json").read_text())
    instance = resolved["instances"][0]
    task_dir = run / "harbor_tasks" / instance["name"]
    prompt = (task_dir / "instruction.md").read_text()
    assert instance["instruction"] in prompt
    assert "{{TASK_INSTRUCTION}}" not in prompt and "{{OBSERVATION_ACCESS}}" not in prompt
    assert "Solve the simulator task described" not in prompt
    assert "task_instruction" not in instance.get("observation_profile", {})
    assert json.loads((task_dir / "environment/instance.json").read_text()) == instance


@pytest.mark.parametrize("task", TASKS)
def test_sweep_keeps_goal_and_budget_for_all_integrated_standard_difficulties(tmp_path, task):
    config = load_config(PRESETS / f"{task}_rollout.yaml", overrides={"model": "openrouter/test"})
    instruction = config["instances"][0]["instruction"]
    difficulties = [r["difficulty"] for r in RECORDS if r["task_id"] == task
                    and r["status"] == "integrated" and r["difficulty"] in {"easy", "medium", "hard"}]
    # A task can have additional named variants at the same difficulty.
    difficulties = sorted(set(difficulties))
    expand(config, difficulties=difficulties, seeds=[0, 1])
    config["attempts"] = 2
    run = prepare(config, tmp_path, task)
    assert verify_frozen(run)["expected_trials"] == len(difficulties) * 4
    resolved = json.loads((run / "experiment.resolved.json").read_text())
    for instance in resolved["instances"]:
        task_dir = run / "harbor_tasks" / instance["name"]
        assert instance["instruction"] == instruction
        assert instruction in (task_dir / "instruction.md").read_text()
        assert json.loads((task_dir / "environment/usage.json").read_text()) == config["usage"]


@pytest.mark.parametrize("task,difficulty", [(r["task_id"], r["difficulty"]) for r in RECORDS
    if r["status"] != "integrated" and r["difficulty"] in {"easy", "medium", "hard"}])
def test_unavailable_difficulties_still_fail(task, difficulty):
    config = load_config(PRESETS / f"{task}_rollout.yaml")
    expand(config, difficulties=[difficulty])
    with pytest.raises(ValueError, match="unavailable"):
        resolve_instances(config)


@pytest.mark.parametrize("instruction", [None, "", "  \n", 123, ["goal"]])
def test_missing_or_invalid_task_text_fails_before_key_or_run_directory(tmp_path, monkeypatch, instruction):
    import harbor_runners.run as runner
    value = yaml.safe_load((PRESETS / "cast_coil_rollout.yaml").read_text())
    if instruction is None:
        value["instances"][0].pop("instruction")
    else:
        value["instances"][0]["instruction"] = instruction
    path = tmp_path / "experiment.yaml"
    path.write_text(yaml.safe_dump(value))
    def unexpected(*args, **kwargs):
        pytest.fail("An invalid instruction must fail before credentials or launch")
    monkeypatch.setattr(runner, "input_key", unexpected)
    monkeypatch.setattr(runner, "launch", unexpected)
    assert main(["run", "--root", str(tmp_path), "--config", str(path),
                 "--model-name", "openrouter/test"]) == 2
    assert not (tmp_path / "runs").exists()


@pytest.mark.parametrize("preset", ["cube_pick_place_rollout", "fiber_bundling_rollout"])
def test_limited_override_does_not_keep_privileged_prompt(tmp_path, preset):
    assert main(["prepare", "--root", str(tmp_path), "--run-id", preset,
                 "--experiment", preset, "--model-name", "openrouter/test", "--mode", "limited"]) == 0
    run = tmp_path / "runs/harbor" / preset
    instruction = next((run / "harbor_tasks").glob("*/instruction.md")).read_text()
    assert "Observation mode: limited" in instruction
    assert "authorizes world" not in instruction
    assert "CubePickPlacePolicy" not in instruction


def test_instruction_is_not_an_observation_setting_and_cross_task_sweep_is_rejected():
    config = load_config(PRESETS / "cast_coil_rollout.yaml")
    with pytest.raises(ValueError, match="target task"):
        expand(config, task="fiber_bundling")
    config["instances"][0]["observation_profile"] = {"task_instruction": "conflicting goal"}
    with pytest.raises(ValueError, match="put task text in instruction"):
        validate(config)
