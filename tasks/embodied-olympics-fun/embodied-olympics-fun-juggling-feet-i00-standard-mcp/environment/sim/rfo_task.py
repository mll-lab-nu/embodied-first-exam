"""Keepie-uppie with the feet (Ontario Soccer OPDL Technical Benchmark Exercises, instep juggling): the size-5 football
starts pressed between the two open palms (nothing grips: only the arms' squeeze and friction hold it, it can slip
out), and the drop is the hands' own movement. Then ten foot touches in a row, every touch a strike that sends the
whole ball above the knee, nothing but the feet on the ball, inside a 5 m x 5 m grid."""
import math
import xml.etree.ElementTree as ET

import numpy as np

import mujoco

from rfo.referee import Touch
from rfo.scene import OFFICIAL
from rfo.task import TaskBase

BALL = OFFICIAL["football"]
GRASS = (0.16, 0.50, 0.20, 1)
ARMS = {"left_upper_arm", "left_forearm", "left_hand", "right_upper_arm", "right_forearm", "right_hand"}
FEET = ("left_foot", "right_foot")
HANDS = {"left_hand", "right_hand"}


# ---- the ball between the palms ----
# The G1's hands are flat palm pads (4.4 x 8 x 10 cm boxes on the wrist mounts, the broad face on the mount's +x the
# palm) inside the rubber fists; a fist's collision shell (rfo/world.py) stands up to 21 mm proud of the pad's face on
# the palm side, so the ball is held between the fists (the pad and the fist both have the palm's contact, below). The start: both forearms forward at the height of the hips, turned
# so that the palms face each other across the body (the wrist rolls), the upper arms turned in until both palms touch
# the ball in front of the pelvis (HOLD: the joint angles where each palm's face touches the ball); the start command
# is SQUEEZE, the same pose with the palms' faces SQUEEZE_M further in, so that the shoulder servos press the ball
# between them: nothing else holds it. The arms have no gravity feed-forward: under that command the arms settle
# against the ball in about 2 s (measured offline: 2.5 s with the ball held at its start, then let go); the robot
# starts there, at rest (SETTLED: the pelvis' height and orientation, every joint), the ball where it then sits
# (BALL_AT: its centre in the right mount's frame). The drop is the hands' own movement: the palms parting (or the
# arms lowering, turning) until the ball falls free. Measured: the squeeze
# presses about 6.6 N on each palm and holds the ball still for a whole episode (it creeps 3 to 4 mm in 60 s); with
# the command at HOLD (the palms only touching) the ball slips out at once.
# With the fists (each hand 21 mm further out along its palm normal, the same squeeze) the ball creeps 6 mm in 20 s.
HOLD = dict(right_shoulder_pitch=-0.0299, right_shoulder_roll=-0.0282, right_shoulder_yaw=0.005, right_elbow=0.2272,
            right_wrist_roll=1.6012, right_wrist_pitch=-0.0067, right_wrist_yaw=0.1985, left_shoulder_pitch=-0.0299,
            left_shoulder_roll=0.0282, left_shoulder_yaw=-0.005, left_elbow=0.2272, left_wrist_roll=-1.6012,
            left_wrist_pitch=-0.0067, left_wrist_yaw=-0.1985)
SQUEEZE = dict(right_shoulder_pitch=-0.0309, right_shoulder_roll=0.0351, right_shoulder_yaw=0.0438,
               right_elbow=0.2273, right_wrist_roll=1.5483, right_wrist_pitch=-0.0591, right_wrist_yaw=0.1964,
               left_shoulder_pitch=-0.0309, left_shoulder_roll=-0.0352, left_shoulder_yaw=-0.0438, left_elbow=0.2274,
               left_wrist_roll=-1.5483, left_wrist_pitch=-0.0591, left_wrist_yaw=-0.1964)
SQUEEZE_M = 0.02
SETTLED_Z_QUAT = (0.78584, 1, -9e-05, 0.00101, -0.00074)
SETTLED = (-0.10061, 0.01288, -0.00709, 0.29941, -0.20286, 0.05367, -0.10138, -0.01304, 0.00684, 0.29926, -0.20196,
           -0.05394, -0.00084, -0.00032, 0.03417, -0.0173, -0.02307, -0.02589, 0.23539, -1.55514, -0.10642, -0.1876,
           -0.01752, 0.02314, 0.02601, 0.23496, 1.55545, -0.10573, 0.18842)
