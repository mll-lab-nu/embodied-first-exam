"""Volleyball set: a pass from the back court comes down above the setter at the net; set it overhead with the hands,
in one contact, at least a metre above the net to the outside hitter's target at position 4."""
import math

import numpy as np

from rfo.scene import HITTABLE, OFFICIAL, VISUAL, WHITE, quat_z
from rfo.task import TaskBase

BALL = OFFICIAL["volleyball"]
HANDS = {"left_hand", "right_hand"}


class Strike:
    """One strike of the ball by the robot: from the first contact until the ball has been clear of the robot for
    `clear_s`. It records the ball's velocity at the last physics step before the first contact (v_in) and at the
    last separation (v_out), the parts that touched and the contact points."""

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

def build_court(sc, p, centre, yaw):
    """The FIVB court (Rules 1 and 2) around the foot of the net's centre: 18 m x 9 m with 5 cm lines drawn inside
    it, the centre line, the attack lines (rear edge 3 m from the centre line's axis), the free zone, the men's net
    (1 m deep, its top at 2.43 m, 9.5 m long), the posts (2.55 m, 1 m outside the side lines) and the antennas (1.80 m
    long, 10 mm, above the side lines, 0.80 m above the net). Court frame: u from the net towards the opponent's
    court (the direction `yaw` in the world), v along the net to the left of it."""
    c, s = math.cos(yaw), math.sin(yaw)
    L, hw, top, lw = p["court_half_length_m"], p["court_width_m"] / 2, p["net_height_m"], 0.05

    def W(u, v):
        return (centre[0] + c * u - s * v, centre[1] + s * u + c * v)

    sc.geom(sc.wb, "free_zone", type="box", pos=(*W(0, 0), 0.0002), size=(L + 6.5, hw + 5.0, 0.0002), quat=quat_z(yaw),
            rgba=(0.18, 0.40, 0.62, 1), **VISUAL)
    sc.geom(sc.wb, "court", type="box", pos=(*W(0, 0), 0.0004), size=(L, hw, 0.0002), quat=quat_z(yaw),
            rgba=(0.86, 0.56, 0.30, 1), **VISUAL)
    for sg in (1, -1):
        sc.line(f"side_line{sg}", W(-L, sg * (hw - lw / 2)), W(L, sg * (hw - lw / 2)), width=lw)
        sc.line(f"end_line{sg}", W(sg * (L - lw / 2), -hw), W(sg * (L - lw / 2), hw), width=lw)
        a = p["attack_line_m"] - lw / 2
        sc.line(f"attack_line{sg}", W(sg * a, -hw), W(sg * a, hw), width=lw)
    sc.line("centre_line", W(0, -hw), W(0, hw), width=lw)
    net = sc.body("net", (centre[0], centre[1], 0.0), quat_z(yaw))
    sc.geom(net, "net_mesh", type="box", pos=(0, 0, top - 0.5), size=(0.004, 4.75, 0.5), rgba=(0.95, 0.95, 0.95, 0.45),
            **HITTABLE)
    sc.geom(net, "net_band", type="box", pos=(0, 0, top - 0.035), size=(0.006, 4.75, 0.035), rgba=WHITE, **VISUAL)
    for sg, tag in ((1, "L"), (-1, "R")):
        sc.geom(net, f"net_post{tag}", type="cylinder", pos=(0, sg * (hw + 1.0), 1.275), size=(0.05, 1.275),
                rgba=(0.3, 0.3, 0.33, 1), **HITTABLE)
        sc.geom(net, f"net_antenna{tag}", type="cylinder", pos=(0, sg * hw, top - 0.1), size=(0.005, 0.9),
                rgba=(0.9, 0.15, 0.15, 1), **HITTABLE)
        sc.geom(net, f"net_side_band{tag}", type="box", pos=(0, sg * (hw - 0.025), top - 0.5), size=(0.005, 0.025, 0.5),
                rgba=WHITE, **VISUAL)
    return W


def to_court(centre, yaw, pts):
    """World points (n, 2+) -> court coordinates (u, v)."""
    c, s = math.cos(yaw), math.sin(yaw)
    d = np.atleast_2d(np.asarray(pts, float))[:, :2] - np.asarray(centre, float)
    return np.c_[c * d[:, 0] + s * d[:, 1], -s * d[:, 0] + c * d[:, 1]]


