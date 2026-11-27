"""Penalty kick (IFAB Law 14) on the official goal: one kick of a size-5 ball from the penalty mark, 11 m out, past a
goalkeeper dummy on a rail along the goal line, driven by a force-limited servo motor (the shared block Keeper)."""
import math
import xml.etree.ElementTree as ET

import numpy as np

from rfo.referee import MouthPass
from rfo.scene import OFFICIAL
from rfo.task import TaskBase

BALL = OFFICIAL["football"]
GRASS = (0.16, 0.50, 0.20, 1)


# ---- shared block "keeper" (v1) ----
# Copy this block byte-identically into a family module (it needs `math`, `xml.etree.ElementTree as ET`, `numpy as np`
# imported by the module). Usage:
#   build(sc):          self.keeper = Keeper("keeper", x=goal_x, y=0.0, rail_half=goal_half - width / 2); self.keeper.build(sc)
#   reset(w):           self.keeper.reset(w)            (the board at its rail's centre, at rest; t = 0 placement)
#   referee_reset:      self.trackers["keeper"] = self.keeper   (its setpoint profile is part of the state hash)
#   before_step(w):     self.keeper.command(target_y)   (optional: where the servo's setpoint should go; omit = hold)
#   actuate(w, ref):    self.keeper.substep(w)          (REQUIRED: advances the setpoint by 1 ms, also after the call)
#   self.keeper.y(w), .vy(w), .force(w)                 (the board's world y, its speed and the motor's force)
#   self.keeper.bind(w).qa / .va / .aid                 (its qpos / dof / actuator addresses, read-only use)
class Keeper:
    """A goalkeeper dummy as a physical mechanism (no pose or velocity is ever written after reset).

    A rigid board (WIDTH x HEIGHT x DEPTH, MASS) on a carriage that runs on a straight rail along the goal line: a slide
    joint (axis y) with hard end stops at +-rail_half (the rail's buffers; they keep the board between the posts). A
    linear servo motor drives the carriage: one PD force on a setpoint, F = KP (s - y) + KV (s' - y') + MASS s'',
    saturated at +-F_MAX (MuJoCo's forcerange). The only thing a family scripts is the setpoint s: it moves on a trapezoidal profile
    (|s'| <= V_MAX, |s''| <= A_MAX) towards the commanded target, integrated every 1 ms physics step. A ball that hits
    the board pushes it: the board takes the impulse as an 80 kg free carriage would along the rail, and the servo
    pulls it back with at most F_MAX (the command carries the profile's speed and acceleration as feed-forward:
    ctrl = s + (KV s' + MASS s'') / KP); across the rail (x, z, rotations) the carriage is held by the rail.

    Limits and their sources:
    - MASS 80 kg, 1.9 m x 0.6 m x 0.3 m: the dummy's mass and size (an adult goalkeeper's mass and standing height,
      shoulder width).
    - V_MAX 3.0 m/s: an elite goalkeeper's lateral shuffle and the start of a dive move at about 3 m/s.
    - F_MAX 800 N (about one body weight of the 80 kg dummy, 10 m/s^2): of the order of the peak lateral push-off a
      goalkeeper applies in a dive (about one body weight); an off-the-shelf industrial linear motor of this peak force
      is a common size. A_MAX 9 m/s^2 is the profile's acceleration, inside F_MAX / MASS = 10 m/s^2 so the servo can
      follow it.
    - KP 20 000 N/m, KV 2 500 N s/m: a stiff, critically damped servo for 80 kg (2 sqrt(KP MASS) = 2 530 N s/m); a
      0.04 m tracking error already saturates F_MAX.
    - Rail rolling friction 4 N (a linear-guide rolling coefficient about 0.005 x the 785 N weight)."""

    MASS, WIDTH, HEIGHT, DEPTH = 80.0, 0.6, 1.9, 0.3
    V_MAX, A_MAX, F_MAX = 3.0, 9.0, 800.0
    KP, KV, FRICTION_N = 20000.0, 2500.0, 4.0
    LIFT = 0.01                     # the board's bottom edge above the ground (the carriage runs on the rail)

    def __init__(self, name="keeper", x=0.0, y=0.0, rail_half=3.36, rgba=(0.95, 0.75, 0.1, 1)):
        self.name, self.x, self.y0, self.rail_half, self.rgba = name, float(x), float(y), float(rail_half), rgba
        self.s = self.sv = self.target = 0.0        # the setpoint (rail coordinate, m), its speed, the target
        self.ph = 0.001

    def build(self, sc):
        n = self.name
        b = sc.body(n, (self.x, self.y0, 0.0))
        ET.SubElement(b, "joint", name=n, type="slide", axis="0 1 0", limited="true",
                      range=f"{-self.rail_half:.6g} {self.rail_half:.6g}", damping="0", armature="0",
                      frictionloss=f"{self.FRICTION_N:g}", solreflimit="0.005 1")
        sc.geom(b, n, type="box", pos=(0, 0, self.HEIGHT / 2 + self.LIFT),
                size=(self.DEPTH / 2, self.WIDTH / 2, self.HEIGHT / 2), mass=self.MASS, rgba=self.rgba,
                contype="1", conaffinity="13", friction="0.6 0.005 0.0001")
        # ctrl = s + (KV s' + MASS s'') / KP: the affine bias then gives F = KP (s - y) + KV (s' - y') + MASS s''
        ET.SubElement(sc.root.find("actuator"), "general", name=f"{n}_motor", joint=n, gainprm=f"{self.KP:g}",
                      biastype="affine", biasprm=f"0 {-self.KP:g} {-self.KV:g}", ctrllimited="false",
                      forcelimited="true", forcerange=f"{-self.F_MAX:g} {self.F_MAX:g}")

    def bind(self, w):
        """The joint's and the motor's addresses in this world's model (done by every call; the referee may ask
        before the first reset)."""
        if getattr(self, "_m", None) is not w.m:
            m = self._m = w.m
            j = m.joint(self.name)
            self.qa, self.va = int(j.qposadr[0]), int(j.dofadr[0])
            self.aid = int(m.actuator(f"{self.name}_motor").id)
            self.ph = float(m.opt.timestep)
        return self

    def reset(self, w):
        self.bind(w)
        w.d.qpos[self.qa] = 0.0                     # t = 0: at the rail's centre, at rest (the start state)
        w.d.qvel[self.va] = 0.0
        self.s = self.sv = self.target = 0.0
        w.d.ctrl[self.aid] = 0.0

    def command(self, target_y):
        """Where the setpoint should go (a world y, clipped to the rail); the profile gets it there."""
        self.target = float(np.clip(target_y - self.y0, -self.rail_half, self.rail_half))

    def substep(self, w):
        """One physics step of the setpoint profile; writes the servo command for the next physics step."""
        self.bind(w)
        dt, a, e = self.ph, self.A_MAX, self.target - self.s
        v_des = math.copysign(min(self.V_MAX, math.sqrt(2.0 * a * abs(e))), e) if abs(e) > 1e-9 else 0.0
        acc = float(np.clip(v_des - self.sv, -a * dt, a * dt)) / dt
        self.sv += acc * dt
        self.s += self.sv * dt
        # feed-forward of the profile's speed and acceleration through the command (MASS acc: the force it needs)
        w.d.ctrl[self.aid] = self.s + (self.KV * self.sv + self.MASS * acc) / self.KP

    def y(self, w):
        self.bind(w)
        return float(w.d.qpos[self.qa]) + self.y0

    def vy(self, w):
        self.bind(w)
        return float(w.d.qvel[self.va])

    def force(self, w):
        self.bind(w)
        return float(w.d.actuator_force[self.aid])

    def facts(self):
        return dict(mass_kg=self.MASS, width_m=self.WIDTH, height_m=self.HEIGHT, depth_m=self.DEPTH,
                    v_max_m_s=self.V_MAX, a_max_m_s2=self.A_MAX, f_max_n=self.F_MAX, kp_n_m=self.KP,
                    kv_n_s_m=self.KV, rail_half_m=self.rail_half)

    def state(self):
        return [self.s, self.sv, self.target]
