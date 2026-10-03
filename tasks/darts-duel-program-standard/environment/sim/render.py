"""Camera renderer for the darts match: a MuJoCo scene used ONLY for drawing (the flight is darts.py).

Scene: a regulation board (texture drawn here from darts.py's geometry: bull 6.35 mm, outer bull 15.9 mm, treble
ring 99-107 mm, double ring 162-170 mm, numbers 20-1-18-...-5) on the wall, the throw line (oche) 2.37 m in front
of it, the release mechanism (a post with an arm holding the dart at the release point) and up to six darts as mocap
bodies (your three: yellow, cyan, magenta flights for darts 1, 2, 3 of the visit; the opponent's: orange).
Cameras (world poses and intrinsics in CAMERAS, served by `game spec`):
  oche  : the thrower's eye at the throw line (0, 0, 1.80), looking at the bullseye;
  side  : from the thrower's right (y = -3.4 m) looking along +y (image right = towards the board); the path of your
          last dart is drawn as small yellow balls every 10 ms;
  board : straight at the board face from 0.9 m (image right = u, the thrower's right; image up = up).
CPU rendering (osmesa)."""
from __future__ import annotations

import io
import math
import os
import tempfile

import numpy as np

os.environ.setdefault("MUJOCO_GL", "osmesa")
os.environ.setdefault("PYOPENGL_PLATFORM", "osmesa")
import mujoco  # noqa: E402
from PIL import Image, ImageDraw, ImageFont  # noqa: E402

import darts as D  # noqa: E402

HERE = os.path.dirname(os.path.abspath(__file__))
TEX_N = 2048
TEX_HALF = 0.25                                     # the texture covers a 0.5 m square centred on the bull
FLIGHT_RGBA = ["0.98 0.85 0.05 1", "0.05 0.85 0.95 1", "0.95 0.15 0.85 1", "1.0 0.5 0.05 1", "1.0 0.5 0.05 1",
               "1.0 0.5 0.05 1"]


def _font(sz):
    for p in ("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", "DejaVuSans-Bold.ttf"):
        try:
            return ImageFont.truetype(p, sz)
        except OSError:
            continue
    return ImageFont.load_default(size=sz)          # Pillow's embedded font (the simulator image has no system fonts)


