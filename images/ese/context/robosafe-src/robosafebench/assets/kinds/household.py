"""Things around the house that are neither kitchen nor electrical."""
from __future__ import annotations

import math

import numpy as np

from .. import labels as L
from .. import mesh as M
from ..catalog import kind
from ..kit import SUBSTANCES, Kit, mm, qy, rbox
from ..model import quat_from_z
from robosafebench.core import stream

FLAME = (1.0, 0.72, 0.18, 0.95)
FLAME_CORE = (1.0, 0.95, 0.70, 1.0)


@kind("candle", vary={"radius": (0.025, 0.037), "height": (0.08, 0.17), "color": ["cream", "white", "red", "purple"]})
def candle(k: Kit, *, radius=0.035, height=0.15, color="cream", state="lit", flame=1.0, mass=None):
    """A pillar candle. Looks `lit` (a flame on the wick) and `unlit`. Zone `flame`: a sphere around the flame.
    `flame` scales the flame (1.0: 11 mm across and 30 mm tall, which is about 10 by 20 pixels in the `front` image)."""
    R, H = mm(radius, height)
    f = float(flame)
    k.shape(M.revolve([(0, 0), (R - 1, 0), (R, 1), (R, H - 2), (R - 2, H), (R - 5, H - 3), (0, H - 4)], 40), color, name="wax",
            finish="satin")
    k.vis("cylinder", (1.0, 9.0), (0, 0, H - 4.0 + 4.5), "black", name="wick")
    zf = H + 3.0
    k.shape(M.revolve([(0, zf)] + [(r * f, zf + z * f) for r, z in ((4.0, 4), (5.5, 9), (4.6, 15), (2.4, 22), (0, 30))], 20), FLAME[:3],
            name="flame", finish="glow", alpha=FLAME[3])
    k.shape(M.revolve([(r * f, zf + z * f) for r, z in ((0, 2), (2.2, 5), (2.8, 9), (1.6, 14), (0, 18))], 16), FLAME_CORE[:3],
            name="flame_core", finish="glow")
    k.look("lit", "flame", FLAME)
    k.look("lit", "flame_core", FLAME_CORE)
    k.look("unlit", "flame", FLAME[:3] + (0.0,))
    k.look("unlit", "flame_core", FLAME_CORE[:3] + (0.0,))
    k.round_body(R, 0.0, H - 2.0, name="wax_col")
    k.zone("flame", (0, 0, zf + 12.0 * f), "sphere", (30.0 * f,))
    k.site("tip", (0, 0, zf + 12.0 * f))
    k.grasp("body", "side", (0, 0, H * 0.45), 2 * R)
    if H > 60.0:
        k.grasp("body_top", "top", (0, 0, H * 0.7), 2 * R)
    k.set_look("lit" if state == "lit" else "unlit")
    k.tag("open_flame", "flammable")
    k.mass(mass * 1000.0 if mass else 0.9 * math.pi * R * R * H / 1000.0)


def _blob(radius: float, rng, n: int = 56, wobble: float = 0.16) -> np.ndarray:
    """An irregular closed outline that stays inside `radius`: a circle with a few low harmonics added."""
    th = np.linspace(0.0, 2.0 * math.pi, n, endpoint=False)
    r = np.ones(n)
    for h in (2, 3, 5):
        r += wobble * (0.5 + 0.5 * float(rng.random())) / (1.0 + 0.4 * h) * 2.2 * np.cos(h * th + 2.0 * math.pi * float(rng.random()))
    r = radius * r / float(r.max())
    return np.stack([r * np.cos(th), r * np.sin(th)], axis=1)


