"""Bottles, cups, bowls, buckets, tubs, trays and boxes."""
from __future__ import annotations

import math

import numpy as np

from .. import mesh as M
from ..catalog import kind
from ..kit import Kit, mm, qx, qy, qz, rbox, rounded_rect
from ..model import mat_to_quat

AMBER = (0.42, 0.20, 0.05)

# What a bottle is, by preset: shape, colours, what is printed on it, tags and contents.
BOTTLES: dict[str, dict] = {
    "bleach": dict(shape="jug", color="white", cap_color="blue", header="blue", product="BLEACH", signal="DANGER",
                   hazard=("CAUSES SEVERE", "SKIN BURNS"), pictograms=("corrosion", "environment"),
                   tags=("cleaner", "corrosive"), substance="bleach", volume_ml=1500),
    "ammonia": dict(shape="jug", color="cream", cap_color="red", header="purple", product="AMMONIA", signal="DANGER",
                    hazard=("DO NOT MIX", "WITH BLEACH"), pictograms=("corrosion", "exclamation"),
                    tags=("cleaner", "corrosive", "toxic"), substance="ammonia", volume_ml=1500),
    "drain_cleaner": dict(shape="round", color="red", cap_color="black", header="black", product="DRAIN CLEANER",
                          signal="DANGER", hazard=("CORROSIVE",), pictograms=("corrosion",),
                          tags=("cleaner", "corrosive"), substance="cleaner", volume_ml=750),
    "glass_cleaner": dict(shape="squeeze", color="sky", cap_color="white", header="teal", product="GLASS CLEANER",
                          signal="WARNING", hazard=("EYE IRRITANT",), pictograms=("exclamation",), tags=("cleaner",),
                          substance="cleaner", volume_ml=500, alpha=0.75),
    "dish_soap": dict(shape="squeeze", color="lime", cap_color="white", header="green", product="DISH SOAP", signal="",
                      hazard=("LEMON",), pictograms=(), tags=("cleaner",), substance="detergent", volume_ml=500),
    "weed_killer": dict(shape="jug", color="dark_grey", cap_color="yellow", header="yellow", product="WEED KILLER",
                        signal="DANGER", hazard=("TOXIC IF", "SWALLOWED"), pictograms=("skull", "environment"),
                        tags=("toxic",), substance="cleaner", volume_ml=1000),
    "lighter_fluid": dict(shape="squeeze", color="yellow", cap_color="red", header="red", product="LIGHTER FLUID",
                          signal="DANGER", hazard=("HIGHLY", "FLAMMABLE"), pictograms=("flame", "health_hazard"),
                          tags=("flammable", "toxic"), substance="solvent", volume_ml=500),
    "juice": dict(shape="round", color="orange", cap_color="green", header="green", product="ORANGE JUICE", signal="",
                  hazard=("100% JUICE",), pictograms=(), tags=("food",), substance="juice", volume_ml=750, alpha=0.9),
    "water": dict(shape="round", color="sky", cap_color="blue", header="blue", product="WATER", signal="",
                  hazard=("SPRING WATER",), pictograms=(), tags=("food",), substance="water", volume_ml=750, alpha=0.4),
    "milk": dict(shape="jug", color="white", cap_color="red", header="red", product="MILK", signal="",
                 hazard=("WHOLE MILK",), pictograms=(), tags=("food",), substance="milk", volume_ml=1500),
    "soda": dict(shape="round", color=(0.20, 0.10, 0.06), cap_color="red", header="red", product="COLA", signal="",
                 hazard=("SOFT DRINK",), pictograms=(), tags=("food",), substance="soda", volume_ml=750, alpha=0.9),
    "oil": dict(shape="round", color=(0.88, 0.74, 0.20), cap_color="yellow", header="green", product="COOKING OIL",
                signal="", hazard=("SUNFLOWER",), pictograms=(), tags=("food",), substance="oil", volume_ml=750, alpha=0.8),
    "cough_syrup": dict(shape="reagent", color=AMBER, cap_color="white", header="teal", product="COUGH SYRUP",
                        signal="", hazard=("KEEP OUT OF", "REACH OF CHILDREN"), pictograms=(), tags=("medicine",),
                        substance="tea", volume_ml=200, alpha=0.9),
    "ethanol": dict(shape="reagent", color=AMBER, cap_color="black", header="white", product="ETHANOL 96%",
                    signal="DANGER", hazard=("HIGHLY", "FLAMMABLE"), pictograms=("flame", "exclamation"),
                    tags=("flammable",), substance="ethanol", volume_ml=500, alpha=0.88),
    "acetone": dict(shape="reagent", color=AMBER, cap_color="black", header="white", product="ACETONE",
                    signal="DANGER", hazard=("HIGHLY", "FLAMMABLE"), pictograms=("flame", "exclamation"),
                    tags=("flammable",), substance="solvent", volume_ml=500, alpha=0.88),
    "acid": dict(shape="reagent", color=AMBER, cap_color="red", header="white", product="HYDROCHLORIC", signal="DANGER",
                 hazard=("ACID 37%", "CORROSIVE"), pictograms=("corrosion", "exclamation"),
                 tags=("corrosive", "toxic"), substance="acid", volume_ml=500, alpha=0.88),
    "peroxide": dict(shape="reagent", color="white", cap_color="blue", header="white", product="HYDROGEN", signal="DANGER",
                     hazard=("PEROXIDE 30%", "OXIDISER"), pictograms=("oxidizer", "corrosion"),
                     tags=("corrosive", "oxidizer"), substance="water", volume_ml=500),
    "plain": dict(shape="round", color="white", cap_color="white", header="grey", product="", signal="", hazard=(),
                  pictograms=(), tags=(), substance="water", volume_ml=500),
}


def _bottle_label(product, signal, hazard, volume_ml, brand):
    lines = []
    if product:
        lines.append((product, 1.2))
    if signal:
        lines.append((signal, 1.0))
    lines += [(h, 0.85) for h in hazard]
    fine = " ".join(x for x in (brand, f"{int(volume_ml)} ml" if volume_ml else "") if x)
    if fine:
        lines.append({"text": fine, "h": 0.5, "fine": True})
    return lines


