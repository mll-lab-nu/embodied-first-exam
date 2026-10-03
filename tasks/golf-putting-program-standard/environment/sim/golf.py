"""Mini-golf putting course: deterministic putting physics + MuJoCo scene / osmesa rendering.

Physics (pure Python floats, fixed step, no randomness except the seeded stroke scatter, so a recorded list of
strokes replays bit-exactly in any process):
  * the green of each hole is a smooth height field z = h(x, y) (planar tilt + Gaussian bumps/bowls + ridges),
    bounded by straight walls (mini-golf), with optional rectangular obstacle blocks;
  * the ball (golf ball, r = 21.35 mm) rolls without slipping: a = -(5/7) g grad h - c v/|v|, with the rolling
    resistance c = V0^2 / (2 D_STIMP) (stimpmeter: a ball rolled at 1.83 m/s on the flat stops after 3.05 m = 10 ft);
    it comes to rest when |v| is tiny and the slope cannot move it;
  * walls: circle-vs-segment collisions, restitution 0.7 normal, 0.92 tangential;
  * the cup (r = 54 mm): while the ball centre is over the cup the ball is unsupported and falls; when it reaches
    the far wall of the cup (centre at R_cup - r_ball, moving outwards) it is holed if it has dropped by more than
    0.6 r_ball (so a centred putt drops up to ~1.7 m/s); otherwise it rides over the lip, losing radial speed
    (a lip-out, often deflected around the cup).
MuJoCo (3.3.7) holds the scene: a textured mesh of the green (0.5 m grid lines), walls, blocks, cup, flagstick,
ball (mocap). It is used for rendering only.
"""
from __future__ import annotations

import hashlib
import io
import json
import math
import os
import sys

import numpy as np

G = 9.81
R_BALL = 0.02135
R_CUP = 0.054
V_STIMP, D_STIMP = 1.83, 3.05
C_ROLL = V_STIMP ** 2 / (2 * D_STIMP)          # 0.549 m/s^2 rolling-resistance deceleration
DT = 0.002
MAX_T = 40.0
HOLE_DROP = 0.6 * R_BALL
E_N, E_T = 0.7, 0.92
AIM_SIGMA_DEG, SPEED_SIGMA = 0.3, 0.015      # stroke execution scatter (seeded)
MAX_STROKES = 6                              # not holed after 6 strokes: pick up, the hole scores 7
BASE_SEED = 20260928                         # the original course (holes as designed below)
SEED = int(os.environ.get("GOLF_SEED", BASE_SEED))   # course layout + stroke scatter
TRAIL_DT = 1.0 / 30.0

# Holes: green x in [0, L], y in [-W/2, W/2]; heights in metres.
#   tilt (sx, sy): h += sx x + sy y
#   bumps: (x0, y0, amp, sigma_x, sigma_y)
#   ridges: (x0, y0, theta_deg, amp, sigma): h += amp exp(-u^2 / 2 sigma^2), u = (p - p0) . (cos t, sin t)
#   blocks: (x0, x1, y0, y1) rectangular obstacles (0.12 m tall)
BASE_HOLES = [
    dict(name="Hole 1", par=2, L=8.0, W=3.0, ball=(1.0, 0.2), cup=(6.6, -0.35), tilt=(0.012, 0.03),
         bumps=[], ridges=[], blocks=[]),
    dict(name="Hole 2", par=2, L=9.0, W=3.5, ball=(1.0, -1.1), cup=(7.9, 0.1), tilt=(-0.008, -0.015),
         bumps=[(4.6, -0.4, 0.09, 1.3, 1.1)], ridges=[], blocks=[]),
    dict(name="Hole 3", par=2, L=10.0, W=4.0, ball=(1.0, 1.0), cup=(8.8, -0.6), tilt=(0.0, -0.018),
         bumps=[(6.6, 0.25, 0.05, 0.8, 0.8)], ridges=[(4.4, 0.0, 15.0, 0.07, 0.9)], blocks=[]),
    dict(name="Hole 4", par=3, L=10.0, W=4.0, ball=(1.0, -0.3), cup=(8.6, 0.25), tilt=(0.0, 0.012),
         bumps=[(8.6, 0.25, -0.035, 1.0, 1.0)], ridges=[], blocks=[(4.7, 5.3, -1.1, 1.1)]),
]


