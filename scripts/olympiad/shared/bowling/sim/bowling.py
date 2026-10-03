"""Ten-pin bowling (MuJoCo 3.3.7): lane with an oil pattern, gutters, pin deck, pit, kickbacks; 10 pins; a 7 kg ball.

Everything that decides a result is MuJoCo rigid-body physics: the ball slides on the oiled front of the lane, hooks
where the friction rises (Frohlich 2004: most of the hook comes from the drier back end), rolls, hits the pins; pins
collide with the ball, each other, the deck, the kickbacks and the pit. The release primitive only sets the ball's
initial state (position across the lane, launch direction, speed, rev rate, axis rotation); nothing uses the pins'
state to steer the ball. The only randomness is the seeded execution scatter on the five release parameters.

Frame: x along the lane from the foul line (x = 0) to the pins (head pin at x = 18.288 m), y across the lane,
positive to the LEFT as seen by the bowler, z up; the lane surface is z = 0. Boards are numbered from the RIGHT
gutter (board 1) to the left (board 39), 1.0541 / 39 = 27.03 mm each; board 20 is the centre (y = 0).

CLI: `python3 bowling.py replay trajectory.json` replays the recorded balls in a fresh process and prints the state
hash and the scorecard (one JSON line).
"""
from __future__ import annotations

import hashlib
import io
import json
import math
import os
import sys

import numpy as np

# ---------------------------------------------------------------- geometry (USBC dimensions, metres / kilograms)
IN = 0.0254
LANE_W = 1.0541                     # 41.5 in
N_BOARDS = 39
BOARD_W = LANE_W / N_BOARDS
HEAD_PIN_X = 18.288                 # 60 ft foul line -> head pin centre
PIN_SPACING = 0.3048                # 12 in triangle
ROW_DX = PIN_SPACING * math.sqrt(3) / 2
PIT_X = 19.157                      # 62 ft 10 3/16 in: end of the pin deck
GUTTER_W = 0.235                    # 9.25 in
GUTTER_D = 0.047                    # 1 7/8 in deep
KICK_Y = LANE_W / 2 + GUTTER_W      # kickback (side wall) plane at the pin deck
KICK_X0 = HEAD_PIN_X - 0.45
R_BALL = 0.109                      # 21.8 cm diameter (the rules allow up to 8.595 in)
M_BALL = 7.0
RG_BALL = 0.0648                    # radius of gyration 2.55 in (typical 2.46-2.80); isotropic: no mass bias
PIN_H = 15 * IN
M_PIN = 1.53                        # 3 lb 6 oz (rules: 3-6 to 3-10)
PIN_COM_Z = 0.147                   # 5 13/16 in (rules: 5 11/16 - 5 15/16)
RELEASE_X = 0.35                    # the ball is laid down 35 cm past the foul line

# pin profile (USBC specification): height in inches -> diameter in inches
PIN_PROFILE = [(0.0, 2.03), (0.375, 2.5), (0.75, 2.828), (1.5, 3.4), (2.25, 3.906), (3.375, 4.51), (4.5, 4.766),
               (5.875, 4.563), (7.25, 3.927), (8.625, 2.828), (9.375, 2.237), (10.0, 1.797), (10.875, 1.87),
               (11.75, 2.2), (12.5, 2.38), (13.5, 2.2), (14.25, 1.75), (14.75, 1.1), (15.0, 0.0)]

PIN_SPOTS = []                      # pins 1..10: (x, y)
for _row, _pins in enumerate([[1], [2, 3], [4, 5, 6], [7, 8, 9, 10]]):
    for _k, _p in enumerate(_pins):
        PIN_SPOTS.append((HEAD_PIN_X + _row * ROW_DX, (_row / 2 - _k) * PIN_SPACING))

# ---------------------------------------------------------------- simulation settings
DT = 0.0005
MAX_ROLL_T = 6.0                    # ball on the lane (a slow ball needs < 5 s)
SETTLE_T = 3.0                      # after the ball reaches the pins / pit / stops: let the pins settle
DOWN_TILT_DEG = 20.0                # a pin tilted more than this, or off the lane surface, is down
LANE_X_MIN = -1.5                   # the lane surface for USBC 7b: from 1.5 m behind the foul line to the pit
FPS = 30
CONTACT_DAMP = 0.35 # contact damping ratio (solref): sets the restitution
DECK_MU = 0.2 # pin <-> pin deck
PIN_MU = 0.3   # pin <-> pin / ball; calibrated against the USBC pin carry study (Bowlscore strike % vs entry angle)

# ---------------------------------------------------------------- lane condition (assumed values, Frohlich 2004)
BASE_SEED = 20260930
SEED = int(os.environ.get("BOWL_SEED", BASE_SEED))
MAX_FRAMES = 10


TAPER_D0, TAPER_D1 = 6, 16            # boards from the centre where the oil starts to shorten / reaches the outside length


def make_lane(seed):
    """The lane condition for a seed: a house-style pattern. Assumed values after Frohlich (2004): oil mu ~0.04 on the
    front of the lane, dry mu ~0.2 on the back end, a short transition. The oil reaches furthest in the middle of the
    lane (`oil_len`, boards 14-26) and is `taper` metres shorter on the outside boards (boards 1-4 and 36-39), with a
    smooth taper in between (a typical house shot is longer in the middle than outside). The base seed is the standard
    condition; other seeds draw the oil lengths and the friction levels (the player is not told them)."""
    if seed == BASE_SEED:
        return {"oil_len": 13.5, "ramp": 1.2, "mu_oil": 0.040, "mu_dry": 0.20, "taper": 3.0}
    r = np.random.default_rng([seed, 7])
    ln = {"oil_len": round(float(r.uniform(12.0, 14.7)), 2), "ramp": round(float(r.uniform(0.8, 1.8)), 2),
          "mu_oil": round(float(r.uniform(0.032, 0.05)), 3), "mu_dry": round(float(r.uniform(0.16, 0.24)), 3)}
    ln["taper"] = round(float(r.uniform(2.5, 3.5)), 2)
    return ln


