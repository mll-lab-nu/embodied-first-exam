"""Light laboratory things: tubes, bins, the solvent cabinet, the waste carboy."""
from __future__ import annotations

import math

import numpy as np

from .. import mesh as M
from ..catalog import kind
from ..kit import SUBSTANCES, Kit, mm, rbox, rounded_rect
from .containers import _rim_grasps
from .furniture import _cabinet


@kind("sample_tube", priority=2, vary={"text": ["SAMPLE 12", "BLOOD 07", "SWAB 3", "CULTURE A"], "cap_color": ["blue", "red", "purple", "green"]})
def sample_tube(k: Kit, *, radius=0.0145, height=0.115, text="SAMPLE 12", biohazard=True, cap_color="blue", fill=0.5,
                substance="sample", label_yaw_deg=0.0, mass=None, wear=None, frosted=False):
    """A capped 50 ml tube that stands on its skirt, with a written label and (by default) the biohazard symbol.
    `wear` (0.5.0): the label worn (`robosafebench.assets.wear`; in reading orientation, the symbol on the left).
    `frosted` (0.5.0): an opaque white tube, its contents not seen."""
    R, H = mm(radius, height)
    hb = H - 14.0
    k.shape(M.revolve([(0, 0), (R, 0), (R, hb), (R - 1.2, hb), (R - 1.2, 22.0), (3.0, 4.0), (0, 4.0)], 32), "white" if frosted else "plastic_clear",
            name="tube", **({"finish": "matte"} if frosted else {}))
    cap_ml = math.pi * (R - 1.2) ** 2 * (hb - 16.0) / 1000.0
    ml = max(0.0, min(1.0, fill)) * cap_ml
    if ml > 0 and not frosted:
        rg = SUBSTANCES.get(substance, SUBSTANCES["sample"])
        lvl = ml * 1000.0 / (math.pi * (R - 1.4) ** 2)
        k.vis("cylinder", (R - 1.5, lvl), (0, 0, 20.0 + lvl / 2), rg[:3], alpha=rg[3], name="liquid")
    k.shape(M.revolve([(0, hb - 2), (R + 2.5, hb - 2), (R + 2.5, H - 1), (R + 1, H), (0, H)], 32), cap_color, name="cap")
    k.round_body(R, 0.0, hb, name="tube_col")
    k.col("cylinder", (R + 2.5, 14.0), (0, 0, H - 7.0), name="cap_col")
    k.label_wrap([text], ("biohazard",) if biohazard else (), radius=R, z0=22.0, z1=hb - 3.0, arc_deg=100.0, upright=False,
                 center_deg=-90.0 + label_yaw_deg, style={"base": "plain", "pictograms": "left", "pictogram_share": 0.30, "border": None},
                 **({"wear": wear} if wear else {}))
    k.site("mouth", (0, 0, H))
    k.site("inside_bottom", (0, 0, 6.0))
    k.vessel = {"capacity_ml": round(cap_ml, 1), "inner_radius": (R - 1.2) * 1e-3, "inner_depth": (hb - 6.0) * 1e-3,
                "bottom_site": "inside_bottom", "mouth_site": "mouth", "closed": True, "shape": "cyl", "bottom_offset": 0.0,
                "rim_site": "mouth"}
    k.contents = {substance: round(ml, 1)} if ml > 0 else {}
    k.grasp("body", "side", (0, 0, hb * 0.6), 2 * R)
    k.grasp("cap", "top", (0, 0, H - 16.0), 2 * R + 5.0)
    if biohazard:
        k.tag("biohazard")
    k.mass(mass * 1000.0 if mass else 13.0 + ml)


def _bin(k: Kit, R, H, color, lines, pictograms, style, mass, liner=None):
    rb = R * 0.80
    k.round_vessel([(rb, 0), (R, H)], wall=3.0, floor=4.0, color=color, finish="satin", liquid=False, n=14)
    k.shape(M.revolve([(R - 1, H - 10), (R + 4, H - 10), (R + 4, H), (R - 1, H)], 48), color, name="rim")
    if liner:
        k.shape(M.revolve([(R - 2.5, H - 30), (R + 5.5, H - 30), (R + 5.5, H + 1.5), (R - 2.5, H + 1.5)], 48), liner, name="liner", alpha=0.85)
    r_lab0 = rb + (R - rb) * 0.30
    r_lab1 = rb + (R - rb) * 0.86
    k.label_wrap(lines, pictograms, radius=r_lab0 + 0.6, r_top=r_lab1 + 0.6, z0=H * 0.30, z1=H * 0.86, arc_deg=64.0, style=style)
    _rim_grasps(k, R, H - 12.0, 3.0, 4)
    k.mass(mass * 1000.0)


