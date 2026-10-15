"""Kitchen things: burner, toaster, kettle, cans, pots, knives and food."""
from __future__ import annotations

import math

import numpy as np

from .. import mesh as M
from ..catalog import kind
from ..kit import Kit, mm, qx, qy, qz, rbox, rot_x, rot_y, rot_z

GLOW_HOT = (1.0, 0.33, 0.06, 1.0)
COIL_COLD = (0.13, 0.13, 0.14, 1.0)


def _coil_mesh(r_out: float, turns: int, z: float, thick: float = 7.0) -> M.Mesh:
    """Concentric heating rings joined by three spokes (a spiral coil, near enough)."""
    parts = []
    for k in range(turns):
        r = r_out - k * (r_out - 14.0) / max(1, turns - 1)
        parts.append(M.revolve([(r - thick / 2, z), (r + thick / 2, z), (r + thick / 2, z + thick * 0.8),
                                (r - thick / 2, z + thick * 0.8)], 40))
    for a in (90.0, 210.0, 330.0):
        parts.append(M.box((r_out - 6.0, 5.0, 3.0), ((r_out - 6.0) / 2.0 + 6.0, 0.0, z + 1.5)).transformed(rot_z(a)))
    return M.merge(parts)


@kind("hot_plate", vary={"width": (0.22, 0.26), "color": ["dark_grey", "white", "black", "silver"],
                         "style": ["coil", "coil", "plate"]})
def hot_plate(k: Kit, *, width=0.24, depth=0.26, height=0.075, style="coil", color="dark_grey", state="off",
              cord=True, warning_label=True, mass=1.6, glow=True, button="front", lamp_mm=None):
    """A single burner: a coil (or a flat laboratory plate) on a low housing, a power button and a lamp at the front.
    Looks `on` (the coil glows, lamp lit) and `off`. Zone `surface`: the hot surface and 12 mm above it.
    `glow=False` (since 0.5.0): the surface looks the same on and off, as a ceramic plate does, and only the lamp
    tells; the lamp then has a site, `lamp`. `button="top"` (since 0.5.0): the power button sits on top of the housing at
    its front left corner, pressed from above (the default is on the front face). `lamp_mm` (after 0.5.1): the lamp's
    diameter in millimetres (default: 7, or 12 with `glow=False`); `hot_plate(glow=False, lamp_mm=5)` is an indicator
    LED that the fixed cameras show as a pixel or two (`c_burner_left_on`, `hazard_hidden` `closer`)."""
    if button not in ("front", "top"):
        raise ValueError("button: front or top")
    W, D, H = mm(width, depth, height)
    k.shape(rbox(W, D, H - 8.0, 14.0, (0, 0, (H - 8.0) / 2.0 + 4.0)), color, name="housing", finish="satin")
    for sx in (-1, 1):                                            # four feet
        for sy in (-1, 1):
            k.solid("box", (22.0, 22.0, 6.0), (sx * (W / 2 - 26), sy * (D / 2 - 26), 3.0), "rubber", finish="matte")
    k.col("box", (W, D, H - 9.0), (0, 0, (H - 9.0) / 2.0 + 5.0), name="housing_col")
    r = min(W, D) * 0.33
    cy = 14.0                                                     # the burner sits a little behind the middle
    top = H - 4.0
    k.shape(M.revolve([(0, top - 1), (r + 14, top - 1), (r + 14, top + 3), (r + 9, top + 3), (r + 6, top + 0.5), (0, top + 0.5)], 40)
            .moved((0, cy, 0)), "steel", name="drip_pan")
    if style == "coil":
        k.shape(_coil_mesh(r, 4, top + 1.0).moved((0, cy, 0)), COIL_COLD, name="coil", finish="glow")
        surf = top + 1.0 + 5.6
        on = GLOW_HOT
    else:
        k.shape(M.cylinder(r + 3, top + 0.5, top + 7.0, 48).moved((0, cy, 0)), (0.16, 0.16, 0.17), name="coil", finish="glow")
        surf = top + 7.0
        on = (0.78, 0.16, 0.07, 1.0)
    cold = COIL_COLD if style == "coil" else (0.16, 0.16, 0.17, 1.0)
    k.look("on", "coil", on if glow else cold)
    k.look("off", "coil", cold)
    side = r * math.sqrt(2.0)
    for a in (0.0, 45.0):                                         # what a pot stands on
        k.col("box", (side, side, surf - top + 2.0), (0, cy, (surf + top - 2.0) / 2.0), quat=qz(a), name=f"burner_col_{int(a)}")
    k.site("burner", (0, cy, surf))
    k.zone("surface", (0, cy, surf + 6.0), "cylinder", (r + 4.0, 12.0))
    # front: power button, lamp, a dial that is only drawn
    if button == "top":
        k.button("power", (-W / 2 + 20.0, -D / 2 + 16.0, H - 4.0), axis=(0, 0, 1), size=(20.0, 16.0), color="red")
    else:
        k.button("power", (-W / 2 + 24.0, -D / 2, H / 2 + 2.0), size=(20.0, 16.0), color="red")
    # (with `glow=False` the lamp is all that tells, and it is drawn larger: 12 mm across instead of 7)
    k.lamp("lamp", (-W / 2 + 47.0, -D / 2 - 0.5, H / 2 + 2.0), radius=(3.5 if glow else 6.0) if lamp_mm is None else float(lamp_mm) / 2.0,
           on=(1.0, 0.25, 0.1), off=(0.30, 0.07, 0.05))
    if not glow:
        k.site("lamp", (-W / 2 + 47.0, -D / 2 - 2.0, H / 2 + 2.0))
    k.vis("cylinder", (13.0, 12.0), (W / 2 - 30.0, -D / 2 - 6.0, H / 2 + 2.0), "black", quat=qx(90), name="dial", finish="satin")
    k.vis("box", (3.0, 2.0, 11.0), (W / 2 - 30.0, -D / 2 - 12.5, H / 2 + 6.5), "white", name="dial_mark")
    if warning_label:
        k.label_flat([("CAUTION", 1.0), ("HOT SURFACE", 1.0)], ("hot_surface",), size=(104.0, 38.0),
                     pos=(6.0, -D / 2, H / 2 + 2.0), style="warning_sign")
    if cord:
        k.cord((W / 2 - 40.0, D / 2, 14.0))
    k.set_look("on" if state == "on" else "off")
    k.tag("hot_surface", "electrical")
    k.mass(mass * 1000.0)


