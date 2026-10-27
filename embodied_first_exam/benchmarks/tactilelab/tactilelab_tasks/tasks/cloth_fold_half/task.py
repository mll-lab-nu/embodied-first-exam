"""cloth_fold_half: fold a small cloth once with a real pinch and release it.

Scene (env frame): the cloth lies on a pedestal; its near half is held down by a fixture (pinned particles, the fold line
is the first pinned column) and the far half overhangs the pedestal edge.  The whole layout is turned by 90 degrees about
z (``layout``): the fold line runs along the arm's reach and the flap overhangs to the robot's right.  The gel pads pinch
the flap's free edge, the hand rolls about the fold line with the flap, lets go before the inner finger reaches the pinned
half, and the flap falls onto it; the sheet keeps its crease through the plastic bending hinge of the soft world.

Success (``success_predicate``, held ``success.hold`` ticks, metrics in the layout frame):

* aligned: the free edge of the folded flap lies within ``align_edge`` of its mirror partners (mean xy over the strip) and
  no particle is skewed along the fold line by more than ``align_y``;
* folded over: the flap lies above its partners (mean ``dz >= over_dz``);
* released and at rest: both pads touched the cloth once, now touch nothing, the gripper is open by at least ``open_gap``
  and the fastest particle moves slower than ``rest_speed``.

Truncated: the cloth state is not finite, the cloth left the work plate, or it was pushed through a gel pad.
"""

from __future__ import annotations

from typing import Any, Dict, List

import numpy as np

from ...core.types import CONTROL_DT
from ...soft import metrics as M
from ...soft.base import SoftTask, _deep_merge
from ...softbody_geom import soft_scenes, spec

__all__ = ["ClothFoldHalfTask", "SUCCESS_DEFAULTS"]

SUCCESS_DEFAULTS: Dict[str, Any] = {
    "hold": 30,
    "align_y": 0.008,
    "align_edge": 0.030,
    "over_dz": 0.002,
    "rest_speed": 0.006,
    "open_gap": 0.016,
    "min_contacts": 1,
    "attach_columns": 2,
}


