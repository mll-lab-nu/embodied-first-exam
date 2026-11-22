"""Badminton, the singles service (BWF Laws of Badminton, Laws 1-4, 9, 10 and 13): standing in your right service
court, let the shuttle go from your left hand and hit it, base first, with the racket held in your right hand, the
whole shuttle below 1.15 m, the racket moving forwards, over the net into the receiver's right service court.

Official setting: the BWF court (13.40 m x 6.10 m, the singles side lines 5.18 m apart, the short service lines 1.98 m
from the net, 40 mm lines), the net (1.524 m at the centre, 1.55 m at the posts on the doubles side lines, 0.76 m
deep; a net of cord hung from its tensioned top cord, a mechanism: build_net), a feathered shuttle of Law 2 that flies in the venue's air, and a racket of Law 4 as a FREE body held only by
the contact and friction of the right hand, the G1's own Dex3-1 three-finger hand (rfo/realhand.py, "dex3", at the
device's joint torques); the shuttle starts held by its skirt in the left Dex3-1. Nothing is scaled to the robot.

Where the numbers come from:
* the court, the net and the posts: Law 1 (all lines are part of the area they bound; the centre line is shared by the
  right and the left service court); the singles service court: Law 9 / 10 and the court diagram (from the short
  service line to the back boundary line, between the centre line and the singles side line);
* the shuttle: Law 2 (16 feathers 62-70 mm long whose tips form a circle 58-68 mm across, a cork base 25-28 mm across
  with a rounded bottom, 4.74-5.50 g). Modelled as a cork sphere (26 mm, 2.9 g) and a 16-sided conical skirt (from
  25 mm across at the base to 64 mm at the tips, 62 mm long; 1.7 g of feathers and 0.5 g of thread and glue), 5.1 g
  in all, its centre of mass 28.5 mm behind the cork's tip;
* its flight: MuJoCo's ellipsoid fluid model in the venue's air (scene.AIR) on one drag body centred on the skirt,
  31.5 mm behind the centre of mass, so the shuttle turns to fly cork first by itself (weathercock stability). Its
  blunt-drag coefficient (0.275, a drag coefficient of 0.55 on the skirt's 64 mm mouth) is set so that the terminal
  velocity in still air is 6.80 m/s, the value measured by Peastrel, Lynch and Armenti, "Terminal velocity of a
  shuttlecock in vertical fall", Am. J. Phys. 48, 511 (1980); a fast shuttle's speed then falls by a factor e every
  V_t^2 / g = 4.7 m of flight (the quadratic-drag picture of shuttle flight of Cohen, Darbois Texier, Quere and
  Clanet, "The physics of badminton", New J. Phys. 17, 063001 (2015)). Measured in this model: the fall from rest
  (6.795 m/s) and a level shuttle launched at 30 m/s (22.8 m/s after 1.30 m, 13.3 m/s after 3.87 m: the point-mass
  quadratic-drag values within 0.3 %). Law 3's speed test (a full underhand stroke from one back line lands 530-990 mm
  short of the other back line) is met by this shuttle when it leaves 1 m above the back line at 30 degrees at
  52-54 m/s, at 45 degrees at 72-80 m/s. Nothing published fixes how fast a shuttle's wobble dies out after a hit;
  the drag body's angular-drag coefficient (80) makes a shuttle launched at 15 m/s 60 degrees off its path line up
  within 20 degrees in 0.5 m, and one launched skirt first turn over within 0.16 s;
* the racket: Law 4 (at most 680 mm long and 230 mm wide, the strung area at most 280 mm x 220 mm); a 0.67 m, 85 g
  racket (a "3U"-"4U" racket: 80-89 g), its balance point 0.30 m from the butt, the strung area 270 mm x 210 mm, a
  handle of 26 mm x 22 mm flats, 0.20 m long; the strings meet the shuttle with a restitution of 0.5 (a rigid racket:
  the string bed's trampoline is not modelled); hitting with the frame is legal;
* the service: Law 9.1 (both feet in the service court, not on its lines, some part of each in contact with the
  surface in a stationary position from the start of the service until it is delivered; the racket first hits the
  base of the shuttle; the whole shuttle below 1.15 m at the instant of the hit; the racket's movement continues
  forwards from the start of the service until it is delivered; the shuttle's flight is upwards from the racket, over
  the net, into the receiver's service court; the server must not miss the shuttle), Law 9.2 (the start of the
  service: the first forward movement of the server's racket head), Law 10 (singles: at 0 the server serves from the
  right service court to the diagonally opposite one), Law 13 (faults: the shuttle landing outside the boundary
  lines, passing through or under the net, failing to pass the net, touching a player, caught and held on the racket
  and slung, hit twice; a player touching the net or its supports with racket, person or dress). A service that
  touches the net and lands in the court is good.

Singles (not doubles): the service court is long (to the back boundary line) and narrow (to the singles side line).
The robot is the G1: its height suits the 1.15 m service height (the rule's height is about a human's lower ribs; the
G1's racket head swings through it), and an 85 g racket suits its 5 N m wrists.
"""
import math
import xml.etree.ElementTree as ET

import mujoco
import numpy as np

from rfo.referee import Crossing, Touch
from rfo.scene import AIR, HITTABLE, VISUAL, bounce_solref, fmt
from rfo.task import TaskBase
# A rigid racket (graphite frame and shaft, strung bed)'s contact with the robot, the venue's fixtures and the other
# props (the ground keeps its own: rfo/world.py GROUND_SOLMIX): the stiff contact of the core's shells (rfo/world.py
# SHELL_CONTACT: solref 0.004 s, solimp 0.99 0.999 0.0005, from Embodied Olympics' weightlifting fix, a rigid prop on the
# robot's aluminium) with a solmix that wins over a default- contact geom; a ball (priority 1) keeps its own bounce.
# With MuJoCo's default soft contact (solref 0.02 1, solimp 0.9 0.95) it sank 48 mm into the hand, 80 mm into the
# floor (stress test).
from rfo.world import SHELL_CONTACT as RIGID  # noqa: E402

# ------------------------------------------------------------------------------------------------ the court (Law 1)
LENGTH, WIDTH, SINGLES, SHORT, DOUBLES_LONG = 13.40, 6.10, 5.18, 1.98, 0.76
LINE = 0.040
NET_CENTRE, NET_POST, NET_DEPTH = 1.524, 1.55, 0.76
POST_Y = WIDTH / 2                              # the posts stand on the doubles side lines (Law 1.5)
POST_R = 0.02
DEAD = "-4e5 -1000"                             # a shuttle on a post: stiff and nearly dead
# The net's numbers (the mechanism: build_net below):
NET_MASS = 0.45                                 # kg: a 6.1 m competition net of 19 mm nylon mesh with its tape and cord
#                                                 (Harrod Sport No.3 Competition Badminton Net, the maker's listing)
NET_AREA_DENSITY = NET_MASS / (WIDTH * NET_DEPTH)
# Law 1.9: the cord "firmly stretched, flush with the tops of the posts"; the net's top sags from 1.55 m at the posts to
# 1.524 m at the centre (Law 1.10) under its own weight: a uniformly loaded cord sags w L^2 / (8 T), so the tension is
# m g L / (8 sag) (about 130 N)
NET_TENSION = NET_MASS * 9.81 * WIDTH / (8 * (NET_POST - NET_CENTRE))
NET_SOLIDITY = 2 * 0.8 / 19                     # fine cord about 0.8 mm thick, 19 mm mesh (Law 1.6: 15-20 mm)
NET_BAND_M = 0.075                              # Law 1.8: a 75 mm white tape doubled over the cord
NET_STRIP_M, NET_SEGMENTS = 0.5, 2


