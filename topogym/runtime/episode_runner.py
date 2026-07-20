from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Protocol

from topogym.generation import EpisodeResult, EpisodeSpec
from topogym.planning import EpisodePlan


@dataclass(frozen=True)
class EpisodeRunOptions:
    """Presentation/runtime options that should not change the episode variant."""

    viewer: bool = False
    record_video: Path | str | None = None
    close_on_finish: bool = False
    verbose: bool = False


@dataclass(frozen=True)
class EpisodeRunContext:
    """Resolved inputs consumed by a concrete task runner."""

    spec: EpisodeSpec
    plan: EpisodePlan | None = None
    options: EpisodeRunOptions = field(default_factory=EpisodeRunOptions)


class EpisodeRunner(Protocol):
    """Minimal interface implemented by task-specific runners."""

    def run(self, context: EpisodeRunContext) -> EpisodeResult:
        """Build, execute, verify, and return a structured result."""
