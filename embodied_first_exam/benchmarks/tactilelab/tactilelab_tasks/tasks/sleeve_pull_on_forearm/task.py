"""sleeve_pull_on_forearm: the right hand pulls a short sleeve (cloth tube) along the posed left forearm.

Scene (env frame): the left arm is posed with its forearm horizontal (``scene.left_arm_q0``); the forearm link ``J2_3``
is mirrored into the soft world as a kinematic cylinder (collider ``forearm``).  The sleeve starts pre-donned: a cloth
tube of radius ``sleeve_radius`` around the forearm, its cuff ring at axis coordinate ``cuff_start`` and its far ring
``sleeve_length`` behind it.  The cuff carries a stiff funnel-shaped collar (``flare``) and a pull tab (``tab``), a strip
of cloth standing up from the rim, which the gel pads pinch across its faces; the hand pulls the sleeve along the forearm
to the target band and lets go.

Axis coordinate ``t``: along the forearm collider's +z, 0 at the collider centre; ``pull_sign`` is the pull direction.

Success (``success_predicate``, held ``success.hold`` ticks):

* cuff in the target band: the mean axis coordinate of the cuff ring is within ``band_tol`` of ``cuff_target``;
* coverage: the ring spacing stays within ``bunch_tol`` of nominal (the sleeve is spread, not bunched);
* no cloth through the arm: every particle stays at least ``forearm_radius - pen_tol`` from the axis;
* released and at rest: the pads touched the sleeve once, now touch nothing, the gripper is open by ``open_gap`` and the
  fastest particle moves slower than ``rest_speed``.

Truncated: the state is not finite, the sleeve left the work volume, or it was pushed through a gel pad.
"""

from __future__ import annotations

from typing import Any, Dict, List

import numpy as np

from ...core.types import CONTROL_DT
from ...soft import metrics as M
from ...soft.base import SoftTask, _deep_merge
from ...softbody_geom import spec
from ...softbody_geom.soft_scenes import FOREARM_COLLIDER, GSMINI_COLLIDERS

__all__ = ["SleevePullOnForearmTask", "SLEEVE_PINCH", "SUCCESS_DEFAULTS", "CLOTH_COLOR"]

CLOTH_COLOR = (0.25, 0.60, 0.35)

SLEEVE_PINCH: Dict[str, Any] = {
    "forearm_radius": 0.040,
    "sleeve_radius": 0.05,  # a snug sleeve (10 mm clearance) with a wide stiff collar at the cuff
    "sleeve_length": 0.09,
    "n_around": 20,
    "n_len": 8,
    "cuff_start": 0.02,  # axis coordinate of the cuff ring at the start
    "pull_sign": 1.0,  # +1: the cuff leads toward increasing t (toward the left wrist)
    "cuff_target": 0.075,
    "flare": {"rings": 4, "radius": 0.085, "ramp": True},  # funnel mouth: a conical collar the tilted pads can reach
    "tab": {"height": 0.05, "rows": 4, "columns": 3, "orient": "ring"},  # pull tab standing up from the funnel rim
    "pinch_tilt_deg": 25.0,  # hand tilt from the vertical; the tab leans back by the same angle
    "density": 0.30,
    "tri_ke": 1.0e4,
    "tri_ka": 1.0e4,
    "tri_kd": 1.0e-1,
    "edge_ke": 100.0,
    "edge_kd": 1.0e-3,
    "contact": {"ke": 1.0e4, "kd": 1.0e1, "mu": 0.5},
    "radius": 0.0036,
}

SUCCESS_DEFAULTS: Dict[str, Any] = {
    "hold": 30,
    "band_tol": 0.030,
    "pen_tol": 0.004,
    "bunch_tol": 0.5,
    "open_gap": 0.05,
    "rest_speed": 0.01,
    "min_contacts": 1,
}


