"""gear_mesh task: scene, privileged observation and success latch (see cfg.yaml)."""

from __future__ import annotations

from ...rigid.task import RigidAssemblyTask


class Task(RigidAssemblyTask):
    """Rigid assembly task configured by tasks/gear_mesh/cfg.yaml."""

    name = "gear_mesh"


__all__ = ["Task"]
