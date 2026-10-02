"""The single simulator input configuration; task-specific values stay explicit."""
from __future__ import annotations

from dataclasses import dataclass, field
import math
from pathlib import Path
from typing import Mapping, Any

from topogym.utils.snapshots import freeze
from topogym.utils.grasp import GraspAssistConfig, GraspTarget, SoftGraspTarget


# "segment" (default): a complete checkpoint at the episode start and at each SegmentRunner segment start, a light
# record (tick identity, robot targets, task state) at every other tick; rewind reaches only those checkpoints.
# "memory" / "disk": a complete checkpoint at every physics tick (in memory / pickled to a private temporary
# directory); rewind reaches any tick. Callers that rewind to arbitrary ticks select "memory".
DEFAULT_HISTORY_STORAGE = "segment"
HISTORY_STORAGES = {"segment", "memory", "disk"}


# RigidOptions fields an instance may override, with their types. use_contact_island=False: one global constraint solve
# instead of per-island solves; on the CPU backend 1.3x faster (2026-10-02 study).
RIGID_OPTION_OVERRIDES = {"use_contact_island": bool}


@dataclass(frozen=True)
class SimulatorConfig:
    task_id: str = "cast_coil"
    robot_id: str = "auto"
    variation_id: str = "base"
    task_parameters: Mapping[str, Any] = field(default_factory=dict)
    compute_backend: str = "cuda"
    precision: str = "64"
    physics_dt_s: float = .0025
    solver_substeps: int = 4
    terminal_contract_version: int = 1
    control_decimation: int = 10
    max_physics_steps: int | None = 10000
    history_storage: str = field(default_factory=lambda: DEFAULT_HISTORY_STORAGE)
    reset_physics_steps: int = 0
    # Qualified overrides of the task's Genesis RigidOptions (RIGID_OPTION_OVERRIDES); merged in Env.reset.
    rigid_options: Mapping[str, Any] = field(default_factory=dict)
    enable_rgb: bool = True
    enable_depth: bool = False
    observation_mode: str = "JOINT"
    control_mode: str = "JOINT_ABS"
    enable_privileged: bool = False
    seed: int | None = None
    render_backend: str = "nyx"
    asset_root: Path | None = None
    work_dir: Path | None = None
    grasp_assist: GraspAssistConfig = field(default_factory=GraspAssistConfig)

    def __post_init__(self):
        if type(self.terminal_contract_version) is not int or self.terminal_contract_version not in (1, 2):
            raise ValueError("terminal_contract_version must be 1 (tick) or 2 (rigid substeps)")
        if self.terminal_contract_version == 2 and self.task_id not in {
                "cast_coil", "cast_keyhole", "hedgehog_in_cage", "horseshoe_ring", "interlocked_claws"}:
            raise ValueError("terminal contract 2 is not qualified for this task/backend")
        if self.history_storage not in HISTORY_STORAGES:
            raise ValueError("history_storage must be segment, memory or disk")
        if isinstance(self.grasp_assist, Mapping):
            data = dict(self.grasp_assist)
            try:
                target_type = SoftGraspTarget if data.get("model") in {"ipc_soft_band_v1", "pbd_local_patch_v1"} else GraspTarget
                data["targets"] = tuple(target_type(**dict(v)) if isinstance(v, Mapping) else v
                                        for v in data.get("targets", ()))
                object.__setattr__(self, "grasp_assist", GraspAssistConfig(**data))
            except (TypeError, ValueError) as error:
                raise ValueError(f"Invalid grasp_assist configuration: {error}") from error
        if not isinstance(self.grasp_assist, GraspAssistConfig):
            raise ValueError("grasp_assist must be a GraspAssistConfig")
        if self.observation_mode not in {"JOINT", "EE"}:
            raise ValueError("observation_mode must be JOINT or EE")
        if self.control_mode not in {"JOINT_ABS", "JOINT_DELTA", "EE_ABS", "EE_DELTA"}:
            raise ValueError("Unsupported control_mode")
        if not isinstance(self.enable_privileged, bool):
            raise ValueError("enable_privileged must be a boolean")
        if self.seed is not None and (type(self.seed) is not int or not 0 <= self.seed < 2**32):
            raise ValueError("seed must be an integer in [0, 2**32)")
        if not isinstance(self.task_id, str) or not self.task_id:
            raise ValueError("task_id must be a nonempty registered name")
        if self.robot_id not in {"auto", "aloha", "panda_robotiq"}:
            raise ValueError("robot_id must be auto, aloha or panda_robotiq")
        if not isinstance(self.variation_id, str) or not self.variation_id:
            raise ValueError("variation_id must be a nonempty name")
        if self.compute_backend not in {"cpu", "cuda"}:
            raise ValueError("compute_backend must be cpu or cuda")
        if self.precision not in {"32", "64"}:
            raise ValueError("precision must be '32' or '64'")
        if self.render_backend != "nyx":
            raise ValueError("Simulator RGB uses Nyx with compact_lab; render_backend must be nyx")
        if isinstance(self.physics_dt_s, bool) or not math.isfinite(self.physics_dt_s) or self.physics_dt_s <= 0:
            raise ValueError("physics_dt_s must be finite and positive")
        for name in ("solver_substeps", "control_decimation", "max_physics_steps", "reset_physics_steps"):
            value = getattr(self, name)
            if name == "max_physics_steps" and value is None:
                continue
            minimum = 0 if name == "reset_physics_steps" else 1
            if isinstance(value, bool) or not isinstance(value, int) or value < minimum:
                raise ValueError(f"{name} must be an integer >= {minimum}")
        if not isinstance(self.enable_rgb, bool):
            raise ValueError("enable_rgb must be a boolean")
        if type(self.enable_depth) is not bool or self.enable_depth and not self.enable_rgb:
            raise ValueError("Depth requires enable_rgb=True and a boolean enable_depth")
        # Nyx renders on a CUDA device for either physics backend; with CPU physics the plugin copies the visual
        # state to its CUDA buffers per render (2026-10-02 study: same frames up to renderer noise).
        options = dict(self.rigid_options)
        unknown = set(options) - set(RIGID_OPTION_OVERRIDES)
        if unknown or any(type(options[k]) is not RIGID_OPTION_OVERRIDES[k] for k in options):
            raise ValueError(f"rigid_options must use qualified overrides {RIGID_OPTION_OVERRIDES}; got {options}")
        object.__setattr__(self, "rigid_options", freeze(options))
        object.__setattr__(self, "task_parameters", freeze(dict(self.task_parameters)))
        for name in ("asset_root", "work_dir"):
            if getattr(self, name) is not None:
                object.__setattr__(self, name, Path(getattr(self, name)).expanduser().resolve())
