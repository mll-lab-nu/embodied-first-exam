"""Instrument displays: a small bitmap font drawn for this project, a text rasteriser, and `paint`.

`paint(model, name, text_lines)` writes text into the 2-D texture of a display at run time. The glyphs are 5 x 7 dots
on a 6 x 9 cell; lower-case letters are drawn as capitals.
"""
from __future__ import annotations

from typing import Sequence

import numpy as np

GLYPH_W, GLYPH_H = 5, 7
CELL_W, CELL_H = 6, 9

_GLYPHS = {
    " ": "...../...../...../...../...../...../.....",
    "A": ".###./#...#/#...#/#####/#...#/#...#/#...#",
    "B": "####./#...#/#...#/####./#...#/#...#/####.",
    "C": ".###./#...#/#..../#..../#..../#...#/.###.",
    "D": "####./#...#/#...#/#...#/#...#/#...#/####.",
    "E": "#####/#..../#..../####./#..../#..../#####",
    "F": "#####/#..../#..../####./#..../#..../#....",
    "G": ".###./#...#/#..../#.###/#...#/#...#/.###.",
    "H": "#...#/#...#/#...#/#####/#...#/#...#/#...#",
    "I": ".###./..#../..#../..#../..#../..#../.###.",
    "J": "..###/...#./...#./...#./...#./#..#./.##..",
    "K": "#...#/#..#./#.#../##.../#.#../#..#./#...#",
    "L": "#..../#..../#..../#..../#..../#..../#####",
    "M": "#...#/##.##/#.#.#/#.#.#/#...#/#...#/#...#",
    "N": "#...#/##..#/#.#.#/#..##/#...#/#...#/#...#",
    "O": ".###./#...#/#...#/#...#/#...#/#...#/.###.",
    "P": "####./#...#/#...#/####./#..../#..../#....",
    "Q": ".###./#...#/#...#/#...#/#.#.#/#..#./.##.#",
    "R": "####./#...#/#...#/####./#.#../#..#./#...#",
    "S": ".####/#..../#..../.###./....#/....#/####.",
    "T": "#####/..#../..#../..#../..#../..#../..#..",
    "U": "#...#/#...#/#...#/#...#/#...#/#...#/.###.",
    "V": "#...#/#...#/#...#/#...#/#...#/.#.#./..#..",
    "W": "#...#/#...#/#...#/#.#.#/#.#.#/##.##/#...#",
    "X": "#...#/#...#/.#.#./..#../.#.#./#...#/#...#",
    "Y": "#...#/#...#/.#.#./..#../..#../..#../..#..",
    "Z": "#####/....#/...#./..#../.#.../#..../#####",
    "0": ".###./#...#/#..##/#.#.#/##..#/#...#/.###.",
    "1": "..#../.##../..#../..#../..#../..#../.###.",
    "2": ".###./#...#/....#/...#./..#../.#.../#####",
    "3": ".###./#...#/....#/..##./....#/#...#/.###.",
    "4": "...#./..##./.#.#./#..#./#####/...#./...#.",
    "5": "#####/#..../####./....#/....#/#...#/.###.",
    "6": ".###./#..../#..../####./#...#/#...#/.###.",
    "7": "#####/....#/...#./..#../..#../..#../..#..",
    "8": ".###./#...#/#...#/.###./#...#/#...#/.###.",
    "9": ".###./#...#/#...#/.####/....#/....#/.###.",
    ".": "...../...../...../...../...../.##../.##..",
    ",": "...../...../...../...../.##../..#../.#...",
    ":": "...../.##../.##../...../.##../.##../.....",
    ";": "...../.##../.##../...../.##../..#../.#...",
    "-": "...../...../...../.###./...../...../.....",
    "+": "...../..#../..#../#####/..#../..#../.....",
    "/": "....#/....#/...#./..#../.#.../#..../#....",
    "\\": "#..../#..../.#.../..#../...#./....#/....#",
    "%": "##..#/##..#/...#./..#../.#.../#..##/#..##",
    "(": "...#./..#../.#.../.#.../.#.../..#../...#.",
    ")": ".#.../..#../...#./...#./...#./..#../.#...",
    "[": ".###./.#.../.#.../.#.../.#.../.#.../.###.",
    "]": ".###./...#./...#./...#./...#./...#./.###.",
    "=": "...../...../#####/...../#####/...../.....",
    "<": "...#./..#../.#.../#..../.#.../..#../...#.",
    ">": ".#.../..#../...#./....#/...#./..#../.#...",
    "!": "..#../..#../..#../..#../..#../...../..#..",
    "?": ".###./#...#/....#/...#./..#../...../..#..",
    "_": "...../...../...../...../...../...../#####",
    "#": ".#.#./.#.#./#####/.#.#./#####/.#.#./.#.#.",
    "*": "...../#.#.#/.###./#####/.###./#.#.#/.....",
    "'": "..#../..#../.#.../...../...../...../.....",
    '"': ".#.#./.#.#./.#.#./...../...../...../.....",
    "°": ".##../#..#./#..#./.##../...../...../.....",          # degree sign
    "µ": "...../...../#...#/#...#/#..##/###.#/#....",          # micro sign
    "|": "..#../..#../..#../..#../..#../..#../..#..",
    "^": "..#../.#.#./#...#/...../...../...../.....",
    "~": "...../...../.#.../#.#.#/...#./...../.....",
}


