"""Target archery with wind: deterministic arrow ballistics + MuJoCo scene / osmesa rendering.

Physics (pure Python floats, fixed-step RK4, no randomness except the seeded wind sequence and the seeded shot
execution scatter, so a recorded list of shots replays bit-exactly in any process):
  * the arrow is a point mass (m = 20 g, shaft diameter 5.5 mm) launched from LAUNCH (the arrow rest at the
    shooting line, 1.50 m above the ground) with speed V_FULL * DRAW along (elevation, azimuth);
  * forces: gravity and quadratic drag on the velocity RELATIVE TO THE AIR,
        a = -g z_hat - K |v - w| (v - w),   K = rho Cd A / (2 m),
    Cd = 1.5 on the shaft cross-section (Miyazaki et al. 2013, "Aerodynamic properties of an archery arrow",
    Sports Engineering 16: Cd ~ 1.5 with a turbulent boundary layer at Re ~ 1.5e4), rho = 1.2 kg/m^3;
  * wind w = (wx, wy, 0) is uniform over the range and constant during a flight; each end has its own seeded mean
    wind (crosswind and head/tailwind), each arrow a seeded gust on top. The windsocks show the wind of the arrow
    about to be shot;
  * the target face (World Archery 122 cm, 10 rings of 6.1 cm) is the vertical plane x = D, centre (D, 0, 1.30),
    on a 1.30 m square straw boss. The arrow scores the ring its shaft touches (line cutter counts the higher ring);
    X = inner 10. Outside the face, or missing the boss, it scores M (0).
MuJoCo (3.3.7) holds the scene (range, distance lines, windsock poles, boss + textured face, arrows as mocap bodies);
it is used for rendering only.
"""
from __future__ import annotations

import hashlib
import io
import json
import math
import os
import sys

import numpy as np

# ------------------------------------------------------------------------------------------------ constants
G = 9.81
RHO = 1.2                       # air density, kg/m^3 (assumed: 20 C, sea level)
CD = 1.5                        # drag coefficient on the cross-section (Miyazaki et al. 2013)
D_SHAFT = 0.0055                # arrow shaft diameter, m (assumed, typical carbon recurve arrow)
MASS = 0.020                    # arrow mass, kg (assumed, typical 18-22 g)
AREA = math.pi * D_SHAFT ** 2 / 4
K_DRAG = 0.5 * RHO * CD * AREA / MASS          # 1.07e-3 1/m
V_FULL = 68.0                   # launch speed at full draw (DRAW = 1), m/s (assumed, recurve ~ 60-70 m/s)
DRAW_MIN, DRAW_MAX = 0.5, 1.0
LAUNCH = (0.0, 0.0, 1.50)       # arrow rest at the shooting line
FACE_Z = 1.30                   # gold centre height (World Archery)
FACE_R = 0.61                   # 122 cm face
RING_W = 0.061                  # 10 rings of 6.1 cm
ARROW_R = D_SHAFT / 2
BOSS_H = 0.65                   # boss half size (1.30 m square), face centred on it
BOSS_T = 0.30                   # boss thickness
DT = 0.001
SIG_ELEV_DEG = 0.03             # execution scatter (seeded, published)
SIG_AZIM_DEG = 0.03
SIG_DRAW = 0.003                # relative, on the launch speed
DISTANCES = [50.0, 70.0, 70.0, 90.0]   # per end
ARROWS_PER_END = 3
N_ENDS = len(DISTANCES)
SOCK_FULL = 10.0                # a windsock stands horizontal at >= 10 m/s
SOCK_LEN = 1.2
BASE_SEED = 20260929
SEED = int(os.environ.get("ARCHERY_SEED", BASE_SEED))
TRAIL_DT = 1.0 / 30.0


def score_of(r: float) -> tuple[int, bool]:
    """(ring value, is_X) for an arrow whose centre is r metres from the gold centre (line cutter: the shaft touching
    a line scores the higher ring)."""
    re = r - ARROW_R
    if re > FACE_R:
        return 0, False
    if re <= RING_W / 2:
        return 10, True
    return max(1, 10 - int(math.floor(max(0.0, re) / RING_W))), False


def label(v: int, x: bool) -> str:
    return "X" if x else ("M" if v == 0 else str(v))


# ------------------------------------------------------------------------------------------------ wind
def make_winds(seed: int):
    """winds[e][a] = (wx, wy): wx along the range (+ = tailwind, blowing from the archer towards the target),
    wy across it (+ = blowing towards the archer's left). Per end a mean (crosswind 2-6 m/s of random sign,
    head/tailwind -3.5..+2.5 m/s); per arrow a gust N(0, 1.2) across and N(0, 0.8) along (|w| capped at 9 m/s)."""
    rng = np.random.default_rng([seed, 11])
    out, means = [], []
    for e in range(N_ENDS):
        cross = float(rng.uniform(2.0, 6.0)) * (1.0 if rng.uniform() < 0.5 else -1.0)
        along = float(rng.uniform(-3.5, 2.5))
        means.append((round(along, 3), round(cross, 3)))
        row = []
        for a in range(ARROWS_PER_END):
            g = np.random.default_rng([seed, 12, e, a]).standard_normal(2)
            wx, wy = along + 0.8 * float(g[0]), cross + 1.2 * float(g[1])
            s = math.hypot(wx, wy)
            if s > 9.0:
                wx, wy = wx * 9.0 / s, wy * 9.0 / s
            row.append((round(wx, 3), round(wy, 3)))
        out.append(row)
    return out, means


