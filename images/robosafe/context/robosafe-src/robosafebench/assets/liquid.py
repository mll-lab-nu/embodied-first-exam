"""The drawn fill of a generated vessel.

A vessel built with `Kit.round_vessel`, `Kit.box_vessel` or `Kit.fill` has a geom `liquid` (invisible when empty) and
a custom numeric of the same name that holds the inside outline. `show` redraws the fill at a new level. It changes a
drawn geom of the model only; nothing the physics reads.
"""
from __future__ import annotations

import numpy as np


def has_fill(model, name: str, geom: str = "liquid") -> bool:
    import mujoco

    return mujoco.mj_name2id(model, mujoco.mjtObj.mjOBJ_GEOM, f"{name}/{geom}") >= 0


def show(model, data, name: str, level_mm: float, rgba=None, geom: str = "liquid") -> float:
    """Draw the fill of object `name` up to `level_mm` above the inside bottom (clamped to the depth). Returns the
    level drawn, in millimetres. `rgba` changes the colour; a level of 0 hides the fill."""
    g = model.geom(f"{name}/{geom}")
    spec = np.asarray(model.numeric(f"{name}/{geom}").data, dtype=np.float64)
    z_bottom, n = float(spec[0]), int(round(spec[1]))
    level = max(0.0, float(level_mm) * 1e-3)
    pos = np.array(g.pos, dtype=np.float64)
    if n == 0:                                                    # a rectangular tub: the surface is a slab that moves
        depth = float(spec[4])
        level = min(level, depth)
        pos[2] = z_bottom + max(level, 0.001)
    else:
        outline = spec[2:2 + 2 * n].reshape(n, 2)
        level = min(level, float(outline[-1, 1]))
        shown = max(level, 0.0005)
        r = float(np.interp(shown / 2.0, outline[:, 1], outline[:, 0])) - 0.0003
        g.size = [r, shown / 2.0, 0.0]
        pos[2] = z_bottom + shown / 2.0
        g.rbound = float(np.linalg.norm(g.size))
    g.pos = pos
    colour = np.array(g.rgba, dtype=np.float64) if rgba is None else np.asarray(rgba, dtype=np.float64)
    if rgba is None and level > 0 and colour[3] == 0.0:
        colour[3] = 0.45
    if level <= 0:
        colour[3] = 0.0
    g.rgba = colour
    return level * 1e3