@kind("aerosol_can", vary={"radius": (0.028, 0.033), "height": (0.17, 0.21),
                           "color": ["blue", "red", "teal", "purple", "orange", "navy"],
                           "product": ["AIR DUSTER", "SPRAY PAINT", "DEGREASER", "LUBRICANT", "HAIR SPRAY", "BUG SPRAY"]})
def aerosol_can(k: Kit, *, radius=0.0325, height=0.195, product="AIR DUSTER", brand="ACME", color="blue",
                signal="DANGER", hazard=("EXTREMELY", "FLAMMABLE"), pictograms=("flame", "gas_cylinder"),
                volume_ml=400, label_yaw_deg=0.0, cap_color="white", fill=1.0, mass=None):
    """A spray can: steel body with a domed shoulder, a valve button with its nozzle to the front, a sleeve label
    with the product name, the signal word, the hazard statement and pictograms. `fill` scales the mass."""
    R, Ht = mm(radius, height)
    dome, button_h = 0.55 * R, 15.0
    hb = Ht - dome - 3.0 - button_h
    rv = 0.40 * R
    k.shape(M.revolve([(0, 0), (R - 1.2, 0), (R, 1.2), (R, 4), (R - 0.8, 5), (R - 0.8, hb - 5), (R, hb - 4), (R, hb),
                       (R - 2.5, hb + 2.5), (0.74 * R, hb + 0.62 * dome), (rv + 3, hb + dome), (rv + 3, hb + dome + 3),
                       (0, hb + dome + 3)], 48), "aluminium", name="can")
    zt = hb + dome + 3.0
    k.shape(M.revolve([(0, zt), (rv - 1.5, zt), (rv - 1.5, zt + button_h - 2), (rv - 3.5, zt + button_h),
                       (0, zt + button_h)], 32), cap_color, name="valve_button")
    k.vis("cylinder", (2.2, 3.0), (0, -(rv - 1.0), zt + button_h - 6.0), "black", quat=qx(90), name="nozzle")
    k.round_body(R, 0.0, hb + dome, name="can_col")
    k.col("cylinder", (rv - 1.5, button_h + 3.0), (0, 0, zt + (button_h - 3.0) / 2.0), name="valve_col")
    front = -90.0 + float(label_yaw_deg)
    words = product.split()
    lines = [(product, 1.3)] if len(words) < 2 or len(product) <= 8 else [{"text": " ".join(words[:-1]), "h": 1.3}, (words[-1], 1.1)]
    lines += ([(signal, 1.0)] if signal else []) + [(h, 0.85) for h in hazard]
    lines += [{"text": " ".join(x for x in (brand, f"{int(volume_ml)} ml") if x), "h": 0.5, "fine": True}]
    k.label_wrap(lines, pictograms, radius=R - 0.8, z0=6.0, z1=hb - 6.0, arc_deg=132.0, center_deg=front,
                 style={"base": "product", "header": (color, "white"), "pictograms": "top", "pictogram_share": 0.36},
                 band=color,
                 panels=[{"at_deg": 180.0, "arc_deg": 150.0, "style": "hazard", "pictograms": pictograms,
                          "lines": [signal, {"text": "Pressurised container:", "h": 0.5}, {"text": "may burst if heated.", "h": 0.5},
                                    {"text": "Keep away from heat, hot", "h": 0.5}, {"text": "surfaces, sparks and flames.", "h": 0.5},
                                    {"text": "Do not pierce or burn.", "h": 0.5}]}])
    k.site("spout", (0, -(rv + 0.5), zt + button_h - 6.0), quat=qx(90))
    k.grasp("body", "side", (0, 0, hb * 0.55), 2 * R)
    k.grasp("body_top", "top", (0, 0, hb * 0.8), 2 * R)
    k.tag("pressurized", "flammable", "metal")
    full = 0.11 * 1000 + 0.85 * volume_ml                         # grams: empty can plus contents
    k.mass(mass * 1000.0 if mass else 110.0 + (full - 110.0) * max(0.0, min(1.0, fill)))


from ..model import Joint  # noqa: E402

STANDING = np.array([[0.0, 0.0, 1.0], [0.0, 1.0, 0.0], [-1.0, 0.0, 0.0]])       # lying +x (towards the tip) becomes -z


@kind("food_can", vary={"radius": (0.033, 0.037), "height": (0.095, 0.115), "color": ["tomato", "green", "blue", "yellow"],
                        "product": ["TOMATO SOUP", "BAKED BEANS", "SWEET CORN", "CHICKEN SOUP", "PEACHES"]})
def food_can(k: Kit, *, radius=0.0365, height=0.108, product="TOMATO SOUP", brand="ACME", color="tomato",
             weight="400 g", label_yaw_deg=0.0, mass=0.46):
    """A tin of food: ribbed steel can with a paper label all the way round."""
    R, H = mm(radius, height)
    k.shape(M.revolve([(0, 0.8), (R - 3, 0.8), (R - 2, 0), (R, 0), (R, 3), (R - 1, 4), (R - 1, H - 4), (R, H - 3), (R, H),
                       (R - 2, H), (R - 3, H - 1.2), (0, H - 1.2)], 48), "steel", name="can")
    k.vis("cylinder", (7.0, 1.0), (R * 0.45, 0, H - 0.8), "aluminium", name="ring_pull")
    k.round_body(R, 0.0, H, name="can_col")
    words = product.split()
    head = [(product, 1.2)] if len(product) <= 9 or len(words) == 1 else [(" ".join(words[:-1]), 1.0), (words[-1], 1.0)]
    k.label_wrap([(brand, 0.7)] + head + [{"text": weight, "h": 0.5, "fine": True}], radius=R - 1.0, z0=5.0, z1=H - 5.0, arc_deg=128.0, center_deg=-90.0 + label_yaw_deg,
                 style={"base": "product", "header": ("white", color), "bg": color, "fg": "white"}, band=color,
                 panels=[{"at_deg": 180.0, "arc_deg": 120.0, "style": "paper",
                          "lines": [{"text": "INGREDIENTS", "h": 0.8}, {"text": "water, vegetables,", "h": 0.5},
                                    {"text": "salt, sugar, spices", "h": 0.5}, {"text": "Best before: see lid", "h": 0.5}]}])
    k.grasp("body", "side", (0, 0, H * 0.5), 2 * R)
    k.grasp("body_top", "top", (0, 0, H - 22.0), 2 * R)
    k.tag("metal", "food")
    k.mass(mass * 1000.0)


