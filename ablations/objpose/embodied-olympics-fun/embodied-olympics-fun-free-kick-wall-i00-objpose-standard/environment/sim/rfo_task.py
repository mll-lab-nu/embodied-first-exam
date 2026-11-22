"""Direct free kick (IFAB Law 13) from 20 m, past a wall of four free-standing training mannequins 9.15 m from the
ball: one kick of a size-5 ball at rest, over or around the wall, into the official goal."""
import math
import xml.etree.ElementTree as ET

import numpy as np

from rfo.referee import MouthPass
from rfo.scene import HITTABLE, OFFICIAL
from rfo.task import TaskBase
# A rigid mannequin (plastic silhouette on a rubber base)'s contact with the robot, the venue's fixtures and the other
# props (the ground keeps its own: rfo/world.py GROUND_SOLMIX): the stiff contact of the core's shells (rfo/world.py
# SHELL_CONTACT: solref 0.004 s, solimp 0.99 0.999 0.0005, from Embodied Olympics' weightlifting fix, a rigid prop on the
# robot's aluminium) with a solmix that wins over a default- contact geom; a ball (priority 1) keeps its own bounce.
# With MuJoCo's default soft contact (solref 0.02 1, solimp 0.9 0.95) it sank 69 mm into the palm pad and 31 mm into
# the pitch (stress test).
from rfo.world import SHELL_CONTACT as RIGID  # noqa: E402

BALL = OFFICIAL["football"]
GRASS = (0.16, 0.50, 0.20, 1)
WALL_RGBA = (0.95, 0.45, 0.08, 1)
BASE_RGBA = (0.12, 0.12, 0.13, 1)


def foot_contact(w, ref, ball, shin, foot_body, p):
    """The kicking surfaces of football (IFAB glossary: a kick is made with the foot or the ankle). Returns (legal,
    offender): legal is True when the ball touches a foot, or the lower leg's hull over the foot and no higher than
    instep_z_m above the ankle joint (the G1's lower-leg hull covers its instep and ankle); offender is the first
    contact higher up the leg, as (side, point in the foot's frame), else None."""
    legal = False
    for s in ("left", "right"):
        pts = ref.contact_points(ball, shin[s])
        if len(pts):
            b = foot_body[s]
            loc = (pts - w.d.xpos[b]) @ w.d.xmat[b].reshape(3, 3)
            bad = (loc[:, 2] > p["instep_z_m"]) | (loc[:, 0] < -p["heel_x_m"]) | (loc[:, 0] > p["toe_x_m"])
            if np.any(bad):
                return False, (s, [round(float(x), 3) for x in loc[int(np.flatnonzero(bad)[0])]])
            legal = True
    return legal, None


