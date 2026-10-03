"""Cameras and a small pinhole renderer for the billiards table (PIL; no GPU, no OpenGL).

Two cameras per decision point:
  * top:   fixed, 2.6 m above the table centre looking straight down (image right = +y world, image down = +x world);
  * sight: a player's sighting view from behind the cue ball along an aim direction phi (the cue stick is drawn
           along phi), eye 0.75 m behind the cue ball and 0.32 m above the cloth, looking at the cloth 1.0 m ahead.
Both are ideal pinhole cameras (OpenCV convention: x right, y down, z forward); `camera_info()` gives the poses and
intrinsics exactly as used here. Balls are drawn as the projected spheres (their silhouettes), so a ball's image
centre is the projection of its centre (x, y, R) up to a fraction of a pixel.
"""
from __future__ import annotations

import io
import math

import numpy as np
from PIL import Image, ImageDraw, ImageFont

from eightball import L, POCKETS, R, W, TABLE

SS = 2                                     # supersampling
TOP = {"name": "top", "size": (1120, 640), "f": 1150.0, "pos": (W / 2, L / 2, 2.6)}
SIGHT = {"name": "sight", "size": (960, 540), "f": 620.0, "back": 0.75, "height": 0.32, "ahead": 1.0}
BALL_RGB = {"cue": (245, 243, 232), "1": (250, 200, 20), "2": (30, 70, 210), "3": (215, 30, 30), "4": (110, 40, 160),
            "5": (255, 120, 20), "6": (20, 140, 40), "7": (120, 20, 30), "8": (15, 15, 15)}
BALL_RGB.update({str(i + 8): BALL_RGB[str(i)] for i in range(1, 8)})     # stripes 9-15: the colours of 1-7
WHITE = (246, 246, 240)
CLOTH = (38, 110, 150)                     # blue-teal cloth
CUSHION = (28, 88, 122)
RAIL = (96, 58, 30)
BG = (32, 32, 36)
RAIL_W = 0.10                              # rail outer edge distance from the cushion nose line
CUSH_W = 0.045


def _font(px: int):
    for p in ("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", "DejaVuSans-Bold.ttf"):
        try:
            return ImageFont.truetype(p, px)
        except OSError:
            continue
    return ImageFont.load_default()


def top_camera():
    Rwc = np.array([[0.0, 1.0, 0.0], [1.0, 0.0, 0.0], [0.0, 0.0, -1.0]])   # rows: camera x, y, z axes in world
    return np.array(TOP["pos"], dtype=float), Rwc, TOP["f"], TOP["size"]


def sight_camera(cue_xy, phi_deg):
    d = np.array([math.cos(math.radians(phi_deg)), math.sin(math.radians(phi_deg)), 0.0])
    c = np.array([cue_xy[0], cue_xy[1], R])
    eye = c - SIGHT["back"] * d + np.array([0.0, 0.0, SIGHT["height"] - R])
    tgt = c + SIGHT["ahead"] * d; tgt[2] = 0.0
    z = tgt - eye; z /= np.linalg.norm(z)
    x = np.cross(z, np.array([0.0, 0.0, 1.0])); x /= np.linalg.norm(x)
    y = np.cross(z, x)
    return eye, np.stack([x, y, z]), SIGHT["f"], SIGHT["size"]


def camera_info(cam, label: str) -> dict:
    pos, Rwc, f, (w, h) = cam
    return {"name": label, "position_world": [round(float(v), 5) for v in pos],
            "R_world_to_camera": [[round(float(v), 6) for v in row] for row in Rwc],
            "convention": "pinhole, OpenCV axes: camera x = image right, y = image down, z = viewing direction; "
                          "p_cam = R_world_to_camera @ (p_world - position_world); u = fx*x/z + cx, v = fy*y/z + cy",
            "image_px": [w, h], "fx": f, "fy": f, "cx": w / 2, "cy": h / 2}