@kind("billy_can", vary={"color": ["green", "navy", "tomato", "teal"]})
def billy_can(k: Kit, *, radius=0.033, height=0.115, product="BILLY CAN", line="COOKING POT", color="green", water=True,
              label_yaw_deg=0.0, mass=0.50):
    """A camping cook pot, a billy can: an open steel can with a rolled rim and a wire bail folded down at its side,
    drawn with water in it, its name on a band round it. A thing that is made to stand on a stove. Like the other
    cans it is a closed solid: the opening and the water are drawn, nothing can be put into it or poured out of it."""
    R, H = mm(radius, height)
    down = 16.0                                                   # how far below the rim the water stands
    k.shape(M.revolve([(0, 0), (R - 1.5, 0), (R, 1.5), (R, H - 3), (R + 1.4, H - 2), (R + 1.4, H), (R - 1.6, H), (R - 1.6, H - down),
                       (0, H - down)], 48), "steel", name="can", finish="metal")
    if water:
        k.vis("cylinder", (R - 1.8, 1.0), (0, 0, H - down + 0.5), (0.36, 0.62, 0.90), alpha=0.92, name="water", finish="gloss")
    # the bail: pivots at the front and the back under the rim, the wire folded down against the right side of the can
    # (where the `front` and `top` cameras see it); drawn only
    zb, rw = H - 9.0, R + 2.4
    arc = [(rw * math.sin(math.radians(a)), -rw * math.cos(math.radians(a)), zb - 34.0 * math.sin(math.radians(a))) for a in range(0, 181, 20)]
    k.tube(arc, 1.5, (0.20, 0.20, 0.22), finish="metal", name="bail")
    for sy in (-1.0, 1.0):
        k.vis("cylinder", (3.4, 2.4), (0, sy * (R + 0.8), zb), (0.20, 0.20, 0.22), quat=qx(90), name=None, finish="metal")
    k.round_body(R, 0.0, H, name="can_col")
    words = product.split()
    head = [(product, 1.2)] if len(product) <= 9 or len(words) == 1 else [(" ".join(words[:-1]), 1.0), (words[-1], 1.0)]
    k.label_wrap(head + ([(line, 0.8)] if line else []), radius=R + 0.1, z0=10.0, z1=H - 24.0, arc_deg=128.0, center_deg=-90.0 + label_yaw_deg,
                 style={"base": "product", "header": ("white", color), "bg": color, "fg": "white"}, band=color)
    k.grasp("body", "side", (0, 0, H * 0.5), 2 * R)
    k.grasp("body_top", "top", (0, 0, H - 22.0), 2 * R)
    k.tag("metal", "food_vessel")
    k.mass(mass * 1000.0)


@kind("pot", vary={"radius": (0.08, 0.10), "height": (0.085, 0.11), "handle_color": ["black", "red", "dark_grey"]})
def pot(k: Kit, *, radius=0.09, height=0.095, handle=0.17, handle_color="black", contents=None, mass=0.85):
    """A saucepan with one long handle towards +x (`handle`: its length; a short one fits into a microwave)."""
    R, H = mm(radius, height)
    k.round_vessel([(R - 6, 0), (R, 6), (R, H)], wall=2.0, floor=4.0, color="steel", finish="metal", contents=contents, n=14,
                   rings=[0, 2])
    k.shape(M.revolve([(R - 0.5, H - 3), (R + 2.5, H - 3), (R + 2.5, H), (R - 0.5, H)], 48), "steel", finish="metal")
    zh = H - 16.0
    hl = mm(handle)
    k.vis("box", (30.0, 20.0, 5.0), (R + 12.0, 0, zh), "steel")
    k.shape(rbox(hl - 20.0, 24.0, 14.0, 9.0, (R + 20.0 + (hl - 20.0) / 2.0, 0, zh)), handle_color, name="handle", finish="matte")
    k.col("box", (hl, 22.0, 13.0), (R + hl / 2.0, 0, zh), name="handle_col")
    k.site("handle", (R + hl * 0.62, 0, zh))
    k.grasp("handle", "top", (R + hl * 0.62, 0, zh), 24.0)
    k.tag("metal", "food_vessel")
    k.mass(mass * 1000.0 + sum((contents or {}).values()))


