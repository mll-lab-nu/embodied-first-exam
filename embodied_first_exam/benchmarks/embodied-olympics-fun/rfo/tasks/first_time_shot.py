"""First-time shot: a pass released by a gate rolls down a ramp and across in front of you, square to the goal; shoot
it first time, with one touch of a foot, into the official goal 11 m away."""
import math
import xml.etree.ElementTree as ET

import numpy as np

from rfo.referee import MouthPass
from rfo.scene import OFFICIAL, STANDABLE, HITTABLE, fmt
from rfo.task import TaskBase

BALL = OFFICIAL["football"]
GRASS = (0.16, 0.50, 0.20, 1)
WOOD = (0.62, 0.47, 0.30, 1)
STEEL = (0.35, 0.36, 0.40, 1)
# The gate's motor: a ROBOTIS Dynamixel XM430-W350 smart servo (ROBOTIS e-Manual, XM430-W350-T/R specifications: stall
# torque 4.1 N m and no-load speed 46 rev/min at 12 V). A DC motor's torque falls linearly with speed, so its torque
# limit is the actuator's force range and its back-EMF is the joint damping stall torque / no-load speed.
SERVO_STALL_NM = 4.1
SERVO_NOLOAD_RAD_S = 46 * 2 * math.pi / 60
# The gate's flap: a 5 mm polycarbonate sheet (density 1200 kg/m^3, Covestro Makrolon data sheet).
PC_DENSITY = 1200.0


def quat_x(a: float):
    return (math.cos(a / 2), math.sin(a / 2), 0.0, 0.0)


class Strike:
    """One strike of the ball by the robot: from the first contact until the ball has been clear of the robot for
    `clear_s`. It records the ball's velocity at the last physics step before the first contact (v_in) and at the
    last separation (v_out), and the parts that touched. (Copied from rfo/tasks/volley_shot.py.)"""

    def __init__(self, ref, ball, clear_s: float):
        self.ref, self.ball, self.clear_s = ref, ball, clear_s
        self.phase = 0                      # 0: not begun; 1: begun, the ball not yet clear; 2: over
        self.v_free = self.v_in = self.v_out = None
        self.t0 = self.t_last = None
        self.touching = False
        self.parts: set = set()

    def update(self, vel) -> str | None:
        """Once per physics step. "start" at the first contact, "end" when the ball has got clear, else None."""
        ref, out = self.ref, None
        now = ref.touching(self.ball, ref.robot_mask)
        if self.phase == 0:
            if now:
                self.phase, self.t0, self.t_last = 1, ref.time, ref.time
                self.v_in = self.v_free if self.v_free is not None else [float(x) for x in vel]
                out = "start"
            else:
                self.v_free = [float(x) for x in vel]
        elif self.phase == 1:
            if now:
                self.t_last = ref.time
            else:
                if self.touching:
                    self.v_out = [float(x) for x in vel]
                if ref.time - self.t_last >= self.clear_s:
                    self.phase, out = 2, "end"
        if now and self.phase == 1:
            self.parts |= ref.parts_touching(self.ball)
        self.touching = now
        return out

    @property
    def duration(self) -> float:
        return 0.0 if self.t0 is None else self.t_last - self.t0

    def speeds(self) -> tuple[float, float]:
        return float(np.linalg.norm(self.v_in)), float(np.linalg.norm(self.v_out))

    def state(self) -> list:
        return [self.phase, self.v_free, self.v_in, self.v_out, self.t0, self.t_last, self.touching, sorted(self.parts)]


