"""Things with a plug or a battery."""
from __future__ import annotations

import math

import numpy as np

from .. import labels as L
from .. import mesh as M
from ..catalog import kind
from ..kit import PAPER_FRICTION, Kit, mm, qx, qy, rbox, rot_x, rot_y
from ..model import Joint


@kind("power_bank", vary={"capacity": ["10000 mAh", "20000 mAh", "26800 mAh"], "color": ["black", "dark_grey", "navy"]})
def power_bank(k: Kit, *, length=0.15, width=0.065, thickness=0.024, color="black", capacity="20000 mAh", energy="74 Wh",
               top_label=True, mass=0.36, ports=True, lights=True):
    """A lithium power bank: a flat brick with its capacity printed on the long side facing the front and on top,
    two sockets on the +x end and four charge lights. Since 0.5.0, `ports=False` and `lights=False` leave the sockets
    and the charge lights off (with `top_label=False`, a plain black brick but for the print on its long side)."""
    Ln, Wd, T = mm(length, width, thickness)
    k.shape(rbox(Ln, Wd, T, 9.0, (0, 0, T / 2), 5), color, name="case", finish="satin")
    k.col("box", (Ln, Wd, T), (0, 0, T / 2), name="case_col")
    dark = {"base": "dark", "bg": (30, 30, 34), "pad": 0.06}
    k.label_flat([capacity], ("battery",), size=(84.0, T - 5.0), pos=(-8.0, -Wd / 2, T / 2), style=dark)
    if top_label:
        k.label_flat([("POWER BANK", 1.0), (capacity, 1.2), {"text": f"Li-ion  {energy}", "h": 0.6, "fine": True}],
                     size=(92.0, 48.0), pos=(-18.0, 0, T), normal=(0, 0, 1), style=dark, name="label_top")
    for i, (y, w, h, c) in enumerate(((-14.0, 13.0, 6.0, (0.15, 0.3, 0.75)), (12.0, 9.0, 3.5, (0.05, 0.05, 0.05))) if ports else ()):
        k.vis("box", (1.0, w + 2.5, h + 2.5), (Ln / 2 + 0.1, y, T / 2), "steel", name=f"port_{i}_frame")
        k.vis("box", (1.0, w, h), (Ln / 2 + 0.4, y, T / 2), c, name=f"port_{i}")
    for i in range(4 if lights else 0):
        k.vis("cylinder", (2.0, 1.0), (Ln / 2 - 14.0 - 8.0 * i, Wd / 2 - 9.0, T), (0.3, 0.75, 1.0) if i < 3 else (0.12, 0.2, 0.3),
              name=f"led_{i}", finish="glow")
    k.site("port", (Ln / 2, 0, T / 2), quat=qy(90))
    k.grasp("body", "top", (0, 0, T * 0.55), Wd)
    k.tag("battery", "electrical")
    k.mass(mass * 1000.0)


@kind("power_strip", vary={"sockets": [4, 5, 6], "color": ["white", "black"]})
def power_strip(k: Kit, *, sockets=4, color="white", state="on", cord=True, mass=0.45, rating=None, cord_end=None, cord_yaw=0.0, cord_terminal=None):
    """A power strip: sockets along the top (zones `socket_0` ...), a lit rocker switch at the -x end and a cord.
    Looks `on` (switch lit) and `off`. `rating` (0.5.4; default None, which builds the same model as before): lines
    printed on a plate on its front face (-y), the strip's rating plate ("MAX 2300 W", "10 A 230 V"); site `rating`."""
    n = int(sockets)
    pitch, D, H = 52.0, 58.0, 40.0
    W = n * pitch + 62.0
    k.shape(rbox(W, D, H, 10.0, (0, 0, H / 2), 5), color, name="case", finish="gloss")
    k.col("box", (W, D, H), (0, 0, H / 2), name="case_col")
    face = (0.86, 0.86, 0.84) if color != "white" else (0.80, 0.80, 0.78)
    for i in range(n):
        x = -W / 2 + 62.0 + pitch * (i + 0.5) - 6.0
        k.vis("cylinder", (20.0, 1.0), (x, 0, H), face, name=f"socket_{i}_face")
        for sy in (-9.5, 9.5):
            k.vis("cylinder", (2.6, 1.4), (x, sy, H), "black", name=None)
        k.vis("box", (5.0, 2.2, 1.4), (x + 9.0, 0, H), "black")
        k.zone(f"socket_{i}", (x, 0, H + 15.0), "cylinder", (20.0, 30.0))
    k.button("switch", (-W / 2 + 28.0, 0, H), axis=(0, 0, 1), size=(24.0, 15.0), color=(0.5, 0.06, 0.05), kind="switch",
             finish="glow", proud=3.5, travel=3.0)
    k.look("on", "switch_cap", (1.0, 0.22, 0.12))
    k.look("off", "switch_cap", (0.45, 0.05, 0.05))
    if cord:
        k.cord((-W / 2, 0, H / 2), cord_end if cord_end is not None else (-W / 2 - 190.0, 120.0, 3.0),
               plug="socket" if cord == "socket" else "grommet", socket_yaw=cord_yaw, socket_terminal=cord_terminal)
    if rating:                                                    # the rating plate along the front face, under the sockets
        k.label_flat(list(rating), size=(min(W - 70.0, 170.0), H - 8.0), pos=(28.0, -D / 2, H / 2), name="rating",
                     style={"base": "paper", "bg": "white", "fg": "black", "pad": 0.06, "border": ((0, 0, 0), 0.04)})
    k.set_look("on" if state == "on" else "off")
    k.tag("electrical")
    k.mass(mass * 1000.0)