def make_holes(seed):
    """The course for a seed: BASE_SEED is the original course; any other seed moves the ball and the cup, varies the
    tilts (magnitude and the side slope's sign), moves and scales the bumps, turns the ridge. Same holes, same pars,
    same features (hole 4 keeps its block across the middle and its hollow around the cup)."""
    import copy
    holes = copy.deepcopy(BASE_HOLES)
    if seed == BASE_SEED:
        return holes
    rng = np.random.default_rng([seed, 99])
    u = lambda a, b: float(rng.uniform(a, b))
    for i, H in enumerate(holes):
        W = H["W"]
        bx, by = H["ball"]
        H["ball"] = (bx, round(max(-W / 2 + 0.4, min(W / 2 - 0.4, by + u(-0.45, 0.45))), 3))
        cx, cy = H["cup"]
        cy = cy + u(-0.5, 0.5)
        if i == 3:                                 # the block spans |y| <= 1.1: keep the cup behind it
            cy = max(-0.8, min(0.8, cy))
        H["cup"] = (round(cx + u(-0.5, 0.4), 3), round(max(-W / 2 + 0.45, min(W / 2 - 0.45, cy)), 3))
        sx, sy = H["tilt"]
        H["tilt"] = (round(sx * u(0.7, 1.3), 5), round(sy * u(0.7, 1.3) * (1 if rng.uniform() < 0.5 else -1), 5))
        bumps = []
        for x0, y0, a, gx, gy in H["bumps"]:
            if i == 3:                             # the hollow around the cup follows the cup
                bumps.append((H["cup"][0], H["cup"][1], round(a * u(0.8, 1.2), 4), gx, gy))
            else:
                bumps.append((round(x0 + u(-0.4, 0.4), 3), round(y0 + u(-0.35, 0.35), 3), round(a * u(0.8, 1.2), 4), gx, gy))
        H["bumps"] = bumps
        H["ridges"] = [(x0 + round(u(-0.4, 0.4), 3), y0, round(th + u(-12, 12), 2), round(a * u(0.85, 1.15), 4), sg)
                       for x0, y0, th, a, sg in H["ridges"]]
    return holes


HOLES = make_holes(SEED)


# ----------------------------------------------------------------------------------------------- height field
def height(H, x, y):
    sx, sy = H["tilt"]
    z = sx * x + sy * y
    for x0, y0, a, gx, gy in H["bumps"]:
        z += a * math.exp(-((x - x0) ** 2 / (2 * gx * gx) + (y - y0) ** 2 / (2 * gy * gy)))
    for x0, y0, th, a, s in H["ridges"]:
        c, sn = math.cos(math.radians(th)), math.sin(math.radians(th))
        u = (x - x0) * c + (y - y0) * sn
        z += a * math.exp(-u * u / (2 * s * s))
    return z


def grad(H, x, y):
    sx, sy = H["tilt"]
    gx_, gy_ = sx, sy
    for x0, y0, a, gx, gy in H["bumps"]:
        e = a * math.exp(-((x - x0) ** 2 / (2 * gx * gx) + (y - y0) ** 2 / (2 * gy * gy)))
        gx_ += -e * (x - x0) / (gx * gx)
        gy_ += -e * (y - y0) / (gy * gy)
    for x0, y0, th, a, s in H["ridges"]:
        c, sn = math.cos(math.radians(th)), math.sin(math.radians(th))
        u = (x - x0) * c + (y - y0) * sn
        e = a * math.exp(-u * u / (2 * s * s)) * (-u / (s * s))
        gx_ += e * c
        gy_ += e * sn
    return gx_, gy_


def segments(H):
    L, W = H["L"], H["W"]
    segs = [((0, -W / 2), (L, -W / 2)), ((L, -W / 2), (L, W / 2)), ((L, W / 2), (0, W / 2)), ((0, W / 2), (0, -W / 2))]
    for x0, x1, y0, y1 in H["blocks"]:
        segs += [((x0, y0), (x1, y0)), ((x1, y0), (x1, y1)), ((x1, y1), (x0, y1)), ((x0, y1), (x0, y0))]
    return segs


