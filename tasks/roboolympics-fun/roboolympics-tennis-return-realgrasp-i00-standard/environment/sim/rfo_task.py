"""Tennis, return of serve with a real grip (ITF Rules of Tennis): tennis-return's task, the 30 m/s serve into your
right service box, returned after its one bounce over the net into the singles court; but the racket is not part of
the hand. It is a free 0.30 kg racket held only by the friction of the right hand's two-finger gripper (Unitree
Dex1-1): it can slip, twist in the hand when the ball strikes it, and be dropped.

Official setting: as tennis-return (the court and net of ITF Rule 1, the ITF ball in air), and a racket within ITF
Appendix II with a real handle. Nothing is scaled to the robot.

Where the numbers come from (the court, the ball and the serve are tennis-return's, copied: a task directory holds one
module):
* the court, the net and the lines: ITF Rule 1 (all measurements to the outside of the lines);
* the ball: scene.OFFICIAL["tennis"] (Rule 3 / Appendix I); its Magnus coefficient is RoboOlympics tennis' (tn.py:
  C_L = 1 / (2 + 1/S), the Goodwill fit; in MuJoCo's form 0.29 at S = 0.15);
* the serve: tn.py's opponent serve (level 4), the generator's first draw (seed [404, 11, 0]: down the T, 0.60 m from
  the centre line and 5.35 m from the net); 30 m/s from 2.70 m (FAMILIES.md); elevation and azimuth solved so that
  the ball lands on that target (tests/test_tennis_return_realgrasp.py checks it);
* the racket: a free body (FREE_RACKET below): 0.685 m long (Appendix II: at most 73.7 cm), strung surface an ellipse
  0.33 m x 0.25 m (645 cm^2; at most 39.4 x 29.2 cm), 0.30 kg, the balance 0.33 m from the butt, swingweight 320
  kg cm^2 about the axis 0.10 m from the butt and twistweight 14 kg cm^2 (a typical adult racket: Brody, Cross and
  Lindsey, The Physics and Technology of Tennis, 2002; USRSA racquet data); the handle a regular octagon of grip size
  4 3/8 in (111 mm round, 33.5 mm across the flats), 0.19 m long. The block is shared, byte for byte, with
  tennis-serve-realgrasp. The ball-string contact is an explicit pair, a 3.1 ms spring on a 40 mm collision slab,
  friction 0.4 (the racket block's comment has the table). Ball speed out / in, a ball square on the strings' centre
  (measured, mean over the contact's phase): the racket fixed in space 0.85 from 5 to 50 m/s; a free racket 0.44 at
  the centre, 0.32 8 cm towards the tip, 0.20 8 cm off the axis (a real racket's is about 0.4 at the centre, Cross
  2000). Held in the gripper at 120 N (measured on the earlier 4 ms pair, not re-measured): it rocks about 19 degrees in
  the jaws at 30 m/s and comes back; 8 cm off the axis across the head it turns 47 degrees about its handle at 15 m/s
  and 137 at 30, and stays turned.
* the hand: the core's Unitree Dex1-1 gripper (rfo.realhand; 90 mm stroke, 80 mm jaws, 5-120 N): the racket is held by
  contact and friction only, no weld. The handle lies along the jaws (the longest grip the gripper has: 80 mm of pad
  against the impact's lever), the butt 5 mm from the gripper's body, the strings' normal the closing axis, the
  closure command 1 (120 N). "In the hand" = the handle touches both jaws; the measured breaks of that contact are
  2-5 ms at a 30 m/s impact (about 10 ms in a hard swing, badminton-serve's finding), hence out_of_hand_s = 0.05.
"""
import math
import xml.etree.ElementTree as ET

import mujoco
import numpy as np

from rfo.referee import Crossing, Touch
from rfo.scene import HITTABLE, OFFICIAL, VISUAL
from rfo.task import TaskBase

BALL = OFFICIAL["tennis"]
MAGNUS = 0.29                                   # see the module docstring
BALL_FLUID = (BALL["drag"] / 2, 0.25, 0.0, 1.0, MAGNUS)

