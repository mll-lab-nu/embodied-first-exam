"""Volleyball serve (FIVB Rule 12): nothing grips: the ball rests on the open left palm (palm up) and only gravity and
friction keep it there; it can roll off. The toss is the arm's own movement throwing the ball up off the palm. From
behind the end line, toss the ball and hit it with one hand or arm over the 2.43 m net into the opponent's court."""
import math
import xml.etree.ElementTree as ET

import numpy as np

import mujoco

from rfo.referee import Crossing, Flights
from rfo.scene import HITTABLE, OFFICIAL, VISUAL, WHITE, quat_z
from rfo.task import TaskBase

BALL = OFFICIAL["volleyball"]
ARM = {s: {f"{s}_hand", f"{s}_forearm", f"{s}_upper_arm"} for s in ("left", "right")}
HANDS = {"left_hand", "right_hand"}


class Strike:
    """One strike of the ball by the robot: from the first contact until the ball has been clear of the robot for
    `clear_s`. It records the ball's velocity at the last physics step before the first contact (v_in) and at the
    last separation (v_out), the parts that touched and the contact points."""

    def __init__(self, ref, ball, clear_s: float):
        self.ref, self.ball, self.clear_s = ref, ball, clear_s
        self.phase = 0                      # 0: not begun; 1: begun, the ball not yet clear; 2: over
        self.v_free = self.v_in = self.v_out = None
        self.t0 = self.t_last = None
        self.touching = False
        self.parts: set = set()

    def update(self, vel) -> str | None:
        """Once per physics step. "start" at the first contact, "end" when the ball has got clear, else None."""
        ref, out = self.ref, None
        now = ref.touching(self.ball, ref.robot_mask)
        if self.phase == 0:
            if now:
                self.phase, self.t0, self.t_last = 1, ref.time, ref.time
                self.v_in = self.v_free if self.v_free is not None else [float(x) for x in vel]
                out = "start"
            else:
                self.v_free = [float(x) for x in vel]
        elif self.phase == 1:
            if now:
                self.t_last = ref.time
            else:
                if self.touching:
                    self.v_out = [float(x) for x in vel]
                if ref.time - self.t_last >= self.clear_s:
                    self.phase, out = 2, "end"
        if now and self.phase == 1:
            self.parts |= ref.parts_touching(self.ball)
        self.touching = now
        return out

    @property
    def duration(self) -> float:
        return 0.0 if self.t0 is None else self.t_last - self.t0

    def speeds(self) -> tuple[float, float]:
        return float(np.linalg.norm(self.v_in)), float(np.linalg.norm(self.v_out))

    def state(self) -> list:
        return [self.phase, self.v_free, self.v_in, self.v_out, self.t0, self.t_last, self.touching, sorted(self.parts)]

