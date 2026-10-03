"""Core of the robot tennis match service (interactive mode): first to 5 points against a scripted opponent.

World (metres, seconds): court surface z = 0, long axis y, net = the plane y = 0 (top 0.914 m at the centre, rising
linearly to 1.07 m at the singles sticks x = +-5.029). The robot's half is y < 0, the opponent's y > 0. ITF singles
court |x| <= 4.115, |y| <= 11.885 (lines are in); service boxes |y| <= 6.40.

Robot: a Franka Panda arm on a 0.55 m pedestal whose base slides on rails in x and y (2 prismatic joints, speed
<= BASE_VMAX, acceleration <= BASE_AMAX), holding a tennis racket (head centre 0.52 m beyond the flange, strung face
an ellipse of half axes 0.13 x 0.16 m). One action = 9 absolute joint targets [base_x, base_y, q1..q7] held for
10 ms; a PD controller with bias compensation (1 ms physics steps, MuJoCo) tracks them; target steps are limited to
the joint speed limits (checked).

Ball (not a MuJoCo body; integrated here at 1 ms, semi-implicit Euler, pure Python floats, deterministic):
ITF ball, mass 57.7 g, radius 33.5 mm. Forces: gravity; drag 0.5 rho C_D A |v| v with C_D = 0.55 (Goodwill, Chin &
Haake 2004; the value Robot Sports Gym, MIT, uses); Magnus lift 0.5 rho C_L A |v|^2 along (w x v)/|w x v| with
C_L = 1 / (2 + 1/S), S = r|w|/|v| (the Watts & Ferrer / Goodwill fit for tennis balls). Spin is constant in flight.
Court bounce (hard court, impulse model of Cross 2002/2005): vertical restitution E_COURT = 0.76 (the ITF rebound
test: 1.35-1.47 m from 2.54 m on a rigid surface), friction MU_COURT = 0.6 between ball and court; the tangential
impulse stops the contact point's sliding or is limited by friction; the ball's moment of inertia is
ALPHA m r^2 with ALPHA = 0.55 (thick-walled hollow sphere). The same law, with the racket's strings (restitution
E_RACKET = 0.82 at the head centre, dropping by up to 25 % to the frame, friction MU_RACKET = 0.4) and the racket
treated as infinitely massive (the robot holds it rigidly), gives the racket impact.
Net: a ball whose centre comes within r of the net's top edge (the tape: y = 0, z = net top) bounces off the edge (impulse
law with restitution E_NET, friction MU_NET) and goes on (a net cord, ITF Rule 25 a); a ball crossing the
plane y = 0 lower than that (into the net) ends there.

Point flow (all inside Match.step(), so a recorded action sequence replays the whole match bit-exactly):
  ready    READY_STEPS; the opponent holds the ball at its serving position.
  serve    the opponent serves (a seeded serve per point: speed, spin, target in the service box), alternately from
           the deuce and the ad side.
  our leg  the ball comes to us; the serve must bounce in our service box diagonally opposite (else our point) and
           then our racket must hit it; any other ball may be volleyed or hit after one bounce (ITF 24 e; a second
           bounce is a miss). Our shot is good if it crosses the net above the net and its first bounce is in the
           opponent's singles court.
  opp leg  the opponent (below) returns it (a new "our leg" starts at its hit) or cannot reach it (our point).

The opponent (LEVELS): a kinematic player moving along its base line (y = OPP_Y), at the centre between points.
`reaction_s` after our hit it predicts the flight perfectly and moves in x at `chase` towards where it will hit the
ball (after the bounce on its half, at the top of the bounce or when the ball reaches y = OPP_HIT_Y); after its own
shots it walks back to the centre at `recover`. It evaluates
    pressure = max(max(0, |ball x - its x at the hit|) / reach, (our shot's speed - SPEED_FREE) / (max_speed - SPEED_FREE))
and, deterministically: pressure > 1 -> it misses (our point); > PRESSURE_WEAK -> a weak return (slow, central, no
spin); < PRESSURE_PASSIVE -> it attacks (its widest, fastest, most spinning ball); else a normal return (a seeded
target within the level's width, its pace, topspin or slice). It sets the ball's velocity and spin (an impulse; its
racket is drawn only) so that the ball lands deep in our court, clears the net by >= 0.25 m and our robot can reach
the flight from where its base stands; an unreachable shot moves towards the centre and slows down. It never makes
unforced errors.
"""
from __future__ import annotations

import copy
import hashlib
import io
import json
import math
import os
from collections import deque
from pathlib import Path

import numpy as np

import mujoco as mj

HERE = Path(__file__).resolve().parent
SCENE = Path(os.environ.get("RCB_TN_SCENE", HERE / "scene" / "tn_scene.xml"))

CONTROL_DT, SUBSTEPS, PHYS_DT = 0.01, 10, 0.001
GRAV = 9.81
# ---- ball (ITF) and air
BALL_M, BALL_R, RHO, C_D = 0.0577, 0.0335, 1.21, 0.55
BALL_A = math.pi * BALL_R ** 2
K_DRAG = 0.5 * RHO * C_D * BALL_A / BALL_M          # 1/m
K_LIFT = 0.5 * RHO * BALL_A / BALL_M                # 1/m (times C_L)
ALPHA = 0.55                                        # I = ALPHA m r^2
E_COURT, MU_COURT = 0.76, 0.6
E_NET, MU_NET = 0.3, 0.3                            # net cord: the ball against the net's top edge (the tape)
E_RACKET, MU_RACKET, OFFCENTRE_LOSS = 0.82, 0.4, 0.25
RACKET_GAIN = 5.0                                   # the contact sees GAIN x the delivered head velocity (see below)
HEAD_A, HEAD_B = 0.13, 0.16                         # strung-area half axes (racket local y, z)
# ---- court
COURT_X, COURT_Y, SERVICE_Y, DOUBLES_X = 4.115, 11.885, 6.40, 5.485
NET_C, NET_P, NET_STICK, NET_POST = 0.914, 1.07, 5.029, 6.40
# ---- robot
ARM_VEL = np.array([2.175, 2.175, 2.175, 2.175, 2.61, 2.61, 2.61])
BASE_VMAX, BASE_AMAX = 4.0, 8.0
VEL_LIMIT = np.r_[BASE_VMAX, BASE_VMAX, ARM_VEL]
KP = np.array([6e4, 6e4, 2400.0, 2400.0, 2400.0, 2400.0, 1000.0, 600.0, 200.0])
KD = np.array([4e3, 4e3, 100.0, 100.0, 100.0, 100.0, 30.0, 20.0, 6.0])
JOINTS = ["base_x", "base_y"] + [f"joint{i}" for i in range(1, 8)]
HOME = np.array([0.0, -11.4])                 # the robot's base between shots
PED_H = 0.55                                  # link0 height on the pedestal; shoulder at PED_H + 0.333
SHOULDER_Z = PED_H + 0.333
Q0_ARM = np.array([0.0, -0.3, 0.0, -1.9, 0.0, 1.9, 0.785])   # ready pose (refined at import by IK, see _ready_pose)
BASE_LO, BASE_HI = np.array([-5.9, -15.4]), np.array([5.9, -7.6])
STANCE_OFF = np.array([0.62, 0.30])           # forehand stance: base = contact xy - STANCE_OFF (see stance())

REVISION = "wallclock-6"                 # 4: volleys legal except on the serve; the serve is judged against the box; 5: net cord; 6: the duel's match format (win by 2, cap 7, lets, match limit)
# The match format, the same in the single-player game and the duel (duel.py imports these):
WIN_POINTS = 5                  # first to 5; from 4:4 a lead of WIN_BY is needed ...
WIN_BY = 2
CAP_POINTS = 7                  # ... but at 6:6 the next point wins (at most 7)
MAX_HITS = 400                  # match limit: after 400 racket hits (both players) or 40 points played (lets included)
MAX_POINTS = 40                 # the match ends: more points wins; equal points: the winner of the last point wins
READY_STEPS = 100               # 1.0 s between points
LEG_STEPS = 400                 # an incoming ball is decided within 4 s
CAM_EVERY = 2                   # 50 Hz camera snapshots
SWING_AFTER = 20                # first decision point: 0.2 s after the ball was played (serve or the opponent's hit)
ADJUST_FRAMES = 3               # second decision point: 3rd camera frame (0.06 s) after the bounce on our half
OPP_Y, OPP_HIT_Y = 12.3, 13.2
OPP_XLIM = 5.6
SPEED_FREE = 26.0
PRESSURE_WEAK, PRESSURE_PASSIVE = 0.75, 0.35
NET_MARGIN_OPP = 0.25

LEVELS = {   # defence: reaction, chase / recovery speed, reach, too-fast threshold; attack: width, pace, spin; serves
    1: dict(reaction_s=0.38, chase=3.0, recover=1.9, reach=1.15, max_speed=40.0, width=2.6, pace=17.0, spin=100.0,
            serve=(24.0, 28.0), serve_width=2.4, serve_spin=60.0, seed=101),
    2: dict(reaction_s=0.35, chase=3.1, recover=2.1, reach=1.15, max_speed=44.0, width=3.3, pace=20.0, spin=180.0,
            serve=(28.0, 33.0), serve_width=3.3, serve_spin=110.0, seed=202),
    3: dict(reaction_s=0.345, chase=3.15, recover=2.2, reach=1.16, max_speed=45.0, width=3.4, pace=21.0, spin=200.0,
            serve=(29.0, 34.0), serve_width=3.4, serve_spin=125.0, seed=303),
    4: dict(reaction_s=0.335, chase=3.2, recover=2.3, reach=1.18, max_speed=46.0, width=3.5, pace=22.0, spin=220.0,
            serve=(30.0, 35.0), serve_width=3.5, serve_spin=140.0, seed=404),
}


# ---------------------------------------------------------------------- ball physics (pure Python floats)
def net_top(x: float) -> float:
    ax = min(abs(x), NET_STICK)
    return NET_C + (NET_P - NET_C) * ax / NET_STICK


def _accel(vx, vy, vz, wx, wy, wz):
    sp = math.sqrt(vx * vx + vy * vy + vz * vz)
    ax = -K_DRAG * sp * vx
    ay = -K_DRAG * sp * vy
    az = -GRAV - K_DRAG * sp * vz
    cx = wy * vz - wz * vy; cy = wz * vx - wx * vz; cz = wx * vy - wy * vx      # w x v
    cn = math.sqrt(cx * cx + cy * cy + cz * cz)
    if cn > 1e-9 and sp > 0.1:
        wn = math.sqrt(wx * wx + wy * wy + wz * wz)
        S = BALL_R * wn / sp
        cl = S / (2.0 * S + 1.0)                     # 1 / (2 + 1/S)
        f = K_LIFT * cl * sp * sp / cn
        ax += f * cx; ay += f * cy; az += f * cz
    return ax, ay, az


def impact(v, w, n, e, mu):
    """Impulse of the ball (velocity v, spin w, relative to the surface) on a rigid, infinitely massive surface
    with unit normal n pointing towards the ball: normal restitution e, Coulomb friction mu, the tangential impulse
    stops the contact point's sliding (rolling) or is limited by friction. Returns (v', w') relative to the
    surface."""
    vx, vy, vz = v; wx, wy, wz = w; nx, ny, nz = n
    vn = vx * nx + vy * ny + vz * nz
    if vn >= 0:
        return v, w
    # contact point velocity: u = v + w x (-r n)
    rx, ry, rz = -BALL_R * nx, -BALL_R * ny, -BALL_R * nz
    ux = vx + (wy * rz - wz * ry); uy = vy + (wz * rx - wx * rz); uz = vz + (wx * ry - wy * rx)
    un = ux * nx + uy * ny + uz * nz
    tx, ty, tz = ux - un * nx, uy - un * ny, uz - un * nz
    tn = math.sqrt(tx * tx + ty * ty + tz * tz)
    jn = (1.0 + e) * (-vn)                               # normal impulse per unit mass
    jt = 0.0
    if tn > 1e-12:
        jt = min(mu * jn, tn * ALPHA / (1.0 + ALPHA))
        jx, jy, jz = -jt * tx / tn, -jt * ty / tn, -jt * tz / tn
    else:
        jx = jy = jz = 0.0
    v2 = (vx + jn * nx + jx, vy + jn * ny + jy, vz + jn * nz + jz)
    # dw = (r x J) / (ALPHA r^2)
    k = 1.0 / (ALPHA * BALL_R * BALL_R)
    w2 = (wx + k * (ry * jz - rz * jy), wy + k * (rz * jx - rx * jz), wz + k * (rx * jy - ry * jx))
    return v2, w2