@kind("kettle", vary={"color": ["white", "steel", "red", "black"]})
def kettle(k: Kit, *, radius=0.078, height=0.20, color="white", contents=None, state="off", cord=True, switch_at="handle", mass=0.95):
    """An electric kettle on its power base: spout to the front, handle at the back with a switch and a lamp under it.
    `switch_at="base"`: the power base is a wider round plinth, and the switch (a rocker pressed from above) and the
    lamp sit on its ledge on the right (+x) side of the kettle, where a hand coming from above reaches them; the
    handle carries no switch (the switch under the handle cannot be pressed: the handle is over it)."""
    R, H = mm(radius, height)
    fin = "metal" if color == "steel" else "gloss"
    if switch_at not in ("handle", "base"):
        raise ValueError("switch_at: handle or base")
    RB = R + 40.0 if switch_at == "base" else R + 6.0
    if switch_at == "base":
        k.shape(M.revolve([(0, 0), (RB, 0), (RB, 10), (RB - 4, 14), (0, 14)], 48), "dark_grey", name="base")
    else:
        k.shape(M.revolve([(0, 0), (R + 6, 0), (R + 6, 10), (R - 4, 14), (0, 14)], 40), "dark_grey", name="base")
    k.round_vessel([(R, 14.0), (R - 4, H * 0.55), (R - 14, H - 12)], wall=2.5, floor=5.0, color=color, finish=fin,
                   contents=contents, n=12)
    k.shape(M.revolve([(0, H - 13), (R - 13, H - 13), (R - 16, H - 4), (16, H), (0, H)], 40), "dark_grey", name="lid")
    k.vis("ellipsoid", (12.0, 12.0, 7.0), (0, 0, H + 2.0), "black", name="lid_knob")
    k.col("cylinder", (R - 16, 10.0), (0, 0, H - 7.0), name="lid_col")
    k.foot(RB, 0.0, 12.0)
    # spout: a wedge at the front of the rim
    k.shape(M.extrude(np.array([[-16.0, 0.0], [16.0, 0.0], [0.0, -30.0]]), 0.0, 24.0).transformed(rot_x(-20), (0, -(R - 20), H - 42)),
            color, name="spout", finish=fin)
    k.col("box", (20.0, 22.0, 20.0), (0, -(R - 6), H - 30.0), name="spout_col")
    k.site("spout", (0, -(R + 8.0), H - 22.0))
    k.vessel["spout_site"] = "spout"
    hy = R + 34.0
    k.tube([(0, R - 18, H - 22), (0, hy, H - 30), (0, hy, 62), (0, R - 6, 44)], 9.0, "dark_grey", finish="matte", name="handle")
    k.col("box", (18.0, 18.0, H - 100.0), (0, hy, (H - 30 + 62) / 2.0), name="handle_col")
    k.col("box", (16.0, hy - R + 14.0, 14.0), (0, (hy + R - 14.0) / 2.0, H - 28.0))
    k.col("box", (16.0, hy - R + 4.0, 14.0), (0, (hy + R) / 2.0, 50.0))
    if switch_at == "base":
        k.button("switch", (R + 24.0, 4.0, 14.0), axis=(0, 0, 1), size=(18.0, 14.0), color="black", kind="switch", travel=3.0)
        k.lamp("lamp", (R + 24.0, -14.0, 14.5), axis=(0, 0, 1), radius=4.0, on=(0.2, 0.6, 1.0), off=(0.06, 0.10, 0.2))
    else:
        k.button("switch", (0, R + 4.0, 26.0), axis=(0, 0.6, 0.8), size=(16.0, 12.0), color="dark_grey", kind="switch", travel=3.0)
        k.lamp("lamp", (0, R + 2.0, 12.0), axis=(0, 1, 0), radius=4.0, on=(0.2, 0.6, 1.0), off=(0.06, 0.10, 0.2))
    if cord:
        k.cord((R * 0.5, R * 0.8, 6.0))
    k.site("handle", (0, hy, H * 0.5))
    k.grasp("handle", "side", (0, hy, H * 0.5), 18.0, yaw_deg=90.0)
    k.set_look("on" if state == "on" else "off")
    k.tag("electrical", "drink_vessel")
    k.mass(mass * 1000.0 + sum((contents or {}).values()))


@kind("toaster", vary={"color": ["white", "steel", "red", "black", "cream"]})
def toaster(k: Kit, *, width=0.28, depth=0.17, height=0.185, color="white", state="off", cord=True, toy=False, mass=1.4):
    """A two-slice toaster: slots `slot_0` (front) and `slot_1` open to the top, a lever on the right end, a lamp.
    Looks `on` (elements glow in the slots, lamp lit) and `off`.
    `toy=True`: a wooden play-kitchen toaster of the same shape and with the same slots: plain wood, a red knob for
    a lever, WOODEN TOY printed on its front; no elements, lamp, dial or cord, no looks and no tags."""
    W, D, H = mm(width, depth, height)
    sl, sw, sd = 136.0, 30.0, 122.0                               # slot length, width, depth
    zf = H - sd
    ys = (-(sw / 2 + 17.0), sw / 2 + 17.0)
    if toy:
        color, cord = "wood", False
    fin = "metal" if color == "steel" else "matte" if toy else "gloss"
    cells = []
    for i, yc in enumerate(ys):
        y0, y1 = (-D / 2, 0.0) if i == 0 else (0.0, D / 2)
        cells.append(M.Cell(np.array([[-W / 2, y0], [W / 2, y0], [W / 2, y1], [-W / 2, y1]]),
                            M.Pocket(M.rect(sl, sw, (0.0, yc)), floor_z=zf)))
    k.shape(M.pocket_prism(cells, 12.0, H), color, name="housing", finish=fin)
    k.shape(rbox(W - 10.0, D - 10.0, 12.0, 10.0, (0, 0, 6.0)), (0.50, 0.35, 0.22) if toy else "black", name="base", finish="matte")
    k.col("box", (W - 10.0, D - 10.0, 12.0), (0, 0, 6.0))
    k.col("box", (W, D, zf - 12.0), (0, 0, (zf + 12.0) / 2.0), name="housing_col")
    zc, hz = (zf + H) / 2.0, H - zf
    for y0, y1 in ((-D / 2, ys[0] - sw / 2), (ys[0] + sw / 2, ys[1] - sw / 2), (ys[1] + sw / 2, D / 2)):
        k.col("box", (W, y1 - y0, hz), (0, (y0 + y1) / 2.0, zc))
    for sgn in (-1.0, 1.0):
        k.col("box", ((W - sl) / 2.0, ys[1] - ys[0] + sw, hz), (sgn * (W + sl) / 4.0, 0, zc))
    for i, yc in enumerate(ys):
        k.zone(f"slot_{i}", (0, yc, zf + sd / 2.0), "box", (sl - 4.0, sw - 4.0, sd))
        k.site(f"slot_{i}_bottom", (0, yc, zf))
        for j, sgn in enumerate((-1.0, 1.0)):
            if toy:
                continue                                          # bare wood inside the slots
            k.vis("box", (sl - 12.0, 1.2, sd - 30.0), (0, yc + sgn * (sw / 2 - 1.0), zf + sd / 2.0 - 4.0), COIL_COLD,
                  name=f"element_{i}_{j}", finish="glow")
            k.look("on", f"element_{i}_{j}", GLOW_HOT)
            k.look("off", f"element_{i}_{j}", COIL_COLD)
    # lever on the right end: pushed down to start
    k.vis("box", (1.0, 10.0, 70.0), (W / 2 + 0.3, 0, H * 0.52), (0.40, 0.28, 0.17) if toy else "black", name="lever_slot")
    lever = k.part("lever", (W / 2 + 13.0, 0, H * 0.66), mass_g=8.0)
    lever.joints.append(Joint("lever_joint", "slide", axis=(0, 0, 1), range=(-30.0, 0.0), stiffness=60.0, springref=10.0,
                              damping=1.0, armature=0.0005, stiff_limit=True, role="lever"))
    k.solid("box", (24.0, 36.0, 12.0), (0, 0, 0), "red" if toy else "black", body=lever, name="lever_knob")
    k.site("lever", (0, 0, 6.0), body=lever)
    k.controls["lever"] = {"site": "lever", "kind": "switch", "joint": "lever_joint", "travel": 0.03, "force": 2.4}
    if toy:
        k.label_flat([("WOODEN", 1.0), ("TOY", 1.15)], size=(W - 110.0, H - 80.0), pos=(0, -D / 2, H * 0.50),
                     style={"base": "plain", "bg": "cream", "fg": "brown", "pad": 0.08})
        k.mass(mass * 1000.0 * 0.6)
        return
    k.lamp("lamp", (W / 2 - 30.0, -D / 2 - 0.4, 40.0), on=(1.0, 0.3, 0.1), off=(0.28, 0.07, 0.05))
    k.vis("cylinder", (11.0, 8.0), (W / 2 - 60.0, -D / 2 - 4.0, 40.0), "black", quat=qx(90), name="dial")
    if cord:
        k.cord((-W / 2 + 40.0, D / 2, 12.0))
    k.set_look("on" if state == "on" else "off")
    k.tag("electrical")
    k.mass(mass * 1000.0)


