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


def build_cable_routing_episode_spec(
    cfg,
    *,
    seed: int = 0,
    common_config: Path | str | None = None,
    env_config: Path | str | None = None,
    robot_config: Path | str | None = None,
    task_config: Path | str | None = None,
    variant_id: str = "default",
    route_mode: str = "initial",
    execution_profile_id: str = "physical_handle_default",
) -> EpisodeSpec:
    """Build the stable generation contract for one Cable Routing episode."""

    task_cfg = cfg.task
    task_meta = task_cfg.task
    task_id = str(_get(task_meta, "id", "cable_routing"))
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
            "fixtures": _plain(_get(task_cfg, "fixtures", {})),
            "routing": _plain(_get(task_cfg, "routing", {})),
            "target_signature": _plain(_get(task_cfg, "target_signature", [])),
            "route_mode": str(route_mode),
        },
        notes=(
            "Deterministic Cable Routing variant; seed is reserved for future "
            "randomized fixture layouts or target signatures."
        ),
    )
    layout = TaskLayout(
        task_id=task_id,
        layout_id=f"{task_id}_{variant_id}",
        frame=str(_get(task_cfg, "coordinate_frame", "world")),
        objects={
            "board": _plain(_get(task_cfg, "board", {})),
            "fixtures": _plain(_get(task_cfg, "fixtures", {})),
            "routes": _plain(_get(task_cfg, "routes", {})),
            "rope": _plain(_get(task_cfg, "rope", {})),
        },
        metadata={
            "routing": _plain(_get(task_cfg, "routing", {})),
            "target_signature": _plain(_get(task_cfg, "target_signature", [])),
            "physical_handle": _plain(_get(task_cfg, "physical_handle", {})),
        },
    )
    execution_profile = ExecutionProfile(
        profile_id=str(execution_profile_id),
        safety_profile="pbd_cable_endpoint_drag",
        parameters={
            "physical_handle": _plain(_get(task_cfg, "physical_handle", {})),
            "route_mode": str(route_mode),
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