class _Proj:
    def __init__(self, cam):
        self.pos, self.R, self.f, (self.w, self.h) = cam
        self.fs = self.f * SS

    def cam(self, P):
        return (np.atleast_2d(P) - self.pos) @ self.R.T

    def pix(self, Pc):
        Pc = np.atleast_2d(Pc)
        return np.stack([self.fs * Pc[:, 0] / Pc[:, 2] + self.w * SS / 2, self.fs * Pc[:, 1] / Pc[:, 2] + self.h * SS / 2], 1)

    def poly(self, draw, P, fill, near=0.03):
        """Project a planar world polygon, clipped to z_cam > near."""
        Pc = self.cam(P)
        out = []
        n = len(Pc)
        for i in range(n):
            a, b = Pc[i], Pc[(i + 1) % n]
            ina, inb = a[2] > near, b[2] > near
            if ina:
                out.append(a)
            if ina != inb:
                t = (near - a[2]) / (b[2] - a[2]); out.append(a + t * (b - a))
        if len(out) >= 3:
            draw.polygon([tuple(p) for p in self.pix(np.array(out))], fill=fill)


def _circle(c, r, n=40, z=0.0):
    t = np.linspace(0, 2 * math.pi, n, endpoint=False)
    return np.stack([c[0] + r * np.cos(t), c[1] + r * np.sin(t), np.full(n, z)], 1)


def _rect(x0, y0, x1, y1, z=0.0):
    return np.array([[x0, y0, z], [x1, y0, z], [x1, y1, z], [x0, y1, z]])


def _draw_table(pr: _Proj, draw):
    pr.poly(draw, _rect(-RAIL_W - 0.02, -RAIL_W - 0.02, W + RAIL_W + 0.02, L + RAIL_W + 0.02), RAIL)
    pr.poly(draw, _rect(-CUSH_W, -CUSH_W, W + CUSH_W, L + CUSH_W), CUSHION)
    pr.poly(draw, _rect(0, 0, W, L), CLOTH)
    for k, c in POCKETS.items():
        pr.poly(draw, _circle(c, TABLE.pockets[k].radius), (8, 8, 8))
    # diamonds (sights) on the rails: every L/8 along the long rails, every W/4 along the short rails
    for i in range(1, 8):
        if i == 4:
            continue
        for x in (-0.075, W + 0.075):
            pr.poly(draw, _circle((x, L * i / 8), 0.008, 12), (235, 225, 200))
    for i in range(1, 4):
        for y in (-0.075, L + 0.075):
            pr.poly(draw, _circle((W * i / 4, y), 0.008, 12), (235, 225, 200))
    # head spot and foot spot
    for y in (L / 4, 3 * L / 4):
        pr.poly(draw, _circle((W / 2, y), 0.006, 12), (200, 215, 225))


def _draw_stick(pr: _Proj, draw, cue_xy, phi):
    d = np.array([math.cos(math.radians(phi)), math.sin(math.radians(phi)), 0.0])
    n = np.array([-d[1], d[0], 0.0])
    c = np.array([cue_xy[0], cue_xy[1], R])
    segs = [(R + 0.012, R + 0.030, 0.0065, 0.0066, (240, 240, 235)), (R + 0.030, R + 0.75, 0.0066, 0.010, (225, 190, 130)),
            (R + 0.75, R + 1.40, 0.010, 0.0145, (60, 30, 20))]
    for s0, s1, w0, w1, col in segs:
        a = c - d * s0 + np.array([0, 0, 0.07 * (s0 - R)])
        b = c - d * s1 + np.array([0, 0, 0.07 * (s1 - R)])
        pr.poly(draw, np.array([a + n * w0, b + n * w1, b - n * w1, a - n * w0]), col, near=0.05)


def _draw_balls(pr: _Proj, draw, pos: dict):
    items = []
    for k, (x, y) in pos.items():
        Pc = pr.cam(np.array([x, y, R]))[0]
        if Pc[2] > R + 0.02:
            items.append((Pc[2], k, Pc))
    for z, k, Pc in sorted(items, key=lambda t: -t[0]):
        u, v = pr.pix(Pc)[0]
        r = pr.fs * R / math.sqrt(max(z * z - R * R, 1e-9))     # silhouette radius (small-ball approx)
        col = BALL_RGB.get(k, (200, 200, 200))
        stripe = k.isdigit() and int(k) >= 9
        draw.ellipse([u - r, v - r, u + r, v + r], fill=col, outline=(10, 10, 10), width=max(1, int(r * 0.06)))
        if stripe:      # a stripe ball: white caps above and below a coloured band (|dv| < r/2)
            for a0, a1 in ((210, 330), (30, 150)):
                draw.chord([u - r, v - r, u + r, v + r], a0, a1, fill=WHITE)
            draw.ellipse([u - r, v - r, u + r, v + r], outline=(10, 10, 10), width=max(1, int(r * 0.06)))
        hr = r * 0.22
        draw.ellipse([u - 0.45 * r - hr, v - 0.45 * r - hr, u - 0.45 * r + hr, v - 0.45 * r + hr], fill=tuple(min(255, c + 70) for c in col))
        if k != "cue":
            rr = r * 0.46
            draw.ellipse([u - rr, v - rr, u + rr, v + rr], fill=(250, 250, 250))
            fnt = _font(max(8, int(r * 0.72)))
            draw.text((u, v), k, fill=(0, 0, 0), font=fnt, anchor="mm")


