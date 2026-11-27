"""Double Dutch: two ropes turned in opposite directions by two automatic rope turners; the robot enters the turning
ropes and jumps them, one rope per jump, a number of times in a row without the ropes ever touching it.

Everything that moves is physical. Each turner is a post with two motor-driven cranks (its two hands), the way
automatic rope-turning machines work: a crank arm on an axle, a geared motor with a torque limit, the rope tied to
the crank pin by a swivel. Each rope is a chain of 24 capsules (a swivel, then universal joints: they bend, the
rope does not twist against itself) with the rope's real mass and the air's drag. At
t = 0 the ropes are already turning: their state is that of the same machines and ropes turned for a few seconds
from rest (computed once per process in a model of the floor, the turners and the ropes alone)."""
import math
import xml.etree.ElementTree as ET

import numpy as np

import mujoco

from rfo.referee import Flights
from rfo.task import TaskBase

SIDES = ("left", "right")
ROPES = ("rope_a", "rope_b")      # a: the cranks at +x (the turners' right / left hands), b: at -x
PREROLL_S = 6.0                   # the turners spin the ropes up from rest this long before t = 0
RAMP_S = 0.8                      # ... the spin-up at the start of that

# rope_turner v2 (a shared block)
# ---------------------------------------------------------------------------------------------- rope_turner (shared)
# Shared block (v2): physical rope turners and a physical rope, the same code in each family module that uses
# them (a task directory holds one module). Needs: math,
# xml.etree.ElementTree as ET, numpy as np, mujoco.
#
# A turner's hand is a motor-driven crank, the way automatic rope-turning machines work: a crank arm on a horizontal
# axle on a post, driven by a geared motor; the rope's end hangs from the crank pin on a swivel (a ball joint: the
# rope may twist and swing about it freely). The arm meets the robot (contype 64, conaffinity 4 | 8), not the rope
# tied to it nor the floor. The motor is a position servo with a torque limit (MuJoCo `position` actuator: kp, kv,
# forcerange), the axle damped by the motor's back-EMF (crank_xml's damping): its controller follows a steady
# angle ramp (TurnerDrive.angle), so the hands at the two ends of a rope stay in phase, as on a machine with a common
# drive; a rope caught on a body loads the motor, which stalls at its torque limit and the crank lags (the robot is
# pulled, the rope stops on it).
#
# The rope: N segments (capsules) in two chains, one hanging from each crank's pin (the swivel there is the chain's
# first joint), the two halves joined mid-rope by a `connect` (a loop closed between two like segments, not at a
# pin against a crank's inertia, where the 5 g end segment's tie diverged when a robot leaned on the rope); free to
# bend (a cord has almost no bending stiffness), each segment with the rope's mass for its length and a solid
# cylinder's inertia. Between segments the joint is a universal joint (two hinges across the rope), not a ball joint:
# a cord's torsional stiffness is large against a 15 cm segment's twist inertia, so its segments do not twist against
# each other (with ball joints a robot's hip rubbing the rope spun single segments about their own axis to 380
# rad/s and the chain diverged, stress test). The mid-rope `connect` holds as the rope does: solimp 0.99
# 0.999 (with MuJoCo's default impedance, whose force scales with the few grams of a segment, a robot leaning on
# the rope pulled the tie 4 m apart). The air: RopeDrag applies quadratic drag on each segment as a force, the drag of
# a cylinder in cross flow (C_d 1.2 on the flow across the segment, the air's density 1.225 kg/m^3), every physics
# step. A family using it builds its venue without MuJoCo's fluid model (Scene option density 0): with it on, the
# implicit integrator's fluid derivatives over the deep rope chains cost 7 to 9 times the step (measured: 1.4 ms
# against 0.19 ms per physics step for two 24-segment ropes) and the real-time twin would fall below 1.5 times real
# time.
#
#   bodies, acts = crank_xml(name, centre, phi0, radius, kp, kv, torque, rope="")   # the rope's chain inside the crank
#   chain_a, chain_b, eq = rope_xml(name, n_seg, free_len, diameter, lin_density, contype, conaffinity)  # crank_xml
#   start = rope_rest_qpos(name, n_seg, free_len, radius, pa, pb)  # {joint: qpos}: the rope hanging still, pa to pb
#   drive = TurnerDrive({crank name: rate rad/s}, ramp_s, q0)    # drive.ctrl(m, d, t): every crank's target at time t
#   drag = RopeDrag(m, [rope names], n_seg, free_len, diameter)  # drag.apply(d) every physics step (xfrc_applied)
#   state = preroll(key, xml, drive, start_qpos, seconds, ropes, n_seg, free_len, diameter)   # floor, turners, ropes
ROPE_N_SEG = 24                  # segments per rope
ROPE_TWIST_INERTIA = 2e-6        # kg m^2: at least this about a segment's own axis (numerical, as long-rope's: a cord's
#                                  real twist inertia makes the twist mode stiff at 1 ms; its twist plays no part)
ROPE_ARMATURE = 1e-6             # kg m^2 on each joint (numerical)
ROPE_DAMPING = 1e-3              # N m s / rad on each joint: a braided cord's bending loss (its fibres rub), an
#                                  estimate: a kink between two 18 cm segments relaxes in about 50 ms (at 1e-4
#                                  a robot pinching the rope against its hip set the chain chattering until it diverged)
ROPE_EQ_SOLREF = "0.004 1"       # the mid-rope connect's constraint time constant (s) and damping ratio
ROPE_EQ_SOLIMP = "0.99 0.999 0.0005 0.5 2"     # ... and its impedance: it holds as the rope does
ROPE_CONTACT_SOLREF = "0.005 1"  # the rope's contacts (priority 1: the rope's numbers win)
ROPE_CD = 1.2                    # drag coefficient of a cylinder in cross flow (Re ~ 10^3: Hoerner, Fluid-Dynamic Drag)
AIR_DENSITY = 1.225              # kg/m^3 (sea level, 15 C)
CRANK_ARM_MASS = 0.4             # kg: a 25 mm aluminium crank arm with its pin and swivel (estimate)


