"""Penalty kick (IFAB Law 14) on the official goal: one kick of a size-5 ball from the penalty mark, 11 m out, past a
goalkeeper dummy that moves along the goal line."""
import math
import xml.etree.ElementTree as ET

import numpy as np

from rfo.referee import MouthPass
from rfo.scene import OFFICIAL
from rfo.task import TaskBase

BALL = OFFICIAL["football"]
GRASS = (0.16, 0.50, 0.20, 1)


class Task(TaskBase):
    name = "penalty-kick"
    title = "Football: penalty kick"
    category = "football-and-volleyball"
    robot = "unitree_g1"
    rulebook = ("IFAB Laws of the Game 2025/26: Law 1 (the goal 7.32 m x 2.44 m with posts and crossbar 12 cm wide, the "
                "penalty mark 11 m from the goal line, the penalty area, the goal area and the penalty arc), Law 2 (a "
                "size-5 ball: 68-70 cm round, 410-450 g), Law 14 (the penalty kick: the ball at rest on the mark, kicked "
                "forward, the goalkeeper on the goal line between the posts until the kick), Law 10 (kicks from the "
                "penalty mark: one kick, which is over when the ball stops moving or goes out of play; the kicker may "
                "not play the ball a second time) and the glossary (a kick is a contact with the foot or the ankle)")
    deviations = [
        "Law 14 (the goalkeeper): the goalkeeper is a dummy, a rigid board {keeper_height_m} m high and "
        "{keeper_width_m} m wide standing on the goal line. It starts at the centre and, from {keeper_delay_s} s after "
        "the kick, slides along the line at up to {keeper_speed_m_s} m/s towards the point where the ball's velocity "
        "of that moment would take it over the goal line; it stays between the posts and neither dives, jumps nor "
        "uses hands. An opponent cannot be simulated otherwise.",
        "Law 14 (the kick): the referee takes every contact of a foot with the ball within {kick_max_s} s of the "
        "first as the one kick; any later contact is a second touch. A referee's eye is replaced by this number.",
        "Law 14 says the ball is kicked; the Laws do not name the part of the leg. Here the kick is made with a "
        "foot or an ankle (the parts below the shin): a contact of the ball with a shin or any other part is a "
        "failure.",
        "Law 1: only the goal end of the field is there (the penalty area, the goal area, the mark and the arc are "
        "painted); the goal's net is a rigid cage {goal_depth_m} m deep; there is no wind and no other player.",
    ]
    time_limit_s = 15.0
    start = (0.0, 0.0, 0.0)
    stages = ["kick", "goal"]
    fall_z = 0.35
    params = dict(goal_width_m=7.32, goal_height_m=2.44, post_m=0.12, goal_depth_m=2.0, mark_distance_m=11.0,
                  run_up_m=3.0, keeper_height_m=1.9, keeper_width_m=0.6, keeper_depth_m=0.3, keeper_delay_s=0.25,
                  keeper_speed_m_s=3.0, kick_max_s=0.15, rest_speed_m_s=0.1, rest_s=1.0, fall_z_m=0.35)

    sentence = ("Take a penalty kick: with one kick of a foot, send the ball that lies on the penalty mark into the "
                "official goal 11 m away, past the goalkeeper dummy.")
    rules = ("A size-5 football (0.22 m across, 0.43 kg, in air) lies at rest on the penalty mark, {run_up_m} m "
             "straight ahead of you; the goal line is {mark_distance_m} m beyond the mark. The goal is "
             "{goal_width_m} m wide between the posts and {goal_height_m} m high under the crossbar (posts and bar "
             "{post_m} m thick), centred on the line through you and the mark. A goalkeeper dummy, a board "
             "{keeper_height_m} m high, {keeper_width_m} m wide and {keeper_depth_m} m thick, stands on the goal line "
             "at the centre of the goal; from {keeper_delay_s} s after your kick it slides along the goal line at up "
             "to {keeper_speed_m_s} m/s towards the point where the ball, going on as it moves at that moment, would "
             "cross the line, and it blocks the ball. The kick is a contact of a foot or an ankle of yours with the "
             "ball (the parts below the shin); every such contact within {kick_max_s} s of the first belongs to the "
             "one kick. You succeed at the moment the whole ball is over the goal line between the posts and under "
             "the bar; it may touch the posts, the bar, the dummy and the ground on the way. You fail if any other "
             "part of you touches the ball at any time, if a foot touches the ball again later than {kick_max_s} s "
             "after the first contact (a second touch), if the ball is not moving towards the goal line at the end "
             "of the kick, if the whole ball crosses the goal line outside the goal, if after the kick the ball has "
             "been slower than {rest_speed_m_s} m/s for {rest_s} s, if you fall (your pelvis lower than {fall_z_m} m "
             "above the ground, or any part of you other than the feet on the ground), or after {time_limit_s} s.")
    venue = ("You stand facing the goal (+x), {run_up_m} m behind the penalty mark, on the line through the mark and "
             "the centre of the goal. The ball lies on the mark. The penalty area, the goal area and the arc are "
             "painted on the grass; the dummy stands in the middle of the goal.")
    difficulty = ("The dummy reaches any ball that needs more than about 1.3 s for the 11 m: the kick has to send a "
                  "0.43 kg ball off at about 12 m/s or more and into a corner (or over the dummy and under the bar). "
                  "The robot weighs 33 kg and has no kicking skill; a foot that merely runs into the ball at the "
                  "running policy's 4 m/s sends it off at 3 to 5 m/s.")

    def configure(self, params):
        super().configure(params)
        self.fall_z = self.p["fall_z_m"]

    # ------------------------------------------------------------------ geometry
    def geometry(self):
        p = self.p
        mark_x = p["run_up_m"]
        return dict(mark_x=mark_x, goal_x=mark_x + p["mark_distance_m"], half=p["goal_width_m"] / 2,
                    post_r=p["post_m"] / 2)

    def build(self, sc):
        p, g = self.p, self.geometry()
        gx, mx = g["goal_x"], g["mark_x"]
        sc.box("pitch", (gx / 2 - 2.0, 0, 0.0003), (gx / 2 + 6.0, 24.0, 0.0003), rgba=GRASS)
        sc.line("goal_line", (gx, -24.0), (gx, 24.0), width=p["post_m"])
        for name, depth, half in (("penalty_area", 16.5, 20.16), ("goal_area", 5.5, 9.16)):   # Law 1
            sc.line(f"{name}_front", (gx - depth, -half), (gx - depth, half), width=0.12)
            for s in (1, -1):
                sc.line(f"{name}_side{s}", (gx - depth, s * half), (gx, s * half), width=0.12)
        sc.disc("penalty_mark", (mx, 0.0), 0.11, rgba=(1, 1, 1, 1))
        a0 = math.acos((16.5 - p["mark_distance_m"]) / 9.15)                 # the penalty arc, outside the area
        n = 12
        for i in range(n):
            a, b = math.pi - a0 + 2 * a0 * i / n, math.pi - a0 + 2 * a0 * (i + 1) / n
            sc.line(f"arc{i}", (mx + 9.15 * math.cos(a), 9.15 * math.sin(a)), (mx + 9.15 * math.cos(b), 9.15 * math.sin(b)),
                    width=0.12)
        self.goal = sc.goal("goal", gx, 0.0, width=p["goal_width_m"], height=p["goal_height_m"], depth=p["goal_depth_m"],
                            post=g["post_r"])
        # the goalkeeper dummy: a heavy board on a slide along the goal line, driven by the referee (before_step)
        k = sc.body("keeper", (gx, 0.0, 0.0))
        ET.SubElement(k, "joint", name="keeper", type="slide", axis="0 1 0", armature="10000", damping="0")
        sc.geom(k, "keeper", type="box", pos=(0, 0, p["keeper_height_m"] / 2 + 0.01),
                size=(p["keeper_depth_m"] / 2, p["keeper_width_m"] / 2, p["keeper_height_m"] / 2), mass=80.0,
                rgba=(0.95, 0.75, 0.1, 1), contype="1", conaffinity="13")
        sc.ball("ball", "football", (mx, 0.0, BALL["radius"]))
        sc.camera("venue", (-9.0, -11.0, 6.5), (gx - 5.0, 1.0, 0.5), fovy=55)

    def reset(self, w):
        g = self.geometry()
        w.put("ball", (g["mark_x"], 0.0, BALL["radius"]))
        j = w.m.joint("keeper")
        w.d.qpos[j.qposadr[0]] = 0.0
        w.d.qvel[j.dofadr[0]] = 0.0

    # ------------------------------------------------------------------ the referee
    def referee_reset(self, w, ref):
        p, g = self.p, self.geometry()
        self.ball = ref.geoms(body="ball")
        self.foot = (ref.geoms(body="left_ankle_pitch_link") | ref.geoms(body="right_ankle_pitch_link")) & ref.robot_mask
        self.other = ref.robot_mask & ~self.foot
        j = w.m.joint("keeper")
        self.kq, self.kv = int(j.qposadr[0]), int(j.dofadr[0])
        # the whole ball over the goal line: one radius beyond the line's far edge (the line is as wide as the posts)
        self.trackers = {
            "mouth": MouthPass((g["goal_x"] + g["post_r"], 0.0), 0.0, g["half"], 0.0, p["goal_height_m"], BALL["radius"]),
            "kick_t": None, "forward": None,
        }

    def before_step(self, w):
        """The goalkeeper dummy: at rest until keeper_delay_s after the kick, then towards the ball's crossing point."""
        p, g, tr = self.p, self.geometry(), self.trackers
        d = w.d
        v = 0.0
        if tr.get("kick_t") is not None and w.ref.time >= tr["kick_t"] + p["keeper_delay_s"] - 1e-9:
            b, bv = w.pos("ball"), w.vel("ball")
            y = float(d.qpos[self.kq])
            if bv[0] > 0.1 and b[0] < g["goal_x"]:
                lim = g["half"] - p["keeper_width_m"] / 2
                target = float(np.clip(b[1] + bv[1] * (g["goal_x"] - b[0]) / bv[0], -lim, lim))
                v = float(np.clip((target - y) / w.CONTROL_DT, -p["keeper_speed_m_s"], p["keeper_speed_m_s"]))
        d.qvel[self.kv] = v

    def substep(self, w, ref):
        p, tr = self.p, self.trackers
        if ref.touching(self.ball, self.other):
            return ref.fail("the ball was touched by something other than a foot",
                            parts=sorted(ref.parts_touching(self.ball)))
        if ref.touching(self.ball, self.foot):
            if tr["kick_t"] is None:
                tr["kick_t"] = ref.time
                ref.stage("kick", part=sorted(ref.parts_touching(self.ball)))
            elif ref.time - tr["kick_t"] > p["kick_max_s"]:
                return ref.fail("second touch of the ball", after_s=round(ref.time - tr["kick_t"], 3))
        if tr["kick_t"] is not None and tr["forward"] is None and ref.time - tr["kick_t"] >= p["kick_max_s"]:
            v = w.vel("ball")
            tr["forward"] = bool(v[0] > 0.0)
            ref.metrics["kick_speed_m_s"] = round(float(np.linalg.norm(v)), 2)
            if not tr["forward"]:
                return ref.fail("the ball was not kicked forward")
        hit = tr["mouth"].update(w.pos("ball"))
        if hit == "in":
            if ref.stage("goal"):
                ref.succeed()
        elif hit == "wide":
            ref.fail("the ball crossed the goal line outside the goal")

    def step(self, w, ref):
        p = self.p
        b = w.pos("ball")
        ref.metrics["ball_x_m"] = round(float(b[0]), 3)
        ref.metrics["keeper_y_m"] = round(float(w.d.qpos[self.kq]), 3)
        if ref.has("kick") and ref.hold("rest", float(np.linalg.norm(w.vel("ball"))) < p["rest_speed_m_s"], p["rest_s"]):
            ref.fail("the ball came to rest without a goal")

    def privileged(self, w):
        g = self.geometry()
        return {"ball": w.pos("ball").tolist(), "ball_velocity": w.vel("ball").tolist(), "goal": self.goal,
                "penalty_mark": [g["mark_x"], 0.0],
                "keeper": {"y": float(w.d.qpos[self.kq]), "half_width": self.p["keeper_width_m"] / 2,
                           "height": self.p["keeper_height_m"]}}