def centre_line_fault(w, ref, centre, yaw) -> str | None:
    """FIVB 11.2.2: a foot wholly beyond the centre line (every point where it touches the floor is on the opponent's
    side of the line). Returns the foot, or None."""
    for side in ("left", "right"):
        pts = ref.contact_points(ref.part(f"{side}_foot"), ref.ground)
        if len(pts) and float(np.min(to_court(centre, yaw, pts)[:, 0])) > 0.025:
            return f"{side}_foot"
    return None


class Task(TaskBase):
    name = "volleyball-set"
    title = "Volleyball: set"
    category = "football-and-volleyball"
    robot = "unitree_h1"
    rulebook = ("FIVB Official Volleyball Rules 2025-2028: Rule 1 (the court 18 m x 9 m, the front zone between the "
                "centre line and the attack line 3 m from it), Rule 2 (the men's net, top at 2.43 m, the antennas), "
                "Rule 3 (the ball: 65-67 cm round, 260-280 g), Rule 9.2 (the hit: not caught or thrown, one contact), "
                "Rule 11 (no contact with the net, the foot not wholly beyond the centre line)")
    deviations = [
        "The pass is a scripted launch: a ball tossed without spin from the back court, the same in every attempt, "
        "instead of a team-mate.",
        "Rule 9.2 (the overhead pass with the fingers): the robot has no fingers, so the set is one contact of the "
        "hands (the parts beyond the wrists) with the ball's centre above the top of the robot's head "
        "({head_top_m} m above its waist joint along the trunk, about 1.80 m when it stands). 'Not caught or thrown' "
        "is a contact of at most {strike_max_s} s (the ball cannot be gripped).",
        "A set is judged by numbers instead of a referee's eye: the ball must leave the hands moving upward and at "
        "least {set_gain} times as fast as it arrived (hands held still in the ball's path return it at no more than "
        "three quarters of its speed: that is a rebound, not a set); it must be played after it has passed its "
        "highest point, by a setter who has stayed in the front zone.",
        "Nobody attacks the set: a good set is defined as volleyball coaching grades it, a ball that rises at least "
        "{rise_above_net_m} m above the net and comes down in the outside hitter's target, a circle of "
        "{target_radius_m} m radius at position 4, judged where the ball first touches the floor.",
        "No team-mates or opponents, no wind.",
    ]
    time_limit_s = 10.0
    start = (0.0, 0.0, 0.0)
    stages = ["set", "above the net", "in the target"]
    fall_z = 0.35
    params = dict(court_half_length_m=9.0, court_width_m=9.0, net_height_m=2.43, attack_line_m=3.0, net_side_m=1.0,
                  side_line_behind_m=3.0, target_off_net_m=1.0, target_from_side_line_m=1.0, target_radius_m=1.0,
                  rise_above_net_m=1.0, set_gain=1.0, head_top_m=0.76, strike_max_s=0.10, clear_s=0.03, fall_z_m=0.35,
                  launch_time_s=3.0, pass_x_m=1.5, pass_y_m=5.5, pass_z_m=0.9,
                  pass_vx_m_s=-1.013, pass_vy_m_s=-4.457, pass_vz_m_s=7.917)

    sentence = ("Set the pass: with one overhead contact of your hands, send the volleyball that comes down above you "
                "at least a metre above the net and into the outside hitter's target along the net.")
    rules = ("You are the setter on an official volleyball court ({court_half_length_m} m by {court_width_m} m on each "
             "side of the net; the net's top {net_height_m} m high). You stand in your front zone facing along the "
             "net: the net is {net_side_m} m to your right, the attack line {attack_line_m} m from the centre line "
             "to your left, the side line of position 2 {side_line_behind_m} m behind you, the side line of position "
             "4 ahead of you. A volleyball (0.21 m across, 0.27 kg, in air) is tossed to you from the back court "
             "{launch_time_s} s after the start and comes down above you. The set is the ball's first contact "
             "after the toss, before it touches the floor: with your hands (the parts beyond the wrists; one or "
             "both), overhead (the ball's centre above the top of your head, which is {head_top_m} m above your "
             "waist joint along the trunk), after the ball has passed its highest point, all contacts within "
             "{strike_max_s} s, over when the ball has been clear of you for {clear_s} s. It must be a set, not a "
             "rebound: the ball leaves your hands moving upward and at least {set_gain} times as fast as it was "
             "just before they touched it. Then the ball's centre must rise at least {rise_above_net_m} m above "
             "the net's top, and the ball must come down in the outside hitter's target: its first contact with "
             "the floor is inside a circle of {target_radius_m} m radius whose centre is {target_off_net_m} m from "
             "the net on your side and {target_from_side_line_m} m inside the side line ahead of you. That is the "
             "success. You fail if the ball touches the floor before your set, if any part of you other than a hand "
             "touches the ball, if the ball's centre is not above the top of your head when your hands first touch "
             "it, if you touch it before it has passed its highest point, if the contacts last longer than "
             "{strike_max_s} s (the ball held), if the ball leaves your hands downward or slower than that, if you "
             "touch the ball again, if it does not rise that high or comes down outside the target, if before your "
             "set your pelvis is farther from the net than the attack line (you left the front zone), if you touch "
             "the net, an antenna or a post, if a foot of yours is on the floor wholly beyond the centre line, if "
             "you fall (your pelvis lower than {fall_z_m} m above the floor, or any part of you other than the feet "
             "on the floor), or after {time_limit_s} s. The ball cannot be gripped, and it cannot be touched while "
             "it waits to be tossed.")
    venue = ("You face +x, along the net, which is 1 m to your right; the back court is to your left. The ball waits "
             "0.9 m above the floor in the back court, 5.5 m to your left and 1.5 m ahead of you. About 3 s after the "
             "start it is tossed; it climbs to about 3.8 m and comes down steeply (about 56 degrees below the "
             "horizontal) at just under 7 m/s, travelling from your left to your right. About 1.36 s after the toss "
             "it is 2.1 m above the floor about 0.25 m in front of your head; untouched it lands beside the centre "
             "line to your right. The hitter's target is painted on the floor 5 m ahead of you.")
    difficulty = ("The hands (rubber fists) have to meet a 7 m/s ball above the head and drive it away faster than it "
                  "came, up to nearly 4 m and 5 m along the net into a 2 m circle, in a contact of a few hundredths "
                  "of a second: the angle and the speed both have to be right, and arms that are only held up return "
                  "the ball too slowly.")

    def configure(self, params):
        super().configure(params)
        self.fall_z = self.p["fall_z_m"]

    # ------------------------------------------------------------------ geometry
    def geometry(self):
        p = self.p
        hw = p["court_width_m"] / 2
        centre, yaw = (hw - p["side_line_behind_m"], -p["net_side_m"]), -math.pi / 2     # +u = -y, v = +x
        return dict(centre=centre, yaw=yaw,
                    target=(centre[0] + hw - p["target_from_side_line_m"], centre[1] + p["target_off_net_m"]),
                    launch=(p["pass_x_m"], p["pass_y_m"], p["pass_z_m"]),
                    vel=(p["pass_vx_m_s"], p["pass_vy_m_s"], p["pass_vz_m_s"]))

    def build(self, sc):
        p, g = self.p, self.geometry()
        build_court(sc, p, g["centre"], g["yaw"])
        sc.disc("target", g["target"], p["target_radius_m"], rgba=(0.95, 0.85, 0.2, 0.55), z=0.0012)
        sc.ball("ball", "volleyball", g["launch"])
        sc.camera("venue", (-5.0, 8.5, 5.5), (2.5, 0.5, 1.2), fovy=60)

    def _ghost(self, w, on: bool):
        """The waiting ball cannot be touched: it has no contacts until it is launched."""
        gid = w.m.geom("ball").id
        w.m.geom_contype[gid], w.m.geom_conaffinity[gid] = (0, 0) if on else (1, 13)

    def reset(self, w):
        w.pin("ball", self.geometry()["launch"])
        self._ghost(w, True)

    # ------------------------------------------------------------------ the referee
    def referee_reset(self, w, ref):
        self.ball = ref.geoms(body="ball")
        self.hands = ref.part("hands")
        self.other = ref.robot_mask & ~self.hands
        self.net = ref.geoms(body="net")
        self.trackers = {"strike": Strike(ref, self.ball, self.p["clear_s"]), "launched": False, "descending": False,
                         "apex": 0.0}

    def before_step(self, w):
        p, g, tr = self.p, self.geometry(), self.trackers
        if not tr["launched"] and w.t >= p["launch_time_s"] - 1e-9:
            tr["launched"] = True
            self._ghost(w, False)
            w.launch("ball", g["launch"], g["vel"])
            w.ref.event("launch", object="ball")

    def head_top(self, w) -> float:
        """The height above the floor of the top of the head (a point of the trunk shell on the trunk's axis)."""
        t = w.robot.torso
        return float(w.d.xpos[t][2] + w.d.xmat[t].reshape(3, 3)[2, 2] * self.p["head_top_m"])

    def substep(self, w, ref):
        p, g, tr = self.p, self.geometry(), self.trackers
        if ref.touching(ref.robot_mask, self.net):
            return ref.fail("the robot touched the net", parts=sorted(ref.parts_touching(self.net)))
        if not tr["launched"]:
            return
        st = tr["strike"]
        b, v = w.pos("ball"), w.vel("ball")
        if st.phase == 0 and v[2] < 0:
            tr["descending"] = True
        if ref.touching(self.ball, self.other):
            return ref.fail("the ball was touched by something other than a hand",
                            parts=sorted(ref.parts_touching(self.ball) - HANDS))
        if ref.touching(self.ball, ref.ground):
            if st.phase == 0:
                return ref.fail("the ball touched the floor before the set")
            if st.phase == 1:
                return ref.fail("the ball touched the floor during the set")
            off = float(np.hypot(b[0] - g["target"][0], b[1] - g["target"][1]))
            ref.metrics["landing_x_m"], ref.metrics["landing_y_m"] = round(float(b[0]), 3), round(float(b[1]), 3)
            ref.metrics["from_target_centre_m"] = round(off, 3)
            if not ref.has("above the net"):
                return ref.fail("the set did not rise high enough above the net", apex_m=round(tr["apex"], 3))
            if off > p["target_radius_m"]:
                return ref.fail("the set came down outside the target", from_target_centre_m=round(off, 3))
            if ref.stage("in the target"):
                ref.succeed()
            return
        if st.phase == 2 and ref.touching(self.ball, self.hands):
            return ref.fail("second touch of the ball")
        ev = st.update(v)
        if ev == "start":
            if not tr["descending"]:
                return ref.fail("the ball was touched before it had passed its highest point")
            top = self.head_top(w)
            if b[2] <= top:
                return ref.fail("the ball was not played overhead", ball_z=round(float(b[2]), 3), head_top_z=round(top, 3))
        if st.phase == 1 and st.duration > p["strike_max_s"]:
            return ref.fail("the ball was held", touch_s=round(st.duration, 3))
        if ev == "end":
            v_in, v_out = st.speeds()
            ref.metrics["speed_in_m_s"], ref.metrics["speed_out_m_s"] = round(v_in, 2), round(v_out, 2)
            if st.v_out[2] <= 0 or v_out < p["set_gain"] * v_in:
                return ref.fail("the ball was not set: it left the hands downward or slower than it came",
                                speed_in=round(v_in, 2), speed_out=round(v_out, 2), up_m_s=round(st.v_out[2], 2))
            ref.stage("set", parts=sorted(st.parts), speed_in=round(v_in, 2), speed_out=round(v_out, 2))
            tr["apex"] = float(b[2])
        if st.phase == 2:
            tr["apex"] = max(tr["apex"], float(b[2]))
            if tr["apex"] >= p["net_height_m"] + p["rise_above_net_m"]:
                ref.stage("above the net")

    def step(self, w, ref):
        p, g, tr = self.p, self.geometry(), self.trackers
        foot = centre_line_fault(w, ref, g["centre"], g["yaw"])
        if foot:
            return ref.fail("a foot wholly beyond the centre line", foot=foot)
        if tr["strike"].phase == 0:
            u = float(to_court(g["centre"], g["yaw"], [w.pelvis()[:2]])[0, 0])
            if u < -p["attack_line_m"]:
                return ref.fail("the setter left the front zone before the set", from_net_m=round(-u, 3))
        ref.metrics["ball_height_m"] = round(float(w.pos("ball")[2]), 3)
        ref.metrics["set_apex_m"] = round(float(tr["apex"]), 3)

    def privileged(self, w):
        p, g = self.p, self.geometry()
        return {"ball": w.pos("ball").tolist(), "ball_velocity": w.vel("ball").tolist(),
                "launched": bool(self.trackers.get("launched")),
                "launch": {"time_s": p["launch_time_s"], "position": list(g["launch"]), "velocity": list(g["vel"])},
                "net": {"y": g["centre"][1], "top": p["net_height_m"]}, "head_top_z": self.head_top(w),
                "target": {"centre": list(g["target"]), "radius": p["target_radius_m"]}}
