"""Volley shot: a cross from the wing comes down at the penalty mark; strike it with a foot before it bounces, into the
official goal 11 m away, past a goalkeeper dummy."""
import numpy as np

from rfo.referee import MouthPass
from rfo.scene import OFFICIAL
from rfo.task import TaskBase

BALL = OFFICIAL["football"]
GRASS = (0.16, 0.50, 0.20, 1)


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


class Task(TaskBase):
    name = "volley-shot"
    title = "Football: volley shot"
    category = "football-and-volleyball"
    robot = "unitree_h1"
    rulebook = ("IFAB Laws of the Game 2025/26: Law 1 (the goal 7.32 m x 2.44 m with posts and crossbar 12 cm wide, the "
                "penalty mark 11 m from the goal line, the penalty area, the goal area), Law 2 (a size-5 ball: 68-70 cm "
                "round, 410-450 g), Law 10 (a goal: the whole ball over the goal line between the posts and under the "
                "bar), Law 12 (handball), Law 13 (9.15 m from the ball until it is in play) and the glossary (a kick is "
                "a contact with the foot or the ankle)")
    deviations = [
        "The cross is a scripted launch: a fixed lofted kick with backspin from a point {cross_distance_m} m away on "
        "the left wing, the same in every attempt, instead of a team-mate.",
        "The goalkeeper is a dummy, a rigid board {keeper_height_m} m high and {keeper_width_m} m wide that stands "
        "still on the goal line at the centre of the goal: an opponent cannot be simulated.",
        "A volley is judged by numbers instead of a referee's eye: every contact within {strike_max_s} s of the first "
        "is the one strike, and a strike is a ball that leaves the foot at least {strike_gain} times as fast as it "
        "arrived (a ball that only rebounds from a leg held in its path leaves slower: it is not a shot).",
        "Law 13's distance is applied to the robot itself: until the cross is played it stays {keep_away_m} m from "
        "the ball, so that the cross is played, not met at the kicker.",
        "The Laws allow any number of touches and any part but the arms; the task is narrower than the Laws: one "
        "touch, with a foot or an ankle only, before the cross touches the ground (the task is a volley, not open "
        "play).",
        "Law 1: only the goal end of the field is there; the goal's net is a rigid cage {goal_depth_m} m deep; no "
        "wind, no other player.",
    ]
    time_limit_s = 10.0
    start = (0.0, 0.0, 0.0)
    stages = ["volley", "goal"]
    fall_z = 0.35
    params = dict(goal_width_m=7.32, goal_height_m=2.44, post_m=0.12, goal_depth_m=2.0, mark_distance_m=11.0,
                  keeper_height_m=1.9, keeper_width_m=0.6, keeper_depth_m=0.3, cross_distance_m=20.0, keep_away_m=9.15,
                  strike_max_s=0.15, clear_s=0.03, strike_gain=1.0, rest_speed_m_s=0.1, rest_s=1.0, fall_z_m=0.35,
                  launch_time_s=3.0, launch_x_m=6.0, launch_y_m=19.079, launch_vx_m_s=-3.240, launch_vy_m_s=-11.386,
                  launch_vz_m_s=8.289, launch_wx_rad_s=-28.85, launch_wy_rad_s=8.21)

    sentence = ("Volley the cross: strike the football that is crossed to you from the wing with a foot before it "
                "touches the ground, into the official goal 11 m away, past the goalkeeper dummy.")
    rules = ("You stand on the penalty mark, facing the goal; the goal line is {mark_distance_m} m ahead of you. The "
             "goal is {goal_width_m} m wide between the posts and {goal_height_m} m high under the crossbar (posts and "
             "bar {post_m} m thick), centred on the line you face along. A goalkeeper dummy, a board "
             "{keeper_height_m} m high, {keeper_width_m} m wide and {keeper_depth_m} m thick, stands still on the goal "
             "line at the centre of the goal. A size-5 football (0.22 m across, 0.43 kg, in air) waits on the ground "
             "on the left wing, {cross_distance_m} m from you, and {launch_time_s} s after the start it is crossed: a "
             "lofted ball with backspin that comes down in front of you. The volley is the ball's first contact "
             "after the cross: with a foot or an ankle of yours (the parts below the shin), before the ball has "
             "touched the ground. Every contact within {strike_max_s} s of the first belongs to the one strike, which "
             "is over when the ball has been clear of you for {clear_s} s; and it must be a strike: the ball's speed "
             "when it leaves your foot is at least {strike_gain} times its speed just before the foot touched it. "
             "You succeed at the moment the whole ball is then over the goal line between the posts and under the "
             "bar; after the strike it may touch the ground, the posts, the bar and the dummy. You fail if the ball "
             "touches the ground before your strike, if any part of you other than a foot or an ankle touches the "
             "ball at any time, if the strike's contacts last longer than {strike_max_s} s, if the ball leaves the "
             "foot slower than that, if you touch the ball again after the strike, if the whole ball crosses the "
             "goal line outside the goal, if after the strike the ball has been slower than {rest_speed_m_s} m/s for "
             "{rest_s} s, if your pelvis comes within {keep_away_m} m of the waiting ball before it is crossed, if "
             "you fall (your pelvis lower than {fall_z_m} m above the ground, or any part of you other than the feet "
             "on the ground), or after {time_limit_s} s. The waiting ball cannot be touched.")
    venue = ("You face the goal (+x) from the penalty mark. The ball waits on the ground about 6 m ahead of you and "
             "19 m to your left. About 3 s after the start it is crossed; it climbs to a little over 4 m and comes "
             "down steeply (about 40 degrees below the horizontal) at roughly 11.5 m/s, travelling mostly from your "
             "left to your right. About 2 s after the cross it is knee-high about 0.6 m in front of you, a little to "
             "your left; untouched it lands about half a metre in front of you, on the side of your right foot.")
    difficulty = ("The ball crosses the reach of a leg in a few hundredths of a second, at 11 m/s and at right angles "
                  "to the goal: the foot has to meet it in the air with a swing of its own, fast enough that the ball "
                  "leaves faster than it came, aimed 11 m into the goal and beside the dummy, by a 67 kg robot on one "
                  "leg whose walking policy has no kick.")

    def configure(self, params):
        super().configure(params)
        self.fall_z = self.p["fall_z_m"]

    # ------------------------------------------------------------------ geometry
    def geometry(self):
        p = self.p
        return dict(goal_x=p["mark_distance_m"], half=p["goal_width_m"] / 2, post_r=p["post_m"] / 2,
                    launch=(p["launch_x_m"], p["launch_y_m"], BALL["radius"]),
                    vel=(p["launch_vx_m_s"], p["launch_vy_m_s"], p["launch_vz_m_s"]),
                    spin=(p["launch_wx_rad_s"], p["launch_wy_rad_s"], 0.0))

    def build(self, sc):
        p, g = self.p, self.geometry()
        gx = g["goal_x"]
        sc.box("pitch", (gx / 2 - 4.0, 0, 0.0003), (gx / 2 + 8.0, 26.0, 0.0003), rgba=GRASS)
        sc.line("goal_line", (gx, -26.0), (gx, 26.0), width=p["post_m"])
        for name, depth, half in (("penalty_area", 16.5, 20.16), ("goal_area", 5.5, 9.16)):   # Law 1
            sc.line(f"{name}_front", (gx - depth, -half), (gx - depth, half), width=0.12)
            for s in (1, -1):
                sc.line(f"{name}_side{s}", (gx - depth, s * half), (gx, s * half), width=0.12)
        sc.disc("penalty_mark", (gx - 11.0, 0.0), 0.11, rgba=(1, 1, 1, 1))
        self.goal = sc.goal("goal", gx, 0.0, width=p["goal_width_m"], height=p["goal_height_m"], depth=p["goal_depth_m"],
                            post=g["post_r"])
        sc.box("keeper", (gx, 0.0, p["keeper_height_m"] / 2), (p["keeper_depth_m"] / 2, p["keeper_width_m"] / 2,
                                                              p["keeper_height_m"] / 2), rgba=(0.95, 0.75, 0.1, 1), solid="hit")
        sc.ball("ball", "football", g["launch"])
        sc.camera("venue", (-7.0, -9.0, 5.0), (gx - 4.0, 3.0, 0.5), fovy=60)

    def _ghost(self, w, on: bool):
        """The waiting ball cannot be touched: it has no contacts until it is launched."""
        gid = w.m.geom("ball").id
        w.m.geom_contype[gid], w.m.geom_conaffinity[gid] = (0, 0) if on else (1, 13)

    def reset(self, w):
        w.pin("ball", self.geometry()["launch"])
        self._ghost(w, True)

    # ------------------------------------------------------------------ the referee
    def referee_reset(self, w, ref):
        p, g = self.p, self.geometry()
        self.ball = ref.geoms(body="ball")
        self.foot = (ref.geoms(body="left_ankle_pitch_link") | ref.geoms(body="right_ankle_pitch_link")) & ref.robot_mask
        self.other = ref.robot_mask & ~self.foot
        self.trackers = {
            "strike": Strike(ref, self.ball, p["clear_s"]),
            "mouth": MouthPass((g["goal_x"] + g["post_r"], 0.0), 0.0, g["half"], 0.0, p["goal_height_m"], BALL["radius"]),
            "launched": False, "up": False,
        }

    def before_step(self, w):
        p, g, tr = self.p, self.geometry(), self.trackers
        if not tr["launched"] and w.t >= p["launch_time_s"] - 1e-9:
            tr["launched"] = True
            self._ghost(w, False)
            w.launch("ball", g["launch"], g["vel"], angvel=g["spin"])
            w.ref.event("launch", object="ball")

    def substep(self, w, ref):
        p, tr = self.p, self.trackers
        if not tr["launched"]:
            return
        st = tr["strike"]
        if ref.touching(self.ball, self.other):
            return ref.fail("the ball was touched by something other than a foot", parts=sorted(ref.parts_touching(self.ball)))
        if not tr["up"]:                                 # the cross is kicked off the ground: it has left it
            tr["up"] = bool(w.pos("ball")[2] > BALL["radius"] + 0.05)
        elif st.phase == 0 and ref.touching(self.ball, ref.ground):
            return ref.fail("the ball touched the ground before the strike")
        if st.phase == 2 and ref.touching(self.ball, self.foot):
            return ref.fail("second touch of the ball")
        ev = st.update(w.vel("ball"))
        if st.phase == 1 and st.duration > p["strike_max_s"]:
            return ref.fail("the ball was carried", touch_s=round(st.duration, 3))
        if ev == "end":
            v_in, v_out = st.speeds()
            ref.metrics["speed_in_m_s"], ref.metrics["speed_out_m_s"] = round(v_in, 2), round(v_out, 2)
            if v_out < p["strike_gain"] * v_in:
                return ref.fail("the ball was not struck: it left the foot slower than it came",
                                speed_in=round(v_in, 2), speed_out=round(v_out, 2))
            ref.stage("volley", parts=sorted(st.parts), speed_in=round(v_in, 2), speed_out=round(v_out, 2))
        hit = tr["mouth"].update(w.pos("ball"))
        if hit is not None and not ref.has("volley"):
            return ref.fail("the ball crossed the goal line without a volley")
        if hit == "in":
            if ref.stage("goal"):
                ref.succeed()
        elif hit == "wide":
            ref.fail("the ball crossed the goal line outside the goal")

    def step(self, w, ref):
        p, g, tr = self.p, self.geometry(), self.trackers
        b = w.pos("ball")
        ref.metrics["ball_x_m"] = round(float(b[0]), 3)
        if not tr["launched"]:
            pel = w.pelvis()
            if float(np.hypot(pel[0] - g["launch"][0], pel[1] - g["launch"][1])) < p["keep_away_m"]:
                ref.fail("too close to the ball before the cross")
            return
        if ref.has("volley") and ref.hold("rest", float(np.linalg.norm(w.vel("ball"))) < p["rest_speed_m_s"], p["rest_s"]):
            ref.fail("the ball came to rest without a goal")

    def privileged(self, w):
        g = self.geometry()
        return {"ball": w.pos("ball").tolist(), "ball_velocity": w.vel("ball").tolist(),
                "launched": bool(self.trackers.get("launched")), "goal": self.goal,
                "launch": {"time_s": self.p["launch_time_s"], "position": list(g["launch"]), "velocity": list(g["vel"]),
                           "spin_rad_s": list(g["spin"])},
                "keeper": {"y": 0.0, "half_width": self.p["keeper_width_m"] / 2, "height": self.p["keeper_height_m"]}}