def build_court(sc, p, centre, yaw):
    """The FIVB court (Rules 1 and 2) around the foot of the net's centre: 18 m x 9 m with 5 cm lines drawn inside
    it, the centre line, the attack lines (rear edge 3 m from the centre line's axis), the free zone, the men's net
    (1 m deep, its top at 2.43 m, 9.5 m long), the posts (2.55 m, 1 m outside the side lines) and the antennas (1.80 m
    long, 10 mm, above the side lines, 0.80 m above the net). Court frame: u from the net towards the opponent's
    court (the direction `yaw` in the world), v along the net to the left of it."""
    c, s = math.cos(yaw), math.sin(yaw)
    L, hw, top, lw = p["court_half_length_m"], p["court_width_m"] / 2, p["net_height_m"], 0.05

    def W(u, v):
        return (centre[0] + c * u - s * v, centre[1] + s * u + c * v)

    sc.geom(sc.wb, "free_zone", type="box", pos=(*W(0, 0), 0.0002), size=(L + 6.5, hw + 5.0, 0.0002), quat=quat_z(yaw),
            rgba=(0.18, 0.40, 0.62, 1), **VISUAL)
    sc.geom(sc.wb, "court", type="box", pos=(*W(0, 0), 0.0004), size=(L, hw, 0.0002), quat=quat_z(yaw),
            rgba=(0.86, 0.56, 0.30, 1), **VISUAL)
    for sg in (1, -1):
        sc.line(f"side_line{sg}", W(-L, sg * (hw - lw / 2)), W(L, sg * (hw - lw / 2)), width=lw)
        sc.line(f"end_line{sg}", W(sg * (L - lw / 2), -hw), W(sg * (L - lw / 2), hw), width=lw)
        a = p["attack_line_m"] - lw / 2
        sc.line(f"attack_line{sg}", W(sg * a, -hw), W(sg * a, hw), width=lw)
    sc.line("centre_line", W(0, -hw), W(0, hw), width=lw)
    net = sc.body("net", (centre[0], centre[1], 0.0), quat_z(yaw))
    sc.geom(net, "net_mesh", type="box", pos=(0, 0, top - 0.5), size=(0.004, 4.75, 0.5), rgba=(0.95, 0.95, 0.95, 0.45),
            **HITTABLE)
    sc.geom(net, "net_band", type="box", pos=(0, 0, top - 0.035), size=(0.006, 4.75, 0.035), rgba=WHITE, **VISUAL)
    for sg, tag in ((1, "L"), (-1, "R")):
        sc.geom(net, f"net_post{tag}", type="cylinder", pos=(0, sg * (hw + 1.0), 1.275), size=(0.05, 1.275),
                rgba=(0.3, 0.3, 0.33, 1), **HITTABLE)
        sc.geom(net, f"net_antenna{tag}", type="cylinder", pos=(0, sg * hw, top - 0.1), size=(0.005, 0.9),
                rgba=(0.9, 0.15, 0.15, 1), **HITTABLE)
        sc.geom(net, f"net_side_band{tag}", type="box", pos=(0, sg * (hw - 0.025), top - 0.5), size=(0.005, 0.025, 0.5),
                rgba=WHITE, **VISUAL)
    return W


def to_court(centre, yaw, pts):
    """World points (n, 2+) -> court coordinates (u, v)."""
    c, s = math.cos(yaw), math.sin(yaw)
    d = np.atleast_2d(np.asarray(pts, float))[:, :2] - np.asarray(centre, float)
    return np.c_[c * d[:, 0] + s * d[:, 1], -s * d[:, 0] + c * d[:, 1]]


def centre_line_fault(w, ref, centre, yaw) -> str | None:
    """FIVB 11.2.2: a foot wholly beyond the centre line (every point where it touches the floor is on the opponent's
    side of the line). Returns the foot, or None."""
    for side in ("left", "right"):
        pts = ref.contact_points(ref.part(f"{side}_foot"), ref.ground)
        if len(pts) and float(np.min(to_court(centre, yaw, pts)[:, 0])) > 0.025:
            return f"{side}_foot"
    return None



# ---- the ball on the open palm ----
# The H1-2's hand is a flat palm pad (4.4 x 8 x 10 cm, a box on the wrist mount; its broad face on the mount's +x is
# the palm). At rest the forearms point forward, the palms facing each other across the body; turning the left forearm
# by its elbow roll (-90 degrees) turns the left palm up, level, about 1.2 m above the floor, and the ball rests on it
# under its own weight: nothing else holds it. A ball on a level palm stays only while the palm stays level (the
# ball's rolling resistance, 4 mm, holds it on a palm tilted by up to about 2 degrees) and moves straight up or down:
# a palm moved sideways leaves the rolling ball behind. The start command PALM_UP is the palm-up pose with the arm's
# sag under the ball's weight taken out (the arms have no gravity feed-forward; measured offline with the ball's
# weight as a force on the palm): with the ball on it the palm settles level. Under that command, with the ball on the
# palm, the standing robot settles in about 2 s (its legs give a little; measured offline): it starts there, at rest
# (SETTLED: the pelvis' height and orientation, every joint), the ball resting on the palm where it then rests
# (BALL_ON_PALM: its centre in the mount's frame, from the middle of the palm's face). Started straight from the
# command, the first 0.1 s of the stand settling would drop the palm away from the ball.
# Measured: the ball stays on the palm, still, for the whole 8 s of the service.
PALM_UP = dict(left_shoulder_pitch=-0.0161, left_shoulder_roll=0.0002, left_elbow_pitch=-0.0239,
               left_elbow_roll=-1.5709, left_wrist_yaw=-0.0138)