def _rt_fmt(v) -> str:
    return " ".join(f"{float(x):.6g}" for x in v)


def crank_xml(name, centre, phi0, radius, kp, kv, torque, rope="", rgba=(0.30, 0.30, 0.34, 1),
              damping=0.01):
    """(bodies, actuators) MJCF of one crank: a hinge about -y at `centre` (so the joint angle q grows with the
    crank's angle phi in the x-z plane, phi = 0 towards +x, pi/2 up), its arm built at phi0 (q = 0 there): the pin
    at centre + radius (cos phi, 0, sin phi). The motor: a position servo on q with a torque limit (torque);
    damping: the axle's (N m s / rad): a DC gear motor's back-EMF gives the slope of its torque-speed line, stall
    torque / no-load speed (with the stall torque as the servo's limit, the torque left at speed w is torque - damping
    w: the motor's line). rope: a rope's chain (rope_xml) hanging from this crank's pin."""
    c, s = math.cos(phi0), math.sin(phi0)
    pin = (radius * c, 0.0, radius * s)
    body = (f'<body name="{name}" pos="{_rt_fmt(centre)}"><joint name="{name}" type="hinge" axis="0 -1 0" '
            f'damping="{damping:g}" armature="0.002"/>'
            f'<geom name="{name}_arm" type="capsule" fromto="0 0 0 {_rt_fmt(pin)}" '
            f'size="0.0125" mass="{CRANK_ARM_MASS:g}" rgba="{_rt_fmt(rgba)}" contype="64" conaffinity="12"/>'
            f'<site name="{name}_pin" pos="{_rt_fmt(pin)}" size="0.012"/>'
            f'<body name="{name}_swivel" pos="{_rt_fmt(pin)}">{rope}</body></body>')
    act = (f'<position name="{name}_motor" joint="{name}" kp="{kp:g}" kv="{kv:g}" forcelimited="true" '
           f'forcerange="{-torque:g} {torque:g}" ctrllimited="false"/>')
    return body, act


def rope_xml(name, n_seg, free_len, diameter, lin_density, contype=2, conaffinity=13,
             rgba=(0.85, 0.12, 0.10, 1)):
    """(chain_a, chain_b, equality) MJCF of a rope of n_seg segments (n_seg even; body, geom the same name f"{name}{i}",
    i = 0 .. n_seg - 1 along the rope): chain_a, segments 0 .. n_seg/2 - 1, to hang from the first crank's pin and
    chain_b, segments n_seg - 1 .. n_seg/2, from the second's (crank_xml(rope=...)); each chain's first joint is the
    swivel there (a ball joint f"{name}{i}"), the others universal joints (f"{name}{i}_z", f"{name}{i}_y"). The two
    halves meet mid-rope at a `connect` (the equality): a loop of chains closed where the masses on its two sides are
    equal (closed at a crank's pin, against the crank's far larger inertia, the 5 g end segment's tie diverged when a
    robot leaned on the rope: stress test). Sites: f"{name}{i}" at the rope's point i (its start, along the
    rope) and f"{name}_end" at its far end (the second pin), so the nodes read in order whichever chain holds them."""
    L, r = free_len / n_seg, diameter / 2
    h = n_seg // 2
    m_seg = free_len * lin_density / n_seg
    i_bend = m_seg * (L * L / 12 + r * r / 4)          # a solid cylinder's, about a diameter through its centre
    i_twist = max(m_seg * r * r / 2, ROPE_TWIST_INERTIA)
    geom = (f'size="{r:.6g}" contype="{contype}" conaffinity="{conaffinity}" condim="3" '
            f'friction="0.6 0.005 0.0001" solref="{ROPE_CONTACT_SOLREF}" priority="1" rgba="{_rt_fmt(rgba)}"')
    jk = f'damping="{ROPE_DAMPING:g}" armature="{ROPE_ARMATURE:g}"'

    def seg(i, first, last, reverse, inner):
        joints = (f'<joint name="{name}{i}" type="ball" {jk}/>' if first else
                  f'<joint name="{name}{i}_z" type="hinge" axis="0 0 1" {jk}/>'
                  f'<joint name="{name}{i}_y" type="hinge" axis="0 1 0" {jk}/>')
        sites = (f'<site name="{name}{i}" pos="{L:.6g} 0 0" size="0.002"/>' if reverse else
                 f'<site name="{name}{i}" size="0.002"/>')
        if reverse and first:
            sites += f'<site name="{name}_end" size="0.002"/>'
        if last and not reverse:
            sites += f'<site name="{name}_mid" pos="{L:.6g} 0 0" size="0.002"/>'
        return (f'<body name="{name}{i}" pos="{"0 0 0" if first else f"{L:.6g} 0 0"}"><inertial pos="{L / 2:.6g} 0 0" '
                f'mass="{m_seg:.6g}" diaginertia="{i_twist:.6g} {i_bend:.6g} {i_bend:.6g}"/>{joints}'
                f'<geom name="{name}{i}" type="capsule" fromto="0 0 0 {L:.6g} 0 0" {geom}/>{sites}{inner}</body>')
    chain_a = ""
    for i in reversed(range(h)):
        chain_a = seg(i, i == 0, i == h - 1, False, chain_a)
    chain_b = ""
    for i in range(h, n_seg):
        chain_b = seg(i, i == n_seg - 1, i == h, True, chain_b)
    eq = (f'<connect name="{name}_tie" site1="{name}_mid" site2="{name}{h}" solref="{ROPE_EQ_SOLREF}" '
          f'solimp="{ROPE_EQ_SOLIMP}"/>')
    return chain_a, chain_b, eq