WINDS, WIND_MEANS = make_winds(SEED)


def shot_noise(e: int, a: int):
    z = np.random.default_rng([SEED, e, a]).standard_normal(3)
    return float(z[0]) * SIG_ELEV_DEG, float(z[1]) * SIG_AZIM_DEG, float(z[2]) * SIG_DRAW


# ------------------------------------------------------------------------------------------------ flight
def _acc(vx, vy, vz, wx, wy):
    rx, ry, rz = vx - wx, vy - wy, vz
    s = math.sqrt(rx * rx + ry * ry + rz * rz)
    return -K_DRAG * s * rx, -K_DRAG * s * ry, -G - K_DRAG * s * rz


def fly(D, elev_deg, azim_deg, speed, wind, trail=True):
    """Integrate one arrow. Returns dict(kind='boss'|'ground', hit=(x, y, z), vel, t, trail=[(t, x, y, z, vx, vy, vz)]).
    'boss': it reached the face plane x = D within the boss square; 'ground': it came down in the grass (short, or
    past/over the boss)."""
    el, az = math.radians(elev_deg), math.radians(azim_deg)
    x, y, z = LAUNCH
    vx = speed * math.cos(el) * math.cos(az)
    vy = speed * math.cos(el) * math.sin(az)
    vz = speed * math.sin(el)
    wx, wy = wind
    t = 0.0
    out = []
    next_tr = 0.0
    passed = False           # beyond the boss plane (missed the boss)
    while t < 12.0:
        if trail and t >= next_tr - 1e-12:
            out.append((round(t, 4), x, y, z, vx, vy, vz))
            next_tr += TRAIL_DT
        s0 = (x, y, z, vx, vy, vz)
        k1 = (vx, vy, vz) + _acc(vx, vy, vz, wx, wy)
        s = [s0[i] + 0.5 * DT * k1[i] for i in range(6)]
        k2 = (s[3], s[4], s[5]) + _acc(s[3], s[4], s[5], wx, wy)
        s = [s0[i] + 0.5 * DT * k2[i] for i in range(6)]
        k3 = (s[3], s[4], s[5]) + _acc(s[3], s[4], s[5], wx, wy)
        s = [s0[i] + DT * k3[i] for i in range(6)]
        k4 = (s[3], s[4], s[5]) + _acc(s[3], s[4], s[5], wx, wy)
        n = [s0[i] + DT / 6.0 * (k1[i] + 2 * k2[i] + 2 * k3[i] + k4[i]) for i in range(6)]
        if not passed and x < D <= n[0]:
            f = (D - x) / (n[0] - x)
            p = [s0[i] + f * (n[i] - s0[i]) for i in range(6)]
            if abs(p[1]) <= BOSS_H and abs(p[2] - FACE_Z) <= BOSS_H:
                t += f * DT
                if trail:
                    out.append((round(t, 4), *p))
                return dict(kind="boss", hit=(D, p[1], p[2]), vel=(p[3], p[4], p[5]), t=round(t, 4), trail=out)
            passed = True
        if n[2] <= 0.0:
            f = z / (z - n[2])
            p = [s0[i] + f * (n[i] - s0[i]) for i in range(6)]
            t += f * DT
            if trail:
                out.append((round(t, 4), *p))
            return dict(kind="ground", hit=(p[0], p[1], 0.0), vel=(p[3], p[4], p[5]), t=round(t, 4), trail=out,
                        passed=passed)
        x, y, z, vx, vy, vz = n
        t += DT
    return dict(kind="ground", hit=(x, y, 0.0), vel=(vx, vy, vz), t=round(t, 4), trail=out, passed=passed)


def miss_words(r, D):
    """What the spotter calls for an arrow that did not hit the face (no numbers)."""
    x, y, z = r["hit"]
    if r["kind"] == "boss":
        dz, dy = z - FACE_Z, y
    elif not r.get("passed"):
        return "short: it came down in the grass in front of the target"
    else:
        # where it crossed the target plane: re-derive from the trail
        dz, dy = 0.0, 0.0
        tr = r["trail"]
        for i in range(1, len(tr)):
            if tr[i - 1][1] < D <= tr[i][1]:
                f = (D - tr[i - 1][1]) / (tr[i][1] - tr[i - 1][1])
                dy = tr[i - 1][2] + f * (tr[i][2] - tr[i - 1][2])
                dz = tr[i - 1][3] + f * (tr[i][3] - tr[i - 1][3]) - FACE_Z
                break
    parts = []
    if abs(dz) > 0.3 * max(abs(dy), 1e-9) or abs(dz) > BOSS_H:
        parts.append("high" if dz > 0 else "low")
    if abs(dy) > 0.3 * max(abs(dz), 1e-9) or abs(dy) > BOSS_H:
        parts.append("left" if dy > 0 else "right")
    where = " and ".join(parts) or "wide"
    if r["kind"] == "boss":
        return f"on the boss but off the face ({where})"
    return f"missed the boss, passed {where} of it"


