"""square_table task: scene, privileged observation and success latch (see cfg.yaml)."""

from __future__ import annotations

from ...rigid.task import RigidAssemblyTask


class Task(RigidAssemblyTask):
    """Rigid assembly task configured by tasks/square_table/cfg.yaml."""

    name = "square_table"


__all__ = ["Task"]
