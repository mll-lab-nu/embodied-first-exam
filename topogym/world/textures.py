"""Procedurally generated diffuse textures (module A's companion).

`materials.py` owns the finish, this owns the surface detail. They are separate
because of what the renderer keeps: Genesis' rasterizer honours a surface's
diffuse colour and diffuse TEXTURE and discards roughness, metallic, normal and
emissive, which are raytracer-only -- and the raytracer needs a LuisaRender build
this install does not have (`docs/develop/visual/photorealism_workstream_zh.md`
§2). So a diffuse image is the ONLY channel through which an object can be given
any surface detail, and everything that would normally live in a normal map has
to be painted into it.

That is why `fabric_weave` shades each thread rather than drawing flat stripes:
the light-centre-dark-edge gradient across a thread is the roundness cue a normal
map would otherwise carry, and without it a weave reads as a checkerboard.

Generated rather than photographed: nothing to download, no licence to track, no
binary in the repository, any resolution, and the parameters are open -- which is
what a per-episode "different cloth every time" randomisation would need later.

Returned as an array rather than written to a file: `gs.textures.ImageTexture`
takes `image_array` directly, so there is no file to cache, stale or fail to find.
The dtype is uint8 because the renderer asserts exactly that
(`genesis/utils/mesh.py surface_uvs_to_trimesh_visual`).
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

    ``preview_path`` writes the same image out as a PNG as well, for looking at
    without a render. Nothing in the pipeline reads it.

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
    if pattern != "stripes":
        raise ValueError(f"pattern must be 'plain' or 'stripes', got {pattern!r}.")
    if accent_color is None:
        raise ValueError("pattern='stripes' needs accent_color.")

    accent = np.asarray([float(channel) for channel in accent_color], dtype=float)
    # Bands run along one axis at a physical pitch, so their width on screen is
    # set in millimetres like everything else here rather than in pixels.
    span = float(np.asarray(size_m, dtype=float)[1])
    position = np.linspace(0.0, span, shape[0], endpoint=False)
    band = (np.floor(position / float(stripe_pitch_m)).astype(int) % 2) == 1
    field[band, :, :] = accent
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
