"""Keepie-uppie with the feet: drop a size-5 football from the hand and keep it up for ten foot touches in a row, every
touch a strike that sends the whole ball above the knee, nothing but the feet on the ball, inside a 5 m x 5 m grid."""
import math

import numpy as np

import mujoco

from rfo.referee import Touch
from rfo.scene import OFFICIAL
from rfo.task import TaskBase

BALL = OFFICIAL["football"]
GRASS = (0.16, 0.50, 0.20, 1)
ARMS = {"left_upper_arm", "left_forearm", "left_hand", "right_upper_arm", "right_forearm", "right_hand"}
FEET = ("left_foot", "right_foot")


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
        "The ball starts in the robot's right hand, held by the simulator's grip (the robot has fists, no fingers); "
        "the drop is the opening of the grip. No wind.",
    ]
    time_limit_s = 60.0
    start = (0.0, 0.0, 0.0)
    stages = [f"touch {i + 1}" for i in range(10)]
    fall_z = 0.35
    legal_ground = FEET
    params = dict(touches=10, rise_m=0.22, knee_z_m=0.36, carry_s=0.05, touch_gap_s=0.05, release_grace_s=0.15,
                  touch_gain=0.95, grid_m=5.0, fall_z_m=0.35, instep_z_m=0.12, heel_x_m=0.08, toe_x_m=0.15)

    sentence = ("Juggle the football with your feet: drop it from your hand and keep it in the air for ten foot "
                "touches in a row, each one sending the ball up above your knees, without it touching the ground or "
                "any other part of you.")
    rules = ("A size-5 football (0.22 m across, 0.43 kg, in air) starts gripped in your right hand; you stand in the "
             "middle of a square grid {grid_m} m on each side, marked on the grass. The drop is the moment no hand "
             "grips the ball any more; a hand or an arm may still be in contact with the ball for {release_grace_s} s "
             "after that (the ball leaving the hand), and the ball cannot be gripped again. From the drop on, only "
             "your feet may touch the ball: a foot is the part below the ankle joint (sole, instep, sides, toe and "
             "heel); a contact with your lower leg also counts as the foot where it lies over the foot (from "
             "{heel_x_m} m behind to {toe_x_m} m ahead of the ankle joint along the foot) and no more than "
             "{instep_z_m} m above the ankle joint (along the foot's up direction), because your leg's collision "
             "shape covers the instep; the leg above that (shin, knee, thigh), the trunk, the head and the arms are "
             "other surfaces. A touch is a contact of the ball with a foot (contacts less than {touch_gap_s} s apart are one touch). "
             "It counts when, before anything touches the ball again, the ball's centre has risen at least {rise_m} "
             "m above the height it had when the touch began and the whole ball (its lowest point) has risen above "
             "{knee_z_m} m, your knee height; and when the ball left the touch with at least {touch_gain} of the speed "
             "it had when the touch began (both taken at the height where the touch began): a ball that only bounces "
             "off a still foot leaves slower, and such a touch is not counted, and is not a fault. You succeed at the "
             "moment the tenth touch counts. You fail if the ball touches the ground, if a hand or an arm touches it "
             "later than {release_grace_s} s after the drop, or at all while a foot touches it or before a foot's touch "
             "has counted or been judged a bounce, if any part of you other than a foot touches it, if both "
             "feet touch it at once (the ball trapped), if one touch lasts longer than {carry_s} s (the ball resting, "
             "rolling or balanced on a foot), if the ball is touched again before a touch has counted or been "
             "judged a bounce, if a foot (its ankle) leaves the grid, if you fall (your pelvis lower than "
             "{fall_z_m} m above the ground, or any part of you other than the feet on the ground; standing on one "
             "foot is not a fall), or after {time_limit_s} s.")
    venue = ("You stand on level grass in the middle of a {grid_m} m x {grid_m} m grid marked by white lines, facing "
             "along one side, with the ball in your right fist, beyond its knuckles, the arm at rest. Opening the "
             "right grip (grip_right below 0.5) drops the ball where the hand is.")
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
        sc.ball("ball", "football", (0.3, -0.3, 1.0), grippable=True)
        sc.camera("venue", (2.4, -2.4, 1.3), (0.1, -0.1, 0.45), fovy=50)

    def reset(self, w):
        m, d = w.m, w.d
        mujoco.mj_kinematics(m, d)
        b = w.robot.mount["right"]
        R = d.xmat[b].reshape(3, 3)
        w.put("ball", d.xpos[b] + R @ np.array([0.0, 0.0, 0.105 + BALL["radius"]]))
        w.grab("right", "ball", event=False)

    def may_grip(self, w, side, name):
        return self.trackers.get("dropped") is None         # once dropped, the ball may not be gripped again

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
                         "count": 0, "bounces": 0, "pending": False, "z_touch": 0.0, "apex": 0.0, "speed": 0.0,
                         "v_in": 0.0, "v_out": None, "foot": None}

    def substep(self, w, ref):
        p, tr = self.p, self.trackers
        # the ball's speed one physics step ago (a touch's arrival speed), kept up to date on every step
        speed, tr["speed"] = tr["speed"], float(np.linalg.norm(w.vel("ball")))
        if tr["dropped"] is None:
            if not w.holder("ball"):
                tr["dropped"] = ref.time
                ref.event("drop")
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