def oil_len_at(lane, d):
    """Oil length (m) on a board d boards from the centre board (0..19)."""
    t = min(1.0, max(0.0, (d - TAPER_D0) / (TAPER_D1 - TAPER_D0)))
    return lane["oil_len"] - lane.get("taper", 0.0) * t * t * (3 - 2 * t)


LANE = make_lane(SEED)

# execution scatter (published): release board, launch angle, speed, rev rate, axis rotation
SIG = {"board": 1.0, "angle_deg": 0.24, "speed_frac": 0.015, "rpm_frac": 0.04, "axis_deg": 2.0}


def scatter(frame_i, ball_i):
    r = np.random.default_rng([SEED, 11, frame_i, ball_i])
    z = r.standard_normal(5)
    return [float(v) for v in z]


# ---------------------------------------------------------------- scene
def _pin_mesh(n_seg, profile):
    V, F = [], []
    rings = []
    for h, d in profile:
        z, r = h * IN, d * IN / 2
        if r <= 1e-9:
            rings.append([len(V)]); V.append((0.0, 0.0, z)); continue
        ring = []
        for k in range(n_seg):
            a = 2 * math.pi * k / n_seg
            ring.append(len(V)); V.append((r * math.cos(a), r * math.sin(a), z))
        rings.append(ring)
    base_c = len(V); V.append((0.0, 0.0, 0.0))
    for k in range(n_seg):
        F.append((base_c, rings[0][(k + 1) % n_seg], rings[0][k]))
    for a, b in zip(rings[:-1], rings[1:]):
        if len(b) == 1:
            for k in range(n_seg):
                F.append((a[k], a[(k + 1) % n_seg], b[0]))
        else:
            for k in range(n_seg):
                k1 = (k + 1) % n_seg
                F.append((a[k], a[k1], b[k1])); F.append((a[k], b[k1], b[k]))
    vs = " ".join(f"{c:.5f}" for v in V for c in v)
    fs = " ".join(str(i) for f in F for i in f)
    return vs, fs


def pin_inertia():
    """Principal moments about the CoM for a solid of revolution with the pin profile (uniform density),
    scaled to M_PIN; the CoM is set to PIN_COM_Z (a real pin is slightly bottom-weighted)."""
    zs = np.linspace(0, PIN_H, 2001)
    ph = np.array([p[0] * IN for p in PIN_PROFILE]); pr = np.array([p[1] * IN / 2 for p in PIN_PROFILE])
    r = np.interp(zs, ph, pr)
    dz = zs[1] - zs[0]
    dm = math.pi * r ** 2 * dz
    m = dm.sum()
    izz = (0.5 * dm * r ** 2).sum()
    ixx = (dm * (r ** 2 / 4 + (zs - PIN_COM_Z) ** 2)).sum()
    s = M_PIN / m
    return ixx * s, izz * s


def _lane_texture():
    """Maple/pine boards, the arrows at ~15 ft and the dots at 7 ft, printed on the lane (x from -1.5 to PIT_X)."""
    from PIL import Image, ImageDraw
    x0, x1 = -1.5, PIT_X
    ppm_x, ppb = 100, 10                         # 1 cm per pixel along the lane, 10 px per board
    w, h = int((x1 - x0) * ppm_x), N_BOARDS * ppb
    img = np.zeros((h, w, 3), np.float32)
    rng = np.random.default_rng(5)
    for b in range(N_BOARDS):
        tone = np.array([214, 172, 118]) * rng.uniform(0.9, 1.06)
        grain = 1 + 0.035 * np.sin(np.arange(w) / rng.uniform(9, 30) + rng.uniform(0, 6))
        img[b * ppb:(b + 1) * ppb] = tone[None, None, :] * grain[None, :, None]
        img[b * ppb, :] *= 0.8                   # the joint between boards
    xs = x0 + (np.arange(w) + 0.5) / ppm_x
    img[:, (xs >= -1.5) & (xs < 0)] *= 0.93      # approach
    fl = (xs >= -0.01) & (xs < 0.01)
    img[:, fl] = [25, 25, 25]                    # foul line
    img = np.clip(img, 0, 255).astype(np.uint8)
    im = Image.fromarray(img)
    dr = ImageDraw.Draw(im)
    def px(x, board):                            # texture row 0 = board 39 (left, +y) at the top
        return (x - x0) * ppm_x, (N_BOARDS - board + 0.5) * ppb
    for b in (5, 10, 15, 20, 25, 30, 35):        # arrows: a V, the centre arrow furthest
        xa = 3.66 + (4 - abs(b - 20) / 5) * 0.23
        u, v = px(xa, b)
        dr.polygon([(u + 18, v), (u - 22, v - 4.5), (u - 22, v + 4.5)], fill=(40, 40, 40))
    for b in (3, 5, 8, 11, 14, 26, 29, 32, 35, 37):   # dots at 7 ft
        u, v = px(2.13, b)
        dr.ellipse([u - 3, v - 3, u + 3, v + 3], fill=(40, 40, 40))
    for b in range(1, 40):                        # spots on the pin deck: none; deck is the same wood
        pass
    img = np.asarray(im)[::-1]                    # MuJoCo: texture row 0 = v = 1
    b = io.BytesIO()
    Image.fromarray(np.ascontiguousarray(img)).save(b, format="PNG")
    return b.getvalue()


