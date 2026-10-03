"""Core of the robot baseball batting service: 5 plate appearances against a scripted pitcher (the duel's batting rules).

World (metres, seconds): ground z = 0; home plate centred at the origin, +y towards the pitcher and centre field,
+x towards first base (the catcher's right), z up. Home plate is 0.432 m wide (|x| <= 0.216, |y| <= 0.216). The
pitcher releases the ball at REL = (-0.50, 16.80, 1.80) (a right-hander, 16.8 m in front of the plate). Foul lines
run from home at +-45 deg from the +y axis; the fence is the arc at 100 m from home, 3 m high.

Ball (not a MuJoCo body; integrated here with RK4 in pure Python floats, deterministic):
  a = g - K_D |v| v + K_L0 C_L(S) |v| (w_hat x v),   K_D = rho C_D A / (2 m), K_L0 = rho A / (2 m)
  m = 0.145 kg, R = 0.0365 m (7.3 cm), rho = 1.19 kg/m^3 [assumed], C_D = 0.35 [assumed, the order of the values in
  Nathan 2008], spin factor S = R |w| / |v|, C_L(S) = 1.5 S (S < 0.1), 0.09 + 0.6 S (S >= 0.1) (the bilinear fit of
  Sawicki, Hubbard & Stronge 2003, which Nathan 2008, Am. J. Phys. 76, 119, compares with his measurements).
  Spin decays as exp(-t / 30 s) [assumed].

Batter: a kinematic 4-parameter swing rig (not a Franka: a pro swing moves the barrel at ~30 m/s, 10x what a Franka
can). The bat (0.84 m, 0.90 kg, rigid, round) rotates about its knob, the pivot P = (-0.66 + REACH, 0.25, HEIGHT).
Its axis direction is u(theta) = cos(theta) x + sin(theta) e2, e2 = (0, cos a, sin a) with a = PLANE_DEG (the swing
plane / attack angle); theta = 0 is "square" (the bat along +x over the plate, moving towards the pitcher and, for
a > 0, upwards). Angle profile from the swing start T: theta = -180 deg at rest, constant angular acceleration to
omega = SPEED / 0.69 at -30 deg, constant omega to +90 deg, then a deceleration to rest at +150 deg. SPEED is the
speed of the sweet spot (0.69 m from the knob). The rig never uses the ball state.

Bat-ball collision (a model, after Nathan 2000, Am. J. Phys. 68, 979; not MuJoCo contact): continuous detection
(50 us substeps + bisection) of the ball touching the bat surface (radius profile below); at contact an impulse along
the contact normal n with a location-dependent COR e(s) = max(0.10, 0.50 - 4.0 (s - 0.69)^2) and the free-bat
effective mass 1/M_eff = 1/M + (s - s_cm)^2 / I_cm (s_cm = 0.56 m, I_cm = 0.048 kg m^2 [assumed wood-bat values]);
a tangential friction impulse (mu = 0.5 [assumed]) capped at the rolling condition changes the spin.

Batted ball: the same flight model; on the ground it bounces (vertical COR 0.5, horizontal 0.75 kept [assumed]) and
then rolls (2.5 m/s^2 [assumed]). Fair iff the first landing point is in front of home within the foul lines (or it
leaves over the fence between them). Fielders (FIELDERS) are fixed; a fielder reaches a point at distance r0 +
v_run max(0, t - t_react) at time t after contact, for a ball at most 2.4 m high. The earliest reach decides:
caught in the air = out; a ground ball fielded by an infielder = out if fielding time + 0.6 s + throw (30 m/s) to
first base <= 4.3 s (the runner), else an infield single; fielded by an outfielder = single, or double when it
landed beyond 80 m or was fielded after 5 s. Over the fence (>= 3 m high at 100 m) = home run; off the wall = double.

Count, PA and scoring: 3 strikes = strikeout, 4 balls = walk, fouls are strikes except with 2 strikes (never
caught). Strike zone: the ball's centre crossing the plane y = 0 with |x| <= 0.216 + R and 0.46 - R <= z <= 1.07 + R.
Score = bases: walk 1, single 1, double 2, home run 4 (no triples in this model).
"""
from __future__ import annotations

import hashlib
import io
import json
import math
import os
import sys

import numpy as np

# ------------------------------------------------------------------ physics constants
G = 9.81
RHO = 1.19                      # air density, kg/m^3 [assumed: 25 C, sea level]
M_BALL, R_BALL = 0.145, 0.0365  # regulation baseball: 142-149 g, 22.9-23.5 cm circumference
AREA = math.pi * R_BALL ** 2
CD = 0.35                       # [assumed] drag coefficient
K_D = 0.5 * RHO * CD * AREA / M_BALL
K_L0 = 0.5 * RHO * AREA / M_BALL
SPIN_TAU = 30.0                 # [assumed] spin decay time, s
I_BALL = 0.4 * M_BALL * R_BALL ** 2

# bat and swing rig
L_BAT, M_BAT, S_CM, I_CM, S_SS = 0.84, 0.90, 0.56, 0.048, 0.69
E0, E_K, E_MIN, MU = 0.50, 4.0, 0.10, 0.5
PIVOT_X0, PIVOT_Y = -0.66, 0.25
TH0, TH1, TH2, TH3 = -math.pi, -math.pi / 6, math.pi / 2, 5 * math.pi / 6

# field
REL = (-0.50, 16.80, 1.80)
FENCE_R, FENCE_H = 100.0, 3.0
ZONE_X, ZONE_LO, ZONE_HI = 0.216, 0.46, 1.07
BASE_PATH = 27.43               # MLB Official Baseball Rules 2.01: the bases are 90 ft apart
B1 = (BASE_PATH * math.sin(math.radians(45)), BASE_PATH * math.cos(math.radians(45)))   # first base
RUNNER_TO_1B, THROW_V, TRANSFER = 4.3, 30.0, 0.6
REACH_H = 2.4
# name, distance from home, azimuth (deg, + = towards left field / -x), r0, v_run, t_react, infielder
FIELDERS = [("P", 18.0, 0.0, 1.0, 5.0, 0.35, True), ("C", -1.0, 0.0, 0.8, 5.0, 0.5, True),
            ("1B", 28.0, -38.0, 1.5, 6.0, 0.2, True), ("2B", 42.0, -15.0, 1.5, 6.0, 0.2, True),
            ("SS", 42.0, 15.0, 1.5, 6.0, 0.2, True), ("3B", 28.0, 38.0, 1.5, 6.0, 0.2, True),
            ("LF", 84.0, 30.0, 1.5, 7.0, 0.4, False), ("CF", 94.0, 0.0, 1.5, 7.0, 0.4, False),
            ("RF", 84.0, -30.0, 1.5, 7.0, 0.4, False)]


def fielder_xy(d, az):
    return (-d * math.sin(math.radians(az)), d * math.cos(math.radians(az)))


FIELDER_POS = {f[0]: fielder_xy(f[1], f[2]) for f in FIELDERS}

T_DECISION = 0.10              # the decision point: 0.10 s after release
VIEW_TIMES = (0.01, 0.04, 0.07, 0.10)
PA_MAX_PITCHES = 15            # a plate appearance reaching this many pitches is an out (the duel's limit)

