"""Scripted expert of ``dough_fill_tray``: rack pickup + scrape passes (``softbody_geom.dough_expert.fill_script`` with ``tool_pickup``).

The pickup steps (open, pre-grasp 60 mm above the handle, grasp at the tool's rest pose, close, lift 40 mm) are ``free`` moves of
the hand to the nominal grip; the lift measures the real tool-in-hand pose (tolerance 15 mm / 12 degrees) and every pass
re-measures it in the air before lowering the blade.
"""

from __future__ import annotations

from ...dough.script import DoughScriptPolicy
from ...softbody_geom.dough_expert import fill_script


class DoughFillTrayPolicy(DoughScriptPolicy):
    SCRIPT = staticmethod(fill_script)


__all__ = ["DoughFillTrayPolicy"]