class Round:
    """The round: end, arrow, scores. shoot(elev, azim, draw) plays one arrow."""

    def __init__(self):
        self.end = 0
        self.arrow = 0                   # arrows shot in the current end
        self.scores = [[] for _ in range(N_ENDS)]    # ring values
        self.xs = [[] for _ in range(N_ENDS)]
        self.log = []
        self.stuck = []                  # this end's arrows: (hit, vel) for rendering
        self.done = False
        self.last = None

    def D(self):
        return DISTANCES[self.end]

    def shoot(self, elev_deg, azim_deg, draw):
        e, a = self.end, self.arrow
        ne, na, nd = shot_noise(e, a)
        el, az = elev_deg + ne, azim_deg + na
        v = V_FULL * draw * (1.0 + nd)
        w = WINDS[e][a]
        r = fly(DISTANCES[e], el, az, v, w)
        if r["kind"] == "boss":
            rr = math.hypot(r["hit"][1], r["hit"][2] - FACE_Z)
            val, isx = score_of(rr)
        else:
            rr, val, isx = None, 0, False
        call = label(val, isx)
        where = None if val > 0 else miss_words(r, DISTANCES[e])
        self.scores[e].append(val)
        self.xs[e].append(isx)
        rec = dict(end=e + 1, arrow=a + 1, distance_m=DISTANCES[e], elev_deg=elev_deg, azim_deg=azim_deg, draw=draw,
                   executed_elev_deg=el, executed_azim_deg=az, launch_speed=v, wind=w, kind=r["kind"],
                   hit=r["hit"], r_m=rr, score=val, call=call, miss=where, flight_s=r["t"])
        self.log.append(rec)
        self.stuck.append((r["hit"], r["vel"], r["kind"]))
        self.last = dict(rec, trail=r["trail"])
        self.arrow += 1
        rec["end_finished"] = False
        if self.arrow >= ARROWS_PER_END:
            rec["end_finished"] = True
            rec["end_score"] = sum(self.scores[e])
            self.next_end()
        return rec, r

    def next_end(self):
        self.end += 1
        self.arrow = 0
        if self.end >= N_ENDS:
            self.done = True
            self.end = N_ENDS - 1
            return
        self.stuck = []
        self.last = None

    def total(self):
        return sum(sum(s) for s in self.scores)

    def n_x(self):
        return sum(sum(1 for v in x if v) for x in self.xs)

    def state_sha(self):
        s = json.dumps([[r["end"], r["arrow"], repr(r["hit"][0]), repr(r["hit"][1]), repr(r["hit"][2]), r["call"]]
                        for r in self.log] + [self.scores, self.end, self.arrow, self.done])
        return hashlib.sha256(s.encode()).hexdigest()


# ------------------------------------------------------------------------------------------------ scene
ARCHER_W, ARCHER_H, FOVY_ARCHER = 1000, 600, 24.0
ARCHER_POS, ARCHER_PITCH = (-1.2, -0.25, 1.65), 0.0
SCOPE_W = SCOPE_H = 600
SIDE_W, SIDE_H, FOVY_SIDE = 800, 500, 22.0
SIDE_OFF, SIDE_Z, SIDE_PITCH = 12.0, 2.4, 3.0
CLOSE_W = CLOSE_H = 600
CLOSE_BACK = 10.0
POLE_Y, POLE_H = 3.5, 4.0            # windsock poles along the range, left side (y = +3.5)
TPOLE_Y, TPOLE_H, TSOCK_SCALE = 1.1, 3.1, 0.6   # the windsock beside the target
ARROW_COLS = [(1.0, 0.1, 0.9), (0.35, 1.0, 0.1), (0.1, 0.95, 1.0)]   # fletching / nock: arrow 1 magenta, 2 lime, 3 cyan


def sock_x(D):
    return [round(D * f, 3) for f in (0.25, 0.5, 0.75)]


def scope_fovy(D):
    return 2 * math.degrees(math.atan(1.8 / D))


def scope_pitch(D):
    return math.degrees(math.atan2(FACE_Z - LAUNCH[2], D))


def close_fovy():
    return 2 * math.degrees(math.atan(0.72 / CLOSE_BACK))


def sock_angles(w):
    """(heading of the sock = downwind direction, deg; droop below horizontal, deg)."""
    wx, wy = w
    s = math.hypot(wx, wy)
    head = math.degrees(math.atan2(wy, wx)) if s > 1e-6 else 0.0
    droop = 90.0 * (1.0 - min(s / SOCK_FULL, 1.0))
    return head, droop


def _quat_yaw_pitch(yaw_deg, pitch_down_deg):
    """Rotation: yaw about z, then pitch about the new y by pitch_down (local +x tipped downwards)."""
    cy, sy = math.cos(math.radians(yaw_deg) / 2), math.sin(math.radians(yaw_deg) / 2)
    cp, sp = math.cos(math.radians(pitch_down_deg) / 2), math.sin(math.radians(pitch_down_deg) / 2)
    # q = qz * qy
    return [cy * cp, -sy * sp, cy * sp, sy * cp]


def _quat_dir(v):
    """Quaternion taking local +x to the direction v."""
    vx, vy, vz = v
    s = math.sqrt(vx * vx + vy * vy + vz * vz)
    yaw = math.degrees(math.atan2(vy, vx))
    pitch_down = -math.degrees(math.asin(max(-1.0, min(1.0, vz / s))))
    return _quat_yaw_pitch(yaw, pitch_down)


