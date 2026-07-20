from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable

import numpy as np


def _as_numpy(value) -> np.ndarray:
    if hasattr(value, "detach"):
        value = value.detach().cpu().numpy()
    return np.asarray(value)


def _xyz(value) -> np.ndarray:
    return _as_numpy(value).reshape(-1, 3)[0]


def yaw_quat(yaw: float) -> tuple[float, float, float, float]:
    half = 0.5 * float(yaw)
    return (float(np.cos(half)), 0.0, 0.0, float(np.sin(half)))


def rotate_z(offset, yaw: float) -> np.ndarray:
    offset = np.asarray(offset, dtype=float)
    c = float(np.cos(float(yaw)))
    s = float(np.sin(float(yaw)))
    return np.array(
        [
            c * offset[0] - s * offset[1],
            s * offset[0] + c * offset[1],
            offset[2],
        ],
        dtype=float,
    )


def parent_pos_for_child(child_pos, offset, yaw: float) -> np.ndarray:
    return np.asarray(child_pos, dtype=float) - rotate_z(offset, yaw)


@dataclass
class RigidAttachment:
    """Runtime state for a kinematic object attached to a moving parent.

    ``offset`` is the child origin in the parent's planar-yaw frame. For a
    Franka grasp demo this means: object_center = actual_hand_pos + Rz(yaw) *
    offset.
    """

    entity: Any
    parent_pos_fn: Callable[[], Any]
    offset: np.ndarray
    yaw: float = 0.0
    child_yaw_offset: float = 0.0
    active: bool = False

    def attach(self, *, yaw: float | None = None) -> None:
        if yaw is not None:
            self.yaw = float(yaw)
        self.active = True
        self.sync()

    def set_yaw(self, yaw: float) -> None:
        self.yaw = float(yaw)

    def sync(self) -> None:
        if not self.active:
            return
        parent_pos = _xyz(self.parent_pos_fn())
        child_pos = parent_pos + rotate_z(self.offset, self.yaw)
        self.entity.set_pos(tuple(child_pos), zero_velocity=True)
        self.entity.set_quat(yaw_quat(self.yaw + self.child_yaw_offset), zero_velocity=True, relative=False)

    def release(self, *, sync: bool = True) -> None:
        if sync:
            self.sync()
        self.active = False


class AttachmentManager:
    """Keeps active attachments synchronized around every scene step."""

    def __init__(self, scene: Any):
        self.scene = scene
        self.attachments: list[RigidAttachment] = []
        self._original_step = None

    def create(
        self,
        *,
        entity: Any,
        parent_pos_fn: Callable[[], Any],
        offset,
        yaw: float = 0.0,
        child_yaw_offset: float = 0.0,
    ) -> RigidAttachment:
        attachment = RigidAttachment(
            entity=entity,
            parent_pos_fn=parent_pos_fn,
            offset=np.asarray(offset, dtype=float),
            yaw=float(yaw),
            child_yaw_offset=float(child_yaw_offset),
        )
        self.attachments.append(attachment)
        return attachment

    def sync(self) -> None:
        for attachment in self.attachments:
            attachment.sync()

    def __enter__(self) -> AttachmentManager:
        if self._original_step is not None:
            return self
        self._original_step = self.scene.step

        def wrapped_step(*args, **kwargs):
            self.sync()
            result = self._original_step(*args, **kwargs)
            self.sync()
            return result

        self.scene.step = wrapped_step
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        if self._original_step is not None:
            self.scene.step = self._original_step
            self._original_step = None
