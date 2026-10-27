"""``dough_target_shape``: the gel pads pinch a dough bar at the slots of the target pattern (two of three slots, 32 mm
apart); the remaining slot must stay thick.  Same machinery and metric as ``dough_press_thickness``, per zone, plus the
``keep`` test of ``pinch_report`` (an untouched slot narrower than ``keep_min`` fails).

The nominal pattern is fixed by the configuration (``pinch_offsets`` / ``keep_offsets``): the outer two slots are pinched,
the middle one is kept.
"""

from __future__ import annotations

from ..dough_press_thickness.task import DoughPressThicknessTask


class DoughTargetShapeTask(DoughPressThicknessTask):
    name = "dough_target_shape"


__all__ = ["DoughTargetShapeTask"]
