"""Scene builders of the dough tasks (pure numpy): geometry, particles, masks, the Newton world description.

Frames: everything here is in the *anchored* frame - origin = the plate-top (or tray-floor) point ``anchor`` of the env-local
frame, z up, so the MPM grid sits at the origin whatever height the table has.  ``DoughScene.to_local`` / ``to_anchored``
convert.  The task config block (``p``) is the single source of the numbers; the Isaac-side scene objects (plate, tray walls)
are built from the same numbers.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple

import numpy as np

from . import dough_metrics as dm
from . import dough_scene as ds
from . import tools as tl


@dataclass
class DoughScene:
    kind: str
    world_cfg: dict  # dough world cfg (material, voxel, colliders, tools, bounds)
    points: np.ndarray  # (n, 3) anchored
    pvol: float
    anchor: np.ndarray  # (3,) env-local
    grid: dm.HeightGrid  # anchored frame, z0 = 0 (plate / floor top)
    masks: Dict[str, np.ndarray] = field(default_factory=dict)
    info: Dict[str, float] = field(default_factory=dict)
    extra: Dict[str, object] = field(default_factory=dict)  # non-numeric plan data

    def to_local(self, p: np.ndarray) -> np.ndarray:
        return np.asarray(p) + self.anchor

    def to_anchored(self, p: np.ndarray) -> np.ndarray:
        return np.asarray(p) - self.anchor


def plate_box(half_xy, thickness: float = 0.02, mu: float = 0.6) -> dict:
    """The static plate under the dough: top face at z = 0 of the anchored frame."""
    return {"center": [0.0, 0.0, -0.5 * thickness], "half": [half_xy[0], half_xy[1], 0.5 * thickness], "mu": mu}


def stadium_mask(grid: dm.HeightGrid, a_xy, b_xy, half_width: float) -> np.ndarray:
    """Cells within ``half_width`` of the segment a-b (the footprint a head of that half width sweeps)."""
    xs, ys = grid.centers()
    X, Y = np.meshgrid(xs, ys, indexing="ij")
    a, b = np.asarray(a_xy, float), np.asarray(b_xy, float)
    ab = b - a
    t = np.clip(((X - a[0]) * ab[0] + (Y - a[1]) * ab[1]) / max(float(ab @ ab), 1e-12), 0.0, 1.0)
    d = np.hypot(X - (a[0] + t * ab[0]), Y - (a[1] + t * ab[1]))
    return d <= half_width


def press_segment(p: dict, rng: np.random.Generator) -> Tuple[np.ndarray, np.ndarray]:
    """Press start / end of an episode (anchored xy): a lateral stroke of ``stroke_len`` along a yaw drawn in ``yaw_deg``,
    centred ``center_jitter`` around the dough centre."""
    yaw = np.deg2rad(float(rng.uniform(*p.get("yaw_deg", [0.0, 0.0]))))
    jit = float(p.get("center_jitter", 0.0))
    c = np.asarray(p.get("blob_center", [0.0, 0.0]), float) + rng.uniform(-jit, jit, size=2)
    half = 0.5 * float(p.get("stroke_len", 0.03))
    u = np.array([np.cos(yaw), np.sin(yaw)])
    return c - half * u, c + half * u


def make_press_scene(p: dict, anchor, rng: Optional[np.random.Generator] = None) -> DoughScene:
    """``dough_press_thickness`` (tool variant): a puck of dough on a fixed plate; the press head presses a strip of it."""
    rng = np.random.default_rng(0) if rng is None else rng
    voxel = float(p.get("voxel", 0.005))
    mat = p.get("material", "dough")
    blob_c = np.asarray(p.get("blob_center", [0.0, 0.0]), float)
    blob = {
        "type": "cylinder",
        "center": [blob_c[0], blob_c[1], float(p.get("blob_z0", 0.0003))],
        "radius": float(p.get("blob_radius", 0.04)),
        "height": float(p.get("blob_height", 0.025)),
    }
    pts, pvol = ds.blob_points(blob, voxel, int(p.get("ppc", 2)), int(rng.integers(1 << 30)))
    head = tl.tool_spec("press_tool", "tool", mu=p.get("tool_mu"))
    half_plate = p.get("plate_half", [0.12, 0.12])
    cfg = {
        "material": mat,
        "voxel": voxel,
        "dt": float(p.get("dt", 1.0 / 30.0)),
        "substeps": int(p.get("substeps", 1)),
        "iterations": int(p.get("iterations", 40)),
        "collider_margin": float(p.get("collider_margin", voxel)),
        "boxes": [plate_box(half_plate)],
        "tools": [head],
        "bounds": p.get("bounds", [[-0.12, -0.12, -0.02], [0.12, 0.12, 0.10]]),
        "ground": False,
    }
    grid = dm.HeightGrid(lo=(-0.1, -0.1), nx=50, ny=50, dx=0.004, z0=0.0)
    a, b = press_segment(p, rng)
    hw = 0.5 * tl.PRESS_HEAD[1] if not p.get("region_half_width") else float(p["region_half_width"])
    region = stadium_mask(grid, a, b, hw)
    return DoughScene(
        kind="press",
        world_cfg=cfg,
        points=pts,
        pvol=pvol,
        anchor=np.asarray(anchor, float),
        grid=grid,
        masks={"region": region},
        info={"press_a_x": a[0], "press_a_y": a[1], "press_b_x": b[0], "press_b_y": b[1]},
    )


def tray_boxes(inner_xy, wall_h: float, wall_t: float = 0.006, floor_t: float = 0.01, mu: float = 0.6) -> List[dict]:
    """Static boxes of an open shallow tray centred on the anchor: floor top at z = 0, four walls ``wall_h`` high."""
    hx, hy = 0.5 * inner_xy[0], 0.5 * inner_xy[1]
    boxes = [{"center": [0, 0, -0.5 * floor_t], "half": [hx + wall_t, hy + wall_t, 0.5 * floor_t], "mu": mu}]
    for sx, sy, ex, ey in (
        (1, 0, 0.5 * wall_t, hy + wall_t),
        (-1, 0, 0.5 * wall_t, hy + wall_t),
        (0, 1, hx, 0.5 * wall_t),
        (0, -1, hx, 0.5 * wall_t),
    ):
        boxes.append(
            {
                "center": [sx * (hx + 0.5 * wall_t), sy * (hy + 0.5 * wall_t), 0.5 * wall_h],
                "half": [ex, ey, 0.5 * wall_h],
                "mu": mu,
            }
        )
    return boxes


def make_fill_scene(p: dict, anchor, rng: Optional[np.random.Generator] = None) -> DoughScene:
    """``dough_fill_tray``: dough heaped on one side of an open shallow tray; a scraper spreads and levels it.

    Nominal scene (no randomisation): ``side`` (+1: heap on the +x side), ``init_frac`` (heap length as a fraction of the tray
    length), ``blob_height``, ``blob_width_frac``, ``heap_dy`` (lateral offset of the heap, clipped to the walls)."""
    rng = np.random.default_rng(0) if rng is None else rng
    voxel = float(p.get("voxel", 0.005))
    inner = np.asarray(p.get("tray_inner", [0.16, 0.10]), float)
    wall_h = float(p.get("wall_h", 0.02))
    side = float(p.get("side", 1.0))  # +1: dough on the +x side, -1: on the -x side
    frac = float(p.get("init_frac", 0.4))  # the dough block spans this fraction of the tray length
    bh = float(p.get("blob_height", 0.02))
    size_x = frac * inner[0]
    size_y = float(p.get("blob_width_frac", 0.9)) * inner[1]
    cx = side * (0.5 * inner[0] - 0.5 * size_x - 0.003)
    cy = float(
        np.clip(float(p.get("heap_dy", 0.0)), -0.5 * (inner[1] - size_y), 0.5 * (inner[1] - size_y))
    )  # the heap stays inside the walls
    blob = {"type": "box", "center": [cx, cy, 0.0003], "size": [size_x, size_y, bh]}
    pts, pvol = ds.blob_points(blob, voxel, int(p.get("ppc", 2)), int(rng.integers(1 << 30)))
    vol = len(pts) * pvol
    level = vol / float(inner[0] * inner[1])  # level of the dough when it fills the tray evenly
    scraper = tl.tool_spec("scraper_tool", "tool", mu=p.get("tool_mu"))
    cfg = {
        "material": p.get("material", "dough"),
        "voxel": voxel,
        "dt": float(p.get("dt", 1.0 / 30.0)),
        "substeps": int(p.get("substeps", 1)),
        "iterations": int(p.get("iterations", 40)),
        "collider_margin": float(p.get("collider_margin", voxel)),
        "boxes": tray_boxes(inner, wall_h, float(p.get("wall_t", 0.006))),
        "tools": [scraper],
        "bounds": p.get(
            "bounds",
            [
                [-0.5 * inner[0] - 0.03, -0.5 * inner[1] - 0.03, -0.02],
                [0.5 * inner[0] + 0.03, 0.5 * inner[1] + 0.03, 0.09],
            ],
        ),
        "ground": False,
    }
    grid = dm.HeightGrid(lo=(-0.1, -0.1), nx=50, ny=50, dx=0.004, z0=0.0)
    tray = grid.box_mask((-0.5 * inner[0], -0.5 * inner[1]), (0.5 * inner[0], 0.5 * inner[1]))
    # the under-filled region: the tray cells with (almost) no dough at the start
    under = tray & (dm.column_top(pts, grid) < 0.35 * level)
    return DoughScene(
        kind="fill",
        world_cfg=cfg,
        points=pts,
        pvol=pvol,
        anchor=np.asarray(anchor, float),
        grid=grid,
        masks={"tray": tray, "under": under},
        info={
            "fill_level": level,
            "volume": vol,
            "side": side,
            "inner_x": inner[0],
            "inner_y": inner[1],
            "heap_cy": cy,
        },
    )
