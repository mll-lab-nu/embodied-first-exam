"""Catch a fly ball with real grasping: catch's fly ball (a baseball launched from 40 m away on a high arc that comes
down within 3 m of you), but both hands of the Unitree H1-2 are Unitree Dex1-1 two-jaw grippers and nothing is
welded: a catch is the jaws of one gripper closing on the ball (the baseball, 73 mm, fits the 90 mm stroke), and the
ball is held only by the friction of the jaws' pads, so it can slip out, turn and drop. A real fly ball (official
ball, drag and lift in air).

Everything but the hold is catch's (shared/rfo/tasks/catch.py, copied: the launch, the flight, the rule book, the
numbers); what is new: the real grippers (rfo/realhand.py), the catch as a clamp of both jaws' pads, the window from
the ball's first touch to the clamp, and the hold by those jaws alone."""
import math

import numpy as np

from rfo.scene import OFFICIAL
from rfo.task import TaskBase

BALL = OFFICIAL["baseball"]                    # 9 to 9.25 in round, 5 to 5.25 oz; drag and Magnus lift in air
LEGAL = {"left_hand", "right_hand", "left_forearm", "right_forearm"}
SIDES = ("left", "right")


def pinched(w, ball: int, pads, centre: int, cos_max: float) -> bool:
    """Both jaws' pads (two geom masks) touch the geom `ball` with a contact normal within acos(cos_max) of the
    closing axis of the jaw frame (the site `centre`), in this physics step's contacts."""
    d = w.d
    n = d.ncon
    g = d.contact.geom[:n]
    keep = d.contact.dist[:n] <= 0.0
    x = d.site_xmat[centre].reshape(3, 3)[:, 0]
    for pad in pads:
        sel = keep & (((g[:, 0] == ball) & pad[g[:, 1]]) | ((g[:, 1] == ball) & pad[g[:, 0]]))
        if not np.any(np.abs(d.contact.frame[:n][sel, :3] @ x) >= cos_max):
            return False
    return True