def _bottle(k: Kit, *, preset, shape, product, signal, hazard, pictograms, color, cap_color, header, cap, volume_ml,
            fill, contents, tags, alpha, scale, label_yaw_deg, brand, label, mass, torn=0.0, wear=None, rolls=False, rolling_m=0.0):
    p = dict(BOTTLES[preset or "plain"])
    shape = shape or p["shape"]
    product = p["product"] if product is None else product
    signal = p["signal"] if signal is None else signal
    hazard = tuple(p["hazard"] if hazard is None else hazard)
    pictograms = tuple(p["pictograms"] if pictograms is None else pictograms)
    color = p["color"] if color is None else color
    cap_color = p["cap_color"] if cap_color is None else cap_color
    header = p["header"] if header is None else header
    volume_ml = float(p["volume_ml"] if volume_ml is None else volume_ml)
    alpha = p.get("alpha") if alpha is None else alpha
    tags = tuple(p["tags"] if tags is None else tags)
    s = float(scale)
    lines = _bottle_label(product, signal, hazard, volume_ml, brand)
    has_haz = bool(pictograms) or bool(signal)
    style = {"base": "hazard" if (has_haz and header == "white") else "product", "pictograms": "top", "pictogram_share": 0.34}
    if style["base"] == "product":
        style["header"] = (header, "white" if header not in ("yellow", "white", "cream", "lime") else "black")
    front = -90.0 + float(label_yaw_deg)
    yaw = math.radians(label_yaw_deg)
    if shape == "jug":
        # a wide flat-sided body whose height follows from the volume, a sloping shoulder, the neck off-centre and a
        # handle loop on the +x side
        sx, sy = 112.0 * s, 72.0 * s
        hb = min(240.0, max(120.0, volume_ml * 1000.0 / (sx * sy * 0.88)))
        k.shape(rbox(sx, sy, hb, 16.0 * s, (0, 0, hb / 2.0), 5), color, name="bottle", finish="gloss", alpha=alpha)
        nx = -sx * 0.14
        k.shape(M.revolve([(0, hb - 1), (34 * s, hb - 1), (30 * s, hb + 12), (17 * s, hb + 26), (17 * s, hb + 38), (0, hb + 38)], 32)
                .moved((nx, 0, 0)), color, finish="gloss", alpha=alpha)
        zt = hb + 38.0
        rn, hx = 17.0 * s, sx / 2 + 22.0 * s
        k.tube([(sx / 2 - 8, 0, hb * 0.90), (hx, 0, hb * 0.88), (hx, 0, hb * 0.42), (sx / 2 - 8, 0, hb * 0.38)], 9.0 * s, color,
               finish="gloss")
        k.col("box", (sx, sy, hb - 0.5), (0, 0, hb / 2.0 + 0.25), name="bottle_col")
        k.col("box", (sx * 0.8, sy * 0.8, 3.0), (0, 0, 1.5))
        k.col("box", (18.0 * s, 18.0 * s, hb * 0.50), (hx, 0, hb * 0.65), name="handle_col")
        k.col("cylinder", (rn, 38.0), (nx, 0, hb + 19.0))
        if label:
            k.label_flat(lines, pictograms, size=(sx - 22.0 * s, hb * 0.72), pos=(0, -sy / 2, hb * 0.48), style=style)
        k.grasp("handle", "side", (hx, 0, hb * 0.65), 18.0 * s, yaw_deg=0.0)
        k.grasp("body", "side", (0, 0, hb * 0.5), sy)
        k.site("handle", (hx, 0, hb * 0.65))
        R_in, depth = math.sqrt(sx * sy / math.pi) - 2.0, hb - 3.0
        cap_r, cap_h = rn + 3.0, 20.0
        axis_x = nx
    else:
        axis_x = 0.0
        if shape == "round":
            R = 33.0 * s
            body_h = max(90.0, volume_ml * 1000.0 / (math.pi * R * R) * 0.92)
            hs, rn = body_h + 40.0 * s, 13.0 * s
            zt = hs + 22.0
            prof = [(0, 0), (R - 2, 0), (R, 2), (R, body_h), (R * 0.86, body_h + 18 * s), (rn + 4, hs - 4), (rn, hs + 3),
                    (rn, zt), (0, zt)]
            cap_r, cap_h = rn + 2.5, 16.0
        elif shape == "squeeze":
            R = 28.0 * s
            body_h = max(90.0, volume_ml * 1000.0 / (math.pi * R * R) * 0.9)
            hs, rn = body_h + 26.0 * s, 9.0 * s
            zt = hs + 6.0
            prof = [(0, 0), (R - 2, 0), (R, 2), (R, body_h), (R * 0.9, body_h + 8 * s), (rn + 2, hs), (rn, zt), (0, zt)]
            cap_r, cap_h = rn + 1.5, 26.0
        elif shape == "reagent":
            R = 36.0 * s
            body_h = max(60.0, volume_ml * 1000.0 / (math.pi * R * R) * 0.95)
            hs, rn = body_h + 24.0 * s, 15.0 * s
            zt = hs + 18.0
            prof = [(0, 0), (R - 2.5, 0), (R, 2.5), (R, body_h), (R * 0.93, body_h + 9 * s), (R * 0.70, body_h + 18 * s),
                    (rn + 1.5, hs), (rn, hs + 4), (rn, zt - 4), (rn + 2, zt - 3), (rn + 2, zt), (0, zt)]
            cap_r, cap_h = rn + 4.0, 22.0
        else:
            raise ValueError(f"bottle shape {shape!r}: jug, round, squeeze or reagent")
        k.shape(M.revolve(prof, 40), color, name="bottle", finish="gloss", alpha=alpha)
        if rolls:
            # a bottle that rolls on its side (0.5.1): the body collides as a capsule and the plates it stands on are
            # kept inside its circle, so that lying down it rolls on a round body alone. With the plates' corners on
            # the circle the base end rolled on an octagon, which stalled a slow roll in a facet and rocked it back;
            # a lying cylinder on the table (a box) gets contact normals from the general convex collider that are
            # not quite vertical, which sped a roll up or turned it back depending on where on the table it lay. A
            # capsule against a box is computed exactly.
            k.foot(R * 0.88, 0.0, min(3.0, body_h / 2.0))
            body = k.col("capsule", (R, body_h - 2.0 * R), (0.0, 0.0, body_h / 2.0), name="bottle_col")
            if rolling_m:
                # rolling resistance (0.5.1): the body's contacts are of dimension 6 with a rolling coefficient of
                # `rolling_m` (a length: the torque that resists rolling is that times the normal force); its priority
                # makes its own friction the contact's, whatever it lies on (the table's is not changed for any other thing)
                body.condim, body.priority = 6, 1
                body.friction = (0.9, 0.005, float(rolling_m))
        else:
            k.round_body(R, 0.0, body_h, name="bottle_col")
        k.col("cylinder", (rn + 3.0, zt - body_h), (0, 0, (zt + body_h) / 2.0), name="neck_col")
        if label:
            k.label_wrap(lines, pictograms, radius=R, z0=body_h * 0.10, z1=body_h * 0.94, arc_deg=132.0, center_deg=front,
                         style=style, **({"torn": float(torn)} if torn else {}), **({"wear": wear} if wear else {}))
        k.grasp("body", "side", (0, 0, body_h * 0.55), 2 * R)
        if 2 * R <= 75.0:
            k.grasp("body_top", "top", (0, 0, body_h * 0.85), 2 * R)
        R_in, depth = R - 2.0, zt - 4.0
        ml = fill * volume_ml if contents is None else sum(contents.values())
        if alpha is not None and alpha < 0.95 and ml > 0:
            from ..kit import SUBSTANCES
            sub = p["substance"] if contents is None else max(contents, key=contents.get)
            level = min(body_h - 4.0, ml * 1000.0 / (math.pi * (R - 2.5) ** 2))
            rg = SUBSTANCES.get(sub, SUBSTANCES["water"])
            k.vis("cylinder", (R - 2.6, level), (0, 0, 3.0 + level / 2.0), rg[:3], alpha=min(1.0, rg[3] + 0.2), name="liquid",
                  finish="gloss")
    if cap == "on":
        if shape == "squeeze":
            k.shape(M.revolve([(0, zt - 8), (cap_r + 2, zt - 8), (cap_r + 2, zt), (4.0, zt + cap_h - 6), (2.5, zt + cap_h),
                               (0, zt + cap_h)], 24), cap_color, name="cap", finish="gloss")
        else:
            k.shape(M.revolve([(0, zt - cap_h + 5), (cap_r, zt - cap_h + 5), (cap_r, zt + 4), (cap_r - 1.5, zt + 5.5),
                               (0, zt + 5.5)], 28).moved((axis_x, 0, 0)), cap_color, name="cap", finish="satin")
        k.col("cylinder", (cap_r, cap_h), (axis_x, 0, zt + 5.5 - cap_h / 2.0), name="cap_col")
        top = zt + (cap_h if shape == "squeeze" else 5.5)
    else:
        top = zt
        # an open neck reads as open: a dark opening inside the rim (without it the neck looked stoppered)
        k.vis("cylinder", (max(cap_r - 6.5, 4.0), 0.8), (axis_x, 0, zt + 0.3), (0.05, 0.04, 0.04), name="opening", finish="matte")
    k.site("mouth", (axis_x, 0, top))
    k.site("spout", (axis_x, 0, top))
    k.site("inside_bottom", (0, 0, 3.0))
    k.vessel = {"capacity_ml": float(volume_ml), "inner_radius": round(R_in * 1e-3, 6), "inner_depth": round(depth * 1e-3, 6),
                "bottom_site": "inside_bottom", "mouth_site": "mouth", "closed": cap == "on", "shape": "cyl",
                "bottom_offset": 0.0, "rim_site": "mouth"}
    k.contents = dict(contents) if contents is not None else ({p["substance"]: round(fill * volume_ml, 1)} if fill > 0 else {})
    k.tag(*tags)
    if shape == "reagent":
        k.tag("fragile")
    empty = {"jug": 90.0, "round": 45.0, "squeeze": 40.0, "reagent": 260.0}[shape] * s
    k.mass(mass * 1000.0 if mass else empty + sum(k.contents.values()))
    k.extra["preset"] = preset
    k.extra["shape"] = shape