def net_top(dy: float) -> float:
    """The height of the net's top edge dy metres from the centre: the cord's sag under the net's weight, a parabola
    from NET_CENTRE at the centre to NET_POST at the posts."""
    u = min(abs(dy), POST_Y) / POST_Y
    return NET_CENTRE + (NET_POST - NET_CENTRE) * u * u


# ---------------------------------------------------------------------------------------- the net (a mechanism)
# The net is a real one, a mechanism of bodies on joints, nothing scripted: the cable at its top, tensioned between the
# posts, is a string of beads (one per strip of net, NET_STRIP_M wide), each on a slide joint across the net (x), coupled
# to its neighbours and to the posts by springs of stiffness T / spacing (fixed tendons: a taut string's transverse
# stiffness, linearised); under each bead hangs that strip of mesh as a chain of NET_SEGMENTS rigid panels on hinges
# along the cable (a hanging sheet: it swings away from a ball and back under its weight; the strips are not coupled to
# each other below the cable, and the mesh does not stretch). Masses from the net's mass per area and the cable's per
# length; air drag on the mesh by its solidity (Loland's net drag formula, C_d = 0.04 + (-0.04 + 0.33 S + 6.54 S^2 -
# 4.88 S^3) for a net square to the flow; Loland 1991, "Current forces on and flow through fish farms", NTH Trondheim);
# the beads have 5 % of critical damping (the cable's internal friction, not measured). A ball meets the twine with
# its own rule-book restitution (an explicit pair whose spring is stiff enough that a fast ball does not pass through
# the 2 cm panel); what absorbs it is the net's own motion.
NET_SEG_HALF_T = 0.01                           # m: each panel's collision box is 2 cm thick
NET_GAP = 0.01                                  # m: between neighbouring strips (a ball cannot pass)


def net_drag_cd(solidity: float) -> float:
    s = solidity
    return 0.04 + (-0.04 + 0.33 * s + 6.54 * s ** 2 - 4.88 * s ** 3)