SETTLED_Z_QUAT = (1.02075, 1.0, 0.00231, -0.0008, -0.00137)
SETTLED = (-0.01587, -0.15902, 0.03034, 0.35949, -0.20435, 0.19505, 0.01546, -0.16128, -0.02627, 0.36019, -0.19729,
           -0.17731, -1e-05, 0.00027, -1e-05, -4e-05, 7e-05, -1.57101, 2e-05, 0.00037, 0.01221, 0.00014, -4e-05,
           0.01816, 9e-05, 0.00759, -1e-05)
BALL_ON_PALM = (0.10499, -0.0051, 0.00906)
PAD_HALF, PAD_Z = 0.022, 0.05                  # the palm pad's half thickness and its centre along the forearm
# The palm-ball contact. The palm pad is the hand's rubber on a rigid mount; its contact with a ball is given the
# restitution of a ball on a supported human hand: Ivanova, "Energy transfer evaluation in the 'striker-ball' system
# during impact", ISBS 2000 (18th International Symposium on Biomechanics in Sports, Hong Kong), Table 1: a volleyball
# dropped 5.5 m (10.4 m/s) onto the hand of a player whose wrist rests on a table keeps 0.10 of its speed with the hand
# relaxed, 0.14 strained, 0.17 as a clenched fist; ball impacts last 5 to 20 ms. The pad is passive rubber (no muscle
# tone), so here the relaxed hand's 0.10: a critically damped spring of time constant 5 ms (MuJoCo's solref; solimp
# 0.99-0.999), measured against a pad fixed in space (every official ball alike: MuJoCo's contact
# is mass-normalised): a ball thrown head-on at 1 to 10.4 m/s keeps 0.09 to 0.11 of its speed (0.093 at 10.4 m/s)
# after 19 ms of contact. Friction 0.7 (rubber on a ball's cover; not separately measured). With elliptic friction
# cones and impratio 100 for the whole world (as in the worlds with a real gripper, realhand.py) a squeezed or resting
# ball stays put (tests); with the ball's own rule-book contact (rebound 0.85, a lightly damped spring) instead, a ball
# squeezed between two palms rattles out of them within a second. Every other contact of the ball keeps its own rule-book rebound.
PALM_SOLREF, PALM_SOLIMP, PALM_MU, PALM_REBOUND = "0.005 1", "0.99 0.999 0.001", 0.7, 0.10
CONE, IMPRATIO = "elliptic", 100.0


def _joint(w, name: str) -> int:
    return w.L.JOINTS.index(name + "_joint")


def palm_face(w, side: str) -> tuple[np.ndarray, np.ndarray]:
    """The centre of the pad's palm face (the mount's +x face) and its outward normal, in the world."""
    d, b = w.d, w.robot.mount[side]
    R = d.xmat[b].reshape(3, 3)
    return d.xpos[b] + R @ np.array([PAD_HALF, 0.0, PAD_Z]), R[:, 0].copy()


def palm_contact(sc, ball: str, roll: float) -> None:
    """The palm-ball pairs (both palms) and the world's friction cones."""
    opt = sc.root.find("option")
    opt.set("cone", CONE)
    opt.set("impratio", f"{IMPRATIO:g}")
    for side in ("left", "right"):
        ET.SubElement(sc.root.find("contact"), "pair", name=f"palm_ball_{side}", geom1=ball,
                      geom2=f"{side}_palm_pad", condim="6",
                      friction=f"{PALM_MU} {PALM_MU} 0.003 {roll} {roll}", solref=PALM_SOLREF,
                      solimp=PALM_SOLIMP)


