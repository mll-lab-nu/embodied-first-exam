"""The darts scene for the renderers (renderers/, the players' images and the replay video): drawing only, the flight
and the scoring are darts.py.

A regulation board (its texture drawn here from darts.py's geometry: bull 6.35 mm, outer bull 15.9 mm, treble ring
99-107 mm, double ring 162-170 mm, the numbers 20-1-18-...-5) on the wall, the throw line (oche) 2.37 m in front of
it, the release mechanism (a post with an arm holding the dart at the release point) and the three darts of the
latest visit as mocap bodies, flights yellow, cyan and magenta for darts 1, 2 and 3 (a dart that missed the board
is not shown). The camera definitions are CAMERAS (served by /spec with their intrinsics)."""
from __future__ import annotations

import io
import math

import numpy as np

import darts as D

TEX_N = 2048
TEX_HALF = 0.25                                     # the texture covers a 0.5 m square centred on the bull
TEX_FILE = "board_tex.png"
FLIGHT_RGBA = ["0.98 0.85 0.05 1", "0.05 0.85 0.95 1", "0.95 0.15 0.85 1"]
SLOTS = len(FLIGHT_RGBA)
HIDDEN = [0.0, 5.0, -1.0]                           # where an unused dart waits (under the floor, out of view)
TIP_IN = 0.006                                      # a stuck dart's tip is 6 mm inside the board

CAMERAS = [
    {"name": "oche", "pos": [0.0, 0.0, 1.80], "lookat": [D.X_BOARD, 0.0, D.Z_BULL], "fovy_deg": 12.0,
     "width": 900, "height": 900},
    {"name": "board", "pos": [D.X_BOARD - 0.9, 0.0, D.Z_BULL], "lookat": [D.X_BOARD, 0.0, D.Z_BULL], "fovy_deg": 32.0,
     "width": 900, "height": 900},
    {"name": "side", "pos": [1.25, -3.4, 1.55], "lookat": [1.25, 0.0, 1.55], "fovy_deg": 26.0, "width": 1024,
     "height": 576},
]


def _font(sz):
    from PIL import ImageFont
    for p in ("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", "DejaVuSans-Bold.ttf"):
        try:
            return ImageFont.truetype(p, sz)
        except OSError:
            continue
    return ImageFont.load_default(size=sz)          # Pillow's embedded font (the simulator image has no system fonts)


_TEX = None


