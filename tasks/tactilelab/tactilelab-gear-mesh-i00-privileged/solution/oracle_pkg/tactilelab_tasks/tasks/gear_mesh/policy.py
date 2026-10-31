"""gear_mesh scripted demonstration policy (grasp -> insert -> screw per part)."""

from __future__ import annotations

from ...rigid.policy import RigidAssemblyPolicy


class Policy(RigidAssemblyPolicy):
    """Phases built from cfg.yaml of the gear_mesh task."""


__all__ = ["Policy"]
