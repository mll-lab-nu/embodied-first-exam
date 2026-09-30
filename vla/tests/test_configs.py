"""Config files: instructions cover every task and match code; model and eval configs are well formed."""
from pathlib import Path

import pytest
from omegaconf import OmegaConf

import topogym
from topogym.config.registry import task_definition, variation_registration
from vla.protocol import PolicySpec

CONFIGS = Path(__file__).resolve().parents[1] / "configs"


def test_instructions_cover_every_task():
    instructions = OmegaConf.load(CONFIGS / "instructions.yaml")
    assert isinstance(instructions.version, int)
    assert set(instructions.tasks) == set(topogym.env_list())


@pytest.mark.parametrize("task_id", ["buzz_wire_3d", "rope_threading", "lock_picking", "fiber_bundling",
                                     "knot_untying"])
def test_instructions_match_task_attributes(task_id):
    task = task_definition(task_id, variation_registration(task_id, "base", 0)["variation_id"])
    assert OmegaConf.load(CONFIGS / "instructions.yaml").tasks[task_id] == task.instruction


@pytest.mark.parametrize("path", sorted((CONFIGS / "models").glob("*.yaml")), ids=lambda p: p.stem)
def test_model_configs_define_a_policy_spec(path):
    config = OmegaConf.load(path)
    spec = PolicySpec(**config.spec)
    assert config.class_path.startswith("vla.models.") and spec.name == path.stem
    assert 1 <= spec.execute_steps <= spec.chunk_size


@pytest.mark.parametrize("path", sorted((CONFIGS / "eval").glob("*.yaml")), ids=lambda p: p.stem)
def test_eval_configs_name_a_task_and_a_policy(path):
    cfg = OmegaConf.load(path)
    assert cfg.task.id in topogym.env_list() and cfg.task.seeds and cfg.task.sim_seconds > 0
    assert cfg.policy.address or (CONFIGS.parent.parent / cfg.policy.local).is_file()
    assert set(cfg) == {"policy", "task", "run", "env"}
