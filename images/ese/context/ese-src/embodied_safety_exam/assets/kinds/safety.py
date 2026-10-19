"""Safety devices and signs."""
from __future__ import annotations

import math

import numpy as np

from .. import labels as L
from .. import mesh as M
from ..catalog import kind
from ..kit import Kit, mm, qx, rbox


@kind("estop_button", priority=2, fixed=True)
def estop_button(k: Kit, *, size=0.085, height=0.06, text="EMERGENCY STOP", mass=0.4, shroud=False, wear=None):
    """An emergency stop: a red mushroom button (control `stop`) on a yellow housing with the words on its front.
    Zone `access`: the space above it that has to stay free.

    0.5.0 (the member `hazard_hidden`): `shroud=True`: a portable stop in a plain grey housing whose button sits under
    a grey hinged guard: from outside it is a grey box with the words on its front, nothing of the mushroom shows;
    `wear`: the words worn (`embodied_safety_exam.assets.wear`)."""
    S, H = mm(size, height)
    k.shape(rbox(S, S, H, 8.0, (0, 0, H / 2), 4), "grey" if shroud else "warning_yellow", name="housing", finish="satin" if shroud else "gloss")
    k.col("box", (S, S, H), (0, 0, H / 2), name="housing_col")
    if not shroud:
        k.decal(_on_yellow(L.pictogram("emergency_stop", 256)), size=(S - 6.0, S - 6.0),
                pos=(0, 0, H), normal=(0, 0, 1), name="ring_label")
    b = k.button("stop", (0, 0, H), axis=(0, 0, 1), size=(26.0, 26.0), round=True, color="ghs_red", travel=6.0, proud=14.0,
                 stiffness=350.0)
    k.shape(M.revolve([(0, 14.0), (26.0, 14.0), (27.0, 18.0), (22.0, 26.0), (0, 30.0)], 36), "ghs_red", body=b, name="mushroom",
            finish="gloss")
    k.col("cylinder", (26.0, 14.0), (0, 0, 21.0), body=b, name="mushroom_col")
    if shroud:                                                 # the guard over the button: a grey box with a hinge line
        g = 38.0
        k.shape(rbox(S, S, g, 6.0, (0, 0, H + g / 2.0), 4), "grey", name="guard", finish="satin")
        k.vis("box", (S - 4.0, 1.5, 3.0), (0, S / 2.0 - 1.0, H + g - 2.0), "dark_grey", name="hinge")
        k.col("box", (S, S, 4.0), (0, 0, H + g - 2.0), name="guard_col")    # its lid only, clear of the mushroom (top at H + 30)
    k.label_flat(text.split() if len(text) > 10 else [text], size=(S - 8.0, H - 12.0), pos=(0, -S / 2, H / 2),
                 style={"base": "plain", "bg": "warning_yellow", "border": None}, **({"wear": wear} if wear else {}))
    k.zone("access", (0, 0, H + 100.0), "cylinder", (90.0, 200.0))
    k.tag("safety_device")
    k.mass(mass * 1000.0)


def _on_yellow(rgba: np.ndarray) -> np.ndarray:
    """A pictogram with its transparent surround filled with housing yellow."""
    out = np.zeros(rgba.shape[:2] + (3,), dtype=np.uint8)
    out[:, :] = L.COLORS["warning_yellow"]
    a = rgba[:, :, 3:4].astype(np.float64) / 255.0
    return (out * (1 - a) + rgba[:, :, :3] * a).astype(np.uint8)


@kind("floor_sign", priority=2, minor_contact=True, vary={"lines": [["CAUTION", "WET FLOOR"], ["CAUTION", "CLEANING"], ["DANGER", "KEEP OUT"]]})
def floor_sign(k: Kit, *, width=0.30, height=0.62, lines=("CAUTION", "WET FLOOR"), pictogram="wet_floor", color="warning_yellow",
               mass=1.1):
    """An A-frame floor sign, printed on both faces. A hand hole at the top to carry it by."""
    W, H = mm(width, height)
    lean = math.radians(14.0)
    half = H * math.sin(lean)
    zt = H * math.cos(lean)
    for sgn in (-1.0, 1.0):
        n = (0.0, sgn * math.cos(lean), math.sin(lean))
        up = (0.0, -sgn * math.sin(lean), math.cos(lean))
        c = (0.0, sgn * half / 2.0, zt / 2.0 + 1.0)
        k.solid("box", (W, 6.0, H), c, color, quat=qx(sgn * math.degrees(lean)), name=f"panel_{'front' if sgn < 0 else 'back'}")
        k.label_flat(list(lines), (pictogram,) if pictogram else (), size=(W - 30.0, H * 0.62),
                     pos=(c[0] + n[0] * 3.0, c[1] + n[1] * 3.0 - up[1] * 30.0, c[2] + n[2] * 3.0 - up[2] * 30.0), normal=n, up=up,
                     style={"base": "warning_sign", "bg": color, "border": None, "pictograms": "top", "pictogram_share": 0.5},
                     name="label" if sgn < 0 else "label_back")
        k.col("box", (W, 14.0, 6.0), (0, sgn * (half + 2.0), 3.0), name=f"foot_{'front' if sgn < 0 else 'back'}")
    k.solid("box", (W * 0.5, 16.0, 14.0), (0, 0, zt + 4.0), color, name="ridge")
    k.site("handle", (0, 0, zt + 4.0))
    k.grasp("ridge", "top", (0, 0, zt + 2.0), 16.0)
    k.tag("safety_device")
    k.mass(mass * 1000.0)


