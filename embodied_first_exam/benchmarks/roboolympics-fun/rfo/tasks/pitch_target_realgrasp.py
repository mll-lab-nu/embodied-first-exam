"""Baseball pitch with real grasping (Official Baseball Rules): pitch-target, but nothing is welded. The baseball starts
held between the jaws of the right hand's Unitree Dex1-1 two-jaw gripper (the core's rfo.realhand) by their friction
only: it can slip, roll out and drop. The release is the ball leaving the hand: the jaws must open (at most 375 mm/s,
from the clamp: when they let go is the pitcher's timing, not a switch) and the ball touch nothing of the pitcher any
more. From the pitcher's plate on the mound, with a foot on the plate at that release, throw the baseball through the
strike zone over home plate, 18.44 m away, on the fly.

Everything else is pitch-target's (shared/rfo/tasks/pitch_target.py, copied here, unchanged where not said): the
official mound, plate distance, strike zone and ball, its flight in air (drag and Magnus lift), the Unitree H1-2, the
success line, every number.

What is new, and why:
* the right hand is the Dex1-1 (the core's model): the ball (73 mm) sits at the centre of its jaws (90 mm stroke) and
  the jaws close on it at reset (close_on: the full 120 N clamp), the forearm level and pointing forwards as in
  pitch-target;
* the release, the ball before it and no re-grip are judged from contacts (below), not from a grip switch;
* the ball may not touch the ground at any time (pitch-target judges the ground only after its switched release; a
  ball that is still being held can reach it now).
"""
import math

import mujoco
import numpy as np

from rfo.referee import Crossing
from rfo.scene import HITTABLE, OFFICIAL, STANDABLE, VISUAL
from rfo.task import TaskBase

BALL = OFFICIAL["baseball"]                    # 9 to 9.25 in round, 5 to 5.25 oz; drag and Magnus lift in air
IN, FT = 0.0254, 0.3048
# OBR 2.04 (Appendix 2): the level area round the plate is 5 ft wide and 34 in deep, from 6 in in front of the plate's
# front edge to 22 in behind its back edge; the mound's 18 ft circle is centred 18 in in front of the plate's front
# edge; from the level area's front edge the slope falls 1 in per ft.
LEVEL_FRONT, LEVEL_BACK, LEVEL_HALF = 6 * IN, 28 * IN, 2.5 * FT
CIRCLE_AHEAD = 18 * IN
DIRT, CHALK = (0.66, 0.47, 0.30, 1), (0.97, 0.97, 0.95, 1)


def set_arm(w, **angles) -> None:
    """Put arm joints (names without "_joint") at angles for t = 0, and their held targets with them."""
    r, d = w.robot, w.d
    for name, v in angles.items():
        i = w.L.JOINTS.index(name + "_joint")
        d.qpos[r.qadr[i]] = v
        r.arb.q_a[i] = r.arb.q_b[i] = v
    mujoco.mj_kinematics(w.m, d)


