"""Wall ball: from behind the line, throw the tennis ball at the target circle on the wall 5 m away
and catch the rebound before it touches the ground, and keep it. No weld grip: both hands are the H1-2's own Inspire
five-finger hands (rfo.realhand, "inspire"), holding the ball by contact and friction only (the throw is the right hand
opening; the catch is a hand's fingers closing round the ball in the air). Official ball with its real flight and
bounce; the Unitree H1-2."""
import math

import mujoco
import numpy as np

from rfo.referee import Touch
from rfo.scene import OFFICIAL, VISUAL
from rfo.task import TaskBase

BALL = OFFICIAL["tennis"]                      # ITF: 6.54-6.86 cm, 56.0-59.4 g, rebound 0.745; drag and Magnus lift
LEGAL = {"left_hand", "right_hand", "left_forearm", "right_forearm"}
BALL_IN_HAND_M = (0.016, 0.030)                # the ball's centre from the right hand's grasp centre at the start: out
#                                                of the palm, along the fingers (it rests on the palm; a search)
HOLD_REACH_M = 0.12                            # a held ball's centre within this of the hand's grasp centre
# The ball on the wall. The wall (concrete or plywood) is rigid next to a tennis ball: what yields in the impact is the
# ball itself. R. Cross, "Dynamic properties of tennis balls", Sports Engineering 2 (1999) 23-33, Figs 7-8 (a ball
# fired at a rigid force plate, 2-17 m/s): the impact lasts 4.0-4.5 ms at 10-17 m/s and the ball's centre of mass
# comes at most 16.5 mm closer to the surface at 17 m/s (about 10 mm at 10 m/s). The ball's own contact (rfo/scene.py:
# a spring of 250 rad/s, a 12.6 ms impact) let its centre sink 57-73 mm into the wall at 17-21 m/s, more than
# its diameter. The wall's contact wins over the ball's (priority 2) and is that impact: a spring-damper of natural
# frequency WALL_W (pi / WALL_W = 4.5 ms, the measured duration) whose damping ratio WALL_ZETA keeps, on average, the
# ITF rebound (BALL["bounce"]) that the rules quote, measured in this simulator (1 ms physics, the ball shot at the
# wall from 10 arrival phases at 10, 17 and 21 m/s): it keeps 0.747-0.756 on average (0.70-0.80 by
# phase), its centre comes 12 / 21 / 25 mm closer (at most 14 / 23 / 28 mm), the impact lasts 4-5 ms. The ball's
# friction and rolling resistance are kept (condim 6). The robot never reaches the wall (it stays behind the line).
WALL_W, WALL_ZETA = 700.0, 0.096


