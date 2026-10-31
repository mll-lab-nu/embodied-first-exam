"""Dough (implicit MPM) and FEM plug tasks: the Isaac side of the Newton sidecar worlds.

Modules
    pads      pad-pair frame of the two gel pads (pure numpy): the frame the direct-sensor scripts command
    scene     Isaac Lab scene of a dough task built from the task block of its ``cfg.yaml`` (plate, tray, rack, hole plate)
    visual    USD mesh of a deformable surface (the dough's marching-cubes surface, the plug's boundary)
    tactile   GelSight-Mini sensors raycast against the deformable surface and / or a rigid tool
    script    :class:`DoughScriptPolicy`: runs a dict script (open / close / move / wait / hold_width) with ``MoveL`` / ``Gripper``
    base      :class:`DoughTask`: owns the sidecar world, couples it to the robot, judges the dough

Only :mod:`pads` and the pure parts of :mod:`script` import without a simulator; everything Isaac-specific is imported
lazily inside the methods that need it.
"""

from .base import DoughTask  # noqa: F401

try:
    from .script import DoughScriptPolicy  # noqa: F401
except ImportError:  # not part of this copy
    pass

__all__ = ["DoughTask", "DoughScriptPolicy"]
