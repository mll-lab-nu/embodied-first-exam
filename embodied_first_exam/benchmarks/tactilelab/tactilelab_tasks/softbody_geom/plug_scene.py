"""Scene of ``fem_plug_insert`` (pure numpy): a compliant square plug, a rigid hole fixture, success metrics.

Frames: env-local metres, z up.  The hole fixture is centred on ``hole_xy`` with its top face at ``top_z``; the plug is built
standing above it, axis along z.  The plug is a regular tetrahedral grid (``add_soft_grid``: 5 tets per cell) of a soft rubber
(``k_mu`` / ``k_lambda`` of a Neo-Hookean-like VBD material); it is slightly OVERSIZED (``interference``) so that seating it
deforms it: the task is judged on seated depth AND on the deformation (compressed cross-section, no buckling).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import List, Sequence

import numpy as np


@dataclass
class PlugSpec:
    size: Sequence[float] = (0.018, 0.018, 0.030)  # plug cross-section x, y and length z [m]
    cell: float = 0.003  # grid cell [m]
    density: float = 1100.0
    k_mu: float = 2.0e5  # shear modulus [Pa] (soft rubber ~ 1e5 .. 1e6)
    k_lambda: float = 6.0e5
    k_damp: float = 1.0e-3
    hole: Sequence[float] = (0.0165, 0.0165)  # hole cross-section [m]: interference = size - hole
    hole_depth: float = 0.026
    wall: float = 0.012  # fixture wall thickness around the hole [m]
    floor: float = 0.010
    grip_band: float = 0.008  # the held band at the top of the plug [m]
    mu: float = 0.8  # friction plug-fixture (rubber on printed plastic)

    @property
    def interference(self) -> float:
        return float(min(self.size[0] - self.hole[0], self.size[1] - self.hole[1]))


def grid_dims(spec: PlugSpec):
    n = [max(1, int(round(s / spec.cell))) for s in spec.size]
    cell = [s / k for s, k in zip(spec.size, n)]
    return n, cell


def fixture_boxes(hole_xy, top_z: float, spec: PlugSpec) -> List[dict]:
    """Static boxes of the hole fixture (4 walls + floor) as ``{name, pos, half, mu}`` (env-local)."""
    hx, hy = 0.5 * spec.hole[0], 0.5 * spec.hole[1]
    w, d, fl = spec.wall, spec.hole_depth, spec.floor
    cx, cy = float(hole_xy[0]), float(hole_xy[1])
    zc = top_z - 0.5 * d
    out = [
        {
            "name": "hole_floor",
            "pos": [cx, cy, top_z - d - 0.5 * fl],
            "half": [hx + w, hy + w, 0.5 * fl],
            "mu": spec.mu,
        },
        {"name": "hole_px", "pos": [cx + hx + 0.5 * w, cy, zc], "half": [0.5 * w, hy + w, 0.5 * d], "mu": spec.mu},
        {"name": "hole_nx", "pos": [cx - hx - 0.5 * w, cy, zc], "half": [0.5 * w, hy + w, 0.5 * d], "mu": spec.mu},
        {"name": "hole_py", "pos": [cx, cy + hy + 0.5 * w, zc], "half": [hx + w, 0.5 * w, 0.5 * d], "mu": spec.mu},
        {"name": "hole_ny", "pos": [cx, cy - hy - 0.5 * w, zc], "half": [hx + w, 0.5 * w, 0.5 * d], "mu": spec.mu},
    ]
    return out


def plug_particle_grid(spec: PlugSpec, center_xy, bottom_z: float) -> np.ndarray:
    """Rest positions ``(P, 3)`` of the plug's grid nodes in the order of ``add_soft_grid`` (x fastest, then y, then z)."""
    n, cell = grid_dims(spec)
    xs = (np.arange(n[0] + 1) - 0.5 * n[0]) * cell[0] + center_xy[0]
    ys = (np.arange(n[1] + 1) - 0.5 * n[1]) * cell[1] + center_xy[1]
    zs = np.arange(n[2] + 1) * cell[2] + bottom_z
    Z, Y, X = np.meshgrid(zs, ys, xs, indexing="ij")  # add_soft_grid order: x fastest, then y, then z
    return np.stack([X.ravel(), Y.ravel(), Z.ravel()], axis=1)


