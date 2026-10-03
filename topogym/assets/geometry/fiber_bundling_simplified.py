"""Two opposed or three triangular branches on the existing anchored cable.

Dimensions, axial sleeve exits and seeded curvature come from FiberLayout.
Each branch is a rotated copy of the first, so every cross section preserves
the requested 180/120 degree spacing, including the tips. This authors the
reset shape only; the existing passive joints remain free during simulation.
"""
from dataclasses import dataclass

import numpy as np

from .fiber_bundling import FiberLayout, minimum_fiber_clearance


@dataclass(frozen=True)
class SymmetricFiberLayout(FiberLayout):
    fiber_count: int = 2
    minimum_fiber_count = 2

    def __post_init__(self):
        super().__post_init__()
        if self.fiber_count not in (2, 3):
            raise ValueError("Simplified fibers require two opposed or three triangular branches")

    def fibers(self):
        reference = super().fibers()[0]
        paths = []
        for index in range(self.fiber_count):
            angle = 2 * np.pi * index / self.fiber_count
            cosine, sine = np.cos(angle), np.sin(angle)
            rotation = np.array([[cosine, -sine], [sine, cosine]])
            points = reference.copy()
            points[:, 1:] = reference[:, 1:] @ rotation.T
            paths.append(points)
        clearance = minimum_fiber_clearance(paths, self.fiber_radius_m)
        if clearance <= 0:
            raise ValueError(f"Symmetric branches intersect ({clearance:g} m)")
        return paths