def _bitmap(ch: str) -> np.ndarray:
    g = _GLYPHS.get(ch)
    if g is None:
        g = _GLYPHS.get(ch.upper(), _GLYPHS["?"])
    return np.array([[c == "#" for c in row] for row in g.split("/")], dtype=bool)


_BITMAPS: dict[str, np.ndarray] = {}


def glyph(ch: str) -> np.ndarray:
    """A (7, 5) boolean bitmap."""
    if ch not in _BITMAPS:
        _BITMAPS[ch] = _bitmap(ch)
    return _BITMAPS[ch]


def text_mask(text: str, scale: int = 1) -> np.ndarray:
    """A boolean image of one line of text: height 9 x scale, width 6 x scale per character."""
    out = np.zeros((CELL_H, CELL_W * max(len(text), 1)), dtype=bool)
    for i, ch in enumerate(text):
        out[1:1 + GLYPH_H, i * CELL_W:i * CELL_W + GLYPH_W] = glyph(ch)
    return np.kron(out, np.ones((scale, scale), dtype=bool)) if scale > 1 else out


def draw_text(image: np.ndarray, x: int, y: int, text: str, scale: int = 1, color: Sequence[int] = (255, 255, 255)) -> None:
    """Draw one line with its top-left corner at pixel (x, y); parts outside the image are clipped."""
    m = text_mask(text, scale)
    h, w = image.shape[:2]
    y0, x0 = max(y, 0), max(x, 0)
    y1, x1 = min(y + m.shape[0], h), min(x + m.shape[1], w)
    if y1 <= y0 or x1 <= x0:
        return
    sub = m[y0 - y:y1 - y, x0 - x:x1 - x]
    image[y0:y1, x0:x1][sub] = np.asarray(color, dtype=np.uint8)


def text_image(lines: Sequence[str], width: int, height: int, fg: Sequence[int] = (130, 255, 170),
               bg: Sequence[int] = (8, 20, 14), margin: int = 2) -> np.ndarray:
    """An RGB image of the lines, left-aligned, at the largest whole-number scale that fits."""
    lines = [str(s) for s in lines] or [""]
    cols = max(max(len(s) for s in lines), 1)
    scale = max(1, min((width - 2 * margin) // (CELL_W * cols), (height - 2 * margin) // (CELL_H * len(lines))))
    img = np.empty((height, width, 3), dtype=np.uint8)
    img[:] = np.asarray(bg, dtype=np.uint8)
    block = CELL_H * scale * len(lines)
    y = max((height - block) // 2, 0)
    for s in lines:
        draw_text(img, margin + scale, y, s, scale, fg)
        y += CELL_H * scale
    return img


def paint(model, name: str, text_lines: Sequence[str], fg: Sequence[int] = (130, 255, 170), bg: Sequence[int] = (8, 20, 14)) -> np.ndarray:
    """Write text into the texture of a display (`name` is the texture name, e.g. `display` or `balance/display`).

    Changes `model.tex_data` in place and returns the image that was written (row 0 at the top). A renderer made
    before the call keeps the old picture until the texture is uploaded again: see `upload`, or use
    `embodied_safety_exam.assets.render.render`, which always draws the current texture.
    """
    import mujoco

    tid = mujoco.mj_name2id(model, mujoco.mjtObj.mjOBJ_TEXTURE, name)
    if tid < 0:
        raise KeyError(f"no display texture named {name!r}")
    w, h, c = int(model.tex_width[tid]), int(model.tex_height[tid]), int(model.tex_nchannel[tid])
    img = text_image(text_lines, w, h, fg, bg)
    adr = int(model.tex_adr[tid])
    buf = img[::-1]                                         # texture row 0 is the bottom of the panel
    if c == 4:
        buf = np.concatenate([buf, np.full((h, w, 1), 255, dtype=np.uint8)], axis=2)
    elif c != 3:
        raise ValueError(f"display texture {name!r} has {c} channels")
    model.tex_data[adr:adr + w * h * c] = buf.reshape(-1)
    return img


def upload(model, renderer, name: str) -> None:
    """Send a repainted display texture to an existing `mujoco.Renderer`."""
    import mujoco

    tid = mujoco.mj_name2id(model, mujoco.mjtObj.mjOBJ_TEXTURE, name)
    ctx = getattr(renderer, "_mjr_context", None)
    if tid < 0 or ctx is None:
        raise KeyError(f"cannot upload display texture {name!r}")
    mujoco.mjr_uploadTexture(model, ctx, tid)