PITCH_TYPES = {
    # spin rad/s, spin axis (for a ball moving along -y): backspin + arm-side tilt; curveball: topspin + glove side
    "fastball": dict(spin=230.0, axis=(-0.866, 0.0, -0.5)),
    "changeup": dict(spin=178.0, axis=(-0.707, 0.0, -0.707)),
    "curveball": dict(spin=262.0, axis=(0.866, 0.0, 0.5)),
    # slider: partly gyro spin (along the flight, no Magnus); the rest breaks it to the glove side (+x), a little down
    "slider": dict(spin=250.0, axis=(0.25, -0.60, 0.76)),
}
LEVELS = {
    1: dict(seed=301, n_pa=5, mix={"fastball": 1.0}, mix_2k=None, speeds={"fastball": (34.0, 36.0)},
            p_zone=0.85, p_zone_2k=0.85, p_zone_3b=0.95, threshold=4),
    2: dict(seed=302, n_pa=5, mix={"fastball": 0.5, "changeup": 0.25, "curveball": 0.25},
            mix_2k={"fastball": 0.4, "changeup": 0.25, "curveball": 0.35},
            speeds={"fastball": (35.0, 37.0), "changeup": (29.0, 31.0), "curveball": (28.0, 30.0)},
            p_zone=0.62, p_zone_2k=0.45, p_zone_3b=0.80, threshold=4),
    # L3: sliders, faster fastballs, slider / changeup speeds touching, 60 % of the strikes on the zone edges (mostly inside
    # and low, where the bat's sweet spot cannot reach), balls just off
    3: dict(seed=303, n_pa=5, mix={"fastball": 0.45, "slider": 0.25, "changeup": 0.15, "curveball": 0.15},
            mix_2k={"fastball": 0.30, "slider": 0.35, "changeup": 0.15, "curveball": 0.20},
            speeds={"fastball": (38.0, 40.0), "slider": (33.5, 35.5), "changeup": (31.5, 33.5), "curveball": (29.0, 31.0)},
            p_zone=0.70, p_zone_2k=0.55, p_zone_3b=0.90, edge=0.6, edge_sides=(0.4, 0.2, 0.3, 0.1), out_margin=(0.02, 0.10),
            threshold=4),
    # L4: full mix sequenced by the count (ahead: breaking balls off the zone; behind: fastballs in it), top velocity,
    # overlapping speed bands (slider / changeup / curveball are hard to tell apart by speed)
    4: dict(seed=304, n_pa=5, mix={"fastball": 0.40, "slider": 0.25, "changeup": 0.20, "curveball": 0.15},
            mix_ahead={"fastball": 0.25, "slider": 0.35, "changeup": 0.15, "curveball": 0.25},
            mix_behind={"fastball": 0.60, "slider": 0.15, "changeup": 0.20, "curveball": 0.05},
            speeds={"fastball": (40.0, 42.0), "slider": (35.0, 37.5), "changeup": (33.5, 35.5), "curveball": (31.0, 33.5)},
            p_zone=0.72, p_zone_ahead=0.55, p_zone_behind=0.85, p_zone_3b=0.95, edge=0.8, edge_sides=(0.5, 0.15, 0.3, 0.05),
            out_margin=(0.015, 0.07),
            threshold=4),
}
SCATTER = dict(t_ms=3.0, plane_deg=1.0, height_m=0.008, speed_frac=0.015, reach_m=0.008)


# ------------------------------------------------------------------ flight
def c_lift(S):
    return 1.5 * S if S < 0.1 else 0.09 + 0.6 * S


def acc(vx, vy, vz, wx, wy, wz):
    sp = math.sqrt(vx * vx + vy * vy + vz * vz)
    ax, ay, az = -K_D * sp * vx, -K_D * sp * vy, -G - K_D * sp * vz
    wm = math.sqrt(wx * wx + wy * wy + wz * wz)
    if wm > 0.0 and sp > 0.0:
        k = K_L0 * c_lift(R_BALL * wm / sp) * sp / wm
        ax += k * (wy * vz - wz * vy)
        ay += k * (wz * vx - wx * vz)
        az += k * (wx * vy - wy * vx)
    return ax, ay, az


def rk4(s, h):
    """s = (x, y, z, vx, vy, vz, wx, wy, wz); one RK4 step of h seconds (spin held, then decayed)."""
    x, y, z, vx, vy, vz, wx, wy, wz = s
    a1 = acc(vx, vy, vz, wx, wy, wz)
    v2 = (vx + 0.5 * h * a1[0], vy + 0.5 * h * a1[1], vz + 0.5 * h * a1[2])
    a2 = acc(*v2, wx, wy, wz)
    v3 = (vx + 0.5 * h * a2[0], vy + 0.5 * h * a2[1], vz + 0.5 * h * a2[2])
    a3 = acc(*v3, wx, wy, wz)
    v4 = (vx + h * a3[0], vy + h * a3[1], vz + h * a3[2])
    a4 = acc(*v4, wx, wy, wz)
    h6 = h / 6.0
    d = math.exp(-h / SPIN_TAU)
    return (x + h6 * (vx + 2 * v2[0] + 2 * v3[0] + v4[0]), y + h6 * (vy + 2 * v2[1] + 2 * v3[1] + v4[1]),
            z + h6 * (vz + 2 * v2[2] + 2 * v3[2] + v4[2]),
            vx + h6 * (a1[0] + 2 * a2[0] + 2 * a3[0] + a4[0]), vy + h6 * (a1[1] + 2 * a2[1] + 2 * a3[1] + a4[1]),
            vz + h6 * (a1[2] + 2 * a2[2] + 2 * a3[2] + a4[2]), wx * d, wy * d, wz * d)


def fly_to_plane(s, y_stop, dt=0.001, t_max=2.0):
    """Integrate until the ball's y drops below y_stop; returns (t, x, z) at the crossing (linear interpolation)."""
    t = 0.0
    while t < t_max:
        n = rk4(s, dt)
        if n[1] <= y_stop:
            f = (s[1] - y_stop) / (s[1] - n[1])
            return t + f * dt, s[0] + f * (n[0] - s[0]), s[2] + f * (n[2] - s[2])
        s, t = n, t + dt
    return None


def launch_state(speed, el, az, spin, axis):
    v = (speed * math.cos(el) * math.sin(az), -speed * math.cos(el) * math.cos(az), speed * math.sin(el))
    return (REL[0], REL[1], REL[2], v[0], v[1], v[2], spin * axis[0], spin * axis[1], spin * axis[2])


def aim_pitch(speed, spin, axis, xt, zt):
    """The pitcher's aim: Newton on (elevation, azimuth) so that the ball's centre crosses y = 0 at (xt, zt)."""
    dy = REL[1]
    tf = dy / speed
    el = math.atan2(zt - REL[2] + 0.5 * G * tf * tf, dy)
    az = math.atan2(xt - REL[0], dy)
    for _ in range(8):
        c = fly_to_plane(launch_state(speed, el, az, spin, axis), 0.0)
        ex, ez = c[1] - xt, c[2] - zt
        if abs(ex) < 2e-4 and abs(ez) < 2e-4:
            break
        e = 1e-4
        c1 = fly_to_plane(launch_state(speed, el + e, az, spin, axis), 0.0)
        c2 = fly_to_plane(launch_state(speed, el, az + e, spin, axis), 0.0)
        j11, j21 = (c1[1] - c[1]) / e, (c1[2] - c[2]) / e
        j12, j22 = (c2[1] - c[1]) / e, (c2[2] - c[2]) / e
        det = j11 * j22 - j12 * j21
        del_el = (j22 * ex - j12 * ez) / det
        del_az = (-j21 * ex + j11 * ez) / det
        el -= del_el
        az -= del_az
    return el, az


