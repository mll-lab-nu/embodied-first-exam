"""``dough_press_thickness``: the two gel pads pinch a dough ridge standing on a plate (pinch-walk: close, hold, release,
step along the ridge, withdraw).  The closed pads (~6.5 mm between the gel faces) set the thickness.

Success (``softbody_geom.dough_pinch.pinch_report``, judged once the pads are ``clear_z`` above the plate): the mean x-width
of the dough in the judged height band over the pinched zones is within ``thickness_tol`` of ``target_thickness``, the
zones are flat along the ridge (``flatness_tol``), little dough left the workspace.
"""

from __future__ import annotations

from typing import Dict

import numpy as np

from ...dough.base import DoughTask
from ...softbody_geom import dough_pinch as dp


class DoughPressThicknessTask(DoughTask):
    name = "dough_press_thickness"
    kind = "pinch"
    metric_names = ("thickness", "flatness", "outside", "thickness_loose_ok")

    def judge(self, scene, q):
        p = self.p
        return dp.pinch_report(
            q,
            scene.pvol,
            scene.info,
            centers=tuple(scene.extra.get("pinch_offsets", p.get("pinch_offsets", (-0.018, 0.018)))),
            keep_centers=tuple(scene.extra.get("keep_offsets", ())),
            keep_min=float(p.get("keep_min", 0.014)),
            half_len=float(p.get("zone_half", 0.005)),
            target_thickness=float(p.get("target_thickness", 0.009)),
            thickness_tol=float(p.get("thickness_tol", 0.002)),
            flatness_tol=float(p.get("flatness_tol", 0.0035)),
            band=tuple(p.get("band", (0.013, 0.021))),
            workspace_radius=float(p.get("workspace_radius", 0.09)),
            outside_tol=float(p.get("outside_tol", 0.03)),
        )

    def report_metrics(self, r) -> Dict[str, float]:
        # thickness_loose_ok is informational: the same judgement with the looser window; the success label stays the strict one
        p = self.p
        others = [x for x in str(r.why).split("; ") if x and x != "ok" and not x.startswith("thickness")]
        thk = float(r.thickness_mean)
        loose = bool(
            np.isfinite(thk)
            and not others
            and abs(thk - float(p.get("loose_target_thickness", 0.008))) <= float(p.get("loose_thickness_tol", 0.004))
        )
        return {
            "thickness": float(r.thickness_mean),
            "flatness": float(r.flatness),
            "outside": float(r.outside_frac),
            "thickness_loose_ok": float(loose),
        }


__all__ = ["DoughPressThicknessTask"]