class ClothFoldHalfTask(SoftTask):
    name = "cloth_fold_half"

    def __init__(self, cfg: Dict[str, Any], **kw):
        super().__init__(cfg, **kw)
        self.g = _deep_merge(soft_scenes.CLOTH_FOLD_PINCH, cfg.get("world", {}))
        self.nx, self.ny = (int(v) for v in self.g["cloth_cells"])
        self.grid = np.arange((self.nx + 1) * (self.ny + 1)).reshape(self.ny + 1, self.nx + 1)
        self.s = _deep_merge(SUCCESS_DEFAULTS, cfg.get("success", {}))
        self.sets = M.fold_partners(self.nx, self.ny, int(self.s["attach_columns"]), flap="near")
        self._m: Dict[str, Any] = {}

    # ------------------------------------------------------------------ geometry
    def geometry(self) -> Dict[str, Any]:
        return soft_scenes.cloth_fold_pinch_geometry(self.g, self.table_z)

    def build_world(self) -> Dict[str, Any]:
        return soft_scenes.cloth_fold_pinch_world(self.g, self.table_z)

    def fold_root(self) -> np.ndarray:
        """The fold line on top of the pedestal edge: the point the carry turns around."""
        return self.geometry()["root"]

    def layout_rot(self) -> np.ndarray:
        """Rotation of the layout: world vectors = R @ layout-frame vectors."""
        return soft_scenes.pinch_layout_xf(self.g)[0]

    def to_layout(self, p_world) -> np.ndarray:
        """World point(s) in the layout frame (fold line along +y at the pedestal front, flap toward -x)."""
        R, t = soft_scenes.pinch_layout_xf(self.g)
        return (np.asarray(p_world, dtype=np.float64) - t) @ R

    def from_layout(self, p_layout) -> np.ndarray:
        R, t = soft_scenes.pinch_layout_xf(self.g)
        return np.asarray(p_layout, dtype=np.float64) @ R.T + t

    def fixtures(self) -> List[Dict[str, Any]]:
        lx, ly = (float(v) for v in self.g["cloth_size"])
        s = self.g["shelf"]
        h = float(s["height"])
        top = self.table_z + h
        x0 = float(s["x_front"])
        R, t = soft_scenes.pinch_layout_xf(self.g)
        shelf_c, shelf_h = soft_scenes._xf_box(
            R,
            t,
            [x0 + 0.5 * float(s["depth"]), float(self.g["center_y"]), self.table_z + 0.5 * h],
            [0.5 * float(s["depth"]), float(s["half_y"]), 0.5 * h],
        )
        plate_c, plate_h = soft_scenes._xf_box(
            R,
            t,
            [x0 + 0.25 * lx, float(self.g["center_y"]), top + 0.0004],
            [0.25 * lx + 0.004, 0.5 * ly + 0.006, 0.0004],
        )
        return [
            {"name": "shelf", "center": shelf_c, "half": shelf_h, "color": [0.55, 0.55, 0.60], "friction": 0.5},
            # the hold-down fixture of the pinned half (a marker: the pinned particles are the fixture)
            {"name": "fix_plate", "center": plate_c, "half": plate_h, "color": [0.2, 0.2, 0.25], "friction": 0.5},
        ]

    # ------------------------------------------------------------------ episode
    def initial_state(self) -> Dict[str, Any]:
        rest = spec.cloth_rest_positions(self.build_world()["cloth"])
        return {"particle_q": rest.astype(np.float32)}

    def on_reset(self, state: Dict[str, np.ndarray]) -> None:
        self._m = {
            "rest": None,
            "released": False,
            "gripped": False,
            "contacts": np.zeros(2, dtype=np.int64),
            "err_mean": float("nan"),
            "err_corner": float("nan"),
            "over": float("nan"),
            "speed": 0.0,
            "prev": None,
        }

    def flap_tip(self) -> np.ndarray:
        """Mean position of the flap's free edge (column 0)."""
        q = np.asarray(self.state["particle_q"], dtype=np.float64)
        return q[self.grid[:, 0]].mean(axis=0)

    def cloth_z_near(self, xy, radius: float = 0.012) -> float:
        q = np.asarray(self.state["particle_q"], dtype=np.float64)
        near = q[np.linalg.norm(q[:, :2] - np.asarray(xy, dtype=np.float64)[None, :2], axis=1) < radius]
        return float(near[:, 2].mean()) if len(near) else float(q[:, 2].mean())

    def update_metrics(self, state: Dict[str, np.ndarray], pads: np.ndarray) -> None:
        m = self._m
        if not m:
            return
        q = np.asarray(state["particle_q"], dtype=np.float64)
        if not np.isfinite(q).all():
            self.truncation_reason = self.truncation_reason or "cloth state is not finite"
            return
        if m["rest"] is None:
            m["rest"] = q.copy()
        e = M.fold_errors(self.to_layout(q), self.sets)  # the skew is measured along the fold line (layout y)
        m["err_mean"], m["err_corner"], m["over"] = e["edge"], e["skew"], e["over"]
        if m["prev"] is not None:
            m["speed"] = float(np.abs(q - m["prev"]).max() / CONTROL_DT)
        m["prev"] = q.copy()
        if self.settling:
            return
        pads2 = np.asarray(pads, dtype=np.float64)[:2]
        gap = float(np.linalg.norm(pads2[0, :3] - pads2[1, :3]))
        m["contacts"] = M.contact_counts(M.cloth_samples(q, self.tris), float(self.g["radius"]), pads2, self.pad_halves)
        if np.all(m["contacts"] >= int(self.s["min_contacts"])):
            m["gripped"] = True
        if m["gripped"] and int(m["contacts"].sum()) == 0 and gap >= float(self.s["open_gap"]):
            m["released"] = True

    def success_predicate(self) -> bool:
        m = self._m
        if not m or m["rest"] is None or not np.isfinite(m["err_mean"]) or "particle_q" not in self.state:
            return False
        q = np.asarray(self.state["particle_q"])
        reason = None
        if not np.isfinite(q).all():
            reason = "cloth state is not finite"
        elif q[:, 2].min() < self.table_z - 0.03 or np.abs(q[:, :2]).max() > 0.8:
            reason = "the cloth left the work plate"
        if reason is not None:
            self.truncation_reason = self.truncation_reason or reason
            return False
        return bool(
            m["released"]
            and m["err_mean"] <= float(self.s["align_edge"])
            and m["err_corner"] <= float(self.s["align_y"])
            and m["over"] >= float(self.s["over_dz"])
            and m["speed"] <= float(self.s["rest_speed"])
        )

    def task_obs(self) -> Dict[str, np.ndarray]:
        m = self._m
        if not m:
            return {}
        return {
            "err_mean": np.array([m["err_mean"]], dtype=np.float32),
            "err_corner": np.array([m["err_corner"]], dtype=np.float32),
            "over": np.array([m["over"]], dtype=np.float32),
            "released": np.array([float(m["released"])], dtype=np.float32),
            "pad_contacts": np.asarray(m["contacts"], dtype=np.float32),
        }

    def task_metrics(self) -> Dict[str, float]:
        m = self._m
        if not m:
            return {}
        return {
            "err_mean_mm": 1e3 * m["err_mean"],
            "err_corner_mm": 1e3 * m["err_corner"],
            "over_mm": 1e3 * m["over"],
            "speed_mm_s": 1e3 * m["speed"],
            "released": int(m["released"]),
            "gripped": int(m["gripped"]),
        }