def _rt_catenary_a(L: float, span: float) -> float:
    lo, hi = 1e-3, 1e3
    for _ in range(200):
        a = (lo + hi) / 2
        lo, hi = (a, hi) if 2 * a * math.sinh(span / (2 * a)) > L else (lo, a)
    return (lo + hi) / 2


def _rt_qmul(a, b):
    w1, x1, y1, z1 = a
    w2, x2, y2, z2 = b
    return np.array([w1 * w2 - x1 * x2 - y1 * y2 - z1 * z2, w1 * x2 + x1 * w2 + y1 * z2 - z1 * y2,
                     w1 * y2 - x1 * z2 + y1 * w2 + z1 * x2, w1 * z2 + x1 * y2 - y1 * x2 + z1 * w2])


def rope_rest_points(n_seg, free_len, radius, pa, pb) -> list:
    """The n_seg + 1 points of the rope hanging still from pa to pb (a catenary in their vertical plane; where it would
    reach below the floor it lies on it). pa and pb at the same height."""
    pa, pb = np.asarray(pa, float), np.asarray(pb, float)
    span = float(np.linalg.norm(pb[:2] - pa[:2]))
    u = (pb[:2] - pa[:2]) / span
    a = _rt_catenary_a(free_len, span)
    pts = []
    for i in range(n_seg + 1):
        s = i * free_len / n_seg
        h = a * math.asinh(s / a - math.sinh(span / (2 * a)))          # the horizontal distance from the middle
        z = pa[2] + a * (math.cosh(h / a) - math.cosh(span / (2 * a)))
        xy = pa[:2] + u * (span / 2 + h)
        pts.append(np.array((xy[0], xy[1], max(z, radius + 0.001))))
    return pts


def rope_rest_qpos(name, n_seg, free_len, radius, pa, pb) -> dict:
    """{joint name: qpos} of rope_xml's rope hanging still from pa to pb (rope_rest_points), the cranks at q = 0 (each
    chain's parent frame aligned with the world): each swivel's quaternion, then each universal joint's two angles
    (about z, then about the turned y) that point a segment along its chord."""
    pts = rope_rest_points(n_seg, free_len, radius, pa, pb)
    h = n_seg // 2
    out = {}
    for order in (list(range(h)), list(range(n_seg - 1, h - 1, -1))):
        R = None
        for i in order:
            rev = order[0] != 0
            v = (pts[i] - pts[i + 1]) if rev else (pts[i + 1] - pts[i])
            v = v / np.linalg.norm(v)
            if R is None:                                # the swivel: the rotation taking +x onto v
                q = np.array([1.0 + v[0], 0.0, -v[2], v[1]])
                q = q / np.linalg.norm(q)
                out[f"{name}{i}"] = q
                Rm = np.zeros(9)
                mujoco.mju_quat2Mat(Rm, q)
                R = Rm.reshape(3, 3)
                continue
            u = R.T @ v
            a = math.atan2(u[1], u[0])
            b = math.atan2(-u[2], math.hypot(u[0], u[1]))
            out[f"{name}{i}_z"], out[f"{name}{i}_y"] = np.array([a]), np.array([b])
            ca, sa, cb, sb = math.cos(a), math.sin(a), math.cos(b), math.sin(b)
            Rz = np.array([[ca, -sa, 0], [sa, ca, 0], [0, 0, 1.0]])
            R = R @ Rz @ np.array([[cb, 0, sb], [0, 1, 0], [-sb, 0, cb]])
    return out


class TurnerDrive:
    """The turners' controller: each crank follows the angle ramp q(t) = q0 + rate (t - t0) (from rest it spins up
    over ramp_s with a constant angular acceleration). ctrl() writes every crank motor's target for time t."""

    def __init__(self, rates: dict, ramp_s: float = 0.0, q0: dict | None = None, t0: float = 0.0):
        self.rates, self.ramp, self.q0, self.t0 = dict(rates), float(ramp_s), dict(q0 or {}), float(t0)

    def angle(self, name: str, t: float) -> float:
        w, T = self.rates[name], self.ramp
        tt = t - self.t0
        sweep = w * tt * tt / (2 * T) if T > 0 and tt < T else (w * T / 2 + w * (tt - T) if T > 0 else w * tt)
        return self.q0.get(name, 0.0) + sweep

    def ctrl(self, m, d, t: float) -> None:
        ids = getattr(self, "_ids", None)
        if ids is None or self._m is not m:              # the motors' actuator ids, once per model
            self._m, self._ids = m, [m.actuator(f"{name}_motor").id for name in self.rates]
        for i, name in zip(self._ids, self.rates):
            d.ctrl[i] = self.angle(name, t)