# ---------------------------------------------------------------------------------------------- the court (ITF Rule 1)
HALF_LENGTH, HALF_WIDTH, SERVICE = 23.77 / 2, 8.23 / 2, 6.40
NET_CENTRE, NET_POST, POST_OUT = 0.914, 1.07, 0.914
POST_Y = HALF_WIDTH + POST_OUT                  # 5.029 m: the posts' centres from the centre line
LINE = 0.05                                     # every line 5 cm wide (Rule 1: 2.5-5 cm; centre line and mark 5 cm)
NET_HALF_THICK = 0.01                           # the net's collision body: a wall 2 cm thick
POST_R = 0.0375                                 # singles sticks / posts: at most 7.5 cm (15 cm) across
NET_SOLREF = "-4e5 -1000"                       # ball on the net: stiff and nearly dead (measured restitution 0.2-0.25)
POST_SOLREF = "-1e6 -430"                       # ball on a post: stiff, restitution about 0.5


def net_top(dy: float) -> float:
    """The height of the net's top edge dy metres from the centre strap (the cord is straight from the strap to each
    post)."""
    return NET_CENTRE + (NET_POST - NET_CENTRE) * min(abs(dy), POST_Y) / POST_Y


def build_court(sc, nx: float, cy: float, balls=("ball",)) -> None:
    """The singles court with its net in the plane x = nx, its centre line along y = cy."""
    blue, green = (0.20, 0.36, 0.62, 1), (0.25, 0.50, 0.33, 1)
    sc.box("surround", (nx, cy, 0.0001), (HALF_LENGTH + 6.4, HALF_WIDTH + 3.66, 0.0001), rgba=green)
    sc.box("court", (nx, cy, 0.0002), (HALF_LENGTH, HALF_WIDTH, 0.0002), rgba=blue)
    h = LINE / 2
    for s, tag in ((-1, "near"), (1, "far")):
        for name, x in (("baseline", nx + s * (HALF_LENGTH - h)), ("service_line", nx + s * (SERVICE - h))):
            sc.line(f"{name}_{tag}", (x, cy - HALF_WIDTH), (x, cy + HALF_WIDTH))
        sc.line(f"centre_mark_{tag}", (nx + s * (HALF_LENGTH - 0.10), cy), (nx + s * HALF_LENGTH, cy))
    for s, tag in ((-1, "right"), (1, "left")):
        y = cy + s * (HALF_WIDTH - h)
        sc.line(f"sideline_{tag}", (nx - HALF_LENGTH, y), (nx + HALF_LENGTH, y))
    sc.line("centre_service_line", (nx - SERVICE, cy), (nx + SERVICE, cy))
    asset, contact = sc.root.find("asset"), sc.root.find("contact")
    t = NET_HALF_THICK
    net = sc.body("net", (nx, cy, 0.0))
    for s, tag in ((1, "L"), (-1, "R")):
        v = [(x, s * y, z) for x in (-t, t) for y, z in ((0, 0), (0, NET_CENTRE), (POST_Y, NET_POST), (POST_Y, 0))]
        ET.SubElement(asset, "mesh", name=f"net_{tag}", vertex=" ".join(f"{c:.5f}" for p in v for c in p))
        sc.geom(net, f"net_{tag}", type="mesh", mesh=f"net_{tag}", rgba=(0.1, 0.1, 0.1, 0.55), **HITTABLE)
        sc.geom(net, f"net_post{tag}", type="cylinder", pos=(0, s * (POST_Y + POST_R + t), NET_POST / 2),
                size=(POST_R, NET_POST / 2), rgba=(0.25, 0.25, 0.28, 1), **HITTABLE)
        L = math.hypot(POST_Y, NET_POST - NET_CENTRE)                    # the white band along the top (drawn only)
        a = math.atan2(NET_POST - NET_CENTRE, POST_Y)
        sc.geom(net, f"net_band{tag}", type="box", pos=(0, s * POST_Y / 2, (NET_CENTRE + NET_POST) / 2 - 0.03),
                size=(t + 0.002, L / 2, 0.03), quat=(math.cos(s * a / 2), math.sin(s * a / 2), 0, 0),
                rgba=(0.97, 0.97, 0.97, 1), **VISUAL)
        for b in balls:                              # (with its own soft contact a 30 m/s ball would pass through)
            ET.SubElement(contact, "pair", name=f"{b}_net_{tag}", geom1=b, geom2=f"net_{tag}", condim="3",
                          friction="0.3 0.3 0.005 0.0001 0.0001", solref=NET_SOLREF, solimp="0.95 0.99 0.001")
            ET.SubElement(contact, "pair", name=f"{b}_net_post{tag}", geom1=b, geom2=f"net_post{tag}", condim="3",
                          friction="0.3 0.3 0.005 0.0001 0.0001", solref=POST_SOLREF, solimp="0.95 0.99 0.001")
    sc.geom(net, "net_strap", type="box", pos=(0, 0, NET_CENTRE / 2), size=(t + 0.002, 0.025, NET_CENTRE / 2),
            rgba=(0.97, 0.97, 0.97, 1), **VISUAL)