def _face_png():
    from PIL import Image
    n = 1024
    half = BOSS_H                   # the texture covers the boss's front (1.30 m square)
    px = (np.arange(n) + 0.5) / n * 2 * half - half
    X, Y = np.meshgrid(px, -px)     # row 0 = top
    r = np.hypot(X, Y)
    img = np.zeros((n, n, 3), np.float32)
    img[:] = (196, 170, 110)        # straw
    cols = {1: (245, 245, 245), 2: (245, 245, 245), 3: (25, 25, 25), 4: (25, 25, 25), 5: (30, 150, 220),
            6: (30, 150, 220), 7: (225, 35, 35), 8: (225, 35, 35), 9: (250, 215, 40), 10: (250, 215, 40)}
    for ring in range(1, 11):
        ro = FACE_R - (ring - 1) * RING_W
        img[r <= ro] = cols[ring]
    lw = 0.0015
    for ring in range(1, 11):
        ro = FACE_R - (ring - 1) * RING_W
        line = (255, 255, 255) if ring in (3, 4) else (20, 20, 20)
        img[np.abs(r - ro) < lw] = line
    img[np.abs(r - RING_W / 2) < lw * 0.8] = (20, 20, 20)            # X ring
    img[(np.abs(X) < 0.004) & (np.abs(Y) < 0.0008)] = (20, 20, 20)    # centre cross
    img[(np.abs(Y) < 0.004) & (np.abs(X) < 0.0008)] = (20, 20, 20)
    b = io.BytesIO()
    Image.fromarray(img.astype(np.uint8)).save(b, format="PNG")
    return b.getvalue()


def _grass_png():
    from PIL import Image
    n = 256
    rng = np.random.default_rng(5)
    base = np.array([70, 130, 55], np.float32)
    img = base[None, None, :] * (0.9 + 0.2 * rng.random((n, n, 1)))
    b = io.BytesIO()
    Image.fromarray(np.clip(img, 0, 255).astype(np.uint8)).save(b, format="PNG")
    return b.getvalue()


def _sock_body(name, pos, scale):
    L = SOCK_LEN * scale
    nseg = 5
    geoms = []
    for i in range(nseg):
        x0, x1 = i * L / nseg, (i + 1) * L / nseg
        r = scale * (0.16 - 0.08 * (i + 0.5) / nseg)
        col = "1 0.45 0.05 1" if i % 2 == 0 else "0.97 0.97 0.97 1"
        geoms.append(f'<geom type="cylinder" fromto="{x0:.4f} 0 0 {x1:.4f} 0 0" size="{r:.4f}" rgba="{col}"/>')
    geoms.append(f'<geom type="cylinder" fromto="-0.01 0 0 0.01 0 0" size="{scale * 0.17:.4f}" rgba="0.2 0.2 0.2 1"/>')
    return (f'<body name="{name}" mocap="true" pos="{pos[0]} {pos[1]} {pos[2]}">' + "".join(geoms) + "</body>")


def _arrow_body(name, col):
    c = " ".join(f"{v:g}" for v in col)
    # local +x = flight direction, tip at the origin; visible shaft 0.60 m behind the tip (the point is 5 cm in)
    return (f'<body name="{name}" mocap="true" pos="0 0 -50">'
            f'<geom type="cylinder" fromto="-0.60 0 0 0.05 0 0" size="{ARROW_R * 1.3:.4f}" rgba="0.08 0.08 0.1 1"/>'
            f'<geom type="box" pos="-0.52 0 0.012" size="0.05 0.0008 0.012" rgba="{c} 1"/>'
            f'<geom type="box" pos="-0.52 -0.0104 -0.006" size="0.05 0.0008 0.012" euler="120 0 0" rgba="{c} 1"/>'
            f'<geom type="box" pos="-0.52 0.0104 -0.006" size="0.05 0.0008 0.012" euler="-120 0 0" rgba="{c} 1"/>'
            f'<geom type="sphere" pos="-0.60 0 0" size="0.012" rgba="{c} 1"/>'
            "</body>")


