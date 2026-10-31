"""Scripted handover policy (bimanual).

Plan, built at reset from the live wrist, pad-centre and rod poses (the left arm holds
its start pose as the explicit second target of every arm move):

``right_hold`` (right jaws close on the rod) -> ``right_hold_settle`` -> ``align``
(rod axis through the left jaws, still short of the fingers) -> ``insert`` (rod end
between the open left jaws) -> up to ``refine_tries`` corrective moves while the rod
centre is more than ``refine_tol`` from its wanted spot -> ``settle_before_close`` ->
``left_close`` -> ``settle_after_close`` -> ``right_open`` -> ``settle_after_open`` ->
``retract`` (right arm backs away along -x) -> ``rest``.

Every arm move is a Cartesian interpolation with fixed limits (60 ticks,
0.10 m/s, converge to 4 mm / 0.06, timeout 400).
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

import numpy as np

from ...core.policy import Gripper, Hold, MoveL, PhaseBase, PhasedPolicy, ee_pose
from .._common import TCP_OFFSET, tcp_of_wrist

__all__ = ["Policy", "OptionalMoveL"]


class OptionalMoveL(MoveL):
    """A :class:`MoveL` whose callable target may return ``None`` to skip the move."""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._skipped = False

    def start(self, obs, info) -> None:
        spec = self.target_spec(obs, info) if callable(self.target_spec) else self.target_spec
        if spec is None:
            self._skipped = True
            self._done_reason = "skipped"
            return
        self._skipped = False
        saved = self.target_spec
        self.target_spec = spec
        try:
            super().start(obs, info)
        finally:
            self.target_spec = saved

    def done(self, obs, info) -> bool:
        if self._skipped:
            return True
        return super().done(obs, info)


class Policy(PhasedPolicy):
    """Fixed-pose handover expert (see the module docstring)."""

    def __init__(self, cfg: Dict[str, Any], task=None, verbose: bool = True, planner=None):
        super().__init__(phases=None, cfg=cfg, verbose=verbose)
        self.task = task
        self.planner = planner  # unused: every move is a Cartesian interpolation
        self.p = dict(self.cfg.get("policy") or {})
        ho = self.cfg.get("handover", {})
        self.rod_key = f"object_pose/{ho.get('rod', 'rod')}"
        self.tcp_offset = float(ho.get("tcp_offset", TCP_OFFSET))
        self._left_hold: Optional[np.ndarray] = None

    # -- live measurements
    def _live(self, obs):
        wrist_r = ee_pose(obs, 0)
        wrist_l = ee_pose(obs, 1)
        tcp_l = tcp_of_wrist(wrist_l, self.tcp_offset)
        rod_c = np.asarray(obs["privileged"][self.rod_key], dtype=np.float64)[:3]
        return wrist_r, wrist_l, tcp_l, rod_c

    def _wanted_rod_centre(self, tcp_l: np.ndarray) -> np.ndarray:
        return np.array([tcp_l[0] - float(self.p.get("hold_offset", 0.03)), tcp_l[1], tcp_l[2]])

    def _log(self, msg: str) -> None:
        if self.verbose:
            print(f"[handover] {msg}", flush=True)

    # -- phase builders
    def _both(self, name: str, right_target, cls=MoveL) -> MoveL:
        mv = self.p.get("move", {})

        def target(obs, info):
            r = right_target(obs, info) if callable(right_target) else right_target
            if r is None:
                return None
            return {0: np.asarray(r, dtype=np.float64), 1: self._left_hold}

        return cls(
            target,
            "both",
            steps=int(mv.get("interp_steps", 60)),
            speed=float(mv.get("speed", 0.10)),
            converge=True,
            tol=(float(mv.get("translation_tol", 0.004)), float(mv.get("rotation_tol", 0.06))),
            timeout=int(mv.get("timeout", 400)),
            name=name,
        )

    def _gripper(self, command: str, arm: str, name: str) -> Gripper:
        g = self.p.get("gripper", {})
        return Gripper(
            command,
            arm,
            timeout=int(g.get("timeout", 30)),
            settle_threshold=float(g.get("settle_threshold", 1e-3)),
            name=name,
        )

    def _refine(self, k: int):
        tol = float(self.p.get("refine_tol", 0.004))

        def target(obs, info):
            wrist_r, _, tcp_l, rod_c = self._live(obs)
            err = self._wanted_rod_centre(tcp_l) - rod_c
            self._log(f"refine_{k}: insert error {np.round(err, 4).tolist()} m")
            if float(np.linalg.norm(err)) < tol:
                return None
            w = wrist_r.copy()
            w[:3] += err
            return w

        return self._both(f"refine_{k}", target, cls=OptionalMoveL)

    def build_phases(self, obs, info) -> List[PhaseBase]:
        wrist_r, wrist_l, tcp_l, rod_c = self._live(obs)
        self._left_hold = wrist_l.copy()
        delta = self._wanted_rod_centre(tcp_l) - rod_c
        pre = delta.copy()
        pre[0] -= float(self.p.get("pre_insert_dist", 0.10))
        w_align = wrist_r.copy()
        w_align[:3] += pre
        w_insert = wrist_r.copy()
        w_insert[:3] += delta
        retract = float(self.p.get("retract_dist", 0.20))
        settle = int(self.p.get("settle_ticks", 20))
        self._log(
            f"rod {np.round(rod_c, 3).tolist()} -> centre {np.round(self._wanted_rod_centre(tcp_l), 3).tolist()}, left tcp {np.round(tcp_l, 3).tolist()}"
        )

        def retract_target(obs_, info_):
            w = ee_pose(obs_, 0).copy()
            w[0] -= retract
            return w

        phases: List[PhaseBase] = [
            self._gripper("close", "right", "right_hold"),
            Hold(settle, name="right_hold_settle"),
            self._both("align", w_align),
            self._both("insert", w_insert),
        ]
        phases += [self._refine(k + 1) for k in range(int(self.p.get("refine_tries", 3)))]
        phases += [
            Hold(settle, name="settle_before_close"),
            self._gripper("close", "left", "left_close"),
            Hold(settle, name="settle_after_close"),
            self._gripper("open", "right", "right_open"),
            Hold(max(1, settle // 2), name="settle_after_open"),
            self._both("retract", retract_target),
            Hold(int(self.p.get("rest_ticks", 15)), name="rest"),
        ]
        return phases