def scene_xml(lane):
    hw = LANE_W / 2
    n_r = 6

    def segs_for(L0):
        L1 = L0 + lane["ramp"]
        segs = [(-1.5, L0, lane["mu_oil"])]                  # (x0, x1, mu) lane friction segments along one strip
        for k in range(n_r):
            a, b = L0 + k * lane["ramp"] / n_r, L0 + (k + 1) * lane["ramp"] / n_r
            f = (k + 0.5) / n_r
            segs.append((a, b, lane["mu_oil"] + f * (lane["mu_dry"] - lane["mu_oil"])))
        segs.append((L1, HEAD_PIN_X - 0.3, lane["mu_dry"]))
        return segs

    # strips across the lane: boards with the same oil length share one strip (the middle boards, the outside boards)
    strips = []                                            # (y0, y1, oil length)
    for j in range(N_BOARDS):
        y0, y1 = -hw + j * BOARD_W, -hw + (j + 1) * BOARD_W
        L0 = round(oil_len_at(lane, abs(j + 1 - 20)), 4)
        if strips and strips[-1][2] == L0:
            strips[-1] = (strips[-1][0], y1, L0)
        else:
            strips.append((y0, y1, L0))
    lane_geoms = "".join(
        f'<geom name="lane{i}_{k}" type="box" pos="{(a+b)/2:.4f} {(y0+y1)/2:.5f} -0.05" size="{(b-a)/2:.4f} {(y1-y0)/2:.5f} 0.05" '
        f'friction="{mu:.4f} 0.005 0.0001" priority="1" rgba="0 0 0 0" group="3"/>'
        for i, (y0, y1, L0) in enumerate(strips) for k, (a, b, mu) in enumerate(segs_for(L0)))
    lane_geoms += (f'<geom name="deck" type="box" pos="{(HEAD_PIN_X - 0.3 + PIT_X)/2:.4f} 0 -0.05" '
                   f'size="{(PIT_X - HEAD_PIN_X + 0.3)/2:.4f} {hw:.5f} 0.05" friction="{DECK_MU:.4f} 0.005 0.0001" '
                   f'priority="1" rgba="0 0 0 0" group="3"/>')   # pin deck (pins slide on it)
    gy = hw + GUTTER_W / 2
    vw = f"{-1.5} {-hw:.5f} 0.0005  {PIT_X} {-hw:.5f} 0.0005  {PIT_X} {hw:.5f} 0.0005  {-1.5} {hw:.5f} 0.0005"
    ixx, izz = pin_inertia()
    pv, pf = _pin_mesh(20, PIN_PROFILE)
    pvv, pvf = _pin_mesh(40, PIN_PROFILE)
    pins = []
    for i, (x, y) in enumerate(PIN_SPOTS):
        pins.append(f"""
    <body name="pin{i+1}" pos="{x:.5f} {y:.5f} 0">
      <freejoint name="pin{i+1}"/>
      <inertial pos="0 0 {PIN_COM_Z}" mass="{M_PIN}" diaginertia="{ixx:.6e} {ixx:.6e} {izz:.6e}"/>
      <geom type="mesh" mesh="pin_col" friction="{PIN_MU} 0.005 0.0001" rgba="0 0 0 0" group="3"/>
      <geom type="mesh" mesh="pin_vis" material="pinm" contype="0" conaffinity="0" mass="0"/>
      <geom type="cylinder" size="{0.9*IN+0.0012:.5f} 0.0045" pos="0 0 {10.25*IN:.4f}" rgba="0.8 0.05 0.05 1" contype="0" conaffinity="0" mass="0"/>
      <geom type="cylinder" size="{1.05*IN+0.0012:.5f} 0.004" pos="0 0 {11.3*IN:.4f}" rgba="0.8 0.05 0.05 1" contype="0" conaffinity="0" mass="0"/>
    </body>""")
    return f"""
<mujoco model="bowling">
  <compiler angle="radian" autolimits="true"/>
  <option timestep="{DT}" cone="elliptic" noslip_iterations="0" integrator="Euler">
    <flag warmstart="enable"/>
  </option>
  <visual><global offwidth="1600" offheight="1400"/><quality shadowsize="4096"/>
    <headlight ambient="0.35 0.35 0.35" diffuse="0.3 0.3 0.3" specular="0 0 0"/><map znear="0.02" zfar="80"/></visual>
  <asset>
    <texture name="lanetex" type="2d" file="lane.png"/>
    <material name="lanem" texture="lanetex" specular="0.35" shininess="0.6" reflectance="0.08"/>
    <material name="gutter" rgba="0.55 0.56 0.6 1" specular="0.3"/>
    <material name="wall" rgba="0.12 0.14 0.2 1"/>
    <material name="pinm" rgba="0.97 0.97 0.95 1" specular="0.5" shininess="0.6"/>
    <material name="ballm" rgba="0.1 0.2 0.75 1" specular="0.7" shininess="0.9"/>
    <texture name="floor" type="2d" builtin="checker" rgb1="0.25 0.2 0.25" rgb2="0.3 0.25 0.3" width="256" height="256"/>
    <material name="floorm" texture="floor" texrepeat="20 20"/>
    <mesh name="lane_vis" inertia="shell" vertex="{vw}" texcoord="0 0  1 0  1 1  0 1" face="0 1 2  0 2 3"/>
    <mesh name="pin_col" vertex="{pv}" face="{pf}"/>
    <mesh name="pin_vis" vertex="{pvv}" face="{pvf}"/>
  </asset>
  <default><geom solref="0.002 {CONTACT_DAMP}" solimp="0.95 0.99 0.001"/></default>
  <worldbody>
    <light directional="true" pos="0 0 10" dir="0.2 0.3 -1" diffuse="0.6 0.6 0.6" castshadow="true"/>
    <light pos="{HEAD_PIN_X - 2} 0 3" dir="0.3 0 -1" diffuse="0.5 0.5 0.5" castshadow="false"/>
    <geom name="floor" type="plane" size="40 10 0.1" pos="10 0 -0.6" material="floorm" priority="1" friction="0.8 0.005 0.0001"/>
    <geom type="mesh" mesh="lane_vis" material="lanem" contype="0" conaffinity="0"/>
    {lane_geoms}
    <geom name="gutterR" type="box" pos="{(PIT_X-1.5)/2:.4f} {-gy:.5f} {-GUTTER_D-0.02:.4f}" size="{(PIT_X+1.5)/2:.4f} {GUTTER_W/2:.4f} 0.02" material="gutter" friction="0.2 0.005 0.0001" priority="1"/>
    <geom name="gutterL" type="box" pos="{(PIT_X-1.5)/2:.4f} {gy:.5f} {-GUTTER_D-0.02:.4f}" size="{(PIT_X+1.5)/2:.4f} {GUTTER_W/2:.4f} 0.02" material="gutter" friction="0.2 0.005 0.0001" priority="1"/>
    <geom name="capR" type="box" pos="{(KICK_X0-1.5)/2:.4f} {-(KICK_Y+0.04):.5f} 0.02" size="{(KICK_X0+1.5)/2:.4f} 0.04 0.02" material="gutter"/>
    <geom name="capL" type="box" pos="{(KICK_X0-1.5)/2:.4f} {KICK_Y+0.04:.5f} 0.02" size="{(KICK_X0+1.5)/2:.4f} 0.04 0.02" material="gutter"/>
    <geom name="kickR" type="box" pos="{(KICK_X0+PIT_X+0.95)/2:.4f} {-(KICK_Y+0.02):.5f} 0.2" size="{(PIT_X+0.95-KICK_X0)/2:.4f} 0.02 0.8" material="wall" friction="0.2 0.005 0.0001"/>
    <geom name="kickL" type="box" pos="{(KICK_X0+PIT_X+0.95)/2:.4f} {KICK_Y+0.02:.5f} 0.2" size="{(PIT_X+0.95-KICK_X0)/2:.4f} 0.02 0.8" material="wall" friction="0.2 0.005 0.0001"/>
    <geom name="pitfloor" type="box" pos="{PIT_X+0.45:.4f} 0 -0.42" size="0.45 {KICK_Y:.4f} 0.02" material="wall" friction="0.5 0.005 0.0001" priority="1"/>
    <geom name="pitfront" type="box" pos="{PIT_X-0.02:.4f} 0 -0.35" size="0.02 {KICK_Y:.4f} 0.25" material="wall"/>
    <geom name="cushion" type="box" pos="{PIT_X+0.92:.4f} 0 0.2" size="0.02 {KICK_Y:.4f} 0.8" rgba="0.08 0.08 0.1 1" solref="0.02 1"/>
    <geom name="masking" type="box" pos="{PIT_X-0.2:.4f} 0 1.05" size="0.02 {KICK_Y:.4f} 0.25" rgba="0.1 0.1 0.35 1" contype="0" conaffinity="0"/>
    <geom name="store" type="box" pos="45 0 -2.02" size="6 2 0.02" rgba="0.2 0.2 0.2 1" priority="1" friction="0.8 0.005 0.0001"/>
    <body name="ball" pos="{RELEASE_X} 0 {R_BALL}">
      <freejoint name="ball"/>
      <inertial pos="0 0 0" mass="{M_BALL}" diaginertia="{M_BALL*RG_BALL**2:.6f} {M_BALL*RG_BALL**2:.6f} {M_BALL*RG_BALL**2:.6f}"/>
      <geom name="ballg" type="sphere" size="{R_BALL}" material="ballm" friction="0.04 0.005 0.0001" mass="0"/>
      <geom type="sphere" size="0.012" pos="0 0.035 {R_BALL-0.018:.4f}" rgba="0.02 0.02 0.02 1" contype="0" conaffinity="0" mass="0"/>
      <geom type="sphere" size="0.012" pos="0 -0.035 {R_BALL-0.018:.4f}" rgba="0.02 0.02 0.02 1" contype="0" conaffinity="0" mass="0"/>
      <geom type="sphere" size="0.014" pos="-0.06 0 {R_BALL-0.042:.4f}" rgba="0.02 0.02 0.02 1" contype="0" conaffinity="0" mass="0"/>
      <geom type="cylinder" size="{R_BALL-0.0003:.4f} 0.004" euler="0 1.5708 0" rgba="0.95 0.8 0.1 1" contype="0" conaffinity="0" mass="0"/>
    </body>
    {''.join(pins)}
  </worldbody>
</mujoco>"""