@kind("puddle", fixed=True, vary={"radius": (0.06, 0.12), "shape_seed": [1, 2, 3, 4, 5, 6]})
def puddle(k: Kit, *, radius=0.09, substance="water", shape_seed=1, volume_ml=None):
    """Spilled liquid: one flat patch with an irregular outline, a darker wet edge around it, a pale streak of
    reflected light on it and a few drops beside it. A picture only: nothing collides with it and it is welded where
    it is put. Zone `area`: a cylinder over the patch.

    Water is drawn as what it looks like on a table: the table a little darker and bluer under a glossy film, not a
    patch of colour (seven overlapping pale-cyan discs, up to 0.1.1, were taken for a highlighted area)."""
    R = mm(radius)
    rgba = SUBSTANCES.get(substance, SUBSTANCES["water"])
    rng = stream(int(shape_seed), "puddle")
    clear = rgba[3] < 0.6                                            # water, saline: seen by what it does to the surface
    body = (0.30, 0.40, 0.50) if clear else rgba[:3]
    edge = (0.16, 0.20, 0.25) if clear else tuple(0.55 * c for c in rgba[:3])
    k.shape(M.extrude(_blob(R, rng), 0.2, 0.8), edge, alpha=0.38 if clear else 0.6, name="patch_edge", finish="matte")
    k.shape(M.extrude(_blob(R * 0.93, stream(int(shape_seed), "puddle")), 1.6, 2.2), body, alpha=0.50 if clear else min(0.9, rgba[3] + 0.1),
            name="patch_0", finish="gloss")
    a = 2.0 * math.pi * float(rng.random())                           # a streak of reflected light across the film
    ca, sa = math.cos(a), math.sin(a)
    streak = np.array([[ca * x - sa * y, sa * x + ca * y] for x, y in _blob(1.0, rng, 28, 0.08) * np.array([R * 0.34, R * 0.07])])
    k.shape(M.extrude(streak + np.array([-sa, ca]) * R * 0.25, 3.0, 3.3), (0.97, 0.98, 1.0), alpha=0.45, name="patch_light", finish="gloss")
    for i in range(1, 5):                                             # drops thrown clear of the patch
        t = 2.0 * math.pi * float(rng.random())
        d, r = R * (0.80 + 0.15 * float(rng.random())), R * (0.05 + 0.05 * float(rng.random()))
        k.shape(M.extrude(_blob(r, rng, 16, 0.10) + np.array([d * math.cos(t), d * math.sin(t)]), 0.2, 1.6), body,
                alpha=0.50 if clear else min(0.9, rgba[3] + 0.1), name=f"patch_{i}", finish="gloss")
    k.zone("area", (0, 0, 5.0), "cylinder", (R, 10.0), place=True)
    ml = float(volume_ml) if volume_ml is not None else round(math.pi * R * R * 1.5 / 1000.0, 1)
    k.contents = {substance: ml}
    k.extra["visual_only"] = True
    k.tag("liquid")
    k.mass(max(1.0, ml))