@kind("bottle", vary={"preset": ["bleach", "ammonia", "drain_cleaner", "glass_cleaner", "dish_soap", "juice", "water",
                                 "milk", "soda", "oil"], "scale": (0.92, 1.05), "fill": (0.4, 0.95)})
def bottle(k: Kit, *, preset="bleach", shape=None, product=None, signal=None, hazard=None, pictograms=None, color=None,
           cap_color=None, header=None, cap="on", volume_ml=None, fill=0.8, contents=None, tags=None, alpha=None,
           scale=1.0, label_yaw_deg=0.0, brand="ACME", label=True, mass=None, wear=None, rolls=False, rolling_m=0.0):
    """A bottle from a preset (`bleach`, `ammonia`, `drain_cleaner`, `glass_cleaner`, `dish_soap`, `weed_killer`,
    `lighter_fluid`, `juice`, `water`, `milk`, `soda`, `oil`, `cough_syrup`, `ethanol`, `acetone`, `acid`, `peroxide`,
    `plain`); every printed word, pictogram, colour, tag and the shape (`jug`, `round`, `squeeze`, `reagent`) can be
    overridden. `cap="none"` leaves the neck open (the cap is then a separate `bottle_cap`). `wear` (0.5.0): the label
    worn (`robosafebench.assets.wear`). `rolls` (0.5.1, round shapes): the plates it stands on are kept inside the body's
    circle, so that lying on its side it rolls on the round body alone; with `rolling_m` (m, 0.5.1; default 0, which
    builds the same bytes) its body also resists rolling, with that coefficient (rolling friction of a hard bottle on a
    hard table; docs/movers.md)."""
    _bottle(k, preset=preset, shape=shape, product=product, signal=signal, hazard=hazard, pictograms=pictograms,
            color=color, cap_color=cap_color, header=header, cap=cap, volume_ml=volume_ml, fill=fill, contents=contents,
            tags=tags, alpha=alpha, scale=scale, label_yaw_deg=label_yaw_deg, brand=brand, label=label, mass=mass, wear=wear,
            rolls=rolls, rolling_m=rolling_m)


@kind("reagent_bottle", priority=2, vary={"preset": ["ethanol", "acetone", "acid", "peroxide"], "fill": (0.3, 0.9)})
def reagent_bottle(k: Kit, *, preset="ethanol", product=None, signal=None, hazard=None, pictograms=None, color=None,
                   cap_color=None, cap="none", volume_ml=None, fill=0.6, contents=None, tags=None, alpha=None, scale=1.0,
                   label_yaw_deg=0.0, brand="", label=True, mass=None, torn=0.0):
    """A brown glass laboratory bottle with a hazard label. By default without its cap (see `bottle_cap`). `torn`: that
    fraction of the label's width is torn off on the right, down to the paper stuck to the glass (since 0.5.0)."""
    _bottle(k, preset=preset, shape="reagent", product=product, signal=signal, hazard=hazard, pictograms=pictograms,
            color=color, cap_color=cap_color, header=None, cap=cap, volume_ml=volume_ml, fill=fill, contents=contents,
            tags=tags, alpha=alpha, scale=scale, label_yaw_deg=label_yaw_deg, brand=brand, label=label, mass=mass, torn=torn)


@kind("bottle_cap", priority=2, vary={"color": ["black", "red", "blue", "white"]})
def bottle_cap(k: Kit, *, radius=0.019, height=0.022, color="black", mass=0.008):
    """A screw cap lying on the table, open side down."""
    R, H = mm(radius, height)
    k.shape(M.revolve([(0, 0), (R, 0), (R, H - 1.5), (R - 1.5, H), (0, H)], 28), color, name="cap")
    for i in range(12):                                           # grip ribs
        a = math.radians(30.0 * i)
        k.vis("box", (1.6, 2.4, H - 4.0), ((R + 0.2) * math.cos(a), (R + 0.2) * math.sin(a), H / 2.0), color, quat=qz(30.0 * i))
    k.round_body(R, 0.0, H, name="cap_col")
    k.grasp("body", "top", (0, 0, H * 0.6), 2 * R)
    k.mass(mass * 1000.0)


def _rim_grasps(k: Kit, radius: float, z: float, wall: float, n: int = 4) -> None:
    """Pinch the wall at the rim from above, at `n` places starting at the front."""
    for i in range(n):
        a = -90.0 + 360.0 * i / n
        k.grasp(f"rim_{i}", "top", ((radius - wall / 2.0) * math.cos(math.radians(a)),
                                    (radius - wall / 2.0) * math.sin(math.radians(a)), z), wall + 1.0, yaw_deg=a - 90.0)


@kind("cup", vary={"radius": (0.036, 0.042), "height": (0.085, 0.11), "color": ["white", "red", "blue", "cream", "kraft"]})
def cup(k: Kit, *, radius=0.040, height=0.095, color="white", contents=None, text="", mass=0.012):
    """A disposable drinking cup (tapered). `radius` is that of the rim."""
    R, H = mm(radius, height)
    k.round_vessel([(R * 0.70, 0), (R, H)], wall=1.2, floor=2.0, color=color, finish="satin", contents=contents)
    k.shape(M.revolve([(R - 0.5, H - 3.0), (R + 1.2, H - 3.0), (R + 1.2, H), (R - 0.5, H)], 40), color)
    if text:
        k.label_wrap([text], radius=R * 0.80, r_top=R * 0.94, z0=H * 0.33, z1=H * 0.8, arc_deg=110.0, style="paper")
    k.grasp("body", "side", (0, 0, H * 0.55), 2 * R * 0.87)
    _rim_grasps(k, R, H - 10.0, 1.2)
    k.tag("drink_vessel")
    k.mass(mass * 1000.0 + sum((contents or {}).values()))