# ---------------------------------------------------------------- the physics
def release_state(board, angle_deg, speed, rpm, axis_deg):
    """The ball's initial state for a release: centre over `board` at the lay-down point, velocity `speed` along the
    launch direction (angle_deg from the lane axis, + = to the left), angular velocity rpm about the axis obtained by
    rotating the pure forward-roll axis by axis_deg counter-clockwise seen from above (0 = end over end, 90 = axis
    along the direction of travel; + hooks to the left, as a right-hander's ball)."""
    y = -LANE_W / 2 + (board - 0.5) * BOARD_W
    a = math.radians(angle_deg)
    d = np.array([math.cos(a), math.sin(a), 0.0])
    roll_axis = np.array([-math.sin(a), math.cos(a), 0.0])        # z x d: the forward-roll axis
    t = math.radians(axis_deg)
    ax = np.array([roll_axis[0] * math.cos(t) - roll_axis[1] * math.sin(t),
                   roll_axis[0] * math.sin(t) + roll_axis[1] * math.cos(t), 0.0])
    w = rpm * 2 * math.pi / 60 * ax
    return np.array([RELEASE_X, y, R_BALL]), speed * d, w


class Lane:
    """A MuJoCo lane. Holds the pins between balls: `rack()` sets a full rack, `sweep(down)` removes the pins that
    are down (to a storage shelf far off the lane), `roll(...)` bowls one ball."""

    def __init__(self, lane=None):
        import mujoco as mj
        self.mj = mj
        self.lane = lane or LANE
        self.m = mj.MjModel.from_xml_string(scene_xml(self.lane), assets={"lane.png": _lane_texture()})
        self.d = mj.MjData(self.m)
        self.ball_q = self.m.jnt_qposadr[self.m.joint("ball").id]
        self.ball_v = self.m.jnt_dofadr[self.m.joint("ball").id]
        self.pin_q = [self.m.jnt_qposadr[self.m.joint(f"pin{i+1}").id] for i in range(10)]
        self.pin_v = [self.m.jnt_dofadr[self.m.joint(f"pin{i+1}").id] for i in range(10)]
        self.standing = [True] * 10
        self.rack()

    def pin_pose(self, i):
        q = self.pin_q[i]
        return self.d.qpos[q:q + 3].copy(), self.d.qpos[q + 3:q + 7].copy()

    def rack(self):
        mj = self.mj
        mj.mj_resetData(self.m, self.d)
        for i, (x, y) in enumerate(PIN_SPOTS):
            q = self.pin_q[i]
            self.d.qpos[q:q + 7] = [x, y, 0.0, 1, 0, 0, 0]
        self._park_ball()
        self.standing = [True] * 10
        mj.mj_forward(self.m, self.d)

    def _park_ball(self):
        q = self.ball_q
        self.d.qpos[q:q + 7] = [40.0, 0.0, -2.0 + R_BALL, 1, 0, 0, 0]
        self.d.qvel[self.ball_v:self.ball_v + 6] = 0

    def sweep(self, down):
        """Deadwood removal: pins that are down go to the storage shelf; standing pins stay where they are (at rest)."""
        for i in range(10):
            if down[i] or not self.standing[i]:
                q = self.pin_q[i]
                self.d.qpos[q:q + 7] = [41.0 + 0.4 * i, 0.0, -2.0, 1, 0, 0, 0]
                self.standing[i] = False
            v = self.pin_v[i]
            self.d.qvel[v:v + 6] = 0
        self._park_ball()
        self.d.time = 0.0
        self.d.qacc_warmstart[:] = 0
        self.mj.mj_forward(self.m, self.d)

    def pin_down(self, i):
        p, q = self.pin_pose(i)
        up_z = 1 - 2 * (q[1] ** 2 + q[2] ** 2)                       # z-component of the pin's axis
        tilt = math.degrees(math.acos(max(-1.0, min(1.0, up_z))))
        # USBC 7b: a pin that stands anywhere on the lane surface counts as standing; off the lane (gutter, pit,
        # kickback side) it is down
        on_lane = (abs(p[1]) <= LANE_W / 2) and (LANE_X_MIN <= p[0] <= PIT_X) and p[2] > -0.01
        return (tilt > DOWN_TILT_DEG) or not on_lane

    def roll(self, board, angle_deg, speed, rpm, axis_deg, record=False):
        """Bowl one ball; returns (result dict, frames). frames (if record): list of (t, qpos copy) at FPS."""
        mj, m, d = self.mj, self.m, self.d
        p0, v0, w0 = release_state(board, angle_deg, speed, rpm, axis_deg)
        q, v = self.ball_q, self.ball_v
        d.qpos[q:q + 7] = [*p0, 1, 0, 0, 0]
        d.qvel[v:v + 3] = v0
        d.qvel[v + 3:v + 6] = w0                   # free joint: angular velocity in the (identity) body frame
        d.time = 0.0
        d.qacc_warmstart[:] = 0                    # a ball is a pure function of (qpos, qvel, release)
        mj.mj_forward(m, d)
        frames, trail = [], []
        every = int(round(1.0 / FPS / DT))
        n, t_end = 0, None
        first_contact_t = None
        gutter = False
        hook_start = None
        max_steps = int((MAX_ROLL_T + SETTLE_T) / DT)
        while n < max_steps:
            mj.mj_step(m, d)
            n += 1
            bx, by, bz = d.qpos[q:q + 3]
            if n % every == 0:
                if bz > -0.02 and bx < PIT_X:
                    trail.append((round(n * DT, 4), float(bx), float(by)))
                if record:
                    frames.append((n * DT, d.qpos.copy()))
            if not gutter and abs(by) > LANE_W / 2 + 0.01 and bx < HEAD_PIN_X - 0.3:
                gutter = True
            if t_end is None:
                vb = math.hypot(d.qvel[v], d.qvel[v + 1])
                if bx > HEAD_PIN_X - 0.25 - R_BALL and first_contact_t is None:
                    first_contact_t = n * DT
                if bx > PIT_X or bz < -0.1 or (vb < 0.05 and n * DT > 1.0) or n * DT > MAX_ROLL_T:
                    t_end = n * DT + SETTLE_T
            elif n * DT >= t_end:
                break
        down_now = [self.standing[i] and self.pin_down(i) for i in range(10)]
        res = {"down": down_now, "count": int(sum(down_now)), "gutter": gutter, "t": round(n * DT, 4),
               "trail": trail}
        return res, frames

    def state_bytes(self):
        return self.d.qpos.tobytes() + self.d.qvel.tobytes()


