"""Measure authored glyph ink on an original camera raster; this is not OCR.

UV character cells come from the font/layout that drew the label. A cell does not identify its character from
the image. Native image pixels must resolve its ink in both directions, including after shear or minification.
"""
from __future__ import annotations

import numpy as np

INK_CONTRAST = 32.0       # minimum foreground/background separation in the original 8-bit RGB raster
INK_WIDTH_PX = 2.0       # at least two native pixel cells across the ink, perpendicular to its cap direction
INK_HEIGHT_PX = 4.0      # calibrated native ink support, normal to the baseline; not nominal font cap height
INK_MASS_PX = 10.0       # integrated foreground contrast, in full-contrast native pixel equivalents
INK_GAP_PX = 1.0         # gap between closed unit native foreground pixel cells of neighbouring glyphs


def measure(image, cells, foreground, background, height_floor=INK_HEIGHT_PX):
    """Per-glyph native ink support; cells contain actual visible (u,v) pixels and projected text axes.

    Height is measured normal to the baseline, width normal to the cap direction. Long slanted edges do not
    substitute for either dimension. Pixel cells have their original unit square footprint; no resizing occurs.
    """
    direction = np.asarray(foreground, dtype=float) - np.asarray(background, dtype=float)
    norm = float(np.linalg.norm(direction))
    if norm < INK_CONTRAST:
        return {"readable": 0.0, "contrast": 0.0, "glyphs": []}
    direction /= norm
    pixels = sorted({tuple(p) for cell in cells for p in cell["pixels"]})
    if not pixels:
        return {"readable": 0.0, "contrast": 0.0, "glyphs": []}
    values = np.asarray([image[v, u, :3] for u, v in pixels], dtype=float) @ direction
    lo, hi = float(np.min(values)), float(np.max(values))
    contrast = hi - lo
    # A uniform card or shadow cannot obtain credit from authored text alone.
    if contrast < INK_CONTRAST:
        return {"readable": 0.0, "contrast": round(contrast, 2), "glyphs": []}
    boundary = (lo + hi) / 2.0
    rows, ink_points = [], []
    for cell in cells:
        xy = np.asarray(cell["pixels"], dtype=float).reshape(-1, 2)
        intensities = np.asarray([image[int(v), int(u), :3] for u, v in xy], dtype=float).reshape(-1, 3) @ direction
        alpha = np.clip((intensities - lo) / contrast, 0.0, 1.0)
        fg = intensities >= boundary
        ink = xy[fg]
        ink_points.append(ink)
        baseline, cap = np.asarray(cell["baseline"]), np.asarray(cell["cap"])
        cap_normal = np.asarray([-baseline[1], baseline[0]]) / max(float(np.linalg.norm(baseline)), 1e-12)
        base_normal = np.asarray([-cap[1], cap[0]]) / max(float(np.linalg.norm(cap)), 1e-12)

        def span(axis):
            return float(np.ptp(ink @ axis) + np.abs(axis).sum()) if len(ink) else 0.0

        height, width = span(cap_normal), span(base_normal)
        mass = float(alpha.sum())
        enough = bool(height >= height_floor and width >= INK_WIDTH_PX and mass >= INK_MASS_PX)
        rows.append({"height_px": round(height, 2), "width_px": round(width, 2), "ink_pixels": len(ink),
                     "ink_mass_px": round(mass, 3), "visible_pixels": len(xy), "readable": enough})
    occupied = [set(map(tuple, points.astype(int))) for points in ink_points]
    gaps = {}
    for i in range(len(rows) - 1):
        a, b = occupied[i], occupied[i + 1]
        if not a or not b:
            gaps[i] = 0.0
            continue
        if len(a) > len(b):
            a, b = b, a
        # Integer unit foreground pixel squares have gap < 1 iff two centres are 8-neighbours (or equal).
        # A linear bounded membership check avoids a quadratic, potentially many-gigabyte pairwise array.
        touching = any((u + du, v + dv) in b for u, v in a for du in (-1, 0, 1) for dv in (-1, 0, 1))
        gaps[i] = 0.0 if touching else INK_GAP_PX
    for i, row in enumerate(rows):
        gap = max((gaps[n] for n in (i-1,i) if n in gaps), default=0.0)
        row["adjacent_ink_gap_px"] = gap if len(rows) > 1 else None
        row["adjacent_ink_gap_capped_at_px"] = INK_GAP_PX
        row["readable"] = bool(row["readable"] and (len(rows) == 1 or gap >= INK_GAP_PX))
    return {"readable": round(sum(p["readable"] for p in rows) / max(len(cells), 1), 3),
            "contrast": round(contrast, 2), "glyphs": rows}