def _knife_shapes(k: Kit, blade: float, blade_h: float, handle: float, color):
    """A kitchen knife lying flat along x, tip at +x, edge towards -y. Returns the tip position."""
    L = blade + handle
    x0 = -L / 2.0
    xh = x0 + handle                                              # where the blade starts
    th, hw, zc = 2.2, 26.0, 9.0
    spine = hw / 2.0
    k.shape(rbox(handle, hw, 18.0, 8.0, (x0 + handle / 2.0, 0, zc)), color, name="handle", finish="matte")
    for x in (x0 + handle * 0.3, x0 + handle * 0.7):
        k.vis("cylinder", (3.0, 18.4), (x, 0, zc), "steel", name=None)
    tip = (L / 2.0, spine - blade_h * 0.42)
    outline = np.array([[xh, spine], [L / 2.0 - blade * 0.22, spine], [tip[0], tip[1]], [L / 2.0 - blade * 0.10, spine - blade_h * 0.80],
                        [L / 2.0 - blade * 0.34, spine - blade_h], [xh, spine - blade_h]])
    k.shape(M.extrude(outline, zc - th / 2, zc + th / 2), "steel", name="blade", finish="metal")
    k.col("box", (handle, hw - 2.0, 18.0), (x0 + handle / 2.0, 0, zc), name="handle_col")
    k.col("box", (blade * 0.70, blade_h, th), (xh + blade * 0.35, spine - blade_h / 2.0, zc), name="blade_col")
    k.col("box", (blade * 0.30, blade_h * 0.5, th), (xh + blade * 0.85, spine - blade_h * 0.42, zc), name="blade_tip_col")
    k.site("tip", (tip[0], tip[1], zc), quat=qy(90))
    k.site("handle", (x0 + handle / 2.0, 0, zc))
    return (tip[0], tip[1], zc), (x0 + handle / 2.0, 0.0, zc)


@kind("knife", vary={"blade": (0.16, 0.21), "handle_color": ["black", "brown", "red"]})
def knife(k: Kit, *, blade=0.20, blade_height=0.045, handle=0.12, handle_color="black", pose="lying", mass=0.19):
    """A kitchen knife. `pose="lying"`: flat on the table along x, tip at +x, edge towards the front. `pose="standing"`:
    tip down at the origin with the handle up, for a knife block (`at: block/slot_k_bottom`)."""
    B, BH, HL = mm(blade, blade_height, handle)
    tip, hc = _knife_shapes(k, B, BH, HL, handle_color)
    if pose == "standing":
        k.reframe(STANDING, (tip[0], 13.0 - BH / 2.0, 9.0))
        k.grasp("handle", "top", (0, hc[1] - (13.0 - BH / 2.0), tip[0] - hc[0] + 20.0), 18.0, yaw_deg=90.0)
        # once it has been put down and lies on its side: across the handle, from whichever flat side is up
        k.grasp("handle_flat", "top", (0, hc[1] - (13.0 - BH / 2.0), tip[0] - hc[0]), 24.0, quat=(0.70710678, 0.0, 0.70710678, 0.0))
    elif pose == "lying":
        k.grasp("handle", "top", (hc[0], 0, 9.0), 24.0)
    else:
        raise ValueError("pose: lying or standing")
    k.extra["blade"] = {"geoms": ["blade_col", "blade_tip_col"], "tip": "tip"}      # what goes into soft things (hazard.insert.Blade)
    k.tag("sharp", "metal", "conductive")
    k.mass(mass * 1000.0)


@kind("knife_block", vary={"color": ["wood", "black", "cream"]})
def knife_block(k: Kit, *, slots=3, height=0.215, color="wood", mass=1.6):
    """A block with slots in its top (zones `slot_k`). A `knife` with `pose="standing"` placed at the site
    `slot_k_bottom` stands with its handle out of the block, where a grasp from above takes it."""
    H = mm(height)
    n = int(slots)
    pitch = 36.0
    sx, sy = n * pitch + 20.0, 90.0
    floors = k.holed_block(sx, sy, 0.0, H, [((i - (n - 1) / 2.0) * pitch, 3.2, 27.0) for i in range(n)], floor=25.0, color=color)
    for i, f in enumerate(floors):
        k.site(f"slot_{i}_bottom", f)
        k.zone(f"slot_{i}", (f[0], f[1], (f[2] + H) / 2.0), "box", (6.4, 54.0, H - f[2]))
    k.tag("storage")
    k.mass(mass * 1000.0)


@kind("cutting_board", vary={"color": ["wood", "white", "green"], "width": (0.30, 0.38)})
def cutting_board(k: Kit, *, width=0.35, depth=0.25, thickness=0.018, color="wood", mass=0.9):
    """A cutting board. Zone `surface`: the 60 mm above it."""
    W, D, T = mm(width, depth, thickness)
    k.shape(rbox(W, D, T, 18.0, (0, 0, T / 2)), color, name="board", finish="matte")
    k.vis("cylinder", (9.0, T + 0.4), (W / 2 - 24.0, D / 2 - 24.0, T / 2), (0.25, 0.22, 0.2), name="hole")
    k.col("box", (W, D, T), (0, 0, T / 2), name="board_col")
    k.zone("surface", (0, 0, T + 30.0), "box", (W, D, 60.0))
    k.mass(mass * 1000.0)


