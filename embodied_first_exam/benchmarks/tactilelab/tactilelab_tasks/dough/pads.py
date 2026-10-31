"""Pad-pair frame of the direct-sensor dough / plug tasks (pure numpy).

The two gel pads of the right gripper are mirrored into the sidecar world as kinematic box colliders
(:data:`PAD_COLLIDERS`: the ``pad_left`` / ``pad_right`` entries of ``softbody_geom.soft_scenes.GSMINI_COLLIDERS``, poses
``x y z qx qy qz qw`` env-local).  The *pad-pair frame* ("mid frame") is what the scripted expert commands: origin = the
centre between the pads, z = the closing axis (from pad 0 towards pad 1), x / y = pad 0's other axes (x vertical for a
hand pointing down).  ``MoveL`` wants an end-effector pose, so :func:`eef_pose_for_mid` converts: the mid frame seen from
the hand (:func:`mid_in_eef`) is constant while the gripper only opens and closes (symmetric fingers), and the commanded
mid pose maps back to the hand.

Quaternions: pad poses are xyzw (the sidecar wire order), end-effector poses are the package's ``x y z qw qx qy qz``.
"""

from __future__ import annotations

from typing import Dict, List, Tuple

import numpy as np

from ..softbody_geom import spec
from ..softbody_geom.soft_scenes import GSMINI_COLLIDERS

#: the two gel pads as collider descriptions (``link`` = gel body, ``offset`` = the box centre in the gel frame)
PAD_COLLIDERS: List[dict] = [dict(d) for d in GSMINI_COLLIDERS[:2]]


def pad_specs(cfg_list=None, mu: float = None) -> List[spec.ColliderSpec]:
    """``ColliderSpec`` of the two pads: ``cfg_list`` (yaml ``colliders``) or the package defaults, friction ``mu`` if given."""
    out = []
    for d in cfg_list or PAD_COLLIDERS:
        d = dict(d)
        if mu is not None:
            d["mu"] = float(mu)
        out.append(spec.ColliderSpec.from_cfg(d))
    return out[:2]


def pad_poses_from_gels(specs, gel_poses_wxyz: Dict[str, np.ndarray]) -> np.ndarray:
    """``(2, 7)`` env-local xyzw pad collider poses from the gel body poses (``{body: pose7 wxyz}``)."""
    links = {k: spec.pose7_wxyz_to_xyzw(np.asarray(v, dtype=np.float64)) for k, v in gel_poses_wxyz.items()}
    return spec.collider_poses(specs, links).astype(np.float64)


def mid_frame(pads: np.ndarray) -> Tuple[np.ndarray, np.ndarray]:
    """``(centre (3,), R (3x3))`` of the pad pair: R's z axis points from pad 0 to pad 1, the rest is pad 0's rotation."""
    pads = np.asarray(pads, dtype=np.float64)
    c = pads[:, :3].mean(axis=0)
    R = spec.quat_to_mat(pads[0, 3:7])
    if float(R[:, 2] @ (pads[1, :3] - pads[0, :3])) < 0.0:
        R = R @ np.diag([1.0, -1.0, -1.0])
    return c, R


def mid_in_eef(pads: np.ndarray, eef_wxyz: np.ndarray) -> Tuple[np.ndarray, np.ndarray]:
    """The pad-pair frame in the hand frame: ``(t (3,), R_em (3x3))``."""
    e = np.asarray(eef_wxyz, dtype=np.float64)
    Re = spec.quat_to_mat(spec.quat_wxyz_to_xyzw(e[3:7]))
    c, R = mid_frame(pads)
    return Re.T @ (c - e[:3]), Re.T @ R


def eef_pose_for_mid(pads: np.ndarray, eef_wxyz: np.ndarray, mid_pos, R_mid: np.ndarray) -> np.ndarray:
    """Hand pose ``(7,)`` (``x y z qw qx qy qz``) that puts the pad-pair frame at ``mid_pos`` with rotation ``R_mid``."""
    t, R_em = mid_in_eef(pads, eef_wxyz)
    R_we = np.asarray(R_mid, dtype=np.float64) @ R_em.T
    p = np.asarray(mid_pos, dtype=np.float64) - R_we @ t
    q = spec.quat_xyzw_to_wxyz(spec.mat_to_quat(R_we))
    return np.concatenate([p, q])


def approach_axis_in_mid(pads: np.ndarray, eef_wxyz: np.ndarray) -> np.ndarray:
    """The hand's approach direction (flange -> pad-pair centre) in the pad-pair frame, unit vector."""
    t, R_em = mid_in_eef(pads, eef_wxyz)
    return R_em.T @ (t / np.linalg.norm(t))


def closing_axis(yaw: float) -> np.ndarray:
    """``n(yaw) = (-sin yaw, cos yaw, 0)``: yaw 0 closes along +y, -pi/2 along +x (the convention of ``dough_pinch.pad_pose``)."""
    return np.array([-np.sin(yaw), np.cos(yaw), 0.0])


def mid_rotation(pads: np.ndarray, eef_wxyz: np.ndarray, yaw: float, approach=(0.0, 0.0, -1.0)) -> np.ndarray:
    """Pad-pair rotation with the hand's approach axis along ``approach`` (down) and the closing axis along ``n(yaw)``."""
    a_loc = approach_axis_in_mid(pads, eef_wxyz)
    Bl = spec.frame_from_axes(a_loc, np.array([0.0, 0.0, 1.0]))
    Bw = spec.frame_from_axes(np.asarray(approach, dtype=np.float64), closing_axis(yaw))
    return Bw @ Bl.T


def eef_for_pad_mid(pads: np.ndarray, eef_wxyz: np.ndarray, mid_xyz, yaw: float = -0.5 * np.pi) -> np.ndarray:
    """Hand pose (``x y z qw qx qy qz``) that puts the centre between the pads at ``mid_xyz`` with the closing axis along
    ``n(yaw)`` and the hand pointing down."""
    return eef_pose_for_mid(pads, eef_wxyz, mid_xyz, mid_rotation(pads, eef_wxyz, float(yaw)))


def mid_pose_wxyz(pads: np.ndarray) -> np.ndarray:
    """``x y z qw qx qy qz`` of the pad-pair frame (what the direct tasks report as the "tool" pose)."""
    c, R = mid_frame(pads)
    return np.concatenate([c, spec.quat_xyzw_to_wxyz(spec.mat_to_quat(R))])


def pad_face_gap(pads: np.ndarray, half_z: float) -> float:
    """Distance between the two gel faces along the line of the pad centres [m] (~6.5 mm with the gripper closed)."""
    pads = np.asarray(pads, dtype=np.float64)
    return float(np.linalg.norm(pads[1, :3] - pads[0, :3])) - 2.0 * float(half_z)


def extrapolate_points(last: np.ndarray, vel: np.ndarray, ticks: float, control_dt: float) -> np.ndarray:
    """A soft tactile target moved on by ``ticks`` control ticks with its per-vertex velocity (the sidecar steps every
    ``mpm_every``-th tick, the gels every tick)."""
    return (
        np.asarray(last, dtype=np.float64) + np.asarray(vel, dtype=np.float64) * (float(ticks) * float(control_dt))
    ).astype(np.float32)


__all__ = [
    "PAD_COLLIDERS",
    "pad_specs",
    "pad_poses_from_gels",
    "mid_frame",
    "mid_in_eef",
    "eef_pose_for_mid",
    "approach_axis_in_mid",
    "closing_axis",
    "mid_rotation",
    "eef_for_pad_mid",
    "mid_pose_wxyz",
    "pad_face_gap",
    "extrapolate_points",
]