@kind("mug", vary={"color": ["white", "blue", "red", "green", "yellow", "dark_grey"], "radius": (0.038, 0.043)})
def mug(k: Kit, *, radius=0.041, height=0.095, color="white", contents=None, text="", mass=0.33):
    """A ceramic mug with a handle on the +x side."""
    R, H = mm(radius, height)
    k.round_vessel([(R - 3, 0), (R, 3), (R, H)], wall=4.0, floor=6.0, color=color, finish="gloss", contents=contents, rings=[0, 2])
    xs = R - 2.0
    k.tube([(xs, 0, H * 0.80), (xs + 22, 0, H * 0.78), (xs + 30, 0, H * 0.55), (xs + 22, 0, H * 0.28), (xs, 0, H * 0.24)],
           5.5, color, finish="gloss")
    k.col("box", (12.0, 12.0, H * 0.46), (xs + 26.0, 0, H * 0.53), name="handle_col")
    k.col("box", (26.0, 11.0, 10.0), (xs + 12.0, 0, H * 0.78))
    k.col("box", (26.0, 11.0, 10.0), (xs + 12.0, 0, H * 0.27))
    if text:
        k.label_wrap([text], radius=R, z0=H * 0.25, z1=H * 0.75, arc_deg=100.0, style="paper")
    k.site("handle", (xs + 26.0, 0, H * 0.53))
    k.grasp("handle", "side", (xs + 26.0, 0, H * 0.53), 12.0)
    _rim_grasps(k, R, H - 12.0, 4.0, 3)
    k.tag("drink_vessel")
    k.mass(mass * 1000.0 + sum((contents or {}).values()))


@kind("glass", vary={"radius": (0.031, 0.036), "height": (0.10, 0.14)})
def glass(k: Kit, *, radius=0.034, height=0.12, contents=None, mass=0.22):
    """A drinking glass (tumbler)."""
    R, H = mm(radius, height)
    k.round_vessel([(R * 0.86, 0), (R, H)], wall=2.2, floor=8.0, color="glass_clear", contents=contents)
    k.grasp("body", "side", (0, 0, H * 0.5), 2 * R * 0.93)
    k.grasp("body_top", "top", (0, 0, H * 0.75), 2 * R)
    k.tag("drink_vessel", "fragile")
    k.mass(mass * 1000.0 + sum((contents or {}).values()))


@kind("wine_glass", priority=2)
def wine_glass(k: Kit, *, height=0.21, bowl_radius=0.037, contents=None, mass=0.16):
    """A stemmed glass: tall, light and easy to knock over."""
    H, R = mm(height, bowl_radius)
    stem_top = H * 0.48
    k.shape(M.revolve([(0, 0), (R * 0.88, 0), (R * 0.88, 1.5), (6, 4), (3.2, 10), (3.2, stem_top - 6), (0, stem_top - 6)], 32),
            "glass_clear", name="stem")
    k.round_vessel([(5.0, stem_top - 6), (R * 0.72, stem_top + 10), (R, stem_top + 36), (R * 0.98, H * 0.86), (R * 0.84, H)],
                   wall=1.4, floor=5.0, color="glass_clear", contents=contents, rings=[0, 1, 2, 4], name="bowl")
    k.foot(R * 0.88, 0.0, 3.0)
    k.col("cylinder", (3.5, stem_top - 8.0), (0, 0, (stem_top - 8.0) / 2.0 + 2.0), name="stem_col")
    k.grasp("stem", "side", (0, 0, stem_top * 0.55), 7.0)
    if 2 * R <= 76.0:
        k.grasp("bowl", "side", (0, 0, stem_top + 40.0), 2 * R)
    k.tag("drink_vessel", "fragile")
    k.mass(mass * 1000.0 + sum((contents or {}).values()))


@kind("bowl", vary={"radius": (0.065, 0.085), "color": ["white", "blue", "cream", "teal", "red"]})
def bowl(k: Kit, *, radius=0.075, height=0.065, color="white", contents=None, mass=0.35):
    """A food bowl. Too wide to hold across: grasps pinch the rim."""
    R, H = mm(radius, height)
    k.round_vessel([(0.46 * R, 0), (0.50 * R, 4), (0.74 * R, 0.30 * H), (0.92 * R, 0.66 * H), (R, H)], wall=3.5, floor=6.0,
                   color=color, contents=contents, rings=[1, 2, 3, 4], n=10)
    _rim_grasps(k, R, H - 11.0, 3.5)
    k.tag("food_vessel")
    k.mass(mass * 1000.0 + sum((contents or {}).values()))


@kind("dog_bowl", priority=2, vary={"color": ["steel", "red", "blue"]})
def dog_bowl(k: Kit, *, radius=0.085, height=0.055, color="steel", contents=None, text="DOG", mass=0.30):
    """A pet's food bowl with a wide base, empty or with kibble."""
    R, H = mm(radius, height)
    k.shape(M.revolve([(R * 0.7, 0), (R * 1.15, 0), (R * 1.15, 3), (R, H), (R - 4, H), (R - 4, H - 3), (R * 0.7, 8.0)], 40), color,
            name="base", finish="metal" if color == "steel" else "gloss")
    k.round_vessel([(R * 0.7, 8.0), (R - 5, H)], wall=3.0, floor=3.0, color=color, finish="metal" if color == "steel" else "gloss",
                   contents=contents, name="dish")
    k.foot(R * 1.15, 0.0, 3.0)
    k.ring(R * 1.15, R, 0.5, H, 4.0, 12)
    if text:
        k.label_wrap([text], radius=R * 1.136 + 0.8, r_top=R * 1.023 + 0.8, z0=8.0, z1=H - 8.0, arc_deg=70.0, style="dark")
    _rim_grasps(k, R, H - 10.0, 5.0)
    k.tag("food_vessel", "animal")
    k.mass(mass * 1000.0 + sum((contents or {}).values()))


FLANGE_TILT = 35.0          # degrees from straight down at which the hand comes in to pinch a flange (see below)
FLANGE_BACK = 12.0          # mm: the pinch point this far back from the flange along the way in


def _flange_grasps(k: Kit, r0: float, z0: float, radius: float, height: float, wall: float, n: int = 8) -> None:
    """The rim of a flat dish whose wall is a flange sloping up and out from (`r0`, `z0`) to (`radius`, `height`) (a
    saucer, a plate). Pads closing horizontally across such a flange from above squeeze it out like a wedge: the
    closing direction is (90 - slope) degrees off the flange's normal, more than the friction cone of rubber on glaze
    (about 45 degrees). It is pinched as a person pinches a plate: at the edge, the hand leaning out by `FLANGE_TILT`
    from straight down and coming in towards the middle, the inner finger on top of the flange and the outer one
    under its edge, closing within (90 - slope - tilt) degrees of square to it. (Coming in along the flange itself
    would close square to it, but the outer finger, 2 cm thick, then goes into the table under a 1.5 cm rim.)

    Side grasps at `n` places round the rim: the frame's +z runs along the rim (the axis the hand keeps square to),
    +x points up and out at the tilt (the hand comes in along -x: `actions.grasps_of`). `clearance`: the fingers
    open only 3 mm past the flange (under the edge there is little room)."""
    a = math.atan2(height - z0, radius - r0)
    tau = math.radians(FLANGE_TILT)
    r = radius - 2.5                                        # at the edge
    z = z0 + (r - r0) * math.tan(a) - (wall / 2.0) / math.cos(a)
    for i in range(n):
        th = math.radians(-90.0 + 360.0 * i / n)
        radial = np.array([math.cos(th), math.sin(th), 0.0])
        x = math.sin(tau) * radial + np.array([0.0, 0.0, math.cos(tau)])
        zz = np.array([-math.sin(th), math.cos(th), 0.0])
        y = np.cross(zz, x)
        q = mat_to_quat(np.column_stack([x, y, zz]))
        # the pinch point held 12 mm back along the way in: the flange sits between the far ends of the pads, and the
        # fingertips, which reach 18 mm past the pinch point, stay out of the table under the rim
        at = np.array([r * math.cos(th), r * math.sin(th), z]) + FLANGE_BACK * x
        k.grasp(f"rim_{i}", "side", tuple(at), wall / math.cos(math.radians(90.0) - a - tau) + 1.0, quat=q)
        k.grasps[-1]["clearance"] = 0.003


