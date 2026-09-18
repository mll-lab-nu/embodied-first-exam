"""Compose and resolve every maintained Hydra primary and task configuration.

Run: python -m tests.check_configs_compose
Standalone previews need not provide recording or prefab sections.
"""
from pathlib import Path
import unittest

from hydra import compose, initialize_config_dir
from omegaconf import OmegaConf

CONFIGS = Path(__file__).resolve().parents[1] / "configs"
REQUIRED = {"common", "env", "robot_control", "task", "run"}


class ConfigChecks(unittest.TestCase):
    def test_all_primary_configs_resolve(self):
        with initialize_config_dir(version_base="1.3", config_dir=str(CONFIGS)):
            for path in sorted(CONFIGS.glob("*.yaml")):
                with self.subTest(config=path.stem):
                    cfg = compose(config_name=path.stem)
                    resolved = OmegaConf.to_container(cfg, resolve=True, throw_on_missing=True)
                    self.assertTrue(REQUIRED <= resolved.keys())

    def test_task_group_resolves_with_both_world_backends(self):
        with initialize_config_dir(version_base="1.3", config_dir=str(CONFIGS)):
            for path in sorted((CONFIGS / "task_configs").glob("*.yaml")):
                for env in ("world_tabletop_v1", "world_tabletop_fem_v1"):
                    with self.subTest(task=path.stem, env=env):
                        cfg = compose(config_name="config", overrides=[
                            f"task_configs@task={path.stem}", f"env_configs@env={env}"])
                        OmegaConf.to_container(cfg, resolve=True, throw_on_missing=True)


if __name__ == "__main__":
    unittest.main()