BALL_AT = (0.15062, 0.02906, 0.04234)
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
        for g in (f"{side}_palm_pad", f"{side}_wrist_yaw_link_shell0"):     # the pad and the rubber fist's shell
            ET.SubElement(sc.root.find("contact"), "pair", name=f"palm_ball_{g}", geom1=ball, geom2=g, condim="6",
                          friction=f"{PALM_MU} {PALM_MU} 0.003 {roll} {roll}", solref=PALM_SOLREF,
                          solimp=PALM_SOLIMP)


def ball_between_palms(w) -> None:
    """t = 0: the robot settled under its start command (both arms' is SQUEEZE, the other joints' their rest), the
    ball between the palms."""
    r, d = w.robot, w.d
    for jn, v in SQUEEZE.items():
        i = _joint(w, jn)
        r.arb.q_a[i] = r.arb.q_b[i] = v
    d.qpos[r.fq + 2:r.fq + 7] = SETTLED_Z_QUAT
    d.qpos[r.qadr] = SETTLED
    mujoco.mj_kinematics(w.m, d)
    b = r.mount["right"]
    w.put("ball", d.xpos[b] + d.xmat[b].reshape(3, 3) @ np.array(BALL_AT))
# ---- end of the palms ----


class Task(TaskBase):
    name = "juggling-feet"
    title = "Football: keepie-uppie with the feet"
    category = "football-and-volleyball"
    robot = "unitree_g1"
    rulebook = ("Ontario Soccer, OPDL Player Technical Benchmark Exercises (2015): Ball Mastery, juggled on the "
                "instep (the exercise list's 'one attempt on each instep', the warm-up's 'instep right juggling' and "
                "'instep left juggling'): the ball starts in the hands, the player works in a 5 m x 5 m grid and has "
                "60 seconds, the maximum number of consecutive juggles is recorded, and the ground, another surface "
                "or stepping out of the grid stops the count; the test sets no pass mark, so the family's standard "
                "is 10 consecutive foot juggles (the first milestone of youth juggling ladders and the standard of "
                "the existing juggling family). IFAB Laws of the Game 2025/26 for the ball (Law 2: size 5, 68-70 cm "
                "round, 410-450 g) and for handling (Law 12: the hand or the arm)")
    deviations = [
        "The test's either-instep attempts are one attempt here in which either foot may play, in any order.",
        "The foot is the robot's ankle-roll link, the shoe-like part below the ankle joint: its sole, its top (the "
        "instep and laces), its sides, toe and heel; the robot has no separate toes and no laces, so the whole "
        "part counts. The G1's collision hull of the lower leg is wider and deeper than its shin and covers the "
        "instep: a ball lying on the top of the foot touches it. A contact with the lower leg's hull therefore "
        "counts as the foot where its point lies over the foot (between {heel_x_m} m behind and {toe_x_m} m ahead "
        "of the ankle joint along the foot) and at most {instep_z_m} m above the ankle joint (measured along the "
        "foot's up direction: where the ball's equator is when it lies on the instep, plus 1 cm); a contact "
        "higher up the leg is the shin, the knee or the thigh: another surface, which the test's count does not "
        "allow.",
        "A counter's eye is replaced by numbers: contacts less than {touch_gap_s} s apart are one touch, a touch may "
        "last at most {carry_s} s (a juggle is a strike, the ball may not rest, be cushioned or be balanced on the "
        "foot; a real instep kick's contact lasts about 0.01 s, Nunome et al. 2006, J. Sports Sci. 24: 11-22, and "
        "the robot's strikes last 0.011-0.013 s), and a "
        "touch counts when the ball's centre has then risen at least {rise_m} m (one ball diameter) above where it "
        "was when the touch began and the whole ball has risen above the robot's knee height ({knee_z_m} m above "
        "the ground standing), before anything touches it again.",
        "A juggle is a strike: so that a ball that merely bounces off a still foot is not juggling, a touch must send "
        "the ball off with at least {touch_gain} of the speed it arrived with (a still foot returns at most the "
        "ball's own restitution, 0.85, and a raised leg held by its motors about 0.55); a touch that does not is "
        "not counted, and is not a fault.",
        "The ball's contact with the foot keeps the ball's own restitution (0.85, from the rule book's drop test): "
        "the robot's foot is rigid, like the metal pendulum with which Andersen, Kristensen and Sorensen (Football "
        "Science 5: 45-50, 2008) measured 0.82, and the compliance of a human foot and ankle (whose kicks they and "
        "earlier studies measured at 0.45-0.65) is here the compliance of the robot's own joints: a raised leg "
        "held by its motors returns about 0.55 of the ball's speed.",
        "The ball starts pressed between the robot's two open palms in front of its hips (the robot has flat palm "
        "pads, no fingers and no grip): only the arms' squeeze and friction hold it, and it slips out when they "
        "press too little. The drop is the hands' own movement (the palms parting); a referee's eye for 'the "
        "ball has left the hand' is replaced by a number: the ball touches no part of the robot for {hold_gap_s} s, "
        "and the drop is the end of its last contact. Before the drop only the hands may touch the ball (a ball held "
        "against the body, an arm or a leg is not in the hand). The palm pads' contact with the ball is that of "
        "a ball on a human hand (a ball thrown at a still palm keeps " + f"{PALM_REBOUND:.2f}" + " of its speed, as a volleyball dropped onto a supported, relaxed hand does: Ivanova, ISBS 2000); every other contact keeps the ball's rule-book rebound. No wind.",
    ]
    time_limit_s = 60.0
    start = (0.0, 0.0, 0.0)
    stages = [f"touch {i + 1}" for i in range(10)]
    fall_z = 0.35
    legal_ground = FEET
    params = dict(touches=10, rise_m=0.22, knee_z_m=0.36, carry_s=0.05, touch_gap_s=0.05, hold_gap_s=0.03,
                  release_grace_s=0.15, touch_gain=0.95, grid_m=5.0, fall_z_m=0.35, instep_z_m=0.12, heel_x_m=0.08,
                  toe_x_m=0.15)

    sentence = ("Juggle the football with your feet: drop it from between your palms and keep it in the air for ten "
                "foot touches in a row, each one sending the ball up above your knees, without it touching the "
                "ground or any other part of you.")
    rules = ("A size-5 football (0.22 m across, 0.43 kg, in air) starts pressed between your two open palms; you "
             "stand in the middle of a square grid {grid_m} m on each side, marked on the grass. Your hands have no "
             "fingers and no grip (the grip columns of the action rows do nothing in this task): only the squeeze of "
             "your arms and friction hold the ball, and it slips out when they press too little. Until the drop only "
             "your hands (the palm pads and the wrists) may touch the ball. The drop: the ball has touched no part "
             "of you for {hold_gap_s} s; it is the end of the ball's last contact with a hand. A hand or an arm may "
             "still be in contact with the ball for {release_grace_s} s after the drop (the ball leaving the hand); "
             "after that a hand or an arm on the ball is a handball. From the drop on, only your feet may touch the "
             "ball: a foot is the part below the ankle joint (sole, instep, sides, toe and heel); a contact with "
             "your lower leg also counts as the foot where it lies over the foot (from {heel_x_m} m behind to "
             "{toe_x_m} m ahead of the ankle joint along the foot) and no more than {instep_z_m} m above the ankle "
             "joint (along the foot's up direction), because your leg's collision shape covers the instep; the leg "
             "above that (shin, knee, thigh), the trunk, the head and the arms are other surfaces. A touch is a "
             "contact of the ball with a foot (contacts less than {touch_gap_s} s apart are one touch). It counts "
             "when, before anything touches the ball again, the ball's centre has risen at least {rise_m} m above "
             "the height it had when the touch began and the whole ball (its lowest point) has risen above "
             "{knee_z_m} m, your knee height; and when the ball left the touch with at least {touch_gain} of the "
             "speed it had when the touch began (both taken at the height where the touch began): a ball that only "
             "bounces off a still foot leaves slower, and such a touch is not counted, and is not a fault. You "
             "succeed at the moment the tenth touch counts. You fail if the ball touches the ground (before the drop "
             "too), if a part of you other than the hands touches it before the drop, if a hand or an arm touches it "
             "later than {release_grace_s} s after the drop, or at all while a foot touches it or before a foot's "
             "touch has counted or been judged a bounce, if any part of you other than a foot touches it, if both "
             "feet touch it at once (the ball trapped), if one touch lasts longer than {carry_s} s (the ball "
             "resting, rolling or balanced on a foot), if the ball is touched again before a touch has counted or "
             "been judged a bounce, if a foot (its ankle) leaves the grid, if you fall (your pelvis lower than "
             "{fall_z_m} m above the ground, or any part of you other than the feet on the ground; standing on one "
             "foot is not a fall), or after {time_limit_s} s.")
    venue = ("You stand on level grass in the middle of a {grid_m} m x {grid_m} m grid marked by white lines, facing "
             "along one side. Your upper arms hang, your forearms point forward and are turned so that the palms "
             "face each other; the ball is pressed between them, its centre about 0.85 m above the ground and 0.33 m "
             "ahead of your pelvis. The start command keeps that squeeze (the joint table's start angles are where "
             "the arms stand with the ball between the palms; the command is a little further in: the difference is "
             "the squeeze).")
    difficulty = ("Each touch is an upward strike of a foot, timed to a falling 0.43 kg ball and aimed so that the "
                  "ball comes down on a foot again, ten times in a row, and the robot's thick lower leg leaves only "
                  "the front few centimetres of the foot where a falling ball meets the foot and not the shin, a "
                  "spot where a few millimetres decide whether the ball goes up, forward or back onto the leg. To "
                  "bring a foot under the ball the robot has to stand on the other leg, which neither built-in gait "
                  "does, and a ball that merely bounces off a still foot loses most of its height and wanders off.")

    def __init__(self):
        super().__init__()
        self.stages = [f"touch {i + 1}" for i in range(int(self.p["touches"]))]

    def configure(self, params):
        super().configure(params)
        self.stages = [f"touch {i + 1}" for i in range(int(self.p["touches"]))]
        self.fall_z = self.p["fall_z_m"]

    def build(self, sc):
        h = self.p["grid_m"] / 2
        sc.box("pitch", (0.0, 0, 0.0003), (6.0, 6.0, 0.0003), rgba=GRASS)
        for i, (p0, p1) in enumerate((((-h, -h), (h, -h)), ((h, -h), (h, h)), ((h, h), (-h, h)), ((-h, h), (-h, -h)))):
            sc.line(f"grid_{i}", p0, p1, width=0.06)
        sc.ball("ball", "football", (0.3, -0.3, 1.0))           # no grip: the ball is not grippable
        palm_contact(sc, "ball", BALL["roll"])
        sc.camera("venue", (2.4, -2.4, 1.3), (0.1, -0.1, 0.45), fovy=50)

    def reset(self, w):
        ball_between_palms(w)

    def referee_reset(self, w, ref):
        self.ball = ref.geoms(body="ball")
        self.feet = ref.part("feet")
        self.shin = {s: ref.part(f"{s}_shin") for s in ("left", "right")}
        self.side_mask = {s: ref.part(f"{s}_foot", f"{s}_shin") for s in ("left", "right")}
        self.foot_body = {s: w.m.body(f"{s}_ankle_roll_link").id for s in ("left", "right")}
        self.arms = ref.part("arms")
        legal = self.feet | ref.part("shins")             # the shins: only over the foot (instep), see substep
        self.other = ref.robot_mask & ~legal & ~self.arms
        self.radius = float(w.m.geom("ball").size[0])
        self.legal = legal
        self.trackers = {"touch": Touch(ref, self.ball, legal, gap=self.p["touch_gap_s"]), "dropped": None,
                         "last_on": 0.0,
                         "count": 0, "bounces": 0, "pending": False, "z_touch": 0.0, "apex": 0.0, "speed": 0.0,
                         "v_in": 0.0, "v_out": None, "foot": None}

    def substep(self, w, ref):
        p, tr = self.p, self.trackers
        # the ball's speed one physics step ago (a touch's arrival speed), kept up to date on every step
        speed, tr["speed"] = tr["speed"], float(np.linalg.norm(w.vel("ball")))
        if tr["dropped"] is None:                            # the ball on the hand(s): nothing but contact holds it
            if ref.touching(self.ball, ref.ground):
                return ref.fail("the ball touched the ground", touches=0)
            if ref.touching(self.ball, ref.robot_mask):
                parts = ref.parts_touching(self.ball)
                if not parts <= HANDS:
                    return ref.fail("the ball was held with a part other than the hands", parts=sorted(parts))
                tr["last_on"] = ref.time
            elif ref.time - tr["last_on"] >= p["hold_gap_s"] - 1e-9:
                # clear of every hand for hold_gap_s: the ball has left the hand at the end of its last contact
                tr["dropped"] = tr["last_on"]
                ref.event("drop", at=round(tr["last_on"], 3), speed=round(float(np.linalg.norm(w.vel("ball"))), 2))
            return
        since = ref.time - tr["dropped"]
        if ref.touching(self.ball, ref.ground):
            return ref.fail("the ball touched the ground", touches=tr["count"])
        if ref.touching(self.ball, self.arms) and since > p["release_grace_s"]:
            return ref.fail("handball", parts=sorted(ref.parts_touching(self.ball) & ARMS), touches=tr["count"])
        if ref.touching(self.ball, self.other):
            return ref.fail("the ball touched a part other than a foot",
                            parts=sorted(ref.parts_touching(self.ball) - ARMS - set(FEET)), touches=tr["count"])
        on = []
        for s in ("left", "right"):
            pts = ref.contact_points(self.ball, self.shin[s])
            if len(pts):                                  # the lower leg's hull: the instep, or the shin above it
                b = self.foot_body[s]
                loc = (pts - w.d.xpos[b]) @ w.d.xmat[b].reshape(3, 3)       # in the foot's frame
                bad = (loc[:, 2] > p["instep_z_m"]) | (loc[:, 0] < -p["heel_x_m"]) | (loc[:, 0] > p["toe_x_m"])
                if np.any(bad):
                    i = int(np.flatnonzero(bad)[0])
                    return ref.fail("the ball touched a part other than a foot", parts=[f"{s}_shin"],
                                    at_foot_frame=[round(float(x), 3) for x in loc[i]], touches=tr["count"])
            if ref.touching(self.ball, self.side_mask[s]):
                on.append(f"{s}_foot")
        if len(on) == 2:
            return ref.fail("the ball was trapped between the feet", touches=tr["count"])
        touch = tr["touch"]
        z = float(w.pos("ball")[2])
        if touch.update():                                 # a new touch
            if tr["pending"]:
                return ref.fail("the ball was touched again before it had risen enough",
                                rise_m=round(tr["apex"] - tr["z_touch"], 3), touches=tr["count"])
            tr["pending"], tr["z_touch"], tr["apex"], tr["v_in"], tr["v_out"] = True, z, z, speed, None
            tr["foot"] = sorted(on)[0] if on else None
        if ref.touching(self.ball, self.arms) and (touch.active or tr["pending"]):    # (within the release grace)
            return ref.fail("handball", parts=sorted(ref.parts_touching(self.ball) & ARMS), during_touch=True,
                            touches=tr["count"])
        if touch.active and touch.duration > p["carry_s"]:
            return ref.fail("the ball was carried", touch_s=round(touch.duration, 3), touches=tr["count"])
        if tr["pending"]:
            tr["apex"] = max(tr["apex"], z)
            high = z - tr["z_touch"] >= p["rise_m"] and z - self.radius >= p["knee_z_m"]
            if not ref.touching(self.ball, self.legal) and high:
                tr["pending"] = False
                # the speed the ball left the touch with, at the touch's height (from its energy now: free flight)
                tr["v_out"] = math.sqrt(max(0.0, tr["speed"] ** 2 + 2 * 9.81 * (z - tr["z_touch"])))
                if tr["v_out"] < p["touch_gain"] * tr["v_in"]:      # a passive bounce: no touch of the count
                    tr["bounces"] += 1
                    ref.event("bounce", speed_in=round(tr["v_in"], 2), speed_out=round(tr["v_out"], 2))
                    return
                tr["count"] += 1
                if ref.stage(f"touch {tr['count']}", foot=tr["foot"], touch_s=round(touch.duration, 3),
                             speed_in=round(tr["v_in"], 2), speed_out=round(tr["v_out"], 2)) \
                        and tr["count"] >= p["touches"]:
                    ref.succeed()

    def step(self, w, ref):
        tr = self.trackers
        h = self.p["grid_m"] / 2
        for s in ("left", "right"):
            x, y = w.d.site_xpos[w.robot.foot_site[s]][:2]
            if abs(float(x)) > h or abs(float(y)) > h:
                return ref.fail("stepped out of the grid", foot=s, at=[round(float(x), 3), round(float(y), 3)])
        ref.metrics["touches"] = tr["count"]
        ref.metrics["bounces"] = tr["bounces"]
        ref.metrics["ball_height_m"] = round(float(w.pos("ball")[2]), 3)

    def privileged(self, w):
        tr = self.trackers
        return {"ball": w.pos("ball").tolist(), "ball_velocity": w.vel("ball").tolist(),
                "feet": {s: w.d.site_xpos[w.robot.foot_site[s]].tolist() for s in ("left", "right")},
                "dropped": tr.get("dropped") is not None, "touches": int(tr.get("count", 0)),
                "touch_pending": bool(tr.get("pending", False))}