@dataclass
class PlugReport:
    depth: float  # how far the plug's bottom is below the hole's top face [m]
    seated_frac: float  # depth / hole_depth
    width_x: float  # extent of the inserted part [m]
    width_y: float
    compression: float  # 1 - mean inserted width / rest width (the press-fit squeeze)
    tilt_deg: float  # tilt of the plug axis (bottom centre -> top centre) from vertical
    released: bool
    ok: bool
    why: str


def plug_report(
    q: np.ndarray,
    spec: PlugSpec,
    hole_xy,
    top_z: float,
    seated_min: float = 0.9,
    compression_range=(0.005, 0.25),
    tilt_max_deg: float = 6.0,
    released: bool = True,
    xy_tol: float = 0.004,
) -> PlugReport:
    """Seated depth + deformation of the plug (particles ``q`` (P, 3) env-local)."""
    zmin = float(q[:, 2].min())
    depth = top_z - zmin
    seated = depth / spec.hole_depth
    # the part inside the hole: particles below the fixture's top face, without the top grip band (while the gripper holds the plug
    # that band is kinematic: it does not touch the walls, so it keeps its rest width)
    inside = (q[:, 2] < top_z - 1e-4) & (q[:, 2] < q[:, 2].max() - spec.grip_band - 1e-3)
    if inside.sum() >= 8:
        wx = float(np.ptp(q[inside, 0]))
        wy = float(np.ptp(q[inside, 1]))
    else:
        wx = wy = float(spec.size[0])
    rest = 0.5 * (spec.size[0] + spec.size[1])
    comp = 1.0 - 0.5 * (wx + wy) / rest
    low = q[q[:, 2] < zmin + 0.005]
    high = q[q[:, 2] > q[:, 2].max() - 0.005]
    axis = high.mean(0) - low.mean(0)
    tilt = float(np.degrees(np.arccos(np.clip(axis[2] / max(np.linalg.norm(axis), 1e-9), -1, 1))))
    off = float(np.hypot(*(low.mean(0)[:2] - np.asarray(hole_xy, float))))
    why = []
    if seated < seated_min:
        why.append(f"seated {seated:.2f} < {seated_min:.2f}")
    if not (compression_range[0] <= comp <= compression_range[1]):
        why.append(f"compression {comp:.3f} outside {compression_range}")
    if tilt > tilt_max_deg:
        why.append(f"tilt {tilt:.1f} deg > {tilt_max_deg}")
    if off > xy_tol:
        why.append(f"{1e3 * off:.1f} mm off the hole axis")
    if not released:
        why.append("gripper still holding")
    return PlugReport(depth, seated, wx, wy, comp, tilt, released, not why, "; ".join(why) or "ok")


def grid_surface_tris(dims) -> np.ndarray:
    """Outward-oriented boundary triangles ``(F, 3)`` of the regular node grid of :func:`plug_particle_grid` (node
    ``i + (nx + 1) * (j + (ny + 1) * k)``, ``dims`` = cells ``(nx, ny, nz)``): two triangles per boundary quad, counter-clockwise
    seen from outside (positive signed volume).  Newton's own ``tri_indices`` of ``add_soft_grid`` carry no orientation
    guarantee; the tactile raycast uses this surface."""
    nx, ny, nz = (int(v) for v in dims)

    def idx(i, j, k):
        return i + (nx + 1) * (j + (ny + 1) * k)

    tris = []

    def quad(a, b, c, d):  # a, b, c, d counter-clockwise seen from outside
        tris.append((a, b, c))
        tris.append((a, c, d))

    for j in range(ny):
        for k in range(nz):
            quad(idx(0, j, k), idx(0, j, k + 1), idx(0, j + 1, k + 1), idx(0, j + 1, k))  # x = min face (outward -x)
            quad(idx(nx, j, k), idx(nx, j + 1, k), idx(nx, j + 1, k + 1), idx(nx, j, k + 1))  # x = max
    for i in range(nx):
        for k in range(nz):
            quad(idx(i, 0, k), idx(i + 1, 0, k), idx(i + 1, 0, k + 1), idx(i, 0, k + 1))  # y = min
            quad(idx(i, ny, k), idx(i, ny, k + 1), idx(i + 1, ny, k + 1), idx(i + 1, ny, k))  # y = max
    for i in range(nx):
        for j in range(ny):
            quad(idx(i, j, 0), idx(i, j + 1, 0), idx(i + 1, j + 1, 0), idx(i + 1, j, 0))  # z = min
            quad(idx(i, j, nz), idx(i + 1, j, nz), idx(i + 1, j + 1, nz), idx(i, j + 1, nz))  # z = max
    return np.asarray(tris, dtype=np.int32)