class RopeDrag:
    """The air's drag on rope segments: F = -1/2 rho C_d D L |v_n| v_n at each segment's centre of mass, v_n its
    velocity across the segment's axis (the flow along a cord adds only skin friction, left out). apply(d) writes
    d.xfrc_applied of the segments (nothing else there), once per physics step before it."""

    def __init__(self, m, ropes, n_seg, free_len, diameter):
        self.ids = np.array([m.body(f"{r}{i}").id for r in ropes for i in range(n_seg)])
        self.root = m.body_rootid[self.ids]
        self.k = 0.5 * AIR_DENSITY * ROPE_CD * diameter * free_len / n_seg

    def apply(self, d):
        ids = self.ids
        R = d.xmat[ids].reshape(-1, 3, 3)
        u = R[:, :, 0]                                     # each segment's axis
        cv = d.cvel[ids]                                   # (angular, linear) about the tree's centre of mass
        v = cv[:, 3:] + np.cross(cv[:, :3], d.xipos[ids] - d.subtree_com[self.root])
        vn = v - np.sum(v * u, axis=1)[:, None] * u
        d.xfrc_applied[ids, :3] = -self.k * np.linalg.norm(vn, axis=1)[:, None] * vn
        d.xfrc_applied[ids, 3:] = 0.0


_RT_PREROLL: dict = {}


def preroll(key, xml: str, drive: TurnerDrive, start_qpos: dict, seconds: float, ropes=(), n_seg=ROPE_N_SEG,
            free_len=1.0, diameter=0.01) -> dict:
    """The turners and ropes alone (the model `xml`: the floor, the cranks, the ropes; no MuJoCo fluid, RopeDrag on
    the ropes), started from rest in start_qpos ({joint name: qpos}), turned by `drive` for `seconds` at 1 ms: {joint
    name: (qpos, qvel)} of every joint at the end. Cached by `key` (a hashable of everything that defines the
    model)."""
    if key in _RT_PREROLL:
        return _RT_PREROLL[key]
    m = mujoco.MjModel.from_xml_string(xml)
    d = mujoco.MjData(m)
    for name, q in start_qpos.items():
        j = m.joint(name)
        d.qpos[int(j.qposadr[0]):int(j.qposadr[0]) + len(q)] = q
    drive.ctrl(m, d, m.opt.timestep)
    mujoco.mj_forward(m, d)
    drag = RopeDrag(m, ropes, n_seg, free_len, diameter) if ropes else None
    n = int(round(seconds / m.opt.timestep))
    for k in range(n):
        drive.ctrl(m, d, (k + 1) * m.opt.timestep)
        if drag is not None:
            drag.apply(d)
        mujoco.mj_step(m, d)
    if not np.all(np.isfinite(d.qpos)):
        raise RuntimeError("rope_turner: the pre-roll diverged")
    out = {}
    for j in range(m.njnt):
        qa, va = int(m.jnt_qposadr[j]), int(m.jnt_dofadr[j])
        nq, nv = {0: (7, 6), 1: (4, 3)}.get(int(m.jnt_type[j]), (1, 1))
        out[m.joint(j).name] = (d.qpos[qa:qa + nq].copy(), d.qvel[va:va + nv].copy())
    _RT_PREROLL[key] = out
    return out
# ------------------------------------------------------------------------------------------ end of rope_turner (shared)


def rope_point_at_y(nodes: np.ndarray, y: float):
    """The rope's point where it crosses the plane y = const, interpolated between the nodes; of several crossings,
    the one nearest the rope's middle. None if the rope does not reach that plane (long-rope's)."""
    s = nodes[:, 1] - y
    idx = np.flatnonzero((s[:-1] <= 0) != (s[1:] <= 0))
    if not len(idx):
        return None
    i = int(idx[np.argmin(np.abs(idx + 0.5 - (len(nodes) - 1) / 2))])
    f = s[i] / (s[i] - s[i + 1]) if s[i] != s[i + 1] else 0.0
    return nodes[i] + f * (nodes[i + 1] - nodes[i])


def rope_points_at_ys(nodes: np.ndarray, ys) -> list:
    """rope_point_at_y for several planes at once (one pass over the nodes)."""
    s = nodes[None, :, 1] - np.asarray(ys, float)[:, None]
    neg = s <= 0
    ch = neg[:, :-1] != neg[:, 1:]
    mid = (len(nodes) - 1) / 2
    out = []
    for k in range(len(ys)):
        idx = np.flatnonzero(ch[k])
        if not len(idx):
            out.append(None)
            continue
        i = int(idx[np.argmin(np.abs(idx + 0.5 - mid))])
        a, b = s[k, i], s[k, i + 1]
        f = a / (a - b) if a != b else 0.0
        out.append(nodes[i] + f * (nodes[i + 1] - nodes[i]))
    return out


