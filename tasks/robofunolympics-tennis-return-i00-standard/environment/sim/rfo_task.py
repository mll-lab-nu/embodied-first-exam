"""Tennis, return of serve (ITF Rules of Tennis): a 30 m/s serve comes from the far baseline into your right service
box; after its one bounce, hit it with the racket on your right hand back over the net into the singles court.

Official setting: the ITF singles court (Rule 1), the net with its sag (0.914 m at the centre strap, 1.07 m at the
posts), the ITF ball of rfo.scene.OFFICIAL in air (drag; Magnus lift with the tennis coefficient, below), a 27 inch,
0.30 kg racket inside the limits of Appendix II clamped in the hand. Nothing is scaled to the robot.

Where the numbers come from:
* the court, the net and the lines: ITF Rule 1 (all measurements to the outside of the lines);
* the ball: scene.OFFICIAL["tennis"] (Rule 3 / Appendix I: 56.0-59.4 g, 6.54-6.86 cm, rebound 135-147 cm from 254 cm);
  its Magnus coefficient is RoboOlympics tennis' (sports/tennis/sim/tn.py: C_L = 1 / (2 + 1/S), the Goodwill fit;
  in MuJoCo's form F = c rho V (w x v) that is c = 0.375 / (1 + 2 S), 0.29 at S = 0.15) instead of the generic 1.0,
  which would make a ball that has just bounced (2000-4000 rpm of topspin from the court's friction) dive at
  several g;
* the serve: tn.py's opponent serve (level 4): struck 0.2 m behind the baseline, 0.8 m to the server's right of the
  centre mark, "flat" = 42 rad/s of topspin; the target is that generator's first draw (seed [404, 11, 0]: a serve
  down the T, 0.60 m from the centre line and 5.35 m from the net), not chosen for being returnable; 30 m/s and the
  2.70 m strike height are the family's (FAMILIES.md). The elevation and the azimuth below are solved so that the
  ball of this module lands on that target (tests/test_tennis_return.py checks it);
* the racket: 0.685 m long, strung surface an ellipse 0.33 m x 0.25 m (645 cm^2, "100 square inches"), 0.30 kg,
  balance 0.32 m from the butt; the ball-string contact is an explicit MuJoCo pair, a spring-damper of 4 ms dwell
  whose restitution on a clamped racket is 0.85 (measured 0.85 at 5-35 m/s) and friction 0.4 (tn.py's): no gain.
  The racket is as light as a real one, so what the ball gets is what the arm delivers.
"""
import math
import xml.etree.ElementTree as ET

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


# ---------------------------------------------------------------------------------- the racket (ITF Appendix II)
# In the wrist mount's frame (+z along the forearm, away from the wrist; +-x the palm's two broad sides): the handle
# lies along the forearm with its butt 2.5 cm behind the wrist, the strings' normal is the mount's x axis.
RACKET = dict(length_m=0.685, width_m=0.25, strung_length_m=0.33, strung_width_m=0.25, mass_kg=0.30,
              balance_from_butt_m=0.32, butt_z_m=-0.025, head_centre_z_m=0.495, half_thickness_m=0.0125,
              restitution_clamped=0.85, string_friction=0.4)
HEAD_A, HEAD_B = RACKET["strung_length_m"] / 2, RACKET["strung_width_m"] / 2
STRING_SOLREF = "-616850 -84"                   # 785 rad/s (4 ms on the strings); the damping gives e = 0.85 (measured)


