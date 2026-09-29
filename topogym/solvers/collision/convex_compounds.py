"""Separating-axis queries for unions of closed convex collision meshes."""
from __future__ import annotations

import numpy as np


def _directions(vectors):
    vectors = np.asarray(vectors, dtype=float)
    lengths = np.linalg.norm(vectors, axis=1)
    vectors = vectors[lengths > 1e-10] / lengths[lengths > 1e-10, None]
    vectors = np.unique(np.round(vectors, 10), axis=0)
    return vectors / np.linalg.norm(vectors, axis=1)[:, None]


class ConvexCompoundCollision:
    """SAT overlap query; a positive gap is a separation lower bound.

    World-axis bounds reject distant pairs; the remaining pairs use face normals
    and crossed edge directions. Containment counts as overlap, unlike a query
    that tests triangle-surface intersections alone.
    """

    def __init__(self, fixed, moving):
        fixed, moving = list(fixed), list(moving)
        if not fixed or not moving:
            raise ValueError("Expected nonempty fixed and moving convex compounds")
        self.fixed = [self._data(mesh) for mesh in fixed]
        self.moving = [self._data(mesh) for mesh in moving]
        self.fixed_bounds = np.array([mesh.bounds for mesh in fixed])
        self.moving_corners = np.concatenate([vertices for vertices, _, _ in self.moving])

    @staticmethod
    def _data(mesh):
        if not mesh.is_convex or not mesh.is_watertight or not np.isfinite(mesh.vertices).all():
            raise ValueError("Expected closed finite convex collision cells")
        edges = mesh.vertices[mesh.edges_unique[:, 1]] - mesh.vertices[mesh.edges_unique[:, 0]]
        return mesh.vertices.copy(), _directions(mesh.face_normals), _directions(edges)

    def gap(self, rotation, translation):
        rotation, translation = np.asarray(rotation, dtype=float), np.asarray(translation, dtype=float)
        if (rotation.shape != (3, 3) or translation.shape != (3,)
                or not np.isfinite(np.r_[rotation.ravel(), translation]).all()
                or not np.allclose(rotation.T @ rotation, np.eye(3), atol=1e-8, rtol=0.)
                or not np.isclose(np.linalg.det(rotation), 1., atol=1e-8, rtol=0.)):
            raise ValueError("Expected a finite rigid relative pose")
        transformed = [(v @ rotation.T + translation, n @ rotation.T, e @ rotation.T)
                       for v, n, e in self.moving]
        bounds = np.array([[v.min(axis=0), v.max(axis=0)] for v, _, _ in transformed])
        delta = np.maximum(self.fixed_bounds[:, None, 0] - bounds[None, :, 1],
                           bounds[None, :, 0] - self.fixed_bounds[:, None, 1])
        broad = delta.max(axis=-1)
        best = float("inf")
        for flat in np.argsort(broad, axis=None):
            i, j = np.unravel_index(flat, broad.shape)
            if broad[i, j] >= best:
                break
            av, an, ae = self.fixed[i]
            bv, bn, be = transformed[j]
            cross = np.cross(ae[:, None], be[None]).reshape(-1, 3)
            lengths = np.linalg.norm(cross, axis=1)
            axes = np.concatenate((np.eye(3), an, bn,
                                   cross[lengths > 1e-8] / lengths[lengths > 1e-8, None]))
            ap, bp = av @ axes.T, bv @ axes.T
            gap = np.maximum(ap.min(axis=0) - bp.max(axis=0), bp.min(axis=0) - ap.max(axis=0)).max()
            best = min(best, float(gap))
        return best
