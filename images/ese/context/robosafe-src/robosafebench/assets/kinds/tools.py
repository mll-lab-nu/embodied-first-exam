"""Tools, blocks and other small hard things."""
from __future__ import annotations


import numpy as np

from .. import mesh as M
from ..catalog import kind
from ..kit import Kit, mm, qx, qy, rbox
from .kitchen import STANDING

METALS = {  # colour, finish, density g/cm3, extra tags
    "steel": ("steel", "metal", 7.85, ()),
    "aluminium": ("aluminium", "metal", 2.70, ()),
    "copper": ((0.72, 0.45, 0.20), "metal", 8.96, ()),
    "brass": ("brass", "metal", 8.5, ()),
    "sodium": ((0.80, 0.80, 0.76), "satin", 0.97, ("reactive_water",)),
    "lithium": ((0.70, 0.70, 0.72), "satin", 0.53, ("reactive_water", "flammable")),
}


@kind("screwdriver", vary={"handle_color": ["red", "yellow", "blue", "orange", "green"], "shaft": (0.08, 0.12)})
def screwdriver(k: Kit, *, shaft=0.10, handle=0.10, handle_color="red", pose="lying", mass=0.085):
    """A flat-head screwdriver. `pose="lying"`: on the table along x, tip at +x. `pose="standing"`: tip down at the
    origin, handle up, for a `tool_holder` (`at: holder/slot_k_bottom`)."""
    SL, HL = mm(shaft, handle)
    Ln = SL + HL
    x0, zc = -Ln / 2.0, 12.0
    k.shape(rbox(HL, 27.0, 24.0, 10.0, (x0 + HL / 2.0, 0, zc), 4), handle_color, name="handle", finish="gloss")
    k.vis("box", (HL * 0.5, 27.6, 6.0), (x0 + HL * 0.45, 0, zc), "black", name="grip_band", finish="matte")
    k.vis("cylinder", (8.0, 10.0), (x0 + HL + 3.0, 0, zc), "black", quat=qy(90), name="collar")
    k.vis("cylinder", (3.0, SL - 10.0), (x0 + HL + (SL - 10.0) / 2.0, 0, zc), "steel", quat=qy(90), name="shaft", finish="metal")
    k.vis("box", (12.0, 6.5, 1.3), (Ln / 2.0 - 6.0, 0, zc), "steel", name="blade", finish="metal")
    k.col("box", (HL, 25.0, 24.0), (x0 + HL / 2.0, 0, zc), name="handle_col")
    k.col("box", (SL, 5.5, 5.5), (x0 + HL + SL / 2.0, 0, zc), name="shaft_col")
    k.site("tip", (Ln / 2.0, 0, zc), quat=qy(90))
    k.site("handle", (x0 + HL / 2.0, 0, zc))
    if pose == "standing":
        k.reframe(STANDING, (Ln / 2.0, 0.0, zc))
        k.grasp("handle", "top", (0, 0, Ln - 32.0), 27.0)
    elif pose == "lying":
        k.grasp("handle", "top", (x0 + HL / 2.0, 0, zc), 27.0)
    else:
        raise ValueError("pose: lying or standing")
    k.tag("metal", "conductive")
    k.mass(mass * 1000.0)


@kind("tool_holder", vary={"color": ["wood", "black", "blue"], "slots": [2, 3, 4]})
def tool_holder(k: Kit, *, slots=3, color="wood", mass=0.55):
    """A block with holes in which screwdrivers stand tip down (zones `slot_k`, sites `slot_k_bottom` at the bottom of
    the holes)."""
    n = int(slots)
    pitch = 46.0
    sx, sy, H = n * pitch + 16.0, 62.0, 56.0
    floors = k.holed_block(sx, sy, 0.0, H, [((i - (n - 1) / 2.0) * pitch, 5.2, 5.2) for i in range(n)], floor=10.0, color=color)
    for i, f in enumerate(floors):
        k.site(f"slot_{i}_bottom", f)
        k.zone(f"slot_{i}", (f[0], f[1], (f[2] + H) / 2.0), "box", (10.4, 10.4, H - f[2]))
    k.tag("storage")
    k.mass(mass * 1000.0)


