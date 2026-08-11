from __future__ import annotations

from pathlib import Path

from omegaconf import OmegaConf


CONFIG_ROOT = Path(__file__).resolve().parents[2] / "configs"
def save_resolved_config(cfg) -> Path | None:
    """Write the run's config with every interpolation expanded, next to Hydra's own.

    Hydra already saves `.hydra/config.yaml`, but with `OmegaConf.to_yaml`'s default
    `resolve=False` (`hydra/core/utils.py:_save_config`), so a value written as a
    reference stays a reference. Our task configs are full of them -- `rope.fem.E` is
    `${prefabs.rope_fem.E}` -- which turns "what did this run use" into a lookup in
    another part of the same file, and a lookup can be done wrong. It is done wrong
    most easily in exactly the case that matters: a command-line override of the
    referenced value leaves the referring line unchanged.

    So this writes a second copy with the references expanded. Both are kept: Hydra's
    can be reloaded and re-resolved, this one can be read.

    Returns the path written, or None when running outside a Hydra job (a plain
    import, or a demo not yet migrated).
    """

    from hydra.core.hydra_config import HydraConfig

    if not HydraConfig.initialized():
        return None
    target = Path(HydraConfig.get().runtime.output_dir) / ".hydra" / "config_resolved.yaml"
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(OmegaConf.to_yaml(cfg, resolve=True), encoding="utf-8")
    return target


# Hydra config group -> the directory its options live in. The `@` part is the
# package the group is mounted at, which is also the name the rest of the code
# knows the section by (cfg.env, cfg.task, ...).
_CONFIG_GROUP_DIRS = {
    "common_configs@common": "common_configs",
    "env_configs@env": "env_configs",
    "robot_control_configs@robot_control": "robot_control_configs",
    "task_configs@task": "task_configs",
    "prefab_configs@prefabs": "prefab_configs",
}


def hydra_config_sources() -> dict[str, Path]:
    """Which file each config group resolved to, keyed by section name.

    Episode specs record the config files they came from, as provenance. Before
    Hydra the demos had those paths in hand because they were argparse values; now
    the group choice is what is known, so rebuild the paths from it.

    Returns an empty dict outside a Hydra job, which is what the not-yet-migrated
    demos and `topogym/data/replay.py` will see.
    """

    from hydra.core.hydra_config import HydraConfig

    if not HydraConfig.initialized():
        return {}
    choices = HydraConfig.get().runtime.choices
    sources: dict[str, Path] = {}
    for group, directory in _CONFIG_GROUP_DIRS.items():
        option = choices.get(group)
        if option is None:
            continue
        sources[group.split("@")[-1]] = CONFIG_ROOT / directory / f"{option}.yaml"
    return sources
