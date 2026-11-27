"""Round-off: the floor-exercise round-off (FIG): from the feet onto the hands, through the handstand with a half turn
about the body's long axis, and down onto both feet together, landing facing back the way you came; then stand.

Robot: the G1, the robot that can bear its weight on its arms (see the handstand family: 162 N per arm against 25 N m
shoulders; the H1-2 has half the torque per kilogram and wrists that bend 0.47 rad)."""
import math

import numpy as np

from rfo.task import TaskBase


class Task(TaskBase):
    name = "round-off"
    title = "Round-off"
    category = "parkour-apparatus-balance"
    robot = "unitree_g1"
    rulebook = ("FIG Men's Artistic Gymnastics Code of Points 2025-2028: floor exercise, Art. 10.1 (the floor area, "
                "12 m x 12 m), Art. 10.2.1.2a (inside the floor area, the lines included), Art. 10.2.2.6l (a "
                "round-off with a 1/4 turn to land facing forward, the Tinsica, is not permitted: the round-off lands "
                "facing back), Art. 9.2.12-13 (an element through the handstand deviating more than 45 degrees from "
                "it is not recognised), Art. 9.2.17 (landings on the feet, the feet at most 10 cm apart to bring the "
                "heels together); the round-off itself as gymnastics defines it: a half turn with hand support, "
                "the legs joined over the top, both feet landing together facing the direction you came from")
    deviations = [
        "FIG Apparatus Norms, floor: the floor is rigid and level (friction 1.0), not the norm's sprung floor, "
        "because the simulator's ground is rigid and no sourced stiffness of the sprung floor is used here",
        "the hands: the G1 has rubber fists without fingers; any part of the hand may touch the floor",
        "Art. 9.2.17 (feet together at the landing): the robot's legs are 0.24 m apart in its stance and its hips "
        "are not built to close them; a two-foot landing here is both feet touching down within {two_feet_s} s of "
        "each other (judged after every 1 ms physics step; a foot counts as down until it has been off the floor "
        "for more than {foot_gap_s} s), not the feet within 10 cm",
        "the round-off is one continuous element, a half turn through the handstand without a stop (Art. 9.2.12-13 "
        "recognise it through the handstand; a held handstand is another element). The Code sets no time, so here "
        "the hand support, from the moment the feet leave the floor before it to the first foot's touchdown of the "
        "landing, may last at most {hand_support_max_s} s (the number is this benchmark's: a gymnast's round-off "
        "spends a few tenths of a second on the hands; the G1 falling from a straight handstand, its feet over its "
        "hands, needs about 0.6 s to reach the floor with its feet); a kick-up to a handstand and a step down is not "
        "a round-off",
        "a round-off is judged pass or fail, as one element without a run-up requirement or judges: hand support "
        "with the torso within {max_dev_deg} degrees of upside down, a two-foot landing facing back within "
        "{face_dev_deg} degrees, and a stand; height, speed and form are not scored",
    ]
    time_limit_s = 30.0
    start = (0.0, 0.0, 0.0)
    fall_rule = True
    legal_ground = ("left_foot", "right_foot", "left_hand", "right_hand")
    stages = ["hand support", "landing", "stand"]
    params = dict(max_dev_deg=45.0, face_dev_deg=45.0, two_feet_s=0.10, foot_gap_s=0.03, hand_support_max_s=0.70,
                  stand_s=1.0, stand_tilt_deg=20.0,
                  stand_still_m_s=0.35, fall_pelvis_m=0.25, area_m=12.0)

    sentence = ("Do a round-off: go over onto your hands with a half turn, land on both feet together facing back "
                "the way you came, and stand.")
    rules = ("You face +x at the start. The hand support counts when only your hands touch the floor and your torso "
             "is upside down, its long axis (from the pelvis up to the neck) within {max_dev_deg} degrees of "
             "pointing straight down. After it, the landing: your feet come down with no hand on the floor, the "
             "second foot within {two_feet_s} s of the first (both feet together; a foot off the floor again for "
             "more than {foot_gap_s} s before the other is down starts the landing over), the first foot down at "
             "most {hand_support_max_s} s after your feet left the floor for the hand support (one continuous "
             "motion, not a held handstand), and when both feet are down "
             "your pelvis and your torso face back, -x, each within {face_dev_deg} degrees (landing facing +x or "
             "sideways is a cartwheel or a Tinsica, not a round-off). Then you stand for {stand_s} s without a "
             "break: only your feet on the floor, your torso within {stand_tilt_deg} degrees of vertical, your "
             "pelvis slower than {stand_still_m_s} m/s. You fail if any part of you other than your hands and feet "
             "touches the floor or your pelvis is lower than {fall_pelvis_m} m (a fall); if after the hand support "
             "one foot lands and the other does not follow within {two_feet_s} s, or no foot is down "
             "{hand_support_max_s} s after your feet left the floor, or a hand is on the floor when "
             "both feet are down, or you land not facing back; if a hand touches the floor after the landing; if "
             "any part of you touches the floor outside the {area_m} m x {area_m} m floor area; or after "
             "{time_limit_s} s. Before the hand support anything is free (steps, a hop, a hurdle).")
    venue = ("You stand in the middle of a gymnastics floor-exercise area, {area_m} m by {area_m} m, marked by white "
             "lines, flat, level and rigid, with nothing on it; you face +x.")
    difficulty = ("The round-off passes your whole weight over two small fists while the body turns half round in the "
                  "air above them, and ends in a two-foot landing that must stop the rotation: there is no built-in "
                  "action for any of it and the arms' motors give 25 N m.")

    @property
    def fall_z(self):
        return self.p["fall_pelvis_m"]

    def build(self, sc):
        h = self.p["area_m"] / 2
        sc.box("mat", (0.0, 0, 0.0003), (h, h, 0.0003), rgba=(0.25, 0.35, 0.65, 1))
        for i, (a, b) in enumerate((((-h, -h), (h, -h)), ((h, -h), (h, h)), ((h, h), (-h, h)), ((-h, h), (-h, -h)))):
            sc.line(f"area_line{i}", a, b)
        sc.camera("venue", (0.4, -3.8, 1.2), (0.4, 0.0, 0.6), fovy=55)

    def referee_reset(self, w, ref):
        self.min_upright = math.cos(math.radians(self.p["stand_tilt_deg"]))
        # judged after every physics step (1 ms): feet_off: since when no foot has touched the floor (before the hand
        # support); support_t0: the start of the hand support's feet-free phase; foot_t: each foot's last floor
        # contact; first_foot_t: the first foot's touchdown of the landing being judged
        self.trackers = {"feet_off": None, "support_t0": None, "foot_t": [-1.0, -1.0], "first_foot_t": None,
                         "min_dev_deg": 180.0, "landed": False}

    def facing_dev(self, w, body):
        """Degrees between the body's forward (x) axis, levelled, and -x."""
        f = w.d.xmat[body].reshape(3, 3)[:, 0]
        n = math.hypot(f[0], f[1])
        if n < 1e-6:
            return 180.0
        return math.degrees(math.acos(max(-1.0, min(1.0, -f[0] / n))))

    def substep(self, w, ref):
        p, tr = self.p, self.trackers
        if not (ref.failed or ref.success):              # the fall rule, also after every physics step (1 ms):
            z = float(w.d.qpos[w.robot.fq + 2])            # a touch shorter than a control step is not missed
            bad = ref.parts_touching(ref.ground) - set(self.legal_ground)
            if z < self.fall_z:
                return ref.fail("fell", pelvis_z=round(z, 3))
            if bad:
                return ref.fail("fell", on_the_ground=sorted(bad))
        half = p["area_m"] / 2
        pts = ref.contact_points(ref.robot_mask, ref.ground)
        if len(pts) and (np.abs(pts[:, :2]) > half + 1e-9).any():
            return ref.fail("outside the floor area")
        parts = ref.parts_touching(ref.ground)
        feet = parts & {"left_foot", "right_foot"}
        hands = parts & {"left_hand", "right_hand"}
        now = round(ref.time, 4)
        if not ref.has("hand support"):
            tr["feet_off"] = None if feet else (now if tr["feet_off"] is None else tr["feet_off"])
            if hands and not feet:
                u = w.d.xmat[w.robot.torso].reshape(3, 3)[:, 2]
                dev = math.degrees(math.acos(max(-1.0, min(1.0, -u[2]))))
                tr["min_dev_deg"] = round(min(tr["min_dev_deg"], dev), 1)
                if dev <= p["max_dev_deg"]:
                    tr["support_t0"] = tr["feet_off"]
                    ref.stage("hand support", dev_deg=round(dev, 1))
            return
        if not tr["landed"]:
            for i, s in enumerate(("left_foot", "right_foot")):
                if s in feet:
                    tr["foot_t"][i] = now
            down = [now - t <= p["foot_gap_s"] + 1e-9 for t in tr["foot_t"]]
            if not any(down):                             # both feet off (for more than foot_gap_s): no landing yet
                tr["first_foot_t"] = None
                if now - tr["support_t0"] > p["hand_support_max_s"] + 1e-9:
                    return ref.fail("not a round-off: the hand support lasted too long",
                                    support_s=round(now - tr["support_t0"], 3))
                return
            if tr["first_foot_t"] is None:
                tr["first_foot_t"] = now
                ref.metrics["hand_support_s"] = round(now - tr["support_t0"], 3)
            if not (all(down) and min(tr["foot_t"]) >= tr["first_foot_t"]):
                if now - tr["first_foot_t"] > p["two_feet_s"] + 1e-9:
                    return ref.fail("not a two-foot landing")
                return
            tr["landed"] = True
            if hands:
                return ref.fail("hand on the floor at the landing")
            dp, dt = self.facing_dev(w, w.robot.pelvis), self.facing_dev(w, w.robot.torso)
            ref.metrics["landing_facing_dev_deg"] = round(max(dp, dt), 1)
            if max(dp, dt) > p["face_dev_deg"]:
                return ref.fail("did not land facing back", pelvis_dev_deg=round(dp, 1), torso_dev_deg=round(dt, 1))
            ref.stage("landing")
            return
        if hands:
            return ref.fail("hand on the floor after the landing")

    def step(self, w, ref):
        p = self.p
        if not ref.has("landing"):
            return
        still = ref.standing(max_speed=p["stand_still_m_s"], min_upright=self.min_upright)
        if ref.hold("stand", still, p["stand_s"]):
            if ref.stage("stand"):
                ref.succeed()

    def privileged(self, w):
        u = w.d.xmat[w.robot.torso].reshape(3, 3)[:, 2]
        return {"pelvis": w.pelvis().tolist(), "com": w.com().tolist(),
                "torso_down_dev_deg": math.degrees(math.acos(max(-1.0, min(1.0, -float(u[2]))))),
                "facing_back_dev_deg": self.facing_dev(w, w.robot.pelvis), "landed": self.trackers.get("landed")}
