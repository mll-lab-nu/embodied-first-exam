"""Dough surface mesh from a particle cloud (numpy + scipy + scikit-image; Isaac side only, both are imported lazily).

``cloud_to_mesh``: splat the particles into a density grid, blur it a little, and run marching cubes at a level that puts the
surface half a particle spacing outside the outermost particle centres.  The mesh is what the camera and the tactile
raycast see; the success predicates use the particles themselves (``dough_metrics``).
"""

from __future__ import annotations

from typing import Optional, Tuple

import numpy as np


def cloud_to_mesh(
    points: np.ndarray,
    voxel: float,
    lo: Tuple[float, float, float],
    hi: Tuple[float, float, float],
    sigma: float = 1.0,
    level: float = 0.5,
    pad: int = 2,
    tight: bool = False,
    ref: Optional[float] = None,
) -> Optional[Tuple[np.ndarray, np.ndarray, np.ndarray]]:
    """``(vertices (v, 3), triangles (f, 3), vertex normals (v, 3))`` of the dough surface, or None if there is none.

    The grid has cell ``voxel`` over [lo, hi]; ``sigma`` (cells) blurs the occupancy before the iso-surface at ``level``.
    ``tight``: the grid covers the particles' bounding box only.  ``ref``: the particle count per cell of the undeformed paste
    (``voxel**3 / particle_volume``); the iso-level is ``level`` x this density.  None = adaptive (the median of the dense
    cells); pass the fixed reference whenever the particle volume is known, otherwise a strongly compacted part of the paste
    lifts the reference until the normal-density paste vanishes from the mesh."""
    from scipy.ndimage import gaussian_filter
    from skimage.measure import marching_cubes

    lo = np.asarray(lo, float)
    hi = np.asarray(hi, float)
    if tight and len(points):
        lo = np.maximum(points.min(axis=0), lo)
        hi = np.minimum(points.max(axis=0), hi)
    shape = np.maximum(np.ceil((hi - lo) / voxel).astype(int), 1) + 2 * pad
    origin = lo - pad * voxel
    idx = np.floor((points - origin) / voxel).astype(int)
    ok = ((idx >= 0) & (idx < shape)).all(axis=1)
    if not ok.any():
        return None
    grid = np.zeros(shape, np.float32)
    np.add.at(grid, (idx[ok, 0], idx[ok, 1], idx[ok, 2]), 1.0)
    grid = gaussian_filter(grid, sigma)
    # normalise by the density of a fully packed cell (so level ~ 0.5 is the boundary of the packed paste)
    if ref is None:
        top = float(grid.max())
        nz = grid[grid > 0.0]
        # a clump of a few particles (ejected / stacked) far denser than the paste must not set the reference
        if nz.size and top > 3.0 * float(np.percentile(nz, 99)):
            top = float(np.percentile(nz, 99))
        ref = float(np.percentile(grid[grid > 0.5 * top], 50)) if top > 0 else 1.0
    grid = grid / max(float(ref), 1e-6)
    if grid.max() < level:
        return None
    verts, faces, normals, _ = marching_cubes(grid, level=level, spacing=(voxel,) * 3)
    verts = verts + origin + 0.5 * voxel
    return verts.astype(np.float32), faces.astype(np.int32), normals.astype(np.float32)