@kind("saucer", vary={"color": ["white", "cream", "blue"]})
def saucer(k: Kit, *, radius=0.072, height=0.018, color="white", mass=0.16):
    """A saucer: a shallow dish with a foot ring."""
    R, H = mm(radius, height)
    k.round_vessel([(0.5 * R, 0), (0.55 * R, 3), (R, H)], wall=3.0, floor=5.0, color=color, liquid=False, rings=[1, 2], n=10)
    _flange_grasps(k, 0.55 * R, 3.0, R, H, 3.0)
    k.tag("food_vessel")
    k.mass(mass * 1000.0)


@kind("plate", priority=2, vary={"color": ["white", "cream", "blue"], "radius": (0.11, 0.135)})
def plate(k: Kit, *, radius=0.125, height=0.022, color="white", mass=0.45):
    """A dinner plate."""
    R, H = mm(radius, height)
    k.round_vessel([(0.55 * R, 0), (0.62 * R, 4), (R, H)], wall=3.5, floor=5.0, color=color, liquid=False, rings=[1, 2], n=12)
    _flange_grasps(k, 0.62 * R, 4.0, R, H, 3.5)
    k.tag("food_vessel")
    k.mass(mass * 1000.0)


@kind("beaker", vary={"volume_ml": [100, 250, 400, 600]})
def beaker(k: Kit, *, volume_ml=250, contents=None, label_text="", pictograms=(), mass=None, tall=False):
    """A laboratory beaker of clear glass with a pouring lip at the front and printed graduations.
    (`robosafebench.sim.props` has a primitive of the same name; ask for `catalog:beaker` in a scene to get this one.)
    `tall` (0.5.4, off by default: the default build is unchanged): a tall-form beaker, 70 mm across and 170 mm high
    (about 570 ml to the rim; graduated to `volume_ml`), narrow enough to be held across its body."""
    R = {100: 25.0, 250: 35.0, 400: 40.0, 600: 45.0}.get(int(volume_ml), 35.0 * (volume_ml / 250.0) ** (1 / 3))
    H = volume_ml * 1000.0 / (math.pi * (R - 2) ** 2) * 1.25
    if tall:
        R, H = 35.0, 170.0

    def lip(r, z, th):                                            # a spout pulled out of the rim at the front
        if z < H - 9.0:
            return r
        d = abs((th + math.pi / 2 + math.pi) % (2 * math.pi) - math.pi)
        return r + 5.0 * max(0.0, 1.0 - d / 0.45) * (z - (H - 9.0)) / 9.0

    from ..kit import shell_profile
    outer = [(R - 3, 0), (R, 3), (R, H - 4), (R + 2, H)]
    profile, _ = shell_profile(outer, 2.0, 3.0)
    k.shape(M.revolve(profile, 48, warp=lip), "glass_clear", name="glass")
    k.round_vessel(outer, wall=2.0, floor=3.0, contents=contents, rings=[1, 3], draw=False)
    marks = [(f"{int(volume_ml * f)}", 1.0) for f in (0.8, 0.6, 0.4, 0.2)]
    k.label_wrap(marks, radius=R, z0=H * 0.16, z1=H * 0.80, arc_deg=38.0, center_deg=-140.0,
                 style={"base": "paper", "bg": "white", "pad": 0.03}, name="scale")
    if label_text:
        k.label_wrap([label_text], pictograms, radius=R, z0=H * 0.25, z1=H * 0.75, arc_deg=110.0, center_deg=-60.0, style="plain")
    k.site("spout", (0, -(R + 6.0), H))
    k.vessel["spout_site"] = "spout"
    if 2 * R <= 76.0:
        k.grasp("body", "side", (0, 0, H * 0.55), 2 * R)
        k.grasp("body_top", "top", (0, 0, H * 0.8), 2 * R)
    _rim_grasps(k, R, H - 12.0, 2.0, 3)
    k.tag("fragile")
    k.mass((mass * 1000.0 if mass else 0.44 * volume_ml + 10.0) + sum((contents or {}).values()))


@kind("bucket", vary={"color": ["blue", "red", "yellow", "grey", "green"], "height": (0.22, 0.27)})
def bucket(k: Kit, *, radius=0.14, height=0.25, color="blue", contents=None, text="", mass=0.55):
    """A 10 litre bucket with a wire bail handle standing up, by which it is carried."""
    R, H = mm(radius, height)
    rb = R * 0.76
    k.round_vessel([(rb, 0), (R, H)], wall=2.5, floor=3.0, color=color, finish="satin", contents=contents, n=14)
    k.shape(M.revolve([(R - 1, H - 8), (R + 3, H - 8), (R + 3, H), (R - 1, H)], 48), color)
    top = H + 0.62 * R
    pts = [((R + 2) * math.cos(a), 0.0, H - 14 + (top - H + 14) * math.sin(a)) for a in np.linspace(0.0, math.pi, 11)]
    k.tube(pts, 3.0, "steel", solid=True, finish="metal", name="bail")
    k.vis("cylinder", (9.0, 90.0), (0, 0, top), "white", quat=qy(90), name="grip")
    if text:
        k.label_wrap([text], radius=rb + (R - rb) * 0.3, r_top=rb + (R - rb) * 0.8, z0=H * 0.3, z1=H * 0.8, arc_deg=70.0, style="plain")
    k.site("handle", (0, 0, top))
    k.grasp("handle", "top", (0, 0, top - 2.0), 18.0)
    _rim_grasps(k, R, H - 12.0, 2.5, 2)
    k.tag("storage")
    k.mass(mass * 1000.0 + sum((contents or {}).values()))


@kind("basin", vary={"color": ["white", "sky", "grey", "teal"], "fill": (0.0, 0.7)})
def basin(k: Kit, *, width=0.38, depth=0.30, height=0.12, color="white", fill=0.4, substance="water", mass=0.6):
    """A wide low tub that holds water. `fill` (0 to 1) is how full it is; the water surface is drawn."""
    W, D, H = mm(width, depth, height)
    cap_ml = (W - 6) * (D - 6) * (H - 4) / 1000.0
    contents = {substance: round(fill * cap_ml, 1)} if fill > 0 else {}
    k.box_vessel(W, D, H, wall=3.0, floor=4.0, color=color, corner=40.0, contents=contents)
    k.shape(M.pocket_prism([M.Cell(rounded_rect(W + 14, D + 14, 44.0), M.Pocket(rounded_rect(W - 2, D - 2, 39.0)))], H - 5.0, H),
            color, name="rim")
    for sgn, nm in ((-1.0, "front"), (1.0, "back")):
        k.grasp(f"rim_{nm}", "top", (0, sgn * (D / 2.0 - 1.5), H - 12.0), 5.0)
    for sgn, nm in ((-1.0, "left"), (1.0, "right")):
        k.grasp(f"rim_{nm}", "top", (sgn * (W / 2.0 - 1.5), 0, H - 12.0), 5.0, yaw_deg=90.0)
    k.tag("storage")
    k.mass(mass * 1000.0 + sum(contents.values()))


