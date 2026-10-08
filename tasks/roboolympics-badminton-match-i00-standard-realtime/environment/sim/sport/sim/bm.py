"""Core of the robot badminton match service (interactive mode): first to 5 (two-point lead from 4-4, at most 7) against a scripted opponent.

World (metres, seconds): floor z = 0, court long axis y, net = the plane y = 0 with its top at 1.524 m. The robot's
half is y < 0, the opponent's y > 0. Singles court |x| <= 2.59, |y| <= 6.70.

Robot: a Franka Panda arm on a 1.0 m pedestal whose base slides in x and y (a mobile base: 2 prismatic joints, speed
<= 6 m/s), holding a badminton racket (head centre 0.56 m beyond the flange). One action = 9 absolute joint targets
[base_x, base_y, q1..q7] held for 10 ms; a PD controller with bias compensation (1 ms physics steps) tracks them;
target steps are limited to the joint speed limits (base 6 m/s, Franka datasheet for the arm).

Shuttlecock (not a MuJoCo body; integrated here at 1 ms, semi-implicit Euler, pure Python floats, deterministic):
a point mass under gravity and quadratic drag, dv/dt = g - K |v| v with K = g / V_TERM^2, V_TERM = 6.8 m/s (the
measured terminal speed of a feather shuttle). A real shuttle flips to fly cork first within a few centimetres of a
hit; a point mass has no orientation, it is drawn cork first along its velocity. No bounce: when the shuttle reaches
the floor (z <= 0) the rally is over.

Racket-shuttle contact (a model, not MuJoCo contact): at every 1 ms step the shuttle's centre is tested against the
racket's string plane; when it crosses the plane within R_HEAD of the head centre, the shuttle leaves along the face
normal (the side facing the relative motion) at
    speed = RACKET_GAIN * (racket-head speed along the normal) * (1 - OFFCENTRE_LOSS (r / R_HEAD)^2)
            + E_SHUTTLE * (incoming speed into the face)
RACKET_GAIN = 20 stands for the string bed and the wrist snap a Franka does not have (a Franka moves the head at a few
m/s; a badminton shot needs 15-50 m/s). One hit per shot.

Point flow (all inside Match.step() and the player's commands, so a recorded command sequence replays the whole match
bit-exactly). You serve the first point; then the winner of the last rally serves (BWF Law 10.3). Both players stand
at their spots in their service courts (serve_spot, diagonally opposite) before every serve:
  ready    READY_STEPS; the server holds the shuttle.
  serve    the opponent's serve: high and deep, or short (a seeded choice per point, by level), hit at 1.05 m
           upwards into your diagonal service court. Your serve (leg kind "our_serve"): within SERVE_WINDOW_STEPS you
           toss the shuttle (toss(), the `toss` command) and hit it below SERVE_MAX_Z, upwards; then it flies
           to the opponent like any of your shots (it must land in the opponent's diagonal service court).
  our leg  the shuttle comes to us; the model decides the shot (live code: swing / adjust decision points); the
           robot hits it or not. Our shot is good if the shuttle crosses the net above its top and would land in the
           opponent's court. The shuttle landing in our court, the net, out = the opponent's point.
  opp leg  the opponent (below) returns it (a new "our leg" starts at its hit) or cannot reach it (our point when it
           lands in); a shot that would land out it leaves (our fault).

The opponent (LEVELS): a kinematic player on its half, at home (0, 3.8) between rallies. `reaction_s` after our hit it
predicts the flight perfectly and moves in a straight line towards the best interception point at `chase` m/s; after
its own shots it walks back home at `recover` m/s. For every point of the flight in its hitting envelope (its half,
height 0.1-2.7 m) it evaluates
    pressure = max(max(0, distance - chase * time) / reach, (shuttle speed there - SPEED_FREE) / (max_speed - SPEED_FREE))
takes the shuttle at the earliest point whose pressure is within 0.05 of the minimum, and there, deterministically:
pressure > 1 -> it misses (our point); > PRESSURE_WEAK -> a weak lift to the middle of our court; < PRESSURE_PASSIVE ->
it attacks (a smash from above 1.9 m, else a tight drop or a fast push to a corner, at its widest); otherwise a
normal return (a seeded clear / drop / drive within the level's width and pace). It sets the shuttle's velocity (an
impulse; its racket is drawn only) so that the shuttle lands at its target, clears the net by >= 15 cm, and our robot
can reach the flight from where it stands; an unreachable shot moves towards the centre and becomes gentler.
Our strokes scatter: the aim is perturbed by a seeded N(0, EXEC_SIGMA[power]) per shot.
"""
from __future__ import annotations

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
SCENE = Path(os.environ.get("RCB_BM_SCENE", HERE / "scene" / "bm_scene.xml"))

CONTROL_DT, SUBSTEPS, PHYS_DT = 0.01, 10, 0.001
GRAV, V_TERM = 9.81, 6.8
K_DRAG = GRAV / V_TERM ** 2
NET_TOP, COURT_X, COURT_Y, POST_X = 1.524, 2.59, 6.70, 3.05   # BWF Law 1.10: net top 1.524 m (at the centre)
SHORT_SERVICE_Y = 1.98
R_HEAD, RACKET_GAIN, E_SHUTTLE, OFFCENTRE_LOSS = 0.14, 20.0, 0.15, 0.3
ARM_VEL = np.array([2.175, 2.175, 2.175, 2.175, 2.61, 2.61, 2.61])
BASE_VMAX, BASE_AMAX = 6.0, 20.0       # the base moves like a fast badminton player (single and duel; 2026-10-03)
VEL_LIMIT = np.r_[BASE_VMAX, BASE_VMAX, ARM_VEL]
KP = np.array([4e4, 4e4, 2400.0, 2400.0, 2400.0, 2400.0, 1000.0, 600.0, 200.0])
KD = np.array([3e3, 3e3, 100.0, 100.0, 100.0, 100.0, 30.0, 20.0, 6.0])
JOINTS = ["base_x", "base_y"] + [f"joint{i}" for i in range(1, 8)]
HOME = np.array([0.0, -4.0])                 # the robot's base between shots
PED_H = 1.0                                  # link0 height on the pedestal; shoulder at PED_H + 0.333
Q0_ARM = np.array([0.0, -0.3, 0.0, -1.9, 0.0, 1.9, 0.785])   # ready pose (refined at import by IK, see _ready_pose)
BASE_LO, BASE_HI = np.array([-3.25, -7.5]), np.array([3.25, -0.5])

WIN_POINTS = 5                  # first to 5; from 4-4 a two-point lead is needed; the first to CAP_POINTS wins
CAP_POINTS = 7
MAX_HITS = 300                  # cap on hits in the match (both sides): the match ends after that point; the leader wins,
MAX_POINTS = 40                 # if level the winner of the last point (no draws; the same in single and duel)
READY_STEPS = 100               # 1.0 s between points
LEG_STEPS = 600                 # safety: 6 s after a serve or hit without a decision -> the player to hit loses
CAM_EVERY = 2                   # 50 Hz camera snapshots
SWING_AFTER = 20                # first decision point: 0.2 s after the shuttle was played (serve or opponent's hit)
ADJUST_BEFORE = 30              # second decision point: 0.3 s before the planned contact
OPP_HOME = np.array([0.0, 3.8])
OPP_Z = (0.10, 2.70)            # the opponent's hitting envelope (height)
SPEED_FREE = 12.0
PRESSURE_WEAK, PRESSURE_PASSIVE = 0.75, 0.35
EXEC_SIGMA = {"soft": 0.12, "normal": 0.20, "hard": 0.30}
POWER = ("soft", "normal", "hard")
AIM_DEFAULT = (0.0, 4.0)

LEVELS = {   # defence: reaction, chase / recovery speed, reach, too-fast threshold; attack: width, pace (smash speed);
             # serve: share of high serves, |x| range of the serve's target, depth range of a short serve (receiver frame)
    1: dict(reaction_s=0.30, chase=2.2, recover=1.6, reach=0.95, max_speed=24.0, width=1.4, pace=24.0, seed=101,
            serve_high=0.7, serve_x=(0.4, 1.6), serve_short_y=(-2.5, -2.8)),
    2: dict(reaction_s=0.25, chase=2.6, recover=1.9, reach=1.05, max_speed=28.0, width=1.9, pace=30.0, seed=202,
            serve_high=0.5, serve_x=(0.25, 2.2), serve_short_y=(-2.2, -2.5)),
}

