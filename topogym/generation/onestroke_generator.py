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


def build_onestroke_episode_spec(
    cfg,
    *,
    seed: int = 0,
    common_config: Path | str | None = None,
    env_config: Path | str | None = None,
    robot_config: Path | str | None = None,
    task_config: Path | str | None = None,
    variant_id: str = "default",
    execution_profile_id: str = "physical_wall_default",
) -> EpisodeSpec:
    """Build the stable generation contract for one OneStroke episode."""

    task_cfg = cfg.task
    task_meta = task_cfg.task
    task_id = str(_get(task_meta, "id", "onestroke"))
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
            "grid": _plain(_get(task_cfg, "grid", {})),
            "puzzle": _plain(_get(task_cfg, "puzzle", {})),
            "wall_block": _plain(_get(task_cfg, "wall_block", {})),
            "edge_slots": _plain(_get(task_cfg, "edge_slots", {})),
        },
        notes=(
            "Deterministic OneStroke separator variant; seed reserved for "
            "future randomized puzzles."
        ),
    )
    layout = TaskLayout(
        task_id=task_id,
        layout_id=f"{task_id}_{variant_id}",
        frame=str(_get(task_cfg, "coordinate_frame", "world")),
        objects={
            "grid": _plain(_get(task_cfg, "grid", {})),
            "supply": _plain(_get(task_cfg, "supply", {})),
            "wall_block": _plain(_get(task_cfg, "wall_block", {})),
            "edge_slots": _plain(_get(task_cfg, "edge_slots", {})),
        },
        metadata={
            "oracle": _plain(_get(task_cfg, "oracle", {})),
            "physical": _plain(_get(task_cfg, "physical", {})),
        },
    )
    execution_profile = ExecutionProfile(
        profile_id=str(execution_profile_id),
        safety_profile="rigid_wall_pick_place",
        parameters={
            "oracle": _plain(_get(task_cfg, "oracle", {})),
            "primitive": _plain(_get(task_cfg, "primitive", {})),
            "physical": _plain(_get(task_cfg, "physical", {})),
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
