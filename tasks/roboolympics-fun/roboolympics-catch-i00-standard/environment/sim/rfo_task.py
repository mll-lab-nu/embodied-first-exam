"""Catch a fly ball: a baseball is launched from 40 m away on a high arc and comes down within 3 m of you; grip it with
a hand before it touches the ground or your body, and keep it. A real fly ball (official ball, drag and lift in air);
the Unitree H1-2."""
import math

from rfo.scene import OFFICIAL
from rfo.task import TaskBase

BALL = OFFICIAL["baseball"]                    # 9 to 9.25 in round, 5 to 5.25 oz; drag and Magnus lift in air
LEGAL = {"left_hand", "right_hand", "left_forearm", "right_forearm"}


class Task(TaskBase):
    name = "catch"
    title = "Baseball: catch a fly ball"
    category = "throwing-catching-striking"
    robot = "unitree_h1"
    rulebook = ("Official Baseball Rules (MLB, 2024 edition): 3.01 (the ball), Definitions of Terms: \"catch\" (secure "
                "possession in the hand before the ball touches the ground, held long enough to show control), \"in "
                "flight\"")
    deviations = [
        "Definitions (catch): no glove; the hand catches by a grip that closes on a ball whose surface is within "
        "3.5 cm of the palm and that moves no faster than 6 m/s relative to it (the platform's grip). \"Held long "
        "enough\" is {hold_s} s without letting go and without falling. A ball that touches the body (any part other "
        "than the hands and forearms) before it is gripped is not a catch here (the rule would allow it).",
        "The fly ball is not batted: a launcher {launch_distance_m} m away sends it at {launch_speed_m_s} m/s, "
        "{launch_elevation_deg} degrees above the horizon, {launch_time_s} s after the start, without spin; where "
        "it comes down (within {land_within_m} m of where you stand) is this instance's draw.",
        "Flight: quasi-steady aerodynamics (MuJoCo's ellipsoid fluid model: drag and Magnus lift), still air.",
    ]
    time_limit_s = 9.0
    start = (0.0, 0.0, 0.0)
    stages = ["catch", "hold"]
    fall_z = 0.50
    # the launch speed and azimuth are measured (tests/test_catch.py): with drag the ball lands 1.28 m from the robot
    params = dict(launch_time_s=1.0, launch_distance_m=40.0, launch_height_m=1.0, launch_speed_m_s=21.35,
                  launch_elevation_deg=45.0, launch_azimuth_deg=1.18, land_within_m=3.0, hold_s=1.0,
                  fall_pelvis_m=0.50)

    sentence = ("Catch the fly ball: grip the baseball with a hand before it touches the ground or your body, and "
                "keep hold of it.")
    rules = ("A baseball (" + f"{2 * BALL['radius']:.3f} m across, {BALL['mass']:.3f} kg" + ", it flies in air with "
             "drag) rests on a launcher {launch_distance_m} m in front of you, {launch_height_m} m above the ground, "
             "and is launched at t = {launch_time_s} s at {launch_speed_m_s} m/s, {launch_elevation_deg} degrees above "
             "the horizon, {launch_azimuth_deg} degrees to the left of the line from the launcher to you, so that "
             "untouched it would come down within {land_within_m} m of where you stand at the start. A catch is a "
             "hand's grip closing on the ball in flight after it has passed the top of its arc: the grip holds a ball "
             "whose surface is within 3.5 cm of the palm and that moves no faster than 6 m/s relative to it. Before "
             "the grip the ball may touch only your hands and forearms. You succeed when a hand has gripped the ball "
             "and kept it for {hold_s} s without a break. You fail if the ball touches the ground, or any part of you "
             "other than a hand or a forearm, before it is gripped; if you let go of it after the catch; if you fall "
             "(your pelvis lower than {fall_pelvis_m} m above the ground, or any part of you other than your feet on "
             "the ground) before the end; or after {time_limit_s} s.")
    venue = ("You stand on a level field facing the launcher (+x), {launch_distance_m} m away. The ball rises to "
             "about 11 m and comes down steeply, about three seconds after the launch, somewhere within "
             "{land_within_m} m of you. Nothing can be gripped before the launch. Still air.")
    difficulty = ("The ball is in the air for three seconds and comes down at about 17 m/s more than a metre away: "
                  "the body has to walk there at 0.6 m/s and put a palm on the ball's line to within a few "
                  "centimetres, facing it, with the grip closing in the few milliseconds in which the ball is "
                  "against the palm.")

    def launch_state(self):
        p = self.p
        e, a = math.radians(p["launch_elevation_deg"]), math.radians(p["launch_azimuth_deg"])
        v = p["launch_speed_m_s"]
        pos = (p["launch_distance_m"], 0.0, p["launch_height_m"])
        # towards the robot (-x); a positive azimuth turns the flight to the launcher's left: towards -y
        vel = (-v * math.cos(e) * math.cos(a), -v * math.cos(e) * math.sin(a), v * math.sin(e))
        return pos, vel

    def build(self, sc):
        p = self.p
        self.fall_z = p["fall_pelvis_m"]
        x, z = p["launch_distance_m"], p["launch_height_m"]
        sc.disc("field_mark", (0.0, 0.0), p["land_within_m"], rgba=(0.95, 0.95, 0.95, 0.18))
        sc.box("launcher", (x + 0.3, 0.0, (z - 0.06) / 2), (0.25, 0.25, (z - 0.06) / 2), rgba=(0.3, 0.3, 0.33, 1))
        sc.ball("ball", "baseball", (x, 0.0, z), grippable=True)
        sc.camera("venue", (-5.0, -7.0, 3.0), (8.0, 0.0, 3.0), fovy=60)

    def reset(self, w):
        w.pin("ball", self.launch_state()[0])

    def referee_reset(self, w, ref):
        self.ball = ref.geoms(body="ball")
        self.robot = ref.part("robot")
        self.other = self.robot & ~ref.part("hands", "forearms")
        self.trackers = {"launched": False, "falling": False, "caught": None}

    def before_step(self, w):
        tr = self.trackers
        if not tr["launched"] and w.t >= self.p["launch_time_s"] - 1e-9:
            tr["launched"] = True
            pos, vel = self.launch_state()
            w.launch("ball", pos, vel)
            w.ref.event("launch")

    def may_grip(self, w, side, name):
        return bool(self.trackers.get("falling")) and self.trackers.get("caught") is None

    def substep(self, w, ref):
        tr = self.trackers
        if not tr["launched"]:
            return
        if not tr["falling"]:
            tr["falling"] = bool(w.vel("ball")[2] < 0.0)      # past the top of its arc
        held = bool(w.holder("ball"))
        if tr["caught"] is None:
            if held:
                tr["caught"] = ref.time
                ref.metrics["catch_height_m"] = round(float(w.pos("ball")[2]), 3)
                ref.stage("catch", hand=w.holder("ball")[0])
            elif ref.touching(self.ball, ref.ground):
                p = w.pos("ball")
                ref.metrics["landed_from_start_m"] = round(float(math.hypot(p[0] - self.start[0], p[1] - self.start[1])), 3)
                ref.fail("the ball touched the ground", x=round(float(p[0]), 3), y=round(float(p[1]), 3))
            elif ref.touching(self.ball, self.other):
                ref.fail("the ball touched the body before it was gripped", parts=sorted(ref.parts_touching(self.ball) - LEGAL))
            elif not tr["falling"] and ref.touching(self.ball, self.robot):
                ref.fail("the ball was touched before it had passed the top of its arc")
        elif not held:
            ref.fail("the ball was dropped after the catch")

    def step(self, w, ref):
        if ref.has("catch") and ref.hold("hold", bool(w.holder("ball")), self.p["hold_s"]):
            if ref.stage("hold"):
                ref.succeed()

    def privileged(self, w):
        pos, vel = self.launch_state()
        return {"ball": w.pos("ball").tolist(), "ball_velocity": w.vel("ball").tolist(), "held_by": w.holder("ball"),
                "launched": bool(self.trackers.get("launched")), "launch_time_s": self.p["launch_time_s"],
                "launch_position": list(pos), "launch_velocity": list(vel)}