# The players' serve (BWF Laws 9-10; 2026-10-07). Before every serve both robots are put in their service courts at
# their spot (serve_spot: x = +SPOT_X in the right court, -SPOT_X in the left one; own frame), at rest in the ready
# pose; the spot is the robot's home (the ready target's base goal) for the whole point. READY_STEPS after play
# resumes the receiver is ready (Law 9.4) and the server may toss the shuttle (docs/conventions/racket_serve_zh.md):
# it appears at a point the server chooses, within TOSS_REACH (horizontally) of its base and TOSS_Z high, and is
# released from rest (height 0) or projected straight up to rise at most TOSS_H_MAX (the robot has no free hand: the
# toss stands for the server's hand letting go of the shuttle, Law 9.1.5: no spin), within SERVE_WINDOW_STEPS (else a
# fault: undue delay, Law 9.1.1). Then the server must hit it (a miss is a fault, Law 9.1.8) below SERVE_MAX_Z (Law 9.1.6) and upwards (Law
# 9.1), over the net into the receiver's diagonal service court (Laws 9.1, 10.1). Both bases stay within BASE_TOL of
# their spots until the serve is delivered (Law 9.1.4; both moving: a let, Law 14.2.2). The rally winner serves next
# (Law 10.3).
SPOT_X, SPOT_Y = 0.3, -4.0
TOSS_REACH, TOSS_Z, TOSS_H_MAX = 1.0, (0.5, 1.8), 0.5
SERVE_MAX_Z = 1.15
SERVE_WINDOW_STEPS = 300                     # 3 s after the receiver is ready
BASE_TOL = 0.05
MAX_DELAY_FAULTS = 3                         # the third undue-delay fault of a player disqualifies it (Laws 16.6.1, 16.7)


def serve_spot(right: bool) -> np.ndarray:
    """Where both robots stand before a serve (own frame): in their right service courts when the server's score is
    even (BWF 10.1), else in their left ones."""
    return np.array([SPOT_X if right else -SPOT_X, SPOT_Y])


def toss_problem(p, h, base) -> str | None:
    """Why a toss (point p in the own frame, height h) is not allowed for a robot whose base is at `base`, or None."""
    p = np.asarray(p, float)
    if p.shape != (3,) or not np.all(np.isfinite(p)):
        return "the toss point must be 3 finite numbers"
    if not (isinstance(h, (int, float)) and math.isfinite(h) and 0.0 <= h <= TOSS_H_MAX):
        return f"the toss height must be 0-{TOSS_H_MAX} m (0: released from rest)"
    if not TOSS_Z[0] <= p[2] <= TOSS_Z[1]:
        return f"the toss point must be {TOSS_Z[0]}-{TOSS_Z[1]} m high"
    d = float(np.hypot(p[0] - base[0], p[1] - base[1]))
    if d > TOSS_REACH:
        return f"the toss point must be within {TOSS_REACH} m (horizontally) of your base; it is {d:.2f} m away"
    if p[1] > -0.5:
        return "the toss point must be on your half, y <= -0.5"
    return None


def toss_vz(h) -> float:
    """The upward speed that makes a shuttle rise h metres under gravity and quadratic drag (exact for the continuous
    model: h = V_TERM^2 / (2 g) ln(1 + vz^2 / V_TERM^2))."""
    return float(V_TERM * math.sqrt(math.expm1(2.0 * GRAV * float(h) / V_TERM ** 2)))

# launch-angle families (deg) of the opponent's shots, tried in order; max launch speed (m/s)
SHOT_THETAS = {"clear": (50, 45, 55, 40, 60, 35), "lift": (58, 52, 64, 46), "drop": (5, 0, 10, 15, -5, 20, 25, 30),
               "drive": (6, 2, 10, 14, -2, 18), "smash": (-14, -10, -18, -6, -22, -2), "push": (28, 32, 24, 36, 20),
               "serve_high": (55, 50, 60, 45), "serve_short": (22, 26, 18, 30, 34)}
SHOT_VMAX = {"clear": 60.0, "lift": 50.0, "drop": 25.0, "drive": 34.0, "smash": 45.0, "push": 34.0,
             "serve_high": 55.0, "serve_short": 14.0}
OUR_THETAS = (-30, -22, -15, -9, -4, 0, 4, 8, 13, 19, 26, 34, 43, 52, 61)
OUR_VMAX = 55.0


# ---------------------------------------------------------------------- shuttle physics
def sh_step(p, v):
    """One 1 ms step of the shuttle (python floats)."""
    vx, vy, vz = v
    c = K_DRAG * math.sqrt(vx * vx + vy * vy + vz * vz) * PHYS_DT
    vx -= c * vx
    vy -= c * vy
    vz -= GRAV * PHYS_DT + c * vz
    return (p[0] + vx * PHYS_DT, p[1] + vy * PHYS_DT, p[2] + vz * PHYS_DT), (vx, vy, vz)


def predict(p, v, n_max=6000):
    """Shuttle-only flight from (p, v): arrays P, V (N, 3) after 1..N steps of 1 ms, until the floor (inclusive) or
    the net (the step at which it crossed y = 0 below the net top, inclusive)."""
    p = tuple(float(x) for x in p); v = tuple(float(x) for x in v)
    P, V = [], []
    for _ in range(n_max):
        p1, v1 = sh_step(p, v)
        if (p[1] > 0) != (p1[1] > 0) and p[1] != p1[1]:
            f = p[1] / (p[1] - p1[1])
            z = p[2] + f * (p1[2] - p[2]); x = p[0] + f * (p1[0] - p[0])
            if z < NET_TOP and abs(x) <= POST_X:
                P.append(p1); V.append(v1)
                break
        P.append(p1); V.append(v1)
        p, v = p1, v1
        if p[2] <= 0.0:
            break
    return np.array(P), np.array(V)


def flight_table(p0, heading, thetas_deg, speeds, dt=0.002, t_max=4.0):
    """Vectorised planar flights from p0 along `heading` (unit xy) for every (theta, speed): horizontal range at the
    floor, height when crossing the net plane y = 0 (nan if it never does), flight time. Solver only (2 ms steps);
    the real flight is the 1 ms 3-D integration."""
    th = np.deg2rad(np.asarray(thetas_deg, float))[:, None]
    sp = np.asarray(speeds, float)[None, :]
    vh = (np.cos(th) * sp).ravel(); vz = (np.sin(th) * sp).ravel()
    n = vh.size
    h = np.zeros(n); z = np.full(n, float(p0[2]))
    s_net = (-p0[1] / heading[1]) if abs(heading[1]) > 1e-9 else np.inf
    rng_ = np.full(n, np.nan); znet = np.full(n, np.nan); tf = np.full(n, np.nan)
    alive = np.ones(n, bool)
    for i in range(int(t_max / dt)):
        s = np.sqrt(vh * vh + vz * vz)
        c = K_DRAG * s * dt
        vh = vh - c * vh; vz = vz - GRAV * dt - c * vz
        h1 = h + vh * dt; z1 = z + vz * dt
        cross = alive & (h < s_net) & (h1 >= s_net)
        if cross.any():
            f = (s_net - h[cross]) / (h1[cross] - h[cross])
            znet[cross] = z[cross] + f * (z1[cross] - z[cross])
        land = alive & (z1 <= 0.0)
        if land.any():
            f = z[land] / (z[land] - z1[land])
            rng_[land] = h[land] + f * (h1[land] - h[land]); tf[land] = (i + f) * dt
            alive &= ~land
        h, z = h1, z1
        if not alive.any():
            break
    shp = (len(thetas_deg), len(speeds))
    return rng_.reshape(shp), znet.reshape(shp), tf.reshape(shp)


def solve_shots(p0, target, thetas, vmax, net_margin=0.15, vmin=2.0):
    """Launch velocities from p0 that land at `target` (xy) and clear the net top by >= net_margin: one per launch
    angle that works (in the order given). Returns [(theta, speed, v (3,), flight time)]."""
    p0 = np.asarray(p0, float); target = np.asarray(target, float)
    d = target - p0[:2]; H = float(np.linalg.norm(d))
    if H < 1e-6:
        return []
    hd = d / H
    speeds = np.linspace(vmin, vmax, 90)
    R, ZN, TF = flight_table(p0, hd, thetas, speeds)
    out = []
    for i, th in enumerate(thetas):
        r = R[i]; ok = np.isfinite(r)
        if not ok.any():
            continue
        r_ok = r[ok]; s_ok = speeds[ok]
        j = np.nonzero(r_ok >= H)[0]
        if len(j) == 0:
            continue
        j = j[0]
        if j == 0:
            v = s_ok[0]; f = 0.0; j0 = 0
        else:
            f = (H - r_ok[j - 1]) / (r_ok[j] - r_ok[j - 1]); v = s_ok[j - 1] + f * (s_ok[j] - s_ok[j - 1]); j0 = j - 1
        zn = ZN[i][ok]; tf = TF[i][ok]
        crosses = (p0[1] > 0) != (target[1] > 0)
        if crosses:
            z_net = zn[j0] + f * (zn[min(j, len(zn) - 1)] - zn[j0]) if j > 0 else zn[0]
            if not np.isfinite(z_net) or z_net < NET_TOP + net_margin:
                continue
        t_f = tf[j0] + f * (tf[min(j, len(tf) - 1)] - tf[j0]) if j > 0 else tf[0]
        thr = math.radians(th)
        vel = np.array([hd[0] * v * math.cos(thr), hd[1] * v * math.cos(thr), v * math.sin(thr)])
        out.append((th, float(v), vel, float(t_f)))
    return out