# ---------------------------------------------------------------- scoring
def frame_scores(frames):
    """Standard ten-pin scoring. frames: list (<= 10) of lists of pin counts. Returns the per-frame running totals
    (None where a bonus is still pending or the frame is unfinished)."""
    rolls = [c for f in frames for c in f]
    out, total, k = [], 0, 0
    for fi, f in enumerate(frames):
        if fi < 9:
            if f and f[0] == 10:
                nxt = rolls[k + 1:k + 3]
                if len(nxt) < 2:
                    out.append(None); k += 1; continue
                total += 10 + sum(nxt); out.append(total); k += 1
            elif len(f) == 2:
                if f[0] + f[1] == 10:
                    nxt = rolls[k + 2:k + 3]
                    if len(nxt) < 1:
                        out.append(None); k += 2; continue
                    total += 10 + nxt[0]
                else:
                    total += f[0] + f[1]
                out.append(total); k += 2
            else:
                out.append(None); k += len(f)
        else:
            need = 3 if (len(f) >= 2 and (f[0] == 10 or f[0] + f[1] == 10)) else 2
            if len(f) >= need:
                total += sum(f); out.append(total)
            else:
                out.append(None)
            k += len(f)
    return out


def score_total(frames):
    """Pins so far including the bonuses already earned (what the scoreboard's last number would read if the game
    stopped now: pending bonuses count as the balls rolled so far)."""
    rolls = [c for f in frames for c in f]
    total, k = 0, 0
    for fi, f in enumerate(frames):
        if fi < 9:
            if f and f[0] == 10:
                total += 10 + sum(rolls[k + 1:k + 3]); k += 1
            else:
                total += sum(f)
                if len(f) == 2 and f[0] + f[1] == 10:
                    total += sum(rolls[k + 2:k + 3])
                k += len(f)
        else:
            total += sum(f); k += len(f)
    return total


