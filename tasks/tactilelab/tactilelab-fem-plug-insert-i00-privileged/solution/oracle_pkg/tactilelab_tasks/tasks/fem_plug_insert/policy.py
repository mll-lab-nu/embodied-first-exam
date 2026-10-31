"""Scripted expert of ``fem_plug_insert``: pick, carry, seat, release (``softbody_geom.plug_pad_scene.plug_pad_script``) in the pad-pair frame."""

from __future__ import annotations

from ...dough.script import DoughScriptPolicy
from ...softbody_geom.plug_pad_scene import plug_pad_script


class FemPlugInsertPolicy(DoughScriptPolicy):
    SCRIPT = staticmethod(plug_pad_script)


__all__ = ["FemPlugInsertPolicy"]
