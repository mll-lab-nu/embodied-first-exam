from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any, Mapping


class EpisodeStatus(str, Enum):
    """Outcome of one episode, mirroring RoboMME's ``status`` enum.

    ``error`` is an explicit, reportable outcome (a physics blow-up / PBD soft
    abort), not a process crash. ``ongoing`` is the default before a result is
    finalized.
    """

    SUCCESS = "success"
    FAIL = "fail"
    TIMEOUT = "timeout"
    ERROR = "error"
    ONGOING = "ongoing"


def _frozen_dict(value: Mapping[str, Any] | None) -> dict[str, Any]:
    return dict(value or {})


@dataclass(frozen=True)
class EpisodeKey:
    """Stable identity for one generated environment variant."""

    task_id: str
    seed: int
    preset_id: str = "topogym_tabletop_v1"
    variant_id: str = "default"

    def stable_id(self) -> str:
        return (
            f"{self.task_id}__{self.preset_id}"
            f"__seed{int(self.seed)}__{self.variant_id}"
        )


@dataclass(frozen=True)
class ScenePreset:
    """Shared tabletop, robot, camera, color, and coordinate settings."""

    preset_id: str
    common_config: Path | str | None = None
    env_config: Path | str | None = None
    robot_config: Path | str | None = None
    description: str = ""
    metadata: Mapping[str, Any] = field(default_factory=dict)

    def metadata_dict(self) -> dict[str, Any]:
        return _frozen_dict(self.metadata)


@dataclass(frozen=True)
class TaskVariant:
    """Task-specific randomization result produced from a seed."""

    key: EpisodeKey
    difficulty: str = "default"
    parameters: Mapping[str, Any] = field(default_factory=dict)
    #: The episode's natural-language instruction, already filled in for this
    #: seed. It belongs to the variant because for three tasks it varies with a
    #: sampled axis (cloth_fold's corner, ring_transfer's goal post,
    #: rope_winding's direction) -- those are the axes the picture cannot show.
    instruction: str = ""
    #: The same fact as `instruction`, as an integer, for baselines that take no
    #: language: which entry of this task's own finite goal list the sentence
    #: names (linkbar's target colour, red 0 and blue 1). A task whose
    #: instruction is a constant has one goal and leaves this 0. What the number
    #: means per task is the task module's `goal.goal_id_fn`.
    goal_id: int = 0
    notes: str = ""

    def parameters_dict(self) -> dict[str, Any]:
        return _frozen_dict(self.parameters)


@dataclass(frozen=True)
class TaskLayout:
    """World-coordinate geometry derived from a task variant."""

    task_id: str
    layout_id: str = "default"
    frame: str = "world"
    objects: Mapping[str, Any] = field(default_factory=dict)
    metadata: Mapping[str, Any] = field(default_factory=dict)

    def objects_dict(self) -> dict[str, Any]:
        return _frozen_dict(self.objects)

    def metadata_dict(self) -> dict[str, Any]:
        return _frozen_dict(self.metadata)


@dataclass(frozen=True)
class ExecutionProfile:
    """Motion and safety policy used by a runner for one episode."""

    profile_id: str = "default"
    speed_scale: float = 1.0
    safety_profile: str = "default"
    parameters: Mapping[str, Any] = field(default_factory=dict)

    def parameters_dict(self) -> dict[str, Any]:
        return _frozen_dict(self.parameters)


@dataclass(frozen=True)
class EpisodeSpec:
    """Complete, replayable input for building and running one episode."""

    key: EpisodeKey
    preset: ScenePreset
    variant: TaskVariant
    layout: TaskLayout | None = None
    execution_profile: ExecutionProfile = field(default_factory=ExecutionProfile)
    resolved_config: Mapping[str, Any] = field(default_factory=dict)

    @property
    def task_id(self) -> str:
        return self.key.task_id

    @property
    def seed(self) -> int:
        return self.key.seed

    def stable_id(self) -> str:
        return self.key.stable_id()

    def resolved_config_dict(self) -> dict[str, Any]:
        return _frozen_dict(self.resolved_config)


@dataclass(frozen=True)
class EpisodeArtifact:
    """File or diagnostic object emitted by a demo, viewer, or batch run."""

    kind: str
    path: Path | str
    metadata: Mapping[str, Any] = field(default_factory=dict)

    def metadata_dict(self) -> dict[str, Any]:
        return _frozen_dict(self.metadata)


@dataclass(frozen=True)
class EpisodeResult:
    """Structured result shared by demos, future data export, and debugging."""

    key: EpisodeKey
    success: bool
    stable_ready: bool
    export_ready: bool
    status: EpisodeStatus = EpisodeStatus.ONGOING
    failure_reason: str | None = None
    metrics: Mapping[str, float | int | str | bool] = field(default_factory=dict)
    artifacts: tuple[EpisodeArtifact, ...] = ()

    @classmethod
    def ok(
        cls,
        key: EpisodeKey,
        *,
        metrics: Mapping[str, float | int | str | bool] | None = None,
        artifacts: tuple[EpisodeArtifact, ...] = (),
        export_ready: bool = True,
    ) -> "EpisodeResult":
        return cls(
            key=key,
            success=True,
            stable_ready=True,
            export_ready=bool(export_ready),
            status=EpisodeStatus.SUCCESS,
            metrics=_frozen_dict(metrics),
            artifacts=artifacts,
        )

    @classmethod
    def failed(
        cls,
        key: EpisodeKey,
        reason: str,
        *,
        metrics: Mapping[str, float | int | str | bool] | None = None,
        artifacts: tuple[EpisodeArtifact, ...] = (),
        stable_ready: bool = False,
        status: EpisodeStatus = EpisodeStatus.FAIL,
    ) -> "EpisodeResult":
        return cls(
            key=key,
            success=False,
            stable_ready=bool(stable_ready),
            export_ready=False,
            status=EpisodeStatus(status),
            failure_reason=str(reason),
            metrics=_frozen_dict(metrics),
            artifacts=artifacts,
        )

    def metrics_dict(self) -> dict[str, float | int | str | bool]:
        return dict(self.metrics)
