"""cable_slack_reduce scripted policy: pinch the free end of the slack cable and pull it away from the clamp until taut.

    open -> above the grip point -> descend -> close (calibrated pinch) -> settle -> pull along the fixed-end -> grip direction
    -> hold -> verdict

The pull length is computed from the live cable: the chord that leaves ``slack_target`` of slack between the clamp and the
gripped point, plus ``overpull`` x the target.
"""

from __future__ import annotations

from typing import Any, Dict, List

import numpy as np

from ...soft import cables
from ...soft.plan import INTERP, MOTIONGEN, Step, StepPolicy


class Policy(StepPolicy):
    """Step plan of the slack-reduction task (numbers in ``cfg["policy"]``)."""

    def __init__(self, cfg: Dict[str, Any], task=None, planner=None, verbose: bool = False):
        if not isinstance(cfg, dict):  # (task, cfg) order
            cfg, task = task, cfg
        super().__init__(task, cfg, planner=planner, verbose=verbose)
        p = self.p
        self.back = float(p.get("grip_back", 0.006))
        self.hover = float(p.get("hover", 0.07))
        self.grip_dz = float(p.get("grip_dz", 0.021))
        self.overpull = float(p.get("overpull", 1.0))

    def attach(self, task) -> None:
        """Bind the policy to its task (for runners that build the policy before the task)."""
        self.task = task

    def build_plan(self) -> List[Step]:
        task = self.task
        nodes = task.nodes()
        p, d = cables.point_before_end(nodes, self.back)
        fixed = nodes[0]
        s_grip = float(cables.edge_arclength(nodes)[-1] - self.back)
        away = p - fixed
        away[2] = 0.0
        chord = float(np.linalg.norm(away))
        away /= max(chord, 1e-9)
        slack_target = float(task.g["slack_target"])
        target_chord = s_grip / (1.0 + 0.5 * slack_target)
        pull = max(target_chord - chord, 0.0) + self.overpull * slack_target * s_grip
        n = np.array([-d[1], d[0], 0.0])  # closing axis: horizontal, across the cable
        R = self.R_pinch(approach=(0.0, 0.0, -1.0), normal=n)
        z_g = task.table_z + self.grip_dz
        p_up = np.array([p[0], p[1], z_g + self.hover])
        p_dn = np.array([p[0], p[1], z_g])
        p_end = np.array([p[0] + away[0] * pull, p[1] + away[1] * pull, z_g + 0.004])
        self._log(
            f"grip {np.round(p, 3).tolist()} chord {chord:.3f} s_grip {s_grip:.3f}: pull {pull:.3f} m along {np.round(away[:2], 2).tolist()}"
        )
        return [
            self.step_hand("open", "open"),
            self.step_move("above", MOTIONGEN, lambda: p_up, lambda: R, post_idle=5),
            self.step_move("descend", INTERP, lambda: p_dn, lambda: R, post_idle=5),
            self.step_hand("pinch", "close"),
            self.step_wait("settle_pinch", 15),
            self.step_move("pull", INTERP, lambda: p_end, lambda: R),
            self.step_wait("hold", 20),
            self.verdict_step(),
        ]


__all__ = ["Policy"]
