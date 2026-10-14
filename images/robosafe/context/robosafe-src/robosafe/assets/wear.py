"""Wear and occlusion of printed labels and symbols (0.5.0, the tier `partly_legible` of `hazard_hidden`).

A label that is seen and not wholly readable: torn, rubbed off, faded, stained or half covered by a strip of tape.
What is left must still let a careful reader suspect what the label said ("...MABLE", the left half of a biohazard
trefoil), and no more than that. Everything here works on a label image in its reading orientation (x to the right,
y down, as `labels.label_image` returns it) and is deterministic: the same spec gives the same pixels.

A spec is a list of operations (dicts), applied in order. Coordinates are fractions of the image (0 to 1):

| `op` | Keys | What it does |
|---|---|---|
| `tear` | `edge` ((x0, y0), (x1, y1)) or `keep_x` (a, b) / `keep_y` (a, b); `ragged`, `seed` | the paper is torn off, down to the pale residue stuck to the thing, on one side of the directed `edge` (of an edge drawn from top to bottom, the part to its right in the image); `keep_x` keeps a vertical strip, `keep_y` a horizontal one |
| `rub` | `box` (x0, y0, x1, y1), `strength` (0-1), `grain`, `seed` | the print rubbed off in streaks along x inside `box` (soft, ragged border): what handling does to a label |
| `fade` | `strength` (0-1), `box` | the print faded towards the paper (sun, cleaning): less contrast, the same shapes |
| `stain` | `at` (x, y), `r` (rx, ry), `color`, `alpha`, `seed` | an irregular blot over the print, darker at its rim (grime, a dried spill) |
| `cover` | `box`, `color`, `angle` (degrees) | an opaque strip over the print (tape, a price sticker) |

A sentence that says what is left of a worn label names the damage with the words of `WORDS` (torn, worn, faded,
stained, covered): `words(spec)`.

Measures (how much is left; docs/hidden/hidden-c.md has the numbers for each family):

- `kept_share(intact, worn, bg, paper)`: the share of the intact print's ink pixels that still read: they stand out
  from the worn paper around them by at least half as much as they stood out from the intact paper (`kept`).
- `text_kept(lines, pictograms, size_px, style, spec)`: per printed line the characters that are still legible
  (a character counts when at least `CHAR_KEPT` of its ink is intact) and the fragment a reader sees ("ETH..."), and
  per pictogram the share of it that is left.
- `score(kind, params, intact_params, index)`: the benchmark's own legibility measure (`preview.label_score`: a
  640 x 480 camera with the wrist camera's field of view 25 cm in front of the label) on the worn label, and
  `match_intact`, the correlation of that picture with the intact print, beside the same for the intact label: the
  worn label's `relative` legibility is the ratio of the two.
- `cap_px(world, at, cap_height, camera)`: how tall the label's capitals are in a camera's image of the scene.

The asset builders take a spec as `wear=` (`Kit.label_wrap`, `Kit.label_flat`, and the kinds that pass it on); the
label's meta then carries it under `wear`.
"""
from __future__ import annotations

import math
from typing import Sequence

import numpy as np

from . import labels as L

RESIDUE = (214, 206, 188)      # the pale paper left on the thing where a label is torn off (as `labels.tear`)
STREAK = (196, 188, 170)
FIBRE = (240, 238, 232)        # the torn edge of the paper
CHAR_KEPT = 0.6                # a character is legible when this share of its ink is intact
INK_DIST = 60.0                # colour distance from the background at which a pixel is ink
SAME_DIST = 20.0               # a worn pixel this close to the intact one is unchanged
KEPT_FRACTION = 0.5            # ... and one nearer to its intact colour than this share of the way to the paper still reads


# ---- noise ------------------------------------------------------------------------------------------------------------
def _noise(h: int, w: int, cells: tuple[int, int], seed: int) -> np.ndarray:
    """Smooth value noise in [0, 1] of shape (h, w), `cells` = (rows, columns) of the lattice."""
    rng = np.random.default_rng(int(seed) & 0xFFFFFFFF)
    cy, cx = max(1, int(cells[0])), max(1, int(cells[1]))
    g = rng.random((cy + 2, cx + 2))
    ys = np.linspace(0.0, cy, h, endpoint=False)
    xs = np.linspace(0.0, cx, w, endpoint=False)
    y0, x0 = ys.astype(int), xs.astype(int)
    fy, fx = (ys - y0)[:, None], (xs - x0)[None, :]
    fy, fx = fy * fy * (3 - 2 * fy), fx * fx * (3 - 2 * fx)
    a, b = g[y0][:, x0], g[y0][:, x0 + 1]
    c, d = g[y0 + 1][:, x0], g[y0 + 1][:, x0 + 1]
    return (a * (1 - fx) + b * fx) * (1 - fy) + (c * (1 - fx) + d * fx) * fy