def in_service_court(x, y, right):
    """The receiver's service court in the receiver's frame (receiver on y < 0, facing +y; singles: between the short
    service line and the back line; its right court is x >= 0). BWF Laws 9.1 / 10.1: the serve must land in the court
    diagonally opposite, the receiver's right court when the server's score is even (lines are in)."""
    return (0.0 <= x <= COURT_X if right else -COURT_X <= x <= 0.0) and -COURT_Y <= y <= -SHORT_SERVICE_Y


def serve_plan(seed, n, server_score, base, reachable, lv=None):
    """The scripted opponent's serve (type, hitting point p0, velocity) in the RECEIVER's frame, from the server's
    service court into the receiver's diagonal service court (BWF 10.1.1: from the right court when the server's score
    is even), hit at 1.05 m (below 1.15 m, Law 9.1.6) and upwards (Law 9.1). The server faces -y, so its right court is
    x < 0. seed: the rng seed list prefix; n: the point's serial number (lets included, for the seeded choice);
    reachable(p0, v, base): the receiver can meet the flight; lv: the level (share of high serves, target range)."""
    lv = lv or LEVELS[1]
    rng = np.random.default_rng(list(seed) + [11, n])
    u = rng.uniform(-1, 1, 4)
    right = server_score % 2 == 0
    sx = -0.45 if right else 0.45                  # the server's right court is at x < 0 in the receiver's frame
    p0 = np.array([sx, 2.3, 1.05])
    high = (u[0] + 1.0) / 2.0 < lv["serve_high"]
    typ = "serve_high" if high else "serve_short"
    side = 1.0 if right else -1.0                  # the receiver's diagonal court: x > 0 when the server serves from its right
    x0, x1 = lv["serve_x"]
    tx = side * (x0 + (x1 - x0) * (u[1] + 1.0) / 2.0)
    y0, y1 = lv["serve_short_y"]
    ty = -5.9 - 0.4 * abs(u[2]) if high else y0 + (y1 - y0) * abs(u[2])
    v = None
    for frac in (1.0, 0.6, 0.3):
        c = solve_shots(p0, (side * max(0.25, abs(tx) * frac), ty), SHOT_THETAS[typ], SHOT_VMAX[typ])
        c = [x for x in c if reachable(p0, x[2], base)]
        if c:
            v = c[0][2]; break
    if v is None:
        v = solve_shots(p0, (side * 0.6, -5.5), SHOT_THETAS["serve_high"], 60.0)[0][2]
    return typ, p0, np.asarray(v, float), right


def in_court(x, y, side):
    """side +1: the opponent's court, -1: ours (lines are in)."""
    return abs(x) <= COURT_X and (0.0 < side * y <= COURT_Y)


def base_goto(b, v, goal):
    """One control step of the base's go-to generator (bounded speed and acceleration): new (target, velocity)."""
    e = goal - b; dist = float(np.hypot(e[0], e[1]))
    sp = float(np.hypot(v[0], v[1]))
    if dist < 0.004 and sp < 0.15:
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


SHOULDER_Z = PED_H + 0.333


def stance(p):
    """Where the base should stand to meet the shuttle at p with a forehand: the contact to the right of and in front
    of the base, closer in for high and low contacts."""
    dz = float(p[2]) - SHOULDER_Z
    r = max(0.30, 0.95 - 0.35 * abs(dz))
    off = np.array([0.62 * r, 0.62 * r])
    return np.clip(np.asarray(p[:2], float) - off, BASE_LO, BASE_HI)


def quat_z_to(v):
    """Quaternion rotating the local z axis onto the direction v."""
    v = np.asarray(v, float); n = np.linalg.norm(v)
    if n < 1e-9:
        return np.array([1.0, 0, 0, 0])
    v = v / n; z = np.array([0.0, 0, 1])
    c = float(z @ v)
    if c < -0.999999:
        return np.array([0.0, 1, 0, 0])
    ax = np.cross(z, v); s = math.sqrt((1 + c) * 2)
    return np.array([s / 2, ax[0] / s, ax[1] / s, ax[2] / s])


def hermite(q0, v0, q1, v1, T, n):
    t = np.arange(1, n + 1) * (T / n)
    s = t / T
    h00 = 2 * s**3 - 3 * s**2 + 1; h10 = s**3 - 2 * s**2 + s; h01 = -2 * s**3 + 3 * s**2; h11 = s**3 - s**2
    return h00[:, None] * q0 + h10[:, None] * T * v0 + h01[:, None] * q1 + h11[:, None] * T * v1


