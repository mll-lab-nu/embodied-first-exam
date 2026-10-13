"""Juggle three balls: a three-ball cascade. Two balls start in the right hand and one in the left; every ball is
thrown from one hand in an arc to the other; ten catches in a row in the cascade's order, no ball on the ground. The
Unitree G1."""
import math

import mujoco
import numpy as np

from rfo.task import TaskBase

BALLS = ("ball_a", "ball_b", "ball_c")         # the order in which they are caught: a, b, c, a, ...
COLOURS = ((0.90, 0.20, 0.20, 1), (0.20, 0.55, 0.90, 1), (0.95, 0.80, 0.15, 1))
PALM_OFFSET = 0.022 + 0.003                    # the palm face of the fist's pad, and a gap, from the wrist mount's axis
FOREARMS_LEVEL = -0.29                         # the elbows' angle of t = 0: the forearms level, the palms up
OTHER = {"left": "right", "right": "left"}
G = 9.81


def set_arm(w, **angles) -> None:
    """Put arm joints (names without "_joint") at angles for t = 0, and their held targets with them."""
    r, d = w.robot, w.d
    for name, v in angles.items():
        i = w.L.JOINTS.index(name + "_joint")
        d.qpos[r.qadr[i]] = v
        r.arb.q_a[i] = r.arb.q_b[i] = v
    mujoco.mj_kinematics(w.m, d)


