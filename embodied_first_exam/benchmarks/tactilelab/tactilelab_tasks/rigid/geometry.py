"""Insertion and grasp geometry for the rigid assembly tasks (numpy only).

Two annotation files describe every held / target pair:

* ``Annotation/insertion_pose.json`` of the **held** part carries an
  ``insertion_axis`` (``tail_local`` = shoulder end, ``head_local`` = the tip that
  enters the hole first) and optionally ``grasp_mid_local`` (middle of the
  graspable segment, used by the screw re-grip);
* ``Annotation/insertion_pose.json`` of the **target** part carries ``slots``
  (``hole_top_local`` = opening, ``hole_bottom_local`` = deepest point);
* ``Annotation/grasp_pose.json`` of a graspable part carries lists of end-effector
  poses expressed in the part frame (``functional_grasp`` / ``grasp`` families,
  one list per named region such as ``body``).

All poses are ``[x y z qw qx qy qz]`` in the env frame (:mod:`tactilelab_tasks.core.math`).
The hole axis ``n_w`` points from the opening to the bottom; the signed depth of the
held tip is its projection on that axis from the opening, the lateral error is the
remainder.
"""

from __future__ import annotations

import json
import math
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Sequence, Tuple

import numpy as np

from ..core import math as m

__all__ = [
    "HeldAxis",
    "Slot",
    "load_held_axis",
    "load_slot",
    "load_grasp_candidates",
    "insertion_world",
    "signed_depth_lateral",
    "angle_between_deg",
    "quat_align",
    "object_pose_for_tip",
    "eef_from_object",
    "relative_pose",
    "twist_about",
    "frame_from_axis_y",
    "candidates_world",
    "clearance_filter",
    "pad_center_filter",
    "pose_backward_along_z",
    "pose_up",
    "yaw_deg",
]

_EPS = 1e-9


# --------------------------------------------------------------------------- annotations
@dataclass
class HeldAxis:
    """Insertion axis of a held part in its own frame."""

    tail: np.ndarray
    head: np.ndarray
    grasp_mid: Optional[np.ndarray] = None

    @property
    def direction(self) -> np.ndarray:
        v = self.head - self.tail
        n = float(np.linalg.norm(v))
        return v / n if n > _EPS else np.array([0.0, 0.0, -1.0])

    @property
    def length(self) -> float:
        return float(np.linalg.norm(self.head - self.tail))


@dataclass
class Slot:
    """One hole of a target part in the target frame."""

    top: np.ndarray
    bottom: np.ndarray
    name: str = ""

    @property
    def depth(self) -> float:
        return float(np.linalg.norm(self.bottom - self.top))


def _vec3(v) -> np.ndarray:
    return np.asarray(v, dtype=np.float64).reshape(3)


def load_held_axis(path: str) -> HeldAxis:
    """Read ``insertion_axis`` (and ``grasp_mid_local``) of a held part."""
    with open(path, "r", encoding="utf-8") as fh:
        ann = json.load(fh)
    axis = ann.get("insertion_axis")
    if not isinstance(axis, dict) or "head_local" not in axis:
        raise KeyError(f"{path}: no insertion_axis.head_local")
    tail = _vec3(axis.get("tail_local", [0.0, 0.0, 0.0]))
    head = _vec3(axis["head_local"])
    mid = ann.get("grasp_mid_local")
    return HeldAxis(tail, head, None if mid is None else _vec3(mid))


def load_slot(path: str, slot_name: str) -> Slot:
    """Read one slot (``hole_top_local`` / ``hole_bottom_local``) of a target part."""
    with open(path, "r", encoding="utf-8") as fh:
        ann = json.load(fh)
    slots = ann.get("slots") or {}
    slot = slots.get(slot_name)
    if not isinstance(slot, dict):
        raise KeyError(f"{path}: slot {slot_name!r} not in {sorted(slots)}")
    bottom = slot.get("hole_bottom_local", slot.get("slot_center_local"))
    top = slot.get("hole_top_local")
    if bottom is None or top is None:
        raise KeyError(f"{path}: slot {slot_name!r} needs hole_top_local and hole_bottom_local")
    return Slot(_vec3(top), _vec3(bottom), slot_name)


