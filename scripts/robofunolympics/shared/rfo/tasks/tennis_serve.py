"""Tennis, the serve (ITF Rules of Tennis, Rules 16-19 and 22): from behind your baseline, release the ball in your
left hand, strike it with the racket on your right hand before it reaches the ground, over the net into the service
box diagonally opposite. A serve that touches the net and is otherwise good is a let and is served again, once.

Official setting: the ITF singles court (Rule 1), the net with its sag (0.914 m at the centre strap, 1.07 m at the
posts), the ITF ball of rfo.scene.OFFICIAL in air (drag; Magnus lift with the tennis coefficient, below), a 27 inch,
0.30 kg racket inside the limits of Appendix II clamped in the hand. Nothing is scaled to the robot.

Where the numbers come from:
* the court, the net and the lines: ITF Rule 1 (all measurements to the outside of the lines);
* the ball: scene.OFFICIAL["tennis"] (Rule 3 / Appendix I); its Magnus coefficient is RoboOlympics tennis'
  (sports/tennis/sim/tn.py: C_L = 1 / (2 + 1/S); in MuJoCo's form F = c rho V (w x v) that is c = 0.375 / (1 + 2 S),
  0.29 at S = 0.15) instead of the generic 1.0;
* the racket: 0.685 m long, strung surface an ellipse 0.33 m x 0.25 m (645 cm^2), 0.30 kg, balance 0.32 m from the
  butt; the ball-string contact is an explicit MuJoCo pair, a spring-damper of 4 ms dwell whose restitution on a
  clamped racket is 0.85 (measured) and friction 0.4 (tn.py's): no gain (tn.py's RACKET_GAIN = 5 is not used);
* the service rules: Rule 16 (at rest behind the baseline, release by hand, strike before the ball lands), Rule 17
  (from the right half into the diagonally opposite box), Rule 18 (foot faults), Rule 19 (faults), Rule 22 (the let).
  The spare ball for a let waits in a cup on a stand beside the server (a player's pocket).
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


SPARE = "ball2"


class Task(TaskBase):
    name = "tennis-serve"
    title = "Tennis: serve"
    category = "basketball-and-rackets"
    robot = "unitree_h1"
    rulebook = ("ITF Rules of Tennis 2024: Rule 1 (the court), Rule 3 and Appendix I (the ball), Rule 4 and "
                "Appendix II (the racket), Rule 12 (a ball on a line), Rules 16-19 (the service, its order, the foot "
                "fault, the service fault), Rule 22 (the let)")
    deviations = [
        "Rules 5-11, 20, 23-26 (the point): one first serve only, with no receiver; a fault ends the attempt as a "
        "failure (there is no second serve after a fault), a good serve ends it as the success",
        "Rule 22 (the let is replayed, as often as it happens): a let is replayed {lets_replayed} time(s), with the "
        "spare ball that waits in a cup on a stand {spare_y_m} m to your left; a further let ends the attempt as a "
        "failure",
        "Rule 16 ('stand at rest ... immediately before starting the service motion'): made measurable: both feet "
        "on the ground and neither moved more than {rest_move_m} m during the {rest_s} s before the ball leaves the "
        "hand; the service motion is the time from that release to the racket's strike",
        "Rule 18 a ('slight movements of the feet are permitted', no walking or running): made measurable: during "
        "the service motion no foot may touch the ground more than {foot_move_m} m from where it stood at the release",
        "Rule 19 Case 1 (a toss that the server does not try to hit may be caught or let drop and tossed again): the "
        "intention cannot be judged and the hand takes the ball only once: one toss per serve; a tossed ball that "
        "reaches the ground unstruck is a fault",
        "Rule 16 (release 'by hand'): the hand's grip is a weld that is switched off; so that a ball struck out of "
        "the hand is not a serve, the ball must have been touching nothing of you for {toss_free_s} s when the "
        "racket strikes it",
        "Rule 16 ('hit the ball with the racket'): so that a ball thrown past the racket is not a serve, the hit "
        "must add speed: {retouch_gap_s} s after its last contact with the racket the ball must be faster than it "
        "was when it reached the racket; and the ball may move at most {toss_max_speed_m_s} m/s when it reaches the "
        "racket (the speed of a ball that has fallen about 1.3 m: a toss, not a throw)",
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
    time_limit_s = 20.0
    fall_z = 0.35                                                  # = params["fall_z_m"] (configure)
    start = (0.0, 0.0, 0.0)
    stages = ["toss", "strike", "over the net", "in"]
    legal_ground = ("left_foot", "right_foot", "right_tool")       # the racket may touch the ground (it is not a fall)
    params = dict(
        court_length_m=23.77, court_width_m=8.23, service_line_m=6.40, net_centre_m=NET_CENTRE, net_post_m=NET_POST,
        post_outside_m=POST_OUT, line_width_m=LINE,
        net_x_m=12.385, centre_y_m=1.0,                               # the court in the robot's starting frame
        rest_s=0.5, rest_move_m=0.02, foot_move_m=0.30, toss_free_s=0.10, toss_max_speed_m_s=5.0, max_touch_s=0.05,
        retouch_gap_s=0.05,
        bounce_gap_s=0.02, lets_replayed=1, spare_x_m=0.25, spare_y_m=0.60, spare_z_m=1.05, fall_z_m=0.35)

    sentence = ("Serve: from behind your baseline, release the tennis ball in your left hand, strike it with the "
                "racket on your right hand before it reaches the ground, and send it over the net into the service "
                "box diagonally opposite.")
    rules = (
        "The court is the ITF singles court: {court_length_m} m long and {court_width_m} m wide, measured to the "
        "outside of the lines, with a service line {service_line_m} m from the net on each side and a centre "
        "service line that divides the space between the net and each service line into two service boxes. The net "
        "stands across the middle, {net_centre_m} m high at its centre and rising in a straight line to "
        "{net_post_m} m at the posts, which stand {post_outside_m} m outside the sidelines. The ball is the ITF "
        "ball (radius 0.0335 m, 0.0577 kg, with air drag and spin lift) and starts gripped in your left hand; the "
        "racket (0.685 m long, 0.30 kg, strung surface 0.33 m by 0.25 m) is fixed to your right hand. You serve "
        "from the right of the centre mark into the far service box on the left of the centre line. In order: "
        "(1) the toss: you let go of the ball (the grip takes a ball only once) while you stand at rest, both feet "
        "on the ground behind the baseline, between the extension of the centre mark and the extension of the "
        "right sideline, neither foot having left the ground or moved more than {rest_move_m} m in the last "
        "{rest_s} s (so not before {rest_s} s after the start); (2) the strike: your racket hits the ball before it reaches the ground (any part of the "
        "racket counts), the ball having touched nothing of you for the last {toss_free_s} s and moving at most "
        "{toss_max_speed_m_s} m/s when it reaches the racket (a toss, not a throw), and the hit speeds "
        "the ball up ({retouch_gap_s} s after its last contact with the racket it is faster than it was when it "
        "reached the racket); (3) the ball's centre passes the net's plane between the posts above the net's top "
        "edge; (4) its first contact with the ground is inside that service box, the lines included (the point "
        "under the ball's centre decides; ground contacts less than {bounce_gap_s} s apart are one): that is the "
        "success. From the release to the strike your feet may not touch the baseline or the court, the ground "
        "beyond the sideline's extension or the centre mark's extension, nor the ground more than {foot_move_m} m "
        "from where each stood at the release (a foot fault); after the strike you may step anywhere on your side. "
        "A serve that touches the net and still lands in the box is a let: it does not count, and you serve again, "
        "under the same rules, with the spare ball (your left hand's grip can take it from then on); this happens "
        "at most {lets_replayed} time(s), a further let fails. You fail on any fault: releasing the ball when not "
        "at rest in the server's position, a foot fault, the tossed ball reaching the ground or passing the net "
        "unstruck, the racket striking the ball before it is clear of you, a ball that reaches the racket faster "
        "than {toss_max_speed_m_s} m/s, a hit that does not speed it up, the racket "
        "touching the struck ball again (contacts less than {retouch_gap_s} s apart are one hit) or staying on it "
        "longer than {max_touch_s} s, the served ball touching you, a net post, the ground on your side or the "
        "ground outside the service box, or passing the net's plane anywhere but over the net. You also fail if "
        "any part of you or the racket touches the net or a post, if you fall, or after {time_limit_s} s. A fall "
        "is: your pelvis lower than {fall_z_m} m above the ground, or any part of you other than your feet touching "
        "the ground; the racket may touch the ground.")
    venue = (
        "You stand as the server: your pelvis 0.5 m behind your baseline and {centre_y_m} m to the right of the "
        "centre mark, facing the net (+x), which is {net_x_m} m ahead of you. Painted on the court, all "
        "{line_width_m} m wide and inside the measurements: the two baselines, the two singles sidelines, the two "
        "service lines, the centre service line between them and a 0.10 m centre mark on each baseline; there are "
        "no doubles lines. Your target, the far service box on the left of the centre line, begins at the net and "
        "ends {service_line_m} m beyond it, and reaches from the centre service line 4.115 m to the left. The ball "
        "lies in your left palm; the spare ball rests in a cup on a thin stand, its centre {spare_x_m} m ahead of "
        "your pelvis, {spare_y_m} m to your left and {spare_z_m} m above the ground. The racket's handle lies along "
        "your right forearm; its strings face the way your palm faces. A ball is released when the hand's grip is "
        "switched off; it leaves with the hand's velocity.")
    difficulty = ("The ball must be struck in the air with the strings of a racket that reaches up to 2.7 m, leave "
                  "at well over 10 m/s in a narrow window of directions to clear a net 11.9 m away and still come "
                  "down within 6.4 m beyond it, and the swing that gives it that speed must not knock over or move "
                  "the feet of a body that stands without a balance controller. Both arms have to work in time: the "
                  "released ball is in the racket's reach for a few tenths of a second.")

    def configure(self, params):
        super().configure(params)
        self.fall_z = self.p["fall_z_m"]

    # ------------------------------------------------------------------ the venue
    def box(self):
        """The service box diagonally opposite, lines included: (x0, x1, y0, y1)."""
        p = self.p
        return (p["net_x_m"], p["net_x_m"] + SERVICE, p["centre_y_m"] - LINE / 2, p["centre_y_m"] + HALF_WIDTH)

    def build(self, sc):
        p = self.p
        nx, cy = p["net_x_m"], p["centre_y_m"]
        build_court(sc, nx, cy, balls=("ball", SPARE))
        x0, x1, y0, y1 = self.box()
        sc.zone("service_box", ((x0 + x1) / 2, (y0 + y1) / 2), ((x1 - x0) / 2 - LINE, (y1 - y0) / 2 - LINE),
                rgba=(0.95, 0.85, 0.2, 0.18))
        sc.ball("ball", "tennis", (0.4, 0.2, 1.1), grippable=True, fluidcoef=BALL_FLUID)
        sc.ball(SPARE, "tennis", (p["spare_x_m"], p["spare_y_m"], p["spare_z_m"]), grippable=True, fluidcoef=BALL_FLUID)
        # the spare ball's cup: a ring of six capsules on a thin stand; the ball rests in the ring
        ring_r, tube = 0.022, 0.004
        zr = p["spare_z_m"] - math.sqrt((BALL["radius"] + tube) ** 2 - ring_r ** 2)
        stand = sc.body("spare_stand", (p["spare_x_m"], p["spare_y_m"], 0.0))
        for i in range(6):
            a0, a1 = math.pi * i / 3, math.pi * (i + 1) / 3
            sc.geom(stand, f"spare_cup{i}", type="capsule", size=(tube,), rgba=(0.3, 0.3, 0.33, 1), **HITTABLE,
                    fromto=(ring_r * math.cos(a0), ring_r * math.sin(a0), zr,
                            ring_r * math.cos(a1), ring_r * math.sin(a1), zr))
        sc.geom(stand, "spare_post", type="cylinder", pos=(0, 0, (zr - 0.03) / 2), size=(0.012, (zr - 0.03) / 2),
                rgba=(0.3, 0.3, 0.33, 1), **HITTABLE)
        build_racket(sc, balls=("ball", SPARE))
        sc.camera("venue", (-7.5, cy - 4.5, 5.5), (nx - 2.0, cy, 0.0), fovy=50)

    def reset(self, w):
        m, d, p = w.m, w.d, self.p
        mujoco.mj_kinematics(m, d)
        R = d.xmat[w.robot.mount["left"]].reshape(3, 3)             # the palm faces the mount's +x
        w.put("ball", d.site_xpos[w.robot.palm["left"]] + R[:, 0] * (0.022 + BALL["radius"] + 0.004))
        w.grab("left", "ball", event=False)
        w.put(SPARE, (p["spare_x_m"], p["spare_y_m"], p["spare_z_m"]))

    def may_grip(self, w, side, name):
        tr = self.trackers                             # the first ball starts in the hand; the spare only after a let
        return side == "left" and name == tr.get("ball") and tr.get("phase") == "await"

    # ------------------------------------------------------------------ the referee
    def _feet_xy(self, w) -> list:
        return [round(float(x), 5) for s in ("left", "right") for x in w.d.site_xpos[w.robot.foot_site[s]][:2]]

    def _new_serve(self, ref, name: str) -> None:
        p, tr = self.p, self.trackers
        tr.update({"ball": name, "released": None, "last_touch": None, "net_touched": False, "feet0": None,
                   "speed": 0.0, "came": None, "sped_up": None,
                   "racket": Touch(ref, self.ballg[name], self.racket, gap=p["retouch_gap_s"]),
                   "ground": Touch(ref, self.ballg[name], ref.ground, gap=p["bounce_gap_s"]),
                   "net": Crossing((1, 0, 0), p["net_x_m"], direction=1)})

    def referee_reset(self, w, ref):
        self.racket = ref.part("right_tool")
        self.body = ref.part("robot") & ~self.racket
        self.feet = ref.part("feet")
        self.netg = ref.geoms(body="net")
        self.posts = ref.geoms(names=["net_postL", "net_postR"])
        self.mesh = ref.geoms(names=["net_L", "net_R"])
        self.ballg = {n: ref.geoms(body=n) for n in ("ball", SPARE)}
        # feet: where the feet were at the end of each of the last control steps (rest_s of them); feet_up: the last
        # time a foot was off the ground
        self.trackers = {"serve": 1, "phase": "hold", "feet": [self._feet_xy(w)], "feet_up": None}
        self._new_serve(ref, "ball")

    def _not_at_rest(self, w, ref):
        """Rule 16 at the release: None, or what was not at rest during the last rest_s seconds."""
        p, tr = self.p, self.trackers
        n = int(round(p["rest_s"] / w.CONTROL_DT))
        if not {"left_foot", "right_foot"} <= ref.parts_touching(ref.ground):
            return {"both_feet_down": False}
        if tr["feet_up"] is not None and ref.time - tr["feet_up"] < p["rest_s"]:
            return {"a_foot_was_up_s_ago": round(ref.time - tr["feet_up"], 3)}
        if len(tr["feet"]) < n + 1:
            return {"standing_s": round(ref.time, 3)}
        now = tr["feet"][-1]
        moved = max(math.hypot(now[i] - f[i], now[i + 1] - f[i + 1]) for f in tr["feet"] for i in (0, 2))
        return {"feet_moved_m": round(moved, 3)} if moved > p["rest_move_m"] else None

    def _where(self, w, ref):
        """Rule 18 b-d at this instant: where the feet touch the ground. None, or the foot fault."""
        p = self.p
        pts = ref.contact_points(self.feet, ref.ground)
        if not len(pts):
            return None
        if float(np.max(pts[:, 0])) >= p["net_x_m"] - HALF_LENGTH:
            return "a foot touched the baseline or the court"
        if float(np.min(pts[:, 1])) < p["centre_y_m"] - HALF_WIDTH:
            return "a foot touched the ground outside the sideline's extension"
        if float(np.max(pts[:, 1])) >= p["centre_y_m"] - LINE / 2:
            return "a foot touched the centre mark's extension"
        return None

    def substep(self, w, ref):
        p, tr = self.p, self.trackers
        if ref.touching(ref.robot_mask, self.netg):
            return ref.fail("you touched the net", parts=sorted(ref.parts_touching(self.netg)))
        name = tr["ball"]
        ball = self.ballg[name]
        if tr["phase"] == "await":                     # after a let: the spare ball must be taken into the hand
            if w.holder(name):
                tr["phase"] = "hold"
            return
        if tr["phase"] == "hold":
            if w.holder(name):
                return
            why = self._not_at_rest(w, ref)
            if why:
                return ref.fail("you were not standing at rest when you released the ball", **why)
            why = self._where(w, ref)
            if why:
                return ref.fail("you did not stand in the server's position when you released the ball: " + why)
            tr.update(phase="toss", released=ref.time, last_touch=ref.time, feet0=self._feet_xy(w))
            ref.stage("toss")
        b = w.pos(name)
        came, tr["speed"] = tr["speed"], round(float(np.linalg.norm(w.vel(name))), 3)     # (the speed one step ago)
        rk = tr["racket"]
        new = rk.update()
        if tr["phase"] == "toss":
            why = self._where(w, ref)
            if why:
                return ref.fail("foot fault: " + why)
            if ref.touching(ball, self.body):
                tr["last_touch"] = ref.time
            if new:
                clear = ref.time - tr["last_touch"]
                if clear < p["toss_free_s"]:
                    return ref.fail("the racket struck the ball before it was clear of you", clear_s=round(clear, 3))
                if came > p["toss_max_speed_m_s"]:
                    return ref.fail("the ball was thrown, not tossed", speed_before_m_s=came)
                tr["phase"], tr["came"] = "served", came
                ref.stage("strike", ball_height_m=round(float(b[2]), 3), speed_before_m_s=came)
            elif ref.touching(ball, ref.ground):
                return ref.fail("the tossed ball reached the ground unstruck")
            elif tr["net"].update(b) is not None:
                return ref.fail("the ball passed the net without a racket strike")
            return
        # the served ball
        if new and rk.count > 1:
            return ref.fail("the racket hit the ball twice")
        if rk.active and rk.duration > p["max_touch_s"]:
            return ref.fail("the racket carried the ball", touch_s=round(rk.duration, 3))
        if tr["sped_up"] is None and not rk.active:    # the hit is over ({retouch_gap_s} s after its last contact)
            tr["sped_up"] = bool(tr["speed"] > tr["came"])
            ref.metrics["strike_speed_m_s"] = tr["speed"]
            if not tr["sped_up"]:
                return ref.fail("the racket did not speed the ball up", before_m_s=tr["came"], after_m_s=tr["speed"])
        if ref.touching(ball, self.body):
            return ref.fail("the served ball touched you", parts=sorted(ref.parts_touching(ball) - {"right_tool"}))
        if ref.touching(ball, self.posts):
            return ref.fail("the serve touched a net post")
        if ref.touching(ball, self.mesh):
            tr["net_touched"] = True
        x = tr["net"].update(b)
        if x is not None:
            dy = float(x[1]) - p["centre_y_m"]
            if abs(dy) <= POST_Y and x[2] > net_top(dy):
                ref.stage("over the net", y=round(float(x[1]), 3), z=round(float(x[2]), 3),
                          clearance_m=round(float(x[2] - net_top(dy)), 3),
                          speed_m_s=round(float(np.linalg.norm(w.vel(name))), 2))
            else:
                return ref.fail("the serve did not pass over the net")
        if tr["ground"].update():
            x0, x1, y0, y1 = self.box()
            if b[0] <= p["net_x_m"]:
                return ref.fail("the serve landed on your own side")
            ref.metrics["landing_x_m"], ref.metrics["landing_y_m"] = round(float(b[0]), 3), round(float(b[1]), 3)
            if not (b[0] <= x1 and y0 <= b[1] <= y1):
                return ref.fail("the serve landed outside the service box")
            if not tr["net_touched"]:
                if ref.stage("in"):
                    ref.succeed()
            elif tr["serve"] > p["lets_replayed"]:
                ref.fail("a second let")
            else:                                      # a let: the serve is replayed with the spare ball
                ref.event("let", serve=tr["serve"])
                ref.metrics["lets"] = tr["serve"]
                tr["serve"] += 1
                tr["phase"] = "await"
                self._new_serve(ref, SPARE)

    def step(self, w, ref):
        p, tr = self.p, self.trackers
        xy = self._feet_xy(w)
        down = ref.parts_touching(ref.ground)
        tr["feet"] = tr["feet"][-int(round(p["rest_s"] / w.CONTROL_DT)):] + [xy]
        if not {"left_foot", "right_foot"} <= down:
            tr["feet_up"] = round(ref.time, 4)
        if tr["phase"] == "toss":                      # Rule 18 a: no walking during the service motion
            for i, foot in ((0, "left_foot"), (2, "right_foot")):
                d = math.hypot(xy[i] - tr["feet0"][i], xy[i + 1] - tr["feet0"][i + 1])
                if foot in down and d > p["foot_move_m"]:
                    return ref.fail("foot fault: you changed position by walking", foot=foot, moved_m=round(d, 3))

    def privileged(self, w):
        p, tr = self.p, self.trackers
        x0, x1, y0, y1 = self.box()
        return {"ball": w.pos(tr["ball"]).tolist(), "ball_velocity": w.vel(tr["ball"]).tolist(),
                "ball_in_play": tr["ball"], "phase": tr["phase"], "serve": tr["serve"],
                "spare_ball": w.pos(SPARE).tolist(), "service_box": {"x": [x0, x1], "y": [y0, y1]},
                "net": {"x": p["net_x_m"], "centre_y": p["centre_y_m"], "top_centre": NET_CENTRE, "top_post": NET_POST,
                        "post_y": POST_Y}, "racket": RACKET}
