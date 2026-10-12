"""Volleyball spike: a set comes down half a metre from the net at position 4; jump, strike it with a hand above the
height of the 2.43 m net and put it down in the opponent's court, without touching the net or crossing the centre
line."""
import math

import numpy as np

from rfo.referee import Crossing, Flights
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
    name = "volleyball-spike"
    title = "Volleyball: spike"
    category = "football-and-volleyball"
    robot = "unitree_h1"
    rulebook = ("FIVB Official Volleyball Rules 2025-2028: Rule 1 (the court 18 m x 9 m, the attack lines), Rule 2 (the "
                "men's net, top at 2.43 m, the antennas), Rule 3 (the ball: 65-67 cm round, 260-280 g), Rule 8 (ball in "
                "and out: the lines belong to the court; a ball that touches an antenna or crosses outside the "
                "crossing space is out), Rule 9.2 (the hit: not caught or thrown, one contact), Rule 10.2 (the ball "
                "may touch the net), Rule 11.2-11.3 (the foot not wholly beyond the centre line; no contact with the "
                "net), Rule 13 (the attack hit)")
    deviations = [
        "The set is a scripted launch from the setter's place at position 2/3: a ball without spin that rises to "
        "4.5 m and comes down {set_off_net_m} m from the net at position 4, the same in every attempt, instead of a "
        "team-mate.",
        "The family asks for the spike, where Rule 13 allows any attack hit: the ball is struck with a hand (the "
        "parts beyond the wrist) at a point above the height of the net's top, while the robot is in the air in a "
        "jump (its pelvis rises at least {jump_rise_m} m above where it was when the feet left the floor: drawing "
        "the legs up is not a jump), after the ball has passed its highest point, and the ball leaves the hand "
        "moving downward and at least {spike_gain} times as fast as it arrived (a hand held in the ball's path "
        "returns it slower). 'Not caught or thrown' is a contact of at most {strike_max_s} s.",
        "Rule 11 is judged for the whole attempt, until the robot has landed and stood for {stand_s} s after the "
        "ball is down: there is no rally to end the play.",
        "No blockers or defenders, no wind.",
    ]
    time_limit_s = 12.0
    start = (0.0, 0.0, 0.0)
    stages = ["spike", "over the net", "in the court", "landing"]
    fall_z = 0.35
    params = dict(court_half_length_m=9.0, court_width_m=9.0, net_height_m=2.43, attack_line_m=3.0, net_distance_m=3.0,
                  side_line_left_m=1.0, set_off_net_m=0.5, jump_rise_m=0.10, spike_gain=1.0, strike_max_s=0.10,
                  clear_s=0.03, stand_s=1.0, fall_z_m=0.35, launch_time_s=3.0, set_x_m=2.0, set_y_m=-5.0, set_z_m=2.3,
                  set_vx_m_s=0.4315, set_vy_m_s=4.3151, set_vz_m_s=6.8071)

    sentence = ("Spike the set: jump and strike the volleyball that comes down near the net with a hand, above the "
                "height of the net, down into the opponent's court, and land on your feet without touching the net.")
    rules = ("You are the outside hitter on an official volleyball court ({court_half_length_m} m by {court_width_m} m "
             "on each side of the net; the net's top {net_height_m} m high, an antenna above each side line). You "
             "stand on your attack line facing the net, which is {net_distance_m} m ahead of you; the left side line "
             "is {side_line_left_m} m to your left. A volleyball (0.21 m across, 0.27 kg, in air) is set from your "
             "right {launch_time_s} s after the start: it rises to 4.5 m and comes down {set_off_net_m} m from the "
             "net, in front of you. In order: (1) the spike: the ball's first contact after the set, before it "
             "touches the floor, is with a hand of yours (the parts beyond the wrist; one or both), after the ball "
             "has passed its highest point, at points that are all higher than the net's top, while you are in the "
             "air (nothing of you touches the floor or anything else) in a jump: during that flight your pelvis "
             "rises at least {jump_rise_m} m above the height it had when your feet left the floor. All contacts "
             "lie within {strike_max_s} s (the strike is over when the ball has been clear of you for {clear_s} s), "
             "and the ball leaves your hand moving downward and at least {spike_gain} times as fast as it was just "
             "before the hand touched it. (2) the ball crosses the net's plane above the net and between the "
             "antennas; it may touch the net. (3) the ball's first contact with the floor is in the opponent's court "
             "({court_half_length_m} m by {court_width_m} m, lines included); from then on the ball is dead and what "
             "it touches is not judged. (4) after that you stand for "
             "{stand_s} s without a break (only your feet on the floor, your trunk within about 20 degrees of "
             "upright, your pelvis slower than 0.35 m/s): that is the success. You fail if the ball touches the "
             "floor before the spike, if any part of you other than a hand touches it, if you touch it before it "
             "has passed its highest point, from the floor, below the height of the net's top, or in a flight in "
             "which your pelvis did not rise {jump_rise_m} m, if the contacts last longer than {strike_max_s} s, if "
             "the ball leaves the hand upward or slower than that, if you touch the ball again, if it crosses the "
             "net's plane under the net or outside the antennas or touches an antenna, if it lands anywhere else, "
             "if you touch the net, an antenna or a post at any time, if a foot of yours is on the floor wholly "
             "beyond the centre line, if you fall (your pelvis lower than {fall_z_m} m above the floor, or any part "
             "of you other than the feet on the floor), or after {time_limit_s} s. The ball cannot be gripped, and "
             "it cannot be touched while it waits to be set.")
    venue = ("You face the net (+x) from the attack line. The ball waits 2.3 m above the floor at the setter's place, "
             "1 m from the net and 5 m to your right. About 3 s after the start it is set towards you along the net; "
             "it reaches 4.5 m and comes down at about 57 degrees below the horizontal and 6 to 7 m/s, still moving "
             "to your left. About 1.26 s after the set it is 2.8 m above the floor, 2.5 m ahead of where you stand "
             "and straight in front of you, half a metre from the net; about 0.07 s later it is down to the height "
             "of the net's top, and untouched it lands just outside the left side line.")
    difficulty = ("The robot reaches 2.24 m standing: its hand has to be above 2.43 m, so it must jump at least a "
                  "quarter of a metre, after an approach of about 2 m on a walking policy, and swing through a ball "
                  "that falls through the reachable window in under a tenth of a second, half a metre from a net it "
                  "may not touch, then land a 67 kg body on its feet. No jumping skill is built in.")

    def configure(self, params):
        super().configure(params)
        self.fall_z = self.p["fall_z_m"]

    # ------------------------------------------------------------------ geometry
    def geometry(self):
        p = self.p
        return dict(centre=(p["net_distance_m"], p["side_line_left_m"] - p["court_width_m"] / 2), yaw=0.0,
                    launch=(p["set_x_m"], p["set_y_m"], p["set_z_m"]),
                    vel=(p["set_vx_m_s"], p["set_vy_m_s"], p["set_vz_m_s"]))

    def build(self, sc):
        p, g = self.p, self.geometry()
        build_court(sc, p, g["centre"], g["yaw"])
        sc.ball("ball", "volleyball", g["launch"])
        sc.camera("venue", (-4.5, -9.5, 5.0), (g["centre"][0], -2.0, 1.3), fovy=60)

    def _ghost(self, w, on: bool):
        """The waiting ball cannot be touched: it has no contacts until it is launched."""
        gid = w.m.geom("ball").id
        w.m.geom_contype[gid], w.m.geom_conaffinity[gid] = (0, 0) if on else (1, 13)

    def reset(self, w):
        w.pin("ball", self.geometry()["launch"])
        self._ghost(w, True)

    # ------------------------------------------------------------------ the referee
    def referee_reset(self, w, ref):
        g = self.geometry()
        self.ball = ref.geoms(body="ball")
        self.hands = ref.part("hands")
        self.other = ref.robot_mask & ~self.hands
        self.net = ref.geoms(body="net")
        self.antennas = ref.geoms(prefix="net_antenna")
        self.trackers = {"strike": Strike(ref, self.ball, self.p["clear_s"]),
                         "flights": Flights(ref, min_air=0.0, also_allowed=self.ball),
                         "plane": Crossing((1, 0, 0), g["centre"][0], direction=1),
                         "launched": False, "descending": False, "lowest_contact_m": None, "in_strike_flight": False, "cross": None,
                         "jump_ok": False, "rise": 0.0}

    def before_step(self, w):
        p, g, tr = self.p, self.geometry(), self.trackers
        if not tr["launched"] and w.t >= p["launch_time_s"] - 1e-9:
            tr["launched"] = True
            self._ghost(w, False)
            w.launch("ball", g["launch"], g["vel"])
            w.ref.event("launch", object="ball")

    def substep(self, w, ref):
        p, g, tr = self.p, self.geometry(), self.trackers
        fl = tr["flights"]
        landed = fl.update()                                # the flight that has just ended, if any
        if landed is not None and tr["in_strike_flight"]:
            tr["in_strike_flight"] = False
            tr["rise"] = round(landed["apex_z"] - landed["pelvis0"][2], 4)
            ref.metrics["jump_rise_m"], ref.metrics["air_s"] = tr["rise"], landed["air_s"]
            if tr["rise"] < p["jump_rise_m"]:
                return ref.fail("the strike was not made in a jump", pelvis_rise_m=tr["rise"], air_s=landed["air_s"])
            tr["jump_ok"] = True
        if ref.touching(ref.robot_mask, self.net):
            return ref.fail("the robot touched the net", parts=sorted(ref.parts_touching(self.net)))
        if not tr["launched"] or ref.has("in the court"):   # the ball is dead once it has landed in the court
            return
        st = tr["strike"]
        b, v = w.pos("ball"), w.vel("ball")
        if st.phase == 0 and v[2] < 0:
            tr["descending"] = True
        if ref.touching(self.ball, self.other):
            return ref.fail("the ball was touched by something other than a hand",
                            parts=sorted(ref.parts_touching(self.ball) - HANDS))
        if ref.touching(self.ball, self.antennas):
            return ref.fail("the ball touched an antenna")
        if st.phase == 2 and ref.touching(self.ball, self.hands):
            return ref.fail("second touch of the ball")
        pts = ref.contact_points(self.ball, self.hands)
        if len(pts):
            low = float(np.min(pts[:, 2]))
            tr["lowest_contact_m"] = low if tr["lowest_contact_m"] is None else min(tr["lowest_contact_m"], low)
        ev = st.update(v)
        if ev == "start":
            if not tr["descending"]:
                return ref.fail("the ball was touched before it had passed its highest point")
            if not fl.air:
                return ref.fail("the ball was struck from the floor",
                                on=sorted(ref.parts_touching(~ref.robot_mask & ~self.ball)))
            tr["in_strike_flight"] = True
        if st.phase == 1:
            if tr["lowest_contact_m"] is not None and tr["lowest_contact_m"] <= p["net_height_m"]:
                return ref.fail("the ball was struck below the height of the net", contact_z=round(tr["lowest_contact_m"], 3))
            if st.duration > p["strike_max_s"]:
                return ref.fail("the ball was held", touch_s=round(st.duration, 3))
        if ev == "end":
            v_in, v_out = st.speeds()
            ref.metrics["speed_in_m_s"], ref.metrics["speed_out_m_s"] = round(v_in, 2), round(v_out, 2)
            ref.metrics["contact_height_m"] = round(tr["lowest_contact_m"], 3)
            if st.v_out[2] >= 0 or v_out < p["spike_gain"] * v_in:
                return ref.fail("the ball was not spiked: it left the hand upward or slower than it came",
                                speed_in=round(v_in, 2), speed_out=round(v_out, 2), down_m_s=round(-st.v_out[2], 2))
            ref.stage("spike", parts=sorted(st.parts), speed_in=round(v_in, 2), speed_out=round(v_out, 2),
                      contact_z=round(tr["lowest_contact_m"], 3))
        x = tr["plane"].update(b)
        if x is not None and tr["cross"] is None:
            tr["cross"] = [float(x[1]), float(x[2])]
        if tr["cross"] is not None and not ref.has("over the net"):
            if st.phase == 0:
                return ref.fail("the ball crossed the net without a spike")
            if ref.has("spike"):                            # (a fast ball is over the net before the strike is judged)
                y, z = tr["cross"]
                if z < p["net_height_m"] or abs(y - g["centre"][1]) > p["court_width_m"] / 2:
                    return ref.fail("the ball did not cross above the net between the antennas", y=round(y, 3), z=round(z, 3))
                ref.stage("over the net", z=round(z, 3))
        if ref.touching(self.ball, ref.ground) and not ref.has("in the court"):
            if not ref.has("spike"):
                return ref.fail("the ball touched the floor before the spike")
            u, vv = to_court(g["centre"], g["yaw"], [b])[0]
            ref.metrics["landing_x_m"], ref.metrics["landing_y_m"] = round(float(b[0]), 3), round(float(b[1]), 3)
            if ref.has("over the net") and 0.0 <= u <= p["court_half_length_m"] and abs(vv) <= p["court_width_m"] / 2:
                ref.stage("in the court")
            else:
                ref.fail("the ball landed outside the opponent's court", x=round(float(b[0]), 3), y=round(float(b[1]), 3))

    def step(self, w, ref):
        p, g, tr = self.p, self.geometry(), self.trackers
        foot = centre_line_fault(w, ref, g["centre"], g["yaw"])
        if foot:
            return ref.fail("a foot wholly beyond the centre line", foot=foot)
        ref.metrics["ball_height_m"] = round(float(w.pos("ball")[2]), 3)
        if ref.has("in the court") and tr["jump_ok"] and ref.hold("stand", ref.standing(), p["stand_s"]):
            if ref.stage("landing"):
                ref.succeed()

    def privileged(self, w):
        p, g = self.p, self.geometry()
        return {"ball": w.pos("ball").tolist(), "ball_velocity": w.vel("ball").tolist(),
                "launched": bool(self.trackers.get("launched")),
                "launch": {"time_s": p["launch_time_s"], "position": list(g["launch"]), "velocity": list(g["vel"])},
                "net": {"x": g["centre"][0], "top": p["net_height_m"]},
                "court": {"x": [g["centre"][0], g["centre"][0] + p["court_half_length_m"]],
                          "y": [g["centre"][1] - p["court_width_m"] / 2, g["centre"][1] + p["court_width_m"] / 2]}}
