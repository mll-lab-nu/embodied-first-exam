"""Volleyball serve receive: a float serve from behind the far end line comes down beside you; pass it with the
forearms, in one contact, above net height to the setter's target at the net."""
import math

import numpy as np

from rfo.scene import HITTABLE, OFFICIAL, VISUAL, WHITE, quat_z
from rfo.task import TaskBase

BALL = OFFICIAL["volleyball"]
PLATFORM = {"left_forearm", "right_forearm", "left_hand", "right_hand"}


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
    name = "volleyball-bump"
    title = "Volleyball: serve receive"
    category = "football-and-volleyball"
    robot = "unitree_h1"
    rulebook = ("FIVB Official Volleyball Rules 2025-2028: Rule 1 (the court 18 m x 9 m, the attack lines 3 m from the "
                "centre line), Rule 2 (the men's net, top at 2.43 m, the antennas), Rule 3 (the ball: 65-67 cm round, "
                "260-280 g), Rule 9.2 (the hit: the ball may touch any part of the body, it must not be caught or "
                "thrown), Rule 11 (no contact with the net, the foot not wholly beyond the centre line), Rule 14.5 (the "
                "serve may not be blocked)")
    deviations = [
        "Rule 12 (the service): the serve is a scripted launch, a float serve (no spin) of about 14 m/s from "
        "0.6 m behind the far end line, the same in every attempt, instead of an opponent; the ball follows MuJoCo's "
        "drag model, without a float serve's sideways wobble.",
        "Rule 9.2 lets a team-mate play the ball next; here nobody does, and a good reception is defined as volleyball "
        "coaching grades it: the pass rises above the net's height and comes down in the setter's target, a circle of "
        "{target_radius_m} m radius {target_off_net_m} m from the net between positions 2 and 3, judged where the "
        "ball first touches the floor.",
        "The family asks for the forearm pass: only the forearms and the hands (the arm from the elbow down) may touch "
        "the ball, where Rule 9.2.1 allows any part of the body. 'Not caught or thrown' is a contact of at most "
        "{strike_max_s} s (the ball cannot be gripped).",
        "No team-mates or opponents, no wind.",
    ]
    time_limit_s = 10.0
    start = (0.0, 0.0, 0.0)
    stages = ["pass", "above the net height", "in the target"]
    fall_z = 0.35
    params = dict(court_half_length_m=9.0, court_width_m=9.0, net_height_m=2.43, attack_line_m=3.0, net_distance_m=6.0,
                  target_off_net_m=1.0, target_right_m=1.5, target_radius_m=1.0, strike_max_s=0.10, clear_s=0.03,
                  fall_z_m=0.35, launch_time_s=3.0, serve_x_m=15.6, serve_y_m=1.5, serve_z_m=2.6,
                  serve_vx_m_s=-12.622, serve_vy_m_s=-0.687, serve_vz_m_s=6.017)

    sentence = ("Receive the serve: pass the volleyball that is served over the net to you with your forearms, in one "
                "contact, above net height and into the setter's target at the net.")
    rules = ("You stand in your own half of an official volleyball court ({court_half_length_m} m by {court_width_m} m "
             "on each side of the net), facing the net, {net_distance_m} m from it, midway between the side lines. "
             "The net's top is {net_height_m} m high. A volleyball (0.21 m across, 0.27 kg, in air) is served over "
             "the net from behind the far end line {launch_time_s} s after the start: a float serve, without spin, "
             "that comes down in your part of the court. The pass is the ball's first contact after the serve, on "
             "your side of the net and before it touches the floor: with your forearms or hands (one arm or both; "
             "the arm from the elbow down), all contacts within {strike_max_s} s, over when the ball has been clear "
             "of you for {clear_s} s. After it the ball's centre must rise above the height of the net's top, and "
             "the ball must come down in the setter's target: its first contact with the floor is inside a circle "
             "of {target_radius_m} m radius whose centre is {target_off_net_m} m from the net on your side and "
             "{target_right_m} m to the right of the court's middle (to your right as you face the net). That is "
             "the success. You fail if the ball touches the floor before your pass, if any part of you other than a "
             "forearm or a hand touches the ball, if the pass's contacts last longer than {strike_max_s} s (the ball "
             "held), if you touch the ball again after the pass, if you touch the ball before it has crossed the "
             "net, if the ball comes down outside the target or without having risen above the net's height, if you "
             "touch the net, an antenna or a post, if a foot of yours is on the floor wholly beyond the centre line, "
             "if you fall (your pelvis lower than {fall_z_m} m above the floor, or any part of you other than the "
             "feet on the floor), or after {time_limit_s} s. The ball cannot be gripped, and it cannot be touched "
             "while it waits to be served.")
    venue = ("You face the net (+x), which is 6 m ahead of you; your end line is 3 m behind you. The ball waits about "
             "2.6 m above the floor behind the far end line, 15.6 m ahead of you and 1.5 m to your left. About 3 s "
             "after the start it is served at about 14 m/s; it climbs to a little over 4 m, clears the net by more "
             "than a metre and comes down at about 40 degrees below the horizontal and 11 m/s. About 1.4 s after "
             "the serve it is 1 m above the floor about 0.9 m in front of you and 0.7 m to your left; untouched it "
             "lands level with you, about 0.65 m to your left. The setter's target is painted on the floor at the net, ahead of you and "
             "to your right.")
    difficulty = ("The arms have to be made into a platform 0.7 m to the side and in front of where the robot stands, "
                  "within about four seconds of a walking policy that manages half a metre per second sideways, and "
                  "angled so that an 11 m/s ball rebounds 2 m up and 5 m forward into a 2 m circle: a few degrees of "
                  "platform angle are a metre at the target.")

    def configure(self, params):
        super().configure(params)
        self.fall_z = self.p["fall_z_m"]

    # ------------------------------------------------------------------ geometry
    def geometry(self):
        p = self.p
        centre, yaw = (p["net_distance_m"], 0.0), 0.0
        return dict(centre=centre, yaw=yaw,
                    target=(centre[0] - p["target_off_net_m"], -p["target_right_m"]),
                    launch=(p["serve_x_m"], p["serve_y_m"], p["serve_z_m"]),
                    vel=(p["serve_vx_m_s"], p["serve_vy_m_s"], p["serve_vz_m_s"]))

    def build(self, sc):
        p, g = self.p, self.geometry()
        build_court(sc, p, g["centre"], g["yaw"])
        sc.disc("target", g["target"], p["target_radius_m"], rgba=(0.95, 0.85, 0.2, 0.55), z=0.0012)
        sc.ball("ball", "volleyball", g["launch"])
        sc.camera("venue", (-6.5, -9.0, 6.0), (g["centre"][0] - 1.0, 0.0, 1.0), fovy=60)

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
        self.platform = ref.part("forearms", "hands")
        self.other = ref.robot_mask & ~self.platform
        self.net = ref.geoms(body="net")
        self.trackers = {"strike": Strike(ref, self.ball, self.p["clear_s"]), "launched": False, "apex": 0.0}

    def before_step(self, w):
        p, g, tr = self.p, self.geometry(), self.trackers
        if not tr["launched"] and w.t >= p["launch_time_s"] - 1e-9:
            tr["launched"] = True
            self._ghost(w, False)
            w.launch("ball", g["launch"], g["vel"])
            w.ref.event("launch", object="ball")

    def substep(self, w, ref):
        p, g, tr = self.p, self.geometry(), self.trackers
        if ref.touching(ref.robot_mask, self.net):
            return ref.fail("the robot touched the net", parts=sorted(ref.parts_touching(self.net)))
        if not tr["launched"]:
            return
        st = tr["strike"]
        b = w.pos("ball")
        if ref.touching(self.ball, self.other):
            return ref.fail("the ball was touched by something other than a forearm or a hand",
                            parts=sorted(ref.parts_touching(self.ball) - PLATFORM))
        if ref.touching(self.ball, ref.ground):
            if st.phase == 0:
                return ref.fail("the ball touched the floor before the pass")
            if st.phase == 1:
                return ref.fail("the ball touched the floor during the pass")
            off = float(np.hypot(b[0] - g["target"][0], b[1] - g["target"][1]))
            ref.metrics["landing_x_m"], ref.metrics["landing_y_m"] = round(float(b[0]), 3), round(float(b[1]), 3)
            ref.metrics["from_target_centre_m"] = round(off, 3)
            if not ref.has("above the net height"):
                return ref.fail("the pass did not rise above the height of the net", apex_m=round(tr["apex"], 3))
            if off > p["target_radius_m"]:
                return ref.fail("the pass came down outside the target", from_target_centre_m=round(off, 3))
            if ref.stage("in the target"):
                ref.succeed()
            return
        if st.phase == 2 and ref.touching(self.ball, self.platform):
            return ref.fail("second touch of the ball")
        ev = st.update(w.vel("ball"))
        if ev == "start" and float(to_court(g["centre"], g["yaw"], [b])[0, 0]) > -BALL["radius"]:
            return ref.fail("the serve was touched before it had crossed the net")
        if st.phase == 1 and st.duration > p["strike_max_s"]:
            return ref.fail("the ball was held", touch_s=round(st.duration, 3))
        if ev == "end":
            v_in, v_out = st.speeds()
            ref.metrics["speed_in_m_s"], ref.metrics["speed_out_m_s"] = round(v_in, 2), round(v_out, 2)
            ref.stage("pass", parts=sorted(st.parts), touch_s=round(st.duration, 3))
            tr["apex"] = float(b[2])
        if st.phase == 2:
            tr["apex"] = max(tr["apex"], float(b[2]))
            if tr["apex"] > p["net_height_m"]:
                ref.stage("above the net height")

    def step(self, w, ref):
        g = self.geometry()
        foot = centre_line_fault(w, ref, g["centre"], g["yaw"])
        if foot:
            return ref.fail("a foot wholly beyond the centre line", foot=foot)
        ref.metrics["ball_height_m"] = round(float(w.pos("ball")[2]), 3)
        ref.metrics["pass_apex_m"] = round(float(self.trackers["apex"]), 3)

    def privileged(self, w):
        p, g = self.p, self.geometry()
        return {"ball": w.pos("ball").tolist(), "ball_velocity": w.vel("ball").tolist(),
                "launched": bool(self.trackers.get("launched")),
                "launch": {"time_s": p["launch_time_s"], "position": list(g["launch"]), "velocity": list(g["vel"])},
                "net": {"x": g["centre"][0], "top": p["net_height_m"]},
                "target": {"centre": list(g["target"]), "radius": p["target_radius_m"]}}
