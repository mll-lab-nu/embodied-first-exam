"""insert_hdmi scripted demonstration policy.

Phases (right arm; the left arm holds its parked pose)::

    reach -> grasp (lift 15 cm) -> insert (press into the port) -> release, freeze

The insert releases after the plug has dwelt ``release_dwell_steps`` ticks within
``seat_margin`` of the port depth (``release_at_stop``) with the finger effort
raised to the drive limit for the press; the hand freezes at the release pose and
the task judges the opened jaws and the hand-to-plug distance.
"""

from __future__ import annotations

from ...rigid.policy import RigidAssemblyPolicy

__all__ = ["Policy"]


class Policy(RigidAssemblyPolicy):
    """Reach -> grasp -> insert over the single part of cfg.yaml (``plan.rehome_first``)."""
