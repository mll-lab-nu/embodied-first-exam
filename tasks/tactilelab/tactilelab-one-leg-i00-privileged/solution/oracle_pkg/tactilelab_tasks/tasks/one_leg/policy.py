"""one_leg scripted demonstration policy (grasp -> insert -> screw per part)."""

from __future__ import annotations

from ...rigid.policy import RigidAssemblyPolicy


class Policy(RigidAssemblyPolicy):
    """Phases built from cfg.yaml of the one_leg task."""


__all__ = ["Policy"]