# (lit, unlit) colour of each lamp. 0.5.1: an unlit lens is dull, a desaturated tint (saturation 0.4) drawn as a lit
# surface, not emissive, and a little translucent (about 30 % value in the front image); the lit lamp is an emissive
# core over the lens with a faint halo around it. Up to 0.5.0 every lens glowed, the unlit ones in a saturated colour at half value (amber 131,80,15
# beside a lit red 254,41,31 in the front image), so "only red is on" rested on a comparison of brightness.
LIGHT = {"red": ((1.0, 0.10, 0.08), (0.46, 0.28, 0.28)), "amber": ((1.0, 0.62, 0.05), (0.46, 0.39, 0.28)),
         "green": ((0.15, 1.0, 0.25), (0.28, 0.46, 0.31)), "blue": ((0.20, 0.45, 1.0), (0.28, 0.34, 0.46))}
LENS_ALPHA = 0.85       # the unlit lens: a little translucent
HALO_ALPHA = 0.22       # the lit lamp's halo


@kind("stack_light", priority=2, fixed=True, vary={"state": ["off", "red", "amber", "green"]})
def stack_light(k: Kit, *, segments=("red", "amber", "green"), state="off", height=0.30, mass=0.6):
    """A signal tower: stacked lamps, top first. Looks: one per colour (that lamp lit, the others dark) and `off`.
    Each lamp is a dull lens (`lamp_<colour>`, drawn as a surface and solid), an emissive core just over it
    (`glow_<colour>`) and a translucent halo (`halo_<colour>`), both drawn only while the lamp is lit (alpha 0 else)."""
    H = mm(height)
    segs = [s for s in segments]
    seg_h = 46.0
    base_h = 26.0
    pole = max(30.0, H - base_h - seg_h * len(segs) - 10.0)
    k.shape(M.revolve([(0, 0), (40, 0), (40, base_h - 6), (30, base_h), (0, base_h)], 36), "black", name="base")
    k.foot(40.0, 0.0, 6.0)
    k.col("cylinder", (38.0, base_h - 1.0), (0, 0, base_h / 2 + 0.5), name="base_col")
    k.solid("cylinder", (11.0, pole), (0, 0, base_h + pole / 2), "aluminium", name="pole", finish="metal")
    z = base_h + pole
    for i, colour in enumerate(reversed(segs)):                    # built bottom-up; the first named is on top
        on, off = LIGHT[colour]
        k.solid("cylinder", (30.0, seg_h - 4.0), (0, 0, z + seg_h / 2), off, name=f"lamp_{colour}", finish="gloss", alpha=LENS_ALPHA)
        k.vis("cylinder", (30.6, seg_h - 3.4), (0, 0, z + seg_h / 2), on, name=f"glow_{colour}", finish="glow", alpha=0.0)
        k.vis("cylinder", (36.0, seg_h - 1.0), (0, 0, z + seg_h / 2), on, name=f"halo_{colour}", finish="glow", alpha=0.0)
        k.vis("cylinder", (31.0, 4.0), (0, 0, z + seg_h - 2.0), "black", name=None)
        z += seg_h
    k.shape(M.revolve([(0, z), (31, z), (31, z + 6), (20, z + 12), (0, z + 12)], 36), "black", name="cap")
    for look in segs + ["off"]:
        for colour in segs:
            lit = colour == look
            k.look(look, f"lamp_{colour}", LIGHT[colour][1], LENS_ALPHA)
            k.look(look, f"glow_{colour}", LIGHT[colour][0], 0.97 if lit else 0.0)
            k.look(look, f"halo_{colour}", LIGHT[colour][0], HALO_ALPHA if lit else 0.0)
    k.set_look(state if state in segs else "off")
    k.tag("safety_device", "electrical")
    k.mass(mass * 1000.0)