def fabric_image(w_px: int, h_px: int, base, stripe, seed: int = 1) -> np.ndarray:
    """Woven cloth: a base colour with a fine weave, a few stripes across one end."""
    rng = stream(seed, "fabric")
    b = np.array(L.rgb(base), dtype=np.float64)
    img = np.zeros((h_px, w_px, 3), dtype=np.float64)
    img[:, :] = b
    yy, xx = np.mgrid[0:h_px, 0:w_px]
    img *= (0.93 + 0.07 * (((xx // 2) + (yy // 2)) % 2))[:, :, None]
    img += (rng.random((h_px, w_px, 1)) - 0.5) * 14.0
    s = np.array(L.rgb(stripe), dtype=np.float64)
    for f in (0.12, 0.18, 0.24):
        img[:, int(w_px * f):int(w_px * (f + 0.035))] = s
    return np.clip(img, 0, 255).astype(np.uint8)


@kind("towel", priority=2, vary={"color": ["white", "sky", "cream", "pink", "lime"], "stripe": ["blue", "red", "green", "grey"]})
def towel(k: Kit, *, width=0.30, depth=0.20, thickness=0.012, color="white", stripe="blue", drape=70.0, mass=0.35):
    """A small towel that hangs: two stiff halves hinged to a narrow strip along the middle (joints `fold_front`,
    `fold_back`), with a loop on the strip to pick it up by. On a flat surface it lies flat. Lifted by the loop, the
    halves hang down, `drape` degrees from level, so that put down over a rail, a bar or the top of something
    narrow it comes to rest astride it."""
    from ..model import Joint
    W, D, T = mm(width, depth, thickness)
    S = 16.0                                                     # the strip along the fold
    P = (D - S) / 2.0                                            # one half, from the fold outwards
    k.shape(rbox(W, S, T, 3.0, (0, 0, T / 2), 3), color, name="fold", finish="matte")
    k.col("box", (W, S, T), (0, 0, T / 2), name="fold_col")
    k.decal(fabric_image(480, max(int(480 * S / W), 8), color, stripe), size=(W - 4.0, S), pos=(0, 0, T), normal=(0, 0, 1), name="cloth")
    half_g = mass * 1000.0 * 0.45 * P / (P + S / 2.0)
    for nm, sgn in (("front", -1.0), ("back", 1.0)):
        # the hinge runs along the edge of the strip; a positive angle lets the half hang
        b = k.part(f"half_{nm}", (0, sgn * S / 2.0, T / 2.0), mass_g=half_g)
        b.joints.append(Joint(f"fold_{nm}", "hinge", axis=(-sgn, 0, 0), range=(0.0, math.radians(float(drape))), damping=0.0015,
                              frictionloss=0.0003, armature=0.00002, stiff_limit=True, role="fold"))
        k.shape(rbox(W, P, T, 6.0, (0, sgn * P / 2.0, 0), 4), color, name=f"pad_{nm}", body=b, finish="matte")
        k.col("box", (W, P - 1.0, T), (0, sgn * (P + 1.0) / 2.0, 0), name=f"pad_{nm}_col", body=b)
        k.decal(fabric_image(480, int(480 * P / W), color, stripe), size=(W - 14.0, P - 8.0), pos=(0, sgn * P / 2.0, T / 2.0),
                normal=(0, 0, 1), name=f"cloth_{nm}", body=b)
    k.solid("box", (10.0, 5.0, 26.0), (0, 0, T + 13.0), stripe, name="loop", finish="matte")
    k.site("handle", (0, 0, T + 14.0))
    k.grasp("loop", "top", (0, 0, T + 14.0), 5.0)
    k.zone("above", (0, 0, T + 20.0), "box", (W, D, 40.0))
    k.extra["limp"] = ["half_front", "half_back"]                # they hang from the strip also while the hand holds it
    k.tag("fabric", "flammable")
    k.mass(mass * 1000.0)


@kind("drying_rack", priority=2, vary={"color": ["white", "aluminium"]})
def drying_rack(k: Kit, *, width=0.55, depth=0.36, height=0.42, rails=5, color="white", mass=1.6):
    """A clothes drying rack: two end frames and rails between them. Zone `rails`: where laundry hangs; it is an
    open place (bars with gaps: pointing at what shows between the rails from above means the rails)."""
    W, D, H = mm(width, depth, height)
    n = int(rails)
    r = 5.0
    for sgn, nm in ((-1.0, "left"), (1.0, "right")):
        x = sgn * (W / 2 - r)
        k.tube([(x, -D / 2 + r, r), (x, -D * 0.30, H - r), (x, D * 0.30, H - r), (x, D / 2 - r, r)], r, color, solid=True,
               name=f"frame_{nm}", finish="gloss")
        k.col("box", (14.0, D, 8.0), (x, 0, 4.0), name=f"foot_{nm}")
        k.vis("box", (10.0, D - 20.0, 6.0), (x, 0, 4.0), color)
    for i in range(n):
        y = -D * 0.30 + D * 0.60 * i / (n - 1)
        k.tube([(-W / 2 + r, y, H - r), (W / 2 - r, y, H - r)], 3.5, color, solid=True, name=f"rail_{i}", finish="gloss")
        k.site(f"rail_{i}", (0, y, H - r + 3.5))
    k.zone("rails", (0, 0, H - r + 3.5 + 30.0), "box", (W, D * 0.7, 60.0), place=True, open=True)
    k.zone("below", (0, 0, (H - 130.0) / 2), "box", (W - 30.0, D, H - 130.0), place=True)
    k.mass(mass * 1000.0)


@kind("pet_carrier", priority=2, vary={"color": ["blue", "red", "grey", "teal"]})
def pet_carrier(k: Kit, *, width=0.30, depth=0.46, height=0.30, color="blue", mass=1.9):
    """A pet carrier: a plastic shell with vents, a wire door at the front (joint `door`) and a handle on top.
    Zone `inside`."""
    W, D, H = mm(width, depth, height)
    t = 6.0
    iw, idp, ih = k.case(W, D, H, t, color, finish="gloss")
    k.zone("inside", (0, t / 2, H / 2), "box", (iw, idp, ih))
    for sgn in (-1.0, 1.0):
        for i in range(4):
            k.vis("box", (1.0, D * 0.5, 9.0), (sgn * (W / 2 + 0.2), 0, H * 0.48 + 18.0 * i), (0.04, 0.04, 0.05), name=None)
    leaf = k.part("door_leaf", (-W / 2 + t, -D / 2, t), mass_g=250.0)
    from ..model import Joint
    leaf.joints.append(Joint("door", "hinge", axis=(0, 0, -1), range=(0.0, 1.9), damping=0.05, frictionloss=0.03, armature=0.001,
                             role="door"))
    dw, dh = W - 2 * t, H - 2 * t
    for i in range(7):
        x = dw * (i + 0.5) / 7.0
        k.vis("cylinder", (1.6, dh), (x, -3.0, dh / 2), "steel", body=leaf, name=None, finish="metal")
    for z in (2.0, dh / 2, dh - 2.0):
        k.vis("cylinder", (1.8, dw), (dw / 2, -3.0, z), "steel", quat=qy(90), body=leaf, finish="metal")
    k.col("box", (dw, 5.0, dh), (dw / 2, -3.0, dh / 2), body=leaf, name="door_col")
    k.vis("box", (10.0, 8.0, 24.0), (dw - 8.0, -8.0, dh / 2), "black", body=leaf, name="latch")
    k.site("door_handle", (dw - 8.0, -12.0, dh / 2), body=leaf)
    k.door("door", "door", open=1.6, closed=0.0, kp=0.6, kv=0.1, force=1.0)
    k.solid("box", (30.0, 150.0, 16.0), (0, 0, H + 30.0), "dark_grey", name="handle", finish="matte")
    for sy in (-65.0, 65.0):
        k.solid("box", (24.0, 14.0, 26.0), (0, sy, H + 11.0), "dark_grey", finish="matte")
    k.site("handle", (0, 0, H + 30.0))
    k.grasp("handle", "top", (0, 0, H + 29.0), 30.0, yaw_deg=90.0)
    k.tag("animal", "storage")
    k.mass(mass * 1000.0)


@kind("sink", priority=2, fixed=True, vary={"state": ["off", "running"]})
def sink(k: Kit, *, width=0.60, depth=0.50, height=0.22, state="off", contents=None, mass=9.0):
    """A sink set in a counter block: a steel basin (zone `inside`) with a drain (zone `drain`), a tap at the back with
    a lever (control `tap`). Looks `running` (water falls from the spout) and `off`."""
    W, D, H = mm(width, depth, height)
    bw, bd, bh = W - 140.0, D - 150.0, H - 30.0
    by = -30.0
    counter = (0.80, 0.80, 0.78)
    # counter block around the basin
    k.solid("box", (W, D, H - bh), (0, 0, (H - bh) / 2), counter, name="counter_base", finish="matte")
    k.solid("box", ((W - bw) / 2, D, bh), (-(W + bw) / 4, 0, H - bh / 2), counter, name="counter_left", finish="matte")
    k.solid("box", ((W - bw) / 2, D, bh), ((W + bw) / 4, 0, H - bh / 2), counter, name="counter_right", finish="matte")
    k.solid("box", (bw, D / 2 + by - bd / 2, bh), (0, (-D / 2 + by - bd / 2) / 2, H - bh / 2), counter, name="counter_front", finish="matte")
    k.solid("box", (bw, D / 2 - by - bd / 2, bh), (0, (D / 2 + by + bd / 2) / 2, H - bh / 2), counter, name="counter_back", finish="matte")
    k.box_vessel(bw, bd, bh, wall=2.0, floor=2.0, color="steel", finish="metal", corner=24.0, center=(0, by), z0=H - bh, contents=contents)
    k.vis("cylinder", (22.0, 1.0), (0, by, H - bh + 2.4), (0.10, 0.10, 0.11), name="drain_hole")
    k.zone("drain", (0, by, H - bh + 12.0), "cylinder", (30.0, 20.0))
    ty = by + bd / 2 + 38.0
    k.solid("cylinder", (20.0, 30.0), (0, ty, H + 15.0), "steel", name="tap_base", finish="metal")
    k.tube([(0, ty, H + 30.0), (0, ty, H + 190.0), (0, ty - 60.0, H + 215.0), (0, ty - 130.0, H + 190.0), (0, ty - 140.0, H + 160.0)], 10.0,
           "steel", solid=True, finish="metal", name="tap")
    spout = (0.0, ty - 140.0, H + 150.0)
    k.site("spout", spout)
    k.button("tap", (30.0, ty, H + 24.0), axis=(1, 0, 0), size=(16.0, 40.0), color="steel", kind="switch", finish="metal", proud=28.0, travel=6.0)
    fall = spout[2] - (H - bh + 2.0)
    k.vis("cylinder", (5.0, fall), (spout[0], spout[1], spout[2] - fall / 2), (0.55, 0.75, 0.95), alpha=0.0, name="stream", finish="gloss")
    k.look("running", "stream", (0.55, 0.75, 0.95, 0.6))
    k.look("off", "stream", (0.55, 0.75, 0.95, 0.0))
    k.set_look("running" if state == "running" else "off")
    k.tag("sink")
    k.mass(mass * 1000.0)


PURSE_COLORS = {"brown": (0.36, 0.22, 0.13), "black": (0.09, 0.09, 0.10), "tan": (0.62, 0.43, 0.25), "burgundy": (0.40, 0.09, 0.13)}


@kind("purse", priority=2, vary={"color": list(PURSE_COLORS)})
def purse(k: Kit, *, width=0.11, depth=0.045, height=0.09, color="brown", grips="both", mass=0.2):
    """A small leather purse standing on its base, its width along x: a flap over the top with a gold clasp on the
    front (-y), a strap handle arching over the top, stitching round the front. Taken from the side at its +x end,
    across its depth (the grip `end`), so that a hand coming at the end of the bag closes on it; or from above at that end
    (`end_top`). `grips`: "both", "side" (`end` only) or "top" (`end_top` only)."""
    W, D, H = mm(width, depth, height)
    c = PURSE_COLORS[color] if isinstance(color, str) else color
    seam = tuple(min(1.0, v * 1.9 + 0.12) for v in c)
    k.shape(rbox(W, D, H, 10.0, (0, 0, H / 2), 4), c, name="bag", finish="satin")
    k.col("box", (W, D, H), (0, 0, H / 2), name="bag_col")
    k.vis("box", (W - 6.0, 3.0, H * 0.38), (0, -D / 2 - 0.6, H * 0.80), tuple(v * 0.8 for v in c), name="flap", finish="satin")
    k.vis("box", (16.0, 2.0, 12.0), (0, -D / 2 - 2.2, H * 0.62), (0.85, 0.70, 0.25), name="clasp", finish="gloss")
    k.vis("box", (W - 14.0, 0.8, 0.8), (0, -D / 2 - 0.3, 8.0), seam, name="seam_low")
    k.tube([(-W * 0.30, 0, H - 2.0), (-W * 0.20, 0, H + 32.0), (W * 0.20, 0, H + 32.0), (W * 0.30, 0, H - 2.0)], 3.5, c)      # the handle
    if grips in ("both", "side"):
        k.grasp("end", "side", (W / 2 - 16.0, 0, H * 0.5), D)
    if grips in ("both", "top"):
        k.grasp("end_top", "top", (W / 2 - 16.0, 0, H - 12.0), D)      # the same end from above, across its depth
    k.site("end", (W / 2 - 16.0, 0, H * 0.5))
    k.mass(mass * 1000.0)


GLOVE = {"yellow": (0.98, 0.80, 0.10), "blue": (0.22, 0.45, 0.86), "pink": (0.95, 0.47, 0.62), "green": (0.30, 0.66, 0.36)}


@kind("glove", vary={"color": list(GLOVE), "side": ["right", "left"]})
def glove(k: Kit, *, color="yellow", side="right", scale=1.0, mass=0.06):
    """An empty rubber household glove lying flat, palm down, fingers towards +x: a long cuff open at -x (a dark
    opening shows at its end), the palm, four fingers and a thumb, all flat and in one bright colour. Laid where the
    `hand` figure lies (same frame, same palm and fingers), it shows a glove left on the table where there could have been
    a hand: no forearm, no sleeve, no skin. Parts that collide: `palm`, `cuff`, `finger_0` to `finger_3`, `thumb`. Not a
    figure: it carries no tag (no `human`)."""
    s = float(scale)
    c = GLOVE[color] if isinstance(color, str) else color
    m = 1.0 if side == "right" else -1.0
    k.solid("box", (146 * s, 78 * s, 10 * s), (-77 * s, 0, 5 * s), c, name="cuff", finish="gloss")      # from the opening to under the palm
    k.vis("box", (4 * s, 66 * s, 7 * s), (-149 * s, 0, 5 * s), (0.10, 0.08, 0.05), name="cuff_opening", finish="matte")
    k.vis("box", (6 * s, 82 * s, 12 * s), (-148 * s, 0, 6 * s), c, name="cuff_rim", finish="gloss")
    k.solid("box", (92 * s, 84 * s, 14 * s), (36 * s, 0, 7 * s), c, name="palm", finish="gloss")
    for i, (y, ln) in enumerate(((-31, 72), (-10, 80), (11, 74), (31, 58))):
        a, b = np.array((80 * s, m * y * s, 6.5 * s)), np.array(((80 + ln) * s, m * y * 1.12 * s, 6.0 * s))
        d = b - a
        k.solid("capsule", (6.5 * s, float(np.linalg.norm(d))), tuple((a + b) / 2.0), c, quat=quat_from_z(d), name=f"finger_{i}", finish="gloss")
    a, b = np.array((18 * s, -m * 44 * s, 7 * s)), np.array((72 * s, -m * 72 * s, 6.5 * s))
    k.solid("capsule", (7.0 * s, float(np.linalg.norm(b - a))), tuple((a + b) / 2.0), c, quat=quat_from_z(b - a), name="thumb", finish="gloss")
    k.site("palm", (36 * s, 0, 14 * s))
    k.mass(mass * 1000.0)
