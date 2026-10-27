"""cable_route_channel: press a cable into a shallow slot, segment by segment (see cfg.yaml).

The first segments of the cable are clamped in the slot's first section; the rest lies beside the slot on a row of cable
clips at the gel-pad height, its tail running up to a tall far post.  Success (``success_predicate``): the cable lies in the
slot continuously from the fixed end for at least ``route_len`` (every node of that prefix within the slot's lateral bounds
and on the slot floor), the hand has released it (pad gap above ``open_gap``) and the cable is at rest; held for
``success.hold`` ticks.  Truncated when the cable leaves the plate or a gel pad cuts into a fixture.
"""

from __future__ import annotations

from typing import Any, Dict, Optional, Tuple

import numpy as np

from ...core.types import CONTROL_DT
from ...soft import cables
from ...soft.base import SoftTask
from ...softbody_geom import spec


class Task(SoftTask):
    """Cable-routing task on the ``softbody.world`` cable rod."""

    name = "cable_route_channel"
    success_hold = 25

    def __init__(self, cfg: Dict[str, Any], **kw):
        super().__init__(cfg, **kw)
        self.g = spec.merge_dicts(cables.ROUTE, dict(cfg.get("world", {})))
        self.geo = cables.RouteScene(self.g, self.table_z)
        self.tracker: Optional[cables.RouteTracker] = None

    # ------------------------------------------------------------------ scene
    def fixtures(self):
        return [dict(fx, physics=True, friction=0.5) for fx in self.geo.fixtures()]

    def initial_state(self) -> Dict[str, Any]:
        self.tracker = cables.RouteTracker(self.geo, CONTROL_DT)
        return {"cable_points": self.geo.initial_cable()}

    def rest_cable_points(self, points):
        return self.geo.rest_cable_points(points)

    def build_world(self) -> Dict[str, Any]:
        return self.geo.world_block()

    # ------------------------------------------------------------------ what the policy reads
    def nodes(self) -> np.ndarray:
        return np.asarray(self.state["cable_nodes"], dtype=np.float64)

    def cable_point_at(self, s: float) -> Tuple[np.ndarray, np.ndarray]:
        """Cable point at arc length ``s`` from the fixed end and the horizontal unit tangent there."""
        return cables.cable_point_at(self.nodes(), s)

    def centerline_point(self, s: float) -> Tuple[np.ndarray, np.ndarray]:
        return self.geo.centerline_point(s)

    def closed_face_gap(self) -> Optional[float]:
        """Gel-face gap of the calibrated pinch close (None with the fixed close command)."""
        if self.pinch_overlap is None:
            return None
        return cables.closed_face_gap(float(self.g["radius"]), float(self.pinch_overlap))

    def next_pick(
        self, s_min: float, margin: float, grip_dz: float = 0.026, open_gap: float = 0.082
    ) -> Optional[float]:
        """Arc length of the next pick on the live cable (None when the cable is used up)."""
        return self.geo.next_pick(
            self.nodes(), s_min, margin=margin, grip_dz=grip_dz, closed_gap=self.closed_face_gap(), open_gap=open_gap
        )

    def routed(self) -> float:
        return 0.0 if self.tracker is None else float(self.tracker.routed)

    # ------------------------------------------------------------------ metrics / success
    def update_metrics(self, state: Dict[str, np.ndarray], pads: np.ndarray) -> None:
        if self.tracker is not None:
            self.tracker.update(np.asarray(state["cable_nodes"], dtype=np.float64), pads)

    def success_predicate(self) -> bool:
        if self.tracker is None or not self.state or self.settling:
            return False
        ok, reason = self.tracker.judge(self.nodes())
        if reason and self.truncation_reason is None:
            self.truncation_reason = reason
        return bool(ok)

    def task_obs(self) -> Dict[str, np.ndarray]:
        d = self.tracker.as_dict() if self.tracker is not None else {}
        return {
            "routed": np.array([d.get("routed", 0.0)], dtype=np.float32),
            "released": np.array([float(d.get("released", False))], dtype=np.float32),
            "speed": np.array([d.get("speed", 0.0)], dtype=np.float32),
            "pad_fixture_overlap": np.array([d.get("pad_fixture_overlap", -1.0)], dtype=np.float32),
            "finger_fixture_overlap": np.array([d.get("finger_fixture_overlap", -1.0)], dtype=np.float32),
            "ok": np.array([float(self._hold_count >= self.success_hold)], dtype=np.float32),
        }

    def task_metrics(self) -> Dict[str, Any]:
        return dict(self.tracker.as_dict()) if self.tracker is not None else {}


__all__ = ["Task"]