# ---------------------------------------------------------------------------------- the free racket (ITF Appendix II)
# A free body "racket" in its own frame: the butt at the origin, +z along the handle to the tip (the frame's outer
# edge at length_m), the strings' normal is the body's x axis (the strings span y and z). Shared, identically, by
# tennis-serve-realgrasp and tennis-return-realgrasp.
FREE_RACKET = dict(length_m=0.685, mass_kg=0.30, balance_from_butt_m=0.33, handle_across_flats_m=0.0335,
                   handle_length_m=0.19, strung_length_m=0.33, strung_width_m=0.25, head_centre_z_m=0.496,
                   frame_radius_m=0.012, strings_half_thickness_m=0.02, strings_look_half_thickness_m=0.0125,
                   string_friction=0.4,
                   swingweight_kg_cm2=320.0, twistweight_kg_cm2=14.0)
# The body's inertia is explicit (the geoms carry no mass): 0.30 kg with its centre 0.33 m from the butt; about the
# centre, I_yy (the swing axis: in the strings' plane, across the handle) = swingweight about the axis 0.10 m from the
# butt less M (0.33 - 0.10)^2; I_zz (about the handle) = the twistweight; I_xx = I_yy + I_zz (a flat body;
# 0.999 of it: MuJoCo requires A + B >= C strictly after rounding). Typical of
# an adult racket (Brody, Cross and Lindsey, The Physics and Technology of Tennis, 2002; USRSA's racquet data).
FR_IYY = FREE_RACKET["swingweight_kg_cm2"] * 1e-4 - FREE_RACKET["mass_kg"] * (FREE_RACKET["balance_from_butt_m"] - 0.10) ** 2
FR_IZZ = FREE_RACKET["twistweight_kg_cm2"] * 1e-4
FR_INERTIA = (0.999 * (FR_IYY + FR_IZZ), FR_IYY, FR_IZZ)
# The ball-string contact: an explicit pair per ball, a linear spring-damper (MuJoCo's direct solref: 1000 rad/s, a
# 3.1 ms dwell; the damping sets the restitution), constant impedance, friction 0.4 (tn.py's), on an invisible
# collision slab 40 mm thick (strings_half_thickness_m) round the strings' plane; the strings drawn are 25 mm thick.
# The slab is thicker than the strings drawn so that a fast ball, which sinks up to v / 1000 rad/s into it, never
# reaches the slab's middle (where the contact's normal would flip and the ball pass through): good to 50 m/s
# relative speed. tennis_return.py's clamped racket (785 rad/s on a 25 mm slab) averages 0.85 too, but lets a ball
# faster than about 37 m/s through.
STRING_SOLREF = "-1000000 -110"
STRING_SOLIMP = "0.99 0.99 0.001"
# Measured with this block (a ball square on the head's centre, no gravity, no air, the real-hand worlds' elliptic
# cones and impratio 100; mean [min, max] over where in the 1 ms physics step the contact begins):
#   racket fixed in space   5 m/s 0.852 [0.80, 0.93]   10: 0.852 [0.80, 0.93]   15: 0.853 [0.80, 0.94]
#                          20: 0.853 [0.81, 0.94]   25: 0.853 [0.81, 0.94]   30: 0.853 [0.81, 0.94]
#                          35: 0.853 [0.81, 0.94]   40: 0.854 [0.81, 0.94]   50: 0.854 [0.81, 0.94]; never through
#   free racket (apparent restitution, out / in, at 10, 20 and 30 m/s alike): 0.44 at the head's centre, 0.32 8 cm
#   towards the tip, 0.20 8 cm off the axis (a real racket's: about 0.4 at the centre, less towards the tip: Cross,
#   "The coefficient of restitution for collisions of happy balls, unhappy balls, and tennis balls", 2000)