class Task(TaskBase):
    name = "catch-realgrasp"
    title = "Baseball: catch a fly ball, real grasp"
    category = "throwing-catching-striking"
    robot = "unitree_h1"
    rulebook = ("Official Baseball Rules (MLB, 2024 edition): 3.01 (the ball), Definitions of Terms: \"catch\" (secure "
                "possession in the hand before the ball touches the ground, held long enough to show control), \"in "
                "flight\"")
    deviations = [
        "Definitions (catch): no glove; both hands are Unitree's Dex1-1 two-jaw grippers (sold for the G1, the H2 and "
        "the R1, not for the H1-2; mounted on the wrist where the H1-2's palm ends): 90 mm stroke, jaws 80 mm long "
        "and 34 mm wide with rubber pads, at most 120 N of grip, opening and closing at most 375 mm/s. A catch is the "
        "pads of both jaws of one gripper pressing on the ball from its two sides at the same time (each with a "
        "contact whose direction is within {max_contact_angle_deg} degrees of the jaws' closing direction: the jaws "
        "closed on it, not a ball lying on their tips or edges), at the latest {catch_window_s} s after the ball "
        "first touched you; \"held long enough\" is {hold_s} s in which the ball "
        "stays between the pads of that gripper (breaks of at most {hold_gap_s} s) and touches nothing else, without "
        "falling. Nothing is welded: the ball is held only by the pads' friction and can slip out.",
        "Definitions (catch): a ball that touches the body (any part other than the grippers and the forearms) before "
        "it is caught is not a catch here (the rule would allow trapping it against the body), and neither is a ball "
        "held at the end by anything but the jaws of the gripper that caught it (the other hand, a forearm, the body).",
        "The fly ball is not batted: a launcher {launch_distance_m} m away sends it at {launch_speed_m_s} m/s, "
        "{launch_elevation_deg} degrees above the horizon, {launch_time_s} s after the start, without spin; where "
        "it comes down (within {land_within_m} m of where you stand) is this instance's draw.",
        "Flight: quasi-steady aerodynamics (MuJoCo's ellipsoid fluid model: drag and Magnus lift), still air.",
    ]
    time_limit_s = 9.0
    start = (0.0, 0.0, 0.0)
    stages = ["catch", "hold"]
    fall_z = 0.50
    # the launch is catch's (measured there: with drag the ball lands 1.28 m from the robot)
    params = dict(launch_time_s=1.0, launch_distance_m=40.0, launch_height_m=1.0, launch_speed_m_s=21.35,
                  launch_elevation_deg=45.0, launch_azimuth_deg=1.18, land_within_m=3.0, hold_s=1.0,
                  catch_window_s=0.5, hold_gap_s=0.02, max_contact_angle_deg=45.0, fall_pelvis_m=0.50)

    sentence = ("Catch the fly ball: close the jaws of one of your grippers on the baseball before it touches the "
                "ground or your body, and keep it there.")
    rules = ("A baseball (" + f"{2 * BALL['radius']:.3f} m across, {BALL['mass']:.3f} kg" + ", it flies in air with "
             "drag) rests on a launcher {launch_distance_m} m in front of you, {launch_height_m} m above the ground, "
             "and is launched at t = {launch_time_s} s at {launch_speed_m_s} m/s, {launch_elevation_deg} degrees above "
             "the horizon, {launch_azimuth_deg} degrees to the left of the line from the launcher to you, so that "
             "untouched it would come down within {land_within_m} m of where you stand at the start. Both your hands "
             "are two-jaw grippers (90 mm stroke, jaws 80 mm long with rubber pads on their inner faces, at most 120 N "
             "of grip) that hold things only by friction; they start open. A catch: the pads of both jaws of one "
             "gripper touch the ball at the same time from its two sides, each with a contact whose direction is "
             "within {max_contact_angle_deg} degrees of the jaws' closing direction (a ball lying on the jaws' tips "
             "or edges, or on closed jaws, is not caught), after the ball has passed the top of its arc and at the latest "
             "{catch_window_s} s after it first touched you. Before the catch the ball may touch only your grippers "
             "and forearms. You succeed when, from the catch, the ball has stayed between the pads of that gripper "
             "for {hold_s} s (both pads touching it in that way, apart from breaks of at most {hold_gap_s} s) touching nothing "
             "but that gripper. You fail if the ball touches the ground, or any part of you other than a gripper or a "
             "forearm, before the catch; if it is touched before it has passed the top of its arc; if it is not "
             "caught within {catch_window_s} s of first touching you; if after the catch it is out of the jaws for "
             "longer than {hold_gap_s} s (dropped, slipped out or let go: a ball caught again does not count) or "
             "touches anything but the gripper that caught it (your other gripper, a forearm, your body, the "
             "ground); if you fall (your pelvis lower than {fall_pelvis_m} m above the ground, or any part of you "
             "other than your feet on the ground) before the end; or after {time_limit_s} s.")
    venue = ("You stand on a level field facing the launcher (+x), {launch_distance_m} m away. The ball rises to "
             "about 11 m and comes down steeply, about three seconds after the launch, somewhere within "
             "{land_within_m} m of you. Your grippers are open, their jaws pointing forwards along your forearms. "
             "Still air.")
    difficulty = ("The ball is in the air for three seconds and comes down at about 17 m/s more than a metre away: "
                  "the body has to walk there at 0.6 m/s and bring a gripper whose open jaws leave 8 mm on each side "
                  "of the ball onto its line, and the jaws need about 40 ms to close on it, while a ball that meets "
                  "the gripper at that speed bounces off it in a few milliseconds.")

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
        sc.real_hands["left"] = sc.real_hands["right"] = "dex1"
        x, z = p["launch_distance_m"], p["launch_height_m"]
        sc.disc("field_mark", (0.0, 0.0), p["land_within_m"], rgba=(0.95, 0.95, 0.95, 0.18))
        sc.box("launcher", (x + 0.3, 0.0, (z - 0.06) / 2), (0.25, 0.25, (z - 0.06) / 2), rgba=(0.3, 0.3, 0.33, 1))
        sc.ball("ball", "baseball", (x, 0.0, z))                 # nothing grippable: no weld, only the jaws' friction
        sc.camera("venue", (-5.0, -7.0, 3.0), (8.0, 0.0, 3.0), fovy=60)

    def reset(self, w):
        w.pin("ball", self.launch_state()[0])

    # ------------------------------------------------------------------ the referee
    def referee_reset(self, w, ref):
        self.ball = ref.geoms(body="ball")
        self.ball_geom = w.m.geom("ball").id
        self.cos_max = math.cos(math.radians(self.p["max_contact_angle_deg"]))
        self.robot = ref.part("robot")
        self.other = self.robot & ~ref.part("hands", "forearms")
        self.hand = {s: ref.part(f"{s}_hand") for s in SIDES}
        self.pads = {s: (ref.geoms(prefix=f"{s}_hand_pad_a"), ref.geoms(prefix=f"{s}_hand_pad_b")) for s in SIDES}
        self.not_hand = {s: ~(self.ball | self.hand[s]) for s in SIDES}
        # first_touch: when the ball first touched you; caught: the side whose jaws hold it; clamp_t: the last time
        # both of that side's pads touched it
        self.trackers = {"launched": False, "falling": False, "first_touch": None, "caught": None, "clamp_t": None}

    def clamped(self, w, ref, side) -> bool:
        """The jaws closed on the ball: the pads of both jaws touch it from the two sides, each with a contact whose
        normal is within max_contact_angle_deg of the jaws' closing axis (a ball lying on the jaws' tips or edges,
        or on the closed jaws, is not between them)."""
        a, b = self.pads[side]
        if not (ref.touching(self.ball, a) and ref.touching(self.ball, b)):
            return False
        return pinched(w, self.ball_geom, (a, b), w.hands.centre[side], self.cos_max)

    def before_step(self, w):
        tr = self.trackers
        if not tr["launched"] and w.t >= self.p["launch_time_s"] - 1e-9:
            tr["launched"] = True
            pos, vel = self.launch_state()
            w.launch("ball", pos, vel)
            w.ref.event("launch")

    def substep(self, w, ref):
        tr, p = self.trackers, self.p
        if not tr["launched"]:
            return
        if not tr["falling"]:
            tr["falling"] = bool(w.vel("ball")[2] < 0.0)      # past the top of its arc
        side = tr["caught"]
        if side is None:
            if ref.touching(self.ball, ref.ground):
                q = w.pos("ball")
                ref.metrics["landed_from_start_m"] = round(float(math.hypot(q[0] - self.start[0], q[1] - self.start[1])), 3)
                return ref.fail("the ball touched the ground", x=round(float(q[0]), 3), y=round(float(q[1]), 3))
            if ref.touching(self.ball, self.other):
                return ref.fail("the ball touched the body before it was caught",
                                parts=sorted(ref.parts_touching(self.ball) - LEGAL))
            if not ref.touching(self.ball, self.robot):
                if tr["first_touch"] is not None and ref.time - tr["first_touch"] > p["catch_window_s"]:
                    return ref.fail("the ball was not caught in time after it first touched you",
                                    since_first_touch_s=round(ref.time - tr["first_touch"], 3))
                return
            if not tr["falling"]:
                return ref.fail("the ball was touched before it had passed the top of its arc")
            if tr["first_touch"] is None:
                tr["first_touch"] = round(ref.time, 4)
            if ref.time - tr["first_touch"] > p["catch_window_s"]:
                return ref.fail("the ball was not caught in time after it first touched you",
                                since_first_touch_s=round(ref.time - tr["first_touch"], 3))
            for s in SIDES:
                if self.clamped(w, ref, s):
                    tr["caught"], tr["clamp_t"] = s, round(ref.time, 4)
                    q = w.pos("ball")
                    ref.metrics["catch_height_m"] = round(float(q[2]), 3)
                    ref.metrics["catch_speed_m_s"] = round(float(math.sqrt(sum(v * v for v in w.vel("ball")))), 3)
                    ref.stage("catch", hand=s, after_first_touch_s=round(ref.time - tr["first_touch"], 4))
                    return
            return
        if self.clamped(w, ref, side):
            tr["clamp_t"] = round(ref.time, 4)
        elif ref.time - tr["clamp_t"] > p["hold_gap_s"] + 1e-9:
            return ref.fail("the ball came out of the jaws after the catch", out_s=round(ref.time - tr["clamp_t"], 4))
        if ref.touching(self.ball, self.not_hand[side]):
            parts = sorted(ref.parts_touching(self.ball) - {f"{side}_hand"})
            return ref.fail("after the catch the ball touched something other than the gripper that caught it",
                            parts=parts, ground=ref.touching(self.ball, ref.ground))

    def step(self, w, ref):
        tr, p = self.trackers, self.p
        if ref.has("catch") and tr["caught"] is not None:
            held = ref.time - tr["clamp_t"] <= p["hold_gap_s"] + 1e-9
            if ref.hold("hold", held, p["hold_s"]) and ref.stage("hold"):
                ref.succeed()

    def privileged(self, w):
        pos, vel = self.launch_state()
        tr = self.trackers
        return {"ball": w.pos("ball").tolist(), "ball_velocity": w.vel("ball").tolist(), "caught_by": tr.get("caught"),
                "held_by": w.holder("ball"), "launched": bool(tr.get("launched")),
                "launch_time_s": self.p["launch_time_s"], "launch_position": list(pos), "launch_velocity": list(vel),
                "grippers": w.hands.state() if w.hands else {}}