def in_zone(x, z):
    return abs(x) <= ZONE_X + R_BALL and ZONE_LO - R_BALL <= z <= ZONE_HI + R_BALL


# ------------------------------------------------------------------ swing rig
def bat_radius(s):
    if s < 0.02:
        return 0.025       # knob
    if s < 0.40:
        return 0.0125      # handle
    if s < 0.60:
        return 0.0125 + (s - 0.40) / 0.20 * (0.033 - 0.0125)
    return 0.033           # barrel


def cor(s):
    return max(E_MIN, E0 - E_K * (s - S_SS) ** 2)


class Swing:
    """Kinematic swing: start time t0 (s after release), plane angle a (rad), pivot height H, sweet-spot speed,
    reach (pivot x offset)."""

    def __init__(self, t0, plane_deg, height, speed, reach):
        self.t0, self.plane_deg, self.H, self.speed, self.reach = t0, plane_deg, height, speed, reach
        a = math.radians(plane_deg)
        self.ca, self.sa = math.cos(a), math.sin(a)
        self.px, self.py = PIVOT_X0 + reach, PIVOT_Y
        self.w = speed / S_SS
        self.acc1 = self.w ** 2 / (2 * (TH1 - TH0))
        self.tau1 = 2 * (TH1 - TH0) / self.w
        self.tau2 = self.tau1 + (TH2 - TH1) / self.w
        self.dec = self.w ** 2 / (2 * (TH3 - TH2))
        self.tau3 = self.tau2 + 2 * (TH3 - TH2) / self.w

    def angle(self, t):
        tau = t - self.t0
        if tau <= 0:
            return TH0, 0.0
        if tau <= self.tau1:
            return TH0 + 0.5 * self.acc1 * tau * tau, self.acc1 * tau
        if tau <= self.tau2:
            return TH1 + self.w * (tau - self.tau1), self.w
        if tau <= self.tau3:
            d = tau - self.tau2
            return TH2 + self.w * d - 0.5 * self.dec * d * d, self.w - self.dec * d
        return TH3, 0.0

    def time_to(self, theta):
        """Seconds from the swing start until the bat reaches angle theta (published formula)."""
        if theta <= TH1:
            return math.sqrt(2 * (theta - TH0) / self.acc1)
        return self.tau1 + (theta - TH1) / self.w

    def axis(self, th):
        c, s = math.cos(th), math.sin(th)
        return (c, s * self.ca, s * self.sa)

    def normal(self):
        return (0.0, -self.sa, self.ca)

    def gap(self, t, p):
        """Distance between the ball surface and the bat surface (< 0 = touching) and the closest axis point."""
        th, _ = self.angle(t)
        u = self.axis(th)
        dx, dy, dz = p[0] - self.px, p[1] - self.py, p[2] - self.H
        s = dx * u[0] + dy * u[1] + dz * u[2]
        s = min(max(s, 0.0), L_BAT)
        q = (self.px + s * u[0], self.py + s * u[1], self.H + s * u[2])
        dist = math.sqrt((p[0] - q[0]) ** 2 + (p[1] - q[1]) ** 2 + (p[2] - q[2]) ** 2)
        return dist - (R_BALL + bat_radius(s)), s, q, th


def cross(a, b):
    return (a[1] * b[2] - a[2] * b[1], a[2] * b[0] - a[0] * b[2], a[0] * b[1] - a[1] * b[0])


def dot(a, b):
    return a[0] * b[0] + a[1] * b[1] + a[2] * b[2]


def collide(sw, t, st):
    """Impulse at contact. st = ball state at the contact time. Returns the new state and contact info, or None when
    the surfaces are separating."""
    p, v, w = st[0:3], st[3:6], st[6:9]
    g, s, q, th = sw.gap(t, p)
    d = (p[0] - q[0], p[1] - q[1], p[2] - q[2])
    dn = math.sqrt(dot(d, d))
    n = (d[0] / dn, d[1] / dn, d[2] / dn)
    rho = bat_radius(s)
    _, thd = sw.angle(t)
    ns = sw.normal()
    cb = (q[0] + rho * n[0] - sw.px, q[1] + rho * n[1] - sw.py, q[2] + rho * n[2] - sw.H)
    vb = cross((thd * ns[0], thd * ns[1], thd * ns[2]), cb)
    rc = (-R_BALL * n[0], -R_BALL * n[1], -R_BALL * n[2])
    wr = cross(w, rc)
    vc = (v[0] + wr[0], v[1] + wr[1], v[2] + wr[2])
    vr = (vc[0] - vb[0], vc[1] - vb[1], vc[2] - vb[2])
    vn = dot(vr, n)
    if vn >= 0.0:
        return None
    e = cor(s)
    inv_bat = 1.0 / M_BAT + (s - S_CM) ** 2 / I_CM
    jn = -(1.0 + e) * vn / (1.0 / M_BALL + inv_bat)
    vt = (vr[0] - vn * n[0], vr[1] - vn * n[1], vr[2] - vn * n[2])
    vtm = math.sqrt(dot(vt, vt))
    J = (jn * n[0], jn * n[1], jn * n[2])
    if vtm > 1e-9:
        j_roll = vtm / (1.0 / M_BALL + R_BALL ** 2 / I_BALL + inv_bat)
        jt = min(MU * jn, j_roll)
        J = (J[0] - jt * vt[0] / vtm, J[1] - jt * vt[1] / vtm, J[2] - jt * vt[2] / vtm)
    nv = (v[0] + J[0] / M_BALL, v[1] + J[1] / M_BALL, v[2] + J[2] / M_BALL)
    tq = cross(rc, J)
    nw = (w[0] + tq[0] / I_BALL, w[1] + tq[1] / I_BALL, w[2] + tq[2] / I_BALL)
    info = {"t": t, "s": s, "theta_deg": math.degrees(th), "cor": e, "bat_speed": math.sqrt(dot(vb, vb)),
            "offset": dot(d, sw.normal()), "pos": list(p)}
    return (p[0], p[1], p[2], nv[0], nv[1], nv[2], nw[0], nw[1], nw[2]), info


# ------------------------------------------------------------------ batted ball
def azimuth(x, y):
    """deg from the +y axis, + towards left field (-x)."""
    return math.degrees(math.atan2(-x, y))