# ---------------------------------------------------------------------- robot + shuttle physics
class Phys:
    """MuJoCo robot (mobile base + Franka + racket), the shuttle integrator and the racket-shuttle contact model."""

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
        self.sh_p, self.sh_v, self.sh_live = (0.0, 3.0, 1.0), (0.0, 0.0, 0.0), False
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
        self.sh_p, self.sh_v, self.sh_live, self.hit_enabled = o.sh_p, o.sh_v, o.sh_live, o.hit_enabled
        self.events = []
        self._prev = None if o._prev is None else (o._prev[0].copy(), o._prev[1].copy(), o._prev[2])

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
            # site pose now = the pose at the start of this step (time t_n), the same time as self.sh_p
            c = d.site_xpos[self.site].copy(); n = d.site_xmat[self.site].reshape(3, 3)[:, 0].copy()
            if self.sh_live:
                if self.hit_enabled and self._prev is not None and self.sh_p[1] < 0:   # only on our half (BWF 13.4.2)
                    self._check_hit(c, n)
                self._prev = (c, n, self.sh_p)
                self._advance_shuttle()
            else:
                self._prev = (c, n, self.sh_p)
        self.target = q.copy()
        self._actions.append(q.copy())
        self.k += 1
        self.steps_total += SUBSTEPS

    def actions(self) -> np.ndarray:
        """(N, 9) joint targets applied since the reset."""
        return np.array(self._actions, dtype=np.float64).reshape(-1, 9)

    def _advance_shuttle(self):
        p, v = self.sh_p, self.sh_v
        p1, v1 = sh_step(p, v)
        if (p[1] > 0) != (p1[1] > 0) and p[1] != p1[1]:
            f = p[1] / (p[1] - p1[1])
            z = p[2] + f * (p1[2] - p[2]); x = p[0] + f * (p1[0] - p[0])
            self.events.append({"kind": "cross", "k": self.k, "x": round(x, 4), "z": round(z, 4),
                                "to": "opp" if p1[1] > 0 else "own"})
            if z < NET_TOP and abs(x) <= POST_X:
                self.sh_p = (x, 0.0, z); self.sh_v = (0.0, 0.0, 0.0); self.sh_live = False
                self.events.append({"kind": "net", "k": self.k, "x": round(x, 4), "z": round(z, 4)})
                return
        if p1[2] <= 0.0:
            f = p[2] / (p[2] - p1[2]) if p[2] != p1[2] else 1.0
            x = p[0] + f * (p1[0] - p[0]); y = p[1] + f * (p1[1] - p[1])
            self.sh_p = (x, y, 0.0); self.sh_v = (0.0, 0.0, 0.0); self.sh_live = False
            self.events.append({"kind": "land", "k": self.k, "x": round(x, 4), "y": round(y, 4)})
            return
        self.sh_p, self.sh_v = p1, v1

    def _check_hit(self, c, n):
        cp, npv, sp = self._prev
        sp = np.array(sp); sh = np.array(self.sh_p)
        s0 = float((sp - cp) @ npv); s1 = float((sh - c) @ n)
        if s0 * s1 > 0 or (s0 == 0 and s1 == 0):
            return
        f = s0 / (s0 - s1) if s0 != s1 else 0.0
        pc = cp + f * (c - cp); ps = sp + f * (sh - sp)
        r = ps - pc
        off = float(np.linalg.norm(r - (r @ n) * n))
        if off > R_HEAD:
            return
        vr = (c - cp) / PHYS_DT; vs = np.array(self.sh_v)
        n_out = n if float((vr - vs) @ n) >= 0 else -n
        u = float(vr @ n_out); vin = float(vs @ n_out)
        spd = RACKET_GAIN * max(u, 0.0) * (1 - OFFCENTRE_LOSS * (off / R_HEAD) ** 2) + E_SHUTTLE * max(0.0, -vin)
        v_out = n_out * spd
        p_new = ps + n_out * 0.002
        self.sh_p = tuple(float(x) for x in p_new); self.sh_v = tuple(float(x) for x in v_out)
        self.hit_enabled = False
        self.events.append({"kind": "hit", "k": self.k, "pos": [round(float(x), 4) for x in ps],
                            "offcentre": round(off, 4), "racket_speed": round(u, 3), "speed": round(spd, 3),
                            "v_out": [round(float(x), 3) for x in v_out]})

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
        for a in (d.qpos, d.qvel, d.qacc_warmstart, d.ctrl, np.array([d.time]), np.array(self.sh_p + self.sh_v)):
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
    """The match. Live: run_to_decision() / shot() / adjust(). Replay: replay(actions)."""

    # decision cameras: (lookat, distance, azimuth, elevation) of MuJoCo free cameras
    CAMS = (([0.0, -1.0, 2.8], 13.5, 90.0, -6.0),         # behind and above the robot's baseline, looking down the court
            ([0.0, -1.5, 3.0], 14.0, 0.0, -4.0))          # at the side of the court (x < 0), looking along +x
    VIEW_BACK = (0, 3, 6, 9)                              # snapshots back from the latest: 0, 60, 120, 180 ms
    TILE = (480, 360)

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
        self.points: list[dict] = []
        self.legs: list[dict] = []
        self.results: list[dict] = []
        self.shots: list[dict] = []
        self.hist: deque = deque(maxlen=16)
        self.done = False
        self.winner = None                         # 0 you, 1 the opponent (set when the match ends)
        self.hits = 0                              # hits in the match, both sides (the MAX_HITS cap)
        self.phase = "swing"
        self.plan, self.plan_j, self._rec = [], 0, {}
        self._adj_k = None
        self.n_our_legs = 0
        self.delay_faults = 0                      # your serves not tossed in time (undue delay)
        self.disqualified = False                  # MAX_DELAY_FAULTS reached: you lose the match (Law 16.7)
        self._start_point(hold_from=0)

    @property
    def k(self) -> int:
        return self.s.k

    # ------------------------------------------------------------------ points / legs
    def next_server(self) -> int:
        """0 (you) or 1 (the opponent): you serve the first point (Law 6: the toss is fixed in this format); then the
        winner of the last rally serves (Law 10.3); after a let the same player serves again (Law 14.3)."""
        if not self.points:
            return 0
        last = self.points[-1]
        if last.get("let"):
            return last["server"]
        return 0 if last["winner"] == "you" else 1

    def _start_point(self, hold_from: int):
        self.hist.clear()          # camera history (display only): no frames of the previous point in the next views
        n = len(self.points)
        server = self.point_server = self.next_server()
        right = self.score[server] % 2 == 0          # the server's right court when its score is even (Law 10.1)
        self.home = serve_spot(right)                # both robots in their right (left) courts, diagonally (Law 9.1.3)
        if server == 1:
            # the opponent serves from its right court when its own score is even (BWF 10.1.1), diagonally to us
            typ, p0, v, right = serve_plan([self.lv["seed"]], n, self.score[1], self.home, self._reachable, self.lv)
            sx = float(p0[0])
            self.leg = {"kind": "serve", "serve": typ, "point": n, "hold_from": hold_from, "server": 1,
                        "launch": hold_from + READY_STEPS, "state": "incoming", "p0": p0.tolist(),
                        "v0": [float(x) for x in v], "service_court_right": right}
            # the server stands at its serving spot and walks home from the moment it serves
            self.opp = {"xy0": np.array([sx, 2.7]), "k0": hold_from + READY_STEPS, "txy": OPP_HOME.copy(),
                        "speed": self.lv["recover"]}
        else:
            # you serve: READY_STEPS after play resumes the opponent is ready and you may toss the shuttle
            ready = hold_from + READY_STEPS
            self.leg = {"kind": "our_serve", "point": n, "hold_from": hold_from, "server": 0, "launch": ready,
                        "ready": ready, "deadline": ready + SERVE_WINDOW_STEPS, "state": "held",
                        "service_court_right": right}
            # the opponent receives in its diagonal service court (its right court is x < 0 in your frame) and
            # stands still until the serve is delivered
            spot = np.array([-0.45 if right else 0.45, OPP_HOME[1]])
            self.opp = {"xy0": spot, "k0": hold_from, "txy": spot.copy(), "speed": 0.0}
            p0 = np.r_[self.home + np.array([-0.25, 0.35]), 1.0]   # held in the server's (missing) free hand
            v = np.zeros(3)
        self.legs.append(self.leg)
        self._new_leg()
        self.s.sh_p = tuple(float(x) for x in p0); self.s.sh_v = tuple(float(x) for x in v); self.s.sh_live = False
        self._go_home()

    def _go_home(self):
        """Before every serve: the robot at its spot in its service court (its home for the point) in the ready pose,
        at rest, no command (as in the duel)."""
        ph = self.s
        q = np.r_[self.home, Q0_ARM]
        ph.d.qpos[ph.qa] = q; ph.d.qvel[ph.va] = 0.0
        mj.mj_forward(ph.m, ph.d)
        ph.target = q.copy()
        self.plan, self.plan_j = [], 0
        self._last_act = None; self._q_hit_active = None
        self._since_reset = 0

    def toss(self, p, h=0.0):
        """Your serve: the shuttle appears at p (your frame) now and rises h straight up (0: from rest). Raises
        ValueError if not allowed."""
        leg = self.leg
        if self.done or leg["kind"] != "our_serve":
            raise ValueError("it is not your serve")
        if leg["state"] != "held":
            raise ValueError("the shuttle was already tossed")
        if self.k < leg["ready"]:
            raise ValueError(f"the opponent is not ready before step {leg['ready']}")
        why = toss_problem(p, h, self.s.d.qpos[self.s.qa[:2]])
        if why:
            raise ValueError(why)
        self.s.sh_p = tuple(float(x) for x in p); self.s.sh_v = (0.0, 0.0, toss_vz(h))
        self.s.sh_live = True; self.s.hit_enabled = True
        leg["state"] = "falling"; leg["toss_k"] = self.k; leg["launch"] = self.k
        leg["toss"] = [round(float(x), 4) for x in p]; leg["toss_height"] = float(h)

    def delivered(self) -> bool:
        """The serve of the current point was delivered (hit, missed or faulted)."""
        leg = self.leg
        if leg["kind"] == "our_serve":
            return leg["state"] not in ("held", "falling")
        if leg["kind"] == "serve":
            return self.k >= leg["launch"]
        return True

    def _new_leg(self):
        self.s.events.clear()
        self.s.hit_enabled = False
        self._opp_plan_k = None

    def in_play(self) -> bool:
        return self.k >= self.leg["launch"]

    def t_since_launch(self) -> float:
        return round((self.k - self.leg["launch"]) * CONTROL_DT, 6)

    # ------------------------------------------------------------------ the opponent
    def opp_xy(self, k=None) -> np.ndarray:
        k = self.k if k is None else k
        o = self.opp
        dt = max(0.0, (k - o["k0"]) * CONTROL_DT)
        e = o["txy"] - o["xy0"]; dist = float(np.hypot(e[0], e[1]))
        if dist < 1e-9:
            return o["xy0"].copy()
        return o["xy0"] + e / dist * min(dist, o["speed"] * dt)

    def _opp_plan(self):
        """`reaction_s` after our hit: predict the flight, choose the interception point, start moving."""
        leg = self.leg
        P, V = predict(self.s.sh_p, self.s.sh_v)
        o = self.opp_xy()
        last = P[-1]
        if leg["kind"] == "our_serve":               # a serve must land in the opponent's diagonal service court
            lands_in = bool(last[2] <= 1e-9 and in_service_court(-last[0], -last[1], leg["service_court_right"]))
        else:
            lands_in = bool(last[2] <= 1e-9 and in_court(last[0], last[1], +1))
        leg["opp_x_react"] = [round(float(x), 3) for x in o]
        if not lands_in:
            leg["opp_leave"] = True
            return
        idx = np.arange(9, len(P), 10)
        j = (idx + 1) // 10
        Pc, sp = P[idx], np.linalg.norm(V[idx], axis=1)
        ok = (Pc[:, 1] > 0.3) & (Pc[:, 2] >= OPP_Z[0]) & (Pc[:, 2] <= OPP_Z[1])
        if not ok.any():
            leg["opp_leave"] = True
            leg["opp_miss"] = "the shuttle never came into the opponent's hitting range"
            return
        lv = self.lv
        dist = np.hypot(Pc[:, 0] - o[0], Pc[:, 1] - o[1])
        t = j * CONTROL_DT
        pp = np.maximum(0.0, dist - lv["chase"] * t) / lv["reach"]
        ps = (sp - SPEED_FREE) / (lv["max_speed"] - SPEED_FREE)
        pr = np.where(ok, np.maximum(pp, ps), np.inf)
        pmin = float(pr.min())
        js = int(np.nonzero(pr <= pmin + 0.05)[0][0])
        leg["opp_hit_k"] = self.k + int(j[js])
        leg["opp_pressure"] = round(float(pr[js]), 3)
        leg["opp_gap"] = round(float(max(0.0, dist[js] - lv["chase"] * t[js])), 3)
        leg["opp_speed_in"] = round(float(sp[js]), 2)
        self.opp = {"xy0": o, "k0": self.k, "txy": Pc[js, :2].copy(), "speed": lv["chase"]}

    def _opp_hit(self):
        leg = self.leg
        p = np.array(self.s.sh_p)
        pr = leg["opp_pressure"]
        rec = {"k": self.k, "pos": [round(float(x), 3) for x in p], "opp_xy": [round(float(x), 3) for x in self.opp_xy()],
               "pressure": pr, "gap": leg.get("opp_gap"), "speed_in": leg.get("opp_speed_in")}
        leg["opp"] = rec
        if pr > 1.0:
            gap = leg.get("opp_gap", 0.0)
            why = (f"out of reach: the opponent was {gap:.2f} m short of the shuttle (reach {self.lv['reach']:.2f} m)"
                   if gap > self.lv["reach"] else
                   f"too fast: the shuttle arrived at {leg.get('opp_speed_in'):.1f} m/s (it handles up to "
                   f"{self.lv['max_speed']:.0f} m/s)")
            leg["opp_miss"] = why; rec["missed"] = why
            return
        mode = "weak" if pr > PRESSURE_WEAK else ("attack" if pr < PRESSURE_PASSIVE else "normal")
        rec["mode"] = mode
        shot, v, target = self._opp_return(p, mode)
        rec.update(shot=shot, target=[round(float(x), 3) for x in target], speed=round(float(np.linalg.norm(v)), 2))
        self._close_our_leg(True, f"good: the opponent played it ({mode} return, a {shot})")
        self.hits += 1
        self.s.sh_v = tuple(float(x) for x in v)
        leg["state"] = "done"
        self.opp = {"xy0": self.opp_xy(), "k0": self.k, "txy": OPP_HOME.copy(), "speed": self.lv["recover"]}
        self.leg = {"kind": "return", "shot": shot, "point": len(self.points), "launch": self.k, "state": "incoming",
                    "opp_hit_pos": rec["pos"]}
        self.legs.append(self.leg)
        self._new_leg()
        self.s.hit_enabled = True

    def _opp_return(self, p, mode):
        lv = self.lv
        rng = np.random.default_rng([lv["seed"], len(self.points), len(self.legs)])
        u = rng.uniform(-1, 1, 5)
        side = 1.0 if u[0] >= 0 else -1.0
        high = p[2] >= 1.9
        W = lv["width"]
        if mode == "weak":
            plan = [("lift", 0.35 * u[0], -3.9 + 0.4 * u[1], 45.0)]
        elif mode == "attack":
            if high:
                plan = [("smash", side * W, -3.3 + 0.5 * u[1], lv["pace"])]
            elif u[1] > 0:
                plan = [("drop", side * W, -1.2, 25.0)]
            else:
                plan = [("push", side * W, -6.0, 34.0)]
        else:
            x = side * W * abs(u[0]) ** 0.5
            if high and u[3] > 0.5:
                plan = [("smash", x, -3.6 + 0.4 * u[1], 0.8 * lv["pace"])]
            elif u[2] < -0.1:
                plan = [("clear", x, -5.9 + 0.3 * u[1], 60.0)]
            elif u[2] < 0.5:
                plan = [("drop", x, -1.7 + 0.3 * u[1], 25.0)]
            else:
                plan = [("drive", x, -4.6 + 0.4 * u[1], 30.0)]
        base = self.s.d.qpos[self.s.qa[:2]].copy()
        typ, tx, ty, vmax = plan[0]
        for frac, t2 in ((1.0, typ), (0.6, typ), (0.3, typ), (0.6, "clear"), (0.0, "clear"), (0.0, "lift")):
            vm = vmax if t2 == typ else SHOT_VMAX[t2]
            tyy = ty if t2 == typ else (-5.6 if t2 == "clear" else -4.0)
            for c in solve_shots(p, (tx * frac, tyy), SHOT_THETAS[t2], vm):
                if self._reachable(p, c[2], base):
                    return t2, c[2], (tx * frac, tyy)
        c = solve_shots(p, (0.0, -4.0), SHOT_THETAS["lift"] + (70, 40, 30), 60.0)
        v = c[0][2] if c else np.array([0.0, -8.0, 12.0])
        return "lift", v, (0.0, -4.0)

    def _reachable(self, p0, v, base) -> bool:
        """Our robot can meet this flight: a point 0.5-2.5 m high inside our court, >= 0.55 s after the shot, whose
        stance the base can reach in time (0.45 s kept for the decision and the swing)."""
        P, _ = predict(p0, v)
        if len(P) == 0 or P[-1][2] > 1e-9 or not in_court(P[-1][0], P[-1][1], -1):
            return False
        idx = np.arange(549, len(P) - 20, 20)
        for i in idx:
            q = P[i]
            if not (0.5 <= q[2] <= 2.5 and q[1] < -0.5):
                continue
            st = stance(q)
            if base_time(float(np.hypot(*(st - base)))) <= (i + 1) * PHYS_DT - 0.45:
                return True
        return False

    # ------------------------------------------------------------------ stepping (shared by live and replay)
    def step(self, q):
        self.s.step(q)
        self._since_reset = getattr(self, "_since_reset", 0) + 1
        leg = self.leg
        if leg["kind"] == "serve" and leg["state"] == "incoming" and self.k == leg["launch"]:
            self.s.sh_live = True; self.s.hit_enabled = True
        self._referee()
        if self.k % CAM_EVERY == 0:
            self.hist.append({"k": self.k, "t": self.t_since_launch(), "qpos": self.s.d.qpos.copy(),
                              "sh": self.s.sh_p, "shv": self.s.sh_v, "opp": self.opp_xy().copy()})

    def _referee(self):
        if self.done:
            return
        leg, s = self.leg, self.s
        kinds = [e["kind"] for e in s.events]
        if not self.delivered():
            moved = float(np.hypot(*(s.d.qpos[s.qa[:2]] - self.home)))
            if moved > BASE_TOL:                        # Law 9.1.4: both players stand still until the serve
                who = "serve_fault:moved" if leg["kind"] == "our_serve" else "receive_fault:moved"
                self._close_our_leg(False, f"{who}: your base moved {moved:.2f} m from its spot before the serve was "
                                           "delivered (Law 9.1.4)")
                self._end_point(1, self.results[-1]["summary"])
                return
        if leg["kind"] == "our_serve" and leg["state"] in ("held", "falling"):
            if leg["state"] == "held":
                if self.k >= leg["deadline"]:
                    self.delay_faults += 1
                    dq = self.delay_faults >= MAX_DELAY_FAULTS
                    self.disqualified = dq
                    self._close_our_leg(False, f"serve_fault:undue_delay: you did not toss the shuttle within "
                                               f"{SERVE_WINDOW_STEPS * CONTROL_DT:.0f} s (undue delay, Law 9.1.1)"
                                        + (f"; your {MAX_DELAY_FAULTS}rd undue-delay fault disqualifies you (Law 16.7)"
                                           if dq else ""))
                    self._end_point(1, self.results[-1]["summary"])
                return
            if "hit" in kinds:
                e = next(e for e in s.events if e["kind"] == "hit")
                leg["hit"] = e; self.hits += 1
                if e["pos"][2] > SERVE_MAX_Z:
                    self._close_our_leg(False, f"serve_fault:too_high: you hit the shuttle {e['pos'][2]:.2f} m high, above "
                                               f"{SERVE_MAX_Z} m (Law 9.1.6)")
                    self._end_point(1, self.results[-1]["summary"])
                elif e["v_out"][2] <= 0.0:
                    self._close_our_leg(False, "serve_fault:not_upwards: the serve did not go upwards from your racket (Law 9.1)")
                    self._end_point(1, self.results[-1]["summary"])
                else:
                    leg["state"] = "to_opp"; leg["delivered_k"] = self.k
                    self._opp_plan_k = self.k + int(round(self.lv["reaction_s"] / CONTROL_DT))
                return
            if "land" in kinds or self.k - leg["launch"] >= LEG_STEPS:
                self._close_our_leg(False, "serve_fault:missed: you missed the shuttle (Law 9.1.8)")
                self._end_point(1, self.results[-1]["summary"])
            return
        if leg["state"] == "incoming":
            if "hit" in kinds:
                e = next(e for e in s.events if e["kind"] == "hit")
                leg["hit"] = e; leg["state"] = "to_opp"; self.hits += 1
                self._opp_plan_k = self.k + int(round(self.lv["reaction_s"] / CONTROL_DT))
                return
            if "net" in kinds:                          # never seen: serves and returns are solved over the net
                e = next(x for x in s.events if x["kind"] == "net")
                what = "serve_fault:net: the opponent's serve" if leg["kind"] == "serve" else "the opponent's shot"
                self._close_our_leg(True, f"{what} hit the net (x={e['x']:.2f}, height {e['z']:.2f} m)")
                self._end_point(0, self.results[-1]["summary"])
                return
            if "land" in kinds:
                e = next(x for x in s.events if x["kind"] == "land")
                if leg["kind"] == "serve" and not in_service_court(e["x"], e["y"], leg["service_court_right"]):
                    self._close_our_leg(True, f"serve_fault:out: the opponent's serve landed outside your service court "
                                              f"(x={e['x']:.2f}, y={e['y']:.2f})")
                    self._end_point(0, self.results[-1]["summary"])
                elif in_court(e["x"], e["y"], -1):
                    self._close_our_leg(False, f"missed: the shuttle landed in your court at x={e['x']:.2f}, y={e['y']:.2f}")
                    self._end_point(1, self.results[-1]["summary"])
                else:
                    self._close_our_leg(True, f"the opponent's shot landed out (x={e['x']:.2f}, y={e['y']:.2f})")
                    self._end_point(0, self.results[-1]["summary"])
            elif self.in_play() and self.k - leg["launch"] >= LEG_STEPS:
                self._close_our_leg(False, "missed"); self._end_point(1, "missed")
            return
        if leg["state"] == "to_opp":
            serve = leg["kind"] == "our_serve"
            if "net" in kinds:
                e = next(x for x in s.events if x["kind"] == "net")
                what = "serve_fault:net: your serve" if serve else "fault: your shot"
                self._close_our_leg(False, f"{what} hit the net (x={e['x']:.2f}, height {e['z']:.2f} m)")
                self._end_point(1, self.results[-1]["summary"])
                return
            if "land" in kinds:
                e = next(x for x in s.events if x["kind"] == "land")
                if e["y"] < 0:
                    self._close_our_leg(False, f"fault: your shot came down on your own side (x={e['x']:.2f}, y={e['y']:.2f})")
                    self._end_point(1, self.results[-1]["summary"])
                elif serve and not in_service_court(-e["x"], -e["y"], leg["service_court_right"]):
                    self._close_our_leg(False, f"serve_fault:out: your serve landed outside the opponent's service court "
                                               f"at x={e['x']:.2f}, y={e['y']:.2f} (the opponent let it go)")
                    self._end_point(1, self.results[-1]["summary"])
                elif serve or in_court(e["x"], e["y"], +1):
                    why = leg.get("opp_miss") or "the opponent could not reach it"
                    self._close_our_leg(True, f"winner: landed in at x={e['x']:.2f}, y={e['y']:.2f} ({why})")
                    self._end_point(0, self.results[-1]["summary"])
                else:
                    self._close_our_leg(False, f"fault: your shot landed out at x={e['x']:.2f}, y={e['y']:.2f} "
                                               "(the opponent let it go)")
                    self._end_point(1, self.results[-1]["summary"])
                return
            if self._opp_plan_k is not None and self.k == self._opp_plan_k:
                self._opp_plan()
            if leg.get("opp_hit_k") == self.k and "opp_miss" not in leg:
                self._opp_hit()
            elif self.k - leg["launch"] >= 3 * LEG_STEPS:
                self._close_our_leg(False, "?"); self._end_point(1, "timeout")

    def _close_our_leg(self, ok, summary):
        leg = self.leg
        if leg.get("closed"):
            return
        leg["closed"] = True
        h = leg.get("hit")
        res = {"leg": self.n_our_legs, "point": len(self.points), "kind": leg["kind"], "returned": bool(ok),
               "summary": summary, "hit": int(h is not None), "speed_out": None if h is None else h["speed"],
               "offcentre": None if h is None else h["offcentre"], "step": self.k}
        self.results.append(res)
        self.n_our_legs += 1

    def match_over(self) -> bool:
        """First to WIN_POINTS; from 4-4 a two-point lead is needed; the first to CAP_POINTS wins."""
        hi, lo = max(self.score), min(self.score)
        return (hi >= WIN_POINTS and hi - lo >= 2) or hi >= CAP_POINTS

    def _end_point(self, winner, how: str):
        """winner 0 (you), 1 (the opponent) or None (a let: the point is replayed)."""
        if winner is not None:
            self.score[winner] += 1
        self.points.append({"point": len(self.points), "winner": None if winner is None else
                            ("you" if winner == 0 else "opponent"), "how": how, "score": list(self.score),
                            "step": self.k, "let": winner is None, "server": self.point_server})
        self.leg["state"] = "done"
        if self.disqualified:
            self.points[-1]["disqualified"] = "you"
            self.winner = 1
            self.done = True
            return
        if self.match_over():
            self.winner = 0 if self.score[0] > self.score[1] else 1
            self.done = True
            return
        if getattr(self, "hits", 0) >= MAX_HITS or len(self.points) >= MAX_POINTS:
            # the cap: the leader wins; if level, the winner of the last point (no draws)
            last = next((p["winner"] for p in reversed(self.points) if p["winner"]), "opponent")
            self.winner = (0 if self.score[0] > self.score[1] else 1 if self.score[1] > self.score[0]
                           else 0 if last == "you" else 1)
            self.points[-1]["cap"] = True
            self.done = True
            return
        self._start_point(hold_from=self.k)

    def replay(self, actions) -> None:
        for q in actions:
            self.step(q)

    # ------------------------------------------------------------------ live control
    def _target_vel(self):
        a = self.s._actions
        return (a[-1] - a[-2]) / CONTROL_DT if len(a) >= 2 and getattr(self, "_since_reset", 2) >= 2 else np.zeros(9)

    def _ready_target(self):
        """Service-driven recovery: the arm back to the ready pose (60 % of its speed limits), the base to its home
        (the point's spot in its service court, serve_spot)."""
        tgt = self.s.target
        lim = ARM_VEL * CONTROL_DT * 0.6
        arm = tgt[2:] + np.clip(Q0_ARM - tgt[2:], -lim, lim)
        b, _ = base_goto(tgt[:2], self._target_vel()[:2], self.home)
        return np.r_[b, arm]

    def _arm_target(self):
        if self.plan_j < len(self.plan):
            q = self.plan[self.plan_j]; self.plan_j += 1
            return q
        return self._ready_target()

    def decision_due(self) -> bool:
        leg = self.leg
        if self.done or leg["state"] != "incoming" or not self.in_play():
            return False
        if any(e["kind"] == "hit" for e in self.s.events):
            return False
        if self.phase == "swing":
            return self.k - leg["launch"] >= SWING_AFTER
        return self._adj_k is not None and self.k >= self._adj_k

    def run_to_decision(self) -> None:
        self.phase = "swing"
        while not self.done:
            if self.decision_due():
                return
            self.step(self._arm_target())

    def shot(self, decision: dict, delay_steps: int) -> dict:
        leg_i = self.n_our_legs
        rec = {"leg": leg_i, "decision": decision, "delay_steps": int(delay_steps), "k_decision": self.k}
        for _ in range(delay_steps):
            if self.leg["state"] != "incoming" or self.done:
                break
            self.step(self._arm_target())
        rec["k_exec"] = self.k
        self._adj_k = None
        if decision.get("type") == "swing" and self.leg["state"] == "incoming" and not self.done:
            self._ik_seed = None
            if "normal" in decision:
                self.plan, info = self.plan_racket(float(decision["t"]), decision["pos"], decision["normal"],
                                                   decision["vel"])
            else:
                self.plan, info = self.plan_stroke(float(decision["t"]), np.asarray(decision["pos"], float),
                                                   np.asarray(decision.get("aim", AIM_DEFAULT), float),
                                                   decision.get("power", "normal"))
            self.plan_j = 0
            rec.update(info)
            if self.plan and info.get("k_hit") is not None and info["k_hit"] - ADJUST_BEFORE >= self.k + 5:
                self._adj_k = info["k_hit"] - ADJUST_BEFORE
        self._rec = rec
        if decision.get("type") == "swing" and self._adj_k is not None:
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
            if "normal" in decision:
                plan, info = self.plan_racket(float(decision["t"]), decision["pos"], decision["normal"], decision["vel"])
            else:
                plan, info = self.plan_stroke(float(decision["t"]), np.asarray(decision["pos"], float),
                                              np.asarray(decision.get("aim", rec.get("aim", AIM_DEFAULT)), float),
                                              decision.get("power", rec.get("power", "normal")))
            q_hit = info.pop("_q_hit", None)
            rec["adjust_info"] = info
            if plan:
                rec["_q_hit"] = q_hit
                self.plan, self.plan_j = plan, 0
        return self._after_leg(rec, leg_i)

    # ------------------------------------------------------------------ real-time protocol (no decision points)
    def rt_advance(self, n_steps: int):
        """Run up to n_steps control steps with the current command (the planned stroke, then the return to ready);
        stops early when a point ends (the command is then dropped). Returns (steps run, points, our results)."""
        n0, r0, n = len(self.points), len(self.results), 0
        while n < n_steps and not self.done and len(self.points) == n0:
            self.step(self._arm_target()); n += 1
        if len(self.points) > n0:
            self.plan, self.plan_j = [], 0
            self._last_act = None
        return n, self.points[n0:], self.results[r0:]

    def rt_act(self, T, pos, nrm, vel) -> dict:
        """A new command: the racket state at contact T s from now, planned from the robot's current motion; it
        replaces the stroke under way (the hit configuration of the replaced stroke seeds the IK)."""
        t_hit = (self.k - self.leg["launch"]) * CONTROL_DT + float(T)
        self._ik_seed = getattr(self, "_q_hit_active", None) if self.plan_j < len(self.plan) else None
        plan, info = self.plan_racket(t_hit, pos, nrm, vel)
        q_hit = info.pop("_q_hit", None)
        info["T_from_now"] = round(float(T), 4)
        if plan:
            self.plan, self.plan_j = plan, 0
            self._q_hit_active = q_hit
        self.shots.append({"k": self.k, "leg": self.n_our_legs, **info})
        self._last_act = info
        return info

    def rt_clear(self):
        self.plan, self.plan_j = [], 0
        self._last_act = None

    def _after_leg(self, rec, leg_i) -> dict:
        n0 = len(self.points)
        while not self.done and self.n_our_legs == leg_i:
            self.step(self._arm_target())
        rec.pop("_q_hit", None)
        self.shots.append(rec)
        res = dict(self.results[leg_i]) if leg_i < len(self.results) else {"summary": "match over"}
        self.run_to_decision()
        res["points_finished"] = self.points[n0:]
        return res

    # ------------------------------------------------------------------ stroke controller
    def _twin_phys(self) -> Phys:
        if self._twin is None:
            self._twin = Phys()
            self._twin.reset(self.s.target)
        return self._twin

    def _base_plan(self, goal, n):
        """n base targets of the go-to generator from the current base target/velocity towards goal; and the step
        index at which it has arrived (None if not within n)."""
        b = self.s.target[:2].copy(); v = self._target_vel()[:2].copy()
        out, arrived = [], None
        for i in range(n):
            b, v = base_goto(b, v, goal)
            out.append(b.copy())
            if arrived is None and np.all(b == goal) and not v.any():
                arrived = i
        return out, arrived

    def _stroke_for(self, v_in, v_out, p_hit, bxy, seed):
        ph = self.s
        sp = float(np.linalg.norm(v_out)); nrm = v_out / sp
        vin_n = float(v_in @ nrm)
        u = max(0.05, (sp - E_SHUTTLE * max(0.0, -vin_n)) / RACKET_GAIN)
        v_p = u * nrm
        best = None
        for sgn in (1.0, -1.0):
            q_h, res = ik(ph, p_hit, sgn * nrm, bxy, seed)
            if best is None or res < best[1] - 1e-6:
                best = (q_h, res)
        q_h, res = best
        Jp = ph.jac(np.r_[bxy, q_h])[:3]
        Winv = np.diag(ARM_VEL ** 2)
        qd_h = Winv @ Jp.T @ np.linalg.solve(Jp @ Winv @ Jp.T + 1e-9 * np.eye(3), v_p)
        ratio = float(np.max(np.abs(qd_h) / ARM_VEL))
        return dict(nrm=nrm, v_p=v_p, q_h=q_h, qd_h=qd_h, ik=res, ratio=ratio, v_out=v_out, u=u,
                    p_hit=np.asarray(p_hit, float))

    def plan_stroke(self, t_hit, p_hit, aim, power="normal"):
        """Swing so that the racket-head centre meets a shuttle centred at p_hit at t_hit (s after it was played)
        and sends it towards aim. Base: the go-to generator to the forehand stance for p_hit (or as far as it gets
        0.05 s before the contact). Shot: the launch velocities that land at aim and clear the net (one per launch
        angle, the controller's own flight model); power: soft = the slowest, hard = the fastest the arm can swing,
        normal = the least demanding for the arm. Face normal = the launch direction, head speed from the racket
        model; IK + a speed-weighted Jacobian inverse give the hit configuration; a cubic swing and follow-through,
        refined by robot-only rehearsals on a twin; then up to 4 full rehearsals (arm and the real shuttle) correct
        the aim by the rehearsed landing error. A wrong contact misses in the rehearsal too and is not corrected."""
        power = power if power in POWER else "normal"
        info = {"t_hit": t_hit, "p_hit": [float(x) for x in p_hit], "aim": [float(x) for x in aim], "power": power}
        k_hit = self.leg["launch"] + int(round(t_hit / CONTROL_DT))
        n_avail = k_hit - self.k
        info["n_swing_steps_available"] = int(n_avail)
        info["k_hit"] = None
        if n_avail < 3:
            info["stroke"] = "too late: the contact time has already passed"
            return [], info
        info["k_hit"] = int(k_hit)
        # base: stance, or as far as it gets
        st = stance(p_hit)
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
            info["base"] = f"could not reach the stance in time: {float(np.linalg.norm(st - goal)):.2f} m short"
        else:
            info["base"] = "ok"
        info["base_goal"] = [round(float(x), 3) for x in goal]
        base_tg, _ = self._base_plan(goal, n_avail + 40)
        # incoming shuttle at the contact (the controller's forward model from the true current state)
        P, V = predict(self.s.sh_p, self.s.sh_v, n_max=int(n_avail * SUBSTEPS))
        v_in = V[-1] if len(V) else np.zeros(3)
        rng = np.random.default_rng([self.lv["seed"], 7, self.n_our_legs])
        aim_n = np.asarray(aim, float) + rng.normal(0.0, EXEC_SIGMA[power], 2)
        aim_eff = aim_n.copy()
        seed = getattr(self, "_ik_seed", None)
        seed = Q0_ARM if seed is None else seed
        best = None
        for it in range(4):
            cands = solve_shots(p_hit, aim_eff, OUR_THETAS, OUR_VMAX, net_margin=0.08)
            if not cands:
                info["stroke"] = "no shot from this contact point reaches the aim over the net"
                if best is None:
                    cands = solve_shots(p_hit, (0.0, 4.0), OUR_THETAS, OUR_VMAX, net_margin=0.08)
                    if not cands:
                        return [], info
                else:
                    break
            strokes = [self._stroke_for(v_in, c[2], p_hit, goal, seed) for c in cands]
            c = self._pick_stroke(strokes, power)
            tg, sinfo = self._swing(c, goal, base_tg, n_avail)
            L, spd = self._rehearse(tg)
            err = None if L is None else float(np.linalg.norm(np.asarray(L) - aim_n))
            if best is None or (err is not None and (best[2] is None or err < best[2])):
                best = (tg, sinfo, err, L, spd, c)
            if L is None or err < 0.08:
                break
            aim_eff = aim_eff + (aim_n - np.asarray(L))
        tg, sinfo, err, L, spd, c = best
        info.update(sinfo)
        info["_q_hit"] = c["q_h"]
        info["rehearsal_landing"] = None if L is None else [round(float(x), 3) for x in L]
        info["rehearsal_speed"] = None if spd is None else round(float(spd), 2)
        info.setdefault("stroke", "ok" if L is not None else "the rehearsal missed the shuttle")
        return tg, info

    RACKET_SCATTER = dict(pos=0.006, ang_deg=0.8, speed=0.03)   # execution scatter of the racket state at contact

    def plan_racket(self, t_hit, p_c, nrm, v_p):
        """Racket-level decision: the player gives the racket state at contact (time t_hit s after the shuttle was
        played, head centre p_c, string-face normal nrm, head velocity v_p). The controller only makes the robot
        deliver it: the base to the forehand stance for p_c (or as far as it gets), IK, a speed-weighted Jacobian
        inverse, a joint-speed-limited cubic swing and robot-only rehearsals that correct the PD lag. It uses no
        shuttle state and does not aim. The delivered state scatters (seeded, RACKET_SCATTER)."""
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
        rng = np.random.default_rng([self.lv["seed"], 13, self.n_our_legs])
        sc = self.RACKET_SCATTER
        p_c = p_c + rng.normal(0.0, sc["pos"], 3)
        axis = np.cross(nrm, rng.normal(0.0, 1.0, 3)); axis /= np.linalg.norm(axis)
        ang = np.radians(rng.normal(0.0, sc["ang_deg"]))
        nrm = nrm * np.cos(ang) + np.cross(axis, nrm) * np.sin(ang); nrm /= np.linalg.norm(nrm)
        v_p = v_p * (1.0 + rng.normal(0.0, sc["speed"]))
        st = stance(p_c)
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
            info["base"] = f"could not reach the stance in time: {float(np.linalg.norm(st - goal)):.2f} m short"
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
        for q_h, res, _ in [(q_h, res, sgn)] + alts:
            Jp = ph.jac(np.r_[goal, q_h])[:3]
            qd_h = Winv @ Jp.T @ np.linalg.solve(Jp @ Winv @ Jp.T + 1e-9 * np.eye(3), v_p)
            ratio = float(np.max(np.abs(qd_h) / ARM_VEL))
            c = dict(nrm=nrm, v_p=v_p, q_h=q_h, qd_h=qd_h, ik=res, ratio=ratio, v_out=np.zeros(3), p_hit=p_c)
            tg, sinfo = self._swing(c, goal, base_tg, n_avail)
            sc = swing_score(sinfo["blade_error_m"], sinfo["normal_error_deg"],
                             np.linalg.norm(self._swing_last[2] - v_p / sinfo["speed_scale"]))
            if tried is None or sc < tried[0]:
                tried = (sc, tg, sinfo, self._swing_last, q_h, res)
            if sinfo["blade_error_m"] <= DELIVERY_POS_WARN and sinfo["normal_error_deg"] <= DELIVERY_ANG_WARN:
                break                                 # delivered: the nearest solution that works
        _, tg, sinfo, self._swing_last, q_h, res = tried
        for k in ("shot_speed_plan", "launch_dir", "head_speed_plan"):
            sinfo.pop(k, None)
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

    @staticmethod
    def _pick_stroke(strokes, power):
        good = ([c for c in strokes if c["ik"] < 2e-3 and c["ratio"] <= 1.0] or [c for c in strokes if c["ik"] < 2e-3]
                or strokes)
        if power == "normal":
            return min(good, key=lambda c: c["ratio"])
        sp = sorted(good, key=lambda c: float(np.linalg.norm(c["v_out"])))
        return sp[-1] if power == "hard" else sp[0]

    def _swing(self, c, goal, base_tg, n_avail):
        """Arm swing (cubic to the hit configuration, follow-through) + base plan; 5 robot-only twin rehearsals
        correct the hit configuration/velocity for the PD lag, and the best of them (swing_score) is kept."""
        ph = self.s
        scale = max(1.0, c["ratio"] / 0.9)
        q_h, qd_h = c["q_h"].copy(), c["qd_h"] / scale
        v_p = c["v_p"] / scale
        q_s = ph.target[2:].copy(); v_s = self._target_vel()[2:]
        n_sw = int(n_avail)
        if np.max(np.abs(v_s)) < 1e-6:
            for n in range(25, int(n_avail) + 1):
                sw = hermite(q_s, np.zeros(7), q_h, qd_h, n * CONTROL_DT, n)
                if np.max(np.abs(np.diff(np.vstack([q_s, sw]), axis=0)) / (ARM_VEL * CONTROL_DT)) <= 0.97:
                    n_sw = n
                    break
        n_sw = int(min(n_sw, n_avail))
        Winv = np.diag(ARM_VEL ** 2)
        q_goal, qd_goal = q_h.copy(), qd_h.copy()
        best = None
        for it in range(5):
            tg = self._swing_targets(q_goal, qd_goal, n_avail, n_sw, base_tg)
            p, n_act, v_act = self._simulate_arm(tg, n_avail)
            sg = 1.0 if n_act @ c["nrm"] >= 0 else -1.0
            perr = float(np.linalg.norm(p - c["p_hit"]))
            nerr = float(np.degrees(np.arccos(np.clip(abs(float(n_act @ c["nrm"])), 0.0, 1.0))))
            sc = swing_score(perr, nerr, np.linalg.norm(v_act - v_p))
            if best is None or sc < best[0]:          # keep the best of the correction passes, not the last one
                best = (sc, tg, (p, n_act, v_act), perr, nerr)
            if it == 4:
                break
            J = ph.jac(np.r_[goal, q_goal])
            e = np.r_[c["p_hit"] - p, np.cross(n_act, sg * c["nrm"])]
            q_goal = np.clip(q_goal + J.T @ np.linalg.solve(J @ J.T + 1e-4 * np.eye(6), e),
                             ph.lo[2:] + 1e-4, ph.hi[2:] - 1e-4)
            Jp = J[:3]
            qd_goal = qd_goal + Winv @ Jp.T @ np.linalg.solve(Jp @ Winv @ Jp.T + 1e-9 * np.eye(3), v_p - v_act) * 0.7
            qd_goal = qd_goal / max(1.0, float(np.max(np.abs(qd_goal) / ARM_VEL)))
        _, tg, self._swing_last, perr, nerr = best
        info = {"ik_residual": round(float(c["ik"]), 5), "speed_scale": round(scale, 3), "n_swing_steps": n_sw,
                "blade_error_m": round(perr, 4), "normal_error_deg": round(nerr, 2),
                "head_speed_plan": round(float(np.linalg.norm(v_p)), 2),
                "shot_speed_plan": round(float(np.linalg.norm(c["v_out"]) / scale), 2),
                "launch_dir": [round(float(x), 3) for x in c["nrm"]]}
        info["stroke"] = "ok" if n_sw >= 20 else "short swing (little time left: slow racket)"
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

    def _simulate_arm(self, targets, n):
        """Robot-only twin rollout from the live robot state: racket (pos, normal, velocity) after n steps."""
        tw = self._twin_phys()
        tw.copy_from(self.s)
        tw.sh_live = False; tw.hit_enabled = False
        for j in range(n):
            tw.step(targets[j])
        mj.mj_forward(tw.m, tw.d)
        return tw.racket_state()

    def _rehearse(self, targets):
        """Full twin rehearsal (robot and the real shuttle): landing xy of our shot (shuttle-only prediction after
        the hit) and its speed off the racket; (None, None) if the racket never meets the shuttle."""
        tw = self._twin_phys()
        tw.copy_from(self.s)
        for j in range(len(targets) + 30):
            tw.step(targets[j] if j < len(targets) else targets[-1])
            h = [e for e in tw.events if e["kind"] == "hit"]
            if h:
                P, _ = predict(tw.sh_p, tw.sh_v)
                return (P[-1][:2].tolist() if len(P) else list(tw.sh_p[:2])), h[0]["speed"]
            if not tw.sh_live:
                break
        return None, None

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
        rd.mocap_pos[0] = sn["sh"]
        v = np.asarray(sn["shv"], float)
        if np.linalg.norm(v) < 1e-6:
            v = np.array([0.0, 0.0, -1.0])
        rd.mocap_quat[0] = quat_z_to(v)
        mj.mj_kinematics(self.s.m, rd)

    @staticmethod
    def _extra_geoms(scn, opp_xy, sh=None):
        def add(typ, size, pos, rgba, mat=np.eye(3)):
            if scn.ngeom >= scn.maxgeom:
                return
            mj.mjv_initGeom(scn.geoms[scn.ngeom], typ, np.asarray(size, float), np.asarray(pos, float),
                            np.asarray(mat, float).ravel(), np.asarray(rgba, np.float32))
            scn.ngeom += 1
        ox, oy = float(opp_xy[0]), float(opp_xy[1])
        add(mj.mjtGeom.mjGEOM_CAPSULE, [0.16, 0.55, 0], [ox, oy, 0.75], [0.35, 0.35, 0.42, 1])
        add(mj.mjtGeom.mjGEOM_SPHERE, [0.12, 0, 0], [ox, oy, 1.55], [0.85, 0.7, 0.6, 1])
        # the opponent's racket: red head, reaching towards the shuttle when it is near
        rp = np.array([ox + 0.45, oy - 0.1, 1.9])
        if sh is not None:
            d = np.array(sh) - np.array([ox, oy, 1.2])
            if np.linalg.norm(d) < 1.6:
                rp = np.array([ox, oy, 1.2]) + d / max(1e-6, np.linalg.norm(d)) * min(1.2, np.linalg.norm(d))
        add(mj.mjtGeom.mjGEOM_ELLIPSOID, [0.10, 0.02, 0.13], rp, [0.9, 0.1, 0.1, 1])

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
        """PNG: 2 rows (behind camera, side camera) x 4 columns (snapshots 60 ms apart, oldest left), each tile
        stamped with its time since the shuttle was played."""
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
                self._extra_geoms(r.scene, sn["opp"], sn["sh"])
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
        heard = []
        if leg["kind"] == "serve":
            heard.append({"event": "the opponent served", "t": 0.0})
        else:
            heard.append({"event": "the opponent hit the shuttle", "t": 0.0})
        c, n, _ = ph.racket_state()
        return {"score": {"you": self.score[0], "opponent": self.score[1]}, "point": len(self.points) + 1,
                "ball": "serve" if leg["kind"] == "serve" else "opponent's return",
                "t_since_played": self.t_since_launch(), "heard": heard, "view_times": self.view_times(),
                "robot_base_xy": [round(float(x), 3) for x in ph.d.qpos[ph.qa[:2]]],
                "q_arm": [round(float(x), 4) for x in ph.d.qpos[ph.qa[2:]]],
                "racket_pos": [round(float(x), 3) for x in c], "racket_normal": [round(float(x), 3) for x in n]}