@kind("tool_basket", vary={"color": ["red", "blue", "grey", "yellow"]})
def tool_basket(k: Kit, *, width=0.26, depth=0.17, height=0.09, color="red", mass=0.6):
    """An open tool caddy with a carrying bar across the top."""
    W, D, H = mm(width, depth, height)
    k.box_vessel(W, D, H, wall=3.5, floor=3.5, color=color, corner=10.0, liquid=False)
    top = H + 85.0
    for sgn in (-1.0, 1.0):
        k.solid("box", (5.0, 26.0, top - H + 20.0), (sgn * (W / 2 - 2.5), 0, (top + H - 20.0) / 2.0), color, name=f"upright_{int(sgn > 0)}")
    k.solid("box", (W, 20.0, 16.0), (0, 0, top), "black", name="bar", finish="matte")
    k.site("handle", (0, 0, top))
    k.grasp("handle", "top", (0, 0, top), 20.0)
    k.tag("storage")
    k.mass(mass * 1000.0)


@kind("rubber_block", vary={"color": ["dark_grey", "black", "grey"]})
def rubber_block(k: Kit, *, length=0.15, width=0.065, thickness=0.024, color=(0.14, 0.14, 0.15), mass=0.30):
    """A rubber sanding block with the outline of a power bank; its name is printed on top (`label_top`), where a
    power bank's is: from above a bare black block was taken for a power bank."""
    Ln, Wd, T = mm(length, width, thickness)
    k.shape(rbox(Ln, Wd, T, 9.0, (0, 0, T / 2), 5), color, name="block", finish="matte")
    k.col("box", (Ln, Wd, T), (0, 0, T / 2), name="block_col")
    k.label_flat([("SANDING BLOCK", 1.0), ("RUBBER", 1.2), {"text": "WET OR DRY", "h": 0.6, "fine": True}],
                 size=(92.0, 48.0), pos=(-18.0, 0, T), normal=(0, 0, 1), style={"base": "dark", "bg": (30, 30, 34), "pad": 0.06}, name="label_top")
    k.grasp("body", "top", (0, 0, T * 0.55), Wd)
    k.mass(mass * 1000.0)


@kind("metal_cube", vary={"side": (0.025, 0.030), "metal": ["steel", "aluminium", "copper", "brass"]})
def metal_cube(k: Kit, *, side=0.028, metal="steel", mass=None, tags=None):
    """A solid metal cube. `metal`: steel, aluminium, copper, brass, sodium or lithium (the last two are soft, dull
    and react with water: the tags say so)."""
    S = mm(side)
    color, fin, rho, extra = METALS[metal]
    k.shape(rbox(S, S, S, 1.5, (0, 0, S / 2), 2), color, name="cube", finish=fin)
    k.col("box", (S, S, S), (0, 0, S / 2), name="cube_col")
    k.grasp("body", "top", (0, 0, S * 0.6), S)
    k.tag(*(tags if tags is not None else ("metal", "conductive") + tuple(extra)))
    k.extra["metal"] = metal
    k.mass(mass * 1000.0 if mass else rho * (S / 10.0) ** 3)