def batted_flight(st, dt=0.002, t_max=12.0):
    """Flight + ground phase. Returns samples [(t, x, y, z, airborne)], landing point, flags."""
    samples = [(0.0, st[0], st[1], st[2], True)]
    t, s = 0.0, st
    landed = None
    hr = wall = False
    airborne = True
    rolling = None
    k = 0
    while t < t_max:
        if rolling is None:
            n = rk4(s, dt)
            t += dt
            d = math.hypot(n[0], n[1])
            if landed is None and d >= FENCE_R and n[1] > 0:
                if n[2] > FENCE_H:
                    hr = True
                    samples.append((t, n[0], n[1], n[2], True))
                    break
                wall = True
                samples.append((t, n[0], n[1], n[2], airborne))
                break
            if d >= FENCE_R and landed is not None:
                wall = True
                samples.append((t, n[0], n[1], n[2], False))
                break
            if n[2] <= R_BALL and n[5] < 0:
                if landed is None:
                    landed = (t, n[0], n[1])
                airborne = False
                vz = -0.5 * n[5]
                vx, vy = 0.75 * n[3], 0.75 * n[4]
                if vz < 1.0:
                    rolling = [n[0], n[1], vx, vy]
                    s = (n[0], n[1], R_BALL, vx, vy, 0.0, 0.0, 0.0, 0.0)
                else:
                    s = (n[0], n[1], R_BALL, vx, vy, vz, 0.0, 0.0, 0.0)
            else:
                s = n
        else:
            x, y, vx, vy = rolling
            sp = math.hypot(vx, vy)
            if sp < 0.05:
                samples.append((t, x, y, R_BALL, False))
                break
            nsp = max(0.0, sp - 2.5 * dt)
            vx, vy = vx * nsp / sp, vy * nsp / sp
            x, y = x + vx * dt, y + vy * dt
            t += dt
            rolling = [x, y, vx, vy]
            s = (x, y, R_BALL, vx, vy, 0.0, 0.0, 0.0, 0.0)
            if math.hypot(x, y) >= FENCE_R:
                wall = True
                samples.append((t, x, y, R_BALL, False))
                break
        k += 1
        if k % 5 == 0:
            samples.append((t, s[0], s[1], s[2], airborne))
    return samples, landed, hr, wall


def judge_batted(st):
    """Outcome of a batted ball: dict(kind, bases, fielder, ...)."""
    samples, landed, hr, wall = batted_flight(st)
    v = st[3:6]
    vh = math.hypot(v[0], v[1])
    info = {"exit_speed": round(math.sqrt(dot(v, v)), 2), "launch_deg": round(math.degrees(math.atan2(v[2], vh)), 1),
            "spray_deg": round(azimuth(v[0], v[1]), 1)}
    if landed is not None:
        info["landing"] = [round(landed[1], 2), round(landed[2], 2)]
        info["distance"] = round(math.hypot(landed[1], landed[2]), 1)
        info["hang_time"] = round(landed[0], 2)
        fair = landed[2] > 0 and abs(azimuth(landed[1], landed[2])) <= 45.0
    else:
        last = samples[-1]
        info["distance"] = round(math.hypot(last[1], last[2]), 1)
        fair = last[2] > 0 and abs(azimuth(last[1], last[2])) <= 45.0
    info["samples"] = samples
    if not fair:
        return dict(kind="foul", bases=0, **info)
    for (t, x, y, z, air) in samples:
        if z > REACH_H or math.hypot(x, y) >= FENCE_R:
            continue
        best = None
        for (name, dd, az, r0, vr, tr, inf) in FIELDERS:
            fx, fy = FIELDER_POS[name]
            reach = r0 + vr * max(0.0, t - tr)
            if math.hypot(x - fx, y - fy) <= reach:
                best = (name, inf)
                break
        if best is None:
            continue
        name, inf = best
        info.update(fielder=name, t_fielded=round(t, 2))
        if air:
            kind = "popout" if (landed is None or info.get("distance", 0) < 40) and info["launch_deg"] > 50 else \
                "lineout" if info["launch_deg"] < 20 else "flyout"
            return dict(kind=kind, bases=0, **info)
        if inf:
            t_throw = t + TRANSFER + math.hypot(x - B1[0], y - B1[1]) / THROW_V
            info["t_throw"] = round(t_throw, 2)
            if t_throw <= RUNNER_TO_1B:
                return dict(kind="groundout", bases=0, **info)
            return dict(kind="single", bases=1, **info)
        if (landed is not None and math.hypot(landed[1], landed[2]) > 80.0) or t > 5.0:
            return dict(kind="double", bases=2, **info)
        return dict(kind="single", bases=1, **info)
    if hr:
        return dict(kind="home run", bases=4, **info)
    return dict(kind="double", bases=2, **info)


# ------------------------------------------------------------------ one pitch
class Pitch:
    def __init__(self, ptype, speed, xt, zt):
        self.ptype, self.speed, self.target = ptype, speed, (xt, zt)
        pt = PITCH_TYPES[ptype]
        el, az = aim_pitch(speed, pt["spin"], pt["axis"], xt, zt)
        self.s0 = launch_state(speed, el, az, pt["spin"], pt["axis"])
        self.el, self.az = el, az
        # the coarse path: 1 ms steps until y = 2.5, then 50 us steps until y = -1.5
        self.path = []                   # (t, state)
        t, s = 0.0, self.s0
        self.path.append((t, s))
        while s[1] > 2.5:
            s = rk4(s, 0.001); t += 0.001
            self.path.append((t, s))
        self.i_fine = len(self.path) - 1
        self.fine_dt = 5e-5
        cr = None
        while s[1] > -1.5 and s[2] > R_BALL:
            n = rk4(s, self.fine_dt)
            if cr is None and n[1] <= 0.0:
                f = s[1] / (s[1] - n[1])
                cr = (t + f * self.fine_dt, s[0] + f * (n[0] - s[0]), s[2] + f * (n[2] - s[2]))
            s = n; t += self.fine_dt
            self.path.append((t, s))
        self.cross = cr                  # (t, x, z) at the plate plane y = 0
        self.zone = cr is not None and in_zone(cr[1], cr[2])
        self._fine_np = None

    def state_at(self, t):
        """Ball state at time t (s after release): the stored step before t, then one RK4 step."""
        lo, hi = 0, len(self.path) - 1
        if t >= self.path[hi][0]:
            return self.path[hi][1]
        while hi - lo > 1:
            mid = (lo + hi) // 2
            if self.path[mid][0] <= t:
                lo = mid
            else:
                hi = mid
        t0, s0 = self.path[lo]
        return s0 if t - t0 <= 0 else rk4(s0, t - t0)

    def fine_arrays(self):
        if self._fine_np is None:
            seg = self.path[self.i_fine:]
            self._fine_np = (np.array([p[0] for p in seg]), np.array([p[1][:3] for p in seg]))
        return self._fine_np

    def radar(self):
        return round(math.sqrt(dot(self.s0[3:6], self.s0[3:6])), 1)