def scene_xml(D):
    lines = []
    for xm in range(0, int(D) + 1, 10):
        w = 0.08 if xm in (0, int(D)) else 0.04
        lines.append(f'<geom type="box" pos="{xm} 0 0.001" size="{w} 6 0.001" rgba="0.95 0.95 0.95 1"/>')
    poles = []
    for xs in sock_x(D):
        poles.append(f'<geom type="cylinder" fromto="{xs} {POLE_Y} 0 {xs} {POLE_Y} {POLE_H}" size="0.03" '
                     f'rgba="0.85 0.85 0.85 1"/>')
    poles.append(f'<geom type="cylinder" fromto="{D} {TPOLE_Y} 0 {D} {TPOLE_Y} {TPOLE_H}" size="0.02" '
                 f'rgba="0.85 0.85 0.85 1"/>')
    socks = [_sock_body(f"sock{i}", (xs, POLE_Y, POLE_H), 1.0) for i, xs in enumerate(sock_x(D))]
    socks.append(_sock_body("sock3", (D, TPOLE_Y, TPOLE_H), TSOCK_SCALE))
    arrows = [_arrow_body(f"arrow{i}", ARROW_COLS[i]) for i in range(3)] + [_arrow_body("flying", (1.0, 0.5, 0.0))]
    h = BOSS_H
    return f"""
<mujoco model="archery">
  <visual><global offwidth="1600" offheight="1000"/><quality shadowsize="4096"/>
    <headlight ambient="0.35 0.35 0.35" diffuse="0.25 0.25 0.25" specular="0 0 0"/><map znear="0.02" zfar="50"/></visual>
  <statistic extent="10" center="{D / 2} 0 1"/>
  <asset>
    <texture name="sky" type="skybox" builtin="gradient" rgb1="0.5 0.7 0.95" rgb2="0.95 0.97 1.0" width="256" height="256"/>
    <texture name="grass" type="2d" file="grass.png"/>
    <texture name="face" type="2d" file="face.png"/>
    <material name="grass" texture="grass" texrepeat="120 120" specular="0"/>
    <material name="face" texture="face" specular="0.02"/>
    <mesh name="face" vertex="0 {h} {-h}  0 {-h} {-h}  0 {-h} {h}  0 {h} {h}  0.004 {h} {-h}  0.004 {-h} {-h}  0.004 {-h} {h}  0.004 {h} {h}"
          texcoord="0 0  1 0  1 1  0 1  0 0  1 0  1 1  0 1" face="0 1 2  0 2 3" inertia="shell"/>
  </asset>
  <worldbody>
    <light directional="true" pos="0 0 10" dir="0.35 0.3 -0.8" diffuse="0.8 0.8 0.75" castshadow="false"/>
    <geom type="plane" size="200 200 0.1" pos="{D / 2} 0 0" material="grass"/>
    {''.join(lines)}
    {''.join(poles)}
    <geom type="box" pos="{D + BOSS_T / 2 + 0.008} 0 {FACE_Z}" size="{BOSS_T / 2} {h} {h}" rgba="0.77 0.67 0.43 1"/>
    <geom type="mesh" mesh="face" material="face" pos="{D - 0.002} 0 {FACE_Z}" contype="0" conaffinity="0"/>
    <geom type="box" pos="{D + 0.25} 0.5 {(FACE_Z - h) / 2}" size="0.04 0.04 {(FACE_Z - h) / 2}" rgba="0.45 0.3 0.15 1"/>
    <geom type="box" pos="{D + 0.25} -0.5 {(FACE_Z - h) / 2}" size="0.04 0.04 {(FACE_Z - h) / 2}" rgba="0.45 0.3 0.15 1"/>
    <geom type="box" pos="-0.4 -0.25 0.6" size="0.02 0.02 0.6" rgba="0.3 0.3 0.35 1"/>
    {''.join(socks)}
    {''.join(arrows)}
  </worldbody>
</mujoco>"""


class Views:
    """Renders the decision views for an end's distance (MuJoCo, osmesa)."""

    def __init__(self):
        self.models = {}
        self.renderers = {}

    def model(self, D):
        import mujoco as mj
        if D not in self.models:
            m = mj.MjModel.from_xml_string(scene_xml(D), assets={"face.png": _face_png(), "grass.png": _grass_png()})
            d = mj.MjData(m)
            self.models[D] = (m, d)
        return self.models[D]

    def renderer(self, D, w, h):
        import mujoco as mj
        key = (D, w, h)
        if key not in self.renderers:
            m, _ = self.model(D)
            self.renderers[key] = mj.Renderer(m, height=h, width=w)
        return self.renderers[key]

    @staticmethod
    def cam(pos, yaw_deg, pitch_deg):
        import mujoco as mj
        c = mj.MjvCamera()
        dist = 1.0
        fw = np.array([math.cos(math.radians(pitch_deg)) * math.cos(math.radians(yaw_deg)),
                       math.cos(math.radians(pitch_deg)) * math.sin(math.radians(yaw_deg)),
                       math.sin(math.radians(pitch_deg))])
        c.lookat[:] = np.asarray(pos) + dist * fw
        c.distance = dist
        c.azimuth = yaw_deg
        c.elevation = pitch_deg
        return c

    def set_state(self, D, wind, stuck, flying=None):
        """Windsocks for `wind`; stuck = [(hit, vel, kind)] of this end's arrows; flying = (pos, vel) or None."""
        import mujoco as mj
        m, d = self.model(D)
        head, droop = sock_angles(wind)
        q = _quat_yaw_pitch(head, droop)
        for i in range(4):
            d.mocap_quat[i] = q
        for i in range(3):
            if i < len(stuck):
                hit, vel, kind = stuck[i]
                d.mocap_pos[4 + i] = hit
                d.mocap_quat[4 + i] = _quat_dir(vel)
            else:
                d.mocap_pos[4 + i] = [0, 0, -50]
        if flying is not None:
            d.mocap_pos[7] = flying[0]
            d.mocap_quat[7] = _quat_dir(flying[1])
        else:
            d.mocap_pos[7] = [0, 0, -50]
        mj.mj_forward(m, d)

    def _shot(self, D, w, h, fovy, pos, yaw, pitch):
        m, d = self.model(D)
        r = self.renderer(D, w, h)
        m.vis.global_.fovy = fovy
        r.update_scene(d, camera=self.cam(pos, yaw, pitch))
        im = r.render().copy()
        m.vis.global_.fovy = 45.0
        return im

    def render(self, D, wind, stuck):
        """dict name -> RGB uint8: archer, scope, side, target."""
        self.set_state(D, wind, stuck)
        return {
            "archer": self._shot(D, ARCHER_W, ARCHER_H, FOVY_ARCHER, ARCHER_POS, 0.0, ARCHER_PITCH),
            "scope": self._shot(D, SCOPE_W, SCOPE_H, scope_fovy(D), LAUNCH, 0.0, scope_pitch(D)),
            "side": self._shot(D, SIDE_W, SIDE_H, FOVY_SIDE, (D / 2, -SIDE_OFF, SIDE_Z), 90.0, SIDE_PITCH),
            "target": self._shot(D, CLOSE_W, CLOSE_H, close_fovy(), (D - CLOSE_BACK, 0.0, FACE_Z), 0.0, 0.0),
        }

    def tv(self, D, look, yaw, elev, dist, w=960, h=544, fovy=45.0):
        import mujoco as mj
        m, d = self.model(D)
        r = self.renderer(D, w, h)
        m.vis.global_.fovy = fovy
        c = mj.MjvCamera()
        c.lookat[:] = look
        c.distance = dist
        c.azimuth = yaw
        c.elevation = elev
        r.update_scene(d, camera=c)
        im = r.render().copy()
        m.vis.global_.fovy = 45.0
        return im


