"""Scripted expert of ``dough_target_shape``: the pinch-walk over the target slots (``softbody_geom.dough_pinch.pinch_script``)."""

from __future__ import annotations

from ...dough.script import DoughScriptPolicy
from ...softbody_geom.dough_pinch import pinch_script


class DoughTargetShapePolicy(DoughScriptPolicy):
    SCRIPT = staticmethod(pinch_script)


__all__ = ["DoughTargetShapePolicy"]