def swing_result(pitch: Pitch, sw: Swing):
    """Contact search for a swing against a pitch; returns (contact info, post-contact ball state) or (None, None)."""
    ts, ps = pitch.fine_arrays()
    tau = ts - sw.t0
    th = np.where(tau <= 0, TH0, np.where(tau <= sw.tau1, TH0 + 0.5 * sw.acc1 * tau * tau,
                  np.where(tau <= sw.tau2, TH1 + sw.w * (tau - sw.tau1),
                           np.where(tau <= sw.tau3, TH2 + sw.w * (tau - sw.tau2) - 0.5 * sw.dec * (tau - sw.tau2) ** 2,
                                    TH3))))
    u = np.stack([np.cos(th), np.sin(th) * sw.ca, np.sin(th) * sw.sa], axis=1)
    d = ps - np.array([sw.px, sw.py, sw.H])
    s = np.clip(np.sum(d * u, axis=1), 0.0, L_BAT)
    q = np.array([sw.px, sw.py, sw.H]) + s[:, None] * u
    dist = np.linalg.norm(ps - q, axis=1)
    rad = np.where(s < 0.02, 0.025, np.where(s < 0.40, 0.0125, np.where(s < 0.60, 0.0125 + (s - 0.40) / 0.20 * 0.0205,
                                                                         0.033)))
    gap = dist - (R_BALL + rad)
    idx = np.nonzero(gap <= 0.002)[0]          # candidates (with margin); confirmed in pure Python below
    base = pitch.i_fine
    for i in idx:
        i = int(i)
        if i == 0:
            continue
        t1, s1 = pitch.path[base + i]
        g1 = sw.gap(t1, s1[:3])[0]
        if g1 > 0:
            continue
        t0, s0 = pitch.path[base + i - 1]
        if sw.gap(t0, s0[:3])[0] <= 0:
            continue
        lo, hi = 0.0, t1 - t0
        for _ in range(40):
            mid = 0.5 * (lo + hi)
            if sw.gap(t0 + mid, rk4(s0, mid)[:3])[0] > 0:
                lo = mid
            else:
                hi = mid
        tc = t0 + hi
        sc = rk4(s0, hi)
        r = collide(sw, tc, sc)
        if r is None:
            continue
        return r[1], r[0]
    return None, None


# ------------------------------------------------------------------ the game
def _rng(*key):
    return np.random.Generator(np.random.PCG64(list(key)))


class Game:
    def __init__(self, level: int = 1, lv_override: dict | None = None):
        self.level = level
        self.lv = dict(LEVELS[level], **(lv_override or {}))
        self.seed = self.lv["seed"]
        self.pa = 0                 # index of the current plate appearance
        self.balls = self.strikes = 0
        self.bases = 0
        self.pa_results = []
        self.history = []           # one entry per pitch
        self.decisions = []         # applied decisions (for replay)
        self.done = False
        self.pitch = None
        self._new_pitch()

    # --- pitcher
    def _new_pitch(self):
        k = len(self.history)
        lv = self.lv
        r = _rng(self.seed, 1, k)
        if lv.get("mix_ahead"):          # L4: sequencing by the count
            mix = lv["mix_ahead"] if self.strikes > self.balls else lv["mix_behind"] if self.balls > self.strikes \
                else lv["mix"]
        else:
            mix = lv["mix_2k"] if (self.strikes == 2 and lv.get("mix_2k")) else lv["mix"]
        names = sorted(mix)
        u = r.random()
        acc_p = 0.0
        ptype = names[-1]
        for nme in names:
            acc_p += mix[nme]
            if u < acc_p:
                ptype = nme
                break
        lo, hi = lv["speeds"][ptype]
        speed = lo + (hi - lo) * r.random()
        if lv.get("mix_ahead"):
            pz = lv["p_zone_3b"] if self.balls == 3 else lv["p_zone_ahead"] if self.strikes > self.balls else \
                lv["p_zone_behind"] if self.balls > self.strikes else lv["p_zone"]
        else:
            pz = lv["p_zone_3b"] if self.balls == 3 else lv["p_zone_2k"] if self.strikes == 2 else lv["p_zone"]
        if r.random() < pz:
            if lv.get("edge") and r.random() < lv["edge"]:      # L3/L4: a strike on the edge (<= 6 cm inside)
                u_side, d, along = r.random(), 0.06 * r.random(), r.random()
                w = lv.get("edge_sides", (0.25, 0.25, 0.25, 0.25))     # inside (-x), outside, low, high
                side = 0 if u_side < w[0] else 1 if u_side < w[0] + w[1] else 2 if u_side < w[0] + w[1] + w[2] else 3
                if side < 2:
                    xt, zt = (1 if side else -1) * (ZONE_X - d), 0.47 + 0.59 * along
                elif side == 2:
                    xt, zt = -0.20 + 0.40 * along, ZONE_LO + d
                else:
                    xt, zt = -0.20 + 0.40 * along, ZONE_HI - d
            else:
                xt = -0.19 + 0.38 * r.random()
                zt = 0.50 + 0.53 * r.random()
        else:
            side = r.integers(0, 4)
            mlo, mspan = lv.get("out_margin", (0.03, 0.22))      # (lowest margin, span)
            m = mlo + mspan * r.random()
            along = r.random()
            if side == 0:
                xt, zt = -(ZONE_X + R_BALL + m), 0.45 + 0.65 * along
            elif side == 1:
                xt, zt = ZONE_X + R_BALL + m, 0.45 + 0.65 * along
            elif side == 2:
                xt, zt = -0.25 + 0.5 * along, ZONE_LO - R_BALL - m
            else:
                xt, zt = -0.25 + 0.5 * along, ZONE_HI + R_BALL + m * 0.8
        self.pitch = Pitch(ptype, speed, xt, zt)

    # --- the batter's decision
    def scatter(self):
        r = _rng(self.seed, 7, len(self.history))
        z = r.standard_normal(5)
        S = SCATTER
        return dict(t=z[0] * S["t_ms"] / 1000.0, plane=z[1] * S["plane_deg"], height=z[2] * S["height_m"],
                    speed=1.0 + z[3] * S["speed_frac"], reach=z[4] * S["reach_m"])

    def decide(self, dec: dict, delay_s: float) -> dict:
        """Apply the batter's decision for the current pitch (made at T_DECISION, effective after delay_s).
        The three phases below, run back to back; the wall-clock service runs them at different times (the outcome
        is the same function of the decision, so the result and the state hash are identical)."""
        rec = self.decide_begin(dec, delay_s)
        self.decide_finish(rec)
        self.next_pitch()
        return rec

    def decide_begin(self, dec: dict, delay_s: float) -> dict:
        """Phase 1 (cheap, ~1 ms): fix the decision, the executed swing and the bat-ball contact (if any). The count,
        the history and the batted-ball outcome are not touched yet."""
        p = self.pitch
        k = len(self.history)
        t_eff = T_DECISION + delay_s
        rec = {"pitch": k, "pa": self.pa, "count": [self.balls, self.strikes], "type": p.ptype,
               "radar": p.radar(), "decision": dict(dec), "delay_s": delay_s}
        self.decisions.append({"k": k, "decision": dict(dec), "delay_s": delay_s})
        if dec["type"] == "take":
            res = "strike (called)" if p.zone else "ball"
            rec.update(outcome=res)
        else:
            sc = self.scatter()
            t_cmd = float(dec["t"])
            t0 = max(t_cmd, t_eff) + sc["t"]
            sw = Swing(t0, float(dec["plane"]) + sc["plane"], float(dec["height"]) + sc["height"],
                       float(dec["speed"]) * sc["speed"], float(dec.get("reach", 0.0)) + sc["reach"])
            rec["swing_executed"] = {"t_start": round(t0, 4), "plane_deg": round(sw.plane_deg, 3),
                                     "height": round(sw.H, 4), "speed": round(sw.speed, 3), "reach": round(sw.reach, 4),
                                     "late_by_think_s": round(max(0.0, t_eff - t_cmd), 4)}
            info, st = swing_result(p, sw)
            rec["swing_obj"] = sw
            if info is None:
                rec.update(outcome="strike (swinging)")
            else:
                rec["contact"] = {k2: (round(v, 4) if isinstance(v, float) else v) for k2, v in info.items()
                                  if k2 != "pos"}
                rec["contact"]["pos"] = [round(x, 4) for x in info["pos"]]
                rec["post_state"] = st
        rec["_finished"] = False
        return rec

    def decide_finish(self, rec: dict) -> dict:
        """Phase 2 (~10-40 ms for a batted ball: its flight and the fielders): the outcome, the count, the history."""
        assert not rec.pop("_finished"), "decide_finish called twice"
        p = self.pitch
        if "post_state" in rec:
            b = judge_batted(rec["post_state"])
            rec["batted_samples"] = b.pop("samples")
            rec["batted"] = b
            rec.update(outcome="foul" if b["kind"] == "foul" else b["kind"])
        rec["crossing"] = None if p.cross is None else [round(p.cross[0], 4), round(p.cross[1], 4), round(p.cross[2], 4)]
        rec["zone"] = p.zone
        rec["pitch_obj"] = p
        # count
        o = rec["outcome"]
        pa_end = None
        if o in ("strike (called)", "strike (swinging)"):
            self.strikes += 1
            if self.strikes >= 3:
                pa_end = ("strikeout", 0)
        elif o == "ball":
            self.balls += 1
            if self.balls >= 4:
                pa_end = ("walk", 1)
        elif o == "foul":
            if self.strikes < 2:
                self.strikes += 1
        else:
            pa_end = (o, rec["batted"]["bases"])
        if pa_end is None and 1 + sum(1 for h in self.history if h["pa"] == self.pa) >= PA_MAX_PITCHES:
            pa_end = ("out (pitch limit)", 0)
        rec["count_after"] = [self.balls, self.strikes]
        self.history.append(rec)
        if pa_end:
            self.bases += pa_end[1]
            self.pa_results.append({"pa": self.pa + 1, "result": pa_end[0], "bases": pa_end[1],
                                    "pitches": sum(1 for h in self.history if h["pa"] == self.pa)})
            rec["pa_result"] = pa_end[0]
            self.pa += 1
            self.balls = self.strikes = 0
        if self.pa >= self.lv["n_pa"]:
            self.done = True
            self.pitch = None
        return rec

    def next_pitch(self) -> None:
        """Phase 3 (~20-30 ms: the next pitch's flight): a pure function of the seed, the pitch index and the count."""
        if not self.done:
            self._new_pitch()

    # --- summaries
    def public_rec(self, rec: dict) -> dict:
        out = {"pitch": rec["pitch"] + 1, "pitch_type": rec["type"], "radar_mps": rec["radar"],
               "your_decision": rec["decision"], "outcome": rec["outcome"], "count_after": rec["count_after"],
               "heard_mitt_or_contact_t": None}
        p = rec["pitch_obj"]
        if "contact" in rec:
            out["heard_mitt_or_contact_t"] = round(rec["contact"]["t"], 3)
            b = rec["batted"]
            out["batted_ball"] = {k: b[k] for k in ("exit_speed", "launch_deg", "spray_deg", "distance", "hang_time",
                                                    "fielder") if k in b}
        elif p.cross is not None:
            out["heard_mitt_or_contact_t"] = round(p.cross[0], 3)
        if "swing_executed" in rec:
            out["swing_executed"] = rec["swing_executed"]
        if rec.get("pa_result"):
            out["plate_appearance_result"] = rec["pa_result"]
        return out

    def state_sha(self) -> str:
        h = hashlib.sha256()
        for rec in self.history:
            p = rec["pitch_obj"]
            h.update(repr((rec["pitch"], rec["outcome"], rec["count_after"], p.s0, p.path[-1], p.cross,
                           rec.get("post_state"), rec.get("contact"), rec.get("batted"),
                           rec.get("batted_samples", [])[-1:] if rec.get("batted_samples") else None)).encode())
        h.update(repr((self.bases, self.pa_results, self.done)).encode())
        return h.hexdigest()

    def summary(self) -> dict:
        kinds = [r["result"] for r in self.pa_results]
        hits = sum(1 for k in kinds if k in ("single", "double", "triple", "home run"))
        return {"bases": self.bases, "pa_done": len(self.pa_results), "n_pa": self.lv["n_pa"], "hits": hits,
                "walks": kinds.count("walk"), "strikeouts": kinds.count("strikeout"),
                "home_runs": kinds.count("home run"), "pitches": len(self.history), "pa_results": self.pa_results}

    # --- replay (fresh process)
    def replay(self, decisions):
        for d in decisions:
            assert d["k"] == len(self.history), (d["k"], len(self.history))
            self.decide(d["decision"], d["delay_s"])


