"""``dough_fill_tray``: dough heaped on one side of an open shallow tray; the gripper picks the scraper out of its rack
(a real grasp: open, pre-grasp, descend, close, lift), pushes the heap to the under-filled side in two passes and levels it.

Success (``softbody_geom.dough_metrics.fill_report``, judged once the scraper is ``clear_z`` above the tray floor):
coverage of the tray floor by dough thicker than ``min_h_frac`` x the even-spread level, the initially empty part covered
(``under_min``), a flat surface (``flat_min`` of the covered cells within ``flat_band`` x level), little dough outside the
tray.  The tool feels the dough: ``reaction_gain`` of the sidecar's wrench (clipped to 50 N) is applied to the PhysX scraper.
The gel pads see the rigid scraper handle (the tactile target of this task).
"""

from __future__ import annotations

from typing import Dict

from ...dough.base import DoughTask
from ...softbody_geom import dough_metrics as dm


class DoughFillTrayTask(DoughTask):
    name = "dough_fill_tray"
    kind = "fill"
    metric_names = ("coverage", "flat_frac", "under_cover", "surface_err", "outside")

    def judge(self, scene, q):
        p = self.p
        return dm.fill_report(
            q,
            scene.pvol,
            scene.grid,
            scene.masks["tray"],
            target_h=float(scene.info["fill_level"]) * float(p.get("level_factor", 1.0)),
            min_h_frac=float(p.get("min_h_frac", 0.35)),
            coverage_min=float(p.get("coverage_min", 0.7)),
            surface_tol=float(p.get("surface_tol", 0.0)),
            outside_tol=float(p.get("outside_tol", 0.02)),
            flat_min=float(p.get("flat_min", 0.6)),
            flat_band=tuple(p.get("flat_band", (0.5, 1.5))),
            under_mask=scene.masks.get("under"),
            under_min=float(p.get("under_min", 0.0)),
        )

    def report_metrics(self, r) -> Dict[str, float]:
        return {
            "coverage": float(r.coverage),
            "flat_frac": float(r.flat_frac),
            "under_cover": float(r.under_cover),
            "surface_err": float(r.surface_err),
            "outside": float(r.outside_frac),
        }


__all__ = ["DoughFillTrayTask"]
