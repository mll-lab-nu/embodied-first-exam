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
from .cable_routing_generator import build_cable_routing_episode_spec
from .maze_wall_removal_generator import build_maze_wall_removal_episode_spec
from .onestroke_generator import build_onestroke_episode_spec
from .peeling_generator import build_peeling_episode_spec
from .stacked_plate_generator import build_stacked_plate_episode_spec
from .swap_generator import build_swap_episode_spec
from .untangle_generator import build_untangle_episode_spec
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
    "build_cable_routing_episode_spec",
    "build_maze_wall_removal_episode_spec",
    "build_onestroke_episode_spec",
    "build_peeling_episode_spec",
    "build_stacked_plate_episode_spec",
    "build_swap_episode_spec",
    "build_untangle_episode_spec",
    "iter_episode_specs",
    "load_split",
    "make_episode_spec",
    "split_seeds",
]
