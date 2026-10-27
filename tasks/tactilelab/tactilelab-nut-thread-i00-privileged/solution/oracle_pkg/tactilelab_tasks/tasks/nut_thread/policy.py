"""nut_thread scripted demonstration policy (grasp -> insert -> screw per part)."""

from __future__ import annotations

from ...rigid.policy import RigidAssemblyPolicy


class Policy(RigidAssemblyPolicy):
    """Phases built from cfg.yaml of the nut_thread task."""


__all__ = ["Policy"]