# ---- end of shared block "keeper" ----


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
        "Law 14 (the goalkeeper): the goalkeeper is a dummy, a rigid board {keeper_height_m} m high, "
        "{keeper_width_m} m wide and {keeper_mass_kg} kg on a carriage that runs on a rail along the goal line, driven "
        "by a linear servo motor of at most {keeper_force_n} N (at most {keeper_speed_m_s} m/s); the rail's end stops "
        "keep it between the posts. It starts at the centre and, from {keeper_delay_s} s after the kick, the motor "
        "drives it towards the point where the ball's velocity of that moment would take it over the goal line. The "
        "ball pushes it along the rail when it hits it; it neither dives, jumps nor uses hands. An opponent cannot be "
        "simulated otherwise.",
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
                  run_up_m=3.0, keeper_height_m=Keeper.HEIGHT, keeper_width_m=Keeper.WIDTH, keeper_depth_m=Keeper.DEPTH,
                  keeper_mass_kg=Keeper.MASS, keeper_force_n=Keeper.F_MAX, keeper_delay_s=0.25,
                  keeper_speed_m_s=Keeper.V_MAX, kick_max_s=0.15, rest_speed_m_s=0.1, rest_s=1.0, fall_z_m=0.35)

    sentence = (("Take a penalty kick: with one kick, send the ball past the goalkeeper dummy into the goal."))
    rules = ("A size-5 football (0.22 m across, 0.43 kg, in air) lies at rest on the penalty mark, {run_up_m} m "
             "straight ahead of you; the goal line is {mark_distance_m} m beyond the mark. The goal is "
             "{goal_width_m} m wide between the posts and {goal_height_m} m high under the crossbar (posts and bar "
             "{post_m} m thick), centred on the line through you and the mark. A goalkeeper dummy, a board "
             "{keeper_height_m} m high, {keeper_width_m} m wide, {keeper_depth_m} m thick and {keeper_mass_kg} kg, "
             "stands on the goal line at the centre of the goal on a carriage that runs on a rail along the line, "
             "driven by a motor of at most {keeper_force_n} N; from {keeper_delay_s} s after your kick the motor "
             "drives it at up to {keeper_speed_m_s} m/s towards the point where the ball, going on as it moves at "
             "that moment, would cross the line, and it blocks the ball (a hit pushes it along the rail). The kick is a contact of a foot or an ankle of yours with the "
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
    difficulty = ("The dummy reaches any ball that needs more than about 1.45 s for the 11 m: the kick has to send a "
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
        # the goalkeeper dummy: a board on a rail along the goal line, driven by a force-limited servo (Keeper)
        self.keeper = Keeper("keeper", x=gx, y=0.0, rail_half=g["half"] - p["keeper_width_m"] / 2)
        k = self.keeper
        k.HEIGHT, k.WIDTH, k.DEPTH, k.MASS = p["keeper_height_m"], p["keeper_width_m"], p["keeper_depth_m"], p["keeper_mass_kg"]
        k.F_MAX, k.V_MAX = p["keeper_force_n"], p["keeper_speed_m_s"]
        k.build(sc)
        sc.ball("ball", "football", (mx, 0.0, BALL["radius"]))
        sc.camera("venue", (-9.0, -11.0, 6.5), (gx - 5.0, 1.0, 0.5), fovy=55)

    def reset(self, w):
        g = self.geometry()
        w.put("ball", (g["mark_x"], 0.0, BALL["radius"]))
        self.keeper.reset(w)                       # t = 0: at the centre of its rail, at rest

    # ------------------------------------------------------------------ the referee
    def referee_reset(self, w, ref):
        p, g = self.p, self.geometry()
        self.ball = ref.geoms(body="ball")
        self.foot = (ref.geoms(body="left_ankle_pitch_link") | ref.geoms(body="right_ankle_pitch_link")) & ref.robot_mask
        self.other = ref.robot_mask & ~self.foot
        self.kq, self.kv = self.keeper.bind(w).qa, self.keeper.va
        # the whole ball over the goal line: one radius beyond the line's far edge (the line is as wide as the posts)
        self.trackers = {
            "mouth": MouthPass((g["goal_x"] + g["post_r"], 0.0), 0.0, g["half"], 0.0, p["goal_height_m"], BALL["radius"]),
            "kick_t": None, "forward": None, "keeper": self.keeper,
        }

    def before_step(self, w):
        """The goalkeeper dummy's script, through its motor only: the servo's target is the centre until
        keeper_delay_s after the kick, then the point where the ball's velocity would take it over the line."""
        p, g, tr = self.p, self.geometry(), self.trackers
        if tr.get("kick_t") is not None and w.ref.time >= tr["kick_t"] + p["keeper_delay_s"] - 1e-9:
            b, bv = w.pos("ball"), w.vel("ball")
            if bv[0] > 0.1 and b[0] < g["goal_x"]:
                self.keeper.command(b[1] + bv[1] * (g["goal_x"] - b[0]) / bv[0])

    def actuate(self, w, ref):
        self.keeper.substep(w)                     # the servo's setpoint, every physics step

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
        ref.metrics["keeper_y_m"] = round(self.keeper.y(w), 3)
        if ref.has("kick") and ref.hold("rest", float(np.linalg.norm(w.vel("ball"))) < p["rest_speed_m_s"], p["rest_s"]):
            ref.fail("the ball came to rest without a goal")

    def privileged(self, w):
        g = self.geometry()
        return {"ball": w.pos("ball").tolist(), "ball_velocity": w.vel("ball").tolist(), "goal": self.goal,
                "penalty_mark": [g["mark_x"], 0.0],
                "keeper": {"y": self.keeper.y(w), "vy": self.keeper.vy(w), "force_n": self.keeper.force(w),
                           "half_width": self.p["keeper_width_m"] / 2, "height": self.p["keeper_height_m"],
                           **self.keeper.facts()}}