def spec_cameras():
    def f(h, fovy):
        return round(h / 2 / math.tan(math.radians(fovy / 2)), 2)
    return {
        "archer": {"tile_px": [ARCHER_W, ARCHER_H], "fovy_deg": FOVY_ARCHER, "focal_px": f(ARCHER_H, FOVY_ARCHER),
                   "pose": f"at {list(ARCHER_POS)} (just behind and left of the bow), looking along +x (down the range), "
                           f"pitch {ARCHER_PITCH} deg, no roll. Image left = +y"},
        "scope": {"tile_px": [SCOPE_W, SCOPE_H], "fovy_deg": "2 atan(1.8 m / D) (per end, see ends[].scope_fovy_deg)",
                  "pose": "at the arrow rest (0, 0, 1.50), looking at the gold centre (D, 0, 1.30): heading 0 deg, "
                          "pitched down atan(0.20 / D); image centre = gold centre, image left = +y"},
        "side": {"tile_px": [SIDE_W, SIDE_H], "fovy_deg": FOVY_SIDE, "focal_px": f(SIDE_H, FOVY_SIDE),
                 "pose": f"at (D/2, -{SIDE_OFF}, {SIDE_Z}) (right of the range, level with the middle windsock), looking "
                         f"along +y (across the range, heading +90 deg), pitched {SIDE_PITCH} deg up. Image right = +x "
                         f"(towards the target)"},
        "target": {"tile_px": [CLOSE_W, CLOSE_H], "fovy_deg": round(close_fovy(), 4), "focal_px": f(CLOSE_H, close_fovy()),
                   "pose": f"a spotting-scope close-up: at (D - {CLOSE_BACK}, 0, {FACE_Z}), looking along +x at the gold "
                           f"centre, no roll (image centre = gold centre, image left = +y). It shows this end's arrows: "
                           f"nock and fletching magenta = arrow 1, lime = arrow 2, cyan = arrow 3 of the end"},
        "pinhole": "square pixels, principal point at the image centre",
    }


def spec_ends():
    return [{"end": e + 1, "distance_m": D, "arrows": ARROWS_PER_END,
             "windsock_x_m": sock_x(D) + [D], "scope_fovy_deg": round(scope_fovy(D), 4)}
            for e, D in enumerate(DISTANCES)]


def cameras_numeric(D):
    """The decision cameras' poses for an end at distance D, as numbers: position, forward / right / up axes, focal
    length and principal point in pixels (pinholes, square pixels)."""
    def cam(name, w, h, fovy, pos, yaw, pitch):
        y, p = math.radians(yaw), math.radians(pitch)
        fw = [math.cos(p) * math.cos(y), math.cos(p) * math.sin(y), math.sin(p)]
        right = [math.sin(y), -math.cos(y), 0.0]
        up = [-math.sin(p) * math.cos(y), -math.sin(p) * math.sin(y), math.cos(p)]
        return {"name": name, "tile_px": [w, h], "fovy_deg": round(fovy, 6), "pos": [round(float(v), 6) for v in pos],
                "forward": [round(v, 9) for v in fw], "right": [round(v, 9) for v in right],
                "up": [round(v, 9) for v in up], "focal_px": round(h / 2 / math.tan(math.radians(fovy / 2)), 4),
                "principal_point_px": [w / 2, h / 2]}
    return [cam("archer", ARCHER_W, ARCHER_H, FOVY_ARCHER, ARCHER_POS, 0.0, ARCHER_PITCH),
            cam("scope", SCOPE_W, SCOPE_H, scope_fovy(D), LAUNCH, 0.0, scope_pitch(D)),
            cam("side", SIDE_W, SIDE_H, FOVY_SIDE, (D / 2, -SIDE_OFF, SIDE_Z), 90.0, SIDE_PITCH),
            cam("target", CLOSE_W, CLOSE_H, close_fovy(), (D - CLOSE_BACK, 0.0, FACE_Z), 0.0, 0.0)]


def sock_tops(D):
    """Where the windsocks hang (their mouths): three on 4 m poles left of the range, the small one by the target."""
    return [[x, POLE_Y, POLE_H] for x in sock_x(D)] + [[D, TPOLE_Y, TPOLE_H]]


