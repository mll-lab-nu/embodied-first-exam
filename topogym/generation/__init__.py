"""Shared contracts; task implementations own their task-specific APIs."""

from .episode_spec import (
    EpisodeArtifact,
    EpisodeKey,
    EpisodeResult,
    EpisodeSpec,
    EpisodeStatus,
    ExecutionProfile,
    ScenePreset,
    TaskLayout,
    TaskVariant,
)

__all__ = ['EpisodeArtifact', 'EpisodeKey', 'EpisodeResult', 'EpisodeSpec', 'EpisodeStatus', 'ExecutionProfile', 'ScenePreset', 'TaskLayout', 'TaskVariant']