class Task(TaskBase):
    name = "free-kick-wall"
    title = "Football: direct free kick over or around the wall"
    category = "football-and-volleyball"
    robot = "unitree_g1"
    rulebook = ("IFAB Laws of the Game 2025/26: Law 1 (the goal 7.32 m x 2.44 m, posts and crossbar 12 cm wide; the "
                "penalty area 16.5 m deep), Law 2 (a size-5 ball: 68-70 cm round, 410-450 g), Law 10 (a goal: the "
                "whole ball passes over the goal line between the posts and under the crossbar), Law 13 (free kicks: "
                "a direct free kick, the ball stationary, in play when it is kicked and clearly moves; the kicker "
                "may not touch it again until it has touched another player; all opponents at least 9.15 m from the "
                "ball until it is in play) and the glossary (a kick: contact with the foot and/or the ankle)")
    deviations = [
        "Law 13 (the opponents): the defensive wall is {wall_n} free-standing training mannequins (FORZA senior "
        "free-kick mannequin size: {mannequin_h_m} m tall, {mannequin_w_m} m wide) on FORZA's {base_kg} kg rubber "
        "base, side by side with their faces {wall_distance_m} m from the ball, covering the near post. They are "
        "free bodies standing on the grass (rubber on grass, friction {base_mu}: an estimate): a ball that hits "
        "one can rock, slide or topple it. They do not jump, "
        "and there is no goalkeeper and no other player: opponents cannot be simulated otherwise.",
        "Law 13 (one kick): the referee takes every contact of a foot with the ball within {kick_max_s} s of the "
        "first as the one kick; a later contact by the kicker is a second touch. A referee's eye is replaced by "
        "this number.",
        "Glossary (a kick is made with the foot or the ankle): the foot is the robot's ankle-roll link; its "
        "lower-leg collision hull covers the instep and the ankle, so a contact with that hull counts as the foot "
        "where it lies over the foot (from {heel_x_m} m behind to {toe_x_m} m ahead of the ankle joint) and no "
        "more than {instep_z_m} m above the ankle joint; higher up it is the shin, which may not touch the ball.",
        "Law 1: only the attacked end of the field is there (the penalty area, the goal area and the arc painted); "
        "the goal's net is a rigid cage {goal_depth_m} m deep; no wind. The free kick's spot ({distance_m} m from "
        "the goal line, {offset_m} m to the right of the goal's centre) is this benchmark's choice: outside the "
        "penalty area, where a direct free kick is taken, and inside the range of the robot's measured hard kicks "
        "(10 to 16 m/s; the ball has to roll or fly about 21 m). The kicker starts at the ball, without a run-up.",
    ]
    time_limit_s = 30.0
    start = (0.0, 0.0, 0.0)
    stages = ["kick", "goal"]
    fall_z = 0.35
    params = dict(distance_m=20.0, offset_m=4.0, ball_ahead_m=0.32, ball_side_m=-0.13, goal_width_m=7.32,
                  goal_height_m=2.44, post_m=0.12,
                  goal_depth_m=2.0, wall_distance_m=9.15, wall_n=4, wall_cover_m=0.25, mannequin_h_m=1.75,
                  mannequin_w_m=0.50, mannequin_kg=3.0, base_kg=13.0, base_w_m=0.50, base_d_m=0.40, base_h_m=0.05,
                  base_mu=0.8, kick_max_s=0.15, rest_speed_m_s=0.1, rest_s=1.0, instep_z_m=0.12, heel_x_m=0.08,
                  toe_x_m=0.15, fall_z_m=0.35, fall_after_kick_fails=0)

    sentence = ("Take a direct free kick: with one kick of a foot, send the ball over or around the wall of "
                "mannequins into the official goal {distance_m} m away.")
    rules = ("A size-5 football (0.22 m across, 0.43 kg, in air) lies at rest on the grass in front of your right "
             "foot: its centre {ball_ahead_m} m ahead of your pelvis and {ball_side_m} m to your left (negative: "
             "to the "
             "right). The goal line is {distance_m} m beyond the ball, square to the direction you face; the "
             "goal is {goal_width_m} m wide between the posts and {goal_height_m} m high under the crossbar (posts "
             "and bar {post_m} m thick), its centre {offset_m} m to the left of the line straight ahead through the "
             "ball. A wall of {wall_n} training mannequins stands between the ball and the goal, side by side, their "
             "faces {wall_distance_m} m from the ball, covering the near (right-hand) post (its outer edge "
             "{wall_cover_m} m outside the line from the ball to that post's inner edge): each {mannequin_h_m} m "
             "tall and {mannequin_w_m} m wide, {mannequin_kg} kg, standing free on a {base_kg} kg rubber base "
             "({base_w_m} m wide, {base_d_m} m deep, {base_h_m} m high), so that a ball can knock one over. "
             "There is no goalkeeper. "
             "The kick is a contact of a foot of yours with the ball: the foot below the ankle, or your lower leg "
             "where it lies over the foot and no more than {instep_z_m} m above the ankle joint; every such contact "
             "within {kick_max_s} s of the first belongs to the one kick. You succeed at the moment the whole ball "
             "is over the goal line between the posts and under the bar; it may touch the mannequins, the posts, "
             "the bar and the ground on the way. You fail if any other part of you touches the ball at any time, if "
             "a foot touches the ball again later than {kick_max_s} s after the first contact (a second touch), if "
             "the ball is not moving towards the goal line at the end of the kick, if the whole ball crosses the goal "
             "line outside the goal, if after the kick the ball has been slower than {rest_speed_m_s} m/s for "
             "{rest_s} s, if you fall before the kick (your pelvis lower than {fall_z_m} m above the ground, or "
             "any part of you other than the feet on the ground), or after {time_limit_s} s. A fall after the kick "
             "does not end the attempt (the Laws judge the ball once it is in play, not the kicker; the setting "
             "fall_after_kick_fails = {fall_after_kick_fails}, where 1 would make any fall a failure).")
    venue = ("You stand facing the goal line (+x) right behind the ball, ready to kick it with the right foot: its "
             "centre is {ball_ahead_m} m ahead of your pelvis and {ball_side_m} m to your left. The goal's centre "
             "is {distance_m} m "
             "beyond the ball and {offset_m} m to your left; the near post is almost straight ahead, the far post "
             "to the left. The wall stands {wall_distance_m} m from the ball across the way to the near post; the "
             "penalty area, the goal area and the arc are painted on the grass.")
    difficulty = ("The wall hides the near half of the goal: the ball has to be driven past or over its end along a "
                  "narrow line, or round it into the far half, some 21 m, which needs well over 6 m/s off the foot "
                  "(over the wall about 11 m/s). The robot has no kicking skill: Embodied Olympics' balanced model-based "
                  "kick sends the ball off at about 4 m/s, and a swing hard enough (10 to 16 m/s measured) throws the "
                  "33 kg body round on its standing foot.")

    def configure(self, params):
        super().configure(params)
        self.fall_z = self.p["fall_z_m"]

    # ------------------------------------------------------------------ geometry
    def geometry(self):
        p = self.p
        bx, by = p["ball_ahead_m"], p["ball_side_m"]
        gx, gy = bx + p["distance_m"], by + p["offset_m"]
        near = gy - p["goal_width_m"] / 2                      # the near post's inner edge (y)
        a_near = math.atan2(near - by, p["distance_m"])       # the line from the ball to it
        r = p["wall_distance_m"] + p["base_d_m"] / 2          # the mannequins' centres
        # side by side: neighbouring bases touch at their inner corners (spaced by the base's width on the arc through
        # their front faces, r - depth / 2); spaced on the centres' arc instead, the corners overlapped by 11 mm at the
        # start and the wall shoved itself apart (stress test)
        step = max(p["mannequin_w_m"], p["base_w_m"]) / (r - p["base_d_m"] / 2)
        a0 = a_near - p["wall_cover_m"] / p["wall_distance_m"]  # the outer mannequin's right edge, past that line
        wall = []
        for i in range(p["wall_n"]):
            a = a0 + step * (i + 0.5)
            wall.append((bx + r * math.cos(a), by + r * math.sin(a), a))
        return dict(ball_x=bx, ball_y=by, goal_x=gx, goal_y=gy, half=p["goal_width_m"] / 2, post_r=p["post_m"] / 2,
                    wall=wall)

    def build(self, sc):
        p, g = self.p, self.geometry()
        gx, gy, bx = g["goal_x"], g["goal_y"], g["ball_x"]
        self.fall_z = p["fall_z_m"]
        sc.box("pitch", (gx / 2 - 2.0, gy, 0.0003), (gx / 2 + 6.0, 26.0, 0.0003), rgba=GRASS)
        sc.line("goal_line", (gx, gy - 26.0), (gx, gy + 26.0), width=p["post_m"])
        for name, depth, half in (("penalty_area", 16.5, 20.16), ("goal_area", 5.5, 9.16)):   # Law 1
            sc.line(f"{name}_front", (gx - depth, gy - half), (gx - depth, gy + half), width=0.12)
            for s in (1, -1):
                sc.line(f"{name}_side{s}", (gx - depth, gy + s * half), (gx, gy + s * half), width=0.12)
        sc.disc("penalty_mark", (gx - 11.0, gy), 0.11, rgba=(1, 1, 1, 1))
        a0 = math.acos((16.5 - 11.0) / 9.15)                  # the penalty arc, outside the area
        n = 12
        for i in range(n):
            a, b = math.pi - a0 + 2 * a0 * i / n, math.pi - a0 + 2 * a0 * (i + 1) / n
            sc.line(f"arc{i}", (gx - 11.0 + 9.15 * math.cos(a), gy + 9.15 * math.sin(a)),
                    (gx - 11.0 + 9.15 * math.cos(b), gy + 9.15 * math.sin(b)), width=0.12)
        self.goal = sc.goal("goal", gx, gy, width=p["goal_width_m"], height=p["goal_height_m"], depth=p["goal_depth_m"],
                            post=g["post_r"])
        # The wall: FORZA free-kick mannequins (forza.com: senior 175 cm; the full-size rubber base 13 kg). Each is one
        # free body: the base (a rubber slab; rubber on grass mu 0.8, an estimate) and the silhouette (a board with a
        # head; its mass, about 3 kg, is an estimate: the listing gives none) fixed on it. Hittable: the ball and
        # the robot meet them.
        bh, h = p["base_h_m"], p["mannequin_h_m"]
        for i, (x, y, a) in enumerate(g["wall"]):
            b = sc.body(f"mannequin{i}", (x, y, 0.0), quat=(math.cos(a / 2), 0, 0, math.sin(a / 2)), free=True)
            sc.geom(b, f"mannequin{i}_base", type="box", pos=(0, 0, bh / 2),
                    size=(p["base_d_m"] / 2, p["base_w_m"] / 2, bh / 2),
                    mass=p["base_kg"], rgba=BASE_RGBA, friction=(p["base_mu"], 0.005, 0.0001), **HITTABLE, **RIGID)
            body_h = h - 0.25 - bh                              # the board from the base to the shoulders
            sc.geom(b, f"mannequin{i}_board", type="box", pos=(0, 0, bh + body_h / 2),
                    size=(0.015, p["mannequin_w_m"] / 2, body_h / 2), mass=p["mannequin_kg"] * 0.85, rgba=WALL_RGBA,
                    **HITTABLE, **RIGID)
            sc.geom(b, f"mannequin{i}_head", type="capsule", fromto=(0, 0, h - 0.17, 0, 0, h - 0.08), size=(0.08,),
                    mass=p["mannequin_kg"] * 0.15, rgba=WALL_RGBA, **HITTABLE, **RIGID)
        sc.ball("ball", "football", (bx, g["ball_y"], BALL["radius"]))
        sc.camera("venue", (-4.0, -5.0, 3.5), (bx + 9.0, 2.0, 0.8), fovy=60)

    def reset(self, w):
        g = self.geometry()
        w.put("ball", (g["ball_x"], g["ball_y"], BALL["radius"]))
        for i, (x, y, a) in enumerate(g["wall"]):
            w.put(f"mannequin{i}", (x, y, 0.0), quat=(math.cos(a / 2), 0, 0, math.sin(a / 2)))

    # ------------------------------------------------------------------ the referee
    def referee_reset(self, w, ref):
        p, g = self.p, self.geometry()
        self.fall_rule = True                                  # (switched off after the kick: see substep)
        self.ball = ref.geoms(body="ball")
        self.feet = ref.part("feet")
        self.shin = {s: ref.part(f"{s}_shin") for s in ("left", "right")}
        self.foot_body = {s: w.m.body(f"{s}_ankle_roll_link").id for s in ("left", "right")}
        self.other = ref.robot_mask & ~self.feet & ~ref.part("shins")
        self.trackers = {
            "mouth": MouthPass((g["goal_x"] + g["post_r"], g["goal_y"]), 0.0, g["half"], 0.0, p["goal_height_m"],
                               BALL["radius"]),
            "kick_t": None, "forward": None,
        }

    def substep(self, w, ref):
        p, tr = self.p, self.trackers
        if ref.touching(self.ball, self.other):
            return ref.fail("the ball was touched by something other than a foot",
                            parts=sorted(ref.parts_touching(self.ball)))
        legal, bad = foot_contact(w, ref, self.ball, self.shin, self.foot_body, p)
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
                return ref.fail("second touch of the ball", after_s=round(ref.time - tr["kick_t"], 3))
        if tr["kick_t"] is not None and tr["forward"] is None and ref.time - tr["kick_t"] >= p["kick_max_s"]:
            v = w.vel("ball")
            tr["forward"] = bool(v[0] > 0.0)
            ref.metrics["kick_speed_m_s"] = round(float(np.linalg.norm(v)), 2)
            if not tr["forward"]:
                return ref.fail("the ball was not kicked forward")
        hit = tr["mouth"].update(w.pos("ball"))
        if hit is not None:
            b = w.pos("ball")
            ref.metrics["cross_y_m"] = round(float(b[1] - self.geometry()["goal_y"]), 3)   # from the goal's centre
            ref.metrics["cross_z_m"] = round(float(b[2]), 3)
        if hit == "in":
            if ref.stage("goal"):
                ref.succeed()
        elif hit == "wide":
            ref.fail("the ball crossed the goal line outside the goal")

    def step(self, w, ref):
        p = self.p
        if not self.fall_rule and w.pelvis()[2] < self.fall_z:
            ref.metrics["fell_after_kick"] = 1
        ref.metrics["ball_x_m"] = round(float(w.pos("ball")[0]), 3)
        slow = float(np.linalg.norm(w.vel("ball"))) < p["rest_speed_m_s"]
        if ref.has("kick") and ref.hold("rest", slow, p["rest_s"]):
            ref.fail("the ball came to rest without a goal")

    def privileged(self, w):
        g = self.geometry()
        return {"ball": w.pos("ball").tolist(), "ball_velocity": w.vel("ball").tolist(), "goal": self.goal,
                "wall": [w.pos(f"mannequin{i}").tolist() for i in range(self.p["wall_n"])],
                "wall_at_start": [list(x) for x in g["wall"]]}