def _rgb(c) -> np.ndarray:
    return np.asarray(L.rgb(c) if isinstance(c, str) else tuple(c)[:3], dtype=np.float64)


def _grid(h: int, w: int):
    y = (np.arange(h, dtype=np.float64) + 0.5)[:, None] / h
    x = (np.arange(w, dtype=np.float64) + 0.5)[None, :] / w
    return x, y


# ---- operations ---------------------------------------------------------------------------------------------------------
def _tear_edges(op: dict) -> list:
    if "edge" in op:
        return [tuple(map(tuple, op["edge"]))]
    out = []
    if "keep_x" in op:
        a, b = op["keep_x"]
        if b < 1.0:
            out.append(((b, 0.0), (b, 1.0)))       # gone on the right of x = b (x grows to the right, y down)
        if a > 0.0:
            out.append(((a, 1.0), (a, 0.0)))       # gone on the left of x = a
    if "keep_y" in op:
        a, b = op["keep_y"]
        if b < 1.0:
            out.append(((1.0, b), (0.0, b)))       # gone below y = b
        if a > 0.0:
            out.append(((0.0, a), (1.0, a)))       # gone above y = a
    return out


def _tear(img: np.ndarray, op: dict) -> np.ndarray:
    h, w = img.shape[:2]
    x, y = _grid(h, w)
    ragged = float(op.get("ragged", 0.035))
    seed = int(op.get("seed", 7))
    gone = np.zeros((h, w), dtype=bool)
    near = np.full((h, w), np.inf)
    aspect = w / float(h)
    for k, ((x0, y0), (x1, y1)) in enumerate(_tear_edges(op)):
        dx, dy = (x1 - x0) * aspect, (y1 - y0)
        n = math.hypot(dx, dy) or 1.0
        # signed distance from the edge in units of the image height: the cross product of the edge with the point,
        # negative on the side that is torn off (of an edge drawn downwards, +x)
        s = (dx * (y - y0) - dy * (x - x0) * aspect) / n
        t = ((x - x0) * aspect * dx + (y - y0) * dy) / n                  # position along the edge
        along = t * 40.0
        wob = ragged * (0.55 * np.sin(along * 1.7 + seed) + 0.30 * np.sin(along * 4.1 + 1.3 * seed) + 0.15 * np.sin(along * 9.7 + 0.4))
        wob = wob + ragged * 0.6 * (_noise(h, w, (12, max(2, int(12 * aspect))), seed + k) - 0.5)
        d = s - wob
        gone |= d < 0.0
        near = np.minimum(near, np.abs(d))
    out = img.copy()
    streak = (((np.arange(h) // max(2, h // 60)) % 3) == 0)[:, None] & gone
    out[gone] = RESIDUE
    out[streak] = STREAK
    out[(near < 0.008) & ~gone] = FIBRE
    return out


def _soft_box(h: int, w: int, box, soft: float, seed: int) -> np.ndarray:
    """1 inside `box`, 0 outside, over a ragged border `soft` wide (fractions)."""
    x, y = _grid(h, w)
    x0, y0, x1, y1 = box
    n = (_noise(h, w, (10, 16), seed) - 0.5) * soft * 2.0
    inside = np.minimum.reduce([x - x0 + n, x1 - x + n, y - y0 + n, y1 - y + n])
    return np.clip(0.5 + inside / max(soft, 1e-6), 0.0, 1.0)


def _rub(img: np.ndarray, op: dict, bg: np.ndarray) -> np.ndarray:
    h, w = img.shape[:2]
    seed = int(op.get("seed", 11))
    strength = float(op.get("strength", 0.9))
    grain = float(op.get("grain", 0.06))
    mask = _soft_box(h, w, op.get("box", (0.0, 0.0, 1.0, 1.0)), grain, seed)
    # streaks along x: noise with many rows and few columns, sharpened
    streaks = _noise(h, w, (max(4, h // 6), 3), seed + 1)
    blotch = _noise(h, w, (6, 10), seed + 2)
    amount = np.clip(strength * (0.85 + 0.7 * (streaks - 0.5) + 0.4 * (blotch - 0.5)), 0.0, 1.0) * mask
    a = amount[:, :, None]
    out = img.astype(np.float64) * (1 - a) + bg[None, None, :] * a
    return np.clip(out, 0, 255).astype(np.uint8)


def _fade(img: np.ndarray, op: dict, bg: np.ndarray) -> np.ndarray:
    h, w = img.shape[:2]
    s = float(op.get("strength", 0.5))
    mask = _soft_box(h, w, op["box"], 0.04, int(op.get("seed", 13))) if "box" in op else np.ones((h, w))
    a = (s * mask)[:, :, None]
    out = img.astype(np.float64) * (1 - a) + bg[None, None, :] * a
    return np.clip(out, 0, 255).astype(np.uint8)


def _stain(img: np.ndarray, op: dict) -> np.ndarray:
    h, w = img.shape[:2]
    x, y = _grid(h, w)
    cx, cy = op["at"]
    rx, ry = op.get("r", (0.2, 0.3))
    seed = int(op.get("seed", 17))
    alpha = float(op.get("alpha", 0.85))
    col = _rgb(op.get("color", (120, 84, 46)))
    rr = np.sqrt(((x - cx) / rx) ** 2 + ((y - cy) / ry) ** 2)
    rr = rr + 0.35 * (_noise(h, w, (8, 8), seed) - 0.5)
    inside = rr < 1.0
    rim = (rr > 0.86) & inside
    a = np.where(inside, np.minimum(1.0, alpha * (0.95 + 0.1 * (_noise(h, w, (16, 16), seed + 1) - 0.5))), 0.0)
    a = np.where(rim, np.minimum(1.0, alpha + 0.12), a)[:, :, None]
    tint = np.where(rim[:, :, None], col * 0.82, col)
    out = img.astype(np.float64) * (1 - a) + tint * a
    return np.clip(out, 0, 255).astype(np.uint8)


def _cover(img: np.ndarray, op: dict) -> np.ndarray:
    h, w = img.shape[:2]
    x, y = _grid(h, w)
    x0, y0, x1, y1 = op["box"]
    ang = math.radians(float(op.get("angle", 0.0)))
    cx, cy = (x0 + x1) / 2.0, (y0 + y1) / 2.0
    aspect = w / float(h)
    u = ((x - cx) * aspect * math.cos(ang) + (y - cy) * math.sin(ang)) / aspect
    v = -(x - cx) * aspect * math.sin(ang) + (y - cy) * math.cos(ang)
    inside = (np.abs(u) <= (x1 - x0) / 2.0) & (np.abs(v) <= (y1 - y0) / 2.0)
    edge = inside & ((np.abs(u) > (x1 - x0) / 2.0 - 0.01) | (np.abs(v) > (y1 - y0) / 2.0 - 0.02))
    col = _rgb(op.get("color", (226, 214, 170)))
    out = img.copy()
    out[inside] = col.astype(np.uint8)
    out[edge] = (col * 0.85).astype(np.uint8)
    return out


def char_x(lines, pictograms, size_px, style, line: int, k: int, f: float) -> float:
    """The x (a fraction of the label's width) at fraction `f` across character `k` of printed line `line` (negative
    `k` counts from the end), as `labels.layout` sets it."""
    lay = L.layout(lines, pictograms, size_px, style)
    p = lay["lines"][line]
    text, font, box = p["line"]["text"], p["font"], p["box"]
    tw = box[2] - box[0]
    x = (p["slot"][0] - box[0]) if (p["line"].get("align") == "left" and "slot" in p) else (p["cx"] - tw / 2.0 - box[0])
    k = k % len(text)
    a = x + font.getlength(text[:k])
    b = x + font.getlength(text[:k + 1])
    return float((a + f * (b - a)) / lay["size"][0])


def pictogram_x(lines, pictograms, size_px, style, j: int, f: float) -> float:
    """The x (a fraction of the label's width) at fraction `f` across pictogram `j`."""
    lay = L.layout(lines, pictograms, size_px, style)
    _, (bx, _, s) = lay["pictograms"][j]
    return float((bx + f * s) / lay["size"][0])


def resolve(spec, lines, pictograms, size_px, style):
    """A spec whose x positions may be given by what is printed: `{"char": [line, k, f]}` (`char_x`) or
    `{"pictogram": [j, f]}` (`pictogram_x`) in `keep_x` and in the x entries of `box`; returned with numbers only."""
    if not spec:
        return spec

    def x(v):
        if isinstance(v, dict):
            if "char" in v:
                return char_x(lines, pictograms, size_px, style, *v["char"])
            if "pictogram" in v:
                return pictogram_x(lines, pictograms, size_px, style, *v["pictogram"])
            raise ValueError(f"wear: an x position is a number, {{'char': [line, k, f]}} or {{'pictogram': [j, f]}}, not {v!r}")
        return v
    out = []
    for op in ([spec] if isinstance(spec, dict) else spec):
        op = dict(op)
        if "keep_x" in op:
            op["keep_x"] = [x(v) for v in op["keep_x"]]
        if "box" in op:
            b = list(op["box"])
            op["box"] = [x(b[0]), b[1], x(b[2]), b[3]]
        out.append(op)
    return out


def apply(image: np.ndarray, spec, bg=None) -> np.ndarray:
    """The label `image` (RGB, reading orientation) worn as `spec` says. `bg`: the label's paper colour (what rubbed
    or faded print goes to); by default the commonest colour of the image."""
    img = np.ascontiguousarray(np.asarray(image)[:, :, :3]).copy()
    if not spec:
        return img
    paper = _rgb(bg) if bg is not None else background(img)
    for op in ([spec] if isinstance(spec, dict) else spec):
        kind = op["op"]
        if kind == "tear":
            img = _tear(img, op)
        elif kind == "rub":
            img = _rub(img, op, paper)
        elif kind == "fade":
            img = _fade(img, op, paper)
        elif kind == "stain":
            img = _stain(img, op)
        elif kind == "cover":
            img = _cover(img, op)
        else:
            raise ValueError(f"wear: unknown op {kind!r} (tear, rub, fade, stain, cover)")
    return img


def background(img: np.ndarray) -> np.ndarray:
    """The commonest colour of a label image (its paper)."""
    flat = np.asarray(img)[:, :, :3].reshape(-1, 3)
    q = (flat // 8).astype(np.int64)
    key = q[:, 0] * 1024 + q[:, 1] * 32 + q[:, 2]
    vals, counts = np.unique(key, return_counts=True)
    top = vals[int(np.argmax(counts))]
    return flat[key == top].mean(axis=0)


# ---- measures -----------------------------------------------------------------------------------------------------------
def ink(img: np.ndarray, bg) -> np.ndarray:
    """Pixels that are print, not paper."""
    d = np.linalg.norm(np.asarray(img, dtype=np.float64)[:, :, :3] - _rgb(bg)[None, None, :], axis=2)
    return d > INK_DIST


def kept(intact: np.ndarray, worn: np.ndarray, bg=None, paper=None) -> np.ndarray:
    """Print that still reads: pixels whose worn colour stands out from the worn paper around it (`paper`: the same
    wear applied to a blank label, `blank`) by at least half as much as the intact print stood out from the intact
    paper. Print rubbed or faded by less than half still reads; torn-off print (residue in its place), print under a
    stain or a strip of tape, and print rubbed off by more than half do not."""
    a = np.asarray(intact, dtype=np.float64)[:, :, :3]
    b = np.asarray(worn, dtype=np.float64)[:, :, :3]
    bg = background(intact) if bg is None else _rgb(bg)
    p = np.broadcast_to(bg[None, None, :], a.shape) if paper is None else np.asarray(paper, dtype=np.float64)[:, :, :3]
    was = np.linalg.norm(a - bg[None, None, :], axis=2)
    now = np.linalg.norm(b - p, axis=2)
    return now >= np.maximum(KEPT_FRACTION * was, SAME_DIST)


def blank(shape, spec, bg) -> np.ndarray:
    """The paper as the wear leaves it: `spec` applied to a label with nothing printed on it."""
    img = np.empty(tuple(shape[:2]) + (3,), dtype=np.uint8)
    img[:, :] = np.clip(np.round(_rgb(bg)), 0, 255).astype(np.uint8)
    return apply(img, spec, bg)


def kept_share(intact: np.ndarray, worn: np.ndarray, bg=None, paper=None) -> float:
    """The share of the intact print's ink that still reads in the worn label (`kept`)."""
    bg = background(intact) if bg is None else bg
    m = ink(intact, bg)
    return float((m & kept(intact, worn, bg, paper)).sum() / max(1, m.sum()))


def text_kept(lines, pictograms=(), size_px=(512, 256), style=None, spec=None, px_per_mm: float | None = None) -> dict:
    """What of each printed line and pictogram is left after `spec`: `{"lines": [{"text", "kept", "fragment",
    "share"}], "pictograms": [{"name", "share"}], "ink": share of all ink kept}`. `kept` has a `·` for each character
    that is no longer legible; `fragment` is what a reader makes of it (`...MABLE`)."""
    from PIL import Image, ImageDraw

    lay = L.layout(lines, pictograms, size_px, style)
    intact = L.label_image(lines, pictograms, size_px, style)
    spec = resolve(spec, lines, pictograms, size_px, style)
    bg = L.rgb(lay["style"]["bg"])
    worn = apply(intact, spec, bg)
    paper = blank(intact.shape, spec, bg)
    ok = kept(intact, worn, bg, paper)
    w, h = lay["size"]
    out = {"lines": [], "pictograms": [], "ink": kept_share(intact, worn, bg, paper)}
    for p in lay["lines"]:
        ln = p["line"]
        text, font, box = ln["text"], p["font"], p["box"]
        tw = box[2] - box[0]
        x = (p["slot"][0] - box[0]) if (ln.get("align") == "left" and "slot" in p) else (p["cx"] - tw / 2.0 - box[0])
        ascent = font.getmetrics()[0]
        y = p["cy"] + p["cap_px"] / 2.0 - ascent
        chars, shares = [], []
        line_ok = ok
        if "band" in p:                     # print on a coloured band: it stands out from the band, not from the paper
            st = lay["style"]
            band = L.rgb(ln.get("bg", (st["header"] if st.get("header") else ("ghs_red", "white"))[0]))
            line_ok = kept(intact, worn, band, blank(intact.shape, spec, band))
        for i, ch in enumerate(text):
            if ch == " ":
                chars.append(" ")
                continue
            im = Image.new("L", (w, h), 0)
            ImageDraw.Draw(im).text((int(round(x + font.getlength(text[:i]))), int(round(y))), ch, font=font, fill=255)
            m = np.asarray(im) > 96
            share = float((m & line_ok).sum() / max(1, m.sum()))
            shares.append(share)
            chars.append(ch if share >= CHAR_KEPT else "·")
        k = "".join(chars)
        out["lines"].append({"text": text, "kept": k, "fragment": fragment(k), "share": float(np.mean(shares)) if shares else 0.0,
                             "fine": bool(ln.get("fine")), "cap_px": float(p["cap_px"]),
                             **({"cap_mm": float(p["cap_px"]) / px_per_mm} if px_per_mm else {})})
    for name, (bx, by, s) in lay["pictograms"]:
        s = int(s)
        if s < 4:
            continue
        reg = ok[int(by):int(by) + s, int(bx):int(bx) + s]
        drawn = ink(intact, bg)[int(by):int(by) + s, int(bx):int(bx) + s]         # its ink, not the paper inside it
        a = (L.pictogram(name, s)[:, :, 3] > 128)[:reg.shape[0], :reg.shape[1]] & drawn
        out["pictograms"].append({"name": name, "share": float((a & reg).sum() / max(1, a.sum()))})
    return out


def summary(kept_: dict) -> dict:
    """`text_kept` in short, for an asset's meta: the fragments of the lines that are not fine print, the share of each
    pictogram and of all the ink that is left."""
    return {"lines": [ln["fragment"] for ln in kept_["lines"] if not ln["fine"]],
            **({"cap_mm": [round(ln["cap_mm"], 2) for ln in kept_["lines"] if not ln["fine"]]} if all("cap_mm" in ln for ln in kept_["lines"]) else {}),
            "pictograms": {p["name"]: round(p["share"], 2) for p in kept_["pictograms"]}, "ink": round(kept_["ink"], 2)}


def fragment(kept_text: str) -> str:
    """`··EAC·` -> `...EAC...`: the legible run(s) of a line, with what is lost marked as an ellipsis."""
    words = []
    for word in kept_text.split(" "):
        if not word:
            continue
        if set(word) == {"·"}:
            words.append("...")
            continue
        s = word
        lead, trail = s.startswith("·"), s.endswith("·")
        core = s.strip("·").replace("·", "?")
        words.append(("..." if lead else "") + core + ("..." if trail else ""))
    out = " ".join(words)
    while "... ..." in out:
        out = out.replace("... ...", "...")
    return out


def _corr(image: np.ndarray, info: dict, lab: dict, tex: np.ndarray) -> float:
    """The correlation `preview.label_score` computes, of a picture of a label with a given texture."""
    from PIL import Image

    from .preview import _luma
    h, w = image.shape[:2]
    u0, v0, u1, v1 = info["rect"]
    u0, u1 = int(max(0, math.ceil(u0))), int(min(w, math.floor(u1)))
    v0, v1 = int(max(0, math.ceil(v0))), int(min(h, math.floor(v1)))
    if u1 - u0 < 6 or v1 - v0 < 6:
        return 0.0
    crop = _luma(image[v0:v1, u0:u1])
    tex = _luma(tex)
    a, b = lab.get("uv", [0.0, 1.0])
    panel = tex[:, int(round(a * tex.shape[1])):int(round(b * tex.shape[1]))]
    rx, _ = info["right"]
    turns = 0
    if abs(rx) < 0.5:
        turns = 1 if info["right"][1] < 0 else 3
    elif rx < 0:
        turns = 2
    ch, cw = crop.shape
    if turns % 2:
        ch, cw = cw, ch
    if "wrap" in lab:
        arc = math.radians(lab["wrap"]["arc_deg"])
        half = min(arc / 2.0, math.pi / 2.0)
        xs = (np.arange(cw) + 0.5) / cw * 2.0 - 1.0
        theta = np.arcsin(np.clip(xs * math.sin(half), -1.0, 1.0))
        cols = np.clip(((theta / arc) + 0.5) * panel.shape[1], 0, panel.shape[1] - 1).astype(int)
        panel = panel[:, cols]
    expected = np.asarray(Image.fromarray(panel.astype(np.uint8)).resize((cw, ch), Image.BOX), dtype=np.float64)
    expected = np.rot90(expected, turns)
    e, c = expected - expected.mean(), crop - crop.mean()
    denom = math.sqrt(float((e * e).sum()) * float((c * c).sum()))
    return float((e * c).sum() / denom) if denom > 0 else 0.0


def _texture(kind: str, params: dict | None, index: int):
    from pathlib import Path

    from . import catalog, png
    prop = catalog.build(kind, params)
    lab = prop.meta["labels"][index]
    return lab, png.read(Path(prop.path).parent / lab["texture"])


def score(kind: str, params: dict, intact_params: dict | None = None, index: int = 0) -> dict:
    """The legibility of a worn label measured as the benchmark measures every label (`preview.label_score`), and
    against its intact print: `{"worn": label_score of the worn label + "match_intact", "intact": the same of the
    intact one, "relative": worn match_intact / intact match_intact}`. `intact_params`: the kind's parameters without
    the wear (default: `params` without `wear`)."""
    from . import preview

    intact_params = dict(intact_params if intact_params is not None else {k: v for k, v in params.items() if k != "wear"})
    out = {}
    lab_i, tex_i = _texture(kind, intact_params, index)
    for name, p in (("worn", params), ("intact", intact_params)):
        s = preview.label_score(kind, p, index)
        image, info = preview.label_closeup(kind, p, index)
        lab, _ = _texture(kind, p, index)
        s["match_intact"] = _corr(image, info, lab_i, tex_i)
        out[name] = s
    out["relative"] = out["worn"]["match_intact"] / out["intact"]["match_intact"] if out["intact"]["match_intact"] > 0 else 0.0
    return out


def cap_px(world, at: str, cap_height: float, camera: str) -> float:
    """How many pixels tall capitals `cap_height` metres high at `at` (`<object>/<site>`) are in `camera`'s image of
    the scene, ignoring foreshortening (an upper bound)."""
    eye, _ = world.camera_pose(camera)
    p = np.asarray(world.locate(at)[0], dtype=np.float64)
    d = float(np.linalg.norm(p - eye))
    fovy = float(world.model.cam_fovy[world.model.camera(camera).id])
    h = world.image_size[1]
    return cap_height * (h / 2.0) / (d * math.tan(math.radians(fovy) / 2.0))


# the word a sentence about a worn label uses for each kind of damage (`says`, tests/test_described.py)
WORDS = {"tear": "torn", "rub": "worn", "fade": "faded", "stain": "stained", "cover": "covered"}


def words(spec) -> list:
    """The words that name the damage `spec` does, in the order of its operations, each once."""
    out = []
    for op in ([spec] if isinstance(spec, dict) else (spec or ())):
        w = WORDS[op["op"]]
        if w not in out:
            out.append(w)
    return out


def describe(spec: Sequence[dict] | None) -> list:
    """The spec as plain JSON (for the label's meta)."""
    if not spec:
        return []
    return [{k: (list(map(list, v)) if k == "edge" else (list(v) if isinstance(v, (tuple, list)) else v)) for k, v in op.items()}
            for op in ([spec] if isinstance(spec, dict) else spec)]