# ------------------------------------------------------------------ rendering (MuJoCo, CPU / OSMesa)
def _look(pos, target, up=(0, 0, 1)):
    f = np.array(target, float) - np.array(pos, float); f /= np.linalg.norm(f)
    r = np.cross(f, up); r /= np.linalg.norm(r)
    u = np.cross(r, f)
    return f, u, r


CAMS = {  # name: (position, look-at, fovy)
    "catcher": ((0.0, -2.4, 1.50), (-0.30, 12.0, 1.40), 18.0),
    "side": ((7.0, 14.6, 1.55), (0.0, 14.6, 1.55), 30.0),
    "plate_side": ((5.5, 0.8, 1.3), (-0.3, 0.5, 0.9), 40.0),
    "wide": ((0.0, -14.0, 9.0), (0.0, 45.0, 0.0), 58.0),
    "behind": ((1.6, -5.0, 3.3), (-0.2, 4.0, 0.6), 34.0),
}
TILE_W, TILE_H = 480, 360


def cam_info():
    out = []
    for name in ("catcher", "side"):
        pos, tg, fovy = CAMS[name]
        f, u, r = _look(pos, tg)
        focal = TILE_H / 2 / math.tan(math.radians(fovy) / 2)
        out.append({"name": name, "position": list(pos), "forward": [round(x, 5) for x in f],
                    "up": [round(x, 5) for x in u], "right": [round(x, 5) for x in r], "fovy_deg": fovy,
                    "tile_px": [TILE_W, TILE_H], "focal_px": round(focal, 2), "principal_point_px": [TILE_W / 2, TILE_H / 2]})
    return out