def _cord(p, q):
    """Net cord: the first point of the step p -> q where the ball's centre comes within BALL_R of the net's top edge
    (the line y = 0, z = net top, |x| <= NET_POST), as (fraction s, contact point, unit normal from the edge to the
    ball) or None. Only an approach from outside counts (a ball already touching the edge moves off it)."""
    y0, dy = p[1], q[1] - p[1]
    xm = p[0] + 0.5 * (q[0] - p[0])
    if abs(xm) > NET_POST:
        return None
    top = net_top(xm)
    z0, dz = p[2] - top, q[2] - p[2]
    c = y0 * y0 + z0 * z0 - BALL_R * BALL_R
    if c <= 0.0:
        return None
    a = dy * dy + dz * dz
    if a <= 0.0:
        return None
    b = 2.0 * (y0 * dy + z0 * dz)
    disc = b * b - 4.0 * a * c
    if disc < 0.0:
        return None
    s = (-b - math.sqrt(disc)) / (2.0 * a)
    if not (0.0 <= s <= 1.0):
        return None
    cp = (p[0] + s * (q[0] - p[0]), y0 + s * dy, p[2] + s * dz)
    ny, nz = cp[1], cp[2] - top
    nn = math.hypot(ny, nz)
    return s, cp, (0.0, ny / nn, nz / nn)


def ball_advance(p, v, w):
    """One 1 ms step: (p', v', w', event) with event None, ("bounce", x, y), ("cord", x, z) (the ball touched the net's
    top edge and goes on, ITF Rule 25 a) or ("net", x, z) (it went into the net below the edge: dead)."""
    ax, ay, az = _accel(v[0], v[1], v[2], w[0], w[1], w[2])
    vx = v[0] + ax * PHYS_DT; vy = v[1] + ay * PHYS_DT; vz = v[2] + az * PHYS_DT
    px = p[0] + vx * PHYS_DT; py = p[1] + vy * PHYS_DT; pz = p[2] + vz * PHYS_DT
    hit = _cord(p, (px, py, pz))
    if hit is not None:
        s, cp, n = hit
        if vy * n[1] + vz * n[2] < 0.0:
            v2, w2 = impact((vx, vy, vz), w, n, E_NET, MU_NET)
            rem = (1.0 - s) * PHYS_DT
            q = (cp[0] + v2[0] * rem, cp[1] + v2[1] * rem, cp[2] + v2[2] * rem)
            return q, v2, w2, ("cord", cp[0], cp[2])
    if (p[1] > 0) != (py > 0) and p[1] != py:
        f = p[1] / (p[1] - py)
        xn = p[0] + f * (px - p[0]); zn = p[2] + f * (pz - p[2])
        if abs(xn) <= NET_POST and zn < net_top(xn) - BALL_R:
            return (xn, 0.0, max(zn, BALL_R)), (0.0, 0.0, 0.0), (0.0, 0.0, 0.0), ("net", xn, zn)
    if pz < BALL_R and vz < 0:
        f = (p[2] - BALL_R) / (p[2] - pz) if p[2] != pz else 1.0
        f = min(max(f, 0.0), 1.0)
        cx = p[0] + f * (px - p[0]); cy = p[1] + f * (py - p[1])
        v2, w2 = impact((vx, vy, vz), w, (0.0, 0.0, 1.0), E_COURT, MU_COURT)
        rem = (1.0 - f) * PHYS_DT
        return ((cx + v2[0] * rem, cy + v2[1] * rem, BALL_R + v2[2] * rem), v2, w2, ("bounce", cx, cy))
    return (px, py, pz), (vx, vy, vz), w, None


def predict(p, v, w, n_max=4000, stop_bounces=2):
    """Ball-only flight: arrays P, V, W (N, 3) after 1..N steps of 1 ms and the events [(i, kind, x, y_or_z)],
    until `stop_bounces` bounces or the net (inclusive)."""
    p = tuple(float(x) for x in p); v = tuple(float(x) for x in v); w = tuple(float(x) for x in w)
    P, V, Wl, ev = [], [], [], []
    nb = 0
    for i in range(n_max):
        p, v, w, e = ball_advance(p, v, w)
        P.append(p); V.append(v); Wl.append(w)
        if e is not None:
            ev.append((i, e[0], e[1], e[2]))
            if e[0] == "net":
                break
            if e[0] == "cord":
                continue
            nb += 1
            if nb >= stop_bounces:
                break
    return np.array(P), np.array(V), np.array(Wl), ev


def first_landing(p, v, w, n_max=4000):
    """(x, y) of the first bounce, the net clearance at y = 0 (height above the net top, or None if it does not
    cross), and the flight time; ("net", ...) as None landing."""
    p = tuple(float(x) for x in p); v = tuple(float(x) for x in v); w = tuple(float(x) for x in w)
    clear = None
    for i in range(n_max):
        p0 = p
        p, v, w, e = ball_advance(p, v, w)
        if (p0[1] > 0) != (p[1] > 0) and p0[1] != p[1] and clear is None:
            f = p0[1] / (p0[1] - p[1])
            xn = p0[0] + f * (p[0] - p0[0]); zn = p0[2] + f * (p[2] - p0[2])
            clear = zn - BALL_R - net_top(xn)
        if e is not None and e[0] != "cord":
            if e[0] == "net":
                return None, clear, (i + 1) * PHYS_DT
            return (e[1], e[2]), clear, (i + 1) * PHYS_DT
    return None, clear, n_max * PHYS_DT


def serve_index(n_played, half):
    """The serve generator's index of a point: the points played so far (lets included, so a replayed point gets a
    fresh serve) and the box half (0: deuce, the receiver's right; 1: ad), which changes every two points scored:
    deuce, deuce, ad, ad, ... (the same in the single-player game and the duel)."""
    return 2 * int(n_played) + int(half)


def match_won(a, b):
    """First to WIN_POINTS; from 4:4 a lead of WIN_BY; at most CAP_POINTS."""
    return (max(a, b) >= WIN_POINTS and abs(a - b) >= WIN_BY) or max(a, b) >= CAP_POINTS


def match_winner(a, b, points, last_resort):
    """The winner (0 for a, 1 for b) of a finished match: by the score, else (a match limit at equal points) the winner
    of the last point that was not a let, else `last_resort`. `points`: the winners (0, 1 or None for a let) in order."""
    if a != b:
        return 0 if a > b else 1
    won = [w for w in points if w is not None]
    return won[-1] if won else last_resort


def in_court(x, y, side):
    """side +1: the opponent's singles court, -1: ours (lines are in)."""
    return abs(x) <= COURT_X and (0.0 < side * y <= COURT_Y)


def in_service_box(x, y, sx):
    """Our service box diagonal to a server standing at sx (the opponent serves from y > 0)."""
    return (0.0 <= -np.sign(sx) * x <= COURT_X) and (-SERVICE_Y <= y < 0.0)


def base_goto(b, v, goal):
    """One control step of the base's go-to generator (bounded speed and acceleration): new (target, velocity)."""
    e = goal - b; dist = float(np.hypot(e[0], e[1]))
    sp = float(np.hypot(v[0], v[1]))
    if dist < 0.004 and sp < 0.2:
        return goal.copy(), np.zeros(2)
    vdes = e / max(dist, 1e-9) * min(BASE_VMAX * 0.98, math.sqrt(2 * BASE_AMAX * 0.85 * dist))
    dv = vdes - v; ndv = float(np.hypot(dv[0], dv[1])); lim = BASE_AMAX * CONTROL_DT
    if ndv > lim:
        dv = dv * (lim / ndv)
    v = v + dv
    nv = float(np.hypot(v[0], v[1]))
    if nv > BASE_VMAX * 0.98:
        v = v * (BASE_VMAX * 0.98 / nv)
    return np.clip(b + v * CONTROL_DT, BASE_LO, BASE_HI), v


def base_time(dist):
    """Approximate time for the base to travel `dist` from rest to rest."""
    a, vm = BASE_AMAX * 0.85, BASE_VMAX * 0.98
    return 2 * math.sqrt(dist / a) if dist < vm * vm / a else dist / vm + vm / a


def stance(p):
    """Where the base stands to meet a contact (racket-head centre) at p with a forehand: the contact STANCE_OFF to
    the right of and in front of the base. Uses only the commanded racket position."""
    return np.clip(np.asarray(p[:2], float) - STANCE_OFF, BASE_LO, BASE_HI)


def hermite(q0, v0, q1, v1, T, n):
    t = np.arange(1, n + 1) * (T / n)
    s = t / T
    h00 = 2 * s**3 - 3 * s**2 + 1; h10 = s**3 - 2 * s**2 + s; h01 = -2 * s**3 + 3 * s**2; h11 = s**3 - s**2
    return h00[:, None] * q0 + h10[:, None] * T * v0 + h01[:, None] * q1 + h11[:, None] * T * v1