@kind("waste_bin", priority=2, vary={"color": ["grey", "dark_grey", "blue", "green"], "text": ["GENERAL WASTE", "PAPER ONLY", "RECYCLING"]})
def waste_bin(k: Kit, *, radius=0.13, height=0.30, color="grey", text="GENERAL WASTE", mass=0.9):
    """An open waste bin with its purpose printed on the front."""
    R, H = mm(radius, height)
    _bin(k, R, H, color, text.split(" ", 1) if " " in text else [text], (), "plain", mass)
    k.tag("waste_bin")


@kind("biohazard_bin", priority=2)
def biohazard_bin(k: Kit, *, radius=0.13, height=0.32, color="yellow", text="BIOHAZARD", mass=1.0):
    """A yellow bin for infectious waste with the biohazard symbol, lined with a red bag."""
    R, H = mm(radius, height)
    _bin(k, R, H, color, [text], ("biohazard",), {"base": "plain", "pictograms": "top", "pictogram_share": 0.62}, mass, liner="ghs_red")
    k.tag("waste_bin", "biohazard")


@kind("sharps_box", priority=2)
def sharps_box(k: Kit, *, width=0.16, depth=0.13, height=0.21, mass=0.35):
    """A sharps container: yellow box, red lid with a round opening (zone `opening`) and a carrying bar."""
    W, D, H = mm(width, depth, height)
    hb = H - 28.0
    k.box_vessel(W, D, hb, wall=3.0, floor=3.0, color="yellow", corner=10.0, liquid=False)
    # the lid: four strips around a square opening
    op = 62.0
    k.shape(M.pocket_prism([M.Cell(rounded_rect(W + 4, D + 4, 12.0), M.Pocket(M.circle(op / 2, 24, (-W * 0.14, 0.0))))], hb, H),
            "ghs_red", name="lid", finish="gloss")
    cx = -W * 0.14
    k.col("box", (W / 2 + cx - op / 2 + 2.0, D + 4, 28.0), ((-W / 2 - 2 + cx - op / 2) / 2, 0, hb + 14.0))
    k.col("box", (W / 2 - cx - op / 2 + 2.0, D + 4, 28.0), ((W / 2 + 2 + cx + op / 2) / 2, 0, hb + 14.0))
    for sgn in (-1.0, 1.0):
        k.col("box", (op, (D + 4 - op) / 2, 28.0), (cx, sgn * (D + 4 + op) / 4, hb + 14.0))
    k.zone("opening", (cx, 0, H + 10.0), "cylinder", (op / 2, 60.0), place=True)
    k.solid("box", (16.0, 70.0, 12.0), (W * 0.30, 0, H + 22.0), "ghs_red", name="handle")
    for sy in (-30.0, 30.0):
        k.solid("box", (12.0, 10.0, 18.0), (W * 0.30, sy, H + 8.0), "ghs_red")
    k.site("handle", (W * 0.30, 0, H + 22.0))
    k.grasp("handle", "top", (W * 0.30, 0, H + 21.0), 16.0, yaw_deg=90.0)
    k.label_flat([("DANGER", 1.0), ("SHARPS", 1.2)], ("biohazard",), size=(W - 16.0, hb * 0.66), pos=(0, -D / 2, hb * 0.5),
                 style={"base": "hazard", "pictograms": "top", "pictogram_share": 0.46})
    k.tag("waste_bin", "biohazard")
    k.mass(mass * 1000.0)


