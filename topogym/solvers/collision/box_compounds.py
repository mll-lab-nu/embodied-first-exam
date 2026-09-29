"""Separating-axis queries for compounds of authored axis-aligned boxes."""
from __future__ import annotations

import numpy as np


def box_corners(boxes):
    """List each box's local material vertices from (N, 2, 3) bounds."""
    indices = np.array([[x, y, z] for x in (0, 1) for y in (0, 1) for z in (0, 1)])
    return np.concatenate([np.where(indices, hi, lo) for lo, hi in boxes])


class BoxCompoundCollision:
    """Return a conservative signed SAT gap for fixed and moving box unions."""

    def __init__(self, fixed_boxes, moving_boxes):
        self.fixed = np.array(fixed_boxes, dtype=float, copy=True)
        self.moving = np.array(moving_boxes, dtype=float, copy=True)
        for boxes in (self.fixed, self.moving):
            if boxes.ndim != 3 or boxes.shape[1:] != (2, 3) or not len(boxes):
                raise ValueError("Expected nonempty (N, 2, 3) box bounds")
            if not np.isfinite(boxes).all() or np.any(boxes[:, 1] <= boxes[:, 0]):
                raise ValueError("Invalid box bounds")
        self.moving_corners = box_corners(self.moving)
        self.ac, self.bc = self.fixed.mean(axis=1), self.moving.mean(axis=1)
        self.ah = np.diff(self.fixed, axis=1)[:, 0] / 2
        self.bh = np.diff(self.moving, axis=1)[:, 0] / 2

    def gap(self, rotation, translation):
        """Minimum pairwise maximal unit-axis separation, in metres."""
        rotation, translation = np.asarray(rotation, dtype=float), np.asarray(translation, dtype=float)
        if (rotation.shape != (3, 3) or translation.shape != (3,)
                or not np.isfinite(np.r_[rotation.ravel(), translation]).all()
                or not np.allclose(rotation.T @ rotation, np.eye(3), atol=1e-8, rtol=0.)
                or not np.isclose(np.linalg.det(rotation), 1., atol=1e-8, rtol=0.)):
            raise ValueError("Expected a finite rigid relative pose")
        axes = np.concatenate((np.eye(3), rotation.T,
            np.cross(np.eye(3)[:, None, :], rotation.T[None]).reshape(-1, 3)))
        norm = np.linalg.norm(axes, axis=1)
        axes = axes[norm > 1e-10] / norm[norm > 1e-10, None]
        delta = (self.bc @ rotation.T + translation)[None] - self.ac[:, None]
        intervals = (np.abs(delta @ axes.T) - (self.ah @ np.abs(axes.T))[:, None]
                     - (self.bh @ np.abs(rotation.T @ axes.T))[None])
        return float(intervals.max(axis=-1).min())
