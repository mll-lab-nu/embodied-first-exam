"""cable_slack_reduce: pull a slack cable taut between a clamp and the gripper (see cfg.yaml).

The first segments of the cable are pinned under a clamp bar; the free part lies on the plate in a bump and its straight tail
rests on a thin notched ridge at the gel-pad height.  Success (``success_predicate``): the pads have pinched the cable, the
slack (path length / chord - 1) between the clamp and the gripped material point is at most ``slack_target``, the pinch has not
slipped along the cable by more than ``slip_max``, the cable has not stretched beyond ``stretch_max`` and the pinch was not lost;
held for ``success.hold`` ticks.  Truncated when the cable leaves the plate, the pinch is lost for ``lost_max`` ticks or a gel
pad cuts into the ridge.
"""

from __future__ import annotations

from typing import Any, Dict, Optional

import numpy as np

from ...soft import cables
from ...soft.base import SoftTask
from ...softbody_geom import spec


class Task(SoftTask):
    """Slack-reduction task on the ``softbody.world`` cable rod."""

    name = "cable_slack_reduce"
    success_hold = 20

    def __init__(self, cfg: Dict[str, Any], **kw):
        super().__init__(cfg, **kw)
        self.g = spec.merge_dicts(cables.SLACK, dict(cfg.get("world", {})))
        self.geo = cables.SlackScene(self.g, self.table_z)
        self.tracker: Optional[cables.SlackTracker] = None
        self._init_checked = False

    # ------------------------------------------------------------------ scene
    def fixtures(self):
        return [dict(fx, physics=True, friction=0.5) for fx in self.geo.fixtures()]

    def initial_state(self) -> Dict[str, Any]:
        self.tracker = self.geo.tracker()
        self._init_checked = False
        return {"cable_points": self.geo.initial_cable()}

    def build_world(self) -> Dict[str, Any]:
        return self.geo.world_block()

    # ------------------------------------------------------------------ what the policy reads
    def nodes(self) -> np.ndarray:
        return np.asarray(self.state["cable_nodes"], dtype=np.float64)

    def free_end_grip(self, back: float = 0.02):
        """A point ``back`` metres of cable before the free end and the horizontal cable direction there."""
        return cables.point_before_end(self.nodes(), back)

    def fixed_end(self) -> np.ndarray:
        return self.geo.fixed_end(self.nodes())

    # ------------------------------------------------------------------ metrics / success
    def update_metrics(self, state: Dict[str, np.ndarray], pads: np.ndarray) -> None:
        if self.tracker is not None:
            self.tracker.update(np.asarray(state["cable_nodes"], dtype=np.float64), pads, settling=self.settling)

    def success_predicate(self) -> bool:
        if self.tracker is None or not self.state:
            return False
        nodes = self.nodes()
        if not self.settling and not self._init_checked:
            # the settled free end must rest on the ridge (pad-centre height), else there is nothing for the pads to pinch
            self._init_checked = True
            z_end = float(nodes[-1, 2]) - self.table_z
            if z_end < 0.7 * (float(self.g["ridge_h"]) + float(self.g["radius"])) and self.truncation_reason is None:
                self.truncation_reason = f"the free end is off the ridge after the settle (z {z_end * 1e3:.1f} mm)"
        ok, reason = self.tracker.judge(nodes)
        if reason and self.truncation_reason is None:
            self.truncation_reason = reason
        return bool(ok)

    def task_obs(self) -> Dict[str, np.ndarray]:
        d = self.tracker.as_dict() if self.tracker is not None else {}
        return {
            "slack": np.array([d.get("slack", np.nan)], dtype=np.float32),
            "sag": np.array([d.get("sag", np.nan)], dtype=np.float32),
            "slip": np.array([d.get("slip", 0.0)], dtype=np.float32),
            "stretch": np.array([d.get("stretch", 1.0)], dtype=np.float32),
            "pinched": np.array([float(d.get("pinched", False))], dtype=np.float32),
            "pad_fixture_overlap": np.array([d.get("pad_fixture_overlap", -1.0)], dtype=np.float32),
        }

    def task_metrics(self) -> Dict[str, Any]:
        d = self.tracker.as_dict() if self.tracker is not None else {}
        return {k: (v.tolist() if isinstance(v, np.ndarray) else v) for k, v in d.items() if k != "lost"}


__all__ = ["Task"]
