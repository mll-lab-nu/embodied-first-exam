"""Handover task: a rod passes from the right gripper to the left gripper.

The rod starts across the closed right pads as a weightless fixture; gravity is
switched on once the right jaws have been commanded closed for
``gravity_on_after_closed_ticks`` ticks. Success (every term held ``success_hold``
ticks):

* ``left_holds``: the left pad centre is on the rod axis and the left jaws are closed on
  the rod (gap within ``closed_gap_tol`` of the rod diameter);
* ``right_released``: the right jaws are open and the right pad centre is clear of the
  rod axis;
* ``unsupported``: the rod's lowest point is ``support_clearance`` above the table top;
* ``stable``: the rod is nearly at rest.

The rod coming down onto the table or leaving the workspace truncates the episode.
"""

from __future__ import annotations

from dataclasses import dataclass, fields
from typing import Any, Dict, Optional

import numpy as np

from ...core import math as m
from ...core.types import GRIPPER_CLOSE
from .._common import TCP_OFFSET, RigidTask, tcp_of_wrist

__all__ = ["Task", "HandoverParams", "handover_flags", "rod_axis", "point_to_axis_distance", "lowest_point_z"]


@dataclass(frozen=True)
class HandoverParams:
    rod_radius: float = 0.0125
    rod_length: float = 0.24
    table_top_z: float = 1.102
    support_clearance: float = 0.05
    hold_radius: float = 0.02
    closed_gap_tol: float = 0.012
    gap_offset: float = 0.0
    right_open_gap: float = 0.09
    right_away: float = 0.10
    max_speed: float = 0.03
    max_rate: float = 0.5

    @classmethod
    def from_cfg(cls, d: Dict[str, Any]) -> "HandoverParams":
        return cls(**{f.name: float(d[f.name]) for f in fields(cls) if f.name in d})


def rod_axis(quat: np.ndarray) -> np.ndarray:
    """World direction of the rod's local z axis."""
    return m.quat_rotate(quat, np.array([0.0, 0.0, 1.0]))


def point_to_axis_distance(p: np.ndarray, centre: np.ndarray, axis: np.ndarray, half_length: float) -> float:
    """Distance from ``p`` to the rod's axis segment."""
    d = np.asarray(p, dtype=np.float64) - centre
    t = float(np.clip(np.dot(d, axis), -half_length, half_length))
    return float(np.linalg.norm(d - t * axis))


def lowest_point_z(centre: np.ndarray, axis: np.ndarray, length: float, radius: float) -> float:
    """Height of the lowest point of the (cylinder-approximated) rod."""
    az = min(abs(float(axis[2])), 1.0)
    return float(centre[2] - 0.5 * length * az - radius * np.sqrt(max(1.0 - az * az, 0.0)))


def handover_flags(
    rod_pose, rod_lin_vel, rod_ang_vel, tcp_right, tcp_left, gap_right, gap_left, p: HandoverParams
) -> Dict[str, Any]:
    """The four success terms, their conjunction and the diagnostic distances."""
    rod_pose = np.asarray(rod_pose, dtype=np.float64)
    axis = rod_axis(rod_pose[3:7])
    half = 0.5 * p.rod_length
    left_dist = point_to_axis_distance(tcp_left, rod_pose[:3], axis, half)
    left_closed_on = abs(float(gap_left) - p.gap_offset - 2.0 * p.rod_radius) < p.closed_gap_tol
    left_holds = left_dist < p.hold_radius and left_closed_on
    right_dist = point_to_axis_distance(tcp_right, rod_pose[:3], axis, half)
    right_released = float(gap_right) > p.right_open_gap and right_dist > p.right_away
    low = lowest_point_z(rod_pose[:3], axis, p.rod_length, p.rod_radius)
    unsupported = low > p.table_top_z + p.support_clearance
    stable = float(np.linalg.norm(rod_lin_vel)) < p.max_speed and float(np.linalg.norm(rod_ang_vel)) < p.max_rate
    return {
        "left_holds": bool(left_holds),
        "right_released": bool(right_released),
        "unsupported": bool(unsupported),
        "stable": bool(stable),
        "success": bool(left_holds and right_released and unsupported and stable),
        "right_dist": right_dist,
        "left_rod_dist": left_dist,
        "rod_low_z": low,
    }


