from __future__ import annotations

from pathlib import Path
from typing import Any

from omegaconf import OmegaConf

from .episode_spec import (
    EpisodeKey,
    EpisodeSpec,
    ExecutionProfile,
    ScenePreset,
    TaskLayout,
    TaskVariant,
)


def _plain(value: Any) -> Any:
    if OmegaConf.is_config(value):
        return OmegaConf.to_container(value, resolve=True)
    return value


def _get(config: Any, name: str, default: Any = None) -> Any:
    getter = getattr(config, "get", None)
    if getter is not None:
        return getter(name, default)
    return getattr(config, name, default)


def _path_text(path: Path | str | None) -> str | None:
    if path is None:
        return None
    return str(path)


def build_untangle_episode_spec(
    cfg,
    *,
    seed: int = 0,
    common_config: Path | str | None = None,
    env_config: Path | str | None = None,
    robot_config: Path | str | None = None,
    task_config: Path | str | None = None,
    variant_id: str = "default",
    execution_profile_id: str = "physical_handle_default",
) -> EpisodeSpec:
    """Build the stable generation contract for one Untangle episode."""

    task_cfg = cfg.task
    task_meta = task_cfg.task
    task_id = str(_get(task_meta, "id", "untangle"))
    preset_id = str(_get(cfg.env, "preset_id", "topogym_tabletop_v1"))
    key = EpisodeKey(
        task_id=task_id,
        preset_id=preset_id,
        seed=int(seed),
        variant_id=str(variant_id),
    )
    preset = ScenePreset(
        preset_id=preset_id,
        common_config=common_config,
        env_config=env_config,
        robot_config=robot_config,
        description="TopoGym tabletop baseline shared by physical demos.",
        metadata={
            "common_config": _path_text(common_config),
            "env_config": _path_text(env_config),
            "robot_config": _path_text(robot_config),
            "task_config": _path_text(task_config),
        },
    )
    variant = TaskVariant(
        key=key,
        difficulty=str(_get(task_meta, "difficulty", "default")),
        parameters={
            "holes": _plain(_get(task_cfg, "holes", {})),
            "rope": _plain(_get(task_cfg, "rope", {})),
            "oracle": _plain(_get(task_cfg, "oracle", {})),
        },
        notes=(
            "Deterministic Untangle topology variant. The seed is part of the "
            "episode identity and is reserved for future randomized rope layouts."
        ),
    )
    layout = TaskLayout(
        task_id=task_id,
        layout_id=f"{task_id}_{variant_id}",
        frame=str(_get(task_cfg, "coordinate_frame", "world")),
        objects={
            "board": _plain(_get(task_cfg, "board", {})),
            "holes": _plain(_get(task_cfg, "holes", {})),
            "rope": _plain(_get(task_cfg, "rope", {})),
            "peg": _plain(_get(task_cfg, "peg", {})),
        },
        metadata={
            "oracle": _plain(_get(task_cfg, "oracle", {})),
            "physical_handle": _plain(_get(task_cfg, "physical_handle", {})),
        },
    )
    execution_profile = ExecutionProfile(
        profile_id=str(execution_profile_id),
        safety_profile="pbd_handle_drag",
        parameters={
            "physical_handle": _plain(_get(task_cfg, "physical_handle", {})),
            "mdp": _plain(_get(task_cfg, "mdp", {})),
        },
    )
    return EpisodeSpec(
        key=key,
        preset=preset,
        variant=variant,
        layout=layout,
        execution_profile=execution_profile,
        resolved_config={
            "common_config": _path_text(common_config),
            "env_config": _path_text(env_config),
            "robot_config": _path_text(robot_config),
            "task_config": _path_text(task_config),
        },
    )