def render(cam, pos: dict, stick_phi: float | None = None, label: str = "") -> Image.Image:
    pr = _Proj(cam)
    img = Image.new("RGB", (pr.w * SS, pr.h * SS), BG)
    draw = ImageDraw.Draw(img)
    _draw_table(pr, draw)
    if stick_phi is not None and "cue" in pos and pr.pos[2] > 1.0:     # top view: stick under the balls
        _draw_stick(pr, draw, pos["cue"], stick_phi)
    _draw_balls(pr, draw, pos)
    if stick_phi is not None and "cue" in pos and pr.pos[2] <= 1.0:    # sight view: stick in front
        _draw_stick(pr, draw, pos["cue"], stick_phi)
    img = img.resize((pr.w, pr.h), Image.LANCZOS)
    if label:
        d2 = ImageDraw.Draw(img)
        d2.text((8, 6), label, fill=(255, 255, 255), font=_font(16))
    return img


def default_sight_phi(pos: dict) -> float:
    """Sighting direction when none is asked for: from the cue ball towards the table centre (or +y)."""
    if "cue" not in pos:
        return 90.0
    c = np.array(pos["cue"]); t = np.array([W / 2, L / 2]) - c
    if np.linalg.norm(t) < 0.15:
        return 90.0
    return math.degrees(math.atan2(t[1], t[0])) % 360.0


def png(img: Image.Image) -> bytes:
    b = io.BytesIO(); img.save(b, format="PNG"); return b.getvalue()


def views(pos: dict, phi: float, eye_xy=None) -> dict:
    """Top and sighting views. With the cue ball off the table (ball in hand after a scratch) there is no stick and
    the sighting view looks from `eye_xy` (default: the head spot)."""
    from eightball import HEAD_SPOT
    c = pos.get("cue") or eye_xy or HEAD_SPOT
    stick = phi if "cue" in pos else None
    top = render(top_camera(), pos, stick_phi=stick, label="top view (image right = +y, image down = +x)")
    lab = f"sighting view along aim {phi:.2f} deg" + ("" if "cue" in pos else " (cue ball in hand: from the head spot)")
    sight = render(sight_camera(c, phi), pos, stick_phi=stick, label=lab)
    return {"top": png(top), "sight": png(sight),
            "cameras": [camera_info(top_camera(), "top"), camera_info(sight_camera(c, phi), "sight")]}


# ----------------------------------------------------------------------------- replay video
def render_video(clips: list, final_pos: dict, final_label: str, path: str, fps: int = 30) -> None:
    """Top-view video. clips: [(label, positions before the shot, continuized pooltool system)]."""
    import imageio.v2 as imageio
    cam = top_camera()
    wr = imageio.get_writer(path, fps=fps, codec="libx264", quality=7, macro_block_size=8)
    for lab, pos0, s in clips:
        hist, T = {}, 0.0
        for bid, b in s.balls.items():
            rvw, st, ts = b.history_cts.vectorize()
            hist[bid] = (rvw[:, 0, :2], st, ts)
            T = max(T, float(ts[-1]) if len(ts) else 0.0)
        for _ in range(12):
            wr.append_data(np.asarray(render(cam, pos0, label=lab)))
        for fi in range(int(T * fps) + 1):
            t = fi / fps
            pos = {}
            for bid, (xy, st, ts) in hist.items():
                j = min(int(np.searchsorted(ts, t)), len(ts) - 1)
                if st[j] >= 4:
                    continue
                pos[bid] = (float(xy[j][0]), float(xy[j][1]))
            wr.append_data(np.asarray(render(cam, pos, label=lab)))
    for _ in range(45):
        wr.append_data(np.asarray(render(cam, final_pos, label=final_label)))
    wr.close()
