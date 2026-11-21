"""Rugby union conversion (World Rugby Law 8): a place kick of a size-5 rugby ball standing on a kicking tee, from the
5-metre line straight in front of the posts, over the 3.0 m crossbar between the posts 5.6 m apart."""
import math
import xml.etree.ElementTree as ET

import numpy as np

from rfo.referee import Crossing
from rfo.scene import AIR, HITTABLE, VISUAL, bounce_solref
from rfo.task import TaskBase
# A rigid kicking tee (moulded plastic)'s contact with the robot, the venue's fixtures and the other props (the ground
# keeps its own: rfo/world.py GROUND_SOLMIX): the stiff contact of the core's shells (rfo/world.py SHELL_CONTACT:
# solref 0.004 s, solimp 0.99 0.999 0.0005, from Embodied Olympics' weightlifting fix, a rigid prop on the robot's
# aluminium) with a solmix that wins over a default-contact geom; a ball (priority 1) keeps its own bounce. With
# MuJoCo's default soft contact (solref 0.02 1, solimp 0.9 0.95) it sank 36 mm into the palm pad and 34 mm into the
# pitch (stress test).
from rfo.world import SHELL_CONTACT as RIGID  # noqa: E402

GRASS = (0.16, 0.50, 0.20, 1)
POST_RGBA = (0.97, 0.97, 0.97, 1)
PAD_RGBA = (0.10, 0.25, 0.60, 1)
BALL_RGBA = (0.93, 0.90, 0.80, 1)
TEE_RGBA = (0.95, 0.85, 0.10, 1)

# The ball (World Rugby Law 2 / Regulation 12): oval, 280-300 mm long, 740-770 mm round end to end, 580-620 mm round
# across, 410-460 g, 65.71-68.75 kPa: a prolate spheroid, semi-axes 0.145 m (along) and 0.0955 m (across: 600 mm
# round), 0.435 kg, a thin shell (its inertia below). Drag: Alam et al. (RMIT wind tunnel, 2008/2010) measured C_d
# 0.18 end-on and about 0.60 side-on; MuJoCo's ellipsoid fluid model has one blunt-drag coefficient over the projected
# area, set from the side-on value (C_d / 2, as scene.OFFICIAL's balls): end-on the model's drag is then higher than
# the measured one. Bounce: no rebound test is published for a rugby ball; it is inflated to the pressure of a size-5
# football (IFAB Law 2: 0.6-1.1 atm) and gets the football's FIFA-test restitution, 0.85.
BALL = dict(a=0.145, b=0.0955, mass=0.435, bounce=0.85, drag=0.60, roll=0.006)


def shell_inertia(a: float, b: float, mass: float, n: int = 400) -> tuple[float, float]:
    """The principal moments (across, along) of a thin prolate spheroidal shell of uniform areal density: a surface
    integral over the polar angle (deterministic quadrature)."""
    t = (np.arange(n) + 0.5) * math.pi / n
    z, r = a * np.cos(t), b * np.sin(t)
    ds = np.sqrt((a * np.sin(t)) ** 2 + (b * np.cos(t)) ** 2) * (math.pi / n)
    dA = 2 * math.pi * r * ds
    A = float(dA.sum())
    i_along = float((dA * r ** 2).sum()) / A * mass
    i_across = float((dA * (r ** 2 / 2 + z ** 2)).sum()) / A * mass
    return i_across, i_along