def board_texture(path: str) -> None:
    n = TEX_N
    c = (np.arange(n) + 0.5) / n * 2 * TEX_HALF - TEX_HALF
    u = c[None, :].repeat(n, 0)
    v = -c[:, None].repeat(n, 1)                     # row 0 = top (+v)
    r = np.hypot(u, v)
    th = np.degrees(np.arctan2(u, v)) % 360.0
    seg = (((th + 9.0) % 360.0) // 18.0).astype(int) % 20
    even = seg % 2 == 0                              # segment 20 (index 0): black single, red double/treble
    img = np.zeros((n, n, 3), np.uint8)
    img[:] = (22, 22, 22)                            # surround / cabinet
    single = np.where(even[..., None], np.array([20, 20, 20]), np.array([236, 222, 186]))
    ring = np.where(even[..., None], np.array([214, 30, 36]), np.array([20, 140, 60]))
    img = np.where((r <= D.R_DBL_OUT)[..., None], single, img)
    tri = (r >= D.R_TRI_IN) & (r <= D.R_TRI_OUT)
    dbl = (r >= D.R_DBL_IN) & (r <= D.R_DBL_OUT)
    img = np.where((tri | dbl)[..., None], ring, img)
    img = np.where((r <= D.R_OBULL)[..., None], np.array([20, 140, 60]), img)
    img = np.where((r <= D.R_BULL)[..., None], np.array([214, 30, 36]), img)
    # wires (0.9 mm wide, silver): rings and the radial wires between the bull and the double ring
    w = 0.00045
    wire = np.zeros((n, n), bool)
    for rr in (D.R_BULL, D.R_OBULL, D.R_TRI_IN, D.R_TRI_OUT, D.R_DBL_IN, D.R_DBL_OUT):
        wire |= np.abs(r - rr) < w
    for k in range(20):
        a = math.radians(k * 18.0 + 9.0)
        d = np.abs(u * math.cos(a) - v * math.sin(a))          # distance to the line at angle a (cw from up)
        along = u * math.sin(a) + v * math.cos(a)
        wire |= (d < w) & (along > D.R_OBULL) & (r <= D.R_DBL_OUT)
    img = np.where(wire[..., None], np.array([190, 190, 196]), img).astype(np.uint8)
    im = Image.fromarray(img)
    dr = ImageDraw.Draw(im)
    f = _font(int(0.026 / (2 * TEX_HALF) * n))
    for k, num in enumerate(D.SEGMENTS):
        a = math.radians(k * 18.0)
        uu, vv = 0.197 * math.sin(a), 0.197 * math.cos(a)
        px, py = (uu + TEX_HALF) / (2 * TEX_HALF) * n, (TEX_HALF - vv) / (2 * TEX_HALF) * n
        dr.text((px, py), str(num), fill=(240, 240, 240), font=f, anchor="mm")
    dr.ellipse([(TEX_HALF - 0.2255) / (2 * TEX_HALF) * n, (TEX_HALF - 0.2255) / (2 * TEX_HALF) * n,
                (TEX_HALF + 0.2255) / (2 * TEX_HALF) * n, (TEX_HALF + 0.2255) / (2 * TEX_HALF) * n],
               outline=(120, 120, 120), width=3)
    im.save(path)


def _look(pos, target):
    d = np.array(target, float) - np.array(pos, float)
    d /= np.linalg.norm(d)
    x = np.cross(d, [0.0, 0.0, 1.0]); x /= np.linalg.norm(x)
    y = np.cross(x, d)
    return x, y, d


def _cam(name, pos, target, fovy, w, h):
    x, y, d = _look(pos, target)
    f = (h / 2) / math.tan(math.radians(fovy) / 2)
    return {"name": name, "pos": [float(v) for v in pos], "looks_at": [float(v) for v in target], "fovy_deg": fovy,
            "width_px": w, "height_px": h, "focal_px": round(f, 3), "principal_point_px": [w / 2, h / 2],
            "axes_world": {"image_right": [round(float(v), 6) for v in x], "image_up": [round(float(v), 6) for v in y],
                           "optical_axis_forward": [round(float(v), 6) for v in d]},
            "_xyaxes": " ".join(f"{v:.6f}" for v in list(x) + list(y))}


CAMERAS = [
    _cam("oche", (0.0, 0.0, 1.80), (D.X_BOARD, 0.0, D.Z_BULL), 12.0, 900, 900),
    _cam("side", (1.25, -3.4, 1.55), (1.25, 0.0, 1.55), 26.0, 1024, 576),
    _cam("board", (D.X_BOARD - 0.9, 0.0, D.Z_BULL), (D.X_BOARD, 0.0, D.Z_BULL), 32.0, 900, 900),
]


def _dart_body(i):
    col = FLIGHT_RGBA[i]
    return (f'<body name="dart{i}" mocap="true" pos="0 {5 + i} 0">'
            '<geom type="cylinder" fromto="0 0 0 0 0 -0.032" size="0.0011" rgba="0.8 0.8 0.82 1"/>'
            '<geom type="cylinder" fromto="0 0 -0.032 0 0 -0.080" size="0.0036" rgba="0.25 0.25 0.28 1"/>'
            '<geom type="cylinder" fromto="0 0 -0.080 0 0 -0.118" size="0.0021" rgba="0.1 0.1 0.1 1"/>'
            f'<geom type="box" pos="0 0 -0.135" size="0.015 0.0004 0.019" rgba="{col}"/>'
            f'<geom type="box" pos="0 0 -0.135" size="0.0004 0.015 0.019" rgba="{col}"/>'
            '</body>')


def scene_xml(tex_path: str) -> str:
    X, Z = D.X_BOARD, D.Z_BULL
    rx, ry, rz = D.RELEASE
    cams = "".join(f'<camera name="{c["name"]}" pos="{" ".join(map(str, c["pos"]))}" xyaxes="{c["_xyaxes"]}" '
                   f'fovy="{c["fovy_deg"]}"/>' for c in CAMERAS)
    return f"""<mujoco model="darts">
  <visual><global offwidth="1280" offheight="1280"/><quality shadowsize="2048"/>
    <headlight ambient="0.35 0.35 0.35" diffuse="0.4 0.4 0.4" specular="0.05 0.05 0.05"/></visual>
  <asset>
    <texture name="board" type="2d" file="{tex_path}"/>
    <material name="board" texture="board" texrepeat="1 1" texuniform="false" specular="0.05" shininess="0.1"/>
    <texture name="floor" type="2d" builtin="checker" rgb1="0.28 0.22 0.18" rgb2="0.24 0.19 0.15" width="256" height="256"/>
    <material name="floor" texture="floor" texrepeat="8 8"/>
  </asset>
  <worldbody>
    <light pos="1.2 0 3.0" dir="0.3 0 -1" directional="false" diffuse="0.55 0.55 0.55" castshadow="false"/>
    <light pos="1.8 -0.6 2.4" dir="1 0.3 -0.4" diffuse="0.35 0.35 0.35" castshadow="false"/>
    <geom name="floor" type="plane" pos="1.2 0 0" size="4 4 0.1" material="floor" contype="0" conaffinity="0"/>
    <geom name="wall" type="box" pos="{X + 0.06} 0 1.5" size="0.02 3 1.5" rgba="0.55 0.60 0.66 1" contype="0" conaffinity="0"/>
    <geom name="backwall" type="box" pos="1.0 2.2 1.5" size="2.0 0.02 1.5" rgba="0.36 0.42 0.52 1" contype="0" conaffinity="0"/>
    <geom name="cabinet" type="box" pos="{X + 0.03} 0 {Z}" size="0.02 0.30 0.30" rgba="0.12 0.08 0.05 1" contype="0" conaffinity="0"/>
    <geom name="board" type="plane" pos="{X} 0 {Z}" xyaxes="0 -1 0 0 0 1" size="{TEX_HALF} {TEX_HALF} 0.01" material="board" contype="0" conaffinity="0"/>
    <geom name="oche" type="box" pos="-0.02 0 0.019" size="0.02 0.3 0.019" rgba="0.85 0.85 0.85 1" contype="0" conaffinity="0"/>
    <geom name="line_mark" type="box" pos="{X / 2} 0 0.001" size="{X / 2} 0.004 0.001" rgba="0.6 0.6 0.6 1" contype="0" conaffinity="0"/>
    <geom name="post" type="cylinder" fromto="{rx - 0.12} 0 0 {rx - 0.12} 0 {rz - 0.08}" size="0.02" rgba="0.35 0.37 0.40 1" contype="0" conaffinity="0"/>
    <geom name="base" type="cylinder" fromto="{rx - 0.12} 0 0 {rx - 0.12} 0 0.02" size="0.15" rgba="0.3 0.3 0.32 1" contype="0" conaffinity="0"/>
    <geom name="arm" type="capsule" fromto="{rx - 0.12} 0 {rz - 0.08} {rx - 0.01} 0 {rz - 0.012}" size="0.012" rgba="0.75 0.2 0.1 1" contype="0" conaffinity="0"/>
    <geom name="cradle" type="box" pos="{rx - 0.01} 0 {rz - 0.008}" size="0.012 0.008 0.004" rgba="0.2 0.2 0.2 1" contype="0" conaffinity="0"/>
    {''.join(_dart_body(i) for i in range(6))}
    {cams}
  </worldbody>
</mujoco>"""


class Renderer:
    def __init__(self):
        tex = os.path.join(HERE, "board_tex.png")
        if not os.path.exists(tex):                 # the code is mounted read-only: draw the texture into /tmp
            tex = os.path.join(tempfile.gettempdir(), "darts_board_tex.png")
        if not os.path.exists(tex):
            board_texture(tex)
        self.m = mujoco.MjModel.from_xml_string(scene_xml(tex))
        self.d = mujoco.MjData(self.m)
        self.r = {}
        self.trail = []

    def _rend(self, cam, w, h):
        key = (cam, w, h)
        if key not in self.r:
            self.r[key] = mujoco.Renderer(self.m, h, w)
        return self.r[key]

    def set_darts(self, darts: list[tuple[int, tuple, tuple]]) -> None:
        """darts: [(slot, tip_position_xyz, direction_xyz)]; other slots are hidden."""
        for i in range(6):
            self.d.mocap_pos[i] = [0.0, 5.0 + i, -1.0]
            self.d.mocap_quat[i] = [1, 0, 0, 0]
        for slot, p, dvec in darts:
            q = np.zeros(4)
            dv = np.array(dvec, float); dv /= np.linalg.norm(dv)
            mujoco.mju_quatZ2Vec(q, dv)
            self.d.mocap_pos[slot] = p
            self.d.mocap_quat[slot] = q
        mujoco.mj_forward(self.m, self.d)

    def image(self, cam: str, w: int = None, h: int = None, trail: list = None) -> np.ndarray:
        c = next(c for c in CAMERAS if c["name"] == cam)
        r = self._rend(cam, w or c["width_px"], h or c["height_px"])
        r.update_scene(self.d, camera=cam)
        for pt in (trail or []):
            sc = r.scene
            if sc.ngeom >= sc.maxgeom:
                break
            mujoco.mjv_initGeom(sc.geoms[sc.ngeom], mujoco.mjtGeom.mjGEOM_SPHERE, np.array([0.006, 0, 0]),
                                np.array(pt, float), np.eye(3).flatten(), np.array([1.0, 0.9, 0.1, 1.0], np.float32))
            sc.ngeom += 1
        return r.render()

    def png(self, cam: str, trail: list = None) -> bytes:
        b = io.BytesIO()
        Image.fromarray(self.image(cam, trail=trail)).save(b, format="PNG", optimize=True)
        return b.getvalue()


def stuck(rec: dict, slot: int):
    """(slot, tip, direction) of a dart stuck in the board (tip 6 mm into the board), or None if it missed it."""
    if rec["hit"] != "board" or math.hypot(rec["u"], rec["v"]) > D.R_BOARD:
        return None
    return (slot, (D.X_BOARD + 0.006, -rec["u"], rec["v"] + D.Z_BULL), tuple(rec["vel"]))


def render_match_video(level: int, seed: int, decisions: list[dict], path: str, fps: int = 12,
                       forfeit: bool = False) -> None:
    import imageio.v2 as imageio
    m = D.Match(level, seed)
    m.replay(decisions, forfeit)
    R = Renderer()
    W, H = 1280, 540
    fnt, fsm = _font(22), _font(17)
    wr = imageio.get_writer(path, fps=fps, codec="libx264", quality=7, macro_block_size=8)
    rem = [D.START, D.START]
    board = []                                          # darts in the board in the current visit

    def frame(banner, sub, trail=None):
        side = Image.fromarray(R.image("side", 768, 432, trail=trail))
        oche = Image.fromarray(R.image("oche", 432, 432))
        cv = Image.new("RGB", (W, H), (18, 18, 22))
        cv.paste(side, (0, 60)); cv.paste(oche, (776, 60))
        dr = ImageDraw.Draw(cv)
        dr.text((10, 6), banner, fill=(240, 240, 240), font=fnt)
        dr.text((10, 34), sub, fill=(250, 210, 90), font=fsm)
        dr.text((10, 500), f"YOU {rem[0]} (legs {legs[0]})    OPPONENT {rem[1]} (legs {legs[1]})    best of 3 legs, level {level}",
                fill=(220, 220, 220), font=fnt)
        wr.append_data(np.asarray(cv))

    last_visit, cur_leg, legs = None, 1, [0, 0]
    for rec in m.log:
        if rec["leg"] != cur_leg:                          # a new leg
            cur_leg, rem = rec["leg"], [D.START, D.START]
            legs = [sum(1 for x in m.leg_results[:cur_leg - 1] if x["winner"] == w) for w in ("you", "opponent")]
        key = (rec["who"], rec["leg"], rec["visit"])
        if key != last_visit:
            board, last_visit = [], key
        who = "YOU" if rec["who"] == 0 else "OPPONENT"
        slot = (rec["dart"] - 1) + (0 if rec["who"] == 0 else 3)
        ex = rec["executed"]
        f = D.fly(ex[0], ex[1], ex[2], m.k, trail=True)
        pts = f["trail"]
        banner = f"leg {rec['leg']}  {who}  visit {rec['visit']}, dart {rec['dart']}   ({rem[rec['who']]} left)"
        n = 8
        for j in range(1, n + 1):
            idx = min(len(pts) - 1, int(round(j / n * (len(pts) - 1))))
            _, x, y, z = pts[idx]
            a = pts[max(0, idx - 1)]
            dv = (x - a[1], y - a[2], z - a[3]) if idx > 0 else (1, 0, 0)
            tip = (x, y, z) if j < n else None
            ds = list(board) + ([(slot, tip, dv)] if tip else [])
            s = stuck(rec, slot) if j == n else None
            if s:
                ds.append(s)
            R.set_darts(ds)
            frame(banner, "", trail=[(p[1], p[2], p[3]) for p in pts[:idx + 1:2]])
        s = stuck(rec, slot)
        if s:
            board.append(s)
        rem[rec["who"]] = rec["after"]
        call = rec["call"] + (f"  -  {rec['event'].upper()}" if rec.get("event") else "")
        R.set_darts(board)
        for _ in range(5):
            frame(banner, f"caller: {call}")
    end = f"MATCH OVER: {'YOU WIN' if m.winner == 0 else 'OPPONENT WINS'} ({m.reason}), legs {m.legs[0]}-{m.legs[1]}"
    for _ in range(3 * fps):
        frame(end, "")
    wr.close()


def render_duel_video(seed: int, first: str, decisions: list[dict], path: str, fps: int = 12) -> None:
    """Replay video of a two-player match (darts.Duel): the side and thrower views of every dart, the caller's call."""
    import imageio.v2 as imageio
    m = D.Duel(seed, first)
    m.replay(decisions)
    R = Renderer()
    W, H = 1280, 540
    fnt, fsm = _font(22), _font(17)
    wr = imageio.get_writer(path, fps=fps, codec="libx264", quality=7, macro_block_size=8)
    rem, legs = {"A": D.START, "B": D.START}, {"A": 0, "B": 0}
    board, last_visit, cur_leg = [], None, 1

    def frame(banner, sub, trail=None):
        side = Image.fromarray(R.image("side", 768, 432, trail=trail))
        oche = Image.fromarray(R.image("oche", 432, 432))
        cv = Image.new("RGB", (W, H), (18, 18, 22))
        cv.paste(side, (0, 60)); cv.paste(oche, (776, 60))
        dr = ImageDraw.Draw(cv)
        dr.text((10, 6), banner, fill=(240, 240, 240), font=fnt)
        dr.text((10, 34), sub, fill=(250, 210, 90), font=fsm)
        dr.text((10, 500), f"A {rem['A']} (legs {legs['A']})    B {rem['B']} (legs {legs['B']})    best of 3 legs, 501",
                fill=(220, 220, 220), font=fnt)
        wr.append_data(np.asarray(cv))

    for rec in m.log:
        key = (rec["seat"], rec["leg"], rec["visit"])
        if key != last_visit:
            board, last_visit = [], key
        if rec["leg"] != cur_leg:                          # a new leg
            cur_leg, rem = rec["leg"], {"A": D.START, "B": D.START}
        slot = rec["dart"] - 1
        ex = rec["executed"]
        pts = D.fly(ex[0], ex[1], ex[2], m.k, trail=True)["trail"]
        banner = f"leg {rec['leg']}  {rec['seat']}  visit {rec['visit']}, dart {rec['dart']}   ({rem[rec['seat']]} left)"
        for j in range(1, 5):
            idx = min(len(pts) - 1, int(round(j / 4 * (len(pts) - 1))))
            R.set_darts(list(board))
            frame(banner, "", trail=[(p[1], p[2], p[3]) for p in pts[:idx + 1:2]])
        s = stuck(rec, slot)
        if s:
            board.append(s)
        rem[rec["seat"]] = rec["after"]
        R.set_darts(board)
        call = rec["call"] + (f"  -  {rec['event'].upper()}" if rec.get("event") else "")
        for _ in range(4):
            frame(banner, f"caller: {call}")
        if rec.get("leg_over"):
            legs = {s_: sum(1 for x in m.leg_results[:rec["leg"]] if x["winner"] == s_) for s_ in ("A", "B")}
    end = f"MATCH OVER: {m.winner} WINS ({m.reason}), legs A {m.legs['A']} - B {m.legs['B']}"
    for _ in range(3 * fps):
        frame(end, "")
    wr.close()


# The observation is one PNG: the three cameras as tiles (x, y, width, height) on a dark canvas.
TILES = {"oche": [0, 0, 900, 900], "board": [900, 0, 900, 900], "side": [0, 900, 1024, 576]}
CANVAS = (1800, 1476)


def compose(R, darts: list, trail: list) -> bytes:
    """The observation image: oche and board on top, side below (TILES); `darts` stuck in the board, `trail` the
    path drawn in the side view."""
    R.set_darts(darts)
    cv = Image.new("RGB", CANVAS, (18, 18, 22))
    for cam, (x, y, w, h) in TILES.items():
        cv.paste(Image.fromarray(R.image(cam, trail=trail if cam == "side" else None)), (x, y))
    b = io.BytesIO()
    cv.save(b, format="PNG", optimize=True)
    return b.getvalue()
