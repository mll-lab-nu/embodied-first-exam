"""Shared procedural diffuse images, independent of physical materials.

Fabric weave, grid/stripe patterns and corner marks use explicit dimensions,
colours and a seed. The generator returns uint8 RGB and can write the identical
PNG as an episode asset; World owns conversion to a Genesis surface. No engine
initialization, download or simulation is performed here.
"""

from __future__ import annotations

from pathlib import Path

import numpy as np


def fabric_weave(
    *,
    color,
    size_m,
    pattern: str = "plain",
    accent_color=None,
    stripe_pitch_m: float = 0.030,
    corner_colors=None,
    corner_size_m: float = 0.0,
    thread_pitch_m: float = 0.002,
    pixels_per_thread: int = 8,
    thread_shading: float = 0.45,
    weft_tint: float = 0.94,
    fibre_noise: float = 0.05,
    cloud_noise: float = 0.08,
    seed: int = 0,
    preview_path: Path | None = None,
) -> np.ndarray:
    """Paint a plain-weave sheet. Returns an ``(H, W, 3)`` uint8 array.

    ``preview_path`` optionally writes the same image as PNG. It can be inspected
    without rendering or referenced by an entity as a generated texture asset.

    ``size_m`` is the cloth's real extent and ``thread_pitch_m`` the spacing
    between neighbouring threads, so the weave's on-screen scale is physical
    rather than arbitrary. 2 mm is coarser than real fabric on purpose: at the
    camera distance these scenes use, a real 0.3 mm weave lands under a pixel and
    turns into grey mush or moire, and a weave that cannot be resolved is worth
    nothing. This is the apparent scale a photograph at this distance would show.

    Plain weave means each thread passes over one and under the next, so which of
    the two directions is on top flips every cell -- that alternation, not the
    colour, is what makes a surface read as woven.

    ``pattern="stripes"`` bands ``accent_color`` across ``color`` every
    ``stripe_pitch_m``. Worth having for more than looks: a fold is hard to read
    in a video of a plain sheet, because a folded half looks like the half it
    landed on. With stripes the two halves visibly meet, and a sheet that has
    been dragged or bunched shows it in the pattern rather than only in the
    numbers.

    ``corner_colors`` paints a square patch of its own colour into each of the
    four corners, over whatever ``pattern`` produced; ``corner_size_m`` is how
    far the patch reaches along each of the two edges that meet there. This is
    what lets an instruction name a corner without a direction word: "the red
    corner" means the same thing from every camera position, while "the far left
    corner" does not. Orthogonal to ``pattern``, so the stripes stay.
    """

    size_m = np.asarray(size_m, dtype=float)
    threads = np.maximum(4, np.round(size_m / float(thread_pitch_m)).astype(int))
    pixels = np.maximum(16, threads * int(pixels_per_thread))
    rng = np.random.default_rng(int(seed))

    # Which cell each pixel is in, and where inside that cell it sits.
    cell_u, frac_u = _cells(pixels[0], threads[0])
    cell_v, frac_v = _cells(pixels[1], threads[1])
    cell_x, cell_y = np.meshgrid(cell_u, cell_v, indexing="xy")
    frac_x, frac_y = np.meshgrid(frac_u, frac_v, indexing="xy")

    # Plain weave: the warp is the visible one on every other cell.
    warp_on_top = ((cell_x + cell_y) % 2) == 0
    # A thread's cross-section, faked. Bright along the middle, falling off to
    # the sides -- the cue a normal map would carry if this renderer had one.
    round_x = np.cos(np.pi * (frac_x - 0.5))
    round_y = np.cos(np.pi * (frac_y - 0.5))
    shade = 1.0 - float(thread_shading) * (
        1.0 - np.where(warp_on_top, round_x, round_y)
    )
    # One direction slightly darker than the other, as a real fabric's warp and
    # weft are: it stops the two sets of threads reading as one grid.
    shade = shade * np.where(warp_on_top, 1.0, float(weft_tint))

    # Fibre: per-pixel grain. Cloud: a slow wash so the sheet is not uniform
    # across its whole area, which is most of what makes flat colour look moulded.
    shade = shade * (1.0 + float(fibre_noise) * rng.standard_normal(shade.shape))
    shade = shade * (
        1.0 + float(cloud_noise) * _smooth_noise(shade.shape, rng, octaves=3)
    )

    # The renderer multiplies the texture by a white diffuse, so the image's own
    # colours ARE the final colours -- the surface's `color` stops mattering once
    # a texture is attached, and the tint has to be baked here.
    base = _base_colour(
        shade.shape,
        color=color,
        pattern=pattern,
        accent_color=accent_color,
        stripe_pitch_m=stripe_pitch_m,
        size_m=size_m,
    )
    if corner_colors is not None and float(corner_size_m) > 0.0:
        base = _paint_corners(
            base, corner_colors, corner_size_m=corner_size_m, size_m=size_m
        )
    image = np.clip(shade[..., None] * base, 0.0, 1.0)
    rgb = (image * 255.0 + 0.5).astype(np.uint8)
    if preview_path is not None:
        _write_png(Path(preview_path), rgb)
    return rgb