# ---------------------------------------------------------------------- robot + ball physics
class Phys:
    """MuJoCo robot (rail base + Franka + racket), the ball integrator and the racket impact model."""

    def __init__(self):
        self.m = mj.MjModel.from_xml_path(str(SCENE))
        self.d = mj.MjData(self.m)
        m = self.m
        jid = [mj.mj_name2id(m, mj.mjtObj.mjOBJ_JOINT, j) for j in JOINTS]
        self.qa = np.array([m.jnt_qposadr[j] for j in jid]); self.va = np.array([m.jnt_dofadr[j] for j in jid])
        self.lo = m.jnt_range[jid, 0].copy(); self.hi = m.jnt_range[jid, 1].copy()
        self.site = mj.mj_name2id(m, mj.mjtObj.mjOBJ_SITE, "racket_center")
        self.kin = mj.MjData(m)
        self.steps_total = 0

    def reset(self, q9):
        m, d = self.m, self.d
        mj.mj_resetData(m, d)
        d.qpos[self.qa] = q9
        mj.mj_forward(m, d)
        self.target = np.asarray(q9, float).copy()
        self.k = 0
        self._actions: list[np.ndarray] = []
        self.b_p, self.b_v, self.b_w, self.b_live = (0.0, 11.0, 1.0), (0.0, 0.0, 0.0), (0.0, 0.0, 0.0), False
        self.hit_enabled = False
        self.events: list[dict] = []
        self._prev = None

    def copy_from(self, o: "Phys"):
        d = self.d
        mj.mj_resetData(self.m, d)
        d.qpos[:] = o.d.qpos; d.qvel[:] = o.d.qvel; d.qacc_warmstart[:] = o.d.qacc_warmstart; d.time = o.d.time
        d.ctrl[:] = o.d.ctrl
        mj.mj_forward(self.m, d)
        self.target = o.target.copy(); self.k = o.k; self._actions = []
        self.b_p, self.b_v, self.b_w, self.b_live, self.hit_enabled = o.b_p, o.b_v, o.b_w, o.b_live, o.hit_enabled
        self.events = []
        self._prev = None if o._prev is None else tuple(x.copy() if hasattr(x, "copy") else x for x in o._prev)

    def check_target(self, q):
        if q.shape != (9,) or not np.all(np.isfinite(q)):
            raise ValueError(f"action must be 9 finite joint targets, got {q.shape}")
        if (q < self.lo - 1e-9).any() or (q > self.hi + 1e-9).any():
            raise ValueError(f"step {self.k}: joint target outside range: {q}")
        dq = np.abs(q - self.target)
        lim = VEL_LIMIT * CONTROL_DT * (1 + 1e-6) + 1e-12
        if (dq > lim).any():
            j = int(np.argmax(dq / lim))
            raise ValueError(f"step {self.k}: joint {JOINTS[j]} target moved {dq[j]:.5f} in one control step "
                             f"(limit {VEL_LIMIT[j] * CONTROL_DT:.5f})")

    def step(self, q):
        q = np.asarray(q, dtype=np.float64).reshape(-1)
        self.check_target(q)
        m, d = self.m, self.d
        q_prev = self.target
        qd_des = (q - q_prev) / CONTROL_DT
        lo, hi = m.actuator_ctrlrange[:, 0], m.actuator_ctrlrange[:, 1]
        for j in range(1, SUBSTEPS + 1):
            q_des = q_prev + (q - q_prev) * (j / SUBSTEPS)
            tau = KP * (q_des - d.qpos[self.qa]) + KD * (qd_des - d.qvel[self.va]) + d.qfrc_bias[self.va]
            d.ctrl[:] = np.clip(tau, lo, hi)
            mj.mj_step(m, d)
            # site pose now = the pose at the start of this step (time t_n), the same time as self.b_p
            R = d.site_xmat[self.site].reshape(3, 3)
            c = d.site_xpos[self.site].copy(); fr = R.copy()
            if self.b_live:
                if self.hit_enabled and self._prev is not None:
                    self._check_hit(c, fr)
                self._prev = (c, fr, self.b_p)
                self._advance_ball()
            else:
                self._prev = (c, fr, self.b_p)
        self.target = q.copy()
        self._actions.append(q.copy())
        self.k += 1
        self.steps_total += SUBSTEPS

    def actions(self) -> np.ndarray:
        return np.array(self._actions, dtype=np.float64).reshape(-1, 9)

    def _advance_ball(self):
        p, v, w, e = ball_advance(self.b_p, self.b_v, self.b_w)
        self.b_p, self.b_v, self.b_w = p, v, w
        if e is None:
            return
        if e[0] == "net":
            self.b_live = False
            self.events.append({"kind": "net", "k": self.k, "x": round(e[1], 4), "z": round(e[2], 4)})
        elif e[0] == "cord":
            self.events.append({"kind": "cord", "k": self.k, "x": round(e[1], 4), "z": round(e[2], 4)})
        else:
            self.events.append({"kind": "bounce", "k": self.k, "x": round(e[1], 4), "y": round(e[2], 4),
                                "side": "own" if e[2] < 0 else "opp"})

    def _check_hit(self, c1, R1):
        c0, R0, p0 = self._prev
        n0, n1 = R0[:, 0], R1[:, 0]
        p0a = np.array(p0); p1a = np.array(self.b_p)
        s0 = float((p0a - c0) @ n0); s1 = float((p1a - c1) @ n1)
        side = 1.0 if s0 >= 0 else -1.0
        a0, a1 = side * s0, side * s1
        if not (a0 >= BALL_R > a1):
            return
        f = (a0 - BALL_R) / (a0 - a1)
        pc = c0 + f * (c1 - c0); ps = p0a + f * (p1a - p0a)
        nn = n0 + f * (n1 - n0); nn = nn / np.linalg.norm(nn)
        r = ps - pc
        la, lb = float(r @ R1[:, 1]), float(r @ R1[:, 2])
        rho2 = (la / HEAD_A) ** 2 + (lb / HEAD_B) ** 2
        if rho2 > 1.0:
            return
        vr = (c1 - c0) / PHYS_DT * RACKET_GAIN            # effective racket velocity at the strings
        n_out = side * nn
        vb = np.array(self.b_v)
        e = E_RACKET * (1.0 - OFFCENTRE_LOSS * rho2)
        u = tuple(float(x) for x in vb - vr)
        u2, w2 = impact(u, self.b_w, tuple(float(x) for x in n_out), e, MU_RACKET)
        v_out = np.array(u2) + vr
        p_new = pc + (r - (r @ nn) * nn) + n_out * (BALL_R + 0.0005)
        self.b_p = tuple(float(x) for x in p_new); self.b_v = tuple(float(x) for x in v_out)
        self.b_w = tuple(float(x) for x in w2)
        self.hit_enabled = False
        self.events.append({"kind": "hit", "k": self.k, "pos": [round(float(x), 4) for x in ps],
                            "offcentre": round(math.sqrt(rho2), 3), "racket_vel": [round(float(x), 3) for x in vr],
                            "normal": [round(float(x), 4) for x in n_out], "speed": round(float(np.linalg.norm(v_out)), 3),
                            "v_out": [round(float(x), 3) for x in v_out], "spin_out": [round(float(x), 1) for x in w2]})

    # kinematics (scratch data; never stepped)
    def kin_set(self, q9):
        self.kin.qpos[:] = self.d.qpos
        self.kin.qpos[self.qa] = q9
        mj.mj_kinematics(self.m, self.kin)
        mj.mj_comPos(self.m, self.kin)

    def fk(self, q9):
        self.kin_set(np.asarray(q9, float))
        return self.kin.site_xpos[self.site].copy(), self.kin.site_xmat[self.site].reshape(3, 3).copy()

    def jac(self, q9):
        """(6, 7) racket-centre Jacobian w.r.t. the arm joints."""
        self.kin_set(np.asarray(q9, float))
        jp = np.zeros((3, self.m.nv)); jr = np.zeros((3, self.m.nv))
        mj.mj_jacSite(self.m, self.kin, jp, jr, self.site)
        return np.vstack([jp[:, self.va[2:]], jr[:, self.va[2:]]])

    def racket_state(self):
        d = self.d
        jp = np.zeros((3, self.m.nv)); jr = np.zeros((3, self.m.nv))
        mj.mj_jacSite(self.m, d, jp, jr, self.site)
        return (d.site_xpos[self.site].copy(), d.site_xmat[self.site].reshape(3, 3)[:, 0].copy(), jp @ d.qvel)

    def state_sha(self):
        d = self.d
        h = hashlib.sha256()
        for a in (d.qpos, d.qvel, d.qacc_warmstart, d.ctrl, np.array([d.time]), np.array(self.b_p + self.b_v + self.b_w)):
            h.update(np.ascontiguousarray(a, dtype=np.float64).tobytes())
        h.update(json.dumps(self.events, sort_keys=True).encode())
        return h.hexdigest()


def ik(ph: Phys, pos, normal, base_xy, q_init, iters=150, tol=1e-4):
    """Damped least squares over the 7 arm joints (base fixed at base_xy): racket centre at pos, face normal along
    `normal` (rotation about the normal free)."""
    q = np.r_[base_xy, q_init].astype(float)
    n_t = np.asarray(normal, float); n_t = n_t / np.linalg.norm(n_t)
    lo, hi = ph.lo[2:] + 1e-4, ph.hi[2:] - 1e-4
    err = np.inf
    for _ in range(iters):
        p, R = ph.fk(q)
        n = R[:, 0]
        e = np.r_[pos - p, np.cross(n, n_t)]
        err = float(np.linalg.norm(e[:3]) + np.arcsin(min(1.0, np.linalg.norm(e[3:]))))
        if n @ n_t < 0:
            e[3:] = np.cross(n, n_t) + 0.5 * np.cross(n, R[:, 1]); err += np.pi / 2
        if err < tol:
            break
        J = ph.jac(q)
        dq = J.T @ np.linalg.solve(J @ J.T + 1e-3 * np.eye(6), e)
        nd = float(np.max(np.abs(dq)))
        if nd > 0.25:
            dq *= 0.25 / nd
        q[2:] = np.clip(q[2:] + dq, lo, hi)
    return q[2:].copy(), err


# fixed extra IK start poses (offsets from the ready pose Q0_ARM): arm lowered / raised, turned left / right, wrist
# turned. Deterministic: the same list every run, so the plan is a pure function of the state (replay is bit-exact).
IK_SEED_OFFSETS = np.array([
    [0.0, 0.5, 0.0, 0.6, 0.0, -0.4, 0.0],
    [0.0, -0.4, 0.0, -0.3, 0.0, 0.4, 0.0],
    [0.6, 0.2, 0.0, 0.0, 0.0, 0.0, 0.0],
    [-0.6, 0.2, 0.0, 0.0, 0.0, 0.0, 0.0],
    [0.0, 0.3, 0.0, 0.3, 1.2, 0.0, 0.0],
    [0.0, 0.3, 0.0, 0.3, -1.2, 0.0, 0.0],
])
IK_OK = 2e-3                    # an IK solution with a residual below this counts as reaching the pose


def ik_multi(ph: Phys, pos, normal, base_xy, seeds, q_now):
    """Deterministic multi-start IK for both string faces: starts from `seeds` (the caller's seed, the current joint
    targets, the ready pose) and the fixed IK_SEED_OFFSETS poses. Of the solutions that reach the pose
    (residual < IK_OK) it takes the one nearest to the current joint state in joint-speed terms (the least time at the
    joint speed limits, max_j |q_j - q_now_j| / ARM_VEL_j), so the swing does not wander into a far, flipped
    configuration; if none reaches it, the lowest residual. Returns (q, residual, face sign, fallbacks): up
    to 2 more distinct solutions, next-nearest first, for when the nearest one cannot be swung to in time."""
    n_t = np.asarray(normal, float); n_t = n_t / np.linalg.norm(n_t)
    q_now = np.asarray(q_now, float)
    lo, hi = ph.lo[2:] + 1e-3, ph.hi[2:] - 1e-3
    starts = []
    for s in list(seeds) + [Q0_ARM + d for d in IK_SEED_OFFSETS]:
        s = np.clip(np.asarray(s, float), lo, hi)
        if not any(np.array_equal(s, t) for t in starts):
            starts.append(s)
    cands = []
    for i, sd in enumerate(starts):
        for sgn in (1.0, -1.0):                       # the string bed has two faces (the commanded one first)
            q, r = ik(ph, pos, sgn * n_t, base_xy, sd)
            cands.append((float(np.max(np.abs(q - q_now) / ARM_VEL)), r, i, sgn, q))
    good = sorted((c for c in cands if c[1] < IK_OK), key=lambda c: (round(c[0], 9), c[2], -c[3]))
    if not good:
        c = min(cands, key=lambda c: (c[1], c[2]))
        return c[4], c[1], c[3], []
    alts = []                                         # the next-nearest distinct solutions (fallbacks), at most 2
    for c in good[1:]:
        if len(alts) < 2 and all(np.max(np.abs(c[4] - o[4])) > 0.2 for o in [good[0]] + alts):
            alts.append(c)
    return good[0][4], good[0][1], good[0][3], [(c[4], c[1], c[3]) for c in alts]


def swing_score(perr, nerr_deg, verr):
    """How far a rehearsed swing is from the commanded racket state (m-equivalent: 1 cm ~ 1.7 deg ~ 0.5 m/s)."""
    return float(perr) + 0.006 * float(nerr_deg) + 0.02 * float(verr)


DELIVERY_POS_WARN, DELIVERY_ANG_WARN = 0.03, 5.0   # stroke note when the rehearsed delivery is off by more