class Task(RigidTask):
    """Fixed-pose rod handover (see the module docstring)."""

    name = "handover"
    success_hold = 15

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
        self.params = HandoverParams.from_cfg(suc)
        self.workspace_xy = float(suc.get("workspace_xy", 0.9))
        self.drop_margin = float(suc.get("drop_margin", 0.02))
        ho = cfg.get("handover", {})
        self.rod = str(ho.get("rod", "rod"))
        self.gravity_on_after = int(ho.get("gravity_on_after_closed_ticks", 50))
        self.tcp_offset = float(ho.get("tcp_offset", TCP_OFFSET))
        self._closed_ticks = 0
        self._gravity_on = False
        self._left_tcp0: Optional[np.ndarray] = None
        self._flags: Dict[str, Any] = {}

    # ------------------------------------------------------------------ gravity fixture
    def set_gravity(self, enabled: bool) -> None:
        """Switch gravity of the rod on / off at run time."""
        obj = self.scene.objects[self.rod]
        errors = []
        try:
            import torch

            obj.root_physx_view.set_disable_gravities(
                torch.tensor([0 if enabled else 1], dtype=torch.uint8), torch.tensor([0], dtype=torch.int32)
            )
            self._gravity_on = bool(enabled)
            return
        except Exception as exc:  # fall through to the USD attribute
            errors.append(repr(exc))
        try:
            from isaaclab.sim.utils.stage import get_current_stage
            from pxr import PhysxSchema

            prim = get_current_stage().GetPrimAtPath(self.scene.rigid_body_prim_path(self.rod))
            PhysxSchema.PhysxRigidBodyAPI.Apply(prim).CreateDisableGravityAttr().Set(not enabled)
            self._gravity_on = bool(enabled)
            return
        except Exception as exc:
            errors.append(repr(exc))
        raise RuntimeError("cannot toggle the rod's gravity: " + "; ".join(errors))

    def _after_objects_placed(self) -> None:
        self.set_gravity(False)
        self._closed_ticks = 0
        self._ticks = 0

    def _after_settle(self) -> None:
        self._left_tcp0 = self.tcp(1).copy()
        self._flags = {}

    def _apply_action(self, action) -> None:
        super()._apply_action(action)
        self._closed_ticks = self._closed_ticks + 1 if int(action.gripper[0]) == GRIPPER_CLOSE else 0
        self._ticks += 1
        # the rod starts weightless between the closed pads; gravity switches on once the grip has settled, and in any
        # case after the same number of ticks (opening early must not leave the rod floating)
        if not self._gravity_on and (
            self._closed_ticks >= self.gravity_on_after or self._ticks >= self.gravity_on_after
        ):
            self.set_gravity(True)

    # ------------------------------------------------------------------ measurements
    def tcp(self, arm: int) -> np.ndarray:
        return tcp_of_wrist(self.eef_pose(arm), self.tcp_offset)

    def flags(self) -> Dict[str, Any]:
        pose = self.object_pose(self.rod)
        vel = self.object_velocity(self.rod)
        f = handover_flags(
            pose, vel[:3], vel[3:6], self.tcp(0), self.tcp(1), self.gripper_width(0), self.gripper_width(1), self.params
        )
        f["left_drift"] = float(np.linalg.norm(self.tcp(1) - self._left_tcp0)) if self._left_tcp0 is not None else 0.0
        f["gap_left"] = self.gripper_width(1)
        f["gap_right"] = self.gripper_width(0)
        f["gravity_on"] = self._gravity_on
        f["dropped"] = bool(f["rod_low_z"] < self.params.table_top_z + self.drop_margin)
        f["away"] = bool(np.linalg.norm(pose[:2]) > self.workspace_xy)
        return f

    def success_predicate(self) -> bool:
        f = self.flags()
        self._flags = f
        if f["dropped"]:
            self._truncate("rod dropped on the table")
        elif f["away"]:
            self._truncate("rod left the workspace")
        return bool(f["success"])

    def task_privileged(self) -> Dict[str, np.ndarray]:
        f = self._flags or self.flags()
        return {
            "handover/left_holds": np.float32(f["left_holds"]),
            "handover/right_released": np.float32(f["right_released"]),
            "handover/unsupported": np.float32(f["unsupported"]),
            "handover/stable": np.float32(f["stable"]),
            "handover/right_dist": np.float32(f["right_dist"]),
            "handover/left_rod_dist": np.float32(f["left_rod_dist"]),
            "handover/rod_low_z": np.float32(f["rod_low_z"]),
            "handover/left_drift": np.float32(f["left_drift"]),
            "handover/gap_left": np.float32(f["gap_left"]),
            "handover/gap_right": np.float32(f["gap_right"]),
            "handover/tcp_right": self.tcp(0).astype(np.float32),
            "handover/tcp_left": self.tcp(1).astype(np.float32),
        }

    def metrics(self) -> Dict[str, Any]:
        d = super().metrics()
        if self._flags:
            d.update(
                {
                    k: self._flags[k]
                    for k in (
                        "left_holds",
                        "right_released",
                        "unsupported",
                        "stable",
                        "right_dist",
                        "left_rod_dist",
                        "rod_low_z",
                        "left_drift",
                        "gap_left",
                        "gap_right",
                        "gravity_on",
                    )
                }
            )
        return d