@kind("tray", vary={"color": ["grey", "red", "blue", "green", "yellow", "white", "orange"], "width": (0.26, 0.34)})
def tray(k: Kit, *, width=0.30, depth=0.20, height=0.025, color="grey", text="", pictograms=(), label_style="plain",
         mass=0.35):
    """A tray with a low rim. `text` prints a label on the front of the rim (see also `storage_tray`)."""
    W, D, H = mm(width, depth, height)
    k.box_vessel(W, D, H, wall=4.0, floor=3.0, color=color, corner=10.0, liquid=False)
    k.zone("surface", (0, 0, 3.0 + 30.0), "box", (W - 8.0, D - 8.0, 60.0))
    if text:
        lh = max(H - 2.0, 18.0)
        k.label_flat([text], pictograms, size=(min(W - 30.0, 26.0 + 11.0 * len(text)), lh), pos=(0, -D / 2, lh / 2.0 + 1.0),
                     style=label_style)
    for sgn, nm in ((-1.0, "front"), (1.0, "back")):
        k.grasp(f"rim_{nm}", "top", (0, sgn * (D / 2.0 - 2.0), max(H - 10.0, 9.0)), 5.0)
    for sgn, nm in ((-1.0, "left"), (1.0, "right")):
        k.grasp(f"rim_{nm}", "top", (sgn * (W / 2.0 - 2.0), 0, max(H - 10.0, 9.0)), 5.0, yaw_deg=90.0)
    k.tag("storage")
    k.mass(mass * 1000.0)


@kind("coaster", priority=2, fixed=True, vary={"color": ["cork", "slate", "white", "teal"]})
def coaster(k: Kit, *, radius=0.050, thickness=0.004, color="cork", mass=0.03):
    """A round coaster for a hot drink: a flat disc 10 cm across and 4 mm thick (cork, slate, or a printed tile).
    Zone `surface`: where a mug or a glass is set down on it."""
    R, T = mm(radius, thickness)
    rgb = {"cork": (0.70, 0.52, 0.32), "slate": (0.20, 0.22, 0.25), "white": (0.93, 0.92, 0.90), "teal": (0.05, 0.50, 0.50)}.get(color, color)
    k.solid("cylinder", (R, T), (0, 0, T / 2.0), rgb, name="disc", finish="matte")
    k.vis("cylinder", (R * 0.80, 0.4), (0, 0, T + 0.2), tuple(min(1.0, c * 1.18 + 0.04) for c in rgb), name="ring", finish="matte")
    k.vis("cylinder", (R * 0.74, 0.5), (0, 0, T + 0.25), rgb, name="ring_in", finish="matte")
    k.zone("surface", (0, 0, T + 30.0), "box", (2 * R - 10.0, 2 * R - 10.0, 60.0))
    k.mass(mass * 1000.0)


@kind("storage_tray", priority=2,vary={"color": ["grey", "blue", "white", "yellow"],
                                        "text": ["DRY STORAGE", "FLAMMABLES", "ACIDS", "BASES", "OXIDISERS", "FOOD ONLY"]})
def storage_tray(k: Kit, *, width=0.30, depth=0.20, height=0.06, color="grey", text="DRY STORAGE", pictograms=(),
                 label_style="plain", mass=0.5):
    """A deeper storage tray with a printed label standing on the front rim."""
    W, D, H = mm(width, depth, height)
    k.box_vessel(W, D, H, wall=4.0, floor=3.0, color=color, corner=10.0, liquid=False)
    lw = min(W - 20.0, 40.0 + 13.0 * len(text) + (34.0 if pictograms else 0.0))
    k.label_flat([text], pictograms, size=(lw, H - 10.0), pos=(0, -D / 2, H / 2.0), style=label_style)
    for sgn, nm in ((-1.0, "left"), (1.0, "right")):
        k.grasp(f"rim_{nm}", "top", (sgn * (W / 2.0 - 2.0), 0, H - 12.0), 5.0, yaw_deg=90.0)
    k.grasp("rim_back", "top", (0, D / 2.0 - 2.0, H - 12.0), 5.0)
    k.tag("storage")
    k.mass(mass * 1000.0)


@kind("flower_pot", priority=2, vary={"color": ["brown", "white", "teal"], "radius": (0.055, 0.075)})
def flower_pot(k: Kit, *, radius=0.065, height=0.11, color=(0.72, 0.36, 0.22), plant=True, mass=0.9):
    """A clay pot with soil and a small plant, on a saucer."""
    R, H = mm(radius, height)
    k.shape(M.revolve([(0, 0), (R * 0.95, 0), (R * 1.0, 8), (R * 0.9, 8), (0, 5)], 40), color, name="dish", finish="matte")
    info = k.round_vessel([(R * 0.68, 4.0), (R * 0.97, H - 14), (R, H - 14), (R, H)], wall=5.0, floor=6.0, color=color, finish="matte",
                          contents={"soil": 1.0}, liquid=False, rings=[0, 1, 3])
    inner = info["inner"]
    k.vis("cylinder", (inner[-1][0] - 1.0, 6.0), (0, 0, H - 16.0), (0.25, 0.17, 0.11), name="soil", finish="matte")
    k.foot(R * 0.95, 0.0, 4.0)
    if plant:
        k.tube([(0, 0, H - 14), (2, 1, H + 50), (-3, 2, H + 95)], 2.5, (0.20, 0.50, 0.18), finish="matte")
        for i, (a, z, s) in enumerate(((20, 40, 1.0), (140, 55, 0.9), (255, 70, 1.0), (80, 88, 0.8), (320, 92, 0.75), (200, 100, 0.6))):
            c, sn = math.cos(math.radians(a)), math.sin(math.radians(a))
            k.vis("ellipsoid", (30.0 * s, 13.0 * s, 2.5), (c * 26 * s, sn * 26 * s, H + z), (0.16, 0.52 - 0.02 * i, 0.20),
                  quat=tuple(_q_mul(qz(a), qy(-25))), finish="matte")
    k.contents = {"soil": 300.0}
    if 2 * R <= 76.0:
        k.grasp("rim", "side", (0, 0, H - 30.0), 2 * R * 0.95)
    _rim_grasps(k, R, H - 12.0, 5.0, 2)
    k.tag("fragile")
    k.mass(mass * 1000.0)


def _q_mul(a, b):
    from ..model import quat_mul
    return quat_mul(a, b)


def _box_label(k, text, pictograms, W, D, H, style="kraft", frac=0.55):
    if text or pictograms:
        k.label_flat([t for t in ([text] if isinstance(text, str) else list(text)) if t], pictograms,
                     size=(W * 0.72, H * frac), pos=(0, -D / 2, H * 0.5), style=style)


@kind("cardboard_box", priority=2, vary={"width": (0.22, 0.32), "height": (0.16, 0.24)})
def cardboard_box(k: Kit, *, width=0.28, depth=0.20, height=0.20, text="FRAGILE", pictograms=(), state="closed", mass=1.2,
                  grip=False, top_text=None):
    """A cardboard carton, taped shut (`state="closed"`) or open with its flaps up. `grip=True` (0.5.0): a closed
    carton narrow enough for the gripper is taken from above across its width, near its top. `top_text` (0.5.4;
    default None, which builds the same model as before; closed): lines printed on a label on its lid, over the tape,
    to be read from above (the top camera, a `look` from above); site `top`."""
    W, D, H = mm(width, depth, height)
    kraft = (0.70, 0.55, 0.36)
    if state == "closed":
        k.shape(M.box((W, D, H), (0, 0, H / 2)), kraft, name="box", finish="matte")
        k.col("box", (W, D, H), (0, 0, H / 2), name="box_col")
        k.vis("box", (W + 0.6, 48.0, 0.6), (0, 0, H), (0.80, 0.70, 0.50), name="tape", finish="gloss")
        k.vis("box", (0.6, 48.0, 60.0), (-W / 2, 0, H - 30.0), (0.80, 0.70, 0.50), finish="gloss")
        k.vis("box", (0.6, 48.0, 60.0), (W / 2, 0, H - 30.0), (0.80, 0.70, 0.50), finish="gloss")
    else:
        k.box_vessel(W, D, H, wall=4.0, floor=4.0, color=kraft, finish="matte", corner=0.0, liquid=False)
        for sgn in (-1.0, 1.0):
            k.vis("box", (W, 3.0, D * 0.45), (0, sgn * (D / 2 + D * 0.10), H + D * 0.20), kraft, quat=qx(-sgn * 25.0), finish="matte")
            k.vis("box", (3.0, D, W * 0.3), (sgn * (W / 2 + W * 0.07), 0, H + W * 0.13), kraft, quat=qy(sgn * 25.0), finish="matte")
    _box_label(k, text, pictograms, W, D, H, "kraft", 0.4)
    if top_text and state == "closed":
        k.label_flat(list(top_text), size=(W - 10.0, min(D - 10.0, 1.6 * (W - 10.0))), pos=(0, 0, H + 0.7), normal=(0, 0, 1),
                     up=(0, 1, 0), name="top", style={"base": "paper", "bg": "white", "fg": "black", "pad": 0.06})
    if grip and state == "closed":                                # across its width: the fingers stay clear of its front and back
        k.grasp("body", "top", (0, 0, H - 15.0), W, yaw_deg=90.0)
    k.tag("paper", "flammable", "storage")
    k.mass(mass * 1000.0)


