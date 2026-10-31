"""Shared layer of the cloth / cable tasks: the soft-world task base, the step-plan policies and the metrics.

* :mod:`.base` - :class:`SoftTask`: owns a ``softbody.world`` in the Newton sidecar, mirrors the gripper colliders from the
  robot links every tick, exposes the soft state as privileged observation, raycasts the two GelSight Mini sensors against
  the deformed surface, and provides the pinch-frame helpers the plans use.
* :mod:`.plan` - :class:`Step` / :class:`StepPolicy`: the scripted experts as lists of steps over the ``MoveL`` / ``Gripper``
  primitives of :mod:`tactilelab_tasks.core.policy`.
* :mod:`.metrics` - pure-numpy contact counts, pad penetration, cloth / cable / fold metrics.
* :mod:`.kinematic_hand` - a kinematic stand-in of the robot for sidecar-only tests.

Importing this package pulls in numpy only; Isaac Lab, torch and warp are imported lazily by :meth:`SoftTask.build`.
"""

from . import metrics
from .base import DEFAULT_CLOSE_GAP_CALIB, PAD_HALF, SoftMeshVisual, SoftTactileRig, SoftTask

try:
    from .plan import INTERP, MOTIONGEN, SNAP, Step, StepPolicy
except ImportError:  # not part of this copy
    pass

__all__ = [
    "SoftTask",
    "SoftTactileRig",
    "SoftMeshVisual",
    "Step",
    "StepPolicy",
    "SNAP",
    "MOTIONGEN",
    "INTERP",
    "DEFAULT_CLOSE_GAP_CALIB",
    "PAD_HALF",
    "metrics",
]