class SleevePullOnForearmTask(SoftTask):
    name = "sleeve_pull_on_forearm"

    def __init__(self, cfg: Dict[str, Any], **kw):
        super().__init__(cfg, **kw)
        self.g = _deep_merge(SLEEVE_PINCH, cfg.get("world", {}))
        self.s = _deep_merge(SUCCESS_DEFAULTS, cfg.get("success", {}))
        self.n_a, self.n_l = int(self.g["n_around"]), int(self.g["n_len"])
        names = [c.name for c in self.colliders]
        self.forearm_slot = names.index("forearm")
        self._m: Dict[str, Any] = {}

    def collider_cfgs(self, soft: Dict[str, Any]) -> List[Dict[str, Any]]:
        """The gripper boxes with the forearm cylinder inserted after the two gel pads."""
        if soft.get("colliders"):
            return [dict(c) for c in soft["colliders"]]
        out = [dict(d) for d in GSMINI_COLLIDERS]
        for d in out[:2]:
            if soft.get("pad_mu") is not None:
                d["mu"] = float(soft["pad_mu"])
        out.insert(2, dict(FOREARM_COLLIDER))
        return out

    # ------------------------------------------------------------------ geometry
    def forearm_frame(self):
        """``(centre, unit axis)`` of the forearm cylinder in the env frame (the collider's current pose)."""
        p = np.asarray(self.pads[self.forearm_slot], dtype=np.float64)
        return p[:3], spec.quat_to_mat(p[3:7])[:, 2]

    @property
    def pinch_tilt_deg(self) -> float:
        return float(self.g["pinch_tilt_deg"])

    def tube_cfg(self) -> Dict[str, Any]:
        c, ax = self.forearm_frame()
        L = float(self.g["sleeve_length"])
        sign = float(self.g["pull_sign"])
        s_center = float(self.g["cuff_start"]) - 0.5 * L * sign
        end = "last" if sign > 0 else "first"
        t: Dict[str, Any] = {
            "center": [round(float(v), 5) for v in c + s_center * ax],
            "axis": [round(float(v), 5) for v in ax],
            "radius": float(self.g["sleeve_radius"]),
            "length": L,
            "n_around": self.n_a,
            "n_len": self.n_l,
        }
        if self.g.get("flare"):
            t["flare"] = dict(self.g["flare"], end=end)
        if self.g.get("tab"):
            a = np.radians(self.pinch_tilt_deg)
            t["tab"] = dict(self.g["tab"], end=end, up=[-float(np.sin(a)), 0.0, float(np.cos(a))])
        return t

    def build_world(self) -> Dict[str, Any]:
        g = self.g
        cn = g["contact"]
        return {
            "table": {"z": self.table_z, "half": [1.0, 1.0], "center": [0.0, 0.0], "mu": 0.7},
            "soft_contact": {"ke": float(cn["ke"]), "kd": float(cn["kd"]), "mu": float(cn["mu"]), "gap": 0.005},
            "cloth": {
                "tube": self.tube_cfg(),
                "radius": float(g["radius"]),
                "density": float(g["density"]),
                "tri_ke": float(g["tri_ke"]),
                "tri_ka": float(g["tri_ka"]),
                "tri_kd": float(g["tri_kd"]),
                "edge_ke": float(g["edge_ke"]),
                "edge_kd": float(g["edge_kd"]),
                "self_contact": True,
                "color": list(CLOTH_COLOR),
            },
        }

    def ring_ids(self, j: int) -> np.ndarray:
        return np.arange(self.n_a) + j * self.n_a

    @property
    def cuff_ring(self) -> int:
        return self.n_l if float(self.g["pull_sign"]) > 0 else 0

    # ------------------------------------------------------------------ episode
    def on_reset(self, state: Dict[str, np.ndarray]) -> None:
        self._m = {
            "released": False,
            "gripped": False,
            "contacts": np.zeros(2, dtype=np.int64),
            "speed": 0.0,
            "prev": None,
            "cuff_t": float("nan"),
            "band_err": float("nan"),
            "pen": 0.0,
            "bunch": 0.0,
            "elev_deg": float("nan"),
        }

    def update_metrics(self, state: Dict[str, np.ndarray], pads: np.ndarray) -> None:
        m = self._m
        if not m:
            return
        q = np.asarray(state["particle_q"], dtype=np.float64)
        if not np.isfinite(q).all():
            self.truncation_reason = self.truncation_reason or "cloth state is not finite"
            return
        g = self.g
        c, ax = self.forearm_frame()
        m["elev_deg"] = float(np.degrees(np.arcsin(np.clip(ax[2], -1.0, 1.0))))
        t = (q - c[None]) @ ax
        radial = np.linalg.norm((q - c[None]) - t[:, None] * ax[None], axis=1)
        m["cuff_t"] = float(t[self.ring_ids(self.cuff_ring)].mean())
        m["band_err"] = abs(m["cuff_t"] - float(g["cuff_target"]))
        m["pen"] = float(max(float(g["forearm_radius"]) - radial.min(), 0.0))
        ring_t = np.array([t[self.ring_ids(j)].mean() for j in range(self.n_l + 1)])
        spacing = np.abs(np.diff(ring_t))
        nominal = float(g["sleeve_length"]) / self.n_l
        m["bunch"] = float(np.abs(spacing / nominal - 1.0).max())
        if m["prev"] is not None:
            m["speed"] = float(np.abs(q - m["prev"]).max() / CONTROL_DT)
        m["prev"] = q.copy()
        pads2 = np.asarray(pads, dtype=np.float64)[:2]
        gap = float(np.linalg.norm(pads2[0, :3] - pads2[1, :3]))
        m["contacts"] = M.contact_counts(M.cloth_samples(q, self.tris), float(g["radius"]), pads2, self.pad_halves)
        if np.all(m["contacts"] >= int(self.s["min_contacts"])):
            m["gripped"] = True
        if m["gripped"] and int(m["contacts"].sum()) == 0 and gap >= float(self.s["open_gap"]):
            m["released"] = True

    def success_predicate(self) -> bool:
        m = self._m
        if not m or self.settling or not np.isfinite(m["cuff_t"]) or "particle_q" not in self.state:
            return False
        q = np.asarray(self.state["particle_q"])
        reason = None
        if not np.isfinite(q).all():
            reason = "cloth state is not finite"
        elif q[:, 2].min() < self.table_z - 0.05 or np.abs(q[:, :2]).max() > 1.2:
            reason = "the sleeve left the work volume"
        if reason is not None:
            self.truncation_reason = self.truncation_reason or reason
            return False
        return bool(
            m["released"]
            and m["band_err"] <= float(self.s["band_tol"])
            and m["pen"] <= float(self.s["pen_tol"])
            and m["bunch"] <= float(self.s["bunch_tol"])
            and m["speed"] <= float(self.s["rest_speed"])
        )

    def task_obs(self) -> Dict[str, np.ndarray]:
        m = self._m
        if not m:
            return {}
        return {
            "cuff_t": np.array([m["cuff_t"]], dtype=np.float32),
            "band_err": np.array([m["band_err"]], dtype=np.float32),
            "pen": np.array([m["pen"]], dtype=np.float32),
            "bunch": np.array([m["bunch"]], dtype=np.float32),
            "released": np.array([float(m["released"])], dtype=np.float32),
            "pad_contacts": np.asarray(m["contacts"], dtype=np.float32),
            "speed": np.array([m["speed"]], dtype=np.float32),
            "forearm_elev_deg": np.array([m["elev_deg"]], dtype=np.float32),
        }

    def task_metrics(self) -> Dict[str, float]:
        m = self._m
        if not m:
            return {}
        return {
            "cuff_t_mm": 1e3 * m["cuff_t"],
            "band_err_mm": 1e3 * m["band_err"],
            "pen_mm": 1e3 * m["pen"],
            "bunch": m["bunch"],
            "speed_mm_s": 1e3 * m["speed"],
            "released": int(m["released"]),
            "gripped": int(m["gripped"]),
            "forearm_elev_deg": m["elev_deg"],
        }

    # ------------------------------------------------------------------ helpers for the policy
    def rim_grip_point(self) -> np.ndarray:
        """Where the hand takes the sleeve: the centre of the pull tab's top row (its last vertices)."""
        q = np.asarray(self.state["particle_q"], dtype=np.float64)
        if self.g.get("tab"):
            return q[-int(self.g["tab"].get("columns", 3)) :].mean(axis=0)
        ids = self.ring_ids(self.cuff_ring)
        return q[ids[int(np.argmax(q[ids, 2]))]]

    def cuff_remaining(self) -> float:
        """How far the cuff still has to travel along the pull direction to reach the target [m] (negative: past it)."""
        return float(self.g["pull_sign"]) * (float(self.g["cuff_target"]) - self._m["cuff_t"])

    def pull_direction(self) -> np.ndarray:
        _, ax = self.forearm_frame()
        return float(self.g["pull_sign"]) * ax
