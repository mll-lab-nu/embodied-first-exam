"""Insert-tube task: the test tube out of its rack and into the inclined slot bore.

A :class:`~tactilelab_tasks.rigid.task.RigidAssemblyTask` (grasp accessors, insertion
geometry, tactile rig) with the seating judge: the tube was grasped this episode, its
tip is at least ``bore - assembled_margin`` (4 cm) into the slot bore, within
``assembled_lateral`` of the bore axis and ``assembled_axis_deg`` of its direction,
and the hand has opened (``jaw_open_width``) and moved ``release_clear`` away.
``extract_geometry()`` gives the same geometry against the rack bore for the
extraction stage of the policy.
"""

from __future__ import annotations

from typing import Any, Dict

import numpy as np

from ...assets.resolve import annotation_file
from ...core.types import GRIPPER_WIDTH_OFFSET
from ...rigid import geometry as G
from ...rigid.task import RigidAssemblyTask

__all__ = ["Task", "SeatedInsertTask"]


class SeatedInsertTask(RigidAssemblyTask):
    """Assembly task with a seating success gate (seat depth + released and clear)."""

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
        self.release_clear = float(s.get("release_clear", 0.15))
        self.jaw_open_width = float(s.get("jaw_open_width", 0.09))
        self.drop_z = float(s.get("drop_z", 0.95))
        self.carry_lost = float(s.get("carry_lost", 0.45))
        self.target_move = float(s.get("target_move", 0.05))
        ex = cfg.get("extract")
        self.extract_slot = None
        self.extract_target = None
        if ex:
            self.extract_target = str(ex["target"])
            self.extract_slot = G.load_slot(
                annotation_file(self._usd_of[self.extract_target], "insertion_pose"), str(ex.get("slot", "hole"))
            )
        self._target_reset_xy = None
        self._last_flags: Dict[str, Any] = {}

    # ------------------------------------------------------------------ accessors
    def gripper_width(self) -> float:
        q = self.scene.robot.joint_pos()[12:14]
        return float(GRIPPER_WIDTH_OFFSET + q[0] - q[1])

    def extract_geometry(self) -> Dict[str, Any]:
        """Insertion geometry of the held part against the rack bore (extraction stage)."""
        if self.extract_slot is None:
            raise RuntimeError("no extract block in the configuration")
        return G.insertion_world(
            self.held_pose(), self.held_axis(), self.object_pose(self.extract_target), self.extract_slot
        )

    # ------------------------------------------------------------------ judge
    def _reset_scene(self, seed: int) -> None:
        super()._reset_scene(seed)
        self._target_reset_xy = self.target_pose()[:2].copy()
        self._last_flags = {}

    def success_predicate(self) -> bool:
        st = self._part_state(0)
        eef = self.eef_pose()
        held = self.held_pose()
        dist = float(np.linalg.norm(eef[:3] - held[:3]))
        lifted = float(held[2]) - float(self._held_reset_z[0]) > self.grasp_lift_thresh
        if lifted and dist < self.grasp_hold_thresh:
            self._ever_grasped = True
        in_bore = st["lateral"] <= self.assembled_lateral and st["axis_err_deg"] <= self.assembled_axis_deg
        deep = st["depth"] >= st["bore"] - self.assembled_margin
        seated = bool(in_bore and deep)
        released_clear = dist > self.release_clear and self.gripper_width() > self.jaw_open_width
        moved = (
            float(np.linalg.norm(self.target_pose()[:2] - self._target_reset_xy)) > self.target_move
            if self._target_reset_xy is not None
            else False
        )
        self._last_metrics = st
        self._last_flags = {
            "seated": seated,
            "released_clear": bool(released_clear),
            "dist_eef_held": dist,
            "ever_grasped": bool(self._ever_grasped),
            "held_dropped": bool(
                (not seated) and (float(held[2]) < self.drop_z or (self._ever_grasped and dist > self.carry_lost))
            ),
            "target_moved": bool(moved),
        }
        self._parts_deep[0] = self._parts_deep[0] or seated
        return bool((self._ever_grasped or not self.require_grasp_latch) and seated and released_clear)

    def privileged_obs(self) -> Dict[str, np.ndarray]:
        out = super().privileged_obs()
        geo = self.geometry(0)
        out["insert_tip_w"] = np.asarray(geo["tip_w"], dtype=np.float32)
        out["insert_top_w"] = np.asarray(geo["top_w"], dtype=np.float32)
        out["insert_n_w"] = np.asarray(geo["n_w"], dtype=np.float32)
        out["insert_axis_w"] = np.asarray(geo["axis_w"], dtype=np.float32)
        out["insert_bore"] = np.float32(geo["depth"])
        out["gripper_width"] = np.float32(self.gripper_width())
        if self.extract_slot is not None:
            g = self.extract_geometry()
            d, lat, _ = G.signed_depth_lateral(g["tip_w"], g["top_w"], g["n_w"])
            out["extract_depth"] = np.float32(d)
            out["extract_lateral"] = np.float32(lat)
            out["extract_top_w"] = np.asarray(g["top_w"], dtype=np.float32)
            out["extract_n_w"] = np.asarray(g["n_w"], dtype=np.float32)
        return out

    def metrics(self) -> Dict[str, Any]:
        d = super().metrics()
        d.update(self._last_flags)
        d["gripper_width"] = self.gripper_width()
        return d


class Task(SeatedInsertTask):
    """Insert-tube on the X-Trainer (see the module docstring)."""

    name = "insert_tube"