class Task(TaskBase):
    name = "pitch-target-realgrasp"
    title = "Baseball: pitch a strike, real grasp"
    category = "throwing-catching-striking"
    robot = "unitree_h1"
    rulebook = ("Official Baseball Rules (MLB, 2024 edition): 2.01 and Appendices 1-2 (the pitcher's plate 60 ft 6 in "
                "from the back point of home plate, 10 in above it; the mound), 2.02 (home plate), 3.01 (the ball), "
                "5.07(a) (the pivot foot in contact with the plate), 5.07(c) (the 15 s pitch timer), Definitions of "
                "Terms: \"strike zone\", \"in flight\"")
    deviations = [
        "3.01 (the ball in the pitcher's hand): the hand is a two-jaw gripper, Unitree's Dex1-1 (90 mm stroke, 80 mm "
        "jaws, at most 120 N of clamp, opening at most 375 mm/s; Unitree sells it for the G1, the H2 and the R1, not "
        "the H1-2: here it sits on the H1-2's right wrist where the palm ends); the ball starts held between its jaws "
        "by their friction only (no fingers, no seams: no grip-made spin beyond what the jaws' motion gives). The "
        "release is the moment the ball last touched you before it had touched nothing of you for {release_s} s.",
        "Definitions (strike zone): there is no batter, so the zone's height is fixed, {zone_low_m} m to "
        "{zone_high_m} m above home plate (the hollow of the knee to the midpoint of the torso of a 1.8 m batter). A "
        "strike is called when the ball's centre crosses the zone's front plane (home plate's front edge) inside "
        "the zone, in flight; the rule's \"any part of the ball through any part of the zone\" (the plate's whole "
        "depth, the ball's edge) is not used: stricter.",
        "5.07(a): \"the pivot foot in contact with the plate\" is judged at the release: a foot that touches the mound "
        "and whose sole is over the plate; either foot may be the pivot foot. Wind-up and set positions and balks "
        "are not judged (no runners).",
        "5.07(c): the pitch timer runs from the start of the episode: the ball must be released within "
        "{release_limit_s} s.",
        "No batter, catcher or umpire: a backstop behind home plate; one pitch (a ball dropped or caught again is no "
        "second chance), and a fall before the call ends the attempt as a failure.",
        "Flight: quasi-steady aerodynamics (MuJoCo's ellipsoid fluid model: drag and Magnus lift), still air.",
    ]
    time_limit_s = 20.0
    start = (-0.09, 0.0, 0.0)
    stages = ["release", "strike"]
    fall_z = 0.75
    params = dict(plate_distance_m=18.44, mound_height_m=0.254, mound_diameter_m=5.486, pitchers_plate_width_m=0.610,
                  pitchers_plate_depth_m=0.152, home_plate_width_m=0.432, zone_width_m=0.432, zone_low_m=0.46,
                  zone_high_m=1.07, release_limit_s=15.0, release_s=0.02, retouch_grace_s=0.20, fall_pelvis_m=0.75)

    sentence = ("Pitch a strike: from the pitcher's plate on the mound, with a foot on the plate, throw the baseball "
                "held in your right gripper through the strike zone over home plate, on the fly.")
    rules = ("The baseball (" + f"{2 * BALL['radius']:.3f} m across, {BALL['mass']:.3f} kg" + ", it flies in air with "
             "drag and spin lift) starts held between the two jaws of your right hand, a two-jaw gripper that holds "
             "only by friction: the ball can slip or roll out and drop. You stand on the pitcher's plate (a slab "
             "{pitchers_plate_width_m} m wide and {pitchers_plate_depth_m} m deep, level with the mound's top) on a "
             "mound {mound_diameter_m} m across whose top is {mound_height_m} m above home plate; in front of the "
             "plate the mound falls 1 in 12. The front edge of the pitcher's plate is {plate_distance_m} m from the "
             "back point of home plate; home plate is {home_plate_width_m} m wide and as deep, so its front edge is "
             "that much nearer. The strike zone is the rectangle above home plate's front edge, {zone_width_m} m wide "
             "and from {zone_low_m} m to {zone_high_m} m above home plate. The pitch: the release is the moment the "
             "ball last touched you, once it has then touched nothing of you for {release_s} s (until then it is "
             "still in your hand, wherever it rests on you). There is one release: within {release_limit_s} s of "
             "the start, and at that moment at least one of your feet is in contact with the pitcher's plate (it "
             "touches the mound and part of its sole is over the plate). After the release no part of you may touch "
             "the ball and your gripper may not hold it again (both jaws on it), except that your right arm and its "
             "gripper may still brush it during the first {retouch_grace_s} s. You succeed when the ball's centre "
             "then crosses the plane of the zone inside the zone, before the ball has touched the ground. You fail "
             "if no foot is on the plate at the release; if the ball is not released in time; if it touches the "
             "ground (the mound included) at any time before home plate, also before the release; if it crosses the "
             "plane outside the zone (a ball); if it is held again or touched after the release (but for the grace "
             "above); if you fall before the call (your pelvis lower than {fall_pelvis_m} m above home plate's "
             "level, or any part of you other than your feet on the ground or the mound); or after {time_limit_s} s.")
    venue = ("You stand on the mound facing home plate (+x), both feet across the pitcher's plate, your pelvis above "
             "its middle; home plate's front edge is 18.1 m ahead and {mound_height_m} m below the plate you stand "
             "on. The mound's level top reaches 0.15 m in front of the pitcher's plate, 0.56 m behind it and 0.76 m "
             "to each side. A backstop stands 3 m behind home plate. Your right forearm is level and points "
             "forwards, the gripper's fingers forwards and its jaws closed on the ball (they close along the palm's "
             "normal, sideways: one jaw on each side of the ball). Still air. The jaws open when your right grip "
             "command goes to 0 (at most 375 mm/s).")
    difficulty = ("From 18.44 m the ball needs more than 13 m/s even on a high arc, and the zone is 0.43 m wide: "
                  "a release direction right to about one degree. The H1-2 has no throwing motion; the speed has to "
                  "come from the trunk and the whole arm while a foot stays on the plate and the body on the mound, "
                  "and two jaws that open no faster than 375 mm/s have to let the ball go at the right hundredth of "
                  "a second.")

    # ------------------------------------------------------------------ the venue
    def geometry(self):
        p = self.p
        return dict(zone_x=p["plate_distance_m"] - p["home_plate_width_m"], apex_x=p["plate_distance_m"],
                    top=p["mound_height_m"], circle_x=CIRCLE_AHEAD, radius=p["mound_diameter_m"] / 2)

    def build(self, sc):
        p, g = self.p, self.geometry()
        self.fall_z = p["fall_pelvis_m"]
        sc.real_hands["right"] = "dex1"
        H, R = g["top"], g["radius"]
        sc.root.find("option").append(sc.root.makeelement("flag", dict(multiccd="enable")))   # feet (hulls) on the mound
        # the mound: the convex hull of its level top and its base circle; in front that is the 1 in 12 slope
        d = p["pitchers_plate_depth_m"]
        v = []
        for x, y in ((LEVEL_FRONT, LEVEL_HALF), (LEVEL_FRONT, -LEVEL_HALF), (-LEVEL_BACK, LEVEL_HALF), (-LEVEL_BACK, -LEVEL_HALF)):
            v += [x, y, H]
        n = 40
        for i in range(n):
            a = 2 * math.pi * i / n
            v += [g["circle_x"] + R * math.cos(a), R * math.sin(a), 0.0]
        asset = sc.root.find("asset")
        asset.append(asset.makeelement("mesh", dict(name="mound", vertex=" ".join(f"{x:.6g}" for x in v))))
        sc.geom(sc.wb, "mound", type="mesh", mesh="mound", rgba=DIRT, friction=(1.0, 0.005, 0.0001), **STANDABLE)
        sc.ground.append("mound")
        sc.box("pitchers_plate", (-d / 2, 0, H + 0.0006), (d / 2, p["pitchers_plate_width_m"] / 2, 0.0006), rgba=CHALK)
        # home plate (2.02): a 17 in square whose back corners are cut to a point; drawn in strips
        hw, zx = p["home_plate_width_m"] / 2, g["zone_x"]
        sc.disc("home_dirt", (g["apex_x"] - 0.2, 0.0), 3.96, rgba=DIRT)
        sc.box("home_plate_front", (zx + hw / 2, 0, 0.0012), (hw / 2, hw, 0.0006), rgba=CHALK)
        k = 8
        for i in range(k):
            f = (i + 0.5) / k
            sc.box(f"home_plate_back{i}", (zx + hw + f * hw, 0, 0.0012), (hw / (2 * k), hw * (1 - f), 0.0006), rgba=CHALK)
        zl, zh = p["zone_low_m"], p["zone_high_m"]
        zw, t = p["zone_width_m"] / 2, 0.006                 # the zone: a drawn frame (it stops nothing)
        frame = dict(rgba=(0.95, 0.2, 0.15, 0.9), **VISUAL)
        for s, tag in ((1, "L"), (-1, "R")):
            sc.geom(sc.wb, f"zone_side{tag}", type="box", pos=(zx, s * (zw + t), (zl + zh) / 2), size=(t, t, (zh - zl) / 2 + 2 * t), **frame)
        for z, tag in ((zl - t, "low"), (zh + t, "high")):
            sc.geom(sc.wb, f"zone_{tag}", type="box", pos=(zx, 0, z), size=(t, zw, t), **frame)
        sc.geom(sc.wb, "backstop", type="box", pos=(g["apex_x"] + 3.0, 0, 2.0), size=(0.05, 4.0, 2.0),
                rgba=(0.2, 0.3, 0.25, 0.6), **HITTABLE)
        sc.ball("ball", "baseball", (0.4, -0.17, H + 1.13))
        sc.camera("venue", (-4.5, -5.0, 3.2), (6.0, 0.0, 0.8), fovy=55)
        sc.camera("plate", (g["zone_x"] - 3.5, -2.0, 1.6), (g["zone_x"], 0.0, 0.8), fovy=50)
        sc.camera("hand", (1.0, -1.1, 1.6), (0.3, -0.25, 1.15), fovy=40)

    def reset(self, w):
        m, d = w.m, w.d
        d.qpos[w.robot.fq + 2] += self.p["mound_height_m"]    # the robot stands on the mound's top
        mujoco.mj_kinematics(m, d)
        c, _ = w.jaw_frame("right")                           # the ball at the jaws' centre (pitch-target's arm)
        w.put("ball", c)
        w.close_on("right", "ball")

    # ------------------------------------------------------------------ the referee
    def referee_reset(self, w, ref):
        g = self.geometry()
        self.ball = ref.geoms(body="ball")
        self.robot = ref.part("robot")
        self.arm = ref.part("right_arm")
        self.not_arm = self.robot & ~self.arm
        self.jaws = [ref.geoms(body=f"right_hand_jaw_{j}") for j in ("a", "b")]
        self.soles = {s: w.m.geom(f"{s}_foot_strike").id for s in ("left", "right")}
        # free: (time, speed, height, feet on the plate) of the ball's first step touching nothing of you, while the
        # release is not yet confirmed
        self.trackers = {"released": None, "free": None, "plane": Crossing((1, 0, 0), g["zone_x"], direction=1)}

    def may_grip(self, w, side, name):
        return False                                          # (no weld grip: nothing is grippable)

    def feet_on_plate(self, w, ref) -> list[str]:
        """The feet in contact with the pitcher's plate: on the mound, part of the sole over the plate's rectangle."""
        p, m, d = self.p, w.m, w.d
        on = ref.parts_touching(ref.ground)
        out = []
        for side, g in self.soles.items():
            if f"{side}_foot" not in on:
                continue
            hx, hy, hz = m.geom_size[g]
            R = d.geom_xmat[g].reshape(3, 3)
            for fx in np.linspace(-1, 1, 13):
                for fy in (-1.0, 0.0, 1.0):
                    q = d.geom_xpos[g] + R @ np.array([fx * hx, fy * hy, -hz])
                    if -p["pitchers_plate_depth_m"] <= q[0] <= 0.0 and abs(q[1]) <= p["pitchers_plate_width_m"] / 2:
                        out.append(side)
                        break
                else:
                    continue
                break
        return out

    def _held(self, ref) -> bool:
        return all(ref.touching(j, self.ball) for j in self.jaws)

    def substep(self, w, ref):
        tr, p = self.trackers, self.p
        if ref.has("strike"):
            return
        if ref.touching(self.ball, ref.ground):
            return ref.fail("the ball touched the ground before home plate", x=round(float(w.pos("ball")[0]), 2))
        if tr["released"] is None:
            if ref.touching(self.ball, self.robot):           # still in your hand (or on you)
                tr["free"] = None
                return
            if tr["free"] is None:                            # the last contact was the step before: the release, if
                tr["free"] = [round(ref.time - w.m.opt.timestep, 4),     # it stays free for release_s
                              round(float(np.linalg.norm(w.vel("ball"))), 2), round(float(w.pos("ball")[2]), 3),
                              self.feet_on_plate(w, ref)]
            if ref.time - tr["free"][0] < p["release_s"] - 1e-9:
                return
            t, speed, height, feet = tr["free"]
            tr["released"] = t
            ref.metrics["release_speed_m_s"] = speed
            ref.metrics["release_height_m"] = height
            if t > p["release_limit_s"] + 1e-9:
                return ref.fail("the ball was not delivered within the pitch timer")
            if not feet:
                return ref.fail("no foot was on the pitcher's plate at the release")
            tr["plane"].update(w.pos("ball"))
            ref.stage("release", t=t, pivot_foot=feet)
            return
        if self._held(ref):
            return ref.fail("the ball was held again after the release")
        if (ref.touching(self.ball, self.not_arm)
                or (ref.time - tr["released"] > p["retouch_grace_s"] and ref.touching(self.ball, self.arm))):
            return ref.fail("the ball was touched after the release", parts=sorted(ref.parts_touching(self.ball)))
        x = tr["plane"].update(w.pos("ball"))
        if x is None:
            return
        y, z = float(x[1]), float(x[2])
        ref.metrics["cross_y_m"], ref.metrics["cross_z_m"] = round(y, 3), round(z, 3)
        ref.metrics["cross_speed_m_s"] = round(float(np.linalg.norm(w.vel("ball"))), 2)
        if abs(y) <= p["zone_width_m"] / 2 and p["zone_low_m"] <= z <= p["zone_high_m"]:
            if ref.stage("strike", y=round(y, 3), z=round(z, 3)):
                ref.succeed()
        else:
            ref.fail("a ball: it crossed the plate outside the strike zone", y=round(y, 3), z=round(z, 3))

    def step(self, w, ref):
        tr = self.trackers
        if tr["released"] is None and tr["free"] is None and w.t >= self.p["release_limit_s"] - 1e-9:
            ref.fail("the ball was not delivered within the pitch timer")

    def privileged(self, w):
        p, g = self.p, self.geometry()
        return {"ball": w.pos("ball").tolist(), "ball_velocity": w.vel("ball").tolist(),
                "held": w.held["right"] == "ball", "released_t": self.trackers.get("released"),
                "zone": {"x": g["zone_x"], "half_width": p["zone_width_m"] / 2, "low": p["zone_low_m"],
                         "high": p["zone_high_m"]},
                "feet_on_plate": self.feet_on_plate(w, w.ref)}