def _base_colour(shape, *, color, pattern, accent_color, stripe_pitch_m, size_m):
    """Per-pixel colour before the weave's shading is applied."""

    base = np.asarray([float(channel) for channel in color], dtype=float)
    field = np.broadcast_to(base, (*shape, 3)).copy()
    if pattern == "plain":
        return field
    if pattern not in ("stripes", "grid"):
        raise ValueError(f"pattern must be 'plain', 'stripes' or 'grid', got {pattern!r}.")
    if accent_color is None:
        raise ValueError(f"pattern={pattern!r} needs accent_color.")

    accent = np.asarray([float(channel) for channel in accent_color], dtype=float)
    # Bands run along one axis at a physical pitch, so their width on screen is
    # set in millimetres like everything else here rather than in pixels.
    size = np.asarray(size_m, dtype=float)
    position_v = np.linspace(0.0, float(size[1]), shape[0], endpoint=False)
    band_v = (np.floor(position_v / float(stripe_pitch_m)).astype(int) % 2) == 1
    if pattern == "stripes":
        field[band_v, :, :] = accent
        return field
    # ``grid``: the same bands along BOTH texture axes, drawn as lines rather
    # than filled cells so the sheet still reads as one colour. A crease running
    # along the stripes of a one-axis pattern leaves no mark on it; a grid is cut
    # by a crease in either direction, which is what a sheet folded once each
    # way (cloth_unpleat's cross) needs to show both folds.
    position_u = np.linspace(0.0, float(size[0]), shape[1], endpoint=False)
    band_u = (np.floor(position_u / float(stripe_pitch_m)).astype(int) % 2) == 1
    line_v = np.diff(band_v.astype(int), prepend=band_v[0]) != 0
    line_u = np.diff(band_u.astype(int), prepend=band_u[0]) != 0
    thick = max(1, shape[0] // 400)      # ~1/400 of the sheet: hairline, not a stripe
    for k in range(thick):
        field[np.roll(line_v, k), :, :] = accent
        field[:, np.roll(line_u, k), :] = accent
    return field


def _paint_corners(field, corner_colors, *, corner_size_m, size_m):
    """Paint a square patch of its own colour into each of the sheet's corners.

    ``corner_colors`` is a 2x2 nesting indexed ``[v][u]``, index 0 meaning the
    LOW end of that texture axis -- so ``corner_colors[0][0]`` is the patch at
    (u minimum, v minimum). Which world corner each of the four is depends on
    how the mesh laid out its UVs, so that mapping is the caller's business,
    not this module's.

    Rows run along v and columns along u (`fabric_weave` builds them that way),
    but the renderer reads v from the BOTTOM of the image upwards: trimesh's UV
    lookup flips it, so v = 0 lands on the LAST row of the array rather than the
    first. Everything else here is symmetric in v -- the weave and the stripes
    both are -- so this is the first place in the module where the flip shows,
    and it is handled here once rather than at every call site.
    """

    field = np.asarray(field, dtype=float)
    height, width = field.shape[0], field.shape[1]
    span = np.asarray(size_m, dtype=float)
    # Patch extent in pixels, at least one so a small patch never vanishes.
    rows = max(1, min(height // 2, int(round(float(corner_size_m) / float(span[1]) * height))))
    cols = max(1, min(width // 2, int(round(float(corner_size_m) / float(span[0]) * width))))
    # v index 0 is the array's last rows (see the docstring's flip note).
    row_slices = (slice(height - rows, height), slice(0, rows))
    col_slices = (slice(0, cols), slice(width - cols, width))
    for v_index, row_slice in enumerate(row_slices):
        for u_index, col_slice in enumerate(col_slices):
            patch = corner_colors[v_index][u_index]
            if patch is None:
                continue
            field[row_slice, col_slice, :] = np.asarray(
                [float(channel) for channel in patch], dtype=float
            )
    return field


def _cells(pixels: int, threads: int):
    """Per-pixel (cell index, position within the cell) along one axis."""

    position = (np.arange(int(pixels)) + 0.5) * (float(threads) / float(pixels))
    return np.floor(position).astype(int), position % 1.0


def _smooth_noise(shape, rng, *, octaves: int = 3) -> np.ndarray:
    """Zero-mean low-frequency noise, by upsampling a few coarse grids.

    Bilinear upsampling of small random grids rather than a real gradient noise:
    a handful of octaves is enough for "the sheet is not perfectly even", and it
    keeps this module to NumPy.
    """

    total = np.zeros(shape, dtype=float)
    weight = 0.0
    for octave in range(max(1, int(octaves))):
        cells = 2 ** (octave + 2)
        coarse = rng.standard_normal((cells, cells))
        amplitude = 0.5**octave
        total += amplitude * _bilinear(coarse, shape)
        weight += amplitude
    total /= max(weight, 1e-9)
    return total - float(total.mean())


def _bilinear(source: np.ndarray, shape) -> np.ndarray:
    rows = np.linspace(0, source.shape[0] - 1, shape[0])
    cols = np.linspace(0, source.shape[1] - 1, shape[1])
    r0 = np.floor(rows).astype(int)
    c0 = np.floor(cols).astype(int)
    r1 = np.minimum(r0 + 1, source.shape[0] - 1)
    c1 = np.minimum(c0 + 1, source.shape[1] - 1)
    dr = (rows - r0)[:, None]
    dc = (cols - c0)[None, :]
    top = source[np.ix_(r0, c0)] * (1 - dc) + source[np.ix_(r0, c1)] * dc
    bottom = source[np.ix_(r1, c0)] * (1 - dc) + source[np.ix_(r1, c1)] * dc
    return top * (1 - dr) + bottom * dr


def _write_png(path: Path, rgb: np.ndarray) -> None:
    from PIL import Image

    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    Image.fromarray(rgb, mode="RGB").save(path, format="PNG", optimize=True)
