"""``fem_plug_insert``: the two gel pads pinch a compliant (tetrahedral VBD) rubber plug standing in a loose pick socket,
lift it, carry it over the press-fit target hole (45 degree lead-in funnel), seat it, release and withdraw.  The pads are
the kinematic colliders of the sidecar's ``fem.plugpad`` world (friction grip); the plug's boundary is the tactile target
(fixed topology, refitted every sidecar step and carried on with its bulk velocity in between).

Success (``softbody_geom.plug_pad_scene.plug_pad_report``, judged once the pads are ``clear_z`` above the plate): seated depth
>= ``seated_min`` of the hole depth, press-fit squeeze inside ``compression_range``, tilt below ``tilt_max_deg``, centred on
the hole within ``xy_tol``.
"""

from __future__ import annotations

from typing import Dict

from ...dough.base import DoughTask
from ...softbody_geom import plug_pad_scene as pps


class FemPlugInsertTask(DoughTask):
    name = "fem_plug_insert"
    kind = "plug_pads"
    metric_names = ("depth", "seated", "compression", "tilt")

    def judge(self, scene, q):
        p = self.p
        return pps.plug_pad_report(
            q,
            scene.extra["spec"],
            (scene.info["hole_x"], scene.info["hole_y"]),
            0.0,
            seated_min=float(p.get("seated_min", 0.85)),
            compression_range=tuple(p.get("compression_range", (0.0, 0.30))),
            tilt_max_deg=float(p.get("tilt_max_deg", 10.0)),
            xy_tol=float(p.get("xy_tol", 0.004)),
        )

    def report_metrics(self, r) -> Dict[str, float]:
        return {
            "depth": float(r.depth),
            "seated": float(r.seated_frac),
            "compression": float(r.compression),
            "tilt": float(r.tilt_deg),
        }


__all__ = ["FemPlugInsertTask"]
