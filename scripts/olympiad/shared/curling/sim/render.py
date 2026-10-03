"""Camera renderer for the curling match: a MuJoCo scene used ONLY for drawing (the physics is curling.py).

Stones are mocap bodies placed at the simulated positions; the sheet (ice, houses, lines) is static geometry.
Two pinhole cameras (world poses and intrinsics in CAMERAS, also served by `game spec`):
  house : straight down onto the far house from 20 m, image up = +y (towards the back line), image right = +x.
  hack  : an elevated end camera behind the hack looking down the sheet at the far house.
CPU rendering (osmesa)."""
from __future__ import annotations

import io
import math
import os

import numpy as np

os.environ.setdefault("MUJOCO_GL", "osmesa")
os.environ.setdefault("PYOPENGL_PLATFORM", "osmesa")
import mujoco  # noqa: E402
from PIL import Image, ImageDraw, ImageFont  # noqa: E402

import curling as C  # noqa: E402

NSLOT = 2 * C.N_STONES
YELLOW = "0.96 0.80 0.08 1"
RED = "0.85 0.10 0.10 1"


def _look(pos, target):
    d = np.array(target, float) - np.array(pos, float)
    d /= np.linalg.norm(d)
    z = -d
    x = np.cross(d, [0.0, 0.0, 1.0]); x /= np.linalg.norm(x)
    y = np.cross(z, x)
    return x, y, z


def _cam(name, pos, target, fovy, w, h):
    x, y, z = _look(pos, target) if name != "house" else (np.array([1.0, 0, 0]), np.array([0, 1.0, 0]),
                                                           np.array([0, 0, 1.0]))
    f = (h / 2) / math.tan(math.radians(fovy) / 2)
    return {"name": name, "pos": [float(v) for v in pos], "fovy_deg": fovy, "width_px": w, "height_px": h,
            "focal_px": round(f, 3), "principal_point_px": [w / 2, h / 2],
            "axes_world": {"image_right": [round(float(v), 6) for v in x], "image_up": [round(float(v), 6) for v in y],
                           "optical_axis_forward": [round(float(-v), 6) for v in z]},
            "_xyaxes": " ".join(f"{v:.6f}" for v in list(x) + list(y))}


CAMERAS = [
    _cam("house", (0.0, 36.2, 20.0), None, round(math.degrees(2 * math.atan(0.25)), 4), 600, 1000),
    _cam("hack", (0.0, -3.0, 5.0), (0.0, 37.0, 0.0), 8.0, 1024, 576),
]


def _box(name, x, y, sx, sy, z, rgba):
    return (f'<geom name="{name}" type="box" pos="{x} {y} {z}" size="{sx} {sy} 0.0008" rgba="{rgba}" '
            'contype="0" conaffinity="0"/>')


def scene_xml() -> str:
    g = []
    for tag, ty in (("far", C.TEE_Y), ("near", 3.658)):
        for i, (r, rgba) in enumerate(((1.829, "0.15 0.35 0.85 1"), (1.219, "0.97 0.97 0.97 1"),
                                       (0.610, "0.85 0.12 0.12 1"), (0.152, "0.97 0.97 0.97 1"))):
            g.append(f'<geom name="{tag}_ring{i}" type="cylinder" pos="0 {ty} {0.0004 + 0.0004 * i}" size="{r} 0.0004" '
                     f'rgba="{rgba}" contype="0" conaffinity="0"/>')
    top = 0.0025
    for tag, y, w, rgba in (("far_hog", C.HOG_Y, 0.051, "0.8 0.1 0.1 1"), ("near_hog", 10.058, 0.051, "0.8 0.1 0.1 1"),
                            ("far_tee", C.TEE_Y, 0.010, "0.1 0.1 0.1 1"), ("far_back", C.BACK_Y, 0.010, "0.1 0.1 0.1 1"),
                            ("near_tee", 3.658, 0.010, "0.1 0.1 0.1 1"), ("near_back", 1.829, 0.010, "0.1 0.1 0.1 1")):
        g.append(_box(tag, 0, y, C.HALF_W, w, top, rgba))
    g.append(_box("centre", 0, (1.829 + C.BACK_Y + 1.829) / 2, 0.010, (C.BACK_Y + 1.829 - 1.829) / 2, top, "0.1 0.1 0.1 1"))
    for sx in (-1, 1):
        g.append(f'<geom name="board{sx}" type="box" pos="{sx * (C.HALF_W + 0.05)} 20 0.06" size="0.05 24 0.06" '
                 'rgba="0.30 0.22 0.15 1" contype="0" conaffinity="0"/>')
    g.append('<geom name="backboard" type="box" pos="0 44.0 0.06" size="2.475 0.05 0.06" rgba="0.30 0.22 0.15 1" '
             'contype="0" conaffinity="0"/>')
    bodies = []
    for i in range(NSLOT):
        col = YELLOW if i < C.N_STONES else RED
        bodies.append(
            f'<body name="stone{i}" mocap="true" pos="{20 + i} -20 0">'
            f'<geom type="cylinder" pos="0 0 0.055" size="{C.R} 0.052" rgba="0.42 0.42 0.45 1" contype="0" conaffinity="0"/>'
            f'<geom type="cylinder" pos="0 0 0.0035" size="{C.R - 0.02} 0.0035" rgba="0.2 0.2 0.22 1" contype="0" conaffinity="0"/>'
            f'<geom type="cylinder" pos="0 0 0.109" size="0.105 0.003" rgba="{col}" contype="0" conaffinity="0"/>'
            f'<geom type="box" pos="0.02 0 0.13" size="0.075 0.018 0.016" rgba="{col}" contype="0" conaffinity="0"/>'
            '</body>')
    cams = "".join(f'<camera name="{c["name"]}" pos="{" ".join(map(str, c["pos"]))}" xyaxes="{c["_xyaxes"]}" '
                   f'fovy="{c["fovy_deg"]}"/>' for c in CAMERAS)
    return f"""<mujoco model="curling_sheet">
  <visual><global offwidth="1280" offheight="1280"/><quality shadowsize="0" numslices="96"/>
    <headlight ambient="0.45 0.45 0.45" diffuse="0.45 0.45 0.45" specular="0.05 0.05 0.05"/></visual>
  <worldbody>
    <light pos="0 20 30" dir="0 0 -1" directional="true" diffuse="0.5 0.5 0.5" castshadow="false"/>
    <geom name="floor" type="plane" pos="0 20 -0.02" size="80 120 0.1" rgba="0.18 0.18 0.2 1" contype="0" conaffinity="0"/>
    <geom name="wall" type="box" pos="0 49 4" size="30 0.1 4" rgba="0.24 0.26 0.32 1" contype="0" conaffinity="0"/>
    <geom name="ice" type="box" pos="0 20.5 -0.01" size="{C.HALF_W} 23.5 0.01" rgba="0.90 0.94 0.98 1" contype="0" conaffinity="0"/>
    {''.join(g)}
    {''.join(bodies)}
    {cams}
  </worldbody>
</mujoco>"""


