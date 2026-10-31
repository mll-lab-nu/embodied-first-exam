"""Scripted expert of ``cloth_edge_feed`` (pinch frame = the two gel pads; horizontal pinch, hand pointing +x)::

    open -> pre-pinch pose in front of the edge -> slide in -> close -> feed along +y to the corner (closed loop on the
    corner's live position) -> hold -> verdict

Policy numbers (``cfg["policy"]``): ``pre_dx`` (pre-pinch distance in front of the edge), ``pre_mode`` (1 = planned move,
2 = converging interpolation), ``in_dx`` (pad centre behind the edge tip at the pinch), ``in_idle`` (ticks at the edge
before the close), ``start_frac`` (where on the edge the pinch starts), ``end_dx`` / ``end_margin`` (feed target offsets
from the corner).
"""

from __future__ import annotations

from typing import List

import numpy as np

from ...soft.plan import INTERP, MOTIONGEN, Step, StepPolicy

__all__ = ["ClothEdgeFeedPolicy"]


class ClothEdgeFeedPolicy(StepPolicy):
    def build_plan(self) -> List[Step]:
        task, p = self.task, self.p
        pre_dx = float(p.get("pre_dx", 0.05))
        in_dx = float(p.get("in_dx", 0.006))
        in_idle = int(p.get("in_idle", 120))
        end_dx = float(p.get("end_dx", in_dx))
        end_margin = float(p.get("end_margin", 0.0))
        start_frac = float(p.get("start_frac", 0.375))
        pre_mode = int(p.get("pre_mode", 2))
        R = self.R_pinch(approach=(1.0, 0.0, 0.0), normal=(0.0, 0.0, 1.0))
        e0 = task.edge_point(start_frac)
        corner = task.corner_position()
        x_edge, y0 = float(e0[0]), float(e0[1])
        z = task.cloth_z_near((x_edge + in_dx, y0))
        self._log(
            f"edge x={x_edge:.3f} z={z:.3f}; pinch y {y0:.3f} -> {float(corner[1]) - end_margin:.3f} (corner {np.round(corner, 3).tolist()})"
        )
        pre = lambda: (x_edge - pre_dx, y0, z)  # noqa: E731
        inn = lambda: (x_edge + in_dx, y0, z)  # noqa: E731
        # closed loop on the corner: the friction drags it a few mm along with the pads
        end = lambda: (float(task.corner_position()[0]) + end_dx, float(task.corner_position()[1]) - end_margin, z)  # noqa: E731
        Rf = lambda: R  # noqa: E731
        mode, converge = (MOTIONGEN, None) if pre_mode == 1 else (INTERP, True)
        return [
            self.step_hand("open", "open"),
            self.step_move("pre_pinch", mode, pre, Rf, converge=converge, post_idle=80, refine=2),
            self.step_move("slide_in", INTERP, inn, Rf, post_idle=in_idle, refine=3, tol=0.005),
            self.step_hand("pinch", "close"),
            self.step_wait("settle_pinch", 10),
            self.step_move("feed", INTERP, end, Rf, refine=4, tol=0.003, track=True),
            self.step_wait("hold", 10),
            self.verdict_step(),
        ]