def marks(f, tenth=False):
    s, standing = [], 10
    for j, c in enumerate(f):
        if c == 10 and standing == 10:
            s.append("X"); standing = 10 if tenth else 0
        elif c == standing and c > 0:
            s.append("/"); standing = 10
        else:
            s.append("-" if c == 0 else str(c)); standing -= c
            if tenth and standing == 0:
                standing = 10
    return " ".join(s)


class Game:
    """A 10-frame game on one lane. `bowl(req)` applies the seeded execution scatter to the requested release,
    rolls the ball (MuJoCo), counts the pins, updates the scorecard and resets / sweeps the deck by the rules."""

    def __init__(self, n_frames=MAX_FRAMES):
        self.n_frames = n_frames
        self.lane = Lane()
        self.frames = [[]]
        self.log = []
        self.last = None                 # the previous ball's record (with its trail)
        self.after_qpos = None           # the deck right after the previous ball (before the sweep), for the view
        self.sha = hashlib.sha256()
        self.done = False

    @property
    def frame(self):
        return len(self.frames) - 1

    @property
    def ball(self):
        return len(self.frames[-1])

    def standing_count(self):
        return int(sum(self.lane.standing))

    def execute(self, req):
        z = scatter(self.frame, self.ball)
        return {"board": req["board"] + SIG["board"] * z[0], "angle_deg": req["angle_deg"] + SIG["angle_deg"] * z[1],
                "speed": req["speed"] * (1 + SIG["speed_frac"] * z[2]), "rpm": max(0.0, req["rpm"] * (1 + SIG["rpm_frac"] * z[3])),
                "axis_deg": req["axis_deg"] + SIG["axis_deg"] * z[4]}

    def bowl(self, req, record=False):
        ex = self.execute(req)
        q_before = self.lane.d.qpos.copy()
        res, frames = self.lane.roll(ex["board"], ex["angle_deg"], ex["speed"], ex["rpm"], ex["axis_deg"], record=record)
        if res["gutter"]:
            # USBC 6b.1: a ball that leaves the lane before reaching the pins counts as a ball rolled, but its pinfall
            # does not count; the pins it moved are respotted (the deck as it was before the ball)
            res = dict(res, down=[False] * 10, count=0)
            self.lane.d.qpos[:] = q_before
            self.lane.d.qvel[:] = 0
            self.lane._park_ball()
            self.lane.mj.mj_forward(self.lane.m, self.lane.d)
        fi, bi = self.frame, self.ball
        before = list(self.lane.standing)
        cnt = res["count"]
        self.frames[-1].append(cnt)
        f = self.frames[-1]
        self.after_qpos = self.lane.d.qpos.copy()
        for i in range(10):
            if res["down"][i]:
                self.lane.standing[i] = False
        left = [i + 1 for i in range(10) if self.lane.standing[i]]
        # the deck after this ball: new rack, or sweep the deadwood
        frame_over = False
        if fi < 9:
            if cnt == 10 and bi == 0:
                frame_over = True
            elif bi == 1:
                frame_over = True
        else:
            if bi == 1 and f[0] + f[1] < 10:
                frame_over = True
            elif bi == 2:
                frame_over = True
        if frame_over or self.standing_count() == 0:
            self.lane.rack()
        else:
            self.lane.sweep(res["down"])
        self.sha.update(self.lane.state_bytes() + bytes([fi, bi, cnt]))
        rec = {"frame": fi + 1, "ball": bi + 1, "requested": req, "executed": {k: round(v, 6) for k, v in ex.items()},
               "count": cnt, "standing_before": int(sum(before)), "left": left,
               "strike": bi == 0 and cnt == 10 or (fi == 9 and cnt == 10 and sum(before) == 10),
               "spare": cnt > 0 and cnt == sum(before) and sum(before) < 10,
               "gutter": res["gutter"], "sim_t": res["t"], "trail": res["trail"]}
        self.log.append({k: v for k, v in rec.items() if k != "trail"})
        self.last = rec
        if frame_over:
            if fi + 1 >= self.n_frames:
                self.done = True
            else:
                self.frames.append([])
        return rec, frames

    def total(self):
        return score_total(self.frames)

    def state_sha(self):
        return self.sha.hexdigest()

    def scorecard(self):
        cum = frame_scores(self.frames)
        return [{"frame": i + 1, "balls": f, "marks": marks(f, i == 9), "cumulative": cum[i]}
                for i, f in enumerate(self.frames) if f or i == self.frame]