def load_grasp_candidates(
    path: str, part: Optional[str] = "body", families: Sequence[str] = ("functional_grasp", "grasp")
) -> np.ndarray:
    """``(N, 7)`` end-effector poses in the part frame.

    ``part`` selects a region name inside each family (``None`` = every region);
    when the requested region is absent from a family, every region of that family
    is taken instead, so a library with a single unnamed region still loads.
    """
    with open(path, "r", encoding="utf-8") as fh:
        ann = json.load(fh)
    rows: List[np.ndarray] = []
    for fam in families:
        d = ann.get(fam)
        if not isinstance(d, dict) or not d:
            continue
        regions = (
            [d[part]]
            if (part is not None and isinstance(d.get(part), list))
            else [v for v in d.values() if isinstance(v, list)]
        )
        for lst in regions:
            for p in lst:
                if isinstance(p, dict):  # dexterous-hand format: take the final grasp
                    ph = p.get("final_grasp") or p.get("fine_grasp") or p.get("coarse_grasp")
                    if ph is None:
                        continue
                    p = list(ph["position"]) + list(ph["orientation"])
                arr = np.asarray(p, dtype=np.float64).reshape(-1)
                if arr.size == 7 and np.isfinite(arr).all():
                    rows.append(np.concatenate([arr[:3], m.quat_normalize(arr[3:7])]))
    if not rows:
        raise KeyError(f"{path}: no grasp poses (families {list(families)}, part {part!r})")
    return np.stack(rows, axis=0)


# --------------------------------------------------------------------------- world geometry
def quat_align(from_dir: np.ndarray, to_dir: np.ndarray) -> np.ndarray:
    """Shortest-arc quaternion rotating unit ``from_dir`` onto unit ``to_dir``."""
    f = _vec3(from_dir)
    t = _vec3(to_dir)
    f = f / max(np.linalg.norm(f), _EPS)
    t = t / max(np.linalg.norm(t), _EPS)
    c = float(np.dot(f, t))
    if c < -1.0 + 1e-6:  # opposite: 180 degrees about any perpendicular axis
        perp = np.cross(f, [1.0, 0.0, 0.0])
        if np.linalg.norm(perp) < 1e-6:
            perp = np.cross(f, [0.0, 1.0, 0.0])
        perp = perp / np.linalg.norm(perp)
        return np.concatenate([[0.0], perp])
    q = np.concatenate([[1.0 + c], np.cross(f, t)])
    return m.quat_normalize(q)


def insertion_world(
    held_pose: np.ndarray, axis: HeldAxis, target_pose: np.ndarray, slot: Slot
) -> Dict[str, np.ndarray]:
    """World-frame insertion geometry: ``center_w, tip_w, axis_w, top_w, bot_w, n_w, depth``."""
    held_pose = np.asarray(held_pose, dtype=np.float64)
    target_pose = np.asarray(target_pose, dtype=np.float64)
    center_w = m.pose_transform_point(held_pose, axis.tail)
    tip_w = m.pose_transform_point(held_pose, axis.head)
    axis_w = tip_w - center_w
    axis_w = axis_w / max(np.linalg.norm(axis_w), _EPS)
    top_w = m.pose_transform_point(target_pose, slot.top)
    bot_w = m.pose_transform_point(target_pose, slot.bottom)
    descent = bot_w - top_w
    depth = float(np.linalg.norm(descent))
    n_w = descent / max(depth, _EPS)
    return {
        "center_w": center_w,
        "tip_w": tip_w,
        "axis_w": axis_w,
        "top_w": top_w,
        "bot_w": bot_w,
        "n_w": n_w,
        "depth": depth,
    }


def signed_depth_lateral(tip_w: np.ndarray, top_w: np.ndarray, n_w: np.ndarray) -> Tuple[float, float, np.ndarray]:
    """``(signed_depth, lateral, lat_vec)`` of the tip relative to the hole opening."""
    delta = np.asarray(tip_w) - np.asarray(top_w)
    d = float(np.dot(delta, n_w))
    lat_vec = delta - d * np.asarray(n_w)
    return d, float(np.linalg.norm(lat_vec)), lat_vec


def angle_between_deg(a: np.ndarray, b: np.ndarray) -> float:
    a = _vec3(a)
    b = _vec3(b)
    c = float(np.dot(a, b) / max(np.linalg.norm(a) * np.linalg.norm(b), _EPS))
    return math.degrees(math.acos(max(-1.0, min(1.0, c))))


def object_pose_for_tip(target_tip: np.ndarray, q_des: np.ndarray, head_local: np.ndarray) -> np.ndarray:
    """Held-part pose that puts its tip at ``target_tip`` with orientation ``q_des``."""
    pos = np.asarray(target_tip, dtype=np.float64) - m.quat_rotate(q_des, head_local)
    return np.concatenate([pos, m.quat_normalize(q_des)])


def relative_pose(eef_pose: np.ndarray, obj_pose: np.ndarray) -> np.ndarray:
    """Object pose expressed in the end-effector frame (the grip transform)."""
    return m.pose_relative(eef_pose, obj_pose)


def eef_from_object(obj_pose_des: np.ndarray, t_e2o: np.ndarray) -> np.ndarray:
    """End-effector pose that places the held object at ``obj_pose_des`` for grip ``t_e2o``."""
    return m.pose_compose(obj_pose_des, m.pose_inverse(t_e2o))


