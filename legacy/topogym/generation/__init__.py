"""Stable episode generation contracts.

This package owns the seed-to-spec boundary.  It should stay free of Genesis
handles so the same generated episode can be inspected, logged, replayed, or
passed to a viewer/video/training runner.
"""

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
from .episode_index import (
    iter_episode_specs,
    load_split,
    make_episode_spec,
    split_seeds,
)

__all__ = [
    "EpisodeArtifact",
    "EpisodeKey",
    "EpisodeResult",
    "EpisodeSpec",
    "EpisodeStatus",
    "ExecutionProfile",
    "ScenePreset",
    "TaskLayout",
    "TaskVariant",
    "iter_episode_specs",
    "load_split",
    "make_episode_spec",
    "split_seeds",
]