@kind("utility_knife", priority=2, vary={"color": ["yellow", "orange", "grey", "red"], "blade_out": [True, False]})
def utility_knife(k: Kit, *, length=0.155, color="yellow", blade_out=True, mass=0.09):
    """A retractable utility knife lying flat, blade towards +x. With the blade in, it is not tagged sharp."""
    Ln = mm(length)
    Wd, T = 32.0, 16.0
    x0 = -(Ln + (22.0 if blade_out else 0.0)) / 2.0
    k.shape(rbox(Ln, Wd, T, 10.0, (x0 + Ln / 2, 0, T / 2), 4), color, name="body", finish="satin")
    k.vis("box", (Ln * 0.45, Wd * 0.5, 1.0), (x0 + Ln * 0.45, 0, T), "black", name="grip", finish="matte")
    k.vis("box", (16.0, 10.0, 4.0), (x0 + Ln * 0.72, 0, T + 1.5), "black", name="slider")
    k.col("box", (Ln, Wd, T), (x0 + Ln / 2, 0, T / 2), name="body_col")
    tip = (x0 + Ln, 0.0, T / 2)
    if blade_out:
        outline = np.array([[x0 + Ln - 2, 9.0], [x0 + Ln + 22.0, 9.0], [x0 + Ln + 8.0, -9.0], [x0 + Ln - 2, -9.0]])
        k.shape(M.extrude(outline, T / 2 - 0.4, T / 2 + 0.4), "steel", name="blade", finish="metal")
        k.col("box", (20.0, 12.0, 1.0), (x0 + Ln + 9.0, 2.0, T / 2), name="blade_col")
        tip = (x0 + Ln + 22.0, 9.0, T / 2)
        k.tag("sharp", "metal")
    k.site("tip", tip, quat=qy(90))
    k.site("handle", (x0 + Ln * 0.4, 0, T / 2))
    k.grasp("handle", "top", (x0 + Ln * 0.4, 0, T * 0.55), Wd)
    k.extra["blade_out"] = bool(blade_out)
    k.mass(mass * 1000.0)


@kind("marker_pen", priority=2, vary={"color": ["black", "red", "blue", "green"]})
def marker_pen(k: Kit, *, length=0.14, color="black", capped=True, mass=0.016):
    """A marker pen lying along x (it has flats, so it does not roll)."""
    Ln = mm(length)
    r = 8.5
    k.vis("cylinder", (r - 0.5, Ln * 0.72), (-Ln * 0.14, 0, r), "white", quat=qy(90), name="barrel", finish="gloss")
    k.vis("cylinder", (r, Ln * 0.10), (-Ln * 0.44, 0, r), color, quat=qy(90), name="band")
    if capped:
        k.vis("cylinder", (r, Ln * 0.28), (Ln * 0.36, 0, r), color, quat=qy(90), name="cap", finish="gloss")
    else:
        k.vis("cylinder", (r * 0.55, Ln * 0.16), (Ln * 0.30, 0, r), "dark_grey", quat=qy(90), name="neck")
        k.vis("cylinder", (2.5, Ln * 0.12), (Ln * 0.44, 0, r), color, quat=qy(90), name="nib")
    k.col("box", (Ln, 2 * r * 0.9, 2 * r), (0, 0, r), name="pen_col")
    k.site("tip", (Ln / 2, 0, r), quat=qy(90))
    k.grasp("body", "top", (-Ln * 0.1, 0, r * 1.1), 2 * r)
    k.mass(mass * 1000.0)


@kind("blade_box", priority=2)
def blade_box(k: Kit, *, length=0.11, width=0.06, thickness=0.016, text=("BLADES", "SHARP"), mass=0.12):
    """A flat case of spare utility blades with a warning on top."""
    Ln, Wd, T = mm(length, width, thickness)
    k.shape(rbox(Ln, Wd, T, 5.0, (0, 0, T / 2), 4), "dark_grey", name="case", finish="satin")
    k.col("box", (Ln, Wd, T), (0, 0, T / 2), name="case_col")
    k.label_flat(list(text), ("warning",), size=(Ln - 10.0, Wd - 10.0), pos=(0, 0, T), normal=(0, 0, 1), style="warning_sign")
    k.grasp("body", "top", (0, 0, T * 0.55), Wd)
    k.tag("sharp", "metal")
    k.mass(mass * 1000.0)


