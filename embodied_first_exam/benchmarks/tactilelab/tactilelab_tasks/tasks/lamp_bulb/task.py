"""lamp_bulb task: scene, privileged observation and success latch (see cfg.yaml)."""

from __future__ import annotations

from ...rigid.task import RigidAssemblyTask


class Task(RigidAssemblyTask):
    """Rigid assembly task configured by tasks/lamp_bulb/cfg.yaml."""

    name = "lamp_bulb"


__all__ = ["Task"]
