"""Wall ball: from behind the line, throw the tennis ball at the target circle on the wall 5 m away and catch the
rebound with a hand before it touches the ground, and keep it. Official ball with its real flight and bounce; the
Unitree H1-2."""
import math

import mujoco
import numpy as np

from rfo.referee import Touch
from rfo.scene import OFFICIAL, VISUAL
from rfo.task import TaskBase

BALL = OFFICIAL["tennis"]                      # ITF: 6.54-6.86 cm, 56.0-59.4 g, rebound 0.745; drag and Magnus lift
LEGAL = {"left_hand", "right_hand", "left_forearm", "right_forearm"}
PALM_OFFSET = 0.022 + 0.003                    # the palm face of the hand's pad, and a gap, from the wrist mount's axis


class Task(TaskBase):
    name = "wall-ball"
    title = "Wall ball: throw, rebound, catch"
    category = "throwing-catching-striking"
    robot = "unitree_h1"
    rulebook = ("No rule book: a wall-ball drill (throw and catch against a wall, as used in baseball, cricket and "
                "handball training) with this benchmark's numbers. The ball is the ITF's (Rules of Tennis 2024, Rule "
                "3 and Appendix I: size, mass, rebound)")
    deviations = [
        "The hand throws and catches by a grip switched on and off: it holds a ball whose surface is within 3.5 cm of "
        "the palm and that moves no faster than 6 m/s relative to it; the ball is released when the grip is switched "
        "off.",
        "The wall is rigid and smooth; the ball's rebound from it is the ITF ball's rebound from a hard floor "
        "(" + f"{BALL['bounce']:.3f}" + " of the speed across the wall).",
        "Flight: quasi-steady aerodynamics (MuJoCo's ellipsoid fluid model: drag and Magnus lift), still air.",
    ]
    time_limit_s = 15.0
    start = (-0.40, 0.0, 0.0)
    stages = ["release", "target", "catch", "hold"]
    fall_z = 0.50
    params = dict(wall_distance_m=5.0, target_height_m=1.5, target_diameter_m=0.5, target_y_m=0.0,
                  retouch_grace_s=0.15, hold_s=1.0, fall_pelvis_m=0.50)

    sentence = ("Throw the tennis ball in your right hand at the target circle on the wall and catch the rebound with a "
                "hand before it touches the ground, and keep hold of it.")
    rules = ("The tennis ball (" + f"{2 * BALL['radius']:.3f} m across, {BALL['mass']:.4f} kg, it keeps "
             f"{BALL['bounce']:.3f} of its speed in a bounce" + ", it flies in air with drag) starts gripped against "
             "your right palm. A wall stands {wall_distance_m} m beyond the line you stay behind; the target is a "
             "circle {target_diameter_m} m across painted on it, its centre {target_height_m} m above the ground and "
             "{target_y_m} m to the left of the point straight ahead of you. Let go of the ball (the throw, once); "
             "the first thing it touches must be the wall, at a point inside the target circle. Then catch the "
             "rebound: a hand's grip closing on the ball in the air (the grip holds a ball whose surface is within "
             "3.5 cm of the palm and that moves no faster than 6 m/s relative to it); either hand may catch, and "
             "before the grip the rebound may touch only your hands and forearms. You succeed when the ball has been "
             "gripped after the rebound and kept for {hold_s} s without a break. You fail if any part of you touches "
             "the ground on or beyond the line at any time; if the ball touches the ground at any time before it is "
             "caught; if it hits the wall outside the circle; if any part of you touches it after the release and "
             "before the wall (your throwing arm may still brush it during the first {retouch_grace_s} s; it cannot "
             "be gripped then); if the rebound touches any part of you other than a hand or a forearm before it is "
             "gripped; if you let go of it after the catch; if you fall (your pelvis lower than {fall_pelvis_m} m "
             "above the ground, or any part of you other than your feet on the ground); or after {time_limit_s} s.")
    venue = ("You face the wall (+x), your pelvis 0.40 m behind the line; the wall is {wall_distance_m} m beyond the "
             "line, 6 m wide and 4 m high. The target circle is straight ahead. The ball is against your right palm, "
             "the forearm level and pointing forwards. Still air. The ball is released when the hand's grip is "
             "switched off.")
    difficulty = ("To come back five metres through the air the ball has to hit the wall at about 16 m/s or more, "
                  "inside a circle half a metre across, and it then returns in under half a second at about 10 m/s. "
                  "The palm must be on its line within a few centimetres with the grip closing as it arrives.")

    def build(self, sc):
        p = self.p
        self.fall_z = p["fall_pelvis_m"]
        X, r = p["wall_distance_m"], p["target_diameter_m"] / 2
        sc.box("court", (X / 2 - 1.0, 0, 0.0003), (X / 2 + 1.0, 3.0, 0.0003), rgba=(0.30, 0.42, 0.60, 1))
        sc.line("line", (0.0, -3.0), (0.0, 3.0))
        sc.box("wall", (X + 0.10, 0.0, 2.0), (0.10, 3.0, 2.0), rgba=(0.82, 0.80, 0.74, 1), solid="hit")
        q = (math.sqrt(0.5), 0, math.sqrt(0.5), 0)
        sc.geom(sc.wb, "target", type="cylinder", pos=(X - 0.001, p["target_y_m"], p["target_height_m"]), quat=q,
                size=(r, 0.001), rgba=(0.9, 0.2, 0.15, 1), **VISUAL)
        sc.geom(sc.wb, "target_centre", type="cylinder", pos=(X - 0.002, p["target_y_m"], p["target_height_m"]), quat=q,
                size=(r * 0.35, 0.001), rgba=(0.97, 0.97, 0.95, 1), **VISUAL)
        sc.ball("ball", "tennis", (0.0, -0.17, 1.13), grippable=True)
        sc.camera("venue", (-3.0, -3.6, 2.2), (X / 2 + 0.5, 0.0, 1.2), fovy=55)

    def reset(self, w):
        m, d = w.m, w.d
        mujoco.mj_kinematics(m, d)
        b = w.robot.mount["right"]
        w.put("ball", d.xpos[b] + d.xmat[b].reshape(3, 3) @ np.array([PALM_OFFSET + BALL["radius"], 0.0, 0.045]))
        w.grab("right", "ball", event=False)

    def referee_reset(self, w, ref):
        self.ball = ref.geoms(body="ball")
        self.wall = ref.geoms(names=["wall"])
        self.robot = ref.part("robot")
        self.arm = ref.part("right_arm")
        self.not_arm = self.robot & ~self.arm
        self.other = self.robot & ~ref.part("hands", "forearms")
        self.trackers = {"released": None, "wall": Touch(ref, self.ball, self.wall), "caught": None}

    def may_grip(self, w, side, name):
        tr = self.trackers
        return tr.get("released") is None or (w.ref.has("target") and tr.get("caught") is None)

    def substep(self, w, ref):
        tr, p = self.trackers, self.p
        pts = ref.contact_points(self.robot, ref.ground)
        if len(pts) and float(pts[:, 0].max()) >= 0.0:
            return ref.fail("touched the ground on or beyond the line", x=round(float(pts[:, 0].max()), 3))
        held = bool(w.holder("ball"))
        if tr["caught"] is not None:
            if not held:
                ref.fail("the ball was dropped after the catch")
            return
        if ref.touching(self.ball, ref.ground):
            return ref.fail("the ball touched the ground")
        if tr["released"] is None:
            if not held:
                tr["released"] = ref.time
                ref.metrics["release_speed_m_s"] = round(float(np.linalg.norm(w.vel("ball"))), 2)
                ref.stage("release")
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
            elif (ref.touching(self.ball, self.not_arm)
                  or (ref.time - tr["released"] > p["retouch_grace_s"] and ref.touching(self.ball, self.arm))):
                return ref.fail("the ball was touched again before it had hit the wall", parts=sorted(ref.parts_touching(self.ball)))
            return
        if held:
            tr["caught"] = ref.time
            ref.metrics["catch_height_m"] = round(float(w.pos("ball")[2]), 3)
            ref.stage("catch", hand=w.holder("ball")[0])
        elif ref.touching(self.ball, self.other):
            ref.fail("the rebound touched the body before it was gripped", parts=sorted(ref.parts_touching(self.ball) - LEGAL))

    def step(self, w, ref):
        if ref.has("catch") and ref.hold("hold", bool(w.holder("ball")), self.p["hold_s"]):
            if ref.stage("hold"):
                ref.succeed()

    def privileged(self, w):
        p = self.p
        return {"ball": w.pos("ball").tolist(), "ball_velocity": w.vel("ball").tolist(), "held_by": w.holder("ball"),
                "target": {"x": p["wall_distance_m"], "y": p["target_y_m"], "z": p["target_height_m"],
                           "radius": p["target_diameter_m"] / 2}}