# ----------------------------------------------------------------------------------------------- one putt
def roll(H, pos, heading, speed, trail=True):
    """Simulate one putt from pos (x, y), initial rolling velocity speed * (cos heading, sin heading).
    Returns dict(end=(x, y), result, holed, t, walls, trail=[(t, x, y, z_center)], lip)."""
    x, y = float(pos[0]), float(pos[1])
    vx, vy = speed * math.cos(heading), speed * math.sin(heading)
    cx, cy = H["cup"]
    segs = segments(H)
    t = 0.0
    t_in = None          # time since the centre came over the cup
    lipped_now = False
    walls = 0
    lips = 0
    rolled_over = False
    out = []
    next_tr = 0.0
    k = 0
    holed = False
    zc = height(H, x, y) + R_BALL
    while t < MAX_T:
        if trail and t >= next_tr - 1e-12:
            out.append((round(t, 4), x, y, zc))
            next_tr += TRAIL_DT
        rho = math.hypot(x - cx, y - cy)
        if rho < R_CUP:
            if t_in is None:
                t_in = 0.0
            t_in += DT
            drop = 0.5 * G * t_in * t_in
            zc = height(H, cx, cy) + R_BALL - drop
            outward = (vx * (x - cx) + vy * (y - cy)) > 0
            if outward and rho >= R_CUP - R_BALL and not lipped_now:
                lipped_now = True
                if drop >= HOLE_DROP:
                    holed = True
                    break
                # rides over the lip: the rim takes radial speed (more the deeper it fell)
                nx, ny = (x - cx) / rho, (y - cy) / rho
                vr = vx * nx + vy * ny
                f = 0.35 + 0.65 * (1.0 - drop / HOLE_DROP)
                vx += (f - 1.0) * vr * nx
                vy += (f - 1.0) * vr * ny
                if drop > 0.25 * HOLE_DROP:
                    lips += 1
                else:
                    rolled_over = True
            x += vx * DT
            y += vy * DT
            t += DT
            k += 1
            if 0.5 * G * t_in * t_in > 3 * R_BALL:      # fell in (very slow ball)
                holed = True
                break
            continue
        t_in = None
        lipped_now = False
        gx_, gy_ = grad(H, x, y)
        ax, ay = -(5.0 / 7.0) * G * gx_, -(5.0 / 7.0) * G * gy_
        v = math.hypot(vx, vy)
        if v < 1e-3:
            if math.hypot(ax, ay) <= C_ROLL:
                vx = vy = 0.0
                break
            vx += ax * DT
            vy += ay * DT
        else:
            ox, oy = vx, vy
            vx += (ax - C_ROLL * ox / v) * DT
            vy += (ay - C_ROLL * oy / v) * DT
            if vx * ox + vy * oy <= 0 and math.hypot(ax, ay) <= C_ROLL:
                vx = vy = 0.0            # resistance reversed the velocity: at rest
                break
        x += vx * DT
        y += vy * DT
        # walls / blocks
        for (x0, y0), (x1, y1) in segs:
            ex, ey = x1 - x0, y1 - y0
            ll = ex * ex + ey * ey
            s = max(0.0, min(1.0, ((x - x0) * ex + (y - y0) * ey) / ll))
            px, py = x0 + s * ex, y0 + s * ey
            dx, dy = x - px, y - py
            d = math.hypot(dx, dy)
            if d < R_BALL and d > 1e-12:
                nx, ny = dx / d, dy / d
                vn = vx * nx + vy * ny
                if vn < 0:
                    tx, ty = vx - vn * nx, vy - vn * ny
                    vx, vy = -E_N * vn * nx + E_T * tx, -E_N * vn * ny + E_T * ty
                    walls += 1
                x, y = px + nx * R_BALL, py + ny * R_BALL
        zc = height(H, x, y) + R_BALL
        t += DT
        k += 1
    if holed:
        x, y = cx, cy
        zc = height(H, cx, cy) - 0.06
    if trail:
        out.append((round(t, 4), x, y, zc))
    if holed:
        result = "holed"
    elif lips:
        result = "lipped out"
    elif rolled_over:
        result = "rolled over the edge of the cup"
    else:
        result = "stopped"
    return dict(end=(x, y), holed=holed, result=result, t=round(t, 3), walls=walls, trail=out, steps=k)