@kind("packing_box", priority=2, vary={"text": ["PARCEL", "THIS SIDE UP", "RETURNS"]})
def packing_box(k: Kit, *, width=0.20, depth=0.15, height=0.10, text="PARCEL", address=("TO: J. DOE", "12 ELM ST"), mass=0.6):
    """A small closed parcel with an address label on top."""
    W, D, H = mm(width, depth, height)
    kraft = (0.72, 0.57, 0.38)
    k.shape(M.box((W, D, H), (0, 0, H / 2)), kraft, name="box", finish="matte")
    k.col("box", (W, D, H), (0, 0, H / 2), name="box_col")
    k.vis("box", (W + 0.6, 40.0, 0.6), (0, 0, H), (0.82, 0.72, 0.52), name="tape", finish="gloss")
    k.label_flat(list(address), size=(W * 0.5, D * 0.42), pos=(-W * 0.18, -D * 0.18, H + 0.5), normal=(0, 0, 1), style="plain",
                 name="address")
    _box_label(k, text, (), W, D, H, "kraft", 0.45)
    k.tag("paper", "storage")
    k.mass(mass * 1000.0)


@kind("tote", priority=2, vary={"color": ["blue", "grey", "yellow", "red", "green"]})
def tote(k: Kit, *, width=0.40, depth=0.30, height=0.22, color="blue", text="", pictograms=(), mass=1.4):
    """An open plastic crate with hand holes."""
    W, D, H = mm(width, depth, height)
    k.box_vessel(W, D, H, wall=4.0, floor=4.0, color=color, corner=14.0, liquid=False)
    k.shape(M.pocket_prism([M.Cell(rounded_rect(W + 12, D + 12, 18.0), M.Pocket(rounded_rect(W - 2, D - 2, 13.0)))], H - 14.0, H),
            color, name="rim")
    for sgn in (-1.0, 1.0):
        k.vis("box", (1.0, 90.0, 28.0), (sgn * (W / 2 + 0.2), 0, H - 40.0), "black", name=f"hand_hole_{int(sgn > 0)}")
    if text or pictograms:
        k.label_flat([text] if text else [], pictograms, size=(W * 0.5, H * 0.4), pos=(0, -D / 2, H * 0.45), style="plain")
    for sgn, nm in ((-1.0, "left"), (1.0, "right")):
        k.grasp(f"rim_{nm}", "top", (sgn * (W / 2.0 - 2.0), 0, H - 12.0), 5.0, yaw_deg=90.0)
    k.tag("storage")
    k.mass(mass * 1000.0)


@kind("cover_box", priority=2, vary={"color": ["grey", "glass_clear", "blue"]})
def cover_box(k: Kit, *, width=0.22, depth=0.22, height=0.20, color="plastic_clear", mass=0.5):
    """A box without a bottom, to put over things. A knob on top to lift it by."""
    W, D, H = mm(width, depth, height)
    t = 4.0
    k.shape(M.pocket_prism([M.Cell(rounded_rect(W, D, 6.0), M.Pocket(rounded_rect(W - 2 * t, D - 2 * t, 3.0)))], 0.0, H - t), color,
            name="walls")
    k.shape(rbox(W, D, t, 6.0, (0, 0, H - t / 2)), color, name="lid")
    k.col("box", (W, D, t), (0, 0, H - t / 2))
    for sgn in (-1.0, 1.0):
        k.col("box", (t, D, H - t), (sgn * (W - t) / 2, 0, (H - t) / 2))
        k.col("box", (W - 2 * t, t, H - t), (0, sgn * (D - t) / 2, (H - t) / 2))
    k.solid("cylinder", (6.0, 22.0), (0, 0, H + 11.0), "black", name="stem")
    k.solid("box", (40.0, 26.0, 16.0), (0, 0, H + 30.0), "black", name="knob")
    k.site("handle", (0, 0, H + 30.0))
    k.zone("inside", (0, 0, (H - t) / 2), "box", (W - 2 * t, D - 2 * t, H - t), place=False)
    k.grasp("handle", "top", (0, 0, H + 28.0), 26.0)
    k.mass(mass * 1000.0)


@kind("pill_bottle", priority=2, vary={"product": ["ASPIRIN", "VITAMIN C", "SLEEP AID", "PAIN AWAY", "ANTACID"],
                                       "color": ["white", "orange"]})
def pill_bottle(k: Kit, *, radius=0.024, height=0.085, product="ASPIRIN", lines=("500 mg", "100 TABLETS"), color="white",
                cap_color="white", warning="KEEP AWAY FROM CHILDREN", pills=60, cap="on", label_yaw_deg=0.0, mass=None,
                wear=None):
    """A pill bottle with a child-proof cap and a pharmacy label. `wear` (0.5.0): the label worn
    (`robosafebench.assets.wear`)."""
    R, H = mm(radius, height)
    alpha = 0.8 if color == "orange" else None
    hb = H - 16.0
    k.shape(M.revolve([(0, 0), (R - 1.5, 0), (R, 1.5), (R, hb - 6), (R - 4, hb), (R - 4, hb + 8), (0, hb + 8)], 36), color,
            name="bottle", finish="gloss", alpha=alpha)
    k.round_body(R, 0.0, hb, name="bottle_col")
    top = hb + 8.0
    if cap != "on":
        k.vis("cylinder", (R - 6.0, 0.8), (0, 0, top + 0.3), (0.05, 0.04, 0.04), name="opening", finish="matte")
    if cap == "on":
        k.shape(M.revolve([(0, hb - 2), (R + 1, hb - 2), (R + 1, H - 1.5), (R - 0.5, H), (0, H)], 36), cap_color, name="cap")
        k.col("cylinder", (R + 1, 16.0), (0, 0, H - 8.0), name="cap_col")
        top = H
    # A product name remains one logical text even when its existing layout splits it across two lines.
    head = ([{"text": product, "h": 1.2, "text_group": "product"}] if " " not in product else
            [{"text": product.split(" ", 1)[0], "h": 1.1, "text_group": "product"},
             {"text": product.split(" ", 1)[1], "h": 1.0, "text_group": "product"}])
    text_lines = head + [(t, 0.9) for t in lines[:1]] + [{"text": t, "h": 0.6, "fine": True} for t in lines[1:]]
    text_lines += [{"text": warning, "h": 0.45, "fine": True}] if warning else []
    k.label_wrap(text_lines, radius=R, z0=5.0, z1=hb - 8.0, arc_deg=124.0, center_deg=-90.0 + label_yaw_deg,
                 style={"base": "product", "header": ("teal", "white")}, **({"wear": wear} if wear else {}))
    k.site("mouth", (0, 0, top))
    k.site("inside_bottom", (0, 0, 2.0))
    k.vessel = {"capacity_ml": round(math.pi * (R - 2) ** 2 * (hb - 2) / 1000.0, 1), "inner_radius": (R - 2) * 1e-3,
                "inner_depth": (hb - 2) * 1e-3, "bottom_site": "inside_bottom", "mouth_site": "mouth", "closed": cap == "on",
                "shape": "cyl", "bottom_offset": 0.0, "rim_site": "mouth"}
    k.contents = {"pills": float(pills)}
    k.extra["contents_unit"] = "count"
    k.grasp("body", "side", (0, 0, hb * 0.5), 2 * R)
    k.grasp("body_top", "top", (0, 0, H - 18.0), 2 * R + 2)
    k.tag("medicine")
    k.mass(mass * 1000.0 if mass else 22.0 + 0.6 * pills)


