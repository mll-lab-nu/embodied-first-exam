"""Cards, notes, signs on stands and stacks of paper."""
from __future__ import annotations

import math

import numpy as np

from .. import labels as L
from .. import mesh as M
from ..catalog import kind
from ..kit import PAPER_FRICTION, Kit, mm, qx, rbox
from robosafebench.core import stream


def _as_lines(text) -> list:
    if isinstance(text, str):
        return [text]
    return [t for t in text]


def _worn(spec) -> dict:
    return {"wear": spec} if spec else {}


@kind("tag_card", minor_contact=True, vary={"text": ["Na", "Fe", "Cu", "Li", "K", "Zn"], "stand": ["tent", "holder"]})
def tag_card(k: Kit, *, text="Na", pictograms=(), style="tag", stand="tent", width=0.085, height=0.055, color="white",
             mass=0.015, wear=None, wear_back=None, printed="both"):
    """A small card with large text: a tent card (`stand="tent"`, printed on both faces), a card in a holder block
    (`holder`), or lying flat (`flat`). Also a note or a sign on a tray: `text` may be several lines. `wear`,
    `wear_back` (0.5.0): the print of the front face (and of the back face) worn (`robosafebench.assets.wear`).
    `printed` (after 0.5.1, the tiers `other_side` of `hazard_hidden`): which faces of a tent or holder card carry the
    print, `both` (the default, the bytes as before), `front` (the -y face; the back is blank card) or `back` (the
    front is blank card). A one-sided card's only print has the site `label` whichever face it is on; `wear` applies to
    it."""
    if printed not in ("both", "front", "back"):
        raise ValueError("printed: both, front or back")
    W, H = mm(width, height)
    lines = _as_lines(text)
    st = style if not isinstance(style, str) else {"base": style}
    if color != "white":
        st = dict(st, bg=color)
    if stand == "tent":
        lean = math.radians(24.0)
        half = H * math.sin(lean)
        zt = H * math.cos(lean)
        for sgn in (-1.0, 1.0):                                   # front face (-y) and back face
            n = (0.0, sgn * math.cos(lean), math.sin(lean))
            up = (0.0, -sgn * math.sin(lean), math.cos(lean))
            c = (0.0, sgn * half / 2.0, zt / 2.0)
            k.vis("box", (W, 0.8, H), c, color, quat=qx(sgn * math.degrees(lean)), name=f"face_{int(sgn > 0)}")
            k.col("box", (W, 1.6, H * 0.98), c, quat=qx(sgn * math.degrees(lean)))
            if printed != "both":                                 # a one-sided card: the other face is blank
                if printed != ("front" if sgn < 0 else "back"):
                    continue
                k.label_flat(lines, pictograms, size=(W - 4.0, H - 4.0), pos=(c[0] + n[0] * 0.5, c[1] + n[1] * 0.5, c[2] + n[2] * 0.5),
                             normal=n, up=up, style=st, name="label", **_worn(wear))
                continue
            k.label_flat(lines, pictograms, size=(W - 4.0, H - 4.0), pos=(c[0] + n[0] * 0.5, c[1] + n[1] * 0.5, c[2] + n[2] * 0.5),
                         normal=n, up=up, style=st, name="label" if sgn < 0 else "label_back",
                         **_worn(wear if sgn < 0 else wear_back))
        k.col("box", (W, 2 * half, 1.2), (0, 0, 0.6), name="rest_col")
    elif stand == "holder":
        k.solid("box", (W * 0.6, 26.0, 12.0), (0, 0, 6.0), "black", name="holder", finish="matte")
        k.solid("box", (W, 1.2, H), (0, 0, 10.0 + H / 2.0), color, name="card")
        for sgn in (-1.0, 1.0):
            if printed != "both":                                 # a one-sided card: the other face is blank
                if printed == ("front" if sgn < 0 else "back"):
                    k.label_flat(lines, pictograms, size=(W - 4.0, H - 4.0), pos=(0, sgn * 0.7, 10.0 + H / 2.0), normal=(0, sgn, 0),
                                 style=st, name="label", **_worn(wear))
                continue
            k.label_flat(lines, pictograms, size=(W - 4.0, H - 4.0), pos=(0, sgn * 0.7, 10.0 + H / 2.0), normal=(0, sgn, 0),
                         style=st, name="label" if sgn < 0 else "label_back", **_worn(wear if sgn < 0 else wear_back))
    elif stand == "flat":
        k.solid("box", (W, H, 1.5), (0, 0, 0.75), color, name="card")
        k.label_flat(lines, pictograms, size=(W - 4.0, H - 4.0), pos=(0, 0, 1.5), normal=(0, 0, 1), style=st, **_worn(wear))
    else:
        raise ValueError("stand: tent, holder or flat")
    if stand != "flat":
        k.grasp("top_edge", "top", (0, 0, (H * math.cos(math.radians(24.0)) if stand == "tent" else 10.0 + H) - 10.0), 8.0)
    k.tag("paper")
    k.mass(mass * 1000.0 + (30.0 if stand == "holder" else 0.0))