def stroke_noise(hole_i, stroke_i):
    rng = np.random.default_rng([SEED, hole_i, stroke_i])
    a, s = rng.standard_normal(2)
    return float(a) * AIM_SIGMA_DEG, float(s) * SPEED_SIGMA


def line_heading(pos, cup):
    return math.atan2(cup[1] - pos[1], cup[0] - pos[0])


class Course:
    """The round: hole index, ball position, strokes. putt(aim_deg, speed) plays one stroke."""

    def __init__(self):
        self.hole = 0
        self.pos = tuple(HOLES[0]["ball"])
        self.strokes = [0] * len(HOLES)
        self.penalties = [0] * len(HOLES)
        self.picked_up = [False] * len(HOLES)
        self.log = []            # one dict per stroke
        self.done = False
        self.last = None         # last stroke on the current hole (for the trail view)

    def H(self):
        return HOLES[self.hole]

    def putt(self, aim_deg, speed):
        H = self.H()
        na, ns = stroke_noise(self.hole, self.strokes[self.hole])
        heading = math.radians(aim_deg + na)       # aim_deg: the putter face's direction in the green's frame (0 = +x)
        v = speed * (1.0 + ns)
        r = roll(H, self.pos, heading, v)
        self.strokes[self.hole] += 1
        rec = dict(hole=self.hole + 1, stroke=self.strokes[self.hole], aim_deg=aim_deg, speed=speed,
                   executed_aim_deg=aim_deg + na, executed_speed=v, start=self.pos, end=r["end"],
                   result=r["result"], holed=r["holed"], walls=r["walls"], roll_time_s=r["t"])
        self.log.append(rec)
        self.last = dict(rec, trail=r["trail"])
        self.pos = r["end"]
        rec["hole_finished"] = False
        if r["holed"] or self.strokes[self.hole] >= MAX_STROKES:
            if not r["holed"]:
                self.picked_up[self.hole] = True
            rec["hole_finished"] = True
            self.next_hole()
        return rec, r

    def next_hole(self):
        self.hole += 1
        if self.hole >= len(HOLES):
            self.done = True
            self.hole = len(HOLES) - 1
            return
        self.pos = tuple(HOLES[self.hole]["ball"])
        self.last = None

    def hole_score(self, i):
        return self.strokes[i] + (1 if self.picked_up[i] else 0) + self.penalties[i]

    def total(self):
        return sum(self.hole_score(i) for i in range(len(HOLES)))

    def state_sha(self):
        s = json.dumps([[r["hole"], r["stroke"], repr(r["end"][0]), repr(r["end"][1]), r["result"]] for r in self.log]
                       + [self.strokes, self.picked_up, self.hole, self.done])
        return hashlib.sha256(s.encode()).hexdigest()


# ----------------------------------------------------------------------------------------------- scene
IMG_W, IMG_H = 800, 500              # behind / side views
TOP_W, TOP_H = 1200, 600             # overhead
FOVY_EYE, FOVY_TOP = 50.0, 40.0
EYE_BACK, EYE_UP, EYE_PITCH = 2.0, 1.1, -14.0
SIDE_OFF, SIDE_UP, SIDE_PITCH = 7.0, 1.6, -12.0     # side camera: SIDE_OFF beyond the left wall (y = W/2), mid-green


def side_pose(H):
    return (H["L"] / 2, H["W"] / 2 + SIDE_OFF, height(H, H["L"] / 2, 0.0) + SIDE_UP)
GRID = 0.5


def top_height(H):
    t = math.tan(math.radians(FOVY_TOP / 2))
    return round(max((H["W"] / 2 + 0.4) / t, (H["L"] / 2 + 0.4) / (t * TOP_W / TOP_H)), 3)