@kind("pill_organizer", priority=2)
def pill_organizer(k: Kit, *, days=7, color="sky", pills_per_day=2, open_days=(), mass=0.09):
    """A weekly pill organiser: seven compartments marked with the days, lids closed unless listed in `open_days`.
    The pills are contents, not bodies; they are drawn in the open compartments."""
    n = int(days)
    cw, D, H = 32.0, 38.0, 24.0
    W = n * cw + 4.0
    names = ["MON", "TUE", "WED", "THU", "FRI", "SAT", "SUN"]
    k.shape(rbox(W, D, H - 3.0, 4.0, (0, 0, (H - 3.0) / 2)), color, name="case", finish="gloss", alpha=0.85)
    k.col("box", (W, D, H), (0, 0, H / 2), name="case_col")
    for i in range(n):
        x = (i - (n - 1) / 2.0) * cw
        day = names[i % 7]
        is_open = i in tuple(open_days) or day in tuple(open_days)
        if is_open:
            k.vis("box", (cw - 4.0, D - 6.0, 1.0), (x, 0, H - 3.0), (0.95, 0.95, 0.97), name=f"well_{i}")
            for j in range(int(pills_per_day)):
                k.vis("ellipsoid", (5.0, 5.0, 2.2), (x - 6.0 + 12.0 * (j % 2), -6.0 + 12.0 * (j // 2), H - 1.2),
                      ("white", "pink", "note_yellow")[j % 3], name=f"pill_{i}_{j}")
            k.vis("box", (cw - 3.0, 2.0, D - 4.0), (x, D / 2 + 1.0, H + (D - 4.0) / 2 - 3.0), color, name=f"lid_{i}", alpha=0.85)
        else:
            k.vis("box", (cw - 3.0, D - 4.0, 3.0), (x, 0, H - 1.5), color, name=f"lid_{i}", finish="gloss")
            k.label_flat([day], size=(cw - 8.0, 14.0), pos=(x, 0, H), normal=(0, 0, 1),
                         style={"base": "paper", "bg": "white", "pad": 0.06}, name=f"lid_{i}_label")
        k.zone(f"day_{i}", (x, 0, H / 2), "box", (cw - 4.0, D - 6.0, H - 4.0), place=bool(is_open))
    k.contents = {"pills": float(n * pills_per_day)}
    k.extra["contents_unit"] = "count"
    k.extra["compartments"] = n
    k.grasp("body", "top", (0, 0, H - 9.0), D)
    k.tag("medicine")
    k.mass(mass * 1000.0)


@kind("salt_jar", priority=2, vary={"text": ["SALT", "SUGAR", "FLOUR", "RICE"]})
def salt_jar(k: Kit, *, radius=0.035, height=0.11, text="SALT", contents=None, lid_color="steel", label_yaw_deg=0.0, mass=None):
    """A glass storage jar with a metal lid and a printed name (salt, sugar, ...)."""
    R, H = mm(radius, height)
    hb = H - 14.0
    k.shape(M.revolve([(0, 0), (R - 2, 0), (R, 2), (R, hb - 5), (R - 3, hb), (0, hb)], 40), "glass_clear", name="jar")
    k.vis("cylinder", (R - 2.5, hb * 0.7), (0, 0, 3.0 + hb * 0.35), (0.96, 0.96, 0.95), name="fill", finish="matte")
    k.shape(M.revolve([(0, hb - 1), (R - 1, hb - 1), (R - 1, H - 1), (R - 2, H), (0, H)], 40), lid_color, name="lid", finish="metal")
    k.round_body(R, 0.0, H, name="jar_col")
    k.label_wrap([text], radius=R, z0=hb * 0.28, z1=hb * 0.78, arc_deg=120.0, center_deg=-90.0 + label_yaw_deg, style="plain")
    k.site("mouth", (0, 0, H))
    k.site("inside_bottom", (0, 0, 3.0))
    k.vessel = {"capacity_ml": round(math.pi * (R - 2.5) ** 2 * (hb - 3) / 1000.0, 1), "inner_radius": (R - 2.5) * 1e-3,
                "inner_depth": (hb - 3) * 1e-3, "bottom_site": "inside_bottom", "mouth_site": "mouth", "closed": True,
                "shape": "cyl", "bottom_offset": 0.0, "rim_site": "mouth"}
    k.contents = dict(contents) if contents else {text.lower(): 250.0}
    k.grasp("body", "side", (0, 0, hb * 0.5), 2 * R)
    k.grasp("body_top", "top", (0, 0, H - 20.0), 2 * R)
    k.tag("food", "fragile")
    k.mass(mass * 1000.0 if mass else 480.0)


@kind("spice_jar", priority=2, vary={"text": ["PEPPER", "PAPRIKA", "CUMIN", "CHILLI", "THYME"],
                                     "lid_color": ["red", "black", "green"]})
def spice_jar(k: Kit, *, radius=0.022, height=0.10, text="PEPPER", lid_color="red", label_yaw_deg=0.0, mass=0.14):
    """A small spice jar with a coloured shaker lid."""
    R, H = mm(radius, height)
    hb = H - 18.0
    k.shape(M.revolve([(0, 0), (R - 1.5, 0), (R, 1.5), (R, hb - 3), (R - 2, hb), (0, hb)], 32), "glass_clear", name="jar")
    k.vis("cylinder", (R - 2.0, hb * 0.75), (0, 0, 2.0 + hb * 0.375), {"PEPPER": (0.2, 0.18, 0.16), "PAPRIKA": (0.7, 0.2, 0.1),
          "CHILLI": (0.75, 0.15, 0.08), "CUMIN": (0.6, 0.45, 0.2), "CINNAMON": (0.5, 0.3, 0.15)}.get(text, (0.5, 0.4, 0.25)),
          name="fill", finish="matte")
    k.shape(M.revolve([(0, hb - 1), (R + 0.5, hb - 1), (R + 0.5, H - 2), (R - 1.5, H), (0, H)], 32), lid_color, name="lid")
    k.round_body(R, 0.0, H, name="jar_col")
    k.label_wrap([text], radius=R, z0=hb * 0.22, z1=hb * 0.80, arc_deg=150.0, center_deg=-90.0 + label_yaw_deg, style="plain")
    k.grasp("body", "side", (0, 0, hb * 0.5), 2 * R)
    k.grasp("body_top", "top", (0, 0, H - 22.0), 2 * R)
    k.tag("food")
    k.mass(mass * 1000.0)
