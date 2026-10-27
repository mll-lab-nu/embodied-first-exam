"""Drawer-container task: two containers slide into the drawer box's rail pairs.

A :class:`~tactilelab_tasks.rigid.task.RigidAssemblyTask` over the two containers with the
drawer judge: a part latches once its slide depth is within
``assembled_margin`` of the rail length, its nose within ``assembled_lateral`` of the
rail axis, its axis within ``assembled_axis_deg`` and the depth has stopped moving
(less than ``settle_eps`` over ``settle_ticks``); success = all parts latched, the
active part was grasped this episode and the hand is ``assembled_clear`` from it
(0: the arm freezes at its last pose).
"""

from __future__ import annotations

from collections import deque
from typing import Any, Dict, List

import numpy as np

from ...rigid.task import RigidAssemblyTask

__all__ = ["Task"]


class Task(RigidAssemblyTask):
    """Drawer assembly on the X-Trainer (see the module docstring)."""

    name = "drawer_container"

    def __init__(
        self,
        cfg: Dict[str, Any],
        scene=None,
        obs_mode: str = "full",
        device: str = "cuda:0",
        cameras: bool = True,
        tactile: bool = True,
    ):
        super().__init__(cfg, scene, obs_mode, device=device, cameras=cameras, tactile=tactile)
        s = cfg.get("success", {})
        self.settle_window = int(s.get("settle_ticks", 30))
        self.settle_eps = float(s.get("settle_eps", 0.0005))
        self._hist: List[deque] = [deque(maxlen=self.settle_window) for _ in self.parts]
        self._part_states: List[Dict[str, float]] = [{} for _ in self.parts]

    def _reset_scene(self, seed: int) -> None:
        super()._reset_scene(seed)
        for h in self._hist:
            h.clear()
        self._part_states = [{} for _ in self.parts]

    def _settled(self, k: int, depth: float) -> bool:
        h = self._hist[k]
        h.append(depth)
        return len(h) == self.settle_window and abs(h[-1] - h[0]) < self.settle_eps

    def success_predicate(self) -> bool:
        eef = self.eef_pose()
        for k in range(len(self.parts)):
            st = self._part_state(k)
            st["settled"] = float(self._settled(k, st["depth"]))
            in_bore = st["lateral"] <= self.assembled_lateral and st["axis_err_deg"] <= self.assembled_axis_deg
            deep = st["depth"] >= st["bore"] - self.assembled_margin
            if in_bore and deep and st["settled"] > 0.0:
                self._parts_deep[k] = True
            st["latched"] = float(self._parts_deep[k])
            self._part_states[k] = st
            if k == self.active:
                self._last_metrics = st
        held = self.held_pose()
        dist = float(np.linalg.norm(eef[:3] - held[:3]))
        lifted = float(held[2]) - float(self._held_reset_z[self.active]) > self.grasp_lift_thresh
        if lifted and dist < self.grasp_hold_thresh:
            self._ever_grasped = True
        clear = dist >= self.assembled_clear
        return bool(self._parts_deep.all() and (self._ever_grasped or not self.require_grasp_latch) and clear)

    def privileged_obs(self) -> Dict[str, np.ndarray]:
        out = super().privileged_obs()
        for k, st in enumerate(self._part_states):
            if st:
                out[f"part{k}_depth"] = np.float32(st["depth"])
                out[f"part{k}_lateral"] = np.float32(st["lateral"])
                out[f"part{k}_axis_err_deg"] = np.float32(st["axis_err_deg"])
                out[f"part{k}_settled"] = np.bool_(st["settled"] > 0.0)
        return out

    def metrics(self) -> Dict[str, Any]:
        d = super().metrics()
        for k, st in enumerate(self._part_states):
            if st:
                d[f"part{k}_depth_mm"] = 1e3 * st["depth"]
                d[f"part{k}_settled"] = bool(st["settled"] > 0.0)
        return d