def zspan(w, ids):
    m, d = w.m, w.d
    R = d.geom_xmat[ids].reshape(-1, 3, 3)
    c = d.geom_xpos[ids] + np.einsum("gij,gj->gi", R, m.geom_aabb[ids, :3])
    half = np.sum(np.abs(R[:, 2, :]) * m.geom_aabb[ids, 3:], axis=1)
    return float(np.min(c[:, 2] - half)), float(np.max(c[:, 2] + half))


class Task(TaskBase):
    name = "double-dutch"
    title = "Double Dutch (enter two turning ropes and jump them)"
    category = "track-and-jumps"
    robot = "unitree_g1"
    rulebook = ("IJRU Rule Book 5.0.0 (International Jump Rope Union, 2026): Competition Manual, event Double Dutch "
                "Single Freestyle (DDSF: three athletes, two turners and one jumper, one set of two ropes; a 12 x 12 m "
                "field); Judging Manual, Counting: 'Double Dutch ropes must be turned counter clockwise with the "
                "right hand and clockwise with the left hand'; Violations: a space violation is any part of an "
                "athlete touching the ground outside the field; ropes may be of any length")
    deviations = [
        "the turners are machines, not athletes: each is a post with two motor-driven cranks of {crank_radius_m} "
        "m (its right and left hands, {hand_gap_m} m apart, their axles {hand_height_m} m high), each crank a "
        "position servo on a 90 W geared DC motor ({motor_torque_nm} N m at one turn per second, its maximum-power "
        "point: its torque-speed line from twice that at stall to no torque at two turns per second) following a "
        "steady {tempo_rev_s} turns per second, right hands counter-clockwise and left hands "
        "clockwise as the turner sees them, the ropes half a turn apart; the turners' axles are "
        "{turner_distance_m} m apart; they never adapt to the jumper and do not stop when a rope is caught (the "
        "motor stalls at its limit)",
        "the routine: a freestyle is judged on its skills; here the task is the basic one every routine starts "
        "with: enter the turning ropes from outside and jump {jumps_required} rope passes in a row, one rope per "
        "jump, with no miss (the count is the benchmark's mark, a round number); any jump style is allowed",
        "the start: the ropes are already turning at t = 0 (a freestyle routine starts with the ropes turning "
        "and an entry); the robot stands outside them, {start_x_m} m from the middle, facing in",
        "a miss is any touch of a rope on the robot; a counted jump is a pass of a rope under both feet while "
        "nothing of the robot touches the ground, with the pelvis in the middle (the centre zone, "
        "{zone_half_x_m} by {zone_half_y_m} m each way), each rope having gone over the head since its last pass; "
        "once in the zone the robot must stay in it (instead of the field's space rule, which the robot cannot "
        "break here); the end: the first contact after the last counted jump must be the feet only",
        "the ropes: {rope_length_m} m (14 ft) of {rope_diameter_m} m braided rope at {rope_linear_density_kg_m} "
        "kg/m (a typical braided double-dutch cord), tied at both ends to the crank pins by swivels, each a "
        "chain of 24 capsules on universal joints (free to bend; it turns about its own axis at the swivels), in "
        "still air: the drag of a cylinder in cross "
        "flow (C_d 1.2) on each segment; the air's drag on the robot and the machines is left out (a few newtons at "
        "most at their speeds; the fluid model would cost the real-time twin its speed); the ropes collide with each "
        "other, the floor and the robot",
    ]
    time_limit_s = 25.0
    params = dict(turner_distance_m=3.9, hand_gap_m=0.40, hand_height_m=0.95, crank_radius_m=0.30,
                  rope_length_m=4.27, rope_diameter_m=0.008, rope_linear_density_kg_m=0.040, tempo_rev_s=1.1,
                  phase_a0_deg=-130.0, motor_torque_nm=14.0, motor_kp=300.0, motor_kv=3.0, start_x_m=1.5,
                  zone_half_x_m=0.35, zone_half_y_m=0.5, jumps_required=10, fall_z_m=0.35,
                  turner_y_m=1.95, half_gap_m=0.2, pass_period_s=0.4545)       # (the last three: derived, for the texts)

    sentence = (("Jump Double Dutch: get into the two turning ropes and jump them 10 times in a row, one rope per"
                 " jump, without a rope touching you, then land on your feet."))
    rules = ("Two rope-turning machines stand {turner_distance_m} m apart, at y = -{turner_y_m} and +{turner_y_m} "
             "m; each turns the ends of two ropes on cranks {crank_radius_m} m long whose axles are "
             "{hand_height_m} m above the floor, {hand_gap_m} m apart (one at x = +{half_gap_m} m, one at x = "
             "-{half_gap_m} m), at {tempo_rev_s} turns per second each, the two ropes in opposite directions and "
             "half a turn apart, so that a rope passes under the middle every {pass_period_s} s, the two ropes "
             "taking turns: the rope at +x goes over the top towards -x and under the middle towards +x, the rope at "
             "-x the other way round. They are already turning at the start, and they never stop. You start "
             "outside the ropes and must enter them: the centre zone is within {zone_half_x_m} m of x = 0 and "
             "{zone_half_y_m} m of y = 0 (your pelvis decides). A jump counts when a rope passes under both your "
             "feet while nothing of you touches the ground and your pelvis is in the centre zone, if that rope has "
             "passed over your head since it last passed under you, and if it is not the same flight as the last "
             "counted jump (one rope per jump). You succeed when, after {jumps_required} counted jumps, your first "
             "contact with the floor is your feet only. You fail at once if a rope touches any part of you (a "
             "miss), if a rope passes under a foot that is on the ground or through you, if your pelvis leaves the "
             "centre zone after it has entered it, on a fall (your pelvis lower than {fall_z_m} m, or any part of "
             "you other than your feet on the floor), on a landing after the last jump that is not on the feet, "
             "if you touch a turning machine, or after {time_limit_s} s.")
    venue = ("A wooden sports floor. The two turning machines stand on the y axis, at y = -{turner_y_m} m and "
             "+{turner_y_m} m (to your right and left), the ropes turning between them across your way. You stand "
             "at x = -{start_x_m} m, y = 0, facing +x, towards the middle of the ropes (x = 0), outside the space "
             "the turning ropes sweep; the centre zone is painted on the floor round the middle.")
    difficulty = ("Neither built-in gait can jump: the robot has to get in between two ropes that sweep the floor "
                  "in turn every half second, then hop again and again in that rhythm, feet off the ground at the "
                  "very moment each rope passes and back on balance for the next. A drift out of the middle or a "
                  "toe left behind catches a rope.")

    def __init__(self):
        super().__init__()
        self._sync()

    def configure(self, params):
        super().configure(params)
        self._sync()

    def _sync(self):
        p = self.p
        p["turner_y_m"] = round(p["turner_distance_m"] / 2, 6)
        p["half_gap_m"] = round(p["hand_gap_m"] / 2, 6)
        p["pass_period_s"] = round(0.5 / p["tempo_rev_s"], 4)
        self.start = (-p["start_x_m"], 0.0, 0.0)
        self.stages = ["entry"] + [f"jump {i}" for i in range(1, int(p["jumps_required"]) + 1)] + ["landing"]

    # ------------------------------------------------------------------ the machines and the ropes
    def _spec(self):
        """The cranks: name -> (centre, phi0, rate rad/s); the ropes: name -> (crank at -y, crank at +y)."""
        p = self.p
        w = 2 * math.pi * p["tempo_rev_s"]
        a0 = math.radians(p["phase_a0_deg"])
        hy, hx, hz = p["turner_distance_m"] / 2, p["hand_gap_m"] / 2, p["hand_height_m"]
        # rope a (cranks at +x) turns with phi increasing (seen from the turner at -y: its right hand, counter-
        # clockwise); rope b (at -x) with phi decreasing, its mirror image half a turn later (phi_b = -phi_a at t = 0)
        cr = {"crank_a_s": ((hx, -hy, hz), a0, w), "crank_a_n": ((hx, hy, hz), a0, w),
              "crank_b_s": ((-hx, -hy, hz), -a0, -w), "crank_b_n": ((-hx, hy, hz), -a0, -w)}
        ropes = {"rope_a": ("crank_a_s", "crank_a_n"), "rope_b": ("crank_b_s", "crank_b_n")}
        return cr, ropes

    def _machine_xml(self):
        p = self.p
        cr, ropes = self._spec()
        chains, eqs = {}, ""
        for name, (sa, sb) in ropes.items():
            # rope a: contype 2, rope b: contype 32; each accepts the other (they can clash), never itself
            ct, ca = (2, 45) if name == "rope_a" else (32, 15)
            col = (0.85, 0.12, 0.10, 1) if name == "rope_a" else (0.10, 0.35, 0.85, 1)
            ch_a, ch_b, e = rope_xml(name, ROPE_N_SEG, p["rope_length_m"], p["rope_diameter_m"],
                                     p["rope_linear_density_kg_m"], contype=ct, conaffinity=ca, rgba=col)
            chains[sa], chains[sb] = ch_a, ch_b
            eqs += e
        bodies, acts = "", ""
        for name, (c, phi0, _) in cr.items():
            # the 90 W gear motor gives motor_torque_nm at one turn per second, its maximum-power point: half its
            # stall torque at half its no-load speed (a DC motor's straight torque-speed line). Modelled as that line:
            # the servo limited at the stall torque, the axle damped by the line's slope (stall / no-load speed)
            stall, w0 = 2 * p["motor_torque_nm"], 2 * 2 * math.pi
            b, a = crank_xml(name, c, phi0, p["crank_radius_m"], p["motor_kp"], p["motor_kv"], stall,
                             rope=chains.get(name, ""), damping=stall / w0)
            bodies += b
            acts += a
        return bodies, acts, eqs

    def _pin0(self, name):
        cr, _ = self._spec()
        c, phi0, _ = cr[name]
        r = self.p["crank_radius_m"]
        return (c[0] + r * math.cos(phi0), c[1], c[2] + r * math.sin(phi0))

    def _preroll(self):
        p = self.p
        cr, ropes = self._spec()
        bodies, acts, eqs = self._machine_xml()
        xml = ('<mujoco><compiler angle="radian" autolimits="true"/><option timestep="0.001" integrator="implicitfast"/>'
               '<worldbody><geom name="floor" type="plane" size="40 20 0.05" '
               f'contype="1" conaffinity="5" friction="1 0.005 0.0001"/>{bodies}</worldbody><equality>{eqs}'
               f'</equality><actuator>{acts}</actuator></mujoco>')
        start = {}
        for name, (sa, sb) in ropes.items():
            start.update(rope_rest_qpos(name, ROPE_N_SEG, p["rope_length_m"], p["rope_diameter_m"] / 2,
                                        self._pin0(sa), self._pin0(sb)))
        drive = TurnerDrive({n: v[2] for n, v in cr.items()}, ramp_s=RAMP_S)
        key = ("double-dutch", tuple(sorted((k, float(v)) for k, v in p.items())))
        return preroll(key, xml, drive, start, PREROLL_S, ROPES, ROPE_N_SEG, p["rope_length_m"],
                       p["rope_diameter_m"]), drive

    def build(self, sc):
        p = self.p
        opt = sc.root.find("option")                     # no MuJoCo fluid model: the ropes' drag is RopeDrag's
        opt.attrib.pop("density", None)
        opt.attrib.pop("viscosity", None)
        hy = p["turner_distance_m"] / 2
        sc.box("gym_floor", (0, 0, 0.0003), (4.0, hy + 1.2, 0.0003), rgba=(0.76, 0.58, 0.38, 1))
        zx, zy = p["zone_half_x_m"], p["zone_half_y_m"]
        for i, (a, b) in enumerate((((-zx, -zy), (zx, -zy)), ((zx, -zy), (zx, zy)), ((zx, zy), (-zx, zy)),
                                    ((-zx, zy), (-zx, -zy)))):
            sc.line(f"zone{i}", a, b, width=0.04, z=0.0009)
        for s in (-1, 1):                                # the machines' posts and frames (fixed)
            y = s * (hy + 0.06)
            sc.geom(sc.wb, f"turner{s:+d}_post", type="box", pos=(0, y, p["hand_height_m"] / 2),
                    size=(p["hand_gap_m"] / 2 + 0.05, 0.04, p["hand_height_m"] / 2), rgba=(0.20, 0.32, 0.65, 1),
                    contype="1", conaffinity="13")
            sc.geom(sc.wb, f"turner{s:+d}_base", type="box", pos=(0, y + s * 0.15, 0.02), size=(0.45, 0.30, 0.02),
                    rgba=(0.20, 0.32, 0.65, 1), contype="1", conaffinity="13")
        bodies, acts, eqs = self._machine_xml()
        for el in ET.fromstring(f"<x>{bodies}</x>"):
            sc.wb.append(el)
        for el in ET.fromstring(f"<x>{eqs}</x>"):
            sc.root.find("equality").append(el)
        for el in ET.fromstring(f"<x>{acts}</x>"):
            sc.root.find("actuator").append(el)
        sc.camera("venue", (3.6, -3.4, 1.8), (-0.4, 0.0, 0.7), fovy=55)
        sc.camera("side", (1.6, -5.4, 1.0), (0.0, 0.0, 0.7), fovy=45)        # along the ropes, past a machine
        sc.camera("close", (2.3, -1.6, 1.1), (0.0, 0.0, 0.55), fovy=50)

    def reset(self, w):
        m, d = w.m, w.d
        state, drive = self._preroll()
        cr, ropes = self._spec()
        q0 = {}
        for name, (q, v) in state.items():
            if name == "floor" or name not in [m.joint(j).name for j in range(m.njnt)]:
                continue
            j = m.joint(name)
            qa, va = int(j.qposadr[0]), int(j.dofadr[0])
            if name in cr:                                # a crank: its angle less whole turns, its target with it
                k = round(drive.angle(name, PREROLL_S) / (2 * math.pi))
                d.qpos[qa] = float(q[0]) - 2 * math.pi * k
                d.qvel[va] = float(v[0])
                q0[name] = drive.angle(name, PREROLL_S) - 2 * math.pi * k
            else:
                d.qpos[qa:qa + len(q)] = q
                d.qvel[va:va + len(v)] = v
        self.drive = TurnerDrive({n: c[2] for n, c in cr.items()}, q0=q0)
        self.drag = RopeDrag(m, ROPES, ROPE_N_SEG, self.p["rope_length_m"], self.p["rope_diameter_m"])

    def before_step(self, w):
        if w.k == 0:                                      # the first physics step's targets and drag
            self.drive.ctrl(w.m, w.d, w.PHYS_DT)
            self.drag.apply(w.d)

    # ------------------------------------------------------------------ the referee
    def referee_reset(self, w, ref):
        m, p = w.m, self.p
        self.fall_z = p["fall_z_m"]
        self.rope_sel = {n: ref.geoms(prefix=n) for n in ROPES}
        self.ropes_any = self.rope_sel["rope_a"] | self.rope_sel["rope_b"]
        self.robot_sel = ref.part("robot")
        self.machines = ref.geoms(prefix="turner") | ref.geoms(prefix="crank_")
        self.nodes = {n: np.array([m.site(f"{n}{i}").id for i in range(ROPE_N_SEG)] + [m.site(f"{n}_end").id])
                      for n in ROPES}
        self.dir = {"rope_a": 1.0, "rope_b": -1.0}       # the way each rope moves along x under the robot
        self.foot_ids = {s: np.flatnonzero(ref.part(f"{s}_foot")) for s in SIDES}
        self.trackers = {"flights": Flights(ref, min_air=0.0), "jumps": 0, "entered": False,
                         "prev": {n: {"left": None, "right": None, "head": None} for n in ROPES},
                         "under": {n: {"left": None, "right": None} for n in ROPES},
                         "over": {n: True for n in ROPES}, "last_flight_t0": None, "passes": []}
        if not hasattr(self, "drive"):                    # (the referee is built before the first reset)
            self.drive = None

    def _in_zone(self, w) -> bool:
        x, y = w.pelvis()[:2]
        return abs(x) <= self.p["zone_half_x_m"] and abs(y) <= self.p["zone_half_y_m"]

    def actuate(self, w, ref):
        if self.drive is not None:
            self.drive.ctrl(w.m, w.d, ref.time + w.PHYS_DT)   # the turners' targets for the next physics step
            self.drag.apply(w.d)                              # the air on the ropes for the next physics step

    def substep(self, w, ref):
        p, tr, d, r = self.p, self.trackers, w.d, w.robot
        fl = tr["flights"]
        landed = fl.update()
        if ref.touching(self.ropes_any, self.robot_sel):
            return ref.fail("a rope touched the robot (a miss)", parts=sorted(ref.parts_touching(self.ropes_any)))
        if ref.touching(self.machines, self.robot_sel):
            return ref.fail("touched a turning machine")
        if ref.has(self.stages[-2]):                     # the last jump is in: the landing
            if landed is not None:
                if set(landed["landing_parts"]) <= {"left_foot", "right_foot"}:
                    if ref.stage("landing"):
                        ref.succeed()
                else:
                    ref.fail("the landing was not on the feet", parts=landed["landing_parts"])
            return
        refs = {s: d.site_xpos[r.foot_site[s]] for s in SIDES}
        refs["head"] = d.site_xpos[r.head_site]
        hz = p["hand_height_m"]
        keys = ("left", "right", "head")
        ys = [float(refs[k][1]) for k in keys]
        for n in ROPES:
            nodes = d.site_xpos[self.nodes[n]]
            sgn = self.dir[n]
            pts = dict(zip(keys, rope_points_at_ys(nodes, ys)))
            for key in ("left", "right"):
                q, pt = refs[key], pts[key]
                if pt is None:
                    tr["prev"][n][key] = None
                    continue
                sx = sgn * float(pt[0] - q[0])            # < 0: the rope is on the side it comes from
                prev, tr["prev"][n][key] = tr["prev"][n][key], sx
                if prev is None or not (prev < 0.0 <= sx) or pt[2] > hz:
                    continue                              # (a crossing above the axis is not a pass under)
                sole = zspan(w, self.foot_ids[key])[0]
                if pt[2] + p["rope_diameter_m"] / 2 >= sole:
                    return ref.fail("a rope passed through the robot", rope=n, foot=key,
                                    rope_z=round(float(pt[2]), 3), sole_z=round(sole, 3))
                if not ref.airborne():
                    return ref.fail("a rope passed under a foot that was on the ground", rope=n, foot=key)
                tr["under"][n][key] = round(ref.time, 4)
                if tr["under"][n]["left"] is not None and tr["under"][n]["right"] is not None:
                    tr["under"][n] = {"left": None, "right": None}
                    counted = (self._in_zone(w) and tr["over"][n] and fl.cur is not None
                               and fl.cur["t0"] != tr["last_flight_t0"])
                    tr["over"][n] = False
                    ref.event("under", rope=n, counted=bool(counted))
                    if counted:
                        tr["jumps"] += 1
                        tr["last_flight_t0"] = fl.cur["t0"]
                        tr["passes"].append([n, round(ref.time, 4)])
                        ref.metrics["jumps"] = tr["jumps"]
                        ref.stage(f"jump {tr['jumps']}")
            # over the head (the other way round, above the axis): the rope has come round
            q, pt = refs["head"], pts["head"]
            if pt is not None and pt[2] > hz:
                sx = -sgn * float(pt[0] - q[0])
                hp = tr["prev"][n].get("head_over")
                tr["prev"][n]["head_over"] = sx
                if hp is not None and hp < 0.0 <= sx:
                    top = ref.robot_span((0.0, 0.0, 1.0))[1]
                    if pt[2] - p["rope_diameter_m"] / 2 <= top:
                        return ref.fail("a rope passed through the robot", rope=n, rope_z=round(float(pt[2]), 3))
                    tr["over"][n] = True
            else:
                tr["prev"][n]["head_over"] = None

    def step(self, w, ref):
        tr = self.trackers
        inz = self._in_zone(w)
        if not tr["entered"] and inz:
            tr["entered"] = True
            ref.stage("entry")
        elif tr["entered"] and not inz:
            return ref.fail("the robot left the centre zone", pelvis=[round(float(x), 3) for x in w.pelvis()[:2]])

    def privileged(self, w):
        cr, _ = self._spec()
        d = w.d
        return {"pelvis": w.pelvis().tolist(),
                "ropes": {n: d.site_xpos[self.nodes[n]].round(4).tolist() for n in ROPES},
                "crank_angle_rad": {n: float(d.qpos[w.m.joint(n).qposadr[0]]) + cr[n][1] for n in cr},
                "crank_rate_rad_s": {n: cr[n][2] for n in cr}, "rope_axis_z": self.p["hand_height_m"],
                "jumps": self.trackers["jumps"], "entered": self.trackers["entered"],
                "over_since_last_pass": dict(self.trackers["over"])}