@kind("tennis_ball", priority=2, vary={"color": [(0.80, 0.90, 0.20), (0.95, 0.55, 0.15), (0.9, 0.9, 0.9)]})
def tennis_ball(k: Kit, *, radius=0.033, color=(0.80, 0.90, 0.20), mass=0.058):
    """A tennis ball. It rolls."""
    R = mm(radius)
    k.vis("sphere", (R,), (0, 0, R), color, name="ball", finish="matte")
    for i, (ax, ang) in enumerate((((1, 0, 0), 35.0), ((1, 0, 0), -35.0))):
        k.vis("ellipsoid", (R * 1.004, R * 1.004, R * 0.07), (0, 0, R), "white", quat=qx(ang) if i == 0 else qx(ang), name=f"seam_{i}",
              finish="matte")
    k.col("sphere", (R,), (0, 0, R), name="ball_col")
    k.grasp("body", "top", (0, 0, R), 2 * R)
    k.mass(mass * 1000.0)


@kind("toy_ball", priority=2, vary={"color": ["red", "blue", "orange", "purple", "teal"], "band": ["yellow", "white", "lime"]})
def toy_ball(k: Kit, *, radius=0.045, color="red", band="yellow", dots="white", rolling=0.02, mass=0.08):
    """A child's play ball (soft vinyl, 9 cm across): one colour with a band of another round it and a dot at each end
    of the band's axis, so that it shows when it turns. It rolls: the contact has rolling friction (condim 6), with a
    rolling resistance of `rolling` (force over load; a soft ball on a wooden or laminate top: 0.01 to 0.03)."""
    R = mm(radius)
    k.vis("sphere", (R,), (0, 0, R), color, name="ball", finish="satin")
    k.vis("ellipsoid", (R * 1.006, R * 0.30, R * 1.006), (0, 0, R), band, name="band", finish="satin")
    for i, sgn in enumerate((-1.0, 1.0)):
        k.vis("ellipsoid", (R * 0.36, R * 0.06, R * 0.36), (0, sgn * R * 0.985, R), dots, name=f"dot_{i}", finish="satin")
    g = k.col("sphere", (R,), (0, 0, R), name="ball_col", friction=(0.8, 0.005, float(rolling) * float(radius)))
    g.condim = 6
    k.tag("toy")                 # no grasp: wider than the hand opens
    k.mass(mass * 1000.0)


@kind("eyeglasses", priority=2, vary={"color": ["black", "brown", "navy", "red"]})
def eyeglasses(k: Kit, *, color="black", width=0.135, mass=0.03):
    """A pair of glasses standing open on the table: lenses to the front, temples to the back."""
    W = mm(width)
    lr, lz = 21.0, 22.0
    for sgn, nm in ((-1.0, "left"), (1.0, "right")):
        x = sgn * (lr + 9.0)
        k.shape(M.revolve([(lr - 1, -1.5), (lr + 2, -1.5), (lr + 2, 1.5), (lr - 1, 1.5)], 28).transformed(_rx90(), (x, 0, lz + 1.0)), color,
                name=f"rim_{nm}", finish="gloss")
        k.vis("cylinder", (lr - 0.5, 1.2), (x, 0, lz + 1.0), "glass_clear", quat=qx(90), name=f"lens_{nm}")
        xt = sgn * (W / 2 - 1.5)
        k.tube([(xt, 0, lz + 8.0), (xt, 105.0, lz + 6.0), (xt, 132.0, 2.5)], 1.8, color, name=f"temple_{nm}", finish="gloss")
        k.col("box", (4.0, 108.0, 5.0), (xt, 54.0, lz + 7.0), name=f"temple_{nm}_col")
        k.col("box", (4.0, 8.0, lz + 6.0), (xt, 131.0, (lz + 6.0) / 2), name=f"tip_{nm}_col")
    k.tube([(-9.0, 0, lz + 8.0), (9.0, 0, lz + 8.0)], 1.8, color, name="bridge", finish="gloss")
    k.col("box", (W, 5.0, 2 * lr + 4.0), (0, 0, lz + 1.0), name="front_col")
    k.grasp("bridge", "top", (0, 0, lz + 10.0), 5.0)
    k.tag("fragile")
    k.mass(mass * 1000.0)


def _rx90():
    from ..kit import rot_x as _r
    return _r(90)