@kind("bread_loaf", vary={"length": (0.30, 0.42)})
def bread_loaf(k: Kit, *, length=0.38, width=0.064, mass=0.25):
    """A baguette lying along x."""
    Ln, Wd = mm(length, width)
    r, h = Wd / 2.0, Ln / 2.0
    prof = [(0, -h), (0.45 * r, -h + 4), (0.75 * r, -h + 15), (0.94 * r, -h + 40), (r, 0), (0.94 * r, h - 40), (0.75 * r, h - 15),
            (0.45 * r, h - 4), (0, h)]
    m = M.revolve(prof, 28).transformed(rot_y(90))
    m.v[:, 2] = m.v[:, 2] * 0.74 + r * 0.74
    k.shape(m, (0.80, 0.56, 0.26), name="loaf", finish="matte")
    for i in range(6):                                            # the baker's cuts
        x = (i - 2.5) * Ln * 0.13
        k.vis("box", (Ln * 0.10, 5.0, 2.0), (x, 0, 2 * r * 0.74 - 1.2), (0.95, 0.84, 0.60), quat=qz(35), finish="matte")
    k.col("box", (Ln * 0.80, Wd * 0.80, 2 * r * 0.70), (0, 0, r * 0.74), name="loaf_col")
    for sgn in (-1.0, 1.0):
        k.col("box", (Ln * 0.10, Wd * 0.5, r * 0.8), (sgn * Ln * 0.44, 0, r * 0.74))
    k.grasp("middle", "top", (0, 0, r * 0.9), Wd)
    k.tag("food")
    k.mass(mass * 1000.0)


@kind("melon", vary={"radius": (0.07, 0.085)})
def melon(k: Kit, *, radius=0.078, length=0.19, color=(0.16, 0.42, 0.16), stripe=(0.07, 0.24, 0.09), mass=1.6):
    """A small watermelon, its long axis along x. Too big for the gripper: there is no grasp."""
    R, Ln = mm(radius, length)
    a = Ln / 2.0
    k.vis("ellipsoid", (a, R, R), (0, 0, R), color, name="melon", finish="gloss")
    for i in range(6):
        k.vis("ellipsoid", (a * 1.004, R * 0.10, R * 1.004), (0, 0, R), stripe, quat=qx(30.0 * i), finish="gloss")
    k.vis("cylinder", (3.5, 8.0), (-a - 2.0, 0, R), (0.35, 0.28, 0.12), quat=qy(90), name="stem")
    k.col("ellipsoid", (a, R, R), (0, 0, R + 0.4), name="melon_col")
    k.col("box", (60.0, 50.0, 5.0), (0, 0, 2.5), name="rest_col")
    k.tag("food")
    k.mass(mass * 1000.0)


@kind("apple", priority=2, vary={"color": ["red", (0.55, 0.75, 0.2), "yellow"]})
def apple(k: Kit, *, radius=0.036, color="red", mass=0.17):
    """An apple."""
    R = mm(radius)
    k.vis("ellipsoid", (R, R, R * 0.90), (0, 0, R * 0.90), color, name="apple", finish="gloss")
    k.vis("cylinder", (1.5, 14.0), (0, 1.0, R * 1.80 + 3.0), (0.35, 0.25, 0.12), name="stem")
    k.vis("ellipsoid", (9.0, 5.0, 1.2), (8.0, 2.0, R * 1.80 + 6.0), (0.2, 0.5, 0.15), name="leaf")
    k.col("sphere", (R * 0.93,), (0, 0, R * 0.93 + 0.3), name="apple_col")
    k.col("box", (26.0, 26.0, 4.0), (0, 0, 2.0), name="rest_col")
    k.grasp("body", "top", (0, 0, R * 0.95), 2 * R)
    k.tag("food")
    k.mass(mass * 1000.0)


@kind("chocolate_bar", priority=2, vary={"product": ["MILK CHOCOLATE", "DARK CHOCOLATE", "RAISIN BAR", "CEREAL BAR"],
                                         "color": ["brown", "purple", "red", "blue"]})
def chocolate_bar(k: Kit, *, length=0.15, width=0.07, thickness=0.011, product="MILK CHOCOLATE", color="brown",
                  weight="100 g", mass=0.105):
    """A wrapped bar of chocolate lying flat, the name printed on top."""
    Ln, Wd, T = mm(length, width, thickness)
    k.shape(rbox(Ln, Wd, T, 4.0, (0, 0, T / 2)), color, name="wrapper", finish="gloss")
    for sgn in (-1.0, 1.0):
        k.vis("box", (8.0, Wd, 1.0), (sgn * (Ln / 2 + 3.0), 0, T / 2), color, name=None)
    k.col("box", (Ln, Wd, T), (0, 0, T / 2), name="bar_col")
    words = product.split()
    lines = [(product, 1.0)] if len(words) == 1 else [(" ".join(words[:-1]), 1.0), (words[-1], 1.0)]
    k.label_flat(lines + [{"text": weight, "h": 0.5, "fine": True}], size=(Ln - 30.0, Wd - 14.0), pos=(0, 0, T), normal=(0, 0, 1),
                 style={"base": "product", "header": ("cream", color), "bg": "cream", "fg": color})
    k.grasp("body", "top", (0, 0, T * 0.6), Wd)
    k.tag("food")
    k.mass(mass * 1000.0)


BISCUIT_PAW = ((0.0, -5.5, 10.5, 8.5, 0.0), (-13.5, 4.0, 4.4, 5.8, 28.0), (-5.0, 11.5, 4.4, 6.0, 9.0), (5.0, 11.5, 4.4, 6.0, -9.0),
               (13.5, 4.0, 4.4, 5.8, -28.0))                      # a paw print for a biscuit 64 mm across: x, y, half axes, turn


def _paw(k: Kit, scale: float, color, *, at=(0.0, 0.0, 0.0), rot=None, thick: float = 0.5, name: str | None = None) -> None:
    """A paw print (one large pad, four toes above it) drawn flat at `at`: in the plane z = at[2] with the toes
    towards +y, or in the plane that the rotation `rot` turns that one into."""
    r = np.eye(3) if rot is None else np.asarray(rot, dtype=np.float64)
    pads = [M.extrude(_ellipse(a * scale, b * scale, turn) + np.array([x * scale, y * scale]), 0.0, thick) for x, y, a, b, turn in BISCUIT_PAW]
    k.shape(M.merge(pads).transformed(r), color, pos=tuple(float(v) for v in at), name=name, finish="matte")


def _ellipse(a: float, b: float, turn_deg: float = 0.0, n: int = 20) -> np.ndarray:
    t = np.linspace(0.0, 2.0 * math.pi, n, endpoint=False)
    c, s = math.cos(math.radians(turn_deg)), math.sin(math.radians(turn_deg))
    x, y = a * np.cos(t), b * np.sin(t)
    return np.stack([c * x - s * y, s * x + c * y], axis=1)