def replay(balls, n_frames=MAX_FRAMES):
    g = Game(n_frames)
    for b in balls:
        if g.done:
            break
        g.bowl({k: b[k] for k in ("board", "angle_deg", "speed", "rpm", "axis_deg")})
    return g


# ---------------------------------------------------------------- cameras
IMG_W, IMG_H = 960, 540
FOVY_APPROACH = 38.0
APPROACH_POS = (-2.2, 0.0, 1.55)
APPROACH_PITCH = -5.0
PANEL_W, PANEL_H = 1000, 340
PANEL_X = [(-0.5, 4.5), (4.5, 9.5), (9.5, 14.5), (14.5, 19.5)]
PANEL_Z = 6.0
FOVY_PANEL = 2 * math.degrees(math.atan(PANEL_H / PANEL_W * 2.5 / PANEL_Z))
DECK_POS = (HEAD_PIN_X - 2.4, 0.0, 0.95)
DECK_PITCH = -17.0
FOVY_DECK = 30.0


def spec_cameras():
    return [
        {"name": "approach", "size_px": [IMG_W, IMG_H], "fovy_deg": FOVY_APPROACH, "pos_m": list(APPROACH_POS),
         "look": "along +x (down the lane)", "pitch_deg": APPROACH_PITCH,
         "what": "the bowler's eye on the approach, behind the foul line at the centre of the lane"},
        {"name": "lane", "size_px": [PANEL_W, PANEL_H * 4], "fovy_deg_per_panel": round(FOVY_PANEL, 4),
         "panels": [{"x_range_m": list(p), "camera_pos_m": [(p[0] + p[1]) / 2, 0.0, PANEL_Z],
                     "rows_px": [k * PANEL_H, (k + 1) * PANEL_H]} for k, p in enumerate(PANEL_X)],
         "look": "straight down; in each panel image right = +x (towards the pins), image up = +y (left)",
         "what": "the lane from above in four stacked panels (5 m each, top panel = nearest the foul line); the "
                 "previous ball's path is drawn as yellow dots (every 1/30 s)"},
        {"name": "pindeck", "size_px": [IMG_W, IMG_H], "fovy_deg": FOVY_DECK, "pos_m": list(DECK_POS),
         "look": "along +x", "pitch_deg": DECK_PITCH,
         "what": "the pin deck now (only the pins standing for this ball)"},
        {"name": "pindeck_after", "size_px": [IMG_W, IMG_H], "fovy_deg": FOVY_DECK, "pos_m": list(DECK_POS),
         "look": "along +x", "pitch_deg": DECK_PITCH,
         "what": "the pin deck right after your previous ball settled, before the deadwood was swept"},
    ]


