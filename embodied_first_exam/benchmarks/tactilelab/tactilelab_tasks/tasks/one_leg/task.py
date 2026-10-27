"""one_leg task: scene, privileged observation and success latch (see cfg.yaml)."""

from __future__ import annotations

from ...rigid.task import RigidAssemblyTask


class Task(RigidAssemblyTask):
    """Rigid assembly task configured by tasks/one_leg/cfg.yaml."""

    name = "one_leg"


__all__ = ["Task"]
