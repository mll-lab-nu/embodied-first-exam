"""Scripted expert of ``dough_press_thickness``: the pinch-walk of ``softbody_geom.dough_pinch.pinch_script`` in the pad-pair frame."""

from __future__ import annotations

from ...dough.script import DoughScriptPolicy
from ...softbody_geom.dough_pinch import pinch_script


class DoughPressThicknessPolicy(DoughScriptPolicy):
    SCRIPT = staticmethod(pinch_script)


__all__ = ["DoughPressThicknessPolicy"]