def scene_xml() -> str:
    g = []
    add = g.append
    # field: grass, dirt around home / mound / infield arc, plate, bases, foul lines, fence, figures
    add('<geom name="grass" type="plane" size="130 130 0.1" pos="0 50 0" rgba="0.22 0.50 0.20 1"/>')
    add('<geom type="cylinder" size="29 0.002" pos="0 18.4 0.001" rgba="0.62 0.45 0.30 1" contype="0" conaffinity="0"/>')
    add(f'<geom type="box" size="12.9 12.9 0.002" pos="0 {B1[1]:.3f} 0.003" euler="0 0 45" rgba="0.24 0.54 0.22 1" contype="0" conaffinity="0"/>')
    add('<geom type="cylinder" size="4.0 0.002" pos="0 0 0.004" rgba="0.62 0.45 0.30 1" contype="0" conaffinity="0"/>')
    add('<geom type="cylinder" size="2.7 0.12" pos="0 18.44 0.0" rgba="0.62 0.45 0.30 1" contype="0" conaffinity="0"/>')
    add('<geom type="box" size="0.30 0.08 0.01" pos="0 18.44 0.125" rgba="1 1 1 1" contype="0" conaffinity="0"/>')
    add('<geom type="box" size="0.216 0.108 0.006" pos="0 0.108 0.006" rgba="1 1 1 1" contype="0" conaffinity="0"/>')
    add('<geom type="box" size="0.153 0.153 0.006" pos="0 0 0.005" euler="0 0 45" rgba="1 1 1 1" contype="0" conaffinity="0"/>')
    for (bx, by) in ((B1[0], B1[1]), (0.0, 2 * B1[1]), (-B1[0], B1[1])):
        add(f'<geom type="box" size="0.19 0.19 0.04" pos="{bx:.3f} {by:.3f} 0.04" rgba="1 1 1 1" contype="0" conaffinity="0"/>')
    for sgn in (1, -1):
        L = FENCE_R
        add(f'<geom type="box" size="0.04 {L / 2:.2f} 0.004" pos="{sgn * L / 2 * 0.7071:.3f} {L / 2 * 0.7071:.3f} 0.006" '
            f'euler="0 0 {-sgn * 45}" rgba="1 1 1 1" contype="0" conaffinity="0"/>')
    n = 36
    for i in range(n):
        a0 = math.radians(-48 + 96 * (i + 0.5) / n)
        seg = 2 * FENCE_R * math.sin(math.radians(96 / n / 2)) + 0.1
        x, y = -FENCE_R * math.sin(a0), FENCE_R * math.cos(a0)
        add(f'<geom type="box" size="{seg / 2:.3f} 0.2 {FENCE_H / 2}" pos="{x:.3f} {y:.3f} {FENCE_H / 2}" '
            f'euler="0 0 {math.degrees(a0):.3f}" rgba="0.08 0.28 0.14 1" contype="0" conaffinity="0"/>')
        add(f'<geom type="box" size="{seg / 2:.3f} 2.0 6" pos="{x * 1.12:.3f} {y * 1.12:.3f} 6" '
            f'euler="0 0 {math.degrees(a0):.3f}" rgba="0.35 0.37 0.42 1" contype="0" conaffinity="0"/>')

    def figure(x, y, col, h=1.8, face=0.0):
        add(f'<geom type="capsule" fromto="{x - 0.12} {y} 0.05 {x - 0.1} {y} {0.5 * h:.2f}" size="0.07" rgba="{col}" contype="0" conaffinity="0"/>')
        add(f'<geom type="capsule" fromto="{x + 0.12} {y} 0.05 {x + 0.1} {y} {0.5 * h:.2f}" size="0.07" rgba="{col}" contype="0" conaffinity="0"/>')
        add(f'<geom type="capsule" fromto="{x} {y} {0.52 * h:.2f} {x} {y} {0.80 * h:.2f}" size="0.17" rgba="{col}" contype="0" conaffinity="0"/>')
        add(f'<geom type="sphere" size="0.11" pos="{x} {y} {0.93 * h:.2f}" rgba="0.85 0.70 0.55 1" contype="0" conaffinity="0"/>')
    # pitcher (follow-through pose is not modelled; a standing figure behind the release point)
    figure(-0.15, 17.6, "0.16 0.22 0.45 1")
    add(f'<geom type="capsule" fromto="-0.3 17.55 1.45 {REL[0]} {REL[1] + 0.1} {REL[2]}" size="0.045" rgba="0.16 0.22 0.45 1" contype="0" conaffinity="0"/>')
    for (name, d, az, *_r) in FIELDERS:
        if name in ("P", "C"):
            continue
        fx, fy = FIELDER_POS[name]
        figure(round(fx, 2), round(fy, 2), "0.16 0.22 0.45 1")
    # catcher crouched behind the plate, umpire behind
    add('<geom type="ellipsoid" size="0.3 0.3 0.45" pos="0 -1.05 0.45" rgba="0.2 0.2 0.25 1" contype="0" conaffinity="0"/>')
    add('<geom type="sphere" size="0.13" pos="0 -1.0 1.0" rgba="0.15 0.15 0.2 1" contype="0" conaffinity="0"/>')
    # batter body (the rig's stylised body; the swing rig is the bat body below)
    figure(-1.05, 0.05, "0.75 0.12 0.12 1")
    geoms = "\n    ".join(g)
    cams = []
    for name, (pos, tg, fovy) in CAMS.items():
        f, u, r = _look(pos, tg)
        cams.append(f'<camera name="{name}" pos="{pos[0]} {pos[1]} {pos[2]}" xyaxes="{r[0]:.6f} {r[1]:.6f} {r[2]:.6f} '
                    f'{u[0]:.6f} {u[1]:.6f} {u[2]:.6f}" fovy="{fovy}"/>')
    cams = "\n    ".join(cams)
    return f"""<mujoco model="baseball">
  <visual><global offwidth="1280" offheight="720"/><quality shadowsize="2048"/>
    <headlight ambient="0.45 0.45 0.45" diffuse="0.5 0.5 0.5"/><map znear="0.01" zfar="600"/></visual>
  <asset><texture type="skybox" builtin="gradient" rgb1="0.55 0.72 0.92" rgb2="0.85 0.9 0.97" width="256" height="256"/>
    <material name="ballmat" rgba="1 1 1 1" emission="0.7"/></asset>
  <worldbody>
    <light pos="30 -20 60" dir="-0.3 0.4 -1" directional="true" diffuse="0.6 0.6 0.6"/>
    {geoms}
    {cams}
    <body name="ball" mocap="true" pos="{REL[0]} {REL[1]} {REL[2]}">
      <geom type="sphere" size="{R_BALL}" material="ballmat" contype="0" conaffinity="0"/>
    </body>
    <body name="bat" mocap="true" pos="{PIVOT_X0} {PIVOT_Y} 0.9">
      <geom type="sphere" size="0.025" pos="0 0 0" rgba="0.55 0.35 0.2 1" contype="0" conaffinity="0"/>
      <geom type="capsule" fromto="0.02 0 0 0.40 0 0" size="0.0125" rgba="0.80 0.62 0.38 1" contype="0" conaffinity="0"/>
      <geom type="capsule" fromto="0.40 0 0 0.60 0 0" size="0.022" rgba="0.80 0.62 0.38 1" contype="0" conaffinity="0"/>
      <geom type="capsule" fromto="0.60 0 0 {L_BAT - 0.033} 0 0" size="0.033" rgba="0.80 0.62 0.38 1" contype="0" conaffinity="0"/>
    </body>
    <body name="hands" mocap="true" pos="{PIVOT_X0} {PIVOT_Y} 0.9">
      <geom type="sphere" size="0.05" pos="0.05 0 0" rgba="0.15 0.15 0.15 1" contype="0" conaffinity="0"/>
      <geom type="capsule" fromto="0 0 0 -0.30 -0.15 0.20" size="0.03" rgba="0.75 0.12 0.12 1" contype="0" conaffinity="0"/>
    </body>
  </worldbody>
</mujoco>"""


