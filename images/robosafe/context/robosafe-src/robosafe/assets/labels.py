"""Printed labels: text and hazard pictograms rasterised into textures, and the thin panels and shells that carry them.

Everything here is drawn by code. The pictograms are our own drawings of the usual hazard symbols (flame, corrosion,
skull and crossbones, ...) inside the frames people know them by (a red diamond, a yellow triangle, a red disc); no
image file is read. Text is set in DejaVu Sans (vendored under `assets/third_party/fonts/`) and rasterised with Pillow
when an asset is built.

    png = label_texture(["AIR DUSTER", "EXTREMELY FLAMMABLE"], pictograms=("flame", "gas_cylinder"), size_px=(512, 384))

Sizes are in pixels here; the asset builders decide how many pixels a millimetre gets (`PX_PER_MM`).
"""
from __future__ import annotations

import math
import os
from functools import lru_cache
from pathlib import Path
from typing import Sequence

import numpy as np

from . import mesh as M
from . import png as _png

PX_PER_MM = 6.0             # default resolution of a printed label
MAX_TEXTURE = 1024          # longest side of a label texture, pixels
CAP_RATIO = 0.729           # cap height of DejaVu Sans as a fraction of the font size
STEM_RATIO = 0.19           # stem width of DejaVu Sans Bold as a fraction of the font size (regular: about 0.09)

_SS = 4                     # supersampling of drawn shapes

COLORS = {
    "white": (255, 255, 255), "paper": (246, 244, 236), "black": (16, 16, 18), "ink": (24, 24, 28),
    "red": (204, 24, 30), "ghs_red": (218, 30, 36), "orange": (236, 122, 28), "amber": (245, 166, 35),
    "yellow": (250, 208, 44), "warning_yellow": (252, 212, 40), "green": (0, 135, 82), "exit_green": (0, 150, 86),
    "blue": (24, 84, 168), "navy": (22, 40, 92), "sky": (120, 180, 226), "teal": (14, 128, 128),
    "purple": (104, 60, 150), "pink": (226, 108, 150), "brown": (118, 76, 44), "kraft": (188, 150, 104),
    "grey": (128, 130, 134), "light_grey": (212, 214, 216), "dark_grey": (58, 60, 66), "cream": (240, 230, 200),
    "lime": (150, 200, 60), "silver": (190, 194, 198), "tomato": (200, 52, 36), "note_yellow": (252, 232, 120),
    "note_pink": (250, 170, 196), "note_green": (176, 232, 150), "note_blue": (160, 210, 246),
}


def rgb(c) -> tuple[int, int, int]:
    """A colour name, `#rrggbb`, or three numbers (0-1 floats or 0-255 integers) as an 8-bit triple."""
    if isinstance(c, str):
        if c.startswith("#") and len(c) == 7:
            return tuple(int(c[i:i + 2], 16) for i in (1, 3, 5))
        if c not in COLORS:
            raise KeyError(f"unknown colour {c!r}; known: {sorted(COLORS)}")
        return COLORS[c]
    v = [float(x) for x in c][:3]
    if all(x <= 1.0 for x in v):
        return tuple(int(round(x * 255)) for x in v)
    return tuple(int(round(x)) for x in v)


def rgba01(c, alpha: float = 1.0) -> tuple[float, float, float, float]:
    """The same colour as floats for a geom."""
    if not isinstance(c, str) and len(c) == 4:
        return tuple(float(x) for x in c)
    r, g, b = rgb(c)
    return (round(r / 255.0, 4), round(g / 255.0, 4), round(b / 255.0, 4), float(alpha))


def font_dir() -> Path:
    env = os.environ.get("ROBOSAFE_THIRD_PARTY")
    base = Path(env) if env else Path(__file__).resolve().parents[2] / "assets" / "third_party"
    return base / "fonts"


@lru_cache(maxsize=512)
def _font(bold: bool, px: int):
    from PIL import ImageFont

    path = font_dir() / ("DejaVuSans-Bold.ttf" if bold else "DejaVuSans.ttf")
    if not path.exists():
        raise FileNotFoundError(f"label font missing: {path} (see assets/third_party/README.md)")
    return ImageFont.truetype(str(path), int(px))


# ----------------------------------------------------------------------------------------------------------------------
# Drawing surface in unit coordinates
# ----------------------------------------------------------------------------------------------------------------------