@kind("plug_adapter", vary={"color": ["white", "black"]})
def plug_adapter(k: Kit, *, size=0.046, thickness=0.028, color="white", text=("5V 2A",), pose="lying", mass=0.065,
                 top_text=None):
    """A plug-in charger. `pose="lying"`: on its back, prongs up. `pose="standing"`: prongs down, their ends at the
    origin, as it is held to be plugged into a socket that faces up; it stands like that on a `plug_stand`
    (`at: stand/seat`). Site `tip`: the ends of the prongs. `top_text` (0.5.4; default None, which builds the same
    model as before; standing pose): lines printed on the face away from the prongs, a cord-end tag that says whose
    plug it is and what it draws ("MITRE SAW", "1200 W"); site `tag`."""
    S, T = mm(size, thickness)
    PL = 17.0                                                    # length of the prongs
    if pose not in ("lying", "standing"):
        raise ValueError("pose: lying or standing")
    down = pose == "standing"
    z0 = PL if down else 0.0                                     # the underside of the case
    k.shape(rbox(S, S, T, 7.0, (0, 0, z0 + T / 2), 5), color, name="case", finish="gloss")
    k.col("box", (S, S, T), (0, 0, z0 + T / 2), name="case_col")
    for i, sx in enumerate((-6.35, 6.35)):
        k.solid("box", (1.5, 6.3, PL), (sx, 0, PL / 2 if down else T + PL / 2), "steel", name=f"prong_{i}", finish="metal")
    k.vis("box", (13.0, 1.0, 6.0), (0, -S / 2 - 0.1, z0 + T * (0.65 if down else 0.35)), "black", name="usb_port")
    k.label_flat(list(text), size=(S - 8.0, T * 0.46), pos=(0, -S / 2, z0 + T * (0.27 if down else 0.73)),
                 style={"base": "paper", "bg": color, "fg": "black" if color == "white" else "white", "pad": 0.03})
    if top_text:
        if not down:
            raise ValueError("top_text: on the standing pose only")
        k.label_flat(list(top_text), size=(S - 6.0, S - 6.0), pos=(0, 0, z0 + T), normal=(0, 0, 1), up=(0, 1, 0), name="tag",
                     style={"base": "paper", "bg": "white", "fg": "black", "pad": 0.05})
    k.site("tip", (0, 0, 0.0 if down else T + PL))
    k.grasp("body", "top", (0, 0, z0 + T * 0.6), S)
    # what goes into a socket (hazard.insert.Plug): the prongs, which way they point and the line they stand on
    k.extra["plug"] = {"geoms": ["prong_0", "prong_1"], "tip": "tip", "length": PL * 1e-3,
                       "into": [0.0, 0.0, -1.0 if down else 1.0], "row": [1.0, 0.0, 0.0]}
    k.tag("electrical", "metal", "conductive")
    k.mass(mass * 1000.0)


@kind("plug_stand", priority=2, vary={"color": ["grey", "cream", "black"]})
def plug_stand(k: Kit, *, width=0.040, depth=0.026, height=0.020, color="grey", mass=0.08):
    """A small block on which a plug-in charger is kept, prongs down in its slot. Site `seat`: where the ends of the
    prongs are when the charger sits on it (`{"kind": "plug_adapter", "params": {"pose": "standing"}, "at": "stand/seat"}`).
    It is narrower than the charger from front to back, so that fingers closing on the charger pass beside it."""
    W, D, H = mm(width, depth, height)
    k.holed_block(W, D, 0.0, H, [(0.0, 11.0, 5.0)], floor=H - 18.0, color=color, finish="matte")
    k.site("seat", (0, 0, H - 17.0))
    k.tag("storage")
    k.mass(mass * 1000.0)


GLOW_HOT = (1.0, 0.33, 0.06, 1.0)
ELEMENT_COLD = (0.16, 0.15, 0.15, 1.0)


def keys_image(cols: int, rows: int, w_px: int, h_px: int, bg=(28, 28, 32), key=(62, 62, 68)) -> np.ndarray:
    """A keyboard seen from above: a grid of keys with a wide space bar in the last row."""
    img = np.zeros((h_px, w_px, 3), dtype=np.uint8)
    img[:, :] = bg
    kw, kh = w_px / cols, h_px / rows
    for r in range(rows):
        for c in range(cols):
            if r == rows - 1 and cols * 0.28 <= c < cols * 0.68:
                continue
            x0, y0 = int(c * kw + kw * 0.10), int(r * kh + kh * 0.10)
            img[y0:int((r + 1) * kh - kh * 0.10), x0:int((c + 1) * kw - kw * 0.10)] = key
    y0 = int((rows - 1) * kh + kh * 0.10)
    img[y0:int(rows * kh - kh * 0.10), int(cols * 0.28 * kw + 2):int(cols * 0.68 * kw - 2)] = key
    return img