def twist_about(q_a: np.ndarray, q_b: np.ndarray, axis_w: np.ndarray) -> float:
    """Signed rotation (rad, in ``(-pi, pi]``) of ``q_a`` relative to ``q_b`` about ``axis_w``."""
    q_rel = m.quat_mul(q_a, m.quat_conjugate(q_b))
    if q_rel[0] < 0.0:
        q_rel = -q_rel
    t = 2.0 * math.atan2(float(np.dot(q_rel[1:4], axis_w)), float(q_rel[0]))
    while t > math.pi:
        t -= 2.0 * math.pi
    while t <= -math.pi:
        t += 2.0 * math.pi
    return t


def frame_from_axis_y(axis_w: np.ndarray, y_dir: np.ndarray) -> np.ndarray:
    """Hand orientation with tool +Z along ``axis_w`` and +Y along ``y_dir`` (projected)."""
    axis_w = _vec3(axis_w) / max(np.linalg.norm(axis_w), _EPS)
    y_t = _vec3(y_dir) - axis_w * float(np.dot(y_dir, axis_w))
    y_t = y_t / max(np.linalg.norm(y_t), _EPS)
    q1 = quat_align([0.0, 0.0, 1.0], axis_w)
    y1 = m.quat_rotate(q1, [0.0, 1.0, 0.0])
    y1 = y1 - axis_w * float(np.dot(y1, axis_w))
    y1 = y1 / max(np.linalg.norm(y1), _EPS)
    ang = math.atan2(float(np.dot(np.cross(y1, y_t), axis_w)), float(np.dot(y1, y_t)))
    return m.quat_normalize(m.quat_mul(m.quat_from_axis_angle(axis_w, ang), q1))


def yaw_deg(q: np.ndarray) -> float:
    """Yaw about world Z (degrees)."""
    w, x, y, z = (float(v) for v in q)
    return math.degrees(math.atan2(2.0 * (w * z + x * y), 1.0 - 2.0 * (y * y + z * z)))


# --------------------------------------------------------------------------- grasp candidates
def candidates_world(cands_local: np.ndarray, obj_pose: np.ndarray) -> np.ndarray:
    """Part-frame candidates ``(N, 7)`` mapped to the env frame."""
    obj_pose = np.asarray(obj_pose, dtype=np.float64)
    return np.stack([m.pose_compose(obj_pose, c) for c in cands_local], axis=0)


def clearance_filter(cands_world: np.ndarray, obj_pose: np.ndarray, max_offset: Optional[float]) -> np.ndarray:
    """Boolean mask of candidates whose hand centre lies within ``max_offset`` of the part's
    body axis (part local +Z) measured along the jaw-closing direction (hand +Y).

    Offset perpendicular to the jaws is free (open side of the finger cage); offset
    along the jaws eats the pad-to-body margin. ``None`` keeps every candidate; a
    filter that would empty the set is skipped.
    """
    n = len(cands_world)
    if max_offset is None or n == 0:
        return np.ones(n, dtype=bool)
    axis = m.quat_rotate(obj_pose[3:7], [0.0, 0.0, 1.0])
    keep = np.ones(n, dtype=bool)
    for i, c in enumerate(cands_world):
        lat = c[:3] - obj_pose[:3]
        lat = lat - axis * float(np.dot(lat, axis))
        jaw = m.quat_rotate(c[3:7], [0.0, 1.0, 0.0])
        jaw = jaw - axis * float(np.dot(jaw, axis))
        nj = float(np.linalg.norm(jaw))
        if nj < 1e-6:
            continue
        keep[i] = abs(float(np.dot(lat, jaw))) / nj <= max_offset
    return keep if keep.any() else np.ones(n, dtype=bool)


def pad_center_filter(
    cands_local: np.ndarray, target_local: Optional[Sequence[float]], pad_offset: float, tol: float
) -> np.ndarray:
    """Mask of candidates whose pad centre (``pad_offset`` down the tool +Z) lies within ``tol`` of
    ``target_local`` in the part frame. ``None`` target or an emptying filter keeps everything."""
    n = len(cands_local)
    if target_local is None or n == 0:
        return np.ones(n, dtype=bool)
    tgt = _vec3(target_local)
    keep = np.ones(n, dtype=bool)
    for i, c in enumerate(cands_local):
        pad = c[:3] + m.quat_rotate(c[3:7], [0.0, 0.0, 1.0]) * pad_offset
        keep[i] = float(np.linalg.norm(pad - tgt)) <= tol
    return keep if keep.any() else np.ones(n, dtype=bool)


def pose_backward_along_z(pose: np.ndarray, distance: float) -> np.ndarray:
    """``pose`` moved backwards by ``distance`` along its own +Z (the approach axis)."""
    out = np.asarray(pose, dtype=np.float64).copy()
    out[:3] = out[:3] - m.quat_rotate(out[3:7], [0.0, 0.0, 1.0]) * float(distance)
    return out


def pose_up(pose: np.ndarray, distance: float) -> np.ndarray:
    """``pose`` lifted by ``distance`` along world +Z."""
    out = np.asarray(pose, dtype=np.float64).copy()
    out[2] += float(distance)
    return out