def _biscuit(k: Kit, R: float, T: float, color, *, at=(0.0, 0.0, 0.0), name: str | None = None) -> None:
    """The drawn part of a round dog biscuit lying flat with its underside at `at`: the disc and its paw print."""
    dark = tuple(0.62 * float(c) for c in color)
    disc = M.revolve([(0, 0), (R - 2.0, 0), (R, 2.0), (R, T - 2.0), (R - 2.0, T), (0, T)], 32)
    k.shape(disc, color, name=name, pos=at, finish="matte")
    _paw(k, R / 32.0, dark, at=(at[0], at[1], at[2] + T - 0.1), name=None if name is None else f"{name}_paw")


@kind("dog_biscuit", priority=2, vary={"color": [(0.74, 0.55, 0.32), (0.66, 0.46, 0.26), (0.80, 0.62, 0.40)]})
def dog_biscuit(k: Kit, *, diameter=0.064, thickness=0.013, color=(0.74, 0.55, 0.32), mass=0.025):
    """A dog biscuit as it comes out of its box: a flat round disc, baked brown, with a paw print pressed into its
    top (the toes towards +y). Loose, without a wrapper; nothing is printed on it. (Up to 0.4.0 the kind had the
    shape of a bone.)"""
    D, T = mm(diameter, thickness)
    R = D / 2.0
    _biscuit(k, R, T, tuple(color), name="biscuit")
    k.col("cylinder", (R, T), (0, 0, T / 2), name="biscuit_col")
    k.grasp("body", "top", (0, 0, T * 0.6), D)
    k.tag("food")
    k.mass(mass * 1000.0)


@kind("dog_biscuit_box", priority=2, vary={"color": ["orange", "teal", "yellow"]})
def dog_biscuit_box(k: Kit, *, width=0.14, depth=0.075, height=0.12, color="orange", text=("DOG", "BISCUITS"),
                    biscuit=(0.74, 0.55, 0.32), mass=0.35):
    """An opened carton of dog biscuits standing upright: the name on its front in two lines, a biscuit with its paw
    print drawn under the name, the lid folded right back so that its inside, printed with the name again, faces up
    behind the box, and two biscuits lying in the open top. The biscuits in it are a picture: nothing can be taken
    out or put in."""
    W, D, H = mm(width, depth, height)
    wall = 2.0
    k.box_vessel(W, D, H, wall=wall, floor=3.0, color=color, finish="matte", corner=1.5, liquid=False, register=False, name="carton")
    # what is in it: a cardboard-coloured filling up to 18 mm under the rim, and two biscuits on it
    fill = H - 18.0
    k.solid("box", (W - 2 * wall - 0.6, D - 2 * wall - 0.6, fill - 3.0), (0, 0, 3.0 + (fill - 3.0) / 2.0), (0.62, 0.48, 0.30), name="filling", finish="matte")
    r = min((W - 2 * wall) / 4.0 - 1.0, (D - 2 * wall) / 2.0 - 1.0)
    for i, sx in enumerate((-1.0, 1.0)):
        _biscuit(k, r, 11.0, tuple(biscuit), at=(sx * (r + 1.0), 0.0, fill), name=f"inside_{i}")
    # the lid, folded right back: it lies level behind the box at the height of the rim, its printed inside up
    lid = D - 4.0
    k.solid("box", (W, lid, 1.6), (0, D / 2.0 + lid / 2.0, H - 0.8), color, name="lid", finish="matte")
    lines = [(str(t), 1.0) for t in text]
    style = {"base": "product", "header": ("navy", "white"), "bg": "cream", "fg": "navy"}
    k.label_flat(lines, size=(W - 8.0, H * 0.56), pos=(0, -D / 2, H * 0.68), style=style, name="label")
    k.label_flat(lines, size=(W - 8.0, lid - 8.0), pos=(0, D / 2.0 + lid / 2.0, H), normal=(0, 0, 1), style=style, name="label_lid")
    # the picture on the front, under the name: one biscuit seen from above
    rp = H * 0.15
    rot = rot_x(90.0)
    k.shape(M.cylinder(rp, 0.0, 0.6, 32).transformed(rot), tuple(biscuit), pos=(0, -D / 2, H * 0.20), name="picture", finish="matte")
    _paw(k, rp / 32.0, tuple(0.62 * float(c) for c in biscuit), at=(0, -D / 2 - 0.6, H * 0.20), rot=rot, name="picture_paw")
    k.tag("paper", "storage")
    k.mass(mass * 1000.0)


@kind("spoon", priority=2, vary={"material": ["metal", "wood"]})
def spoon(k: Kit, *, length=0.17, material="metal", pose="lying", mass=None):
    """A tablespoon (steel) or a wooden spoon, lying along x with the bowl at +x; `pose="standing"`: bowl down."""
    Ln = mm(length) if material == "metal" else mm(length) * 1.6
    color, fin = ("steel", "metal") if material == "metal" else ("wood", "matte")
    bl, bw = (48.0, 32.0) if material == "metal" else (62.0, 44.0)
    hl = Ln - bl
    hw, ht = (9.0, 2.6) if material == "metal" else (13.0, 9.0)
    x0 = -Ln / 2.0
    zc = max(ht / 2.0, 3.0)
    k.shape(rbox(hl + 6.0, hw, ht, hw / 2.2, (x0 + (hl + 6.0) / 2.0, 0, zc)), color, name="handle", finish=fin)
    k.vis("ellipsoid", (bl / 2.0, bw / 2.0, 3.2), (Ln / 2.0 - bl / 2.0, 0, 3.2), color, name="bowl", finish=fin)
    k.col("box", (hl, hw, max(ht, 2.6)), (x0 + hl / 2.0, 0, zc), name="handle_col")
    k.col("box", (bl, bw * 0.7, 6.0), (Ln / 2.0 - bl / 2.0, 0, 3.0), name="bowl_col")
    k.site("handle", (x0 + hl * 0.4, 0, zc))
    k.site("tip", (Ln / 2.0, 0, 3.0), quat=qy(90))
    if pose == "standing":
        k.reframe(STANDING, (Ln / 2.0, 0.0, 3.0))
        k.grasp("handle", "top", (0, 0, Ln - 25.0), hw, yaw_deg=0.0)
    else:
        k.grasp("handle", "top", (x0 + hl * 0.4, 0, zc), hw)
    if material == "metal":
        k.tag("metal", "conductive")
    k.mass(mass * 1000.0 if mass else (45.0 if material == "metal" else 40.0))