# The observation is one PNG: the four cameras as tiles (x, y, width, height) on a dark canvas.
TILES = {"archer": [0, 0, ARCHER_W, ARCHER_H], "scope": [ARCHER_W, 0, SCOPE_W, SCOPE_H],
         "side": [0, ARCHER_H, SIDE_W, SIDE_H], "target": [ARCHER_W, ARCHER_H, CLOSE_W, CLOSE_H]}
CANVAS = (ARCHER_W + SCOPE_W, ARCHER_H + CLOSE_H)


def compose(images: dict) -> bytes:
    """One PNG of the decision views (Views.render) laid out as TILES."""
    from PIL import Image
    cv = Image.new("RGB", CANVAS, (18, 18, 22))
    for name, (x, y, w, h) in TILES.items():
        cv.paste(Image.fromarray(images[name]), (x, y))
    b = io.BytesIO()
    cv.save(b, format="PNG")
    return b.getvalue()


def replay(shots):
    c = Round()
    for s in shots:
        assert c.end + 1 == s["end"] and c.arrow + 1 == s["arrow"] and not c.done, (c.end, c.arrow, s)
        c.shoot(s["elev_deg"], s["azim_deg"], s["draw"])
    return c


def render_video(shots, out, fps=30):
    """Replay video: per arrow, the archer's view (windsocks) for 0.6 s, the flight followed from behind and above
    (camera 2.2 m behind and above it, real time), then the spotting-scope close-up for 1.2 s; a scoreboard line."""
    import imageio.v2 as imageio
    from PIL import Image, ImageDraw
    v = Views()
    c = Round()
    w = imageio.get_writer(out, fps=fps, macro_block_size=8)

    def put(im, txt):
        im = Image.fromarray(im)
        if im.size != (960, 544):
            im = im.resize((960, 544))
        dr = ImageDraw.Draw(im)
        dr.rectangle([0, 0, im.width, 26], fill=(0, 0, 0))
        dr.text((8, 7), txt, fill=(255, 255, 255))
        w.append_data(np.asarray(im))

    for s in shots:
        e, a = c.end, c.arrow
        D = DISTANCES[e]
        wind = WINDS[e][a]
        so_far = c.total()
        hdr = f"End {e + 1} ({D:g} m)  arrow {a + 1}   total before: {so_far}"
        stuck = list(c.stuck)
        v.set_state(D, wind, stuck)
        im = v._shot(D, 960, 544, FOVY_ARCHER, ARCHER_POS, 0.0, ARCHER_PITCH)
        for _ in range(int(fps * 0.6)):
            put(im, hdr + f"   elev {s['elev_deg']:.3f} azim {s['azim_deg']:+.3f} draw {s['draw']:.3f}")
        rec, r = c.shoot(s["elev_deg"], s["azim_deg"], s["draw"])
        for tr in r["trail"]:
            p, vel = tr[1:4], tr[4:7]
            v.set_state(D, wind, stuck, flying=(p, vel))
            look = (p[0], p[1], p[2])
            put(v.tv(D, look, 12.0, -8.0, 2.2), hdr + "   in flight")
        stuck2 = stuck + [(r["hit"], r["vel"], r["kind"])]
        v.set_state(D, wind, stuck2)
        im = v._shot(D, 960, 544, close_fovy() * 1.0, (D - CLOSE_BACK, 0.0, FACE_Z), 0.0, 0.0)
        for _ in range(int(fps * 1.2)):
            put(im, hdr + f"   -> {rec['call']}" + (f" ({rec['miss']})" if rec["miss"] else ""))
    w.close()


# ------------------------------------------------------------------------------------------------ duel
SEATS = ("A", "B")
OTHER = {"A": "B", "B": "A"}
SHOOTOFF_D = 70.0


def shootoff_wind(i: int):
    """The wind of shoot-off arrow pair i (the same for both players): an end mean and a gust, as in make_winds."""
    rng = np.random.default_rng([SEED, 77, i])
    cross = float(rng.uniform(2.0, 6.0)) * (1.0 if rng.uniform() < 0.5 else -1.0)
    along = float(rng.uniform(-3.5, 2.5))
    g = rng.standard_normal(2)
    wx, wy = along + 0.8 * float(g[0]), cross + 1.2 * float(g[1])
    sp = math.hypot(wx, wy)
    if sp > 9.0:
        wx, wy = wx * 9.0 / sp, wy * 9.0 / sp
    return round(wx, 3), round(wy, 3)


