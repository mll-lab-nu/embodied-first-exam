"""Pure rigid-motion segments and geometric witness interpolation."""
from __future__ import annotations

from dataclasses import dataclass
import numpy as np
from scipy.spatial.transform import Rotation, Slerp


@dataclass
class RigidMotionSegment:
    """A translation or rotation segment, parameterized by progress u in [0, 1]."""

    name: str
    duration_s: float
    start_rotation: np.ndarray
    start_translation: np.ndarray
    end_translation: np.ndarray | None = None
    axis: np.ndarray | None = None
    angle_rad: float = 0.
    pivot: np.ndarray | None = None

    def __post_init__(self):
        if not np.isfinite(self.duration_s) or self.duration_s <= 0:
            raise ValueError("duration_s must be finite and positive")
        self.start_rotation = np.array(self.start_rotation, dtype=float, copy=True)
        self.start_translation = np.array(self.start_translation, dtype=float, copy=True)
        if (self.start_rotation.shape != (3, 3) or self.start_translation.shape != (3,)
                or not np.isfinite(np.r_[self.start_rotation.ravel(), self.start_translation]).all()
                or not np.allclose(self.start_rotation.T @ self.start_rotation, np.eye(3), atol=1e-8, rtol=0.)
                or not np.isclose(np.linalg.det(self.start_rotation), 1., atol=1e-8, rtol=0.)):
            raise ValueError("Expected a finite rigid start pose")
        if self.axis is None:
            self.end_translation = np.array(self.end_translation, dtype=float, copy=True)
            if self.end_translation.shape != (3,) or not np.isfinite(self.end_translation).all():
                raise ValueError("A translation segment requires a finite end_translation")
        else:
            self.axis = np.array(self.axis, dtype=float, copy=True)
            self.pivot = np.array(self.pivot, dtype=float, copy=True)
            if (self.axis.shape != (3,) or self.pivot.shape != (3,)
                    or not np.isfinite(np.r_[self.axis, self.pivot, self.angle_rad]).all()
                    or not np.isclose(np.linalg.norm(self.axis), 1., atol=1e-8, rtol=0.)):
                raise ValueError("A rotation segment requires a unit axis, finite angle and pivot")

    def pose(self, u):
        if not np.isfinite(u) or not 0 <= u <= 1:
            raise ValueError("Motion progress must be finite and in [0, 1]")
        if self.axis is None:
            return self.start_rotation, (1-u)*self.start_translation + u*self.end_translation
        delta = Rotation.from_rotvec(self.axis*self.angle_rad*u).as_matrix()
        return delta @ self.start_rotation, self.pivot + delta @ (self.start_translation-self.pivot)

    def point_speed_bound(self, corners):
        """Maximum material displacement per unit progress u, not metres/second."""
        if self.axis is None:
            return float(np.linalg.norm(self.end_translation-self.start_translation))
        points = np.asarray(corners) @ self.start_rotation.T + self.start_translation-self.pivot
        radius = np.linalg.norm(np.cross(points, self.axis), axis=1).max()
        return float(abs(self.angle_rad)*radius)

    def to_dict(self):
        return {key: value.tolist() if isinstance(value, np.ndarray) else value
                for key, value in vars(self).items()}





