"""The seats' cameras (each in its own frame) and the observation image (drawn in the seat's render worker of the v0.2
core), fencing-7.

Each seat has two fixed cameras, placed the same way in its own frame (fencing.py: the seat stands at x < 0 and faces
+x): `side` beside the piste (y = -7 m) looking across it, the seat's robot on the left and the opponent on the right;
`top` above and beside the piste looking down at it. The observation image shows the last phrase (phrases.py): 2 rows
(side, top) x 2 columns (the phrase half-way, at its end) of 800 x 360 pixel tiles; before the first phrase both
fencers on guard. Every seat sees its own robot red and the opponent's blue, the points yellow
(fencing.scene_xml(view=seat): the same scene, other colours).

The frames were kept from the measured phrases (phrases/frames.npz) on the table's ends; when a fencer fenced the
phrase from the table's other end (phrases.py: the ends are drawn for each phrase), the picture is turned by half a
turn about the centre of the piste (half_turn), so that each fencer is always drawn at its own end.

A Renderer keeps the tiles it drew (by camera and the frame's joint positions) and its last image.
"""
from __future__ import annotations

import hashlib
import math
from collections import OrderedDict

import numpy as np

import fencing as F

TILE = (800, 360)                  # width, height (as the legacy views.py)
FOVY = 45.0
FOCAL = TILE[1] / 2 / math.tan(math.radians(FOVY / 2))      # 434.6 px
CAMS = {   # own frame: lookat, distance, azimuth (deg), elevation (deg)  [MuJoCo free camera] (as the legacy views.py)
    "side": ((0.0, 0.0, 0.75), 7.0, 90.0, -5.0),
    "top": ((0.0, 0.0, 0.8), 7.5, 90.0, -70.0),
}
N_FRAMES = 2                       # columns of the observation image: the last phrase half-way and at its end
IMAGE_LAYOUT = ("2 rows x 2 columns of 800 x 360 tiles. Row 1: the side camera, row 2: the top camera (poses in `game "
                "spec`). Columns: the last phrase half-way (left) and at its end (right); before the first phrase "
                "both fencers on guard. Your robot is red, the opponent's blue; the points are yellow.")


def cam_info():
    """camera pose (own frame) and intrinsics, for /spec"""
    out = []
    for name, (la, dist, az, el) in CAMS.items():
        a, e = math.radians(az), math.radians(el)
        fwd = np.array([math.cos(e) * math.cos(a), math.cos(e) * math.sin(a), math.sin(e)])
        pos = np.asarray(la) - dist * fwd
        right = np.cross(fwd, [0.0, 0.0, 1.0])
        right /= np.linalg.norm(right)
        up = np.cross(right, fwd)
        out.append(dict(name=name, pos=[round(float(x), 4) for x in pos], forward=[round(float(x), 5) for x in fwd],
                        right=[round(float(x), 5) for x in right], up=[round(float(x), 5) for x in up],
                        fovy_deg=FOVY, tile_px=list(TILE), focal_px=round(FOCAL, 2),
                        principal_point_px=[TILE[0] / 2, TILE[1] / 2],
                        model="pinhole: pixel u = cx + f (d.right)/(d.forward), v = cy - f (d.up)/(d.forward) for a "
                              "point at offset d from pos (u to the right, v down)"))
    return out


class Renderer:
    """Draws one seat's observation image from camera frames (qpos); owns its own MjData and GL context."""

    def __init__(self, seat: str, cache: int = 32):
        import mujoco as mj
        self.mj, self.seat = mj, seat
        self.m = m = mj.MjModel.from_xml_string(F.scene_xml(view=seat))
        self.d = mj.MjData(m)
        self.r = mj.Renderer(m, height=TILE[1], width=TILE[0])
        self.cams = []
        sg = F.SIGN[seat]
        for la, dist, az, el in CAMS.values():
            c = mj.MjvCamera()
            c.lookat[:] = (sg * la[0], sg * la[1], la[2])
            c.distance, c.azimuth, c.elevation = dist, az + (0.0 if seat == "A" else 180.0), el
            self.cams.append(c)
        self.cache: OrderedDict = OrderedDict()
        self.size = cache
        self.drawn = 0             # tiles actually rendered (the rest came from the cache)
        self.last = (None, None)   # (the frames' keys, the PNG) of the last image

    def tile(self, ci, snap):
        from PIL import Image, ImageDraw
        q = np.ascontiguousarray(snap["qpos"], dtype=np.float64)
        key = (ci, snap["label"], hashlib.sha1(q.tobytes()).hexdigest())
        if key in self.cache:
            self.cache.move_to_end(key)
            return self.cache[key]
        self.d.qpos[:] = q
        self.mj.mj_kinematics(self.m, self.d)
        self.r.update_scene(self.d, camera=self.cams[ci])
        im = Image.fromarray(self.r.render())
        ImageDraw.Draw(im).text((6, 4), snap["label"], fill=(255, 255, 255))
        img = np.asarray(im)
        self.drawn += 1
        self.cache[key] = img
        while len(self.cache) > self.size:
            self.cache.popitem(last=False)
        return img

    def render(self, snaps):
        """snaps: [{label, qpos}], oldest first -> PNG bytes"""
        from core.observe import png
        keys = tuple((sn["label"], hashlib.sha1(np.ascontiguousarray(sn["qpos"], dtype=np.float64).tobytes()).hexdigest())
                     for sn in snaps)
        if self.last[0] == keys:
            return self.last[1]
        rows = [np.concatenate([self.tile(ci, sn) for sn in snaps], axis=1) for ci in range(len(self.cams))]
        out = png(np.concatenate(rows, axis=0))
        self.last = (keys, out)
        return out


_HALF = {}


def half_turn(m, qpos):
    """the same pose turned by half a turn about the vertical through the centre of the piste: fencer A's joints become
    B's and B's A's, each floating base at (-x, -y, z) and turned by pi about z"""
    import mujoco as mj
    key = id(m)
    if key not in _HALF:
        pairs = []
        for j in range(m.njnt):
            nm = mj.mj_id2name(m, mj.mjtObj.mjOBJ_JOINT, j)
            if nm.startswith("A_"):
                jb = mj.mj_name2id(m, mj.mjtObj.mjOBJ_JOINT, "B_" + nm[2:])
                pairs.append((int(m.jnt_type[j]), int(m.jnt_qposadr[j]), int(m.jnt_qposadr[jb])))
        _HALF[key] = pairs
    q = np.asarray(qpos, float)
    out = q.copy()
    zpi = np.array([0.0, 0.0, 0.0, 1.0])
    for typ, a, b in _HALF[key]:
        for src, dst in ((a, b), (b, a)):
            if typ == mj.mjtJoint.mjJNT_FREE:
                out[dst:dst + 3] = (-q[src], -q[src + 1], q[src + 2])
                qq = np.zeros(4)
                mj.mju_mulQuat(qq, zpi, q[src + 3:src + 7])
                out[dst + 3:dst + 7] = qq
            else:
                out[dst] = q[src]
    return out
