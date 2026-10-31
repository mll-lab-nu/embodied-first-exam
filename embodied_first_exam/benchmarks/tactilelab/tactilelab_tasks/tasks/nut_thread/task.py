"""nut_thread task: scene, privileged observation and success latch (see cfg.yaml)."""

from __future__ import annotations

from ...rigid.task import RigidAssemblyTask


class Task(RigidAssemblyTask):
    """Rigid assembly task configured by tasks/nut_thread/cfg.yaml."""

    name = "nut_thread"


__all__ = ["Task"]
