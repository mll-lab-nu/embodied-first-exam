"""Insert-HDMI task: the HDMI connector into the vertical port.

The seating judge of :class:`~tactilelab_tasks.tasks.insert_tube.task.SeatedInsertTask`
with the port numbers: success when the plug tongue is about 5 mm into the 9.9 mm
port, within 6 mm of the port axis and 15 deg of its direction, after the hand has
released and moved away.
"""

from __future__ import annotations

from ..insert_tube.task import SeatedInsertTask

__all__ = ["Task"]


class Task(SeatedInsertTask):
    """Insert-HDMI on the X-Trainer (see the module docstring)."""

    name = "insert_hdmi"