def _ready_pose():
    """Ready pose: racket head up in front of the robot's right shoulder, face towards the net."""
    global Q0_ARM
    ph = Phys(); ph.reset(np.r_[HOME, Q0_ARM])
    q, err = ik(ph, np.r_[HOME + np.array([0.35, 0.45]), SHOULDER_Z + 0.45], np.array([0.0, 1.0, 0.25]), HOME,
                np.array([0.0, -0.2, 0.0, -1.6, 0.0, 1.6, 0.785]), iters=400)
    Q0_ARM = np.round(q, 4)


_ready_pose()


def render_video(actions, level, out, fps=25, every=2):
    """Replay video: the two decision cameras side by side, 2x slow motion (every `every` control steps at 25 fps),
    3x fewer frames while no shuttle is in play."""
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
        live = mt.s.sh_live
        if k % (every if live else 3 * every):
            continue
        sn = {"qpos": mt.s.d.qpos.copy(), "sh": mt.s.sh_p, "shv": mt.s.sh_v}
        mt._set_render_state(rd, sn)
        imgs = []
        for c in cams:
            r.update_scene(rd, camera=c)
            mt._extra_geoms(r.scene, mt.opp_xy(), mt.s.sh_p)
            imgs.append(r.render())
        im = Image.fromarray(np.concatenate(imgs, axis=1))
        ImageDraw.Draw(im).text((8, 6), f"robot {mt.score[0]} : {mt.score[1]} opponent   (level {level})",
                                fill=(255, 255, 255))
        w.append_data(np.asarray(im))
    w.close(); r.close()
