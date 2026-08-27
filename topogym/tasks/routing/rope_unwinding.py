"""Rope Unwinding (task book 2.5): take a rope that is wound on a post off it.

The mirror of Rope Winding, and built the same way: a Cable Routing scene with
the winding fixture set, so the builder subclasses Cable Routing's. What makes
it a different task is

- the initial state: the rope spawns ALREADY WOUND `winding.start_turns` times
  around the post (the `helix_around` entry of `routes.initial`), its anchor end
  pinned at the terminal and its plug lying on the board;
- the oracle: the same planner as rope_winding, orbiting the other way and
  descending from the top wrap (`winding.turns: 0` with `start_turns > 0`,
  `topogym/planning/rope_winding_planner.py`);
- the criterion: the same signed winding number, with target 0
  (`topogym/supervision/rope_winding.py`).
"""

from __future__ import annotations

from .cable_routing import (
    CableRoutingLayout,
    CableRoutingScene,
    CableRoutingSceneBuilder,
)

RopeUnwindingLayout = CableRoutingLayout
RopeUnwindingScene = CableRoutingScene


class RopeUnwindingSceneBuilder(CableRoutingSceneBuilder):
    """Cable Routing's scene assembly, driven by the rope_unwinding task config."""


__all__ = [
    "RopeUnwindingLayout",
    "RopeUnwindingScene",
    "RopeUnwindingSceneBuilder",
]