# ---------------------------------------------------------------------- the match
class Match:
    """The match. Live, real time: rt_advance() / rt_act() / rt_move() / rt_clear() (the event-style run_to_decision() /
    shot() / adjust() are kept for the offline reference tools). Replay: replay(actions)."""

    # decision cameras: (lookat, distance, azimuth, elevation) of MuJoCo free cameras
    CAMS = (([0.0, -2.0, 0.0], 20.0, 90.0, -20.0),         # behind and above the robot's base line, looking down the court
            ([0.0, -0.5, 0.3], 25.0, 0.0, -16.0))         # at the side of the court (x < 0), looking along +x
    VIEW_BACK = (0, 2, 4, 6)                              # snapshots back from the latest: 0, 40, 80, 120 ms
    TILE = (640, 480)
    FOVY = 45.0

    def __init__(self, level: int = 1, lv_override: dict | None = None):
        self.level = int(level)
        self.lv = dict(LEVELS.get(self.level, LEVELS[1]))
        if lv_override:
            self.lv.update(lv_override)
        if os.environ.get("MATCH_SEED"):           # other instances of the same level: serves + opponent + scatter
            self.lv["seed"] = int(os.environ["MATCH_SEED"])
        self.s = Phys()
        self.s.reset(np.r_[HOME, Q0_ARM])
        self._twin = None
        self.score = [0, 0]
        self.hits = 0
        self.limit_reached = False
        self.points: list[dict] = []
        self.legs: list[dict] = []
        self.results: list[dict] = []
        self.shots: list[dict] = []
        self.hist: deque = deque(maxlen=16)
        self.done = False
        self.phase = "swing"
        self.plan, self.plan_j, self._rec = [], 0, {}
        self.base_goal = None
        self.n_our_legs = 0
        self._serve_cache: dict = {}
        self.opp_cache: dict = {}
        self.opp_cache_stats = {"hit": 0, "miss": 0}
        self.review_hist: list = []
        self._start_point(hold_from=0)

    @property
    def k(self) -> int:
        return self.s.k

    # ------------------------------------------------------------------ points / legs
    def precompute_serves(self, n_max: int = 2 * CAP_POINTS - 1) -> None:
        """Wall clock: solve the serves of the match in advance (a pure function of the level, seed and serve index;
        both halves of every point a match without lets can reach), so the step that ends a point does not search for
        the next serve. A point after a let is solved when it starts."""
        for n in range(n_max):
            for half in (0, 1):
                self._serve_solution(serve_index(n, half))

    def _start_point(self, hold_from: int):
        # camera history (display only): no frames of the previous point in the next views; the review shows them
        self.review_hist = list(self.hist)
        self.hist.clear()
        n = len(self.points)
        lv = self.lv
        c = self._serve_solution(serve_index(n, (sum(self.score) // 2) % 2))
        sx, p0, kind, tx, ty, spd, styp, v, w = (c[k] for k in ("sx", "p0", "kind", "tx", "ty", "spd", "styp", "v", "w"))
        self.leg = {"kind": "serve", "serve": {"type": styp, "target_kind": kind, "speed": round(float(spd), 2),
                                               "target": [round(float(tx), 3), round(float(ty), 3)],
                                               "spin": [round(float(x), 1) for x in w], "from_x": sx},
                    "point": n, "hold_from": hold_from, "launch": hold_from + READY_STEPS, "state": "incoming",
                    "p0": p0.tolist(), "v0": [float(x) for x in v]}
        self.legs.append(self.leg)
        self.opp = {"x0": float(sx), "k0": hold_from + READY_STEPS, "tx": 0.0, "speed": lv["recover"]}
        self._opp_plan_k = None
        self._new_leg()
        self.s.b_p = tuple(float(x) for x in p0); self.s.b_v = tuple(float(x) for x in v)
        self.s.b_w = tuple(float(x) for x in w); self.s.b_live = False
        self.base_goal = None

    def _serve_solution(self, n: int) -> dict:
        """The serve of point n: a pure function of the level, the seed and n (cached)."""
        if n in self._serve_cache:
            return self._serve_cache[n]
        lv = self.lv
        rng = np.random.default_rng([lv["seed"], 11, n])
        u = rng.uniform(-1, 1, 5)
        sx = -0.8 if n % 2 == 0 else 0.8                 # deuce side first (the server's right = -x)
        p0 = np.array([sx, COURT_Y + 0.2, 2.75])
        side = -np.sign(sx)                              # our box diagonal to the server: x * side > 0
        kind = ("wide", "body", "T")[int((u[0] + 1) * 1.5) % 3]
        tx = side * {"wide": lv["serve_width"], "body": 2.0, "T": 0.45}[kind]
        tx = float(np.clip(tx + 0.25 * u[1], -COURT_X + 0.3, COURT_X - 0.3))
        if tx * side < 0.3:
            tx = side * 0.3
        ty = -5.3 + 0.5 * u[2]
        spd = lv["serve"][0] + (lv["serve"][1] - lv["serve"][0]) * 0.5 * (u[3] + 1)
        styp = ("flat", "slice", "kick")[int((u[4] + 1) * 1.5) % 3]
        S = lv["serve_spin"]
        v = w = None
        for frac, dsp in ((1.0, 0.0), (0.7, 0.0), (0.7, -3.0), (0.4, -5.0), (0.0, -7.0)):
            # topspin for a ball flying -y is w_x > 0 (w x v points down); sidespin w_z > 0 curves it to +x
            ww = {"flat": (0.3 * S, 0.0, 0.0), "slice": (0.3 * S, 0.0, side * 0.8 * S),
                  "kick": (1.0 * S, 0.0, -side * 0.3 * S)}[styp]
            txx = side * max(0.3, abs(tx) * frac) if frac < 1.0 else tx
            vv = self._solve_serve(p0, (txx, ty), spd + dsp, ww)
            if vv is not None and self._reachable(p0, vv, ww, HOME, serve_sx=sx):
                v, w = vv, ww; tx = txx; spd = spd + dsp
                break
        if v is None:
            w = (0.3 * S, 0.0, 0.0)
            v = self._solve_serve(p0, (side * 1.2, -5.0), 20.0, w)
            if v is None:
                v = np.array([side * 0.1, -20.0, -1.0])
        c = {"sx": sx, "p0": p0, "kind": kind, "tx": tx, "ty": ty, "spd": spd, "styp": styp, "v": v, "w": w}
        self._serve_cache[n] = c
        return c

    def _solve_serve(self, p0, target, speed, w):
        """Launch velocity of the given speed from p0 whose first bounce is at target (Newton on azimuth and
        elevation) and which clears the net by >= 0.05 m."""
        d = np.array([target[0] - p0[0], target[1] - p0[1]])
        az = math.atan2(d[1], d[0]); el = -0.05
        def vel(a, e):
            return np.array([speed * math.cos(e) * math.cos(a), speed * math.cos(e) * math.sin(a), speed * math.sin(e)])
        for _ in range(25):
            L, clr, _ = first_landing(p0, vel(az, el), w)
            if L is None:
                el += 0.02
                continue
            err = np.array(L) - np.asarray(target)
            if np.linalg.norm(err) < 0.02:
                return vel(az, el) if (clr is not None and clr >= 0.05) else None
            J = np.zeros((2, 2))
            for c, (da, de) in enumerate(((1e-3, 0.0), (0.0, 1e-3))):
                L2, _, _ = first_landing(p0, vel(az + da, el + de), w)
                if L2 is None:
                    return None
                J[:, c] = (np.array(L2) - np.array(L)) / 1e-3
            try:
                dx = np.linalg.solve(J, err)
            except np.linalg.LinAlgError:
                return None
            dx = np.clip(dx, -0.05, 0.05)
            az -= dx[0]; el -= dx[1]
        return None

    def _new_leg(self):
        self.s.events.clear()
        self.s.hit_enabled = False
        self._opp_plan_k = None

    def in_play(self) -> bool:
        return self.k >= self.leg["launch"]

    def t_since_launch(self) -> float:
        return round((self.k - self.leg["launch"]) * CONTROL_DT, 6)

    # ------------------------------------------------------------------ the opponent
    def opp_x(self, k=None) -> float:
        k = self.k if k is None else k
        o = self.opp
        dt = max(0.0, (k - o["k0"]) * CONTROL_DT)
        dx = o["tx"] - o["x0"]
        return float(o["x0"] + math.copysign(min(abs(dx), o["speed"] * dt), dx))

    def _opp_plan(self):
        """`reaction_s` after our hit: predict the flight, find where it will hit the ball, start moving there."""
        leg = self.leg
        P, V, W, ev = predict(self.s.b_p, self.s.b_v, self.s.b_w)
        leg["opp_x_react"] = round(self.opp_x(), 3)
        b = [e for e in ev if e[1] == "bounce"]
        if not b or not in_court(b[0][2], b[0][3], +1):
            leg["opp_leave"] = True            # a ball that will land out (or in the net): it lets it go
            return
        i0 = b[0][0]
        j = None
        for i in range(i0 + 1, len(P)):
            if V[i, 2] <= 0 or P[i, 1] >= OPP_HIT_Y:
                j = i; break
            if len(b) > 1 and i >= b[1][0]:
                break
        if j is None:
            j = min(len(P) - 1, i0 + 1)
        r_ = (j + 1) % 10
        if r_:
            j += 10 - r_                                      # align to the end of a control step
        j = min(j, len(P) - 1)
        n_steps = (j + 1) // 10
        lv = self.lv
        ox = self.opp_x()
        hx = float(np.clip(P[j, 0], -OPP_XLIM, OPP_XLIM))
        t = n_steps * CONTROL_DT
        gap = max(0.0, abs(float(P[j, 0]) - ox) - lv["chase"] * t)
        vo = leg["hit"]["speed"] if leg.get("hit") else float(np.linalg.norm(self.s.b_v))
        pressure = max(gap / lv["reach"], (vo - SPEED_FREE) / (lv["max_speed"] - SPEED_FREE))
        leg["opp_hit_k"] = self.k + n_steps
        leg["opp_pressure"] = round(float(pressure), 3)
        leg["opp_gap"] = round(float(gap), 3)
        leg["opp_speed_in"] = round(float(vo), 2)
        self.opp = {"x0": ox, "k0": self.k, "tx": hx, "speed": lv["chase"]}

    def _opp_hit(self):
        leg = self.leg
        p = np.array(self.s.b_p)
        pr = leg["opp_pressure"]
        rec = {"k": self.k, "pos": [round(float(x), 3) for x in p], "opp_x": round(self.opp_x(), 3),
               "pressure": pr, "gap": leg.get("opp_gap"), "speed_in": leg.get("opp_speed_in")}
        leg["opp"] = rec
        if pr > 1.0:
            gap = leg.get("opp_gap", 0.0)
            why = (f"out of reach: the opponent was {gap:.2f} m short of the ball (reach {self.lv['reach']:.2f} m)"
                   if gap > self.lv["reach"] else
                   f"too fast: your shot left the racket at {leg.get('opp_speed_in'):.1f} m/s (it handles up to "
                   f"{self.lv['max_speed']:.0f} m/s)")
            leg["opp_miss"] = why; rec["missed"] = why
            return
        mode = "weak" if pr > PRESSURE_WEAK else ("attack" if pr < PRESSURE_PASSIVE else "normal")
        rec["mode"] = mode
        shot, v, w, target = self._opp_return(p, mode)
        rec.update(shot=shot, target=[round(float(x), 3) for x in target], speed=round(float(np.linalg.norm(v)), 2),
                   spin=[round(float(x), 1) for x in w])
        self._close_our_leg(True, f"good: the opponent played it ({mode} return, {shot})")
        self.hits += 1
        self.s.b_v = tuple(float(x) for x in v); self.s.b_w = tuple(float(x) for x in w)
        leg["state"] = "done"
        self.opp = {"x0": self.opp_x(), "k0": self.k, "tx": 0.0, "speed": self.lv["recover"]}
        self.leg = {"kind": "return", "shot": shot, "point": len(self.points), "launch": self.k, "state": "incoming",
                    "opp_hit_pos": rec["pos"]}
        self.legs.append(self.leg)
        self._new_leg()
        self.s.hit_enabled = True

    def _opp_return(self, p, mode):
        """The opponent's return: the candidate search (pure in p, mode, the level, the seed and the point / leg
        counts; cached, see opp_candidates / opp_spec) and the first candidate our robot can reach from where its
        base stands now."""
        key = (tuple(float(x) for x in p), mode, len(self.points), len(self.legs))
        c = self.opp_cache.pop(key, None)
        if c is None:
            self.opp_cache_stats["miss"] += 1
            c = opp_candidates(p, mode, self.lv, len(self.points), len(self.legs))
        else:
            self.opp_cache_stats["hit"] += 1
        self.opp_cache.clear()
        base = self.s.d.qpos[self.s.qa[:2]].copy()
        for shot, tgt, ww, v, reach in c["cands"]:
            if v is not None and _reach_ok(reach, base):
                return shot, v, ww, tgt
        if not c.get("complete", True):           # a partial speculative list: the rest of the search, in-process
            self.opp_cache_stats["partial"] = self.opp_cache_stats.get("partial", 0) + 1
            c = opp_candidates(p, mode, self.lv, len(self.points), len(self.legs))
            for shot, tgt, ww, v, reach in c["cands"]:
                if v is not None and _reach_ok(reach, base):
                    return shot, v, ww, tgt
        return "lob-safe", c["fallback"], (0.0, 0.0, 0.0), (0.0, -8.0)

    def _solve_shot(self, p0, target, pace, w):
        """Newton on (vx, vz) with vy = -pace so that the first bounce is at target and the ball clears the net by
        >= NET_MARGIN_OPP."""
        v = np.array([(target[0] - p0[0]) * pace / max(1.0, p0[1] - target[1]), -pace, 3.0])
        for _ in range(20):
            L, clr, _ = first_landing(p0, v, w)
            if L is None:
                v[2] += 1.0
                continue
            err = np.array(L) - np.asarray(target)
            if np.linalg.norm(err) < 0.03:
                return v if (clr is not None and clr >= NET_MARGIN_OPP) else None
            J = np.zeros((2, 2))
            for c, idx in enumerate((0, 2)):
                dv = np.zeros(3); dv[idx] = 1e-2
                L2, _, _ = first_landing(p0, v + dv, w)
                if L2 is None:
                    return None
                J[:, c] = (np.array(L2) - np.array(L)) / 1e-2
            try:
                dx = np.linalg.solve(J, err)
            except np.linalg.LinAlgError:
                return None
            dx = np.clip(dx, -2.0, 2.0)
            v[0] -= dx[0]; v[2] -= dx[1]
        return None

    def _reachable(self, p0, v, w, base, serve_sx=None) -> bool:
        """Our robot can meet this flight: it lands in our court (in the service box for a serve), and after that
        bounce, before the second, a point 0.55-1.45 m high whose forehand stance the base can reach in time
        (0.5 s kept for the decision and the swing)."""
        P, V, _, ev = predict(p0, v, w)
        b = [e for e in ev if e[1] == "bounce"]
        if not b or [e for e in ev if e[1] != "cord"][0][1] == "net":
            return False
        x, y = b[0][2], b[0][3]
        if serve_sx is not None:
            if not in_service_box(x, y, serve_sx):
                return False
        elif not in_court(x, y, -1):
            return False
        i0 = b[0][0]; i1 = b[1][0] if len(b) > 1 else len(P)
        for i in range(i0 + 9, i1 - 5, 10):
            q = P[i]
            if not (0.55 <= q[2] <= 1.45 and q[1] <= -3.0):
                continue
            st = stance(q)
            if np.any(np.abs(st - (np.asarray(q[:2]) - STANCE_OFF)) > 1e-6):
                continue                           # stance outside the base's rails
            if base_time(float(np.hypot(*(st - base)))) <= (i + 1) * PHYS_DT - 0.5:
                return True
        return False

    # ------------------------------------------------------------------ stepping (shared by live and replay)
    def step(self, q):
        self.s.step(q)
        leg = self.leg
        if leg["kind"] == "serve" and leg["state"] == "incoming" and self.k == leg["launch"]:
            self.s.b_live = True; self.s.hit_enabled = True
        self._referee()
        if self.k % CAM_EVERY == 0:
            self.hist.append({"k": self.k, "t": self.t_since_launch(), "qpos": self.s.d.qpos.copy(),
                              "b": self.s.b_p, "opp": self.opp_x(), "leg_id": len(self.legs) - 1})

    def _referee(self):
        if self.done:
            return
        leg, s = self.leg, self.s
        ev = s.events
        if leg["state"] == "incoming":
            if not self.in_play():
                return
            hits = [i for i, e in enumerate(ev) if e["kind"] == "hit"]
            own_b = [e for e in ev if e["kind"] == "bounce"]
            if hits:
                pre = ev[:hits[0]]
                nb = sum(1 for e in pre if e["kind"] == "bounce")
                if nb == 0 and leg["kind"] == "serve":     # ITF 24 e: the serve must bounce first; other volleys are legal
                    self._close_our_leg(False, "fault: you returned the serve before it bounced")
                    self._end_point(1, self.results[-1]["summary"]); return
                leg["hit"] = ev[hits[0]]; leg["state"] = "to_opp"; self.hits += 1
                s.events = [e for e in ev[hits[0] + 1:]]
                self._opp_plan_k = self.k + int(round(self.lv["reaction_s"] / CONTROL_DT))
                return
            if leg["kind"] == "serve" and any(e["kind"] in ("net", "cord") for e in ev):
                leg["closed"] = True                      # ITF 22 a: a serve touching the net is a let
                self._end_point(None, "let: the serve touched the net"); return
            if "net" in [e["kind"] for e in ev]:
                self._close_our_leg(True, "the opponent's shot hit the net"); self._end_point(0, "the opponent hit the net"); return
            if len(own_b) >= 2:
                self._close_our_leg(False, "missed: the ball bounced twice on your side")
                self._end_point(1, self.results[-1]["summary"]); return
            if len(own_b) == 1 and leg["kind"] == "serve" and not in_service_box(own_b[0]["x"], own_b[0]["y"],
                                                                                 leg["serve"]["from_x"]):
                leg["closed"] = True                      # a machine-like serve: replayed (as in the duel)
                self._end_point(None, "let: the serve missed your service box"); return
            if len(own_b) == 1 and not in_court(own_b[0]["x"], own_b[0]["y"], -1):
                self._close_our_leg(True, "the opponent's shot landed out")
                self._end_point(0, self.results[-1]["summary"]); return
            if self.k - leg["launch"] >= LEG_STEPS:
                self._close_our_leg(False, "missed"); self._end_point(1, "missed"); return
            return
        if leg["state"] == "to_opp":
            kinds = [e["kind"] for e in ev]
            if "net" in kinds:
                e = next(x for x in ev if x["kind"] == "net")
                self._close_our_leg(False, f"fault: your shot hit the net (x={e['x']:.2f}, height {e['z']:.2f} m)")
                self._end_point(1, self.results[-1]["summary"]); return
            bb = [e for e in ev if e["kind"] == "bounce"]
            if bb and "bounce_checked" not in leg:
                e = bb[0]
                leg["bounce_checked"] = True
                if e["y"] < 0:
                    self._close_our_leg(False, f"fault: your shot came down on your own side (x={e['x']:.2f}, y={e['y']:.2f})")
                    self._end_point(1, self.results[-1]["summary"]); return
                if not in_court(e["x"], e["y"], +1):
                    self._close_our_leg(False, f"fault: your shot landed out at x={e['x']:.2f}, y={e['y']:.2f}")
                    self._end_point(1, self.results[-1]["summary"]); return
                leg["landing"] = [e["x"], e["y"]]
            if self._opp_plan_k is not None and self.k == self._opp_plan_k:
                self._opp_plan()
            if leg.get("opp_hit_k") == self.k and "opp_miss" not in leg and not leg.get("opp_leave"):
                self._opp_hit()
                return
            if "opp_miss" in leg or leg.get("opp_leave"):
                if len(bb) >= 2 or self.k - leg.get("opp_hit_k", self.k) >= 40 or not s.b_live:
                    L = leg.get("landing") or [0, 0]
                    why = leg.get("opp_miss") or "the opponent could not reach it"
                    self._close_our_leg(True, f"winner: landed in at x={L[0]:.2f}, y={L[1]:.2f} ({why})")
                    self._end_point(0, self.results[-1]["summary"]); return
            if self.k - leg["launch"] >= 3 * LEG_STEPS:
                self._close_our_leg(False, "?"); self._end_point(1, "timeout")

    def _close_our_leg(self, ok, summary):
        leg = self.leg
        if leg.get("closed"):
            return
        leg["closed"] = True
        h = leg.get("hit")
        res = {"leg": self.n_our_legs, "point": len(self.points), "kind": leg["kind"], "returned": bool(ok),
               "summary": summary, "hit": int(h is not None), "speed_out": None if h is None else h["speed"],
               "offcentre": None if h is None else h["offcentre"], "landing": leg.get("landing"), "step": self.k}
        self.results.append(res)
        self.n_our_legs += 1

    def _end_point(self, winner, how: str):
        """winner: 0 (you), 1 (the opponent) or None (a let: the point is replayed, no score)."""
        if winner is not None:
            self.score[winner] += 1
        self.points.append({"point": len(self.points), "winner": {0: "you", 1: "opponent", None: "let"}[winner],
                            "how": how, "score": list(self.score), "step": self.k})
        self.leg["state"] = "done"
        if match_won(*self.score):
            self.done = True
            return
        if self.hits >= MAX_HITS or len(self.points) >= MAX_POINTS:
            self.done = True
            self.limit_reached = True
            return
        self._start_point(hold_from=self.k)

    def winner(self):
        """0 (you) or 1 (the opponent) once the match is over, else None. The agent always receives, so the last resort
        (no point won at all) is the opponent, the player who did not receive first (as in the duel)."""
        if not self.done:
            return None
        return match_winner(self.score[0], self.score[1],
                            [{"you": 0, "opponent": 1}.get(p["winner"]) for p in self.points], 1)

    def replay(self, actions) -> None:
        for q in actions:
            self.step(q)

    # ------------------------------------------------------------------ live control
    def _target_vel(self):
        a = self.s._actions
        return (a[-1] - a[-2]) / CONTROL_DT if len(a) >= 2 else np.zeros(9)

    def _ready_target(self):
        """Service-driven recovery: the arm back to the ready pose (60 % of its speed limits), the base to the goal
        of the last `move` (else home)."""
        tgt = self.s.target
        lim = ARM_VEL * CONTROL_DT * 0.6
        arm = tgt[2:] + np.clip(Q0_ARM - tgt[2:], -lim, lim)
        goal = HOME if self.base_goal is None else self.base_goal
        b, _ = base_goto(tgt[:2], self._target_vel()[:2], goal)
        return np.r_[b, arm]

    def _arm_target(self):
        if self.plan_j < len(self.plan):
            q = self.plan[self.plan_j]; self.plan_j += 1
            return q
        return self._ready_target()

    def _adjust_due(self):
        ev = self.s.events
        b = [e for e in ev if e["kind"] == "bounce"]
        return bool(b) and self.k - b[0]["k"] >= ADJUST_FRAMES * CAM_EVERY

    def decision_due(self) -> bool:
        leg = self.leg
        if self.done or leg["state"] != "incoming" or not self.in_play():
            return False
        if any(e["kind"] == "hit" for e in self.s.events):
            return False
        if self.k % CAM_EVERY:
            return False                     # decision points coincide with a camera snapshot
        if self.phase == "swing":
            return self.k - leg["launch"] >= SWING_AFTER
        return self._adjust_due()

    def run_to_decision(self) -> None:
        self.phase = "swing"
        while not self.done:
            if self.decision_due():
                return
            self.step(self._arm_target())

    def shot(self, decision: dict, delay_steps: int) -> dict:
        """Decision 1 (swing / move / skip): think delay (the robot keeps doing what it did), then the stroke
        controller plans and starts the swing (or the base starts moving); runs to the adjust point."""
        leg_i = self.n_our_legs
        rec = {"leg": leg_i, "decision": decision, "delay_steps": int(delay_steps), "k_decision": self.k}
        for _ in range(delay_steps):
            if self.leg["state"] != "incoming" or self.done:
                break
            self.step(self._arm_target())
        rec["k_exec"] = self.k
        typ = decision.get("type")
        if typ == "swing" and self.leg["state"] == "incoming" and not self.done:
            self._ik_seed = None
            self.plan, info = self.plan_racket(float(decision["t"]), decision["pos"], decision["normal"],
                                               decision["vel"], decision.get("base"))
            self.plan_j = 0
            rec.update(info)
        elif typ == "move":
            self.base_goal = np.clip(np.asarray(decision["base"], float), BASE_LO, BASE_HI)
            self.plan, self.plan_j = [], 0
            rec["base_goal"] = [round(float(x), 3) for x in self.base_goal]
        self._rec = rec
        if typ in ("swing", "move"):
            self.phase = "adjust"
            while not self.done and self.n_our_legs == leg_i:
                if self.decision_due():
                    return {"phase": "adjust", **{k: rec[k] for k in rec if k != "decision"}}
                self.step(self._arm_target())
        return self._after_leg(rec, leg_i)

    def adjust(self, decision: dict, delay_steps: int) -> dict:
        rec, leg_i = self._rec, self.n_our_legs
        rec["adjust"] = decision
        rec["adjust_delay_steps"] = int(delay_steps)
        for _ in range(delay_steps):
            if self.n_our_legs != leg_i or self.done:
                break
            self.step(self._arm_target())
        if decision.get("type") == "adjust" and self.n_our_legs == leg_i and not self.done \
                and self.leg["state"] == "incoming":
            self._ik_seed = rec.get("_q_hit")
            plan, info = self.plan_racket(float(decision["t"]), decision["pos"], decision["normal"], decision["vel"],
                                          decision.get("base"))
            q_hit = info.pop("_q_hit", None)
            rec["adjust_info"] = info
            if plan:
                rec["_q_hit"] = q_hit
                self.plan, self.plan_j = plan, 0
        return self._after_leg(rec, leg_i)

    def _after_leg(self, rec, leg_i) -> dict:
        n0 = len(self.points)
        while not self.done and self.n_our_legs == leg_i:
            self.step(self._arm_target())
            if self.leg.get("state") == "to_opp" and self.plan_j >= len(self.plan):
                self.base_goal = None
        self.base_goal = None
        rec.pop("_q_hit", None)
        self.shots.append(rec)
        res = dict(self.results[leg_i]) if leg_i < len(self.results) else {"summary": "match over"}
        self.run_to_decision()
        res["points_finished"] = self.points[n0:]
        return res

    # ------------------------------------------------------------------ real-time protocol (server.py: observe / act / move / wait)
    def rt_advance(self, n_steps: int):
        """Run up to n_steps control steps with the current command (the stroke under way, else the recovery to the
        ready pose and the base's rest position); stops early at the end of a point. Returns (steps run, points
        finished, our shots judged)."""
        n0, r0, n = len(self.points), len(self.results), 0
        while n < n_steps and not self.done and len(self.points) == n0:
            self.step(self._arm_target()); n += 1
        if len(self.points) > n0:                  # a new point: no command carries over, the base goes home
            self.plan, self.plan_j = [], 0
            self._last_act = None; self._q_hit_active = None
        return n, self.points[n0:], self.results[r0:]

    def rt_act(self, T, pos, nrm, vel, base=None) -> dict:
        """A new command: the racket state at contact T s from now (optionally the base position at contact),
        planned from the robot's current state; replaces any stroke under way."""
        t_hit = (self.k - self.leg["launch"]) * CONTROL_DT + float(T)
        active = self.plan_j < len(self.plan)
        self._ik_seed = getattr(self, "_q_hit_active", None) if active else None
        plan, info = self.plan_racket(t_hit, pos, nrm, vel, base)
        q_hit = info.pop("_q_hit", None)
        info["T_from_now"] = round(float(T), 4)
        if plan:
            self.plan, self.plan_j = plan, 0
            self._q_hit_active = q_hit
        self.shots.append({"k": self.k, "leg": self.n_our_legs, "type": "act", **info})
        self._last_act = info if plan else getattr(self, "_last_act", None)
        return info

    def rt_install(self, res: dict) -> dict:
        """Wall clock: install a stroke planned outside the sim lock (PlanCtx.plan_act) at its effect step. Exactly what
        rt_act does after its planning: the plan replaces the stroke under way (if the planner produced one)."""
        if res["k_effect"] != self.k or not np.array_equal(res["target_at_effect"], self.s.target):
            raise RuntimeError(f"plan for step {res['k_effect']} installed at step {self.k} (or its predicted joint "
                               "targets differ from the live ones)")
        info = res["info"]
        if res["plan"]:
            self.plan, self.plan_j = list(res["plan"]), 0
            self._q_hit_active = res["q_hit"]
        self.shots.append({"k": self.k, "leg": self.n_our_legs, "type": "act", **info})
        self._last_act = info if res["plan"] else getattr(self, "_last_act", None)
        return info

    def export_state(self) -> dict:
        """The full match state (privileged: the reference player only, RCB_PLAYER_MODE=oracle)."""
        s, d = self.s, self.s.d
        return copy.deepcopy({
            "level": self.level, "lv": self.lv, "k": s.k, "qpos": d.qpos, "qvel": d.qvel,
            "qacc_warmstart": d.qacc_warmstart, "ctrl": d.ctrl, "time": float(d.time), "qfrc_bias": d.qfrc_bias,
            "target": s.target, "tail": s._actions[-2:], "ball": (s.b_p, s.b_v, s.b_w, s.b_live, s.hit_enabled), "events": s.events,
            "prev": s._prev, "score": self.score, "points": self.points, "legs": self.legs, "opp": self.opp,
            "opp_plan_k": self._opp_plan_k, "plan": self.plan[self.plan_j:], "base_goal": self.base_goal,
            "n_our_legs": self.n_our_legs, "results": self.results, "q_hit_active": getattr(self, "_q_hit_active", None),
            "last_act": getattr(self, "_last_act", None), "done": self.done})

    def import_state(self, st: dict) -> None:
        """Make this Match a copy of an exported state (the reference player's private twin of the world)."""
        st = copy.deepcopy(st)
        s, d = self.s, self.s.d
        mj.mj_resetData(s.m, d)
        d.qpos[:] = st["qpos"]; d.qvel[:] = st["qvel"]; d.qacc_warmstart[:] = st["qacc_warmstart"]
        d.ctrl[:] = st["ctrl"]; d.time = st["time"]
        mj.mj_forward(s.m, d)
        d.qfrc_bias[:] = st["qfrc_bias"]   # the live step's PD bias term is the previous substep's (bit-exact twin)
        s.target = np.asarray(st["target"], float).copy(); s.k = int(st["k"]); s._actions = list(st["tail"])
        s.b_p, s.b_v, s.b_w, s.b_live, s.hit_enabled = st["ball"]
        s.events = st["events"]; s._prev = st["prev"]
        self.level, self.lv = st["level"], st["lv"]
        self.score, self.points, self.legs = st["score"], st["points"], st["legs"]
        self.leg = self.legs[-1]
        self.opp, self._opp_plan_k = st["opp"], st["opp_plan_k"]
        self.plan, self.plan_j, self.base_goal = st["plan"], 0, st["base_goal"]
        self.n_our_legs, self.results, self.done = st["n_our_legs"], st["results"], st["done"]
        self._q_hit_active, self._last_act = st["q_hit_active"], st["last_act"]

    def rt_move(self, bx, by) -> list:
        """The base's rest position: where the base goes whenever no stroke is under way (reset to home after each
        point). A stroke under way keeps its own base plan."""
        self.base_goal = np.clip(np.array([bx, by], float), BASE_LO, BASE_HI)
        g = [round(float(x), 3) for x in self.base_goal]
        self.shots.append({"k": self.k, "leg": self.n_our_legs, "type": "move", "base_goal": g})
        return g

    def rt_clear(self):
        self.plan, self.plan_j = [], 0
        self._last_act = None; self._q_hit_active = None

    # ------------------------------------------------------------------ stroke controller
    def _twin_phys(self) -> Phys:
        if self._twin is None:
            self._twin = Phys()
            self._twin.reset(self.s.target)
        return self._twin

    def _base_plan(self, goal, n):
        b = self.s.target[:2].copy(); v = self._target_vel()[:2].copy()
        out, arrived = [], None
        for i in range(n):
            b, v = base_goto(b, v, goal)
            out.append(b.copy())
            if arrived is None and np.all(b == goal) and not v.any():
                arrived = i
        return out, arrived

    RACKET_SCATTER = dict(pos=0.005, ang_deg=0.5, speed=0.02)   # execution scatter of the racket state at contact

    def plan_racket(self, t_hit, p_c, nrm, v_p, base=None, scatter=True):
        """Racket-level decision: the player gives the racket state at contact (time t_hit s after the ball was
        played, head centre p_c, string-face normal nrm, head velocity v_p) and optionally the base position. The
        controller only makes the robot deliver it: the base to `base` (default: the forehand stance for p_c), or
        as far as it gets 0.05 s before the contact, IK, a speed-weighted Jacobian inverse, a joint-speed-limited
        cubic swing and robot-only rehearsals that correct the PD lag. It uses no ball state and does not aim. The
        delivered state scatters (seeded, RACKET_SCATTER)."""
        p_c = np.asarray(p_c, float); nrm = np.asarray(nrm, float); nrm = nrm / np.linalg.norm(nrm)
        v_p = np.asarray(v_p, float)
        info = {"t_hit": t_hit, "racket_pos": p_c.round(4).tolist(), "racket_normal": nrm.round(4).tolist(),
                "racket_vel": v_p.round(3).tolist()}
        k_hit = self.leg["launch"] + int(round(t_hit / CONTROL_DT))
        n_avail = k_hit - self.k
        info["n_swing_steps_available"] = int(n_avail)
        info["k_hit"] = None
        if n_avail < 3:
            info["stroke"] = "too late: the contact time has already passed"
            return [], info
        info["k_hit"] = int(k_hit)
        if scatter:
            rng = np.random.default_rng([self.lv["seed"], 13, self.n_our_legs])
            sc = self.RACKET_SCATTER
            p_c = p_c + rng.normal(0.0, sc["pos"], 3)
            axis = np.cross(nrm, rng.normal(0.0, 1.0, 3)); axis /= np.linalg.norm(axis)
            ang = np.radians(rng.normal(0.0, sc["ang_deg"]))
            nrm = nrm * np.cos(ang) + np.cross(axis, nrm) * np.sin(ang); nrm /= np.linalg.norm(nrm)
            v_p = v_p * (1.0 + rng.normal(0.0, sc["speed"]))
        st = stance(p_c) if base is None else np.clip(np.asarray(base, float), BASE_LO, BASE_HI)
        goal = st
        b0 = self.s.target[:2].copy()
        _, arr = self._base_plan(goal, n_avail)
        if arr is None or arr > n_avail - 5:
            lo_, hi_ = 0.0, 1.0
            for _ in range(10):
                mid = 0.5 * (lo_ + hi_)
                _, a2 = self._base_plan(b0 + mid * (st - b0), n_avail)
                if a2 is not None and a2 <= n_avail - 5:
                    lo_ = mid
                else:
                    hi_ = mid
            goal = b0 + lo_ * (st - b0)
            info["base"] = f"could not reach the base position in time: {float(np.linalg.norm(st - goal)):.2f} m short"
        else:
            info["base"] = "ok"
        info["base_goal"] = [round(float(x), 3) for x in goal]
        base_tg, _ = self._base_plan(goal, n_avail + 40)
        ph = self.s
        seed = getattr(self, "_ik_seed", None)
        q_now = ph.target[2:].copy()                # the swing starts from the current joint targets
        seeds = ([] if seed is None else [seed]) + [q_now, Q0_ARM]
        q_h, res, sgn, alts = ik_multi(ph, p_c, nrm, goal, seeds, q_now)   # deterministic multi-start, nearest first
        Winv = np.diag(ARM_VEL ** 2)
        tried = None
        for q_h, res, sgn in [(q_h, res, sgn)] + alts:
            Jp = ph.jac(np.r_[goal, q_h])[:3]
            qd_h = Winv @ Jp.T @ np.linalg.solve(Jp @ Winv @ Jp.T + 1e-9 * np.eye(3), v_p)
            ratio = float(np.max(np.abs(qd_h) / ARM_VEL))
            c = dict(nrm=sgn * nrm, v_p=v_p, q_h=q_h, qd_h=qd_h, ik=res, ratio=ratio, p_hit=p_c)
            tg, sinfo = self._swing(c, goal, base_tg, n_avail)
            sc = swing_score(sinfo["blade_error_m"], sinfo["normal_error_deg"],
                             np.linalg.norm(self._swing_last[2] - v_p / sinfo["speed_scale"]))
            if tried is None or sc < tried[0]:
                tried = (sc, tg, sinfo, self._swing_last, q_h, res)
            if sinfo["blade_error_m"] <= DELIVERY_POS_WARN and sinfo["normal_error_deg"] <= DELIVERY_ANG_WARN:
                break                                 # delivered: the nearest solution that works
        _, tg, sinfo, self._swing_last, q_h, res = tried
        info.update(sinfo)
        p, n_act, v_act = self._swing_last
        info["racket_vel_delivered"] = [round(float(x), 3) for x in v_act]
        info["_q_hit"] = q_h
        notes = []
        if res > IK_OK: notes.append(f"pose not reachable exactly (IK residual {res:.3f})")
        if sinfo["blade_error_m"] > DELIVERY_POS_WARN or sinfo["normal_error_deg"] > DELIVERY_ANG_WARN:
            notes.append(f"pose not delivered: the rehearsed racket head is {100 * sinfo['blade_error_m']:.1f} cm off "
                         f"and the face {sinfo['normal_error_deg']:.1f} deg off the command at the contact time")
        if sinfo["speed_scale"] > 1.005: notes.append(f"head speed limited by the joint speed limits (x{1 / sinfo['speed_scale']:.2f})")
        if sinfo["n_swing_steps"] < 20: notes.append("short swing (little time left)")
        if info["base"] != "ok": notes.append(info["base"])
        info["stroke"] = "; ".join(notes) or "ok"
        return tg, info

    def _swing(self, c, goal, base_tg, n_avail):
        """Arm swing (cubic to the hit configuration, follow-through) + base plan; 5 robot-only twin rehearsals
        correct the hit configuration/velocity for the PD lag, and the best of them (swing_score) is kept."""
        ph = self.s
        scale = max(1.0, c["ratio"] / 0.9)
        q_h, qd_h = c["q_h"].copy(), c["qd_h"] / scale
        v_p = c["v_p"] / scale
        q_s = ph.target[2:].copy(); v_s = self._target_vel()[2:]
        n_sw = int(n_avail)
        if np.max(np.abs(v_s)) < 1e-6 and n_avail >= 25:
            # the shortest swing (0.25-0.9 s) within the joint speed limits, else the one closest to them
            best = None
            for n in range(25, int(min(n_avail, 90)) + 1):
                sw = hermite(q_s, np.zeros(7), q_h, qd_h, n * CONTROL_DT, n)
                r_ = float(np.max(np.abs(np.diff(np.vstack([q_s, sw]), axis=0)) / (ARM_VEL * CONTROL_DT)))
                if r_ <= 0.97:
                    best = (r_, n)
                    break
                if best is None or r_ < best[0]:
                    best = (r_, n)
            n_sw = best[1]
        n_sw = int(min(n_sw, n_avail))
        Winv = np.diag(ARM_VEL ** 2)
        q_goal, qd_goal = q_h.copy(), qd_h.copy()
        best = None
        for it in range(5):
            tg = self._swing_targets(q_goal, qd_goal, n_avail, n_sw, base_tg)
            p, n_act, v_act = self._simulate_arm(tg, n_avail, pre=n_avail - n_sw)
            perr = float(np.linalg.norm(p - c["p_hit"]))
            nerr = float(np.degrees(np.arccos(np.clip(float(n_act @ c["nrm"]), -1.0, 1.0))))
            sc = swing_score(perr, nerr, np.linalg.norm(v_act - v_p))
            if best is None or sc < best[0]:          # keep the best of the correction passes, not the last one
                best = (sc, tg, (p, n_act, v_act), perr, nerr)
            if it == 4:
                break
            J = ph.jac(np.r_[goal, q_goal])
            e = np.r_[c["p_hit"] - p, np.cross(n_act, c["nrm"])]
            q_goal = np.clip(q_goal + J.T @ np.linalg.solve(J @ J.T + 1e-4 * np.eye(6), e),
                             ph.lo[2:] + 1e-4, ph.hi[2:] - 1e-4)
            Jp = J[:3]
            qd_goal = qd_goal + Winv @ Jp.T @ np.linalg.solve(Jp @ Winv @ Jp.T + 1e-9 * np.eye(3), v_p - v_act) * 0.7
            qd_goal = qd_goal / max(1.0, float(np.max(np.abs(qd_goal) / ARM_VEL)))
        _, tg, self._swing_last, perr, nerr = best
        info = {"ik_residual": round(float(c["ik"]), 5), "speed_scale": round(scale, 3), "n_swing_steps": n_sw,
                "blade_error_m": round(perr, 4), "normal_error_deg": round(nerr, 2)}
        return tg, info

    def _swing_targets(self, q_h, qd_h, n_avail, n_sw, base_tg):
        ph = self.s
        q_s = ph.target[2:].copy(); v_s = self._target_vel()[2:]
        pre = np.tile(q_s, (n_avail - n_sw, 1))
        swing = hermite(q_s, v_s if n_sw == n_avail else np.zeros(7), q_h, qd_h, n_sw * CONTROL_DT, n_sw)
        n_f = 25
        follow = hermite(q_h, qd_h, q_h + qd_h * 0.5 * n_f * CONTROL_DT, np.zeros(7), n_f * CONTROL_DT, n_f)
        out, prev = [], ph.target.copy()
        lim = VEL_LIMIT * CONTROL_DT * 0.999
        for i, q in enumerate(np.vstack([pre, swing, follow])):
            q9 = np.r_[base_tg[min(i, len(base_tg) - 1)], q]
            q9 = np.clip(q9, ph.lo + 1e-4, ph.hi - 1e-4)
            q9 = prev + np.clip(q9 - prev, -lim, lim)
            out.append(q9); prev = q9
        return out

    def _simulate_arm(self, targets, n, pre=0):
        """Robot-only twin rollout from the live robot state: racket (pos, normal, velocity) after n steps. The
        first `pre` steps (the hold before the swing, identical in every correction pass) are rolled out once per
        live state and target prefix; later passes restore a full copy of that MjData (bit-identical to rolling out again)."""
        tw = self._twin_phys()
        pre = int(max(0, min(pre, n)))
        key = None
        if pre > 0:
            s, d = self.s, self.s.d
            key = (s.k, s.target.tobytes(), d.qpos.tobytes(), d.qvel.tobytes(), d.qacc_warmstart.tobytes(),
                   d.ctrl.tobytes(), float(d.time), np.asarray(targets[:pre], float).tobytes())
        c = getattr(self, "_pre_cache", None)
        if key is not None and c is not None and c[0] == key:
            tw.d = copy.copy(c[1])                    # MjData copy: mj_copyData of every field
            tw.target, tw.k, tw.steps_total = c[2].copy(), c[3], c[4]
            tw.b_live = False; tw.hit_enabled = False; tw.events = []; tw._prev = c[5]
        else:
            tw.copy_from(self.s)
            tw.b_live = False; tw.hit_enabled = False
            for j in range(pre):
                tw.step(targets[j])
            if key is not None:
                self._pre_cache = (key, copy.copy(tw.d), tw.target.copy(), tw.k, tw.steps_total, tw._prev)
        for j in range(pre, n):
            tw.step(targets[j])
        mj.mj_forward(tw.m, tw.d)
        return tw.racket_state()

    def _rehearse(self, targets):
        """Full twin rehearsal (robot and the real ball): (hit event, first bounce after it, net clearance) or
        (None, None, None) if the racket never meets the ball. Privileged: used only by the offline reference."""
        tw = self._twin_phys()
        tw.copy_from(self.s)
        for j in range(len(targets) + 40):
            tw.step(targets[j] if j < len(targets) else targets[-1])
            h = [e for e in tw.events if e["kind"] == "hit"]
            if h:
                L, clr, _ = first_landing(tw.b_p, tw.b_v, tw.b_w)
                return h[0], L, clr
            if not tw.b_live:
                break
        return None, None, None

    # ------------------------------------------------------------------ views
    @staticmethod
    def cam_pose(lookat, dist, az, el):
        a, e = math.radians(az), math.radians(el)
        fwd = np.array([math.cos(e) * math.cos(a), math.cos(e) * math.sin(a), math.sin(e)])
        up = np.array([-math.sin(e) * math.cos(a), -math.sin(e) * math.sin(a), math.cos(e)])
        pos = np.asarray(lookat, float) - dist * fwd
        return pos, fwd, up

    @classmethod
    def cam_info(cls):
        out = []
        for name, c in zip(("behind", "side"), cls.CAMS):
            pos, fwd, up = cls.cam_pose(*c)
            out.append({"name": name, "position": [round(float(x), 4) for x in pos],
                        "forward": [round(float(x), 4) for x in fwd], "up": [round(float(x), 4) for x in up]})
        return out

    def _set_render_state(self, rd, sn):
        rd.qpos[:] = sn["qpos"]
        rd.mocap_pos[0] = sn["b"]
        mj.mj_kinematics(self.s.m, rd)

    @staticmethod
    def _extra_geoms(scn, opp_x, b=None):
        def add(typ, size, pos, rgba, mat=np.eye(3)):
            if scn.ngeom >= scn.maxgeom:
                return
            mj.mjv_initGeom(scn.geoms[scn.ngeom], typ, np.asarray(size, float), np.asarray(pos, float),
                            np.asarray(mat, float).ravel(), np.asarray(rgba, np.float32))
            scn.ngeom += 1
        ox, oy = float(opp_x), OPP_Y
        add(mj.mjtGeom.mjGEOM_CAPSULE, [0.18, 0.55, 0], [ox, oy, 0.75], [0.35, 0.35, 0.42, 1])
        add(mj.mjtGeom.mjGEOM_SPHERE, [0.13, 0, 0], [ox, oy, 1.55], [0.85, 0.7, 0.6, 1])
        rp = np.array([ox - 0.6, oy - 0.2, 1.0])
        if b is not None:
            d = np.array(b) - np.array([ox, oy, 1.0])
            if np.linalg.norm(d) < 2.0 and b[1] > 0:
                rp = np.array([ox, oy, 1.0]) + d / max(1e-6, np.linalg.norm(d)) * min(1.3, np.linalg.norm(d))
        add(mj.mjtGeom.mjGEOM_ELLIPSOID, [0.14, 0.02, 0.17], rp, [0.9, 0.1, 0.1, 1])

    def _renderer(self, w, h):
        key = (w, h)
        if getattr(self, "_rkey", None) != key:
            self._r = mj.Renderer(self.s.m, height=h, width=w)
            self._rd = mj.MjData(self.s.m)
            self._rkey = key
            self._cams = []
            for lookat, dist, az, el in self.CAMS:
                c = mj.MjvCamera(); c.lookat[:] = lookat; c.distance = dist; c.azimuth = az; c.elevation = el
                self._cams.append(c)
        return self._r, self._rd

    def render_views(self) -> bytes:
        """PNG: 2 rows (behind camera, side camera) x 4 columns (snapshots 40 ms apart, oldest left), each tile
        stamped with its time since the ball was played."""
        import imageio.v2 as imageio
        from PIL import Image, ImageDraw
        w, h = self.TILE
        r, rd = self._renderer(w, h)
        hist = list(self.hist)
        snaps = [hist[max(0, len(hist) - 1 - b)] for b in reversed(self.VIEW_BACK)]
        rows = []
        for c in self._cams:
            tiles = []
            for sn in snaps:
                self._set_render_state(rd, sn)
                r.update_scene(rd, camera=c)
                self._extra_geoms(r.scene, sn["opp"], sn["b"])
                im = Image.fromarray(r.render())
                ImageDraw.Draw(im).text((6, 4), f"t={sn['t']:.2f}s", fill=(255, 255, 255))
                tiles.append(np.asarray(im))
            rows.append(np.concatenate(tiles, axis=1))
        buf = io.BytesIO()
        imageio.imwrite(buf, np.concatenate(rows, axis=0), format="png")
        return buf.getvalue()

    def view_times(self):
        hist = list(self.hist)
        return [hist[max(0, len(hist) - 1 - b)]["t"] for b in reversed(self.VIEW_BACK)]

    def decision_observation(self) -> dict:
        ph = self.s
        leg = self.leg
        heard = [{"event": "the opponent served" if leg["kind"] == "serve" else "the opponent hit the ball", "t": 0.0}]
        for e in ph.events:
            if e["kind"] == "bounce":
                heard.append({"event": "bounce on your side" if e["side"] == "own" else "bounce on the opponent's side",
                              "t": round((e["k"] - leg["launch"]) * CONTROL_DT, 2)})
        c, n, _ = ph.racket_state()
        return {"score": {"you": self.score[0], "opponent": self.score[1]}, "point": len(self.points) + 1,
                "ball": "serve" if leg["kind"] == "serve" else "opponent's return",
                "t_since_played": self.t_since_launch(), "heard": heard, "view_times": self.view_times(),
                "robot_base_xy": [round(float(x), 3) for x in ph.d.qpos[ph.qa[:2]]],
                "q_arm": [round(float(x), 4) for x in ph.d.qpos[ph.qa[2:]]],
                "racket_pos": [round(float(x), 3) for x in c], "racket_normal": [round(float(x), 3) for x in n]}


# ---------------------------------------------------------------------- the opponent's return search (pure, cacheable)
def _reach_points(p0, v, w):
    """The base-independent part of Match._reachable (no serve): None if the flight is not playable at all, else
    the list of (stance, latest base travel time) of the candidate contact points, in the same order."""
    P, V, _, ev = predict(p0, v, w)
    b = [e for e in ev if e[1] == "bounce"]
    if not b or [e for e in ev if e[1] != "cord"][0][1] == "net":
        return None
    x, y = b[0][2], b[0][3]
    if not in_court(x, y, -1):
        return None
    i0 = b[0][0]; i1 = b[1][0] if len(b) > 1 else len(P)
    out = []
    for i in range(i0 + 9, i1 - 5, 10):
        q = P[i]
        if not (0.55 <= q[2] <= 1.45 and q[1] <= -3.0):
            continue
        st = stance(q)
        if np.any(np.abs(st - (np.asarray(q[:2]) - STANCE_OFF)) > 1e-6):
            continue
        out.append((st, (i + 1) * PHYS_DT - 0.5))
    return out


def _reach_ok(reach, base) -> bool:
    return bool(reach) and any(base_time(float(np.hypot(*(st - base)))) <= thr for st, thr in reach)


def opp_candidates(p, mode, lv, n_points, n_legs, base_hints=None):
    """The candidates of the opponent's return search, in the order Match._opp_return tries them (the same targets,
    paces, spins and solver as the lock-step engine), with the base-independent reachability data. With base_hints
    (the speculative precompute) it stops after the first candidate reachable from every hint plus one more
    ("complete": False); the selection then recomputes the full list if it needs a later one (same values)."""
    rng = np.random.default_rng([lv["seed"], n_points, n_legs])
    u = rng.uniform(-1, 1, 5)
    side = 1.0 if u[0] >= 0 else -1.0
    W = lv["width"]
    if mode == "weak":
        tx, ty, pace, w, shot = 0.6 * u[0], -8.5 + 0.5 * u[1], 13.0, (0.0, 0.0, 0.0), "weak"
    else:
        topspin = u[3] > -0.4                                      # 70 % topspin, 30 % slice
        mag = lv["spin"] * (1.0 if mode == "attack" else 0.6 + 0.4 * abs(u[2]))
        tx = side * W * (1.0 if mode == "attack" else abs(u[0]) ** 0.5)
        ty = -9.6 + 0.9 * u[1] if mode != "attack" else -10.2 + 0.4 * u[1]
        pace = lv["pace"] + (3.0 if mode == "attack" else 0.0)
        # a ball flying -y: topspin w_x > 0, slice (backspin) w_x < 0
        w = (mag, 0.0, 0.0) if topspin else (-0.6 * mag, 0.0, 0.0)
        shot = ("attacking " if mode == "attack" else "") + ("topspin" if topspin else "slice")
        if not topspin:
            pace -= 2.0
    cands = []
    extra = None
    for frac, dp, ws in ((1.0, 0.0, 1.0), (1.0, -2.0, 1.0), (0.6, 0.0, 1.0), (0.6, -3.0, 0.5), (0.3, -4.0, 0.5),
                         (0.0, -5.0, 0.0), (0.0, -7.0, 0.0)):
        ww = tuple(ws * x for x in w)
        for dty in (0.0, 1.0):
            tgt = (tx * frac, ty + dty)
            v = Match._solve_shot(None, p, tgt, max(10.0, pace + dp), ww)
            cands.append((shot, tgt, ww, v, None if v is None else _reach_points(p, v, ww)))
            if base_hints is not None:
                if extra is not None:
                    return {"cands": cands, "fallback": None, "complete": False}
                if v is not None and all(_reach_ok(cands[-1][4], np.asarray(b, float)) for b in base_hints):
                    extra = len(cands)
    ww = (0.0, 0.0, 0.0)
    for ty2 in (-8.0, -7.0, -9.0):
        v = Match._solve_shot(None, p, (0.0, ty2), 12.0, ww)
        cands.append(("lob-safe", (0.0, ty2), ww, v, None if v is None else _reach_points(p, v, ww)))
    v = Match._solve_shot(None, p, (0.0, -8.0), 12.0, ww)
    return {"cands": cands, "fallback": v if v is not None else np.array([-p[0] * 0.05, -12.0, 4.0]), "complete": True}


def opp_spec(b_p, b_v, b_w, n_sub, mode, lv, n_points, n_legs, base_hints=None):
    """Speculative precompute (wall clock): the ball after n_sub more 1 ms steps of free flight (the live integrator,
    bit-exact) and the opponent's candidate search there. Returns (cache key, candidates) or None (net)."""
    p, v, w = tuple(b_p), tuple(b_v), tuple(b_w)
    for _ in range(int(n_sub)):
        p, v, w, e = ball_advance(p, v, w)
        if e is not None and e[0] == "net":
            return None
    pa = np.array(p)
    return (tuple(float(x) for x in pa), mode, n_points, n_legs), opp_candidates(pa, mode, lv, n_points, n_legs,
                                                                                  base_hints)



# ---------------------------------------------------------------------- wall clock: stroke planning outside the lock
def plan_snapshot(m: "Match") -> dict:
    """What the stroke planner needs, taken at the step k_s an act is accepted: the robot's physical state, its
    joint targets, its current command (the rest of the stroke under way, the base's rest position) and the leg
    context (launch step, shot index, seed). No ball state."""
    s, d = m.s, m.s.d
    return {"k": s.k, "qpos": d.qpos.copy(), "qvel": d.qvel.copy(), "qacc_warmstart": d.qacc_warmstart.copy(),
            "ctrl": d.ctrl.copy(), "time": float(d.time), "target": s.target.copy(),
            "tail": [a.copy() for a in s._actions[-2:]], "plan": [q.copy() for q in m.plan[m.plan_j:]],
            "base_goal": None if m.base_goal is None else m.base_goal.copy(),
            "q_hit_active": getattr(m, "_q_hit_active", None), "launch": int(m.leg["launch"]),
            "seed": int(m.lv["seed"]), "n_our_legs": int(m.n_our_legs)}


class PlanCtx(Match):
    """A robot-only twin for planning an act outside the sim lock (a worker process; the replay uses the same
    code in-process). plan_act(): restore the snapshot of step k_s, run the robot `lead` control steps with its current
    command (joint targets bit-exact, they do not depend on the physics), then plan the stroke exactly as rt_act
    would at k_e = k_s + lead, with the snapshot's leg context."""

    def __init__(self):  # noqa: D107 (no match, no ball)
        self.s = Phys()
        self.s.reset(np.r_[HOME, Q0_ARM])
        self._twin = None
        self.leg, self.lv, self.n_our_legs = {"launch": 0}, {"seed": 0}, 0
        self.plan, self.plan_j, self.base_goal = [], 0, None
        self._q_hit_active = None

    def plan_act(self, snap: dict, lead: int, T, pos, nrm, vel, base=None) -> dict:
        s, d = self.s, self.s.d
        mj.mj_resetData(s.m, d)
        d.qpos[:] = snap["qpos"]; d.qvel[:] = snap["qvel"]; d.qacc_warmstart[:] = snap["qacc_warmstart"]
        d.ctrl[:] = snap["ctrl"]; d.time = snap["time"]
        mj.mj_forward(s.m, d)
        s.target = snap["target"].copy(); s.k = snap["k"]; s._actions = [a.copy() for a in snap["tail"]]
        s.b_live = s.hit_enabled = False; s.events = []; s._prev = None
        self.plan, self.plan_j = [q.copy() for q in snap["plan"]], 0
        self.base_goal = None if snap["base_goal"] is None else snap["base_goal"].copy()
        self._q_hit_active = snap["q_hit_active"]
        self.leg = {"launch": snap["launch"]}; self.lv = {"seed": snap["seed"]}; self.n_our_legs = snap["n_our_legs"]
        for _ in range(int(lead)):
            s.step(self._arm_target())
        t_hit = (self.k - self.leg["launch"]) * CONTROL_DT + float(T)
        active = self.plan_j < len(self.plan)
        self._ik_seed = self._q_hit_active if active else None
        plan, info = self.plan_racket(t_hit, pos, nrm, vel, base)
        q_hit = info.pop("_q_hit", None)
        info["T_from_now"] = round(float(T), 4)
        return {"plan": plan, "info": info, "q_hit": q_hit, "k_effect": int(self.k),
                "target_at_effect": s.target.copy()}


def _ready_pose():
    """Ready pose: racket head in front of the robot's right side at about 1 m, face towards the net."""
    global Q0_ARM
    ph = Phys(); ph.reset(np.r_[HOME, Q0_ARM])
    q, err = ik(ph, np.r_[HOME + STANCE_OFF + np.array([0.0, -0.1]), 1.0], np.array([0.0, 1.0, 0.1]), HOME,
                np.array([0.0, -0.2, 0.0, -1.6, 0.0, 1.6, 0.785]), iters=400)
    Q0_ARM = np.round(q, 4)


_ready_pose()


def render_video(actions, level, out, fps=25, every=2):
    """Replay video: the two decision cameras side by side, 2x slow motion (every `every` control steps at 25 fps),
    3x fewer frames while no ball is in play."""
    import imageio.v2 as imageio
    from PIL import Image, ImageDraw
    mt = Match(level)
    r = mj.Renderer(mt.s.m, height=360, width=640)
    rd = mj.MjData(mt.s.m)
    cams = []
    for lookat, dist, az, el in Match.CAMS:
        c = mj.MjvCamera(); c.lookat[:] = lookat; c.distance = dist; c.azimuth = az; c.elevation = el
        cams.append(c)
    w = imageio.get_writer(out, fps=fps, macro_block_size=8)
    for k, q in enumerate(actions):
        mt.step(q)
        live = mt.s.b_live
        if k % (every if live else 3 * every):
            continue
        sn = {"qpos": mt.s.d.qpos.copy(), "b": mt.s.b_p}
        mt._set_render_state(rd, sn)
        imgs = []
        for c in cams:
            r.update_scene(rd, camera=c)
            mt._extra_geoms(r.scene, mt.opp_x(), mt.s.b_p)
            imgs.append(r.render())
        im = Image.fromarray(np.concatenate(imgs, axis=1))
        ImageDraw.Draw(im).text((8, 6), f"robot {mt.score[0]} : {mt.score[1]} opponent   (level {level})",
                                fill=(255, 255, 255))
        w.append_data(np.asarray(im))
    w.close(); r.close()