def _texture_png(H):
    from PIL import Image
    L, W = H["L"], H["W"]
    ppm = 100
    w, h = int(L * ppm), int(W * ppm)
    img = np.zeros((h, w, 3), np.uint8)
    xs = (np.arange(w) + 0.5) / ppm
    ys = (np.arange(h) + 0.5) / ppm
    stripe = ((xs // 1.0) % 2).astype(bool)          # mowing stripes 1 m wide
    base = np.array([62, 140, 58], np.float32)
    col = np.where(stripe[None, :, None], base * 1.08, base * 0.94)
    col = np.broadcast_to(col, (h, w, 3)).copy()
    gx = (np.abs(((xs + GRID / 2) % GRID) - GRID / 2) < 0.012)
    gy = (np.abs(((ys + GRID / 2) % GRID) - GRID / 2) < 0.012)
    col[:, gx] = (col[:, gx] * 0.35 + 255 * 0.65)
    col[gy, :] = (col[gy, :] * 0.35 + 255 * 0.65)
    img[:] = np.clip(col, 0, 255).astype(np.uint8)
    img = img[::-1]          # row 0 = top of the texture (v = 1)
    b = io.BytesIO()
    Image.fromarray(img).save(b, format="PNG")
    return b.getvalue()


def _mesh(H, step=0.1):
    L, W = H["L"], H["W"]
    nx, ny = int(round(L / step)) + 1, int(round(W / step)) + 1
    V, T, F = [], [], []
    for j in range(ny):
        for i in range(nx):
            x, y = i * L / (nx - 1), -W / 2 + j * W / (ny - 1)
            V += [x, y, height(H, x, y)]
            T += [x / L, (y + W / 2) / W]
    for j in range(ny - 1):
        for i in range(nx - 1):
            a = j * nx + i
            F += [a, a + 1, a + nx + 1, a, a + nx + 1, a + nx]
    return " ".join(f"{v:.5f}" for v in V), " ".join(f"{v:.5f}" for v in T), " ".join(map(str, F))


def scene_xml(H):
    L, W = H["L"], H["W"]
    cx, cy = H["cup"]
    zc = height(H, cx, cy)
    v, t, f = _mesh(H)
    geoms = []
    wt, wh = 0.1, 0.08
    for (x0, y0), (x1, y1) in segments(H)[:4]:
        mx, my = (x0 + x1) / 2, (y0 + y1) / 2
        hx = abs(x1 - x0) / 2 + (wt if y0 == y1 else 0)
        hy = abs(y1 - y0) / 2 + (wt if x0 == x1 else 0)
        ox = (wt / 2 if mx >= L - 1e-9 else -wt / 2) if x0 == x1 else 0
        oy = (wt / 2 if my >= W / 2 - 1e-9 else -wt / 2) if y0 == y1 else 0
        if x0 == x1:
            hx = wt / 2
        else:
            hy = wt / 2
        zm = min(height(H, px, py) for px, py in [(x0, y0), (x1, y1), (mx, my)])
        ztop = max(height(H, px, py) for px, py in [(x0, y0), (x1, y1), (mx, my)]) + wh
        geoms.append(f'<geom type="box" material="wood" pos="{mx+ox:.4f} {my+oy:.4f} {(zm-0.2+ztop)/2:.4f}" '
                     f'size="{hx:.4f} {hy:.4f} {(ztop-zm+0.2)/2:.4f}"/>')
    for x0, x1, y0, y1 in H["blocks"]:
        zs = [height(H, px, py) for px in (x0, x1) for py in (y0, y1)]
        zlo, ztop = min(zs) - 0.1, max(zs) + 0.12
        geoms.append(f'<geom type="box" material="block" pos="{(x0+x1)/2:.4f} {(y0+y1)/2:.4f} {(zlo+ztop)/2:.4f}" '
                     f'size="{(x1-x0)/2:.4f} {(y1-y0)/2:.4f} {(ztop-zlo)/2:.4f}"/>')
    gxc, gyc = grad(H, cx, cy)
    n = np.array([-gxc, -gyc, 1.0]); n /= np.linalg.norm(n)
    ax = np.cross([0, 0, 1.0], n); s = np.linalg.norm(ax)
    ang = math.atan2(s, n[2])
    q = [math.cos(ang / 2)] + list((ax / s if s > 0 else np.zeros(3)) * math.sin(ang / 2))
    qs = " ".join(f"{a:.6f}" for a in q)
    return f"""
<mujoco model="golf">
  <visual><global offwidth="1600" offheight="1000"/><quality shadowsize="4096"/>
    <headlight ambient="0.3 0.3 0.3" diffuse="0.2 0.2 0.2" specular="0 0 0"/><map znear="0.01" zfar="60"/></visual>
  <asset>
    <texture name="sky" type="skybox" builtin="gradient" rgb1="0.55 0.75 0.95" rgb2="0.95 0.97 1.0" width="256" height="256"/>
    <texture name="grass" type="2d" file="green.png"/>
    <texture name="rough" type="2d" builtin="checker" rgb1="0.20 0.42 0.18" rgb2="0.22 0.45 0.20" width="256" height="256"/>
    <material name="green" texture="grass" specular="0.05" shininess="0.1"/>
    <material name="roughm" texture="rough" texrepeat="40 40" specular="0"/>
    <material name="wood" rgba="0.55 0.36 0.2 1" specular="0.1"/>
    <material name="block" rgba="0.75 0.22 0.18 1" specular="0.1"/>
    <mesh name="green" vertex="{v}" texcoord="{t}" face="{f}"/>
  </asset>
  <worldbody>
    <light directional="true" pos="0 0 10" dir="0.3 0.85 -0.4" diffuse="0.85 0.85 0.8" castshadow="true"/>
    <geom type="plane" size="40 40 0.1" pos="{L/2} 0 -0.25" material="roughm" contype="0" conaffinity="0"/>
    <geom type="mesh" mesh="green" material="green" contype="0" conaffinity="0"/>
    {''.join(geoms)}
    <body pos="{cx} {cy} {zc:.5f}" quat="{qs}">
      <geom type="cylinder" size="{R_CUP+0.006} 0.0012" pos="0 0 0.0003" rgba="0.95 0.95 0.95 1" contype="0" conaffinity="0"/>
      <geom type="cylinder" size="{R_CUP} 0.0015" pos="0 0 0.0008" rgba="0.02 0.02 0.02 1" contype="0" conaffinity="0"/>
    </body>
    <geom type="cylinder" size="0.006 0.75" pos="{cx} {cy} {zc+0.75:.4f}" rgba="0.95 0.85 0.1 1" contype="0" conaffinity="0"/>
    <geom type="box" size="0.002 0.16 0.1" pos="{cx} {cy+0.16:.4f} {zc+1.38:.4f}" rgba="0.9 0.1 0.1 1" contype="0" conaffinity="0"/>
    <body name="ball" mocap="true" pos="0 0 0">
      <geom type="sphere" size="{R_BALL}" rgba="1 1 1 1" contype="0" conaffinity="0"/>
    </body>
  </worldbody>
</mujoco>"""


class Views:
    """Renders the decision views for a hole (MuJoCo, osmesa)."""

    def __init__(self):
        self.models = {}
        self.renderers = {}

    def model(self, hi):
        import mujoco as mj
        if hi not in self.models:
            H = HOLES[hi]
            m = mj.MjModel.from_xml_string(scene_xml(H), assets={"green.png": _texture_png(H)})
            d = mj.MjData(m)
            self.models[hi] = (m, d)
        return self.models[hi]

    def renderer(self, hi, w, h):
        import mujoco as mj
        key = (hi, w, h)
        if key not in self.renderers:
            m, _ = self.model(hi)
            self.renderers[key] = mj.Renderer(m, height=h, width=w)
        return self.renderers[key]

    @staticmethod
    def cam(pos, yaw_deg, pitch_deg):
        """A free camera at pos looking along heading yaw, pitched by pitch (negative = down)."""
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

    def set_ball(self, hi, x, y, z=None):
        import mujoco as mj
        m, d = self.model(hi)
        H = HOLES[hi]
        d.mocap_pos[0] = [x, y, height(H, x, y) + R_BALL if z is None else z]
        mj.mj_forward(m, d)

    def eye_poses(self, hi, pos):
        """behind: EYE_BACK behind the ball along -x, looking along +x (down the green); side: fixed per hole, off the
        green's left wall at its middle, looking along -y. Neither depends on where the cup is."""
        H = HOLES[hi]
        behind = (pos[0] - EYE_BACK, pos[1], height(H, *pos) + EYE_UP)
        return dict(behind=(behind, 0.0, EYE_PITCH), side=(side_pose(H), -90.0, SIDE_PITCH))

    def render(self, hi, pos, trail=None, ball_z=None):
        """Returns dict name -> RGB uint8 array: behind, side, overhead."""
        import mujoco as mj
        H = HOLES[hi]
        self.set_ball(hi, pos[0], pos[1], ball_z)
        m, d = self.model(hi)
        out = {}
        for name, (p, yaw, pitch) in self.eye_poses(hi, pos).items():
            r = self.renderer(hi, IMG_W, IMG_H)
            m.vis.global_.fovy = FOVY_EYE
            r.update_scene(d, camera=self.cam(p, yaw, pitch))
            out[name] = r.render().copy()
        r = self.renderer(hi, TOP_W, TOP_H)
        m.vis.global_.fovy = FOVY_TOP
        r.update_scene(d, camera=self.cam((H["L"] / 2, 0.0, top_height(H)), 90.0, -90.0))
        top = r.render().copy()
        if trail:
            top = draw_trail(H, top, trail[::3])
        out["overhead"] = top
        m.vis.global_.fovy = 45.0
        return out

    def tv(self, hi, look, yaw_deg, w=960, h=544):
        """Broadcast view: follows `look` (x, y), looking along yaw, from 3.2 m away, 30 deg down."""
        H = HOLES[hi]
        import mujoco as mj
        m, d = self.model(hi)
        r = self.renderer(hi, w, h)
        m.vis.global_.fovy = 45.0
        c = mj.MjvCamera()
        c.lookat[:] = [look[0], look[1], height(H, look[0], look[1])]
        c.distance = 3.2
        c.azimuth = yaw_deg
        c.elevation = -30.0
        r.update_scene(d, camera=c)
        return r.render().copy()

    def top_small(self, hi, w=360, h=180):
        H = HOLES[hi]
        m, d = self.model(hi)
        r = self.renderer(hi, w, h)
        m.vis.global_.fovy = FOVY_TOP
        r.update_scene(d, camera=self.cam((H["L"] / 2, 0.0, top_height(H)), 90.0, -90.0))
        im = r.render().copy()
        m.vis.global_.fovy = 45.0
        return im


def top_project(H, x, y, z, w=TOP_W, h=TOP_H):
    f = h / 2 / math.tan(math.radians(FOVY_TOP / 2))
    dz = top_height(H) - z
    return w / 2 + f * (x - H["L"] / 2) / dz, h / 2 - f * y / dz


def draw_trail(H, img, pts, w=TOP_W, h=TOP_H, rad=3):
    from PIL import Image, ImageDraw
    im = Image.fromarray(img)
    dr = ImageDraw.Draw(im)
    for _, x, y, z in pts:
        u, v = top_project(H, x, y, z, w, h)
        dr.ellipse([u - rad, v - rad, u + rad, v + rad], fill=(255, 220, 30))
    return np.asarray(im).copy()


def spec_cameras():
    t_eye = math.tan(math.radians(FOVY_EYE / 2))
    t_top = math.tan(math.radians(FOVY_TOP / 2))
    return {
        "behind": {"tile_px": [IMG_W, IMG_H], "fovy_deg": FOVY_EYE, "focal_px": round(IMG_H / 2 / t_eye, 2),
                   "principal_point_px": [IMG_W / 2, IMG_H / 2],
                   "pose": f"crouched behind the ball: {EYE_BACK} m behind the ball along -x, {EYE_UP} m above the green "
                           f"surface at the ball, looking along +x (down the green; heading 0 deg), pitched {-EYE_PITCH} "
                           f"deg down, no roll"},
        "side": {"tile_px": [IMG_W, IMG_H], "fovy_deg": FOVY_EYE, "focal_px": round(IMG_H / 2 / t_eye, 2),
                 "principal_point_px": [IMG_W / 2, IMG_H / 2],
                 "pose": f"fixed per hole (holes[].side_camera_pos_m): beyond the green's left wall at mid-green, "
                         f"(L/2, W/2 + {SIDE_OFF}, h(L/2, 0) + {SIDE_UP}), looking along -y (heading -90 deg), pitched "
                         f"{-SIDE_PITCH} deg down, no roll. Image right = +x (the far end of the green)"},
        "overhead": {"tile_px": [TOP_W, TOP_H], "fovy_deg": FOVY_TOP, "focal_px": round(TOP_H / 2 / t_top, 2),
                     "principal_point_px": [TOP_W / 2, TOP_H / 2],
                     "pose": "straight down from (L/2, 0, height) (per hole, see holes[]), image right = +x, image up = +y; "
                             "it shows the whole green; the previous putt on this hole is drawn as a trail of yellow dots"},
        "pinhole": "u = cx + f * X/Z, v = cy - f * Y/Z in the camera frame (X right, Y up, Z forward); square pixels",
    }


def spec_holes():
    return [{"hole": i + 1, "par": H["par"], "green_x_m": [0, H["L"]], "green_y_m": [-H["W"] / 2, H["W"] / 2],
             "overhead_camera_height_m": top_height(H), "obstacle_blocks": len(H["blocks"]),
             "side_camera_pos_m": [round(x, 4) for x in side_pose(H)]}
            for i, H in enumerate(HOLES)]


def replay(strokes):
    """Replay recorded (hole, aim_deg, speed) strokes on a fresh course."""
    c = Course()
    for s in strokes:
        assert c.hole + 1 == s["hole"] and not c.done, (c.hole, s)
        c.putt(s["aim_deg"], s["speed"])
    return c


def render_video(strokes, out, penalties=None, fps=30):
    """Replay video: a camera following the ball (30 deg down, 3.2 m away, looking along the putt), an overhead
    inset with the ball and its path, and a scoreboard line. Real time."""
    import imageio.v2 as imageio
    from PIL import Image, ImageDraw
    v = Views()
    c = Course()
    w = imageio.get_writer(out, fps=fps, macro_block_size=8)
    pen = penalties or [0] * len(HOLES)

    def frame(hi, x, y, z, yaw, txt, path):
        H = HOLES[hi]
        if z is None:
            z = height(H, x, y) + R_BALL
        v.set_ball(hi, x, y, z)
        main = v.tv(hi, (x, y), yaw)
        top = v.top_small(hi)
        top = draw_trail(H, top, path, 360, 180, rad=2)
        u, vv = top_project(H, x, y, z, 360, 180)
        im = Image.fromarray(main)
        tim = Image.fromarray(top)
        ImageDraw.Draw(tim).ellipse([u - 4, vv - 4, u + 4, vv + 4], outline=(255, 255, 255), width=2)
        im.paste(tim, (im.width - 366, 32))
        dr = ImageDraw.Draw(im)
        dr.rectangle([0, 0, im.width, 26], fill=(0, 0, 0))
        dr.text((8, 7), txt, fill=(255, 255, 255))
        w.append_data(np.asarray(im))

    for s in strokes:
        hi = c.hole
        H = HOLES[hi]
        done = sum(c.hole_score(i) for i in range(hi))
        hdr = lambda k: (f"{H['name']} (par {H['par']})  stroke {k}   score before this hole: {done}"
                         f"{'   pace penalty on this hole: +%d' % pen[hi] if pen[hi] else ''}")
        yaw = s["aim_deg"]
        for _ in range(int(fps * 0.7)):
            frame(hi, c.pos[0], c.pos[1], None, yaw, hdr(c.strokes[hi] + 1), [])
        rec, r = c.putt(s["aim_deg"], s["speed"])
        tr = r["trail"]
        for i, (tt, x, y, z) in enumerate(tr):
            frame(hi, x, y, z, yaw, hdr(rec["stroke"]) + f"   aim {s['aim_deg']:+.1f} deg, {s['speed']:.2f} m/s",
                  tr[:i:3])
        tt, x, y, z = tr[-1]
        for _ in range(int(fps * 1.0)):
            frame(hi, x, y, z, yaw, hdr(rec["stroke"]) + f"   -> {rec['result']}", tr[::3])
    w.close()


if __name__ == "__main__":
    if sys.argv[1:2] == ["replay"]:
        tr = json.load(open(sys.argv[2]))
        c = replay(tr["strokes"])
        print(json.dumps({"sha": c.state_sha(), "strokes": c.strokes, "picked_up": c.picked_up, "done": c.done,
                          "hole": c.hole}))