@kind("microwave", priority=2, fixed=True, vary={"color": ["white", "steel", "black"]})
def microwave(k: Kit, *, width=0.46, depth=0.35, height=0.27, color="white", state="idle", mass=11.5):
    """A microwave oven: zone `cavity` behind a door hinged on the left (joint `door`, driven by the actuator of the
    same name), buttons `open` (blue, printed DOOR: it opens and closes the door) and `start` (green, printed START)
    on the panel to the right, a display with the looks `running` and `idle`."""
    W, D, H = mm(width, depth, height)
    t = 14.0
    panel_w = 105.0
    cav_w, cav_d, cav_h = W - panel_w - 2 * t, D - t - 24.0, H - 2 * t - 16.0
    cx = -W / 2 + t + cav_w / 2.0
    cz0 = t + 8.0
    fin = "metal" if color == "steel" else "satin"
    # housing: bottom, top, left, back, and the control block on the right
    for name, size, pos in (("floor", (W, D, cz0), (0, 0, cz0 / 2)),
                            ("roof", (W, D, H - cz0 - cav_h), (0, 0, (H + cz0 + cav_h) / 2)),
                            ("left", (t, D, cav_h), (-W / 2 + t / 2, 0, cz0 + cav_h / 2)),
                            ("back", (cav_w, D - 24.0 - cav_d, cav_h), (cx, D / 2 - (D - 24.0 - cav_d) / 2, cz0 + cav_h / 2)),
                            ("panel", (panel_w + t, D, cav_h), (W / 2 - (panel_w + t) / 2, 0, cz0 + cav_h / 2))):
        k.solid("box", size, pos, color, name=name, finish=fin)
    k.vis("box", (cav_w, cav_d, 0.6), (cx, -D / 2 + 24.0 + cav_d / 2, cz0 + 0.3), (0.82, 0.82, 0.80), name="cavity_floor")
    k.vis("cylinder", (min(cav_w, cav_d) * 0.42, 5.0), (cx, -D / 2 + 24.0 + cav_d / 2, cz0 + 3.0), "glass_frosted", name="turntable")
    k.col("box", (min(cav_w, cav_d) * 0.6, min(cav_w, cav_d) * 0.6, 5.0), (cx, -D / 2 + 24.0 + cav_d / 2, cz0 + 2.5))
    k.site("turntable", (cx, -D / 2 + 24.0 + cav_d / 2, cz0 + 5.5))
    k.zone("cavity", (cx, -D / 2 + 24.0 + cav_d / 2, cz0 + 5.5 + (cav_h - 5.5) / 2), "box", (cav_w, cav_d, cav_h - 5.5))
    k.vis("box", (cav_w * 0.5, cav_d * 0.5, 1.0), (cx, -D / 2 + 24.0 + cav_d / 2, cz0 + cav_h - 0.6), (0.2, 0.2, 0.2), name="cavity_light",
          finish="glow")
    # door
    door_w = W - panel_w - 4.0
    door = k.part("door_leaf", (-W / 2 + 2.0, -D / 2, 0.0), mass_g=1400.0)
    door.joints.append(Joint("door", "hinge", axis=(0, 0, -1), range=(0.0, 1.9), damping=0.15, frictionloss=0.05, armature=0.002,
                             role="door"))
    k.solid("box", (door_w, 20.0, H - 8.0), (door_w / 2, -10.0 + 22.0, H / 2), color, body=door, name="door_frame", finish=fin)
    k.vis("box", (door_w - 60.0, 1.0, H - 80.0), (door_w / 2, 11.5, H / 2), (0.05, 0.06, 0.07), body=door, name="door_window",
          finish="gloss")
    k.vis("box", (12.0, 14.0, H - 90.0), (door_w - 18.0, 6.0, H / 2), "housing_dark", body=door, name="door_handle")
    k.site("door_handle", (door_w - 18.0, 0.0, H / 2), body=door)
    k.door("door", "door", open=1.6, closed=0.0, kp=3.0, kv=0.5, force=4.0)
    # panel: display, start and open buttons with printed names
    px = W / 2 - panel_w / 2 - 2.0
    from .. import labels as L
    for look, text in (("idle", "12:00"), ("running", "1:30")):
        img = L.label_image([text], (), (240, 96), "screen")
        k.decal(img, size=(72.0, 28.0), pos=(px, -D / 2, H - 45.0), name=f"display_{look}", glow=0.9, thick=0.5 if look == "idle" else 0.7)
    k.look("idle", "display_idle", (1, 1, 1, 1))
    k.look("idle", "display_running", (1, 1, 1, 0))
    k.look("running", "display_idle", (1, 1, 1, 0))
    k.look("running", "display_running", (1, 1, 1, 1))
    k.look("idle", "cavity_light", (0.2, 0.2, 0.2, 1))
    k.look("running", "cavity_light", (1.0, 0.92, 0.6, 1))
    # The door button: blue, where up to 0.3.0 it was light grey on a light grey panel under the print OPEN. An agent
    # that had to close the door did not find it ("the only control found was START"): it did not stand out, and a
    # button called OPEN is not where one looks to shut a door. It works the door both ways, and its print says DOOR.
    # The control keeps its name, `open`. On a black housing the buttons get a light surround.
    for z in ((H * 0.50, H * 0.22) if color == "black" else ()):
        k.vis("box", (68.0, 1.0, 34.0), (px, -D / 2 - 0.3, z), "light_grey", name=None, finish="matte")
    k.button("start", (px, -D / 2, H * 0.50), size=(60.0, 26.0), color="green")
    k.button("open", (px, -D / 2, H * 0.22), size=(60.0, 26.0), color="blue")
    sticker = {"base": "paper", "bg": "white", "pad": 0.04}     # white stickers: on a black housing the print was black on black
    k.label_flat(["START"], size=(60.0, 14.0), pos=(px, -D / 2, H * 0.50 + 24.0), style=sticker, name="start_label")
    k.label_flat(["DOOR"], size=(60.0, 14.0), pos=(px, -D / 2, H * 0.22 + 24.0), style=sticker, name="open_label")
    k.set_look("running" if state == "running" else "idle")
    k.tag("electrical")
    k.mass(mass * 1000.0)