class Task(TaskBase):
    name = "first-time-shot"
    title = "Football: first-time shot"
    category = "football-and-volleyball"
    robot = "unitree_g1"
    rulebook = ("IFAB Laws of the Game 2025/26: Law 1 (the goal 7.32 m x 2.44 m with posts and crossbar 12 cm wide, the "
                "penalty mark 11 m from the goal line, the penalty area, the goal area), Law 2 (a size-5 ball: 68-70 cm "
                "round, 410-450 g), Law 10 (a goal: the whole ball over the goal line between the posts and under the "
                "bar), Law 12 (handball) and the glossary (a kick is a contact with the foot or the ankle). The drill "
                "itself, a square pass struck first time (one touch) at goal from the penalty mark, is a coaching "
                "exercise, not a rule-book event: the pass and the one-touch standard are the benchmark's")
    deviations = [
        "The pass comes from a ball ramp instead of a team-mate: the ball rests against a gate {ramp_height_m} m up a "
        "{ramp_slope_deg} degree wooden ramp whose foot is {ramp_foot_m} m to your left on the pass line; at "
        "{release_time_s} s a servo (stall torque {gate_torque_nm} N m) swings the gate open and gravity rolls the ball "
        "down and across, along the line through the penalty mark parallel to the goal line. The same pass in "
        "every attempt; the pitch is level and uniform (the official ball's rolling resistance, no bobble), no wind.",
        "Law 3: no goalkeeper and no defender: a finishing drill on an open goal, not a match situation.",
        "The Laws allow any number of touches and any part but the arms; the task is narrower than the Laws: one "
        "touch, with a foot or an ankle only, while the ball is between the lines of the two posts (the shot is "
        "taken from in front of the goal).",
        "A shot is judged by numbers instead of a referee's eye: every contact within {strike_max_s} s of the first "
        "is the one touch, and a shot is a ball that leaves the foot at least {strike_gain} times as fast as it "
        "arrived (a ball that only rebounds from a foot held in its path leaves slower: it is not a shot).",
        "Law 1: only the goal end of the field is there (the penalty area, the goal area and the mark are painted); "
        "the goal's net is a rigid cage {goal_depth_m} m deep.",
    ]
    time_limit_s = 15.0
    start = (0.0, 0.0, 0.0)
    stages = ["shot", "goal"]
    fall_z = 0.35
    params = dict(goal_width_m=7.32, goal_height_m=2.44, post_m=0.12, goal_depth_m=2.0, mark_distance_m=11.0,
                  behind_line_m=0.3, ramp_height_m=1.2, ramp_slope_deg=20.0, ramp_foot_m=4.0, ramp_width_m=0.40,
                  ramp_arc_m=1.5, release_time_s=2.0, gate_torque_nm=SERVO_STALL_NM, strike_max_s=0.15, clear_s=0.03,
                  strike_gain=1.0, rest_speed_m_s=0.1, rest_s=1.0, fall_z_m=0.35)

    sentence = (("Shoot first time: with one touch of a foot, send the ball rolling across in front of you into "
                 "the goal."))
    rules = ("You stand facing the goal (+x), {behind_line_m} m behind the pass line: the line through the penalty mark "
             "parallel to the goal line, which is {mark_distance_m} m beyond it. The goal is {goal_width_m} m wide "
             "between the posts and {goal_height_m} m high under the crossbar (posts and bar {post_m} m thick), "
             "centred on the line you face along; there is no goalkeeper. A size-5 football (0.22 m across, 0.43 kg, "
             "in air) rests against a gate on a wooden ball ramp: the ramp's foot is on the pass line {ramp_foot_m} m "
             "to your left, it rises away from you at {ramp_slope_deg} degrees (curving into the grass at its foot) "
             "and the ball waits {ramp_height_m} m up it. At {release_time_s} s a servo swings the gate open; the "
             "ball rolls down the ramp and along the pass line from your left to your right. The shot is the ball's "
             "first contact with you after the release: with a foot or an ankle of yours (the parts below the shin), "
             "while the ball's centre is between the lines of the two posts ({goal_width_m} m wide, measured across "
             "the pass). Every contact within {strike_max_s} s of the first belongs to the one touch, which is over "
             "when the ball has been clear of you for {clear_s} s; it must be a shot: the ball's speed when it leaves "
             "your foot is at least {strike_gain} times its speed just before the foot touched it, and it is moving "
             "towards the goal line. You succeed at the moment the whole ball is then over the goal line between "
             "the posts and under the bar; after the shot it may touch the ground, the posts and the bar. You fail "
             "if any part of you other than a foot or an ankle touches the ball at any time, if the first touch is "
             "outside the lines of the posts, if the touch lasts longer than {strike_max_s} s, if the ball leaves the "
             "foot slower than that or not towards the goal line, if you touch the ball again after the shot, if the "
             "pass rolls past the line of the far post untouched, if the whole ball crosses the goal line outside "
             "the goal, if after the shot the ball has been slower than {rest_speed_m_s} m/s for {rest_s} s, if you "
             "touch the ramp or its gate, if you fall (your pelvis lower than {fall_z_m} m above the ground, or any "
             "part of you other than the feet on the ground), or after {time_limit_s} s.")
    venue = ("You face the goal (+x) on level grass, {behind_line_m} m behind the penalty mark, on the line through the "
             "mark and the centre of the goal. The ramp stands on the pass line to your left, its foot {ramp_foot_m} m "
             "from the centre line; it is {ramp_width_m} m wide between its rails and curves into the grass at its foot "
             "on an arc of {ramp_arc_m} m radius; the ball is visible at the gate near its top. Released at {release_time_s} s, "
             "it reaches the grass about 1.8 s later and crosses in front of you, {behind_line_m} m ahead of your "
             "pelvis, about 3.1 s after the release, at about 3.1 m/s, rolling from your left to your right.")
    difficulty = ("The ball crosses the width of a foot in a few hundredths of a second and at right angles to the "
                  "goal: the foot has to arrive with a swing or a run of its own at that moment, angled so that the "
                  "pass's sideways speed is turned towards the goal, faster than the ball came, by a 33 kg robot "
                  "that has no kicking skill and has to stay on its feet.")

    def configure(self, params):
        super().configure(params)
        self.fall_z = self.p["fall_z_m"]

    # ------------------------------------------------------------------ geometry
    def geometry(self):
        p = self.p
        th = math.radians(p["ramp_slope_deg"])
        R = p["ramp_arc_m"]                                    # the transition's radius: the ramp curves into the grass
        u_arc, z_arc = R * math.sin(th), R * (1 - math.cos(th))
        u_gate = u_arc + (p["ramp_height_m"] - z_arc) / math.tan(th)
        return dict(px=p["behind_line_m"], goal_x=p["behind_line_m"] + p["mark_distance_m"], half=p["goal_width_m"] / 2,
                    post_r=p["post_m"] / 2, th=th, R=R, u_arc=u_arc, z_arc=z_arc, u_gate=u_gate,
                    y_foot=p["ramp_foot_m"])

    def _profile(self):
        """The ramp's surface from its foot uphill: [(u, z)], u along +y from the foot."""
        g = self.geometry()
        n = 8
        pts = [(g["R"] * math.sin(g["th"] * i / n), g["R"] * (1 - math.cos(g["th"] * i / n))) for i in range(n + 1)]
        top_u = g["u_gate"] + 0.45                             # room behind the ball, then a back stop
        pts.append((top_u, g["z_arc"] + (top_u - g["u_arc"]) * math.tan(g["th"])))
        return pts

    def _surface(self, u):
        """(world point, normal, uphill) of the ramp's straight part at u (u >= u_arc)."""
        g = self.geometry()
        th = g["th"]
        z = g["z_arc"] + (u - g["u_arc"]) * math.tan(th)
        return (np.array([g["px"], g["y_foot"] + u, z]), np.array([0.0, -math.sin(th), math.cos(th)]),
                np.array([0.0, math.cos(th), math.sin(th)]))

    def gate_frame(self):
        """The gate's hinge (world point) and the ball's starting centre."""
        g, p = self.geometry(), self.p
        S, n, up = self._surface(g["u_gate"])
        r = BALL["radius"]
        return dict(hinge=S + n * 0.27, ball=S + up * (r + 0.0025 + 0.002) + n * r)

    def build(self, sc):
        p, g = self.p, self.geometry()
        gx, px = g["goal_x"], g["px"]
        sc.box("pitch", (gx / 2 - 2.0, 4.0, 0.0003), (gx / 2 + 6.0, 24.0, 0.0003), rgba=GRASS)
        sc.line("goal_line", (gx, -24.0), (gx, 24.0), width=p["post_m"])
        for name, depth, half in (("penalty_area", 16.5, 20.16), ("goal_area", 5.5, 9.16)):   # Law 1
            sc.line(f"{name}_front", (gx - depth, -half), (gx - depth, half), width=0.12)
            for s in (1, -1):
                sc.line(f"{name}_side{s}", (gx - depth, s * half), (gx, s * half), width=0.12)
        sc.disc("penalty_mark", (px, 0.0), 0.11, rgba=(1, 1, 1, 1))
        self.goal = sc.goal("goal", gx, 0.0, width=p["goal_width_m"], height=p["goal_height_m"], depth=p["goal_depth_m"],
                            post=g["post_r"])
        # the ramp: wooden boards along the profile (a circular transition of 8 chords, then the straight slope), side
        # rails, a back stop; every piece a fixed geom of the world
        W, tk, rail_h, rail_t = p["ramp_width_m"], 0.04, 0.08, 0.02
        pts = self._profile()
        self.ramp_geoms = []
        for i, ((u0, z0), (u1, z1)) in enumerate(zip(pts[:-1], pts[1:])):
            a = math.atan2(z1 - z0, u1 - u0)
            L = math.hypot(u1 - u0, z1 - z0) + 0.02
            nrm = np.array([-math.sin(a), math.cos(a)])       # (u, z) normal
            cu, cz = (u0 + u1) / 2 - nrm[0] * tk / 2, (z0 + z1) / 2 - nrm[1] * tk / 2
            name = f"ramp_board{i}"
            sc.geom(sc.wb, name, type="box", pos=(px, g["y_foot"] + cu, cz), size=(W / 2 + rail_t, L / 2, tk / 2),
                    quat=quat_x(a), rgba=WOOD, friction=(0.6, 0.005, 0.0001), **STANDABLE)
            self.ramp_geoms.append(name)
            for s in (1, -1):
                ru, rz = (u0 + u1) / 2 + nrm[0] * rail_h / 2, (z0 + z1) / 2 + nrm[1] * rail_h / 2
                rn = f"ramp_rail{i}_{'L' if s > 0 else 'R'}"
                sc.geom(sc.wb, rn, type="box", pos=(px + s * (W / 2 + rail_t / 2), g["y_foot"] + ru, rz),
                        size=(rail_t / 2, L / 2, rail_h / 2), quat=quat_x(a), rgba=WOOD, **STANDABLE)
                self.ramp_geoms.append(rn)
        top_u, top_z = pts[-1]
        S, nn, up = self._surface(top_u)
        c = S + nn * 0.15 + up * 0.01
        sc.geom(sc.wb, "ramp_stop", type="box", pos=tuple(c), size=(W / 2 + rail_t, 0.01, 0.15), quat=quat_x(g["th"]),
                rgba=WOOD, **STANDABLE)
        self.ramp_geoms.append("ramp_stop")
        # legs under the straight part (visual supports to the ground)
        for k, u in enumerate((g["u_arc"] + 0.3, (g["u_arc"] + top_u) / 2, top_u - 0.05)):
            S, _, _ = self._surface(u)
            for s in (1, -1):
                h = float(S[2]) - tk
                if h > 0.02:
                    sc.geom(sc.wb, f"ramp_leg{k}_{s}", type="box", pos=(px + s * (W / 2), S[1], h / 2),
                            size=(0.02, 0.02, h / 2), rgba=WOOD, **STANDABLE)
                    self.ramp_geoms.append(f"ramp_leg{k}_{s}")
        # the gate: a polycarbonate flap hanging from a hinge across the ramp, 0.27 m above its surface, swung open
        # downhill (and up, over the ball's path) by the servo
        gf = self.gate_frame()
        hinge = gf["hinge"]
        for s in (1, -1):
            post_h = float(hinge[2]) + 0.03
            sc.geom(sc.wb, f"gate_post{'L' if s > 0 else 'R'}", type="box",
                    pos=(px + s * (W / 2 + rail_t + 0.02), hinge[1], post_h / 2), size=(0.02, 0.02, post_h / 2),
                    rgba=STEEL, **STANDABLE)
            self.ramp_geoms.append(f"gate_post{'L' if s > 0 else 'R'}")
        gb = sc.body("gate", tuple(hinge), quat=quat_x(g["th"]))
        fw, ft, fl = W / 2 - 0.01, 0.0025, 0.12               # half sizes: across, thickness, along
        ET.SubElement(gb, "joint", name="gate", type="hinge", axis="1 0 0", range="-1.9 0.02",
                      damping=f"{SERVO_STALL_NM / SERVO_NOLOAD_RAD_S:.6g}", armature="0.005")
        sc.geom(gb, "gate_flap", type="box", pos=(0, 0, -fl), size=(fw, ft, fl), mass=PC_DENSITY * 8 * fw * ft * fl,
                rgba=(0.75, 0.85, 0.95, 0.7), **HITTABLE)
        sc.geom(gb, "gate_axle", type="capsule", fromto=(-fw, 0, 0, fw, 0, 0), size=(0.008,), mass=0.05, rgba=STEEL,
                **HITTABLE)
        ET.SubElement(sc.root.find("actuator"), "position", name="gate_servo", joint="gate", kp="40",
                      forcerange=f"{-p['gate_torque_nm']:.6g} {p['gate_torque_nm']:.6g}", ctrlrange="-1.9 0.02")
        self.gate_geoms = ["gate_flap", "gate_axle"]
        sc.ball("ball", "football", tuple(gf["ball"]))
        sc.camera("venue", (-5.0, -4.0, 3.5), (px + 4.0, 2.0, 0.3), fovy=65)

    def reset(self, w):
        w.put("ball", tuple(self.gate_frame()["ball"]))
        j = w.m.joint("gate")
        w.d.qpos[j.qposadr[0]] = 0.0
        w.d.qvel[j.dofadr[0]] = 0.0

    # ------------------------------------------------------------------ the referee
    def referee_reset(self, w, ref):
        p, g = self.p, self.geometry()
        self.ball = ref.geoms(body="ball")
        self.foot = (ref.geoms(body="left_ankle_pitch_link") | ref.geoms(body="right_ankle_pitch_link")) & ref.robot_mask
        self.other = ref.robot_mask & ~self.foot
        self.ramp = ref.geoms(names=self.ramp_geoms + self.gate_geoms)
        self.servo = int(w.m.actuator("gate_servo").id)
        j = w.m.joint("gate")
        self.gq = int(j.qposadr[0])
        self.trackers = {
            "strike": Strike(ref, self.ball, p["clear_s"]),
            "mouth": MouthPass((g["goal_x"] + g["post_r"], 0.0), 0.0, g["half"], 0.0, p["goal_height_m"], BALL["radius"]),
            "released": False,
        }

    def before_step(self, w):
        p, tr = self.p, self.trackers
        if not tr["released"] and w.t >= p["release_time_s"] - 1e-9:
            tr["released"] = True
            w.ref.event("gate opens")
        w.d.ctrl[self.servo] = -1.75 if tr["released"] else 0.0

    def substep(self, w, ref):
        p, g, tr = self.p, self.geometry(), self.trackers
        if ref.touching(ref.robot_mask, self.ramp):
            return ref.fail("touched the ramp", parts=sorted(ref.parts_touching(self.ramp)))
        st = tr["strike"]
        if ref.touching(self.ball, self.other):
            return ref.fail("the ball was touched by something other than a foot", parts=sorted(ref.parts_touching(self.ball)))
        if st.phase == 2 and ref.touching(self.ball, ref.robot_mask):
            return ref.fail("second touch of the ball")
        b = w.pos("ball")
        ev = st.update(w.vel("ball"))
        if ev == "start" and abs(float(b[1])) > g["half"]:
            return ref.fail("the first touch was outside the lines of the posts", ball_y=round(float(b[1]), 3))
        if st.phase == 1 and st.duration > p["strike_max_s"]:
            return ref.fail("the ball was carried", touch_s=round(st.duration, 3))
        if ev == "end":
            v_in, v_out = st.speeds()
            ref.metrics["speed_in_m_s"], ref.metrics["speed_out_m_s"] = round(v_in, 2), round(v_out, 2)
            if v_out < p["strike_gain"] * v_in:
                return ref.fail("the ball was not struck: it left the foot slower than it came",
                                speed_in=round(v_in, 2), speed_out=round(v_out, 2))
            if st.v_out[0] <= 0.0:
                return ref.fail("the ball was not struck towards the goal line")
            ref.stage("shot", parts=sorted(st.parts), speed_in=round(v_in, 2), speed_out=round(v_out, 2))
        if st.phase == 0 and float(b[1]) < -g["half"] - BALL["radius"]:
            return ref.fail("the pass rolled by untouched")
        hit = tr["mouth"].update(b)
        if hit is not None and not ref.has("shot"):
            return ref.fail("the ball crossed the goal line without a shot")
        if hit == "in":
            if ref.stage("goal"):
                ref.succeed()
        elif hit == "wide":
            ref.fail("the ball crossed the goal line outside the goal")

    def step(self, w, ref):
        p = self.p
        b = w.pos("ball")
        ref.metrics["ball_x_m"] = round(float(b[0]), 3)
        ref.metrics["ball_y_m"] = round(float(b[1]), 3)
        ref.metrics["gate_rad"] = round(float(w.d.qpos[self.gq]), 3)
        if ref.has("shot") and ref.hold("rest", float(np.linalg.norm(w.vel("ball"))) < p["rest_speed_m_s"], p["rest_s"]):
            ref.fail("the ball came to rest without a goal")

    def privileged(self, w):
        g = self.geometry()
        return {"ball": w.pos("ball").tolist(), "ball_velocity": w.vel("ball").tolist(), "goal": self.goal,
                "released": bool(self.trackers.get("released")), "release_time_s": self.p["release_time_s"],
                "gate_angle_rad": float(w.d.qpos[self.gq]), "pass_line_x": g["px"], "ramp_foot_y": g["y_foot"],
                "penalty_mark": [g["px"], 0.0]}