def ball_on_palm(w) -> None:
    """t = 0: the robot settled under its start command (the left arm's is PALM_UP, the other joints' their rest),
    the ball resting on the left palm."""
    r, d = w.robot, w.d
    for jn, v in PALM_UP.items():
        i = _joint(w, jn)
        r.arb.q_a[i] = r.arb.q_b[i] = v
    d.qpos[r.fq + 2:r.fq + 7] = SETTLED_Z_QUAT
    d.qpos[r.qadr] = SETTLED
    mujoco.mj_kinematics(w.m, d)
    c, _ = palm_face(w, "left")
    R = d.xmat[r.mount["left"]].reshape(3, 3)
    w.put("ball", c + R @ np.array(BALL_ON_PALM))
# ---- end of the palm ----


class Task(TaskBase):
    name = "volleyball-serve"
    title = "Volleyball: serve"
    category = "football-and-volleyball"
    robot = "unitree_h1"
    rulebook = ("FIVB Official Volleyball Rules 2025-2028: Rule 1 (the court 18 m x 9 m, the service zone 9 m wide "
                "behind the end line), Rule 2 (the men's net, top at 2.43 m, the antennas), Rule 3 (the ball: 65-67 cm "
                "round, 260-280 g), Rule 8 (ball in and out: the lines belong to the court; a ball that touches an "
                "antenna or crosses the net's plane outside the crossing space is out), Rule 10.2 (the ball may touch "
                "the net while crossing it), Rule 12.4 (the service: the ball is hit with one hand or any part of the "
                "arm after being tossed or released from the hands; one toss only; the server does not touch the "
                "court or the floor outside the service zone at the hit; the hit comes within 8 s of the whistle)")
    deviations = [
        "Rule 12.4.1 (tossed or released from the hand(s)): the robot's hands are flat palm pads without fingers and "
        "without grip; the ball starts resting on the open left palm, turned up, and only its weight and friction "
        "keep it there (it rolls off a palm that tilts by more than about 2 degrees or moves sideways). The toss is "
        "the arm's own movement throwing the ball up off the palm (or letting it fall from it). The ball has left "
        "the hand when it has touched no part of the robot for {hold_gap_s} s; the release is the end of its last "
        "contact; until then only the hands may touch it. The palm pad's contact with the ball is that of "
        "a ball on a human hand (a ball thrown at a still palm keeps " + f"{PALM_REBOUND:.2f}" + " of its speed, as a volleyball dropped onto a supported, relaxed hand does: Ivanova, ISBS 2000), in the world's elliptic friction cones; every other contact keeps the ball's rule-book rebound.",
        "Rule 12.4.1 (tossed, then hit): a referee's eye for 'tossed, then hit' is replaced by "
        "numbers: after the release the ball must be clear of the robot for at least {toss_free_s} s before the "
        "hit, it may move at most {toss_max_speed_m_s} m/s just before the hit (the speed of a ball that has fallen "
        "about 1.3 m: a toss, not a throw), the hit's contacts last at most {strike_max_s} s, and the ball must "
        "leave the hit faster than it arrived.",
        "Rule 12.4.3 (the server's feet) is judged at the first contact of the hit, or at the take-off before it "
        "when the robot is in the air; the whistle is the start of the episode.",
        "No opponents (nobody receives the serve), no wind.",
    ]
    time_limit_s = 12.0
    start = (0.0, 0.0, 0.0)
    stages = ["toss", "hit", "over the net", "in the court"]
    fall_z = 0.35
    params = dict(court_half_length_m=9.0, court_width_m=9.0, net_height_m=2.43, attack_line_m=3.0, end_line_m=0.5,
                  service_time_s=8.0, hold_gap_s=0.03, release_grace_s=0.10, toss_free_s=0.10, toss_max_speed_m_s=5.0,
                  strike_max_s=0.10, clear_s=0.03, fall_z_m=0.35)

    sentence = ("Serve the volleyball: from behind the end line, toss it up off your open left palm and hit it with "
                "one hand or arm over the net into the opponent's court.")
    rules = ("You stand behind the end line of an official volleyball court ({court_half_length_m} m by "
             "{court_width_m} m on each side of the net), facing the net, midway between the side lines; the end "
             "line's outer edge is {end_line_m} m ahead of your pelvis and the net is {court_half_length_m} m beyond "
             "it, its top {net_height_m} m high, with an antenna above each side line. A volleyball (0.21 m across, "
             "0.27 kg, in air) starts resting on your open left palm, turned up. Your hands have no fingers and no "
             "grip (the grip columns of the action rows do nothing in this task): only the ball's weight and "
             "friction keep it on the palm, and it rolls off a palm that tilts or moves sideways. Until the toss "
             "only your hands (the palm pads and the wrists) may touch the ball, and the ball may not touch the "
             "floor. In order: (1) the toss: the ball has touched no part of you for {hold_gap_s} s; the release is "
             "the end of its last contact with a hand. For {release_grace_s} s from the release the hand that held "
             "it may still touch it (it follows the toss up; any other touch in that time is already the hit), and "
             "the ball must be clear of that hand when that time ends. (2) the hit: the next contact of the ball, "
             "with one hand or one arm of yours (hand, forearm or upper arm of the same side), within "
             "{service_time_s} s of the start. The ball must have been clear of you for at least {toss_free_s} s "
             "before the hit (counted from the end of the last touch of the toss), moving at most "
             "{toss_max_speed_m_s} m/s just before it; the hit's contacts last at most {strike_max_s} s (it is over "
             "when the ball has been clear of you for {clear_s} s), and the ball leaves the hit faster than it "
             "arrived. At the first contact of the hit no foot of yours touches the court (the end line included) or "
             "the floor beyond the extensions of the side lines; if you are in the air, this holds for where you "
             "took off. (3) the ball crosses the net's plane above the net and between the antennas; it may touch "
             "the net. (4) the ball's first contact with the floor is in the opponent's court ({court_half_length_m} "
             "m by {court_width_m} m, lines included): that is the success. You fail if the hit does not come within "
             "{service_time_s} s, if after the toss the ball touches the floor or any other part of you before the "
             "hit, if it is hit before it has been clear for {toss_free_s} s, if it moves faster than "
             "{toss_max_speed_m_s} m/s just before the hit, if the hit is made with more than one arm or another "
             "part, lasts longer than {strike_max_s} s or does not add speed, if you touch the ball again or hold it "
             "again, if a part of you other than the hands touches it before the toss, at a foot fault, if the ball "
             "crosses the net's plane under the net or outside the antennas or touches an antenna, if it lands "
             "anywhere else, if you fall (your pelvis lower than {fall_z_m} m above the floor, or any part of you "
             "other than the feet on the floor), or after {time_limit_s} s.")
    venue = ("You face the net (+x), which is 9.5 m ahead of you, from the middle of the service zone. Your upper "
             "arms hang and your forearms point forward; the left forearm is turned palm up (its elbow roll at -90 "
             "degrees) and the ball rests on the middle of the left palm, its centre about 1.3 m above the floor, "
             "0.43 m ahead of your pelvis and 0.21 m to its left. The start command keeps the palm level under the "
             "ball (the joint table's start angles are where the arm stands with the ball on it; the command differs "
             "from them by the arm's sag).")
    difficulty = ("The ball has to leave the hit at about 11 m/s (10.8 m/s from 2.2 m up, 11.5 m/s underarm from 1 "
                  "m) to clear a 2.43 m net 9 m away and still come down inside the far court: a fist at 6 to 7 m/s, "
                  "about the most a full swing of this arm gives, through a ball the robot has tossed itself off a "
                  "flat palm (straight up: a palm that moves sideways leaves the ball behind), at the right instant, "
                  "on a 67 kg robot whose stand has no balance feedback.")

    def configure(self, params):
        super().configure(params)
        self.fall_z = self.p["fall_z_m"]

    # ------------------------------------------------------------------ geometry
    def geometry(self):
        p = self.p
        return dict(centre=(p["end_line_m"] + p["court_half_length_m"], 0.0), yaw=0.0)

    def build(self, sc):
        p, g = self.p, self.geometry()
        build_court(sc, p, g["centre"], g["yaw"])
        sc.ball("ball", "volleyball", (0.5, 0.2, 1.3))           # no grip: the ball is not grippable
        palm_contact(sc, "ball", BALL["roll"])
        sc.camera("venue", (-6.0, -8.0, 5.5), (g["centre"][0] - 2.0, 0.0, 1.0), fovy=62)

    def reset(self, w):
        ball_on_palm(w)

    # ------------------------------------------------------------------ the referee
    def referee_reset(self, w, ref):
        g = self.geometry()
        self.ball = ref.geoms(body="ball")
        self.net = ref.geoms(body="net")
        self.antennas = ref.geoms(prefix="net_antenna")
        self.feet = ref.part("feet")
        self.trackers = {"released": None, "tosser": ["left_hand"], "last_on": 0.0, "free_t": None, "strike": None,
                         "flights": Flights(ref, min_air=0.0, also_allowed=self.ball),
                         "plane": Crossing((1, 0, 0), g["centre"][0], direction=1)}

    def _foot_fault(self, w, ref):
        """The points where the feet are (or, in the air, were at the take-off) on the floor: none on the court or
        beyond the extensions of the side lines."""
        p, fl = self.p, self.trackers["flights"]
        pts = ref.contact_points(self.feet, ref.ground)
        if not len(pts) and fl.air and fl.cur is not None:
            pts = np.asarray(fl.cur["takeoff"].get("points", [])).reshape(-1, 3)
        for q in pts:
            if q[0] >= p["end_line_m"] or abs(q[1]) > p["court_width_m"] / 2:
                return [round(float(q[0]), 3), round(float(q[1]), 3)]
        return None

    def substep(self, w, ref):
        p, g, tr = self.p, self.geometry(), self.trackers
        tr["flights"].update()
        if tr["released"] is None:                           # the ball on the hand(s): nothing but contact holds it
            if ref.touching(self.ball, ref.ground):
                return ref.fail("the ball touched the floor before the hit")
            if ref.touching(self.ball, ref.robot_mask):
                parts = ref.parts_touching(self.ball)
                if not parts <= HANDS:
                    return ref.fail("the ball was held with a part other than the hands", parts=sorted(parts))
                tr["tosser"] = sorted(set(tr["tosser"]) | parts)
                tr["last_on"] = ref.time
            elif ref.time - tr["last_on"] >= p["hold_gap_s"] - 1e-9:
                # clear of every hand for hold_gap_s: the ball has left the hand at the end of its last contact
                tr["released"] = tr["free_t"] = tr["last_on"]
                ref.stage("toss", at=round(tr["last_on"], 3), speed=round(float(np.linalg.norm(w.vel("ball"))), 2))
            return
        b, v = w.pos("ball"), w.vel("ball")
        on = ref.touching(self.ball, ref.robot_mask)
        st = tr["strike"]
        if st is None:                                       # released: the toss leaves the hand
            tossing = on and ref.parts_touching(self.ball) <= set(tr["tosser"])
            if ref.time - tr["released"] <= p["release_grace_s"] and (tossing or not on):
                # for release_grace_s the hand that held the ball may still touch it (it follows the toss up);
                # the ball is clear from the end of its last such touch. Any other touch is the hit.
                tr["free_t"] = None if on else (ref.time if tr["free_t"] is None else tr["free_t"])
                return
            if tr["free_t"] is None:
                if tossing:
                    return ref.fail("the ball was not tossed: it stayed on the hand",
                                    after_s=round(ref.time - tr["released"], 3))
                tr["free_t"] = ref.time
            st = tr["strike"] = Strike(ref, self.ball, p["clear_s"])
        if ref.touching(self.ball, self.antennas):
            return ref.fail("the ball touched an antenna")
        if st.phase == 2 and on:
            return ref.fail("second touch of the ball")
        ev = st.update(v)
        if ev == "start":
            parts = ref.parts_touching(self.ball)
            free = ref.time - tr["free_t"]
            v_in = float(np.linalg.norm(st.v_in))
            if not (parts <= ARM["left"] or parts <= ARM["right"]):
                return ref.fail("the ball was not hit with one hand or arm", parts=sorted(parts))
            if free < p["toss_free_s"]:
                return ref.fail("the ball was hit out of the hand", free_s=round(free, 3))
            if v_in > p["toss_max_speed_m_s"]:
                return ref.fail("the ball was thrown, not tossed", speed_before_hit_m_s=round(v_in, 2))
            fault = self._foot_fault(w, ref)
            if fault is not None:
                return ref.fail("foot fault", foot_at=fault)
        if st.phase == 1:
            if not (st.parts <= ARM["left"] or st.parts <= ARM["right"]):
                return ref.fail("the ball was not hit with one hand or arm", parts=sorted(st.parts))
            if st.duration > p["strike_max_s"]:
                return ref.fail("the ball was held", touch_s=round(st.duration, 3))
        if ev == "end":
            v_in, v_out = st.speeds()
            ref.metrics["speed_in_m_s"], ref.metrics["speed_out_m_s"] = round(v_in, 2), round(v_out, 2)
            if v_out <= v_in:
                return ref.fail("the hit did not add speed", speed_in=round(v_in, 2), speed_out=round(v_out, 2))
            ref.stage("hit", parts=sorted(st.parts), speed_in=round(v_in, 2), speed_out=round(v_out, 2),
                      free_s=round(st.t0 - tr["free_t"], 3))
        x = tr["plane"].update(b)
        if x is not None and not ref.has("over the net"):
            if not ref.has("hit"):
                return ref.fail("the ball crossed the net without a hit")
            if x[2] < p["net_height_m"] or abs(x[1] - g["centre"][1]) > p["court_width_m"] / 2:
                return ref.fail("the ball did not cross above the net between the antennas",
                                y=round(float(x[1]), 3), z=round(float(x[2]), 3))
            ref.stage("over the net", z=round(float(x[2]), 3))
        if ref.touching(self.ball, ref.ground):
            if st.phase < 2 or not ref.has("hit"):
                return ref.fail("the ball touched the floor before the hit")
            u, vv = to_court(g["centre"], g["yaw"], [b])[0]
            ref.metrics["landing_x_m"], ref.metrics["landing_y_m"] = round(float(b[0]), 3), round(float(b[1]), 3)
            if ref.has("over the net") and 0.0 <= u <= p["court_half_length_m"] and abs(vv) <= p["court_width_m"] / 2:
                if ref.stage("in the court"):
                    ref.succeed()
            else:
                ref.fail("the ball landed outside the opponent's court", x=round(float(b[0]), 3), y=round(float(b[1]), 3))

    def step(self, w, ref):
        p, tr = self.p, self.trackers
        if not ref.has("hit") and (tr["strike"] is None or tr["strike"].phase == 0) and w.t >= p["service_time_s"] - 1e-9:
            return ref.fail("the serve was not hit in time")
        ref.metrics["ball_height_m"] = round(float(w.pos("ball")[2]), 3)

    def privileged(self, w):
        p, g = self.p, self.geometry()
        return {"ball": w.pos("ball").tolist(), "ball_velocity": w.vel("ball").tolist(),
                "end_line_x": p["end_line_m"], "net": {"x": g["centre"][0], "top": p["net_height_m"]},
                "court": {"x": [g["centre"][0], g["centre"][0] + p["court_half_length_m"]],
                          "y": [-p["court_width_m"] / 2, p["court_width_m"] / 2]}}