@kind("card", minor_contact=True, vary={"color": ["white", "cream", "note_blue"]})
def card(k: Kit, *, lines=("FRAGILE", "HANDLE WITH CARE"), pictograms=(), style="plain", width=0.10, height=0.07,
         thickness=0.0015, color="white", mass=0.006):
    """A printed card lying flat on the table, to be read from the front."""
    W, H, T = mm(width, height, thickness)
    k.solid("box", (W, H, T), (0, 0, T / 2), color, name="card", finish="matte", **PAPER_FRICTION)
    st = style if not isinstance(style, str) else {"base": style}
    if color != "white":
        st = dict(st, bg=color)
    k.label_flat(_as_lines(lines), pictograms, size=(W - 3.0, H - 3.0), pos=(0, 0, T), normal=(0, 0, 1), style=st)
    if H <= 76.0:
        k.grasp("edges", "top", (0, 0, T / 2), H)
    k.tag("paper", "document")
    k.mass(mass * 1000.0)


@kind("sticky_note", minor_contact=True, vary={"color": ["note_yellow", "note_pink", "note_green", "note_blue"]})
def sticky_note(k: Kit, *, lines=("DO NOT", "UNPLUG"), color="note_yellow", size=0.076, mass=0.002):
    """A sticky note lying flat with a few written words."""
    S = mm(size)
    k.solid("box", (S, S, 1.2), (0, 0, 0.6), color, name="note", finish="matte", **PAPER_FRICTION)
    k.label_flat(_as_lines(lines), size=(S - 2.0, S - 2.0), pos=(0, 0, 1.2), normal=(0, 0, 1),
                 style={"base": "note", "bg": color, "pad": 0.10})
    if S <= 76.0:
        k.grasp("edges", "top", (0, 0, 0.6), S)
    k.tag("paper")
    k.mass(mass * 1000.0)


