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


def build_swap_episode_spec(
    cfg,
    *,
    seed: int = 0,
    common_config: Path | str | None = None,
    env_config: Path | str | None = None,
    robot_config: Path | str | None = None,
    task_config: Path | str | None = None,
    variant_id: str = "default",
    execution_profile_id: str = "physical_grasp_default",
) -> EpisodeSpec:
    """Build the stable generation contract for one Swap episode.

    The current Swap layout is deterministic, so the seed is part of the
    episode identity and manifest even though it does not yet randomize slots.
    Future randomized Swap variants should only change this generator, not the
    physical demo script.
    """

    task_cfg = cfg.task
    task_meta = task_cfg.task
    task_id = str(_get(task_meta, "id", "swap"))
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
            "oracle": _plain(_get(task_cfg, "oracle", {})),
            "goal": _plain(_get(task_cfg, "goal", {})),
            "slots": _plain(_get(task_cfg, "slots", [])),
            "blocks": _plain(_get(task_cfg, "blocks", {})),
        },
        notes="Deterministic Swap smoke variant; seed reserved for future randomization.",
    )
    layout = TaskLayout(
        task_id=task_id,
        layout_id=f"{task_id}_{variant_id}",
        frame=str(_get(task_cfg, "coordinate_frame", "world")),
        objects={
            "slots": _plain(_get(task_cfg, "slots", [])),
            "blocks": _plain(_get(task_cfg, "blocks", {})),
        },
        metadata={
            "slot_size": _plain(_get(task_cfg, "slot_size", [])),
            "target_assignment": _plain(_get(task_cfg, "goal", {})),
        },
    )
    execution_profile = ExecutionProfile(
        profile_id=str(execution_profile_id),
        safety_profile="rigid_pick_place",
        parameters={
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