def build_racket(sc, balls=("ball",)) -> None:
    zc, t, n = RACKET["head_centre_z_m"], RACKET["half_thickness_m"], 24
    ring = [(HEAD_B * math.sin(2 * math.pi * i / n), zc + HEAD_A * math.cos(2 * math.pi * i / n)) for i in range(n)]
    ET.SubElement(sc.root.find("asset"), "mesh", name="racket_head",
                  vertex=" ".join(f"{c:.5f}" for x in (-t, t) for y, z in ring for c in (x, y, z)))
    frame = "".join(
        f'<geom name="racket_frame{i}" type="capsule" fromto="0 {ring[i][0]:.4f} {ring[i][1]:.4f} 0 '
        f'{ring[(i + 1) % n][0]:.4f} {ring[(i + 1) % n][1]:.4f}" size="{t + 0.001}" mass="0" rgba="0.1 0.1 0.12 1" '
        'contype="0" conaffinity="0"/>' for i in range(n))
    sc.hand_tools["right"] = (
        '<geom name="racket_handle" type="capsule" fromto="0 0 -0.010 0 0 0.325" size="0.015" mass="0.174" '
        'rgba="0.1 0.1 0.12 1" contype="4" conaffinity="0"/>'
        '<geom name="racket_head" type="mesh" mesh="racket_head" mass="0.126" rgba="0.95 0.9 0.35 0.55" contype="4" '
        'conaffinity="0"/>' + frame)
    for b in balls:
        ET.SubElement(sc.root.find("contact"), "pair", name=f"{b}_strings", geom1=b, geom2="racket_head", condim="3",
                      friction="{0} {0} 0.005 0.0001 0.0001".format(RACKET["string_friction"]), solref=STRING_SOLREF,
                      solimp="0.95 0.99 0.001")