def board_texture() -> bytes:
    """The board face as a PNG (row 0 = top), computed once per process."""
    global _TEX
    if _TEX is not None:
        return _TEX
    from PIL import Image, ImageDraw
    n = TEX_N
    c = (np.arange(n) + 0.5) / n * 2 * TEX_HALF - TEX_HALF
    u = c[None, :].repeat(n, 0)
    v = -c[:, None].repeat(n, 1)
    r = np.hypot(u, v)
    th = np.degrees(np.arctan2(u, v)) % 360.0
    seg = (((th + 9.0) % 360.0) // 18.0).astype(int) % 20
    even = seg % 2 == 0                              # segment 20 (index 0): black single, red double / treble
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
    w = 0.00045                                      # wires, 0.9 mm wide, silver
    wire = np.zeros((n, n), bool)
    for rr in (D.R_BULL, D.R_OBULL, D.R_TRI_IN, D.R_TRI_OUT, D.R_DBL_IN, D.R_DBL_OUT):
        wire |= np.abs(r - rr) < w
    for k in range(20):
        a = math.radians(k * 18.0 + 9.0)
        d = np.abs(u * math.cos(a) - v * math.sin(a))
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
    e0, e1 = (TEX_HALF - 0.2255) / (2 * TEX_HALF) * n, (TEX_HALF + 0.2255) / (2 * TEX_HALF) * n
    dr.ellipse([e0, e0, e1, e1], outline=(120, 120, 120), width=3)
    b = io.BytesIO()
    im.save(b, format="PNG")
    _TEX = b.getvalue()
    return _TEX


def _dart_body(i):
    col = FLIGHT_RGBA[i]
    return (f'<body name="dart{i}" mocap="true" pos="{" ".join(map(str, HIDDEN))}">'
            '<geom type="cylinder" fromto="0 0 0 0 0 -0.032" size="0.0011" rgba="0.8 0.8 0.82 1"/>'
            '<geom type="cylinder" fromto="0 0 -0.032 0 0 -0.080" size="0.0036" rgba="0.25 0.25 0.28 1"/>'
            '<geom type="cylinder" fromto="0 0 -0.080 0 0 -0.118" size="0.0021" rgba="0.1 0.1 0.1 1"/>'
            f'<geom type="box" pos="0 0 -0.135" size="0.015 0.0004 0.019" rgba="{col}"/>'
            f'<geom type="box" pos="0 0 -0.135" size="0.0004 0.015 0.019" rgba="{col}"/>'
            '</body>')


def scene_xml() -> str:
    X, Z = D.X_BOARD, D.Z_BULL
    rx, _ry, rz = D.RELEASE
    g = 'contype="0" conaffinity="0"'
    return f"""<mujoco model="darts">
  <visual><global offwidth="1280" offheight="1280"/><quality shadowsize="2048"/>
    <headlight ambient="0.35 0.35 0.35" diffuse="0.4 0.4 0.4" specular="0.05 0.05 0.05"/></visual>
  <asset>
    <texture name="board" type="2d" file="{TEX_FILE}"/>
    <material name="board" texture="board" texrepeat="1 1" texuniform="false" specular="0.05" shininess="0.1"/>
    <texture name="floor" type="2d" builtin="checker" rgb1="0.28 0.22 0.18" rgb2="0.24 0.19 0.15" width="256" height="256"/>
    <material name="floor" texture="floor" texrepeat="8 8"/>
  </asset>
  <worldbody>
    <light pos="1.2 0 3.0" dir="0.3 0 -1" directional="false" diffuse="0.55 0.55 0.55" castshadow="false"/>
    <light pos="1.8 -0.6 2.4" dir="1 0.3 -0.4" diffuse="0.35 0.35 0.35" castshadow="false"/>
    <geom name="floor" type="plane" pos="1.2 0 0" size="4 4 0.1" material="floor" {g}/>
    <geom name="wall" type="box" pos="{X + 0.06} 0 1.5" size="0.02 3 1.5" rgba="0.55 0.60 0.66 1" {g}/>
    <geom name="backwall" type="box" pos="1.0 2.2 1.5" size="2.0 0.02 1.5" rgba="0.36 0.42 0.52 1" {g}/>
    <geom name="cabinet" type="box" pos="{X + 0.03} 0 {Z}" size="0.02 0.30 0.30" rgba="0.12 0.08 0.05 1" {g}/>
    <geom name="board" type="plane" pos="{X} 0 {Z}" xyaxes="0 -1 0 0 0 1" size="{TEX_HALF} {TEX_HALF} 0.01" material="board" {g}/>
    <geom name="oche" type="box" pos="-0.02 0 0.019" size="0.02 0.3 0.019" rgba="0.85 0.85 0.85 1" {g}/>
    <geom name="line_mark" type="box" pos="{X / 2} 0 0.001" size="{X / 2} 0.004 0.001" rgba="0.6 0.6 0.6 1" {g}/>
    <geom name="post" type="cylinder" fromto="{rx - 0.12} 0 0 {rx - 0.12} 0 {rz - 0.08}" size="0.02" rgba="0.35 0.37 0.40 1" {g}/>
    <geom name="base" type="cylinder" fromto="{rx - 0.12} 0 0 {rx - 0.12} 0 0.02" size="0.15" rgba="0.3 0.3 0.32 1" {g}/>
    <geom name="arm" type="capsule" fromto="{rx - 0.12} 0 {rz - 0.08} {rx - 0.01} 0 {rz - 0.012}" size="0.012" rgba="0.75 0.2 0.1 1" {g}/>
    <geom name="cradle" type="box" pos="{rx - 0.01} 0 {rz - 0.008}" size="0.012 0.008 0.004" rgba="0.2 0.2 0.2 1" {g}/>
    {''.join(_dart_body(i) for i in range(SLOTS))}
  </worldbody>
</mujoco>"""


def quat_z_to(vec) -> list[float]:
    """The unit quaternion (w, x, y, z) that turns +z onto `vec` (as mujoco.mju_quatZ2Vec)."""
    v = np.asarray(vec, float)
    v = v / np.linalg.norm(v)
    c = float(v[2])
    if c > 1 - 1e-12:
        return [1.0, 0.0, 0.0, 0.0]
    if c < -1 + 1e-12:
        return [0.0, 1.0, 0.0, 0.0]
    axis = np.cross([0.0, 0.0, 1.0], v)
    axis /= np.linalg.norm(axis)
    a = math.acos(max(-1.0, min(1.0, c))) / 2
    return [math.cos(a), *(float(x) * math.sin(a) for x in axis)]


def stuck(rec: dict):
    """(tip position, arrival direction) of a dart stuck in the board, or None if it missed the board."""
    if rec["hit"] != "board" or math.hypot(rec["u"], rec["v"]) > D.R_BOARD:
        return None
    return (D.X_BOARD + TIP_IN, -rec["u"], rec["v"] + D.Z_BULL), tuple(rec["vel"])


def mocap(visit_darts: list[dict]) -> dict:
    """The renderer state of the board: the darts of one visit (darts.py dart records) in their flight-colour slots."""
    pos = [list(HIDDEN) for _ in range(SLOTS)]
    quat = [[1.0, 0.0, 0.0, 0.0] for _ in range(SLOTS)]
    for rec in visit_darts:
        s = stuck(rec)
        if s is not None:
            pos[rec["dart"] - 1] = [float(x) for x in s[0]]
            quat[rec["dart"] - 1] = quat_z_to(s[1])
    return {"qpos": [], "mocap_pos": [x for p in pos for x in p], "mocap_quat": [x for q in quat for x in q]}
