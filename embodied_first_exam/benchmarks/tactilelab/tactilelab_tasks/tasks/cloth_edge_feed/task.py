"""cloth_edge_feed: feed the gripper along a cloth edge to its corner and clamp it.

Scene (env frame, work plate top ``table_z``): a shelf (static box) with a short felt-like cloth lying on it.  The cloth
overhangs the shelf's front face by ``overhang``; its far end (``clamp_len`` deep, on the shelf) is held by a clamp bar
(pinned particles under a static bar), so the cloth cannot be dragged along.  The right gripper pinches the overhanging
front edge from above and below (horizontal pinch, hand pointing +x) and slides the pinch along that edge (+y) until the
cloth's corner (``ix = 0, iy = ny``) sits between the pads, then closes on it.

Success (``success_predicate``, held ``success.hold`` ticks):

* corner in the grip zone: the corner particle is inside ``corner_zone`` of the pad midpoint frame and both pads touch the
  cloth there;
* real relative feed: the material coordinate (rest arc length along the edge) of the pinch moved by at least ``feed_min``
  since the pinch was established (the pads slid over the cloth instead of carrying it);
* not dragged: the RMS displacement of the free cloth from its settled state stays below ``drag_max``;
* not released: the pads kept contact during the feed (no gap longer than ``lost_max`` ticks).

Truncated: the pinch was lost, the cloth was dragged away or fell off, or the cloth was pushed through a gel pad.
"""

from __future__ import annotations

from typing import Any, Dict, List

import numpy as np

from ...soft import metrics as M
from ...soft.base import SoftTask, _deep_merge
from ...softbody_geom import soft_scenes, spec

__all__ = ["ClothEdgeFeedTask", "SUCCESS_DEFAULTS"]

SUCCESS_DEFAULTS: Dict[str, Any] = {
    "hold": 15,
    "feed_min": 0.03,
    "corner_zone": [0.0085, 0.0075, 0.01],
    "drag_max": 0.015,
    "lost_max": 25,
    "min_contacts": 1,
    "pinch_gap": 0.0105,
}