def build_net(sc, net, top, half_span, anchor_y, bottom, strip_w, n_seg, area_density, cable_density, tension,
              strap_k, band_h, solidity, balls=(), ball_solref=None, ball_friction="0.3 0.3 0.005 0.0001 0.0001",
              mesh_rgba=(0.1, 0.1, 0.1, 0.55), band_rgba=(0.97, 0.97, 0.97, 1)):
    """The net under the static body `net` (its frame: x across the net, y along it, z up from the floor): strips of
    width ~strip_w between y = -half_span and +half_span, the cable anchored at y = +-anchor_y (the posts); top(y) the
    height of the band's top edge, bottom(y) the mesh's lower edge. strap_k (N/m) is an extra spring on the two middle
    beads together (tennis' centre strap). Geoms: net_band<i> (the band over the cable) and net_mesh<i>_<k>."""
    root = sc.root
    tendons = root.find("tendon")
    if tendons is None:
        tendons = ET.SubElement(root, "tendon")
    contact = root.find("contact")
    n = max(2, int(round(2 * half_span / strip_w)))
    w = 2 * half_span / n
    half_w = w / 2 - NET_GAP / 2
    # MuJoCo's blunt drag is C rho A |v| v on the equivalent ellipsoid's projected area (pi a b); a panel's outline is
    # 4 a b: C = C_d / 2 * 4 / pi
    mesh_fluid = (net_drag_cd(solidity) / 2 * 4 / math.pi, 0.0, 0.0, 0.0, 0.0)
    band_fluid = (1.2 / 2 * 4 / math.pi, 0.0, 0.0, 0.0, 0.0)          # the band: a solid strip (flat plate, C_d 1.2)
    T2 = (2 * NET_SEG_HALF_T) ** 2                                   # (the panels' thickness, for the inertia)
    k_link = tension / w
    k_end = tension / (anchor_y - half_span + w / 2)
    geoms = []
    for i in range(n):
        yc = -half_span + (i + 0.5) * w
        zt = top(yc)
        slope = (top(yc + 1e-4) - top(yc - 1e-4)) / 2e-4
        a = math.atan(slope)
        h_mesh = zt - band_h - bottom(yc)
        hs = h_mesh / n_seg
        m_seg = area_density * w * hs
        m_bead = area_density * w * band_h + cable_density * w
        k = 2 * k_link if 0 < i < n - 1 else k_link + k_end
        if strap_k and i in (n // 2 - 1, n // 2) and n % 2 == 0:
            k += strap_k / 2
        m_eff = m_bead + n_seg * m_seg                                  # the strip moves with its bead
        c = 2 * 0.05 * math.sqrt(k * m_eff)
        bead = sc.body(f"net_cord{i}", (0.0, yc, zt - band_h / 2), parent=net)
        extra = 0.0
        if i in (0, n - 1):
            extra = k_end
        if strap_k and i in (n // 2 - 1, n // 2) and n % 2 == 0:
            extra += strap_k / 2
        ET.SubElement(bead, "joint", name=f"net_cord{i}", type="slide", axis="1 0 0", stiffness=f"{extra:.6g}",
                      springref="0", damping=f"{c:.6g}")
        ET.SubElement(bead, "inertial", pos="0 0 0", mass=f"{m_bead:.6g}",
                      diaginertia=f"{m_bead * (w * w + band_h ** 2) / 12:.6g} {m_bead * (band_h ** 2 + T2) / 12:.6g} "
                                  f"{m_bead * (w * w + T2) / 12:.6g}")
        sc.geom(bead, f"net_band{i}", type="box", size=(NET_SEG_HALF_T, half_w, band_h / 2),
                quat=(math.cos(a / 2), math.sin(a / 2), 0.0, 0.0), rgba=band_rgba, mass=0, fluidshape="ellipsoid",
                fluidcoef=band_fluid, **HITTABLE)
        geoms.append(f"net_band{i}")
        parent, z0 = bead, -band_h / 2
        for kk in range(n_seg):
            seg = sc.body(f"net_seg{i}_{kk}", (0.0, 0.0, z0), parent=parent)
            # a panel folds against the one above it at most to the horizontal: the mesh is one sheet, tied along its
            # sides to the neighbouring strips (not modelled), so a strip cannot turn over; free hinges let a hit spin
            # a light panel round its cord at 124 rad/s (stress test). The limit is the sheet's ties, taut:
            # stiff (the core's shells' solref 0.004 s, solimp 0.99 0.999; MuJoCo's default limit let a hand push a
            # panel 0.75 rad past it)
            ET.SubElement(seg, "joint", name=f"net_seg{i}_{kk}", type="hinge", axis="0 1 0", damping="1e-4",
                          range=f"{-math.pi / 2:.6g} {math.pi / 2:.6g}", solreflimit="0.004 1",
                          solimplimit="0.99 0.999 0.0005 0.5 2")
            ET.SubElement(seg, "inertial", pos=f"0 0 {-hs / 2:.6g}", mass=f"{m_seg:.6g}",
                          diaginertia=f"{m_seg * (w * w + hs * hs) / 12:.6g} {m_seg * (hs * hs + T2) / 12:.6g} "
                                      f"{m_seg * (w * w + T2) / 12:.6g}")
            sc.geom(seg, f"net_mesh{i}_{kk}", type="box", pos=(0.0, 0.0, -hs / 2), size=(NET_SEG_HALF_T, half_w, hs / 2),
                    rgba=mesh_rgba, mass=0, fluidshape="ellipsoid", fluidcoef=mesh_fluid, **HITTABLE)
            geoms.append(f"net_mesh{i}_{kk}")
            parent, z0 = seg, -hs
        if i < n - 1:
            t = ET.SubElement(tendons, "fixed", name=f"net_cable{i}", stiffness=f"{k_link:.6g}", springlength="0")
            ET.SubElement(t, "joint", joint=f"net_cord{i}", coef="1")
            ET.SubElement(t, "joint", joint=f"net_cord{i + 1}", coef="-1")
    for b in balls:
        for g in geoms:
            ET.SubElement(contact, "pair", name=f"{b}_{g}", geom1=b, geom2=g, condim="3", friction=ball_friction,
                          solref=ball_solref, solimp="0.99 0.99 0.001")
    return dict(n=n, strip_w=w, k_link=k_link, k_end=k_end, geoms=geoms)


# --------------------------------------------------------------------------------------------- the shuttle (Law 2)
# Along the shuttle's axis, s from the cork's tip (s = 0) towards the skirt's tips.
CORK_R, CORK_M = 0.013, 0.0029
SKIRT_S0, SKIRT_S1, SKIRT_R0, SKIRT_R1 = 0.022, 0.084, 0.0125, 0.032
FEATHERS_M, THREAD_M, THREAD_S = 0.0017, 0.0005, 0.035
N_FEATHERS = 16
SHUTTLE_M = CORK_M + FEATHERS_M + THREAD_M      # 5.1 g (Law 2.6: 4.74-5.50 g)
V_TERMINAL = 6.80                               # m/s (Peastrel et al. 1980)
CP_S, CP_AXES = 0.060, (SKIRT_R1, SKIRT_R1, 0.031)    # the drag body: centred on the skirt


def shuttle_mass_model():
    """The shuttle's centre of mass (s) and its inertia about it (axial, transverse), from the cork (a solid sphere),
    the feathers (16 straight rods of uniform mass from the base ring to the tip circle) and the thread ring."""
    pts = [(CORK_M, CORK_R, 0.0, 0.4 * CORK_M * CORK_R ** 2, 0.4 * CORK_M * CORK_R ** 2)]   # (m, s, r, Iax, Itr)
    n = 40
    for i in range(n):
        f = (i + 0.5) / n
        s = SKIRT_S0 + f * (SKIRT_S1 - SKIRT_S0)
        r = SKIRT_R0 + f * (SKIRT_R1 - SKIRT_R0)
        mi = FEATHERS_M / n
        pts.append((mi, s, r, mi * r * r, mi * r * r / 2))          # a ring of radius r: Iax = m r^2, Itr = m r^2 / 2
    pts.append((THREAD_M, THREAD_S, SKIRT_R0 + 0.002, THREAD_M * (SKIRT_R0 + 0.002) ** 2,
                THREAD_M * (SKIRT_R0 + 0.002) ** 2 / 2))
    M = sum(p[0] for p in pts)
    sc = sum(p[0] * p[1] for p in pts) / M
    iax = sum(p[3] for p in pts)
    itr = sum(p[4] + p[0] * (p[1] - sc) ** 2 for p in pts)
    return sc, iax, itr


S_COM, I_AX, I_TR = shuttle_mass_model()
# the drag body's blunt-drag coefficient: MuJoCo's blunt drag is C rho A |v| v (A the projected area of the drag
# ellipsoid, here pi a^2 along the axis), so the terminal velocity V_t is reached at C = m g / (rho A V_t^2)
SHUTTLE_CB = SHUTTLE_M * 9.81 / (AIR["density"] * math.pi * CP_AXES[0] * CP_AXES[1] * V_TERMINAL ** 2)
SHUTTLE_FLUID = (SHUTTLE_CB, 0.25, 80.0, 0.0, 0.0)    # blunt, slender, angular drag (see the docstring); no lift
SHUTTLE_SOLREF = bounce_solref(0.3, 785.0)      # the shuttle on the floor and the body: e = 0.3
SHUTTLE = "shuttle"


def z_of(s: float) -> float:
    """Body z of the point s along the axis (body +z points from the skirt to the cork; the origin at the centre of
    mass)."""
    return S_COM - s


def build_shuttle(sc, pos=(0.5, 0.3, 1.0)) -> None:
    b = sc.body(SHUTTLE, pos, free=True)
    ET.SubElement(b, "inertial", pos="0 0 0", mass=f"{SHUTTLE_M:.6g}", diaginertia=f"{I_TR:.6g} {I_TR:.6g} {I_AX:.6g}")
    ring = []
    for s, r in ((SKIRT_S0, SKIRT_R0), (SKIRT_S1, SKIRT_R1)):
        for i in range(N_FEATHERS):
            a = 2 * math.pi * (i + 0.5) / N_FEATHERS
            ring += [r * math.cos(a), r * math.sin(a), z_of(s)]
    ET.SubElement(sc.root.find("asset"), "mesh", name="shuttle_skirt", vertex=" ".join(f"{c:.6f}" for c in ring))
    kw = dict(condim="3", priority="1", solref=SHUTTLE_SOLREF, solimp="0.95 0.99 0.001", friction="0.4 0.005 0.0001")
    sc.geom(b, "shuttle_cork", type="sphere", size=(CORK_R,), pos=(0, 0, z_of(CORK_R)), mass="0",
            rgba=(0.97, 0.97, 0.95, 1), **kw, **HITTABLE)
    sc.geom(b, "shuttle_skirt", type="mesh", mesh="shuttle_skirt", mass="0", rgba=(1.0, 1.0, 0.97, 0.85), **kw,
            **HITTABLE)
    sc.geom(b, "shuttle_band", type="cylinder", size=(SKIRT_R0 + 0.002, 0.004), pos=(0, 0, z_of(THREAD_S)), mass="0",
            rgba=(0.15, 0.25, 0.75, 1), **VISUAL)
    # the drag body: no contact, no mass, the fluid forces only (the body's other geoms have none: MuJoCo's
    # ellipsoid model then applies to this geom alone, and the inertia-box model to nothing)
    sc.geom(b, "shuttle_air", type="ellipsoid", size=CP_AXES, pos=(0, 0, z_of(CP_S)), mass="0", rgba=(1, 1, 1, 0),
            group="5", fluidshape="ellipsoid", fluidcoef=SHUTTLE_FLUID, **VISUAL)


def shuttle_top(w) -> float:
    """The height of the shuttle's highest point (the cork's top or a point of the tip circle)."""
    d, b = w.d, w.m.body(SHUTTLE).id
    R = d.xmat[b].reshape(3, 3)
    c = d.xpos[b]
    ax = R[:, 2]                                # from the skirt to the cork
    cork = c[2] + ax[2] * z_of(CORK_R) + CORK_R
    rim = c[2] + ax[2] * z_of(SKIRT_S1) + SKIRT_R1 * math.sqrt(max(0.0, 1.0 - ax[2] ** 2))
    return float(max(cork, rim))


# --------------------------------------------------------------------------------------------- the racket (Law 4)
# The racket's frame: the butt at the origin, the shaft along +z, the strings' normal along x.
RACKET = dict(length_m=0.670, width_m=0.230, strung_length_m=0.270, strung_width_m=0.210, mass_kg=0.085,
              handle_length_m=0.20, handle_flats_m=(0.026, 0.022), head_centre_z_m=0.525, restitution=0.5)
HEAD_A, HEAD_B = 0.140, 0.110                   # the frame's centre line (a 5 mm tube): 0.29 x 0.23 m outside
STRINGS_A, STRINGS_B = RACKET["strung_length_m"] / 2, RACKET["strung_width_m"] / 2
STRINGS_HALF = 0.004                            # the strings' collision plate: 8 mm thick (a fast cork must not tunnel)
STRINGS_SOLREF = bounce_solref(0.5, 785.0)      # 785 rad/s (4 ms on the strings), the damping for e = 0.5
GRIP_Z = 0.040                                  # a point on the handle (from the butt): the racket_grip site
# Where the racket and the shuttle sit in the hands (the grasp frame, rfo.realhand: x out of the palm, z along the
# fingers, y = z x x): the racket's handle across the right palm along y (the head beyond the index finger's side),
# the butt racket_butt_out_m before the grasp centre, the strings' normal the palm's; the shuttle's axis along the left
# hand's y (the cork towards the side that is lower at the start: down, the left palm facing in), held round its
# skirt at PINCH_S from the cork's tip, its axis shuttle_palm_off_m out of the palm (a search for the hold)
GRIP = dict(racket_butt_out_m=0.05, racket_palm_off_m=0.0, shuttle_palm_off_m=0.012)
RACKET_CLOSURE = 1.0                            # the start's grip commands: the racket held at the full command,
SHUTTLE_CLOSURE = 1.0                           # the shuttle's skirt too (the fingers stop on it)
PINCH_S = 0.060                                 # where the left hand holds the skirt (s from the cork's tip)
# the start pose of the arms (left: shoulder pitch, roll, yaw, elbow, wrist roll, pitch, yaw; right: the same)
START_LEFT = np.array([0.0, 0.1, 0.0, 0.0, 0.0, 0.0, 0.0])      # (the left palm facing in: the shuttle hangs)
START_RIGHT = np.array([0.0, -0.1, 0.0, 0.0, 0.0, 1.0, 0.0])


def build_racket(sc, pos=(0.3, -0.4, 0.8)) -> None:
    b = sc.body("racket", pos, free=True)
    zc = RACKET["head_centre_z_m"]
    hx, hy = RACKET["handle_flats_m"][0] / 2, RACKET["handle_flats_m"][1] / 2
    sc.geom(b, "racket_handle", type="box", pos=(0, 0, RACKET["handle_length_m"] / 2),
            size=(hx, hy, RACKET["handle_length_m"] / 2), mass=0.040, rgba=(0.12, 0.12, 0.14, 1), condim="4",
            friction="1.0 0.01 0.0001", **HITTABLE, **RIGID)
    sc.geom(b, "racket_shaft", type="capsule", fromto=(0, 0, RACKET["handle_length_m"], 0, 0, zc - HEAD_A),
            size=(0.0035,), mass=0.008, rgba=(0.75, 0.75, 0.8, 1), **HITTABLE, **RIGID)
    n = 24
    ring = [(HEAD_B * math.sin(2 * math.pi * i / n), zc + HEAD_A * math.cos(2 * math.pi * i / n)) for i in range(n)]
    for i in range(n):
        y0, z0 = ring[i]
        y1, z1 = ring[(i + 1) % n]
        sc.geom(b, f"racket_frame{i}", type="capsule", fromto=(0, y0, z0, 0, y1, z1), size=(0.005,), mass=0.030 / n,
                rgba=(0.1, 0.25, 0.8, 1), **HITTABLE, **RIGID)
    m = 32
    pts = [(STRINGS_B * math.sin(2 * math.pi * i / m), zc + STRINGS_A * math.cos(2 * math.pi * i / m))
           for i in range(m)]
    ET.SubElement(sc.root.find("asset"), "mesh", name="racket_strings",
                  vertex=" ".join(f"{c:.5f}" for x in (-STRINGS_HALF, STRINGS_HALF) for y, z in pts for c in (x, y, z)))
    sc.geom(b, "racket_strings", type="mesh", mesh="racket_strings", mass=0.007, rgba=(0.95, 0.95, 0.95, 0.5),
            friction="0.4 0.005 0.0001", **HITTABLE, **RIGID)
    # The strings' and the frame's bounce (STRINGS_SOLREF: 785 rad/s, e = 0.5) is the shuttle's contact with them only:
    # explicit pairs (the shuttle's own contact with the racket excluded). As the geoms' own contact it also held for
    # the hand, the floor and the robot, where a racket twisted in the hand took up to 160 kN and 595 J and flew off
    # at 32 m/s (stress test); everywhere else the racket is a rigid graphite frame (RIGID).
    contact = sc.root.find("contact")
    ET.SubElement(contact, "exclude", body1=SHUTTLE, body2="racket")
    for g in ["racket_strings"] + [f"racket_frame{i}" for i in range(n)]:
        mu = "0.4" if g == "racket_strings" else "1"
        for s in ("cork", "skirt"):
            ET.SubElement(contact, "pair", name=f"{SHUTTLE}_{s}_{g}", geom1=f"{SHUTTLE}_{s}", geom2=g, condim="3",
                          friction=f"{mu} {mu} 0.005 0.0001 0.0001", solref=STRINGS_SOLREF, solimp="0.95 0.99 0.001")
    ET.SubElement(b, "site", name="racket_head", pos=fmt((0, 0, zc)), size="0.005", group="4")
    ET.SubElement(b, "site", name="racket_grip", pos=fmt((0, 0, GRIP_Z)), size="0.005", group="4")


# -------------------------------------------------------------------------------------------------- the texts' help
FAULT_FEET = "foot fault"


class Task(TaskBase):
    name = "badminton-serve"
    title = "Badminton: singles service"
    category = "basketball-and-rackets"
    robot = "unitree_g1"
    rulebook = ("BWF Laws of Badminton (BWF Statutes, Section 4.1, the edition in force in 2025): Law 1 (the court "
                "and the court equipment: 13.40 m x 6.10 m, 40 mm lines that are part of the area they bound, the "
                "singles side lines 5.18 m apart, the short service lines 1.98 m from the net; the net 1.524 m high "
                "at the centre and 1.55 m over the doubles side lines, 760 mm deep; the posts on the doubles side "
                "lines), Law 2 (the shuttle: 16 feathers, a cork base 25-28 mm across, 4.74-5.50 g), Law 3 (testing a "
                "shuttle for speed), Law 4 (the racket: at most 680 mm long and 230 mm wide), Law 9 (the service: 9.1 "
                "a correct service, 9.2 its start), Law 10 (singles: the service courts), Law 13 (faults)")
    deviations = [
        "Laws 7, 8, 10.2-10.3, 11 (the toss, the scoring, the rally, the receiver): one service only, with no "
        "receiver; a fault ends the attempt as a failure, a correct service that lands in the receiver's service "
        "court is the success; singles at the score 0 (so from the right service court, into the diagonally opposite "
        "one)",
        "Law 9.1 (no undue delay; the receiver ready): there is no receiver; the service may come at any time within "
        "the episode",
        "Law 9.2 (the start of the service is the first forward movement of the server's racket head once the players "
        "have taken their positions): taking position cannot be told from the robot's other arm movements; made "
        "measurable: a forward movement of the racket head starts when its speed towards the net rises above "
        "{start_speed_m_s} m/s and lasts until that speed falls below {stop_speed_m_s} m/s; the service starts at the "
        "earlier of the release of the shuttle and the start of the head's forward movement that brings it to the "
        "hit; a forward movement of the head that starts after the release and stops before the hit is a fault (Law "
        "9.1: the racket's movement continues forwards until the service is delivered)",
        "Law 9.1 (some part of both feet in contact with the court in a stationary position): made measurable: from "
        "the start of the service to the hit each foot touches the floor (a gap of at most {foot_gap_s} s, the "
        "chatter of a contact, still counts as touching) and moves at most {foot_move_m} m",
        "Law 9.1 (the server lets go of the shuttle and hits it): the shuttle starts held by its feathers in the "
        "left hand (the G1's three-finger hand) and is let go by opening it; it counts as let go once it has touched "
        "nothing of yours for {clear_s} s (the release is the moment it came free), so that the fingers' last brush "
        "as they open "
        "is part of the holding; so that the hand does not throw the service, the shuttle may move at most "
        "{drop_max_speed_m_s} m/s when it reaches the racket and must leave it faster than it came; one release per "
        "service (a shuttle that has been let go may be touched by nothing of yours but the racket)",
        "Law 9.1 (the server's racket initially hits the base of the shuttle): judged at the physics step (1 ms) of "
        "the racket's first contact: the cork base must be touching the racket then (the feathers may touch it in the "
        "same step)",
        "Law 9.1 (the server's racket): the racket must be held in the right hand throughout the attempt: it counts "
        "as held while it touches the right hand's fingers and its thumb or palm, and a break of at most "
        "{hold_gap_s} s (the contact chatter of a fast swing) is still held; the hands are the G1's own Dex3-1 "
        "three-finger hands at the device's joint torques",
        "Law 13 ('caught and held on the racket and then slung', 'hit twice'): made measurable: racket contacts less "
        "than {retouch_gap_s} s apart are one hit, a later one is a second hit, and a contact longer than "
        "{max_touch_s} s is a carry",
        "Law 9.1 (the flight upwards from the racket): judged when the hit is over ({retouch_gap_s} s after its last "
        "contact): the shuttle is then rising",
        "Law 13 (the shuttle landing outside the boundary lines; lines are in): the landing point is where the "
        "shuttle first touches the floor",
        "Law 4 (the racket): a rigid racket (no string-bed deflection, no frame flex); its strings meet the shuttle "
        "with a restitution of {string_restitution}",
        "Law 1 (the net): a net of cord hung from its tensioned top cord, modelled as strips of mesh "
        f"{NET_STRIP_M:g} m wide, each a chain of {NET_SEGMENTS} rigid panels 2 cm thick hinged under the tape, the tape "
        "and cord a string of beads across the net (the net's mass, its sag and the cord's tension as in the venue "
        "text); the strips are not joined to each other below the cord and the mesh does not stretch; a shuttle meets "
        "the mesh with its own contact (it cannot pass through it)",
        "the hall's air: still (no draught), at sea level and 15 C; the shuttle's spin about its axis is not driven "
        "by its feathers",
    ]
    time_limit_s = 15.0
    fall_z = 0.35
    start = (0.0, 0.0, 0.0)
    stages = ["release", "hit", "over the net", "in"]
    params = dict(
        court_length_m=LENGTH, court_width_m=WIDTH, singles_width_m=SINGLES, short_service_m=SHORT,
        doubles_long_service_m=DOUBLES_LONG, line_width_m=LINE, net_centre_m=NET_CENTRE, net_post_m=NET_POST,
        net_depth_m=NET_DEPTH,
        net_x_m=2.45, centre_y_m=0.45,                         # the court in the robot's starting frame
        max_hit_height_m=1.15, start_speed_m_s=0.50, stop_speed_m_s=0.10, foot_move_m=0.03, foot_gap_s=0.02,
        drop_max_speed_m_s=4.0, clear_s=0.03, retouch_gap_s=0.03, max_touch_s=0.02, hold_gap_s=0.05,
        string_restitution=RACKET["restitution"], landing_gap_s=0.02, fall_z_m=0.35)

    sentence = ("Serve: standing in your right service court, let the shuttle go from your left hand and hit it with "
                "the racket in your right hand, base first and below 1.15 m, over the net into the receiver's service "
                "court diagonally opposite.")
    rules = (
        "The court is the BWF court: {court_length_m} m long and {court_width_m} m wide (between the doubles side "
        "lines), with the singles side lines {singles_width_m} m apart, a short service line {short_service_m} m from "
        "the net on each side, a centre line from each short service line to the back boundary line, and a doubles "
        "long service line {doubles_long_service_m} m inside each back boundary line; every line is {line_width_m} m "
        "wide and is part of the area it bounds (the centre line is shared by the two service courts). This is "
        "singles: a service court reaches from the short service line to the back boundary line and from the centre "
        "line to the singles side line. The net stands across the middle, its top {net_centre_m} m high at the centre "
        "and rising to {net_post_m} m at the posts on the doubles side lines (the cord sags under the net's weight); "
        "it is {net_depth_m} "
        "m deep, with open space under it. The shuttle is a feathered shuttle (5.1 g, a cork base 26 mm across, 16 "
        "feathers whose tips form a circle 64 mm across) with a shuttle's heavy air drag (it falls at 6.8 m/s at "
        "most) that turns it to fly cork first; it starts held by its feathers in your left hand. The racket (0.67 m, "
        "85 g, strung area 0.27 m by 0.21 m) is held in your right hand by contact and friction alone: it can slip, "
        "turn and fall. Both hands are three-finger hands (a thumb, an index and a middle finger). You serve from your right service court into the receiver's "
        "right service court, the one diagonally opposite. The racket must stay in your right hand all the time: it "
        "touches the hand's fingers and its thumb or palm, and a break of more than {hold_gap_s} s is a fault. In order: (1) the "
        "release: your left hand lets the shuttle go; it is let go once it has touched nothing of yours for "
        "{clear_s} s (the release is the moment it came free; until then it is still held), and from then on nothing "
        "of yours but the racket may touch it. (2) the hit: the racket hits the shuttle before it reaches the floor. "
        "At the first instant of contact the "
        "cork base is touching the racket (the feathers touching it first, alone, is a fault), the whole shuttle is "
        "lower than {max_hit_height_m} m above the floor, the shuttle moves at most {drop_max_speed_m_s} m/s, and "
        "the racket head is moving towards the net. A forward "
        "movement of the racket head starts when its speed towards the net rises above {start_speed_m_s} m/s and "
        "lasts until that speed falls below {stop_speed_m_s} m/s. The service starts at the earlier of the release "
        "and the start of the racket head's forward movement that brings it to the hit; a forward movement that "
        "starts after the release and stops before the hit is a fault. From the start of the service to the hit both "
        "feet stand in your service court, touching neither its lines nor anything outside it, each foot touching the "
        "floor all the time (a gap of at most {foot_gap_s} s still counts as touching) and moving at most "
        "{foot_move_m} m. The hit is one contact: racket contacts less than {retouch_gap_s} s apart are one hit, it "
        "lasts at most {max_touch_s} s, and when it is over ({retouch_gap_s} s after its last contact) the shuttle is "
        "faster than it was when it reached the racket and is rising. (3) the shuttle passes the net's plane over the "
        "net's top edge, between the posts (it may touch the net). (4) its first contact with the floor (contacts "
        "less than {landing_gap_s} s apart are one) is inside the receiver's right service court, the lines included: "
        "that is the success. You fail on any fault: the shuttle reaching the floor, touching the net or passing the "
        "net's plane without a hit; the racket touching the shuttle before you let it go; the shuttle touching you, "
        "or touched by anything of yours but the racket, after the release; a hit that breaks a rule of (2); a second "
        "hit; a carry; the shuttle passing through or under the net or outside the posts, touching a post, landing on "
        "your side or outside that service court; the racket leaving your right hand, or touching the floor, the net "
        "or a post, at any time; any "
        "part of you touching the net or a post; a fall; or {time_limit_s} s passing. A fall is: your pelvis lower "
        "than {fall_z_m} m above the floor, or any part of you other than your feet touching the floor.")
    venue = (
        "You stand in your right service court facing the net (+x), whose plane is {net_x_m} m ahead of your pelvis; "
        "the middle of the centre line is {centre_y_m} m to your left, so your service court reaches from the near "
        "edge of the centre line to the outer edge of the singles side line 2.59 m to the right of the centre line's "
        "middle, and from the short service line (its edge nearest the net {short_service_m} m from the net) back to "
        "the back boundary line 6.70 m from the net. The receiver's right service court, your target, is beyond the "
        "net on the other side of the centre line: from {short_service_m} m to 6.70 m beyond the net, from the centre "
        "line to the singles side line 2.59 m to the left of the centre line's middle. Your forearms point forward; "
        "your left hand, its palm facing in, holds the shuttle round its feathers, the shuttle hanging cork down "
        "across the palm; your right hand holds the "
        "racket's handle near its butt across the palm, the fingers and the thumb closed round it, the racket "
        "pointing out of the index finger's side, its strings facing the way your palm does.")
    difficulty = ("The shuttle must leave the strings at about 9 m/s or more, 40 to 55 degrees upwards, to clear a "
                  "1.52 m net 2 m away from a hit below 1.15 m, and the G1 meets it only in the lower part of a swing "
                  "whose racket is held by friction in a three-finger hand; the left hand's reach and the racket's "
                  "path barely overlap, and the shuttle falls through it in a few hundredths of a second. The swing "
                  "must leave the feet where they stand and the robot on them, on a stand without balance feedback.")

    def configure(self, params):
        super().configure(params)
        self.fall_z = self.p["fall_z_m"]

    # ------------------------------------------------------------------ the venue
    def courts(self):
        """The server's right service court (inside its lines: where the feet may touch) and the receiver's right
        service court (lines included: where the shuttle must land), each (x0, x1, y0, y1)."""
        p = self.p
        nx, cy, hs, L = p["net_x_m"], p["centre_y_m"], p["singles_width_m"] / 2, p["court_length_m"] / 2
        lw, ss = p["line_width_m"], p["short_service_m"]
        server = (nx - L + lw, nx - ss - lw, cy - hs + lw, cy - lw / 2)
        target = (nx + ss, nx + L, cy - lw / 2, cy + hs)
        return server, target

    def build(self, sc):
        p = self.p
        nx, cy, L = p["net_x_m"], p["centre_y_m"], LENGTH / 2
        sc.box("hall_floor", (nx, cy, 0.0001), (L + 2.5, WIDTH / 2 + 2.0, 0.0001), rgba=(0.80, 0.62, 0.40, 1))
        sc.box("court", (nx, cy, 0.0002), (L, WIDTH / 2, 0.0002), rgba=(0.16, 0.40, 0.46, 1))
        h = LINE / 2
        for s, tag in ((-1, "near"), (1, "far")):
            for name, x in (("back_line", nx + s * (L - h)), ("long_service_line", nx + s * (L - DOUBLES_LONG + h)),
                            ("short_service_line", nx + s * (SHORT + h))):
                sc.line(f"{name}_{tag}", (x, cy - WIDTH / 2), (x, cy + WIDTH / 2), width=LINE)
            sc.line(f"centre_line_{tag}", (nx + s * SHORT, cy), (nx + s * L, cy), width=LINE)
        for s, tag in ((-1, "right"), (1, "left")):
            for name, y in (("singles_side_line", cy + s * (SINGLES / 2 - h)),
                            ("doubles_side_line", cy + s * (WIDTH / 2 - h))):
                sc.line(f"{name}_{tag}", (nx - L, y), (nx + L, y), width=LINE)
        server, target = self.courts()
        sc.zone("target_court", ((target[0] + target[1]) / 2, (target[2] + target[3]) / 2),
                ((target[1] - target[0]) / 2 - LINE, (target[3] - target[2]) / 2 - LINE), rgba=(0.95, 0.85, 0.2, 0.18))
        net = sc.body("net", (nx, cy, 0.0))
        for s_, tag in ((1, "L"), (-1, "R")):
            sc.geom(net, f"net_post{tag}", type="cylinder", pos=(0, s_ * (POST_Y + POST_R + NET_SEG_HALF_T), NET_POST / 2),
                    size=(POST_R, NET_POST / 2), rgba=(0.25, 0.25, 0.28, 1), priority="3", solref=DEAD,
                    solimp="0.95 0.99 0.001", **HITTABLE)
        build_net(sc, net, net_top, POST_Y - 0.005, POST_Y, lambda y: net_top(y) - NET_DEPTH, NET_STRIP_M, NET_SEGMENTS,
                  NET_AREA_DENSITY, 0.0, NET_TENSION, 0.0, NET_BAND_M, NET_SOLIDITY)
        build_shuttle(sc)
        build_racket(sc)
        sc.real_hands["right"] = sc.real_hands["left"] = "dex3"
        sc.camera("venue", (-3.2, -3.4, 2.6), (nx + 1.0, cy + 0.6, 0.6), fovy=60)

    # ------------------------------------------------------------------ the hands (the G1's Dex3-1, realhand.py)
    def may_grip(self, w, side, name):
        return False                            # (both hands are real hands: nothing is grippable)

    def _racket_in_hand(self, w, ref) -> bool:
        """The right hand has held the racket within the last hold_gap_s (a swing's contact chatter
        of a few milliseconds is not a release)."""
        t = self.trackers.get("racket_held")
        return t is not None and ref.time - t <= self.p["hold_gap_s"] + 1e-9

    def start_pose(self, w):
        """The arms at the start pose (their targets held there), the robot otherwise as it stands."""
        r, d = w.robot, w.d
        ARMS = w.L.ARMS
        pose = np.r_[START_LEFT, START_RIGHT]
        d.qpos[r.qadr[ARMS]] = pose
        r.arb.q_a[ARMS] = r.arb.q_b[ARMS] = pose
        mujoco.mj_kinematics(w.m, d)

    def place(self, w):
        """The racket's handle across the right palm (GRIP), the shuttle's skirt across the left palm, the cork
        towards the lower side."""
        c, R = w.grasp_frame("right")
        Rr = np.c_[R[:, 0], -R[:, 2], R[:, 1]]          # racket x = the palm's normal, z = the handle = grasp y
        q = np.zeros(4)
        mujoco.mju_mat2Quat(q, Rr.ravel())
        w.put("racket", c - R[:, 1] * GRIP["racket_butt_out_m"] + R[:, 0] * GRIP["racket_palm_off_m"], q)
        c, R = w.grasp_frame("left")
        # the shuttle's +z (towards the cork) along the left hand's y, the lower way; held at s = PINCH_S
        down = R[:, 1] if R[2, 1] < 0 else -R[:, 1]
        x = R[:, 0]
        y = np.cross(down, x)
        Rs = np.c_[x, y, down]
        qs = np.zeros(4)
        mujoco.mju_mat2Quat(qs, Rs.ravel())
        w.put(SHUTTLE, c + R[:, 0] * GRIP["shuttle_palm_off_m"] - down * z_of(PINCH_S), qs)

    def reset(self, w):
        self.start_pose(w)
        self.place(w)
        self.grasp = {"racket": w.close_on("right", "racket", closure=RACKET_CLOSURE),
                      "shuttle": w.close_on("left", SHUTTLE, closure=SHUTTLE_CLOSURE)}
        self.trackers = {"phase": "hold"}

    # ------------------------------------------------------------------ the referee
    def _feet_xy(self, w) -> list:
        return [round(float(x), 5) for s in ("left", "right") for x in w.d.site_xpos[w.robot.foot_site[s]][:2]]

    def referee_reset(self, w, ref):
        p = self.p
        self.racket = ref.geoms(body="racket")
        self.cork = ref.geoms(names=["shuttle_cork"])
        self.skirt = ref.geoms(names=["shuttle_skirt"])
        self.shuttle = self.cork | self.skirt
        self.netg = ref.geoms(body="net")
        self.posts = ref.geoms(names=["net_postL", "net_postR"])
        self.feet = ref.part("feet")
        self.head_site = w.m.site("racket_head").id
        self.trackers = {
            "phase": "hold", "released": None, "last_touch": None, "free_since": None, "feet_free": None,
            "came": None, "speed": 0.0, "sped_up": None,
            "run": None,                 # the start time of the racket head's forward movement in progress
            "feet_bad": None,            # the last time the feet were not where Law 9.1.2-3 wants them
            "feet_run": None, "feet_rel": None,     # the feet at the start of the run / at the release
            "move_run": 0.0, "move_rel": 0.0,       # the most each foot has moved since then
            "foot_down": {"left_foot": 0.0, "right_foot": 0.0},     # the last time each foot touched the floor
            "racket_held": round(ref.time, 4) if getattr(w, "held", {}).get("right") == "racket" else None,
            "racket": Touch(ref, self.shuttle, self.racket, gap=p["retouch_gap_s"]),
            "ground": Touch(ref, self.shuttle, ref.ground, gap=p["landing_gap_s"]),
            "net": Crossing((1, 0, 0), p["net_x_m"], direction=1),
        }

    def _head_forward(self, w) -> float:
        """The racket head's speed towards the net (+x)."""
        v = np.zeros(6)
        mujoco.mj_objectVelocity(w.m, w.d, mujoco.mjtObj.mjOBJ_SITE, self.head_site, v, 0)
        return float(v[3])

    def _feet_ok(self, w, ref) -> bool:
        """Law 9.1 at this instant: each foot touches the floor (a gap of at most foot_gap_s, a contact's chatter, is
        still contact), and only inside the server's court's lines."""
        (x0, x1, y0, y1), _ = self.courts()
        tr, down = self.trackers, ref.parts_touching(ref.ground)
        for f in ("left_foot", "right_foot"):
            if f in down:
                tr["foot_down"][f] = round(ref.time, 4)
        if any(ref.time - tr["foot_down"][f] > self.p["foot_gap_s"] + 1e-9 for f in ("left_foot", "right_foot")):
            return False
        pts = ref.contact_points(self.feet, ref.ground)
        return bool(np.all((pts[:, 0] > x0) & (pts[:, 0] < x1) & (pts[:, 1] > y0) & (pts[:, 1] < y1)))

    def _moved(self, a, b) -> float:
        return max(math.hypot(a[0] - b[0], a[1] - b[1]), math.hypot(a[2] - b[2], a[3] - b[3]))

    def substep(self, w, ref):
        p, tr = self.p, self.trackers
        if ref.touching(ref.robot_mask, self.netg):
            return ref.fail("you touched the net or a post", parts=sorted(ref.parts_touching(self.netg)))
        if ref.touching(self.racket, self.netg):
            return ref.fail("the racket touched the net or a post")
        if ref.touching(self.racket, ref.ground):
            return ref.fail("you dropped the racket: it touched the floor")
        if w.held["right"] == "racket":
            tr["racket_held"] = round(ref.time, 4)
        if not self._racket_in_hand(w, ref):
            return ref.fail("the racket left your right hand", since_s=tr["racket_held"])
        rk = tr["racket"]
        new = rk.update()
        phase = tr["phase"]
        # the racket head's forward movement (Law 9.2, 9.1.7) and the feet (Law 9.1.2-3), until the hit
        if phase in ("hold", "free"):
            v = self._head_forward(w)
            feet = self._feet_xy(w)
            if not self._feet_ok(w, ref):
                tr["feet_bad"] = round(ref.time, 4)
            if tr["run"] is None and v > p["start_speed_m_s"]:
                tr["run"], tr["feet_run"], tr["move_run"] = round(ref.time, 4), feet, 0.0
            elif tr["run"] is not None and v < p["stop_speed_m_s"]:
                if phase == "free" and not new and tr["run"] >= tr["released"]:
                    return ref.fail("the racket's forward movement stopped before the hit",
                                    started_s=tr["run"])
                tr["run"] = None
            if tr["feet_run"] is not None and tr["run"] is not None:
                tr["move_run"] = max(tr["move_run"], self._moved(feet, tr["feet_run"]))
            if tr["feet_rel"] is not None:
                tr["move_rel"] = max(tr["move_rel"], self._moved(feet, tr["feet_rel"]))
        if phase == "hold":
            if new or rk.active:
                return ref.fail("the racket touched the shuttle before you let it go")
            if ref.touching(self.shuttle, ref.robot_mask):          # held (or still touching you): not let go yet
                tr["free_since"] = None
                return
            if tr["free_since"] is None:                             # free of you from this step on
                tr["free_since"], tr["feet_free"] = round(ref.time, 4), self._feet_xy(w)
            if ref.time - tr["free_since"] < p["clear_s"] - 1e-9:
                return
            # let go: free of you for clear_s; the release is the moment it came free
            tr.update(phase="free", released=tr["free_since"], last_touch=tr["free_since"], feet_rel=tr["feet_free"],
                      move_rel=0.0)
            ref.stage("release", at_s=tr["released"])
            phase = "free"
        b = w.pos(SHUTTLE)
        came, tr["speed"] = tr["speed"], round(float(np.linalg.norm(w.vel(SHUTTLE))), 4)   # (the speed one step ago)
        if phase == "free":
            if ref.touching(self.shuttle, ref.robot_mask):
                return ref.fail("the shuttle touched you after you let it go",
                                parts=sorted(ref.parts_touching(self.shuttle)))
            if new:
                return self._hit(w, ref, came)
            if ref.touching(self.shuttle, ref.ground):
                return ref.fail("you missed the shuttle: it reached the floor without a hit")
            if tr["net"].update(b) is not None:
                return ref.fail("the shuttle passed the net without a hit")
            if ref.touching(self.shuttle, self.netg):
                return ref.fail("the shuttle touched the net without a hit")
            return
        # the served shuttle
        if new and rk.count > 1:
            return ref.fail("the racket hit the shuttle twice")
        if rk.active and rk.duration > p["max_touch_s"]:
            return ref.fail("the shuttle was carried on the racket", touch_s=round(rk.duration, 4))
        if tr["sped_up"] is None and not rk.active:     # the hit is over
            vel = w.vel(SHUTTLE)
            tr["sped_up"] = bool(tr["speed"] > tr["came"])
            ref.metrics["shuttle_speed_m_s"] = tr["speed"]
            ref.metrics["shuttle_angle_deg"] = round(math.degrees(math.atan2(vel[2], math.hypot(vel[0], vel[1]))), 2)
            if not tr["sped_up"]:
                return ref.fail("the racket did not speed the shuttle up", before_m_s=tr["came"], after_m_s=tr["speed"])
            if vel[2] <= 0.0:
                return ref.fail("the shuttle's flight from the racket was not upwards", vz_m_s=round(float(vel[2]), 3))
        if ref.touching(self.shuttle, ref.robot_mask):
            return ref.fail("the served shuttle touched you", parts=sorted(ref.parts_touching(self.shuttle)))
        if ref.touching(self.shuttle, self.posts):
            return ref.fail("the service touched a post")
        if ref.touching(self.shuttle, self.netg):
            ref.metrics["net_touched"] = 1.0                # (a service may touch the net)
        x = tr["net"].update(b)
        if x is not None:
            dy = float(x[1]) - p["centre_y_m"]
            if abs(dy) <= POST_Y and x[2] > net_top(dy):
                ref.stage("over the net", y=round(float(x[1]), 3), z=round(float(x[2]), 3),
                          clearance_m=round(float(x[2] - net_top(dy)), 3))
            else:
                return ref.fail("the service did not pass over the net", y=round(float(x[1]), 3),
                                z=round(float(x[2]), 3))
        if tr["ground"].update():
            pts = ref.contact_points(self.shuttle, ref.ground)
            q = pts[0] if len(pts) else b
            ref.metrics["landing_x_m"], ref.metrics["landing_y_m"] = round(float(q[0]), 3), round(float(q[1]), 3)
            if q[0] <= p["net_x_m"]:
                return ref.fail("the service landed on your own side")
            _, (x0, x1, y0, y1) = self.courts()
            if not (x0 <= q[0] <= x1 and y0 <= q[1] <= y1):
                return ref.fail("the service landed outside the receiver's service court")
            if ref.stage("in"):
                ref.succeed()

    def _hit(self, w, ref, came):
        """The racket's first contact with the released shuttle: Law 9.1 at that instant."""
        p, tr = self.p, self.trackers
        top = shuttle_top(w)
        cork = ref.touching(self.cork, self.racket)
        info = dict(shuttle_top_m=round(top, 4), speed_before_m_s=came,
                    head_forward_m_s=round(self._head_forward(w), 3))
        if not cork:
            return ref.fail("the racket hit the feathers first, not the base of the shuttle", **info)
        if top >= p["max_hit_height_m"]:
            return ref.fail("the shuttle was not wholly below the service height at the hit", **info)
        if came > p["drop_max_speed_m_s"]:
            return ref.fail("the shuttle was thrown, not let go", **info)
        if tr["run"] is None:
            return ref.fail("the racket head was not moving forwards at the hit", **info)
        t_start = min(tr["released"], tr["run"])
        if tr["feet_bad"] is not None and tr["feet_bad"] >= t_start:
            return ref.fail(FAULT_FEET + ": a foot was off the floor or outside your service court during the service",
                            at_s=tr["feet_bad"], start_s=t_start, **info)
        moved = tr["move_run"] if tr["run"] <= tr["released"] else tr["move_rel"]
        if moved > p["foot_move_m"]:
            return ref.fail(FAULT_FEET + ": a foot moved during the service", moved_m=round(moved, 4), **info)
        tr["phase"], tr["came"] = "served", came
        ref.metrics["hit_height_m"] = round(top, 4)
        ref.stage("hit", service_start_s=t_start, **info)

    def privileged(self, w):
        p, tr = self.p, self.trackers
        server, target = self.courts()
        return {"shuttle": w.pos(SHUTTLE).tolist(), "shuttle_velocity": w.vel(SHUTTLE).tolist(),
                "shuttle_axis": w.d.xmat[w.m.body(SHUTTLE).id].reshape(3, 3)[:, 2].tolist(),
                "shuttle_top_m": shuttle_top(w), "phase": tr.get("phase"),
                "racket": w.pos("racket").tolist(), "racket_head": w.d.site_xpos[self.head_site].tolist(),
                "racket_head_forward_m_s": self._head_forward(w),
                "server_court_feet": dict(zip(("x0", "x1", "y0", "y1"), server)),
                "target_court": dict(zip(("x0", "x1", "y0", "y1"), target)),
                "net": {"x": p["net_x_m"], "centre_y": p["centre_y_m"], "top_centre": NET_CENTRE, "top_post": NET_POST,
                        "post_y": POST_Y}, "racket_spec": RACKET}
