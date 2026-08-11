"""Rope Winding (task book 2.4): wind a rope N turns around a post, then place it.

The scene is a Cable Routing scene with a different fixture set: same asset
family (routing post, fixed terminal, industrial plug, flush ports), same rope
backend seam (anchor band at the terminal, follow band at the plug), same layout
and route readers. So the builder subclasses Cable Routing's rather than copying
it -- what makes this a different task is not how the scene is assembled but

- the oracle: one helix around a single post instead of a hand-authored
  multi-peg route (`topogym/planning/rope_winding_planner.py`), and
- the criterion: a signed winding number instead of a side-of-peg signature
  (`topogym/supervision/rope_winding.py`, which also owns the `task.winding`
  reading both of those share).
"""

from __future__ import annotations

from .cable_routing import (
    CableRoutingLayout,
    CableRoutingScene,
    CableRoutingSceneBuilder,
)

# The scene/layout containers carry nothing cable-specific (board, fixtures,
# routes, rope handle, backend), so this task uses them under names that say
# which task is being built.
RopeWindingLayout = CableRoutingLayout
RopeWindingScene = CableRoutingScene


class RopeWindingSceneBuilder(CableRoutingSceneBuilder):
    """Cable Routing's scene assembly, driven by the rope_winding task config."""


__all__ = [
    "RopeWindingLayout",
    "RopeWindingScene",
    "RopeWindingSceneBuilder",
]