def build_free_racket(sc, pos, quat=(1, 0, 0, 0), balls=("ball",), name="racket"):
    """The racket as a free body at pos/quat (its butt). Geoms: <name>_handle (a regular octagonal prism, the grip),
    <name>_throat{L,R}, <name>_frame{i} (24 capsules round the head) and <name>_strings (the strung ellipse's
    collision slab, invisible, whose contact with each ball is an explicit pair; <name>_strings_look is drawn). All
    collide like a prop (HITTABLE): with the jaws, the robot, the ground, the net."""
    R = FREE_RACKET
    asset = sc.root.find("asset")
    a = R["handle_across_flats_m"] / 2
    s = a * math.tan(math.pi / 8)                               # half a side of the octagon
    octo = [(a, s), (s, a), (-s, a), (-a, s), (-a, -s), (-s, -a), (s, -a), (a, -s)]
    L = R["handle_length_m"]
    ET.SubElement(asset, "mesh", name=f"{name}_handle",
                  vertex=" ".join(f"{c:.5f}" for z in (0.0, L) for x, y in octo for c in (x, y, z)))
    zc, A, B, n = R["head_centre_z_m"], R["strung_length_m"] / 2, R["strung_width_m"] / 2, 24
    ring = [(B * math.sin(2 * math.pi * i / n), zc + A * math.cos(2 * math.pi * i / n)) for i in range(n)]
    for tag, t in (("strings", R["strings_half_thickness_m"]), ("strings_look", R["strings_look_half_thickness_m"])):
        ET.SubElement(asset, "mesh", name=f"{name}_{tag}",
                      vertex=" ".join(f"{c:.5f}" for x in (-t, t) for y, z in ring for c in (x, y, z)))
    b = sc.body(name, pos, quat=quat, free=True)
    ET.SubElement(b, "inertial", pos=f"0 0 {R['balance_from_butt_m']:.4f}", mass=f"{R['mass_kg']:.4f}",
                  diaginertia=" ".join(f"{v:.6g}" for v in FR_INERTIA))
    dark = (0.1, 0.1, 0.12, 1)
    sc.geom(b, f"{name}_handle", type="mesh", mesh=f"{name}_handle", mass=0, rgba=dark,
            friction=(1.0, 0.005, 0.0001), **HITTABLE)
    zt = zc - A - R["frame_radius_m"]                           # the throat meets the head's bottom
    for sgn, tag in ((1, "L"), (-1, "R")):
        sc.geom(b, f"{name}_throat{tag}", type="capsule", size=(0.008,), mass=0, rgba=dark,
                fromto=(0, 0, L - 0.01, 0, sgn * 0.06, zt + 0.012), **HITTABLE)
    for i in range(n):
        y0, z0 = ring[i]
        y1, z1 = ring[(i + 1) % n]
        r = R["frame_radius_m"]
        k = 1 + r / math.hypot(y0, z0 - zc)                     # the frame's tube outside the strung ellipse
        k1 = 1 + r / math.hypot(y1, z1 - zc)
        sc.geom(b, f"{name}_frame{i}", type="capsule", size=(r,), mass=0, rgba=dark,
                fromto=(0, y0 * k, zc + (z0 - zc) * k, 0, y1 * k1, zc + (z1 - zc) * k1), **HITTABLE)
    sc.geom(b, f"{name}_strings", type="mesh", mesh=f"{name}_strings", mass=0, rgba=(1, 1, 1, 0), group=3,
            **HITTABLE)
    sc.geom(b, f"{name}_strings_look", type="mesh", mesh=f"{name}_strings_look", mass=0,
            rgba=(0.95, 0.9, 0.35, 0.55), **VISUAL)
    contact = sc.root.find("contact")
    for ball in balls:
        ET.SubElement(contact, "pair", name=f"{ball}_{name}_strings", geom1=ball, geom2=f"{name}_strings", condim="3",
                      friction="{0} {0} 0.005 0.0001 0.0001".format(R["string_friction"]), solref=STRING_SOLREF,
                      solimp=STRING_SOLIMP)
    return b