class Duel:
    """Two archers on identical lanes (the same wind for the n-th arrow of either player, the same scatter draws).
    4 ends x 3 arrows (50, 70, 70, 90 m); in each end one player shoots its 3 arrows, then the other: FIRST shoots
    first in ends 1 and 3, the other player in ends 2 and 4. Highest total wins (cumulative, as in compound match play,
    WA 12.1.4.3); a tie goes to shoot-off arrows (WA 12.5.2.2): one arrow each at 70 m (FIRST first), the higher score
    wins, then the arrow nearer the centre; tied pairs are repeated until the tie is broken."""

    def __init__(self, first: str):
        assert first in SEATS
        self.first = first
        self.rounds = {s: Round() for s in SEATS}
        self.shootoff = []                    # [{seat, pair, ...}]
        self.decisions = []
        self.done = False
        self.winner = None
        self.reason = None
        self.forfeit = None

    def end_order(self, e: int):
        a = self.first if e % 2 == 0 else OTHER[self.first]
        return a, OTHER[a]

    @property
    def phase(self):
        return "shootoff" if all(self.rounds[s].done for s in SEATS) else "round"

    @property
    def turn(self):
        if self.done:
            return None
        if self.phase == "round":
            shot = {x: sum(len(v) for v in self.rounds[x].scores) for x in SEATS}
            e = min(shot.values()) // ARROWS_PER_END
            a, b = self.end_order(e)
            return a if shot[a] < ARROWS_PER_END * (e + 1) else b
        n = len(self.shootoff)
        return self.first if n % 2 == 0 else OTHER[self.first]

    def shooting(self, seat: str):
        """(distance, wind, end index, arrow index) of `seat`'s next arrow."""
        if self.phase == "round":
            r = self.rounds[seat]
            return DISTANCES[r.end], WINDS[r.end][r.arrow], r.end, r.arrow
        pair = len(self.shootoff) // 2
        return SHOOTOFF_D, shootoff_wind(pair), N_ENDS, pair

    def shoot(self, seat: str, elev: float, azim: float, draw: float) -> dict:
        assert not self.done and seat == self.turn, (seat, self.turn)
        self.decisions.append({"seat": seat, "elev_deg": elev, "azim_deg": azim, "draw": draw})
        if self.phase == "round":
            r = self.rounds[seat]
            rec, fl = r.shoot(elev, azim, draw)
            rec = dict(rec, seat=seat)
            if all(self.rounds[s].done for s in SEATS):
                self._compare()
            return dict(rec, _flight=fl)
        pair = len(self.shootoff) // 2
        w = shootoff_wind(pair)
        z = np.random.default_rng([SEED, 78, pair]).standard_normal(3)
        el, az = elev + float(z[0]) * SIG_ELEV_DEG, azim + float(z[1]) * SIG_AZIM_DEG
        v = V_FULL * draw * (1.0 + float(z[2]) * SIG_DRAW)
        fl = fly(SHOOTOFF_D, el, az, v, w)
        if fl["kind"] == "boss":
            rr = math.hypot(fl["hit"][1], fl["hit"][2] - FACE_Z)
            val, isx = score_of(rr)
        else:
            rr, val, isx = None, 0, False
        rec = dict(seat=seat, end=N_ENDS + 1, arrow=pair + 1, shootoff=True, distance_m=SHOOTOFF_D, elev_deg=elev,
                   azim_deg=azim, draw=draw, executed_elev_deg=el, executed_azim_deg=az, launch_speed=v, wind=w,
                   kind=fl["kind"], hit=fl["hit"], r_m=rr, score=val, call=label(val, isx),
                   miss=None if val > 0 else miss_words(fl, SHOOTOFF_D), flight_s=fl["t"])
        self.shootoff.append(rec)
        if len(self.shootoff) % 2 == 0:
            a, b = self.shootoff[-2], self.shootoff[-1]
            ka = (a["score"], -(a["r_m"] if a["r_m"] is not None else 9.0))
            kb = (b["score"], -(b["r_m"] if b["r_m"] is not None else 9.0))
            if ka != kb:
                self.done, self.winner, self.reason = True, (a["seat"] if ka > kb else b["seat"]), "match_over"
        return dict(rec, _flight=fl)

    def _compare(self):
        ta, tb = self.rounds["A"].total(), self.rounds["B"].total()
        if ta != tb:
            self.done, self.winner, self.reason = True, "A" if ta > tb else "B", "match_over"

    def lose(self, seat: str, why: str):
        if not self.done:
            self.forfeit = {"seat": seat, "why": why}
            self.decisions.append({"seat": seat, "forfeit": why})
            self.done, self.winner, self.reason = True, OTHER[seat], why

    def replay(self, decisions):
        for d in decisions:
            if "forfeit" in d:
                self.lose(d["seat"], d["forfeit"])
            else:
                self.shoot(d["seat"], d["elev_deg"], d["azim_deg"], d["draw"])

    def totals(self):
        return {s: self.rounds[s].total() for s in SEATS}

    def state_sha(self):
        s = json.dumps([self.rounds[x].state_sha() for x in SEATS] + [
            [r["seat"], repr(r["hit"][0]), repr(r["hit"][1]), repr(r["hit"][2]), r["call"]] for r in self.shootoff]
            + [self.winner, self.reason, self.forfeit])
        return hashlib.sha256(s.encode()).hexdigest()


if __name__ == "__main__":
    if sys.argv[1:2] == ["replay_duel"]:
        tr = json.load(open(sys.argv[2]))
        m = Duel(tr["first_player"])
        m.replay(tr["decisions"])
        print(json.dumps({"sha": m.state_sha(), "totals": m.totals(), "winner": m.winner, "reason": m.reason,
                          "done": m.done}))
    elif sys.argv[1:2] == ["replay"]:
        tr = json.load(open(sys.argv[2]))
        c = replay(tr["shots"])
        print(json.dumps({"sha": c.state_sha(), "scores": c.scores, "total": c.total(), "n_x": c.n_x(),
                          "done": c.done, "end": c.end, "arrow": c.arrow}))
