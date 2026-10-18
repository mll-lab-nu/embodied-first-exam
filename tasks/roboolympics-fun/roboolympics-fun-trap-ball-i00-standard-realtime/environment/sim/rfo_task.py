"""Trap a pass: a ground pass from 15 m at 8 m/s goes by half a metre to one side; take it with a foot and have it at
rest within a metre of you inside three seconds."""
import numpy as np

from rfo.scene import OFFICIAL
from rfo.task import TaskBase

BALL = OFFICIAL["football"]
GRASS = (0.16, 0.50, 0.20, 1)
ARMS = {"left_upper_arm", "left_forearm", "left_hand", "right_upper_arm", "right_forearm", "right_hand"}


class Task(TaskBase):
    name = "trap-ball"
    title = "Football: trap a pass"
    category = "football-and-volleyball"
    robot = "unitree_h1"
    rulebook = ("IFAB Laws of the Game 2025/26: Law 2 (a size-5 ball: 68-70 cm round, 410-450 g), Law 12 (handball: the "
                "hand or the arm), Law 13 (9.15 m from the ball until it is in play) and the glossary (a kick is a "
                "contact with the foot or the ankle). Receiving a pass is a skill, not a rule-book event: the pass and "
                "the control standard (first touch with a foot, the ball at rest within 1 m inside 3 s) are "
                "the benchmark's")
    deviations = [
        "The pass is a scripted launch: a ball that rolls without slipping at {pass_speed_m_s} m/s from "
        "{pass_distance_m} m, the same in every attempt, instead of a team-mate; the pitch is level and uniform "
        "(the official ball's rolling resistance, no bobble), no wind.",
        "Law 13's distance is applied to the robot itself: until the pass is played it stays {keep_away_m} m from "
        "the ball, so that the pass is played, not met at the passer.",
    ]
    time_limit_s = 10.0
    start = (0.0, 0.0, 0.0)
    stages = ["first touch", "control"]
    fall_z = 0.35
    params = dict(pass_distance_m=15.0, pass_speed_m_s=8.0, pass_side_m=0.5, control_m=1.0, control_s=3.0,
                  rest_speed_m_s=0.2, rest_s=0.5, keep_away_m=9.15, fall_z_m=0.35, launch_time_s=3.0)

    sentence = ("Trap the pass: take the football that is passed along the ground past you with a foot, and bring it "
                "to rest within a metre of you inside three seconds.")
    rules = ("A size-5 football (0.22 m across, 0.43 kg) waits on the ground {pass_distance_m} m ahead of you and "
             "{pass_side_m} m to your right; {launch_time_s} s after the start it is passed along the ground, "
             "rolling at {pass_speed_m_s} m/s, parallel to the way you face, so that it goes by {pass_side_m} m to "
             "the right of where you stand. Your first touch must be with a foot or an ankle (the parts below the "
             "shin). After it you may play the ball as often as you like with any part of you except the hands and "
             "the arms. You succeed when, within {control_s} s of the first touch, the ball is under control: "
             "slower than {rest_speed_m_s} m/s for {rest_s} s without a break, its centre all that time within "
             "{control_m} m of your pelvis (measured along the ground), you on your feet. You fail if the first part "
             "of you that the ball touches is not a foot or an ankle, if a hand or an arm touches the ball at any "
             "time (handball), if {control_s} s after the first touch the ball is not under control, if your pelvis "
             "comes within {keep_away_m} m of the waiting ball before it is passed, if you fall (your pelvis lower "
             "than {fall_z_m} m above the ground, or any part of you other than the feet on the ground), or after "
             "{time_limit_s} s. The waiting ball cannot be touched.")
    venue = ("You face +x on level grass. The ball waits 15 m ahead of you, half a metre to the right of the line you "
             "face along. About 3 s after the start it is passed straight back along that line; it reaches you "
             "about 2.1 s later, still rolling at about 6 m/s, half a metre to the right of your pelvis (about "
             "0.35 m outside your right foot).")
    difficulty = ("A foot has to be in the way of a 6 m/s ball at the right hundredth of a second, half a metre to "
                  "the side, and it has to take the pace off: a ball that hits a planted foot bounces a few metres "
                  "away, far outside the metre, and the walking policy cannot catch a ball that is faster than it.")

    def configure(self, params):
        super().configure(params)
        self.fall_z = self.p["fall_z_m"]

    def geometry(self):
        p, r = self.p, BALL["radius"]
        v = p["pass_speed_m_s"]
        # rolling without slipping from the first moment, towards -x
        return dict(launch=(p["pass_distance_m"], -p["pass_side_m"], r), vel=(-v, 0.0, 0.0), spin=(0.0, -v / r, 0.0))

    def build(self, sc):
        p, g = self.p, self.geometry()
        D = p["pass_distance_m"]
        sc.box("pitch", (D / 2, 0, 0.0003), (D / 2 + 6.0, 8.0, 0.0003), rgba=GRASS)
        sc.disc("you", (0.0, 0.0), 0.11, rgba=(1, 1, 1, 0.8))
        sc.disc("passer", (D, -p["pass_side_m"]), 0.11, rgba=(1, 1, 1, 0.8))
        sc.disc("control", (0.0, 0.0), p["control_m"], rgba=(1, 1, 1, 0.18))
        sc.ball("ball", "football", g["launch"])
        sc.camera("venue", (-4.0, -5.0, 3.0), (5.0, 0.0, 0.3), fovy=60)

    def _ghost(self, w, on: bool):
        """The waiting ball cannot be touched: it has no contacts until it is launched."""
        gid = w.m.geom("ball").id
        w.m.geom_contype[gid], w.m.geom_conaffinity[gid] = (0, 0) if on else (1, 13)

    def reset(self, w):
        w.pin("ball", self.geometry()["launch"])
        self._ghost(w, True)

    def referee_reset(self, w, ref):
        self.ball = ref.geoms(body="ball")
        self.foot = (ref.geoms(body="left_ankle_pitch_link") | ref.geoms(body="right_ankle_pitch_link")) & ref.robot_mask
        self.arms = ref.part("arms")
        self.trackers = {"launched": False, "touch_t": None, "touches": 0, "on": False}

    def before_step(self, w):
        p, g, tr = self.p, self.geometry(), self.trackers
        if not tr["launched"] and w.t >= p["launch_time_s"] - 1e-9:
            tr["launched"] = True
            self._ghost(w, False)
            w.launch("ball", g["launch"], g["vel"], angvel=g["spin"])
            w.ref.event("launch", object="ball")

    def substep(self, w, ref):
        tr = self.trackers
        if not tr["launched"]:
            return
        on = ref.touching(self.ball, ref.robot_mask)
        if on:
            parts = ref.parts_touching(self.ball)
            if parts & ARMS:
                return ref.fail("handball", parts=sorted(parts & ARMS))
            if tr["touch_t"] is None:
                if not ref.touching(self.ball, self.foot) or ref.touching(self.ball, ref.robot_mask & ~self.foot):
                    return ref.fail("the first touch was not with a foot", parts=sorted(parts))
                tr["touch_t"] = ref.time
                ref.stage("first touch", parts=sorted(parts),
                          ball_speed_m_s=round(float(np.linalg.norm(w.vel("ball"))), 2))
            if not tr["on"]:
                tr["touches"] += 1
        tr["on"] = on

    def step(self, w, ref):
        p, g, tr = self.p, self.geometry(), self.trackers
        b, pel = w.pos("ball"), w.pelvis()
        if not tr["launched"]:
            if float(np.hypot(pel[0] - g["launch"][0], pel[1] - g["launch"][1])) < p["keep_away_m"]:
                ref.fail("too close to the ball before the pass")
            return
        speed = float(np.linalg.norm(w.vel("ball")))
        dist = float(np.hypot(b[0] - pel[0], b[1] - pel[1]))
        ref.metrics["ball_speed_m_s"] = round(speed, 3)
        ref.metrics["ball_from_pelvis_m"] = round(dist, 3)
        ref.metrics["touches"] = tr["touches"]
        if tr["touch_t"] is None:
            return
        if ref.hold("control", speed < p["rest_speed_m_s"] and dist <= p["control_m"], p["rest_s"]):
            ref.metrics["control_after_s"] = round(ref.time - tr["touch_t"], 2)
            if ref.stage("control"):
                ref.succeed()
        elif ref.time - tr["touch_t"] >= p["control_s"]:
            ref.fail("the ball was not under control in time", ball_from_pelvis_m=round(dist, 3),
                     ball_speed_m_s=round(speed, 3))

    def privileged(self, w):
        g = self.geometry()
        return {"ball": w.pos("ball").tolist(), "ball_velocity": w.vel("ball").tolist(),
                "launched": bool(self.trackers.get("launched")),
                "launch": {"time_s": self.p["launch_time_s"], "position": list(g["launch"]), "velocity": list(g["vel"])}}