class Task(TaskBase):
    name = "juggle-three"
    title = "Juggling: a three-ball cascade"
    category = "throwing-catching-striking"
    robot = "unitree_g1"
    rulebook = ("No rule book: the three-ball cascade as jugglers define and count it (siteswap 3; the International "
                "Jugglers' Association counts a run in catches): each ball is thrown from one hand and caught by the "
                "other, the hands throw in turn, the balls follow one another in a fixed order; a run ends with a "
                "drop")
    deviations = [
        "A hand holds one ball at a time by a grip switched on and off (it closes on a ball whose surface is within "
        "3.5 cm of the palm and that moves no faster than 6 m/s relative to it), so \"two balls in one hand at the "
        "start\" is modelled: the first of the two (the red ball) waits {waiting_above_palm_m} m above the right "
        "palm and is thrown by the venue at t = {launch_time_s} s, on an arc that rises {first_throw_rise_m} m and "
        "comes down on where the left palm is at the start. Until then it may not be touched.",
        "A throw is a release after which the ball, touching nothing, rises at least {min_rise_m} m above where it "
        "was let go; a hand-to-hand pass is not a throw. So that a ball laid on the other hand and lifted is not "
        "one, the rise counts only until the ball first touches you again, and from that first touch the other "
        "hand has {catch_window_s} s to grip it.",
        "The balls are spheres of a juggling ball's size and mass with a soft bounce; they fly in air (MuJoCo's "
        "ellipsoid fluid model: drag, a quasi-steady model), still air.",
    ]
    time_limit_s = 20.0
    start = (0.0, 0.0, 0.0)
    stages = ["first catch", "half way", "ten catches"]
    params = dict(ball_diameter_m=0.07, ball_mass_kg=0.13, catches=10, min_rise_m=0.30, launch_time_s=2.0,
                  first_throw_rise_m=0.50, waiting_above_palm_m=0.14, retouch_grace_s=0.10, catch_window_s=0.15, fall_pelvis_m=0.35)

    sentence = ("Juggle three balls in a cascade: throw each ball from one hand in an arc to the other, the hands in "
                "turn, until {catches} catches have been made in a row.")
    rules = ("Three balls ({ball_diameter_m} m across, {ball_mass_kg} kg). At the start your forearms are level, the "
             "palms up; the blue ball is gripped on your left palm, the yellow ball on your right palm, and the red "
             "ball waits {waiting_above_palm_m} m above your right palm: it stands for the second ball of the right "
             "hand and is thrown for you at t = {launch_time_s} s, on an arc that rises {first_throw_rise_m} m and "
             "comes down on where your left palm is at the start. Before that it may not be touched (by you or by a "
             "ball you hold). A hand grips one ball at a time: its grip closes on a ball whose surface is within "
             "3.5 cm of the palm and that moves no faster than 6 m/s relative to it. A throw: a hand lets go of its "
             "ball and the ball, touching nothing but air, rises at least {min_rise_m} m above the point where it was "
             "let go; only the rise before the ball first touches you again counts. A catch: a hand grips a ball "
             "that has been thrown by the other hand (the red ball's first throw counts as the right hand's), at "
             "the latest {catch_window_s} s after the ball first touched you again. The cascade's order: the catches alternate between the hands, the "
             "left hand first, and take the balls in the order red, blue, yellow, red, ... You succeed at the "
             "{catches}th catch. You fail if a ball touches the ground; if a ball in flight touches any part of you "
             "other than a hand, or still touches the hand that threw it later than {retouch_grace_s} s after the "
             "release; if a ball is gripped by the hand that let go of it, or before it has risen {min_rise_m} m; if "
             "a ball that has touched a hand again is not gripped within {catch_window_s} s (it rests on the "
             "hand or bounces off it); if "
             "a catch is out of the cascade's order (the wrong hand or the wrong ball); if the waiting ball is "
             "touched before its launch; if you fall (your pelvis lower than {fall_pelvis_m} m above the ground, or "
             "any part of you other than your feet on the ground); or after {time_limit_s} s.")
    venue = ("You stand on level ground, nothing around you. Your forearms point forwards, level, the palms up, about "
             "0.38 m apart; a ball lies gripped on each, and the red ball hangs above the yellow one over your right "
             "palm until it is thrown towards your left hand. A ball is released when its hand's grip is switched "
             "off.")
    difficulty = ("Each throw has to land on a palm a few centimetres wide 0.4 m away, about 0.6 s later, and "
                  "the catching hand must have thrown its own ball before: three balls, two hands, never two in one. "
                  "Errors add up from throw to throw, because a ball is thrown from wherever it was caught.")

    def build(self, sc):
        p = self.p
        self.fall_z = p["fall_pelvis_m"]
        sc.box("mat", (0.2, 0, 0.0003), (1.2, 1.2, 0.0003), rgba=(0.25, 0.35, 0.55, 1))
        for name, rgba in zip(BALLS, COLOURS):
            sc.ball(name, "baseball", (0.3, 0.0, 0.5), grippable=True, radius=p["ball_diameter_m"] / 2,
                    mass=p["ball_mass_kg"], bounce=0.30, drag=0.47, rgba=rgba)
        sc.camera("venue", (2.1, -1.6, 1.4), (0.15, 0.0, 0.95), fovy=50)

    def reset(self, w):
        p, d = self.p, w.d
        r = p["ball_diameter_m"] / 2
        set_arm(w, left_elbow=FOREARMS_LEVEL, right_elbow=FOREARMS_LEVEL)
        palms = {}
        for side, name in (("left", "ball_b"), ("right", "ball_c")):
            b = w.robot.mount[side]
            R = d.xmat[b].reshape(3, 3)
            w.put(name, d.xpos[b] + R @ np.array([-(PALM_OFFSET + r), 0.0, 0.045]))
            w.grab(side, name, event=False)
            palms[side] = d.site_xpos[w.robot.palm[side]].copy()
        # the red ball's launch: from above the right palm to the left palm's place, over an apex first_throw_rise_m up
        p0 = palms["right"] + [0.0, 0.0, p["waiting_above_palm_m"]]
        target = palms["left"] + [0.0, 0.0, 0.022 + r]
        vz = math.sqrt(2 * G * p["first_throw_rise_m"])
        T = (vz + math.sqrt(vz * vz + 2 * G * max(float(p0[2] - target[2]), 0.0))) / G
        self.launch = (p0.copy(), np.array([(target[0] - p0[0]) / T, (target[1] - p0[1]) / T, vz]))
        w.pin("ball_a", p0)

    # ------------------------------------------------------------------ the referee
    def referee_reset(self, w, ref):
        self.geom = {n: ref.geoms(body=n) for n in BALLS}
        self.robot = ref.part("robot")
        self.hands = {s: ref.part(f"{s}_hand") for s in ("left", "right")}
        self.not_hands = self.robot & ~ref.part("hands")
        # per ball: where it is ("waiting", "held", "flight"), who holds or threw it, the release height and time, apex
        self.trackers = {"launched": False, "catches": 0,
                         "ball_a": {"at": "waiting", "by": "right", "z0": 0.0, "t0": 0.0, "rise": 0.0, "met": None},
                         "ball_b": {"at": "held", "by": "left", "z0": 0.0, "t0": 0.0, "rise": 0.0, "met": None},
                         "ball_c": {"at": "held", "by": "right", "z0": 0.0, "t0": 0.0, "rise": 0.0, "met": None}}

    def before_step(self, w):
        tr = self.trackers
        if not tr["launched"] and w.t >= self.p["launch_time_s"] - 1e-9:
            tr["launched"] = True
            pos, vel = self.launch
            w.launch("ball_a", pos, vel)
            tr["ball_a"].update(at="flight", by="right", z0=float(pos[2]), t0=w.ref.time, rise=0.0, met=None)
            w.ref.event("launch", ball="ball_a")

    def substep(self, w, ref):
        tr, p = self.trackers, self.p
        for name in BALLS:
            st, g = tr[name], self.geom[name]
            if st["at"] == "waiting":
                if ref.touching(g, ~g):
                    return ref.fail("the waiting ball was touched before its launch")
                continue
            holder = w.holder(name)
            z = float(w.pos(name)[2])
            if st["at"] == "held":
                if not holder:                                 # let go: a throw begins
                    st.update(at="flight", z0=z, t0=ref.time, rise=0.0, met=None)
                continue
            # in flight
            if holder:
                hand = holder[0]
                k = tr["catches"] + 1
                if hand == st["by"]:
                    return ref.fail("a ball was gripped by the hand that let go of it", ball=name, hand=hand)
                if st["rise"] < p["min_rise_m"]:
                    return ref.fail("a ball was gripped before it had made its flight", ball=name, rise_m=round(st["rise"], 3))
                if name != BALLS[(k - 1) % 3] or hand != ("left" if k % 2 else "right"):
                    return ref.fail("a catch out of the cascade's order", ball=name, hand=hand, catch=k)
                tr["catches"] = k
                st.update(at="held", by=hand)
                ref.event("catch", n=k, ball=name, hand=hand, rise_m=round(st["rise"], 3))
                ref.metrics["catches"] = k
                if k == 1:
                    ref.stage("first catch")
                if k == (p["catches"] + 1) // 2:
                    ref.stage("half way")
                if k == p["catches"] and ref.stage("ten catches"):
                    ref.succeed()
                continue
            if ref.touching(g, ref.ground):
                return ref.fail("a ball touched the ground", ball=name)
            if ref.touching(g, self.not_hands):
                return ref.fail("a ball in flight touched the body", ball=name,
                                parts=sorted(ref.parts_touching(g) - {"left_hand", "right_hand"}))
            if ref.time - st["t0"] > p["retouch_grace_s"] and ref.touching(g, self.hands[st["by"]]):
                return ref.fail("a ball in flight was touched again by the hand that threw it", ball=name)
            # met: when the ball first touched the robot again (after the release's grace): its flight is over
            if st["met"] is None:
                if not ref.touching(g, self.robot):
                    st["rise"] = max(st["rise"], z - st["z0"])
                elif ref.time - st["t0"] > p["retouch_grace_s"]:
                    st["met"] = ref.time
            elif ref.time - st["met"] > p["catch_window_s"]:
                return ref.fail("a ball that came down on a hand was not caught", ball=name,
                                rise_m=round(st["rise"], 3))

    def privileged(self, w):
        tr = self.trackers
        pos, vel = self.launch
        return {"balls": {n: {"position": w.pos(n).tolist(), "velocity": w.vel(n).tolist(), "held_by": w.holder(n),
                              "state": tr[n]["at"]} for n in BALLS},
                "catches": tr["catches"], "next_ball": BALLS[tr["catches"] % 3],
                "next_hand": "left" if (tr["catches"] + 1) % 2 else "right",
                "launch_time_s": self.p["launch_time_s"], "launch_position": pos.tolist(), "launch_velocity": vel.tolist()}