class Task(TaskBase):
    name = "wall-ball"
    title = "Wall ball: throw, rebound, catch"
    category = "throwing-catching-striking"
    robot = "unitree_h1"
    rulebook = ("No rule book: a wall-ball drill (throw and catch against a wall, as used in baseball, cricket and "
                "handball training) with this benchmark's numbers. The ball is the ITF's (Rules of Tennis 2024, Rule "
                "3 and Appendix I: size, mass, rebound)")
    deviations = [
        "The hands: the H1-2's own Inspire five-finger hands at the device's forces (six drives: four fingers, the "
        "thumb's flexion and rotation; fingertip forces 20 N, the thumb 30 N; the fingers close at most 260 deg/s, "
        "the thumb 70 deg/s), each closed by one command (the synergy: every drive towards its closed position); "
        "they hold the ball by contact and friction only, and it can slip, turn and drop.",
        "The throw and the catch: the ball is released when it has touched no part of you for {release_s} s (at its "
        "last touch); a hand holds it while it touches that hand's fingers and its thumb or palm, its centre on the "
        "palm's side of the hand and within " + f"{HOLD_REACH_M:g}" + " m of the hand's grasp point (not a ball "
        "balanced on the back of the hand or the fingertips), and a catch is the ball held after the rebound. A held "
        "ball may lose that hold for at most {held_gap_s} s.",
        "The wall is rigid and smooth; the ball's rebound from it is the ITF ball's rebound from a hard floor "
        "(" + f"{BALL['bounce']:.3f}" + " of the speed across the wall, on average: with 1 ms physics it varies by "
        "up to 0.05 either way with where in a step the ball arrives; a real ball keeps less at high speed, about "
        "0.65 at 17 m/s). The impact itself is the ball's measured one on a rigid surface (R. Cross, Sports "
        "Engineering 2, 1999): about 4.5 ms long, the ball's centre coming about 20 mm closer to the wall at 17 m/s.",
        "Flight: quasi-steady aerodynamics (MuJoCo's ellipsoid fluid model: drag and Magnus lift), still air. The "
        "world has elliptic friction cones and an impedance ratio of 100 (the real hands' setting, which makes a "
        "held ball stay put); they apply to every contact.",
    ]
    time_limit_s = 15.0
    start = (-0.40, 0.0, 0.0)
    stages = ["release", "target", "catch", "hold"]
    fall_z = 0.50
    params = dict(wall_distance_m=5.0, target_height_m=1.5, target_diameter_m=0.5, target_y_m=0.0, release_s=0.05,
                  retouch_grace_s=0.15, held_gap_s=0.05, hold_s=1.0, fall_pelvis_m=0.50)

    sentence = ("Throw the tennis ball held in your right hand at the target circle on the wall and catch the "
                "rebound in a hand before it touches the ground, and keep hold of it.")
    rules = ("The tennis ball (" + f"{2 * BALL['radius']:.3f} m across, {BALL['mass']:.4f} kg, it keeps "
             f"{BALL['bounce']:.3f} of its speed in a bounce" + ", it flies in air with drag) starts held in "
             "your right hand. Both your hands are five-finger hands that hold things only by contact and friction; "
             "nothing else holds the ball, and it can slip or drop. A hand holds the ball while the ball touches its "
             "fingers and its thumb or palm, with the ball's centre on the palm's side of the hand and within "
             "" + f"{HOLD_REACH_M:g}" + " m of the hand's grasp point (between the closed fingers and the palm; not "
             "resting on the back of the hand or on the fingertips). A wall stands {wall_distance_m} m beyond the line you stay behind; the "
             "target is a circle {target_diameter_m} m across painted on it, its centre {target_height_m} m above "
             "the ground and {target_y_m} m to the left of the point straight ahead of you. The throw: the ball is "
             "released when it has touched no part of you for {release_s} s (it is released at its last touch; "
             "once). The first thing it touches after that must be the wall, at a point inside the target circle. "
             "Then catch the rebound: a hand holding the ball before it has touched the ground; "
             "either hand may catch, and before the catch the rebound may touch only your hands and forearms. You "
             "succeed when the ball has been held for {hold_s} s from the catch, never losing the hold for more than "
             "{held_gap_s} s. You fail if any part of you touches the ground on or beyond "
             "the line at any time; if the ball touches the ground at any time before the end; if it hits the wall "
             "outside the circle; if any part of you touches it after the release and before the wall (your right "
             "arm may still brush it during the first {retouch_grace_s} s, but not hold it); if the rebound touches "
             "any part of you other than a hand or a forearm before the catch; if the ball goes unheld for more than "
             "{held_gap_s} s after the catch; if you fall (your pelvis lower than {fall_pelvis_m} m above the "
             "ground, or any part of you other than your feet on the ground); or after {time_limit_s} s.")
    venue = ("You face the wall (+x), your pelvis 0.40 m behind the line; the wall is {wall_distance_m} m beyond the "
             "line, 6 m wide and 4 m high. The target circle is straight ahead. The ball is held in your closed right hand "
             "(closure command 1), against the palm, the forearm level and pointing forwards; your left hand is open "
             "(closure command 0). Still air. The grip columns of the action rows are the hands' closure commands (0 "
             "open, 1 closed).")
    difficulty = ("To come back five metres through the air the ball has to hit the wall at about 16 m/s or more, "
                  "inside a circle half a metre across, and it then returns in under half a second at about 10 m/s. "
                  "The ball, 67 mm across, has to arrive in an open hand, and the fingers (260 deg/s) and the slower thumb "
                  "have to close round it before it bounces out of the palm.")

    def build(self, sc):
        p = self.p
        self.fall_z = p["fall_pelvis_m"]
        sc.real_hands["left"] = sc.real_hands["right"] = "inspire"
        X, r = p["wall_distance_m"], p["target_diameter_m"] / 2
        sc.box("court", (X / 2 - 1.0, 0, 0.0003), (X / 2 + 1.0, 3.0, 0.0003), rgba=(0.30, 0.42, 0.60, 1))
        sc.line("line", (0.0, -3.0), (0.0, 3.0))
        sc.box("wall", (X + 0.10, 0.0, 2.0), (0.10, 3.0, 2.0), rgba=(0.82, 0.80, 0.74, 1), solid="hit", priority=2,
               condim=6, friction=(0.7, 0.003, BALL["roll"]), solref=(-WALL_W ** 2, -2 * WALL_ZETA * WALL_W),
               solimp=(0.95, 0.99, 0.001, 0.5, 2))
        q = (math.sqrt(0.5), 0, math.sqrt(0.5), 0)
        sc.geom(sc.wb, "target", type="cylinder", pos=(X - 0.001, p["target_y_m"], p["target_height_m"]), quat=q,
                size=(r, 0.001), rgba=(0.9, 0.2, 0.15, 1), **VISUAL)
        sc.geom(sc.wb, "target_centre", type="cylinder", pos=(X - 0.002, p["target_y_m"], p["target_height_m"]), quat=q,
                size=(r * 0.35, 0.001), rgba=(0.97, 0.97, 0.95, 1), **VISUAL)
        sc.ball("ball", "tennis", (0.0, -0.17, 1.13))                       # no weld grip: not grippable
        sc.camera("venue", (-3.0, -3.6, 2.2), (X / 2 + 0.5, 0.0, 1.2), fovy=55)

    def reset(self, w):
        c, R = w.grasp_frame("right")                                       # the ball in the right hand
        w.put("ball", c + R[:, 0] * BALL_IN_HAND_M[0] + R[:, 2] * BALL_IN_HAND_M[1])
        w.close_on("right", "ball")

    def referee_reset(self, w, ref):
        self.ball = ref.geoms(body="ball")
        self.wall = ref.geoms(names=["wall"])
        self.robot = ref.part("robot")
        self.arm = ref.part("right_arm")
        self.not_arm = self.robot & ~self.arm
        self.other = self.robot & ~ref.part("hands", "forearms")
        self.trackers = {"released": None, "last_touch": 0.0, "wall": Touch(ref, self.ball, self.wall),
                         "caught": None, "last_held": None, "hand": None, "v_in": 0.0}

    def may_grip(self, w, side, name):
        return False                                                        # no weld grip exists in this task

    def holding(self, w) -> str | None:
        """The hand that holds the ball now: it touches the hand's fingers and its thumb or palm (World.held), its
        centre on the palm's side and within HOLD_REACH_M of the hand's grasp point (not a ball balanced on the back
        of the hand or on the fingertips)."""
        d = w.d
        for s in ("right", "left"):
            if w.held[s] != "ball":
                continue
            k = w.hands.centre[s]
            off = d.site_xmat[k].reshape(3, 3).T @ (w.pos("ball") - d.site_xpos[k])
            if off[0] >= 0.0 and float(np.linalg.norm(off)) <= HOLD_REACH_M:
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
        if not hit and not ref.has("target") and not ref.touching(self.ball, self.wall):
            tr["v_in"] = float(np.linalg.norm(w.vel("ball")))             # the speed it arrives at the wall with
        if not ref.has("target"):
            if hit:
                pt = ref.contact_points(self.ball, self.wall)[0]
                off = math.hypot(float(pt[1]) - p["target_y_m"], float(pt[2]) - p["target_height_m"])
                ref.metrics["target_offset_m"] = round(off, 3)
                ref.metrics["wall_speed_m_s"] = round(tr["v_in"], 2)
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
