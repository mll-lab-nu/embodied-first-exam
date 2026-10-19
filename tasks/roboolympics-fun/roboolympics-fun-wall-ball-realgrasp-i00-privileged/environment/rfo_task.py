"""Wall ball with a real hold: from behind the line, throw the tennis ball at the target circle on the wall 5 m away
and catch the rebound before it touches the ground, and keep it. No grip: both hands are Unitree Dex1-1 two-jaw
grippers that hold the ball by friction only (the throw is the right gripper opening; the catch is a gripper's two
jaws closing on the ball in the air). Official ball with its real flight and bounce; the Unitree H1-2."""
import math

import mujoco
import numpy as np

from rfo import realhand
from rfo.referee import Touch
from rfo.scene import OFFICIAL, VISUAL
from rfo.task import TaskBase

BALL = OFFICIAL["tennis"]                      # ITF: 6.54-6.86 cm, 56.0-59.4 g, rebound 0.745; drag and Magnus lift
LEGAL = {"left_hand", "right_hand", "left_forearm", "right_forearm"}


class Task(TaskBase):
    name = "wall-ball-realgrasp"
    title = "Wall ball: throw, rebound, catch, real hold"
    category = "throwing-catching-striking"
    robot = "unitree_h1"
    rulebook = ("No rule book: a wall-ball drill (throw and catch against a wall, as used in baseball, cricket and "
                "handball training) with this benchmark's numbers. The ball is the ITF's (Rules of Tennis 2024, Rule "
                "3 and Appendix I: size, mass, rebound)")
    deviations = [
        "The hands: the H1-2's hands are Unitree's Dex1-1 two-jaw grippers (sold for the G1, the H2 and the R1, not "
        "for the H1-2; mounted on the wrist where the H1-2's palm ends): 90 mm stroke, 80 mm jaws with rubber pads, at "
        "most 120 N of grip, each jaw closing at most 187.5 mm/s; they hold the ball by friction only, and it can "
        "slip, turn and drop. One closure command per hand (the real one also takes a speed and a force setting), no "
        "5 N minimum force; two pads at friction 1.0 and 120 N hold about 240 N of shear, some five times the "
        "device's rated 5 kg friction-grasp load.",
        "The throw and the catch: the ball is released when it has touched no part of you for {release_s} s (at its "
        "last touch); it is held while both jaws of one gripper touch it with its centre between the jaws' pads, and "
        "a catch is the ball held after the rebound. A held ball may lose a jaw's touch for at most {held_gap_s} s.",
        "The wall is rigid and smooth; the ball's rebound from it is the ITF ball's rebound from a hard floor "
        "(" + f"{BALL['bounce']:.3f}" + " of the speed across the wall).",
        "Flight: quasi-steady aerodynamics (MuJoCo's ellipsoid fluid model: drag and Magnus lift), still air. The "
        "world has elliptic friction cones and an impedance ratio of 100 (the grippers' setting, which makes a "
        "clamped ball stay put); they apply to every contact.",
    ]
    time_limit_s = 15.0
    start = (-0.40, 0.0, 0.0)
    stages = ["release", "target", "catch", "hold"]
    fall_z = 0.50
    params = dict(wall_distance_m=5.0, target_height_m=1.5, target_diameter_m=0.5, target_y_m=0.0, release_s=0.05,
                  retouch_grace_s=0.15, held_gap_s=0.05, hold_s=1.0, fall_pelvis_m=0.50)

    sentence = ("Throw the tennis ball held in your right gripper at the target circle on the wall and catch the "
                "rebound in a gripper before it touches the ground, and keep hold of it.")
    rules = ("The tennis ball (" + f"{2 * BALL['radius']:.3f} m across, {BALL['mass']:.4f} kg, it keeps "
             f"{BALL['bounce']:.3f} of its speed in a bounce" + ", it flies in air with drag) starts held between "
             "the jaws of your right gripper. Both your hands are two-jaw grippers that hold things only by the "
             "friction of their jaws; nothing else holds the ball, and it can slip or drop. A gripper holds the ball "
             "while both of its jaws touch it and its centre is between the two jaws' pads (not resting on top of "
             "them). A wall stands {wall_distance_m} m beyond the line you stay behind; the "
             "target is a circle {target_diameter_m} m across painted on it, its centre {target_height_m} m above "
             "the ground and {target_y_m} m to the left of the point straight ahead of you. The throw: the ball is "
             "released when it has touched no part of you for {release_s} s (it is released at its last touch; "
             "once). The first thing it touches after that must be the wall, at a point inside the target circle. "
             "Then catch the rebound: a gripper holding the ball (both jaws on it) before it has touched the ground; "
             "either gripper may catch, and before the catch the rebound may touch only your hands (the grippers) "
             "and forearms. You succeed when the ball has been held for {hold_s} s from the catch, never losing a "
             "jaw's touch for more than {held_gap_s} s. You fail if any part of you touches the ground on or beyond "
             "the line at any time; if the ball touches the ground at any time before the end; if it hits the wall "
             "outside the circle; if any part of you touches it after the release and before the wall (your right "
             "arm may still brush it during the first {retouch_grace_s} s, but not hold it); if the rebound touches "
             "any part of you other than a hand or a forearm before the catch; if the ball goes unheld for more than "
             "{held_gap_s} s after the catch; if you fall (your pelvis lower than {fall_pelvis_m} m above the "
             "ground, or any part of you other than your feet on the ground); or after {time_limit_s} s.")
    venue = ("You face the wall (+x), your pelvis 0.40 m behind the line; the wall is {wall_distance_m} m beyond the "
             "line, 6 m wide and 4 m high. The target circle is straight ahead. The ball is held between the closed "
             "jaws of your right gripper (closure command 1), the forearm level and pointing forwards; your left "
             "gripper is open (closure command 0). Still air. The grip columns of the action rows are the grippers' "
             "closure commands (0 open, 1 closed).")
    difficulty = ("To come back five metres through the air the ball has to hit the wall at about 16 m/s or more, "
                  "inside a circle half a metre across, and it then returns in under half a second at about 10 m/s. "
                  "The ball, 67 mm across, has to arrive between two jaws that open at most 90 mm and are 80 mm long, "
                  "and the jaws have to close on it in the few milliseconds it spends between them.")

    def build(self, sc):
        p = self.p
        self.fall_z = p["fall_pelvis_m"]
        sc.real_hands["left"] = sc.real_hands["right"] = "dex1"
        X, r = p["wall_distance_m"], p["target_diameter_m"] / 2
        sc.box("court", (X / 2 - 1.0, 0, 0.0003), (X / 2 + 1.0, 3.0, 0.0003), rgba=(0.30, 0.42, 0.60, 1))
        sc.line("line", (0.0, -3.0), (0.0, 3.0))
        sc.box("wall", (X + 0.10, 0.0, 2.0), (0.10, 3.0, 2.0), rgba=(0.82, 0.80, 0.74, 1), solid="hit")
        q = (math.sqrt(0.5), 0, math.sqrt(0.5), 0)
        sc.geom(sc.wb, "target", type="cylinder", pos=(X - 0.001, p["target_y_m"], p["target_height_m"]), quat=q,
                size=(r, 0.001), rgba=(0.9, 0.2, 0.15, 1), **VISUAL)
        sc.geom(sc.wb, "target_centre", type="cylinder", pos=(X - 0.002, p["target_y_m"], p["target_height_m"]), quat=q,
                size=(r * 0.35, 0.001), rgba=(0.97, 0.97, 0.95, 1), **VISUAL)
        sc.ball("ball", "tennis", (0.0, -0.17, 1.13))                       # no weld grip: not grippable
        sc.camera("venue", (-3.0, -3.6, 2.2), (X / 2 + 0.5, 0.0, 1.2), fovy=55)

    def reset(self, w):
        c, R = w.jaw_frame("right")                                         # the ball between the right jaws
        w.put("ball", c)
        w.close_on("right", "ball")

    def referee_reset(self, w, ref):
        self.ball = ref.geoms(body="ball")
        self.wall = ref.geoms(names=["wall"])
        self.robot = ref.part("robot")
        self.arm = ref.part("right_arm")
        self.not_arm = self.robot & ~self.arm
        self.other = self.robot & ~ref.part("hands", "forearms")
        self.trackers = {"released": None, "last_touch": 0.0, "wall": Touch(ref, self.ball, self.wall),
                         "caught": None, "last_held": None, "hand": None}

    def may_grip(self, w, side, name):
        return False                                                        # no weld grip exists in this task

    def holding(self, w) -> str | None:
        """The gripper that holds the ball now: both its jaws touch it and its centre is between the jaws' pads (not a
        ball balanced on top of closed jaws)."""
        d = w.d
        for s in ("right", "left"):
            if w.held[s] != "ball":
                continue
            k = w.hands.centre[s]
            off = d.site_xmat[k].reshape(3, 3).T @ (w.pos("ball") - d.site_xpos[k])
            if (abs(off[0]) < w.hands.opening(s) / 2 and abs(off[1]) <= realhand.JAW_WIDE / 2
                    and abs(off[2]) <= realhand.JAW_LEN / 2):
                return s
        return None

    def substep(self, w, ref):
        tr, p = self.trackers, self.p
        pts = ref.contact_points(self.robot, ref.ground)
        if len(pts) and float(pts[:, 0].max()) >= 0.0:
            return ref.fail("touched the ground on or beyond the line", x=round(float(pts[:, 0].max()), 3))
        if ref.touching(self.ball, ref.ground):
            return ref.fail("the ball touched the ground")
        side = self.holding(w)
        if tr["caught"] is not None:
            if side is not None:
                tr["last_held"] = round(ref.time, 4)
            elif ref.time - tr["last_held"] > p["held_gap_s"] + 1e-9:
                return ref.fail("the ball was dropped after the catch")
            return
        if tr["released"] is None:
            if ref.touching(self.ball, self.robot):
                tr["last_touch"] = round(ref.time, 4)
                return
            if ref.time - tr["last_touch"] < p["release_s"] - 1e-9:
                return
            tr["released"] = tr["last_touch"]
            ref.metrics["release_speed_m_s"] = round(float(np.linalg.norm(w.vel("ball"))), 2)
            ref.stage("release", t=tr["released"])
            return
        hit = tr["wall"].update()
        if not ref.has("target"):
            if hit:
                pt = ref.contact_points(self.ball, self.wall)[0]
                off = math.hypot(float(pt[1]) - p["target_y_m"], float(pt[2]) - p["target_height_m"])
                ref.metrics["target_offset_m"] = round(off, 3)
                ref.metrics["wall_speed_m_s"] = round(float(np.linalg.norm(w.vel("ball"))), 2)
                if off > p["target_diameter_m"] / 2:
                    return ref.fail("the ball hit the wall outside the target", y=round(float(pt[1]), 3), z=round(float(pt[2]), 3))
                ref.stage("target", offset_m=round(off, 3))
            elif (ref.touching(self.ball, self.not_arm) or side is not None
                  or (ref.time - tr["released"] > p["retouch_grace_s"] and ref.touching(self.ball, self.arm))):
                return ref.fail("the ball was touched again before it had hit the wall", parts=sorted(ref.parts_touching(self.ball)))
            return
        if side is not None:
            tr["caught"] = tr["last_held"] = round(ref.time, 4)
            tr["hand"] = side
            ref.metrics["catch_height_m"] = round(float(w.pos("ball")[2]), 3)
            ref.stage("catch", hand=side)
        elif ref.touching(self.ball, self.other):
            ref.fail("the rebound touched the body before it was caught", parts=sorted(ref.parts_touching(self.ball) - LEGAL))

    def step(self, w, ref):
        tr = self.trackers
        if tr["caught"] is not None and ref.time - tr["caught"] >= self.p["hold_s"] - 1e-9:
            if ref.stage("hold"):
                ref.succeed()

    def privileged(self, w):
        p, tr = self.p, self.trackers
        return {"ball": w.pos("ball").tolist(), "ball_velocity": w.vel("ball").tolist(), "held_by": self.holding(w),
                "released": tr["released"] is not None,
                "target": {"x": p["wall_distance_m"], "y": p["target_y_m"], "z": p["target_height_m"],
                           "radius": p["target_diameter_m"] / 2}}