@kind("solvent_cabinet", priority=2, fixed=True)
def solvent_cabinet(k: Kit, *, width=0.60, depth=0.45, height=0.65, text=("FLAMMABLE", "KEEP FIRE AWAY"), shelves=1, mass=38.0):
    """A yellow safety cabinet for flammable liquids with the flame sign on its door (joint `door`)."""
    W, D, H = mm(width, depth, height)
    _cabinet(k, W, D, H, "warning_yellow", list(text), ("flame", "no_flame"),
             {"base": "plain", "bg": "warning_yellow", "fg": "ghs_red", "border": ("ghs_red", 0.03), "pictograms": "top",
              "pictogram_share": 0.5}, shelves, mass, legs=40.0)
    k.tag("flammable", "safety_device")


@kind("carboy", priority=2, vary={"text": ["WASTE SOLVENTS", "WASTE ACIDS", "AQUEOUS WASTE"], "fill": (0.1, 0.8)})
def carboy(k: Kit, *, width=0.23, depth=0.19, height=0.30, text="WASTE SOLVENTS", pictograms=("flame", "health_hazard"),
           tags=("flammable", "toxic"), fill=0.4, substance="waste", funnel=True, mass=0.65):
    """A 10 litre waste container of translucent plastic with a funnel in its neck (zone `funnel`), a handle on top
    and a hazardous-waste label."""
    W, D, H = mm(width, depth, height)
    k.shape(rbox(W, D, H, 26.0, (0, 0, H / 2), 6), "plastic_natural", name="body", alpha=0.72)
    cap_ml = (W - 6) * (D - 6) * (H - 6) / 1000.0 * 0.95
    ml = max(0.0, min(1.0, fill)) * cap_ml
    if ml > 0:
        rg = SUBSTANCES.get(substance, SUBSTANCES["waste"])
        lvl = (H - 8.0) * ml / cap_ml
        k.shape(rbox(W - 8, D - 8, lvl, 22.0, (0, 0, 4.0 + lvl / 2), 6), rg[:3], name="liquid", alpha=0.9)
    k.col("box", (W, D, H), (0, 0, H / 2), name="body_col")
    nx = -W * 0.22
    k.solid("cylinder", (24.0, 26.0), (nx, 0, H + 13.0), "plastic_natural", name="neck")
    top = H + 26.0
    if funnel:
        k.shape(M.revolve([(20.0, top - 4), (24.0, top - 4), (62.0, top + 62), (58.0, top + 62)], 36).moved((nx, 0, 0)), "blue",
                name="funnel", finish="gloss")
        k.ring(24.0, 62.0, top - 4.0, top + 62.0, 3.0, 10, center=(nx, 0.0))
        k.zone("funnel", (nx, 0, top + 40.0), "cylinder", (58.0, 60.0), place=True)
        mouth = top + 62.0
    else:
        k.solid("cylinder", (27.0, 14.0), (nx, 0, top + 3.0), "ghs_red", name="cap")
        mouth = top + 10.0
    hx = W * 0.20
    k.solid("box", (W * 0.36, 22.0, 16.0), (hx, 0, H + 34.0), "plastic_natural", name="handle")
    for sx in (hx - W * 0.15, hx + W * 0.15):
        k.solid("box", (14.0, 20.0, 28.0), (sx, 0, H + 14.0), "plastic_natural")
    k.site("handle", (hx, 0, H + 34.0))
    k.grasp("handle", "top", (hx, 0, H + 33.0), 22.0)
    words = text.split(" ", 1) if " " in text else [text]
    k.label_flat([("HAZARDOUS WASTE", 0.7)] + [(w_, 1.0) for w_ in words], pictograms, size=(W - 36.0, H * 0.56), pos=(0, -D / 2, H * 0.50),
                 style={"base": "hazard", "pictograms": "top", "pictogram_share": 0.40})
    k.site("mouth", (nx, 0, mouth))
    k.site("inside_bottom", (0, 0, 3.0))
    k.vessel = {"capacity_ml": round(cap_ml, 0), "inner_radius": round(min(W, D) / 2 * 1e-3 - 0.003, 6), "inner_depth": (H - 6.0) * 1e-3,
                "bottom_site": "inside_bottom", "mouth_site": "mouth", "closed": not funnel, "shape": "box", "bottom_offset": 0.0,
                "rim_site": "mouth"}
    k.contents = {substance: round(ml, 0)} if ml > 0 else {}
    k.tag("waste_bin", *tags)
    k.mass(mass * 1000.0 + ml)
