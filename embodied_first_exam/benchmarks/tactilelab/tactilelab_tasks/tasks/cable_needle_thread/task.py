"""cable_needle_thread: thread a cable through the hole of a wall (see cfg.yaml).

The cable lies in two open-top clips under the open hand.  A wall with a square hole stands ahead of the hand (its position
is fixed relative to the gel-pad midpoint at the reset).  Success (``success_predicate``): the cable polyline crosses the wall
mid-plane exactly once and inside the hole, its tip is ``pass_len`` beyond the far face and the cable has not stretched beyond
``stretch_max``; held for ``success.hold`` ticks.  The episode is truncated when the cable falls below the plate.
"""

from __future__ import annotations

from typing import Any, Dict, Optional, Sequence

import numpy as np

from ...core import math as m
from ...soft import cables
from ...soft.base import SoftTask
from ...softbody_geom import spec


class Task(SoftTask):
    """Needle-threading task on the ``softbody.world`` cable rod."""

    name = "cable_needle_thread"
    success_hold = 20

    def __init__(self, cfg: Dict[str, Any], **kw):
        super().__init__(cfg, **kw)
        self.g = spec.merge_dicts(cables.NEEDLE, dict(cfg.get("world", {})))
        self.geo = cables.NeedleScene(self.g, self.table_z)
        self._m: Optional[Dict[str, Any]] = None
        self._spheres: Optional[Dict[str, np.ndarray]] = None
        self.wrist_warning: Optional[str] = None

    # ------------------------------------------------------------------ scene
    def fixtures(self):
        return [dict(fx, physics=True, friction=0.4) for fx in self.geo.fixtures()]

    def initial_state(self) -> Dict[str, Any]:
        # the wall, the hole and the clips are placed relative to the pad midpoint of this reset
        self.geo = cables.NeedleScene(self.g, self.table_z, mid=self.pad_mid())
        self._m = None
        self._place_fixtures()
        self._check_wrist()
        return {"cable_points": self.geo.initial_cable()}

    def build_world(self) -> Dict[str, Any]:
        return self.geo.world_block()

    def _place_fixtures(self) -> None:
        """Move the Isaac copies of the fixtures to this episode's layout (they were spawned at the home layout)."""
        sc = self.scene
        if sc is None or not hasattr(sc, "set_object_pose") or not getattr(sc, "objects", None):
            return
        for fx in self.geo.fixtures():
            if fx["name"] in sc.objects:
                sc.set_object_pose(fx["name"], m.pose_from_pos_quat(fx["center"], (1.0, 0.0, 0.0, 0.0)))

    def _check_wrist(self) -> None:
        """Warn when the wrist camera housing faces the wall (the wrist should then start turned by pi)."""
        try:
            boxes = [fx for fx in self.geo.fixtures() if str(fx["name"]).startswith("wall")]
            facing = cables.housing_faces_fixture(self.hand_spheres(), self.hand_link_poses(), self.pad_mid(), boxes)
            self.wrist_warning = (
                "the wrist camera housing faces the wall: turn J1_6 by pi in scene.right_arm_q0" if facing else None
            )
        except Exception:  # noqa: BLE001 - a diagnostic never stops the task
            self.wrist_warning = None

    # ------------------------------------------------------------------ hand clearance
    def hand_spheres(self) -> Dict[str, np.ndarray]:
        if self._spheres is None:
            self._spheres = cables.load_hand_spheres()
        return self._spheres

    def hand_link_poses(self) -> Dict[str, np.ndarray]:
        """Env-frame xyzw poses of the hand links (wrist and the two fingers)."""
        return {link: spec.pose7_wxyz_to_xyzw(self.link_pose(link)) for link in cables.HAND_LINKS}

    def hand_front_at(
        self, mid_pos: Sequence[float], R_mid: np.ndarray, direction: Sequence[float], z_max: float = np.inf
    ) -> float:
        """How far the hand reaches past the pinch centre along ``direction`` with the pinch frame moved to ``(mid_pos, R_mid)``
        (spheres whose bottom is below ``z_max`` only, e.g. the top of the wall)."""
        c, R = self.mid_frame()
        poses = cables.link_poses_at(self.hand_link_poses(), c, R, mid_pos, R_mid)
        return cables.front_extent(self.hand_spheres(), poses, mid_pos, direction, z_max)

    # ------------------------------------------------------------------ what the policy reads
    @property
    def tip_len(self) -> float:
        return float(self.g["tip_len"])

    def nodes(self) -> np.ndarray:
        return np.asarray(self.state["cable_nodes"], dtype=np.float64)

    def tip(self) -> np.ndarray:
        return self.nodes()[-1]

    def grasp_point(self) -> np.ndarray:
        return self.geo.grasp_point(self.nodes())

    def hole_center(self) -> np.ndarray:
        return self.geo.hole_center

    def hole_size(self):
        return self.geo.hole_size()

    def wall_near_x(self) -> float:
        return self.geo.wall_near_x

    def wall_top_z(self) -> float:
        return self.geo.wall_top_z

    # ------------------------------------------------------------------ metrics / success
    def update_metrics(self, state: Dict[str, np.ndarray], pads: np.ndarray) -> None:
        self._m = self.geo.metrics(np.asarray(state["cable_nodes"], dtype=np.float64))

    def success_predicate(self) -> bool:
        if self._m is None or not self.state:
            return False
        ok, reason = self.geo.judge(self.nodes(), self._m)
        if reason and self.truncation_reason is None:
            self.truncation_reason = reason
        return bool(ok)

    def task_obs(self) -> Dict[str, np.ndarray]:
        mm = self._m or {}
        return {
            "pass": np.array([mm.get("pass", 0.0)], dtype=np.float32),
            "crossings": np.array([mm.get("crossings", 0)], dtype=np.float32),
            "inside": np.array([float(mm.get("inside", False))], dtype=np.float32),
            "stretch": np.array([mm.get("stretch", 1.0)], dtype=np.float32),
            "hole": self.geo.hole_center.astype(np.float32),
            "tip": np.asarray(mm.get("tip", np.zeros(3)), dtype=np.float32),
        }

    def task_metrics(self) -> Dict[str, float]:
        mm = self._m or {}
        out = {
            "pass": float(mm.get("pass", 0.0)),
            "crossings": int(mm.get("crossings", 0)),
            "inside": bool(mm.get("inside", False)),
            "stretch": float(mm.get("stretch", 1.0)),
        }
        if self.wrist_warning:
            out["wrist_warning"] = self.wrist_warning
        return out


__all__ = ["Task"]