# ---------------------------------------------------------------------------------- (end of the shared racket)


# ---------------------------------------------------------------------------------------------- the hand
SIDE = "right"
BUTT_FROM_JAW_CENTRE_M = 0.035     # the butt 5 mm out from the gripper's housing: the handle along the 80 mm jaws


class Task(TaskBase):
    name = "tennis-return-realgrasp"
    title = "Tennis: return of serve, racket held by a real grip"
    category = "basketball-and-rackets"
    robot = "unitree_h1"
    rulebook = ("ITF Rules of Tennis 2024: Rule 1 (the court), Rule 3 and Appendix I (the ball), Rule 4 and "
                "Appendix II (the racket), Rule 12 (a ball on a line), Rules 24 and 25 (losing the point, a good "
                "return)")
    deviations = [
        "Rules 16-21 (the service): the server is a machine: the ball appears at the server's strike point and "
        "leaves it with the serve's velocity and spin {serve_time_s} s after the start; there is no opponent, the "
        "attempt ends when your return lands",
        "Rule 4 (the racket held in the hand): the hand is a two-finger gripper, Unitree's Dex1-1 (90 mm stroke, "
        "80 mm jaws, at most 120 N; Unitree sells it for the G1, the H2 and the R1, not the H1-2: here it sits on the "
        "H1-2's wrist where the palm ends); the handle lies along its jaws, and the racket is held by their friction "
        "alone, as a hand holds it",
        "Rules 4 and 24 (the ball hit with the racket held in the hand; a thrown racket does not play the ball): "
        "\"in the hand\" is defined by contact: the racket's handle touches both of the gripper's jaws; a break of up "
        "to {out_of_hand_s} s (the jolt of an impact or a hard swing; measured breaks last 2 to 10 ms) is not a "
        "release",
        "Rule 12 (a ball touching a line is in): the ball's footprint is one point, the point under its centre at "
        "its first contact with the ground (a real ball's footprint is about 5 cm across)",
        "Rule 24 f (deliberately touching the ball twice, carrying it): intention cannot be judged: racket contacts "
        "less than {retouch_gap_s} s apart are one hit, a later one is a second hit, and a contact longer than "
        "{max_touch_s} s is a carry",
        "Rule 1 (the net): a 2 cm thick wall instead of a mesh of cord; a ball that meets it is stopped by a stiff, "
        "strongly damped contact",
        "wind and weather: none; the air is still (sea level, 15 C)",
    ]
    time_limit_s = 10.0
    fall_z = 0.35                                                  # = params["fall_z_m"] (configure)
    start = (0.0, 0.0, 0.0)
    stages = ["bounce", "racket", "over the net", "in"]
    params = dict(
        court_length_m=23.77, court_width_m=8.23, service_line_m=6.40, net_centre_m=NET_CENTRE, net_post_m=NET_POST,
        post_outside_m=POST_OUT, line_width_m=LINE,
        net_x_m=12.385, centre_y_m=2.75,                              # the court in the robot's starting frame
        serve_time_s=3.0, serve_speed_m_s=30.0, serve_height_m=2.70, serve_behind_baseline_m=0.20,
        serve_right_of_mark_m=0.80, serve_topspin_rad_s=42.0, serve_elevation_deg=-2.238, serve_azimuth_deg=4.583,
        racket_length_m=FREE_RACKET["length_m"], racket_mass_kg=FREE_RACKET["mass_kg"],
        racket_balance_m=FREE_RACKET["balance_from_butt_m"], grip_across_flats_m=FREE_RACKET["handle_across_flats_m"],
        handle_length_m=FREE_RACKET["handle_length_m"], strung_length_m=FREE_RACKET["strung_length_m"],
        strung_width_m=FREE_RACKET["strung_width_m"],
        out_of_hand_s=0.05,
        max_touch_s=0.05, retouch_gap_s=0.05, bounce_gap_s=0.02, fall_z_m=0.35)

    sentence = ("Return the serve: after the tennis ball has bounced once in your service box, hit it with the racket "
                "held in your right hand's gripper back over the net so that it lands in the singles court on the far "
                "side, without letting go of the racket.")
    rules = (
        "The court is the ITF singles court: {court_length_m} m long and {court_width_m} m wide, measured to the "
        "outside of the lines, with a service line {service_line_m} m from the net on each side. The net stands "
        "across the middle, {net_centre_m} m high at its centre and rising in a straight line to {net_post_m} m at "
        "the posts, which stand {post_outside_m} m outside the sidelines. The ball is the ITF ball (radius 0.0335 m, "
        "0.0577 kg, with air drag and spin lift). The racket is a separate body, {racket_length_m} m long and "
        "{racket_mass_kg} kg, balanced {racket_balance_m} m from the butt, with a strung surface {strung_length_m} m "
        "by {strung_width_m} m and an octagonal handle {grip_across_flats_m} m across its flats and "
        "{handle_length_m} m long; at the start its handle is closed in your right hand's two-finger gripper, which "
        "holds it by friction only: it can slip, turn in the gripper and fall. The racket is in your hand while its "
        "handle touches both of the gripper's jaws; it has left your hand when for more than {out_of_hand_s} s "
        "the handle has not touched both jaws. {serve_time_s} s after the start the ball is served from behind the far "
        "baseline at {serve_speed_m_s} m/s into your right service box. In order: the ball bounces once on your "
        "side; the racket, in your hand, hits it (the strings, the frame or any other part of the racket counts); "
        "its centre passes the net's plane from your side to the far side, above the net's top edge or outside a "
        "post (it may touch the net or a post on the way); and its first contact with the ground after that is "
        "inside the far half of the singles court, the lines included (the point under the ball's centre decides; "
        "ground contacts less than {bounce_gap_s} s apart are one bounce): that is the success. You fail if the "
        "racket leaves your hand at any time (dropped, thrown or slipped out of the gripper), if the racket "
        "touches the ball before its bounce (a volley), if the ball bounces a second time on your side before your "
        "hit, if after your hit the ball touches the ground on your side or outside the far court, if the ball "
        "touches any part of you (the gripper included) at any time after the serve, if the racket touches the ball "
        "a second time (contacts less than {retouch_gap_s} s apart are one hit) or stays on it longer than "
        "{max_touch_s} s, if the ball passes the net's plane between the posts below the net's top edge, if any "
        "part of you or the racket touches the net or a post, or the ground beyond the net's plane, if you or the "
        "racket touch the ball before it is served, if you fall, or after {time_limit_s} s. A fall is: your pelvis "
        "lower than {fall_z_m} m above the ground, or any part of you other than your feet touching the ground; the "
        "racket may touch the ground on your side as long as it stays in your hand.")
    venue = (
        "You stand as the receiver: {centre_y_m} m to the right of the court's centre line, your pelvis 0.5 m "
        "behind your baseline, facing the net (+x), which is {net_x_m} m ahead of you. Painted on the court, all "
        "{line_width_m} m wide and inside the measurements: the two baselines, the two singles sidelines, the two "
        "service lines, the centre service line between them and a 0.10 m centre mark on each baseline; there are "
        "no doubles lines. The far baseline is {court_length_m} m beyond yours. The ball waits where the server "
        "strikes it: {serve_height_m} m above the ground, {serve_behind_baseline_m} m behind the far baseline and "
        "{serve_right_of_mark_m} m to the server's right of the centre mark (your left of the centre line). The "
        "serve is flat, with a little topspin; it bounces in your right service box, the one between the centre "
        "line and the right sideline, and reaches your baseline about a second after it was struck. The racket's "
        "handle is closed in your right gripper along its two fingers, the butt just short of the gripper's body "
        "and the rest of the handle reaching beyond the fingertips; the strings face the way the jaws close (your "
        "palm's side), and the racket points ahead along your forearm.")
    difficulty = ("The ball crosses the whole court in about a second and is still moving at more than 15 m/s when "
                  "it reaches you, so the racket has to be in a path a few centimetres wide at an instant you must "
                  "predict, and a robot that only walks cannot go far to meet it. The racket is held only by a "
                  "two-finger gripper's friction: a hard swing and the ball's impact twist it in the grip, so the "
                  "face the ball meets is not where the arm put it, and a swing strong enough to return the ball "
                  "over the net must not fling the racket out of the hand.")

    def configure(self, params):
        super().configure(params)
        self.fall_z = self.p["fall_z_m"]

    # ------------------------------------------------------------------ the venue
    def serve_from(self) -> np.ndarray:
        p = self.p
        return np.array([p["net_x_m"] + HALF_LENGTH + p["serve_behind_baseline_m"],
                         p["centre_y_m"] + p["serve_right_of_mark_m"], p["serve_height_m"]])

    def serve_velocity(self):
        """The serve's velocity and spin: towards -x, `azimuth` towards the robot's right (-y), `elevation` above the
        horizontal; topspin about the horizontal axis across the flight."""
        p = self.p
        el, az = math.radians(p["serve_elevation_deg"]), math.radians(p["serve_azimuth_deg"])
        v = p["serve_speed_m_s"] * np.array([-math.cos(el) * math.cos(az), -math.cos(el) * math.sin(az), math.sin(el)])
        w = p["serve_topspin_rad_s"] * np.array([-math.sin(az), math.cos(az), 0.0]) * -1.0
        return v, w

    def build(self, sc):
        p = self.p
        nx, cy = p["net_x_m"], p["centre_y_m"]
        build_court(sc, nx, cy)
        sc.ball("ball", "tennis", tuple(self.serve_from()), fluidcoef=BALL_FLUID)
        build_free_racket(sc, pos=(0.5, -0.5, 0.05))
        sc.real_hands[SIDE] = "dex1"
        f = self.serve_from()
        sc.geom(sc.wb, "server_stand", type="cylinder", pos=(f[0] + 0.25, f[1], (f[2] - 0.15) / 2),
                size=(0.03, (f[2] - 0.15) / 2), rgba=(0.3, 0.3, 0.33, 1), **VISUAL)
        sc.camera("venue", (-7.5, cy - 3.5, 5.5), (nx - 2.0, cy, 0.0), fovy=50)

    def reset(self, w):
        """The racket's handle along the right gripper's fingers (its axis the fingers' axis, the strings' normal the
        closing axis), the butt BUTT_FROM_JAW_CENTRE_M before the jaws' centre; then the jaws close on it (the full
        command: 120 N) and the grasp settles."""
        w.pin("ball", tuple(self.serve_from()))
        c, R = w.jaw_frame(SIDE)
        q = np.zeros(4)
        mujoco.mju_mat2Quat(q, R.ravel())
        w.put("racket", c - BUTT_FROM_JAW_CENTRE_M * R[:, 2], quat=q)
        self.grasp = w.close_on(SIDE, "racket")

    def referee_reset(self, w, ref):
        p = self.p
        self.ball = ref.geoms(body="ball")
        self.racket = ref.geoms(body="racket")
        self.handle = ref.geoms(names=["racket_handle"])
        self.body = ref.part("robot")
        self.netg = ref.geoms(body="net")
        self.jaws = (ref.geoms(body=f"{SIDE}_hand_jaw_a"), ref.geoms(body=f"{SIDE}_hand_jaw_b"))
        self.trackers = {"served": False, "speed": 0.0, "both_jaws_t": 0.0, "hit_spin_rad_s": None,
                         "racket": Touch(ref, self.ball, self.racket, gap=p["retouch_gap_s"]),
                         "ground": Touch(ref, self.ball, ref.ground, gap=p["bounce_gap_s"]),
                         "net": Crossing((1, 0, 0), p["net_x_m"], direction=1)}

    def before_step(self, w):
        p, tr = self.p, self.trackers
        if not tr["served"] and w.t >= p["serve_time_s"] - 1e-9:
            tr["served"] = True
            v, spin = self.serve_velocity()
            w.launch("ball", tuple(self.serve_from()), tuple(v), angvel=tuple(spin))
            w.ref.event("serve")

    # ------------------------------------------------------------------ the referee
    def in_hand(self, ref) -> bool:
        return ref.touching(self.handle, self.jaws[0]) and ref.touching(self.handle, self.jaws[1])

    def substep(self, w, ref):
        p, tr = self.p, self.trackers
        nx, cy = p["net_x_m"], p["centre_y_m"]
        if self.in_hand(ref):
            tr["both_jaws_t"] = round(ref.time, 4)
        else:
            gap = round(ref.time - tr["both_jaws_t"], 4)
            if gap > ref.metrics.get("grip_break_max_s", 0.0):
                ref.metrics["grip_break_max_s"] = gap       # (reported: the longest break of the two-jaw contact)
            if gap > p["out_of_hand_s"] + 1e-9:
                return ref.fail("the racket left your hand", out_s=gap)
        if ref.touching(ref.robot_mask, self.netg):
            return ref.fail("you touched the net", parts=sorted(ref.parts_touching(self.netg)))
        if ref.touching(self.racket, self.netg):
            return ref.fail("the racket touched the net")
        pts = np.r_[ref.contact_points(ref.robot_mask, ref.ground), ref.contact_points(self.racket, ref.ground)]
        if len(pts) and float(np.max(pts[:, 0])) > nx:
            return ref.fail("you touched the far side of the court")
        if not tr["served"]:
            if ref.touching(self.ball, ref.robot_mask | self.racket):
                rk = ["racket"] if ref.touching(self.ball, self.racket) else []
                ref.fail("the ball was touched before the serve", parts=sorted(ref.parts_touching(self.ball)) + rk)
            return
        b = w.pos("ball")
        came, tr["speed"] = tr["speed"], round(float(np.linalg.norm(w.vel("ball"))), 3)   # (the speed one step ago)
        if ref.touching(self.ball, self.body):
            return ref.fail("the ball touched you", parts=sorted(ref.parts_touching(self.ball)))
        rk = tr["racket"]
        if rk.update():
            if rk.count > 1:
                return ref.fail("the racket hit the ball twice")
            if not ref.stage("racket", speed_in_m_s=came):
                return ref.fail("the racket hit the ball before it bounced")
            tr["ground"].rearm()                             # a contact with the ground that begins now is a new one
        if rk.active and rk.duration > p["max_touch_s"]:
            return ref.fail("the racket carried the ball", touch_s=round(rk.duration, 3))
        x = tr["net"].update(b)
        if x is not None and ref.has("racket"):
            dy = float(x[1]) - cy
            if abs(dy) > POST_Y or x[2] > net_top(dy):
                ref.stage("over the net", y=round(float(x[1]), 3), z=round(float(x[2]), 3),
                          clearance_m=round(float(x[2] - net_top(dy)), 3))
            else:
                return ref.fail("the ball went through the net")
        if tr["ground"].update():
            if b[0] <= nx:
                if not ref.has("bounce"):
                    ref.stage("bounce", x=round(float(b[0]), 3), y=round(float(b[1]), 3))
                elif not ref.has("racket"):
                    ref.fail("the ball bounced twice before the racket hit it")
                else:
                    ref.fail("the ball landed on your own side")
            elif not ref.has("over the net"):               # (a guard for other serve numbers: the serve fell short)
                ref.fail("the serve did not reach your side")
            else:
                ref.metrics["landing_x_m"], ref.metrics["landing_y_m"] = round(float(b[0]), 3), round(float(b[1]), 3)
                if b[0] <= nx + HALF_LENGTH and abs(b[1] - cy) <= HALF_WIDTH:
                    if ref.stage("in"):
                        ref.succeed()
                else:
                    ref.fail("the ball landed outside the court")

    def privileged(self, w):
        p, tr = self.p, self.trackers
        _, va = w.free["racket"]
        return {"ball": w.pos("ball").tolist(), "ball_velocity": w.vel("ball").tolist(),
                "racket_pos": w.pos("racket").tolist(), "racket_quat": w.d.xquat[w.m.body("racket").id].tolist(),
                "racket_velocity": w.d.qvel[va:va + 3].tolist(), "racket_angvel": w.d.qvel[va + 3:va + 6].tolist(),
                "racket_in_hand_t": tr["both_jaws_t"],
                "served": bool(tr["served"]), "serve_time_s": p["serve_time_s"],
                "net": {"x": p["net_x_m"], "centre_y": p["centre_y_m"], "top_centre": NET_CENTRE, "top_post": NET_POST,
                        "post_y": POST_Y}, "racket": FREE_RACKET}