class Renderer:
    def __init__(self, w=TILE_W, h=TILE_H):
        import mujoco as mj
        self.mj = mj
        self.m = mj.MjModel.from_xml_string(scene_xml())
        self.d = mj.MjData(self.m)
        self.r = mj.Renderer(self.m, height=h, width=w)

    def set(self, ball, sw: Swing | None, t, default_h=0.9):
        mj, d = self.mj, self.d
        d.mocap_pos[0] = ball if ball is not None else (0, -50, -5)
        if sw is None:
            th, ca, sa, px, H = TH0, 1.0, 0.0, PIVOT_X0, default_h
            ns = (0.0, 0.0, 1.0)
        else:
            th, _ = sw.angle(t)
            ca, sa, px, H = sw.ca, sw.sa, sw.px, sw.H
            ns = sw.normal()
        u = (math.cos(th), math.sin(th) * ca, math.sin(th) * sa)
        y = cross(ns, u)
        R = np.array([u, y, ns]).T
        q = np.zeros(4)
        mj.mju_mat2Quat(q, R.ravel())
        d.mocap_pos[1] = (px, PIVOT_Y, H)
        d.mocap_quat[1] = q
        d.mocap_pos[2] = (px, PIVOT_Y, H)
        d.mocap_quat[2] = q
        mj.mj_forward(self.m, d)

    def render(self, cam):
        self.r.update_scene(self.d, camera=cam)
        return self.r.render()

    def close(self):
        self.r.close()


def render_decision(pitch: Pitch, rd: Renderer | None = None) -> bytes:
    """PNG: 2 rows (catcher camera, side camera) x 4 columns (t = 0.01, 0.04, 0.07, 0.10 s after release)."""
    import imageio.v2 as imageio
    from PIL import Image, ImageDraw
    own = rd is None
    rd = rd or Renderer()
    rows = []
    for cam in ("catcher", "side"):
        tiles = []
        for t in VIEW_TIMES:
            s = pitch.state_at(t)
            rd.set(s[:3], None, t)
            im = Image.fromarray(rd.render(cam))
            ImageDraw.Draw(im).text((6, 4), f"{cam}  t={t:.2f}s", fill=(255, 255, 0))
            tiles.append(np.asarray(im))
        rows.append(np.concatenate(tiles, axis=1))
    if own:
        rd.close()
    buf = io.BytesIO()
    imageio.imwrite(buf, np.concatenate(rows, axis=0), format="png")
    return buf.getvalue()


def render_video(game: Game, out: str, fps=25):
    """Replay video: per pitch the catcher camera and a side view of the plate (4x slow motion), then for balls in
    play the wide field camera (real time); overlay with PA, count and result."""
    import imageio.v2 as imageio
    from PIL import Image, ImageDraw
    rd = Renderer(640, 360)
    w = imageio.get_writer(out, fps=fps, macro_block_size=8)
    bases = 0
    for rec in game.history:
        p, sw = rec["pitch_obj"], rec.get("swing_obj")
        t_end = (rec["contact"]["t"] if "contact" in rec else (p.cross[0] if p.cross else 0.6)) + 0.12
        head = f"level {game.level}  PA {rec['pa'] + 1}/{game.lv['n_pa']}  count {rec['count'][0]}-{rec['count'][1]}  " \
               f"bases so far {bases}   pitch {rec['pitch'] + 1}: {rec['type']} {rec['radar']} m/s"
        t = 0.0
        while t <= t_end + 1e-9:
            s = p.state_at(t) if ("contact" not in rec or t < rec["contact"]["t"]) else None
            if s is None:
                pc = rec["post_state"]
                dtc = t - rec["contact"]["t"]
                pos = (pc[0] + pc[3] * dtc, pc[1] + pc[4] * dtc, pc[2] + pc[5] * dtc)
            else:
                pos = s[:3]
            rd.set(pos, sw, t)
            im = Image.fromarray(np.concatenate([rd.render("behind"), rd.render("plate_side")], axis=1))
            dr = ImageDraw.Draw(im)
            dr.text((8, 6), head, fill=(255, 255, 0))
            dr.text((8, 20), f"t = {t:.2f} s after release  (slow motion)", fill=(255, 255, 255))
            w.append_data(np.asarray(im))
            t += 0.02 if t < 0.28 else 0.01
        res = rec["outcome"] + (f"  -> {rec['pa_result']}" if rec.get("pa_result") else "")
        if "batted_samples" in rec:
            b = rec["batted"]
            txt = f"{res}   exit {b['exit_speed']} m/s, launch {b['launch_deg']} deg, spray {b['spray_deg']} deg" + \
                  (f", {b.get('distance')} m" if b.get("distance") else "")
            smp = rec["batted_samples"]
            j = 0
            tt = 0.0
            while True:
                while j + 1 < len(smp) and smp[j + 1][0] <= tt:
                    j += 1
                sm = smp[j]
                rd.set(sm[1:4], sw, 10.0)
                im = Image.fromarray(np.concatenate([rd.render("wide"), rd.render("behind")], axis=1))
                dr = ImageDraw.Draw(im)
                dr.text((8, 6), head, fill=(255, 255, 0))
                dr.text((8, 20), txt, fill=(255, 255, 255))
                w.append_data(np.asarray(im))
                if j + 1 >= len(smp) or tt > 7.0:
                    break
                tt += 0.04 if tt < 6.0 else 1.0
            for _ in range(8):
                w.append_data(np.asarray(im))
        else:
            for _ in range(12):
                dr = ImageDraw.Draw(im)
                dr.text((8, 34), res, fill=(255, 80, 80))
                w.append_data(np.asarray(im))
        if rec.get("pa_result"):
            bases = sum(r["bases"] for r in game.pa_results[:rec["pa"] + 1])
    w.close()
    rd.close()


# ------------------------------------------------------------------ fresh-process replay entry point
def replay_file(traj_path: str, out_path: str, video: str | None = None):
    tr = json.load(open(traj_path))
    g = Game(tr["level"], {"seed": tr["seed"]} if "seed" in tr else None)
    g.replay(tr["decisions"])
    out = {"state_sha": g.state_sha(), "bases": g.bases, "summary": g.summary(), "done": g.done}
    if video:
        try:
            render_video(g, video)
            out["video"] = True
        except Exception as exc:  # noqa: BLE001
            out["video"] = False
            out["video_error"] = repr(exc)[:300]
    json.dump(out, open(out_path, "w"), default=float)
    return out


if __name__ == "__main__":
    if sys.argv[1:2] == ["replay"]:
        print(json.dumps(replay_file(sys.argv[2], sys.argv[3], sys.argv[4] if len(sys.argv) > 4 else None))[:500])