class Views:
    def __init__(self, lane: Lane):
        import mujoco as mj
        self.mj = mj
        self.m = lane.m
        self.d = mj.MjData(self.m)
        self.r = {}

    def renderer(self, w, h):
        if (w, h) not in self.r:
            self.r[(w, h)] = self.mj.Renderer(self.m, height=h, width=w)
        return self.r[(w, h)]

    def cam(self, pos, yaw_deg, pitch_deg):
        c = self.mj.MjvCamera()
        fw = np.array([math.cos(math.radians(pitch_deg)) * math.cos(math.radians(yaw_deg)),
                       math.cos(math.radians(pitch_deg)) * math.sin(math.radians(yaw_deg)),
                       math.sin(math.radians(pitch_deg))])
        c.lookat[:] = np.asarray(pos) + fw
        c.distance = 1.0
        c.azimuth = yaw_deg
        c.elevation = pitch_deg
        return c

    def shot(self, qpos, camera, w, h, fovy):
        self.d.qpos[:] = qpos
        self.mj.mj_forward(self.m, self.d)
        r = self.renderer(w, h)
        self.m.vis.global_.fovy = fovy
        r.update_scene(self.d, camera=camera)
        return r.render().copy()

    def lane_panels(self, qpos, trail=None):
        from PIL import Image, ImageDraw
        ims = []
        for k, (x0, x1) in enumerate(PANEL_X):
            im = self.shot(qpos, self.cam(((x0 + x1) / 2, 0.0, PANEL_Z), 90.0, -90.0), PANEL_W, PANEL_H, FOVY_PANEL)
            ims.append(im)
        img = Image.fromarray(np.concatenate(ims, axis=0))
        dr = ImageDraw.Draw(img)
        f = PANEL_H / 2 / math.tan(math.radians(FOVY_PANEL / 2))
        if trail:
            for t, x, y in trail:
                for k, (x0, x1) in enumerate(PANEL_X):
                    if x0 <= x < x1:
                        cx = (x0 + x1) / 2
                        u = PANEL_W / 2 + f * (x - cx) / PANEL_Z
                        v = PANEL_H / 2 - f * y / PANEL_Z + k * PANEL_H
                        dr.ellipse([u - 2.5, v - 2.5, u + 2.5, v + 2.5], fill=(255, 225, 0))
        for k in range(1, 4):
            dr.line([(0, k * PANEL_H), (PANEL_W, k * PANEL_H)], fill=(255, 255, 255), width=2)
        for k, (x0, x1) in enumerate(PANEL_X):
            dr.text((6, k * PANEL_H + 4), f"panel {k + 1}: x {x0:g} .. {x1:g} m", fill=(255, 255, 255))
        return np.asarray(img)

    def decision_views(self, g: Game):
        q = g.lane.d.qpos.copy()
        out = {"approach": self.shot(q, self.cam(APPROACH_POS, 0.0, APPROACH_PITCH), IMG_W, IMG_H, FOVY_APPROACH),
               "lane": self.lane_panels(q, g.last["trail"] if g.last else None),
               "pindeck": self.shot(q, self.cam(DECK_POS, 0.0, DECK_PITCH), IMG_W, IMG_H, FOVY_DECK)}
        if g.after_qpos is not None:
            out["pindeck_after"] = self.shot(g.after_qpos, self.cam(DECK_POS, 0.0, DECK_PITCH), IMG_W, IMG_H, FOVY_DECK)
        return out

    def tv(self, qpos, bx, by):
        """Broadcast camera: behind and above the ball while it runs down the lane, then the pin deck."""
        c = self.mj.MjvCamera()
        if bx < HEAD_PIN_X - 3.0:
            c.lookat[:] = [bx + 1.2, by * 0.5, 0.15]
            c.distance, c.azimuth, c.elevation = 3.4, 0.0, -18.0
            fov = 45.0
        else:
            c.lookat[:] = [HEAD_PIN_X + 0.35, 0.0, 0.15]
            c.distance, c.azimuth, c.elevation = 2.9, 0.0, -20.0
            fov = 45.0
        self.d.qpos[:] = qpos
        self.mj.mj_forward(self.m, self.d)
        r = self.renderer(IMG_W, 544)
        self.m.vis.global_.fovy = fov
        r.update_scene(self.d, camera=c)
        return r.render().copy()


def render_video(balls, out, n_frames=MAX_FRAMES, fps=FPS):
    """Replay video: a camera following the ball, then the pin deck; a scoreboard line. Real time."""
    import imageio.v2 as imageio
    from PIL import Image, ImageDraw
    g = Game(n_frames)
    v = Views(g.lane)
    w = imageio.get_writer(out, fps=fps, macro_block_size=8)
    bq = g.lane.ball_q

    def put(img, txt):
        im = Image.fromarray(img)
        dr = ImageDraw.Draw(im)
        dr.rectangle([0, 0, im.width, 24], fill=(0, 0, 0))
        dr.text((8, 6), txt, fill=(255, 255, 255))
        w.append_data(np.asarray(im))

    for b in balls:
        if g.done:
            break
        fi, bi = g.frame, g.ball
        hdr = f"frame {fi + 1} ball {bi + 1}   score {g.total()}   "
        req = {k: b[k] for k in ("board", "angle_deg", "speed", "rpm", "axis_deg")}
        q0 = g.lane.d.qpos.copy()
        p0, _, _ = release_state(g.execute(req)["board"], 0, 1, 0, 0)
        q0[bq:bq + 3] = p0
        for _ in range(int(fps * 0.5)):
            put(v.tv(q0, p0[0], p0[1]), hdr + "release: board %.1f  angle %+.2f deg  %.2f m/s  %.0f rpm  axis %+.0f deg"
                % (req["board"], req["angle_deg"], req["speed"], req["rpm"], req["axis_deg"]))
        rec, frames = g.bowl(req, record=True)
        for t, q in frames:
            put(v.tv(q, q[bq], q[bq + 1]), hdr + f"t {t:4.2f} s")
        res = "STRIKE" if rec["strike"] else ("SPARE" if rec["spare"] else f"{rec['count']} pins")
        for _ in range(int(fps * 0.8)):
            put(v.tv(frames[-1][1], 99, 0), hdr + f"-> {res}   total {g.total()}")
    w.close()


if __name__ == "__main__":
    if sys.argv[1:2] == ["replay"]:
        tr = json.load(open(sys.argv[2]))
        g = replay(tr["balls"], tr.get("n_frames", MAX_FRAMES))
        print(json.dumps({"sha": g.state_sha(), "frames": g.frames, "total": g.total(), "done": g.done}))
