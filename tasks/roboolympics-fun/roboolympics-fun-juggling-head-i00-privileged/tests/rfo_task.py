"""Head juggling: a feeder drops a size-5 football onto the robot's head; keep it up with ten headers in a row, the
head only."""
import math

import numpy as np

from rfo.referee import Touch
from rfo.scene import OFFICIAL
from rfo.task import TaskBase

BALL = OFFICIAL["football"]
GRASS = (0.16, 0.50, 0.20, 1)
CONE = (0.98, 0.45, 0.05, 1)


class Task(TaskBase):
    name = "juggling-head"
    title = "Football: head juggling"
    category = "football-and-volleyball"
    robot = "unitree_g1"
    rulebook = ("Ontario Soccer Association, Technical Benchmark Exercises (2015, for U12-U13 players), exercise 1 "
                "'Head Juggling': one attempt, the player in a 5 x 5 yard grid keeps the ball up with the head, each "
                "head juggle one point, the count stopped by the ball touching the ground, by another body part, or "
                "by stepping out of the grid; the benchmark records the count and sets no pass mark, so the family's "
                "standard is 10 consecutive headers (the same standard as the family 'juggling'). IFAB Laws of the "
                "Game 2025/26 for the ball (Law 2: size 5, 68-70 cm round, 410-450 g)")
    deviations = [
        "The start: in the benchmark the ball starts in the player's hands and the player throws it up onto the head; "
        "the robot has fists and no fingers, so a feeder drops the ball instead: it is held still {feed_z_m} m above "
        "the ground over the robot's head and let go at {feed_time_s} s (the same in every attempt). Until then it "
        "cannot be touched.",
        "A counter's eye is replaced by numbers: contacts less than {touch_gap_s} s apart are one touch, a touch may "
        "last at most {carry_s} s, and the ball's centre must then rise at least {rise_m} m (one ball diameter) above "
        "where it was when the touch began, before anything touches it again. The limit on a touch's length is twice "
        "a measured human header's (about 25 ms: Bayly et al., IEEE EMBS 2002, the same subjects as Naunheim et al., "
        "Med Sci Sports Exerc 35:1406-1412, 2003; a size-5 ball's contact with the robot's head lasts about 11 ms), so "
        "that a ball cushioned on the head and pushed up is not a header.",
        "The ball bounces off the robot's hard head shell as off a hard floor (the ball's own restitution from the "
        "rule book's drop test; a still head held by its motors returns about 0.83 of the speed). A human head and "
        "neck are softer: the heading model of Naunheim et al. (2003) takes a restitution of 0.4 to 0.7, but no "
        "measurement of the ball on a live head was found, and the robot's head is not a human's; the simulation "
        "keeps the robot's own contact, so a robot header needs less head speed than a human one (about 0.2 m/s "
        "up against a ball arriving at 3.4 m/s, instead of about 0.7 m/s with 0.6).",
        "A header is a strike: so that a ball that merely bounces on a still head (it returns about 0.8 of its speed, "
        "each bounce lower) is not head juggling, a touch counts only if the ball leaves it with at least "
        "{touch_gain} of the speed it arrived with; the first touch too, because the ball is fed, not thrown up by "
        "the robot. A touch that does not is not counted and is not a fault.",
        "The head: the G1's head is the upper hull of its torso link (the part 'head'); any other part of the robot "
        "touching the ball (the shoulders, the chest, an arm) is another body part.",
        "Stepping out of the grid is judged by the feet: a foot's ankle joint beyond the grid's edge. No wind.",
    ]
    time_limit_s = 60.0                 # the benchmark's 60 s
    start = (0.0, 0.0, 0.0)
    stages = [f"header {i + 1}" for i in range(10)]
    fall_z = 0.35
    legal_ground = ("left_foot", "right_foot")
    params = dict(headers=10, grid_m=4.572, feed_time_s=1.0, feed_x_m=0.0, feed_y_m=0.0, feed_z_m=2.0,
                  rise_m=0.22, carry_s=0.05, touch_gap_s=0.05, touch_gain=0.95, fall_z_m=0.35)

    sentence = ("Juggle the football on your head: a feeder drops it onto your head; keep it in the air with ten "
                "headers in a row, touching it with nothing but your head, without it touching the ground.")
    rules = ("You stand in the middle of a square grid {grid_m} m on a side (5 yards; cones at its corners) on level "
             "grass. A size-5 football (0.22 m across, 0.43 kg, in air) is held still by a feeder {feed_z_m} m above "
             "the ground over your head; it cannot be touched until it is let go, at {feed_time_s} s, when it falls. "
             "From then on, a touch is a contact of the ball with your head (contacts less than {touch_gap_s} s "
             "apart are one touch). A touch is a header that counts when the ball's centre has then risen at least "
             "{rise_m} m above the height it had when the touch began, before anything touches it again, and when "
             "the ball left the touch with at least {touch_gain} of the speed it had just before it (both taken at "
             "the height where the touch began): the head must strike the ball, a ball that only bounces on a still "
             "head leaves slower; such a touch is not counted, and is not a fault. This holds for the first touch "
             "too. You succeed at the moment the {headers}th header counts. You fail if the ball touches the ground, "
             "if any part of you other than the head touches it (the shoulders, the chest, an arm, a hand, a leg), "
             "if one touch lasts longer than {carry_s} s (the ball resting or balanced on the head), if the ball is "
             "touched again before it has risen {rise_m} m, if a foot steps out of the grid (a foot's ankle "
             "joint beyond its edge), if you fall (your pelvis lower than {fall_z_m} m above the ground, or any part "
             "of you other than the feet on the ground), or after {time_limit_s} s.")
    venue = ("You stand at the centre of the {grid_m} m grid facing +x, its edges half that to your front, back "
             "and sides. The ball hangs still above your head (its centre {feed_z_m} m above the ground, over the "
             "point {feed_x_m} m ahead of and {feed_y_m} m to the left of where your pelvis starts) and drops at "
             "{feed_time_s} s; untouched it lands on the top of your head about a third of a second later, at about "
             "3.4 m/s.")
    difficulty = ("Every header must give the falling 0.43 kg ball back more speed than a still head would, so the "
                  "head has to meet it moving up at the right moment, ten times in a row; and the head is round and "
                  "only about 15 cm across, so a contact one centimetre off its top sends the ball sideways at about "
                  "0.3 m/s and a few centimetres off it out of reach, all while the robot keeps its balance.")

    def __init__(self):
        super().__init__()
        self._stages()

    def configure(self, params):
        super().configure(params)
        self._stages()
        self.fall_z = self.p["fall_z_m"]

    def _stages(self):
        self.stages = [f"header {i + 1}" for i in range(int(self.p["headers"]))]

    def feed(self):
        p = self.p
        return np.array([p["feed_x_m"], p["feed_y_m"], p["feed_z_m"]])

    # ------------------------------------------------------------------ the venue
    def build(self, sc):
        h = self.p["grid_m"] / 2
        sc.box("pitch", (0.0, 0.0, 0.0003), (8.0, 8.0, 0.0003), rgba=GRASS)
        for i, (a, b) in enumerate((((-h, -h), (h, -h)), ((h, -h), (h, h)), ((h, h), (-h, h)), ((-h, h), (-h, -h)))):
            sc.line(f"grid_{i}", a, b, width=0.05)
        for i, (x, y) in enumerate(((h, h), (h, -h), (-h, h), (-h, -h))):
            sc.cone(f"cone_{i}", x, y, rgba=CONE)
        sc.ball("ball", "football", tuple(self.feed()))
        sc.camera("venue", (2.4, -2.4, 1.6), (0.0, 0.0, 1.2), fovy=50)

    def _ghost(self, w, on: bool):
        """The waiting ball cannot be touched: it has no contacts until it is let go."""
        gid = w.m.geom("ball").id
        w.m.geom_contype[gid], w.m.geom_conaffinity[gid] = (0, 0) if on else self._col

    def reset(self, w):
        gid = w.m.geom("ball").id
        if not hasattr(self, "_col"):
            self._col = (int(w.m.geom_contype[gid]), int(w.m.geom_conaffinity[gid]))
        w.pin("ball", self.feed())
        self._ghost(w, True)

    # ------------------------------------------------------------------ the referee
    def referee_reset(self, w, ref):
        self.ball = ref.geoms(body="ball")
        self.head = ref.part("head")
        self.other = ref.robot_mask & ~self.head
        self.trackers = {"touch": Touch(ref, self.ball, self.head, gap=self.p["touch_gap_s"]), "fed": None,
                         "count": 0, "bounces": 0, "pending": False, "z_touch": 0.0, "apex": 0.0, "speed": 0.0,
                         "v_in": 0.0}

    def before_step(self, w):
        tr = self.trackers
        if tr["fed"] is None and w.t >= self.p["feed_time_s"] - 1e-9:
            tr["fed"] = round(w.t, 4)
            self._ghost(w, False)
            w.launch("ball", self.feed(), (0.0, 0.0, 0.0))
            w.ref.event("feed", object="ball")

    def substep(self, w, ref):
        p, tr = self.p, self.trackers
        if tr["fed"] is None:
            return
        if ref.touching(self.ball, ref.ground):
            return ref.fail("the ball touched the ground", headers=tr["count"])
        if ref.touching(self.ball, self.other):
            return ref.fail("the ball was touched by a part other than the head",
                            parts=sorted(ref.parts_touching(self.ball) - {"head"}), headers=tr["count"])
        touch = tr["touch"]
        z = float(w.pos("ball")[2])
        speed, tr["speed"] = tr["speed"], float(np.linalg.norm(w.vel("ball")))     # speed: one physics step ago
        if touch.update():                                 # a new touch
            if tr["pending"]:
                return ref.fail("the ball was touched again before it had risen enough",
                                rise_m=round(tr["apex"] - tr["z_touch"], 3), headers=tr["count"])
            tr["pending"], tr["z_touch"], tr["apex"], tr["v_in"] = True, z, z, speed
        if touch.active and touch.duration > p["carry_s"]:
            return ref.fail("the ball was carried", touch_s=round(touch.duration, 3), headers=tr["count"])
        if tr["pending"]:
            tr["apex"] = max(tr["apex"], z)
            if not ref.touching(self.ball, self.head) and z - tr["z_touch"] >= p["rise_m"]:
                tr["pending"] = False
                # the speed the ball left the touch with, at the touch's height (from its energy now: free flight)
                v_out = math.sqrt(max(0.0, tr["speed"] ** 2 + 2 * 9.81 * (z - tr["z_touch"])))
                if v_out < p["touch_gain"] * tr["v_in"]:   # a passive bounce: no header
                    tr["bounces"] += 1
                    ref.event("bounce", speed_in=round(tr["v_in"], 2), speed_out=round(v_out, 2))
                    return
                tr["count"] += 1
                if ref.stage(f"header {tr['count']}", speed_in=round(tr["v_in"], 2), speed_out=round(v_out, 2),
                             touch_s=round(touch.duration, 3)) and tr["count"] >= p["headers"]:
                    ref.succeed()

    def step(self, w, ref):
        tr, h = self.trackers, self.p["grid_m"] / 2
        ref.metrics["headers"] = tr["count"]
        ref.metrics["ball_height_m"] = round(float(w.pos("ball")[2]), 3)
        for s in ("left", "right"):
            f = w.d.site_xpos[w.robot.foot_site[s]]
            if abs(float(f[0])) > h or abs(float(f[1])) > h:
                return ref.fail("stepped out of the grid", foot=s, headers=tr["count"])

    def privileged(self, w):
        return {"ball": w.pos("ball").tolist(), "ball_velocity": w.vel("ball").tolist(),
                "fed": self.trackers.get("fed") is not None, "feed_time_s": self.p["feed_time_s"],
                "feed": self.feed().tolist(), "headers": int(self.trackers.get("count", 0)),
                "grid_half_m": self.p["grid_m"] / 2}