class _Canvas:
    """A square drawing surface addressed in unit coordinates (x right, y down), drawn `_SS` times oversized."""

    def __init__(self, size: int, im=None, ox: float = 0.0, oy: float = 0.0, sc: float | None = None):
        from PIL import Image, ImageDraw

        self.n = size * _SS
        self.im = im if im is not None else Image.new("RGBA", (self.n, self.n), (0, 0, 0, 0))
        self.d = ImageDraw.Draw(self.im)
        self.ox, self.oy, self.sc = ox * self.n, oy * self.n, (self.n if sc is None else sc * self.n)

    def sub(self, cx: float, cy: float, scale: float) -> "_Canvas":
        """A view whose unit square is centred at (cx, cy) of this one and `scale` wide."""
        c = _Canvas.__new__(_Canvas)
        c.n, c.im, c.d = self.n, self.im, self.d
        c.sc = self.sc * scale
        c.ox = self.ox + self.sc * cx - c.sc / 2.0
        c.oy = self.oy + self.sc * cy - c.sc / 2.0
        return c

    def _p(self, x, y):
        return (self.ox + x * self.sc, self.oy + y * self.sc)

    def poly(self, pts, fill):
        self.d.polygon([self._p(x, y) for x, y in pts], fill=fill)

    def circle(self, cx, cy, r, fill):
        x, y = self._p(cx, cy)
        rr = r * self.sc
        self.d.ellipse([x - rr, y - rr, x + rr, y + rr], fill=fill)

    def ellipse(self, cx, cy, rx, ry, fill):
        x, y = self._p(cx, cy)
        self.d.ellipse([x - rx * self.sc, y - ry * self.sc, x + rx * self.sc, y + ry * self.sc], fill=fill)

    def rect(self, x0, y0, x1, y1, fill, radius: float = 0.0):
        a, b = self._p(x0, y0), self._p(x1, y1)
        if radius > 0:
            self.d.rounded_rectangle([a[0], a[1], b[0], b[1]], radius=radius * self.sc, fill=fill)
        else:
            self.d.rectangle([a[0], a[1], b[0], b[1]], fill=fill)

    def line(self, pts, width, fill):
        """A polyline with round joints and round ends."""
        q = [self._p(x, y) for x, y in pts]
        w = max(1, int(round(width * self.sc)))
        self.d.line(q, fill=fill, width=w, joint="curve")
        for x, y in q:
            self.d.ellipse([x - w / 2.0, y - w / 2.0, x + w / 2.0, y + w / 2.0], fill=fill)

    def ring(self, cx, cy, r_out, r_in, fill, hole):
        self.circle(cx, cy, r_out, fill)
        self.circle(cx, cy, r_in, hole)

    def finish(self):
        from PIL import Image

        return self.im.resize((self.n // _SS, self.n // _SS), Image.LANCZOS)


# ----------------------------------------------------------------------------------------------------------------------
# Symbols (drawn in `ink` on `paper` inside the unit square)
# ----------------------------------------------------------------------------------------------------------------------

def _s_flame(c: _Canvas, ink, paper, base: bool = True):
    c.poly([(0.50, 0.08), (0.58, 0.24), (0.67, 0.38), (0.72, 0.52), (0.72, 0.63), (0.67, 0.73), (0.58, 0.79),
            (0.50, 0.81), (0.42, 0.79), (0.33, 0.73), (0.28, 0.63), (0.29, 0.52), (0.35, 0.42), (0.40, 0.50),
            (0.42, 0.38), (0.44, 0.24)], ink)
    c.poly([(0.50, 0.50), (0.56, 0.60), (0.58, 0.68), (0.54, 0.75), (0.46, 0.75), (0.42, 0.68), (0.44, 0.60)], paper)
    if base:
        c.rect(0.24, 0.86, 0.76, 0.92, ink)


def _s_oxidizer(c, ink, paper):
    _s_flame(c.sub(0.5, 0.33, 0.66), ink, paper, base=False)
    c.ring(0.5, 0.70, 0.19, 0.115, ink, paper)
    c.rect(0.22, 0.90, 0.78, 0.95, ink)


def _s_gas_cylinder(c, ink, paper):
    c.line([(0.26, 0.66), (0.62, 0.46)], 0.23, ink)
    c.line([(0.62, 0.46), (0.80, 0.36)], 0.085, ink)
    c.line([(0.80, 0.30), (0.84, 0.42)], 0.05, ink)
    c.line([(0.25, 0.60), (0.55, 0.435)], 0.03, paper)


def _s_exploding_bomb(c, ink, paper):
    c.circle(0.5, 0.56, 0.13, ink)
    for k in range(9):
        a = 2 * math.pi * k / 9 + 0.2
        r0, r1 = 0.20, (0.43 if k % 2 == 0 else 0.34)
        dx, dy = math.cos(a), -math.sin(a)
        px, py = -dy, dx
        c.poly([(0.5 + r0 * dx + 0.045 * px, 0.56 + r0 * dy + 0.045 * py), (0.5 + r1 * dx, 0.56 + r1 * dy),
                (0.5 + r0 * dx - 0.045 * px, 0.56 + r0 * dy - 0.045 * py)], ink)
    for x, y in ((0.2, 0.3), (0.82, 0.3), (0.5, 0.12)):
        c.circle(x, y, 0.028, ink)


def _s_corrosion(c, ink, paper):
    for sx in (1.0, -1.0):                                        # two tubes pouring
        f = lambda x: 0.5 + sx * (x - 0.5)                        # noqa: E731  (mirror about the middle)
        c.line([(f(0.10), 0.12), (f(0.30), 0.22)], 0.085, ink)
        c.poly([(f(0.34), 0.28), (f(0.375), 0.37), (f(0.305), 0.37)], ink)
        c.circle(f(0.34), 0.385, 0.036, ink)
    c.rect(0.08, 0.64, 0.46, 0.74, ink)                           # a bar of material being eaten
    c.poly([(0.20, 0.64), (0.26, 0.71), (0.30, 0.66), (0.34, 0.71), (0.38, 0.64)], paper)
    for x in (0.22, 0.30, 0.38):
        c.line([(x, 0.60), (x + 0.02, 0.52)], 0.018, ink)
    c.poly([(0.54, 0.70), (0.54, 0.58), (0.74, 0.54), (0.92, 0.55), (0.94, 0.60), (0.78, 0.62), (0.94, 0.65),
            (0.93, 0.70), (0.80, 0.72), (0.90, 0.75), (0.88, 0.80), (0.66, 0.80), (0.54, 0.76)], ink)   # a hand
    c.poly([(0.60, 0.56), (0.655, 0.64), (0.70, 0.59), (0.72, 0.535)], paper)
    for x in (0.62, 0.69):
        c.line([(x, 0.52), (x + 0.02, 0.45)], 0.018, ink)


def _s_skull(c, ink, paper):
    for sx in (1.0, -1.0):
        f = lambda x: 0.5 + sx * (x - 0.5)                        # noqa: E731
        c.line([(f(0.20), 0.64), (f(0.80), 0.90)], 0.075, ink)
        for ex, ey in ((0.20, 0.64), (0.80, 0.90)):
            c.circle(f(ex - 0.03), ey - 0.035, 0.05, ink)
            c.circle(f(ex + 0.03), ey + 0.035, 0.05, ink) if ex > 0.5 else c.circle(f(ex - 0.02), ey + 0.04, 0.05, ink)
    c.circle(0.5, 0.36, 0.235, ink)
    c.rect(0.375, 0.48, 0.625, 0.69, ink, radius=0.04)
    c.circle(0.405, 0.37, 0.068, paper)
    c.circle(0.595, 0.37, 0.068, paper)
    c.poly([(0.5, 0.455), (0.462, 0.535), (0.538, 0.535)], paper)
    for x in (0.44, 0.50, 0.56):
        c.line([(x, 0.61), (x, 0.69)], 0.016, paper)


def _s_exclamation(c, ink, paper):
    c.poly([(0.415, 0.12), (0.585, 0.12), (0.545, 0.62), (0.455, 0.62)], ink)
    c.circle(0.5, 0.79, 0.085, ink)


def _s_health_hazard(c, ink, paper):
    c.circle(0.5, 0.22, 0.125, ink)
    c.poly([(0.20, 0.94), (0.20, 0.58), (0.30, 0.41), (0.70, 0.41), (0.80, 0.58), (0.80, 0.94)], ink)
    pts = []
    for k in range(12):
        a = math.pi * k / 6.0 + math.pi / 12
        r = 0.19 if k % 2 == 0 else 0.07
        pts.append((0.5 + r * math.cos(a), 0.64 - r * math.sin(a)))
    c.poly(pts, paper)


def _s_environment(c, ink, paper):
    c.line([(0.10, 0.84), (0.92, 0.84)], 0.035, ink)
    c.line([(0.30, 0.84), (0.30, 0.22)], 0.05, ink)
    for a, b in (((0.30, 0.52), (0.14, 0.34)), ((0.30, 0.40), (0.46, 0.22)), ((0.30, 0.64), (0.46, 0.52)),
                 ((0.30, 0.30), (0.20, 0.16)), ((0.14, 0.34), (0.08, 0.36))):
        c.line([a, b], 0.032, ink)
    c.ellipse(0.66, 0.69, 0.15, 0.07, ink)
    c.poly([(0.78, 0.69), (0.92, 0.60), (0.92, 0.78)], ink)
    c.circle(0.57, 0.675, 0.018, paper)


def _s_biohazard(c, ink, paper):
    # the usual construction in units of the gap A: horn circles of radius 15 at 11 from the centre, cut by circles
    # of radius 10.5 at 15; a centre hole of radius 3; a ring from 10 to 13.5 that shows in the mouths of the horns
    cx, cy, u = 0.5, 0.54, 0.46 / 26.0
    dirs = [(math.cos(a), -math.sin(a)) for a in (math.pi / 2, math.pi * 7 / 6, math.pi * 11 / 6)]
    for dx, dy in dirs:
        c.circle(cx + 11 * u * dx, cy + 11 * u * dy, 15 * u, ink)
    for dx, dy in dirs:
        c.circle(cx + 15 * u * dx, cy + 15 * u * dy, 10.5 * u, paper)
    for dx, dy in dirs:
        c.line([(cx, cy), (cx + 6 * u * dx, cy + 6 * u * dy)], 1.6 * u, paper)
        c.poly([(cx + 20 * u * dx - 2.2 * u * dy, cy + 20 * u * dy + 2.2 * u * dx),
                (cx + 27 * u * dx - 2.2 * u * dy, cy + 27 * u * dy + 2.2 * u * dx),
                (cx + 27 * u * dx + 2.2 * u * dy, cy + 27 * u * dy - 2.2 * u * dx),
                (cx + 20 * u * dx + 2.2 * u * dy, cy + 20 * u * dy - 2.2 * u * dx)], paper)   # the horns are open at the tip
    c.circle(cx, cy, 3 * u, paper)
    from PIL import Image, ImageChops, ImageDraw
    ring = Image.new("L", c.im.size, 0)
    d = ImageDraw.Draw(ring)
    x, y = c._p(cx, cy)
    for r, v in ((13.5 * u, 255), (10 * u, 0)):
        d.ellipse([x - r * c.sc, y - r * c.sc, x + r * c.sc, y + r * c.sc], fill=v)
    mouths = Image.new("L", c.im.size, 0)
    d = ImageDraw.Draw(mouths)
    for dx, dy in dirs:
        px, py = c._p(cx + 15 * u * dx, cy + 15 * u * dy)
        rr = 9.3 * u * c.sc
        d.ellipse([px - rr, py - rr, px + rr, py + rr], fill=255)
    c.im.paste(Image.new("RGBA", c.im.size, ink), (0, 0), ImageChops.multiply(ring, mouths))


def _s_bolt(c, ink, paper):
    c.poly([(0.58, 0.10), (0.30, 0.54), (0.47, 0.54), (0.38, 0.92), (0.72, 0.42), (0.54, 0.42), (0.68, 0.10)], ink)


def _s_hot_surface(c, ink, paper):
    for x0 in (0.30, 0.50, 0.70):
        pts = [(x0 + 0.055 * math.sin(2 * math.pi * t / 0.36), 0.16 + t) for t in np.linspace(0.0, 0.50, 21)]
        c.line(pts, 0.055, ink)
    c.rect(0.16, 0.76, 0.84, 0.86, ink)


def _s_slip(c, ink, paper):
    c.circle(0.34, 0.24, 0.085, ink)
    c.line([(0.42, 0.36), (0.56, 0.58)], 0.10, ink)
    c.line([(0.56, 0.58), (0.80, 0.50), (0.88, 0.64)], 0.075, ink)
    c.line([(0.56, 0.58), (0.70, 0.76)], 0.075, ink)
    c.line([(0.44, 0.40), (0.22, 0.48)], 0.065, ink)
    c.line([(0.46, 0.40), (0.68, 0.30)], 0.065, ink)
    c.line([(0.12, 0.88), (0.88, 0.88)], 0.04, ink)
    for x in (0.26, 0.42):
        c.circle(x, 0.78, 0.028, ink)


def _s_running(c, ink, paper):
    c.circle(0.42, 0.20, 0.085, ink)
    c.line([(0.42, 0.33), (0.36, 0.57)], 0.11, ink)
    c.line([(0.43, 0.36), (0.58, 0.46), (0.68, 0.38)], 0.065, ink)
    c.line([(0.40, 0.36), (0.24, 0.42), (0.16, 0.54)], 0.065, ink)
    c.line([(0.37, 0.57), (0.52, 0.68), (0.50, 0.88)], 0.075, ink)
    c.line([(0.35, 0.57), (0.24, 0.72), (0.08, 0.76)], 0.075, ink)


def _s_battery(c, ink, paper):
    c.rect(0.10, 0.32, 0.84, 0.68, ink, radius=0.05)
    c.rect(0.15, 0.37, 0.79, 0.63, paper, radius=0.02)
    c.rect(0.84, 0.43, 0.91, 0.57, ink)
    for x in (0.19, 0.34, 0.49):
        c.rect(x, 0.41, x + 0.11, 0.59, ink)
    c.poly([(0.70, 0.40), (0.63, 0.51), (0.68, 0.51), (0.65, 0.60), (0.74, 0.48), (0.69, 0.48), (0.72, 0.40)], ink)


def _s_drop(c, ink, paper):
    c.poly([(0.5, 0.14), (0.68, 0.50), (0.32, 0.50)], ink)
    c.circle(0.5, 0.60, 0.215, ink)


def _s_hand(c, ink, paper):
    c.rect(0.33, 0.44, 0.70, 0.84, ink, radius=0.08)
    for i, x in enumerate((0.33, 0.43, 0.53, 0.63)):
        c.line([(x + 0.035, 0.50), (x + 0.035, (0.22, 0.14, 0.17, 0.25)[i])], 0.075, ink)
    c.line([(0.34, 0.66), (0.20, 0.50)], 0.08, ink)


def _s_cross(c, ink, paper):
    c.rect(0.40, 0.16, 0.60, 0.84, ink)
    c.rect(0.16, 0.40, 0.84, 0.60, ink)


def _s_arrow(c, ink, paper):
    c.rect(0.12, 0.42, 0.60, 0.58, ink)
    c.poly([(0.56, 0.22), (0.90, 0.50), (0.56, 0.78)], ink)


def _s_fork_knife(c, ink, paper):
    c.line([(0.34, 0.44), (0.34, 0.88)], 0.06, ink)
    for x in (0.25, 0.34, 0.43):
        c.line([(x, 0.14), (x, 0.40)], 0.035, ink)
    c.line([(0.25, 0.40), (0.43, 0.40)], 0.05, ink)
    c.poly([(0.62, 0.12), (0.74, 0.20), (0.74, 0.52), (0.62, 0.52)], ink)
    c.line([(0.66, 0.50), (0.66, 0.88)], 0.06, ink)


def _s_plug(c, ink, paper):
    c.rect(0.30, 0.34, 0.70, 0.62, ink, radius=0.05)
    c.rect(0.37, 0.14, 0.44, 0.36, ink)
    c.rect(0.56, 0.14, 0.63, 0.36, ink)
    c.line([(0.5, 0.62), (0.5, 0.74), (0.36, 0.84), (0.36, 0.94)], 0.06, ink)


_SYMBOLS = {
    "flame": _s_flame, "oxidizer": _s_oxidizer, "gas_cylinder": _s_gas_cylinder, "exploding_bomb": _s_exploding_bomb,
    "corrosion": _s_corrosion, "skull": _s_skull, "exclamation": _s_exclamation, "health_hazard": _s_health_hazard,
    "environment": _s_environment, "biohazard": _s_biohazard, "bolt": _s_bolt, "hot": _s_hot_surface, "slip": _s_slip,
    "running": _s_running, "battery": _s_battery, "drop": _s_drop, "hand": _s_hand, "cross": _s_cross,
    "arrow": _s_arrow, "fork_knife": _s_fork_knife, "plug": _s_plug,
}

# pictogram name -> (frame, symbol). Frames: ghs (red diamond), warning (yellow triangle), prohibition (red ring and
# bar over the symbol), plain (symbol alone), and a few signs that are their own frame.
PICTOGRAMS: dict[str, tuple[str, str | None]] = {
    "flame": ("ghs", "flame"), "oxidizer": ("ghs", "oxidizer"), "gas_cylinder": ("ghs", "gas_cylinder"),
    "exploding_bomb": ("ghs", "exploding_bomb"), "corrosion": ("ghs", "corrosion"), "skull": ("ghs", "skull"),
    "exclamation": ("ghs", "exclamation"), "health_hazard": ("ghs", "health_hazard"),
    "environment": ("ghs", "environment"),
    "biohazard": ("warning", "biohazard"), "high_voltage": ("warning", "bolt"), "hot_surface": ("warning", "hot"),
    "wet_floor": ("warning", "slip"), "warning": ("warning", "exclamation"),
    "no_entry": ("no_entry", None), "emergency_exit": ("exit", None), "emergency_stop": ("estop", None),
    "no_water": ("prohibition", "drop"), "do_not_touch": ("prohibition", "hand"), "no_flame": ("prohibition", "flame"),
    "first_aid": ("green_square", "cross"), "battery": ("plain", "battery"), "food_safe": ("plain", "fork_knife"),
    "arrow_right": ("plain", "arrow"), "plug": ("plain", "plug"), "drop": ("plain", "drop"),
    "biohazard_plain": ("plain", "biohazard"),
}
# pressurised container is the gas cylinder; a couple of everyday names for the same drawings
ALIASES = {"pressurized": "gas_cylinder", "pressurised": "gas_cylinder", "oxidiser": "oxidizer", "toxic": "skull",
           "corrosive": "corrosion", "flammable": "flame", "electrical": "high_voltage", "do_not_enter": "no_entry",
           "exit": "emergency_exit", "estop": "emergency_stop", "irritant": "exclamation", "explosive": "exploding_bomb"}


def pictogram_names() -> list[str]:
    return sorted(PICTOGRAMS)


def _resolve(name: str) -> str:
    name = ALIASES.get(name, name)
    if name not in PICTOGRAMS:
        raise KeyError(f"unknown pictogram {name!r}; known: {pictogram_names()} and aliases {sorted(ALIASES)}")
    return name


@lru_cache(maxsize=256)
def _pictogram_cached(name: str, size: int, ink: tuple, paper: tuple):
    frame, symbol = PICTOGRAMS[name]
    c = _Canvas(size)
    black, white = COLORS["black"] + (255,), (255, 255, 255, 255)
    if frame == "ghs":
        red = COLORS["ghs_red"] + (255,)
        c.poly([(0.5, 0.0), (1.0, 0.5), (0.5, 1.0), (0.0, 0.5)], red)
        m = 0.085
        c.poly([(0.5, m), (1.0 - m, 0.5), (0.5, 1.0 - m), (m, 0.5)], white)
        _SYMBOLS[symbol](c.sub(0.5, 0.5, 0.56), black, white)
    elif frame == "warning":
        yel = COLORS["warning_yellow"] + (255,)
        tri = [(0.5, 0.075), (0.955, 0.885), (0.045, 0.885)]
        c.poly(tri, black)
        c.line(tri + tri[:1], 0.07, black)
        c.poly([(0.5, 0.20), (0.855, 0.83), (0.145, 0.83)], yel)
        _SYMBOLS[symbol](c.sub(0.5, 0.61, 0.46), black, yel)
    elif frame == "prohibition":
        red = COLORS["ghs_red"] + (255,)
        c.circle(0.5, 0.5, 0.49, red)
        c.circle(0.5, 0.5, 0.385, white)
        _SYMBOLS[symbol](c.sub(0.5, 0.5, 0.62), black, white)
        c.line([(0.5 - 0.31, 0.5 - 0.31), (0.5 + 0.31, 0.5 + 0.31)], 0.10, red)
    elif frame == "no_entry":
        c.circle(0.5, 0.5, 0.49, COLORS["ghs_red"] + (255,))
        c.rect(0.16, 0.41, 0.84, 0.59, white)
    elif frame == "exit":
        green = COLORS["exit_green"] + (255,)
        c.rect(0.0, 0.08, 1.0, 0.92, green, radius=0.06)
        c.rect(0.66, 0.20, 0.92, 0.82, white)
        c.rect(0.70, 0.24, 0.92, 0.82, green)
        _SYMBOLS["running"](c.sub(0.36, 0.50, 0.66), white, green)
    elif frame == "estop":
        c.circle(0.5, 0.5, 0.49, black)
        c.circle(0.5, 0.5, 0.465, COLORS["warning_yellow"] + (255,))
        c.circle(0.5, 0.5, 0.25, black)
        c.circle(0.5, 0.5, 0.225, COLORS["ghs_red"] + (255,))
        for k in range(3):                                        # three arrows around the button (turn to release)
            a0 = 2 * math.pi * k / 3 + 0.5
            pts = [(0.5 + 0.36 * math.cos(a0 + t), 0.5 - 0.36 * math.sin(a0 + t)) for t in np.linspace(0.0, 1.1, 12)]
            c.line(pts, 0.045, black)
            a1 = a0 + 1.1
            tx, ty = 0.5 + 0.36 * math.cos(a1), 0.5 - 0.36 * math.sin(a1)
            c.poly([(tx + 0.075 * math.cos(a1), ty - 0.075 * math.sin(a1)),
                    (tx - 0.075 * math.cos(a1), ty + 0.075 * math.sin(a1)),
                    (tx - 0.11 * math.sin(a1), ty - 0.11 * math.cos(a1))], black)
    elif frame == "green_square":
        green = COLORS["exit_green"] + (255,)
        c.rect(0.02, 0.02, 0.98, 0.98, green, radius=0.08)
        _SYMBOLS[symbol](c.sub(0.5, 0.5, 0.78), white, green)
    else:
        _SYMBOLS[symbol](c, ink + (255,), paper + (255,))
    return c.finish()


def pictogram(name: str, size_px: int = 128, ink="black", paper="white") -> np.ndarray:
    """One pictogram as an RGBA array (size_px, size_px, 4) with a transparent surround."""
    return np.asarray(_pictogram_cached(_resolve(name), int(size_px), rgb(ink), rgb(paper))).copy()


# ----------------------------------------------------------------------------------------------------------------------
# Label layout
# ----------------------------------------------------------------------------------------------------------------------

STYLES: dict[str, dict] = {
    # plain black on white with a thin border
    "plain": {"bg": "white", "fg": "black", "border": ("black", 0.012)},
    "paper": {"bg": "paper", "fg": "ink", "border": None},
    # a product label: the first line is a coloured band
    "product": {"bg": "white", "fg": "black", "header": ("blue", "white"), "border": None},
    # a hazard label: white, red border, signal word in a red band if the first line is DANGER or WARNING
    "hazard": {"bg": "white", "fg": "black", "border": ("ghs_red", 0.03), "signal_band": True},
    "warning_sign": {"bg": "warning_yellow", "fg": "black", "border": ("black", 0.03)},
    "danger_sign": {"bg": "white", "fg": "black", "header": ("ghs_red", "white"), "border": ("ghs_red", 0.03)},
    "prohibition_sign": {"bg": "white", "fg": "ghs_red", "border": ("ghs_red", 0.04)},
    "exit_sign": {"bg": "exit_green", "fg": "white", "border": ("white", 0.02)},
    "info_sign": {"bg": "blue", "fg": "white", "border": ("white", 0.02)},
    "tag": {"bg": "white", "fg": "black", "border": ("black", 0.02)},
    "note": {"bg": "note_yellow", "fg": "ink", "border": None, "bold": False},
    "kraft": {"bg": "kraft", "fg": "ink", "border": None},
    "screen": {"bg": (18, 22, 30), "fg": (230, 236, 240), "border": None},
    "dark": {"bg": "black", "fg": "white", "border": None},
}


def _style(style) -> dict:
    if style is None:
        style = "plain"
    if isinstance(style, str):
        if style not in STYLES:
            raise KeyError(f"unknown label style {style!r}; known: {sorted(STYLES)}")
        return dict(STYLES[style])
    if "base" not in style and "bg" in style and "fg" in style:      # already resolved
        return dict(style)
    base = dict(STYLES[style.get("base", "plain")])
    base.update({k: v for k, v in style.items() if k != "base"})
    return base


def _lines(lines) -> list[dict]:
    out = []
    for ln in lines or ():
        if isinstance(ln, str):
            ln = {"text": ln}
        elif isinstance(ln, (tuple, list)):
            ln = {"text": ln[0], "h": float(ln[1])}
        ln = dict(ln)
        ln.setdefault("h", 1.0)
        out.append(ln)
    return out


def _fit(text: str, bold: bool, max_w: float, max_cap: float) -> tuple[object, tuple]:
    """The largest font whose capitals are at most `max_cap` tall and whose text is at most `max_w` wide."""
    px = max(4, int(max_cap / CAP_RATIO))
    while px > 4:
        f = _font(bold, px)
        box = f.getbbox(text)
        if box[2] - box[0] <= max_w:
            return f, box
        px = min(px - 1, int(px * max_w / max(1, box[2] - box[0])) + 1)
    f = _font(bold, 4)
    return f, f.getbbox(text)


def layout(lines, pictograms=(), size_px=(512, 256), style=None) -> dict:
    """Where everything goes. Returns the boxes and, per line, the font size and cap height in pixels."""
    st = _style(style)
    w, h = int(size_px[0]), int(size_px[1])
    lines = _lines(lines)
    pics = [_resolve(p) for p in pictograms]
    border = st.get("border")
    bw = int(round(border[1] * min(w, h))) if border else 0
    pad = bw + int(round(st.get("pad", 0.05) * min(w, h)))
    inset = int(round(st.get("inset_x", 0.0) * w))           # extra side margin (labels bent round a cylinder)
    x0, y0, x1, y1 = pad + inset, pad, w - pad - inset, h - pad
    head = None
    banded = st.get("header") or (st.get("signal_band") and lines and lines[0]["text"].upper() in ("DANGER", "WARNING", "CAUTION"))
    if banded and lines:                                           # the first line is a band across the top
        share = lines[0]["h"] / (sum(ln["h"] for ln in lines) + (1.3 if pics else 0.0))
        bh = int(round(max(0.16, min(0.5, share * 1.15)) * (h - 2 * bw)))
        head = (bw, bw, w - bw, bw + bh)
        y0 = bw + bh + max(2, pad // 3)
    rest = lines[1:] if head else lines
    pic_boxes = []
    side = st.get("pictograms", "auto")
    if pics:
        aw, ah = x1 - x0, y1 - y0
        if side == "auto":
            side = "left" if (aw > 1.6 * ah or not rest) else "top"
        if not rest:
            s = min(ah, aw // len(pics))
            gap = (aw - s * len(pics)) // (len(pics) + 1)
            pic_boxes = [(x0 + gap + i * (s + gap), y0 + (ah - s) // 2, s) for i in range(len(pics))]
        elif side in ("left", "right"):
            n = len(pics)
            cols = 1 if n == 1 else (2 if n <= 4 else 3)
            rows = int(math.ceil(n / cols))
            s = int(min(ah / rows, st.get("pictogram_share", 0.46) * aw / cols))
            bx = x0 if side == "left" else x1 - cols * s
            by = y0 + (ah - rows * s) // 2
            pic_boxes = [(bx + (i % cols) * s, by + (i // cols) * s, s) for i in range(n)]
            if side == "left":
                x0 += cols * s + pad // 2
            else:
                x1 -= cols * s + pad // 2
        else:
            s = int(min(st.get("pictogram_share", 0.48) * ah, aw / len(pics)))
            gap = (aw - s * len(pics)) // (len(pics) + 1)
            by = y0 if side == "top" else y1 - s
            pic_boxes = [(x0 + gap + i * (s + gap), by, s) for i in range(len(pics))]
            if side == "top":
                y0 += s + pad // 3
            else:
                y1 -= s + pad // 3
    placed = []
    bold_default = st.get("bold", True)
    if head:
        ln = lines[0]
        f, box = _fit(ln["text"], ln.get("bold", True), (head[2] - head[0]) * 0.92 - 2 * inset, (head[3] - head[1]) * 0.62)
        placed.append({"line": ln, "font": f, "box": box, "cx": (head[0] + head[2]) / 2.0, "cy": (head[1] + head[3]) / 2.0,
                       "band": head})
    if rest:
        total = sum(ln["h"] for ln in rest)
        gap_share = 0.30                                           # leading, as a fraction of a line's slot
        y = float(y0)
        for ln in rest:
            slot = (y1 - y0) * ln["h"] / total
            f, box = _fit(ln["text"], ln.get("bold", bold_default), (x1 - x0), slot * (1.0 - gap_share))
            placed.append({"line": ln, "font": f, "box": box, "cx": (x0 + x1) / 2.0, "cy": y + slot / 2.0,
                           "slot": (x0, y, x1, y + slot)})
            y += slot
    for p in placed:
        p["cap_px"] = p["font"].size * CAP_RATIO
    return {"size": (w, h), "style": st, "border_px": bw, "lines": placed, "pictograms": list(zip(pics, pic_boxes)),
            "min_cap_px": min((p["cap_px"] for p in placed if not p["line"].get("fine")), default=0.0)}


def label_image(lines, pictograms=(), size_px=(512, 256), style=None) -> np.ndarray:
    """The label as an RGB array (h, w, 3)."""
    from PIL import Image, ImageDraw

    lay = layout(lines, pictograms, size_px, style)
    st = lay["style"]
    w, h = lay["size"]
    im = Image.new("RGB", (w, h), rgb(st["bg"]))
    d = ImageDraw.Draw(im)
    if st.get("border"):
        col, _ = st["border"]
        bw = lay["border_px"]
        d.rectangle([0, 0, w - 1, h - 1], fill=rgb(col))
        d.rectangle([bw, bw, w - 1 - bw, h - 1 - bw], fill=rgb(st["bg"]))
    for p in lay["lines"]:
        ln = p["line"]
        fg = ln.get("fg", st["fg"])
        if "band" in p:
            band_bg, band_fg = st["header"] if st.get("header") else ("ghs_red", "white")
            band_bg = ln.get("bg", band_bg)
            fg = ln.get("fg", band_fg)
            d.rectangle(list(p["band"]), fill=rgb(band_bg))
        elif ln.get("bg"):
            x0, y0, x1, y1 = p["slot"]
            d.rectangle([x0, y0 + 1, x1, y1 - 1], fill=rgb(ln["bg"]))
        box = p["box"]
        tw = box[2] - box[0]
        cap = p["cap_px"]
        align = ln.get("align", "center")
        if align == "left" and "slot" in p:
            x = p["slot"][0] - box[0]
        else:
            x = p["cx"] - tw / 2.0 - box[0]
        # centre the capitals on the line's centre: the baseline sits half a cap height below it
        ascent = p["font"].getmetrics()[0]
        y = p["cy"] + cap / 2.0 - ascent
        d.text((int(round(x)), int(round(y))), ln["text"], font=p["font"], fill=rgb(fg))
    for name, (bx, by, s) in lay["pictograms"]:
        s = int(s)
        if s < 4:
            continue
        pic = _pictogram_cached(name, s, rgb(st["fg"]), rgb(st["bg"]))
        im.paste(pic, (int(bx), int(by)), pic)
    return np.asarray(im).copy()


def tear(image: np.ndarray, fraction: float, side: str = "right") -> np.ndarray:
    """The label with a part torn off (0.5.0, a label that is only partly legible): the `fraction` of its width on
    `side` is gone down to the pale paper that stays stuck to the glass, along a ragged edge. Deterministic."""
    img = np.asarray(image)[:, :, :3].copy()
    h, w = img.shape[:2]
    y = np.arange(h, dtype=np.float64)
    amp = 0.06 * w
    edge = w * (1.0 - fraction) + amp * (0.55 * np.sin(y * 0.071) + 0.30 * np.sin(y * 0.23 + 1.3) + 0.15 * np.sin(y * 0.61 + 0.4))
    xx = np.arange(w, dtype=np.float64)[None, :]
    gone = xx > edge[:, None] if side == "right" else xx < (w - edge)[:, None]
    fibre = (np.abs(xx - edge[:, None]) < 0.012 * w) if side == "right" else (np.abs(xx - (w - edge)[:, None]) < 0.012 * w)
    residue = np.array([214, 206, 188], dtype=np.uint8)
    streak = ((np.arange(h) // 7) % 3 == 0)[:, None] & gone
    img[gone] = residue
    img[streak] = np.array([196, 188, 170], dtype=np.uint8)
    img[fibre & ~gone] = np.array([240, 238, 232], dtype=np.uint8)
    return img


def label_texture(lines, pictograms=(), size_px=(512, 256), style=None) -> bytes:
    """A label as PNG bytes: `lines` of text (strings, `(text, relative height)` pairs or dicts with `text`, `h`,
    `fg`, `bg`, `bold`, `fine`), pictograms by name, in one of the `STYLES` (or a dict that overrides one)."""
    return _png.encode(label_image(lines, pictograms, size_px, style))


def compose(size_px, bg, parts) -> np.ndarray:
    """A texture of `size_px` filled with `bg` with images pasted in: `parts` is a list of `(image, (x, y))` with the
    top left corner of each. Used for wrap-around labels (a front panel and a back panel on a coloured band)."""
    w, h = int(size_px[0]), int(size_px[1])
    out = np.zeros((h, w, 3), dtype=np.uint8)
    out[:, :] = rgb(bg)
    for img, (x, y) in parts:
        img = np.asarray(img)[:, :, :3]
        x, y = int(x), int(y)
        hh, ww = min(img.shape[0], h - y), min(img.shape[1], w - x)
        if hh > 0 and ww > 0:
            out[y:y + hh, x:x + ww] = img[:hh, :ww]
    return out


def stripes(size_px, colors=("warning_yellow", "black"), pitch: int = 24) -> np.ndarray:
    """Diagonal hazard stripes."""
    w, h = int(size_px[0]), int(size_px[1])
    yy, xx = np.mgrid[0:h, 0:w]
    k = ((xx + yy) // int(pitch)) % len(colors)
    lut = np.array([rgb(c) for c in colors], dtype=np.uint8)
    return lut[k]


def texture_size(width_mm: float, height_mm: float, px_per_mm: float = PX_PER_MM) -> tuple[int, int]:
    """Pixels for a label of the given printed size, capped at `MAX_TEXTURE` on the longer side."""
    s = min(px_per_mm, MAX_TEXTURE / max(width_mm, height_mm))
    return max(16, int(round(width_mm * s))), max(16, int(round(height_mm * s)))


# ----------------------------------------------------------------------------------------------------------------------
# Carriers: a flat panel and a shell around a cylinder or cone, both with texture coordinates
# ----------------------------------------------------------------------------------------------------------------------

def flat_panel(width: float, height: float, thick: float = 0.4) -> M.Mesh:
    """A thin box in the xy plane whose +z face shows the texture upright: u along +x, the top of the image at +y."""
    m = M.box((width, height, thick))
    uv = np.array([[x / width + 0.5, y / height + 0.5] for x, y, _ in m.v])
    return M.Mesh(m.v, m.f, uv)


def panel_rotation(normal: Sequence[float], up: Sequence[float]) -> np.ndarray:
    """The rotation that turns `flat_panel` so that its face looks along `normal` with the top of the text towards `up`."""
    n = np.asarray(normal, dtype=np.float64)
    n = n / np.linalg.norm(n)
    u = np.asarray(up, dtype=np.float64)
    u = u - np.dot(u, n) * n
    u = u / np.linalg.norm(u)
    return np.stack([np.cross(u, n), u, n], axis=1)


def wrap_shell(r0: float, r1: float, z0: float, z1: float, arc_deg: float = 360.0, center_deg: float = -90.0,
               thick: float = 0.3, sink: float = 0.15, n: int | None = None) -> M.Mesh:
    """A thin shell around a vertical cylinder or cone (radius `r0` at `z0`, `r1` at `z1`) that shows a texture on its
    outside: the middle of the image at azimuth `center_deg` (-90 is the front, -y), reading left to right for someone
    looking at it from outside, the top of the image at `z1`. A full turn has its seam at the back."""
    if n is None:
        n = max(8, int(round(48 * arc_deg / 360.0)))
    a0 = math.radians(center_deg - arc_deg / 2.0)
    a1 = math.radians(center_deg + arc_deg / 2.0)
    ang = np.linspace(a0, a1, n + 1)
    v, uv = [], []
    for layer, dr in ((0, thick), (1, -sink)):                    # outer, inner
        for zi, (r, z) in enumerate(((r0, z0), (r1, z1))):
            for k, a in enumerate(ang):
                v.append(((r + dr) * math.cos(a), (r + dr) * math.sin(a), z))
                uv.append((k / n, float(zi)))
    idx = lambda layer, zi, k: layer * 2 * (n + 1) + zi * (n + 1) + k          # noqa: E731
    f = []
    for k in range(n):
        ob0, ob1, ot0, ot1 = idx(0, 0, k), idx(0, 0, k + 1), idx(0, 1, k), idx(0, 1, k + 1)
        ib0, ib1, it0, it1 = idx(1, 0, k), idx(1, 0, k + 1), idx(1, 1, k), idx(1, 1, k + 1)
        f += [(ob0, ob1, ot1), (ob0, ot1, ot0)]                   # outside
        f += [(ib0, it1, ib1), (ib0, it0, it1)]                   # inside
        f += [(ot0, ot1, it1), (ot0, it1, it0)]                   # top rim
        f += [(ob0, ib1, ob1), (ob0, ib0, ib1)]                   # bottom rim
    o0, o1, i0, i1 = idx(0, 0, 0), idx(0, 1, 0), idx(1, 0, 0), idx(1, 1, 0)
    f += [(o0, o1, i1), (o0, i1, i0)]                             # the two ends of the arc
    o0, o1, i0, i1 = idx(0, 0, n), idx(0, 1, n), idx(1, 0, n), idx(1, 1, n)
    f += [(o0, i1, o1), (o0, i0, i1)]
    return M.Mesh(np.array(v), np.array(f), np.array(uv))


def decode(png_bytes: bytes) -> np.ndarray:
    return _png.decode(png_bytes)


def contact_sheet(tiles: Sequence[tuple[str, np.ndarray]], columns: int = 6, tile=160, caption_px: int = 13,
                  bg=(238, 238, 238)) -> np.ndarray:
    """Tiles `(caption, image)` in a grid with captions underneath, as an RGB array. `tile`: side, or (width, height)."""
    from PIL import Image, ImageDraw

    tw, th = (tile, tile) if isinstance(tile, int) else tile
    rows = int(math.ceil(len(tiles) / columns))
    cell_h = th + caption_px + 8
    sheet = Image.new("RGB", (columns * (tw + 6) + 6, rows * cell_h + 6), bg)
    d = ImageDraw.Draw(sheet)
    f = _font(False, caption_px)
    for i, (cap, img) in enumerate(tiles):
        a = np.asarray(img)
        im = Image.fromarray(a)
        if im.mode == "RGBA":
            back = Image.new("RGB", im.size, (255, 255, 255))
            back.paste(im, (0, 0), im)
            im = back
        im.thumbnail((tw, th), Image.LANCZOS)
        x = 6 + (i % columns) * (tw + 6)
        y = 6 + (i // columns) * cell_h
        sheet.paste(im, (x + (tw - im.width) // 2, y + (th - im.height) // 2))
        d.text((x + 2, y + th + 1), cap[: max(8, tw // 7)], font=f, fill=(20, 20, 20))
    return np.asarray(sheet).copy()