class Task(TaskBase):
    name = "rugby-conversion"
    title = "Rugby: conversion kick over the crossbar"
    category = "football-and-volleyball"
    robot = "unitree_g1"
    rulebook = ("World Rugby Laws of the Game (2025): Law 1 (the goal posts 5.6 m apart, the crossbar's top edge 3.0 m "
                "above the ground, the posts at least 3.4 m high, padding on the posts; the 5-metre line), Law 2 (the "
                "ball: oval, 280-300 mm long, 740-770 mm round end to end, 580-620 mm round across, 410-460 g), Law 8 "
                "(8.4: a goal is scored when the ball is kicked over the crossbar and between the goal posts without "
                "first touching a team-mate or the ground; 8.7: a conversion is a place-kick or a drop-kick; 8.8: the "
                "kick is taken on a line through the place where the try was awarded, parallel to the touchlines, the "
                "ball on the ground or on a kicking tee, within 60 seconds)")
    deviations = [
        "Law 8.8 (where): the try is taken as awarded under the posts, and the conversion is kicked from the "
        "5-metre line ({kick_distance_m} m from the goal line) on that line: a choice the law allows, made for this "
        "robot, whose measured hard kicks leave the foot at 7 to 11 m/s (a professional's at 25 m/s from 20-40 m). "
        "A ball over the bar from there must still rise more than 3 m within 5 m.",
        "Law 2 (the ball's behaviour): a rigid prolate spheroid (a thin shell's mass distribution); its drag in air "
        "from wind-tunnel measurements (side-on), its bounce a stand-in (no published rebound test for a rugby ball: "
        "a size-5 football's, at the same inflation pressure). It does not deform.",
        "Law 8.8 (the tee): a low plastic kicking tee ({tee_height_m} m to the cup), a free body standing on the "
        "grass; the ball stands upright in its cup. No placer.",
        "Law 8.4 (between the posts): judged as the ball's centre passing the goal line's vertical plane above the "
        "crossbar's top and between the posts' inner faces extended upwards; a ball that hits the bar and goes on "
        "over counts, one that comes back does not. A touch judge's flag is replaced by this geometry.",
        "Law 1: only the goal end of the field is there; the posts are {post_height_m} m high; no wind, no "
        "opponents (a conversion is not charged down after the kicker's first movement in this setting).",
    ]
    time_limit_s = 60.0
    start = (0.0, 0.0, 0.0)
    stages = ["kick", "goal"]
    fall_z = 0.35
    params = dict(kick_distance_m=5.0, ball_ahead_m=0.30, ball_side_m=-0.17, posts_gap_m=5.6, crossbar_m=3.0,
                  post_height_m=8.0,
                  post_diameter_m=0.12, pad_radius_m=0.25, pad_height_m=2.0, tee_height_m=0.06, tee_kg=0.08,
                  kick_max_s=0.15, beyond_m=0.4, instep_z_m=0.12, heel_x_m=0.08, toe_x_m=0.15, fall_z_m=0.35,
                  fall_after_kick_fails=0)

    sentence = ("Kick a conversion: with one place kick of a foot, send the rugby ball standing on its tee over the "
                "crossbar and between the posts.")
    rules = ("A size-5 rugby ball (an oval 0.29 m long and 0.19 m across, 0.435 kg, in air) stands upright on a "
             "kicking tee ({tee_height_m} m high to its cup, {tee_kg} kg, standing free) on the grass in front of "
             "your right foot, on the 5-metre "
             "line: its centre {ball_ahead_m} m ahead of your pelvis and {ball_side_m} m to your left (negative: to "
             "the right). The goal line is {kick_distance_m} m beyond the ball, square to the direction you face; "
             "the goal posts stand on it, {posts_gap_m} m apart between their inner faces, centred on the line "
             "through the ball square to the goal line, {post_height_m} m high and {post_diameter_m} m thick, "
             "padded up to "
             "{pad_height_m} m (the padding {pad_radius_m} m round each post's axis); the crossbar's top edge is "
             "{crossbar_m} m above the ground. The kick is a contact of a "
             "foot of yours with the ball: the foot below the ankle, or your lower leg where it lies over the foot "
             "(from {heel_x_m} m behind to {toe_x_m} m ahead of the ankle joint) and no more than {instep_z_m} m "
             "above the ankle joint; every such contact within {kick_max_s} s of the "
             "first belongs to the one kick. You score when the ball's centre passes the goal line's vertical plane "
             "above the crossbar's top edge and between the posts' inner faces (extended upwards), and goes on "
             "{beyond_m} m beyond it; it may touch the bar or a post on the way. You fail if any other part of you "
             "touches the ball at any time, if you touch it again after the kick, if the ball touches the ground "
             "(not the tee) after the kick before it has scored, if it passes the goal line's plane under the bar "
             "or outside the posts, if you fall before the kick (your pelvis lower than {fall_z_m} m above the "
             "ground, or any part of you other than the feet on the ground), or after {time_limit_s} s. A fall after "
             "the kick does not end the attempt (Law 8 judges the ball, not the kicker; the setting "
             "fall_after_kick_fails = {fall_after_kick_fails}, where 1 would make any fall a failure).")
    venue = ("You stand facing the posts (+x) right behind the ball on its tee, ready to kick it with the right "
             "foot (its centre {ball_ahead_m} m ahead of your pelvis, {ball_side_m} m to your left); the posts are "
             "{kick_distance_m} m beyond the ball, one each side of the line through the ball, {posts_gap_m} m "
             "apart. The 5-metre line, the goal line and the in-goal are painted on the grass.")
    difficulty = ("To clear a 3 m bar 5 m away the ball must leave the foot at about 10 m/s or more, rising at 45 to "
                  "60 degrees: a hard, steep kick under the ball's lower end. The robot has no kicking skill; a hard "
                  "swing on one leg throws the 33 kg body round, and the robot must stay on its feet until the ball "
                  "has scored.")

    def configure(self, params):
        super().configure(params)
        self.fall_z = self.p["fall_z_m"]

    # ------------------------------------------------------------------ geometry
    def geometry(self):
        p = self.p
        bx, by = p["ball_ahead_m"], p["ball_side_m"]
        return dict(ball_x=bx, ball_y=by, goal_x=bx + p["kick_distance_m"], half=p["posts_gap_m"] / 2,
                    post_r=p["post_diameter_m"] / 2, bar_z=p["crossbar_m"])

    def _tee_rest(self):
        """The ball's centre height standing upright in the tee's cup: the cup's six capsules (their middles at
        RING_R cos(0.35 * 60 deg) from the axis, at the cup's height, radius TUBE) touch the ellipsoid; solved by
        bisection (deterministic)."""
        a, b = BALL["a"], BALL["b"]
        R = self.RING_R * math.cos(0.35 * 2 * math.pi / 6)   # the chords' middles
        h, tube = self.p["tee_height_m"], self.TUBE
        th = np.linspace(math.pi / 2, math.pi, 2001)
        ex, ez = b * np.sin(th), a * np.cos(th)          # the ellipse's lower half (x >= 0)

        def gap(zc):                                      # signed: negative with the ring's centreline inside the ball
            dist = float(np.min(np.hypot(ex - R, ez + zc - h)))
            inside = (R / b) ** 2 + ((h - zc) / a) ** 2 < 1.0
            return (-dist if inside else dist) - tube
        lo, hi = h, h + a + 0.05
        for _ in range(60):
            mid = (lo + hi) / 2
            lo, hi = (lo, mid) if gap(mid) > 0 else (mid, hi)
        return hi

    RING_R, TUBE = 0.055, 0.006                # the cup: 0.11 m across (an estimate; a narrower ring lets the upright
                                               # ball creep and topple within a minute)

    def build(self, sc):
        p, g = self.p, self.geometry()
        gx, bx, half, by = g["goal_x"], g["ball_x"], g["half"], g["ball_y"]
        self.fall_z = p["fall_z_m"]
        sc.box("pitch", (gx / 2, 0, 0.0003), (gx / 2 + 8.0, 20.0, 0.0003), rgba=GRASS)
        sc.line("goal_line", (gx, -20.0), (gx, 20.0), width=0.10)
        sc.line("dead_ball_line", (gx + 10.0, -20.0), (gx + 10.0, 20.0), width=0.10)
        for i in range(8):                                    # the 5-metre line: dashes
            y0 = -14.0 + 4.0 * i
            sc.line(f"five_m{i}", (gx - 5.0, y0), (gx - 5.0, y0 + 1.0), width=0.10)
        # the posts and the crossbar (Law 1), static: the posts' inner faces 5.6 m apart, the bar's top at 3.0 m
        pr = g["post_r"]
        for s, tag in ((1, "L"), (-1, "R")):
            y = by + s * (half + pr)
            sc.geom(sc.wb, f"post{tag}", type="cylinder", pos=(gx, y, p["post_height_m"] / 2),
                    size=(pr, p["post_height_m"] / 2), rgba=POST_RGBA, **HITTABLE)
            sc.geom(sc.wb, f"pad{tag}", type="cylinder", pos=(gx, y, p["pad_height_m"] / 2),
                    size=(p["pad_radius_m"], p["pad_height_m"] / 2), rgba=PAD_RGBA, solref="0.02 1", **HITTABLE)
        sc.geom(sc.wb, "crossbar", type="capsule", fromto=(gx, by - half - pr, p["crossbar_m"] - pr, gx, by + half + pr,
                                                         p["crossbar_m"] - pr), size=(pr,), rgba=POST_RGBA, **HITTABLE)
        # the kicking tee: a free plastic body, a base disc, a stem and a cup of six short capsules on a ring
        t = sc.body("tee", (bx, g["ball_y"], 0.0), free=True)
        h = p["tee_height_m"]
        sc.geom(t, "tee_base", type="cylinder", pos=(0, 0, 0.005), size=(0.06, 0.005), mass=p["tee_kg"] * 0.6,
                rgba=TEE_RGBA, friction=(0.8, 0.005, 0.0001), **HITTABLE, **RIGID)
        sc.geom(t, "tee_stem", type="cylinder", pos=(0, 0, (h - 0.02) / 2 + 0.005), size=(0.015, (h - 0.03) / 2),
                mass=p["tee_kg"] * 0.2, rgba=TEE_RGBA, **HITTABLE, **RIGID)
        n = 6
        for i in range(n):
            a0, a1 = 2 * math.pi * (i + 0.15) / n, 2 * math.pi * (i + 0.85) / n
            sc.geom(t, f"tee_cup{i}", type="capsule",
                    fromto=(self.RING_R * math.cos(a0), self.RING_R * math.sin(a0), h,
                            self.RING_R * math.cos(a1), self.RING_R * math.sin(a1), h),
                    size=(self.TUBE,), mass=p["tee_kg"] * 0.2 / n, rgba=TEE_RGBA, friction=(0.8, 0.005, 0.0001),
                    **HITTABLE, **RIGID)
        zc = self._tee_rest()
        # the ball: an ellipsoid, the shell's inertia; its contact parameters win (priority), as scene.ball's
        bb = sc.body("ball", (bx, g["ball_y"], zc), free=True)
        i_across, i_along = shell_inertia(BALL["a"], BALL["b"], BALL["mass"])
        ET.SubElement(bb, "inertial", pos="0 0 0", mass=f"{BALL['mass']:g}",
                      diaginertia=f"{i_across:.8g} {i_across:.8g} {i_along:.8g}")
        sc.geom(bb, "ball", type="ellipsoid", size=(BALL["b"], BALL["b"], BALL["a"]), rgba=BALL_RGBA, condim=6,
                priority=1, friction=(0.7, 0.003, BALL["roll"]), solref=bounce_solref(BALL["bounce"]),
                solimp="0.95 0.99 0.001", fluidshape="ellipsoid", fluidcoef=(BALL["drag"] / 2, 0.25, 0.0, 1.0, 1.0),
                **HITTABLE)
        sc.geom(bb, "ball_seam", type="ellipsoid", size=(BALL["b"] + 0.0008, 0.004, BALL["a"] + 0.0008),
                rgba=(0.75, 0.10, 0.10, 1), **VISUAL)
        sc.camera("venue", (-3.0, -5.5, 2.6), (bx + 3.0, 0.0, 1.4), fovy=60)
        self.air = AIR

    def reset(self, w):
        g = self.geometry()
        w.put("tee", (g["ball_x"], g["ball_y"], 0.0))
        w.put("ball", (g["ball_x"], g["ball_y"], self._tee_rest()))

    # ------------------------------------------------------------------ the referee
    def referee_reset(self, w, ref):
        p, g = self.p, self.geometry()
        self.fall_rule = True                                  # (switched off after the kick: see substep)
        self.ball = ref.geoms(body="ball")
        self.feet = ref.part("feet")
        self.shin = {s: ref.part(f"{s}_shin") for s in ("left", "right")}
        self.foot_body = {s: w.m.body(f"{s}_ankle_roll_link").id for s in ("left", "right")}
        self.other = ref.robot_mask & ~self.feet & ~ref.part("shins")
        self.robot = ref.robot_mask
        self.trackers = {"plane": Crossing((1, 0, 0), g["goal_x"], direction=0), "kick_t": None, "over": False}

    def _foot_contact(self, w, ref):
        """(legal, offender): see free-kick-wall (the IFAB glossary's foot or ankle; the same instep rule)."""
        p = self.p
        legal = False
        for s in ("left", "right"):
            pts = ref.contact_points(self.ball, self.shin[s])
            if len(pts):
                b = self.foot_body[s]
                loc = (pts - w.d.xpos[b]) @ w.d.xmat[b].reshape(3, 3)
                bad = (loc[:, 2] > p["instep_z_m"]) | (loc[:, 0] < -p["heel_x_m"]) | (loc[:, 0] > p["toe_x_m"])
                if np.any(bad):
                    return False, (s, [round(float(x), 3) for x in loc[int(np.flatnonzero(bad)[0])]])
                legal = True
        return legal, None

    def substep(self, w, ref):
        p, g, tr = self.p, self.geometry(), self.trackers
        if ref.touching(self.ball, self.other):
            return ref.fail("the ball was touched by something other than a foot",
                            parts=sorted(ref.parts_touching(self.ball)))
        legal, bad = self._foot_contact(w, ref)
        if bad is not None:
            return ref.fail("the ball was touched by something other than a foot", parts=[f"{bad[0]}_shin"],
                            at_foot_frame=bad[1])
        if legal or ref.touching(self.ball, self.feet):
            if tr["kick_t"] is None:
                tr["kick_t"] = ref.time
                ref.stage("kick", parts=sorted(ref.parts_touching(self.ball)))
                if not p["fall_after_kick_fails"]:
                    self.fall_rule = False                     # the Laws judge the ball from here on, not the kicker
            elif ref.time - tr["kick_t"] > p["kick_max_s"]:
                return ref.fail("the ball was touched again after the kick", after_s=round(ref.time - tr["kick_t"], 3))
        if tr["kick_t"] is not None and ref.touching(self.ball, ref.ground):
            return ref.fail("the ball touched the ground before it scored")
        b = w.pos("ball")
        x = tr["plane"].update(b)
        if x is not None:
            if b[0] >= g["goal_x"]:                            # forwards through the goal line's plane
                ref.metrics["plane_z_m"] = round(float(x[2]), 3)
                ref.metrics["plane_y_m"] = round(float(x[1]), 3)
                if x[2] >= g["bar_z"] and abs(x[1] - g["ball_y"]) <= g["half"]:
                    tr["over"] = True
                else:
                    return ref.fail("the ball passed under the crossbar or outside the posts")
            else:
                tr["over"] = False                             # it came back
        if tr["over"] and b[0] >= g["goal_x"] + p["beyond_m"]:
            if ref.stage("goal"):
                ref.succeed()

    def step(self, w, ref):
        if not self.fall_rule and w.pelvis()[2] < self.fall_z:
            ref.metrics["fell_after_kick"] = 1
        b = w.pos("ball")
        ref.metrics["ball_max_z_m"] = round(max(ref.metrics.get("ball_max_z_m", 0.0), float(b[2])), 3)

    def privileged(self, w):
        g = self.geometry()
        return {"ball": w.pos("ball").tolist(), "ball_quat": w.d.xquat[w.m.body("ball").id].tolist(),
                "ball_velocity": w.vel("ball").tolist(), "tee": w.pos("tee").tolist(), "goal_line_x": g["goal_x"],
                "posts_inner_y": [g["ball_y"] + g["half"], g["ball_y"] - g["half"]], "crossbar_top_z": g["bar_z"],
                "ball_semi_axes": [BALL["b"], BALL["b"], BALL["a"]]}
