"""Config loading (_base_ inheritance, interpolation) and the config files: one model config per checkpoint in its
robot's directory, one eval config per task."""
from pathlib import Path

import pytest
from omegaconf import OmegaConf

import topogym
from vla.config import load_yaml
from vla.protocol import PolicySpec

CONFIGS = Path(__file__).resolve().parents[1] / "configs"
MODEL_CONFIGS = sorted(path for path in (CONFIGS / "models").glob("*/*.yaml") if path.name != "base.yaml")
EVAL_CONFIGS = sorted(path for path in (CONFIGS / "eval").glob("*.yaml") if path.name != "base.yaml")


def test_base_files_merge_first_and_the_child_wins(tmp_path):
    (tmp_path / "sub").mkdir()
    (tmp_path / "a.yaml").write_text("x: {keep: 1, items: [1, 2], name: a}\nz: 0\n")
    (tmp_path / "sub/b.yaml").write_text("_base_: ../a.yaml\nx: {name: b}\ny: ${x.keep}\n")
    (tmp_path / "c.yaml").write_text("_base_: sub/b.yaml\nx: {items: [3]}\nz: 2\n")
    cfg = load_yaml(tmp_path / "c.yaml")
    assert OmegaConf.to_container(cfg, resolve=True) == {"x": {"keep": 1, "items": [3], "name": "b"}, "z": 2, "y": 1}


def test_model_and_eval_configs_exist():
    assert len(MODEL_CONFIGS) >= 7 and len(EVAL_CONFIGS) >= 2


@pytest.mark.parametrize("path", MODEL_CONFIGS, ids=lambda path: path.stem)
def test_model_configs_define_a_policy_spec_for_their_robot(path):
    config = load_yaml(path)
    spec = PolicySpec(**config.spec)
    assert set(config) == {"class_path", "checkpoint", "spec", "model"}  # the port is chosen when serving
    assert config.class_path.startswith("vla.models.") and spec.name == path.stem
    assert spec.embodiment == path.parent.name and 1 <= spec.execute_steps <= spec.chunk_size


@pytest.mark.parametrize("name", ["pi05_base_trossen", "xvla_robotwin2"])
def test_aloha_models_see_the_4_to_3_frames_they_were_trained_on(name):
    assert list(load_yaml(CONFIGS / "models/aloha" / f"{name}.yaml").model.image_aspect) == [4, 3]


@pytest.mark.parametrize("path", EVAL_CONFIGS, ids=lambda path: path.stem)
def test_eval_configs_name_their_task_and_a_policy_address(path):
    cfg = load_yaml(path)
    assert set(cfg) == {"policy", "task", "run", "env"} and cfg.task.id == path.stem
    assert cfg.task.id in topogym.env_list() and cfg.task.seeds and cfg.task.sim_seconds > 0
    assert cfg.policy.address and cfg.policy.local is None