def _page_image(w_px: int, h_px: int, masthead: str, headline: str, seed: int, columns: int = 3) -> np.ndarray:
    """A printed page: masthead, headline, grey bars for the body text and a picture box."""
    img = np.full((h_px, w_px, 3), 236, dtype=np.uint8)
    img[:, :, 2] = 226                                            # newsprint is a little yellow
    head_h = int(h_px * 0.16)
    img[4:4 + head_h, 4:w_px - 4] = L.label_image([masthead], (), (w_px - 8, head_h), {"base": "paper", "bg": (236, 236, 226), "pad": 0.04})
    img[head_h + 6:head_h + 9, 6:w_px - 6] = 30
    hl_h = int(h_px * 0.11)
    img[head_h + 12:head_h + 12 + hl_h, 6:w_px - 6] = L.label_image([headline], (), (w_px - 12, hl_h),
                                                                  {"base": "paper", "bg": (236, 236, 226), "pad": 0.03})
    rng = stream(seed, "page")
    y0 = head_h + 18 + hl_h
    cw = (w_px - 12) // columns
    for c in range(columns):
        x0 = 6 + c * cw
        y = y0
        if c == 1:                                                # a picture
            ph = int(h_px * 0.22)
            img[y:y + ph, x0 + 3:x0 + cw - 6] = 150
            img[y + ph // 3:y + ph, x0 + 3:x0 + cw - 6] = 110
            y += ph + 6
        while y < h_px - 10:
            w = int((cw - 10) * (0.72 + 0.28 * float(rng.random())))
            img[y:y + 2, x0 + 3:x0 + 3 + w] = 95
            y += 5 if int(rng.integers(9)) else 11
    return img


def _edge_image(w_px: int, h_px: int, base=(232, 230, 220)) -> np.ndarray:
    img = np.zeros((h_px, w_px, 3), dtype=np.uint8)
    img[:, :] = base
    img[::3, :] = (base[0] - 60, base[1] - 60, base[2] - 60)
    return img


def _stack(k: Kit, W, D, H, top_img, color, mass):
    k.shape(M.box((W, D, H), (0, 0, H / 2)), color, name="stack", finish="matte")
    k.col("box", (W, D, H), (0, 0, H / 2), name="stack_col")
    k.decal(top_img, size=(W - 0.4, D - 0.4), pos=(0, 0, H), normal=(0, 0, 1), name="top_sheet")
    edge = _edge_image(64, max(8, int(H * 3)))
    for normal, size, pos in (((0, -1, 0), (W, H), (0, -D / 2, H / 2)), ((0, 1, 0), (W, H), (0, D / 2, H / 2)),
                              ((1, 0, 0), (D, H), (W / 2, 0, H / 2)), ((-1, 0, 0), (D, H), (-W / 2, 0, H / 2))):
        k.decal(edge, size=size, pos=pos, normal=normal)
    k.mass(mass * 1000.0)


@kind("paper_stack", vary={"height": (0.02, 0.06), "masthead": ["THE DAILY NEWS", "MORNING POST", "CITY GAZETTE"]})
def paper_stack(k: Kit, *, width=0.30, depth=0.22, height=0.04, masthead="THE DAILY NEWS", headline="MARKET OPENS TODAY",
                seed_page=1, mass=None):
    """A stack of folded newspapers."""
    W, D, H = mm(width, depth, height)
    img = _page_image(600, int(600 * D / W), masthead, headline, int(seed_page))
    _stack(k, W, D, H, img, (0.90, 0.89, 0.84), mass if mass else 0.75 * (W * D * H) / 1e6 * 1.0)
    k.zone("above", (0, 0, H + 40.0), "box", (W, D, 80.0))
    k.tag("paper", "flammable")


@kind("document", priority=2, vary={"stamp": ["", "CONFIDENTIAL", "DRAFT", "URGENT"], "title": ["CONTRACT", "INVOICE", "LAB REPORT", "PAYSLIP"]})
def document(k: Kit, *, title="CONTRACT", lines=("Between A. Smith", "and B. Jones", "Signed: ________"), stamp="", size="a5",
             mass=None):
    """A printed sheet lying flat (`size`: a5 or a4), with a title, a few lines and an optional red stamp."""
    W, H = {"a5": (148.0, 210.0), "a4": (210.0, 297.0)}[size]
    k.solid("box", (W, H, 1.2), (0, 0, 0.6), "white", name="sheet", finish="matte", **PAPER_FRICTION)
    ls = [(title, 1.3)] + [{"text": t, "h": 0.8, "bold": False, "align": "left"} for t in lines]
    if stamp:
        ls.append({"text": stamp, "h": 1.1, "fg": "ghs_red"})
    k.label_flat(ls, size=(W - 6.0, H * 0.62), pos=(0, H * 0.16, 1.2), normal=(0, 0, 1), style={"base": "paper", "bg": "white", "pad": 0.07})
    for i in range(4):                                            # the rest of the page
        k.vis("box", (W * (0.78 - 0.07 * (i % 2)), 1.6, 0.3), (-W * (0.035 * (i % 2)), -H * 0.22 - 9.0 * i, 1.3), (0.55, 0.55, 0.55))
    k.tag("document", "paper", "flammable")
    k.extra["confidential"] = stamp.upper() == "CONFIDENTIAL"
    k.mass(mass * 1000.0 if mass else (0.0025 if size == "a5" else 0.005) * 1000.0)


@kind("passport", priority=2, vary={"color": ["navy", (0.45, 0.08, 0.12), (0.05, 0.30, 0.18)]})
def passport(k: Kit, *, color="navy", country="REPUBLIC OF EXAMPLE", mass=0.035):
    """A passport booklet lying flat: dark cover, gold lettering, no real state's emblem."""
    W, H, T = 88.0, 125.0, 4.0
    gold = (0.86, 0.72, 0.36)
    k.shape(rbox(W, H, T, 5.0, (0, 0, T / 2), 4), color, name="cover", finish="satin")
    k.vis("box", (W - 2.0, H - 2.0, T - 1.6), (0.8, 0, T / 2), "paper", name="pages")
    k.col("box", (W, H, T), (0, 0, T / 2), name="cover_col", **PAPER_FRICTION)
    bg = tuple(int(v * 255) for v in color) if not isinstance(color, str) else color
    k.label_flat([{"text": country, "h": 0.5, "fine": True}, {"text": "PASSPORT", "h": 1.0}], size=(W - 12.0, H * 0.42),
                 pos=(0, H * 0.12, T), normal=(0, 0, 1), style={"base": "dark", "bg": bg, "fg": tuple(int(v * 255) for v in gold), "pad": 0.05})
    k.vis("cylinder", (11.0, 0.4), (0, -H * 0.24, T + 0.1), gold, name="emblem_ring", finish="metal")
    k.vis("cylinder", (8.0, 0.5), (0, -H * 0.24, T + 0.12), color, name="emblem_fill")
    k.tag("document", "paper")
    k.mass(mass * 1000.0)


@kind("flyer_stack", priority=2, vary={"headline": ["SALE", "OPEN DAY", "CONCERT"], "color": ["yellow", "pink", "sky", "lime"]})
def flyer_stack(k: Kit, *, headline="SALE", lines=("50% OFF", "THIS WEEK ONLY"), color="yellow", height=0.025, mass=None):
    """A stack of printed flyers."""
    W, D, H = 148.0, 210.0, mm(height)
    k.shape(M.box((W, D, H), (0, 0, H / 2)), "white", name="stack", finish="matte")
    k.col("box", (W, D, H), (0, 0, H / 2), name="stack_col")
    edge = _edge_image(64, max(8, int(H * 3)), base=(238, 238, 232))
    for normal, size, pos in (((0, -1, 0), (W, H), (0, -D / 2, H / 2)), ((0, 1, 0), (W, H), (0, D / 2, H / 2)),
                              ((1, 0, 0), (D, H), (W / 2, 0, H / 2)), ((-1, 0, 0), (D, H), (-W / 2, 0, H / 2))):
        k.decal(edge, size=size, pos=pos, normal=normal)
    k.label_flat([(headline, 1.6)] + [(t, 0.8) for t in lines], size=(W - 1.0, D - 1.0), pos=(0, 0, H), normal=(0, 0, 1),
                 style={"base": "product", "bg": color, "fg": "black", "header": ("ghs_red", "white")})
    k.zone("above", (0, 0, H + 40.0), "box", (W, D, 80.0))
    k.tag("paper", "flammable")
    k.mass(mass * 1000.0 if mass else 0.8 * W * D * H / 1e6 * 1000.0)
