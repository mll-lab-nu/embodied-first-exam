"""Success predicates of the dough tasks (pure numpy).

All of them read the particle cloud ``(n, 3)`` (env-local metres) and the volume one particle stands for.  A column
height is the volume of the particles above a grid cell divided by the cell area ("how thick would the paste be if it
were fully packed"); it is insensitive to the jitter of single particles, unlike a max-z height map.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional, Tuple

import numpy as np


@dataclass
class HeightGrid:
    """Axis-aligned grid of square cells over the workspace; ``z0`` is the plate top."""

    lo: Tuple[float, float]
    nx: int
    ny: int
    dx: float
    z0: float = 0.0

    @property
    def hi(self):
        return (self.lo[0] + self.nx * self.dx, self.lo[1] + self.ny * self.dx)

    def centers(self):
        xs = self.lo[0] + (np.arange(self.nx) + 0.5) * self.dx
        ys = self.lo[1] + (np.arange(self.ny) + 0.5) * self.dx
        return xs, ys

    def disk_mask(self, center, radius) -> np.ndarray:
        xs, ys = self.centers()
        X, Y = np.meshgrid(xs, ys, indexing="ij")
        return (X - center[0]) ** 2 + (Y - center[1]) ** 2 <= radius**2

    def box_mask(self, lo_xy, hi_xy) -> np.ndarray:
        xs, ys = self.centers()
        X, Y = np.meshgrid(xs, ys, indexing="ij")
        return (X >= lo_xy[0]) & (X <= hi_xy[0]) & (Y >= lo_xy[1]) & (Y <= hi_xy[1])


def column_heights(points: np.ndarray, pvol: float, grid: HeightGrid) -> np.ndarray:
    """``(nx, ny)`` packed column heights [m] of the particles (above ``grid.z0`` is not subtracted: volume only)."""
    ix = np.floor((points[:, 0] - grid.lo[0]) / grid.dx).astype(int)
    iy = np.floor((points[:, 1] - grid.lo[1]) / grid.dx).astype(int)
    ok = (ix >= 0) & (ix < grid.nx) & (iy >= 0) & (iy < grid.ny)
    cols = np.zeros((grid.nx, grid.ny))
    np.add.at(cols, (ix[ok], iy[ok]), pvol)
    return cols / (grid.dx * grid.dx)


def column_extent(points: np.ndarray, grid: HeightGrid, spacing: float) -> np.ndarray:
    """``(nx, ny)`` geometric thickness [m] of the dough per cell: (highest - lowest particle centre) + one particle spacing,
    0 where a cell has no particle.  Unlike :func:`column_heights` it does not read compression of the paste as thinness
    (the MPM paste is compressible by ~30 % under a press) and does not depend on where the floor collider puts the lowest
    particles (margin)."""
    ix = np.floor((points[:, 0] - grid.lo[0]) / grid.dx).astype(int)
    iy = np.floor((points[:, 1] - grid.lo[1]) / grid.dx).astype(int)
    ok = (ix >= 0) & (ix < grid.nx) & (iy >= 0) & (iy < grid.ny)
    zmax = np.full((grid.nx, grid.ny), -np.inf)
    zmin = np.full((grid.nx, grid.ny), np.inf)
    np.maximum.at(zmax, (ix[ok], iy[ok]), points[ok, 2])
    np.minimum.at(zmin, (ix[ok], iy[ok]), points[ok, 2])
    occ = np.isfinite(zmax)
    out = np.zeros((grid.nx, grid.ny))
    out[occ] = zmax[occ] - zmin[occ] + spacing
    return out


def column_top(points: np.ndarray, grid: HeightGrid, min_count: int = 2) -> np.ndarray:
    """``(nx, ny)`` height of the dough surface above ``grid.z0`` [m]: the highest particle centre of each cell (cells with
    fewer than ``min_count`` particles are empty = 0).  This is what a press head sets (its pressing face sits at the surface);
    the volume-based :func:`column_heights` reads compression of the paste as thinness."""
    ix = np.floor((points[:, 0] - grid.lo[0]) / grid.dx).astype(int)
    iy = np.floor((points[:, 1] - grid.lo[1]) / grid.dx).astype(int)
    ok = (ix >= 0) & (ix < grid.nx) & (iy >= 0) & (iy < grid.ny)
    zmax = np.full((grid.nx, grid.ny), -np.inf)
    cnt = np.zeros((grid.nx, grid.ny), int)
    np.maximum.at(zmax, (ix[ok], iy[ok]), points[ok, 2])
    np.add.at(cnt, (ix[ok], iy[ok]), 1)
    out = np.where((cnt >= min_count) & np.isfinite(zmax), zmax - grid.z0, 0.0)
    return np.maximum(out, 0.0)


def blur(h: np.ndarray, sigma_cells: float) -> np.ndarray:
    """Separable Gaussian blur (edge-replicated); sigma 0 returns h."""
    if sigma_cells <= 0:
        return h
    r = int(np.ceil(3 * sigma_cells))
    k = np.exp(-0.5 * (np.arange(-r, r + 1) / sigma_cells) ** 2)
    k /= k.sum()
    out = h
    for axis in (0, 1):
        pad = [(0, 0), (0, 0)]
        pad[axis] = (r, r)
        p = np.pad(out, pad, mode="edge")
        out = np.apply_along_axis(lambda v: np.convolve(v, k, mode="valid"), axis, p)
    return out


@dataclass
class PressReport:
    thickness_mean: float
    thickness_std: float
    thickness_p05: float
    thickness_p95: float
    flatness: float  # (p95 - p05) of the column heights in the pressed region [m]
    area: float  # footprint of the dough above `occupied_h` [m^2]
    outside_frac: float  # mass fraction outside the workspace disk
    n_particles: int
    ok: bool
    why: str


def press_report(
    points: np.ndarray,
    pvol: float,
    grid: HeightGrid,
    region: np.ndarray,
    target_thickness: float,
    thickness_tol: float,
    flatness_tol: float,
    workspace_center,
    workspace_radius: float,
    outside_tol: float,
    occupied_h: Optional[float] = None,
    sigma_cells: float = 0.0,
    spacing: Optional[float] = None,
) -> PressReport:
    """Thickness + flatness of the pressed region, material squeezed out of the workspace.

    ``region``: (nx, ny) bool, the cells that must be at ``target_thickness`` (within ``thickness_tol`` on average, with the
    p05..p95 spread of the column heights within ``flatness_tol``)."""
    spacing = float(pvol ** (1.0 / 3.0)) if spacing is None else spacing
    h = blur(column_top(points, grid), sigma_cells)
    hr = h[region]
    if occupied_h is None:
        occupied_h = 0.25 * target_thickness
    d = np.hypot(points[:, 0] - workspace_center[0], points[:, 1] - workspace_center[1])
    outside = float((d > workspace_radius).mean()) if len(points) else 1.0
    if hr.size == 0:
        raise ValueError("press_report: empty region")
    mean, std = float(hr.mean()), float(hr.std())
    p05, p95 = (float(v) for v in np.percentile(hr, [5, 95]))
    flat = p95 - p05
    why = []
    if abs(mean - target_thickness) > thickness_tol:
        why.append(f"thickness {mean * 1e3:.1f} mm vs {target_thickness * 1e3:.1f}+-{thickness_tol * 1e3:.1f}")
    if flat > flatness_tol:
        why.append(f"flatness {flat * 1e3:.1f} mm > {flatness_tol * 1e3:.1f}")
    if outside > outside_tol:
        why.append(f"{outside:.1%} of the dough outside the workspace > {outside_tol:.1%}")
    return PressReport(
        thickness_mean=mean,
        thickness_std=std,
        thickness_p05=p05,
        thickness_p95=p95,
        flatness=flat,
        area=float((h > occupied_h).sum()) * grid.dx * grid.dx,
        outside_frac=outside,
        n_particles=len(points),
        ok=not why,
        why="; ".join(why) or "ok",
    )


@dataclass
class FillReport:
    coverage: float  # fraction of tray cells whose dough is at least min_h_frac x level thick
    flat_frac: float  # of the covered cells: fraction within flat_band x level (the surface at the target level)
    surface_err: float  # mean |top - level| over the covered cells [m]
    outside_frac: float  # mass fraction outside the tray footprint
    n_particles: int
    ok: bool
    why: str
    under_cover: float = 1.0  # coverage of the initially empty (under-filled) part of the tray


def fill_report(
    points: np.ndarray,
    pvol: float,
    grid: HeightGrid,
    tray_mask: np.ndarray,
    target_h: float,
    min_h_frac: float,
    coverage_min: float,
    surface_tol: float,
    outside_tol: float,
    sigma_cells: float = 0.0,
    spacing: Optional[float] = None,
    flat_min: float = 0.0,
    flat_band=(0.5, 1.5),
    under_mask: Optional[np.ndarray] = None,
    under_min: float = 0.0,
) -> FillReport:
    """Tray fill: ``coverage`` of the tray floor by dough thicker than ``min_h_frac * target_h`` (fill range), how much of that
    dough is at the target level (``flat_frac`` within ``flat_band * target_h``: the target surface; ``surface_tol`` bounds the mean
    |top - level| of the covered cells, 0 = off), material outside the tray footprint.  The total mass does not fill the tray:
    ``target_h`` is the level of the dough spread evenly (the caller sets it from the mass)."""
    h = blur(column_top(points, grid), sigma_cells)
    ht = h[tray_mask]
    covered_mask = ht >= min_h_frac * target_h
    cov = float(covered_mask.mean())
    covered = ht[covered_mask]
    flat = (
        float(((covered >= flat_band[0] * target_h) & (covered <= flat_band[1] * target_h)).mean())
        if len(covered)
        else 0.0
    )
    err = float(np.abs(covered - target_h).mean()) if len(covered) else float(target_h)
    ix = np.floor((points[:, 0] - grid.lo[0]) / grid.dx).astype(int)
    iy = np.floor((points[:, 1] - grid.lo[1]) / grid.dx).astype(int)
    inside_grid = (ix >= 0) & (ix < grid.nx) & (iy >= 0) & (iy < grid.ny)
    inside_tray = np.zeros(len(points), bool)
    inside_tray[inside_grid] = tray_mask[ix[inside_grid], iy[inside_grid]]
    outside = float(1.0 - inside_tray.mean()) if len(points) else 1.0
    under_cov = (
        float((h[under_mask] >= min_h_frac * target_h).mean()) if under_mask is not None and under_mask.any() else 1.0
    )
    why = []
    if cov < coverage_min:
        why.append(f"coverage {cov:.2f} < {coverage_min:.2f}")
    if under_cov < under_min:
        why.append(f"under-filled region covered {under_cov:.2f} < {under_min:.2f}")
    if flat < flat_min:
        why.append(f"flat fraction {flat:.2f} < {flat_min:.2f}")
    if surface_tol > 0 and err > surface_tol:
        why.append(f"surface err {err * 1e3:.1f} mm > {surface_tol * 1e3:.1f}")
    if outside > outside_tol:
        why.append(f"{outside:.1%} outside the tray > {outside_tol:.1%}")
    return FillReport(cov, flat, err, outside, len(points), not why, "; ".join(why) or "ok", under_cov)


def dice(a: np.ndarray, b: np.ndarray) -> float:
    a, b = a.astype(bool), b.astype(bool)
    tot = a.sum() + b.sum()
    return 1.0 if tot == 0 else float(2.0 * (a & b).sum() / tot)


def height_iou(h: np.ndarray, target: np.ndarray, thresh: float) -> float:
    """IoU of the occupied cells (h >= thresh) and a target mask."""
    a = h >= thresh
    b = target.astype(bool)
    u = (a | b).sum()
    return 1.0 if u == 0 else float((a & b).sum() / u)
