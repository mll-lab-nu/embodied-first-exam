"""Keepie-uppie: drop a size-5 football from the hand and keep it up for ten touches in a row with the feet, the legs
or the head."""
import math

import numpy as np

import mujoco

from rfo.referee import Touch
from rfo.scene import OFFICIAL
from rfo.task import TaskBase

BALL = OFFICIAL["football"]
GRASS = (0.16, 0.50, 0.20, 1)
ARMS = {"left_upper_arm", "left_forearm", "left_hand", "right_upper_arm", "right_forearm", "right_hand"}
LEGAL = ("feet", "shins", "thighs", "head")


class Task(TaskBase):
    name = "juggling"
    title = "Football: keepie-uppie"
    category = "football-and-volleyball"
    robot = "unitree_g1"
    rulebook = ("Keepie-uppie (ball juggling), the football skill: the ball is dropped from the hands and kept in the "
                "air with the feet, the legs and the head, each touch counted, the count ending when the ball touches "
                "the ground or a hand; it is a skill test, not an event of the Laws, and the family's standard is 10 "
                "consecutive touches. IFAB Laws of the Game 2025/26 for the ball (Law 2: size 5, 68-70 cm round, "
                "410-450 g) and for handling (Law 12: the hand or the arm)")
    deviations = [
        "A counter's eye is replaced by numbers: contacts less than {touch_gap_s} s apart are one touch, a touch may "
        "last at most {carry_s} s, and it counts when the ball's centre has then risen at least {rise_m} m (one ball "
        "diameter) above where it was when the touch began, before anything touches it again; a ball that rolls or "
        "rests on a leg is not a touch.",
        "A touch is a strike: so that a ball that merely bounces on a still limb or head is not juggling, every "
        "touch after the first must send the ball off with at least {touch_gain} of the speed it arrived with (a "
        "still limb returns about 0.85); a touch that does not is not counted, and is not a fault.",
        "Only the feet, the legs (shin and thigh) and the head count and may touch the ball; the chest and the "
        "shoulders, which a human juggler may use, are not allowed, because the robot's trunk is one rigid shell.",
        "The ball starts in the robot's right hand, held by the simulator's grip (the robot has fists, no fingers); "
        "the drop is the opening of the grip. No wind.",
    ]
    time_limit_s = 30.0
    start = (0.0, 0.0, 0.0)
    stages = [f"touch {i + 1}" for i in range(10)]
    fall_z = 0.35
    legal_ground = ("left_foot", "right_foot")
    params = dict(touches=10, rise_m=0.22, carry_s=0.15, touch_gap_s=0.05, release_grace_s=0.15, touch_gain=0.95, fall_z_m=0.35)

    sentence = ("Juggle the football: drop it from your hand and keep it in the air for ten touches in a row with your "
                "feet, legs or head, without it touching the ground or a hand again.")
    rules = ("A size-5 football (0.22 m across, 0.43 kg, in air) starts gripped in your right hand. The drop is the "
             "moment no hand grips it any more; a hand or an arm may still be in contact with the ball for "
             "{release_grace_s} s after that (the ball leaving the hand), and the ball cannot be gripped again. From "
             "the drop on, a touch is a contact of the ball with a foot, a shin, a thigh or your head (contacts less "
             "than {touch_gap_s} s apart are one touch); it counts when the ball's centre has then risen at least "
             "{rise_m} m above the height it had when the touch began, before anything touches it again, and, "
             "for every touch after the first, when the ball leaves the touch with at least {touch_gain} of the "
             "speed it had when the touch began (both taken at the height where the touch began; a ball that only bounces on a still limb leaves slower: such a "
             "touch is not counted, and is not a fault). You succeed at the moment the tenth touch counts. You fail if the ball touches the ground, if a hand or "
             "an arm touches it later than {release_grace_s} s after the drop, if your trunk (chest, shoulders, "
             "pelvis) touches it, if one touch lasts longer than {carry_s} s (the ball resting or balanced on you), "
             "if the ball is touched again before it has risen {rise_m} m, if you fall (your pelvis lower than "
             "{fall_z_m} m above the ground, or any part of you other than the feet on the ground; standing on one "
             "foot is not a fall), or after {time_limit_s} s.")
    venue = ("You stand on level grass with the ball in your right fist, beyond its knuckles, the arm at rest. Opening "
             "the right grip (grip_right below 0.5) drops the ball where the hand is.")
    difficulty = ("Each touch is an upward strike by a leg or the head, timed to a falling 0.43 kg ball and aimed so "
                  "that the ball comes down within reach again, ten times in a row; the robot has to stand on one leg "
                  "to use a foot or a thigh, which neither built-in gait does, and a ball that merely bounces on a "
                  "still limb loses a quarter of its height each time and wanders off.")

    def __init__(self):
        super().__init__()
        self.stages = [f"touch {i + 1}" for i in range(int(self.p["touches"]))]

    def configure(self, params):
        super().configure(params)
        self.stages = [f"touch {i + 1}" for i in range(int(self.p["touches"]))]
        self.fall_z = self.p["fall_z_m"]

    def build(self, sc):
        sc.box("pitch", (0.0, 0, 0.0003), (6.0, 6.0, 0.0003), rgba=GRASS)
        sc.ball("ball", "football", (0.3, -0.3, 1.0), grippable=True)
        sc.camera("venue", (2.6, -2.6, 1.5), (0.0, -0.1, 0.8), fovy=50)

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
        self.legal = ref.part(*LEGAL)
        self.arms = ref.part("arms")
        self.trunk = ref.robot_mask & ~self.legal & ~self.arms
        self.trackers = {"touch": Touch(ref, self.ball, self.legal, gap=self.p["touch_gap_s"]), "dropped": None,
                         "count": 0, "pending": False, "z_touch": 0.0, "apex": 0.0, "speed": 0.0, "v_in": 0.0, "v_out": None,
                         "first": True}

    def substep(self, w, ref):
        p, tr = self.p, self.trackers
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
        if ref.touching(self.ball, self.trunk):
            return ref.fail("the ball was touched by the trunk", parts=sorted(ref.parts_touching(self.ball)),
                            touches=tr["count"])
        touch = tr["touch"]
        z = float(w.pos("ball")[2])
        speed, tr["speed"] = tr["speed"], float(np.linalg.norm(w.vel("ball")))     # speed: one physics step ago
        if touch.update():                                 # a new touch
            if tr["pending"]:
                return ref.fail("the ball was touched again before it had risen enough",
                                rise_m=round(tr["apex"] - tr["z_touch"], 3), touches=tr["count"])
            tr["pending"], tr["z_touch"], tr["apex"], tr["v_in"], tr["v_out"] = True, z, z, speed, None
        if touch.active and touch.duration > p["carry_s"]:
            return ref.fail("the ball was carried", touch_s=round(touch.duration, 3), touches=tr["count"])
        if tr["pending"]:
            tr["apex"] = max(tr["apex"], z)
            if not ref.touching(self.ball, self.legal) and z - tr["z_touch"] >= p["rise_m"]:
                tr["pending"] = False
                # the speed the ball left the touch with, at the touch's height (from its energy now: free flight)
                tr["v_out"] = math.sqrt(max(0.0, tr["speed"] ** 2 + 2 * 9.81 * (z - tr["z_touch"])))
                struck = tr["first"] or tr["v_out"] >= p["touch_gain"] * tr["v_in"]
                tr["first"] = False
                if not struck:                             # a passive bounce: no touch of the count
                    ref.event("bounce", speed_in=round(tr["v_in"], 2), speed_out=round(tr["v_out"], 2))
                    return
                tr["count"] += 1
                if ref.stage(f"touch {tr['count']}", touch_s=round(touch.duration, 3)) and tr["count"] >= p["touches"]:
                    ref.succeed()

    def step(self, w, ref):
        tr = self.trackers
        ref.metrics["touches"] = tr["count"]
        ref.metrics["ball_height_m"] = round(float(w.pos("ball")[2]), 3)

    def privileged(self, w):
        return {"ball": w.pos("ball").tolist(), "ball_velocity": w.vel("ball").tolist(),
                "dropped": self.trackers.get("dropped") is not None, "touches": int(self.trackers.get("count", 0))}