class ClothEdgeFeedTask(SoftTask):
    name = "cloth_edge_feed"

    def __init__(self, cfg: Dict[str, Any], **kw):
        super().__init__(cfg, **kw)
        self.g = _deep_merge(soft_scenes.CLOTH_EDGE_FEED, cfg.get("world", {}))
        self.nx, self.ny = (int(v) for v in self.g["cloth_cells"])
        ids = soft_scenes.cloth_edge_feed_ids(self.g["cloth_cells"])
        self.corner_id = int(ids["corner"][0])
        self.edge_ids = ids["edge"]
        self.s = _deep_merge(SUCCESS_DEFAULTS, cfg.get("success", {}))
        self._m: Dict[str, Any] = {}

    # ------------------------------------------------------------------ scene
    def geometry(self) -> Dict[str, Any]:
        return soft_scenes.cloth_edge_feed_geometry(self.g, self.table_z)

    def build_world(self) -> Dict[str, Any]:
        return soft_scenes.cloth_edge_feed_world(self.g, self.table_z)

    def fixtures(self) -> List[Dict[str, Any]]:
        s = self.g["shelf"]
        h = float(s["height"])
        cx = float(s["x_front"]) + 0.5 * float(s["depth"])
        geo = self.geometry()
        return [
            {
                "name": "shelf",
                "center": [cx, float(self.g["center_y"]), self.table_z + 0.5 * h],
                "half": [0.5 * float(s["depth"]), float(s["half_y"]), 0.5 * h],
                "color": [0.55, 0.55, 0.60],
                "friction": 0.5,
            },
            {
                "name": "clamp",
                "center": geo["clamp_centre"].tolist(),
                "half": geo["clamp_half"].tolist(),
                "color": [0.25, 0.30, 0.45],
                "friction": 0.8,
            },
        ]

    # ------------------------------------------------------------------ episode
    def initial_state(self) -> Dict[str, Any]:
        rest = spec.cloth_rest_positions(self.build_world()["cloth"])
        return {"particle_q": rest.astype(np.float32)}

    def on_reset(self, state: Dict[str, np.ndarray]) -> None:
        self._m = {
            "rest": None,
            "edge_rest_s": None,
            "pinched": False,
            "s_pinch": None,
            "s_now": None,
            "s_max": 0.0,
            "lost": 0,
            "drag": 0.0,
            "contacts": np.zeros(2, dtype=np.int64),
            "corner_ok": False,
            "feed": 0.0,
        }

    def update_metrics(self, state: Dict[str, np.ndarray], pads: np.ndarray) -> None:
        m = self._m
        if not m:
            return
        q = np.asarray(state["particle_q"], dtype=np.float64)
        if not np.isfinite(q).all():
            self.truncation_reason = self.truncation_reason or "cloth state is not finite"
            return
        if self.settling or m["rest"] is None:
            # the settled cloth is the reference of the drag metric (taken at the end of the settle window)
            if self.soft_ticks >= self.settle_ticks - 1 or (m["rest"] is None and self.soft_ticks == 0):
                m["rest"] = q.copy()
                m["edge_rest_s"] = M.edge_arclength(q[self.edge_ids])
            return
        pads2 = np.asarray(pads, dtype=np.float64)[:2]
        m["contacts"] = M.contact_counts(M.cloth_samples(q, self.tris), float(self.g["radius"]), pads2, self.pad_halves)
        # the grip zone is axis aligned with the commanded pinch frame (approach +x, closing axis z, along the edge y)
        mid = np.concatenate([pads2[:, :3].mean(axis=0), [0.0, 0.0, 0.0, 1.0]])
        s_now, _ = M.project_on_polyline(q[self.edge_ids], m["edge_rest_s"], mid[:3])
        m["s_now"] = s_now
        both = bool(m["contacts"].sum() >= 2 * int(self.s["min_contacts"]))
        gap = float(np.linalg.norm(pads2[0, :3] - pads2[1, :3]))
        closed = gap <= float(self.s["pinch_gap"]) + 0.012
        if not m["pinched"]:
            if both and closed:
                m["pinched"], m["s_pinch"], m["s_max"] = True, s_now, s_now
        else:
            m["s_max"] = max(m["s_max"], s_now)
            m["lost"] = 0 if both else m["lost"] + 1
        m["feed"] = (s_now - m["s_pinch"]) if m["s_pinch"] is not None else 0.0
        m["drag"] = M.displacement_rms(q, m["rest"], mask=np.arange(len(q)) % (self.nx + 1) >= 2)
        m["corner_ok"] = M.in_frame_box(q[self.corner_id], mid, self.s["corner_zone"]) and both

    def success_predicate(self) -> bool:
        m = self._m
        if not m or m["rest"] is None or "particle_q" not in self.state:
            return False
        q = np.asarray(self.state["particle_q"])
        reason = None
        if not np.isfinite(q).all():
            reason = "cloth state is not finite"
        elif m["pinched"] and m["lost"] > int(self.s["lost_max"]):
            reason = "the pinch was lost"
        elif m["drag"] > 4.0 * float(self.s["drag_max"]):
            reason = "the cloth was dragged away"
        elif q[:, 2].min() < self.table_z - 0.02:
            reason = "the cloth fell off the table"
        if reason is not None:
            self.truncation_reason = self.truncation_reason or reason
            return False
        return bool(
            m["pinched"]
            and m["corner_ok"]
            and m["feed"] >= float(self.s["feed_min"])
            and m["drag"] <= float(self.s["drag_max"])
            and m["lost"] <= int(self.s["lost_max"])
        )

    def task_obs(self) -> Dict[str, np.ndarray]:
        m = self._m
        if not m:
            return {}
        return {
            "feed": np.array([m["feed"]], dtype=np.float32),
            "drag": np.array([m["drag"]], dtype=np.float32),
            "pad_contacts": np.asarray(m["contacts"], dtype=np.float32),
            "corner_ok": np.array([float(m["corner_ok"])], dtype=np.float32),
            "pinched": np.array([float(m["pinched"])], dtype=np.float32),
        }

    def task_metrics(self) -> Dict[str, float]:
        m = self._m
        if not m:
            return {}
        return {
            "feed_mm": 1e3 * m["feed"],
            "drag_mm": 1e3 * m["drag"],
            "corner_ok": int(m["corner_ok"]),
            "pinched": int(m["pinched"]),
            "lost": int(m["lost"]),
        }

    # ------------------------------------------------------------------ helpers for the policy
    def cloth_z_near(self, xy, radius: float = 0.012) -> float:
        """Mean height of the cloth particles within ``radius`` of ``xy`` (the sheet's centre line where a pinch will sit)."""
        q = np.asarray(self.state["particle_q"], dtype=np.float64)
        near = q[np.linalg.norm(q[:, :2] - np.asarray(xy, dtype=np.float64)[None, :2], axis=1) < radius]
        return float(near[:, 2].mean()) if len(near) else float(q[:, 2].mean())

    def corner_position(self) -> np.ndarray:
        return np.asarray(self.state["particle_q"][self.corner_id], dtype=np.float64)

    def edge_point(self, frac: float) -> np.ndarray:
        """The edge point at fraction ``frac`` (0 = the -y corner, 1 = the +y corner) of the free edge, as it lies now."""
        q = np.asarray(self.state["particle_q"], dtype=np.float64)[self.edge_ids]
        s = M.edge_arclength(q)
        t = float(np.clip(frac, 0.0, 1.0)) * s[-1]
        return np.array([np.interp(t, s, q[:, k]) for k in range(3)])
