"""Lift task: a lying bottle is grasped, reoriented upright and placed on a pad.

Scene (``cfg.yaml``): the bottle lies along +y with its base in a U-cradle, the place
pad is a 0.2 m board on the worktop. Success: the bottle origin is within ``xy`` /
``z`` of the place target and the right gripper has released, held ``success_hold``
ticks (judged with the arm frozen at the finish). The hand rising above
``eef_z_max`` or the bottle leaving the table truncates the episode.
"""

from __future__ import annotations

import json
from typing import Any, Dict

import numpy as np

from ...assets.resolve import annotation_file
from ...core.types import TABLE_TOP_Z
from .._common import RigidTask


def _object_entry(cfg: Dict[str, Any], name: str) -> Dict[str, Any]:
    return next(o for o in cfg["scene"]["objects"] if o["name"] == name)


def bottom_center(cfg: Dict[str, Any]) -> np.ndarray:
    """Object-frame contact point of the bottle base (``grasp_pose.json: bottom_center``)."""
    usd = _object_entry(cfg, cfg["lift"]["bottle"])["usd"]
    with open(annotation_file(usd, "grasp_pose"), "r", encoding="utf-8") as fh:
        ann = json.load(fh)
    return np.asarray(ann.get("bottom_center", [0.0, 0.0, 0.0]), dtype=np.float64)


def place_target_position(cfg: Dict[str, Any]) -> np.ndarray:
    """Env-frame position of the bottle origin when it stands upright on the pad centre.

    The contact face (``bottom_center``) sits ``release_clearance`` above the pad's top
    face with the bottle axis pointing up.
    """
    pad = _object_entry(cfg, cfg["lift"]["pad"])
    top_z = float(pad["pos"][2]) + 0.5 * float(pad["dims"][2])
    clearance = float(cfg["lift"].get("release_clearance", 0.005))
    return np.array([float(pad["pos"][0]), float(pad["pos"][1]), top_z + clearance - float(bottom_center(cfg)[2])])


def axis_up(quat: np.ndarray) -> float:
    """Cosine between the object's local +z axis and world up."""
    q = np.asarray(quat, dtype=np.float64)
    return float(1.0 - 2.0 * (q[1] * q[1] + q[2] * q[2]))


class Task(RigidTask):
    """Grasp - lift - reorient - place (see the module docstring)."""

    name = "lift"
    success_hold = 20

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
        suc = cfg.get("success", {})
        self.xy_thresh = float(suc.get("xy", 0.10))
        self.z_thresh = float(suc.get("z", 0.06))
        self.jaw_open_width = float(suc.get("jaw_open_width", 0.09))
        self.eef_away = float(suc.get("eef_away", 0.0))
        self.eef_z_max = float(suc.get("eef_z_max", 0.0))
        self.drop_below_table = float(suc.get("drop_below_table", 0.3))
        self.bottle = str(cfg["lift"]["bottle"])
        self.pad = str(cfg["lift"]["pad"])
        self.place_target = place_target_position(cfg)
        self.bottom_center = bottom_center(cfg)

    # ------------------------------------------------------------------ judge
    def _place_errors(self):
        pose = self.object_pose(self.bottle)
        xy = float(np.linalg.norm(pose[:2] - self.place_target[:2]))
        dz = float(pose[2] - self.place_target[2])
        eef = self.eef_pose(0)
        dist = float(np.linalg.norm(eef[:3] - pose[:3]))
        return pose, xy, dz, dist, eef

    def success_predicate(self) -> bool:
        pose, xy, dz, dist, eef = self._place_errors()
        if self.eef_z_max > 0.0 and float(eef[2]) > self.eef_z_max:
            self._truncate("eef above z_max")
        if float(pose[2]) < TABLE_TOP_Z - self.drop_below_table:
            self._truncate("bottle dropped")
        on_pad = xy < self.xy_thresh and abs(dz) < self.z_thresh
        released = self.jaw_open(0, self.jaw_open_width)
        away = dist > self.eef_away if self.eef_away > 0.0 else True
        return bool(on_pad and released and away)

    def task_privileged(self) -> Dict[str, np.ndarray]:
        pose, xy, dz, dist, eef = self._place_errors()
        return {
            "lift/axis_up": np.float32(axis_up(pose[3:7])),
            "lift/place_err_xy": np.float32(xy),
            "lift/place_err_z": np.float32(dz),
            "lift/eef_dist": np.float32(dist),
            "lift/place_target": self.place_target.astype(np.float32),
            "lift/gripper_width": np.float32(self.gripper_width(0)),
        }

    def metrics(self) -> Dict[str, Any]:
        d = super().metrics()
        pose, xy, dz, dist, eef = self._place_errors()
        d.update(
            {
                "axis_up": axis_up(pose[3:7]),
                "place_err_xy_mm": 1e3 * xy,
                "place_err_z_mm": 1e3 * dz,
                "eef_dist": dist,
                "eef_z": float(eef[2]),
                "gripper_width": self.gripper_width(0),
            }
        )
        return d


__all__ = ["Task", "place_target_position", "bottom_center", "axis_up"]