class Task(TaskBase):
    name = "tennis-return"
    title = "Tennis: return of serve"
    category = "basketball-and-rackets"
    robot = "unitree_h1"
    rulebook = ("ITF Rules of Tennis 2024: Rule 1 (the court), Rule 3 and Appendix I (the ball), Rule 4 and "
                "Appendix II (the racket), Rule 12 (a ball on a line), Rules 24 and 25 (losing the point, a good "
                "return)")
    deviations = [
        "Rules 16-21 (the service): the server is a machine: the ball appears at the server's strike point and "
        "leaves it with the serve's velocity and spin {serve_time_s} s after the start; there is no opponent, the "
        "attempt ends when your return lands",
        "Rule 4 (the racket in the hand): the racket is clamped to the right hand with its handle along the forearm "
        "(the hand has no fingers to change the grip); it cannot be dropped or thrown",
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
    legal_ground = ("left_foot", "right_foot", "right_tool")       # the racket may touch the ground (it is not a fall)
    params = dict(
        court_length_m=23.77, court_width_m=8.23, service_line_m=6.40, net_centre_m=NET_CENTRE, net_post_m=NET_POST,
        post_outside_m=POST_OUT, line_width_m=LINE,
        net_x_m=12.385, centre_y_m=2.75,                              # the court in the robot's starting frame
        serve_time_s=3.0, serve_speed_m_s=30.0, serve_height_m=2.70, serve_behind_baseline_m=0.20,
        serve_right_of_mark_m=0.80, serve_topspin_rad_s=42.0, serve_elevation_deg=-2.238, serve_azimuth_deg=4.583,
        max_touch_s=0.05, retouch_gap_s=0.05, bounce_gap_s=0.02, fall_z_m=0.35)

    sentence = ("Return the serve: after the tennis ball has bounced once in your service box, hit it with the racket "
                "on your right hand back over the net so that it lands in the singles court on the far side.")
    rules = (
        "The court is the ITF singles court: {court_length_m} m long and {court_width_m} m wide, measured to the "
        "outside of the lines, with a service line {service_line_m} m from the net on each side. The net stands "
        "across the middle, {net_centre_m} m high at its centre and rising in a straight line to {net_post_m} m at "
        "the posts, which stand {post_outside_m} m outside the sidelines. The ball is the ITF ball (radius 0.0335 m, "
        "0.0577 kg, with air drag and spin lift); the racket (0.685 m long, 0.30 kg, strung surface 0.33 m by 0.25 "
        "m) is fixed to your right hand. {serve_time_s} s after the start the ball is served from behind the far "
        "baseline at {serve_speed_m_s} m/s into your right service box. In order: the ball bounces once on your "
        "side; your racket hits it (any part of the racket counts); its centre passes the net's plane from your "
        "side to the far side, above the net's top edge or outside a post (it may touch the net or a post on the "
        "way); and its first contact with the ground after that is inside the far half of the singles court, the "
        "lines included (the point under the ball's centre decides; ground contacts less than {bounce_gap_s} s apart "
        "are one bounce): that is the success. You fail if the racket "
        "touches the ball before its bounce (a volley), if the ball bounces a second time on your side before your "
        "hit, if after your hit the ball touches the ground on your side or outside the far court, if the ball "
        "touches any part of you other than the racket at any time after the serve, if the racket touches the ball "
        "a second time (contacts less than {retouch_gap_s} s apart are one hit) or stays on it longer than "
        "{max_touch_s} s, if the ball passes the net's plane between the posts below the net's top edge, if any "
        "part of you or the racket touches the net or a post, or the ground beyond the net's plane, if anything of "
        "you touches the ball before it is served, if you fall, or after {time_limit_s} s. A fall is: your pelvis "
        "lower than {fall_z_m} m above the ground, or any part of you other than your feet touching the ground; the "
        "racket may touch the ground.")
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
        "handle lies along your right forearm; its strings face the way your palm faces.")
    difficulty = ("The ball crosses the whole court in about a second and is still moving at more than 15 m/s when "
                  "it reaches you, so the racket has to be in a path a few centimetres wide at an instant you must "
                  "predict, and a robot that only walks cannot go far to meet it. A racket merely held in the way "
                  "sends the ball back at a fraction of its speed, well short of the net twelve metres away: the "
                  "return needs a real swing through a 0.30 kg racket.")

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
        build_racket(sc)
        f = self.serve_from()
        sc.geom(sc.wb, "server_stand", type="cylinder", pos=(f[0] + 0.25, f[1], (f[2] - 0.15) / 2),
                size=(0.03, (f[2] - 0.15) / 2), rgba=(0.3, 0.3, 0.33, 1), **VISUAL)
        sc.camera("venue", (-7.5, cy - 3.5, 5.5), (nx - 2.0, cy, 0.0), fovy=50)

    def reset(self, w):
        w.pin("ball", tuple(self.serve_from()))

    def referee_reset(self, w, ref):
        p = self.p
        self.ball = ref.geoms(body="ball")
        self.racket = ref.part("right_tool")
        self.body = ref.part("robot") & ~self.racket
        self.netg = ref.geoms(body="net")
        self.trackers = {"served": False, "speed": 0.0,
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
    def substep(self, w, ref):
        p, tr = self.p, self.trackers
        nx, cy = p["net_x_m"], p["centre_y_m"]
        if ref.touching(ref.robot_mask, self.netg):
            return ref.fail("you touched the net", parts=sorted(ref.parts_touching(self.netg)))
        pts = ref.contact_points(ref.robot_mask, ref.ground)
        if len(pts) and float(np.max(pts[:, 0])) > nx:
            return ref.fail("you touched the far side of the court")
        if not tr["served"]:
            if ref.touching(self.ball, ref.robot_mask):
                ref.fail("the ball was touched before the serve", parts=sorted(ref.parts_touching(self.ball)))
            return
        b = w.pos("ball")
        came, tr["speed"] = tr["speed"], round(float(np.linalg.norm(w.vel("ball"))), 3)   # (the speed one step ago)
        if ref.touching(self.ball, self.body):
            return ref.fail("the ball touched you", parts=sorted(ref.parts_touching(self.ball) - {"right_tool"}))
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
        p = self.p
        return {"ball": w.pos("ball").tolist(), "ball_velocity": w.vel("ball").tolist(),
                "served": bool(self.trackers["served"]), "serve_time_s": p["serve_time_s"],
                "net": {"x": p["net_x_m"], "centre_y": p["centre_y_m"], "top_centre": NET_CENTRE, "top_post": NET_POST,
                        "post_y": POST_Y}, "racket": RACKET}
