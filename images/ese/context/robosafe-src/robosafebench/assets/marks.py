"""Printed marks as geometry: scale lines and numerals laid out in a plane and put on a flat face or around a cylinder.

A layout is a list of rectangles `(s, h, width, height)` in millimetres, `s` to the right and `h` up as a reader sees
them. Numerals use the bitmap font of `display.py`; lit dots in a row are joined into one rectangle. Every rectangle
becomes a thin closed box, and all boxes of a layout are merged into one mesh (one geom, one draw call).
"""
from __future__ import annotations

import math
from typing import Sequence

import numpy as np

from . import display
from . import mesh as M

Rect = tuple[float, float, float, float]


def text_rects(text: str, pitch: float, s0: float = 0.0, h0: float = 0.0) -> list[Rect]:
    """Rectangles for one line of text whose lower left corner is at (s0, h0); a dot is `pitch` square."""
    out: list[Rect] = []
    for i, ch in enumerate(text):
        g = display.glyph(ch)
        for row in range(display.GLYPH_H):
            col = 0
            while col < display.GLYPH_W:
                if g[row, col]:
                    run = 1
                    while col + run < display.GLYPH_W and g[row, col + run]:
                        run += 1
                    out.append((s0 + (i * display.CELL_W + col) * pitch, h0 + (display.GLYPH_H - 1 - row) * pitch, run * pitch, pitch))
                    col += run
                else:
                    col += 1
    return out


def text_width(text: str, pitch: float) -> float:
    return (len(text) * display.CELL_W - 1) * pitch


def text_height(pitch: float) -> float:
    return display.GLYPH_H * pitch


def on_plane(rects: Sequence[Rect], thick: float, rot: np.ndarray | None = None, pos: Sequence[float] = (0.0, 0.0, 0.0)) -> M.Mesh:
    """Boxes standing on the plane z = 0 (s along +x, h along +y), then rotated and moved."""
    parts = [M.box((w, hh, thick), (s + w / 2.0, h + hh / 2.0, thick / 2.0)) for s, h, w, hh in rects]
    m = M.merge(parts)
    return m.transformed(np.eye(3) if rot is None else rot, pos)


def on_cylinder(rects: Sequence[Rect], radius: float, phi0: float, z0: float, thick: float, max_arc: float = 0.14) -> M.Mesh:
    """Boxes on the outside of a vertical cylinder. `s = 0` is at azimuth `phi0`; text reads upright from outside."""
    parts = []
    for s, h, w, hh in rects:
        n = max(1, int(math.ceil(w / (radius * max_arc))))
        for k in range(n):
            sc = s + (k + 0.5) * w / n
            phi = phi0 + sc / radius
            c, sn = math.cos(phi), math.sin(phi)
            rot = np.array([[c, -sn, 0.0], [sn, c, 0.0], [0.0, 0.0, 1.0]])
            r = radius + thick / 2.0 - 0.03
            parts.append(M.box((thick, w / n * 1.02, hh)).transformed(rot, (r * c, r * sn, z0 + h + hh / 2.0)))
    return M.merge(parts)