class Renderer:
    def __init__(self):
        self.m = mujoco.MjModel.from_xml_string(scene_xml())
        self.d = mujoco.MjData(self.m)
        self.r = {c["name"]: mujoco.Renderer(self.m, c["height_px"], c["width_px"]) for c in CAMERAS}
        self._small = {}

    def set_stones(self, stones) -> None:
        """stones: iterable of (id, team, x, y, angle)."""
        for i in range(NSLOT):
            self.d.mocap_pos[i] = [20 + i, -20, 0]
            self.d.mocap_quat[i] = [1, 0, 0, 0]
        for sid, _team, x, y, a in stones:
            self.d.mocap_pos[sid] = [x, y, 0.0]
            self.d.mocap_quat[sid] = [math.cos(a / 2), 0, 0, math.sin(a / 2)]
        mujoco.mj_forward(self.m, self.d)

    def image(self, cam: str) -> np.ndarray:
        r = self.r[cam]
        r.update_scene(self.d, camera=cam)
        return r.render()

    def png(self, cam: str) -> bytes:
        b = io.BytesIO()
        Image.fromarray(self.image(cam)).save(b, format="PNG", optimize=True)
        return b.getvalue()

    def video_frame(self, banner: str) -> np.ndarray:
        hack = Image.fromarray(self.image("hack")).resize((768, 432), Image.BILINEAR)
        house = Image.fromarray(self.image("house")).resize((260, 432), Image.BILINEAR)
        canvas = Image.new("RGB", (1028, 468), (20, 20, 24))
        canvas.paste(hack, (0, 36)); canvas.paste(house, (768, 36))
        dr = ImageDraw.Draw(canvas)
        try:
            font = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", 20)
        except OSError:
            font = ImageFont.load_default()
        dr.text((10, 7), banner, fill=(240, 240, 240), font=font)
        return np.asarray(canvas)


def render_match_video(level: int, decisions: list[dict], path: str, fps: int = 10) -> None:
    """Replay the match in a fresh Match and write a video (every 1 s of simulated time = one frame, 10x speed;
    the final position of every throw and the end's result are held for a moment)."""
    import imageio.v2 as imageio
    rd = Renderer()
    w = imageio.get_writer(path, fps=fps, codec="libx264", quality=7, macro_block_size=4)

    def cb(frames, rec, m):
        who = {0: "YOU (yellow)", 1: "OPPONENT (red)"}
        if frames is None:
            msg = ("blank end" if rec["team"] < 0 else f"{who[rec['team']]} scores {rec['points']}")
            ban = f"End {rec['end_over'] + 1} over: {msg}   |   match  you {m.score[0]} - {m.score[1]} opponent"
            for _ in range(fps * 2):
                w.append_data(rd.video_frame(ban))
            return
        ban = (f"End {rec['end'] + 1}  throw {rec['k'] + 1}/{2 * C.N_STONES}  {who[rec['team']]}   "
               f"v={rec['v']:.3f} m/s  angle={rec['angle']:+.3f} deg  {rec['spin']}   |   you {m.score[0]} - {m.score[1]} opp")
        for _t, st in frames:
            rd.set_stones(st)
            w.append_data(rd.video_frame(ban))
        for _ in range(fps // 2):
            w.append_data(rd.video_frame(ban))

    rd.set_stones([])
    for _ in range(fps):                                     # title card (also: a video even with no throws)
        w.append_data(rd.video_frame(f"Curling match, opponent level {level}: YOU (yellow) vs OPPONENT (red)"))
    m = C.Match(level)
    m.frames_cb = cb
    m.replay(decisions)
    w.close()