def screen_image(lines, w_px: int, h_px: int, title: str = "") -> tuple[np.ndarray, float]:
    """A lit screen: a title bar and a few lines of text. Returns the image and the cap height of its smallest line
    in pixels."""
    spec = [{"text": t, "h": 1.0, "align": "left"} for t in lines] or [" "]
    style = {"base": "screen", "bg": (236, 240, 244), "fg": (20, 24, 30), "pad": 0.09}
    img = L.label_image(spec, (), (w_px, h_px), style)
    cap = L.layout(spec, (), (w_px, h_px), style)["min_cap_px"]
    bar = max(6, h_px // 9)
    img[:bar] = (40, 90, 170)
    if title:
        t = L.label_image([title], (), (w_px // 2, bar), {"base": "screen", "bg": (40, 90, 170), "fg": "white", "pad": 0.1})
        img[:bar, :w_px // 2] = t
    return img, cap


@kind("space_heater", priority=2, vary={"color": ["white", "black", "light_grey"]})
def space_heater(k: Kit, *, width=0.24, depth=0.13, height=0.32, color="white", state="off", cord=True, warning_label=True, mass=2.2,
                 glow=True, sites=False, cord_end=None, cord_yaw=0.0, cord_terminal=None):
    """A fan heater: glowing bars behind a grille at the front, a switch and a lamp on top, a carrying handle.
    Looks `on` and `off`. Zone `front`: the 30 cm in front of the grille. `warning_label=False` leaves the notice
    CAUTION / DO NOT COVER off its front (as on `hot_plate`). Since 0.5.0: `glow=False`, a ceramic fan heater whose
    element does not glow: it looks the same on and off but for the lamp on top; `sites=True` adds the sites `lamp`
    (just above the lamp) and `grille` (the middle of the grille, among its bars); `cord_end` (mm, in the heater's
    frame): where its cord ends, for a heater turned on the table."""
    W, D, H = mm(width, depth, height)
    k.shape(rbox(W, D, H, 16.0, (0, 0, H / 2), 5), color, name="housing", finish="satin")
    k.col("box", (W, D, H), (0, 0, H / 2), name="housing_col")
    gw, gh = W - 44.0, H * 0.62
    gz = H * 0.46
    k.vis("box", (gw, 2.0, gh), (0, -D / 2 - 0.2, gz), (0.07, 0.07, 0.08), name="grille_back", finish="matte")
    for i in range(5):
        z = gz - gh / 2 + gh * (i + 0.5) / 5.0
        k.vis("box", (gw - 16.0, 2.0, 7.0), (0, -D / 2 - 1.4, z), ELEMENT_COLD, name=f"element_{i}", finish="glow")
        k.look("on", f"element_{i}", GLOW_HOT if glow else ELEMENT_COLD)
        k.look("off", f"element_{i}", ELEMENT_COLD)
    for i in range(9):
        x = -gw / 2 + gw * (i + 0.5) / 9.0
        k.vis("box", (2.0, 1.6, gh), (x, -D / 2 - 3.0, gz), (0.55, 0.56, 0.58), name=None, finish="metal")
    k.button("power", (W / 2 - 40.0, -8.0, H), axis=(0, 0, 1), size=(26.0, 18.0), color="red", kind="switch")
    # (with `glow=False` the lamp is all that tells, and it is drawn larger: 12 mm across instead of 7, as on `hot_plate`)
    k.lamp("lamp", (W / 2 - 78.0, -8.0, H), axis=(0, 0, 1), radius=3.5 if glow else 6.0, on=(1.0, 0.3, 0.1), off=(0.28, 0.07, 0.05))
    if sites:
        k.site("lamp", (W / 2 - 78.0, -8.0, H + 2.0))
        k.site("grille", (0, -D / 2 - 2.0, gz))
    k.solid("box", (110.0, 18.0, 14.0), (-34.0, D / 2 - 26.0, H + 34.0), "dark_grey", name="handle", finish="matte")
    for sx in (-80.0, 12.0):
        k.solid("box", (10.0, 14.0, 30.0), (sx, D / 2 - 26.0, H + 14.0), "dark_grey", finish="matte")
    k.site("handle", (-34.0, D / 2 - 26.0, H + 34.0))
    k.grasp("handle", "top", (-34.0, D / 2 - 26.0, H + 33.0), 18.0)
    k.zone("front", (0, -D / 2 - 150.0, H / 2), "box", (W + 100.0, 300.0, H))
    if warning_label:
        k.label_flat([("CAUTION", 1.0), ("DO NOT COVER", 1.0)], ("hot_surface",), size=(100.0, 34.0), pos=(0, -D / 2, H * 0.88),
                     style="warning_sign")
    if cord:
        k.cord((W / 2 - 40.0, D / 2, 16.0), tuple(cord_end) if cord_end is not None else None,
               plug="socket" if cord == "socket" else "grommet", socket_yaw=cord_yaw, socket_terminal=cord_terminal)
    k.set_look("on" if state == "on" else "off")
    k.tag("electrical", "hot_surface")
    k.mass(mass * 1000.0)


@kind("towel_warmer", priority=2, vary={"color": ["white", "light_grey", "silver"]})
def towel_warmer(k: Kit, *, width=0.24, depth=0.13, height=0.34, color="white", state="on", cord=True, mass=1.8, cord_end=None, cord_yaw=0.0, cord_terminal=None):
    """A free-standing towel warmer: a low electric heater that is made to have towels hung over it. Two end frames
    on feet, three rails across the top and two lower ones, a plate at the front with its name, a switch and a lamp.
    Looks `on` (lamp lit) and `off`; nothing on it glows. Zone `rails`: the top rails, an open place as the rails of
    the drying rack are (a towel put there comes to rest astride a rail)."""
    W, D, H = mm(width, depth, height)
    r = 6.0
    ys = (-D * 0.30, 0.0, D * 0.30)
    for sgn, nm in ((-1.0, "left"), (1.0, "right")):
        x = sgn * (W / 2 - r)
        k.tube([(x, -D / 2 + r, r), (x, ys[0], H - r), (x, ys[2], H - r), (x, D / 2 - r, r)], r, color, solid=True, name=f"frame_{nm}", finish="gloss")
        k.col("box", (14.0, D, 8.0), (x, 0, 4.0), name=f"foot_{nm}")
        k.vis("box", (12.0, D - 16.0, 7.0), (x, 0, 4.0), "dark_grey", finish="matte")
    for i, y in enumerate(ys):
        k.tube([(-W / 2 + r, y, H - r), (W / 2 - r, y, H - r)], 4.5, color, solid=True, name=f"rail_{i}", finish="gloss")
        k.site(f"rail_{i}", (0, y, H - r + 4.5))
    for i, z in enumerate((H * 0.74, H * 0.60)):                  # two lower rails, under the middle one
        k.tube([(-W / 2 + r, 0, z), (W / 2 - r, 0, z)], 4.0, color, solid=True, name=f"rail_low_{i}", finish="gloss")
    # the plate at the front, on the front legs: the name, the switch and the lamp
    pz, ph = H * 0.30, 78.0
    py = -D / 2 + r + (ys[0] + D / 2 - r) * (pz - r) / (H - 2 * r) - r - 1.5
    k.solid("box", (W - 4 * r, 3.0, ph), (0, py, pz), color, name="plate", finish="satin")
    k.label_flat([("TOWEL", 1.0), ("WARMER", 1.0)], size=(W - 4 * r - 70.0, ph - 14.0), pos=(-30.0, py - 1.5, pz),
                 style={"base": "plain", "bg": "white", "fg": "navy", "pad": 0.06})
    k.button("power", (W / 2 - 2 * r - 22.0, py - 1.5, pz + 14.0), size=(22.0, 15.0), color="red", kind="switch")
    k.lamp("lamp", (W / 2 - 2 * r - 22.0, py - 1.9, pz - 16.0), radius=5.0, on=(1.0, 0.35, 0.1), off=(0.28, 0.08, 0.05))
    k.zone("rails", (0, 0, H - r + 4.5 + 30.0), "box", (W, D * 0.7, 60.0), place=True, open=True)
    if cord:
        k.cord((W / 2 - 40.0, D / 2, 16.0), cord_end, plug="socket" if cord == "socket" else "grommet", socket_yaw=cord_yaw, socket_terminal=cord_terminal)
    k.set_look("on" if state == "on" else "off")
    k.tag("electrical")
    k.mass(mass * 1000.0)


@kind("laptop", priority=2, vary={"color": ["silver", "dark_grey", "black"]})
def laptop(k: Kit, *, width=0.32, depth=0.22, color="silver", state="on", lines=("QUARTERLY REPORT", "Revenue  +4 %", "Costs    -2 %"),
           title="report.doc", mass=1.5):
    """An open laptop: keyboard deck and a screen leaning back. Looks `on` (screen lit with text) and `off`.
    Zone `keyboard`: the space just above the keys."""
    W, D = mm(width, depth)
    T = 16.0
    k.shape(rbox(W, D, T, 10.0, (0, 0, T / 2), 4), color, name="deck", finish="metal")
    k.col("box", (W, D, T), (0, 0, T / 2), name="deck_col")
    k.decal(keys_image(14, 5, 560, 220), size=(W - 36.0, D * 0.46), pos=(0, D * 0.14, T), normal=(0, 0, 1), name="keys")
    k.vis("box", (W * 0.30, D * 0.26, 0.5), (0, -D * 0.30, T + 0.1), (0.45, 0.46, 0.48), name="touchpad")
    lean = 18.0
    sh = D * 0.96
    c, s_ = math.cos(math.radians(lean)), math.sin(math.radians(lean))
    centre = (0.0, D / 2 - 4.0 + s_ * sh / 2.0, T + c * sh / 2.0)
    k.solid("box", (W, 6.0, sh), centre, color, quat=qx(-lean), name="lid", finish="metal")
    n = (0.0, -c, s_)
    up = (0.0, s_, c)
    img, cap = screen_image(list(lines), 640, int(640 * (sh - 20.0) / (W - 20.0)), title)
    k.label_flat(list(lines), size=(W - 20.0, sh - 20.0), pos=(centre[0] + n[0] * 3.2, centre[1] + n[1] * 3.2, centre[2] + n[2] * 3.2),
                 normal=n, up=up, image=img, geom="screen", glow=0.85, name="screen", cap_mm=cap * (W - 20.0) / 640.0)
    k.look("on", "screen", (1, 1, 1, 1))
    k.look("off", "screen", (0.03, 0.03, 0.04, 1))
    k.zone("keyboard", (0, D * 0.06, T + 15.0), "box", (W, D * 0.9, 30.0), place=True)
    k.set_look("on" if state == "on" else "off")
    k.tag("electrical", "battery")
    k.mass(mass * 1000.0)


def notice_image(lines, w_px: int, h_px: int, title: str, cap_px: float) -> np.ndarray:
    """A notification filling a screen: a title bar and lines of one fixed type size (capitals `cap_px` tall), left
    aligned, so that two notifications with as many lines differ only in their words."""
    return _notice_artwork(lines, w_px, h_px, title, cap_px)[0]


def _notice_artwork(lines, w_px: int, h_px: int, title: str, cap_px: float):
    """Draw the original artwork and retain its author's body-text layout, without recognising pixels."""
    from PIL import Image, ImageDraw

    bg, fg, bar_bg = (236, 240, 244), (20, 24, 30), (40, 90, 170)
    im = Image.new("RGB", (w_px, h_px), bg)
    d = ImageDraw.Draw(im)
    font = L._font(True, max(4, int(round(cap_px / L.CAP_RATIO))))
    pitch = cap_px * 1.5
    bar = int(round(pitch * 1.1))
    d.rectangle([0, 0, w_px - 1, bar], fill=bar_bg)
    x0 = int(round(cap_px * 0.6))
    ascent = font.getmetrics()[0]
    regions = []
    for i, text in enumerate([title] + list(lines)):
        cy = bar / 2.0 if i == 0 else bar + pitch * (i - 0.5) + cap_px * 0.35
        origin = (x0, int(round(cy + cap_px / 2.0 - ascent)))
        d.text(origin, text, font=font, fill=(255, 255, 255) if i == 0 else fg)
        box = font.getbbox(text)
        right = x0 + box[2]
        if right > w_px - x0 / 2 or cy + cap_px > h_px:
            raise ValueError(f"notice line {text!r} does not fit the screen at {cap_px:.1f} px capitals")
        if i and text.strip():
            y0, y1 = (origin[1] + box[1]) / h_px, (origin[1] + box[3]) / h_px
            cells = [[(x0 + float(font.getlength(text[:j]))) / w_px, y0,
                      (x0 + float(font.getlength(text[:j + 1]))) / w_px, y1]
                     for j, ch in enumerate(text) if not ch.isspace()]
            # The generic title bar is not the notification. Its body is one complete authored message,
            # so a readable title or isolated body fragment cannot stand in for all of the message's words.
            regions.append(dict(text=text, uv_box=[(x0 + box[0]) / w_px, y0, right / w_px, y1],
                                cap_px=cap_px, cap_axis="up", text_group="notice_body",
                                native_ink=dict(glyph_cells=cells, foreground=list(fg), background=list(bg))))
    return np.asarray(im).copy(), regions


@kind("tablet", priority=2, vary={"color": ["black", "silver"]})
def tablet(k: Kit, *, width=0.25, depth=0.175, color="black", state="on", lines=("MESSAGE", "Meet at 3 pm"), title="", mass=0.48,
           stand_deg=0.0, notice=(), notice_title="", notice_cap_mm=18.0):
    """A tablet lying on the table, its screen showing the given lines. Looks `on` and `off`.

    Added after 0.5.1 (e_tablet_popup): `stand_deg` > 0 stands it on a small stand, its screen tilted back by that
    angle from the table and facing -y (the front); `notice` (lines) adds a notification that covers the screen in
    the look `notice` (in `on` and `off` it is hidden, as the microwave switches its display): a title bar with
    `notice_title` and every line with capitals `notice_cap_mm` tall. Meta `screen_normal`: the screen's normal in the
    object frame. Without these parameters the asset is as before."""
    W, D = mm(width, depth)
    T = 8.0
    k.shape(rbox(W, D, T, 12.0, (0, 0, T / 2), 5), color, name="case", finish="gloss")
    k.col("box", (W, D, T), (0, 0, T / 2), name="case_col")
    img, cap = screen_image(list(lines), 600, int(600 * (D - 24.0) / (W - 24.0)), title)
    k.label_flat(list(lines), size=(W - 24.0, D - 24.0), pos=(0, 0, T), normal=(0, 0, 1), image=img, geom="screen", glow=0.85,
                 name="screen", cap_mm=cap * (W - 24.0) / 600.0)
    if notice:
        sw, sh = W - 24.0, D - 24.0
        px = 4.0                                         # texture pixels per mm
        nimg, regions = _notice_artwork(list(notice), int(round(sw * px)), int(round(sh * px)), notice_title, notice_cap_mm * px)
        for region in regions:
            region["cap_height"] = region.pop("cap_px") / nimg.shape[1] * sw * 1e-3
        k.label_flat([notice_title] + list(notice), size=(sw, sh), pos=(0, 0, T), normal=(0, 0, 1), image=nimg, geom="notice",
                     glow=0.85, name="notice", thick=0.7, cap_mm=notice_cap_mm, text_regions=regions)
    k.look("on", "screen", (1, 1, 1, 1))
    k.look("off", "screen", (0.03, 0.03, 0.04, 1))
    if notice:
        k.look("on", "notice", (1, 1, 1, 0))
        k.look("off", "notice", (1, 1, 1, 0))
        k.look("notice", "screen", (1, 1, 1, 1))
        k.look("notice", "notice", (1, 1, 1, 1))
    if stand_deg:
        # tilt about the front lower edge, then put the origin at the middle of the footprint (the stand included)
        a = math.radians(float(stand_deg))
        k.reframe(rot_x(float(stand_deg)), origin=(0.0, -D / 2.0, 0.0))
        back = D * math.cos(a)                           # how far back the tilted case reaches
        leg = 14.0                                       # the stand's leg behind the case
        foot = back + leg
        k.reframe(np.eye(3), origin=(0.0, foot / 2.0 - 6.0, 0.0))
        y0 = -foot / 2.0 + 6.0                           # the case's front lower edge
        # a lip in front of the lower edge and a leg under the upper part, dark grey, colliding
        k.solid("box", (W * 0.7, 10.0, 12.0), (0.0, y0 - 5.0, 6.0), "dark_grey", name="stand_lip")
        zt = (D * 0.75) * math.sin(a)                    # the underside of the case three quarters up
        yl = y0 + (D * 0.75) * math.cos(a) + T * math.sin(a)
        k.solid("box", (W * 0.7, 6.0, zt), (0.0, yl + 3.0, zt / 2.0), "dark_grey", name="stand_leg")
        k.solid("box", (W * 0.7, yl + 6.0 - y0, 6.0), (0.0, (y0 + yl + 6.0) / 2.0, 3.0), "dark_grey", name="stand_rail")
        k.extra["screen_normal"] = [0.0, round(-math.sin(a), 6), round(math.cos(a), 6)]
    k.set_look("notice" if (notice and state == "notice") else "on" if state == "on" else "off")
    k.tag("electrical", "battery")
    k.mass(mass * 1000.0)


@kind("keyboard", priority=2, vary={"color": ["black", "light_grey"]})
def keyboard(k: Kit, *, width=0.44, depth=0.135, color="black", mass=0.6):
    """A computer keyboard. Zone `keys`: the space just above the keys."""
    W, D = mm(width, depth)
    k.shape(rbox(W, D, 18.0, 8.0, (0, 0, 9.0), 4), color, name="case", finish="satin")
    k.col("box", (W, D, 18.0), (0, 0, 9.0), name="case_col")
    light = color != "black"
    img = keys_image(18, 5, 720, 200, bg=(150, 150, 152) if light else (20, 20, 22), key=(225, 225, 222) if light else (58, 58, 62))
    k.decal(img, size=(W - 16.0, D - 16.0), pos=(0, 0, 18.0), normal=(0, 0, 1), name="keys")
    k.vis("box", (W - 16.0, D - 16.0, 3.0), (0, 0, 19.0), (0.5, 0.5, 0.5), alpha=0.0, name="key_height")
    k.zone("keys", (0, 0, 18.0 + 15.0), "box", (W, D, 30.0), place=True)
    k.tube([(0, D / 2, 9.0), (10, D / 2 + 60, 3.0), (60, D / 2 + 120, 3.0)], 2.5, "black", decor=True)
    k.tag("electrical")
    k.mass(mass * 1000.0)


@kind("iron", priority=2, vary={"color": ["blue", "purple", "teal", "red"]})
def iron(k: Kit, *, length=0.26, width=0.115, color="blue", state="off", cord=True, mass=1.3):
    """A clothes iron lying on its sole plate, its point towards +x. Looks `on` (lamp lit) and `off`. Zone `sole`:
    the plate and what it rests on."""
    Ln, Wd = mm(length, width)
    a, b = Ln / 2.0, Wd / 2.0
    sole = np.array([[-a, -b * 0.82], [-a + 14, -b], [a * 0.25, -b], [a * 0.72, -b * 0.55], [a, 0.0], [a * 0.72, b * 0.55],
                     [a * 0.25, b], [-a + 14, b], [-a, b * 0.82]])
    k.shape(M.extrude(sole, 0.0, 6.0), "steel", name="sole_plate", finish="metal")
    k.shape(M.extrude(sole * 0.97, 6.0, 34.0), color, name="body", finish="gloss")
    k.shape(M.extrude(sole * np.array([0.80, 0.72]) + np.array([-a * 0.10, 0.0]), 34.0, 58.0), color, name="tank", finish="gloss", alpha=0.9)
    k.tube([(-a * 0.72, 0, 56.0), (-a * 0.70, 0, 108.0), (a * 0.30, 0, 112.0), (a * 0.52, 0, 60.0)], 12.0, "dark_grey", finish="matte",
           name="handle")
    k.col("box", (Ln * 0.72, Wd, 34.0), (-a * 0.28, 0, 17.0), name="body_col")
    k.col("box", (Ln * 0.28, Wd * 0.5, 34.0), (a * 0.70, 0, 17.0), name="nose_col")
    k.col("box", (Ln * 0.62, Wd * 0.62, 24.0), (-a * 0.14, 0, 46.0), name="tank_col")
    k.col("box", (Ln * 0.48, 24.0, 22.0), (-a * 0.20, 0, 110.0), name="handle_col")
    k.col("box", (22.0, 22.0, 50.0), (-a * 0.71, 0, 82.0))
    k.col("box", (22.0, 22.0, 50.0), (a * 0.42, 0, 84.0))
    k.vis("cylinder", (16.0, 8.0), (a * 0.10, 0, 60.0), "white", name="dial")
    k.button("power", (-a * 0.42, 0, 58.0), axis=(0, 0, 1), size=(18.0, 14.0), color="red", kind="switch", travel=3.0)
    k.lamp("lamp", (a * 0.42, 0, 44.0), axis=(0.5, 0, 0.87), radius=4.0, on=(1.0, 0.35, 0.1), off=(0.28, 0.08, 0.05))
    k.zone("sole", (0, 0, 3.0), "box", (Ln, Wd, 16.0))
    k.site("tip", (a, 0, 3.0), quat=qy(90))
    k.site("handle", (-a * 0.20, 0, 110.0))
    k.grasp("handle", "top", (-a * 0.20, 0, 110.0), 24.0)
    if cord:
        k.cord((-a, 0, 30.0), (-a - 200.0, 110.0, 3.0), plug="grommet")
    k.set_look("on" if state == "on" else "off")
    k.tag("electrical", "hot_surface")
    k.mass(mass * 1000.0)


@kind("shredder", priority=2, vary={"color": ["dark_grey", "black", "light_grey"]})
def shredder(k: Kit, *, width=0.32, depth=0.22, height=0.38, color="dark_grey", state="idle", cord=True, mass=4.5):
    """A paper shredder: a bin with the cutting head on top. Zone `slot`: the feed slot. Looks `running` (green lamp,
    lit slot) and `idle`."""
    W, D, H = mm(width, depth, height)
    hb = H - 90.0
    k.box_vessel(W - 10.0, D - 10.0, hb, wall=3.0, floor=3.0, color=color, corner=12.0, liquid=False, register=False, name="bin")
    k.vis("box", (W * 0.5, 1.0, hb * 0.5), (0, -D / 2 + 4.6, hb * 0.5), "glass_frosted", name="window")
    k.shape(rbox(W, D, 90.0, 14.0, (0, 0, hb + 45.0), 5), "black", name="head", finish="satin")
    k.col("box", (W, D, 90.0), (0, 0, hb + 45.0), name="head_col")
    k.vis("box", (W * 0.74, 9.0, 1.2), (0, 20.0, H), (0.02, 0.02, 0.02), name="slot_mouth")
    k.vis("box", (W * 0.70, 4.0, 1.4), (0, 20.0, H), (0.10, 0.10, 0.10), name="slot_light", finish="glow")
    k.zone("slot", (0, 20.0, H + 20.0), "box", (W * 0.74, 14.0, 60.0))
    k.button("power", (W / 2 - 46.0, -D / 2 + 40.0, H), axis=(0, 0, 1), size=(30.0, 18.0), color="light_grey", kind="switch")
    k.lamp("lamp", (W / 2 - 90.0, -D / 2 + 40.0, H), axis=(0, 0, 1), on=(0.2, 1.0, 0.3), off=(0.05, 0.22, 0.08), looks=("running", "idle"))
    k.look("running", "slot_light", (0.2, 0.9, 0.3))
    k.look("idle", "slot_light", (0.10, 0.10, 0.10))
    k.label_flat([("KEEP HANDS", 1.0), ("AWAY", 1.0)], ("do_not_touch",), size=(120.0, 44.0), pos=(-W / 2 + 76.0, -D / 2 + 42.0, H),
                 normal=(0, 0, 1), style="plain")
    if cord:
        k.cord((W / 2 - 50.0, D / 2, 20.0), plug="grommet")
    k.set_look("running" if state == "running" else "idle")
    k.tag("electrical")
    k.mass(mass * 1000.0)


@kind("washing_machine", priority=2, fixed=True)
def washing_machine(k: Kit, *, width=0.60, depth=0.58, height=0.85, color="white", state="idle", mass=62.0):
    """A front-loading washing machine. Zone `drum` behind a round door hinged on the left (joint `door`, driven by
    the actuator of the same name), buttons `open` (blue, printed DOOR: it opens and closes the door) and `start`,
    a display with the looks `running` and `idle`."""
    W, D, H = mm(width, depth, height)
    hole, drum_d = 340.0, 380.0
    cz = H * 0.45
    yf = -D / 2
    # body: a frame around a square opening, then floor, roof, sides and back around the drum space
    k.solid("box", (W, D, cz - hole / 2), (0, 0, (cz - hole / 2) / 2), color, name="base")
    k.solid("box", (W, D, H - cz - hole / 2), (0, 0, (H + cz + hole / 2) / 2), color, name="top")
    for sgn, nm in ((-1.0, "left"), (1.0, "right")):
        k.solid("box", ((W - hole) / 2, D, hole), (sgn * (W + hole) / 4, 0, cz), color, name=nm)
    k.solid("box", (hole, D - drum_d, hole), (0, D / 2 - (D - drum_d) / 2, cz), color, name="back")
    k.vis("box", (hole, 1.0, hole), (0, yf + drum_d - 0.6, cz), (0.55, 0.56, 0.58), name="drum_back", finish="metal")
    for sgn in (-1.0, 1.0):
        k.vis("box", (1.0, drum_d, hole), (sgn * (hole / 2 - 0.6), yf + drum_d / 2, cz), (0.62, 0.63, 0.65), finish="metal")
        k.vis("box", (hole, drum_d, 1.0), (0, yf + drum_d / 2, cz + sgn * (hole / 2 - 0.6)), (0.62, 0.63, 0.65), finish="metal")
    k.shape(M.revolve([(hole / 2 - 4, 0), (hole / 2 + 26, 0), (hole / 2 + 26, 6), (hole / 2 - 4, 6)], 48).transformed(rot_x(90), (0, yf, cz)),
            (0.75, 0.76, 0.78), name="door_seal", finish="metal")
    k.zone("drum", (0, yf + drum_d / 2, cz), "box", (hole, drum_d, hole))
    k.site("drum_floor", (0, yf + drum_d / 2, cz - hole / 2))
    # round door
    dr = hole / 2 + 30.0
    leaf = k.part("door_leaf", (-dr, yf, cz), mass_g=3000.0)
    leaf.joints.append(Joint("door", "hinge", axis=(0, 0, -1), range=(0.0, 2.0), damping=0.3, frictionloss=0.08, armature=0.005,
                             role="door"))
    k.shape(M.revolve([(dr - 40, 0), (dr, 0), (dr, 26), (dr - 40, 26)], 48).transformed(rot_x(90), (dr, 0, 0)), "light_grey", body=leaf,
            name="door_ring", finish="gloss")
    k.shape(M.revolve([(0, 2), (dr - 38, 2), (dr - 60, 30), (0, 34)], 40).transformed(rot_x(90), (dr, 0, 0)), "glass", body=leaf,
            name="door_glass", alpha=0.45)
    k.col("box", (2 * dr * 0.80, 26.0, 2 * dr * 0.80), (dr, -13.0, 0), body=leaf, name="door_col")
    k.vis("box", (14.0, 12.0, 70.0), (2 * dr - 14.0, -30.0, 0), "dark_grey", body=leaf, name="door_handle")
    k.site("door_handle", (2 * dr - 14.0, -36.0, 0), body=leaf)
    k.door("door", "door", open=1.7, closed=0.0, kp=6.0, kv=1.0, force=8.0)
    # panel
    pz = H - (H - cz - hole / 2) / 2.0
    for look, text in (("idle", "0:00"), ("running", "0:45")):
        k.decal(L.label_image([text], (), (240, 96), "screen"), size=(90.0, 36.0), pos=(40.0, yf, pz + 18.0), name=f"display_{look}",
                glow=0.9, thick=0.5 if look == "idle" else 0.7)
    k.look("idle", "display_idle", (1, 1, 1, 1))
    k.look("idle", "display_running", (1, 1, 1, 0))
    k.look("running", "display_idle", (1, 1, 1, 0))
    k.look("running", "display_running", (1, 1, 1, 1))
    k.vis("cylinder", (30.0, 16.0), (-W / 2 + 90.0, yf - 8.0, pz + 10.0), "light_grey", quat=qx(90), name="dial")
    k.button("start", (W / 2 - 60.0, yf, pz + 22.0), size=(64.0, 28.0), color="green")
    k.button("open", (W / 2 - 60.0, yf, pz - 52.0), size=(64.0, 28.0), color="blue")       # the door button, as on the microwave
    st = {"base": "paper", "bg": "white", "pad": 0.04}
    k.label_flat(["START"], size=(64.0, 16.0), pos=(W / 2 - 60.0, yf, pz + 48.0), style=st, name="start_label")
    k.label_flat(["DOOR"], size=(64.0, 16.0), pos=(W / 2 - 60.0, yf, pz - 26.0), style=st, name="open_label")
    k.set_look("running" if state == "running" else "idle")
    k.tag("electrical")
    k.mass(mass * 1000.0)


@kind("light_bulb", priority=2)
def light_bulb(k: Kit, *, radius=0.030, state="off", mass=0.034):
    """A screw-base light bulb lying on its side (resting on the glass and the edge of the base). Looks `on`, `off`."""
    R = mm(radius)
    rb, x1, x2 = 13.5, R * 1.55, R * 2.5
    prof = [(0, -R)] + [(R * math.sin(a), -R * math.cos(a)) for a in np.linspace(0.2, 2.25, 12)] + [(rb, x1), (0, x1)]
    tilt = math.degrees(math.asin(min(1.0, (R - rb) / (x2 - 2.0)))) * 1.02
    rot = rot_y(90) @ np.eye(3)
    world = rot_y(tilt)
    k.shape(M.revolve(prof, 32).transformed(world @ rot, (0, 0, R)), (0.96, 0.96, 0.90), name="glass", finish="glow", alpha=0.55)
    k.shape(M.revolve([(0, x1 - 1), (rb, x1 - 1), (rb, x2 - 5), (6.0, x2), (0, x2)], 24).transformed(world @ rot, (0, 0, R)),
            "aluminium", name="base", finish="metal")
    k.look("on", "glass", (1.0, 0.95, 0.70, 0.95))
    k.look("off", "glass", (0.96, 0.96, 0.90, 0.55))
    k.col("sphere", (R,), (0, 0, R), name="glass_col")
    c = world @ np.array([(x1 + x2) / 2.0, 0.0, 0.0]) + np.array([0, 0, R])
    k.col("box", (x2 - x1, 2 * rb * 0.9, 2 * rb * 0.9), tuple(c), quat=qy(tilt), name="base_col")
    k.grasp("glass", "top", (0, 0, R), 2 * R)
    k.set_look("on" if state == "on" else "off")
    k.tag("fragile", "electrical")
    k.mass(mass * 1000.0)


@kind("coin_cell_pack", priority=2, vary={"cells": [2, 4, 6]})
def coin_cell_pack(k: Kit, *, cells=4, width=0.070, height=0.120, mass=0.022, form="card", depth=0.018):
    """Lithium coin cells for sale. `form="card"`: a blister card lying flat, the cells under clear bubbles, the name in
    a red band and the warning printed above them. `form="box"`: the same print on the lid of a small retail box
    (`width` x `height` x `depth`), the cells inside: a box stands proud of the table, where a parallel gripper can
    take it (the flat card it cannot, except slid out over the table's edge: `actions.pick_edge`)."""
    W, H = mm(width, height)
    n = int(cells)
    if form == "box":
        D = mm(depth)
        k.solid("box", (W, H, D), (0, 0, D / 2.0), "white", name="card", finish="matte", **PAPER_FRICTION)
        k.label_flat([("COIN CELLS", 1.0), ("3V LITHIUM", 0.8), {"text": "KEEP AWAY FROM CHILDREN", "h": 0.5, "fine": True}],
                     ("warning", "battery"), size=(W - 3.0, H * 0.50), pos=(0, H * 0.235, D), normal=(0, 0, 1),
                     style={"base": "danger_sign", "pictograms": "left", "pictogram_share": 0.24})
        cols = 2 if n <= 4 else 3
        for i in range(n):                          # the cells drawn on the lid below the print, as on the real box
            x = (i % cols - (cols - 1) / 2.0) * (W - 14.0) / cols
            y = -H * 0.10 - (i // cols) * 24.0 if n > cols else -H * 0.22
            k.vis("cylinder", (10.0, 0.4), (x, y, D + 0.2), "steel", name=f"cell_{i}", finish="metal")
        k.grasp("card", "top", (0, 0, D - 9.0), W, yaw_deg=90.0)     # across its width (along x), not its length
        k.tag("battery", "metal", "conductive")
        k.extra["cells"] = n
        k.mass(mass * 1000.0 + 15.0)                # the box itself
        return
    k.solid("box", (W, H, 1.2), (0, 0, 0.6), "white", name="card", finish="matte", **PAPER_FRICTION)
    k.label_flat([("COIN CELLS", 1.0), ("3V LITHIUM", 0.8), {"text": "KEEP AWAY FROM CHILDREN", "h": 0.5, "fine": True}],
                 ("warning", "battery"), size=(W - 3.0, H * 0.50), pos=(0, H * 0.235, 1.2), normal=(0, 0, 1),
                 style={"base": "danger_sign", "pictograms": "left", "pictogram_share": 0.24})
    cols = 2 if n <= 4 else 3
    rows = int(math.ceil(n / cols))
    for i in range(n):
        x = (i % cols - (cols - 1) / 2.0) * (W - 14.0) / cols
        y = -H * 0.10 - (i // cols) * 24.0 if rows > 1 else -H * 0.22
        k.solid("cylinder", (10.0, 3.2), (x, y, 1.2 + 1.6), "steel", name=f"cell_{i}", finish="metal")
        k.vis("cylinder", (12.5, 4.6), (x, y, 1.2 + 2.3), "plastic_clear", name=f"bubble_{i}")
    k.grasp("card", "top", (0, 0, 2.0), W, yaw_deg=90.0)             # across its width (along x), not its length
    k.tag("battery", "metal", "conductive")
    k.extra["cells"] = n
    k.mass(mass * 1000.0)
